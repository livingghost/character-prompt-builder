#!/usr/bin/env python3
"""Offline feature contracts: scoped adoption, retrieval, revision, packs and bulk reads.

python scripts/feature_workflow_smoke_test.py
No image-generation service is contacted. Fixtures are synthetic, not real consent.
"""
from __future__ import annotations
from reading_fixtures import fixture_reading
import argparse
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import adoption_workflow as adoption
import catalog_cli
import dispatch
import pack_manager as pm
import studio
from generation_payload_smoke_test import _write_fixture_pack, _package, PACK_ID, MODEL_ID, APPROVED_PLOT, PROMPT
from prepare_generation_references import empty_stateless_reference_set
from prompt_retrieval import require_generation_retrieval, settle_retrieval_record
from revision_contract import validate_revision, digest
from smoke_fixtures import fixture_retrieval
from verify_generation_payload import verify
from validate_studio import validate as validate_studio


class FeatureWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='cpb-feature-suite-')
        cls.base = Path(cls.temporary.name)
        cls.pack = cls.base / 'pack'
        _write_fixture_pack(cls.pack)
        cls.settings = pm.PackSettings(roots=(cls.pack,), state_file=cls.base/'state.json',
            cache_dir=cls.base/'cache', managed_root=cls.base/'managed', quarantine_root=cls.base/'quarantine',
            default_enabled_packs=(PACK_ID,))
        pm.save_state(cls.settings.state_file, {'pack_roots': [], 'enabled_packs': [PACK_ID], 'resource_providers': {}})
        catalog_cli.configure_pack_runtime(cls.settings)
        cls.package = _package(empty_stateless_reference_set())
        cls.package_path = cls.base/'package.json'; pm.atomic_write_json(cls.package_path, cls.package)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        catalog_cli.configure_pack_runtime(self.settings)
        self.work_context = tempfile.TemporaryDirectory(prefix='case-', dir=self.base)
        self.addCleanup(self.work_context.cleanup)
        self.work = Path(self.work_context.name)
        self.root = studio.init(self.work/'studio', 'fixture-studio', 'Offline fixture')
        self.home = studio.add_character(self.root, 'C01', '')
        # Preserve the same actual source witnesses when changing the fixture root.
        from input_evidence import InputEvidence
        import execution_contract as contract
        evidence = InputEvidence(None, snapshots=self.package['input_snapshots'], live=False)
        for relative, snapshot in evidence.snapshots.items():
            if relative.startswith('@'):
                continue
            destination = contract.local(self.root, relative, exists=False)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(evidence._decode(snapshot))
        (self.root/'continuity-decision.txt').write_text(
            'Synthetic decision: C01 is a recurring test character. Not human consent.\n', encoding='utf-8')

    def iteration(self, color='white', slot='base.front'):
        from PIL import Image
        path = self.work / ('image-' + color + '.png')
        Image.new('RGB', (24, 24), color).save(path)
        return studio.iterate(self.root, 'C01', slot, path, package=self.package_path, request=None, response=None, note='Offline fixture')

    def approval(self, row, scope='sheet', influence='identity', **extra):
        if influence == 'identity':
            from visual_continuity import file_ref
            extra.setdefault('continuity_decision', {
                'character_id': 'C01', 'continuity': 'recurring',
                'basis': file_ref(self.root, 'continuity-decision.txt', locator='whole'),
                'by': 'SYNTHETIC PRINCIPAL, NOT HUMAN CONSENT', 'at': '2000-01-01T00:00:00Z'})
        return {'scope': scope, 'influence': influence, 'character': 'C01',
                'iteration_id': row['iteration_id'], 'slot': row['slot'], 'image_sha256': row['result']['sha256'],
                'by': 'OFFLINE TEST FIXTURE, NOT HUMAN CONSENT', 'at': '2026-09-15T00:00:00Z', **extra}

    def adopt(self, row, **kwargs):
        return adoption.adopt(self.root, 'C01', row['iteration_id'], self.approval(row), **kwargs)

    def index(self): return adoption.reference_index(self.root, 'C01')

    def revision(self, operation='edit'):
        baseline = {'identity': {'face': 'unchanged', 'fixed_wardrobe': None},
                    'identity_slots': {'base.front': 'a'*64},
                    'scene': {'eyes': 'green', 'outfit': 'blue coat', 'lighting': 'soft', 'pose': 'standing'}}
        candidate = copy.deepcopy(baseline); candidate['scene']['eyes'] = 'blue'
        return {'operation': operation, 'baseline': baseline, 'candidate': candidate,
                'requested_paths': ['/scene/eyes'], 'frozen_paths': []}

    def test_01_package_requires_real_settled_record_and_verifies(self):
        self.assertTrue(verify(self.package, project=self.root)['verified'])
        self.assertEqual(self.package['composition_prompt'], PROMPT)
        self.assertEqual(self.package['retrieval_record_sha256'], digest(self.package['retrieval_record']))

    def test_02_missing_unsettled_and_unavailable_retrieval_rejected(self):
        for value in (None, {}, {'unavailable': 'offline'}, {'artifact_type': 'prompt-retrieval-record', 'elements': []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_generation_retrieval(value, prompt=PROMPT, plot=APPROVED_PLOT)
        value = fixture_retrieval(PROMPT, APPROVED_PLOT); value['settled'] = False
        with self.assertRaisesRegex(ValueError, 'settled'):
            require_generation_retrieval(value, prompt=PROMPT, plot=APPROVED_PLOT)

    def test_03_retrieval_cannot_be_reused_for_other_prompt(self):
        with self.assertRaisesRegex(ValueError, 'different prompt|context'):
            require_generation_retrieval(fixture_retrieval(PROMPT, APPROVED_PLOT), prompt=PROMPT+' extra', plot=APPROVED_PLOT)

    def test_04_retrieval_cannot_be_reused_for_other_plot(self):
        value = copy.deepcopy(APPROVED_PLOT); value.pop('approved'); value['story'][0]['beat'] += ' changed'
        from prompt_plot import content_sha256
        value['approved'] = {**APPROVED_PLOT['approved'], 'content_sha256': content_sha256(value)}
        with self.assertRaises(ValueError):
            require_generation_retrieval(fixture_retrieval(PROMPT, APPROVED_PLOT), prompt=PROMPT, plot=value)

    def test_05_verifier_rejects_removal_tampering_and_record_switch(self):
        for key in ('retrieval_record', 'retrieval_record_sha256', 'composition_prompt'):
            value = copy.deepcopy(self.package); value.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError): verify(value, project=self.root)
        value=copy.deepcopy(self.package); value['retrieval_record']['settled']=False
        with self.assertRaises(ValueError): verify(value, project=self.root)
        value=copy.deepcopy(self.package); value['retrieval_record']=fixture_retrieval(PROMPT+' other', APPROVED_PLOT)
        with self.assertRaises(ValueError): verify(value, project=self.root)

    def test_06_adopt_binds_real_image_and_package_and_next_reference(self):
        row=self.iteration(); result=self.adopt(row)
        self.assertEqual(result['status'], 'sheet-bound'); self.assertIsNone(result['next_action'])
        self.assertTrue(self.index()['ok']); self.assertEqual(self.index()['bindings'][0]['image_sha256'],row['result']['sha256'])
        selection=adoption.supplied_selection(self.root,'C01')
        self.assertEqual(selection[0]['role'],'identity')
        self.assertEqual(studio.sha256_file(Path(selection[0]['source']['resolved_path'])),row['result']['sha256'])
        self.assertFalse(validate_studio(self.root))

    def test_07_replacement_preserves_history_and_updates_next_reference(self):
        old=self.iteration(); self.adopt(old); new=self.iteration('red'); self.adopt(new)
        rows=studio.read_iterations(self.home)
        self.assertEqual([r['status'] for r in rows],['superseded','accepted'])
        self.assertEqual(self.index()['bindings'][0]['image_sha256'],new['result']['sha256'])
        self.assertTrue((self.root/old['result']['path']).is_file())
        self.assertTrue((self.home/'sheet'/'bindings'/old['iteration_id']).is_dir())

    def test_08_candidate_only_acceptance_after_binding_reports_staleness(self):
        old=self.iteration(); self.adopt(old); new=self.iteration('red')
        studio.accept(self.root,'C01',new['iteration_id'])
        self.assertFalse(self.index()['ok']); self.assertTrue(validate_studio(self.root))
        with self.assertRaisesRegex(ValueError,'incomplete'): adoption.supplied_selection(self.root,'C01')

    def test_09_generation_rejects_old_reference_and_wrong_authority(self):
        old=self.iteration(); self.adopt(old); new=self.iteration('red'); self.adopt(new)
        def package(sha,role='identity'): return {'prepared_reference_set':{'selected_references':[{'role':role,'source':{'sha256':sha}}]}}
        for value in (self.package,package(old['result']['sha256']),package(new['result']['sha256'],'pose')):
            with self.subTest(value=value),self.assertRaises(ValueError): adoption.validate_for_generation(self.root,'C01',value)
        adoption.validate_for_generation(self.root,'C01',package(new['result']['sha256']))

    def test_10_incomplete_binding_resumes_without_duplicate_iteration(self):
        row=self.iteration()
        with patch.object(adoption,'_bind_sheet',side_effect=OSError('fixture disk failure')):
            with self.assertRaises(OSError): self.adopt(row)
        self.assertFalse(self.index()['ok'])
        result=self.adopt(row); self.assertEqual(result['status'],'sheet-bound')
        self.assertEqual(len(studio.read_iterations(self.home)),1)
        self.assertNotIn('last_error',result)
        self.assertEqual(self.adopt(row)['status'],'sheet-bound')

    def test_11_failure_before_acceptance_is_visible_and_resumable(self):
        row=self.iteration()
        with patch.object(studio,'_record_accept',side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError): self.adopt(row)
        self.assertFalse(self.index()['ok']); self.assertTrue(self.index()['pending_adoptions'])
        self.adopt(row); self.assertTrue(self.index()['ok'])

    def test_12_approval_binds_character_slot_image_scope_and_actor(self):
        row=self.iteration()
        for key,value in [('character','C02'),('slot','base.back'),('image_sha256','0'*64),('by',''),('at','not-time'),('scope','canon'),('influence','outfit')]:
            approval=self.approval(row); approval[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): adoption.adopt(self.root,'C01',row['iteration_id'],approval)
        self.assertEqual(studio.read_iterations(self.home)[0]['status'],'candidate')

    def test_13_changed_source_and_symlink_binding_are_rejected(self):
        row=self.iteration(); (self.root/row['result']['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError): self.adopt(row)
        row=self.iteration('red'); (self.home/'sheet'/'bindings').symlink_to(self.work, target_is_directory=True)
        with self.assertRaises(ValueError): self.adopt(row)

    def record(self):
        return {'id':'adopted-test-character','label':'Adopted fixture','curation_status':'curated','category':'species',
                'prompt':'a fictional test character','domains':['shared'],'tags':['fixture','character'],
                'search_terms':[{'phrase':'adopted test character','facet':'species','weight':1.0,'source':'author'}]}

    def catalog_adopt(self,row,**kwargs):
        record=self.record()
        settings=replace(self.settings,state_file=self.work/'registration-state.json',cache_dir=self.work/'registration-cache')
        pm.save_state(settings.state_file, {'pack_roots':[], 'enabled_packs':[PACK_ID], 'resource_providers':{}})
        return adoption.adopt(self.root,'C01',row['iteration_id'],
            self.approval(row,'catalog',registration_record_sha256=digest(record)),registration_record=record,
            pack_dir=self.work/'registered-pack',settings=settings,**kwargs)

    def test_14_catalog_registration_is_valid_locked_searchable_and_bounded(self):
        row=self.iteration(); result=self.catalog_adopt(row)
        self.assertEqual(result['status'],'catalog-registered')
        reg=result['registration']; report=pm.validate_pack(Path(reg['pack_path']),require_lock=True)
        self.assertTrue(report.valid,[issue.to_dict() for issue in report.issues]);self.assertTrue(report.lock_present)
        receipt=pm.load_json(Path(reg['pack_path'])/'resources/adoption-receipt.json')
        self.assertEqual(receipt['authority']['controls'],['identity'])
        self.assertIn('outfit',receipt['authority']['must_not_control'])
        self.assertIn(reg['pack_id'],pm.load_state(self.work/'registration-state.json')['enabled_packs'])
        settings=replace(self.settings,state_file=self.work/'registration-state.json',cache_dir=self.work/'reg-cache')
        catalog_cli.configure_pack_runtime(settings);catalog_cli.begin_catalog_request()
        from catalog_cli import load_entries, inspect_record, asset_lookup
        self.assertEqual(inspect_record(load_entries(),reg['record_id'])['record']['id'],reg['record_id'])
        assets=asset_lookup(reg['record_id'],summary=False)
        self.assertIn(reg['asset_id'],json.dumps(assets))
        from reference_runtime import build_reference_use_plan, execute_reference_use_plan
        plan=build_reference_use_plan([{'record_id':reg['record_id'],'intended_influence':'identity'}],
             transport_mode='multi-image',target_model=MODEL_ID,source_lighting_mode='replace',
             light_sources=[{'light_id':'key','direction':'front','apparent_size':'large','color':'neutral','relative_intensity':'primary','softness':'soft'}],
             material_responses=[{'material':'textile','roughness':'matte','specular_strength':'low','highlight_shape':'broad','wetness':'dry','anisotropy':'none'}])
        self.assertEqual(len(plan['reference_items']),1)
        self.assertEqual(plan['reference_items'][0]['technical_role'],'adopted-reference')
        produced=execute_reference_use_plan(plan,output_dir=self.work/'prepared')
        prepared=pm.load_json(self.work/'prepared'/'prepared-reference-set.json')
        from build_generation_payload import materialize_cli_reference_bundle
        final=self.work/'generation';final.mkdir()
        prepared,_=materialize_cli_reference_bundle(prepared,model=MODEL_ID,source_root=self.work/'prepared',staging_root=final,companion_name='package.references')
        package=_package(prepared,prepared_reference_root=final)
        self.assertTrue(verify(package,package_root=final, project=self.root)['verified'])
        adoption.validate_for_generation(self.root,'C01',package)

    def test_15_catalog_failure_leaves_resumable_sheet_and_no_false_completion(self):
        row=self.iteration()
        with patch.object(adoption,'_registration',side_effect=OSError('fixture registry failure')):
            with self.assertRaises(OSError): self.catalog_adopt(row)
        self.assertFalse(self.index()['ok'])
        result=self.catalog_adopt(row);self.assertEqual(result['status'],'catalog-registered');self.assertTrue(self.index()['ok'])

    def test_16_catalog_scope_needs_separate_record_bound_approval(self):
        row=self.iteration();record=self.record()
        with self.assertRaises(ValueError): adoption.adopt(self.root,'C01',row['iteration_id'],self.approval(row,'catalog'),
           registration_record=record,pack_dir=self.work/'pack',settings=self.settings)
        self.adopt(row)
        self.assertFalse((self.work/'pack').exists())
        self.assertEqual(self.catalog_adopt(row)['status'],'catalog-registered')

    def test_17_scene_outfit_does_not_change_identity_or_its_slots(self):
        value=self.revision();value['candidate']=copy.deepcopy(value['baseline']);value['candidate']['scene']['outfit']='red coat';value['requested_paths']=['/scene/outfit']
        self.assertTrue(validate_revision(value)['ok'])
        value['candidate']['identity_slots']['base.front']='b'*64
        self.assertFalse(validate_revision(value)['ok'])
        value['candidate']=copy.deepcopy(value['baseline']);value['candidate']['identity']['fixed_wardrobe']='red coat';value['requested_paths']=['/identity/fixed_wardrobe']
        self.assertFalse(validate_revision(value)['ok'])

    def test_18_edit_preserves_unrequested_baseline(self):
        value=self.revision();self.assertTrue(validate_revision(value)['ok'])
        value['candidate']['scene']['lighting']='harsh';self.assertFalse(validate_revision(value)['ok'])
        value['consistency_changes']=[{'path':'/scene/lighting','reason':'Explicitly disclosed consistency repair fixture'}]
        self.assertTrue(validate_revision(value)['ok'])

    def test_19_explore_changes_free_axes_but_not_frozen_ones(self):
        value=self.revision('explore');value['candidate']['scene']['lighting']='harsh';self.assertTrue(validate_revision(value)['ok'])
        value['frozen_paths']=['/scene/lighting'];self.assertFalse(validate_revision(value)['ok'])

    def test_20_retarget_preserves_structured_meaning(self):
        value=self.revision('retarget');self.assertFalse(validate_revision(value)['ok'])
        value['candidate']=copy.deepcopy(value['baseline']);self.assertTrue(validate_revision(value)['ok'])

    def test_21_ancestor_replacement_cannot_bypass_local_edit(self):
        value=self.revision();value['candidate']['scene']='replacement';self.assertFalse(validate_revision(value)['ok'])

    def test_22_fresh_initialization_enables_all_and_preserves_existing_state(self):
        second=self.work/'second';_write_fixture_pack(second)
        manifest=pm.load_json(second/'pack.json');second_id=pm.generate_uuid7();manifest['pack_id']=second_id
        pm.atomic_write_json(second/'pack.json',manifest);pm.write_lock(second)
        settings=replace(self.settings, roots=(self.pack,second),state_file=self.work/'fresh-state.json',initialize_all_discovered=True)
        state=pm.load_effective_state(settings);self.assertEqual(set(state['enabled_packs']),{PACK_ID,second_id})
        state['enabled_packs']=[PACK_ID];pm.save_state(settings.state_file,state)
        self.assertEqual(pm.load_effective_state(settings)['enabled_packs'],[PACK_ID])

    def test_23_default_settings_uses_all_discovered_policy(self):
        settings=pm.default_settings(state_file=self.work/'fresh.json')
        self.assertTrue(settings.initialize_all_discovered)
        self.assertFalse(pm.default_settings(state_file=self.work/'isolated.json', default_enabled_packs=(PACK_ID,)).initialize_all_discovered)

    def test_24_core_commons_is_lockless_but_external_copy_is_not_exempt(self):
        commons=ROOT/'packs/commons'
        self.assertFalse((commons/'pack.lock.json').exists());self.assertTrue(pm.is_project_pack(commons))
        with self.assertRaises(pm.PackError): pm.write_lock(commons)
        with patch.object(pm,'ROOT',self.work): self.assertFalse(pm.is_project_pack(commons))
        copied=self.work/'external';_write_fixture_pack(copied)
        value=pm.load_json(copied/'pack.json');value['pack_id']=pm.load_json(commons/'pack.json')['pack_id'];pm.atomic_write_json(copied/'pack.json',value)
        (copied/'pack.lock.json').unlink()
        report=pm.validate_pack(copied,require_lock=True);self.assertFalse(report.valid)
        self.assertTrue(any(issue.code=='missing-lock' for issue in report.issues))

    def test_25_inspect_many_returns_complete_records_assets_and_one_snapshot(self):
        output=io.StringIO()
        args=['--state-file',str(self.settings.state_file),'--cache-dir',str(self.settings.cache_dir),
              '--managed-root',str(self.settings.managed_root),'--pack-root',str(self.pack),
              'inspect-many','fixture-generic-subject',MODEL_ID]
        with contextlib.redirect_stdout(output):code=catalog_cli.main(args)
        self.assertEqual(code,0,output.getvalue());result=json.loads(output.getvalue())
        self.assertEqual(len(result['records']),2);self.assertTrue(result['runtime_fingerprint'])
        self.assertIn('assets',result['records'][0]);self.assertIn('timing',result)
        self.assertIn(PACK_ID,result['record_source_pack_ids'])

    def test_26_inspect_many_missing_record_fails(self):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            catalog_cli.main(['--state-file',str(self.settings.state_file),'--cache-dir',str(self.settings.cache_dir),
                 '--managed-root',str(self.settings.managed_root),'--pack-root',str(self.pack),'inspect-many','does-not-exist'])
        self.assertNotEqual(exc.exception.code,0)

    def test_27_mock_dispatch_keeps_real_verifier_and_records_returned_result(self):
        options=argparse.Namespace(package=self.package_path,service=None,profiles=None,seed=7,count=1,send=True,
                                   character='C01',slot='base.front',note='Offline fixture')
        transport=SimpleNamespace(build=Mock(return_value={'taskUUID':'fixture-task','prompt':PROMPT}),
            media_paths=Mock(return_value=[]),upload=Mock(side_effect=AssertionError('unexpected upload')),
            send=Mock(return_value={'data':'fixture'}),rejections=Mock(return_value=[]),
            results=Mock(return_value=[{'url':'https://example.invalid/fixture.png','id':'fixture','seed':7}]),
            RESULT_HOSTS=frozenset({'example.invalid'}))
        def save(url,path,hosts):
            from PIL import Image
            Image.new('RGB',(24,24),'white').save(path);return studio.sha256_file(path)
        offering={'service':'fixture','model_identifier':MODEL_ID,'observed_at':'2026-09-15'}
        import production_fixtures as fixture
        import production_workflow as workflow
        run = fixture.prepare_dispatch(self.root, PROMPT)
        package = fixture.bind_package(self.root, run, self.package)
        options.package = self.root / 'bound-package.json'
        options.package.write_text(json.dumps(package), encoding='utf-8')
        rendered = fixture.rendered_request(package, seed=7, count=1)
        offering.update(rendered['sealed']['target'])
        transport.observation_outcome = Mock(return_value='accepted')
        options.production_authorization = fixture.grant(self.root, run, workflow.submission_intent(
            package, rendered=rendered, seed=7, count=1, offering=offering, service={}))
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            for name,kwargs in {'select_offering':{'return_value':offering},'service_for':{'return_value':('fixture',{},transport)},
                'check_request':{},'api_key':{'return_value':'OFFLINE-NOT-A-CREDENTIAL'},'save':{'side_effect':save}}.items():
                stack.enter_context(patch.object(dispatch,name,**kwargs))
            stack.enter_context(patch('request_renderer.generation',return_value=rendered))
            self.assertEqual(dispatch.dispatch_generation(options,self.root),0)
        transport.send.assert_called_once();rows=studio.read_iterations(self.home);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['seed'],7)
        self.adopt(rows[0]);self.assertTrue(self.index()['ok'])

    def test_28_walkthrough_reaches_a_real_request_preview_offline(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('offline_walkthrough',ROOT/'examples/feature-walkthrough/run.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.run(self.work/'walkthrough output')
        self.assertEqual(result['external_requests'],0);self.assertFalse(result['sent']);self.assertEqual(result['iterations'],0)
        self.assertEqual(result['package_run'],result['production_run'])
        self.assertEqual(result['request']['model'],'xai:grok-imagine@image-2.0')
        self.assertEqual((result['request']['width'],result['request']['height']),(832,1248))
        self.assertEqual(result['validation']['checked'],['target-schema'])
        self.assertTrue(result['request_validation']['contract'].startswith('@pack/'))
        args=pm.load_json(self.work/'walkthrough output'/'builder-arguments.json')
        for flag in ('--plot-file','--retrieval-record-file','--continuity','--production-root'):self.assertIn(flag,args)
        for flag in ('--request-validation-file','--visual-continuity-file','--production-run'):self.assertNotIn(flag,args)
        # A plain one-off person needs only the drafted specification.
        subject=pm.load_json(self.work/'walkthrough output'/'production-spec.json')['subjects'][0]
        self.assertEqual(subject['domain'],'human')
        self.assertFalse({'resolved_morphology','identity_contract_ref','species_morphology_profile_ref'}&subject.keys())
        # The transcript lists the commands it ran, each with a short result.
        lines=(self.work/'walkthrough output'/'transcript.txt').read_text(encoding='utf-8').splitlines()
        self.assertTrue(all(line.startswith(('$ python scripts/','  exit 0: ','# ')) for line in lines))
        self.assertEqual([line.split()[2] for line in lines if line.startswith('$ ')],
                         ['scripts/'+name+'.py' for name in ('studio','studio','work_ledger','execution_routes',
                          'production_workflow','prompt_retrieval','production_spec','build_generation_payload','dispatch')])
        self.assertLess(sum(map(len,lines)),8000)
        with self.assertRaises(ValueError):module.run(self.work/'walkthrough output')

    def prompt_artifacts(self, extra, destination='draft'):
        import build_prompt_artifacts
        prompt=self.work/'prompt.txt';prompt.write_text(PROMPT,encoding='utf-8')
        out=self.work/destination
        with patch.object(sys,'argv',['build_prompt_artifacts.py','--prompt',str(prompt),'--out-dir',str(out),*extra]), contextlib.redirect_stdout(io.StringIO()):
            code=build_prompt_artifacts.main()
        self.assertEqual(code,0)
        return pm.load_json(out/'prompt-artifact-manifest.json')

    def test_29_unapproved_draft_needs_no_plot_or_studio_authorization(self):
        manifest=self.prompt_artifacts(['--retrieval-unavailable','offline draft explicitly disclosed'])
        self.assertEqual(manifest['mode'],'prompt-only');self.assertFalse(manifest['plot']['approved'])
        self.assertFalse(manifest['execution_authorized']);self.assertFalse(manifest['canonical_update_authorized'])
        with self.assertRaises(ValueError):self.prompt_artifacts(['--retrieval-unavailable','offline','--prepare-for-generation'],'blocked')

    def test_30_draft_revision_contract_is_validated_and_preserved(self):
        path=self.work/'revision.json';pm.atomic_write_json(path,self.revision())
        manifest=self.prompt_artifacts(['--retrieval-unavailable','offline draft','--revision-contract',str(path)])
        self.assertTrue(manifest['revision']['ok']);self.assertIn('/scene/eyes',manifest['revision']['changed_paths'])
        changed=self.revision();changed['candidate']['scene']['lighting']='unrequested';pm.atomic_write_json(path,changed)
        with self.assertRaisesRegex(ValueError,'revision'):self.prompt_artifacts(['--retrieval-unavailable','offline','--revision-contract',str(path)],'bad-revision')

    def test_31_stateless_builder_itself_rejects_missing_retrieval(self):
        import generation_payload_smoke_test as fixture
        from build_generation_payload import build_payload
        with patch.object(fixture,'build_payload') as capture:
            fixture._package(empty_stateless_reference_set())
        args=capture.call_args.kwargs;args['retrieval_record']=None
        with self.assertRaisesRegex(ValueError,'retrieval'):build_payload(**args)
        args['retrieval_record']=fixture_retrieval(PROMPT,APPROVED_PLOT)
        invalid=self.revision();invalid['candidate']['scene']['lighting']='unrequested'
        args['creative_intent']['revision_contract']=invalid
        with self.assertRaisesRegex(ValueError,'revision'):build_payload(**args)
        value=copy.deepcopy(self.package);value['creative_intent']['revision_contract']=invalid
        with self.assertRaisesRegex(ValueError,'revision'):verify(value, project=self.root)

    def test_32_canonical_revision_approval_is_version_bound_and_not_scene_authority(self):
        value=self.revision();value['candidate']=copy.deepcopy(value['baseline'])
        value['candidate']['identity']['fixed_wardrobe']='red coat';value['requested_paths']=['/identity/fixed_wardrobe']
        value['scope']='identity'
        self.assertFalse(validate_revision(value)['ok'])
        value['canonical_approval']={'by':'OFFLINE FIXTURE','at':'2026-09-15T00:00:00Z',
              'baseline_sha256':digest(value['baseline']),'candidate_sha256':digest(value['candidate'])}
        self.assertTrue(validate_revision(value)['ok'])
        value['candidate']['identity']['fixed_wardrobe']='green coat';self.assertFalse(validate_revision(value)['ok'])

    def test_33_registration_activation_failure_resumes_without_new_pack_or_iteration(self):
        row=self.iteration()
        with patch.object(adoption,'enable_pack',side_effect=pm.PackError('fixture activation error')):
            with self.assertRaises(pm.PackError):self.catalog_adopt(row)
        self.assertFalse(self.index()['ok'])
        previous=pm.load_json(self.work/'registered-pack'/'pack.json')['pack_id']
        result=self.catalog_adopt(row)
        self.assertEqual(result['registration']['pack_id'],previous);self.assertEqual(len(studio.read_iterations(self.home)),1)
        self.assertTrue(self.index()['ok'])

    def test_34_registered_pack_mutation_is_detected_and_not_overwritten(self):
        row=self.iteration();result=self.catalog_adopt(row)
        path=Path(result['registration']['pack_path'])/'resources'/'reference.png'
        path.write_bytes(b'changed')
        self.assertFalse(self.index()['ok'])
        with self.assertRaises(ValueError):self.catalog_adopt(row)
        self.assertEqual(path.read_bytes(),b'changed')

    def test_35_adopted_reference_scope_cannot_expand_in_a_resigned_plan(self):
        row=self.iteration();result=self.catalog_adopt(row)
        settings=replace(self.settings,state_file=self.work/'registration-state.json',cache_dir=self.work/'reg-cache')
        catalog_cli.configure_pack_runtime(settings)
        from reference_runtime import build_reference_use_plan
        # Identity has semantic support, but the registered image is not approved
        # to define a pose or outfit. A new plan must not expand that authority.
        with self.assertRaises(ValueError):
            build_reference_use_plan([{'record_id':result['registration']['record_id'],'intended_influence':'outfit'}],
                  transport_mode='prompt-artifacts',source_lighting_mode='replace')

    def test_36_fresh_pack_state_names_a_duplicate_uuid_instead_of_hiding_it(self):
        from pack_cache import load_runtime_catalog
        second=self.work/'duplicate';_write_fixture_pack(second)
        settings=replace(self.settings,roots=(self.pack,second),state_file=self.work/'fresh.json',
                         cache_dir=self.work/'fresh-cache',initialize_all_discovered=True)
        printed=io.StringIO()
        with contextlib.redirect_stderr(printed):catalog=load_runtime_catalog(settings)
        self.assertEqual(catalog.active_pack_count,0)
        self.assertIn(f'warning: pack {PACK_ID} is in more than one pack root, so no copy is used',printed.getvalue())
        self.assertFalse(settings.state_file.exists())

    def test_37_state_builder_checks_retrieval_before_expensive_graph_work(self):
        import inspect
        import build_state_generation_package as state_builder
        required = {name: {} for name, param in inspect.signature(state_builder.build_package).parameters.items()
                    if param.default is inspect.Parameter.empty}
        required.update(model=MODEL_ID, prompt=PROMPT, negative_prompt='', brief='', plot=APPROVED_PLOT)
        for record in (None, {'settled': False}, fixture_retrieval(PROMPT+' other', APPROVED_PLOT)):
            with self.subTest(record=record), self.assertRaisesRegex(ValueError, 'retrieval'):
                state_builder.build_package(**required, retrieval_record=record)
        with self.assertRaisesRegex(ValueError, 'state-lineage mode'):
            state_builder.build_package(**required, retrieval_record=fixture_retrieval(PROMPT, APPROVED_PLOT))

    def test_38_documented_state_package_commands_include_required_gates(self):
        import re
        for name in ('references/runtime/image-generation.md', 'references/state-aware-prompt-workflow.md'):
            text=(ROOT/name).read_text(encoding='utf-8')
            commands=re.findall(r'python scripts/build_state_generation_package\.py[^`]+?(?=\npython |```)', text)
            self.assertTrue(commands, name)
            for command in commands:
                self.assertIn('--plot-file', command, name)
                self.assertIn('--retrieval-record-file', command, name)

    def test_39_superseded_outfit_reference_is_rejected_without_requiring_it_on_every_scene(self):
        identity=self.iteration(); self.adopt(identity)
        old=self.iteration('blue', slot='work.outfit')
        adoption.adopt(self.root,'C01',old['iteration_id'],self.approval(old,influence='outfit'))
        new=self.iteration('red', slot='work.outfit')
        adoption.adopt(self.root,'C01',new['iteration_id'],self.approval(new,influence='outfit'))
        package={'prepared_reference_set':{'selected_references':[
            {'role':'identity','source':{'sha256':identity['result']['sha256']}}]}}
        adoption.validate_for_generation(self.root,'C01',package)
        package['prepared_reference_set']['selected_references'].append({'role':'outfit','source':{'sha256':old['result']['sha256']}})
        with self.assertRaisesRegex(ValueError,'superseded outfit'):
            adoption.validate_for_generation(self.root,'C01',package)
        package['prepared_reference_set']['selected_references'][-1]['source']['sha256']=new['result']['sha256']
        adoption.validate_for_generation(self.root,'C01',package)

    def test_40_inspect_many_revalidates_changed_pack_bytes(self):
        import shutil
        pack=self.work/'mutable-pack';shutil.copytree(self.pack,pack)
        state=self.work/'bulk-state.json'
        pm.save_state(state,{'pack_roots':[str(pack)],'enabled_packs':[PACK_ID],'resource_providers':{}})
        args=['--state-file',str(state),'--cache-dir',str(self.work/'bulk-cache'),
              '--managed-root',str(self.work/'managed'),'inspect-many','fixture-generic-subject']
        def read():
            out=io.StringIO()
            with contextlib.redirect_stdout(out): self.assertEqual(catalog_cli.main(args),0)
            return json.loads(out.getvalue())
        first=read()
        changed=False
        for path in (pack/'records').rglob('*.json'):
            obj=pm.load_json(path)
            for row in obj.get('records',[]):
                if row.get('id')=='fixture-generic-subject': row['label']='Changed complete record'; changed=True
            pm.atomic_write_json(path,obj)
        self.assertTrue(changed);pm.write_lock(pack)
        second=read()
        self.assertNotEqual(first['runtime_fingerprint'],second['runtime_fingerprint'])
        self.assertIn('Changed complete record',json.dumps(second['records']))

    def test_41_core_gate_reports_lockless_structure_without_claiming_core_release(self):
        from pack_release_gate import run_release_gate
        commons=ROOT/'packs/commons';manifest=pm.load_json(commons/'pack.json');uid=manifest['pack_id']
        state=self.work/'gate-state.json';managed=self.work/'gate-managed';managed.mkdir()
        pm.save_state(state,{'pack_roots':[str(commons)],'enabled_packs':[uid],
              'resource_providers':{name:uid for name in manifest['content']['resource_bindings']}})
        report=run_release_gate(commons,state_file=state,cache_dir=self.work/'gate-cache',managed_root=managed)
        self.assertTrue(report['ok'],report['errors'])
        self.assertEqual(report['pack']['integrity_policy'],'core-managed-live-inventory')
        self.assertEqual(report['scope'],'core-managed-pack-structure')
        self.assertFalse(report['release_authorized']);self.assertIsNone(report['pack']['locked_file_count'])
        self.assertEqual(report['contract']['owner'],'core-release-gate')

    def test_42_an_image_scene_material_uses_the_adopted_identity_while_it_holds(self):
        import scene_persona as scene
        from scene_material_smoke_test import finish_draft, write_series
        write_series(self.root/'story')
        row=self.iteration(); self.adopt(row)
        drafted=scene.draft(self.root,'story/narrative/scenes/sc01-plot.json','plan.json','image')
        self.assertEqual([item['subject_id'] for item in drafted['identities']],['C01'])
        ids={excerpt['excerpt_id'] for excerpt in finish_draft(self.root,'plan.json')['excerpts']}
        self.assertNotIn('C01-appearance-1',ids); self.assertIn('C02-appearance-1',ids)
        built=scene.build(self.root,'plan.json','material')
        self.assertEqual(built['identities'],[{'subject_id':'C01','studio_character':'C01','slot':'base.front',
            'iteration_id':row['iteration_id'],'image_sha256':row['result']['sha256']}])
        self.assertTrue(scene.verify(self.root,'plan.json','material')['ok'])
        newer=self.iteration('red'); studio.accept(self.root,'C01',newer['iteration_id'])
        with self.assertRaisesRegex(ValueError,'C01: the identity image base.front .* is not accepted and bound'):
            scene.verify(self.root,'plan.json','material')


def main():
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream).run(unittest.defaultTestLoader.loadTestsFromTestCase(FeatureWorkflowTests))
    print(json.dumps({'ok':result.wasSuccessful(),'checks':result.testsRun,'failures':len(result.failures),
        'error_count':len(result.errors),'errors':[f'{case.id()}: {detail}' for case,detail in result.failures+result.errors],
        'detail':stream.getvalue()},indent=2))
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
