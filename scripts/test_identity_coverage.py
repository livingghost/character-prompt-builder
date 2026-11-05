"""Identity coverage on synthetic original sources and actual request carriers.

These tests establish explicit coverage and provenance, not visual preservation.
They need no pack, service, approval or generated image.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import execution_contract as c
import identity_coverage as identity
from production_diagnostics import ProductionError
from state_protocol import unsupported_schema_keywords, validate_against_schema


def source(ident='adopted', path='original.json', subjects=None, selectors=None):
    return {'id': ident, 'path': path, 'role': 'adopted source', 'disposition': 'applied',
            'locator': 'original material', 'reason': 'The source defines these subjects.',
            'identity': {'subject_ids': subjects or ['A', 'B'],
                         'selectors': selectors if selectors is not None else ['/identity']}}


def binding(*, selectors=None, subjects=None, treatment='preserve', source_id='adopted'):
    return {'source': source_id, 'subject_ids': subjects or ['A', 'B'],
            'selectors': selectors if selectors is not None else ['/identity'],
            'treatment': treatment, 'reason': 'Retain the source conditions in this scene.',
            'carriers': [{'kind': 'text', 'surface': 'primary', 'quote': 'Keep the conditional relationship.'}],
            'variation': None}


class IdentityCoverageTests(unittest.TestCase):
    def setUp(self):
        self.original = {'identity': {
            'unfamiliar': {'rim/edge': {'axis~key': 'Rim curls inward only when the two forms interlock.'}},
            'scale_relation': ['A remains narrower than B when both are in the same plane.',
                               'Under the stated rotation their apparent order can reverse.'],
            'fine_detail': 'A pale stipple ends before the lower seam; the seam continues behind it.',
            'unspecified': None, 'empty_array': [], 'empty_object': {}},
            'author_notes': 'Do not automatically promote the whole document to canon.'}
        self.files = {'original.json': c.encoded(self.original)}
        self.task = {'task_id': 'scene', 'artifact': 'image', 'features': ['recurring-identity'],
                     'sources': [source()], 'direction': {'decisions': []},
                     'criteria': [{'id': 'continuity', 'strength': 'hard', 'evidence': 'image',
                         'text': 'Compare the original definitions, conditions, detail and relation in the image.',
                         'identity_review': ['A', 'B'], 'identity_bindings': [binding()]}]}
        self.context = {'subject_ids': ['A', 'B'], 'required_subject_ids': ['A', 'B'],
                        'identity_sources': [], 'text': {}, 'references': []}
        self.text('Before. Keep the conditional relationship. After.')

    def text(self, text, surface='primary'):
        self.context['text'][surface] = {'text': text, 'field': ['request', surface],
                                         'sha256': c.digest(text.encode('utf-8'))}

    def compile(self):
        return identity.compile(self.task, self.files.__getitem__, context=self.context)

    def assert_code(self, code, action=None):
        with self.assertRaises(ProductionError) as caught:
            (action or self.compile)()
        self.assertEqual(caught.exception.diagnostic.code, code)
        self.assertEqual(caught.exception.diagnostic.phase, 'identity-coverage')
        return caught.exception.diagnostic.as_dict()

    @property
    def obligation(self):
        return self.task['criteria'][0]['identity_bindings'][0]

    def reference(self):
        self.obligation['carriers'] = [{'kind': 'reference', 'reference': 'approved-angle', 'use': 'identity'}]
        row = {'id': 'approved-angle', 'subject_ids': ['A', 'B'], 'use_for': ['identity', 'pose-camera'],
               'do_not_transfer': ['lighting'],
               'subject_uses': [{'subject_id': subject, 'use': 'identity', 'priority': 0} for subject in ['A', 'B']],
               'source_sha256': c.digest(b'approved alternate angle'), 'carrier_sha256': c.digest(b'actual crop pixels'),
               'request_fields': [['images', 0]], 'region_pixels': {'x': 0, 'y': 0, 'width': 12, 'height': 8},
               'derivation': {'kind': 'crop', 'source_region': [4, 3, 12, 8]}}
        self.context['references'] = [row]
        return row

    def test_arbitrary_details_conditions_relations_and_empty_values_survive_inventory(self):
        report = self.compile()
        record = report['sources'][0]
        leaves = {row['pointer']: row for row in record['terminals']}
        self.assertEqual(record['sha256'], c.digest(self.files['original.json']))
        self.assertEqual(record['scopes'][0]['value_sha256'], c.content_id(self.original['identity']))
        self.assertEqual(leaves['/identity/unfamiliar/rim~1edge/axis~0key']['value'],
                         self.original['identity']['unfamiliar']['rim/edge']['axis~key'])
        self.assertIsNone(leaves['/identity/unspecified']['value'])
        self.assertEqual(leaves['/identity/empty_array']['value'], [])
        self.assertEqual(leaves['/identity/empty_object']['value'], {})
        self.assertEqual(len(leaves['/identity/scale_relation/0']['coverage']), 2)
        self.assertFalse(report['unresolved'])
        self.assertTrue(report['structural_only'])
        self.assertEqual(report['status'], 'structurally-covered')
        self.assertNotIn('/author_notes', leaves)

    def test_new_arbitrary_field_changes_witness_and_is_not_lost_from_inventory(self):
        before = self.compile()
        self.original['identity']['new_condition'] = {'extra_free_detail': 'Only after separation, the notch faces B.'}
        self.files['original.json'] = c.encoded(self.original)
        after = self.compile()
        self.assertNotEqual(before['sources'][0]['sha256'], after['sources'][0]['sha256'])
        self.assertNotEqual(before['sources'][0]['scopes'], after['sources'][0]['scopes'])
        self.assertIn('/identity/new_condition/extra_free_detail',
                      {row['pointer'] for row in after['sources'][0]['terminals']})

    def test_grouped_explicit_selections_leave_uncovered_values_and_subjects_visible(self):
        self.obligation['selectors'] = ['/identity/unfamiliar', '/identity/scale_relation']
        self.obligation['subject_ids'] = ['A']
        report = identity.inventory(self.task, self.files.__getitem__, context=self.context)
        gaps = {row['pointer']: row['subject_ids'] for row in report['uncovered']}
        self.assertEqual(gaps['/identity/scale_relation/0'], ['B'])
        self.assertEqual(gaps['/identity/fine_detail'], ['A', 'B'])
        self.assert_code('IDENTITY_COVERAGE_INCOMPLETE')

    def test_fine_treatment_overrides_group_without_deleting_original_definition(self):
        detail = binding(selectors=['/identity/fine_detail'], treatment='not-exposed')
        detail['carriers'] = []
        detail['reason'] = 'The current crop hides the lower seam; its adopted presence is unchanged.'
        self.task['criteria'].append({'id': 'crop', 'strength': 'advisory', 'evidence': 'image',
                                     'text': 'The crop must not imply that the seam was removed.',
                                     'identity_bindings': [detail]})
        report = self.compile()
        leaf = next(row for row in report['sources'][0]['terminals'] if row['pointer'].endswith('/fine_detail'))
        self.assertEqual({row['treatment'] for row in leaf['coverage']}, {'not-exposed'})
        self.assertEqual(leaf['value'], self.original['identity']['fine_detail'])
        self.assertEqual(report['bindings'][1]['reason'], detail['reason'])

    def test_equally_specific_conflicting_treatments_fail(self):
        alternative = binding(treatment='not-applicable')
        alternative['carriers'] = []
        self.task['criteria'][0]['identity_bindings'].append(alternative)
        self.assert_code('IDENTITY_TREATMENT_CONFLICT')

    def test_selector_boundaries_escapes_arrays_and_duplicates_are_exact(self):
        for invalid in ['/ident', '/identity/scale_relation/01', '/identity/unfamiliar/rim~2edge']:
            with self.subTest(selector=invalid):
                self.obligation['selectors'] = [invalid]
                self.assert_code('IDENTITY_CONTRACT_INVALID' if invalid == '/ident' or '~2' in invalid
                                 else 'IDENTITY_SELECTOR_MISSING')
        self.obligation['selectors'] = ['/identity', '/identity/fine_detail']
        self.assert_code('IDENTITY_CONTRACT_INVALID')
        self.obligation['selectors'] = ['/identity']
        self.task['criteria'][0]['identity_bindings'].append(copy.deepcopy(self.obligation))
        self.assert_code('IDENTITY_CONTRACT_INVALID')

    def test_source_scope_cannot_be_broadened_by_criterion(self):
        self.task['sources'][0]['identity']['selectors'] = ['/identity/fine_detail']
        self.assert_code('IDENTITY_CONTRACT_INVALID')

    def test_whole_prose_is_preserved_without_keyword_extraction(self):
        prose = 'Moiré appears only where the two translucent fields overlap; a narrow clear margin remains.'
        self.files = {'original.txt': prose.encode('utf-8')}
        self.task['sources'] = [source(path='original.txt', selectors=[''])]
        self.obligation['selectors'] = ['']
        record = self.compile()['sources'][0]
        self.assertEqual(record['format'], 'text')
        self.assertEqual(record['terminals'][0]['value'], prose)
        self.obligation['selectors'] = ['/invented-extraction']
        self.assert_code('IDENTITY_SELECTOR_MISSING')

    def test_actual_text_is_required_and_precise_ranges_are_bound(self):
        report = self.compile()
        witness = report['bindings'][0]['carriers'][0]
        self.assertEqual(witness['ranges'], [[8, 42]])
        self.assertEqual(witness['field'], ['request', 'primary'])
        self.text('The authoring note said Keep the conditional relationship but it did not reach this request.')
        self.assert_code('IDENTITY_CARRIER_MISSING')

    def test_absent_surface_changed_surface_hash_and_empty_active_carriers_fail(self):
        for change, code in [
                (lambda: self.context['text'].clear(), 'IDENTITY_CARRIER_MISSING'),
                (lambda: self.context['text']['primary'].update(sha256=c.digest(b'stale')), 'IDENTITY_CARRIER_CHANGED'),
                (lambda: self.obligation.update(carriers=[]), 'IDENTITY_COVERAGE_INCOMPLETE')]:
            with self.subTest(code=code):
                self.setUp()
                change()
                self.assert_code(code)

    def test_negative_surface_is_an_actual_carrier_without_semantic_autofill(self):
        self.text('Do not merge the conditional boundaries.', surface='negative')
        self.obligation['carriers'] = [{'kind': 'text', 'surface': 'negative',
                                       'quote': 'Do not merge the conditional boundaries.'}]
        self.assertEqual(self.compile()['bindings'][0]['carriers'][0]['field'], ['request', 'negative'])

    def test_alternate_actual_media_carrier_preserves_its_distinct_origin_and_crop(self):
        row = self.reference()
        self.context['identity_sources'] = [{'id': 'reference:master', 'path': 'master.png',
            'subject_ids': ['A', 'B'], 'selectors': [''], 'format': 'image', 'value': None,
            'sha256': c.digest(b'original adopted image')}]
        self.files['master.png'] = b'original adopted image'
        self.task['sources'] = []
        self.obligation['source'] = 'reference:master'
        self.obligation['selectors'] = ['']
        report = self.compile()
        actual = report['bindings'][0]['carriers'][0]
        self.assertNotEqual(report['bindings'][0]['source_sha256'], actual['reference_source_sha256'])
        self.assertEqual(actual['derivation'], row['derivation'])
        self.assertEqual(actual['region_pixels'], row['region_pixels'])
        self.assertIsNone(report['sources'][0]['terminals'][0]['value'])
        self.assertFalse(report['unresolved'])

    def test_media_requires_attachment_subject_specific_use_and_unexcluded_scope(self):
        for change, code in [
                (lambda row: row.update(request_fields=[]), 'IDENTITY_CARRIER_MISSING'),
                (lambda row: row.update(subject_ids=['A']), 'IDENTITY_REFERENCE_SUBJECT'),
                (lambda row: row['subject_uses'][1].update(use='pose-camera'), 'IDENTITY_REFERENCE_SUBJECT'),
                (lambda row: row['do_not_transfer'].append('identity'), 'IDENTITY_REFERENCE_SCOPE'),
                (lambda row: row.update(use_for=['pose-camera']), 'IDENTITY_REFERENCE_SCOPE'),
                (lambda row: self.context.update(references=[]), 'IDENTITY_CARRIER_MISSING')]:
            with self.subTest(code=code):
                self.setUp()
                change(self.reference())
                self.assert_code(code)

    def test_relational_binding_can_use_separate_subject_images_but_not_drop_a_subject(self):
        first = self.reference()
        first.update(subject_ids=['A'], subject_uses=[{'subject_id': 'A', 'use': 'identity', 'priority': 0}])
        second = copy.deepcopy(first)
        second.update(id='second-subject', subject_ids=['B'],
                      subject_uses=[{'subject_id': 'B', 'use': 'identity', 'priority': 0}],
                      source_sha256=c.digest(b'original second subject'), request_fields=[['images', 1]])
        self.context['references'].append(second)
        self.obligation['carriers'].append({'kind': 'reference', 'reference': 'second-subject', 'use': 'identity'})
        witnesses = self.compile()['bindings'][0]['carriers']
        self.assertEqual([row['subject_ids'] for row in witnesses], [['A'], ['B']])
        self.obligation['carriers'].pop()
        self.assert_code('IDENTITY_REFERENCE_SUBJECT')

    def test_missing_whole_review_or_actual_identity_source_cannot_opt_out(self):
        self.task['criteria'][0].pop('identity_review')
        self.assert_code('IDENTITY_COVERAGE_INCOMPLETE')
        self.setUp()
        self.task['features'] = []
        self.task['sources'] = []
        self.task['criteria'][0]['identity_bindings'] = []
        detail = self.assert_code('IDENTITY_COVERAGE_INCOMPLETE')
        self.assertEqual(detail['gaps']['missing_subject_sources'], ['A', 'B'])
        self.context['required_subject_ids'] = []
        self.task['features'] = ['recurring-identity']
        self.assert_code('IDENTITY_COVERAGE_INCOMPLETE')

    def test_active_identity_and_whole_review_require_hard_image_criteria(self):
        for key, value in [('strength', 'advisory'), ('evidence', 'text')]:
            with self.subTest(key=key):
                self.setUp()
                self.task['criteria'][0][key] = value
                self.assert_code('IDENTITY_CONTRACT_INVALID')

    def test_unresolved_is_retained_for_independent_review_not_recast_as_absence(self):
        self.obligation['treatment'] = 'unresolved'
        self.obligation['reason'] = 'The original does not settle the rear attachment.'
        report = self.compile()
        self.assertEqual(report['unresolved'][0]['criterion'], 'continuity')
        self.assertEqual(report['bindings'][0]['treatment'], 'unresolved')
        self.assertNotIn('verdict', report['bindings'][0])

    def test_derived_node_retains_original_hash_pointer_and_checks_value(self):
        value = self.original['identity']
        self.task['sources'] = []
        self.obligation.update(source='state:A:identity', selectors=[''])
        row = {'id': 'state:A:identity', 'path': 'original.json', 'source_pointer': '/identity',
               'subject_ids': ['A', 'B'], 'selectors': [''], 'format': 'json', 'value': copy.deepcopy(value),
               'sha256': c.digest(self.files['original.json']), 'authority': {'adoption': 'existing-receipt'}}
        self.context['identity_sources'] = [row]
        identity.validate_task(self.task)
        record = self.compile()['sources'][0]
        self.assertEqual(record['source_pointer'], '/identity')
        self.assertEqual(record['sha256'], c.digest(self.files['original.json']))
        self.assertEqual(record['value_sha256'], c.content_id(value))
        row['value']['fine_detail'] = 'Invented replacement.'
        self.assert_code('IDENTITY_SOURCE_CHANGED')
        row['value'] = copy.deepcopy(value)
        self.files['original.json'] += b'\n'
        self.assert_code('IDENTITY_SOURCE_CHANGED')

    def test_missing_derived_source_and_unprocessed_added_source_fail(self):
        self.obligation['source'] = 'state:A:identity'
        self.assert_code('IDENTITY_SOURCE_MISSING')
        self.setUp()
        self.context['identity_sources'] = [{'id': 'state:A:appearance', 'path': 'original.json',
            'subject_ids': ['A'], 'selectors': [''], 'format': 'json', 'value': self.original,
            'sha256': c.digest(self.files['original.json'])}]
        report = identity.inventory(self.task, self.files.__getitem__, context=self.context)
        self.assertTrue(any(row['source'] == 'state:A:appearance' for row in report['uncovered']))
        self.assert_code('IDENTITY_COVERAGE_INCOMPLETE')

    def variation(self):
        self.task['sources'].append({'id': 'approval', 'path': 'approval.txt', 'disposition': 'applied'})
        self.task['direction']['decisions'] = [{'id': 'depiction', 'basis': ['adopted', 'approval'],
            'criteria': ['continuity'], 'accepted_variations': [{
                'id': 'bounded-turn', 'source': 'approval', 'locator': 'current request',
                'author': 'fixture author', 'scope': {'kind': 'source', 'source': 'adopted',
                                                    'sha256': c.digest(self.files['original.json'])},
                'allowance': 'The thin overlap may bend with the stated turn.',
                'limits': ['Keep the pale seam endpoint and the conditional relation.'], 'criteria': ['continuity']}]}]
        self.obligation.update(treatment='authorized-variation', variation='bounded-turn')
        return self.task['direction']['decisions'][0]['accepted_variations'][0]

    def test_variation_uses_existing_authority_scope_criterion_and_original_bytes(self):
        variation = self.variation()
        self.compile()
        variation['criteria'] = ['another']
        self.assert_code('IDENTITY_CONTRACT_INVALID')
        variation['criteria'] = ['continuity']
        variation['scope']['source'] = 'approval'
        self.assert_code('IDENTITY_CONTRACT_INVALID')
        variation['scope']['source'] = 'adopted'
        self.files['original.json'] += b'\n'
        self.assert_code('IDENTITY_SOURCE_CHANGED')

    def test_variation_cannot_be_invented_or_detached_from_treatment(self):
        self.obligation.update(treatment='authorized-variation', variation='invented')
        self.assert_code('IDENTITY_CONTRACT_INVALID')
        self.obligation['treatment'] = 'preserve'
        self.assert_code('IDENTITY_CONTRACT_INVALID')

    def test_schema_accepts_generic_choices_and_rejects_undeclared_carrier_fields(self):
        schema = json.loads((Path(__file__).resolve().parent.parent / 'schemas/authoring/production-task.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(unsupported_schema_keywords(schema), [])
        binding_schema = {'$defs': schema['$defs'], '$ref': '#/$defs/identityBinding'}
        self.assertEqual(validate_against_schema(self.obligation, binding_schema), [])
        self.obligation['carriers'][0]['claim'] = 'unvalidated text outside actual request'
        self.assertTrue(validate_against_schema(self.obligation, binding_schema))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
