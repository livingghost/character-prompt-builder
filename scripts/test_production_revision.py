"""Public editing lifecycles with synthetic inputs and no provider effects."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import execution_contract as c
import production_case_fixtures as cases
import production_fixtures as fixtures
import production_store as store
import production_workflow as workflow
import test_production_authored as authored_cases
import work_ledger

SCRIPTS = Path(__file__).resolve().parent


class PublicCLI:
    def invoke(self, *arguments, script='production_workflow.py', json_output=True, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, arguments)],
            cwd=self.root, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout) if json_output else result.stdout

    def run_action(self, action, *, reason=None):
        argv = list(action['argv'])
        if reason is not None:
            argv[argv.index('--reason') + 1] = reason
        result = subprocess.run(argv, cwd=self.root, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)


class CompletedSourceCLITests(PublicCLI, unittest.TestCase):
    setUp = authored_cases.AuthoredRevisionTests.setUp
    write = authored_cases.AuthoredRevisionTests.write
    choices = authored_cases.AuthoredRevisionTests.choices

    def test_completed_source_opens_new_work_and_retains_exact_old_completion(self):
        path, _ = self.choices()
        saved = self.invoke('save', '--root', self.root, '--choices', path)
        run = saved['run']
        self.invoke('step', '--studio', self.root, '1', script='work_ledger.py', json_output=False)
        self.invoke('finish', '--studio', self.root, '--run', run, script='work_ledger.py', json_output=False)
        original = workflow.read_run(self.root, run)
        old_events = copy.deepcopy(original.rows)
        old_work = work_ledger.task_path(self.root, self.task['task_id']).read_bytes()
        old_bytes = original.consumer['instructions'].encode('utf-8')
        refused = self.invoke('draft-inputs', '--root', self.root, '--from-run', run,
            '--out-dir', 'revised', expected=2)
        self.assertIn('AUTHORING_TASK_SELECTION_REQUIRED', json.dumps(refused))
        self.assertIsNone(work_ledger.read_current(self.root))
        self.assertFalse((self.root / 'revised').exists())

        draft = self.invoke('draft-inputs', '--root', self.root, '--from-run', run,
            '--new-task', 'Revise the requested wording while retaining its commission.', '--out-dir', 'revised')
        selected = c.load(self.root / draft['choices_file'])
        task = selected['authoring']['task']
        self.assertNotEqual(task['task_id'], self.task['task_id'])
        self.assertEqual(task['production_id'], self.task['production_id'])
        self.assertEqual(task['criteria'], self.task['criteria'])
        self.assertIsNone(task['authority'])
        self.assertEqual((self.root / selected['authoring']['delivery']['file']).read_bytes(), old_bytes)
        revised = 'The empty market glistens after the rain.\r\n'
        (self.root / selected['authoring']['delivery']['file']).write_bytes(revised.encode('utf-8'))
        state = self.invoke('inspect-inputs', '--root', self.root)
        self.assertEqual(state['diagnostics'], [])
        self.assertFalse(state['selection_required'])
        current = next(item for item in state['inputs'] if item['current'])
        self.assertEqual(current['unresolved'], [])
        child = self.run_action(next(item for item in current['next_actions'] if item['operation'] == 'save'))
        loaded = workflow.read_run(self.root, child['run'])
        self.assertEqual(loaded.prepared['parent']['run'], run)
        self.assertEqual(loaded.consumer['instructions'].encode('utf-8'), revised.encode('utf-8'))
        self.assertEqual([row['event'] for row in loaded.rows], ['authored-save'])
        self.assertEqual(store.event_rows(self.root, run), old_events)
        self.assertEqual(work_ledger.task_path(self.root, self.task['task_id']).read_bytes(), old_work)
        self.assertEqual(workflow.read_run(self.root, run).consumer['instructions'].encode('utf-8'), old_bytes)
        exported = self.invoke('build-inputs', '--root', self.root, '--from-run', run,
            '--choices', draft['choices_file'], '--out-dir', 'revision-export')
        self.assertEqual(exported['next_actions'][0]['args']['choices'], draft['choices_file'])
        exported_run = self.invoke('prepare', '--root', self.root,
            '--task', exported['inputs']['production-task']['path'])['run']
        published = workflow.read_run(self.root, exported_run)
        self.assertEqual(published.prepared['parent']['run'], run)
        self.assertEqual(published.prepared['task']['task_id'], task['task_id'])
        self.assertEqual(published.consumer['instructions'].encode('utf-8'), revised.encode('utf-8'))
        self.assertEqual(store.event_rows(self.root, run), old_events)

    def test_refused_draft_opens_no_work(self):
        path, _ = self.choices()
        run = self.invoke('save', '--root', self.root, '--choices', path)['run']
        self.invoke('step', '--studio', self.root, '1', script='work_ledger.py', json_output=False)
        self.invoke('finish', '--studio', self.root, '--run', run, script='work_ledger.py', json_output=False)
        tasks = sorted(item.name for item in (self.root / 'work/tasks').iterdir())
        ledger = work_ledger.read_ledger(self.root)
        self.invoke('draft-inputs', '--root', self.root, '--from-run', run,
            '--new-task', 'Revise the requested wording.', '--scale', '2', '--out-dir', 'revised', expected=2)
        self.invoke('draft-inputs', '--root', self.root, '--route', 'upscale', '--source-image', 'absent.png',
            '--scale', '2', '--purpose', 'Enlarge the selected image twice.', '--out-dir', 'enlarged', expected=2)
        self.assertIsNone(work_ledger.read_current(self.root))
        self.assertEqual(sorted(item.name for item in (self.root / 'work/tasks').iterdir()), tasks)
        self.assertEqual(work_ledger.read_ledger(self.root), ledger)
        self.assertFalse((self.root / 'revised').exists())
        self.assertFalse((self.root / 'enlarged').exists())

    def test_new_task_never_replaces_open_work_or_existing_draft(self):
        path, _ = self.choices()
        run = self.invoke('save', '--root', self.root, '--choices', path)['run']
        before = work_ledger.read_current(self.root)
        self.invoke('draft-inputs', '--root', self.root, '--from-run', run,
            '--new-task', 'A different requested revision.', '--out-dir', 'other', expected=2)
        self.assertEqual(work_ledger.read_current(self.root), before)
        self.assertFalse((self.root / 'other').exists())
        self.invoke('draft-inputs', '--root', self.root, '--from-run', run,
            '--new-task', 'A different requested revision.', '--out-dir', Path(path).parent, expected=2)
        self.assertEqual(work_ledger.read_current(self.root), before)


class ImageBranchCLITests(PublicCLI, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpb-revision-cli-')
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.enterContext(fixtures.scratch_home(base / 'home'))
        self.case = cases.create(base / 'studio', base / 'runtime', with_alternate=True, with_upscale=True)
        self.root = self.case['root']
        from catalog_retrieval import runtime
        self.addCleanup(runtime.configure_pack_runtime, None)
        settings = self.case['settings']
        self.runtime = ['--state-file', str(settings.state_file), '--cache-dir', str(settings.cache_dir),
                        '--managed-root', str(settings.managed_root), '--pack-root', str(self.case['pack'])]
        self.run = self.invoke('prepare', '--root', self.root, '--task', 'task.json', *self.runtime)['run']

    def draft(self, directory, *, source=None, model=None):
        options = ['--model', model, '--service', 'synthetic'] if model else []
        return self.invoke('draft-inputs', '--root', self.root, '--from-run', source or self.run,
            '--out-dir', directory, *options, *self.runtime)

    def current_action(self, choices):
        report = self.invoke('inspect-inputs', '--root', self.root, '--choices', choices, *self.runtime)
        self.assertEqual(report['diagnostics'], [])
        current = next(item for item in report['inputs'] if item['current'])
        self.assertEqual(current['unresolved'], [], current)
        return next(item for item in current['next_actions'] if item.get('operation', item.get('command')) in {'prepare', 'retarget'})

    def test_reopened_scope_error_supplies_the_real_draft_action_and_authored_fields(self):
        prior = workflow.read_run(self.root, self.run)
        refused = self.invoke('draft-inputs', '--root', self.root, '--from-run', self.run,
            '--out-dir', 'scope-revision', '--feature', 'unlisted-interface', *self.runtime, expected=2)
        diagnostic = refused['diagnostics'][0]
        self.assertEqual(diagnostic['requested_fields'], {'authoring.task.features': ['unlisted-interface']})
        self.assertFalse((self.root/'scope-revision').exists())
        draft = self.run_action(diagnostic['next_actions'][0])
        choices = c.load(self.root/draft['choices_file'])
        self.assertEqual(choices['authoring']['task']['criteria'], prior.prepared['task']['criteria'])
        self.assertEqual((self.root/choices['authoring']['delivery']['file']).read_bytes(),
                         prior.consumer['instructions'].encode('utf-8'))
        self.assertIn('inspect-inputs', diagnostic['required_action'])
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_parallel_prompt_and_model_branches_require_selection_and_keep_parent(self):
        first = self.draft('first-pattern')
        second = self.draft('second-model', model=cases.ALTERNATE_MODEL_ID)
        left = c.load(self.root / first['choices_file'])
        right = c.load(self.root / second['choices_file'])
        prompt = 'A flat graphic portrait of a simple synthetic robot beside a bench.\r\n'
        (self.root / left['authoring']['delivery']['file']).write_bytes(prompt.encode('utf-8'))
        left['authoring']['documents']['production_spec']['render_intent']['prompt_expression'] = prompt.strip()
        left['authoring']['documents']['retrieval_record']['elements'][0]['composed_wording'] = prompt.strip()
        cases.write(self.root / first['choices_file'], left)
        cases.alternate_task(self.root)
        import request_validation
        import runtime_evidence
        right['reading']['reading_key'] = c.load(self.root / 'retarget/reading.json')['reading_key']
        right['validation'] = request_validation.draft_choices(
            c.load(self.root / 'retarget/validation.json'), runtime_evidence.reader(self.root))
        right['authoring']['documents']['parameters']['steps'] = 22
        cases.write(self.root / second['choices_file'], right)
        state = self.invoke('inspect-inputs', '--root', self.root, *self.runtime)
        self.assertTrue(state['selection_required'])
        self.assertEqual({row['choices'] for row in state['input_options']},
            {first['choices_file'], second['choices_file']})
        self.assertFalse(any(row['current'] for row in state['inputs']))
        first_run = self.run_action(self.current_action(first['choices_file']))['run']
        second_run = self.run_action(self.current_action(second['choices_file']),
            reason='Compare the independently selected synthetic interface.')['run']
        a, b = (workflow.read_run(self.root, run) for run in (first_run, second_run))
        self.assertEqual(a.consumer['instructions'].encode('utf-8'), prompt.encode('utf-8'))
        self.assertEqual(b.consumer['instructions'], cases.PROMPT)
        self.assertEqual(a.prepared['parent']['run'], self.run)
        self.assertEqual(b.prepared['parent']['run'], self.run)
        self.assertEqual(b.prepared['parent']['kind'], 'retarget')
        self.assertEqual(a.prepared['task']['criteria'], b.prepared['task']['criteria'])
        self.assertEqual(a.artifacts['execution-plan.json']['model'], cases.MODEL_ID)
        self.assertEqual(b.artifacts['execution-plan.json']['model'], cases.ALTERNATE_MODEL_ID)
        for run in (self.run, first_run, second_run):
            self.assertEqual(store.event_rows(self.root, run), [])
        state = self.invoke('inspect-inputs', '--root', self.root, *self.runtime)
        self.assertFalse(state['selection_required'])
        self.assertFalse(state['pending'])

    def test_invalid_changed_choice_preserves_the_compilation_diagnostic(self):
        drafted = self.draft('invalid-control')
        choices = c.load(self.root / drafted['choices_file'])
        choices['authoring']['documents']['parameters']['width'] = 0
        cases.write(self.root / drafted['choices_file'], choices)
        checked = self.invoke('check', '--root', self.root, '--choices', drafted['choices_file'],
            *self.runtime, expected=2)
        prepared = self.invoke('prepare', '--root', self.root, '--choices', drafted['choices_file'],
            *self.runtime, expected=2)
        observed = [(item['code'], item['phase']) for item in checked['diagnostics']]
        self.assertTrue(observed)
        self.assertEqual([(item['code'], item['phase']) for item in prepared['diagnostics']], observed)
        self.assertIn('width', json.dumps(prepared['diagnostics']))
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_reference_add_remove_and_zero_reference_revision_rebuild_only_current_media(self):
        from transport_synthetic import _png
        for name, color in (('red', b'\xff\x00\x00'), ('blue', b'\x00\x00\xff')):
            (self.root / (name + '.png')).write_bytes(_png(32, 32, color))
        draft = self.draft('with-images')
        choices = c.load(self.root / draft['choices_file'])
        choices['authoring']['references']['image_input'] = {'artifact_type': 'image-input-plan',
            'references': [{'id': name, 'role': 'palette', 'file': name + '.png',
                'use_for': ['selected palette'], 'do_not_transfer': ['identity', 'pose']}
                for name in ('red', 'blue')], 'external_request': None}
        choices['authoring']['documents']['production_spec']['render_intent']['execution_mode'] = 'reference-guided'
        cases.write(self.root / draft['choices_file'], choices)
        first = self.invoke('prepare', '--root', self.root, '--choices', draft['choices_file'], *self.runtime)['run']
        parent = workflow.read_run(self.root, first)
        self.assertEqual(len(parent.artifacts['request-contract.json']['media']), 2)
        retained = self.draft('one-image', source=first)
        choices = c.load(self.root / retained['choices_file'])
        choices['authoring']['references']['image_input']['references'].pop(0)
        cases.write(self.root / retained['choices_file'], choices)
        (self.root / 'red.png').unlink()
        second = self.run_action(self.current_action(retained['choices_file']))['run']
        child = workflow.read_run(self.root, second)
        self.assertEqual(len(child.artifacts['request-contract.json']['media']), 1)
        self.assertEqual(child.consumer['image_input']['references'][0]['id'], 'blue')
        self.assertEqual(child.consumer['image_input']['references'][0]['do_not_transfer'], ['identity', 'pose'])
        self.assertEqual(child.prepared['parent']['run'], first)
        final = self.draft('without-images', source=second)
        choices = c.load(self.root / final['choices_file'])
        choices['authoring']['references'] = None
        choices['authoring']['documents']['production_spec']['render_intent']['execution_mode'] = 'text-to-image'
        cases.write(self.root / final['choices_file'], choices)
        (self.root / 'blue.png').unlink()
        third = self.run_action(self.current_action(final['choices_file']))['run']
        plain = workflow.read_run(self.root, third)
        self.assertEqual(plain.artifacts['request-contract.json']['media'], [])
        self.assertNotIn('image_input', plain.prepared['task'])
        self.assertEqual(plain.prepared['task']['criteria'], parent.prepared['task']['criteria'])
        self.assertEqual(plain.consumer['instructions'], cases.PROMPT)
        self.assertEqual(workflow.read_run(self.root, first).artifacts['request-contract.json'],
            parent.artifacts['request-contract.json'])

    def test_reopened_target_uses_registered_new_task_binding(self):
        self.invoke('suspend', '--studio', self.root, '--reason', 'Retain the earlier synthetic comparison.',
            script='work_ledger.py', json_output=False)
        parent_task = work_ledger.task_path(self.root, self.case['task']['task_id']).read_bytes()
        draft = self.invoke('draft-inputs', '--root', self.root, '--from-run', self.run,
            '--new-task', 'Compare another selected interface against the retained commission.',
            '--model', cases.ALTERNATE_MODEL_ID, '--service', 'synthetic', '--out-dir', 'new-model-work', *self.runtime)
        choices = c.load(self.root / draft['choices_file'])
        cases.alternate_task(self.root)
        import request_validation
        import runtime_evidence
        choices['reading']['reading_key'] = c.load(self.root / 'retarget/reading.json')['reading_key']
        choices['validation'] = request_validation.draft_choices(
            c.load(self.root / 'retarget/validation.json'), runtime_evidence.reader(self.root))
        choices['authoring']['documents']['parameters']['steps'] = 22
        cases.write(self.root / draft['choices_file'], choices)
        exported = self.invoke('build-inputs', '--root', self.root, '--from-run', self.run,
            '--choices', draft['choices_file'], '--out-dir', 'target-export', *self.runtime)
        self.assertEqual(exported['next_actions'][0]['operation'], 'retarget')
        action = self.current_action(draft['choices_file'])
        self.assertEqual(action.get('operation', action.get('command')), 'retarget')
        run = self.run_action(action, reason='Explicit synthetic comparison in the newly selected work task.')['run']
        changed = workflow.read_run(self.root, run)
        self.assertEqual(changed.prepared['parent']['run'], self.run)
        self.assertEqual(changed.prepared['task']['task_id'], work_ledger.read_current(self.root)['task_id'])
        self.assertNotEqual(changed.prepared['task']['task_id'], self.case['task']['task_id'])
        self.assertIsNone(changed.prepared['task']['authority'])
        self.assertIsNone(store.read_authority(self.root, changed.prepared['task']['task_id'], required=False))
        self.assertEqual(work_ledger.task_path(self.root, self.case['task']['task_id']).read_bytes(), parent_task)
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_completed_capture_is_selected_directly_for_new_upscale_work(self):
        from test_production_execution import decisions
        self.invoke('execute', '--root', self.root, '--run', self.run,
            '--decisions-file', decisions(self.root, self.run))
        captured = workflow.read_run(self.root, self.run)
        candidate = workflow.find(captured.rows, 'candidate')['sha256']
        self.invoke('draft-review', '--root', self.root, '--run', self.run,
            '--candidate', candidate, '--out', 'source-review.json')
        review = c.load(self.root / 'source-review.json')
        review.update(reviewer='Synthetic fixture reviewer', observations=[{'evidence': 'candidate',
            'locator': {'kind': 'whole'}, 'observation': 'The retained local PNG decodes at its stated dimensions.',
            'interpretation': 'Synthetic protocol assertion only.', 'limitations': ['No model quality is assessed.']}],
            conclusion='Synthetic fixture review.')
        for check in review['checks']:
            check.update(verdict='pass', observation_indices=[0], reason='Measured local synthetic fixture.')
        cases.write(self.root / 'source-review.json', review)
        self.invoke('review', '--root', self.root, '--run', self.run, '--file', 'source-review.json')
        self.invoke('draft-selection', '--root', self.root, '--run', self.run,
            '--candidate', candidate, '--out', 'source-selection.json')
        selected = c.load(self.root / 'source-selection.json')
        selected['reason'] = 'Select this synthetic retained result for delivery.'
        fixtures.selection(self.root, self.run, selected)
        cases.write(self.root / 'source-selection.json', selected)
        self.invoke('select', '--root', self.root, '--run', self.run, '--file', 'source-selection.json')
        self.invoke('complete', '--root', self.root, '--run', self.run)
        for step in (1, 2, 3):
            self.invoke('step', '--studio', self.root, str(step), script='work_ledger.py', json_output=False)
        self.invoke('finish', '--studio', self.root, '--run', self.run, script='work_ledger.py', json_output=False)
        prior = workflow.read_run(self.root, self.run)
        old_events = copy.deepcopy(prior.rows)
        image = workflow.find(prior.rows, 'candidate', candidate)['data']['files'][0]
        self.invoke('draft-inputs', '--root', self.root, '--route', 'upscale',
            '--source-run', self.run, '--new-task', 'A new explicit enlargement.',
            '--out-dir', 'unselected-image', *self.runtime, expected=2)
        self.assertIsNone(work_ledger.read_current(self.root))
        draft = self.invoke('draft-inputs', '--root', self.root, '--route', 'upscale',
            '--source-run', self.run, '--source-candidate', candidate, '--scale', '2',
            '--purpose', 'Enlarge this selected image while retaining its content.',
            '--new-task', 'Create and assess the requested enlargement.', '--model', cases.UPSCALE_MODEL_ID,
            '--service', 'synthetic', '--out-dir', 'enlargement', *self.runtime)
        choices = c.load(self.root / draft['choices_file'])
        self.assertEqual(draft['selected_image']['source_candidate'], candidate)
        self.assertEqual(draft['selected_image']['sha256'], image['sha256'])
        self.assertEqual(choices['authoring']['task']['route'], 'upscale')
        self.assertEqual(choices['authoring']['documents'], {})
        self.assertIsNone(choices['authoring']['delivery']['content'])
        self.assertFalse((self.root / 'enlargement/prompt.txt').exists())
        self.assertNotEqual(choices['authoring']['task']['criteria'], self.case['task']['criteria'])
        self.assertNotEqual(choices['authoring']['task']['task_id'], self.case['task']['task_id'])
        from reading_fixtures import fixture_reading
        from request_validation_fixtures import fixture_validation
        import request_validation
        import runtime_evidence
        choices['reading']['reading_key'] = fixture_reading(route='upscale', execution='dispatcher',
            studio=self.root, ledger=self.root / 'work/reads.jsonl', model=cases.UPSCALE_MODEL_ID,
            service='synthetic')['reading_key']
        validation = fixture_validation(self.root, cases.UPSCALE_MODEL_ID,
            reference_mode='authored-rendition', service='synthetic')
        choices['validation'] = request_validation.draft_choices(validation, runtime_evidence.reader(self.root))
        cases.write(self.root / draft['choices_file'], choices)
        enlarged = self.run_action(self.current_action(draft['choices_file']))['run']
        prepared = workflow.read_run(self.root, enlarged)
        self.assertEqual(prepared.prepared['parent']['kind'], 'upscale')
        self.assertEqual(prepared.prepared['parent']['run'], self.run)
        self.assertEqual(prepared.prepared['parent']['basis'][0]['candidate'], candidate)
        self.assertEqual(prepared.artifacts['package.json']['source']['sha256'], image['sha256'])
        source_media = workflow.find(prior.rows, 'candidate', candidate)['data']['media']
        metadata = prepared.artifacts['request-contract.json']['media'][0]
        self.assertEqual(metadata['media_type'], 'image/png')
        self.assertEqual(metadata['dimensions'], {key: source_media[key] for key in ('width', 'height')})
        self.assertEqual(store.event_rows(self.root, self.run), old_events)
        self.assertEqual(prepared.rows, [])
        authority = copy.deepcopy(store.authority(self.root, self.case['task']['task_id']))
        authority['task_id'] = prepared.prepared['task']['task_id']
        cases.write(self.root/'enlargement-authority.json', authority)
        store.import_authority(self.root, 'enlargement-authority.json')
        executed = self.invoke('execute', '--root', self.root, '--run', enlarged,
            '--decisions-file', decisions(self.root, enlarged))
        self.assertTrue(executed['execution_completed'], executed)
        self.assertEqual(executed.get('warnings'), [])
        result = workflow.read_run(self.root, enlarged)
        capture = workflow.find(result.rows, 'capture-status')['data']
        self.assertEqual(capture['diagnostics'], [])
        self.assertEqual(capture['capture'], 'complete')
        claim = workflow.find(result.rows, 'dispatch-claim')['data']
        journal = self.root/claim['journal']
        result_package = c.load(journal/'upscale-package-1.json')
        from upscale_package import verify_upscale_package
        checked = verify_upscale_package(result_package, package_root=journal,
            model_record=result.artifacts['execution-target.json']['model'])
        self.assertEqual(checked['source_image']['sha256'], image['sha256'])
        self.assertEqual(checked['source_image']['media_type'], 'image/png')
        self.assertEqual(checked['output_image']['dimensions'],
                         {key: source_media[key] * 2 for key in ('width', 'height')})
        self.assertEqual(store.event_rows(self.root, self.run), old_events)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
