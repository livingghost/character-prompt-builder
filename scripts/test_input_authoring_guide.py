"""Input discovery works before any Studio history or compiled request exists."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import production_case_fixtures as fixtures
import production_fixtures
import production_input_guide as guide


class InputGuideTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        import studio
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
        with (patch('production_workflow.read_run', side_effect=AssertionError('no run is needed')),
              patch('catalog_retrieval.runtime.load_pack_catalog', side_effect=AssertionError('no catalog is needed'))):
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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
