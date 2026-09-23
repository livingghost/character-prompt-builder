#!/usr/bin/env python3
"""Synthetic reference-order, board-region and influence-contract checks."""
from __future__ import annotations
import copy
import unittest
import reference_delivery as d
from prepare_generation_references import canonical_reference_preamble, _validate_authority


class ReferenceDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'role': 'declared-subject', 'source': {'sha256': 'a' * 64}, 'transport': {'sha256': 'b' * 64},
                      'authority': {'controls': ['enduring shape'], 'must_not_control': ['current orientation', 'expression']}},
                     {'role': 'environment', 'source': {'sha256': 'c' * 64}, 'transport': {'sha256': 'd' * 64},
                      'authority': {'controls': ['spatial arrangement'], 'must_not_control': ['current light']}}]
        self.board = {'panels': [{'semantic_role': row['role'], 'source_sha256': row['source']['sha256'],
                                 'transport_sha256': row['transport']['sha256'],
                                 'box': {'x': i * 100, 'y': 0, 'width': 100, 'height': 100}}
                                for i, row in enumerate(self.rows)]}

    def test_multiframe_maps_to_actual_order(self):
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual([x['attachment_number'] for x in rows], [1, 2])
        reversed_rows = d.bindings('multi-image', self.rows[::-1])
        self.assertEqual(reversed_rows[0]['role'], 'environment')
        self.assertEqual(reversed_rows[0]['attachment_number'], 1)

    def test_board_regions_are_not_separate_attachments(self):
        rows = d.bindings('single-board', self.rows, self.board)
        self.assertEqual([x['attachment_number'] for x in rows], [1, 1])
        self.assertEqual(rows[1]['region_pixels']['x'], 100)
        text = d.instructions('single-board', self.rows, self.board)
        self.assertIn('There is one attached image', text)
        self.assertIn('Reference 2 means Image 1', text)
        self.assertNotIn('Image 2', text)
        self.assertIn('not the requested output layout', text)

    def test_current_state_is_explicitly_excluded(self):
        text = d.instructions('multi-image', self.rows)
        self.assertIn('Do not inherit: current orientation; expression.', text)
        self.assertIn('Do not inherit: current light.', text)

    def test_board_hash_reordering_is_refused(self):
        board = copy.deepcopy(self.board)
        board['panels'].reverse()
        with self.assertRaises(ValueError):
            d.bindings('single-board', self.rows, board)

    def test_board_role_mismatch_refused(self):
        self.board['panels'][0]['semantic_role'] = 'other'
        with self.assertRaises(ValueError):
            d.bindings('single-board', self.rows, self.board)

    def test_no_model_attachment_claim_for_prompt_only(self):
        self.assertEqual(d.instructions('prompt-artifacts', []), '')
        self.assertEqual(d.instructions('svg-bundle', []), '')
        self.assertEqual(canonical_reference_preamble(transport_mode='none', selected_references=[], reference_use_plan=None), '')

    def test_missing_board_metadata_cannot_produce_final_instructions(self):
        with self.assertRaises(ValueError):
            d.bindings('single-board', self.rows)

    def test_pixel_bool_and_negative_bounds_refused(self):
        for bad in [True, -1, 0.5]:
            board = copy.deepcopy(self.board)
            board['panels'][0]['box']['x'] = bad
            with self.assertRaises(ValueError):
                d.bindings('single-board', self.rows, board)

    def test_explicit_authority_self_conflict_refused(self):
        with self.assertRaises(ValueError):
            _validate_authority({'controls': ['Identity'], 'must_not_control': ['identity']}, 'authority')

    def test_semantic_judgment_is_not_replaced_by_keyword_matching(self):
        _validate_authority({'controls': ['left-side arrangement'], 'must_not_control': ['a different camera placement']}, 'authority')

    def test_canonical_prompt_contains_transport_map(self):
        text = canonical_reference_preamble(transport_mode='single-board', selected_references=self.rows,
                                            reference_use_plan=None, single_board=self.board)
        self.assertIn('Reference 2 means Image 1', text)
        self.assertIn('x=100, y=0, width=100, height=100', text)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    import io
    import json
    buffer = io.StringIO()
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__('sys').modules[__name__]))
    errors = [str(test) + ': ' + detail for test, detail in result.failures + result.errors]
    print(json.dumps({'ok': result.wasSuccessful(), 'checks': result.testsRun,
                      'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
                      'skipped': len(result.skipped), 'errors': errors,
                      'scope': 'constructed correctness tests; no model-quality claim',
                      'details': buffer.getvalue()}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
