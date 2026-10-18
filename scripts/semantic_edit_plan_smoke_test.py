"""Generic edit bindings and external production recovery on real local images."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import semantic_edit_plan as edits

PROMPT = 'Change the wall color behind the vase. Preserve the vase geometry and cafe interior.'
TARGET = {'service': 'synthetic-host', 'model_identifier': 'vendor:example-editor@1', 'operation': 'edit'}


def png(color, size=(24, 16)):
    from PIL import Image
    output = io.BytesIO()
    Image.new('RGB', size, color).save(output, format='PNG')
    return output.getvalue()


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else c.encoded(value))


def setup_plan(root):
    """A generic product scene and construction view, with synthetic evidence."""
    root.mkdir(parents=True, exist_ok=True)
    write(root, 'scene.png', png((20, 80, 100)))
    write(root, 'design.png', png((120, 30, 80), (32, 24)))
    write(root, 'model-evidence.json', {'synthetic': True, 'requested': 'Example Editor 1',
                                      'catalog_status': 'missing', 'offered_target': TARGET})
    write(root, 'upload-evidence.json', {'synthetic': True, 'images': [
        {'source_sha256': c.sha256_file(root / 'scene.png'), 'image_id': 'synthetic-scene'},
        {'source_sha256': c.sha256_file(root / 'design.png'), 'image_id': 'synthetic-design'}]})
    write(root, 'request.json', {'model': TARGET['model_identifier'], 'operation': TARGET['operation'],
                                'prompt': PROMPT, 'count': 1, 'images': ['synthetic-scene', 'synthetic-design']})
    write(root, 'prompt.txt', PROMPT.encode('utf-8'))
    plan = {'artifact_type': 'semantic-edit-plan', 'source': 'scene',
            'edit': {'target': 'wall behind the vase', 'change': 'replace the wall color',
                     'preserve': ['vase geometry', 'camera framing'], 'required_reference_roles': ['scene', 'geometry']},
            'model': {'requested': 'Example Editor 1', 'catalog_status': 'missing', 'catalog_model': None,
                      'target': copy.deepcopy(TARGET), 'evidence': {'path': 'model-evidence.json',
                      'sha256': c.sha256_file(root / 'model-evidence.json'), 'locator': 'whole synthetic lookup'}},
            'references': [
                {'id': 'scene', 'role': 'scene', 'file': 'scene.png', 'use_for': ['composition', 'camera framing'],
                 'do_not_transfer': ['old wall color']},
                {'id': 'design', 'role': 'geometry', 'file': 'design.png', 'use_for': ['vase geometry'],
                 'do_not_transfer': ['reference pose', 'reference background']}],
            'review_criteria': ['wall', 'geometry'],
            'external_request': {'file': 'request.json', 'model_field': ['model'], 'prompt_field': ['prompt'],
                                 'count_field': ['count'], 'operation_field': ['operation'], 'count': 1,
                                 'reference_fields': [
                                     {'reference': ident, 'field': ['images', i], 'value': 'synthetic-' + ident,
                                      'evidence': {'path': 'upload-evidence.json',
                                      'sha256': c.sha256_file(root / 'upload-evidence.json'),
                                      'locator': 'synthetic image ' + str(i)}} for i, ident in enumerate(('scene', 'design'))]}}
    write(root, 'edit-plan.json', plan)
    return plan


class SemanticEditPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = setup_plan(self.root)

    def validate(self):
        return edits.validate(self.plan, self.root)

    def test_binding_keeps_generic_roles_exact_target_and_all_original_hashes(self):
        result = self.validate()
        self.assertEqual(result['status'], 'prepared-not-generated')
        self.assertEqual(result['model']['catalog_status'], 'missing')
        self.assertIsNone(result['model']['catalog_model'])
        self.assertEqual(result['model']['requested'], 'Example Editor 1')
        self.assertEqual([x['role'] for x in result['references']], ['scene', 'geometry'])
        self.assertEqual(result['references'][1]['sha256'], c.sha256_file(self.root / 'design.png'))
        self.assertEqual(result['external_request']['schema_validation'],
                         {'mode': 'bounded-probe', 'unmeasured': ['schema-unavailable']})
        edits.validate_binding(result)

    def test_missing_required_reference_role_is_rejected(self):
        self.plan['edit']['required_reference_roles'].append('surface-material')
        with self.assertRaisesRegex(ValueError, 'missing required reference roles'):
            self.validate()

    def test_duplicate_or_missing_source_reference_is_rejected(self):
        self.plan['references'][1]['id'] = 'scene'
        with self.assertRaisesRegex(ValueError, 'duplicate reference id'):
            self.validate()
        self.plan = setup_plan(self.root)
        self.plan['source'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'scene role'):
            self.validate()

    def test_references_need_actual_decodable_images(self):
        write(self.root, 'design.png', b'not image pixels')
        with self.assertRaisesRegex(ValueError, 'actual image'):
            self.validate()

    def test_pinned_reference_change_is_rejected(self):
        self.plan['references'][1]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.validate()

    def test_scope_types_and_explicit_conflicts_are_rejected(self):
        self.plan['references'][1]['use_for'] = 'shape'
        with self.assertRaisesRegex(ValueError, 'semantic edit plan'):
            self.validate()
        self.plan = setup_plan(self.root)
        self.plan['references'][1]['do_not_transfer'] = ['vase geometry']
        with self.assertRaisesRegex(ValueError, 'allows and forbids'):
            self.validate()

    def test_paths_cannot_escape_the_studio(self):
        self.plan['references'][1]['file'] = '../design.png'
        with self.assertRaises(ValueError):
            self.validate()

    def test_external_request_cannot_substitute_model_or_upload(self):
        request = c.load(self.root / 'request.json')
        request['model'] = 'vendor:different-editor@1'
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'substitutes'):
            self.validate()
        request['model'] = TARGET['model_identifier']
        request['images'].reverse()
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'reference is missing or changed'):
            self.validate()

    def test_external_request_cannot_drop_or_add_undeclared_images(self):
        self.plan['external_request']['reference_fields'].pop()
        with self.assertRaisesRegex(ValueError, 'every selected reference'):
            self.validate()
        self.plan = setup_plan(self.root)
        request = c.load(self.root / 'request.json')
        request['images'].append('unselected-image')
        write(self.root, 'request.json', request)
        with self.assertRaisesRegex(ValueError, 'undeclared or missing reference'):
            self.validate()

    def test_missing_catalog_record_cannot_masquerade_as_defined(self):
        self.plan['model']['catalog_status'] = 'defined'
        with self.assertRaisesRegex(ValueError, 'catalog record'):
            self.validate()

    def test_acquired_schema_checks_actual_media_dimensions_and_unknown_keywords(self):
        schema = {'type': 'object', 'required': ['model', 'prompt', 'images'],
                  'properties': {'model': {'const': TARGET['model_identifier']}, 'prompt': {'type': 'string'},
                                 'images': {'type': 'array', 'minItems': 2, 'maxItems': 2}},
                  'x-constraints': [{'operation': 'width', 'parameters': ['images'], 'scope': 'each', 'minimum': 16}],
                  'x-unmeasured-rendering': True}
        write(self.root, 'schema-evidence.json', {'schema': json.dumps(schema)})
        self.plan['external_request']['schema'] = {'path': 'schema-evidence.json',
            'sha256': c.sha256_file(self.root / 'schema-evidence.json'), 'pointer': ['schema']}
        result = self.validate()
        self.assertEqual(result['external_request']['schema_validation']['mode'], 'target-schema')
        self.assertIn('$.x-unmeasured-rendering', result['external_request']['schema_validation']['unmeasured'])
        write(self.root, 'design.png', png((0, 0, 0), (8, 24)))
        with self.assertRaisesRegex(ValueError, 'violates acquired schema'):
            self.validate()

    def test_dispatch_reference_binding_rejects_reorder_scope_loss_and_target_change(self):
        self.plan['external_request'] = None
        self.plan['model'].update(catalog_status='defined', catalog_model='example-editor')
        binding = self.validate()
        prepared = {'transport_mode': 'multi-image', 'selected_references': [
            {'source': {'sha256': row['sha256']}, 'role': row['role'],
             'authority': {'controls': row['use_for'], 'must_not_control': row['do_not_transfer']}}
            for row in binding['references']]}
        edits.require_prepared(binding, prepared, model_id='example-editor', target=TARGET)
        for change in ('order', 'scope', 'missing'):
            current = copy.deepcopy(prepared)
            if change == 'order':
                current['selected_references'].reverse()
            elif change == 'scope':
                current['selected_references'][1]['authority']['must_not_control'] = []
            else:
                current['selected_references'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                edits.require_prepared(binding, current, model_id='example-editor', target=TARGET)
        with self.assertRaisesRegex(ValueError, 'compiled target'):
            edits.require_prepared(binding, prepared, model_id='another-editor', target=TARGET)

    def test_external_preview_does_not_relax_dispatcher_plan_requirements(self):
        from state_protocol import validate_against_schema
        schema = c.load(edits.ROOT / 'schemas/authoring/production-execution-plan.schema.json')
        value = {'run': None, 'execution': 'external', 'input_sha256': '0' * 64,
                 'request_sha256': None, 'operations': [], 'external_effects': [],
                 'readiness': {'state': 'authorization_required', 'executable': False, 'diagnostics': []},
                 'request': c.load(self.root / 'request.json'), 'service': TARGET['service'],
                 'model': TARGET['model_identifier'], 'quantities': {'submissions': 1, 'outputs': 1}}
        self.assertEqual(validate_against_schema(value, schema), [])
        value['execution'] = 'dispatcher'
        errors = validate_against_schema(value, schema)
        for field in ('recording', 'transport', 'handoff', 'validation', 'mutable_fields'):
            self.assertTrue(any('requires ' + repr(field) in error for error in errors), errors)


class SemanticEditSuppliedDispatchTests(unittest.TestCase):
    """Public scoped preparation, real carrier bytes and frozen dispatcher evidence."""

    def setUp(self):
        import production_case_fixtures as cases
        import production_fixtures as fixture
        import prepare_generation_references as refs
        self.refs = refs
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.enterContext(fixture.scratch_home(self.base / 'home'))
        self.case = cases.create(self.base / 'studio', self.base / 'runtime')
        self.addCleanup(refs.configure_pack_runtime, None)
        self.root = self.case['root']
        self.model = cases.MODEL_ID
        self.plan = setup_plan(self.root)
        self.plan['external_request'] = None
        self.plan['model'].update(catalog_status='defined', catalog_model=self.model,
            target={'service': 'synthetic', 'model_identifier': 'synthetic:robot', 'operation': 'generate'})
        write(self.root, 'model-evidence.json', {'synthetic': True, 'model': self.plan['model']['target']})
        self.plan['model']['evidence']['sha256'] = c.sha256_file(self.root / 'model-evidence.json')
        write(self.root, 'edit-plan.json', self.plan)

    def prepare(self, **kwargs):
        return self.refs.prepare_semantic_edit_references(self.plan, studio=self.root,
            output_dir=self.base / 'carriers', **kwargs)

    def legacy_selections(self):
        return [{'role': row['role'], 'source': {'kind': 'supplied-file',
            'reference_id': row['id'], 'resolved_path': str(self.root / row['file'])}}
            for row in self.plan['references']]

    def test_public_cli_derives_model_files_and_exact_scopes_without_selection_json(self):
        import contextlib
        from pack_runtime_cli import PackRuntimeContext
        output = self.root / 'prepared.json'
        arguments = ['--studio', str(self.root), '--semantic-edit-plan-file', 'edit-plan.json',
            '--output-dir', str(self.base / 'carriers'), '--out', str(output)]
        arguments += PackRuntimeContext(self.case['settings'], (self.case['pack'],)).command_arguments()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.refs.main(arguments), 0)
        self.refs.configure_pack_runtime(self.case['settings'])
        value = c.load(output)
        self.assertEqual(value['target_model'], self.model)
        self.assertEqual(value['semantic_edit_binding'], edits.validate(self.plan, self.root))
        self.assertEqual([row['source']['reference_id'] for row in value['selected_references']], ['scene', 'design'])
        for expected, actual in zip(self.plan['references'], value['selected_references']):
            self.assertEqual(actual['authority'], {'controls': expected['use_for'],
                                                   'must_not_control': expected['do_not_transfer']})
        self.assertIn('vase geometry', value['reference_preamble'])
        self.assertIn('Reference 2 means Image 2', value['reference_preamble'])

    def test_empty_authored_exclusions_remain_empty_only_in_the_bound_branch(self):
        from state_protocol import finalize_artifact, validate_artifact
        self.plan['references'][1]['do_not_transfer'] = []
        value = self.prepare()
        self.assertEqual(value['selected_references'][1]['authority']['must_not_control'], [])
        self.assertNotIn('Do not inherit: .', value['reference_preamble'])
        unbound = copy.deepcopy(value)
        unbound.pop('semantic_edit_binding')
        unbound = finalize_artifact(unbound)
        self.assertFalse(validate_artifact(unbound)['ok'])
        with self.assertRaises(ValueError):
            self.refs.validate_prepared_reference_set(unbound)
        with self.assertRaisesRegex(ValueError, 'must not be empty'):
            self.refs._validate_authority(value['selected_references'][1]['authority'], 'legacy authority')

    def test_bound_rows_reject_resealed_scope_role_order_identity_and_file_drift(self):
        value = self.prepare()
        for change in ('scope', 'role', 'order', 'identity', 'omission'):
            current = copy.deepcopy(value)
            if change == 'scope':
                current['selected_references'][1]['authority']['controls'] = ['scene lighting']
            elif change == 'role':
                current['selected_references'][1]['role'] = 'style'
            elif change == 'order':
                current['selected_references'].reverse()
            elif change == 'identity':
                current['selected_references'][1]['source']['reference_id'] = 'another-design'
            else:
                current['selected_references'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.refs.finalize_prepared_reference_set(current, model=self.model)
        write(self.root, 'design.png', png((1, 2, 3)))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.refs.validate_prepared_reference_set(value)

    def test_exact_model_external_and_state_owners_cannot_be_substituted(self):
        with self.assertRaisesRegex(ValueError, 'differs from the semantic edit plan'):
            self.prepare(model='grok-imagine-image-2.0')
        self.plan['model']['target']['model_identifier'] = 'synthetic:other-model'
        with self.assertRaisesRegex(ValueError, 'active model offering'):
            self.prepare()
        self.plan['model']['target']['model_identifier'] = 'synthetic:robot'
        self.plan['model']['target']['operation'] = 'instruction-edit'
        with self.assertRaisesRegex(ValueError, "expected 'generate', received 'instruction-edit'"):
            self.prepare()
        self.plan['model']['target']['operation'] = 'generate'
        bound = edits.validate(self.plan, self.root)
        with self.assertRaisesRegex(ValueError, 'state or pack authority'):
            self.refs.validate_prepared_references([], model=self.model,
                semantic_edit_binding=bound, reference_selection={})
        with self.assertRaisesRegex(ValueError, 'state or pack authority'):
            self.refs.validate_prepared_references([], model=self.model,
                semantic_edit_binding=bound, reference_use_plan={})
        external = setup_plan(self.root)
        external['model'].update(catalog_status='defined', catalog_model=self.model)
        with self.assertRaisesRegex(ValueError, 'external_request null'):
            self.refs.prepare_semantic_edit_references(external, studio=self.root, output_dir=self.base / 'external')

    def test_pinned_and_concurrently_changed_files_fail_before_a_scoped_set_is_published(self):
        self.plan['references'][1]['sha256'] = c.sha256_file(self.root / 'design.png')
        write(self.root, 'design.png', png((1, 2, 3)))
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.prepare()
        self.plan['references'][1].pop('sha256')
        original = self.refs._preflight_selection_item
        def change_file(raw, index):
            if index == 1:
                write(self.root, 'design.png', png((3, 2, 1)))
            return original(raw, index)
        with patch.object(self.refs, '_preflight_selection_item', side_effect=change_file):
            with self.assertRaisesRegex(ValueError, 'changed during reference preparation'):
                self.prepare()

    def test_legacy_supplied_path_keeps_conservative_authority_and_rejects_scope_injection(self):
        selected = self.legacy_selections()
        legacy = self.refs.prepare_references(selected, model=self.model, output_dir=self.base / 'legacy')
        self.assertNotIn('semantic_edit_binding', legacy)
        self.assertEqual(legacy['selected_references'][1]['authority'], self.refs.conservative_authority('geometry'))
        self.refs.validate_prepared_reference_set(legacy)
        selected[1]['authority'] = {'controls': ['vase geometry'], 'must_not_control': ['scene lighting']}
        with self.assertRaisesRegex(ValueError, 'invalid shape'):
            self.refs.prepare_references(selected, model=self.model, output_dir=self.base / 'injected')
        selected = self.legacy_selections()
        selected[1]['source']['kind'] = 'pack-artifact'
        with self.assertRaisesRegex(ValueError, 'Reference Use Plan'):
            self.refs.prepare_references(selected, model=self.model, output_dir=self.base / 'pack')

    def test_frozen_reference_bundle_keeps_binding_and_verifies_without_original_studio(self):
        import shutil
        from build_generation_payload import materialize_cli_reference_bundle
        from reference_delivery import bindings
        self.plan['references'][1]['do_not_transfer'] = []
        original = self.prepare(transport_mode='single-board')
        staging = self.base / 'portable'
        staging.mkdir()
        value, _ = materialize_cli_reference_bundle(original, model=self.model,
            source_root=self.root, staging_root=staging, companion_name='image.references')
        self.assertEqual(value['semantic_edit_binding'], original['semantic_edit_binding'])
        moved = self.base / 'moved'
        shutil.move(staging, moved)
        shutil.rmtree(self.root)
        self.refs.configure_pack_runtime(None)
        with patch.object(self.refs, 'resolve_model_record', side_effect=AssertionError('Frozen evidence needs no live model')):
            self.assertEqual(self.refs.validate_prepared_reference_content(value, package_root=moved), value)
        self.assertEqual([row['attachment_number'] for row in bindings('single-board', value['selected_references'],
                                                                     value['single_board'])], [1, 1])
        source = moved / 'image.references' / 'sources' / value['selected_references'][1]['source']['sha256']
        source.write_bytes(png((4, 5, 6)))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.refs.validate_prepared_reference_content(value, package_root=moved)

    def object_task(self, model_name=None):
        import studio
        import production_spec
        import prompt_plot
        import prompt_retrieval
        from reading_fixtures import fixture_reading
        from render_contract_fixtures import intent
        from request_validation_fixtures import fixture_validation
        task = self.case['task']
        task['features'] = ['semantic-instruction-edit', 'instruction-edit']
        task['semantic_edit'] = 'edit-plan.json'
        task['sources'] += [{'id': 'source-scene', 'path': 'scene.png', 'role': 'accepted-source',
            'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic product scene selected for this edit.'}]
        task['criteria'] += [{'id': ident, 'strength': 'hard', 'text': text, 'evidence': 'image'}
            for ident, text in [('wall', 'The wall change is visible.'), ('geometry', 'The vase geometry remains fixed.')]]
        spec = production_spec.load(production_spec.TEMPLATE)
        spec.update(source_brief=PROMPT, target_model=model_name or self.model, image_promise=PROMPT,
                    render_intent=intent(PROMPT, 'instruction-edit'))
        spec['scene']['environment'] = 'A ceramic vase on a cafe table with a painted wall behind it.'
        spec['constraints']['construction_invariants'] = ['Preserve the vase geometry and source framing.']
        write(self.root, 'spec.json', spec)
        plot = c.load(self.root / 'plot.json')
        plot['story'] = [{'id': 's1', 'beat': 'A ceramic vase stands against a repainted cafe wall.', 'visibility': 'visible'}]
        plot['derived'] = [{'kind': kind, 'statement': statement, 'from': ['s1']} for kind, statement in (
            ('shows', 'one ceramic vase'), ('placement', 'on the existing cafe table'),
            ('composition', 'retain the source framing'), ('must_preserve', 'retain the vase geometry'))]
        plot['derived'].append({'kind': 'free', 'statement': 'The new wall color is the selected change.'})
        plot['approved']['content_sha256'] = prompt_plot.content_sha256(plot)
        write(self.root, 'plot.json', plot)
        retrieval = c.load(self.root / 'retrieval.json')
        retrieval['elements'][0]['composed_wording'] = PROMPT
        write(self.root, 'retrieval.json', prompt_retrieval.settle_retrieval_record(retrieval, prompt=PROMPT, plot=plot))
        write(self.root, 'validation.json', fixture_validation(self.root, self.model,
            reference_mode='prompt-prefix', service='synthetic'))
        write(self.root, 'references.json', self.prepare())
        task['generation'].update(references='references.json', continuity={})
        studio.add_character(self.root, 'product-scene', 'general')
        task['recording'].update(character='product-scene', slot='candidate', subject_map={}, sheet_panel=False)
        write(self.root, 'reading.json', fixture_reading(route=task['route'], features=task['features'],
                                                        studio=self.root, ledger=self.root / 'work/reads.jsonl'))
        write(self.root, 'task.json', task)
        return task

    def test_object_only_dispatcher_prepares_exact_scopes_and_recovers_frozen_evidence(self):
        import production_workflow as workflow
        import production_execution as execution
        import execution_lifecycle as accounting
        import transport_synthetic
        from production_compiler import check_task
        from test_production_execution import decisions
        from verify_generation_payload import verify_content
        self.object_task()
        check = check_task(self.root, 'task.json')
        self.assertTrue(check['ok'], check)
        self.assertIn('vase geometry', check['request_preview']['prompt'])
        run = workflow.prepare(self.root, 'task.json')['run']
        directory, prepared, consumer, _ = workflow.load_run(self.root, run)
        package = c.load(directory / 'package.json')
        self.assertEqual(package['production_spec']['subjects'], [])
        self.assertEqual(package['visual_continuity']['subjects'], {})
        self.assertEqual(package['prepared_reference_set']['semantic_edit_binding'], consumer['semantic_edit'])
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        for name in ('scene.png', 'design.png', 'edit-plan.json', 'model-evidence.json'):
            (self.root / name).unlink()
        verify_content(package, package_root=directory)
        before = accounting.summary(self.root)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Recovery must not send again')):
            execution.resume(self.root, run)
        self.assertEqual(accounting.summary(self.root), before)
        self.assertEqual((before['submissions'], before['captured_outputs']), (1, 1))

    def test_alias_declared_target_still_seals_the_request(self):
        import production_workflow as workflow
        import production_execution as execution
        from production_compiler import check_task
        from test_production_execution import decisions
        self.object_task(model_name='synthetic robot fixture')
        check = check_task(self.root, 'task.json')
        self.assertTrue(check['ok'], check)
        run = workflow.prepare(self.root, 'task.json')['run']
        directory = workflow.load_run(self.root, run)[0]
        package = c.load(directory / 'package.json')
        self.assertEqual(package['model'], 'synthetic robot fixture')
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertEqual(result['runs'][0]['capture'], 'complete')

    def test_task_cannot_change_or_drop_the_plan_that_owns_prepared_scopes(self):
        from production_compiler import check_task
        task = self.object_task()
        self.plan['edit']['change'] = 'Replace the wall texture as well as its color.'
        write(self.root, 'edit-plan.json', self.plan)
        check = check_task(self.root, 'task.json')
        self.assertFalse(check['ok'])
        self.assertIn('prepared semantic edit binding differs', str(check))
        task.pop('semantic_edit')
        task['features'].remove('semantic-instruction-edit')
        from reading_fixtures import fixture_reading
        write(self.root, 'reading.json', fixture_reading(route=task['route'], features=task['features'],
                                                        studio=self.root, ledger=self.root / 'work/reads.jsonl'))
        write(self.root, 'task.json', task)
        check = check_task(self.root, 'task.json')
        self.assertFalse(check['ok'])
        self.assertIn('scoped semantic references require', str(check))


class SemanticEditProductionTests(unittest.TestCase):
    def setUp(self):
        import production_fixtures as fixture
        import work_ledger as ledger
        self.fixture = fixture
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.enterContext(fixture.scratch_home(base / 'home'))
        self.root = base / 'studio'
        self.plan = setup_plan(self.root)
        entry = ledger.begin(self.root, 'Synthetic product background editing', ['prepare', 'review'])
        self.task = {'task_id': entry['task_id'], 'route': 'generation',
                     'features': ['semantic-instruction-edit', 'instruction-edit'],
                     'sources': [{'id': 'source-scene', 'path': 'scene.png', 'role': 'accepted-source',
                                  'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic product scene.'},
                                 {'id': 'product-design', 'path': 'design.png', 'role': 'reference-images',
                                  'disposition': 'applied', 'locator': 'whole', 'reason': 'Synthetic geometry reference.'}],
                     'delivery': {'path': 'prompt.txt', 'transport': 'authored-rendition',
                                  'translation_notes': 'Synthetic instruction uses explicit reference roles.'},
                     'criteria': [{'id': 'wall', 'strength': 'hard', 'text': 'Requested wall edit is visible.'},
                                  {'id': 'geometry', 'strength': 'hard', 'text': 'Product geometry remains stable.'}],
                     'world_views': [], 'semantic_edit': 'edit-plan.json'}
        fixture.task(self.root, self.task, artifact='image', execution='external')
        for row in self.task['criteria']:
            row['evidence'] = 'image'
        write(self.root, 'task.json', self.task)

    def prepared(self):
        import production_workflow as workflow
        result = workflow.prepare(self.root, 'task.json')
        run = result['run']
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        token = self.fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        return run, token

    def update_authority(self, authority):
        import production_store as store
        prior = store.authority_record(self.root, self.task['task_id'])
        write(self.root, 'amended-authority.json', authority)
        store.import_authority(self.root, 'amended-authority.json', expected=prior['sha256'])

    def test_one_source_edit_needs_no_auxiliary_image(self):
        import production_workflow as workflow
        self.plan['references'] = self.plan['references'][:1]
        self.plan['edit']['required_reference_roles'] = ['scene']
        self.plan['external_request']['reference_fields'] = self.plan['external_request']['reference_fields'][:1]
        request = c.load(self.root / 'request.json')
        request['images'] = request['images'][:1]
        self.task['sources'] = self.task['sources'][:1]
        write(self.root, 'request.json', request)
        write(self.root, 'edit-plan.json', self.plan)
        write(self.root, 'task.json', self.task)
        (self.root / 'design.png').unlink()
        run, token = self.prepared()
        consumer = workflow.load_run(self.root, run)[2]
        self.assertEqual(len(consumer['semantic_edit']['references']), 1)
        self.assertEqual(consumer['semantic_edit']['external_request']['request']['images'], ['synthetic-scene'])
        self.assertEqual(workflow.claim_external(self.root, run, 1, token)['data']['count'], 1)

    def test_scene_must_match_the_applied_task_source(self):
        self.task['sources'][0]['path'] = 'design.png'
        with self.assertRaisesRegex(ValueError, 'applied accepted-source'):
            edits.task_binding(self.root, self.task, lambda base, path: (base / path).read_bytes())

    def test_external_readiness_requires_exact_current_submission_authority(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        run = workflow.prepare(self.root, 'task.json')['run']
        directory = workflow.load_run(self.root, run)[0]
        self.assertEqual(c.load(directory / 'execution-plan.json')['readiness']['state'], 'authorization_required')

        def status_without_events():
            before = workflow.load_run(self.root, run)[3]
            result = workflow.status(self.root, run)['runs'][0]
            self.assertEqual(workflow.load_run(self.root, run)[3], before)
            self.assertEqual(result['submission'], 'unclaimed')
            self.assertFalse(result['send_started'])
            return result

        initial = status_without_events()
        self.assertEqual(initial['readiness'], 'authorization_required')
        self.assertEqual(initial['next_action']['command'], 'handoff')
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        handed = status_without_events()
        self.assertEqual(handed['readiness'], 'authorization_required')
        self.assertEqual(handed['next_action']['command'], 'claim-external')
        self.fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        self.assertEqual(status_without_events()['readiness'], 'ready')

        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['submission_validation_modes'] = ['target-schema']
        self.update_authority(authority)
        narrowed = status_without_events()
        self.assertEqual(narrowed['readiness'], 'authorization_required')
        self.assertIn('GRANT_SCOPE_EXCEEDED', {item['code'] for item in narrowed['readiness_diagnostics']})
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_bounded_probe_uses_actual_validation_mode_authority(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['submission_validation_modes'] = ['target-schema']
        write(self.root, self.task['authority'], authority)
        run = workflow.prepare(self.root, 'task.json')['run']
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        intent = workflow.external_intent(self.root, run, 1)
        with self.assertRaises(ProductionError) as caught:
            self.fixture.grant(self.root, run, intent)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)
        authority['grants'][0]['submission_validation_modes'] = ['bounded-probe']
        self.update_authority(authority)
        token = self.fixture.grant(self.root, run, intent)
        self.assertEqual(workflow.claim_external(self.root, run, 1, token)['data']['count'], 1)

    def test_changed_validation_mode_authority_blocks_a_prepared_claim(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        run, token = self.prepared()
        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['submission_validation_modes'] = ['target-schema']
        self.update_authority(authority)
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_external_request_cannot_use_an_unassessed_dispatcher_scope(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        authority = c.load(self.root / self.task['authority'])
        authority['grants'][0]['request_scope'] = {
            'plan': {'path': 'model-evidence.json', 'sha256': c.sha256_file(self.root / 'model-evidence.json'),
                     'locator': 'whole synthetic declaration'},
            'cases': [{'id': 'synthetic-dispatcher-case', 'productions': [self.task['production_id']],
                       'targets': [{'target': TARGET, 'execution': {key: '0' * 64 for key in (
                           'service_execution_sha256', 'offering_contract_sha256', 'transport_sha256')}}],
                       'fixed': {}, 'variations': {}, 'review_criteria': []}]}
        write(self.root, self.task['authority'], authority)
        run = workflow.prepare(self.root, 'task.json')['run']
        self.fixture.handoff(self.root, run, 'synthetic-host', 'manual')
        with self.assertRaises(ProductionError) as caught:
            self.fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_SCOPE_EXCEEDED')
        self.assertIn('dispatcher request scope', str(caught.exception))
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_check_prepare_external_capture_and_resume_keep_exact_input_and_result(self):
        import production_workflow as workflow
        import production_execution as execution
        import execution_lifecycle as lifecycle
        from production_compiler import check_task
        result = check_task(self.root, 'task.json')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['request_preview'], c.load(self.root / 'request.json'))
        run, token = self.prepared()
        _, prepared, consumer, _ = workflow.load_run(self.root, run)
        bound = consumer['semantic_edit']
        self.assertEqual(bound['references'][1]['sha256'], c.sha256_file(self.root / 'design.png'))
        self.assertIn('design.png', [x['path'] for x in prepared['dependencies']])
        claim = workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(claim['data']['target'], TARGET)
        self.assertEqual(claim['data']['external_request_sha256'], c.sha256_file(self.root / 'request.json'))
        self.assertEqual(workflow.claim_external(self.root, run, 1, token)['sha256'], claim['sha256'])
        output = png((40, 120, 70))
        write(self.root, 'output.png', output)
        (self.root / 'scene.png').unlink()
        candidate = workflow.capture(self.root, run, 'output.png', 'Synthetic returned pixels; no model-quality claim.')
        self.assertEqual(workflow.capture(self.root, run, 'output.png', 'Repeated synthetic receipt.')['sha256'], candidate['sha256'])
        write(self.root, 'host-response.json', {'synthetic': True, 'output_sha256': c.digest(output), 'cost': '0'})
        receipt = {'claim': claim['sha256'], 'actor': self.fixture.ACTOR, 'outputs': 1,
                   'response': {'path': 'host-response.json', 'sha256': c.sha256_file(self.root / 'host-response.json'), 'locator': 'whole'},
                   'cost': {'currency': 'USD', 'amount': '0'}, 'final': True,
                   'reason': 'Synthetic external host receipt of one local PNG.'}
        write(self.root, 'receipt.json', receipt)
        self.assertTrue(workflow.settle_external(self.root, run, 'receipt.json')['execution_completed'])
        before = lifecycle.summary(self.root)
        execution.resume(self.root, run)
        self.assertEqual(lifecycle.summary(self.root), before)
        self.assertEqual((before['submissions'], before['captured_outputs']), (1, 1))
        review = workflow.draft_review(self.root, run, candidate['sha256'])
        self.assertTrue(all(x['verdict'] == 'not-assessed' for x in review['checks']))

    def test_changed_required_reference_blocks_claim_before_any_send(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        from production_diagnostics import ProductionError
        run, token = self.prepared()
        write(self.root, 'design.png', png((1, 2, 3)))
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_external(self.root, run, 1, token)
        self.assertEqual(caught.exception.diagnostic.code, 'SOURCE_CHANGED')
        self.assertEqual(lifecycle.summary(self.root)['submissions'], 0)

    def test_claim_count_and_delivery_prompt_must_match_exact_request(self):
        import production_workflow as workflow
        run, _ = self.prepared()
        with self.assertRaisesRegex(ValueError, 'claim count'):
            workflow.external_intent(self.root, run, 2)
        other = Path(self.temp.name) / 'other'
        plan = setup_plan(other)
        task = copy.deepcopy(self.task)
        write(other, 'prompt.txt', b'Different instruction')
        with self.assertRaisesRegex(ValueError, 'production delivery'):
            edits.task_binding(other, task, lambda base, path: (base / path).read_bytes())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
