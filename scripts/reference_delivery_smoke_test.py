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

    def test_state_subject_survives_without_optional_use_priorities(self):
        from model_rendition import _reference_prefix, validate_bindings
        self.rows[0]['subject_id'] = 'A'
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual(rows[0]['subject_id'], 'A')
        validate_bindings(rows)
        text = _reference_prefix(rows, 'reference-delivery')
        self.assertIn('Apply this reference only to subject A.', text)
        self.assertNotIn('priority', text)

    def test_identity_review_uses_the_appended_subject_scope(self):
        from visual_continuity import _identity_scope
        pack = {'kind': 'pack-artifact', 'sha256': 'a' * 64}
        studio = {'kind': 'studio-artifact', 'sha256': 'b' * 64}
        prepared = {'reference_use_plan': {'reference_items': [{'source': pack, 'intended_influence': 'identity'}]},
            'selected_references': [
                {'source': pack, 'role': 'identity', 'subject_id': 'A', 'intended_influence': ['identity']},
                {'source': studio, 'role': 'accepted-face',
                 'subject_uses': [{'subject_id': 'B', 'use': 'identity', 'priority': 0}]}]}
        self.assertEqual(_identity_scope(prepared, 2, 'B')['source'], studio)
        with self.assertRaisesRegex(ValueError, 'does not carry identity influence'):
            _identity_scope(prepared, 2, 'A')
        prepared['selected_references'][1]['role'] = 'identity'
        prepared['selected_references'][1]['subject_uses'][0]['use'] = 'outfit'
        with self.assertRaisesRegex(ValueError, 'does not carry identity influence'):
            _identity_scope(prepared, 2, 'B')

    def test_external_named_field_keeps_the_same_scope_without_image_numbers(self):
        rows = d.bindings('multi-image', self.rows)
        rows[0]['request_field'] = ['source_image']
        rows[1]['request_field'] = ['references', 0, 'url']
        rows[0]['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]
        text = d.binding_instructions(rows)
        self.assertIn('Reference 1 means request field ["source_image"].', text)
        self.assertIn('Reference 2 means request field ["references",0,"url"].', text)
        self.assertIn('subject A, identity', text)
        self.assertIn('Do not inherit: current orientation; expression.', text)
        self.assertNotIn('Image 1', text)
        self.assertNotIn('Image 2', text)

    def test_external_location_rejects_unresolved_paths(self):
        rows = d.bindings('multi-image', self.rows)
        for path in ([], [''], [True], [-1], ['image', {}]):
            rows[0]['request_field'] = path
            with self.assertRaisesRegex(ValueError, 'JSON field path'):
                d.binding_instructions(rows)

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

    def test_one_attachment_retains_two_logical_sources_and_uses(self):
        self.rows[1]['transport'] = copy.deepcopy(self.rows[0]['transport'])
        self.rows[0]['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]
        self.rows[1]['subject_uses'] = [{'subject_id': 'B', 'use': 'outfit', 'priority': 1}]
        original = copy.deepcopy(self.rows)
        bindings = d.bindings('multi-image', self.rows)
        self.assertEqual([row['attachment_number'] for row in bindings], [1, 1])
        self.assertEqual([row['reference_number'] for row in bindings], [1, 2])
        self.assertEqual(d.delivered_reference_count({'transport_mode': 'multi-image', 'selected_references': self.rows}), 1)
        self.assertNotEqual(self.rows[0]['source'], self.rows[1]['source'])
        self.assertEqual(self.rows, original)
        text = d.instructions('multi-image', self.rows)
        self.assertIn('subject A, identity', text)
        self.assertIn('subject B, outfit', text)
        self.assertNotIn('Image 2', text)

    def test_priority_compares_only_the_same_subject_and_use(self):
        self.rows[0]['subject_uses'] = [
            {'subject_id': 'A', 'use': 'identity', 'priority': 3},
            {'subject_id': 'B', 'use': 'outfit', 'priority': 0}]
        self.rows[1]['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 1}]
        text = d.instructions('multi-image', self.rows)
        self.assertIn('For subject A, identity, resolve source differences in this order: Reference 2; then Reference 1.', text)
        self.assertNotIn('For subject B, outfit, resolve source differences', text)
        self.assertIn('within the listed scopes', text)

    def test_complementary_views_retain_scopes_without_inventing_scene_content(self):
        for row in self.rows:
            row['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]
        original = copy.deepcopy(self.rows)
        text = d.instructions('multi-image', self.rows)
        self.assertIn('Views assigned to the same subject depict one character.', text)
        self.assertIn('For subject A, identity, Reference 1 and Reference 2 provide complementary evidence.', text)
        self.assertNotIn('resolve source differences', text)
        self.assertNotIn('priority', text)
        self.assertEqual(self.rows, original)
        self.assertIn('Use it for: enduring shape.', text)
        self.assertIn('Do not inherit: current orientation; expression.', text)

    def test_complementary_groups_preserve_order_between_scopes(self):
        third = copy.deepcopy(self.rows[1])
        third['transport']['sha256'] = 'e' * 64
        self.rows.append(third)
        for row, priority in zip(self.rows, [2, 0, 0]):
            row['subject_uses'] = [{'subject_id': 'A', 'use': 'outfit', 'priority': priority}]
        text = d.instructions('multi-image', self.rows)
        self.assertIn('For subject A, outfit, Reference 2 and Reference 3 provide complementary evidence.', text)
        self.assertIn('For subject A, outfit, resolve source differences in this order: Reference 2 and Reference 3; then Reference 1.', text)
        self.assertEqual([r['subject_uses'][0]['priority'] for r in d.bindings('multi-image', self.rows)], [2, 0, 0])

    def test_subject_assignment_checks_actual_cast_without_state_graph(self):
        spec = {'subjects': [{'id': 'A'}, {'id': 'B'}], 'state_context': {'mode': 'stateless'}}
        self.rows[0]['subject_uses'] = [{'subject_id': 'B', 'use': 'identity', 'priority': 0}]
        d.validate_reference_subjects(self.rows, spec)
        d.validate_reference_selection_subjects(None, spec)
        self.rows[0]['subject_uses'][0]['subject_id'] = 'C'
        with self.assertRaisesRegex(ValueError, 'unknown subject'):
            d.validate_reference_subjects(self.rows, spec)

    def test_assignments_reject_scope_expansion_and_ambiguous_priority(self):
        valid = {'subject_id': 'A', 'use': 'identity', 'priority': 0}
        for priority in (True, -1, 1.5):
            with self.assertRaises(ValueError):
                d.validate_subject_uses([{**valid, 'priority': priority}])
        with self.assertRaisesRegex(ValueError, 'repeats'):
            d.validate_subject_uses([valid, {**valid, 'priority': 1}])
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            d.validate_subject_uses([valid], allowed_uses=['outfit'])

    def test_state_context_matches_every_subject_independently(self):
        spec = {'state_context': {'mode': 'state-aware'}, 'subjects': [
            {'id': 'A', 'identity_contract_ref': {'sha256': 'a' * 64}, 'state_snapshot_ref': {'sha256': 'b' * 64}},
            {'id': 'B', 'identity_contract_ref': {'sha256': 'c' * 64}, 'state_snapshot_ref': {'sha256': 'd' * 64}}]}
        selection = {'subjects': [{'subject_id': row['id'],
            'identity_contract_sha256': row['identity_contract_ref']['sha256'],
            'state_snapshot_sha256': row['state_snapshot_ref']['sha256']} for row in spec['subjects']],
            'selected_references': []}
        d.validate_reference_selection_subjects(selection, spec)
        swapped = copy.deepcopy(selection)
        swapped['subjects'][1]['state_snapshot_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'subject B'):
            d.validate_reference_selection_subjects(swapped, spec)
        selection['subjects'].pop()
        with self.assertRaisesRegex(ValueError, 'exactly match'):
            d.validate_reference_selection_subjects(selection, spec)


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
