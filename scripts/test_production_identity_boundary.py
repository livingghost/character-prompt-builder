"""Compare synthetic identity selections before a draft has finished delivery."""
from __future__ import annotations

import copy
import unittest

import execution_contract as c
import identity_coverage
import production_identity as identity
import production_identity_boundary as boundary
from production_diagnostics import ProductionError
from reference_runtime_smoke_test import _fixture_png


def source(ident='definition', path='definition.json', **identity_fields):
    return {'id': ident, 'path': path, 'role': 'identity-contract', 'disposition': 'applied',
        'identity': {'subject_ids': ['A'], 'selectors': [''], **identity_fields}}


def task(sources=()):
    return {'artifact': 'image', 'sources': copy.deepcopy(list(sources)),
            'recording': {'subject_map': {'A': {}}}, 'criteria': []}


def amend(snapshot):
    return {'authoring_work': {'operation': 'amend'}, 'retained_identity_sources': snapshot}


def changes(before, after):
    return {(row['source'], row['change_kind']) for row in boundary.compare(before, after)['changes']}


class SourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.files = {'definition.json': c.encoded({'identity': 'A split outer ring.', 'other': 'Scene note.'}),
                      'image.png': _fixture_png()}

    def read(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def snapshot(self, current=None, **kwargs):
        return identity.source_snapshot(current or task([source()]), self.read, **kwargs)

    def native(self):
        return {'references': [{'id': 'angle', 'file': 'image.png', 'role': 'identity',
            'use_for': ['identity'], 'do_not_transfer': ['lighting'],
            'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}]}

    def external(self):
        return {'external': {'image_input': self.native()}}

    def test_snapshot_does_not_require_delivery_or_criteria(self):
        current = task([source(), {'id': 'scene', 'path': 'absent.txt'}])
        current['criteria'] = [{'unfinished': True}]
        current['delivery'] = {'path': 'not-written.txt'}
        acquired = self.snapshot(current)
        self.assertEqual(acquired['unresolved'], [])
        self.assertEqual([row['id'] for row in acquired['sources']], ['definition'])
        self.assertEqual(acquired['sources'][0]['sha256'], c.digest(self.files['definition.json']))

    def test_closed_selection_detects_added_removed_and_renamed_sources(self):
        old = self.snapshot()
        added = self.snapshot(task([source(), source('another')]))
        self.assertEqual(changes(old, added), {('another', 'added')})
        removed = self.snapshot(task())
        self.assertEqual(changes(old, removed), {('definition', 'removed')})
        renamed = self.snapshot(task([source('new-id')]))
        self.assertEqual(changes(old, renamed), {('definition', 'removed'), ('new-id', 'added')})

    def test_reports_content_scope_and_subject_changes_together(self):
        old = self.snapshot()
        self.files['definition.json'] = c.encoded({'identity': 'Two connected rings.'})
        current = self.snapshot(task([source(selectors=['/identity'], subject_ids=['B'])]))
        self.assertEqual(changes(old, current), {('definition', 'content'), ('definition', 'scope'),
                                               ('definition', 'subjects')})

    def test_path_relocation_and_set_order_preserve_selection(self):
        current = task([source(subject_ids=['A', 'B'], selectors=['/identity', '/other'])])
        old = self.snapshot(current)
        self.files['saved/definition.json'] = self.files['definition.json']
        current['sources'][0].update(path='saved/definition.json')
        current['sources'][0]['identity'].update(subject_ids=['B', 'A'], selectors=['/other', '/identity'])
        self.assertEqual(boundary.compare(old, self.snapshot(current)), {'changes': [], 'unresolved': []})

    def test_compose_changes_current_selection_and_amend_rejects_it(self):
        old = self.snapshot()
        proposed = self.snapshot(task())
        boundary.require_unchanged({'authoring_work': {'operation': 'compose'}}, {'operation': 'compose'}, proposed)
        with self.assertRaises(ProductionError) as caught:
            boundary.require_unchanged(amend(old), {'operation': 'amend'}, proposed)
        detail = caught.exception.diagnostic.as_dict()
        self.assertEqual(detail['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertEqual(detail['cause'], 'retained-identity-source-changed')
        self.assertEqual(detail['changes'][0]['change_kind'], 'removed')

    def test_registered_operation_cannot_be_replaced_by_editing_basis(self):
        with self.assertRaises(ProductionError) as caught:
            boundary.require_unchanged(amend(self.snapshot()), {'operation': 'compose'}, self.snapshot(task()))
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORING_WORK_MISMATCH')

    def test_missing_bytes_keep_known_selection_and_unresolved_owner(self):
        old = self.snapshot()
        del self.files['definition.json']
        current = self.snapshot()
        self.assertEqual(current['sources'][0]['id'], 'definition')
        self.assertTrue(current['unresolved'])
        comparison = boundary.compare(old, current)
        self.assertEqual(comparison['changes'], [])
        self.assertTrue(comparison['unresolved'])
        with self.assertRaises(ProductionError) as caught:
            boundary.require_unchanged(amend(old), {'operation': 'amend'}, current)
        self.assertEqual(caught.exception.diagnostic.code, 'IDENTITY_SOURCE_UNAVAILABLE')

    def test_unknown_baseline_does_not_become_a_known_empty_selection(self):
        unknown = boundary.from_coverage(None)
        known_empty = {'sources': [], 'unresolved': []}
        self.assertTrue(boundary.compare(unknown, self.snapshot(task()))['unresolved'])
        self.assertEqual(changes(unknown, self.snapshot()), set())
        self.assertEqual(changes(known_empty, self.snapshot()), {('definition', 'added')})

    def test_coverage_gaps_are_separate_from_source_acquisition(self):
        old = self.snapshot()
        coverage = {**old, 'bindings': [], 'unresolved': [{'criterion': 'not-written'}]}
        self.assertEqual(boundary.from_coverage(coverage), old)
        context = {'authoring_work': {'operation': 'amend'}, 'identity_coverage': coverage}
        boundary.require_unchanged(context, {'operation': 'amend'}, old)

    def test_each_source_path_is_acquired_once(self):
        calls = []
        def reader(path):
            calls.append(path)
            return self.read(path)
        current = task([source(), source('another')])
        identity.source_snapshot(current, reader)
        self.assertEqual(calls, ['definition.json'])

    def test_external_reference_uses_are_visible_without_input_binding(self):
        old = self.snapshot(task(), choices=self.external())
        self.assertEqual(old['unresolved'], [])
        self.assertEqual([row['id'] for row in old['sources']], ['reference:angle'])
        current = self.external()
        current['external']['image_input']['references'][0]['do_not_transfer'] += ['style']
        self.assertEqual(changes(old, self.snapshot(task(), choices=current)), {('reference:angle', 'authority')})

    def test_reference_reordering_and_authority_set_order_are_immaterial(self):
        choice = self.external()
        row = choice['external']['image_input']['references'][0]
        row['use_for'] = ['identity', 'pose-camera']
        row['subject_uses'] += [{'subject_id': 'A', 'use': 'pose-camera', 'priority': 1}]
        choice['external']['image_input']['references'] += [{**copy.deepcopy(row), 'id': 'second-angle'}]
        old = self.snapshot(task(), choices=choice)
        choice['external']['image_input']['references'].reverse()
        for row in choice['external']['image_input']['references']:
            row['use_for'].reverse()
            row['subject_uses'].reverse()
        self.assertEqual(boundary.compare(old, self.snapshot(task(), choices=choice)),
                         {'changes': [], 'unresolved': []})

    def test_retained_witness_does_not_hide_reference_removal(self):
        old = self.snapshot(task(), choices=self.external())
        retained = source('reference:angle', 'image.png', authority=old['sources'][0]['authority'])
        basis = {'sources': {'reference:angle': {'origin': {'kind': 'retained-identity',
            'identity_owner': {'kind': 'reference-use', 'reference': 'angle'}}}}}
        current = self.external()
        current['external']['image_input']['references'] = []
        removed = self.snapshot(task([retained]), choices=current, basis=basis)
        self.assertEqual(changes(old, removed), {('reference:angle', 'removed')})
        active = self.snapshot(task([retained]), choices=self.external(), basis=basis)
        self.assertEqual(boundary.compare(old, active), {'changes': [], 'unresolved': []})

    def test_genuine_direct_evidence_does_not_replace_reference_authority(self):
        current = task([source('pixels', 'image.png')])
        acquired = self.snapshot(current, choices=self.external())
        self.assertEqual({row['id'] for row in acquired['sources']}, {'pixels', 'reference:angle'})

    def test_coverage_keeps_same_pixels_under_independent_reference_authority(self):
        current = task([source('pixels', 'image.png')])
        view = identity.context(current, self.read, inputs=self.native())
        self.assertEqual([row['id'] for row in view['identity_sources']], ['reference:angle'])
        current['sources'][0]['identity']['authority'] = copy.deepcopy(view['identity_sources'][0]['authority'])
        self.assertEqual(identity.context(current, self.read, inputs=self.native())['identity_sources'], [])
        current['sources'][0]['identity']['authority']['do_not_transfer'].append('outfit')
        self.assertEqual([row['id'] for row in identity.context(current, self.read,
            inputs=self.native())['identity_sources']], ['reference:angle'])

    def test_reference_subjectless_owner_is_unknown_not_empty(self):
        choice = self.external()
        choice['external']['image_input']['references'][0]['subject_uses'] = []
        current = task()
        current.pop('recording')
        acquired = self.snapshot(current, choices=choice)
        self.assertEqual(acquired['sources'], [])
        self.assertEqual(acquired['unresolved'][0]['source'], 'reference:angle')

    def test_unfinished_role_only_reference_has_no_implicit_identity_scope(self):
        selected = {'external': {'image_input': {'references': [
            {'id': 'chosen-use', 'file': 'unread.png', 'role': 'palette'},
            {'file': 'also-unread.png', 'role': 'geometry'}]}}}
        acquired = self.snapshot(task(), choices=selected)
        self.assertEqual(acquired, {'sources': [], 'unresolved': []})
        boundary.require_unchanged(amend(acquired), {'operation': 'amend'}, acquired)
        selected['external']['image_input']['references'][0].update(
            file='image.png', use_for=['identity'], do_not_transfer=[],
            subject_uses=[{'subject_id': 'A', 'use': 'identity', 'priority': 0}])
        self.assertEqual(changes(acquired, self.snapshot(task(), choices=selected)),
                         {('reference:chosen-use', 'added')})

    def test_invalid_scope_field_is_unknown_instead_of_reference_removal(self):
        old = self.snapshot(task(), choices=self.external())
        selected = self.external()
        selected['external']['image_input']['references'][0]['use_for'] = 'identity'
        result = boundary.compare(old, self.snapshot(task(), choices=selected))
        self.assertEqual(result['changes'], [])
        self.assertTrue(result['unresolved'])

    def test_saved_reference_reads_the_acquired_file_without_reopening_original(self):
        native = self.native()
        native['prepared_reference_set'] = {'selected_references': [{
            'reference_id': 'angle', 'role': 'identity', 'source': {'kind': 'supplied-file',
                'reference_id': 'angle', 'resolved_path': '/removed/original.png',
                'sha256': c.digest(self.files['image.png']), 'media_type': 'image/png'},
            'authority': {'controls': ['identity'], 'must_not_control': ['lighting']}}]}
        acquired = self.snapshot(task(), choices={'external': {'image_input': native}})
        self.assertEqual(acquired['unresolved'], [])
        self.assertEqual(acquired['sources'][0]['sha256'], c.digest(self.files['image.png']))
        self.assertEqual(acquired['sources'][0]['authority']['source']['resolved_path'], '/removed/original.png')

    def test_external_plan_file_selects_the_same_identity_without_finished_request(self):
        self.files['input-plan.json'] = c.encoded(self.native())
        acquired = self.snapshot(task(), choices={'external': {'image_input': 'input-plan.json'}})
        self.assertEqual(boundary.compare(self.snapshot(task(), choices=self.external()), acquired),
                         {'changes': [], 'unresolved': []})
        del self.files['input-plan.json']
        self.assertTrue(self.snapshot(task(), choices={'external': {'image_input': 'input-plan.json'}})['unresolved'])

    def test_editable_empty_selection_overrides_a_saved_prepared_reference(self):
        current = task()
        current['image_input'] = 'input.json'
        self.files['input.json'] = c.encoded(self.native())
        old = self.snapshot(current)
        selected = {'authoring': {'references': {'additional_references': []}}}
        self.assertEqual(changes(old, self.snapshot(current, choices=selected)), {('reference:angle', 'removed')})

    def test_direct_reference_choice_preserves_source_proof_and_scope(self):
        selection = {'authoring': {'references': {'additional_references': [{
            'id': 'angle', 'role': 'identity', 'source': {'kind': 'supplied-file',
                'reference_id': 'original-angle', 'resolved_path': 'image.png'},
            'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}]}}}
        old = self.snapshot(task(), choices=selection)
        self.assertEqual(old['unresolved'], [])
        proof = old['sources'][0]['authority']['source']
        self.assertEqual(proof['sha256'], c.digest(self.files['image.png']))
        self.assertEqual(proof['media_type'], 'image/png')
        self.files['copy.png'] = self.files['image.png']
        selection['authoring']['references']['additional_references'][0]['source']['resolved_path'] = 'copy.png'
        self.assertEqual(boundary.compare(old, self.snapshot(task(), choices=selection)),
                         {'changes': [], 'unresolved': []})

    def test_plan_reference_has_the_same_owner_before_and_after_preparation(self):
        from reference_contract import authority_for
        proof = {'kind': 'pack-artifact', 'pack_id': '01900000-0000-7000-8000-000000000001',
            'asset_id': 'synthetic-asset', 'artifact_id': 'synthetic-angle', 'resolved_path': 'image.png',
            'sha256': c.digest(self.files['image.png']), 'media_type': 'image/png'}
        uses = [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]
        item = {'id': 'angle', 'source': proof, 'technical_role': 'adopted-reference',
                'intended_influence': 'identity', 'subject_uses': uses}
        selected = {'authoring': {'references': {'reference_use_plan': {'items': [item]}}}}
        before = self.snapshot(task(), choices=selected)
        self.assertEqual(before['unresolved'], [])
        self.files['prepared.json'] = c.encoded({'selected_references': [{
            'reference_id': 'angle', 'role': 'identity', 'source': proof, 'subject_uses': uses,
            'authority': authority_for('adopted-reference', 'identity')}],
            'reference_use_plan': {'reference_items': [{'intended_influence': 'identity'}]}})
        current = task()
        current['generation'] = {'references': 'prepared.json'}
        self.assertEqual(boundary.compare(before, self.snapshot(current)), {'changes': [], 'unresolved': []})
        item['selected_controls'] = authority_for('adopted-reference', 'identity')['controls'][:1]
        self.assertEqual(changes(before, self.snapshot(task(), choices=selected)), {('reference:angle', 'authority')})

    def test_state_reference_has_the_same_owner_before_and_after_preparation(self):
        from reference_contract import state_authority_for
        proof = {'kind': 'supplied-file', 'reference_id': 'image-owner', 'resolved_path': 'image.png',
            'sha256': c.digest(self.files['image.png']), 'media_type': 'image/png'}
        row = {'id': 'angle', 'binding_id': 'state-angle', 'subject_id': 'A',
               'source': proof, 'intended_influence': ['identity']}
        selected = {'authoring': {'references': {'reference_selection': {
            'subjects': [{'subject_id': 'A'}], 'selected_references': [row]}}}}
        before = self.snapshot(task(), choices=selected)
        self.assertEqual(before['unresolved'], [])
        self.files['prepared.json'] = c.encoded({'selected_references': [{
            'reference_id': 'angle', 'role': 'identity', 'source': proof, 'subject_id': 'A',
            'intended_influence': ['identity'], 'authority': state_authority_for(['identity'])}]})
        current = task()
        current['generation'] = {'references': 'prepared.json'}
        self.assertEqual(boundary.compare(before, self.snapshot(current)), {'changes': [], 'unresolved': []})

    def test_same_pixels_with_a_different_adoption_proof_are_different_authority(self):
        old = self.snapshot(task(), choices=self.external())
        row = old['sources'][0]
        row['authority']['source'] = {'kind': 'studio-artifact', 'acceptance_sha256': 'a' * 64,
                                      'resolved_path': 'image.png'}
        current = copy.deepcopy(old)
        current['sources'][0]['authority']['source']['acceptance_sha256'] = 'b' * 64
        self.assertEqual(changes(old, current), {('reference:angle', 'authority')})

    def graphs(self):
        return [{'identity_contract': {'character_id': 'A', 'canon_status': 'adopted', 'outline': 'Split ring.'},
                 'scene_state': {'location': 'Atrium'}}]

    def graph_snapshot(self, graphs):
        return self.snapshot(task(), choices={'authoring': {'documents': {'state_graphs': graphs}}})

    def test_state_scene_edits_do_not_change_the_identity_owner(self):
        graphs = self.graphs()
        old = self.graph_snapshot(graphs)
        graphs[0]['scene_state']['location'] = 'Gallery'
        current = self.graph_snapshot(graphs)
        self.assertNotEqual(old['sources'][0]['sha256'], current['sources'][0]['sha256'])
        self.assertEqual(boundary.compare(old, current), {'changes': [], 'unresolved': []})
        boundary.require_unchanged(amend(old), {'operation': 'amend'}, current)

    def test_state_identity_value_and_authority_changes_are_detected(self):
        graphs = self.graphs()
        old = self.graph_snapshot(graphs)
        graphs[0]['identity_contract']['outline'] = 'Closed ring.'
        graphs[0]['identity_contract']['canon_status'] = 'proposal'
        self.assertEqual(changes(old, self.graph_snapshot(graphs)),
            {('state:A:identity_contract', 'content'), ('state:A:identity_contract', 'authority')})

    def test_state_graph_reordering_preserves_each_independent_owner(self):
        graphs = self.graphs() + [{'identity_contract': {'character_id': 'B', 'canon_status': 'adopted'}}]
        old = self.graph_snapshot(graphs)
        graphs.reverse()
        self.assertEqual(boundary.compare(old, self.graph_snapshot(graphs)), {'changes': [], 'unresolved': []})

    def test_multiple_documents_share_one_acquired_json_with_field_arrays(self):
        graphs = self.graphs()
        self.files['shared.json'] = c.encoded({'documents': [
            {'specification': {'subjects': [{'id': 'A'}]}}, {'graphs': graphs}]})
        choices = {'authoring': {'documents': {
            'production_spec': {'file': 'shared.json', 'field': ['documents', 0, 'specification']},
            'state_graphs': {'file': 'shared.json', 'field': ['documents', 1, 'graphs']}}}}
        calls = []
        def read(path):
            calls.append(path)
            return self.read(path)
        acquired = identity.source_snapshot(task(), read, choices=choices)
        self.assertEqual(acquired['unresolved'], [])
        self.assertEqual(boundary.compare(self.graph_snapshot(graphs), acquired), {'changes': [], 'unresolved': []})
        self.assertEqual(calls, ['shared.json'])

    def test_current_document_removal_does_not_reactivate_a_compiled_graph(self):
        self.files['graphs.json'] = c.encoded(self.graphs())
        current = task()
        current['generation'] = {'state_graphs': 'graphs.json'}
        old = self.snapshot(current)
        removed = self.snapshot(current, choices={'authoring': {'documents': {}}})
        self.assertEqual(changes(old, removed), {('state:A:identity_contract', 'removed')})

    def test_current_inventory_uses_the_same_owner_selection_as_the_boundary(self):
        self.files['graphs.json'] = c.encoded(self.graphs())
        current = task()
        current['generation'] = {'state_graphs': 'graphs.json'}
        selected = {'authoring': {'documents': {'state_graphs': self.graphs()}}}
        selected['authoring']['documents']['state_graphs'][0]['identity_contract']['outline'] = 'Two rings.'
        shown = identity.inspect(current, self.read, choices=selected)
        acquired = self.snapshot(current, choices=selected)
        self.assertEqual(boundary.compare(boundary.from_coverage(shown), acquired),
                         {'changes': [], 'unresolved': []})
        self.assertEqual(shown['sources'][0]['terminals'][-1]['value'], 'Two rings.')

    def test_unread_current_owner_is_reported_with_known_sources_and_action(self):
        selected = {'authoring': {'documents': {'state_graphs': {'file': 'absent.json'}}}}
        shown = identity.inspect(task([source()]), self.read, choices=selected)
        self.assertEqual([row['id'] for row in shown['sources']], ['definition'])
        self.assertEqual(shown['status'], 'unresolved')
        self.assertEqual(shown['diagnostics'][0]['code'], 'IDENTITY_SOURCE_UNAVAILABLE')
        self.assertTrue(shown['diagnostics'][0]['required_action'])

    def test_promoted_graph_owner_matches_its_derived_original(self):
        graphs = self.graphs()
        self.files['graphs.json'] = c.encoded(graphs)
        current = task()
        current['generation'] = {'state_graphs': 'graphs.json'}
        derived = self.snapshot(current)
        authority = derived['sources'][0]['authority']
        direct = source('state:A:identity_contract', 'graphs.json', selectors=['/0/identity_contract'],
                        authority=authority)
        acquired = self.snapshot(task([direct]))
        self.assertEqual(boundary.compare(derived, acquired), {'changes': [], 'unresolved': []})

    def test_state_owner_without_acquired_value_remains_unknown(self):
        acquired = self.graph_snapshot(self.graphs())
        broken = copy.deepcopy(acquired)
        broken['sources'][0].pop('scopes')
        broken['sources'][0].pop('value_sha256')
        result = boundary.compare(acquired, broken)
        self.assertEqual(result['changes'], [])
        self.assertTrue(result['unresolved'])

    def test_ordinary_json_still_retains_its_original_file_bytes(self):
        current = task([source(selectors=['/identity'])])
        old = self.snapshot(current)
        self.files['definition.json'] = c.encoded({'identity': 'A split outer ring.', 'other': 'Changed note.'})
        self.assertEqual(changes(old, self.snapshot(current)), {('definition', 'content')})

    def test_task_local_definition_keeps_its_existing_authored_scope(self):
        row = {'id': 'subject:A', 'path': 'definition.json', 'role': 'definition',
            'definition_owner': {'document': 'production_spec', 'subject_id': 'A'}}
        basis = {'operation': 'amend', 'sources': {'subject:A': {'origin': {'kind': 'task-subject'}}}}
        old = self.snapshot(task([row]), basis=basis)
        self.files['definition.json'] = c.encoded({'identity': 'The current authored candidate changed.'})
        current = self.snapshot(task([row]), basis=basis)
        self.assertEqual(old, {'sources': [], 'unresolved': []})
        boundary.require_unchanged(amend(old), basis, current)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
