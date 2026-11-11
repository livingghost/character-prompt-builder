"""Authored results retain exact revisions, independently recorded uses and drafts."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_authored as authored
import production_fixtures as fixtures
import production_inputs as inputs
import production_workflow as workflow
import production_workspace as workspace
import work_ledger


class AuthoredRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'studio'
        self.root.mkdir()
        self.enterContext(fixtures.scratch_home(base / 'home'))
        task_id = work_ledger.begin(self.root, 'Write a synthetic artifact.', ['Compose the requested text.'])['task_id']
        self.task = {'task_id': task_id, 'route': 'development', 'features': [], 'sources': [],
            'delivery': {'path': 'delivery.txt', 'translation_notes': 'Keep the authored text.'},
            'criteria': [{'id': 'meaning', 'strength': 'hard', 'text': 'The text describes an empty market.'}],
            'world_views': []}
        fixtures.task(self.root, self.task)
        self.write('task.json', self.task)
        self.write('delivery.txt', 'An empty market after the rain.\n')
        self.counter = 0

    def write(self, path, value):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value.encode('utf-8') if isinstance(value, str) else c.encoded(value))

    def choices(self, *, requirements=None, completion_state=None):
        if requirements is not None:
            self.task['authored'] = {'requirements': requirements}
        if completion_state is not None:
            self.task.setdefault('authored', {})['completion_state'] = completion_state
        self.write('task.json', self.task)
        self.counter += 1
        result = inputs.draft_inputs(self.root, 'task.json', 'edit-' + str(self.counter))
        selected = c.load(self.root / result['choices_file'])
        selected['reading']['reading_key'] = c.load(self.root / self.task['route_reading'])['reading_key']
        self.write(result['choices_file'], selected)
        return result['choices_file'], selected

    def delivery(self, run, *, text=None):
        loaded = workflow.read_run(self.root, run)
        text = loaded.consumer['instructions'] if text is None else text
        self.write('host-presentation.json', {'shown': {'text': text}})
        self.write('delivered.json', {'recipient': 'Synthetic recipient', 'channel': 'Synthetic presentation',
            'evidence': {'path': 'host-presentation.json', 'field': ['shown', 'text']},
            'note': 'The synthetic host record contains the actually presented text.'})
        return workflow.deliver(self.root, run, 'delivered.json')

    def review(self, run, *, finding='pass'):
        value = workflow.draft_review(self.root, run)
        value.update(reviewer='Synthetic reviewer', observations=[
            {'evidence': 'candidate', 'locator': {'kind': 'whole'},
             'observation': 'The saved sentence names an empty market.',
             'interpretation': 'Synthetic assessment of the requested meaning.',
             'limitations': ['This is a text assessment, not an observed image.']}],
            checks=[{'criterion': 'meaning', 'verdict': finding, 'observation_indices': [0],
                     'reason': 'The synthetic reviewer assesses the saved sentence.'}],
            unresolved=['Revise the requested meaning.'] if finding == 'fail' else [],
            conclusion='Synthetic saved text assessment.')
        self.write('review.json', value)
        return workflow.review_authored(self.root, run, 'review.json')

    def finish(self, run):
        work_ledger.step_done(self.root, 1)
        return work_ledger.finish(self.root, run)

    def test_custom_authored_review_is_resumed_from_its_registered_location(self):
        path, _ = self.choices(requirements=['save', 'review'])
        run = workflow.save(self.root, path)['run']
        custom = 'work/authored-review.json'
        result = subprocess.run([sys.executable, str(Path(workflow.__file__)), 'draft-review',
            '--root', str(self.root), '--run', run, '--out', custom],
            capture_output=True, text=True, encoding='utf-8', env=dict(os.environ), check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), c.load(self.root / custom))
        before = (self.root / custom).read_bytes()
        status = workflow.status(self.root, run)['runs'][0]
        self.assertEqual(status['next_action']['command'], 'review-authored')
        self.assertEqual(status['next_action']['argv'][-2:], ['--file', custom])
        self.assertEqual((self.root / custom).read_bytes(), before)

    def test_finished_save_completes_the_requested_authored_work(self):
        path, _ = self.choices()
        saved = workflow.save(self.root, path)
        loaded = workflow.read_run(self.root, saved['run'])
        self.assertEqual(Path(saved['artifact']).read_text(encoding='utf-8'), 'An empty market after the rain.\n')
        self.assertEqual(loaded.prepared['authored_revision']['state'], 'finished')
        self.assertTrue(loaded.prepared['authored_revision']['input_verified'])
        self.assertEqual([row['event'] for row in loaded.rows], ['authored-save'])
        first = workspace.workspace(self.root, saved['run'], phase='input')
        self.assertNotIn('criteria', first)
        self.assertEqual(first['artifact']['text'], loaded.consumer['instructions'])
        assessed = workspace.workspace(self.root, saved['run'], phase='review')
        self.assertEqual(assessed['criteria'][0]['id'], 'meaning')
        self.finish(saved['run'])
        completion = workflow.verify_completion(self.root, saved['run'], self.task['task_id'])
        self.assertEqual(completion['data']['scope'], 'authored')
        self.assertEqual(completion['data']['completion_state'], 'finished')
        self.assertEqual(c.load(work_ledger.task_path(self.root, self.task['task_id']))['work_state'], 'completed')
        self.assertEqual(workflow.verify_completion(self.root, saved['run'], self.task['task_id'])['sha256'],
                         completion['sha256'])

    def test_requested_delivery_and_review_are_actual_separate_results(self):
        path, _ = self.choices(requirements=['save', 'delivery', 'review'])
        saved = workflow.save(self.root, path)
        with self.assertRaisesRegex(ValueError, 'delivery, review'):
            workflow.complete(self.root, saved['run'])
        delivered = self.delivery(saved['run'])
        with self.assertRaisesRegex(ValueError, 'review'):
            workflow.complete(self.root, saved['run'])
        reviewed = self.review(saved['run'], finding='fail')
        completed = workflow.complete(self.root, saved['run'])
        self.assertEqual(completed['data']['delivery'], delivered['sha256'])
        self.assertEqual(completed['data']['review'], reviewed['sha256'])
        retained = workflow.read_run(self.root, saved['run'])
        self.assertEqual(next(row for row in retained.rows if row['event'] == 'authored-review')
                         ['data']['review']['checks'][0]['verdict'], 'fail')

    def test_editing_publishes_new_bytes_without_transferring_delivery_or_review(self):
        path, choices = self.choices(requirements=['save', 'delivery', 'review'])
        first = workflow.save(self.root, path)['run']
        self.delivery(first)
        self.review(first)
        body = choices['authoring']['delivery']['file']
        self.write(body, 'A busy market before sunrise.\n')
        second = workflow.save(self.root, path)['run']
        self.assertNotEqual(first, second)
        old, current = workflow.read_run(self.root, first), workflow.read_run(self.root, second)
        self.assertEqual(old.consumer['instructions'], 'An empty market after the rain.\n')
        self.assertEqual(current.consumer['instructions'], 'A busy market before sunrise.\n')
        self.assertEqual([row['event'] for row in current.rows], ['authored-save'])
        with self.assertRaisesRegex(ValueError, 'delivery, review'):
            workflow.complete(self.root, second)
        self.assertTrue(old.prepared['authored_revision']['input_verified'])

    def test_delivery_uses_exact_presented_content_and_replays_saved_evidence(self):
        path, _ = self.choices()
        run = workflow.save(self.root, path)['run']
        with self.assertRaisesRegex(ValueError, 'differs from this saved revision'):
            self.delivery(run, text='Unrelated content.')
        receipt = self.delivery(run)
        self.write('host-presentation.json', {'shown': {'text': 'A later host record.'}})
        retained = workflow.read_run(self.root, run)
        self.assertEqual(retained.rows[-1]['sha256'], receipt['sha256'])
        workflow.complete(self.root, run)
        later = self.review(run)
        self.assertEqual(workflow.read_run(self.root, run).rows[-1]['sha256'], later['sha256'])
        workflow.verify_completion(self.root, run, self.task['task_id'])

    def test_unfinished_source_saves_and_restores_without_finished_input_claim(self):
        draft = inputs.draft_inputs(self.root, None, 'unfinished', route='development')
        choices = c.load(self.root / draft['choices_file'])
        self.write(choices['authoring']['delivery']['file'], 'An unfinished opening.\n')
        saved = workflow.save(self.root, draft['choices_file'], draft=True)
        self.assertEqual(saved['state'], 'draft')
        self.assertTrue(saved['unresolved'])
        loaded = workflow.read_run(self.root, saved['run'])
        self.assertFalse(loaded.prepared['authored_revision']['input_verified'])
        source = authored.draft_source(self.root, saved['run'])
        self.assertEqual(source['choices'], choices)
        self.assertEqual(source['files'][choices['authoring']['delivery']['file']], b'An unfinished opening.\n')
        status = workflow.status(self.root, saved['run'])['runs'][0]
        self.assertEqual(status['authored']['state'], 'draft')
        self.assertEqual(status['next_action']['command'], 'draft-inputs')
        self.assertEqual(status['authored']['missing'], ['finished-revision'])
        with self.assertRaisesRegex(ValueError, 'finished-revision'):
            self.finish(saved['run'])
        restored = inputs.draft_inputs(self.root, None, 'restored', from_run=saved['run'])
        edited = c.load(self.root / restored['choices_file'])
        self.assertEqual((self.root / edited['authoring']['delivery']['file']).read_bytes(), b'An unfinished opening.\n')
        self.assertEqual(edited['reading']['reading_key'], choices['reading']['reading_key'])

    def test_attachment_delivery_binds_real_handle_and_exact_attachment(self):
        path, _ = self.choices()
        run = workflow.save(self.root, path)['run']
        loaded = workflow.read_run(self.root, run)
        self.write('attached.txt', loaded.consumer['instructions'])
        self.write('host-attachment.json', {'handle': 'synthetic-attachment-handle'})
        self.write('attachment-receipt.json', {'recipient': 'Synthetic recipient', 'channel': 'Synthetic attachment',
            'artifact': 'attached.txt', 'evidence': {'path': 'host-attachment.json', 'field': ['handle']},
            'note': 'Synthetic actual attachment evidence.'})
        delivered = workflow.deliver(self.root, run, 'attachment-receipt.json')
        self.assertEqual(delivered['data']['delivery']['kind'], 'attachment')

    def test_explicit_draft_delivery_and_completion_preserve_unfinished_state(self):
        path, selected = self.choices(requirements=['save', 'delivery', 'review'], completion_state='draft')
        self.write(selected['authoring']['delivery']['file'], 'An unfinished market scene.\n')
        run = workflow.save(self.root, path, draft=True)['run']
        before = workflow.status(self.root, run)['runs'][0]
        self.assertEqual(before['next_action']['command'], 'deliver')
        delivered = workflow.deliver(self.root, run, destination='deliveries/market-draft.txt')
        self.assertEqual((self.root / 'deliveries/market-draft.txt').read_bytes(), b'An unfinished market scene.\n')
        self.assertEqual(delivered['data']['delivery']['state'], 'draft')
        self.review(run, finding='fail')
        self.finish(run)
        loaded = workflow.read_run(self.root, run)
        self.assertFalse(loaded.prepared['authored_revision']['input_verified'])
        completion = workflow.verify_completion(self.root, run, self.task['task_id'])
        self.assertEqual(completion['data']['state'], 'draft')
        self.assertEqual(completion['data']['completion_state'], 'draft')
        self.assertFalse(any(row['event'] in {'candidate', 'handoff', 'selection'} for row in loaded.rows))

    def test_unfinished_json_is_saved_and_reviewed_as_exact_text(self):
        self.task['artifact'] = 'json'
        self.write('delivery.txt', '{"prompt": "A market square"}\n')
        path, selected = self.choices(requirements=['save', 'review'], completion_state='draft')
        unfinished = '{"prompt": "An unfinished market'
        self.write(selected['authoring']['delivery']['file'], unfinished)
        run = workflow.save(self.root, path, draft=True)['run']
        loaded = workflow.read_run(self.root, run)
        self.assertEqual(loaded.evidence.read(loaded.prepared['authored_revision']['artifact']['sha256']),
                         unfinished.encode('utf-8'))
        self.assertEqual(workflow.review_basis(self.root, run)['draft']['candidate'],
                         loaded.prepared['authored_revision']['artifact']['sha256'])
        self.review(run, finding='fail')
        self.finish(run)
        self.assertFalse(workflow.read_run(self.root, run).prepared['authored_revision']['input_verified'])

    def test_local_delivery_retries_after_copy_and_refuses_different_destination(self):
        path, _ = self.choices(requirements=['save', 'delivery'])
        run = workflow.save(self.root, path)['run']
        destination = 'deliveries/market.txt'
        with patch.object(workflow, 'append_record', side_effect=RuntimeError('Interrupted after copy')):
            with self.assertRaisesRegex(RuntimeError, 'Interrupted'):
                workflow.deliver(self.root, run, destination=destination)
        self.assertEqual((self.root / destination).read_bytes(), b'An empty market after the rain.\n')
        self.assertEqual([row['event'] for row in workflow.read_run(self.root, run).rows], ['authored-save'])
        delivered = workflow.deliver(self.root, run, destination=destination)
        self.assertEqual(workflow.deliver(self.root, run, destination=destination)['sha256'], delivered['sha256'])
        self.write(destination, 'An unrelated document.\n')
        with self.assertRaisesRegex(ValueError, 'different bytes'):
            workflow.deliver(self.root, run, destination=destination)
        self.assertEqual((self.root / destination).read_bytes(), b'An unrelated document.\n')
        # Historical evidence records the completed copy, not ownership of a mutable destination forever.
        self.assertEqual(workflow.read_run(self.root, run).rows[-1]['sha256'], delivered['sha256'])
        other_run = workflow.save(self.root, path)['run']
        internal = 'production/runs/' + other_run + '/unmanifested-delivery.txt'
        with self.assertRaisesRegex(ValueError, 'publication namespace'):
            workflow.deliver(self.root, run, destination=internal)
        self.assertFalse((self.root / internal).exists())

    def test_review_validates_observation_ranges_and_retains_supplemental_evidence(self):
        path, _ = self.choices(requirements=['save', 'review'])
        run = workflow.save(self.root, path)['run']
        self.review(run)
        value = c.load(self.root / 'review.json')
        value['observations'][0]['locator'] = {'kind': 'lines', 'start': 1, 'end': 50}
        self.write('invalid-review.json', value)
        with self.assertRaisesRegex(ValueError, 'range'):
            workflow.review_authored(self.root, run, 'invalid-review.json')
        value['observations'][0]['locator'] = {'kind': 'whole'}
        value['evidence'] = [{'id': 'commission-note', 'path': 'note.txt', 'kind': 'text',
                              'relation': 'Supplemental synthetic commission evidence.', 'limitations': []}]
        value['observations'].append({'evidence': 'commission-note', 'locator': {'kind': 'whole'},
            'observation': 'The note asks for an empty market.', 'interpretation': 'It supports the requested scope.',
            'limitations': []})
        self.write('note.txt', 'An empty market is the requested setting.\n')
        self.write('review.json', value)
        reviewed = workflow.review_authored(self.root, run, 'review.json')
        self.assertEqual(workflow.review_authored(self.root, run, 'review.json')['sha256'], reviewed['sha256'])
        self.write('note.txt', 'Later unrelated text.\n')
        loaded = workflow.read_run(self.root, run)
        evidence = loaded.rows[-1]['data']['evidence'][0]
        self.assertEqual(loaded.evidence.read(evidence['sha256']), b'An empty market is the requested setting.\n')

    def test_review_basis_preserves_original_sources_beside_adaptations(self):
        original = 'The market is empty and the stalls are closed.\n'
        adaptation = 'The market is crowded and the stalls are open.\n'
        self.write('commission.txt', original)
        self.task['sources'] = [{'id': 'commission', 'path': 'commission.txt', 'role': 'design',
            'disposition': 'applied', 'locator': 'whole document', 'reason': 'Synthetic source of required setting.'}]
        path, selected = self.choices(requirements=['save', 'review'])
        source = selected['authoring']['sources']['commission']
        if 'file' in source:
            self.write(source['file'], adaptation)
        else:
            source['content'] = adaptation
            self.write(path, selected)
        run = workflow.save(self.root, path)['run']
        exported = inputs.build_inputs(self.root, None, path, 'exported-inputs')
        self.write('commission.txt', 'A later changed source.\n')
        basis = workflow.review_basis(self.root, run)
        evidence = {item['id']: item for item in basis['evidence']}
        self.assertEqual((self.root / evidence['source:commission']['path']).read_text(encoding='utf-8'), original)
        self.assertEqual((self.root / evidence['adaptation:commission']['path']).read_text(encoding='utf-8'), adaptation)
        self.assertEqual(basis['commission'], self.task['direction'])
        exported_run = workflow.prepare(self.root, exported['inputs']['production-task']['path'])['run']
        exported_evidence = {item['id']: item for item in workflow.review_basis(self.root, exported_run)['evidence']}
        self.assertEqual((self.root / exported_evidence['source:commission']['path']).read_text(encoding='utf-8'), original)
        self.assertEqual((self.root / exported_evidence['adaptation:commission']['path']).read_text(encoding='utf-8'), adaptation)
        self.review(run, finding='fail')
        self.assertEqual(workflow.read_run(self.root, run).rows[-1]['data']['review']['checks'][0]['verdict'], 'fail')
        (self.root / 'commission.txt').unlink()
        restored = inputs.draft_inputs(self.root, None, 'restored-sources', from_run=run)
        revised = workflow.save(self.root, restored['choices_file'])['run']
        retained = {item['id']: item for item in workflow.review_basis(self.root, revised)['evidence']}
        self.assertEqual((self.root / retained['source:commission']['path']).read_text(encoding='utf-8'), original)
        self.assertEqual((self.root / retained['adaptation:commission']['path']).read_text(encoding='utf-8'), adaptation)

    def test_unfinished_steps_block_closure_before_creating_completion(self):
        path, _ = self.choices()
        run = workflow.save(self.root, path)['run']
        with self.assertRaisesRegex(ValueError, 'not done'):
            work_ledger.finish(self.root, run)
        self.assertEqual([row['event'] for row in workflow.read_run(self.root, run).rows], ['authored-save'])
        self.finish(run)
        self.assertEqual(c.load(work_ledger.task_path(self.root, self.task['task_id']))['work_state'], 'completed')

    def test_requested_review_reports_and_requires_actual_criterion_coverage(self):
        self.task['criteria'].append({'id': 'scope', 'strength': 'advisory',
                                      'text': 'The sentence retains the requested scope.', 'evidence': 'text'})
        path, _ = self.choices(requirements=['save', 'review'])
        run = workflow.save(self.root, path)['run']
        value = workflow.draft_review(self.root, run)
        value.update(reviewer='Synthetic coverage reviewer', observations=[{
            'evidence': 'candidate', 'locator': {'kind': 'whole'},
            'observation': 'The saved sentence names an empty market.',
            'interpretation': 'The criterion verdicts are supplied separately by the reviewer.',
            'limitations': ['This fixture tests review coverage, not prose quality.']}],
            conclusion='Assess the requested criteria before closing this revision.')
        self.write('review.json', value)
        workflow.review_authored(self.root, run, 'review.json')
        status = workflow.status(self.root, run)['runs'][0]
        self.assertEqual(status['review'], 'unreviewed')
        self.assertEqual(status['authored']['missing'], ['review'])
        with self.assertRaisesRegex(ValueError, 'review'):
            workflow.complete(self.root, run)

        value['checks'][0].update(verdict='indeterminate', observation_indices=[0],
                                  reason='The first criterion receives an actual inconclusive assessment.')
        self.write('review.json', value)
        workflow.review_authored(self.root, run, 'review.json')
        status = workflow.status(self.root, run)['runs'][0]
        self.assertEqual(status['review'], 'partial')
        self.assertEqual(status['authored']['missing'], ['review'])
        with self.assertRaisesRegex(ValueError, 'review'):
            workflow.complete(self.root, run)

        value['checks'][1].update(verdict='fail', observation_indices=[0],
                                  reason='The second criterion receives an actual failed assessment.')
        value['unresolved'] = ['Revise the failed scope finding.']
        self.write('review.json', value)
        reviewed = workflow.review_authored(self.root, run, 'review.json')
        self.assertEqual(workflow.status(self.root, run)['runs'][0]['review'], 'complete')
        completed = workflow.complete(self.root, run)
        self.assertEqual(completed['data']['review'], reviewed['sha256'])

    def test_finish_keeps_open_questions_without_creating_completion(self):
        path, _ = self.choices()
        run = workflow.save(self.root, path)['run']
        work_ledger.block(self.root, 'Does the requested setting need another paragraph?')
        with self.assertRaisesRegex(ValueError, 'open author questions'):
            self.finish(run)
        self.assertEqual([row['event'] for row in workflow.read_run(self.root, run).rows], ['authored-save'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
