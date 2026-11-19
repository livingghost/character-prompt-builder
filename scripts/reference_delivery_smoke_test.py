#!/usr/bin/env python3
"""Synthetic reference-order, board-region and influence-contract checks."""
from __future__ import annotations
import runtime_paths
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import reference_delivery as d
from generation_references import _validate_authority


class ReferenceDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'reference_id': 'subject', 'role': 'declared-subject', 'source': {'sha256': 'a' * 64}, 'transport': {'sha256': 'b' * 64},
                      'authority': {'controls': ['enduring shape'], 'must_not_control': ['current orientation', 'expression']}},
                     {'reference_id': 'space', 'role': 'environment', 'source': {'sha256': 'c' * 64}, 'transport': {'sha256': 'd' * 64},
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
        self.assertEqual(rows[1]['region_pixels'], {'x': 100, 'y': 0, 'width': 100, 'height': 100})

    def test_current_state_exclusions_remain_in_review_bindings(self):
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual(rows[0]['must_not_control'], ['current orientation', 'expression'])
        self.assertEqual(rows[1]['must_not_control'], ['current light'])

    def test_scoped_choice_changes_consumed_model_text_without_unrelated_clauses(self):
        from reference_contract import authority_for
        from model_rendition import resolve_reference_text
        source = 'Gesture guide: Image {{reference:subject:attachment_number}}, {{reference:subject:controls}}.'
        texts = []
        for control in ('target pose and body gesture', 'target camera framing and crop'):
            self.rows[0]['authority'] = authority_for('adopted-reference', 'pose-camera',
                selected_controls=[control])
            result = resolve_reference_text(source, d.bindings('multi-image', self.rows[:1]))
            texts.append(result['text'])
            self.assertEqual(result['text'], 'Gesture guide: Image 1, ' + control + '.')
            self.assertEqual(result['source_text'], source)
            self.assertNotIn('must not', result['text'])
            self.assertNotIn('silhouette', result['text'])
        self.assertNotEqual(texts[0], texts[1])

    def test_scope_selection_cannot_expand_declared_capability(self):
        from reference_contract import authority_for
        with self.assertRaisesRegex(ValueError, 'subset'):
            authority_for('adopted-reference', 'identity', selected_controls=['target camera framing and crop'])
        with self.assertRaisesRegex(ValueError, 'subset'):
            authority_for('subject-mask', 'pose-camera', selected_controls=['target pose and body gesture'])
        from reference_contract import normalize_selected_records
        with self.assertRaisesRegex(ValueError, 'select selected_controls'):
            normalize_selected_records([{'record_id': 'chosen-source', 'intended_influence': 'pose-camera'}],
                                       require_selection=True)

    def test_editable_guide_exposes_selected_words_before_preparation(self):
        from production_reference_inputs import text_guide
        guide = text_guide({'external': {'image_input': {'references': [
            {'id': 'keeper', 'role': 'identity', 'use_for': ['three cheek marks'], 'do_not_transfer': []}]}}})
        self.assertEqual(guide['slots'][0]['controls_text'], 'three cheek marks')
        self.assertEqual(guide['slots'][0]['markers']['controls'], '{{reference:keeper:controls}}')
        self.assertEqual(guide['slots'][0]['derived_locations'], ['attachment_number'])
        unresolved = text_guide({'authoring': {'references': {'reference_use_plan': {'items': [
            {'id': 'motion', 'intended_influence': 'pose-camera', 'technical_role': 'structural-line-tone'}]}}}})
        self.assertIsNone(unresolved['slots'][0]['selected_controls'])
        self.assertIn('target camera framing and crop', unresolved['slots'][0]['available_controls'])

    def test_locators_alone_do_not_deliver_selected_contributions(self):
        from model_rendition import resolve_reference_text
        from production_diagnostics import ProductionError
        with self.assertRaises(ProductionError) as caught:
            resolve_reference_text('Use Image {{reference:subject:attachment_number}}.',
                d.bindings('multi-image', self.rows[:1]))
        self.assertEqual(caught.exception.diagnostic.code, 'REFERENCE_TEXT_UNRESOLVED')

    def test_reordering_and_deduplication_rebind_stable_uses_in_authored_relation(self):
        from model_rendition import resolve_reference_text
        source = ('Use {{reference:subject:controls}} from Image {{reference:subject:attachment_number}} '
                  'within {{reference:space:controls}} from Image {{reference:space:attachment_number}}.')
        first = resolve_reference_text(source, d.bindings('multi-image', self.rows))
        second = resolve_reference_text(source, d.bindings('multi-image', self.rows[::-1]))
        self.assertEqual(first['text'], 'Use enduring shape from Image 1 within spatial arrangement from Image 2.')
        self.assertEqual(second['text'], 'Use enduring shape from Image 2 within spatial arrangement from Image 1.')
        self.rows[1]['transport'] = copy.deepcopy(self.rows[0]['transport'])
        shared = resolve_reference_text(source, d.bindings('multi-image', self.rows))
        self.assertEqual(shared['text'], 'Use enduring shape from Image 1 within spatial arrangement from Image 1.')

    def test_board_scope_consumes_actual_region_with_author_owned_syntax(self):
        from model_rendition import resolve_reference_text
        source = ('Image {{reference:subject:attachment_number}} ({{reference:subject:region}}): '
                  '{{reference:subject:controls}}; Image {{reference:space:attachment_number}} '
                  '(x={{reference:space:x}}, y={{reference:space:y}}, w={{reference:space:width}}, '
                  'h={{reference:space:height}}): {{reference:space:controls}}.')
        rows = d.bindings('single-board', self.rows, self.board)
        result = resolve_reference_text(source, rows)
        self.assertEqual(result['text'], 'Image 1 (0, 0, 100, 100): enduring shape; '
            'Image 1 (x=100, y=0, w=100, h=100): spatial arrangement.')
        from production_diagnostics import ProductionError
        with self.assertRaises(ProductionError):
            resolve_reference_text(source.replace('{{reference:subject:region}}', 'top panel'), rows)

    def test_target_expressions_and_explicit_exceptions_preserve_authored_grammar(self):
        from reference_contract import authority_for
        from model_rendition import resolve_reference_text
        self.rows[0]['authority'] = authority_for('adopted-reference', 'pose-camera',
            selected_controls=['target pose and body gesture'],
            control_expressions={'target pose and body gesture': 'raised tentacles'})
        rows = d.bindings('multi-image', self.rows[:1])
        source = 'guide_{{reference:subject:attachment_number}}, ({{reference:subject:controls}}:1.2)'
        self.assertEqual(resolve_reference_text(source, rows)['text'], 'guide_1, (raised tentacles:1.2)')
        explicit = source + '; leave {{reference:subject:must_not_control}} with the scene.'
        self.assertIn(', '.join(rows[0]['must_not_control']), resolve_reference_text(explicit, rows)['text'])

    def test_only_selected_text_channel_requires_scope_consumption(self):
        from model_rendition import resolve_reference_channels, validate_reference_channels
        from production_diagnostics import ProductionError
        rows = d.bindings('multi-image', self.rows[:1])
        source = 'Image {{reference:subject:attachment_number}} supplies {{reference:subject:controls}}.'
        result = resolve_reference_channels({'prompt': 'Working draft.', 'integrated_prompt': source}, rows,
            reference_mode='authored-rendition', negative_transport='integrated-critical')
        self.assertEqual(result['selected_channel'], 'integrated_prompt')
        self.assertEqual(result['channels']['integrated_prompt']['text'], 'Image 1 supplies enduring shape.')
        validate_reference_channels(result, rows, reference_mode='authored-rendition', negative_transport='integrated-critical')
        with self.assertRaises(ProductionError):
            resolve_reference_channels({'prompt': source, 'integrated_prompt': 'Unused scopes.'}, rows,
                reference_mode='authored-rendition', negative_transport='integrated-critical')
        changed = copy.deepcopy(result)
        changed['channels']['integrated_prompt']['text'] = 'Image 1 supplies every feature.'
        with self.assertRaises(ValueError):
            validate_reference_channels(changed, rows, reference_mode='authored-rendition', negative_transport='integrated-critical')

    def test_native_mapping_requires_no_authored_prose_and_no_reference_text_stays_exact(self):
        from model_rendition import resolve_reference_channels
        rows = d.bindings('multi-image', self.rows[:1])
        for bindings, mode in ((rows, 'native-fields'), ([], 'none')):
            record = resolve_reference_channels({'prompt': 'A complete composition.'}, bindings,
                reference_mode=mode, negative_transport='separate-field')
            self.assertEqual(record['channels']['prompt']['text'], 'A complete composition.')
            self.assertEqual(record['channels']['prompt']['trace'], [])

    def test_reference_execution_policy_requires_its_recorded_text_dialect(self):
        import execution_contract as c
        from execution_policy import load_policy
        from input_evidence import InputEvidence
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = {'service': 'synthetic-host', 'model_identifier': 'tag-fixture', 'operation': 'generate'}
            policy = {'artifact_type': 'execution-policy', 'target': target,
                'reference_instruction_transport': None,
                'basis': {'path': 'basis.txt', 'sha256': c.digest(b'Synthetic declaration.'), 'locator': 'whole'}}
            (root / 'basis.txt').write_bytes(b'Synthetic declaration.')
            (root / 'policy.json').write_bytes(c.encoded(policy))
            declaration = {'execution_policy': {'path': 'policy.json', 'sha256': c.sha256_file(root / 'policy.json')}}
            with self.assertRaisesRegex(ValueError, 'text_dialect'):
                load_policy(declaration, InputEvidence(root), target, dialect='fixture-tags')

    def test_state_subject_survives_without_optional_use_priorities(self):
        from model_rendition import validate_bindings
        self.rows[0]['subject_id'] = 'A'
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual(rows[0]['subject_id'], 'A')
        validate_bindings(rows)

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
        for mode in ('none', 'prompt-artifacts', 'svg-bundle'):
            self.assertEqual(d.bindings(mode, []), [])

    def test_missing_board_metadata_cannot_bind_delivery(self):
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

    def test_one_attachment_retains_two_logical_sources_and_uses(self):
        self.rows[1]['transport'] = copy.deepcopy(self.rows[0]['transport'])
        self.rows[0]['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]
        self.rows[1]['subject_uses'] = [{'subject_id': 'B', 'use': 'outfit', 'priority': 1}]
        original = copy.deepcopy(self.rows)
        bindings = d.bindings('multi-image', self.rows)
        self.assertEqual([row['attachment_number'] for row in bindings], [1, 1])
        self.assertEqual([row['reference_number'] for row in bindings], [1, 2])
        self.assertEqual([row['subject_uses'] for row in bindings],
                         [row['subject_uses'] for row in self.rows])
        self.assertEqual(d.delivered_reference_count({'transport_mode': 'multi-image', 'selected_references': self.rows}), 1)
        self.assertNotEqual(self.rows[0]['source'], self.rows[1]['source'])
        self.assertEqual(self.rows, original)

    def test_subject_use_priorities_remain_separate(self):
        self.rows[0]['subject_uses'] = [
            {'subject_id': 'A', 'use': 'identity', 'priority': 3},
            {'subject_id': 'B', 'use': 'outfit', 'priority': 0}]
        self.rows[1]['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 1}]
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual([row['subject_uses'] for row in rows],
                         [row['subject_uses'] for row in self.rows])
        self.assertEqual([row['attachment_number'] for row in rows], [1, 2])

    def test_complementary_views_retain_independent_scope(self):
        for row in self.rows:
            row['subject_uses'] = [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]
        original = copy.deepcopy(self.rows)
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual([row['subject_uses'][0]['subject_id'] for row in rows], ['A', 'A'])
        self.assertEqual([row['controls'] for row in rows], [['enduring shape'], ['spatial arrangement']])
        self.assertEqual([row['must_not_control'] for row in rows],
                         [['current orientation', 'expression'], ['current light']])
        self.assertEqual(self.rows, original)

    def test_complementary_groups_keep_delivery_order_and_priorities(self):
        third = copy.deepcopy(self.rows[1])
        third['reference_id'] = 'space-detail'
        third['transport']['sha256'] = 'e' * 64
        self.rows.append(third)
        for row, priority in zip(self.rows, [2, 0, 0]):
            row['subject_uses'] = [{'subject_id': 'A', 'use': 'outfit', 'priority': priority}]
        rows = d.bindings('multi-image', self.rows)
        self.assertEqual([row['attachment_number'] for row in rows], [1, 2, 3])
        self.assertEqual([row['subject_uses'][0]['priority'] for row in rows], [2, 0, 0])

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


class ReferenceDeliveryCliTests(unittest.TestCase):
    def setUp(self):
        import catalog_api as catalog_cli
        import pack_manager
        from generation_payload_builder import materialize_cli_reference_bundle
        from generation_references import prepare_references
        from production_case_fixtures import create_pack, MODEL_ID, PACK_ID, write
        from production_fixtures import scratch_home
        from reference_runtime_smoke_test import _fixture_png

        temporary = tempfile.TemporaryDirectory(prefix='cpb-reference-delivery-cli-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.enterContext(scratch_home(self.work / 'home'))
        self.addCleanup(catalog_cli.configure_pack_runtime, None)
        self.skill = Path(__file__).resolve().parents[1]
        pack = create_pack(self.work / 'synthetic-pack')
        settings = runtime_paths.PackSettings(roots=(pack,), state_file=self.work / 'state.json',
            cache_dir=self.work / 'cache', managed_root=self.work / 'managed',
            quarantine_root=self.work / 'managed/.quarantine')
        pack_manager.save_state(settings.state_file, {'pack_roots': [str(pack)],
            'enabled_packs': [PACK_ID], 'disabled_packs': [], 'pack_order': [PACK_ID]})
        catalog_cli.configure_pack_runtime(settings)
        self.runtime = pack_manager.pack_runtime_arguments(settings, pack_roots=[pack])
        self.source = self.work / 'source.png'
        self.source.write_bytes(_fixture_png())
        prepared = prepare_references([{'role': 'scene', 'source': {
            'kind': 'supplied-file', 'reference_id': 'scene', 'resolved_path': str(self.source)}}],
            model=MODEL_ID, output_dir=self.work / 'materialized')
        folder = self.work / 'nested/inputs'
        folder.mkdir(parents=True)
        self.prepared, _ = materialize_cli_reference_bundle(prepared, model=MODEL_ID,
            source_root=self.work, staging_root=folder, companion_name='images')
        self.prepared_file = folder / 'references.json'
        write(self.prepared_file, self.prepared)

    def command(self, *arguments):
        return subprocess.run([sys.executable, str(self.skill / 'scripts/reference_delivery.py'),
            *arguments], cwd=self.work, env=os.environ.copy(), text=True, encoding='utf-8',
            capture_output=True, check=False)

    def test_prepared_file_owns_relative_carriers_in_selected_runtime(self):
        result = self.command('--prepared-set', str(self.prepared_file), *self.runtime)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['bindings'][0]['attachment_number'], 1)
        self.assertEqual(report['bindings'][0]['role'], 'scene')
        self.assertFalse(Path(self.prepared['selected_references'][0]['transport']['resolved_path']).is_absolute())

    def test_partial_runtime_selection_is_rejected(self):
        result = self.command('--prepared-set', str(self.prepared_file), '--state-file', str(self.work / 'state.json'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must be supplied together', result.stderr)

    def test_external_projection_uses_existing_prepared_file_location(self):
        from execution_contract import encoded
        from model_prompt_input_fixtures import prompt_input
        row = self.prepared['selected_references'][0]
        plan = {'artifact_type': 'image-input-plan', 'model': {
            'requested': 'fixture', 'catalog_status': 'missing', 'catalog_model': None,
            'prompt_input': prompt_input('descriptive'),
            'target': {'service': 'synthetic', 'model_identifier': 'fixture', 'operation': 'generation'},
            'evidence': {'path': 'provider.txt', 'sha256': 'a' * 64, 'locator': 'whole'}},
            'prepared_references': self.prepared_file.relative_to(self.work).as_posix(),
            'references': [{'id': 'scene', 'file': 'source.png', 'sha256': row['source']['sha256'],
                'role': row['role'], 'use_for': row['authority']['controls'],
                'do_not_transfer': row['authority']['must_not_control']}],
            'external_request': {'file': 'request.json', 'model_field': ['model'], 'prompt_field': ['prompt'],
                'count_field': ['count'], 'operation_field': None, 'count': 1, 'reference_fields': [
                    {'reference': 'scene', 'field': ['images', 0], 'value': 'source.png',
                     'evidence': {'path': 'provider.txt', 'sha256': 'a' * 64, 'locator': 'whole'}}]}}
        plan_file = self.work / 'plan.json'
        plan_file.write_bytes(encoded(plan))
        result = self.command('--image-input-plan', str(plan_file), '--studio', str(self.work), *self.runtime)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['bindings'][0]['request_field'], ['images', 0])


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
