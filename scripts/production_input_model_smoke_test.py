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
import request_validation


class ModelInputTests(unittest.TestCase):
    def setUp(self):
        fixtures.PackageIntegrationTests.setUp(self)
        # Reuse the task/reading actually committed by the package fixture.
        # A new reading locator would be a new task, not the prepared basis.
        self.assertEqual(self.spec['route'], 'generation')
        self.assertEqual(self.spec['artifact'], 'image')
        reading = c.load(self.root / self.spec['route_reading'])
        self.write('production-spec.json', self.package['production_spec'])
        self.write('prepared-references.json', self.package['prepared_reference_set'])
        validation = self.package['request_validation']
        self.target = validation['target']
        from catalog_retrieval.runtime import load_pack_catalog
        service_source = load_pack_catalog().resources['service-profiles'].path
        service = c.load(Path(service_source))['services'][self.target['service']]
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

    def test_next_prepare_keeps_selected_runtime_and_names_built_inputs(self):
        from pack_manager import default_settings
        settings = default_settings(state_file=self.base / 'pack-state.json',
                                    cache_dir=self.base / 'cache',
                                    managed_root=self.base / 'managed')
        context = {'state-file': str(settings.state_file), 'cache-dir': str(settings.cache_dir),
                   'managed-root': str(settings.managed_root), 'pack-root': []}
        result = inputs.build_inputs(self.root, 'task.json', 'choices.json', 'built', runtime_arguments=context)
        self.assertEqual([item['operation'] for item in result['next_actions']], ['prepare', 'draft-execution', 'execute'])
        action = result['next_actions'][0]
        self.assertEqual(action['args']['root'], str(self.root))
        for key, value in context.items():
            self.assertEqual(action['args'][key], value)
        self.assertIn("Name built/visual-continuity.json as the task's generation.visual_continuity.", action['requires'])
        self.assertIn("Name built/request-validation.json as the task's generation.request_validation.", action['requires'])
        saved = c.load(self.root / 'built/input-report.json')
        self.assertEqual(saved['next_actions'], result['next_actions'])
        self.assertFalse(result['execution_ready'])

    def test_null_choices_leave_continuity_and_validation_to_prepare(self):
        self.choices['visual'] = None
        self.choices['validation'] = None
        result = self.build()
        self.assertEqual(sorted(result['inputs']), ['input-snapshots', 'production-task', 'route-reading'])
        action = result['next_actions'][0]
        self.assertEqual(action['operation'], 'prepare')
        self.assertEqual(action['requires'], ['Complete the declared delivery, source and authority files.'])

    def test_side_effect_entrypoints_are_not_called(self):
        import production_workflow
        with (patch.object(production_workflow, 'prepare', side_effect=AssertionError('prepare')),
              patch.object(production_workflow, 'authorize', side_effect=AssertionError('authorize'))):
            self.assertTrue(self.build()['ok'])


class ObservedPackInputTests(unittest.TestCase):
    """The public input command resolves observed schemas through active pack selectors."""

    def setUp(self):
        import tempfile
        import production_case_fixtures as cases
        import production_fixtures
        import pack_manager
        from catalog_retrieval import runtime
        from catalog_retrieval.retrieval import inspect_record
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.enterContext(production_fixtures.scratch_home(self.base / 'home'))
        self.case = cases.create(self.base / 'studio', self.base / 'runtime')
        self.root = self.case['root']
        self.addCleanup(runtime.configure_pack_runtime, None)
        self.schema_relative = 'resources/model-schemas/example-editor.json'
        document = c.load(self.case['pack'] / 'records/models.json')
        offering = document['records'][0]['offerings'][0]
        offering['schema_snapshot'] = self.schema_relative
        self.snapshot = {'artifact_type': 'observed-parameter-schema', 'model_id': cases.MODEL_ID,
            'service': offering['service'], 'model_identifier': offering['model_identifier'],
            'observed_at': offering['observed_at'], 'source': 'Synthetic observed-schema fixture; no provider contacted.',
            'schema': {'type': 'object', 'properties': {'model': {'const': offering['model_identifier']},
                                                      'count': {'type': 'integer', 'minimum': 1, 'maximum': 4}}}}
        cases.write(self.case['pack'] / 'records/models.json', document)
        cases.write(self.case['pack'] / self.schema_relative, self.snapshot)
        cases.write(self.case['pack'] / 'resources/model-schemas/duplicate.json', self.snapshot)
        pack_manager.write_lock(self.case['pack'])
        runtime.configure_pack_runtime(self.case['settings'])
        inspected = inspect_record(runtime.load_entries(), cases.MODEL_ID)
        selected = inspected['record']['offerings'][0]
        self.selector = '@pack/' + inspected['source_pack'] + '/' + selected['schema_snapshot']
        self.target = {'service': selected['service'], 'model_identifier': selected['model_identifier'], 'operation': 'generate'}
        reading = c.load(self.root / self.case['task']['route_reading'])
        policy = c.load(self.root / 'validation.json')['execution_policy']['path']
        self.choices = {'reading': {'snapshot_id': None, 'reading_key': reading['reading_key'],
                                   'applied': reading['applied'], 'resource_applied': reading['resource_applied']},
                        'visual': None, 'source_run': None,
                        'validation': {'mode': 'target-schema', 'model': cases.MODEL_ID, 'target': self.target,
                            'service_profiles': None, 'contract': self.selector, 'evidence': self.selector,
                            'execution_policy': policy}}
        self.original_task = (self.root / 'task.json').read_bytes()

    def cli(self, destination='built'):
        import json
        import subprocess
        import sys
        from pack_runtime_cli import PackRuntimeContext
        (self.root / 'choices.json').write_bytes(c.encoded(self.choices))
        command = [sys.executable, '-B', str(Path(__file__).with_name('production_workflow.py')),
            'build-inputs', '--root', str(self.root), '--task', 'task.json', '--choices', 'choices.json',
            '--out-dir', destination]
        command += PackRuntimeContext(self.case['settings'], (self.case['pack'],)).command_arguments()
        process = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, encoding='utf-8', timeout=60)
        result = json.loads(process.stdout)
        self.assertEqual((self.root / 'task.json').read_bytes(), self.original_task)
        return process.returncode, result

    def test_public_build_inputs_selects_and_snapshots_active_pack_observation(self):
        import shutil
        code, result = self.cli()
        self.assertEqual(code, 0, result)
        self.assertTrue(result['ok'])
        self.assertFalse(result['execution_ready'])
        record = c.load(self.root / result['inputs']['request-validation']['path'])
        self.assertEqual(record['contract'], record['evidence'])
        self.assertEqual(record['contract'], {'path': self.selector,
            'sha256': c.sha256_file(self.case['pack'] / self.schema_relative)})
        snapshots = c.load(self.root / result['inputs']['input-snapshots']['path'])
        self.assertIn(self.selector, snapshots)
        shutil.rmtree(self.case['pack'])
        request_validation.require(record, InputEvidence(None, snapshots=snapshots, live=False),
                                   expected_target=self.target)

    def test_public_selectors_reject_objects_absolute_paths_escape_and_inactive_roots(self):
        choices = copy.deepcopy(self.choices)
        invalid = [({'path': self.selector}, 'object'),
                   (str(self.case['pack'] / self.schema_relative), 'absolute'),
                   (self.selector.replace('/resources/', '/../resources/'), 'escape'),
                   ('@pack/019a0290-1234-789a-8123-0123456789ac/' + self.schema_relative, 'inactive')]
        for selector, name in invalid:
            self.choices = copy.deepcopy(choices)
            self.choices['validation'].update(contract=selector, evidence=selector)
            with self.subTest(name=name):
                code, result = self.cli(name)
                self.assertNotEqual(code, 0, result)
                self.assertFalse((self.root / name).exists())

    def test_public_observation_keeps_one_pack_owner_and_raw_schema_needs_acquisition(self):
        (self.root / 'copied-observation.json').write_bytes(c.encoded(self.snapshot))
        (self.root / 'raw-schema.json').write_bytes(c.encoded(self.snapshot['schema']))
        original = copy.deepcopy(self.choices)
        cases = [('copied-observation.json', 'copied-observation.json', 'active pack'),
                 (self.selector, self.selector.replace('example-editor.json', 'duplicate.json'), 'own evidence'),
                 ('raw-schema.json', 'raw-schema.json', 'target schema contract')]
        for index, (contract, evidence, message) in enumerate(cases):
            self.choices = copy.deepcopy(original)
            self.choices['validation'].update(contract=contract, evidence=evidence)
            destination = 'refused-' + str(index)
            with self.subTest(contract=contract, evidence=evidence):
                code, result = self.cli(destination)
                self.assertNotEqual(code, 0, result)
                self.assertIn(message, str(result))
                self.assertFalse((self.root / destination).exists())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
