"""Saved external media delivery, with synthetic local files and no host calls."""
from __future__ import annotations
import production_workflow as production_workflow_cli
import production_fixtures as authoring_fixtures

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import execution_contract as c
import image_input
import production_external_inputs as authored
import production_fixtures as fixtures
from catalog_retrieval.runtime import configure_pack_runtime
from input_evidence import InputEvidence
from semantic_edit_plan_smoke_test import (PROMPT, PROMPT_FINAL, BOARD_REFERENCE_DIRECTION,
                                           png, setup_plan, sync_external_prompt, write)


class DeliveryFixture:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='saved-external-delivery-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'studio'
        self.directory = self.root / 'saved-run'
        self.enterContext(fixtures.scratch_home(self.base / 'home'))
        configure_pack_runtime(None)
        self.addCleanup(configure_pack_runtime, None)
        self.plan = setup_plan(self.root)

    def local_plan(self):
        request = c.load(self.root / 'request.json')
        values = ['scene.png', str(self.root / 'design.png')]
        request['images'] = values
        request['independent_control'] = 'scene.png'
        for row, value in zip(self.plan['external_request']['reference_fields'], values, strict=True):
            row.pop('evidence')
            row.update(local_file=True, value=value)
        write(self.root, 'request.json', request)
        sync_external_prompt(self.root, self.plan, PROMPT + ' The literal label is scene.png.')
        write(self.root, 'image-input.json', self.plan)

    def capture_binding(self, *, extra=()):
        captured = {}

        def read(path):
            raw = (self.root / path).read_bytes()
            captured[c.digest(raw)] = raw
            return raw

        binding = image_input.validate(self.plan, self.root, read=read)
        for raw in [*captured.values(), *extra]:
            c.object_store(self.directory, raw)
        return binding

    def delivery(self, binding):
        return image_input.external_delivery(binding, run_directory=self.directory,
            read_object=lambda key: c.object_read(self.directory, key))


class ExternalDeliveryTests(DeliveryFixture, unittest.TestCase):
    def test_declared_local_fields_use_saved_pixels_after_original_files_disappear(self):
        self.local_plan()
        binding = self.capture_binding()
        before = copy.deepcopy(binding)
        pixels = [(self.root / row['file']).read_bytes() for row in binding['references']]
        (self.root / 'scene.png').write_bytes(png((1, 2, 3)))
        (self.root / 'design.png').rename(self.root / 'moved-design.png')
        for name in ('request.json', 'prompt.txt', 'image-input.json', 'model-evidence.json'):
            (self.root / name).unlink()
        with patch('production_store.stable_bytes', side_effect=AssertionError('No live source read')):
            delivery = self.delivery(binding)
        self.assertEqual(binding, before)
        self.assertEqual(delivery['request']['prompt'], before['external_request']['request']['prompt'])
        self.assertEqual(delivery['request']['independent_control'], 'scene.png')
        self.assertEqual([Path(path).read_bytes() for path in delivery['request']['images']], pixels)
        self.assertEqual([row['file'] for row in delivery['references']], delivery['request']['images'])
        self.assertEqual([row['role'] for row in delivery['reference_bindings']], ['scene', 'geometry'])

    def test_saved_carrier_paths_are_canonical(self):
        self.local_plan()
        binding = self.capture_binding()
        delivery = self.delivery(binding)
        for item in delivery['media']:
            path = Path(item['path'])
            self.assertTrue(path.is_file())
            self.assertEqual(path, path.resolve())

    def test_provider_values_remain_opaque_even_when_spelled_as_a_source_filename(self):
        request = c.load(self.root / 'request.json')
        request['images'] = ['scene.png', 'https://example.invalid/design.png']
        for row, value in zip(self.plan['external_request']['reference_fields'], request['images'], strict=True):
            row['value'] = value
        write(self.root, 'request.json', request)
        binding = self.capture_binding()
        (self.root / 'scene.png').unlink()
        (self.root / 'design.png').unlink()
        delivery = self.delivery(binding)
        request['prompt'] = PROMPT_FINAL
        self.assertEqual(delivery['request'], request)
        self.assertTrue(all(Path(row['file']).is_file() for row in delivery['references']))

    def test_local_path_must_contain_the_selected_delivery_bytes(self):
        self.local_plan()
        self.plan['external_request']['reference_fields'][0]['value'] = 'design.png'
        request = c.load(self.root / 'request.json')
        request['images'][0] = 'design.png'
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'local file differs from its selected delivery carrier'):
            image_input.validate(self.plan, self.root)

    def test_local_choice_derives_paths_and_redrafts_without_upload_evidence(self):
        choice = authored.draft(self.plan, c.load(self.root / 'request.json'))
        for row in choice['image_input']['references']:
            row['transport'] = {'local_file': True}
        files, report = authored.build(choice, {}, InputEvidence(self.root), self.root,
            'built', PROMPT.encode('utf-8'))
        plan = c.decode(files['image-input.json'])
        request = c.decode(files['external-request.json'])
        self.assertEqual(request['images'], ['scene.png', 'design.png'])
        fields = plan['external_request']['reference_fields']
        self.assertTrue(all(row['local_file'] is True and 'evidence' not in row for row in fields))
        redraft = authored.draft(plan, request)
        self.assertEqual(redraft['source_uploads'], [])
        self.assertEqual([row['transport'] for row in redraft['image_input']['references']],
            [{'local_file': True, 'field': ['images', index]} for index in range(2)])
        self.assertEqual(report['schema_validation']['mode'], 'bounded-probe')

    def test_reopening_redirects_source_owners_and_keeps_provider_values_and_text(self):
        request = c.load(self.root / 'request.json')
        request['images'][0] = 'scene.png'
        self.plan['external_request']['reference_fields'][0]['value'] = 'scene.png'
        request['independent_control'] = 'model-evidence.json'
        choice = authored.draft(self.plan, request, root=self.root)
        mapping = {name: 'retained/' + name for name in
            ('scene.png', 'design.png', 'model-evidence.json', 'upload-evidence.json')}
        moved = authored.relocate_sources(choice, mapping)
        self.assertEqual(moved['request'], choice['request'])
        refs = moved['image_input']['references']
        self.assertEqual(refs[0]['file'], 'retained/scene.png')
        self.assertEqual(refs[0]['transport']['value'], 'scene.png')
        self.assertEqual(refs[0]['transport']['uploaded_file'], 'retained/scene.png')
        self.assertEqual(refs[0]['transport']['evidence']['path'], 'retained/upload-evidence.json')
        self.assertEqual(moved['image_input']['model']['evidence']['path'], 'retained/model-evidence.json')
        self.assertEqual(moved['source_uploads'], choice['source_uploads'])
        self.assertNotEqual(moved, choice)

    def test_saved_delivery_still_respects_the_acquired_native_schema(self):
        self.local_plan()
        schema = {'type': 'object', 'properties': {'images': {
            'const': ['scene.png', str(self.root / 'design.png')]}}}
        write(self.root, 'request-schema.json', schema)
        self.plan['external_request']['schema'] = {'path': 'request-schema.json',
            'sha256': c.sha256_file(self.root / 'request-schema.json'), 'pointer': []}
        binding = self.capture_binding()
        (self.root / 'request-schema.json').unlink()
        with self.assertRaisesRegex(ValueError, 'saved external delivery violates acquired schema'):
            self.delivery(binding)

    def test_board_delivery_keeps_one_saved_carrier_and_independent_panel_roles(self):
        import production_case_fixtures as cases
        import generation_references as refs
        cases.create(self.base / 'catalog-studio', self.base / 'runtime')
        self.plan = setup_plan(self.root)
        selected = [{'role': row['role'], 'source': {'kind': 'supplied-file',
            'reference_id': row['id'], 'resolved_path': str(self.root / row['file'])}}
            for row in self.plan['references']]
        prepared = refs.prepare_references(selected, model=cases.MODEL_ID,
            output_dir=self.base / 'carriers', max_side=96, transport_mode='single-board')
        write(self.root, 'references.json', prepared)
        self.plan['prepared_references'] = 'references.json'
        board = prepared['single_board']
        request = c.load(self.root / 'request.json')
        request['images'] = [board['resolved_path']]
        write(self.root, 'request.json', request)
        for row, reference, field in zip(self.plan['references'], prepared['selected_references'],
                                        self.plan['external_request']['reference_fields'], strict=True):
            row.update(use_for=reference['authority']['controls'],
                       do_not_transfer=reference['authority']['must_not_control'])
            field.pop('evidence')
            field.update(field=['images', 0], value=board['resolved_path'], local_file=True)
        sync_external_prompt(self.root, self.plan, BOARD_REFERENCE_DIRECTION)
        board_bytes = Path(board['resolved_path']).read_bytes()
        binding = self.capture_binding(extra=[board_bytes])
        Path(board['resolved_path']).unlink()
        (self.root / 'scene.png').unlink()
        (self.root / 'design.png').unlink()
        delivery = self.delivery(binding)
        self.assertEqual(len(delivery['media']), 1)
        self.assertEqual(Path(delivery['request']['images'][0]).read_bytes(), board_bytes)
        self.assertEqual([row['attachment_number'] for row in delivery['reference_bindings']], [1, 1])
        self.assertEqual([row['region_pixels'] for row in delivery['reference_bindings']],
                         [panel['box'] for panel in board['panels']])
        self.assertTrue(all(row['sha256'] != board['sha256'] for row in delivery['references']))


class ExternalExecutionDeliveryTests(DeliveryFixture, unittest.TestCase):
    """Use the public run lifecycle with independently received host evidence."""

    def setUp(self):
        super().setUp()
        import work_ledger
        self.local_plan()
        work = work_ledger.begin(self.root, 'Synthetic saved-media execution', ['prepare', 'review'])
        task = {'task_id': work['task_id'], 'route': 'generation',
            'features': ['semantic-instruction-edit', 'instruction-edit'],
            'sources': [{'id': 'scene', 'path': 'scene.png', 'role': 'accepted-source',
                'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic scene.'},
                {'id': 'geometry', 'path': 'design.png', 'role': 'reference-images',
                 'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic geometry.'}],
            'delivery': {'path': 'prompt.txt', 'translation_notes': 'Keep the exact synthetic instruction.'},
            'criteria': [{'id': 'wall', 'strength': 'hard', 'text': 'Inspect the wall edit.'},
                         {'id': 'geometry', 'strength': 'hard', 'text': 'Inspect preserved vase geometry.'}],
            'world_views': [], 'semantic_edit': 'edit-plan.json', 'image_input': 'image-input.json'}
        fixtures.task(self.root, task, artifact='image', execution='external', focus='supporting-setting')
        for row in task['criteria']:
            row['evidence'] = 'image'
        write(self.root, 'task.json', task)

    def test_from_run_draft_and_preparation_keep_saved_external_inputs_without_originals(self):
        import production_inputs
        import production_operations as workflow
        run = workflow.prepare(self.root, 'task.json')['run']
        original = copy.deepcopy(workflow.read_run(self.root, run).consumer['image_input'])
        for name in ('scene.png', 'design.png', 'image-input.json', 'request.json',
                     'model-evidence.json', 'prompt.txt', 'edit-plan.json', 'task.json'):
            (self.root / name).unlink()
        draft = authoring_fixtures.authoring_inputs(self.root, None, 'continued', from_run=run,
                                                   focus='supporting-setting')
        self.assertEqual(draft['unresolved'], [], draft)
        choices = c.load(self.root / draft['choices_file'])
        for reference in choices['external']['image_input']['references']:
            self.assertTrue((self.root / reference['file']).is_file())
            self.assertTrue(reference['transport']['local_file'])
            self.assertNotIn('value', reference['transport'])
        child = workflow.prepare(self.root, choices=draft['choices_file'])['run']
        binding = workflow.read_run(self.root, child).consumer['image_input']
        self.assertEqual(binding['external_request']['request']['prompt'], original['external_request']['request']['prompt'])
        self.assertEqual([row['sha256'] for row in binding['references']],
                         [row['sha256'] for row in original['references']])
        self.assertEqual([row['role'] for row in binding['references']],
                         [row['role'] for row in original['references']])

    def test_public_reopen_distinguishes_saved_input_images_from_captured_output(self):
        import subprocess
        import sys
        import production_operations as workflow
        import work_ledger

        def invoke(argv):
            completed = subprocess.run(argv, cwd=self.root, capture_output=True,
                text=True, encoding='utf-8', timeout=45)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            return json.loads(completed.stdout)

        def production(command, *arguments):
            return invoke([sys.executable, str(Path(__file__).with_name('production_workflow.py')),
                           command, '--root', str(self.root), *arguments])

        run = workflow.prepare(self.root, 'task.json')['run']
        fixtures.handoff(self.root, run, 'synthetic-host', 'manual')
        token = fixtures.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        workflow.claim_external(self.root, run, 1, token)
        pixels = png((25, 50, 75))
        write(self.root, 'output.png', pixels)
        captured = workflow.capture(self.root, run, 'output.png', 'Synthetic local fixture; no provider call.')
        (self.root / 'output.png').unlink()
        parent = workflow.read_run(self.root, run)
        before = copy.deepcopy(parent.rows)
        expected_inputs = [row['sha256'] for row in parent.consumer['image_input']['references']]
        inspected = production('inspect-inputs', '--from-run', run, '--view', 'full')
        reuse = inspected['source_run']['input_reuse']
        self.assertFalse(reuse['automatic_output_selection'])
        self.assertIn('saved authored inputs', reuse['meaning'])
        self.assertIn('no re-entry', reuse['meaning'])
        [output] = reuse['captured_outputs']
        self.assertEqual((output['candidate'], output['artifact']), (captured['sha256'], 'image'))
        [selected_file] = output['files']
        self.assertEqual(selected_file, {'path': f'production/runs/{run}/objects/{c.digest(pixels)}',
                                        'sha256': c.digest(pixels), 'size': len(pixels)})
        self.assertEqual((self.root / selected_file['path']).read_bytes(), pixels)
        self.assertEqual(invoke(reuse['read_action']['argv'])['runs'][0]['candidates'], [captured['sha256']])

        work_ledger.suspend(self.root, reason='Keep the captured parent while opening explicit follow-up work.')
        write(self.root, 'follow-up.txt', b'Change only the fixture wall color in the captured output.')
        draft = production('draft-inputs', '--from-run', run, '--operation', 'amend',
            '--new-task', 'Synthetic follow-up to the captured result.', '--request-file', 'follow-up.txt',
            '--out-dir', 'follow-up', '--focus', 'supporting-setting')
        for key, value in reuse.items():
            self.assertEqual(draft['derived_from']['source_run']['input_reuse'][key], value, key)
        choices = c.load(self.root / draft['choices_file'])
        references = choices['external']['image_input']['references']
        self.assertEqual([c.sha256_file(self.root / row['file']) for row in references], expected_inputs)
        self.assertNotIn(selected_file['sha256'], expected_inputs)
        self.assertEqual(choices['authoring']['task']['criteria'], parent.prepared['task']['criteria'])
        self.assertIsNone(choices['authoring']['task']['authority'])
        prompt = self.root / choices['authoring']['delivery']['file']
        self.assertEqual(prompt.read_bytes(), (parent.directory / 'delivery.txt').read_bytes())

        owner = draft['authoring_guide']['source_acquisition']
        self.assertEqual(owner['schema_pointer'], '/properties/sources/items')
        row = {'id': 'captured-output', 'path': selected_file['path'], 'role': 'reference-images',
               'disposition': 'considered-not-used', 'locator': 'whole image',
               'reason': 'The fixture author retains this candidate; its current reference use is undecided.'}
        write(self.root, owner['source_row_file'], row)
        invoke(owner['argv'])
        acquired = c.load(self.root / 'follow-up/work-basis.json')['sources']['captured-output']
        self.assertEqual(acquired['origin']['source'], row)
        self.assertNotIn('identity', acquired['origin']['source'])
        after = c.load(self.root / draft['choices_file'])
        self.assertEqual(after['external'], choices['external'])
        self.assertIsNone(after['authoring']['task']['authority'])
        explain = production('explain-inputs', '--choices', draft['choices_file'],
                             '--field', 'external.image_input.references')
        self.assertEqual(explain['fields'][0]['field'], 'external.image_input.references')
        self.assertEqual(workflow.read_run(self.root, run).rows, before)

    def test_manual_claim_refuses_an_unusable_native_projection_before_committing(self):
        import production_operations as workflow
        schema = {'type': 'object', 'properties': {'images': {
            'const': c.load(self.root / 'request.json')['images']}}}
        write(self.root, 'request-schema.json', schema)
        self.plan['external_request']['schema'] = {'path': 'request-schema.json',
            'sha256': c.sha256_file(self.root / 'request-schema.json'), 'pointer': []}
        write(self.root, 'image-input.json', self.plan)
        run = workflow.prepare(self.root, 'task.json')['run']
        fixtures.handoff(self.root, run, 'synthetic-host', 'manual')
        token = fixtures.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        with self.assertRaisesRegex(ValueError, 'saved external delivery violates acquired schema'):
            workflow.claim_external(self.root, run, 1, token)
        self.assertFalse(any(row['event'] == 'external-claim' for row in workflow.read_run(self.root, run).rows))

    def test_canonical_board_draft_survives_deleted_svg_sources_and_panel_carriers(self):
        import shutil
        import generation_references as refs
        import production_case_fixtures as cases
        import production_inputs
        import production_operations as workflow
        cases.create(self.base / 'catalog-studio', self.base / 'runtime')
        task = c.load(self.root / 'task.json')
        sources = {row['id']: row for row in task['sources']}
        for row, source, color in zip(self.plan['references'], [sources['scene'], sources['geometry']],
                                       ('#145064', '#781e50'), strict=True):
            row['file'] = row['id'] + '.svg'
            source['path'] = row['file']
            write(self.root, row['file'], ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="24" '
                'viewBox="0 0 32 24"><rect width="32" height="24" fill="' + color + '"/></svg>').encode('utf-8'))
        selected = [{'role': row['role'], 'source': {'kind': 'supplied-file',
            'reference_id': row['id'], 'resolved_path': str(self.root / row['file'])}}
            for row in self.plan['references']]
        prepared = refs.prepare_references(selected, model=cases.MODEL_ID,
            output_dir=self.base / 'carriers', max_side=96, transport_mode='single-board')
        write(self.root, 'references.json', prepared)
        self.plan['prepared_references'] = 'references.json'
        request = c.load(self.root / 'request.json')
        request['images'] = [prepared['single_board']['resolved_path']]
        write(self.root, 'request.json', request)
        for row, selected, field in zip(self.plan['references'], prepared['selected_references'],
                                       self.plan['external_request']['reference_fields'], strict=True):
            row.update(use_for=selected['authority']['controls'],
                       do_not_transfer=selected['authority']['must_not_control'])
            self.assertNotEqual(selected['source']['sha256'], selected['transport']['sha256'])
            field.update(field=['images', 0], value=request['images'][0])
        sync_external_prompt(self.root, self.plan,
            'Edit the scene panel wall color. ' + BOARD_REFERENCE_DIRECTION)
        write(self.root, 'image-input.json', self.plan)
        from reading_fixtures import task_reading
        task_reading(self.root, task)
        fixtures.bind_work_basis(self.root, task,
            request='Edit the cafe scene panel while preserving the original vase geometry.',
            focus='supporting-setting')
        write(self.root, 'task.json', task)
        from production_diagnostics import CompilationError
        try:
            run = workflow.prepare(self.root, 'task.json')['run']
        except CompilationError as exc:
            self.fail(json.dumps(exc.report['diagnostics'], indent=2))
        for name in ('scene.svg', 'design.svg', 'references.json', 'image-input.json', 'request.json',
                     'model-evidence.json', 'prompt.txt', 'edit-plan.json', 'task.json'):
            (self.root / name).unlink()
        shutil.rmtree(self.base / 'carriers')
        draft = authoring_fixtures.authoring_inputs(self.root, None, 'continued-board', from_run=run,
                                                   focus='supporting-setting')
        self.assertEqual(draft['unresolved'], [], draft)
        try:
            child = workflow.prepare(self.root, choices=draft['choices_file'])['run']
        except CompilationError as exc:
            self.fail(json.dumps(exc.report['diagnostics'], indent=2))
        loaded = workflow.read_run(self.root, child)
        binding = loaded.consumer['image_input']
        self.assertEqual(binding['prepared_reference_set']['transport_mode'], 'single-board')
        self.assertEqual([row['sha256'] for row in binding['references']],
                         [row['source']['sha256'] for row in prepared['selected_references']])
        delivery = image_input.external_delivery(binding, run_directory=loaded.directory,
                                                 read_object=loaded.evidence.read)
        self.assertEqual(len(delivery['request']['images']), 1)
        self.assertEqual([row['role'] for row in delivery['reference_bindings']], ['scene', 'geometry'])

    def test_execute_and_receive_share_saved_local_arguments_after_authoring_edits(self):
        import production_case_fixtures as cases
        import production_execution as execution
        import production_operations as workflow
        import production_workspace
        run = workflow.prepare(self.root, 'task.json')['run']
        expected = production_workspace.workspace(self.root, run, phase='input')['prepared_input']
        drafted = execution.draft_execution(self.root, run)
        self.assertEqual(drafted['host_request']['request'], expected['request'])
        decisions = cases.fill_decisions(self.root, run, 'decisions.json')
        for name in ('scene.png', 'design.png', 'image-input.json', 'request.json',
                     'model-evidence.json', 'prompt.txt', 'edit-plan.json', 'task.json'):
            (self.root / name).unlink()
        result = execution.execute(self.root, run, decisions_file=decisions)
        request = result['host_request']['request']
        self.assertEqual(request, expected['request'])
        self.assertTrue(all(Path(path).is_file() for path in request['images']))
        write(self.root, 'host-call.json', {'synthetic': True, 'arguments': request, 'call_id': 'fixture-call'})
        write(self.root, 'host-response.json', {'synthetic': True, 'status': 'complete'})
        write(self.root, 'output.png', png((25, 50, 75)))
        received = workflow.receive_external(self.root, run, response_file='host-response.json',
            artifacts=['output.png'], submission_file='host-call.json', request_pointer=['arguments'],
            final=True, reason='Synthetic local host observation; no provider call.')
        self.assertTrue(received['execution_completed'])
        self.assertEqual(received['request_evidence']['status'], 'matched-recorded-call')
        self.assertEqual(received['request_evidence']['submitted_request_sha256'], c.content_id(request))

    def test_public_parallel_external_tasks_receive_reverse_order_without_resending(self):
        import subprocess
        import sys
        import execution_lifecycle as lifecycle
        import production_case_fixtures as cases
        import production_operations as workflow
        import work_ledger

        def invoke(script, arguments, *, code=0, json_output=True):
            result = subprocess.run([sys.executable, str(Path(__file__).with_name(script)), *arguments],
                cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=45)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            return json.loads(result.stdout) if json_output else result.stdout

        def production(command, *arguments, code=0):
            return invoke('production_workflow.py', [command, '--root', str(self.root), *arguments], code=code)

        task_a = work_ledger.require_open(self.root)['task_id']
        run_a = production('prepare', '--task', 'task.json')['run']
        decisions_a = cases.fill_decisions(self.root, run_a, 'decisions-a.json')
        call_a = production('execute', '--run', run_a, '--decisions-file', decisions_a, '--view', 'full')
        self.assertEqual(call_a['state'], 'host-call-required')
        invoke('work_ledger.py', ['suspend', '--studio', str(self.root), '--reason',
            'Keep A waiting for its synthetic host result while opening independent B.'], json_output=False)
        invoke('work_ledger.py', ['begin', '--studio', str(self.root), '--goal',
            'Independent synthetic image B.', '--step', 'Receive and inspect B.'], json_output=False)
        task_b = work_ledger.require_open(self.root)['task_id']
        write(self.root, 'prompt-b.txt', b'A green glass bowl stands on a round table.')
        spec_b = {'task_id': task_b, 'route': 'generation', 'features': ['generation-package'],
            'sources': [], 'delivery': {'path': 'prompt-b.txt', 'translation_notes': 'Exact synthetic B request.'},
            'criteria': [{'id': 'output-b', 'strength': 'hard', 'text': 'Inspect the actual B image.'}],
            'world_views': []}
        fixtures.external_image_input(self.root, spec_b)
        fixtures.task(self.root, spec_b, artifact='image', execution='external', focus='supporting-setting')
        write(self.root, 'task-b.json', spec_b)
        run_b = production('prepare', '--task', 'task-b.json')['run']
        decisions_b = cases.fill_decisions(self.root, run_b, 'decisions-b.json')
        call_b = production('execute', '--run', run_b, '--decisions-file', decisions_b, '--view', 'full')
        self.assertEqual(call_b['state'], 'host-call-required')
        self.assertNotEqual(task_a, task_b)
        self.assertNotEqual(run_a, run_b)
        self.assertNotEqual(call_a['host_request']['claim'], call_b['host_request']['claim'])
        self.assertNotEqual(call_a['host_request']['request'], call_b['host_request']['request'])
        active_before = (self.root / 'work/current.json').read_bytes()
        suspended_before = work_ledger.task_path(self.root, task_a).read_bytes()
        cases_by_label = {
            'a': (run_a, task_a, decisions_a, call_a, png((25, 50, 75))),
            'b': (run_b, task_b, decisions_b, call_b, png((150, 100, 50))),
        }
        received = {}
        # The second claim returns first. A then arrives while B is still active.
        for label in ('b', 'a'):
            run, task_id, decisions, call, pixels = cases_by_label[label]
            write(self.root, label + '-call.json', {'synthetic': True, 'call_id': 'fixture-' + label,
                                                  'arguments': call['host_request']['request']})
            write(self.root, label + '-response.json', {'synthetic': True, 'call_id': 'fixture-' + label,
                                                       'status': 'complete'})
            write(self.root, label + '-output.png', pixels)
            arguments = ['--run', run, '--response', label + '-response.json',
                '--artifact', label + '-output.png', '--call', label + '-call.json',
                '--request-pointer', '["arguments"]', '--reason', 'Synthetic reverse-order response for ' + label + '.']
            result = production('receive-external', *arguments)
            self.assertTrue(result['execution_completed'])
            self.assertEqual(result['request_evidence']['status'], 'matched-recorded-call')
            self.assertEqual(result['request_evidence']['submitted_request_sha256'],
                             c.content_id(call['host_request']['request']))
            [candidate] = result['candidates']
            received[run] = candidate
            loaded = workflow.read_run(self.root, run)
            self.assertEqual(loaded.prepared['task']['task_id'], task_id)
            [claim] = [row for row in loaded.rows if row['event'] == 'external-claim']
            self.assertEqual(claim['sha256'], call['host_request']['claim'])
            [candidate_row] = [row for row in loaded.rows if row['event'] == 'candidate']
            self.assertEqual(candidate_row['sha256'], candidate)
            self.assertEqual(candidate_row['data']['files'][0]['sha256'], c.digest(pixels))
            observed = production('workspace', '--run', run, '--candidate', candidate, '--phase', 'observe')
            self.assertEqual(observed['run'], run)
            self.assertEqual(Path(observed['candidate']['files'][0]['path']).read_bytes(), pixels)
            state = production('status', '--run', run)['runs'][0]
            self.assertEqual((state['run'], state['task_id'], state['candidates']), (run, task_id, [candidate]))
            before_retry = copy.deepcopy(loaded.rows)
            self.assertEqual(production('receive-external', *arguments)['candidates'], [candidate])
            refused = production('execute', '--run', run, '--decisions-file', decisions, code=4)
            self.assertIn('DISPATCH_ALREADY_CLAIMED', [row['code'] for row in refused['diagnostics']])
            self.assertEqual(workflow.read_run(self.root, run).rows, before_retry)
            self.assertEqual(lifecycle.summary(self.root, run=run)['submissions'], 1)
            self.assertEqual(work_ledger.require_open(self.root)['task_id'], task_b)
        self.assertNotEqual(received[run_a], received[run_b])
        status = production('status')
        self.assertEqual({row['run']: row['candidates'] for row in status['runs']},
                         {run: [candidate] for run, candidate in received.items()})
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 2)
        self.assertEqual((self.root / 'work/current.json').read_bytes(), active_before)
        self.assertEqual(work_ledger.task_path(self.root, task_a).read_bytes(), suspended_before)

    def test_manual_claim_command_exposes_the_same_saved_host_instruction(self):
        import production_execution as execution
        import production_operations as workflow
        run = workflow.prepare(self.root, 'task.json')['run']
        fixtures.handoff(self.root, run, 'synthetic-host', 'manual')
        token = fixtures.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        (self.root / 'scene.png').unlink()
        output = io.StringIO()
        with redirect_stdout(output), patch('sys.argv', ['production_workflow.py', 'claim-external',
                '--root', str(self.root), '--run', run, '--count', '1', '--authorization', token]):
            result = production_workflow_cli.main()
        self.assertEqual(result, 0, output.getvalue())
        instruction = json.loads(output.getvalue())
        self.assertEqual(instruction['artifact_type'], 'external-execution-instruction')
        loaded = workflow.read_run(self.root, run)
        claim = workflow.find(loaded.rows, 'external-claim')
        self.assertNotIn('host_request', claim)
        self.assertEqual(instruction, execution.external_instruction(self.root, run, claim=claim))
        self.assertTrue(all(Path(path).is_file() for path in instruction['host_request']['request']['images']))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
