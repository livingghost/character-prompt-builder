"""Generation-owned uploads and cleanup recovery through the synthetic contract."""
from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import dispatch
import execution_contract as c
import execution_lifecycle as accounting
import production_case_fixtures as fixtures
import production_execution as execution
import production_store as store
import production_workflow as workflow
import transport_contract
import transport_synthetic as transport
from production_diagnostics import ProductionError
from test_production_execution import decisions


class UploadedInputLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        case = fixtures.create(base / 'studio', base / 'runtime', with_upscale=True)
        self.root = case['root']
        self.task = fixtures.upscale_task(self.root)
        self.run = workflow.prepare(self.root, self.task)['run']
        self.decision = decisions(self.root, self.run)

    def call(self):
        return execution.execute(self.root, self.run, decisions_file=self.decision)

    def rows(self):
        return store.event_rows(self.root, self.run)

    def journal(self):
        claim = workflow.find(self.rows(), 'dispatch-claim')
        return dispatch.RunJournal.open(c.local(self.root, claim['data']['journal']))

    def test_new_generation_uploads_afresh_and_deletes_after_output_capture(self):
        actual_delete = transport.send_delete
        local_source = self.root / 'upscale/source.png'
        source_sha = c.sha256_file(local_source)

        def delete(*args, **kwargs):
            rows = self.rows()
            captured = [row for row in rows if row['event'] == 'candidate']
            self.assertEqual(len(captured), 1)
            output = captured[0]['data']['files'][0]
            self.assertEqual(c.digest(c.object_read(workflow.run_dir(self.root, self.run), output['sha256'])), output['sha256'])
            self.assertEqual(accounting.all_states(self.root, run=self.run)[0]['captured_outputs'], 1)
            return actual_delete(*args, **kwargs)

        with patch.object(transport, 'upload_media', wraps=transport.upload_media) as upload, \
                patch.object(transport, 'send_delete', side_effect=delete) as cleanup:
            first = self.call()
            first_id = c.load(self.journal().path / 'upload-001.json')['provider_id']
            first_run = self.run
            self.run = workflow.prepare(self.root, self.task)['run']
            self.assertNotEqual(first_run, self.run)
            self.decision = decisions(self.root, self.run)
            second = self.call()
            second_id = c.load(self.journal().path / 'upload-001.json')['provider_id']
        self.assertNotEqual(first_id, second_id)
        self.assertEqual((upload.call_count, cleanup.call_count), (2, 2))
        self.assertEqual(first['runs'][0]['cleanup']['state'], 'complete')
        self.assertEqual(second['runs'][0]['cleanup']['state'], 'complete')
        self.assertEqual(c.sha256_file(local_source), source_sha)
        plan = execution.compiled(self.root, self.run)[6]
        self.assertEqual(plan['external_effects'], [
            {'operation': 'upload', 'count': 1}, {'operation': 'send', 'count': 1, 'outputs': 1},
            {'operation': 'delete', 'count': 1}])

    def test_failed_delete_is_settled_once_and_leaves_the_image_ready_for_review(self):
        refusal = transport_contract.Refused('Synthetic missing deletion target', {'errors': [{'code': 'fixture-not-found'}]})
        with patch.object(transport, 'send_delete', side_effect=refusal) as delete:
            initial = self.call()
        self.assertEqual(delete.call_count, 1)
        self.assertEqual(initial['runs'][0]['capture'], 'complete')
        self.assertEqual(initial['runs'][0]['cleanup']['state'], 'failed')
        self.assertEqual(initial['runs'][0]['cleanup']['deleted'], 0)
        self.assertTrue(initial['execution_completed'])
        self.assertEqual(initial['runs'][0]['next_action']['command'], 'draft-review')
        self.assertIn('INPUT_CLEANUP_FAILED', [item['code'] for item in initial['warnings']])
        before = [row for row in self.rows() if row['event'] in {'candidate', 'execution-result'}]
        (self.root / 'upscale/source.png').unlink()
        with patch.object(transport, 'upload_media', side_effect=AssertionError('Cleanup must not upload')), \
                patch.object(transport, 'send', side_effect=AssertionError('Cleanup must not generate')), \
                patch.object(dispatch, 'acquire', side_effect=AssertionError('Captured outputs need no acquisition')), \
                patch.object(transport, 'send_delete', side_effect=AssertionError('A failed delete is never repeated')), \
                patch.object(transport, 'lookup_delete', side_effect=AssertionError('A known failure needs no lookup')):
            recovered = execution.resume(self.root, self.run)
        self.assertEqual(recovered['runs'][0]['cleanup']['state'], 'failed')
        self.assertEqual(recovered['runs'][0]['next_action']['command'], 'draft-review')
        self.assertTrue(recovered['execution_completed'])
        self.assertEqual([row for row in self.rows() if row['event'] in {'candidate', 'execution-result'}], before)
        self.assertEqual(accounting.summary(self.root)['submissions'], 1)

    def test_lost_delete_response_is_looked_up_using_its_saved_request(self):
        actual_delete = transport.send_delete

        def lose_response(*args, **kwargs):
            self.assertTrue((self.journal().path / 'delete-001-request.json').is_file())
            actual_delete(*args, **kwargs)
            raise TimeoutError('Synthetic lost deletion response')

        with patch.object(transport, 'send_delete', side_effect=lose_response):
            initial = self.call()
        self.assertEqual(initial['runs'][0]['cleanup']['state'], 'outcome_unknown')
        request = c.load(self.journal().path / 'delete-001-request.json')
        identifier = c.load(self.journal().path / 'upload-001.json')['provider_id']
        (self.root / 'upscale/source.png').unlink()
        with patch.object(transport, 'send_delete', side_effect=AssertionError('Unknown deletion is never repeated')), \
                patch.object(transport, 'send', side_effect=AssertionError('No regeneration')), \
                patch.object(transport, 'upload_media', side_effect=AssertionError('No upload')), \
                patch.object(transport, 'lookup_delete', wraps=transport.lookup_delete) as lookup:
            recovered = execution.resume(self.root, self.run)
        self.assertEqual(lookup.call_args.args[0], request)
        self.assertEqual(lookup.call_args.kwargs['provider_id'], identifier)
        self.assertEqual(recovered['runs'][0]['cleanup']['state'], 'complete')
        self.assertEqual(len([row for row in self.rows() if row['event'] == 'external-step'
                              and row['data']['operation'] == 'delete']), 1)
        self.assertEqual(len([row for row in self.rows() if row['event'] == 'candidate']), 1)

    def test_unknown_delete_without_answer_stays_pending_and_keeps_outputs(self):
        with patch.object(transport, 'send_delete', side_effect=TimeoutError('Synthetic uncertain deletion')):
            self.call()
        with patch.object(transport, 'send_delete', side_effect=AssertionError('Never repeat an unknown delete')), \
                patch.object(transport, 'lookup_delete', return_value=None) as lookup, \
                patch.object(transport, 'send', side_effect=AssertionError('Never regenerate')):
            result = execution.resume(self.root, self.run)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(result['runs'][0]['cleanup']['state'], 'outcome_unknown')
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(result['runs'][0]['next_action']['command'], 'resume')
        self.assertEqual(len([row for row in self.rows() if row['event'] == 'external-step'
                              and row['data']['operation'] == 'delete']), 1)
        self.assertFalse(result['execution_completed'])

    def test_generation_processing_holds_inputs_until_final_outputs_are_saved(self):
        actual_send = transport.send

        def processing(*args, **kwargs):
            actual_send(*args, **kwargs)
            return {'data': [{'id': args[0]['request_id'], 'pending': True}]}

        with patch.object(transport, 'send', side_effect=processing), patch.object(transport, 'send_delete') as delete:
            initial = self.call()
            delete.assert_not_called()
        self.assertEqual(initial['runs'][0]['cleanup']['state'], 'waiting')
        with patch.object(transport, 'send', side_effect=AssertionError('Resume must use the original task')), \
                patch.object(transport, 'upload_media', side_effect=AssertionError('Same run retains its input receipt')), \
                patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
            final = execution.resume(self.root, self.run)
        self.assertTrue(final['execution_completed'])
        self.assertEqual(delete.call_count, 1)

    def test_terminal_answer_with_uncaptured_output_retains_input_until_capture_recovers(self):
        with patch.object(dispatch, 'inline_image', side_effect=ValueError('Synthetic temporary capture failure')), \
                patch.object(transport, 'send_delete') as delete:
            initial = self.call()
            delete.assert_not_called()
        self.assertEqual(initial['runs'][0]['submission'], 'acknowledged')
        self.assertEqual(initial['runs'][0]['cleanup']['state'], 'waiting')
        with patch.object(transport, 'send', side_effect=AssertionError('No second generation')), \
                patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
            final = execution.resume(self.root, self.run)
        self.assertTrue(final['execution_completed'])
        self.assertEqual(delete.call_count, 1)

    def test_terminal_generation_refusal_releases_owned_input(self):
        answer = {'errors': [{'code': 'synthetic-generation-refused', 'message': 'A fixture rejection.'}]}
        with patch.object(transport, 'send', return_value=answer), \
                patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
            result = self.call()
        self.assertEqual(delete.call_count, 1)
        self.assertEqual(result['runs'][0]['cleanup']['state'], 'complete')
        self.assertEqual(result['runs'][0]['candidates'], [])

    def test_failed_cleanup_does_not_hide_or_prevent_output_registration_recovery(self):
        refusal = transport_contract.Refused('Synthetic deletion failure', {'errors': [{'code': 'fixture-refusal'}]})
        with patch('studio.iterate', side_effect=OSError('Synthetic unavailable projection')), \
                patch.object(transport, 'send_delete', side_effect=refusal):
            initial = self.call()
        self.assertEqual(initial['runs'][0]['cleanup']['state'], 'failed')
        self.assertEqual(initial['runs'][0]['registration'], 'projection-missing')
        self.assertEqual(initial['runs'][0]['next_action']['command'], 'resume')
        self.assertFalse(initial['execution_completed'])
        with patch.object(transport, 'send', side_effect=AssertionError('Never regenerate')), \
                patch.object(transport, 'send_delete', side_effect=AssertionError('Never repeat a failed delete')):
            recovered = execution.resume(self.root, self.run)
        self.assertEqual(recovered['runs'][0]['registration'], 'registered')
        self.assertEqual(recovered['runs'][0]['cleanup']['state'], 'failed')
        self.assertTrue(recovered['execution_completed'])
        self.assertEqual(recovered['runs'][0]['next_action']['command'], 'draft-review')

    def test_cleanup_boundary_rejects_an_identifier_not_owned_by_the_run(self):
        with patch.object(transport, 'send_delete', side_effect=transport_contract.Refused('Fixture refusal', {'errors': []})):
            self.call()
        claim = workflow.find(self.rows(), 'dispatch-claim')
        journal = self.journal()
        service = execution.compiled(self.root, self.run)[7]['service']
        path = journal.write('ownership-test-request.json', transport.prepare_delete('unowned-fixture-id', service))
        witness = workflow.file_record(self.root, workflow.run_dir(self.root, self.run), path.relative_to(self.root).as_posix())
        with self.assertRaises(ProductionError) as caught:
            accounting.begin_cleanup_step(self.root, self.run, claim['data']['authorizations'][0], claim=claim['sha256'],
                upload_index=0, provider_id='unowned-fixture-id', request=witness)
        self.assertEqual(caught.exception.diagnostic.code, 'CLEANUP_OWNERSHIP_REQUIRED')

    def test_journal_request_naming_another_input_names_its_restoration(self):
        self.call()
        contract = self.journal().path / 'request-contract.json'
        value = c.load(contract)
        value['media'][0]['sha256'] = '0' * 64
        fixtures.write(contract, value)
        item = execution.status(self.root, self.run)['runs'][0]
        diagnostic = item['diagnostics'][0]
        self.assertEqual((item['integrity'], diagnostic['code'], diagnostic['pointer']),
                         ('blocked', 'CLEANUP_OWNERSHIP_REQUIRED', '$.media[0]'))
        self.assertEqual(diagnostic['actual']['sha256'], '0' * 64)
        self.assertIn(str(workflow.run_dir(self.root, self.run) / 'request-contract.json'), diagnostic['required_action'])
        self.assertEqual(item['next_action']['reason'], diagnostic['required_action'])

    def test_transport_without_deletion_keeps_outputs_and_reports_retained_inputs(self):
        adapter = SimpleNamespace(**{key: value for key, value in vars(transport).items()
            if key not in {'prepare_delete', 'send_delete', 'lookup_delete'}})
        transport_contract.check(adapter)
        with patch.object(transport_contract, 'load', return_value=adapter):
            self.run = workflow.prepare(self.root, self.task)['run']
            self.decision = decisions(self.root, self.run)
            result = self.call()
            again = execution.resume(self.root, self.run)
        for report in (result, again):
            self.assertTrue(report['execution_completed'])
            self.assertEqual(report['runs'][0]['cleanup']['state'], 'unsupported')
            self.assertEqual(report['runs'][0]['cleanup']['retained'], 1)
            self.assertEqual(report['runs'][0]['cleanup']['deleted'], 0)
            self.assertEqual(report['runs'][0]['next_action']['command'], 'draft-review')
            self.assertIn('INPUT_CLEANUP_UNSUPPORTED', [item['code'] for item in report['warnings']])
        self.assertFalse(any(row['event'] == 'external-step' and row['data']['operation'] == 'delete'
                             for row in self.rows()))


class TwoInputCleanupTests(unittest.TestCase):
    def setUp(self):
        import prepare_generation_references as references
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = fixtures.create(base / 'studio', base / 'runtime')['root']
        selections = []
        for index, colour in enumerate((b'\x20\x50\x90', b'\xb0\x70\x30')):
            path = self.root / 'references' / f'palette-{index + 1}.png'
            c.atomic(path, transport._png(32, 32, colour))
            selections.append({'role': 'palette', 'source': {'kind': 'supplied-file',
                'reference_id': f'palette-{index + 1}', 'resolved_path': str(path)}})
        prepared = references.prepare_references(selections, model=fixtures.MODEL_ID,
                                                 output_dir=self.root / 'references/prepared')
        fixtures.write(self.root / 'references.json', prepared)
        task = c.load(self.root / 'task.json')
        task['generation']['references'] = 'references.json'
        fixtures.write(self.root / 'task.json', task)
        spec = c.load(self.root / 'spec.json')
        spec['render_intent']['execution_mode'] = 'reference-guided'
        fixtures.write(self.root / 'spec.json', spec)
        self.run = workflow.prepare(self.root, 'task.json')['run']
        self.decision = decisions(self.root, self.run)

    def call(self):
        return execution.execute(self.root, self.run, decisions_file=self.decision)

    def rows(self):
        return store.event_rows(self.root, self.run)

    def journal(self):
        return dispatch.RunJournal.open(c.local(self.root, workflow.find(self.rows(), 'dispatch-claim')['data']['journal']))

    def test_saved_upload_refusal_recovers_and_deletes_the_earlier_input_once(self):
        actual_upload = transport.upload_media
        uploads = []

        def second_refused(*args, **kwargs):
            if uploads:
                raise transport_contract.Refused('Synthetic second upload refusal', {'errors': [{'code': 'fixture-refusal'}]})
            value = actual_upload(*args, **kwargs)
            uploads.append(value['provider_id'])
            return value

        with patch.object(transport, 'upload_media', side_effect=second_refused), \
                patch.object(execution, '_record_no_effect', side_effect=OSError('Synthetic interruption after saved refusal')), \
                patch.object(transport, 'send', side_effect=AssertionError('An upload refusal prevents generation')):
            with self.assertRaises(OSError):
                self.call()
        self.assertTrue((self.journal().path / 'upload-002-refused.json').is_file())
        with patch.object(transport, 'upload_media', side_effect=AssertionError('No upload after saved refusal')), \
                patch.object(transport, 'send', side_effect=AssertionError('No generation after saved refusal')), \
                patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
            first = execution.resume(self.root, self.run)
            second = execution.resume(self.root, self.run)
        self.assertEqual(delete.call_count, 1)
        self.assertEqual(delete.call_args.kwargs['provider_id'], uploads[0])
        self.assertEqual(first['runs'][0]['cleanup']['state'], 'complete')
        self.assertEqual(second['runs'][0]['cleanup']['state'], 'complete')
        self.assertEqual(second['runs'][0]['next_action']['command'], 'repeat')
        self.assertEqual(accounting.summary(self.root)['submissions'], 0)

    def second_upload_unanswered(self) -> tuple[list[str], object]:
        """The first upload completes and the exchange of the second one ends without an answer."""
        actual_upload = transport.upload_media
        uploads = []

        def second_lost(*args, **kwargs):
            if uploads:
                raise TimeoutError('Synthetic lost answer of the second upload')
            value = actual_upload(*args, **kwargs)
            uploads.append(value['provider_id'])
            return value
        return uploads, second_lost

    def test_unknown_upload_releases_the_completed_input_and_keeps_the_unknown_one(self):
        uploads, upload = self.second_upload_unanswered()
        with patch.object(transport, 'upload_media', side_effect=upload), \
                patch.object(transport, 'send', side_effect=AssertionError('An unknown upload prevents generation')), \
                patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
            with self.assertRaises(ProductionError) as caught:
                self.call()
        diagnostic = caught.exception.diagnostic
        self.assertEqual((diagnostic.code, diagnostic.details['steps']), ('REMOTE_OUTCOME_UNKNOWN', ['upload:1']))
        self.assertEqual([call.kwargs['provider_id'] for call in delete.call_args_list], uploads)
        item = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual((item['cleanup']['state'], item['cleanup']['uploaded'], item['cleanup']['deleted']), ('complete', 1, 1))
        self.assertEqual(item['effects'], [{'step': 'upload:0', 'operation': 'upload', 'result': 'executed'},
                                           {'step': 'upload:1', 'operation': 'upload', 'result': 'unanswered'},
                                           {'step': 'delete:0', 'operation': 'delete', 'result': 'executed'}])
        self.assertEqual(item['next_action']['command'], 'repeat')
        self.assertEqual(diagnostic.details['next_action'], item['next_action'])
        self.assertEqual(diagnostic.details['cleanup']['state'], 'complete')
        rows = self.rows()
        with patch.object(transport, 'upload_media', side_effect=AssertionError('No upload')), \
                patch.object(transport, 'send', side_effect=AssertionError('No generation')), \
                patch.object(transport, 'send_delete', side_effect=AssertionError('No second deletion')), \
                patch.object(transport, 'lookup_delete', side_effect=AssertionError('A settled deletion needs no lookup')):
            with self.assertRaises(ProductionError) as again:
                execution.resume(self.root, self.run)
        self.assertEqual(again.exception.diagnostic.code, 'REMOTE_OUTCOME_UNKNOWN')
        self.assertEqual(self.rows(), rows)
        self.assertEqual(accounting.summary(self.root)['submissions'], 0)

    def test_unknown_upload_of_an_ended_operation_is_recorded_before_the_cleanup(self):
        uploads, upload = self.second_upload_unanswered()
        # The operation ends without recording its stop, as when its process is killed.
        with patch.object(execution, '_record_execution_failure'), \
                patch.object(transport, 'upload_media', side_effect=upload), \
                patch.object(transport, 'send_delete', side_effect=AssertionError('No deletion while the uploader runs')):
            with self.assertRaises(ProductionError):
                self.call()
        self.assertEqual(execution.status(self.root, self.run)['runs'][0]['next_action']['command'], 'status')
        with patch.object(execution, '_sender_alive', return_value=False):
            action = execution.status(self.root, self.run)['runs'][0]['next_action']
            self.assertEqual(action['command'], 'resume')
            with patch.object(transport, 'upload_media', side_effect=AssertionError('No upload')), \
                    patch.object(transport, 'send', side_effect=AssertionError('No generation')), \
                    patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
                with self.assertRaises(ProductionError) as caught:
                    execution.resume(self.root, self.run)
            self.assertEqual(caught.exception.diagnostic.code, 'REMOTE_OUTCOME_UNKNOWN')
            self.assertEqual([call.kwargs['provider_id'] for call in delete.call_args_list], uploads)
            stopped = [row['data'] for row in self.rows() if row['event'] == 'execution-outcome']
            self.assertEqual([(row['code'], row['unknown_uploads']) for row in stopped],
                             [('REMOTE_OUTCOME_UNKNOWN', ['upload:1'])])
            self.assertEqual(execution.status(self.root, self.run)['runs'][0]['next_action']['command'], 'repeat')

    def test_failed_input_is_not_retried_while_untouched_input_cleanup_resumes(self):
        begin = accounting.begin_cleanup_step

        def pause_second(*args, **kwargs):
            if kwargs['upload_index'] == 1:
                raise OSError('Synthetic interruption before second deletion boundary')
            return begin(*args, **kwargs)

        refusal = transport_contract.Refused('Synthetic missing first target', {'errors': [{'code': 'fixture-not-found'}]})
        with patch.object(accounting, 'begin_cleanup_step', side_effect=pause_second), \
                patch.object(transport, 'send_delete', side_effect=refusal) as initial_delete:
            with self.assertRaises(OSError):
                self.call()
        self.assertEqual(initial_delete.call_count, 1)
        pending = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual(pending['cleanup']['state'], 'pending')
        self.assertEqual([item['state'] for item in pending['cleanup']['items']], ['failed', 'pending'])
        self.assertEqual(pending['next_action']['command'], 'resume')
        second_id = c.load(self.journal().path / 'upload-002.json')['provider_id']
        with patch.object(transport, 'upload_media', side_effect=AssertionError('No new uploads')), \
                patch.object(transport, 'send', side_effect=AssertionError('No generation resend')), \
                patch.object(dispatch, 'acquire', side_effect=AssertionError('The outputs are already saved')), \
                patch.object(transport, 'send_delete', wraps=transport.send_delete) as delete:
            recovered = execution.resume(self.root, self.run)
            settled = execution.resume(self.root, self.run)
        self.assertEqual(delete.call_count, 1)
        self.assertEqual(delete.call_args.kwargs['provider_id'], second_id)
        self.assertEqual(recovered['runs'][0]['cleanup']['state'], 'failed')
        self.assertEqual([item['state'] for item in settled['runs'][0]['cleanup']['items']], ['failed', 'deleted'])
        self.assertTrue(settled['execution_completed'])
        self.assertEqual(settled['runs'][0]['next_action']['command'], 'draft-review')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
