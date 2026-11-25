"""Exercise stage selection and fresh continuation through the public input CLI."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as cases
import production_fixtures as fixtures
import production_inputs as inputs
import production_operations as workflow
import production_reading_scope as reading_scope
import production_report_view as views
import route_reading
import studio_workspace as studio
import work_ledger
import production_change_scope as change_scope
import authoring_work
import test_production_adoption as adoption_cases
import test_production_pack_reference as pack_reference_cases


class AmendmentScopeTests(unittest.TestCase):
    """Exercise actual editable owners independently of source-delivery receipts."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-amend-scope-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        task = {'task_id': 'scope', 'production_id': 'scope', 'route': 'character-sheet',
            'features': ['recurring-identity', 'body-plan'], 'artifact': 'image',
            'execution': 'dispatcher', 'sources': [], 'criteria': [],
            'direction': {'purpose': 'Synthetic view', 'basis': []},
            'recording': {'slot': 'front'}}
        self.before = {'authoring_stage': 'depiction',
            'target': {'kind': 'catalog', 'model': 'synthetic:model', 'service': 'synthetic'},
            'authoring': {'task': task, 'delivery': {'content': 'Synthetic figure.', 'translation_notes': None},
                'documents': {'parameters': {'steps': 20}, 'production_spec': {
                    'subjects': [{'id': 'subject', 'domain': 'human', 'identity': {'name': 'Synthetic'},
                                  'pose_and_body_geometry': 'Front view.'}],
                    'scene': 'Empty studio.'}},
                'generation': {'count': 1, 'seed': 7, 'continuity': {'subject': 'recurring'},
                    'render_intent': {'execution_mode': 'generation'}},
                'references': None, 'upscale': None, 'source_files': {}},
            'external': None, 'visual': None, 'validation': None, 'reading': {'reading_key': None},
            'task_changes': {}}

    def scope(self, *, change, retain=(), edit=None):
        current = copy.deepcopy(self.before)
        if edit:
            edit(current)
        basis = authoring_work.begin_work(operation='amend', request='Synthetic amendment.',
            baseline=self.before)['basis']
        basis['change_scope'] = {'retain': list(retain), 'change': list(change)}
        scope = reading_scope.selection(self.root, current, current['authoring']['task'], basis=basis)
        return scope, current, basis

    def test_view_change_preserves_definition_and_stage_does_not_expand_it(self):
        def edit(current):
            current['authoring']['documents']['production_spec']['subjects'][0]['pose_and_body_geometry'] = 'Side view.'
        scope, current, basis = self.scope(change=['depiction.view'], retain=['identity', 'target'], edit=edit)
        self.assertEqual(scope['profiles'], ['amend-depiction'])
        self.assertEqual(scope['observed_changes'], ['depiction'])
        self.assertFalse(scope['change_conflicts'])
        current['authoring_stage'] = 'definition'
        selected = reading_scope.selection(self.root, current, current['authoring']['task'], basis=basis)
        self.assertEqual(selected['profiles'], scope['profiles'])

    def test_actual_definition_edit_enlarges_scope_and_reports_retention_conflict(self):
        def edit(current):
            current['authoring']['documents']['production_spec']['subjects'][0]['identity']['name'] = 'Changed'
        scope, current, _ = self.scope(change=['depiction.view'], retain=['identity'], edit=edit)
        self.assertEqual(scope['profiles'], ['amend-definition', 'amend-depiction'])
        self.assertEqual(scope['change_conflicts'], ['identity'])
        report = reading_scope.projection(current, current['authoring']['task'], [], scope=scope)
        self.assertFalse(report['structural_ready'])
        self.assertIn('work-basis.json', report['unresolved'][0]['required_action'])

    def test_parameter_file_bytes_select_only_control_knowledge(self):
        (self.root / 'parameters.json').write_bytes(c.encoded({'steps': 30}))
        def edit(current):
            current['authoring']['documents']['parameters'] = {'file': 'parameters.json'}
        scope, current, _ = self.scope(change=['controls.parameters'], retain=['identity', 'finish'], edit=edit)
        self.assertEqual(scope['profiles'], ['amend-controls'])
        self.assertEqual(scope['observed_changes'], ['controls.parameters'])
        self.assertFalse(reading_scope.matches({'changes_any': ['controls', 'controls.render-intent']}, scope))
        self.assertEqual(reading_scope.initial_stage(scope['change_scope']), 'rendition')
        current['authoring_stage'] = 'rendition'
        report = reading_scope.projection(current, current['authoring']['task'], [], scope=scope)
        self.assertEqual(report['remaining_stages'], ['prepare'])

    def test_reference_addition_reads_actual_carrier_and_only_reference_knowledge(self):
        (self.root / 'reference.bin').write_bytes(b'synthetic-carrier')
        def edit(current):
            current['authoring']['references'] = {'additional_references': [
                {'id': 'side', 'role': 'identity', 'source': {'kind': 'supplied-file',
                 'reference_id': 'side', 'resolved_path': 'reference.bin'}}], 'image_input': None}
        scope, _, _ = self.scope(change=['references'], retain=['identity'], edit=edit)
        self.assertEqual(scope['profiles'], ['amend-references'])
        self.assertEqual(scope['observed_changes'], ['references'])
        self.assertEqual(reading_scope.next_stage(scope), 'prepare')

    def test_target_changes_cannot_hide_behind_parameter_declaration(self):
        def edit(current):
            current['target']['model'] = 'synthetic:other'
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['identity'], edit=edit)
        self.assertEqual(scope['profiles'], ['amend-controls', 'retarget'])

    def test_route_and_features_select_contracts_without_claiming_content_changes(self):
        import execution_routes
        previous = reading_scope._selected_target_identity(self.root, self.before['target'],
            self.before['authoring']['task'], {})
        def edit(current):
            current['authoring']['task'].update(route='generation', features=['recurring-identity', 'geometry'])
        _, current, basis = self.scope(change=['depiction', 'references'],
            retain=['identity', 'target', 'finish', 'controls'], edit=edit)
        scope = reading_scope.selection(self.root, current, current['authoring']['task'], basis=basis,
            context={'derived_from': {'source_run': {'target_identity': previous}}})
        self.assertEqual(scope['observed_changes'], ['route'])
        self.assertEqual(scope['profiles'], ['amend-depiction', 'amend-references'])
        self.assertNotIn('target-change', scope['conditions'])
        self.assertFalse(scope['change_conflicts'])
        self.assertFalse(reading_scope.matches({'changes_any': ['controls.render-intent']}, scope))
        resolved = execution_routes.resolve('generation', current['authoring']['task']['features'],
            execution='dispatcher', authoring_scope=scope)
        for path in ('references/prompt-composition-geometry', 'references/camera-framing-contract'):
            source = next(row for row in resolved['reads'] if row['document_id'] == path)
            self.assertEqual(source['sections'], [section.metadata() for section in execution_routes.DocumentReader(lambda name: (execution_routes.ROOT / name).read_bytes()).acquire(path).sections])
            self.assertIn('feature:geometry', resolved['read_owners'][path])
        self.assertIn('references/runtime/image-generation', resolved['read_owners'])

    def test_execution_and_artifact_changes_belong_to_the_target_owner(self):
        for key, value in (('execution', 'external'), ('artifact', 'text')):
            with self.subTest(key=key):
                scope, _, _ = self.scope(change=['references'], retain=['target'],
                    edit=lambda current: current['authoring']['task'].update({key: value}))
                self.assertEqual(scope['observed_changes'], ['target'])
                self.assertEqual(scope['profiles'], ['amend-references', 'retarget'])
                self.assertEqual(scope['change_conflicts'], ['target'])

    def test_actual_external_target_fields_select_retarget_knowledge(self):
        self.before['authoring']['task']['execution'] = 'external'
        self.before['target'] = {'kind': 'external', 'model': {'target': {
            'model_identifier': 'synthetic:model', 'service': 'synthetic', 'operation': 'image'}}}
        previous = reading_scope._selected_target_identity(self.root, self.before['target'],
            self.before['authoring']['task'], {})
        for key, value in (('model_identifier', 'synthetic:other'), ('service', 'other'), ('operation', 'edit')):
            with self.subTest(key=key):
                _, current, basis = self.scope(change=['references'], retain=['target'],
                    edit=lambda current: current['target']['model']['target'].update({key: value}))
                scope = reading_scope.selection(self.root, current, current['authoring']['task'], basis=basis,
                    context={'derived_from': {'source_run': {'target_identity': previous}}})
                self.assertIn('target-change', scope['conditions'])
                self.assertEqual(scope['observed_changes'], ['target'])
                self.assertEqual(scope['profiles'], ['amend-references', 'retarget'])
                self.assertEqual(scope['change_conflicts'], ['target'])

    def test_recording_only_starts_at_binding_and_keeps_existing_content(self):
        scope, _, _ = self.scope(change=['recording.slot'], retain=['identity', 'target'],
            edit=lambda current: current['authoring']['task']['recording'].update(slot='side'))
        self.assertEqual(scope['profiles'], ['amend-recording'])
        self.assertEqual(reading_scope.initial_stage(scope['change_scope']), 'prepare')

    def test_unreadable_actual_document_cannot_prove_retention(self):
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['identity'],
            edit=lambda current: current['authoring']['documents'].update(parameters={'file': 'absent.json'}))
        self.assertEqual(scope['profiles'], sorted(change_scope.PROFILES))
        self.assertIn('unknown', scope['observed_changes'])
        self.assertEqual(scope['comparison_notices'][0]['cause'], 'selected-owner-unreadable')

    def test_authored_context_field_is_not_a_generated_witness(self):
        self.before['authoring']['documents']['creative_intent'] = {'context': {'purpose': 'Initial'}}
        scope, _, _ = self.scope(change=['controls.parameters'],
            edit=lambda current: current['authoring']['documents']['creative_intent']['context'].update(purpose='Changed'))
        self.assertIn('amend-depiction', scope['profiles'])
        self.assertIn('depiction', scope['observed_changes'])

    def test_native_parameter_and_negative_fields_follow_explicit_request_paths(self):
        self.before['external'] = {'image_input': {'references': [],
            'external_request': {'prompt_field': ['sentence'], 'negative_field': ['avoid'],
                                 'model_field': ['engine']}},
            'request': {'sentence': None, 'engine': None, 'avoid': 'blur', 'native': {'quality': 2}},
            'source_files': {}, 'media_slots': []}
        scope, _, _ = self.scope(change=['controls.parameters'],
            edit=lambda current: current['external']['request']['native'].update(quality=3))
        self.assertEqual(scope['profiles'], ['amend-controls'])
        self.assertEqual(scope['observed_changes'], ['controls.parameters'])
        scope, _, _ = self.scope(change=['controls.parameters'],
            edit=lambda current: current['external']['request'].update(avoid='glare'))
        self.assertEqual(scope['profiles'], ['amend-controls', 'amend-rendition'])

    def test_external_upload_and_prompt_mapping_changes_keep_their_owners(self):
        from semantic_edit_plan_smoke_test import setup_plan
        import production_external_inputs
        plan = setup_plan(self.root)
        self.before['external'] = production_external_inputs.draft(plan, c.load(self.root / 'request.json'), root=self.root)
        def uploaded(current):
            transport = current['external']['image_input']['references'][0]['transport']
            transport['value'] = 'synthetic-reupload'
            (self.root / 'reupload.json').write_bytes(c.encoded({'image_id': transport['value']}))
            transport['evidence'] = {'path': 'reupload.json', 'locator': 'whole synthetic response'}
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['references'], edit=uploaded)
        self.assertEqual(scope['profiles'], ['amend-controls', 'amend-references'])
        self.assertEqual(scope['change_conflicts'], ['references'])
        scope, _, _ = self.scope(change=['controls.parameters'], edit=lambda current:
            current['external']['image_input']['external_request'].update(prompt_field=['other_text']))
        self.assertEqual(scope['profiles'], ['amend-controls', 'amend-rendition'])
        self.assertIn('rendition', scope['observed_changes'])

    def test_reference_decisions_outside_attachment_rows_are_compared(self):
        self.before['authoring']['references'] = {'additional_references': [], 'image_input': None,
            'reference_use_plan': {'items': [], 'surface_lighting': {'decision': 'Original'},
                                   'unavailable_record_uses': []}}
        scope, _, _ = self.scope(change=['controls.parameters'], edit=lambda current:
            current['authoring']['references']['reference_use_plan']['surface_lighting'].update(decision='Revised'))
        self.assertEqual(scope['profiles'], ['amend-controls', 'amend-references'])

    def test_upload_url_and_authored_negative_bytes_have_actual_change_owners(self):
        raw = b'synthetic-upload'
        (self.root / 'carrier.bin').write_bytes(raw)
        self.before['authoring']['task']['upload_sources'] = [{'file': 'carrier.bin', 'url': 'https://invalid.example/original'}]
        self.before['authoring']['source_files']['carrier.bin'] = c.digest(raw)
        scope, _, _ = self.scope(change=['controls.parameters'], edit=lambda current:
            current['authoring']['task']['upload_sources'][0].update(url='https://invalid.example/revised'))
        self.assertIn('references', scope['observed_changes'])
        raw = b'synthetic original negative'
        (self.root / 'negative.txt').write_bytes(raw)
        self.before['authoring']['task']['authored'] = {'prompt_field': ['text'], 'negative': {'path': 'negative.txt'}}
        self.before['authoring']['source_files']['negative.txt'] = c.digest(raw)
        (self.root / 'negative.txt').write_bytes(b'synthetic revised negative')
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['rendition'])
        self.assertIn('rendition', scope['observed_changes'])
        self.assertEqual(scope['change_conflicts'], ['rendition'])

    def test_identity_source_relocation_preserves_scope_but_bytes_and_authority_do_not(self):
        raw = c.encoded({'identity': 'Synthetic fixed definition'})
        (self.root / 'original.json').write_bytes(raw)
        (self.root / 'relocated.json').write_bytes(raw)
        source = {'id': 'canonical', 'path': 'original.json', 'role': 'definition', 'disposition': 'applied',
            'locator': 'whole source', 'reason': 'Synthetic definition authority.',
            'identity': {'subject_ids': ['subject'], 'selectors': [''], 'authority': {
                'reference': 'canonical', 'use_for': ['identity'], 'controls': ['identity'],
                'intended_influence': ['identity'], 'do_not_transfer': [],
                'subject_uses': [{'subject_id': 'subject', 'use': 'identity', 'priority': 1}]}}}
        self.before['authoring']['task']['sources'] = [source]
        self.before['authoring']['source_files']['original.json'] = c.digest(raw)
        def relocate(current):
            current['authoring']['task']['sources'][0]['path'] = 'relocated.json'
            current['authoring']['source_files']['relocated.json'] = c.digest(raw)
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['identity', 'source-authority'], edit=relocate)
        self.assertEqual(scope['profiles'], ['amend-controls'])
        self.assertEqual(scope['observed_changes'], [])
        (self.root / 'relocated.json').write_bytes(c.encoded({'identity': 'Changed definition'}))
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['identity'], edit=relocate)
        self.assertIn('amend-definition', scope['profiles'])
        self.assertIn('identity', scope['change_conflicts'])
        def authority(current):
            current['authoring']['task']['sources'][0]['identity']['authority']['controls'] = ['identity', 'pose']
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['source-authority'], edit=authority)
        self.assertIn('source-authority', scope['observed_changes'])
        self.assertIn('source-authority', scope['change_conflicts'])

    def test_basis_reference_replacement_uses_the_saved_baseline_witness(self):
        original = b'original synthetic reference'
        replacement = b'replaced synthetic reference'
        (self.root / 'original.txt').write_bytes(original)
        (self.root / 'replacement.txt').write_bytes(replacement)
        row = {'id': 'reference', 'path': 'original.txt', 'role': 'reference',
            'disposition': 'applied', 'locator': 'whole source',
            'reason': 'Synthetic reference.', 'applications': []}
        self.before['authoring']['task']['sources'] = [row]
        self.before['authoring']['source_files']['original.txt'] = c.digest(original)
        basis = authoring_work.begin_work(operation='amend', request='Synthetic amendment.',
            baseline=self.before)['basis']
        basis['sources'] = {'reference': authoring_work.acquire_source(original, origin={'source': row})}
        basis['change_scope'] = {'retain': ['references'], 'change': ['controls.parameters']}
        current = copy.deepcopy(self.before)
        current['authoring']['task']['sources'][0]['path'] = 'replacement.txt'
        current['authoring']['source_files'] = {'replacement.txt': c.digest(replacement)}
        basis['sources']['reference'] = authoring_work.acquire_source(replacement,
            origin={'source': current['authoring']['task']['sources'][0]})
        scope = reading_scope.selection(self.root, current, current['authoring']['task'], basis=basis)
        self.assertEqual(scope['observed_changes'], ['references'])
        self.assertEqual(scope['profiles'], ['amend-controls', 'amend-references'])
        self.assertEqual(scope['change_conflicts'], ['references'])

    def test_current_reference_bytes_override_an_unchanged_saved_measurement(self):
        raw = b'original-synthetic-carrier'
        (self.root / 'carrier.bin').write_bytes(raw)
        self.before['authoring']['references'] = {'additional_references': [
            {'id': 'side', 'role': 'identity', 'source': {'kind': 'supplied-file',
                'reference_id': 'side', 'resolved_path': 'carrier.bin'}}], 'image_input': None,
            'source_files': {'carrier.bin': {'sha256': c.digest(raw), 'media_type': 'image/png'}}}
        (self.root / 'carrier.bin').write_bytes(b'replaced-synthetic-carrier')
        scope, _, _ = self.scope(change=['controls.parameters'], retain=['references'])
        self.assertIn('amend-references', scope['profiles'])
        self.assertEqual(scope['change_conflicts'], ['references'])

    def test_unclassified_structured_field_expands_instead_of_being_ignored(self):
        scope, _, _ = self.scope(change=['controls.parameters'],
            edit=lambda current: current['authoring']['generation'].update(future_control={'value': 1}))
        self.assertEqual(scope['profiles'], sorted(change_scope.PROFILES))
        self.assertEqual(scope['comparison_notices'][0]['cause'], 'unclassified-structured-owner')

    def test_unscoped_existing_work_keeps_its_complete_authoring_contract(self):
        basis = authoring_work.begin_work(operation='amend', request='Synthetic amendment.',
            baseline=self.before)['basis']
        scope = reading_scope.selection(self.root, self.before, self.before['authoring']['task'], basis=basis)
        self.assertNotIn('change_scope', scope)

    def test_conflicting_or_unknown_declared_owners_are_not_silently_ignored(self):
        for value in ({'retain': ['identity'], 'change': ['definition']},
                      {'retain': [], 'change': ['guess-from-prompt']},
                      {'retain': [], 'change': []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reading_scope.validate_change_scope(value)

    def test_final_task_derives_the_same_actual_parameter_scope(self):
        scope, current, basis = self.scope(change=['controls.parameters'], retain=['identity', 'target'],
            edit=lambda value: value['authoring']['documents']['parameters'].update(steps=25))
        task = copy.deepcopy(current['authoring']['task'])
        generation = copy.deepcopy(current['authoring']['generation'])
        for name, value in current['authoring']['documents'].items():
            path = name + '.json'
            (self.root / path).write_bytes(c.encoded(value))
            generation[name] = path
        generation.update(model=current['target']['model'], service=current['target']['service'])
        (self.root / 'delivery.txt').write_text(current['authoring']['delivery']['content'], encoding='utf-8')
        (self.root / 'work-basis.json').write_bytes(c.encoded(basis))
        task.update(generation=generation, delivery={'path': 'delivery.txt', 'translation_notes': None},
                    work_basis='work-basis.json')
        final = reading_scope.from_task(self.root, task)
        self.assertEqual(final['profiles'], scope['profiles'])
        self.assertEqual(final['observed_changes'], scope['observed_changes'])
        specification = c.load(self.root / 'production_spec.json')
        specification['subjects'][0]['identity']['name'] = 'Changed outside the choices'
        (self.root / 'production_spec.json').write_bytes(c.encoded(specification))
        from production_diagnostics import ProductionError
        with self.assertRaises(ProductionError) as raised:
            reading_scope.from_task(self.root, task)
        self.assertIn('identity', str(raised.exception))


class RetainedAmendmentCompilationTests(unittest.TestCase):
    setUpClass = classmethod(adoption_cases.AdoptionTests.setUpClass.__func__)
    setUp = adoption_cases.AdoptionTests.setUp

    def test_route_change_requires_current_contract_and_preserves_final_target_validation(self):
        declaration = {'retain': ['identity', 'target', 'finish', 'controls'],
                       'change': ['depiction', 'references']}
        draft = inputs.draft_inputs(self.root, None, 'work/route-amend', from_run=self.run,
            operation='amend', change_scope=declaration)
        path = draft['choices_file']
        choices = c.load(self.root / path)
        choices['authoring']['task']['route'] = 'batch'
        choices['authoring_stage'] = 'prepare'
        cases.write(self.root / path, choices)
        before = inputs.compile_choices(self.root, path, persist=False)
        self.assertFalse(before.report['publishable'])
        view = inputs.authoring_view(self.root, path)
        scope, task = view['authoring_scope'], view['task']
        self.assertEqual(scope['observed_changes'], ['route'])
        self.assertEqual(scope['profiles'], ['amend-depiction', 'amend-references'])
        self.assertNotIn('target-change', scope['conditions'])
        self.assertTrue(any(row['code'] == 'TARGET_GUIDANCE_REQUIRED' for row in view['unresolved']))
        target = choices['target']
        issued = route_reading.issue(task['route'], task['features'], execution=task['execution'],
            studio=self.root, stream=io.StringIO(), operation='prepare', authoring_scope=scope,
            model=target['model'], service=target.get('service'))
        choices['reading']['reading_key'] = issued['reading_key']
        cases.write(self.root / path, choices)
        final_scopes = []
        derive = reading_scope.from_task
        def observe(root, task, *, read_source=None):
            result = derive(root, task, read_source=read_source)
            final_scopes.append(result)
            return result
        with patch.object(reading_scope, 'from_task', side_effect=observe):
            compiled = inputs.compile_choices(self.root, path, persist=False)
        self.assertTrue(compiled.report['publishable'], compiled.report)
        self.assertTrue(final_scopes)
        self.assertEqual(final_scopes[-1]['profiles'], ['amend-depiction', 'amend-references'])
        self.assertEqual(final_scopes[-1]['observed_changes'], ['route'])
        choices['target']['service'] = 'unselected-service'
        cases.write(self.root / path, choices)
        rejected = inputs.compile_choices(self.root, path, persist=False)
        self.assertFalse(rejected.report['publishable'])

    def test_actual_parameter_edit_prepares_with_the_same_narrow_final_scope(self):
        declaration = {'retain': ['identity', 'target', 'rendition', 'depiction', 'references', 'finish'],
                       'change': ['controls.parameters']}
        draft = inputs.draft_inputs(self.root, None, 'work/controls-amend', from_run=self.run,
            operation='amend', change_scope=declaration)
        path = draft['choices_file']
        choices = c.load(self.root / path)
        parameters = cases.read_document(self.root, choices, 'parameters')
        previous = parameters['steps']
        parameters['steps'] += 1
        cases.write_document(self.root, choices, 'parameters', parameters)
        choices.update(authoring_stage='prepare', reading={'reading_key': None})
        cases.write(self.root / path, choices)
        view = inputs.authoring_view(self.root, path)
        scope, task = view['authoring_scope'], view['task']
        self.assertEqual(scope['profiles'], ['amend-controls'])
        self.assertEqual(scope['observed_changes'], ['controls.parameters'])
        self.assertFalse(scope['comparison_notices'])
        target = choices['target']
        issued = route_reading.issue(task['route'], task['features'], execution=task['execution'],
            studio=self.root, stream=io.StringIO(), operation='prepare', authoring_scope=scope,
            model=target['model'], service=target.get('service'))
        choices['reading']['reading_key'] = issued['reading_key']
        cases.write(self.root / path, choices)
        final_scopes = []
        derive = reading_scope.from_task
        def observe(root, task, *, read_source=None):
            result = derive(root, task, read_source=read_source)
            final_scopes.append(result)
            return result
        with patch.object(reading_scope, 'from_task', side_effect=observe):
            compiled = inputs.compile_choices(self.root, path, persist=False)
        self.assertTrue(compiled.report['publishable'], compiled.report)
        self.assertTrue(final_scopes)
        self.assertEqual(final_scopes[-1]['profiles'], ['amend-controls'])
        self.assertEqual(final_scopes[-1]['observed_changes'], ['controls.parameters'])
        self.assertFalse(final_scopes[-1]['change_conflicts'])
        self.assertFalse(final_scopes[-1]['comparison_notices'])
        self.assertEqual(cases.read_document(self.root, choices, 'parameters')['steps'], previous + 1)


class PackReferenceAmendmentCompilationTests(unittest.TestCase):
    def setUp(self):
        pack_reference_cases.PackReferenceRunTests.setUp(self)
        self.run = self.prepared_run

    test_pack_reference_parameter_amendment_keeps_its_actual_identity_owner = (
        RetainedAmendmentCompilationTests.test_actual_parameter_edit_prepares_with_the_same_narrow_final_scope)


class StageCliTests(unittest.TestCase):
    def setUp(self):
        from catalog_retrieval import runtime
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-stage-inputs-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.enterContext(fixtures.scratch_home(self.base / 'home'))
        self.enterContext(runtime.using_pack_runtime(None))
        self.root = studio.init(self.base / 'studio', 'stage-inputs', 'Synthetic stage continuation')
        self.work = work_ledger.begin(self.root, 'Compose a synthetic local description.', ['Compose'])
        self.request = fixtures.current_request(self.root, 'Compose a synthetic scene of an empty workshop.')

    def command(self, name, *arguments):
        argv = [sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'), name,
                '--root', str(self.root), *arguments, '--view', 'full']
        return self.follow(argv)

    def follow(self, argv):
        completed = subprocess.run(argv, cwd=self.root, env=dict(os.environ), capture_output=True,
                                   text=True, encoding='utf-8', timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def check_choices(self, path):
        result = subprocess.run([sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'),
            'check', '--root', str(self.root), '--choices', path], cwd=self.root,
            env=dict(os.environ), capture_output=True, text=True, encoding='utf-8', timeout=60)
        return result.returncode, json.loads(result.stdout)

    def draft(self, directory='work/draft', *, execution='authored'):
        return self.command('draft-inputs', '--route', 'development' if execution == 'authored' else 'generation',
            '--artifact', 'text' if execution == 'authored' else 'image', '--execution', execution,
            '--operation', 'compose', '--request-file', self.request, '--focus', 'supporting-setting',
            '--out-dir', directory)

    def choose(self, path, stage):
        return self.command('stage-inputs', '--choices', path, '--stage', stage)

    def read(self, path):
        result = self.follow([sys.executable, str(inputs.ROOT / 'scripts/execution_routes.py'),
            'read', '--root', str(self.root), '--choices', path, '--page-bytes', '1000000'])
        self.assertEqual(result['body'], [])
        self.assertIsNone(result['reading'])
        self.assertEqual(result['progress']['reused_bytes'], 0)
        while result['reading'] is None:
            action = result['actions'].get('continue') or result['actions']['all']
            result = self.follow(action['argv'])
        return result

    def store_key(self, path, key):
        choices = c.load(self.root / path)
        choices['reading']['reading_key'] = key
        (self.root / path).write_bytes(c.encoded(choices))

    def sources(self, path):
        folder = self.root / Path(path).parent
        return {file.relative_to(folder).as_posix(): file.read_bytes()
                for file in folder.rglob('*') if file.is_file() and file != self.root / path}

    def test_new_text_and_image_drafts_start_with_definition(self):
        for execution in ('authored', 'external'):
            with self.subTest(execution=execution):
                drafted = self.draft('work/' + execution, execution=execution)
                choices = c.load(self.root / drafted['choices_file'])
                self.assertEqual(choices['authoring_stage'], 'definition')
                self.assertEqual(drafted['authoring_stage']['stage'], 'definition')
                self.assertIsNone(choices['reading']['reading_key'])
                self.assertFalse(drafted['external_effect'])
                action = next(row for row in drafted['next_actions'] if row.get('operation') == 'read')
                page = self.follow(action['argv'])
                self.assertEqual(page['mode'], 'all')
                self.assertTrue(page['body'])
                self.assertLessEqual(sum(len(row['text'].encode('utf-8')) for row in page['body']),
                                     route_reading.DEFAULT_PAGE_BYTES)
                self.assertEqual(page['metadata']['authoring_scope']['stage'], 'definition')

    def test_inspection_finishes_the_required_scope_after_an_explicit_section(self):
        drafted = self.draft()
        path = drafted['choices_file']
        original = self.sources(path)
        indexed = self.follow([sys.executable, str(inputs.ROOT / 'scripts/execution_routes.py'),
            'read', '--root', str(self.root), '--choices', path, '--page-bytes', '1000000'])
        self.assertEqual(indexed['mode'], 'index')
        section = self.follow([*indexed['section_selection']['argv'],
                               '--section', indexed['index'][0]['selector']])
        self.assertEqual(section['mode'], 'section')
        self.assertIsNone(section['actions']['continue'])
        self.assertGreater(section['progress']['remaining_bytes'], 0)
        inspected = self.command('inspect-inputs', '--choices', path)
        retained = next(row for row in inspected['readings'] if row['snapshot'] == indexed['snapshot'])
        completed = self.follow(retained['next_actions'][0]['argv'])
        self.assertEqual(completed['mode'], 'all')
        self.assertIsNotNone(completed['reading'])
        self.assertEqual(completed['progress']['remaining_bytes'], 0)
        delivered = sum(len(row['text'].encode('utf-8'))
                        for result in (section, completed) for row in result['body'])
        self.assertEqual(delivered, indexed['progress']['required_bytes'])
        record = c.load(self.root / completed['reading']['record'])
        route_reading.validate_record_content(record)
        self.assertEqual(self.sources(path), original)

    def test_stage_transitions_keep_sources_and_only_clear_a_changed_stage_key(self):
        drafted = self.draft()
        path = drafted['choices_file']
        reading = self.read(path)
        key = reading['reading']['key']
        original_sources = self.sources(path)
        original = c.load(self.root / path)
        for stage in ('definition', 'depiction', 'rendition', 'prepare'):
            with self.subTest(stage=stage):
                self.store_key(path, key)
                previous = c.load(self.root / path)
                report = self.choose(path, stage)
                changed = c.load(self.root / path)
                expected = copy.deepcopy(previous)
                if previous['authoring_stage'] != stage:
                    expected.update(authoring_stage=stage, reading={'reading_key': None})
                self.assertEqual(changed, expected)
                self.assertEqual(report['authoring_stage']['stage'], stage)
                self.assertEqual(self.sources(path), original_sources)
                self.assertEqual(changed['authoring'], original['authoring'])
                self.store_key(path, key)
                before = (self.root / path).read_bytes()
                self.choose(path, stage)
                self.assertEqual((self.root / path).read_bytes(), before)

    def test_fresh_inspection_reacquires_the_current_stage_without_prior_knowledge(self):
        path = self.draft()['choices_file']
        first = self.read(path)
        self.store_key(path, first['reading']['key'])
        self.choose(path, 'depiction')
        before = (self.root / path).read_bytes(), self.sources(path)
        report = self.command('inspect-inputs', '--choices', path)
        self.assertEqual(report['authoring_stage']['stage'], 'depiction')
        self.assertEqual(report['context']['input']['authoring_stage']['stage'], 'depiction')
        action = report['fresh_context_action']
        self.assertIn('--choices', action['argv'])
        self.assertNotIn('--known-reading', action['argv'])
        self.assertNotIn('--restart', action['argv'])
        fresh = self.follow(action['argv'])
        self.assertEqual(fresh['metadata']['authoring_scope']['stage'], 'depiction')
        self.assertEqual(fresh['progress']['reused_bytes'], 0)
        self.assertGreater(fresh['remaining_bytes'], 0)
        self.assertEqual((self.root / path).read_bytes(), before[0])
        self.assertEqual(self.sources(path), before[1])

    def test_saved_scope_without_choices_restarts_with_bounded_complete_delivery(self):
        path = self.draft()['choices_file']
        scope, task = reading_scope.from_choices(self.root, path)
        self.root = studio.init(self.base / 'scope-only-studio', 'saved-scope', 'Synthetic saved scope')
        work_ledger.begin(self.root, 'Resume the saved reading scope.', ['Read'])
        first = route_reading.read_page(route=task['route'], features=task['features'],
            operation=reading_scope.operation(scope['stage'], task['execution']),
            execution=task['execution'], authoring_scope=scope, studio=self.root,
            ledger=self.root / 'work/reads.jsonl', stream=io.StringIO(), publish_record=True)
        inspected = self.command('inspect-inputs')
        retained = next(row for row in inspected['readings'] if row['snapshot'] == first['snapshot'])
        self.assertIsNone(retained['choices'])
        action = retained['fresh_context_action']
        self.assertIn('--restart', action['argv'])
        self.assertIn('--all', action['argv'])
        self.assertNotIn('--known-reading', action['argv'])
        fresh = self.follow(action['argv'])
        self.assertNotEqual(fresh['snapshot'], first['snapshot'])
        self.assertEqual(fresh['mode'], 'all')
        self.assertEqual(fresh['metadata']['authoring_scope'], scope)
        delivered = 0
        while True:
            self.assertEqual(fresh['progress']['reused_bytes'], 0)
            size = sum(len(row['text'].encode('utf-8')) for row in fresh['body'])
            self.assertGreater(size, 0)
            self.assertLessEqual(size, route_reading.DEFAULT_PAGE_BYTES)
            delivered += size
            if fresh['reading'] is not None:
                break
            self.assertIsNotNone(fresh['actions']['continue'])
            fresh = self.follow(fresh['actions']['continue']['argv'])
        self.assertEqual(delivered, fresh['progress']['required_bytes'])
        self.assertEqual(fresh['progress']['remaining_bytes'], 0)
        route_reading.validate_record_content(c.load(self.root / fresh['reading']['record']))

    def test_early_check_returns_incomplete_content_to_its_current_stage(self):
        path = self.draft()['choices_file']
        reading = self.read(path)
        self.store_key(path, reading['reading']['key'])
        original = (self.root / path).read_bytes(), self.sources(path)
        status, checked = self.check_choices(path)
        self.assertNotEqual(status, 0)
        self.assertFalse(checked['publishable'])
        self.assertFalse(checked['formal_run_created'])
        self.assertTrue(any(row.get('field') == 'authoring.delivery.content'
                            for row in checked['diagnostics']))
        self.assertTrue(any(row.get('code') == 'TARGET_GUIDANCE_REQUIRED'
                            for row in checked['diagnostics']))
        self.assertEqual(checked['next_action'].get('command'), 'inspect-inputs')
        resumed = self.follow(checked['next_action']['argv'])
        self.assertEqual(resumed['authoring_stage']['stage'], 'definition')
        self.assertFalse(resumed['authoring_stage']['final_inputs_ready'])
        self.assertEqual((self.root / path).read_bytes(), original[0])
        self.assertEqual(self.sources(path), original[1])

    def test_check_still_advances_complete_content_to_final_scope(self):
        self.direct_task()
        drafted = self.command('draft-inputs', '--task', 'task.json', '--operation', 'compose',
            '--request-file', self.request, '--focus', 'supporting-setting', '--out-dir', 'work/ready')
        path = drafted['choices_file']
        reading = self.read(path)
        self.store_key(path, reading['reading']['key'])
        status, checked = self.check_choices(path)
        self.assertNotEqual(status, 0)
        self.assertFalse(checked['publishable'])
        self.assertFalse(checked['formal_run_created'])
        self.assertEqual(checked['next_action']['stage'], 'prepare')
        resumed = self.follow(checked['next_action']['argv'])
        self.assertEqual(resumed['authoring_stage']['stage'], 'prepare')
        final = self.read(path)
        self.store_key(path, final['reading']['key'])
        status, checked = self.check_choices(path)
        self.assertEqual(status, 0, checked)
        self.assertTrue(checked['publishable'])

    def test_new_action_slice_requires_its_undelivered_contract(self):
        path = self.draft()['choices_file']
        self.choose(path, 'depiction')
        first = self.read(path)
        self.store_key(path, first['reading']['key'])
        choices = c.load(self.root / path)
        choices['authoring']['task']['direction']['action_slice'] = {
            'phase': 'A fixture shutter is midway through closing.',
            'before': 'The fixture shutter was open.', 'after': 'The fixture shutter is closed.',
            'relations': [], 'not_verified': ['No image observation is claimed.']}
        (self.root / path).write_bytes(c.encoded(choices))
        report = self.command('inspect-inputs', '--choices', path)
        self.assertIn('action-slice', report['authoring_scope']['conditions'])
        diagnostics = report['authoring_stage']['unresolved']
        missing = [row for row in diagnostics if row.get('code') == 'TARGET_GUIDANCE_REQUIRED']
        self.assertTrue(missing, diagnostics)
        action = missing[0]['next_action']
        self.assertIn(path, action['argv'])
        fresh = self.follow(action['argv'])
        self.assertIn('action-slice', fresh['metadata']['authoring_scope']['conditions'])
        current = self.read(path)
        self.store_key(path, current['reading']['key'])
        restored = self.command('inspect-inputs', '--choices', path)
        self.assertFalse(any(row.get('code') == 'TARGET_GUIDANCE_REQUIRED'
                             for row in restored['authoring_stage']['unresolved']))

    def test_summary_keeps_every_current_answer_and_locates_later_stage_omissions(self):
        current = [{'field': 'definition.' + str(number), 'code': 'CURRENT_ANSWER',
                    'message': 'Answer this actual definition field.'} for number in range(12)]
        later = [{'field': 'prepare.' + str(number), 'code': 'LATER_INPUT',
                  'message': 'Resolve this final input when preparing.'} for number in range(35)]
        stage = {'stage': 'definition', 'purpose': 'Establish the fixture definition.',
            'structural_ready': False, 'final_inputs_ready': False, 'unresolved': current, 'pending': later,
            'meaning': 'No artistic completion is inferred.'}
        row = {'state': 'choices', 'kind': 'draft-inputs', 'directory': 'work/draft',
            'choices': 'work/draft/choices.json', 'current': True, 'unresolved': current + later,
            'authoring_stage': stage, 'next_actions': []}
        report = {'state': 'authoring-state', 'task_id': self.work['task_id'], 'inputs': [row],
            'authoring_stage': stage, 'context': {'work': {}, 'input': row}, 'next_actions': []}
        result = views.authoring_state(self.root, report)
        self.assertEqual({row['field'] for row in result['diagnostics']}, {row['field'] for row in current})
        for displayed in (result['authoring_stage'], result['inputs'][0]['authoring_stage'],
                          result['context']['input']['authoring_stage']):
            self.assertEqual(displayed['pending_summary']['total'], len(later))
            self.assertIn('/authoring_stage/pending', displayed['pending_summary']['full_report'])
            self.assertEqual(len(displayed['diagnostic_ids']), len(current))

    def test_registered_runtime_survives_stage_and_fresh_read_then_prepares_current_choices(self):
        from catalog_retrieval import runtime
        case = cases.create(self.base / 'model-studio', self.base / 'selected-runtime')
        self.root = case['root']
        settings = case['settings']
        arguments = {'state-file': str(settings.state_file.resolve()),
            'cache-dir': str(settings.cache_dir.resolve()),
            'managed-root': str(settings.managed_root.resolve()),
            'pack-root': [str(case['pack'].resolve())]}
        original_task = (self.root / 'task.json').read_bytes()
        saved = workflow.prepare(self.root, 'task.json')['run']
        loaded = workflow.read_run(self.root, saved)
        original_run = {path.relative_to(loaded.directory).as_posix(): path.read_bytes()
                        for path in loaded.directory.rglob('*') if path.is_file()}
        self.request = fixtures.current_request(self.root)
        flags = [word for name, value in arguments.items()
                 for item in (value if isinstance(value, list) else [value])
                 for word in ('--' + name, str(item))]
        drafted = self.command('draft-inputs', '--from-run', saved, '--operation', 'amend',
            '--request-file', self.request, '--out-dir', 'work/current', *flags)
        path = drafted['choices_file']
        runtime.configure_pack_runtime(None)
        report = self.choose(path, 'prepare')
        self.assertEqual(report['authoring_stage']['stage'], 'prepare')
        action = report['fresh_context_action']
        for name, value in arguments.items():
            self.assertEqual(action['args'][name], value)
        indexed = self.follow(action['argv'])
        self.assertEqual(indexed['metadata']['model']['id'], case['model'])
        self.assertEqual(indexed['progress']['reused_bytes'], 0)
        result = indexed
        while result['reading'] is None:
            action = result['actions'].get('continue') or result['actions']['all']
            result = self.follow(action['argv'])
        self.store_key(path, result['reading']['key'])
        inspected = self.command('inspect-inputs', '--choices', path)
        prepare = next(item for item in inspected['next_actions'] if item.get('command') == 'prepare')
        for name, value in arguments.items():
            self.assertEqual(prepare['args'][name], value)
        completed = self.follow([*prepare['argv'], '--view', 'full'])
        self.assertTrue(completed['ok'], completed)
        self.assertNotEqual(completed['run'], saved)
        self.assertEqual((self.root / 'task.json').read_bytes(), original_task)
        self.assertEqual({path.relative_to(loaded.directory).as_posix(): path.read_bytes()
                          for path in loaded.directory.rglob('*') if path.is_file()}, original_run)

    def direct_task(self):
        task = {'task_id': self.work['task_id'], 'route': 'development', 'features': [], 'sources': [],
            'delivery': {'path': 'delivery.txt', 'translation_notes': None},
            'criteria': [{'id': 'meaning', 'strength': 'hard', 'text': 'The text describes an empty workshop.'}],
            'world_views': []}
        fixtures.task(self.root, task, focus='supporting-setting')
        (self.root / 'delivery.txt').write_text('An empty workshop after the rain.\n', encoding='utf-8')
        (self.root / 'task.json').write_bytes(c.encoded(task))
        return task

    def scoped_task_reading(self, task, stage, *, conditions=(), source_formats=()):
        scope = {'stage': stage, 'composition': 'compose', 'source_formats': sorted(source_formats),
            'documents': [], 'render_operation': 'generation', 'conditions': sorted(conditions)}
        issued = route_reading.issue(task['route'], task['features'], execution=task['execution'],
            studio=self.root, stream=io.StringIO(), authoring_scope=scope)
        (self.root / task['route_reading']).write_bytes(c.encoded(route_reading.draft_record(issued)))

    def direct_prepare(self):
        result = subprocess.run([sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'),
            'prepare', '--root', str(self.root), '--task', 'task.json', '--view', 'full'],
            cwd=self.root, env=dict(os.environ), capture_output=True, text=True, encoding='utf-8', timeout=60)
        return result.returncode, json.loads(result.stdout)

    def test_public_direct_task_requires_final_scope_and_accepts_its_complete_scoped_reading(self):
        task = self.direct_task()
        for stage in ('definition', 'depiction', 'rendition'):
            with self.subTest(stage=stage):
                self.scoped_task_reading(task, stage)
                status, report = self.direct_prepare()
                self.assertNotEqual(status, 0, report)
                self.assertFalse(report['formal_run_created'])
                self.assertTrue(any(row['phase'] == 'route-reading' and row['state'] == 'failed'
                                    for row in report['checks']), report)
        self.scoped_task_reading(task, 'prepare')
        status, report = self.direct_prepare()
        self.assertEqual(status, 0, report)
        self.assertTrue(report['formal_run_created'])
        self.assertEqual(report['state'], 'finished')

    def test_public_direct_task_rederives_selected_image_requirements_from_current_sources(self):
        task = self.direct_task()
        self.scoped_task_reading(task, 'prepare')
        # A genuinely selected binary source changes the applicable knowledge;
        # the old receipt's no-image declaration cannot choose final sufficiency.
        (self.root / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\nSynthetic acquired image source.')
        task['sources'].append({'id': 'selected-image', 'path': 'image.png', 'role': 'reference',
            'disposition': 'applied', 'locator': 'whole image', 'reason': 'Current selected appearance source.'})
        fixtures.bind_work_basis(self.root, task, focus='supporting-setting')
        (self.root / 'task.json').write_bytes(c.encoded(task))
        status, report = self.direct_prepare()
        self.assertNotEqual(status, 0, report)
        self.assertFalse(report['formal_run_created'])
        self.assertTrue(any(row['phase'] == 'route-reading' and row['state'] == 'failed'
                            for row in report['checks']), report)
        self.scoped_task_reading(task, 'prepare', conditions=['image-source'], source_formats=['image'])
        status, report = self.direct_prepare()
        self.assertEqual(status, 0, report)
        self.assertTrue(report['formal_run_created'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
