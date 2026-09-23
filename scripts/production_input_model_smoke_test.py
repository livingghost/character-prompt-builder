#!/usr/bin/env python3
"""Build real local input contracts with an explicitly synthetic model interface."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import execution_contract as c
from input_evidence import InputEvidence
import production_inputs as inputs
import production_input_adapters as adapters
import production_workflow_smoke_test as fixtures
import reading_fixtures
import request_validation


class ModelInputTests(unittest.TestCase):
    def setUp(self):
        fixtures.PackageIntegrationTests.setUp(self)
        self.spec['route'] = 'generation'
        self.spec['artifact'] = 'image'
        reading_fixtures.task_reading(self.root, self.spec)
        reading = c.load(self.root / self.spec['route_reading'])
        self.write('task.json', self.spec)
        self.write('production-spec.json', self.package['production_spec'])
        self.write('prepared-references.json', self.package['prepared_reference_set'])
        validation = self.package['request_validation']
        self.target = validation['target']
        service = {'id': self.target['service'],
                   'endpoint': {'base_url': 'https://example.invalid/synthetic-interface'},
                   'operations': {self.target['operation']: {}}}
        self.write('services.json', {'services': {self.target['service']: service}})
        visual = copy.deepcopy(self.package['visual_continuity'])
        visual['basis'].pop('sha256')
        visual.update(production_spec='production-spec.json', prepared_reference_set='prepared-references.json')
        self.choices = {'reading': {'snapshot_id': None, 'reading_key': reading['reading_key'],
                                   'applied': reading['applied'], 'resource_applied': reading['resource_applied']},
                        'visual': visual,
                        'validation': {'mode': validation['mode'], 'model': self.package['model'],
                            'target': self.target, 'service_profiles': 'services.json',
                            'contract': validation['contract']['path'], 'evidence': validation['evidence']['path'],
                            'execution_policy': validation['execution_policy']['path']},
                        'source_run': None}
        self.write('choices.json', self.choices)

    def write(self, path, value):
        (self.root / path).write_bytes(c.encoded(value))

    def build(self):
        self.write('choices.json', self.choices)
        return inputs.build_inputs(self.root, 'task.json', 'choices.json', 'built')

    def test_visual_and_validation_are_built_from_selected_evidence(self):
        result = self.build()
        self.assertTrue(result['ok'])
        visual = c.load(self.root / result['inputs']['visual-continuity']['path'])
        validation = c.load(self.root / result['inputs']['request-validation']['path'])
        self.assertEqual(visual, self.package['visual_continuity'])
        self.assertEqual(validation, self.package['request_validation'])
        self.assertNotIn('source_sha256', str(self.choices['visual']))
        self.assertNotIn('service_execution_sha256', self.choices['validation'])
        snapshot = c.load(self.root / result['inputs']['input-snapshots']['path'])
        request_validation.require(validation, InputEvidence(None, snapshots=snapshot, live=False))

    def test_preserves_an_explicit_undecided_single_subject(self):
        subject = next(iter(self.choices['visual']['subjects'].values()))
        subject['continuity'] = 'undecided'
        subject['character_id'] = None
        result = self.build()
        visual = c.load(self.root / result['inputs']['visual-continuity']['path'])
        actual = next(iter(visual['subjects'].values()))
        self.assertEqual(actual['continuity'], 'undecided')
        self.assertIsNone(actual['character_id'])

    def test_an_unselected_subject_is_not_inferred(self):
        self.choices['visual']['subjects'] = {}
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_no_recurring_identity_is_invented_for_two_subjects(self):
        spec = copy.deepcopy(self.package['production_spec'])
        second = copy.deepcopy(spec['subjects'][0])
        second['id'] = 'synthetic-second-subject'
        spec['subjects'].append(second)
        self.write('production-spec.json', spec)
        original = next(iter(self.choices['visual']['subjects'].values()))
        self.choices['visual']['subjects'][second['id']] = dict(original, continuity='recurring', character_id='synthetic-character')
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_forged_basis_hash_is_not_silently_repaired(self):
        self.choices['visual']['basis']['sha256'] = 'a' * 64
        with self.assertRaises(ValueError):
            self.build()

    def test_validation_target_change_is_rejected(self):
        self.choices['validation']['target'] = dict(self.target, model_identifier='another-synthetic-model')
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_corrupt_schema_evidence_does_not_change_validation_mode(self):
        self.write(self.choices['validation']['evidence'], {})
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_supplied_unknowns_cannot_remove_unmeasured_conditions(self):
        self.choices['validation']['unmeasured'] = []
        with self.assertRaises(ValueError):
            self.build()

    def test_prepared_reference_integrity_is_checked(self):
        prepared = copy.deepcopy(self.package['prepared_reference_set'])
        prepared['prepared_reference_set_sha256'] = 'f' * 64
        self.write('prepared-references.json', prepared)
        with self.assertRaises(ValueError):
            self.build()

    def test_next_builder_keeps_selected_runtime_and_input_roots(self):
        from pack_manager import default_settings
        settings = default_settings(state_file=self.base / 'pack-state.json',
                                    cache_dir=self.base / 'cache',
                                    managed_root=self.base / 'managed')
        context = {'state-file': str(settings.state_file), 'cache-dir': str(settings.cache_dir),
                   'managed-root': str(settings.managed_root), 'pack-root': []}
        result = inputs.build_inputs(self.root, 'task.json', 'choices.json', 'built', runtime_arguments=context)
        action = next(item for item in result['next_actions'] if item['operation'] == 'build-generation-payload')
        self.assertEqual(action['args']['production-root'], str(self.root))
        self.assertNotIn('continuity', action['required_args'])
        for key, value in context.items():
            self.assertEqual(action['args'][key], value)
        saved = c.load(self.root / 'built/input-report.json')
        self.assertEqual(saved['next_actions'], result['next_actions'])
        self.assertFalse(result['execution_ready'])

    def test_null_choices_leave_continuity_and_validation_to_the_builder(self):
        self.choices['visual'] = None
        self.choices['validation'] = None
        result = self.build()
        self.assertEqual(sorted(result['inputs']), ['input-snapshots', 'production-task', 'route-reading'])
        action = next(item for item in result['next_actions'] if item['operation'] == 'build-generation-payload')
        self.assertEqual({key for key in action['args'] if key.endswith('-file')}, set())
        self.assertEqual(action['required_args'], ['model', 'prompt-file', 'plot-file', 'retrieval-record-file',
                                                   'production-spec-file', 'continuity', 'out'])

    def test_side_effect_entrypoints_are_not_called(self):
        import production_workflow
        with (patch.object(production_workflow, 'prepare', side_effect=AssertionError('prepare')),
              patch.object(production_workflow, 'authorize', side_effect=AssertionError('authorize'))):
            self.assertTrue(self.build()['ok'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
