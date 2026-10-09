#!/usr/bin/env python3
"""State eligibility and board delivery with genuine synthetic Studio adoption evidence."""
from __future__ import annotations
import copy
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import execution_contract as c
import studio_reference as sr
import studio_reference_fixtures as fixture
import prepare_generation_references as refs
import state_protocol as state
from production_fixtures import scratch_home_dir


class StudioStateTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.adopted_case(self)
        self.root = self.case.root
        self.source = sr.current_source(self.root,'robot',self.case.row['slot'])
        from catalog_retrieval.runtime import configure_pack_runtime
        configure_pack_runtime(None)
        from state_generation_smoke_test import _load_graph
        self.graph = _load_graph()
        self.scope = fixture.scope()
        self.out = self.root / 'state-reference-output'; self.out.mkdir()

    def binding(self):
        return sr.build_binding(self.root,'robot',self.case.row['slot'],scope=self.scope,
            identity=self.graph['identity_contract'], snapshot=self.graph['state_snapshot'])

    def selection(self):
        graph = self.graph
        return state.select_state_references([self.binding()],selection_id='SEL-STUDIO',
            identity_hash=state.artifact_hash(graph['identity_contract']),era_hash=None,appearance_hash=None,
            state_hash=state.artifact_hash(graph['state_snapshot']),story_order=graph['state_snapshot']['story_order'],
            required_features=['identity-anchor'],limit=1)

    def prepared(self, *, mode='multi-image'):
        return refs.prepare_state_reference_selection(self.selection(),model='gpt-image-2.5-flare',
            output_dir=self.out / 'images',transport_mode=mode)

    def packaged(self):
        from build_generation_payload import materialize_cli_reference_bundle
        self.package_root = self.out/'package'; self.package_root.mkdir()
        prepared, _ = materialize_cli_reference_bundle(self.prepared(),model='gpt-image-2.5-flare',
            source_root=self.out,staging_root=self.package_root,companion_name='package.references')
        return prepared

    def payload(self):
        from state_generation_smoke_test import _payload_inputs
        from request_validation_fixtures import fixture_validation
        from reading_fixtures import fixture_reading
        from build_state_generation_package import build_package
        import visual_continuity as vc
        graph = copy.deepcopy(self.graph)
        graph['production_spec']['render_intent']['execution_mode']='reference-guided'
        prepared = self.packaged()
        visual = vc.from_decisions({'C01':'recurring'},production_spec=graph['production_spec'],prepared=prepared,
            root=self.root,characters={'C01':'robot'},work_ids={'C01':'C01'})
        inputs = _payload_inputs(graph)
        inputs.update(input_root=self.root,
            request_validation=fixture_validation(self.root,'gpt-image-2.5-flare',reference_mode='prompt-prefix'),
            parameters={'width':1024,'height':1024,'settings':{'quality':'high'}})
        return build_package(**inputs,visual_continuity=visual,visual_root=self.root,
            route_reading=fixture_reading(route='state-series'),prepared_reference_set=prepared,prepared_reference_root=self.package_root)

    def test_binding_reads_hashes_and_preserves_authored_scope(self):
        binding = self.binding()
        self.assertEqual(binding['source'], self.source)
        self.assertEqual(binding['identity_contract_sha256'],state.artifact_hash(self.graph['identity_contract']))
        for key, value in self.scope.items(): self.assertEqual(binding[key],value)
        self.assertTrue(state.validate_artifact(binding)['ok'])

    def test_binding_accepts_an_explicit_directory_inside_its_studio(self):
        self.assertEqual(sr.build_binding(self.root/'characters/robot','robot',self.case.row['slot'],
            scope=self.scope,identity=self.graph['identity_contract'],snapshot=self.graph['state_snapshot']),self.binding())

    def test_wrong_work_character_is_rejected(self):
        graph = copy.deepcopy(self.graph['identity_contract'])
        graph['character_id']='another'; graph=state.finalize_artifact(graph)
        with self.assertRaisesRegex(ValueError,'another work character'):
            sr.build_binding(self.root,'robot',self.case.row['slot'],scope=self.scope,identity=graph)

    def test_out_of_range_binding_is_not_selected(self):
        self.scope['effective_story_range']={'from_order':1000,'to_order':2000}
        selection=self.selection()
        self.assertEqual(selection['selected_references'],[])
        self.assertEqual(selection['unresolved_requirements'],['identity-anchor'])

    def test_candidate_binding_cannot_be_finalized(self):
        with self.assertRaisesRegex(ValueError,'no current accepted'):
            sr.build_binding(self.root,'robot','unaccepted',scope=self.scope,identity=self.graph['identity_contract'])

    def test_pending_studio_adoption_cannot_be_used(self):
        path=self.root/'characters/robot/adoptions'/f"{self.case.row['iteration_id']}.json"
        data=c.load(path); data['next_action']='bind-sheet';c.atomic_write_json(path,data)
        with self.assertRaisesRegex(ValueError,'incomplete'):
            sr.validate_source(self.source)

    def test_selection_rechecks_adoption_before_preparation(self):
        selection=self.selection()
        path=self.root/'characters/robot/sheet/sheet-data.json';data=c.load(path);data['slots'][self.case.row['slot']]['current']=None
        from character_sheet import sheet_status
        data['sheet_status']=sheet_status(data);c.atomic_write_json(path,data)
        with self.assertRaisesRegex(ValueError,'no current accepted'):
            refs.prepare_state_reference_selection(selection,model='gpt-image-2.5-flare',output_dir=self.out/'images')

    def test_direct_state_preparation_keeps_state_scope(self):
        prepared=self.prepared()
        self.assertIsNone(prepared['reference_use_plan'])
        self.assertEqual(prepared['selected_references'][0]['source'],self.source)
        self.assertEqual(prepared['selected_references'][0]['intended_influence'],['identity'])
        self.assertIn('current-clothing',prepared['selected_references'][0]['unsupported_or_occluded_state'])

    def test_state_selection_can_use_one_explicit_board(self):
        prepared=self.prepared(mode='single-board')
        self.assertEqual(prepared['transport_mode'],'single-board')
        panel=prepared['single_board']['panels'][0]
        self.assertEqual(panel['source_sha256'],self.source['sha256'])
        self.assertEqual(panel['transport_sha256'],prepared['selected_references'][0]['transport']['sha256'])

    def test_state_package_build_and_live_verify(self):
        from build_state_generation_package import verify_package
        package=self.payload()
        self.assertTrue(verify_package(package,package_root=self.package_root,studio=self.root)['verified'])
        ref=package['visual_continuity']['subjects']['C01']['identity_refs'][0]
        self.assertEqual(ref['kind'],'studio-artifact')
        self.assertEqual(ref['proof_sha256'],self.source['proof_sha256'])

    def test_package_replay_survives_source_removal_but_live_verify_stops(self):
        from verify_generation_payload import verify,verify_content
        package=self.payload()
        # Remove only original source/proof bytes, not the owned package companion.
        shutil.rmtree(self.root/'characters/robot/sheet/.fills')
        result=verify_content(package,package_root=self.package_root)
        self.assertTrue(result['content_verified'])
        with self.assertRaises((ValueError,OSError)):verify(package,package_root=self.package_root,studio=self.root)

    def test_binding_file_can_be_selected_without_copying_hashes(self):
        import select_state_references as selector
        for filename, data in [('binding.json',self.binding()),('identity.json',self.graph['identity_contract']),
                               ('snapshot.json',self.graph['state_snapshot'])]:
            c.atomic(self.out/filename,c.encoded(data))
        args=['--binding',str(self.out/'binding.json'),'--selection-id','SEL-CLI',
              '--identity-contract',str(self.out/'identity.json'),'--state-snapshot',str(self.out/'snapshot.json'),
              '--story-order',str(self.graph['state_snapshot']['story_order']),
              '--required-feature','identity-anchor','--out',str(self.out/'selection.json')]
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(selector.main(args),0)
        selected=c.load(self.out/'selection.json')
        self.assertEqual(selected['selected_references'][0]['source'],self.source)
        self.assertEqual(selected['unresolved_requirements'],[])

    def test_duplicate_binding_ids_are_not_an_ambiguous_order(self):
        binding=self.binding()
        with self.assertRaisesRegex(ValueError,'IDs must be unique'):
            state.select_state_references([binding,binding],selection_id='DUPLICATE',
                identity_hash=state.artifact_hash(self.graph['identity_contract']),era_hash=None,appearance_hash=None,
                state_hash=state.artifact_hash(self.graph['state_snapshot']),story_order=1,required_features=[],limit=2)

    def test_binding_cli_uses_explicit_scope_and_actual_contracts(self):
        for filename,data in [('scope.json',self.scope),('identity.json',self.graph['identity_contract']),('snapshot.json',self.graph['state_snapshot'])]:
            c.atomic(self.out/filename,c.encoded(data))
        args=['--studio',str(self.root),'--character','robot','--slot',self.case.row['slot'],'bind',
              '--scope',str(self.out/'scope.json'),'--identity-contract',str(self.out/'identity.json'),
              '--state-snapshot',str(self.out/'snapshot.json'),'--out',str(self.out/'binding.json')]
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(sr.main(args),0)
        self.assertEqual(c.load(self.out/'binding.json'),self.binding())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    with tempfile.TemporaryDirectory(prefix='cpb-state-studio-home-') as home:
        scratch_home_dir(Path(home))
        unittest.main()
