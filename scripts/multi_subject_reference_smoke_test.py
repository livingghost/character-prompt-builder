#!/usr/bin/env python3
"""Synthetic checks for independent character graphs and scoped reference delivery."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build_state_generation_package import build_package
from build_generation_payload import build_payload
from prepare_generation_references import (build_prepared_reference_set, prepare_references,
    prepare_state_reference_selection, validate_prepared_references)
from reading_fixtures import fixture_reading
from state_generation_smoke_test import _load_graph, _payload_inputs
from state_protocol import (artifact_hash, combine_reference_selections, finalize_artifact,
                            select_state_references, validate_artifact, validate_subject_state_graphs)
from visual_fixtures import fixture_root, fixture_visual, verify_package


def replace_values(value, replacements):
    if isinstance(value, dict):
        return {key: replace_values(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_values(item, replacements) for item in value]
    return replacements.get(value, value) if isinstance(value, str) else value


def scene_graphs():
    """Author two independent synthetic identities into the same concrete context."""
    original = _load_graph()
    graphs = [copy.deepcopy(original), json.loads(json.dumps(original).replace('C01', 'C03'))]
    replacements = [{}, {}]
    for index, graph in enumerate(graphs):
        for name in ('species_profile', 'individual_morphology', 'identity_contract', 'state_snapshot'):
            graph[name] = finalize_artifact(replace_values(graph[name], replacements[index]))
            replacements[index][artifact_hash(original[name])] = artifact_hash(graph[name])
    context = copy.deepcopy(original['scene_context'])
    context['active_character_snapshots'] = [
        {'character_id': graph['identity_contract']['character_id'],
         'snapshot_id': graph['state_snapshot']['snapshot_id'],
         'state_snapshot_sha256': artifact_hash(graph['state_snapshot'])} for graph in graphs]
    context = finalize_artifact(context)
    for index, graph in enumerate(graphs):
        graph['scene_context'] = copy.deepcopy(context)
        replacements[index][artifact_hash(original['scene_context'])] = artifact_hash(context)
        for name in ('visual_projection', 'asset_render_spec', 'lineage'):
            if name == 'asset_render_spec':
                for key in ('target_model', 'art_direction', 'scene', 'camera', 'lighting', 'selected_preset_ids'):
                    graph[name][key] = copy.deepcopy(original['production_spec'].get(key))
            graph[name] = finalize_artifact(replace_values(graph[name], replacements[index]))
            replacements[index][artifact_hash(original[name])] = artifact_hash(graph[name])
        graph['production_spec'] = replace_values(graph['production_spec'], replacements[index])
    specification = copy.deepcopy(graphs[0]['production_spec'])
    specification['subjects'].append(copy.deepcopy(graphs[1]['production_spec']['subjects'][0]))
    return [{key: value for key, value in graph.items() if key != 'production_spec'} for graph in graphs], specification


def selection_for(graph, *, feature=None):
    subject = graph['identity_contract']['character_id']
    references = []
    if feature is not None:
        references.append({'subject_id': subject, 'binding_id': 'BIND-local', 'role': 'identity',
            'source': {'kind': 'supplied-file', 'reference_id': subject.lower(),
                'resolved_path': '/synthetic/' + subject + '.png', 'media_type': 'image/png', 'sha256': 'a' * 64},
            'covers': [feature], 'intended_influence': ['identity'], 'review_dimensions': [],
            'unsupported_or_occluded_state': [], 'unsupported_assumptions': [],
            'subject_uses': [{'subject_id': subject, 'use': 'identity', 'priority': 0}]})
    return finalize_artifact({'artifact_type': 'reference-selection', 'selection_id': 'SEL-' + subject,
        'subjects': [{'subject_id': subject, 'identity_contract_sha256': artifact_hash(graph['identity_contract']),
            'era_contract_sha256': None, 'appearance_variant_sha256': None,
            'state_snapshot_sha256': artifact_hash(graph['state_snapshot']),
            'story_order': graph['state_snapshot']['story_order'], 'required_state_features': [feature] if feature else []}],
        'selected_references': references, 'unresolved_requirements': []})


class IndependentReferenceStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graphs, cls.specification = scene_graphs()

    def inputs(self):
        spec = copy.deepcopy(self.specification)
        graphs = copy.deepcopy(self.graphs)
        selection = combine_reference_selections([selection_for(graph) for graph in graphs], selection_id='SEL-SCENE')
        prepared = build_prepared_reference_set(transport_mode='none', target_model=None,
            reference_selection=selection, zero_reference_reason={'code': 'no-canonical-record-selected',
                'record_ids': [], 'detail': 'Synthetic graph validation without visual media.'})
        arguments = _payload_inputs(_load_graph())
        arguments.update(production_spec=spec, state_graphs=graphs, prepared_reference_set=prepared,
            parameters={'width': 1024, 'height': 1024, 'settings': {'quality': 'high'}},
            visual_continuity=fixture_visual(spec), visual_root=fixture_root(),
            route_reading=fixture_reading(route='state-series'))
        return arguments

    def test_two_full_graphs_build_and_verify(self):
        package = build_package(**self.inputs())
        self.assertEqual([graph['identity_contract']['character_id'] for graph in package['state_graphs']], ['C01', 'C03'])
        self.assertTrue(verify_package(package)['verified'])
        changed = copy.deepcopy(package)
        changed['state_graphs'][1]['identity_contract']['display_name'] = 'uncommitted replacement'
        with self.assertRaisesRegex(ValueError, 'invalid state artifact graph for C03'):
            verify_package(changed)

    def test_second_graph_invalid_edge_blocks_build(self):
        arguments = self.inputs()
        arguments['state_graphs'][1]['state_snapshot']['identity_contract_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'invalid state artifact graph for C03'):
            build_package(**arguments)

    def test_regular_builder_derives_primary_state_from_the_same_graphs(self):
        arguments = self.inputs()
        self.assertNotIn('state_lineage', arguments)
        self.assertNotIn('state_snapshot', arguments)
        package = build_payload(**arguments)
        self.assertEqual(package['state_lineage'], arguments['state_graphs'][0]['lineage'])
        self.assertTrue(verify_package(package)['verified'])

    def test_regular_builder_rejects_other_subjects_explicit_primary_state(self):
        for parameter, node in (('state_lineage', 'lineage'), ('state_snapshot', 'state_snapshot')):
            arguments = self.inputs()
            arguments[parameter] = copy.deepcopy(arguments['state_graphs'][1][node])
            with self.subTest(parameter=parameter), self.assertRaisesRegex(ValueError, 'primary'):
                build_payload(**arguments)

    def test_second_subject_wrong_hash_blocks_build(self):
        arguments = self.inputs()
        arguments['production_spec']['subjects'][1]['identity_contract_ref']['sha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'subject C03'):
            build_package(**arguments)

    def test_missing_or_repeated_subject_graph_is_rejected(self):
        for mode in ('missing', 'repeated'):
            arguments = self.inputs()
            if mode == 'missing':
                arguments['state_graphs'].pop()
            else:
                arguments['state_graphs'][1] = copy.deepcopy(arguments['state_graphs'][0])
            with self.assertRaises(ValueError):
                build_package(**arguments)

    def test_stateless_background_subject_requires_no_graph(self):
        arguments = self.inputs()
        extra = copy.deepcopy(arguments['production_spec']['subjects'][0])
        extra['id'] = 'BACKGROUND'
        for key in ('identity_contract_ref', 'species_morphology_profile_ref', 'individual_morphology_contract_ref',
                    'resolved_morphology', 'state_snapshot_ref', 'visual_projection_ref', 'growth_geometry'):
            extra.pop(key, None)
        arguments['production_spec']['subjects'].append(extra)
        arguments['visual_continuity'] = fixture_visual(arguments['production_spec'])
        self.assertTrue(verify_package(build_package(**arguments))['verified'])

    def test_local_binding_ids_and_features_do_not_merge_subjects(self):
        selections = [selection_for(graph, feature='left-ear-anchor') for graph in self.graphs]
        combined = combine_reference_selections(selections, selection_id='SEL-LOCAL',
            reference_order=[{'subject_id': 'C03', 'binding_id': 'BIND-local'},
                             {'subject_id': 'C01', 'binding_id': 'BIND-local'}])
        self.assertTrue(validate_artifact(combined)['ok'])
        self.assertEqual([row['subject_id'] for row in combined['selected_references']], ['C03', 'C01'])
        validate_subject_state_graphs(self.graphs, production_spec=self.specification, reference_selection=combined)
        missing = copy.deepcopy(combined)
        missing['selected_references'].pop()
        self.assertFalse(validate_artifact(finalize_artifact(missing))['ok'])
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            combine_reference_selections(selections, selection_id='SEL-OMISSION',
                reference_order=[{'subject_id': 'C01', 'binding_id': 'BIND-local'}])

    def binding_pool(self):
        from reference_runtime_smoke_test import _fixture_png
        directory = tempfile.TemporaryDirectory(prefix='cpb-subject-bindings-')
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'source.png'
        path.write_bytes(_fixture_png())
        bindings = []
        for graph in self.graphs:
            subject = graph['identity_contract']['character_id']
            bindings.append(finalize_artifact({
                'artifact_type': 'state-aware-reference-binding', 'binding_id': 'BIND-local',
                'role': 'identity', 'character_id': subject,
                'source': {'kind': 'supplied-file', 'reference_id': subject.lower(),
                    'resolved_path': str(path), 'media_type': 'image/png',
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
                'identity_contract_sha256': artifact_hash(graph['identity_contract']),
                'era_contract_sha256': None, 'appearance_variant_sha256': None,
                'state_snapshot_sha256': artifact_hash(graph['state_snapshot']),
                'effective_story_range': {'from_order': 0, 'to_order': None},
                'visibly_supported_state': ['left-ear-anchor'], 'unsupported_or_occluded_state': [],
                'intended_influence': ['identity'], 'unsupported_assumptions': [], 'review_dimensions': [],
                'subject_uses': [{'subject_id': subject, 'use': 'identity', 'priority': 0}],
            }))
        for binding in bindings:
            report = validate_artifact(binding)
            self.assertTrue(report['ok'], report['errors'])
        return bindings

    def select_binding_pool(self, bindings, graph):
        subject = graph['identity_contract']['character_id']
        return select_state_references(bindings, selection_id='SEL-' + subject, subject_id=subject,
            identity_hash=artifact_hash(graph['identity_contract']), era_hash=None, appearance_hash=None,
            state_hash=artifact_hash(graph['state_snapshot']), story_order=graph['state_snapshot']['story_order'],
            required_features=['left-ear-anchor'], limit=None)

    def test_binding_pool_keeps_local_ids_within_each_subject(self):
        bindings = self.binding_pool()
        selections = []
        for graph, binding in zip(self.graphs, bindings, strict=True):
            subject = graph['identity_contract']['character_id']
            with self.subTest(subject=subject):
                selection = self.select_binding_pool(bindings, graph)
                self.assertEqual(len(selection['selected_references']), 1)
                row = selection['selected_references'][0]
                self.assertEqual((row['subject_id'], row['binding_id']), (subject, 'BIND-local'))
                self.assertEqual(row['source'], binding['source'])
                self.assertEqual(row['subject_uses'], binding['subject_uses'])
                self.assertEqual(selection['unresolved_requirements'], [])
                selections.append(selection)
        combined = combine_reference_selections(selections, selection_id='SEL-SHARED-POOL')
        self.assertTrue(validate_artifact(combined)['ok'])
        self.assertEqual([(row['subject_id'], row['binding_id']) for row in combined['selected_references']],
                         [('C01', 'BIND-local'), ('C03', 'BIND-local')])

    def test_binding_pool_rejects_repeated_ids_within_one_subject(self):
        bindings = self.binding_pool()
        duplicate = copy.deepcopy(bindings[0])
        duplicate['source']['reference_id'] = 'another-source'
        duplicate = finalize_artifact(duplicate)
        with self.assertRaisesRegex(ValueError, 'binding IDs must be unique'):
            self.select_binding_pool([*bindings, duplicate], self.graphs[0])

    def test_unresolved_requirements_name_each_subject_and_feature(self):
        selections = [self.select_binding_pool([], graph) for graph in self.graphs]
        selection = combine_reference_selections(selections, selection_id='SEL-UNRESOLVED')
        report = validate_artifact(selection)
        self.assertTrue(report['ok'], report['errors'])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'prepared'
            with self.assertRaises(ValueError) as raised:
                prepare_state_reference_selection(selection, model='synthetic-model', output_dir=output)
            self.assertEqual(str(raised.exception),
                'reference-selection has unresolved requirements and cannot be prepared: '
                'C01: left-ear-anchor, C03: left-ear-anchor')
            self.assertFalse(output.exists())

    def test_binding_pool_reports_malformed_character_ids(self):
        bindings = self.binding_pool()
        malformed = copy.deepcopy(bindings[1])
        malformed['binding_id'] = 'BIND-malformed'
        malformed['character_id'] = []
        malformed = finalize_artifact(malformed)
        self.assertFalse(validate_artifact(malformed)['ok'])
        with self.assertRaisesRegex(ValueError, 'invalid reference binding'):
            self.select_binding_pool([bindings[0], malformed], self.graphs[0])

    def direct_reference_scene(self):
        from reference_runtime_smoke_test import _fixture_png
        directory = tempfile.TemporaryDirectory(prefix='cpb-mixed-direct-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        path = root / 'source.png'; path.write_bytes(_fixture_png())
        source = {'kind': 'supplied-file', 'reference_id': 'source-a', 'resolved_path': str(path)}
        committed = prepare_references([{'role': 'identity', 'source': source}],
            model='gpt-image-2.5-flare', output_dir=root / 'commit')
        selection = selection_for(self.graphs[0], feature='left-ear-anchor')
        selection['selected_references'][0]['source'] = committed['selected_references'][0]['source']
        selection = finalize_artifact(selection)
        direct = [{'role': use, 'source': {**source, 'reference_id': 'source-b'},
                   'subject_uses': [{'subject_id': 'B', 'use': use, 'priority': 0}]}
                  for use in ('identity', 'outfit')]
        return root, selection, direct

    def test_state_selection_covers_only_its_managed_reference_rows(self):
        from reference_delivery import attachment_numbers
        root, selection, direct = self.direct_reference_scene()
        prepared = prepare_state_reference_selection(selection, model='gpt-image-2.5-flare',
            output_dir=root / 'mixed', additional_references=direct)
        rows = prepared['selected_references']
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['subject_id'], 'C01')
        self.assertTrue(all('subject_id' not in row for row in rows[1:]))
        self.assertEqual([row['subject_uses'][0]['subject_id'] for row in rows], ['C01', 'B', 'B'])
        self.assertEqual(attachment_numbers(rows), [1, 1, 1])
        self.assertEqual(prepared['reference_selection'], selection)
        self.assertNotEqual(rows[0]['source'], rows[1]['source'])

    def test_generic_reference_cannot_target_a_state_managed_subject(self):
        root, selection, direct = self.direct_reference_scene()
        direct[0]['subject_uses'][0]['subject_id'] = 'C01'
        with self.assertRaisesRegex(ValueError, 'state-managed subject requires its exact state scope'):
            prepare_state_reference_selection(selection, model='gpt-image-2.5-flare',
                output_dir=root / 'invalid', additional_references=direct)

    def test_removing_state_fields_cannot_downgrade_the_source(self):
        root, selection, direct = self.direct_reference_scene()
        prepared = prepare_state_reference_selection(selection, model='gpt-image-2.5-flare',
            output_dir=root / 'mixed', additional_references=direct)
        original = prepared['selected_references'][0]
        generic = {key: copy.deepcopy(original[key]) for key in ('role', 'source', 'transport', 'authority')}
        with self.assertRaisesRegex(ValueError, 'cannot be downgraded'):
            validate_prepared_references([*prepared['selected_references'], generic],
                model='gpt-image-2.5-flare', reference_selection=selection)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
