"""Authored results retain exact revisions, independently recorded uses and drafts."""
from __future__ import annotations
import production_workflow as production_workflow_cli
import production_fixtures as authoring_fixtures

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
import authoring_work
import production_authored as authored
import production_fixtures as fixtures
import production_inputs as inputs
import production_operations as workflow
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
        fixtures.task(self.root, self.task, focus='supporting-setting')
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
        fixtures.bind_work_basis(self.root, self.task, focus='supporting-setting')
        self.write('task.json', self.task)
        self.counter += 1
        result = authoring_fixtures.authoring_inputs(self.root, 'task.json', 'edit-' + str(self.counter))
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
        result = subprocess.run([sys.executable, str(Path(production_workflow_cli.__file__)), 'draft-review',
            '--root', str(self.root), '--run', run, '--out', custom],
            capture_output=True, text=True, encoding='utf-8', env=dict(os.environ), check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertNotIn('choices', report)
        self.assertEqual(c.load(self.root / custom)['observations'], [])
        self.assertEqual(report['draft_file'], custom)
        self.assertEqual(report['review_guide']['automatic_evidence'][0]['id'], 'candidate')
        self.assertEqual(report['next_action']['command'], 'review-authored')
        before = (self.root / custom).read_bytes()
        status = workflow.status(self.root, run)['runs'][0]
        self.assertEqual(status['next_action']['command'], 'review-authored')
        self.assertEqual(status['next_action']['argv'][-2:], ['--file', custom])
        self.assertEqual((self.root / custom).read_bytes(), before)

    def test_public_save_resumes_its_suspended_task_without_rebinding_other_work(self):
        from reading_fixtures import fixture_reading
        import production_store
        a_path, a_choices = self.choices(requirements=['save'])
        a_id = a_choices['authoring']['task']['task_id']
        a_folder = self.root / Path(a_path).parent
        before_a = {path.relative_to(self.root).as_posix(): path.read_bytes()
                    for path in a_folder.rglob('*') if path.is_file()}

        def invoke(argv, *, code=0, json_output=True):
            result = subprocess.run(argv, cwd=self.root, capture_output=True,
                                    text=True, encoding='utf-8', timeout=45)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            return json.loads(result.stdout) if json_output else result.stdout

        ledger = [sys.executable, str(Path(work_ledger.__file__))]
        production = [sys.executable, str(Path(production_workflow_cli.__file__))]
        invoke([*ledger, 'suspend', '--studio', str(self.root), '--reason',
                'Create independent synthetic work B.'], json_output=False)
        invoke([*ledger, 'begin', '--studio', str(self.root), '--goal',
                'Independent synthetic work B.', '--step', 'Write the harbor description.'], json_output=False)
        self.write('b-request.txt', 'Write an independent description of a quiet harbor.')
        draft = invoke([*production, 'draft-inputs', '--root', str(self.root),
            '--operation', 'compose',
            '--route', 'development', '--artifact', 'text', '--execution', 'authored',
            '--focus', 'supporting-setting', '--request-file', 'b-request.txt', '--out-dir', 'work/b'])
        b_path = draft['choices_file']
        b_choices = c.load(self.root / b_path)
        b_task = b_choices['authoring']['task']
        b_id = b_task['task_id']
        self.assertNotEqual(a_id, b_id)
        self.assertNotEqual(a_choices['authoring']['task']['production_id'], b_task['production_id'])
        b_task['criteria'] = [{'id': 'harbor', 'strength': 'hard', 'evidence': 'artifact',
                              'text': 'The text describes the independent quiet harbor.'}]
        b_task['direction'].update(purpose='Describe the independent harbor.',
            intended_effect='A quiet waterfront scene.', basis=[row['id'] for row in b_task['sources']])
        self.write(b_choices['authoring']['delivery']['file'], 'A quiet harbor before the first ferry.\n')
        reading = fixture_reading(route=b_task['route'], execution=b_task['execution'],
            features=b_task['features'], studio=self.root, operation='author')
        b_choices['reading']['reading_key'] = reading['reading_key']
        self.write(b_path, b_choices)
        invoke([*ledger, 'suspend', '--studio', str(self.root), '--reason',
                'Retain B while returning to A.'], json_output=False)
        invoke([*ledger, 'resume-task', '--studio', str(self.root), '--task-id', a_id], json_output=False)
        current_before = work_ledger.require_open(self.root)
        b_record_before = work_ledger.task_path(self.root, b_id).read_bytes()
        b_before = (self.root / b_path).read_bytes()

        refused = invoke([*production, 'save', '--root', str(self.root), '--choices', b_path], code=2)
        problem = next(row for row in refused['diagnostics'] if row['code'] == 'TASK_CHANGED')
        self.assertEqual((problem['phase'], problem['expected'], problem['actual']), ('publication', a_id, b_id))
        self.assertIsNone(problem['file'])
        self.assertIsNone(problem['pointer'])
        self.assertEqual(problem['authored_task_owner'],
                         {'file': b_path, 'pointer': '/authoring/task/task_id'})
        self.assertEqual(problem['repair_owner']['file'], 'work/current.json')
        self.assertEqual(problem['task_id_to_preserve'], b_id)
        self.assertEqual(problem['intended_task']['state'], 'suspended')
        self.assertEqual(work_ledger.require_open(self.root), current_before)
        self.assertEqual(work_ledger.task_path(self.root, b_id).read_bytes(), b_record_before)
        self.assertEqual((self.root / b_path).read_bytes(), b_before)
        self.assertEqual(production_store.runs(self.root), [])
        from test_production_report_view import resolved_action
        actions = [resolved_action(refused, action) for action in problem['recovery_actions']]
        self.assertEqual([action['command'] for action in actions], ['suspend', 'resume-task', 'save'])
        self.assertEqual(actions[0]['expected_active_task_id'], a_id)
        self.assertEqual(actions[1]['argv'][-2:], ['--task-id', b_id])
        self.assertEqual(actions[2]['argv'][-2:], ['--choices', b_path])
        for action in actions[:2]:
            invoke(action['argv'], json_output=False)
        saved = invoke(actions[2]['argv'])
        loaded = workflow.read_run(self.root, saved['run'])
        self.assertEqual(loaded.prepared['task']['task_id'], b_id)
        self.assertEqual(loaded.consumer['instructions'], 'A quiet harbor before the first ferry.\n')
        self.assertEqual(work_ledger.require_open(self.root)['task_id'], b_id)
        self.assertEqual(c.load(work_ledger.task_path(self.root, a_id))['work_state'], 'suspended')
        self.assertEqual({path: (self.root / path).read_bytes() for path in before_a}, before_a)
        self.assertEqual((self.root / b_path).read_bytes(), b_before)

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

    def test_reopened_target_keeps_captured_model_after_original_removal(self):
        from model_prompt_input_fixtures import prompt_input
        model = {'id': 'synthetic-authored-model', 'prompt_input': prompt_input('descriptive')}
        self.write('model.json', model)
        self.task['authored'] = {'target': {'model_file': 'model.json'}}
        fixtures.task(self.root, self.task, focus='supporting-setting')
        self.write('task.json', self.task)
        parent = workflow.prepare(self.root, 'task.json')
        original = workflow.read_run(self.root, parent['run'])
        (self.root / 'model.json').unlink()

        draft = authoring_fixtures.authoring_inputs(self.root, None, 'reopened-target', from_run=parent['run'])
        selected = draft['choices']['target']['model_file']
        self.assertNotEqual(selected, 'model.json')
        self.assertEqual((self.root / selected).read_bytes(), c.encoded(model))
        self.assertEqual(draft['unresolved'], [])
        child = workflow.prepare(self.root, choices=draft['choices_file'])
        continued = workflow.read_run(self.root, child['run'])
        self.assertEqual(continued.consumer['instructions'], original.consumer['instructions'])
        self.assertEqual(continued.prepared['parent']['run'], parent['run'])
        self.assertEqual(workflow.read_run(self.root, parent['run']).prepared, original.prepared)

    def test_public_task_preserves_each_subject_and_requirement_application(self):
        original = {
            'a': {'identity': {'body': 'A folded reed creature with two fins.'}},
            'b': {'identity': {'body': 'A ringing shell creature.'}},
            'commission': {'event': 'The two creatures meet before departure.'},
            'prior_depiction': {'treatment': 'photograph', 'framing': 'entire figures'},
        }
        self.write('cast.json', original)
        self.task['sources'] = [{'id': 'cast', 'path': 'cast.json', 'role': 'definition',
            'disposition': 'applied', 'locator': 'whole original',
            'reason': 'The acquired character definitions and commission.'}]
        self.task['criteria'][0]['text'] = 'The text describes the two defined creatures meeting.'
        self.write('delivery.txt', 'The reed creature folds its fins as the shell creature rings.\n')
        choices_path, _ = self.choices()
        basis_path = Path(choices_path).parent / 'work-basis.json'
        basis = c.load(self.root / basis_path)
        applications = {
            'reed-definition': {'source': 'cast', 'pointer': '/a/identity'},
            'shell-definition': {'source': 'cast', 'pointer': '/b/identity'},
            'meeting': {'source': 'cast', 'pointer': '/commission'},
        }
        subjects = {'A': ['reed-definition'], 'B': ['shell-definition']}
        basis = authoring_work.revise_basis(basis, applications=applications,
            subjects=subjects, requirements=['meeting'], focus='character')
        self.write(basis_path, basis)

        built = inputs.build_inputs(self.root, None, choices_path, 'published')
        self.assertTrue(built['ok'], built)
        task_path = built['inputs']['production-task']['path']
        published = c.load(self.root / task_path)
        source = next(row for row in published['sources'] if row['id'] == 'cast')
        self.assertEqual({row['id']: row for row in source['applications']}, {
            'reed-definition': {'id': 'reed-definition', 'pointer': '/a/identity', 'subjects': ['A'], 'requirement': False},
            'shell-definition': {'id': 'shell-definition', 'pointer': '/b/identity', 'subjects': ['B'], 'requirement': False},
            'meeting': {'id': 'meeting', 'pointer': '/commission', 'subjects': [], 'requirement': True},
        })
        chosen = {'reed-definition': original['a']['identity'],
                  'shell-definition': original['b']['identity'], 'meeting': original['commission']}
        selected = [chosen[row['id']] for row in source['applications']]
        self.assertEqual(c.load(self.root / source['path']), selected)
        self.assertEqual(c.load(self.root / source['origin']['path']), original)

        reopened = authoring_fixtures.authoring_inputs(self.root, task_path, 'reopened-public',
                                                       focus='character')
        acquired = c.load(self.root / reopened['authoring_work']['basis'])
        self.assertEqual(acquired['applications'], applications)
        self.assertEqual(acquired['subjects'], subjects)
        self.assertEqual(acquired['requirements'], ['meeting'])
        self.assertEqual(authoring_work.source_value(acquired['sources']['cast']), original)
        child = workflow.save(self.root, reopened['choices_file'])['run']
        retained = workflow.read_run(self.root, child).prepared
        saved_source = next(row for row in retained['task']['sources'] if row['id'] == 'cast')
        self.assertEqual(saved_source['applications'], source['applications'])
        self.assertEqual(workflow.read_run(self.root, child).consumer['instructions'],
                         'The reed creature folds its fins as the shell creature rings.\n')

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
        draft = authoring_fixtures.authoring_inputs(self.root, None, 'unfinished', route='development')
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
        restored = authoring_fixtures.authoring_inputs(self.root, None, 'restored', from_run=saved['run'])
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

    def test_review_preserves_complete_source_beside_applied_selection(self):
        original = {'commission': 'The market is empty and the stalls are closed.\n',
                    'proposal': 'The market is crowded and the stalls are open.\n'}
        self.write('commission.json', original)
        self.task['sources'] = [{'id': 'commission', 'path': 'commission.json', 'role': 'design',
            'disposition': 'applied', 'locator': 'whole document', 'reason': 'Synthetic setting and authored proposal.'}]
        path, selected = self.choices(requirements=['save', 'review'])
        basis_path = Path(path).parent / 'work-basis.json'
        current = c.load(self.root / basis_path)
        applications = {**current['applications'], 'commission': {'source': 'commission', 'pointer': '/proposal'}}
        self.write(basis_path, authoring_work.revise_basis(current, applications=applications))

        def retained_selection(run):
            basis = workflow.review_basis(self.root, run)
            evidence = {item['id']: item for item in basis['evidence']}
            self.assertEqual(c.load(self.root / evidence['source:commission']['path']), original['proposal'])
            self.assertEqual(c.load(self.root / evidence['source-origin:commission']['path']), original)
            return basis

        run = workflow.save(self.root, path)['run']
        exported = inputs.build_inputs(self.root, None, path, 'exported-inputs')
        self.write('commission.json', {'commission': 'A later changed source.'})
        basis = retained_selection(run)
        expected_direction = copy.deepcopy(self.task['direction'])
        request_id = 'request:' + c.digest(current['request'].encode('utf-8'))
        if request_id not in expected_direction['basis']:
            expected_direction['basis'].append(request_id)
        self.assertEqual(basis['source_task_direction'], expected_direction)
        exported_run = workflow.prepare(self.root, exported['inputs']['production-task']['path'])['run']
        retained_selection(exported_run)
        exported_draft = authoring_fixtures.authoring_inputs(self.root, exported['inputs']['production-task']['path'], 'exported-draft')
        exported_revision = workflow.save(self.root, exported_draft['choices_file'])['run']
        retained_selection(exported_revision)
        self.review(run, finding='fail')
        self.assertEqual(workflow.read_run(self.root, run).rows[-1]['data']['review']['checks'][0]['verdict'], 'fail')
        (self.root / 'commission.json').unlink()
        restored = authoring_fixtures.authoring_inputs(self.root, None, 'restored-sources', from_run=run)
        revised = workflow.save(self.root, restored['choices_file'])['run']
        retained_selection(revised)

    def test_explicit_current_source_reselection_becomes_the_review_basis(self):
        original = 'The original selected source.\n'
        replacement = 'The explicitly selected current source.\n'
        self.write('source.bin', original)
        self.task['sources'] = [{'id': 'commission', 'path': 'source.bin', 'role': 'design',
            'disposition': 'applied', 'locator': 'whole document', 'reason': 'Synthetic source.'}]
        path, _ = self.choices(requirements=['save', 'review'])
        parent = workflow.save(self.root, path)['run']
        before = workflow.read_run(self.root, parent).prepared
        self.write('source.bin', replacement)
        draft = authoring_fixtures.authoring_inputs(self.root, None, 'reselected-source', from_run=parent)
        choices = draft['choices']
        retained_path = next(row['path'] for row in choices['authoring']['task']['sources'] if row['id'] == 'commission')
        self.assertEqual((self.root / retained_path).read_text(encoding='utf-8'), original)
        current = authoring_fixtures.acquire_application(self.root, draft['choices_file'], 'current-commission',
            (self.root / 'source.bin').read_text(encoding='utf-8'), application='commission')
        self.assertEqual(authoring_work.source_bytes(current['sources']['commission']).decode('utf-8'), original)

        child = workflow.save(self.root, draft['choices_file'])['run']
        evidence = {item['id']: item for item in workflow.review_basis(self.root, child)['evidence']}
        self.assertEqual((self.root / evidence['source:current-commission']['path']).read_text(encoding='utf-8'), replacement)
        retained_basis = c.load(self.root / evidence['authoring-work']['path'])
        self.assertEqual(authoring_work.source_bytes(retained_basis['sources']['commission']).decode('utf-8'), original)
        self.assertEqual(retained_basis['applications']['commission']['source'], 'current-commission')
        self.assertEqual((self.root / retained_path).read_text(encoding='utf-8'), original)
        self.assertEqual(workflow.read_run(self.root, parent).prepared, before)

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
