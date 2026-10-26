#!/usr/bin/env python3
"""Final wire-text checks with an isolated, explicitly authored synthetic tag pack."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import pack_manager as packs
import production_case_fixtures as fixture
import production_workflow as workflow
import prompt_retrieval
from catalog_retrieval import runtime


class TagPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        with patch.object(fixture, 'PROMPT', 'plain backdrop, collar'):
            self.case = fixture.create(base / 'studio', base / 'runtime')
        self.root, self.pack = self.case['root'], self.case['pack']
        manifest = c.load(self.pack / 'pack.json')
        manifest['content']['resource_bindings'].update({
            'prompt-vocabulary': 'resources/dictionary.json', 'prompt-dialects': 'resources/dialects.json'})
        fixture.write(self.pack / 'pack.json', manifest)
        fixture.write(self.pack / 'resources/dictionary.json', {
            'format': 'character-prompt-builder-prompt-vocabulary', 'name': 'Synthetic terms',
            'description': 'Fixture meanings, not provider vocabulary.',
            'categories': [{'id': 'synthetic', 'name': 'Fixture terms', 'description': 'Authored test meanings.',
                           'entries': [{'term': 'plain backdrop'}, {'term': 'collar',
                                'description': 'A garment around a neck, not a biological surface.',
                                'usage_notes': ['Inspect the intended garment meaning.']}]}]})
        fixture.write(self.pack / 'resources/dialects.json', {
            'format': 'character-prompt-builder-prompt-dialects', 'name': 'Synthetic dialects',
            'description': 'A test-only tag grammar.', 'dialects': [{'id': 'synthetic-tags',
                'name': 'Synthetic tags', 'description': 'No external checkpoint claims.',
                'tag_separator': 'comma', 'block_order': ['subject', 'environment']}]})
        models = c.load(self.pack / 'records/models.json')
        models['records'][0]['prompt_dialect'] = 'synthetic-tags'
        fixture.write(self.pack / 'records/models.json', models)
        self.refresh()

    def refresh(self):
        packs.write_lock(self.pack)
        runtime.configure_pack_runtime(self.case['settings'])
        record = c.load(self.root / 'retrieval.json')
        record['pack_state'] = runtime.load_pack_catalog().fingerprint
        prompt = (self.root / 'prompt.txt').read_text(encoding='utf-8')
        record = prompt_retrieval.settle_retrieval_record(record, prompt=prompt, plot=c.load(self.root / 'plot.json'))
        fixture.write(self.root / 'retrieval.json', record)
        from request_validation_fixtures import fixture_validation
        fixture.write(self.root / 'validation.json', fixture_validation(self.root, fixture.MODEL_ID, reference_mode='authored-rendition', service='synthetic'))
        from reading_fixtures import fixture_reading
        fixture.write(self.root / 'reading.json', fixture_reading(route='generation', studio=self.root,
                      ledger=self.root / 'work/reads.jsonl', dialect='synthetic-tags'))

    def test_final_request_has_dictionary_meaning_and_resource_hashes(self):
        result = workflow.prepare(self.root, 'task.json')
        report = result['execution_plan']['prompt_check']
        self.assertEqual(report['state'], 'checked')
        self.assertEqual(report['request_sha256'], result['execution_plan']['request_sha256'])
        meanings = {row['authored_term']: row for row in report['meanings']}
        self.assertIn('garment', meanings['collar']['description'])
        self.assertEqual(len(report['dictionary']['sha256']), 64)
        self.assertEqual(meanings['collar']['usage_notes'], ['Inspect the intended garment meaning.'])

    def test_unlisted_term_is_visible_but_does_not_block_preparation(self):
        data = c.load(self.pack / 'resources/dictionary.json')
        data['categories'][0]['entries'].pop()
        fixture.write(self.pack / 'resources/dictionary.json', data); self.refresh()
        result = workflow.prepare(self.root, 'task.json')
        report = result['execution_plan']['prompt_check']
        self.assertIn({'channel': 'positive', 'clause': 0, 'term': 'collar'}, report['unmatched_terms'])
        self.assertEqual(report['findings'], [])

    def test_model_recommended_negative_reaches_the_exact_channel_check(self):
        models = c.load(self.pack / 'records/models.json')
        models['records'][0].update(recommended_negative_prompt='plain backdrop', recommendation_merge_mode='tag-list')
        fixture.write(self.pack / 'records/models.json', models); self.refresh()
        task = c.load(self.root / 'task.json')
        task['generation']['critical_avoidance_integrated'] = True
        fixture.write(self.root / 'task.json', task)
        result = workflow.prepare(self.root, 'task.json')
        report = result['execution_plan']['prompt_check']
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['channels']['negative']['clauses'][0]['tags'][0]['text'], 'plain backdrop')
        self.assertTrue(any(row['channel'] == 'negative' and row['authored_term'] == 'plain backdrop'
                            for row in report['meanings']))

    def test_changed_dictionary_invalidates_prepared_request(self):
        run = workflow.prepare(self.root, 'task.json')['run']
        data = c.load(self.pack / 'resources/dictionary.json')
        data['categories'][0]['entries'][1]['description'] = 'A changed fixture meaning.'
        fixture.write(self.pack / 'resources/dictionary.json', data); self.refresh()
        with self.assertRaises(ValueError): workflow.assert_current(self.root, run)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
