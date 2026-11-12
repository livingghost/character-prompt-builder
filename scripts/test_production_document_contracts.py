"""Source-backed document discovery and the actual local authoring validators."""
from __future__ import annotations

import contextlib
import copy
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import production_document_contracts as contracts

ROOT = Path(__file__).resolve().parents[1]


class DocumentContractsTests(unittest.TestCase):
    def test_every_editable_document_has_real_guidance_and_a_validation_owner(self):
        import production_authoring
        self.assertEqual(contracts.DOCUMENT_KEYS, production_authoring.DOCUMENTS)
        for name in sorted(contracts.CONTRACT_KEYS):
            with self.subTest(document=name):
                entry = contracts.metadata(name)
                self.assertTrue((ROOT / entry['document_path'].split('#')[0]).is_file())
                if entry['schema']:
                    self.assertTrue((ROOT / entry['schema']).is_file())
                for example in entry['example_paths']:
                    self.assertTrue((ROOT / example).is_file(), example)
                source, function = entry['validator_source'].split(':')
                module = importlib.import_module(Path(source).stem)
                self.assertTrue(callable(getattr(module, function)))
                self.assertIn('python scripts/', entry['validation_command'])

    def test_schema_field_discovery_preserves_exact_nested_requirements(self):
        spec = contracts.metadata('production_spec')
        shape = contracts.schema_fragment('production_spec', '/properties/subjects/items')
        nested = next(row for row in spec['structure']
                      if row['schema_pointer'] == '#/properties/subjects/items')
        self.assertEqual(nested['required_keys'], shape['required'])
        self.assertEqual(nested['permitted_keys'], sorted(shape['properties']))
        self.assertEqual(shape['properties']['domain']['enum'],
                         ['human', 'anthropomorphic-animal', 'animal', 'creature', 'hybrid', 'robot'])
        self.assertEqual(shape['properties']['performance']['$ref'], 'performance-language.schema.json')

    def test_negative_provenance_uses_the_generation_owner_and_complete_key_diagnostic(self):
        from build_generation_payload import NEGATIVE_PROVENANCE_FIELDS, normalize_negative_provenance
        content = {'semantic_exclusions_user_supplied': ['輪郭']}
        report = contracts.validate_document('negative_provenance', content)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['normalized'], normalize_negative_provenance(content))
        invalid = {**content, 'artifact_type': 'negative-provenance'}
        refused = contracts.validate_document('negative_provenance', invalid)
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['permitted_keys'], sorted(NEGATIVE_PROVENANCE_FIELDS))
        self.assertIn('normalize_negative_provenance', refused['guidance']['validator_source'])
        for name in NEGATIVE_PROVENANCE_FIELDS:
            self.assertIn(name, refused['errors'][0])

    def test_standalone_file_validation_reports_the_selected_file_and_same_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'negative.json'
            path.write_text('{"activated_sources":"wrong type"}', encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = contracts.main(['validate', 'negative_provenance', str(path)])
            report = json.loads(output.getvalue())
            self.assertEqual(status, 2)
            self.assertEqual(report['file'], str(path))
            self.assertIn('must be a list', report['errors'][0])
            self.assertIn('explain negative_provenance', report['required_action'])

    def test_schema_errors_show_all_permitted_properties_and_canonical_source(self):
        from production_spec import validate
        value = json.loads((ROOT / 'templates/production-spec-template.json').read_text(encoding='utf-8'))
        value['extra_note'] = 'A mistaken root key'
        report = validate(value)
        error = next(row for row in report['errors'] if 'unexpected properties' in row)
        self.assertEqual(report['schema'], contracts.metadata('production_spec')['schema'])
        for key in contracts.metadata('production_spec')['permitted_keys']:
            self.assertIn(repr(key), error)

    def test_editable_specification_keeps_all_checks_with_target_owned_by_choices(self):
        import production_spec
        value = production_spec.draft(model='synthetic-model', brief='A robot carries a toolbox.',
            subject='robot', kind='robot',
            render_intent={'artifact_type': 'render-intent', 'execution_mode': 'text-to-image'})
        del value['target_model']
        local = contracts.validate_document('production_spec', value)
        self.assertTrue(local['ok'], local)
        self.assertNotIn('target_model', value)
        self.assertFalse(production_spec.validate(value, require_content=True)['ok'])
        owner = contracts.metadata('production_spec')
        self.assertNotIn('target_model', owner['required_keys'])
        self.assertIn('target_model', owner['published_required_keys'])
        self.assertIn('$.target_model', owner['derived_fields'])
        value['target_model'] = None
        self.assertFalse(contracts.validate_document('production_spec', value)['ok'])
        del value['target_model']
        value['subjects'].append(copy.deepcopy(value['subjects'][0]))
        refused = contracts.validate_document('production_spec', value)
        self.assertFalse(refused['ok'])
        self.assertTrue(any('duplicate subject id' in error for error in refused['errors']))

    def test_execution_decisions_validate_shape_without_a_task_or_execution(self):
        value = {'run': 'synthetic-run', 'input_sha256': 'a' * 64,
                 'request_sha256': 'b' * 64,
                 'decisions': [{'operation': 'direction', 'grant': None, 'reason': '',
                                'stop_assessments': []}]}
        report = contracts.validate_document('execution_decisions', value)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['validation_scope'], 'document-shape')
        self.assertIn('current grants', report['remaining_checks'])
        command = contracts.metadata('execution_decisions')['validation_command']
        self.assertIn('validate execution_decisions FILE', command)
        self.assertNotIn('check --choices', command)
        value['decisions'][0]['unknown'] = True
        self.assertFalse(contracts.validate_document('execution_decisions', value)['ok'])

    def test_authored_plot_validates_its_fields_without_manual_approval_hashes(self):
        plot = {'artifact_type': 'prompt-plot',
                'story': [{'id': 'shown', 'beat': 'A lamp rests beside the window.', 'visibility': 'visible'}],
                'derived': [{'kind': 'shows', 'statement': 'The lamp beside the window.', 'from': ['shown']}],
                'approved': {'by': 'synthetic-author', 'at': '2000-01-01T00:00:00Z'}}
        report = contracts.validate_document('plot', plot)
        self.assertTrue(report['ok'], report)
        self.assertNotIn('content_sha256', plot['approved'])
        self.assertIn('prior approval', report['remaining_checks'])
        wrong = copy.deepcopy(plot)
        wrong['approved']['content_sha256'] = '0' * 64
        refused = contracts.validate_document('plot', wrong)
        self.assertFalse(refused['ok'])
        self.assertTrue(any('does not match' in error for error in refused['errors']))

    def test_selected_state_document_cannot_validate_as_another_artifact_kind(self):
        value = json.loads((ROOT / 'examples/protocol-exchange/fixtures/state-lineage.json').read_text(encoding='utf-8'))
        report = contracts.validate_document('state_snapshot', value)
        self.assertFalse(report['ok'], report)
        self.assertTrue(any('artifact_type' in error and 'state-snapshot' in error for error in report['errors']))

    def test_contextual_documents_keep_the_current_full_task_gate(self):
        report = contracts.validate_document('parameters', {'invented_parameter': 7})
        self.assertFalse(report['ok'])
        self.assertEqual(report['validation_scope'], 'task-context')
        self.assertIn('check --root STUDIO --choices CHOICES', report['required_action'])
        visual = contracts.metadata('visual_continuity')
        self.assertIn('$.basis.sha256', visual['derived_fields'])
        self.assertIn('published schema', visual['remaining_checks'])

    def test_scene_plot_points_to_its_actual_logical_contract(self):
        import scene_plot
        report = scene_plot.validate_scene_plot({'unexpected': True})
        self.assertEqual(report['guidance'], contracts.guidance('scene_plot'))
        message = next(row for row in report['errors'] if 'unknown keys' in row)
        for key in scene_plot.ROOT_KEYS:
            self.assertIn(repr(key), message)
        self.assertIsNone(contracts.metadata('scene_plot')['schema'])

    def test_reference_use_and_identity_inventory_have_distinct_documented_ids(self):
        import production_identity
        task = {'artifact': 'image', 'sources': [], 'recording': {'subject_map': {'A': 'keeper'}}}
        inputs = {'references': [{'id': 'keeper-face', 'file': 'original.png', 'role': 'identity',
                                  'use_for': ['identity'], 'do_not_transfer': [],
                                  'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}]}
        view = production_identity.context(task, lambda _: b'synthetic reference bytes', inputs=inputs)
        self.assertEqual(view['references'][0]['id'], 'keeper-face')
        self.assertEqual(view['identity_sources'][0]['id'], 'reference:keeper-face')
        self.assertEqual(production_identity.reference_id({'reference_id': 'use-a',
                         'source': {'reference_id': 'original'}}), 'use-a')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
