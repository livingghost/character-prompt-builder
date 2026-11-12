#!/usr/bin/env python3
"""Exercise the common editable surface without provider calls or invented consent."""
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
import production_authoring as authored
import production_inputs as inputs
import production_inputs_smoke_test as fixtures


class CommonAuthoringTests(unittest.TestCase):
    save_choices = fixtures.InputToolsTests.save_choices

    def setUp(self):
        fixtures.InputToolsTests.setUp(self)
        import work_ledger
        self.work = work_ledger.begin(self.root, 'Synthetic editable authoring.', ['Compose'])
        self.task['task_id'] = self.work['task_id']
        (self.root / 'task.json').write_bytes(c.encoded(self.task))

    def editable(self, directory='draft'):
        result = inputs.draft_inputs(self.root, 'task.json', directory)
        choices = c.load(self.root / result['choices_file'])
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        return result, choices

    def test_existing_text_edit_materializes_delivery_and_keeps_independent_criteria(self):
        result, choices = self.editable()
        (self.root / choices['authoring']['delivery']['file']).write_text(
            'Changed authored delivery.\n', encoding='utf-8')
        choices['authoring']['task']['direction']['purpose'] = 'Revised purpose.'
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, result['choices_file'], 'built')
        self.assertTrue(built['ok'])
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual((self.root / task['delivery']['path']).read_text(encoding='utf-8'), 'Changed authored delivery.\n')
        self.assertEqual(task['criteria'], self.task['criteria'])
        self.assertEqual(task['direction']['purpose'], 'Revised purpose.')
        self.assertEqual(task['authority'], self.task['authority'])
        self.assertEqual((self.root / 'delivery.txt').read_text(encoding='utf-8'), 'Synthetic authored delivery.\n')

    def test_declared_direction_source_is_edited_by_id_without_changing_review_criteria(self):
        text = '# Direction\n\nThe synthetic subject waits by the window.\n'
        (self.root / 'owner-direction.md').write_bytes(text.encode('utf-8'))
        self.task['sources'] = [{'id': 'owner-direction', 'path': 'owner-direction.md',
            'role': 'design', 'disposition': 'applied', 'locator': 'whole document',
            'reason': 'Explicit synthetic direction.'}]
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        result, choices = self.editable()
        self.assertEqual(choices['authoring']['sources']['owner-direction']['content'], text)
        changed = '# Direction\n\nThe synthetic subject sits by the window.\n'
        choices['authoring']['sources']['owner-direction']['content'] = changed
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, result['choices_file'], 'built')
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual((self.root / task['sources'][0]['path']).read_text(encoding='utf-8'), changed)
        self.assertEqual((self.root / 'owner-direction.md').read_text(encoding='utf-8'), text)
        self.assertEqual(task['criteria'], self.task['criteria'])
        self.assertEqual({key: value for key, value in task['sources'][0].items() if key != 'path'},
                         {key: value for key, value in self.task['sources'][0].items() if key != 'path'})

    def test_initial_creation_uses_open_work_identity_and_same_choices_build(self):
        result = inputs.draft_inputs(self.root, None, 'initial', route='development')
        choices = c.load(self.root / result['choices_file'])
        self.assertEqual(choices['authoring']['task']['task_id'], self.work['task_id'])
        delivery = self.root / choices['authoring']['delivery']['file']
        self.assertEqual(delivery.read_text(encoding='utf-8'), '')
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        choices['authoring']['task']['direction'] = copy.deepcopy(self.task['direction'])
        choices['authoring']['task']['criteria'] = copy.deepcopy(self.task['criteria'])
        delivery.write_text('First authored text.', encoding='utf-8')
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, result['choices_file'], 'initial-built')
        self.assertTrue(built['ok'])
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual(task['task_id'], self.work['task_id'])
        self.assertIsNone(task['authority'])
        self.assertEqual((self.root / task['delivery']['path']).read_text(encoding='utf-8'), 'First authored text.')
        self.assertEqual([row['operation'] for row in built['next_actions']], ['prepare'])

    def test_origin_is_required_and_identity_cannot_be_replaced_by_choices(self):
        result, choices = self.editable()
        choices['authoring']['task']['task_id'] = 'different-task'
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, result['choices_file'], 'built')
        self.assertFalse(built['ok'])
        self.assertEqual(built['diagnostics'][0]['code'], 'AUTHORING_DRAFT_UNREGISTERED')
        self.assertEqual(c.load(self.root / result['context_file'])['task_content']['task_id'], self.work['task_id'])
        self.assertFalse((self.root / 'built').exists())
        (self.root / 'orphan.json').write_bytes(c.encoded(choices))
        orphan = inputs.build_inputs(self.root, None, 'orphan.json', 'orphan-built')
        self.assertFalse(orphan['ok'])
        self.assertEqual(orphan['diagnostics'][0]['code'], 'AUTHORING_DRAFT_UNREGISTERED')
        self.assertFalse((self.root / 'orphan-built').exists())

    def test_source_task_change_is_detected_when_source_flags_are_omitted(self):
        result, choices = self.editable()
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        changed = copy.deepcopy(self.task)
        changed['criteria'][0]['text'] = 'Another criterion from a different revision.'
        (self.root / 'task.json').write_bytes(c.encoded(changed))
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            inputs.build_inputs(self.root, None, result['choices_file'], 'built')
        self.assertFalse((self.root / 'built').exists())

    def test_new_plot_approval_hash_is_derived_but_saved_approval_cannot_cover_changed_content(self):
        import prompt_plot
        plot = {'artifact_type': 'prompt-plot', 'story': [{'id': 's1', 'beat': 'Synthetic subject waits.', 'visibility': 'visible'}],
                'derived': [{'kind': 'shows', 'statement': 'one synthetic subject', 'from': ['s1']}],
                'approved': {'by': 'Synthetic fixture author', 'at': '2000-01-01T00:00:00Z'}}
        approved = authored._approved_plot(plot, None)
        self.assertEqual(approved['approved']['content_sha256'], prompt_plot.content_sha256(plot))
        self.assertEqual(authored._approved_plot(plot, approved), approved)
        changed = copy.deepcopy(plot)
        changed['story'][0]['beat'] = 'The subject moves.'
        with self.assertRaisesRegex(ValueError, 'previous approval covers'):
            authored._approved_plot(changed, approved)
        changed['approved'] = {'by': 'Synthetic fixture author', 'at': '2000-01-02T00:00:00Z'}
        new = authored._approved_plot(changed, approved)
        self.assertEqual(new['approved']['content_sha256'], prompt_plot.content_sha256(changed))

    def test_absent_reference_authoring_preserves_external_input_ownership(self):
        from input_evidence import InputEvidence
        import production_fixtures
        task = copy.deepcopy(self.task)
        task.update(artifact='image', execution='external')
        plan = production_fixtures.external_image_input(self.root, task)
        original = (self.root / plan).read_bytes()
        choices = authored.draft(self.root, task, InputEvidence(self.root))
        self.assertIsNone(choices['references'])
        for selected in (None, choices):
            with self.subTest(authoring=selected is not None):
                rebuilt, files, _ = authored.materialize(self.root, task, selected,
                    InputEvidence(self.root), 'rebuilt')
                self.assertEqual(rebuilt['image_input'], plan)
                self.assertNotIn('image-input.json', files)
                self.assertEqual((self.root / plan).read_bytes(), original)


class InitialCLITests(unittest.TestCase):
    def setUp(self):
        import production_fixtures
        import studio
        import work_ledger
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-initial-authoring-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.home = production_fixtures.scratch_home_dir(self.base / 'home')
        self.env = {**os.environ, 'CPB_HOME': str(self.home)}
        self.root = studio.init(self.base / 'studio', 'initial', 'Synthetic initial authoring')
        self.task_id = work_ledger.begin(self.root, 'Compose a synthetic local prompt.', ['Compose'])['task_id']
        self.cli = [sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py')]

    def call(self, arguments, code=0):
        result = subprocess.run(self.cli + arguments, cwd=self.base, env=self.env,
            capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_initial_cli_artifact_is_a_kind_and_defaults_are_owned_by_new_creation(self):
        for name, arguments, artifact, execution in (
                ('default', [], 'text', 'authored'),
                ('text', ['--artifact', 'text', '--execution', 'authored'], 'text', 'authored'),
                ('image', ['--artifact', 'image', '--execution', 'external'], 'image', 'external')):
            with self.subTest(kind=name):
                draft = self.call(['draft-inputs', '--root', str(self.root), '--route', 'development',
                    '--out-dir', name, *arguments])
                task = draft['choices']['authoring']['task']
                self.assertEqual((task['task_id'], task['artifact'], task['execution']),
                    (self.task_id, artifact, execution))
                self.assertTrue((self.root / draft['choices_file']).is_file())
                self.assertFalse(draft['external_effect'])

    def test_initial_flags_cannot_silently_replace_an_existing_task(self):
        draft = self.call(['draft-inputs', '--root', str(self.root), '--route', 'development', '--out-dir', 'initial'])
        context = c.load(self.root / draft['context_file'])
        task = context['task_content']
        task['delivery']['path'] = 'delivery.txt'
        (self.root / 'delivery.txt').write_text('Synthetic existing delivery.', encoding='utf-8')
        (self.root / 'task.json').write_bytes(c.encoded(task))
        for flag, value in (('--artifact', 'image'), ('--execution', 'external')):
            with self.subTest(flag=flag):
                refused = self.call(['draft-inputs', '--root', str(self.root), '--task', 'task.json',
                    '--out-dir', 'rejected-' + flag[2:], flag, value], code=2)
                diagnostic = refused['diagnostics'][0]
                self.assertEqual(diagnostic['code'], 'INPUT_CONSISTENCY_ERROR')
                self.assertIn('authoring.task.' + flag[2:], diagnostic['requested_fields'])
                self.assertEqual(diagnostic['next_actions'][0]['operation'], 'draft-inputs')
                self.assertFalse((self.root / ('rejected-' + flag[2:])).exists())

    def test_local_upscale_draft_imports_actual_bytes_and_initializes_only_requested_content(self):
        from PIL import Image
        source = self.root.parent / 'outside-source.png'
        Image.new('RGB', (13, 9), 'steelblue').save(source)
        raw = source.read_bytes()
        result = self.call(['draft-inputs', '--root', str(self.root), '--route', 'upscale',
            '--source-image', str(source), '--scale', '4', '--purpose', 'Enlarge this image four times.',
            '--out-dir', 'work/local-upscale'])
        choices = c.load(self.root / result['choices_file'])
        authored = choices['authoring']
        self.assertEqual((authored['task']['artifact'], authored['task']['execution']), ('image', 'dispatcher'))
        self.assertEqual(authored['task']['task_id'], self.task_id)
        self.assertIsNone(authored['task']['authority'])
        self.assertEqual(authored['task']['direction']['decisions'], [])
        self.assertEqual(authored['upscale']['render_intent'],
                         {'artifact_type': 'render-intent', 'execution_mode': 'upscale'})
        self.assertIs(type(authored['upscale']['scale_factor']), int)
        self.assertEqual((self.root / authored['upscale']['source']).read_bytes(), raw)
        self.assertEqual(result['selected_image']['sha256'], c.digest(raw))
        self.assertEqual((result['selected_image']['width'], result['selected_image']['height']), (13, 9))
        self.assertFalse(any(row['field'] in {'authoring.task.criteria', 'authoring.task.direction.purpose'}
                             for row in result['unresolved']))
        self.assertTrue(result['next_actions'])


class DispatcherAuthoringTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        import production_fixtures
        import production_case_fixtures as cases
        from catalog_retrieval import runtime
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        self.case = cases.create(base / 'studio', base / 'runtime', with_upscale=True)
        self.root = self.case['root']
        self.addCleanup(runtime.configure_pack_runtime, None)

    def test_standalone_document_edits_change_new_inputs_and_preserve_captured_revisions(self):
        import production_workflow as workflow
        drafted = inputs.draft_inputs(self.root, 'task.json', 'editor')
        choices = drafted['choices']
        for selected in choices['authoring']['documents'].values():
            self.assertEqual(set(selected), {'file'})
            self.assertTrue((self.root / selected['file']).is_file())
        path = self.root / drafted['choices_file']
        choices_raw = path.read_bytes()
        parameters_path = choices['authoring']['documents']['parameters']['file']
        first = workflow.prepare(self.root, choices=drafted['choices_file'])
        original = workflow.read_run(self.root, first['run'])
        self.assertEqual(first['request_preview']['steps'], 20)
        with cases.edit_document(self.root, choices, 'parameters') as parameters:
            parameters['steps'] = 22
        current_raw = (self.root / parameters_path).read_bytes()
        self.assertEqual(path.read_bytes(), choices_raw)
        checked = inputs.compile_choices(self.root, drafted['choices_file'])
        self.assertTrue(checked.report['publishable'], checked.report['diagnostics'])
        self.assertEqual(checked.report['request_preview']['steps'], 22)
        second = workflow.prepare(self.root, choices=drafted['choices_file'])
        revised = workflow.read_run(self.root, second['run'])
        self.assertEqual(second['request_preview']['steps'], 22)
        self.assertNotEqual(original.prepared['input_sha256'], revised.prepared['input_sha256'])
        self.assertEqual(revised.prepared['authoring']['choices_ref']['files'][parameters_path],
                         c.digest(current_raw))
        self.assertEqual(workflow.read_run(self.root, first['run']).artifacts['request-contract.json']['request']['steps'], 20)
        reopened = inputs.draft_inputs(self.root, None, 'reopened', from_run=first['run'])
        self.assertEqual(cases.read_document(self.root, reopened['choices'], 'parameters')['steps'], 20)
        self.assertEqual((self.root / parameters_path).read_bytes(), current_raw)

    def test_document_repair_names_its_source_contract_and_needs_no_choices_copy(self):
        import production_document_contracts
        import production_workflow as workflow
        drafted = inputs.draft_inputs(self.root, 'task.json', 'editor')
        choices = drafted['choices']
        cases.write_document(self.root, choices, 'negative_provenance', {'activated_sources': 'invalid'})
        cases.write(self.root / drafted['choices_file'], choices)
        choices_raw = (self.root / drafted['choices_file']).read_bytes()
        source = choices['authoring']['documents']['negative_provenance']['file']
        failed = inputs.compile_choices(self.root, drafted['choices_file']).report
        workflow.schema_check(failed, 'compilation-report')
        diagnostics = [item for item in failed['diagnostics'] if item.get('file') == source]
        self.assertTrue(diagnostics, failed['diagnostics'])
        owner = production_document_contracts.guidance('negative_provenance')
        self.assertTrue(all(all(item['guidance'][key] == value for key, value in owner.items())
                            for item in diagnostics))
        self.assertTrue(all(source in item['required_action'] for item in diagnostics))
        cases.write_document(self.root, choices, 'negative_provenance', {'activated_sources': [],
            'diagnostic_sources_retained': [], 'semantic_exclusions_user_supplied': []})
        self.assertEqual((self.root / drafted['choices_file']).read_bytes(), choices_raw)
        repaired = inputs.compile_choices(self.root, drafted['choices_file']).report
        self.assertTrue(repaired['publishable'], repaired['diagnostics'])

    def reference_task(self):
        from PIL import Image
        import prepare_generation_references as references
        import production_case_fixtures as cases
        selections = []
        for index, color in enumerate(('red', 'blue')):
            path = self.root / f'reference-{index}.png'
            Image.new('RGB', (16, 16), color).save(path)
            selections.append({'role': 'surface', 'source': {'kind': 'supplied-file',
                'reference_id': f'reference-{index}', 'resolved_path': str(path)}})
        prepared = references.prepare_references(selections, model=cases.MODEL_ID,
            output_dir=self.root / 'original-carriers', max_side=64)
        (self.root / 'prepared.json').write_bytes(c.encoded(prepared))
        task = c.load(self.root / 'task.json')
        task['generation']['references'] = 'prepared.json'
        uploaded = self.root / 'hosted-carriers'
        uploaded.mkdir()
        task['upload_sources'] = []
        for index, row in enumerate(prepared['selected_references']):
            path = uploaded / f'reference-{index}.png'
            path.write_bytes(Path(row['transport']['resolved_path']).read_bytes())
            task['upload_sources'].append({'file': path.relative_to(self.root).as_posix(),
                'url': f'https://files.example/reference-{index}.png'})
        (self.root / 'task.json').write_bytes(c.encoded(task))
        return task, prepared

    def test_reference_removal_prunes_only_unused_url_choices_without_reading_removed_carriers(self):
        original, _ = self.reference_task()
        draft = inputs.draft_inputs(self.root, 'task.json', 'draft')
        choices = c.load(self.root / draft['choices_file'])
        self.assertEqual(set(choices['authoring']['source_files']),
            {row['file'] for row in original['upload_sources']})
        choices['authoring']['references']['additional_references'].pop(0)
        (self.root / original['upload_sources'][0]['file']).unlink()
        (self.root / draft['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, draft['choices_file'], 'built')
        self.assertTrue(built['ok'], built)
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual(task['upload_sources'], [original['upload_sources'][1]])
        self.assertEqual(task['criteria'], original['criteria'])
        import request_contract
        from prepare_generation_references import host_reference_transports
        prepared = c.load(self.root / task['generation']['references'])
        media = [request_contract.media_metadata(Path(row['resolved_path']), role=row['role'])
            for row in host_reference_transports(prepared, package_root=(self.root / task['generation']['references']).parent)]
        bound = request_contract.bind_upload_sources(media, task['upload_sources'], 'url',
            read=lambda path: c.read(self.root / path))
        self.assertEqual(bound[0]['upload_source']['url'], original['upload_sources'][1]['url'])

    def test_retained_url_never_follows_changed_bytes_at_its_selected_source_path(self):
        original, _ = self.reference_task()
        draft = inputs.draft_inputs(self.root, 'task.json', 'draft')
        path = self.root / original['upload_sources'][0]['file']
        from PIL import Image
        Image.new('RGB', (16, 16), 'green').save(path)
        with self.assertRaisesRegex(ValueError, 'input reference bytes differ'):
            inputs.build_inputs(self.root, None, draft['choices_file'], 'built')
        self.assertFalse((self.root / 'built').exists())

    def test_common_reference_revision_prepares_one_carrier_with_captured_url_source(self):
        from unittest.mock import patch
        import production_case_fixtures as cases
        import production_workflow as workflow
        import request_contract
        import transport_synthetic
        original, _ = self.reference_task()
        draft = inputs.draft_inputs(self.root, 'task.json', 'draft')
        choices = c.load(self.root / draft['choices_file'])
        with cases.edit_document(self.root, choices, 'production_spec') as document:
            document['render_intent']['execution_mode'] = 'reference-guided'
        choices['authoring']['references']['additional_references'].pop(0)
        removed, retained = original['upload_sources']
        (self.root / removed['file']).unlink()
        (self.root / draft['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, draft['choices_file'], 'built')
        self.assertTrue(built['ok'], built)
        # Only the source mode is synthetic here: compilation, publication and
        # source snapshots are real. Preparation must never upload or send.
        with patch.object(transport_synthetic, 'UPLOAD_SOURCE', 'url'), \
                patch.object(transport_synthetic, 'send', side_effect=AssertionError('prepare must not send')), \
                patch.object(transport_synthetic, 'upload_media', side_effect=AssertionError('prepare must not upload')), \
                patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('prepare must not fetch URLs')):
            prepared = workflow.prepare(self.root, built['inputs']['production-task']['path'])
            directory, saved, _, events = workflow.load_run(self.root, prepared['run'])
        self.assertEqual(events, [])
        self.assertEqual(saved['task']['criteria'], original['criteria'])
        self.assertEqual(saved['task']['authority'], original['authority'])
        sources = {row['path']: row for row in saved['dependencies'] if row['space'] == 'studio'}
        self.assertNotIn(removed['file'], sources)
        raw = (self.root / retained['file']).read_bytes()
        self.assertEqual(sources[retained['file']]['sha256'], c.digest(raw))
        self.assertEqual(c.object_read(directory, c.digest(raw)), raw)
        self.assertEqual(len(list(directory.glob('package.*.references'))), 1)
        rendered = c.load(directory / 'request-contract.json')
        request_contract.validate_seal(rendered)
        self.assertEqual(len(rendered['media']), 1)
        self.assertEqual(rendered['media'][0]['sha256'], c.digest(raw))
        self.assertEqual(rendered['media'][0]['upload_source'], {'kind': 'url', 'url': retained['url']})
        self.assertEqual(rendered['request']['prompt'], cases.PROMPT)
        self.assertEqual(len(rendered['request']['inputs']['references']), 1)

    def test_image_input_follows_reference_edits_from_task_and_saved_run(self):
        from unittest.mock import patch
        from PIL import Image
        import production_case_fixtures as cases
        import production_workflow as workflow
        import transport_synthetic
        self.enterContext(patch.object(transport_synthetic, 'send',
            side_effect=AssertionError('prepare must not send')))
        self.enterContext(patch.object(transport_synthetic, 'upload_media',
            side_effect=AssertionError('prepare must not upload')))
        self.enterContext(patch('urllib.request.OpenerDirector.open',
            side_effect=AssertionError('prepare must not fetch URLs')))
        Image.new('RGB', (16, 16), 'blue').save(self.root / 'palette.png')
        draft = inputs.draft_inputs(self.root, 'task.json', 'image-draft')
        choices = c.load(self.root / draft['choices_file'])
        self.assertEqual(choices['target'], {'kind': 'catalog', 'model': cases.MODEL_ID, 'service': 'synthetic'})
        zero_reason = copy.deepcopy(choices['authoring']['references']['zero_reference_reason'])
        choices['authoring']['references']['image_input'] = {
            'artifact_type': 'image-input-plan',
            'references': [{'id': 'palette', 'role': 'palette', 'file': 'palette.png',
                'use_for': ['selected color palette'], 'do_not_transfer': ['subject identity', 'pose']}],
            'external_request': None}
        with cases.edit_document(self.root, choices, 'production_spec') as document:
            document['render_intent']['execution_mode'] = 'reference-guided'
        (self.root / draft['choices_file']).write_bytes(c.encoded(choices))
        initial = inputs.build_inputs(self.root, None, draft['choices_file'], 'image-built')
        self.assertTrue(initial['ok'], initial)
        original_task_path = initial['inputs']['production-task']['path']
        original_task = c.load(self.root / original_task_path)
        self.assertEqual(original_task['image_input'], 'image-built/image-input.json')
        original_plan = (self.root / original_task['image_input']).read_bytes()
        self.assertEqual(c.decode(original_plan)['model']['target'],
                         {'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'})
        first_run = workflow.prepare(self.root, original_task_path)
        self.assertTrue(first_run['ok'], first_run)
        for origin in ('task', 'run'):
            with self.subTest(origin=origin):
                draft = inputs.draft_inputs(self.root,
                    original_task_path if origin == 'task' else None, origin + '-draft',
                    from_run=first_run['run'] if origin == 'run' else None)
                choices = c.load(self.root / draft['choices_file'])
                selected = choices['authoring']['references']['image_input']['references'][0]
                selected['use_for'] = ['selected color palette and tonal balance']
                (self.root / draft['choices_file']).write_bytes(c.encoded(choices))
                updated = inputs.build_inputs(self.root, None, draft['choices_file'], origin + '-updated')
                self.assertTrue(updated['ok'], updated)
                task_path = updated['inputs']['production-task']['path']
                task = c.load(self.root / task_path)
                self.assertEqual(task['image_input'], origin + '-updated/image-input.json')
                self.assertEqual(c.load(self.root / task['image_input'])['references'][0]['use_for'], selected['use_for'])
                updated_run = workflow.prepare(self.root, task_path)
                self.assertTrue(updated_run['ok'], updated_run)

                removed = inputs.draft_inputs(self.root, task_path if origin == 'task' else None,
                    origin + '-removed-draft', from_run=updated_run['run'] if origin == 'run' else None)
                choices = c.load(self.root / removed['choices_file'])
                references = choices['authoring']['references']
                references.update(image_input=None, additional_references=[], reference_selection=None,
                    reference_use_plan=None, source_files={}, zero_reference_reason=zero_reason)
                with cases.edit_document(self.root, choices, 'production_spec') as document:
                    document['render_intent']['execution_mode'] = 'text-to-image'
                self.assertEqual(choices['task_changes'], {})
                (self.root / removed['choices_file']).write_bytes(c.encoded(choices))
                cleared = inputs.build_inputs(self.root, None, removed['choices_file'], origin + '-cleared')
                self.assertTrue(cleared['ok'], cleared)
                cleared_task_path = cleared['inputs']['production-task']['path']
                cleared_task = c.load(self.root / cleared_task_path)
                reference_set = c.load(self.root / cleared_task['generation']['references'])
                self.assertEqual(reference_set['selected_references'], [])
                self.assertFalse((self.root / (origin + '-cleared/image-input.json')).exists())
                # The actual compilation boundary must agree with the empty
                # prepared set, without an override of a derived task field.
                cleared_run = workflow.prepare(self.root, cleared_task_path)
                self.assertTrue(cleared_run['ok'], cleared_run)
                self.assertNotIn('image_input', cleared_task)
                directory, saved, _, events = workflow.load_run(self.root, cleared_run['run'])
                self.assertEqual(events, [])
                self.assertEqual(c.load(directory / 'request-contract.json')['media'], [])
                self.assertNotIn(task['image_input'], {row['path'] for row in saved['dependencies']})
                self.assertEqual(saved['task']['criteria'], original_task['criteria'])
                self.assertEqual(saved['task']['authority'], original_task['authority'])
                self.assertEqual((self.root / original_task['image_input']).read_bytes(), original_plan)

    def test_prompt_parameters_and_direction_share_one_edit_source(self):
        result = inputs.draft_inputs(self.root, 'task.json', 'draft')
        choices = c.load(self.root / result['choices_file'])
        original = c.load(self.root / 'task.json')
        prompt = 'A flat graphic portrait of one synthetic robot beside a simple bench.'
        (self.root / choices['authoring']['delivery']['file']).write_text(prompt, encoding='utf-8')
        with cases.edit_document(self.root, choices, 'parameters') as document:
            document.update(width=64, height=64)
        choices['authoring']['task']['direction']['purpose'] = 'Compare an authored local composition.'
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, result['choices_file'], 'built')
        self.assertTrue(built['ok'])
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual((self.root / task['delivery']['path']).read_text(encoding='utf-8'), prompt)
        self.assertEqual(c.load(self.root / task['generation']['parameters'])['width'], 64)
        self.assertEqual(task['criteria'], original['criteria'])
        old_plot = c.load(self.root / original['generation']['plot'])
        new_plot = c.load(self.root / task['generation']['plot'])
        self.assertEqual(new_plot['approved'], old_plot['approved'])
        from prompt_retrieval import retrieval_context
        retrieval = c.load(self.root / task['generation']['retrieval_record'])
        self.assertEqual(retrieval['context'], retrieval_context(prompt, new_plot))
        self.assertEqual(cases.read_document(self.root, choices, 'retrieval_record')['elements'], retrieval['elements'])
        next_draft = inputs.draft_inputs(self.root, built['inputs']['production-task']['path'], 'second-draft')
        self.assertEqual((self.root / next_draft['choices']['authoring']['delivery']['file']).read_text(encoding='utf-8'), prompt)

    def test_upscale_reuses_valid_validation_and_builds_edited_request(self):
        import production_case_fixtures as cases
        import production_binding
        source = cases.upscale_task(self.root)
        original_task = c.load(self.root / source)
        previous = c.load(self.root / original_task['delivery']['path'])['request_validation']
        result = inputs.draft_inputs(self.root, source, 'upscale/draft')
        self.assertEqual(result['unresolved'], [])
        choices = c.load(self.root / result['choices_file'])
        self.assertEqual(choices['target'], {'kind': 'catalog', 'model': cases.UPSCALE_MODEL_ID, 'service': 'synthetic'})
        self.assertEqual(choices['validation'], {'mode': previous['mode'],
            **{key: previous[key]['path'] if previous[key] is not None else None
               for key in ('contract', 'evidence', 'execution_policy')}})
        choices['authoring']['upscale']['scale_factor'] = 4
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        built = inputs.build_inputs(self.root, None, result['choices_file'], 'upscale/built')
        task = c.load(self.root / built['inputs']['production-task']['path'])
        request = c.load(self.root / task['delivery']['path'])
        self.assertEqual(request['scale_factor'], 4)
        self.assertIs(type(request['scale_factor']), int)
        self.assertEqual(request['request_validation'], previous)
        production_binding.validate_upscale_input(self.root, request)
        self.assertEqual([row['operation'] for row in built['next_actions']],
                         ['prepare', 'draft-execution', 'execute'])

    def test_local_source_selection_keeps_existing_criteria_authority_and_image_path(self):
        import production_case_fixtures as cases
        source = cases.upscale_task(self.root)
        original = c.load(self.root / source)
        declaration = c.load(self.root / original['delivery']['path'])
        original_image = declaration['source']['path']
        result = inputs.draft_inputs(self.root, source, 'upscale/selected',
            source_image=self.root / original_image, scale=4.0,
            purpose='Enlarge the already selected image for this delivery.')
        authoring = result['choices']['authoring']
        self.assertEqual(authoring['upscale']['source'], original_image)
        self.assertIs(type(authoring['upscale']['scale_factor']), int)
        self.assertEqual(authoring['task']['criteria'], original['criteria'])
        self.assertEqual(authoring['task']['direction'], original['direction'])
        self.assertEqual(authoring['task']['authority'], original['authority'])
        self.assertEqual(result['selected_image']['sha256'], declaration['source']['sha256'])

    def test_factor_normalization_preserves_fractional_values_and_rejects_non_finite_values(self):
        from production_binding import normalize_upscale_factor
        self.assertIs(type(normalize_upscale_factor(4.0)), int)
        self.assertEqual(normalize_upscale_factor(2.5), 2.5)
        for factor in (True, 0, -1, float('nan'), float('inf')):
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                normalize_upscale_factor(factor)


class DuplicateDependencyTests(unittest.TestCase):
    def setUp(self):
        import production_fixtures
        import production_workflow
        import work_ledger
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        production_fixtures.scratch_home(self.root / 'home')
        entry = work_ledger.begin(self.root, 'Synthetic shared source and authority.', ['prepare'])
        self.task = {'task_id': entry['task_id'], 'route': 'development', 'features': [],
            'sources': [{'id': 'owner-direction', 'path': 'owner-direction.json', 'role': 'design',
                'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic shared source and authority.'}],
            'delivery': {'path': 'delivery.txt', 'translation_notes': 'Synthetic duplicate dependency test.'},
            'criteria': [{'id': 'output', 'text': 'Preserve the declared source.', 'strength': 'hard', 'evidence': 'text'}],
            'world_views': []}
        (self.root / 'delivery.txt').write_bytes(b'Synthetic shared delivery.')
        production_fixtures.task(self.root, self.task)
        (self.root / 'owner-direction.json').write_bytes((self.root / 'fixture-authority.json').read_bytes())
        self.task['authority'] = 'owner-direction.json'
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        self.run = production_workflow.prepare(self.root, 'task.json')['run']

    def test_from_run_uses_studio_content_when_authority_shares_the_source_path(self):
        import production_workflow
        _, prepared, _, _ = production_workflow.load_run(self.root, self.run)
        spaces = [row['space'] for row in prepared['dependencies'] if row['path'] == 'owner-direction.json']
        self.assertEqual(spaces, ['evidence', 'studio'])
        drafted = inputs.draft_inputs(self.root, None, 'draft', from_run=self.run)
        choices = c.load(self.root / drafted['choices_file'])
        self.assertEqual(choices['authoring']['sources']['owner-direction']['content'],
                         c.load(self.root / 'owner-direction.json'))
        saved = inputs._source_run(self.root, self.run)
        self.assertEqual(inputs._saved_delivery(self.root, saved, prepared['task']), b'Synthetic shared delivery.')
        built = inputs.build_inputs(self.root, None, drafted['choices_file'], 'built')
        self.assertTrue(built['ok'], built)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
