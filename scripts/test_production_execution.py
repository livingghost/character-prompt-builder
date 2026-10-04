"""Current execution contract, with real local PNG bytes and no paid service."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_execution as execution
import production_workflow as workflow
import production_store as store
import reservation_lifecycle as accounting
import transport_synthetic
from production_diagnostics import ProductionError


def decisions(root: Path, run: str) -> str:
    from production_request import assessment_source
    from production_fixtures import ACTOR
    value = execution.draft_execution(root, run, 'fixture-grant')
    authority = store.authority(root, workflow.load_run(root, run)[1]['task']['task_id'])
    for request in value['authorizations']:
        request['reason'] = 'Explicit synthetic fixture decision. Not user consent.'
        if request['operation'] == 'submit':
            request['request_decision']['principal_approval'] = assessment_source(root, request['payload'],
                principal=authority['issuer'], path=authority['evidence']['path'], locator='whole')
            request['request_decision']['rendition_review'].update(conclusion='satisfied',
                reason='Synthetic protocol fixture checks exact bytes, not image quality.')
    path = f'decisions-{run}.json'
    fixtures.write(root / path, value)
    return path


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = self.case['root']
        self.prepared = workflow.prepare(self.root, 'task.json')
        self.run = self.prepared['run']

    def test_execute_registers_candidate_and_settles_once(self):
        path = decisions(self.root, self.run)
        result = execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(len(result['runs'][0]['candidates']), 1)
        budget = accounting.budget(self.root)['grants'][0]
        self.assertEqual(budget['consumed']['uses'], 1)
        self.assertEqual(budget['consumed']['outputs'], 1)
        self.assertEqual(budget['outstanding_reserved']['uses'], 0)
        self.assertEqual(budget['consumed']['cost'], {'USD': '0'})
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Resume must not send')):
            again = execution.resume(self.root, self.run)
        self.assertEqual(len(again['runs'][0]['candidates']), 1)
        self.assertEqual(accounting.budget(self.root)['grants'][0]['consumed'], budget['consumed'])

    def test_missing_authority_has_no_reservation_or_claim(self):
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_REQUIRED')
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(accounting.all_states(self.root), [])
        # The dispatch journal is written at the claim boundary, so a refused execute leaves none.
        self.assertEqual([path for path in (self.root / 'runs').glob('*') if path.is_dir()], [])

    def test_missing_direction_does_not_commit_submit_or_reserve(self):
        path = decisions(self.root, self.run)
        value = c.load(self.root / path)
        value['authorizations'] = value['authorizations'][1:]
        fixtures.write(self.root / path, value)
        with self.assertRaises(ProductionError):
            execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_insufficient_budget_rolls_back_receipts_and_claim(self):
        path = decisions(self.root, self.run)
        document = c.load(self.root / 'fixture-authority.json')
        document['grants'][0]['limits']['uses'] = 0
        fixtures.write(self.root / 'authority-update.json', document)
        prior = store.authority_record(self.root, document['task_id'])
        store.import_authority(self.root, 'authority-update.json', expected=prior['sha256'])
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'BUDGET_LIMIT_EXCEEDED')
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_timeout_retains_reservation_and_resume_never_sends(self):
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic timeout')) as send:
            result = execution.execute(self.root, self.run, decisions_file=path)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(result['runs'][0]['submission'], 'outcome_unknown')
        state = accounting.all_states(self.root)[0]
        self.assertFalse(accounting.releasable(state))
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            again = execution.resume(self.root, self.run)
        self.assertEqual(again['runs'][0]['submission'], 'outcome_unknown')
        self.assertEqual(len(accounting.all_states(self.root)), 1)
        # The synthetic service never received the request, so its lookup has no answer.
        asked = [row['data'] for row in store.event_rows(self.root, self.run)
                 if row['event'] == 'execution-outcome' and row['data'].get('lookup')]
        self.assertEqual([item['lookup'] for item in asked], ['no-answer'])
        self.assertTrue(asked[0]['evidence'][0]['path'].endswith('/lookup-001.json'))
        self.assertEqual(again['runs'][0]['next_action']['command'], 'draft-outcome')

    def lost_answer(self):
        """A send the synthetic service carried out, whose answer never reached the dispatcher."""
        actual = transport_synthetic.send
        def lose(request, service, key):
            actual(request, service, key)
            raise TimeoutError('Synthetic answer loss after the service carried out the request')
        return lose

    def test_lost_answer_is_reconciled_through_provider_lookup(self):
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=self.lost_answer()) as send:
            first = execution.execute(self.root, self.run, decisions_file=path)
            self.assertEqual(first['runs'][0]['submission'], 'outcome_unknown')
            again = execution.resume(self.root, self.run)
            self.assertEqual(send.call_count, 1)
        item = again['runs'][0]
        self.assertTrue(again['execution_completed'])
        self.assertEqual((item['submission'], item['capture'], item['registration']), ('acknowledged', 'complete', 'registered'))
        self.assertEqual(len(item['candidates']), 1)
        receipt = [row['data'] for row in store.event_rows(self.root, self.run)
                   if row['event'] == 'execution-outcome' and row['data']['submission'] == 'acknowledged']
        self.assertEqual([row['reconciled'] for row in receipt], ['provider-lookup'])
        names = {entry['path'].rsplit('/', 1)[1] for entry in receipt[0]['evidence']}
        self.assertTrue({'request.json', 'lookup-001.json', 'answer.json', 'transport-outcome.json'} <= names)
        self.assertEqual(accounting.budget(self.root)['grants'][0]['consumed']['uses'], 1)

    def test_evidenced_not_executed_statement_makes_reservation_releasable(self):
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic timeout')):
            execution.execute(self.root, self.run, decisions_file=path)
        execution.resume(self.root, self.run)
        statement = execution.draft_outcome(self.root, self.run)
        fixtures.write(self.root / 'provider-task-list.txt', 'Synthetic provider task export: no task with this identifier.\n')
        authority = store.authority(self.root, workflow.load_run(self.root, self.run)[1]['task']['task_id'])
        statement.update(actor=authority['issuer'], reason='The provider task list holds no task for this request.',
                         evidence={'path': 'provider-task-list.txt', 'sha256': c.sha256_file(self.root / 'provider-task-list.txt'),
                                   'locator': 'whole export'})
        fixtures.write(self.root / 'outcome.json', statement)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            result = execution.resume(self.root, self.run, outcome_file='outcome.json')
        item = result['runs'][0]
        self.assertEqual(item['submission'], 'not_executed')
        self.assertEqual(item['effects'], [{'step': 'send', 'operation': 'send', 'result': 'not_executed'}])
        self.assertTrue(item['reservation']['release_eligible'])
        self.assertEqual(item['next_action']['command'], 'draft-release')
        request = accounting.draft_release(self.root, self.run, item['reservation']['reservation_id'])
        request.update(actor=authority['issuer'], reason='The provider evidenced that the send was never executed.',
                       evidence=statement['evidence'])
        fixtures.write(self.root / 'release.json', request)
        self.assertTrue(accounting.release(self.root, self.run, 'release.json')['released'])
        self.assertEqual(accounting.budget(self.root)['grants'][0]['outstanding_reserved']['uses'], 0)

    def test_send_boundary_records_provider_identifiers_before_io(self):
        execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        rows = store.event_rows(self.root, self.run)
        send = next(row['data'] for row in rows if row['event'] == 'external-step' and row['data']['step'] == 'send')
        claim = workflow.find(rows, 'dispatch-claim')
        request = c.load(c.local(self.root, claim['data']['journal']) / 'request.json')
        self.assertEqual(send['identifiers'], [{'field': ['request_id'], 'value': request['request_id']}])
        outcome = next(row['data'] for row in rows if row['event'] == 'execution-outcome')
        self.assertIn('transport-outcome.json', {entry['path'].rsplit('/', 1)[1] for entry in outcome['evidence']})

    def test_interruption_before_send_boundary_is_reserved_not_unknown(self):
        begin = accounting.begin_step
        def interrupt(*args, **kwargs):
            if kwargs['step'] == 'send':
                raise OSError('Synthetic interruption before the durable send boundary')
            return begin(*args, **kwargs)
        with patch.object(accounting, 'begin_step', side_effect=interrupt), patch.object(transport_synthetic, 'send') as send:
            with self.assertRaises(OSError):
                execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
            send.assert_not_called()
        item = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual((item['submission'], item['send_started']), ('reserved', False))
        self.assertEqual(workflow.find(store.event_rows(self.root, self.run), 'execution-outcome')['data']['submission'], 'reserved')
        self.assertEqual(item['next_action']['command'], 'resume')
        self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])

    def test_send_in_progress_is_send_started(self):
        seen = []
        actual = transport_synthetic.send
        def observe(request, service, key):
            seen.append(execution.status(self.root, self.run)['runs'][0]['submission'])
            return actual(request, service, key)
        with patch.object(transport_synthetic, 'send', side_effect=observe):
            execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertEqual(seen, ['send_started'])

    def test_saved_answer_without_receipt_is_unknown_until_resume_registers_it(self):
        acknowledge = execution._acknowledge
        with patch.object(execution, '_acknowledge', side_effect=OSError('Synthetic receipt storage failure')):
            with self.assertRaises(OSError):
                execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        # The saved answer file alone is not a formal acknowledgement.
        self.assertEqual(execution.status(self.root, self.run)['runs'][0]['submission'], 'outcome_unknown')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')), \
                patch.object(execution, '_acknowledge', side_effect=acknowledge):
            result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        receipt = [row['data'] for row in store.event_rows(self.root, self.run)
                   if row['event'] == 'execution-outcome' and row['data']['submission'] == 'acknowledged']
        self.assertEqual([row['reconciled'] for row in receipt], ['saved-answer'])

    def test_duplicate_execute_is_not_repeat(self):
        path = decisions(self.root, self.run)
        execution.execute(self.root, self.run, decisions_file=path)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'DISPATCH_ALREADY_CLAIMED')

    def test_saved_response_recovered_after_candidate_transaction_failure(self):
        path = decisions(self.root, self.run)
        with patch.object(workflow, 'record_dispatch_results', side_effect=OSError('Synthetic disk error')):
            with self.assertRaises(OSError):
                execution.execute(self.root, self.run, decisions_file=path)
        self.assertFalse(any(row['event'] == 'candidate' for row in store.event_rows(self.root, self.run)))
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            result = execution.resume(self.root, self.run)
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(len(result['runs'][0]['candidates']), 1)

    def test_upscale_upload_cost_is_part_of_the_exact_execution_ceiling(self):
        base = Path(self.temp.name)
        case = fixtures.create(base / 'cost-studio', base / 'cost-runtime', with_upscale=True)
        root = case['root']
        task = fixtures.upscale_task(root)
        prepared = workflow.prepare(root, task)
        directory, document, _, _ = workflow.load_run(root, prepared['run'])
        plan = c.load(directory / 'execution-plan.json')
        self.assertEqual([item['operation'] for item in plan['external_effects']], ['upload', 'send'])
        self.assertEqual(plan['external_effects'][0]['cost']['amount'], '0')
        self.assertEqual(plan['external_effects'][1]['cost']['amount'], '0')
        self.assertEqual(plan['cost']['currency'], 'USD')
        self.assertEqual(plan['cost']['amount'], '0')

    def test_unknown_upload_cost_blocks_execute_without_reservation(self):
        base = Path(self.temp.name)
        case = fixtures.create(base / 'unknown-cost-studio', base / 'unknown-cost-runtime', with_upscale=True)
        root = case['root']
        task_path = fixtures.upscale_task(root)
        task = c.load(root / task_path)
        task['upscale'].pop('external_costs')
        fixtures.write(root / 'upscale/unknown-cost-task.json', task)
        prepared = workflow.prepare(root, 'upscale/unknown-cost-task.json')
        directory, _, _, _ = workflow.load_run(root, prepared['run'])
        plan = c.load(directory / 'execution-plan.json')
        self.assertIsNone(plan['cost'])
        self.assertIn('COST_UNCONFIRMED', {item['code'] for item in plan['readiness']['diagnostics']})
        with self.assertRaises(ProductionError) as caught:
            execution.execute(root, prepared['run'])
        self.assertEqual(caught.exception.diagnostic.code, 'COST_UNCONFIRMED')
        self.assertEqual(accounting.all_states(root), [])

    def test_invalid_upscale_dimensions_are_captured_but_not_completed(self):
        import base64
        base = Path(self.temp.name)
        case = fixtures.create(base / 'upscale-studio', base / 'upscale-runtime', with_upscale=True)
        root = case['root']
        task = fixtures.upscale_task(root)
        prepared = workflow.prepare(root, task)
        run = prepared['run']
        path = decisions(root, run)
        original_send = transport_synthetic.send

        def malformed(request, service, key):
            answer = original_send(request, service, key)
            # Source is 32x32 and scale=2, so the contract requires 64x64.
            answer['data'][0]['data'] = base64.b64encode(
                transport_synthetic._png(61, 64, b'\x70\x40\x20')
            ).decode('ascii')
            return answer

        with patch.object(transport_synthetic, 'send', side_effect=malformed):
            result = execution.execute(root, run, decisions_file=path)
        self.assertFalse(result['ok'])
        self.assertFalse(result['execution_completed'])
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(len(result['runs'][0]['candidates']), 1)
        self.assertIn('UPSCALE_OUTPUT_CONTRACT_MISMATCH', {item['code'] for item in result['warnings']})
        claim = workflow.find(store.event_rows(root, run), 'dispatch-claim')
        journal = c.local(root, claim['data']['journal']) / 'run.json'
        self.assertEqual(c.load(journal)['status'], 'capture-invalid')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Resume must not send')):
            again = execution.resume(root, run)
        self.assertFalse(again['execution_completed'])
        self.assertEqual(len(again['runs'][0]['candidates']), 1)

    def test_revocation_does_not_mutate_input(self):
        path = decisions(self.root, self.run)
        original = workflow.load_run(self.root, self.run)[1]['input_sha256']
        document = c.load(self.root / 'fixture-authority.json')
        document['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        fixtures.write(self.root / 'authority-update.json', document)
        prior = store.authority_record(self.root, document['task_id'])
        store.import_authority(self.root, 'authority-update.json', expected=prior['sha256'])
        self.assertEqual(workflow.assert_current(self.root, self.run)[1]['input_sha256'], original)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_REVOKED')
        self.assertEqual(accounting.all_states(self.root), [])



class ExternalEffectAccountingTests(unittest.TestCase):
    """Local fixture fees verify actual per-effect accounting, never provider billing."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        case=fixtures.create(base/'studio',base/'runtime',with_upscale=True)
        self.root=case['root']
        self.task_path=fixtures.upscale_task(self.root)
        task=c.load(self.root/self.task_path)
        task['upscale']['cost'].update(amount='0.4',basis='Synthetic send upper bound for fee-accounting tests.')
        task['upscale']['external_costs'][0].update(amount='0.2',basis='Synthetic upload upper bound, independent of send.')
        fixtures.write(self.root/self.task_path,task)
        document=c.load(self.root/'fixture-authority.json')
        document['grants'][0]['limits']['cost']={'currency':'USD','amount':'10'}
        fixtures.write(self.root/'fixture-authority.json',document)
        self.run=workflow.prepare(self.root,self.task_path)['run']
        self.decision=decisions(self.root,self.run)
        self.original_upload=transport_synthetic.upload_bytes
        self.original_send=transport_synthetic.send

    def uploader(self,amount='0.1'):
        def upload(*args,**kwargs):
            value=self.original_upload(*args,**kwargs)
            value['usage']=None if amount is None else {'currency':'USD','amount':amount,'final':True}
            value['response']['synthetic_charge']=value['usage']
            return value
        return upload

    def sender(self,amount='0.3'):
        def send(*args,**kwargs):
            value=self.original_send(*args,**kwargs)
            value['usage']=None if amount is None else {'currency':'USD','amount':amount,'final':True}
            return value
        return send

    def budget(self):
        return accounting.budget(self.root)['grants'][0]

    def test_upload_and_send_actuals_are_added_once(self):
        with patch.object(transport_synthetic,'upload_bytes',side_effect=self.uploader()),patch.object(transport_synthetic,'send',side_effect=self.sender()):
            execution.execute(self.root,self.run,decisions_file=self.decision)
        group=self.budget()
        self.assertEqual(group['consumed']['cost'],{'USD':'0.4'})
        self.assertEqual(group['outstanding_reserved']['cost'],{})
        self.assertEqual(group['consumed']['uses'],1)
        self.assertEqual(len(group['reservations'][0]['effect_results']),2)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No repeat send')),patch.object(transport_synthetic,'upload_bytes',side_effect=AssertionError('No repeat upload')):
            execution.resume(self.root,self.run)
        self.assertEqual(self.budget()['consumed'],group['consumed'])

    def test_unknown_upload_charge_is_not_zero_when_send_cost_is_known(self):
        with patch.object(transport_synthetic,'upload_bytes',side_effect=self.uploader(None)),patch.object(transport_synthetic,'send',side_effect=self.sender()):
            execution.execute(self.root,self.run,decisions_file=self.decision)
        group=self.budget()
        self.assertEqual(group['consumed']['cost'],{'USD':'0.3'})
        self.assertEqual(group['outstanding_reserved']['cost'],{'USD':'0.3'})
        self.assertEqual(len(group['unknown_cost_reservations']),1)
        self.assertEqual(group['reservations'][0]['status'],'partially_settled')
        self.assertFalse(group['reservations'][0]['release_eligible'])

    def test_known_upload_fee_survives_send_timeout(self):
        with patch.object(transport_synthetic,'upload_bytes',side_effect=self.uploader()),patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic send timeout')):
            result=execution.execute(self.root,self.run,decisions_file=self.decision)
        self.assertEqual(result['runs'][0]['submission'],'outcome_unknown')
        group=self.budget()
        self.assertEqual(group['consumed']['cost'],{'USD':'0.1'})
        self.assertEqual(group['outstanding_reserved']['cost'],{'USD':'0.5'})
        self.assertEqual(group['consumed']['uses'],0)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No repeat send')),patch.object(transport_synthetic,'upload_bytes',side_effect=AssertionError('No repeat upload')):
            execution.resume(self.root,self.run)

    def test_upload_overrun_is_not_truncated_and_blocks_first_send(self):
        with patch.object(transport_synthetic,'upload_bytes',side_effect=self.uploader('0.25')),patch.object(transport_synthetic,'send') as send:
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run,decisions_file=self.decision)
            send.assert_not_called()
        self.assertEqual(caught.exception.diagnostic.code,'EXTERNAL_COST_LIMIT_EXCEEDED')
        self.assertEqual(self.budget()['consumed']['cost'],{'USD':'0.25'})
        self.assertFalse(self.budget()['reservations'][0]['release_eligible'])

    def test_completed_upload_is_reused_when_send_never_started(self):
        begin=accounting.begin_step
        def interrupt(*args,**kwargs):
            if kwargs['step']=='send':
                raise OSError('Synthetic interruption before the durable send boundary')
            return begin(*args,**kwargs)
        with patch.object(transport_synthetic,'upload_bytes',side_effect=self.uploader()) as upload,patch.object(accounting,'begin_step',side_effect=interrupt):
            with self.assertRaises(OSError):
                execution.execute(self.root,self.run,decisions_file=self.decision)
        self.assertEqual(upload.call_count,1)
        item=execution.status(self.root,self.run)['runs'][0]
        self.assertEqual(item['submission'],'reserved')
        self.assertEqual(item['effects'],[{'step':'upload:0','operation':'upload','result':'executed'}])
        with patch.object(transport_synthetic,'upload_bytes',side_effect=AssertionError('Do not upload twice')),patch.object(transport_synthetic,'send',side_effect=self.sender()) as send:
            result=execution.resume(self.root,self.run)
        self.assertEqual(send.call_count,1)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.budget()['consumed']['cost'],{'USD':'0.4'})

    def test_refused_upload_is_recorded_as_rejected_and_releasable(self):
        import transport_contract
        refusal=transport_contract.Refused('Synthetic refusal of the upload',{'errors':[{'code':'synthetic-upload-refused'}]})
        with patch.object(transport_synthetic,'upload_bytes',side_effect=refusal),patch.object(transport_synthetic,'send') as send:
            result=execution.execute(self.root,self.run,decisions_file=self.decision)
            send.assert_not_called()
        self.assertFalse(result['execution_completed'])
        item=result['runs'][0]
        self.assertEqual(item['submission'],'reserved')
        self.assertEqual(item['effects'],[{'step':'upload:0','operation':'upload','result':'rejected'}])
        self.assertTrue(item['reservation']['release_eligible'])
        self.assertEqual(item['next_action']['command'],'draft-release')
        outcome=workflow.find(store.event_rows(self.root,self.run),'execution-outcome')['data']
        self.assertEqual((outcome['submission'],outcome['code']),('reserved','PROVIDER_REJECTION'))
        self.assertTrue(outcome['evidence'][0]['path'].endswith('/upload-001-refused.json'))
        self.assertEqual(self.budget()['consumed']['cost'],{})

    def test_unanswered_upload_is_not_reissued_by_resume(self):
        with patch.object(transport_synthetic,'upload_bytes',side_effect=TimeoutError('Synthetic upload timeout')):
            with self.assertRaises(TimeoutError):
                execution.execute(self.root,self.run,decisions_file=self.decision)
        with patch.object(transport_synthetic,'upload_bytes',side_effect=AssertionError('No repeated upload')),patch.object(transport_synthetic,'send',side_effect=AssertionError('No send after unknown upload')):
            result=execution.resume(self.root,self.run)
        self.assertFalse(result['execution_completed'])
        self.assertFalse(self.budget()['reservations'][0]['release_eligible'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
