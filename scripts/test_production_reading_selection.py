"""Keep scoped knowledge attached to actual editable source and target owners."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import authoring_work
import execution_contract as c
import execution_routes
import production_inputs
import production_reading_scope as scope


class ReadingSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cpb-reading-selection-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.task = {'route': 'generation', 'execution': 'dispatcher', 'sources': [],
                     'direction': {'source_allowances': []}, 'criteria': []}
        self.choices = {'authoring_stage': 'depiction', 'target': None,
            'task_changes': {}, 'external': None,
            'authoring': {'task': {}, 'delivery': {'content': 'Synthetic authored text.',
                'translation_notes': None}, 'documents': {}, 'generation': {},
                'references': None, 'upscale': None, 'source_files': {}}}

    def selected(self, *, context=None, basis=None):
        return scope.selection(self.root, self.choices, self.task, context=context, basis=basis)

    def references(self, **changes):
        return {'transport_mode': 'multi-image', 'max_side': 1536,
            'reference_use_plan': None, 'reference_selection': None,
            'additional_references': [], 'image_input': {},
            'zero_reference_reason': None, 'source_files': {}, **changes}

    def sections(self, selected, path):
        resolved = execution_routes.resolve(self.task['route'], execution=self.task['execution'],
                                             authoring_scope=selected)
        return {row['anchor'] for row in resolved['section_owners'].get(path, [])}

    def assert_image_knowledge(self, selected, expected=True):
        self.assertEqual('references' in selected['conditions'], expected)
        self.assertEqual('image-source' in selected['conditions'], expected)
        sections = self.sections(selected, 'references/runtime/production-direction.md')
        self.assertEqual('form-a-prompt-from-an-image' in sections, expected)

    def test_pack_and_state_reference_choices_select_the_image_contract(self):
        cases = [self.references(reference_use_plan={'items': [
            {'source': {'kind': 'pack-artifact'}, 'canonical_record_id': 'synthetic-record'}]}),
            self.references(reference_selection={'selected_references': [
                {'source': {'kind': 'supplied-file', 'resolved_path': 'state.png'},
                 'subject_id': 'synthetic-subject', 'binding_id': 'state-binding'}]}),
            self.references(additional_references=[
                {'source': {'kind': 'supplied-file', 'resolved_path': 'direct.png'}}]),
            self.references(image_input={'references': [{'id': 'image', 'file': 'image.png'}]})]
        for references in cases:
            with self.subTest(references=references):
                self.choices['authoring']['references'] = references
                self.assert_image_knowledge(self.selected())

    def test_reference_witnesses_and_deselected_native_rows_are_not_selection(self):
        self.choices['authoring']['references'] = self.references(
            source_files={'old.png': {'sha256': '0' * 64, 'media_type': 'image/png'}})
        self.assert_image_knowledge(self.selected(), False)
        self.choices['authoring']['references'].update(
            reference_use_plan={'items': [{'source': {'kind': 'pack-artifact'}}]},
            image_input={'references': []})
        self.assert_image_knowledge(self.selected(), False)

    def test_external_canonical_choices_own_selection_instead_of_transport_rows(self):
        self.task['execution'] = 'external'
        self.choices['external'] = {'image_input': {'references': []},
            'reference_delivery': {'choices': self.references(reference_use_plan={'items': [
                {'source': {'kind': 'pack-artifact'}}]})}}
        self.assert_image_knowledge(self.selected())
        self.choices['external']['reference_delivery']['choices'] = self.references()
        self.choices['external']['image_input']['references'] = [{'id': 'old', 'transport': {}}]
        self.assert_image_knowledge(self.selected(), False)

    def test_selected_external_file_reads_current_reference_rows_and_reports_unknown(self):
        self.task['execution'] = 'external'
        self.choices['external'] = {'image_input': 'plan.json'}
        self.task['image_input'] = 'plan.json'
        plan = self.root / 'plan.json'
        plan.write_bytes(c.encoded({'references': []}))
        self.assert_image_knowledge(self.selected(), False)
        plan.write_bytes(c.encoded({'references': [{'id': 'selected', 'file': 'image.png'}]}))
        self.assert_image_knowledge(self.selected())
        plan.write_text('not json', encoding='utf-8')
        unreadable = self.selected()
        self.assert_image_knowledge(unreadable)
        self.assertIn('unknown-sources', unreadable['conditions'])
        plan.unlink()
        self.assertIn('unknown-sources', self.selected()['conditions'])

    def test_current_inline_or_authored_selection_replaces_an_original_task_path(self):
        self.task['image_input'] = 'no-longer-selected.json'
        self.choices['external'] = {'image_input': {'references': []}}
        self.assert_image_knowledge(self.selected(), False)
        self.choices['external'] = None
        self.choices['authoring']['references'] = self.references()
        self.assert_image_knowledge(self.selected(), False)
        self.choices['authoring']['references'] = None
        self.assertIn('unknown-sources', self.selected()['conditions'])

    def test_nested_identity_variation_keeps_its_source_contract(self):
        self.task['criteria'] = [{'id': 'criterion', 'identity_bindings': [
            {'source': 'definition', 'treatment': 'authorized-variation', 'variation': 'allowed'}]}]
        selected = self.selected()
        self.assertIn('accepted-variation', selected['conditions'])
        self.assertIn('preserve-accepted-variation-at-its-declared-scope',
            self.sections(selected, 'references/runtime/production-direction.md'))
        self.task['criteria'][0]['identity_bindings'][0]['treatment'] = 'preserve'
        self.assertNotIn('accepted-variation', self.selected()['conditions'])
        self.task['direction']['source_allowances'] = [{'source': 'definition', 'allowance': 'declared'}]
        self.assertIn('accepted-variation', self.selected()['conditions'])

    def previous(self, *, model='fixture-model', service='fixture-service', operation='imageInference'):
        return {'derived_from': {'source_run': {'target_identity': {
            'model': model, 'service': service, 'operation': operation,
            'route': self.task['route'], 'execution': self.task['execution']}}}}

    def test_same_external_identity_is_not_a_target_change_but_native_operation_is(self):
        self.task['execution'] = 'external'
        self.choices['target'] = {'kind': 'external', 'model': {'requested': 'Fixture model',
            'target': {'model_identifier': 'fixture-model', 'service': 'fixture-service',
                       'operation': 'imageInference'},
            'evidence': {'path': 'provider.txt', 'locator': 'Fixture contract'}}}
        previous = self.previous()
        self.assertNotIn('target-change', self.selected(context=previous)['conditions'])
        self.choices['target']['model']['target']['operation'] = 'imageEdit'
        changed = self.selected(context=previous)
        self.assertIn('target-change', changed['conditions'])
        self.assertIn('select-and-change-the-target',
            self.sections(changed, 'references/runtime/production-authoring.md'))

    def test_catalog_compares_explicit_native_operation_without_acquiring_a_runtime(self):
        self.choices['target'] = {'kind': 'catalog', 'model': 'fixture-model', 'service': 'fixture-service'}
        previous = self.previous()
        with patch('production_target._runtime', side_effect=AssertionError('Do not acquire a runtime')):
            self.assertNotIn('target-change', self.selected(context=previous)['conditions'])
            self.choices['target']['operation'] = 'imageEdit'
            self.assertIn('target-change', self.selected(context=previous)['conditions'])
            self.choices['target']['operation'] = 'imageInference'
            self.task['execution'] = 'external'
            self.assertIn('target-change', self.selected(context=previous)['conditions'])

    def test_acquired_target_compares_the_record_identity_not_its_file_path(self):
        self.task['execution'] = 'authored'
        self.choices['target'] = {'kind': 'acquired', 'model_file': 'model.json', 'service': 'fixture-service'}
        path = self.root / 'model.json'
        path.write_bytes(c.encoded({'id': 'fixture-model', 'revision': 'new-guidance'}))
        previous = self.previous()
        self.assertNotIn('target-change', self.selected(context=previous)['conditions'])
        path.write_bytes(c.encoded({'id': 'another-model'}))
        self.assertIn('target-change', self.selected(context=previous)['conditions'])
        path.unlink()
        self.assertIn('target-change', self.selected(context=previous)['conditions'])

    def test_file_selected_external_target_uses_its_declared_native_identity(self):
        self.task['execution'] = 'external'
        self.choices['external'] = {'image_input': 'plan.json'}
        (self.root / 'plan.json').write_bytes(c.encoded({'references': [], 'model': {'target': {
            'model_identifier': 'fixture-model', 'service': 'fixture-service', 'operation': 'imageInference'}}}))
        self.assertNotIn('target-change', self.selected(context=self.previous())['conditions'])

    def test_acquired_source_formats_and_new_semantic_edits_keep_image_knowledge(self):
        source = authoring_work.acquire_source(b'\x89PNG\r\n\x1a\nfixture', format='binary')
        basis = {'operation': 'amend', 'sources': {'image': source},
                 'applications': {'selected': {'source': 'image', 'pointer': ''}}}
        selected = self.selected(basis=basis)
        self.assertEqual(selected['source_formats'], ['image'])
        self.assertIn('image-source', selected['conditions'])
        self.assertEqual(selected['composition'], 'amend')
        self.choices['task_changes']['semantic_edit'] = {'base_image': 'selected.png'}
        self.assertTrue({'semantic-edit', 'image-source', 'references'} <= set(self.selected()['conditions']))

    def test_selected_specification_keeps_its_rendering_contract_after_file_resolution(self):
        from input_evidence import InputEvidence
        from production_authoring import read_editable
        self.choices['authoring_stage'] = 'rendition'
        specification = {'render_intent': {'artifact_type': 'render-intent',
            'execution_mode': 'generation', 'prompt_expression': 'An achromatic illustration.'}}
        (self.root / 'specification.json').write_bytes(c.encoded({'chosen': specification}))
        self.choices['authoring']['documents']['production_spec'] = {
            'file': 'specification.json', 'field': ['chosen']}
        self.choices['authoring']['generation']['render_intent'] = None
        selected = self.selected()
        self.assertIn('production-spec', selected['conditions'])
        self.assertIn('represent-the-selected-design',
            self.sections(selected, 'references/runtime/render-contract.md'))
        resolved, _, missing = read_editable(self.choices['authoring'], InputEvidence(self.root))
        self.assertEqual(missing, [])
        self.assertEqual(resolved['documents']['production_spec'], specification)
        resolved_choices = {**self.choices, 'authoring': resolved}
        self.assertEqual(scope.selection(self.root, resolved_choices, self.task), selected)

    def test_top_level_visual_owner_keeps_the_same_contract_as_its_compiled_document(self):
        self.choices['visual'] = {'purpose': 'image', 'basis': {'path': 'decision.txt', 'locator': 'whole'},
            'subjects': {}, 'production_spec': 'specification.json', 'prepared_reference_set': 'references.json'}
        selected = self.selected()
        self.assertIn('state', selected['conditions'])
        self.assertIn('an-image-of-an-action-is-not-the-action',
            self.sections(selected, 'references/runtime/production-direction.md'))
        self.choices['visual'] = None
        self.choices['authoring']['documents']['visual_continuity'] = {'file': 'visual.json'}
        self.assertEqual(selected['conditions'], self.selected()['conditions'])

    def test_applied_specification_source_keeps_its_contract_without_a_generation_document(self):
        self.task['execution'] = 'external'
        self.task['sources'] = [{'id': 'selected-specification', 'role': 'production-spec',
            'disposition': 'applied', 'path': 'specification.json'}]
        selected = self.selected()
        self.assertIn('production-spec', selected['conditions'])
        self.assertIn('select-a-production-specification',
            self.sections(selected, 'references/runtime/production-authoring.md'))
        self.task['sources'][0]['disposition'] = 'considered-not-used'
        self.assertNotIn('production-spec', self.selected()['conditions'])

    def test_from_choices_and_resolved_selection_derive_the_same_conditions(self):
        self.task['execution'] = 'external'
        self.choices['external'] = {'image_input': 'plan.json'}
        (self.root / 'plan.json').write_bytes(c.encoded({'references': [{'id': 'image', 'file': 'image.png'}],
            'model': {'target': {'model_identifier': 'fixture-model', 'service': 'fixture-service',
                                 'operation': 'imageInference'}}}))
        self.choices['authoring']['task']['criteria'] = [{'identity_bindings': [
            {'treatment': 'authorized-variation'}]}]
        context = {'task_content': copy.deepcopy(self.task), **self.previous()}
        (self.root / 'choices.json').write_bytes(c.encoded(self.choices))
        (self.root / 'context.json').write_bytes(c.encoded(context))
        selected, task = scope.from_choices(self.root, 'choices.json')
        current_task = production_inputs._chosen_task(context['task_content'], self.choices)
        self.assertEqual(task, current_task)
        self.assertEqual(selected, scope.selection(self.root, self.choices, current_task, context=context))
        self.assertTrue({'references', 'image-source', 'accepted-variation'} <= set(selected['conditions']))
        self.assertNotIn('target-change', selected['conditions'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
