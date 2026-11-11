"""External authoring through real image, schema and evidence contracts."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import execution_contract as c
import image_input
from input_evidence import InputEvidence
import production_external_inputs as authored
from semantic_edit_plan_smoke_test import PROMPT, TARGET, png, setup_plan, write


class ExternalInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        from production_fixtures import scratch_home
        from catalog_retrieval.runtime import configure_pack_runtime
        self.enterContext(scratch_home(self.root / 'home'))
        configure_pack_runtime(None)
        self.addCleanup(configure_pack_runtime, None)
        self.plan = setup_plan(self.root)
        self.request = c.load(self.root / 'request.json')

    def build(self, choice, delivery=PROMPT):
        files, report = authored.build(choice, {}, InputEvidence(self.root), self.root,
                                       'built', delivery.encode('utf-8'))
        return c.decode(files['image-input.json']), c.decode(files['external-request.json']), report

    def added_reference(self, choice):
        write(self.root, 'finish.png', png((180, 140, 20)))
        write(self.root, 'finish-upload.json', {'synthetic': True,
            'source_sha256': c.sha256_file(self.root / 'finish.png'), 'image_id': 'synthetic-finish'})
        row = {'id': 'finish', 'role': 'surface', 'file': 'finish.png',
               'use_for': ['surface finish'], 'do_not_transfer': ['camera framing'],
               'transport': {'value': 'synthetic-finish',
                   'evidence': {'path': 'finish-upload.json', 'locator': 'whole synthetic upload'}}}
        choice['image_input']['references'].append(row)
        return row

    def test_draft_and_build_preserve_native_controls_and_exact_delivery(self):
        self.request.update(seed=142, negative='warped table', vendor_extension={'quality': 'standard'})
        self.plan['external_request']['negative_field'] = ['negative']
        before = copy.deepcopy((self.plan, self.request))
        choice = authored.draft(self.plan, self.request)
        original_choice = copy.deepcopy(choice)
        delivery = 'A blue glass vase.\r\nKeep the square table.\r\n'
        plan, request, report = self.build(choice, delivery)
        self.assertEqual((self.plan, self.request), before)
        self.assertEqual(choice, original_choice)
        self.assertIsNone(choice['request']['prompt'])
        self.assertNotIn('reference_fields', choice['image_input']['external_request'])
        self.assertEqual(request['prompt'], delivery)
        self.assertEqual(request['images'], ['synthetic-scene', 'synthetic-design'])
        self.assertEqual(request['vendor_extension'], {'quality': 'standard'})
        self.assertEqual((request['seed'], request['negative']), (142, 'warped table'))
        self.assertEqual(plan['external_request']['sha256'], c.digest(c.encoded(request)))
        self.assertTrue(all('transport' not in row for row in plan['references']))
        self.assertEqual(report['schema_validation']['mode'], 'bounded-probe')

    def test_add_remove_and_redraft_derive_media_order_and_measured_evidence(self):
        choice = authored.draft(self.plan, self.request)
        finish = self.added_reference(choice)
        choice['image_input']['external_request']['count'] = 3
        plan, request, _ = self.build(choice)
        self.assertEqual(request['images'], ['synthetic-scene', 'synthetic-design', 'synthetic-finish'])
        self.assertEqual(request['count'], 3)
        fields = plan['external_request']['reference_fields']
        self.assertEqual([row['field'] for row in fields], [['images', 0], ['images', 1], ['images', 2]])
        self.assertEqual(fields[2]['evidence']['sha256'], c.sha256_file(self.root / 'finish-upload.json'))
        self.assertNotIn('field', finish['transport'])
        redraft = authored.draft(plan, request)
        redraft['image_input']['references'] = [redraft['image_input']['references'][2],
                                               redraft['image_input']['references'][0]]
        rebuilt, second, _ = self.build(redraft)
        self.assertEqual(second['images'], ['synthetic-finish', 'synthetic-scene'])
        self.assertEqual([row['field'] for row in rebuilt['external_request']['reference_fields']],
                         [['images', 0], ['images', 1]])
        self.assertEqual(rebuilt['references'][1]['do_not_transfer'], ['old wall color'])
        self.assertEqual(rebuilt['references'][0]['use_for'], ['surface finish'])

    def test_remove_all_references_keeps_native_empty_array_and_unowned_values(self):
        self.request['vendor_extension'] = {'image': 'independent-control-value'}
        choice = authored.draft(self.plan, self.request)
        choice['image_input']['references'] = []
        plan, request, _ = self.build(choice)
        self.assertEqual(request['images'], [])
        self.assertEqual(request['vendor_extension'], {'image': 'independent-control-value'})
        self.assertEqual(plan['references'], [])
        self.assertEqual(plan['external_request']['reference_fields'], [])
        self.assertEqual(request['prompt'], PROMPT)

    def test_mixed_content_preserves_text_and_relocates_its_declared_field(self):
        self.request.pop('images')
        self.request.pop('prompt')
        self.request['content'] = [
            {'type': 'image', 'url': 'synthetic-scene'},
            {'type': 'text', 'text': PROMPT},
            {'type': 'image', 'url': 'synthetic-design'},
            {'type': 'control', 'options': {'seed': 27}}]
        external = self.plan['external_request']
        external['prompt_field'] = ['content', 1, 'text']
        for row, index in zip(external['reference_fields'], (0, 2), strict=True):
            row['field'] = ['content', index, 'url']
        choice = authored.draft(self.plan, self.request)
        choice['image_input']['references'] = []
        plan, request, _ = self.build(choice)
        self.assertEqual(request['content'], [
            {'type': 'text', 'text': PROMPT}, {'type': 'control', 'options': {'seed': 27}}])
        self.assertEqual(plan['external_request']['prompt_field'], ['content', 0, 'text'])

    def test_native_array_root_uses_exact_target_and_acquired_schema(self):
        self.request = [self.request]
        external = self.plan['external_request']
        for field in ('prompt_field', 'model_field', 'operation_field', 'count_field'):
            external[field] = [0] + external[field]
        for row in external['reference_fields']:
            row['field'] = [0] + row['field']
        schema = {'type': 'array', 'minItems': 1, 'maxItems': 1,
            'items': {'type': 'object', 'additionalProperties': False,
                'required': ['model', 'operation', 'prompt', 'count', 'images'],
                'properties': {'model': {'const': TARGET['model_identifier']},
                    'operation': {'const': 'edit'}, 'prompt': {'type': 'string', 'minLength': 1},
                    'count': {'type': 'integer', 'minimum': 1},
                    'images': {'type': 'array', 'items': {'type': 'string'}}}}}
        write(self.root, 'array-schema.json', schema)
        external['schema'] = {'path': 'array-schema.json', 'pointer': []}
        choice = authored.draft(self.plan, self.request)
        choice['image_input']['references'].pop(0)
        plan, request, report = self.build(choice)
        self.assertIsInstance(request, list)
        self.assertEqual(request[0]['images'], ['synthetic-design'])
        self.assertEqual(request[0]['model'], TARGET['model_identifier'])
        self.assertEqual(plan['external_request']['reference_fields'][0]['field'], [0, 'images', 0])
        self.assertEqual(report['schema_validation'], {'mode': 'target-schema', 'unmeasured': []})

    def test_scalar_removal_preserves_other_native_fields(self):
        self.request.pop('images')
        self.request.update(initial='synthetic-scene', geometry='synthetic-design',
                            settings={'strength': 0.5, 'source': 'independent-setting'})
        for row, key in zip(self.plan['external_request']['reference_fields'], ('initial', 'geometry'), strict=True):
            row['field'] = [key]
        choice = authored.draft(self.plan, self.request)
        choice['image_input']['references'].pop(0)
        _, request, _ = self.build(choice)
        self.assertNotIn('initial', request)
        self.assertEqual(request['geometry'], 'synthetic-design')
        self.assertEqual(request['settings'], {'strength': 0.5, 'source': 'independent-setting'})

    def test_scalar_media_removal_follows_its_container_after_an_array_item_is_removed(self):
        self.request.pop('images')
        self.request.pop('prompt')
        self.request['content'] = [
            {'type': 'image', 'url': 'synthetic-scene'},
            {'type': 'instruction', 'text': PROMPT, 'reference': 'synthetic-design'},
            {'type': 'control', 'options': {'reference': 'independent-setting', 'seed': 27}}]
        external = self.plan['external_request']
        external['prompt_field'] = ['content', 1, 'text']
        for row, field in zip(external['reference_fields'],
                (['content', 0, 'url'], ['content', 1, 'reference']), strict=True):
            row['field'] = field
        choice = authored.draft(self.plan, self.request)
        choice['image_input']['references'] = []
        plan, request, _ = self.build(choice)
        self.assertEqual(request['content'], [
            {'type': 'instruction', 'text': PROMPT},
            {'type': 'control', 'options': {'reference': 'independent-setting', 'seed': 27}}])
        self.assertEqual(plan['external_request']['prompt_field'], ['content', 0, 'text'])
        self.assertEqual(plan['external_request']['reference_fields'], [])

    def test_shared_attachment_retains_independent_reference_scopes(self):
        self.plan['references'][1]['file'] = 'scene.png'
        self.plan['external_request']['reference_fields'][1].update(field=['images', 0], value='synthetic-scene')
        self.request['images'] = ['synthetic-scene']
        choice = authored.draft(self.plan, self.request)
        plan, request, _ = self.build(choice)
        self.assertEqual(request['images'], ['synthetic-scene'])
        self.assertEqual([row['field'] for row in plan['external_request']['reference_fields']],
                         [['images', 0], ['images', 0]])
        self.assertEqual([row['use_for'] for row in plan['references']],
                         [['composition', 'camera framing'], ['vase geometry']])

    def test_undeclared_media_is_rejected_even_when_all_selected_references_are_removed(self):
        choice = authored.draft(self.plan, self.request)
        choice['request']['images'].append('unbound-media')
        choice['image_input']['references'] = []
        with self.assertRaisesRegex(ValueError, 'outside its declared source slots'):
            self.build(choice)

    def test_actual_evidence_and_native_schema_are_not_replaced_by_generated_values(self):
        choice = authored.draft(self.plan, self.request)
        choice['image_input']['references'][0]['transport']['evidence']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'external evidence changed'):
            self.build(choice)
        choice = authored.draft(self.plan, self.request)
        write(self.root, 'exact-schema.json', {'type': 'object', 'properties': {'count': {'const': 1}}})
        choice['image_input']['external_request'].update(
            schema={'path': 'exact-schema.json', 'pointer': []}, count=2)
        with self.assertRaisesRegex(ValueError, 'violates acquired schema'):
            self.build(choice)

    def test_saved_evidence_does_not_authorize_a_different_value_for_the_same_carrier(self):
        prepared = self.prepared_fixture('multi-image')
        choice = authored.draft(self.plan, self.request, prepared=prepared, package_root=self.root, root=self.root)
        self.assertTrue(choice['source_uploads'])
        transport = choice['image_input']['references'][0]['transport']
        transport['value'] += '-different'
        _, report = authored.build(choice, {}, InputEvidence(self.root), self.root,
                                   'different-value', PROMPT.encode())
        self.assertEqual(report['state'], 'reference-upload-required')
        pending = report['unresolved'][0]
        self.assertEqual((pending['code'], pending['reason']), ('AUTHORED_CHOICE_REQUIRED', 'provider-upload-required'))
        self.assertIn('does not match its carrier and provider media value', pending['message'])
        self.assertIn('transport', pending['required_action'])

    def test_a_new_evidence_file_needs_no_manual_hash_edit(self):
        choice = authored.draft(self.plan, self.request)
        evidence = choice['image_input']['references'][0]['transport']['evidence']
        self.assertNotIn('sha256', evidence)
        write(self.root, 'new-upload-evidence.json', {'synthetic': True, 'media': 'synthetic-scene'})
        evidence['path'] = 'new-upload-evidence.json'
        plan, _, _ = self.build(choice)
        measured = plan['external_request']['reference_fields'][0]['evidence']
        self.assertEqual(measured['sha256'], c.sha256_file(self.root / evidence['path']))
        self.assertEqual(choice['source_files']['upload-evidence.json'], c.sha256_file(self.root / 'upload-evidence.json'))

    def prepared_fixture(self, mode):
        import production_case_fixtures as cases
        import prepare_generation_references as refs
        case = cases.create(self.root / 'studio', self.root / 'runtime')
        self.root = case['root']
        self.plan = setup_plan(self.root)
        self.request = c.load(self.root / 'request.json')
        selections = [{'role': row['role'], 'source': {'kind': 'supplied-file',
            'reference_id': row['id'], 'resolved_path': str(self.root / row['file'])}}
            for row in self.plan['references']]
        prepared = refs.prepare_references(selections, model=cases.MODEL_ID,
            output_dir=self.root / 'original-carriers', max_side=96, transport_mode=mode)
        self.plan['prepared_references'] = 'prepared.json'
        write(self.root, 'prepared.json', prepared)
        values = ['synthetic-board'] if mode == 'single-board' else ['synthetic-scene', 'synthetic-design']
        carriers = [prepared['single_board']] if mode == 'single-board' else [row['transport'] for row in prepared['selected_references']]
        self.request['images'] = values
        write(self.root, 'request.json', self.request)
        write(self.root, 'upload-evidence.json', {'synthetic': True,
            'carriers': [{'image_id': value, 'sha256': row['sha256']} for value, row in zip(values, carriers, strict=True)]})
        for index, (row, source, field) in enumerate(zip(self.plan['references'], prepared['selected_references'],
                self.plan['external_request']['reference_fields'], strict=True)):
            row.update(use_for=source['authority']['controls'], do_not_transfer=source['authority']['must_not_control'])
            attachment = 0 if mode == 'single-board' else index
            field.update(field=['images', attachment], value=values[attachment])
            field['evidence']['sha256'] = c.sha256_file(self.root / 'upload-evidence.json')
        write(self.root, 'image-input.json', self.plan)
        task = copy.deepcopy(case['task'])
        task.pop('generation')
        task.pop('recording')
        task.update(execution='external', image_input='image-input.json')
        from reading_fixtures import task_reading
        task_reading(self.root, task)
        write(self.root, 'task.json', task)
        return prepared

    def test_prepared_multi_image_retains_canonical_source_and_separate_external_target(self):
        prepared = self.prepared_fixture('multi-image')
        choice = authored.draft(self.plan, self.request, prepared=prepared, package_root=self.root, root=self.root)
        self.assertEqual(set(choice['image_input']['references'][0]), {'id', 'transport'})
        self.assertNotEqual(choice['reference_delivery']['target_model'], TARGET['model_identifier'])
        files, report = authored.build(choice, {}, InputEvidence(self.root), self.root, 'rebuilt', PROMPT.encode())
        self.assertEqual(report['state'], 'materialized')
        plan = c.decode(files['image-input.json'])
        output = c.decode(files['external-request.json'])
        self.assertEqual(plan['model']['target'], TARGET)
        self.assertEqual(output, self.request)
        self.assertEqual([row['use_for'] for row in plan['references']], [row['authority']['controls'] for row in prepared['selected_references']])
        for name, raw in files.items():
            write(self.root, 'rebuilt/' + name, raw)
        binding = image_input.validate(plan, self.root)
        self.assertEqual([row['source']['kind'] for row in binding['prepared_reference_set']['selected_references']],
                         ['supplied-file', 'supplied-file'])

    def test_common_builder_publishes_changed_board_before_actual_upload_selection(self):
        import production_inputs
        import production_target
        prepared = self.prepared_fixture('single-board')
        draft = production_inputs.draft_inputs(self.root, 'task.json', 'draft')
        path = draft['choices_file']
        choice = c.load(self.root / path)
        external = choice['external']
        external['reference_delivery']['choices']['additional_references'].pop()
        # The source choice owns deletion; its old transport needs no second edit.
        self.assertEqual(len(external['image_input']['references']), 2)
        write(self.root, path, choice)
        partial = production_inputs.build_inputs(self.root, None, path, 'carrier-stage')
        self.assertFalse(partial['ok'])
        self.assertFalse(partial['execution_ready'])
        self.assertEqual(partial['request_state'], 'reference-upload-required')
        self.assertFalse((self.root / 'carrier-stage/production-task.json').exists())
        self.assertFalse((self.root / 'carrier-stage/external-request.json').exists())
        carrier = partial['external_input']['carriers'][0]
        self.assertNotEqual(carrier['sha256'], prepared['single_board']['sha256'])
        self.assertEqual(c.sha256_file(self.root / carrier['path']), carrier['sha256'])
        write(self.root, 'copied-old-upload.json', (self.root / 'upload-evidence.json').read_bytes())
        for change in ('value-only', 'file-only', 'file-and-value', 'copied-evidence'):
            altered = copy.deepcopy(choice)
            transport = altered['external']['image_input']['references'][0]['transport']
            if change != 'value-only':
                transport['uploaded_file'] = carrier['path']
            if change != 'file-only':
                transport['value'] = 'synthetic-rebuilt-board'
            if change == 'copied-evidence':
                transport['evidence']['path'] = 'copied-old-upload.json'
            with self.subTest(retained_upload=change):
                reader = InputEvidence(self.root)
                projected = production_target.project(altered, altered['authoring']['task'],
                    self.root, reader, 'refused-upload')
                self.assertEqual(projected['unresolved'], [])
                _, refused = authored.build(projected['choices']['external'], projected['task'], reader, self.root,
                    'refused-upload', PROMPT.encode(), derived_files=projected['files'])
                self.assertEqual(refused['state'], 'reference-upload-required')
                self.assertTrue(refused['unresolved'])
        write(self.root, 'new-board-upload.json', {'synthetic': True,
            'sha256': carrier['sha256'], 'image_id': 'synthetic-rebuilt-board'})
        selected = external['image_input']['references'][0]['transport']
        selected.update(uploaded_file=carrier['path'], value='synthetic-rebuilt-board',
                        evidence={'path': 'new-board-upload.json', 'locator': 'whole synthetic upload'})
        write(self.root, path, choice)
        result = production_inputs.build_inputs(self.root, None, path, 'final-inputs')
        self.assertTrue(result['ok'], result)
        task = c.load(self.root / result['inputs']['production-task']['path'])
        plan = c.load(self.root / task['image_input'])
        native = c.load(self.root / result['inputs']['external-request']['path'])
        self.assertEqual(native['images'], ['synthetic-rebuilt-board'])
        self.assertEqual([row['id'] for row in plan['references']], ['scene'])
        self.assertEqual(plan['references'][0]['use_for'], self.plan['references'][0]['use_for'])
        self.assertEqual(task['criteria'], choice['authoring']['task']['criteria'])
        image_input.validate(plan, self.root)

    def test_one_actual_board_upload_serves_all_its_logical_references(self):
        prepared = self.prepared_fixture('single-board')
        choice = authored.draft(self.plan, self.request, prepared=prepared, package_root=self.root, root=self.root)
        choice['reference_delivery']['choices']['max_side'] = 64
        files, pending = authored.build(choice, {}, InputEvidence(self.root), self.root,
            'shared-carrier', PROMPT.encode())
        self.assertEqual(len(pending['unresolved']), 2)
        for name, raw in files.items():
            write(self.root, 'shared-carrier/' + name, raw)
        carrier = pending['carriers'][0]
        write(self.root, 'shared-upload.json', {'synthetic': True,
            'sha256': carrier['sha256'], 'value': 'synthetic-new-shared-board'})
        choice['image_input']['references'][0]['transport'].update(
            uploaded_file=carrier['path'], value='synthetic-new-shared-board',
            evidence={'path': 'shared-upload.json', 'locator': 'whole synthetic upload'})
        files, ready = authored.build(choice, {}, InputEvidence(self.root), self.root,
            'shared-final', PROMPT.encode())
        self.assertEqual(ready['state'], 'materialized')
        self.assertEqual(c.decode(files['external-request.json'])['images'], ['synthetic-new-shared-board'])
        plan = c.decode(files['image-input.json'])
        self.assertEqual([row['field'] for row in plan['external_request']['reference_fields']],
                         [['images', 0], ['images', 0]])
        self.assertEqual([row['evidence']['path'] for row in plan['external_request']['reference_fields']],
                         ['shared-upload.json', 'shared-upload.json'])

    def test_first_use_requires_real_choices_and_file_selection_uses_same_builder(self):
        self.assertEqual([row['field'] for row in authored.unresolved(authored.template())],
                         ['external.image_input', 'external.request'])
        with self.assertRaisesRegex(ValueError, 'requires selected choices'):
            self.build(authored.template())
        plan, request, report = self.build({'image_input': 'image-input.json'})
        self.assertEqual(request, self.request)
        self.assertEqual(report['source']['path'], 'image-input.json')
        self.assertEqual(plan['references'][0]['sha256'], c.sha256_file(self.root / 'scene.png'))

    def test_native_array_reaches_check_prepare_and_one_host_instruction(self):
        import production_case_fixtures as cases
        import production_compiler
        import production_execution
        import production_fixtures
        import production_workflow
        import work_ledger
        from unittest.mock import patch
        import transport_synthetic

        external = self.plan['external_request']
        for field in ('prompt_field', 'model_field', 'operation_field', 'count_field'):
            external[field] = [0] + external[field]
        for row in external['reference_fields']:
            row['field'] = [0] + row['field']
        choice = authored.draft(self.plan, [self.request])
        plan, request, _ = self.build(choice)
        write(self.root, 'built/image-input.json', plan)
        write(self.root, 'built/external-request.json', request)
        entry = work_ledger.begin(self.root, 'Synthetic native-array preparation', ['prepare', 'review'])
        task = {'task_id': entry['task_id'], 'route': 'generation',
            'features': ['semantic-instruction-edit', 'instruction-edit'],
            'sources': [{'id': 'scene', 'path': 'scene.png', 'role': 'accepted-source',
                'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic source scene.'},
                {'id': 'design', 'path': 'design.png', 'role': 'reference-images',
                    'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic shape source.'}],
            'delivery': {'path': 'prompt.txt', 'translation_notes': 'One exact synthetic native-array instruction.'},
            'criteria': [{'id': 'wall', 'strength': 'hard', 'text': 'Inspect the requested wall edit.'},
                         {'id': 'geometry', 'strength': 'hard', 'text': 'Inspect the preserved vase geometry.'}],
            'world_views': [], 'semantic_edit': 'edit-plan.json', 'image_input': 'built/image-input.json'}
        production_fixtures.task(self.root, task, artifact='image', execution='external')
        for criterion in task['criteria']:
            criterion['evidence'] = 'image'
        write(self.root, 'task.json', task)
        checked = production_compiler.check_task(self.root, 'task.json')
        self.assertTrue(checked['ok'], checked)
        self.assertEqual(checked['request_preview'], request)
        prepared = production_workflow.prepare(self.root, 'task.json')
        self.assertEqual(prepared['execution_plan']['request'], request)
        run = prepared['run']
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('External host instruction must not send')):
            decision_file = cases.fill_decisions(self.root, run, 'synthetic-decisions.json')
            result = production_execution.execute(self.root, run, decisions_file=decision_file)
        self.assertEqual(result['state'], 'host-call-required')
        self.assertFalse(result['external_effect'])
        self.assertEqual(result['host_request']['request'], request)
        self.assertEqual(result['host_request']['target'], TARGET)
        rows = production_workflow.load_run(self.root, run)[3]
        self.assertEqual(len([row for row in rows if row['event'] == 'external-claim']), 1)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
