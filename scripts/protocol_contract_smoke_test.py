#!/usr/bin/env python3
"""Current public-contract and public-artifact conformance tests.

Conformance uses explicitly supplied protocol artifacts and the bundled validator.
Synthetic samples validate shape and commitments, not media or author approval.
"""
from __future__ import annotations
import argparse
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import protocol_contract as pc
import protocol_exchange as exchange
import temporal_state as temporal
import state_protocol as state
import shot_request as shot
import viewpoint_protocol as viewpoint

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'examples/protocol-exchange'
FIXTURES=EXAMPLE/'fixtures'
SCENE=EXAMPLE/'scene'


def fixture(kind):return pc.load_json(FIXTURES/(kind+'.json'))


def event(eid='EV-TEST',order=1,value='bright',persistence='persistent-until-superseded',**change):
    data=fixture('state-event')
    data.update(event_id=eid,timeline_id='main',event_scope='environment-state',targets=['room'],
                effective_order=order,effective_from=f'story:{order}',canon_status='approved',atomic=False,
                cause={'type':'synthetic test','reference':'protocol conformance fixture'},preconditions=[],
                evidence=[{'type':'synthetic fixture','reference':'not user approval'}],supersedes_event_ids=[],
                occurrence='offscreen',changes=[{'entity_type':'environment','entity_id':'room','path':'/light','operation':'set','value':value,'persistence':persistence,**change}])
    data.pop('scene_context_id',None)
    return data


def world(events,order=5,scene='room',processes=None):
    return temporal.resolve_world(base_state={'environments':{'room':{'light':'dim'}}},events=events,processes=processes or [],timeline_id='main',story_order=order,story_time=f'story:{order}',snapshot_id=f'world-{order}',scene_context_id=scene)


def bundle_args():
    return dict(species_profile_files={cid:SCENE/'source'/f'species-morphology-{cid}.json' for cid in ('C01','C02')},
                individual_morphology_files={cid:SCENE/'source'/f'individual-morphology-{cid}.json' for cid in ('C01','C02')},
                identity_files={cid:SCENE/'source'/f'character-identity-{cid}.json' for cid in ('C01','C02')},
                state_files={cid:SCENE/'generated'/f'character-state-snapshot-{cid}.json' for cid in ('C01','C02')},
                scene_context=SCENE/'generated/scene-context-snapshot.json')


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='public-contract-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def save(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(exchange.encoded(value));return p
    def assertValid(self,value):
        report=pc.validate_artifact(value);self.assertTrue(report['ok'],report)
    def test_complete_installed_closure(self):
        report=exchange.check_installed();self.assertTrue(report['ok']);self.assertEqual(report['public_artifacts'],len(pc.ARTIFACT_TYPES))
    def test_every_public_root_has_current_fixture(self):
        index=pc.load_json(EXAMPLE/'fixture-index.json')
        self.assertEqual({r['artifact_type'] for r in index['artifacts']},pc.ARTIFACT_TYPES)
        for row in index['artifacts']:
            with self.subTest(kind=row['artifact_type']):self.assertValid(pc.load_json(EXAMPLE/row['path']))
    def test_every_public_root_roundtrips(self):
        for i,kind in enumerate(sorted(pc.ARTIFACT_TYPES)):
            with self.subTest(kind=kind):
                self.save('input.json',fixture(kind));result=exchange.export(self.root,'input.json',f'out/{i}')
                report=exchange.verify_bundle(self.root,f'out/{i}');self.assertEqual(result['artifact_sha256'],report['artifact_sha256']);self.assertFalse(report['canonical_adoption'])
    def test_nested_refs_and_ref_siblings(self):
        schema={'$defs':{'value':{'type':'string'}},'$ref':'#/$defs/value','minLength':3}
        self.assertTrue(pc.validate_against_schema('a',schema));self.assertEqual(pc.validate_against_schema('abc',schema),[])
        self.assertEqual(pc.validate_against_schema(fixture('character-identity-contract')['stable_identity']['frame_character'],pc.schema_named('frame-character.schema.json')),[])
    def test_strict_json_input(self):
        for text in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}']:
            with self.subTest(text=text),self.assertRaises(ValueError):pc.parse_json(text)
    def test_hash_is_shared_between_wrappers(self):
        for kind in pc.ARTIFACT_TYPES:
            value=fixture(kind)
            self.assertEqual(state.artifact_hash(value),viewpoint.artifact_hash(value));self.assertEqual(state.finalize_artifact(value),pc.finalize_artifact(value))
    def test_tampered_artifact(self):
        value=fixture('world-state-snapshot');value['story_time']='changed';self.assertFalse(pc.validate_artifact(value)['ok'])
    def test_manifest_byte_tampering(self):
        self.save('input.json',fixture('state-event'));exchange.export(self.root,'input.json','out')
        with (self.root/'out/artifact.json').open('ab') as f:f.write(b' ')
        with self.assertRaises(ValueError):exchange.verify_bundle(self.root,'out')
    def test_substituted_contract_even_with_new_transport_hash(self):
        self.save('input.json',fixture('state-event'));exchange.export(self.root,'input.json','out')
        value=pc.load_json(self.root/'out/contract.json');value['schemas'][0]['sha256']='a'*64;self.save('out/contract.json',value)
        m=pc.load_json(self.root/'out/manifest.json');m['files'][1]['sha256']=exchange.digest((self.root/'out/contract.json').read_bytes());self.save('out/manifest.json',m)
        with self.assertRaises(ValueError):exchange.verify_bundle(self.root,'out')
    def test_extra_bundle_member(self):
        self.save('input.json',fixture('state-event'));exchange.export(self.root,'input.json','out');self.save('out/private.json',{})
        with self.assertRaises(ValueError):exchange.verify_bundle(self.root,'out')
    def test_symlink_and_traversal_boundary(self):
        self.save('input.json',fixture('state-event'));(self.root/'alias.json').symlink_to(self.root/'input.json')
        for name in ['alias.json','../input.json']:
            with self.subTest(name=name),self.assertRaises(ValueError):exchange.inspect_artifact(self.root,name)
    def test_export_does_not_overwrite(self):
        self.save('input.json',fixture('state-event'));exchange.export(self.root,'input.json','out')
        with self.assertRaises(ValueError):exchange.export(self.root,'input.json','out')
    def test_source_is_not_fetched_by_exchange(self):
        value=fixture('state-aware-reference-binding');value['source']={'kind':'supplied-file','reference_id':'unavailable','resolved_path':'/sender-only/no-file.png','media_type':'image/png','sha256':'b'*64}
        value=pc.finalize_artifact(value);self.save('input.json',value);exchange.export(self.root,'input.json','out')
        self.assertFalse(exchange.verify_bundle(self.root,'out')['referenced_media_verified'])
    def test_scene_local_state_does_not_leak(self):
        e=event(persistence='scene-local');e['scene_context_id']='A'
        self.assertEqual(world([e],scene='A')['entities']['environments']['room']['light'],'bright')
        self.assertEqual(world([e],scene='B')['entities']['environments']['room']['light'],'dim')
    def test_individual_change_expiry_is_exclusive(self):
        e=event(order=1,persistence='temporary-until-cleared',effective_until_order=5)
        self.assertEqual(world([e],order=4)['entities']['environments']['room']['light'],'bright')
        self.assertEqual(world([e],order=5)['entities']['environments']['room']['light'],'dim')
    def test_non_linear_presentation_does_not_mutate_input(self):
        e=event(order=10);before=copy.deepcopy(e)
        values=[world([e],order=n)['entities']['environments']['room']['light'] for n in (20,5,21)]
        self.assertEqual(values,['bright','dim','bright']);self.assertEqual(e,before)
    def test_unapproved_event_is_not_canon(self):
        e=event();e['canon_status']='proposed';self.assertEqual(world([e])['entities']['environments']['room']['light'],'dim')
    def test_atomic_failure_preserves_world(self):
        data={'environments':{'room':{'light':'dim'}},'props':{}};before=copy.deepcopy(data);e=event()
        e['atomic']=True;e['preconditions']=[{'entity_type':'environment','entity_id':'room','path':'/light','operator':'equals','value':'wrong'}]
        with self.assertRaises(ValueError):temporal.apply_event(data,e)
        self.assertEqual(data,before)
    def test_editorial_supersession_is_explicit(self):
        a=event('EV-A',1,'bright');b=event('EV-B',2,'blue');b.update(event_scope='editorial-revision',occurrence='editorial',supersedes_event_ids=['EV-A'])
        self.assertEqual(world([a,b])['entities']['environments']['room']['light'],'blue')
        self.assertNotIn('EV-A',world([a,b])['applied_event_ids'])
    def test_process_interrupt_and_restart(self):
        process=fixture('state-process');process.update(process_id='PROC-LAMP',entity_type='environment',entity_id='room',path='/light',timeline_id='main',started_order=1,effective_until_order=None,interruption_policy='restartable',canon_status='approved',evidence=[{'type':'synthetic test'}],milestones=[{'offset':0,'state':'warming','label':'start'},{'offset':2,'state':'bright','label':'lit'}])
        start=event('EV-START',1,'warming',persistence='progressive',process_id='PROC-LAMP')
        def life(eid,n,op):
            v=event(eid,n);v['changes']=[{'entity_type':'environment','entity_id':'room','path':'/light','operation':op,'process_id':'PROC-LAMP'}];return v
        events=[start,life('EV-PAUSE',2,'interrupt-process'),life('EV-RESUME',4,'restart-process')]
        for order,expected in [(2,'warming'),(5,'warming'),(6,'bright')]:
            with self.subTest(order=order):self.assertEqual(world(events,order=order,processes=[process])['entities']['environments']['room']['light'],expected)
    def test_context_matches_exact_world(self):
        req=pc.load_json(SCENE/'source/scene-context-request.json');w=pc.load_json(SCENE/'generated/world-state-snapshot.json');snaps=[pc.load_json(p) for p in sorted((SCENE/'generated').glob('character-state-snapshot-*.json'))]
        self.assertValid(state.build_scene_context(req,w,snaps))
        changed=copy.deepcopy(snaps);changed[0]['story_order']+=1;changed[0]=pc.finalize_artifact(changed[0])
        with self.assertRaises(ValueError):state.build_scene_context(req,w,changed)
        changed=copy.deepcopy(snaps);changed[0]['performance_state']['unapproved']='change';changed[0]=pc.finalize_artifact(changed[0])
        with self.assertRaises(ValueError):state.build_scene_context(req,w,changed)
    def test_context_duplicate_and_missing_entities(self):
        req=pc.load_json(SCENE/'source/scene-context-request.json');w=pc.load_json(SCENE/'generated/world-state-snapshot.json');snaps=[pc.load_json(p) for p in sorted((SCENE/'generated').glob('character-state-snapshot-*.json'))]
        with self.assertRaises(ValueError):state.build_scene_context(req,w,snaps+[snaps[0]])
        req['prop_ids']=['not-authored']
        with self.assertRaises(ValueError):state.build_scene_context(req,w,snaps)
    def test_projection_materialization_has_bound_lineage(self):
        cid='C01';args=[pc.load_json(SCENE/'source'/f'{name}-{cid}.json') for name in ['character-identity','species-morphology','individual-morphology']]
        snap=pc.load_json(SCENE/'generated/character-state-snapshot-C01.json');ctx=pc.load_json(SCENE/'generated/scene-context-snapshot.json');req=pc.load_json(SCENE/'source/projection-request-C01.json')
        result=state.build_projection(*args,snap,ctx,req,None);self.assertValid(result)
        snap['identity_contract_sha256']='a'*64;snap=pc.finalize_artifact(snap)
        with self.assertRaises(ValueError):state.build_projection(*args,snap,ctx,req,None)
    def test_six_complete_shot_requests(self):
        for p in sorted((SCENE/'generated/shot-requests').glob('*.json')):
            with self.subTest(shot=p.stem):
                args=bundle_args();args.update(camera_spec=SCENE/'generated/shots'/p.name,shot_projection=SCENE/'generated/shot-projections'/p.name)
                report=shot.validate_bundle(pc.load_json(p),**args,require_complete=True);self.assertTrue(report['ok'],report);self.assertTrue(report['complete'])
    def test_missing_binding_is_reported(self):
        args=bundle_args();args.update(camera_spec=None,shot_projection=None)
        report=shot.validate_bundle(fixture('shot-request'),**args)
        self.assertTrue(report['ok'],report);self.assertFalse(report['complete']);self.assertIn('camera-spec',report['unverified_bindings'])
        self.assertFalse(shot.validate_bundle(fixture('shot-request'),**args,require_complete=True)['ok'])
    def test_camera_mismatch_after_valid_rehash(self):
        p=next((SCENE/'generated/shot-requests').glob('*.json'));req=pc.load_json(p);cam=pc.load_json(SCENE/'generated/shots'/p.name)
        cam['scene_id']='another-scene';cam=pc.finalize_artifact(cam);req['camera_spec_sha256']=pc.artifact_hash(cam);req=pc.finalize_artifact(req)
        args=bundle_args();args.update(camera_spec=self.save('camera.json',cam),shot_projection=None)
        self.assertFalse(shot.validate_bundle(req,**args)['ok'])
    def test_cast_free_request_and_camera(self):
        request=fixture('shot-request');camera=fixture('shot-camera-spec');projection=fixture('shot-visual-projection')
        for field in ['species_profile_sha256_by_character','individual_morphology_sha256_by_character','identity_contract_sha256_by_character','state_snapshot_sha256_by_character','visible_morphology_feature_refs_by_character']:request[field]={}
        request['visible_identity_obligations']=[];request['visible_state_obligations']=[]
        camera.update(knowledge_scope='objective',focal_character_ids=[],visible_subjects=[],visible_body_regions={},state_snapshot_sha256_by_character={},camera_owner_character_id=None)
        camera=pc.finalize_artifact(camera);request['camera_spec_sha256']=pc.artifact_hash(camera)
        projection.update(camera_spec_sha256=pc.artifact_hash(camera),state_snapshot_sha256_by_character={},visible_identity_obligations=[],visible_state_obligations=[])
        projection=pc.finalize_artifact(projection);request['shot_projection_sha256']=pc.artifact_hash(projection)
        self.assertValid(camera);self.assertValid(projection);self.assertValid(pc.finalize_artifact(request))
    def test_continuity_prose_is_language_independent(self):
        value=fixture('viewpoint-transition')
        value.update(state_change_event_ids=['EV-AUTHORED'],knowledge_change='none',changes_knowledge_scope=False,
                     continuity_requirements=['Maintain the declared outcome.', 'Preserve the declared camera boundary.'])
        self.assertValid(pc.finalize_artifact(value))
        value['continuity_requirements']=['요구 사항 하나.', '요구 사항 둘.']
        self.assertValid(pc.finalize_artifact(value))
    def test_context_rejects_duplicate_subject_ids(self):
        value=fixture('scene-context-snapshot')
        value['active_character_snapshots'].append(copy.deepcopy(value['active_character_snapshots'][0]))
        self.assertFalse(pc.validate_artifact(pc.finalize_artifact(value))['ok'])
    def test_character_map_membership_is_exact(self):
        req=fixture('shot-request');req['state_snapshot_sha256_by_character'].pop(next(iter(req['state_snapshot_sha256_by_character'])))
        self.assertFalse(pc.validate_artifact(pc.finalize_artifact(req))['ok'])
    def test_declared_structure_cycle(self):
        value=fixture('character-identity-contract');value['stable_identity']['frame_character']['structures']={'a':{'kind':'panel','location':'front','presence':'present','geometry':{'shape':'flat'},'parent_id':'b'},'b':{'kind':'panel','location':'back','presence':'present','geometry':{'shape':'flat'},'parent_id':'a'}}
        self.assertFalse(pc.validate_artifact(value)['ok'])
    def test_ledger_requires_valid_cross_scene_inputs(self):
        scene=pc.load_json(SCENE/'generated/scene-viewpoint-plan.json');shots=[pc.load_json(p) for p in (SCENE/'generated/shots').glob('*.json')];trans=[pc.load_json(p) for p in (SCENE/'generated/transitions').glob('*.json')]
        self.assertValid(viewpoint.build_continuity_ledger(scene,shots,trans))
        with self.assertRaises(ValueError):viewpoint.build_continuity_ledger(scene,shots+[shots[0]],trans)
    def test_bound_reference_source_bytes(self):
        f=self.root/'media.bin';f.write_bytes(b'only synthetic fixture bytes')
        value=fixture('state-aware-reference-binding');value.update(identity_contract_sha256='a'*64,era_contract_sha256=None,appearance_variant_sha256=None,state_snapshot_sha256=None,effective_story_range={'from_order':0,'to_order':None},visibly_supported_state=['outline'],unsupported_or_occluded_state=[],superseded_for_future_scenes=False)
        value['source']={'kind':'supplied-file','reference_id':'test-media','resolved_path':str(f.resolve()),'media_type':'application/octet-stream','sha256':exchange.digest(f.read_bytes())}
        value=pc.finalize_artifact(value)
        # Schema-only source exchange does not assert model-specific media support.
        self.assertValid(value)
        if hasattr(state,'validate_source_bytes'):
            state.validate_source_bytes(value['source']);f.write_bytes(b'changed')
            with self.assertRaises(ValueError):state.validate_source_bytes(value['source'])



def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    buf=io.StringIO();result=unittest.TextTestRunner(stream=buf,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    sys.stderr.write(buf.getvalue())
    report={'ok':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'public_fixture_count':len(pc.ARTIFACT_TYPES)}
    print(json.dumps(report,indent=2));return 0 if report['ok'] else 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
