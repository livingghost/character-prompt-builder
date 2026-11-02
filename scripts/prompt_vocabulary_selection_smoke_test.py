#!/usr/bin/env python3
"""Exercise real vocabulary searches and choices with fictional local resources."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_prompt_input_fixtures import prompt_input
import prompt_vocabulary_selection as selection


class VocabularySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dictionary_path = self.root / 'dictionary.json'
        self.dialect_path = self.root / 'dialects.json'
        self.dictionary = {
            'format': 'character-prompt-builder-prompt-vocabulary',
            'name': 'Synthetic material vocabulary',
            'description': 'Fictional local vocabulary for search-contract tests.',
            'categories': [{
                'id': 'surface', 'name': 'Surface construction',
                'description': 'Material shape and texture, not camera direction.',
                'entries': [
                    {'term': 'ribbed glass', 'aliases': ['fluted glass'],
                     'description': 'Glass with repeated narrow raised ribs or grooves.'},
                    {'term': 'striped fabric', 'aliases': ['striped cloth', 'banded fabric'],
                     'description': 'Fabric carrying repeated bands of color.'},
                    {'term': 'text', 'description': 'Visible written text.'},
                    {'term': 'watermark', 'description': 'An identifying overlay.'},
                ],
            }],
        }
        self.dialects = {
            'format': 'character-prompt-builder-prompt-dialects',
            'name': 'Synthetic dialects',
            'description': 'Independent fictional model-control vocabularies.',
            'dialects': [
                {'id': 'fixture-alpha', 'name': 'Alpha', 'description': 'First synthetic family.',
                 'vocabularies': ['fixture-vocabulary'], 'tag_separator': 'comma and space',
                 'block_order': ['content', 'optional controls'],
                 'quality_terms': ['grade_alpha'], 'dataset_terms': ['dataset_alpha'],
                 'meta_terms': ['metadata_alpha']},
                {'id': 'fixture-beta', 'name': 'Beta', 'description': 'Second synthetic family.',
                 'vocabularies': ['fixture-vocabulary'], 'tag_separator': 'comma and space',
                 'block_order': ['content', 'optional controls'],
                 'quality_terms': ['grade_beta']},
            ],
        }
        self.write(self.dictionary_path, self.dictionary)
        self.write(self.dialect_path, self.dialects)
        self.model = {
            'id': 'synthetic-material-model',
            'prompt_input': prompt_input('tag-based', vocabularies=('fixture-vocabulary',),
                                        forms=('tags', 'natural-language')),
            'prompt_dialect': 'fixture-alpha',
        }

    def write(self, path, value):
        path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

    def arguments(self, **changes):
        value = {'prompt': 'fluted glass', 'negative': 'text', 'model_record': self.model,
                 'syntax': 'literal', 'dictionary_path': self.dictionary_path,
                 'dialect_path': self.dialect_path}
        value.update(changes)
        return value

    def search(self, **changes):
        return selection.search_selection(**self.arguments(**changes))

    def require(self, receipt, **changes):
        return selection.require_selection(receipt, **self.arguments(**changes))

    def test_absent_receipt_still_runs_real_search_and_returns_candidates(self):
        original = selection.VocabularyIndex.search
        queries = []
        def search(index, query, **kwargs):
            queries.append(query)
            return original(index, query, **kwargs)
        with patch.object(selection.VocabularyIndex, 'search', new=search):
            with self.assertRaisesRegex(ValueError, 'searched vocabulary selection') as raised:
                self.require(None)
        self.assertEqual(queries, ['fluted glass', 'text'])
        report = raised.exception.vocabulary_search
        candidates = report['entries'][0]['searches'][0]['candidates']
        self.assertTrue(any(row['term'] == 'ribbed glass' for row in candidates))
        self.assertTrue(candidates[0]['definitions'])

    def test_alias_keeps_canonical_meaning_and_complete_category_guidance(self):
        receipt = self.search()
        self.assertEqual(receipt['unresolved'], [])
        meaning = receipt['entries'][0]['choice']['definitions'][0]
        self.assertEqual(meaning['entry']['term'], 'ribbed glass')
        self.assertEqual(meaning['entry']['aliases'], ['fluted glass'])
        self.assertIn('not camera direction', meaning['category_definition']['description'])
        self.assertEqual(self.require(receipt), receipt)

    def test_near_synonym_finds_existing_word_without_inventing_a_semantic_choice(self):
        receipt = self.search(prompt='grooved glass')
        entry = receipt['entries'][0]
        self.assertIsNone(entry['choice'])
        self.assertIn('ribbed glass', [row['term'] for row in entry['searches'][0]['candidates']])
        self.assertEqual(receipt['unresolved'], [entry['id']])
        with self.assertRaisesRegex(ValueError, 'choose an existing term'):
            self.require(receipt, prompt='grooved glass')

    def test_authored_phrase_preserves_needed_meaning_after_additional_search(self):
        prompt = 'three interleaved blue fabric bands'
        receipt = self.search(prompt=prompt)
        chosen = selection.resolve_authored(receipt, prompt,
            'The existing surface terms omit the specified count, color and interleaved arrangement.',
            queries=['striped fabric'])
        with self.assertRaisesRegex(ValueError, 'evidence is incomplete or changed'):
            self.require(chosen, prompt=prompt)
        searched = self.search(prompt=prompt, previous=chosen)
        entry = searched['entries'][0]
        self.assertEqual([row['query'] for row in entry['searches']], [prompt, 'striped fabric'])
        self.assertEqual(entry['choice']['kind'], 'authored')
        self.assertTrue(entry['searches'][1]['candidates'])
        self.assertEqual(self.require(searched, prompt=prompt), searched)

    def test_authored_choice_requires_a_reason_and_an_actual_prior_search(self):
        receipt = self.search(prompt='three interleaved blue fabric bands')
        for reason in ('', '  '):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, 'authored vocabulary needs a reason'):
                selection.resolve_authored(receipt, receipt['entries'][0]['id'], reason)
        changed = copy.deepcopy(receipt)
        changed['entries'][0]['searches'] = []
        with self.assertRaisesRegex(ValueError, 'search the vocabulary'):
            selection.resolve_authored(changed, changed['entries'][0]['id'], 'The phrase supplies the missing arrangement.')

    def test_exact_receipt_binds_text_model_contract_and_syntax(self):
        receipt = self.search()
        other_model = copy.deepcopy(self.model)
        other_model['id'] = 'another-synthetic-model'
        other_contract = copy.deepcopy(self.model)
        other_contract['prompt_input']['notes'] = ['A separately authored input choice.']
        other_dialect = copy.deepcopy(self.model)
        other_dialect['prompt_dialect'] = 'fixture-beta'
        changes = [
            {'prompt': 'ribbed glass'}, {'negative': 'watermark'},
            {'model_record': other_model}, {'model_record': other_contract},
            {'model_record': other_dialect}, {'syntax': 'sdEmbeds'},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'different text, model, syntax or dictionary'):
                self.require(receipt, **change)

    def test_dictionary_and_selected_dialect_changes_invalidate_exact_receipt(self):
        receipt = self.search()
        changed = copy.deepcopy(self.dictionary)
        changed['categories'][0]['entries'][0]['description'] = 'A revised definition with a narrower material scope.'
        self.write(self.dictionary_path, changed)
        with self.assertRaisesRegex(ValueError, 'different text, model, syntax or dictionary'):
            self.require(receipt)
        self.write(self.dictionary_path, self.dictionary)
        changed = copy.deepcopy(self.dialects)
        changed['dialects'][0]['quality_terms'].append('grade_alpha_new')
        self.write(self.dialect_path, changed)
        with self.assertRaisesRegex(ValueError, 'different text, model, syntax or dictionary'):
            self.require(receipt)

    def test_only_selected_family_controls_join_the_dictionary(self):
        receipt = self.search(prompt='grade_alpha, dataset_alpha, metadata_alpha, grade_beta')
        choices = {row['term']: row['choice'] for row in receipt['entries']}
        for term in ('grade alpha', 'dataset alpha', 'metadata alpha'):
            self.assertEqual(choices[term]['kind'], 'dictionary')
        self.assertIsNone(choices['grade beta'])
        self.assertEqual(len(receipt['unresolved']), 1)

    def test_final_wire_search_accepts_known_recommendation_terms(self):
        receipt = self.search()
        final_text = 'grade_alpha, fluted glass'
        with self.assertRaisesRegex(ValueError, 'different text, model, syntax or dictionary'):
            self.require(receipt, prompt=final_text)
        final = selection.require_final_selection(receipt, **self.arguments(prompt=final_text))
        self.assertEqual(final['unresolved'], [])
        self.assertIn('grade alpha', [row['term'] for row in final['entries']])

    def test_unknown_injected_recommendation_cannot_reuse_an_unrelated_authored_choice(self):
        prompt = 'three interleaved blue fabric bands'
        receipt = selection.resolve_authored(self.search(prompt=prompt), prompt,
            'This specific arrangement is not carried by the available surface terms.')
        with self.assertRaisesRegex(ValueError, 'adds wording needing vocabulary selection') as raised:
            selection.require_final_selection(receipt,
                **self.arguments(prompt=prompt + ', luminous crystal haze'))
        current = raised.exception.vocabulary_search
        choices = {row['term']: row['choice'] for row in current['entries']}
        self.assertEqual(choices[prompt]['kind'], 'authored')
        self.assertIsNone(choices['luminous crystal haze'])

    def test_final_wire_selection_keeps_model_dictionary_and_grammar_binding(self):
        receipt = self.search()
        other_model = copy.deepcopy(self.model)
        other_model['id'] = 'another-synthetic-model'
        for change in ({'model_record': other_model}, {'syntax': 'compel'}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'does not match the selected model'):
                selection.require_final_selection(receipt, **self.arguments(**change))

    def test_changed_candidate_evidence_is_recomputed_instead_of_trusted(self):
        receipt = self.search()
        receipt['entries'][0]['searches'][0]['candidates'] = []
        with self.assertRaisesRegex(ValueError, 'evidence is incomplete or changed'):
            self.require(receipt)

    def test_descriptive_input_has_no_lookup_and_unresolved_input_is_not_relabelled(self):
        with patch.object(selection, 'search_selection', side_effect=AssertionError('unexpected dictionary search')):
            descriptive = {'id': 'synthetic-description', 'prompt_input': prompt_input('descriptive')}
            self.assertIsNone(selection.require_for_model({}, prompt='A fluted vase on a shelf.', negative='',
                                                         model_record=descriptive))
            for mode in ('unresolved', 'none'):
                target = {'id': 'synthetic-' + mode, 'prompt_input': prompt_input(mode)}
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'resolve|no text prompt'):
                    selection.require_for_model({}, prompt='A vase.', negative='', model_record=target)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
