#!/usr/bin/env python3
"""Package state-bound pack references beside independently adopted Studio sources.

C01 and C02 are synthetic scene subjects. Local transport fixtures create PNG
test data and real adoption records; no provider or image model is invoked.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import catalog_cli
import execution_contract as c
import pack_manager
import production_case_fixtures as production_fixture
import production_execution
import production_fixtures
import production_spec
import production_workflow
import studio
import studio_reference
import studio_reference_fixtures
import visual_continuity
from build_generation_payload import materialize_cli_reference_bundle
from build_state_generation_package import build_package
from multi_subject_reference_smoke_test import replace_values, selection_for
from reading_fixtures import fixture_reading
from reference_contract import state_authority_for
from reference_delivery import delivered_reference_count
from reference_runtime import build_reference_use_plan, execute_reference_use_plan
from reference_runtime_smoke_test import FIXTURE_PACK_ID, FIXTURE_RECORD_ID, _write_fixture_pack
from request_validation_fixtures import fixture_validation
from smoke_fixtures import fixture_retrieval
from state_generation_smoke_test import _load_graph, _payload_inputs
from state_protocol import artifact_hash, finalize_artifact
from test_production_execution import decisions
from verify_generation_payload import verify, verify_content


ROOT = Path(__file__).resolve().parents[1]
MODEL = 'gpt-image-2.5-flare'
LISTENER = 'C02'


def adopt_wardrobe(case) -> dict:
    """Adopt a second exact image in the same character's wardrobe slot."""
    task_path, _ = studio_reference_fixtures.reference_task(case)
    task = c.load(case.root / task_path)
    task['recording'].update(slot='outfit.turn.front', sheet_panel=True)
    production_fixture.write(case.root / task_path, task)
    run = production_workflow.prepare(case.root, task_path)['run']
    result = production_execution.execute(case.root, run, decisions_file=decisions(case.root, run))
    candidate = result['runs'][0]['candidates'][0]
    row = next(item for item in studio.read_iterations(studio.character_home(case.root, 'robot'))
               if item['production']['run'] == run)
    review = production_workflow.draft_review(case.root, run, candidate)
    review.update(reviewer='Synthetic fixture reviewer', conclusion='Synthetic wardrobe source accepted.',
        observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
            'observation': 'The separate local fixture PNG exists.',
            'interpretation': 'A second source exercises wardrobe provenance.',
            'limitations': ['No image-quality or real author acceptance is asserted.']}])
    for check in review['checks']:
        check.update(verdict='pass', observation_indices=[0], reason='Synthetic source assessment.')
    production_fixture.write(case.root / 'wardrobe-review.json', review)
    production_workflow.review(case.root, run, 'wardrobe-review.json')
    selection = production_workflow.draft_selection(case.root, run, candidate)
    selection['reason'] = 'Synthetic choice of the separate wardrobe source.'
    production_fixtures.selection(case.root, run, selection)
    production_fixture.write(case.root / 'wardrobe-selection.json', selection)
    production_workflow.select(case.root, run, 'wardrobe-selection.json')
    approval = copy.deepcopy(case.approval)
    approval.update(iteration_id=row['iteration_id'], slot=row['slot'], image_sha256=row['result']['sha256'])
    production_fixture.write(case.root / 'wardrobe-approval.json', approval)
    intent = production_workflow.adoption_intent(case.root, run, candidate, 'robot', row['iteration_id'], approval)
    authorization = production_fixtures.grant(case.root, run, intent)
    production_workflow.adopt(case.root, run, candidate, 'robot', row['iteration_id'],
                              'wardrobe-approval.json', authorization)
    return studio_reference.current_source(case.root, 'robot', row['slot'])


class MixedReferenceSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cpb-mixed-reference-sources-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(self.work / 'home'))
        self.case = studio_reference_fixtures.adopted_case(self, work_id=LISTENER)
        self.root = self.case.root
        self.face = studio_reference.current_source(self.root, 'robot', self.case.row['slot'])
        self.wardrobe = adopt_wardrobe(self.case)
        self.addCleanup(catalog_cli.configure_pack_runtime, None)

        pack = _write_fixture_pack(self.work)
        runtime = Path(self.case.temp.name) / 'runtime'
        settings = pack_manager.PackSettings(
            roots=((ROOT / 'packs/commons').resolve(),),
            state_file=runtime / 'state.json', cache_dir=runtime / 'cache',
            managed_root=runtime / 'managed', quarantine_root=runtime / 'managed/.quarantine')
        state = c.load(settings.state_file)
        state['enabled_packs'].remove(production_fixture.PACK_ID)
        state['pack_order'].remove(production_fixture.PACK_ID)
        state['pack_roots'].append(str(pack))
        state['enabled_packs'].append(FIXTURE_PACK_ID)
        pack_manager.save_state(settings.state_file, state)
        catalog_cli.configure_pack_runtime(settings)

    def scene(self):
        graph = _load_graph()
        spec = graph.pop('production_spec')
        spec['render_intent']['execution_mode'] = 'reference-guided'
        spec['render_intent']['presentation'] = 'one shared scene across a desk'
        spec['scene']['support_and_contact'] += '; C02 listens from the other side of the desk'
        spec['camera']['shot_type'] = 'two-character office conversation'
        spec['camera']['framing_and_crop'] = (
            'Both faces, upper torsos, C01 gesturing with the free hand, and the desk remain visible.')
        spec['camera']['required_visible_elements'].extend(['C02 face', 'C02 approved wardrobe'])
        spec['camera']['stability_invariants'] = [
            'Both characters remain visible across the desk.',
            'Identity ratios remain stable while C01 gestures and C02 listens.',
            'The desk contact and free-hand gesture remain readable.']
        spec['subjects'][0]['performance']['prompt_projection']['supporting_clauses'].append(
            'C01 speaks to C02 while making a small gesture with the free hand.')
        listener = production_spec.draft(model=MODEL, brief='Synthetic listener in a shared office scene.',
            subject=LISTENER, kind='robot', render_intent=spec['render_intent'])['subjects'][0]
        listener['identity'] = ['C02 retains its independently approved face and physique.']
        listener['pose_and_body_geometry'] = 'C02 listens attentively to C01 across the desk.'
        listener['gaze_and_head'] = 'C02 looks toward the speaking C01 with an attentive expression.'
        listener['wardrobe_and_accessories'] = 'Preserve C02 wardrobe from its separate approved source.'
        spec['subjects'].append(listener)
        old_render = artifact_hash(graph['asset_render_spec'])
        for field in ('target_model', 'art_direction', 'scene', 'camera', 'lighting', 'selected_preset_ids'):
            graph['asset_render_spec'][field] = copy.deepcopy(spec[field])
        graph['asset_render_spec'] = finalize_artifact(graph['asset_render_spec'])
        old_lineage = artifact_hash(graph['lineage'])
        graph['lineage'] = finalize_artifact(replace_values(graph['lineage'],
            {old_render: artifact_hash(graph['asset_render_spec'])}))
        spec = replace_values(spec, {old_lineage: artifact_hash(graph['lineage'])})
        return graph, spec

    def test_mixed_subjects_keep_all_sources_through_portable_package(self):
        graph, spec = self.scene()
        plan = build_reference_use_plan([
            {'record_id': FIXTURE_RECORD_ID, 'intended_influence': use,
             'subject_uses': [{'subject_id': 'C01', 'use': use, 'priority': 0}]}
            for use in ('identity', 'outfit')], transport_mode='multi-image', target_model=MODEL,
            source_lighting_mode='replace', include_technical_roles=['faithful-archival-vector'],
            light_sources=[{'light_id': 'office-window', 'direction': 'camera right',
                'apparent_size': 'large', 'color': 'warm daylight', 'relative_intensity': 'primary',
                'softness': 'soft'}],
            material_responses=[{'material': 'character and wardrobe surfaces', 'roughness': 'matte',
                'specular_strength': 'low', 'highlight_shape': 'broad and soft', 'wetness': 'dry',
                'anisotropy': 'none'}])
        self.assertEqual(len(plan['reference_items']), 2)
        self.assertEqual(plan['reference_items'][0]['source'], plan['reference_items'][1]['source'])
        selection = selection_for(graph)
        selection['selected_references'] = [
            {'subject_id': 'C01', 'binding_id': 'BIND-A-' + item['intended_influence'],
             'role': item['intended_influence'], 'source': copy.deepcopy(item['source']), 'covers': [],
             'intended_influence': [item['intended_influence']], 'review_dimensions': [item['intended_influence']],
             'unsupported_or_occluded_state': [], 'unsupported_assumptions': [],
             'subject_uses': copy.deepcopy(item['subject_uses'])} for item in plan['reference_items']]
        selection = finalize_artifact(selection)
        additional = [
            {'role': 'identity', 'source': self.face,
             'subject_uses': [{'subject_id': LISTENER, 'use': 'identity', 'priority': 0}]},
            {'role': 'outfit', 'source': self.wardrobe,
             'subject_uses': [{'subject_id': LISTENER, 'use': 'outfit', 'priority': 0}]}]
        prepared = execute_reference_use_plan(plan, output_dir=self.work / 'references',
            reference_selection=selection, additional_references=additional, max_side=128)
        self.assertEqual(len(prepared['selected_references']), 4)
        self.assertEqual(delivered_reference_count(prepared), 3)
        self.assertNotEqual(self.face['sha256'], self.wardrobe['sha256'])
        self.assertEqual(prepared['reference_use_plan'], plan)
        self.assertEqual(prepared['reference_selection'], selection)
        for index, source in ((2, self.face), (3, self.wardrobe)):
            row = prepared['selected_references'][index]
            self.assertEqual(row['source'], source)
            self.assertNotIn('subject_id', row)
            self.assertEqual(row['subject_uses'], additional[index - 2]['subject_uses'])
            self.assertEqual(row['authority'], state_authority_for([row['subject_uses'][0]['use']]))
        self.assertEqual([row['subject_id'] for row in selection['subjects']], ['C01'])
        self.assertNotIn('state_snapshot_ref', spec['subjects'][1])

        package_root = self.work / 'package'
        package_root.mkdir()
        portable, companion = materialize_cli_reference_bundle(prepared, model=MODEL,
            source_root=self.work / 'references', staging_root=package_root,
            companion_name='scene.references')
        self.assertIsNotNone(companion)
        visual = visual_continuity.from_decisions({'C01': 'one-off', LISTENER: 'recurring'},
            production_spec=spec, prepared=portable, root=self.root,
            characters={LISTENER: 'robot'}, work_ids={LISTENER: LISTENER})
        inputs = _payload_inputs(_load_graph())
        scene_clause = ('\nC01 and C02 converse across the desk in one shared scene. '
            'C01 gestures with the free hand while C02 listens attentively. '
            'Keep both independent identities, physiques and approved wardrobes; show both faces and upper torsos.\n')
        inputs['prompt'] += scene_clause
        inputs['integrated_prompt'] += scene_clause
        inputs.update(production_spec=spec, state_graphs=[graph], prepared_reference_set=portable,
            prepared_reference_root=package_root, input_root=self.root,
            parameters={'width': 1024, 'height': 1024, 'settings': {'quality': 'high'}},
            request_validation=fixture_validation(self.root, MODEL, reference_mode='authored-rendition'),
            visual_continuity=visual, visual_root=self.root,
            route_reading=fixture_reading(route='state-series', studio=self.root,
                                         ledger=self.root / 'work/mixed-reference-reads.jsonl'))
        inputs['retrieval_record'] = fixture_retrieval(inputs['prompt'], inputs['plot'])
        package = build_package(**inputs)
        self.assertTrue(verify(package, package_root=package_root, studio=self.root)['verified'])
        self.assertTrue(verify_content(package, package_root=package_root)['content_verified'])
        final = package['prepared_reference_set']
        self.assertEqual([row['source'] for row in final['selected_references']],
                         [row['source'] for row in prepared['selected_references']])
        self.assertEqual([row['subject_uses'] for row in final['selected_references']],
                         [row['subject_uses'] for row in prepared['selected_references']])
        self.assertEqual([row['identity_contract']['character_id'] for row in package['state_graphs']], ['C01'])
        self.assertEqual(package['visual_continuity']['subjects'][LISTENER]['identity_refs'][0]['proof_sha256'],
                         self.face['proof_sha256'])
        for source in (self.face, self.wardrobe):
            archive = package_root / 'scene.references/studio' / source['proof_sha256'] / 'proof.json'
            self.assertTrue(archive.is_file())
        from reference_delivery import bindings
        self.assertEqual(bindings(final['transport_mode'], final['selected_references'], final['single_board']),
                         bindings(prepared['transport_mode'], prepared['selected_references'], prepared['single_board']))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
