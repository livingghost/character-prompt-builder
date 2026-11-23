"""Input discovery works before any Studio history or compiled request exists."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

# Load the import-bound reader before patching runtime; deferred imports must
# not retain a temporary mock after the test restores the runtime function.
import catalog_retrieval.assets as catalog_assets
import catalog_retrieval.runtime as catalog_runtime
import generation_references as references
import production_case_fixtures as fixtures
import production_fixtures
import production_input_guide as guide


class InputGuideTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        import studio_workspace as studio
        self.root = studio.init(base / 'studio', 'input-guide-test', 'Input guide fixture')
        self.path = 'work/input/choices.json'
        self.choices = {'target': None, 'reading': {'reading_key': None},
            'visual': None, 'validation': None, 'external': None, 'task_changes': {},
            'authoring': {'task': {}, 'delivery': {'file': 'work/input/prompt.txt', 'translation_notes': None},
                'documents': {'negative_provenance': {'file': 'work/input/provenance.json'}},
                'generation': {}, 'references': None, 'upscale': None, 'sources': {}, 'source_files': {}}}
        fixtures.write(self.root / self.path, self.choices)

    def test_explanation_needs_no_past_runs_or_catalog_and_does_not_repair_choices(self):
        original = (self.root / self.path).read_bytes()
        with (patch('production_operations.read_run', side_effect=AssertionError('no run is needed')),
              patch.object(catalog_runtime, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed')),
              patch.object(catalog_assets, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed')),
              patch.object(references, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed'))):
            result = guide.explain(self.root, self.path)
        self.assertFalse(result['validated'])
        fields = {row['field']: row for row in result['fields']}
        self.assertEqual(fields['target']['value_state'], 'null')
        self.assertTrue(fields['target']['required_in_draft'])
        self.assertEqual(fields['authoring.delivery']['source']['file'], 'work/input/prompt.txt')
        self.assertEqual((self.root / self.path).read_bytes(), original)
        self.assertFalse((self.root / 'production/records.sqlite3').exists())

    def test_selected_unreadable_document_still_exposes_its_owner_and_permitted_keys(self):
        fixtures.write(self.root / 'work/input/provenance.json', '{')
        result = guide.explain(self.root, self.path, field='authoring.documents.negative_provenance')
        self.assertEqual(result['source'], {'file': 'work/input/provenance.json'})
        self.assertIn('semantic_exclusions_user_supplied', result['contract']['permitted_keys'])
        self.assertIn('normalize_negative_provenance', result['contract']['validator_source'])
        self.assertFalse(result['validated'])
        self.assertEqual((self.root / 'work/input/provenance.json').read_text(encoding='utf-8'), '{')

    def test_json_field_selector_and_schema_backed_owner_remain_exact(self):
        value = copy.deepcopy(self.choices)
        value['authoring']['documents'] = {'production_spec': {'file': 'work/scene.json', 'field': ['image', 0]}}
        fixtures.write(self.root / self.path, value)
        result = guide.explain(self.root, self.path, field='authoring.documents.production_spec')
        self.assertEqual(result['source'], value['authoring']['documents']['production_spec'])
        self.assertEqual(result['contract']['schema'], 'protocols/shared-state/schemas/production-spec.schema.json')
        self.assertIn('subjects', result['contract']['permitted_keys'])
        self.assertTrue((guide.ROOT / result['example']).is_file())

    def test_task_change_display_exposes_the_exact_editable_plan_owner(self):
        import production_choice_edits as edits
        original = (self.root / self.path).read_bytes()
        parent = guide.explain(self.root, self.path, field='task_changes')['fields'][0]
        self.assertFalse(parent['editable_container'])
        self.assertIsNone(edits.editable_owner(parent['choices_pointer']))
        child = parent['child_contracts']['semantic_edit']
        field = child['explain_action']['argv'][-1]
        self.assertEqual(field, 'task_changes.semantic_edit')
        leaf = guide.explain(self.root, self.path, field=field)['fields'][0]
        self.assertEqual(leaf['choices_pointer'], '/task_changes/semantic_edit')
        self.assertEqual(edits.editable_owner(leaf['choices_pointer']), child['choices_pointer'])
        self.assertEqual(child['edit_action'], leaf['edit_action'])
        self.assertEqual(leaf['edit_action']['operation'], 'edit-choices')
        self.assertEqual(leaf['edit_action']['pointer'], leaf['choices_pointer'])
        self.assertIn('--value-file', leaf['edit_action']['required_inputs'])
        self.assertEqual(parent['task_choices_action']['argv'][-1], 'authoring.task')
        completed = subprocess.run(child['explain_action']['argv'], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', check=False, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['fields'][0], leaf)
        self.assertEqual((self.root / self.path).read_bytes(), original)
        selected = copy.deepcopy(self.choices)
        selected['task_changes']['semantic_edit'] = 'work/input/edit-plan.json'
        fixtures.write(self.root / self.path, selected)
        selected_bytes = (self.root / self.path).read_bytes()
        leaf = guide.explain(self.root, self.path, field=field)['fields'][0]
        self.assertEqual(leaf['source'], {'file': 'work/input/edit-plan.json'})
        self.assertEqual((self.root / self.path).read_bytes(), selected_bytes)
        self.assertNotEqual(selected_bytes, original)
        self.assertFalse((self.root / 'production/records.sqlite3').exists())

    def test_diagnostic_criteria_field_has_a_focused_public_action_and_exact_schema(self):
        original = (self.root / self.path).read_bytes()
        with (patch('production_operations.read_run', side_effect=AssertionError('no run is needed')),
              patch.object(catalog_runtime, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed')),
              patch.object(catalog_assets, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed')),
              patch.object(references, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed'))):
            focused = guide.explain(self.root, self.path, field='authoring.task.criteria')
            parent = guide.explain(self.root, self.path, field='authoring.task')
        self.assertFalse(focused['validated'])
        self.assertFalse(focused['external_effect'])
        row, = focused['fields']
        self.assertEqual(row['choices_pointer'], '/authoring/task/criteria')
        self.assertEqual(row['value_state'], 'absent')
        self.assertEqual(row['content_schema'], 'schemas/authoring/production-task.schema.json')
        self.assertEqual(row['schema_pointer'], '/properties/criteria')
        schema = json.loads((guide.ROOT / row['content_schema']).read_text(encoding='utf-8'))
        self.assertEqual(row['schema_fragment'], schema['properties']['criteria'])
        self.assertIn('identity_review', row['schema_fragment']['items']['properties'])
        self.assertIn('identity_bindings', row['schema_fragment']['items']['properties'])
        action = parent['fields'][0]['child_contracts']['criteria']['explain_action']
        self.assertEqual(action['argv'][action['argv'].index('--field') + 1], 'authoring.task.criteria')
        completed = subprocess.run(action['argv'], cwd=self.root, capture_output=True, text=True,
                                   encoding='utf-8', check=False, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['fields'][0], row)
        self.assertEqual((self.root / self.path).read_bytes(), original)
        self.assertFalse((self.root / 'production/records.sqlite3').exists())

    def test_explicit_authoring_explanation_rebuilds_guide_for_current_owners_only(self):
        context = self.root / 'work/input/context.json'
        fixtures.write(context, {'authoring_guide': {'source_acquisition': {
            'argv': ['old-python', '/previous-installation/scripts/production_workflow.py',
                     'acquire-source', '--root', '/previous-studio']}}})
        retained = context.read_bytes()
        original = (self.root / self.path).read_bytes()
        with (patch('production_operations.read_run', side_effect=AssertionError('no run is needed')),
              patch.object(catalog_runtime, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed')),
              patch.object(catalog_assets, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed')),
              patch.object(references, 'load_pack_catalog', side_effect=AssertionError('no catalog is needed'))):
            focused = guide.explain(self.root, self.path, field='authoring')
            catalogue = guide.explain(self.root, self.path)
            child = guide.explain(self.root, self.path, field='authoring.task')
        current = focused['authoring_guide']
        self.assertNotIn('authoring_guide', catalogue)
        self.assertNotIn('authoring_guide', child)
        self.assertFalse(focused['validated'])
        self.assertFalse(focused['external_effect'])
        for name in ('explain_action', 'source_acquisition'):
            argv = current[name]['argv']
            self.assertEqual(argv[argv.index('--root') + 1], str(self.root))
            self.assertEqual(argv[argv.index('--choices') + 1], self.path)
            self.assertIn(str(guide.ROOT / 'scripts/production_workflow.py'), argv)
        self.assertIn(str(self.root / 'work/input/work-basis.json'),
                      current['authoring_work']['context_argv'])
        action = guide.action(self.root, self.path, field='authoring')
        completed = subprocess.run(action['argv'], cwd=self.root, capture_output=True, text=True,
                                   encoding='utf-8', check=False, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['authoring_guide'], current)
        self.assertEqual(context.read_bytes(), retained)
        self.assertEqual((self.root / self.path).read_bytes(), original)
        self.assertFalse((self.root / 'production/records.sqlite3').exists())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
