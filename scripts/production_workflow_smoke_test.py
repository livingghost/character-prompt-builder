#!/usr/bin/env python3
"""Current-form tests for actual production evidence and execution edges."""
from __future__ import annotations
import argparse
import copy
import contextlib
import errno
import io
import json
import os
import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import execution_contract as c
import execution_routes as routes
import production_workflow as w
import production_binding as binding
import work_ledger as ledger
import production_fixtures as fixture


ROOT=Path(__file__).resolve().parents[1]


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        task=ledger.begin(self.root,'Synthetic test',['prepare','deliver'])
        self.write('brief.md','A lamp. PRIVATE_SOURCE_NOT_FOR_CONSUMER.\n')
        self.write('delivery.txt','Describe one lamp.\n')
        self.spec={'task_id':task['task_id'],'route':'development','features':[],
          'sources':[{'id':'brief','path':'brief.md','role':'world','locator':'whole','disposition':'applied','reason':'Explicit test premise.'}],
          'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Only public instructions.'},
          'criteria':[{'id':'lamp','strength':'hard','text':'Keep one lamp.'},{'id':'style','strength':'advisory','text':'Optional spare wording.'}],
          'world_views':[]}
        fixture.task(self.root,self.spec)
        self.save_spec()

    def write(self,name,value):
        p=self.root/name; p.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(value,bytes): p.write_bytes(value)
        elif isinstance(value,str): p.write_bytes(value.encode('utf-8'))
        else: p.write_bytes(c.encoded(value))
        return p

    def save_spec(self):
        from reading_fixtures import task_reading
        task_reading(self.root, self.spec)
        self.write('task.json',self.spec)
    def prepare(self): return w.prepare(self.root,'task.json')['run']
    def candidate(self,run=None,name='output.txt',content='One lamp.\n'):
        run=run or self.prepare(); fixture.handoff(self.root,run,'test','manual')
        self.write(name,content)
        return run,w.capture(self.root,run,name,'Synthetic fixture')
    def review_data(self,run,candidate):
        data=w.draft_review(self.root,run,candidate['sha256'])
        data.update(reviewer='synthetic reviewer',observations=[{'locator':{'kind':'whole'},'observation':'The fixture is inspected.'}],conclusion='Synthetic test only.')
        for x in data['checks']: x.update(verdict='pass',observation_indices=[0],reason='Test observation.')
        return fixture.observation(data)
    def record_review(self,run,candidate,data=None,name='review.json'):
        data=data or self.review_data(run,candidate); self.write(name,data)
        return w.review(self.root,run,name)
    def select(self,run,candidate):
        data=w.draft_selection(self.root,run,candidate['sha256']); data.update(selector='synthetic selector',reason='Test delivery only.')
        fixture.selection(self.root,run,data)
        self.write('selection.json',data); return w.select(self.root,run,'selection.json')
    def finish(self):
        run,candidate=self.candidate(); self.record_review(run,candidate); self.select(run,candidate)
        return run,w.complete(self.root,run)

    def test_impact_names_the_runs_that_used_a_material(self):
        import scene_persona
        import scene_material_smoke_test as material
        material.fixture(self.root); scene_persona.build(self.root,'plan.json','scene-material')
        self.spec.update(route='performance',features=['scene-persona'],
                         scene_materials=[{'plan':'plan.json','bundle':'scene-material'}])
        self.save_spec()
        run,candidate=self.candidate(); self.record_review(run,candidate); self.select(run,candidate)
        rows=scene_persona.impact(self.root)['scenes']
        self.assertEqual([(row['material'],row['runs']) for row in rows],
                         [('scene-material/material.json',[{'run':run,'selection_recorded':True}])])
    def test_routes_all_owners_and_dependencies(self): self.assertTrue(routes.validate()['ok'])
    def test_uuid_identity(self): self.assertEqual(uuid.UUID(self.prepare()).version,7)
    def test_task_template_validates_with_the_printed_series_id(self):
        import subprocess,sys
        task=c.load(ROOT/'templates/realization/production-task.json')
        with self.assertRaisesRegex(ValueError,r'python scripts/production_workflow\.py new-production-id'): w.validate_task(task)
        printed=subprocess.run([sys.executable,str(ROOT/'scripts/production_workflow.py'),'new-production-id'],
                               capture_output=True,text=True,encoding='utf-8',check=True).stdout
        task['production_id']=json.loads(printed)['production_id']
        self.assertEqual(w.validate_task(task)['route'],'development')
    def test_authority_template_shows_a_checked_stop_condition(self):
        import production_permissions as permissions
        authority=c.load(ROOT/'templates/realization/production-authority.json')
        w.schema_check(authority,'authority'); permissions.validate(authority,authority['task_id'])
        self.assertEqual([set(x) for x in authority['stop_conditions']],[{'id','text'}])
    def test_consumer_excludes_raw_dossier(self):
        run=self.prepare(); self.assertNotIn('PRIVATE_SOURCE_NOT_FOR_CONSUMER',c.read(w.run_dir(self.root,run)/'consumer.json').decode())
    def test_exact_binding(self):
        run=self.prepare(); b=binding.create(self.root,run,'Describe one lamp.\n'); binding.validate(b,'Describe one lamp.\n')
    def test_wrong_delivery_binding(self):
        run=self.prepare()
        with self.assertRaises(ValueError): binding.create(self.root,run,'Another picture.')
    def test_binding_changed_without_digest(self):
        run=self.prepare(); b=binding.create(self.root,run,'Describe one lamp.\n'); b['consumer']['instructions']='changed'
        with self.assertRaises(ValueError): binding.validate(b,'Describe one lamp.\n')
    def test_authored_rendition_no_prefix(self):
        run=self.prepare(); b=binding.create(self.root,run,'Describe one lamp.\n')
        self.assertEqual(binding.effective(b,'TAG_1, TAG_2'),'TAG_1, TAG_2')
    def test_bounded_prefix_only_explicit_fields(self):
        self.spec['delivery']['transport']='bounded-context'; self.save_spec(); run=self.prepare()
        b=binding.create(self.root,run,'Describe one lamp.\n'); text=binding.effective(b,'prompt',context_transport='prompt-prefix')
        self.assertIn('Keep one lamp.',text); self.assertNotIn('PRIVATE_SOURCE',text)
    def test_no_handoff_no_capture(self):
        run=self.prepare(); self.write('out.txt','lamp')
        with self.assertRaises(ValueError): w.capture(self.root,run,'out.txt','test')
    def test_no_output_no_completion(self):
        run=self.prepare()
        with self.assertRaises(ValueError): w.complete(self.root,run)
    def test_missing_artifact(self):
        run=self.prepare(); fixture.handoff(self.root,run,'test','manual')
        with self.assertRaises(ValueError): w.capture(self.root,run,'absent.txt','test')
    def test_empty_artifact(self):
        run=self.prepare(); fixture.handoff(self.root,run,'test','manual'); self.write('empty','')
        with self.assertRaises(ValueError): w.capture(self.root,run,'empty','test')
    def test_changed_source(self):
        run=self.prepare(); self.write('brief.md','changed'); self.assertEqual(w.status(self.root,run)['runs'][0]['readiness'],'blocked')
    def test_changed_delivery(self):
        run=self.prepare(); self.write('delivery.txt','changed'); self.assertEqual(w.status(self.root,run)['runs'][0]['readiness'],'blocked')
    def test_changed_criteria(self):
        run=self.prepare(); self.spec['criteria'][0]['text']='changed'; self.save_spec(); self.assertEqual(w.status(self.root,run)['runs'][0]['readiness'],'blocked')
    def test_changed_task_only_note(self):
        run=self.prepare(); self.spec['delivery']['translation_notes']='Different meaning'; self.save_spec(); self.assertEqual(w.status(self.root,run)['runs'][0]['readiness'],'blocked')
    def test_unknown_feature(self):
        self.spec['features']=['missing']; self.write('task.json',self.spec)
        with self.assertRaises(ValueError): self.prepare()
    def test_persona_source_required(self):
        self.spec['features']=['persona']; self.save_spec()
        with self.assertRaises(ValueError): self.prepare()
    def test_explicit_persona_source(self):
        self.spec['features']=['persona']; self.spec['sources'][0]['role']='persona'; self.save_spec(); self.assertTrue(w.status(self.root,self.prepare())['ok'])
    def test_nonadopted_sources_not_forced(self):
        self.spec['sources'][0]['disposition']='considered-not-used'; self.save_spec(); self.assertTrue(w.status(self.root,self.prepare())['ok'])
    def test_no_world_view_for_required_route(self):
        self.spec['route']='world-realization'; self.save_spec()
        with self.assertRaises(ValueError): self.prepare()
    def test_unknown_route(self):
        self.spec['route']='unknown'; self.write('task.json',self.spec)
        with self.assertRaises(ValueError): self.prepare()
    def test_duplicate_json(self):
        with self.assertRaises(ValueError): c.decode(b'{"a":1,"a":2}')
    def test_nonfinite_json(self):
        with self.assertRaises(ValueError): c.decode(b'{"a":NaN}')
    def test_path_escape(self):
        self.spec['delivery']['path']='../outside'; self.save_spec()
        with self.assertRaises(ValueError): self.prepare()
    def test_source_symlink(self):
        (self.root/'link').symlink_to(self.root/'brief.md'); self.spec['sources'][0]['path']='link'; self.save_spec()
        with self.assertRaises(ValueError): self.prepare()
    def test_consumer_integrity(self):
        run=self.prepare(); (w.run_dir(self.root,run)/'consumer.json').write_text('{}',encoding='utf-8'); self.assertFalse(w.status(self.root,run)['ok'])
    def test_object_integrity(self):
        run=self.prepare(); p=next((w.run_dir(self.root,run)/'objects').iterdir()); p.write_bytes(b'bad'); self.assertFalse(w.status(self.root,run)['ok'])
    def test_receipt_integrity(self):
        import production_store as store
        run,ca=self.candidate()
        with store.transaction(self.root) as connection:
            connection.execute("UPDATE events SET body=? WHERE scope=? AND sequence=1",(b'{}',run))
        report=w.status(self.root,run)
        self.assertFalse(report['ok'])
        diagnostic=report['runs'][0]['diagnostics'][0]
        self.assertEqual(diagnostic['code'],'EVENT_CHAIN_CORRUPT')
        self.assertEqual(diagnostic['run'],run)
        self.assertEqual(diagnostic['event'],1)
    def test_unfinished_review_not_accepted(self):
        run,ca=self.candidate(); self.write('review.json',w.draft_review(self.root,run,ca['sha256']))
        with self.assertRaises(ValueError): w.review(self.root,run,'review.json')
    def test_review_missing_observation(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['observations']=[]
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_line_range_bounds(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['observations'][0]['locator']={'kind':'lines','start':1,'end':99}
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_valid_utf8_line_range(self):
        run,ca=self.candidate(content='One lamp.\nSecond line.\n'); d=self.review_data(run,ca); d['observations'][0]['locator']={'kind':'lines','start':2,'end':2}
        self.record_review(run,ca,d)
    def test_byte_range_bounds(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['observations'][0]['locator']={'kind':'bytes','start':0,'end':1}
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_binary_artifact(self):
        self.spec['artifact']='binary'; self.save_spec()
        run,ca=self.candidate(name='binary.bin',content=b'\x00\xff\x12'); self.record_review(run,ca); self.select(run,ca); self.assertEqual(w.complete(self.root,run)['event'],'completion')
    def test_foreign_input_review(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['input_sha256']='a'*64
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_foreign_candidate_review(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['candidate']='a'*64
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_unknown_review_criterion(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['checks'][0]['criterion']='other'
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_bad_observation_index(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['checks'][0]['observation_indices']=[22]
        with self.assertRaises(ValueError): self.record_review(run,ca,d)
    def test_hard_failure_blocks_selection(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['checks'][0]['verdict']='fail'; d['unresolved']=['The failed criterion needs a reviewed correction.']; self.record_review(run,ca,d)
        with self.assertRaises(ValueError): self.select(run,ca)
    def test_advisory_unused_is_allowed(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['checks'][1]['verdict']='not-applicable'; self.record_review(run,ca,d); self.select(run,ca)
    def test_unresolved_blocks_selection(self):
        run,ca=self.candidate(); d=self.review_data(run,ca); d['unresolved']=['Need an actual decision']; self.record_review(run,ca,d)
        with self.assertRaises(ValueError): self.select(run,ca)
    def test_captured_candidate_survives_source_edit(self):
        run,ca=self.candidate(); self.record_review(run,ca)
        self.write('output.txt','Changed output')
        self.select(run,ca)
        saved=ca['data']['files'][0]
        self.assertEqual(c.object_read(w.run_dir(self.root,run),saved['sha256']),b'One lamp.\n')
    def test_recorded_review_survives_source_edit(self):
        run,ca=self.candidate(); recorded=self.record_review(run,ca); self.write('review.json',{})
        self.select(run,ca)
        self.assertEqual(w.latest_review(w.load_run(self.root,run)[3],ca['sha256']),recorded)
    def test_recorded_selection_survives_source_edit(self):
        run,ca=self.candidate(); self.record_review(run,ca); selection=self.select(run,ca)
        self.write('selection.json',{})
        done=w.complete(self.root,run)
        self.assertEqual(done['data']['selection'],selection['sha256'])
    def test_new_review_supersedes_selection(self):
        run,ca=self.candidate(); self.record_review(run,ca); self.select(run,ca)
        d=self.review_data(run,ca); d['checks'][0]['verdict']='fail'; d['unresolved']=['The latest observation leaves the criterion unresolved.']; self.record_review(run,ca,d,name='review2.json')
        with self.assertRaises(ValueError): w.complete(self.root,run)
    def test_idempotent_handoff(self):
        run=self.prepare(); a=fixture.handoff(self.root,run,'test','manual'); b=fixture.handoff(self.root,run,'test','manual'); self.assertEqual(a,b)
    def test_changed_handoff_rejected(self):
        run=self.prepare(); fixture.handoff(self.root,run,'test','manual')
        with self.assertRaises(ValueError): fixture.handoff(self.root,run,'someone else','manual')
    def test_idempotent_capture(self):
        run,ca=self.candidate(); self.assertEqual(ca,w.capture(self.root,run,'output.txt','Synthetic fixture'))
    def test_publish_directory_retries_a_transient_refusal(self):
        staging=self.root/'.pending-x'; staging.mkdir(); target=self.root/'published'
        original=c._rename_directory_exclusive; calls=[]
        def flaky(path,destination):
            calls.append(1)
            if len(calls)==1: raise PermissionError(13,'Permission denied')
            return original(path,destination)
        with patch.object(c,'_rename_directory_exclusive',flaky): c.publish_directory(staging,target)
        self.assertTrue(target.is_dir()); self.assertFalse(staging.exists()); self.assertEqual(len(calls),2)
    def test_publish_directory_raises_a_persistent_refusal(self):
        staging=self.root/'.pending-y'; staging.mkdir(); target=self.root/'never'
        def refused(path,destination): raise PermissionError(13,'Permission denied')
        with patch.object(c,'_rename_directory_exclusive',refused):
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_PUBLISH_FAILED'): c.publish_directory(staging,target,patience=0.3)
        self.assertTrue(staging.is_dir()); self.assertFalse(target.exists())
    def test_lock_waits_longer_than_ten_seconds(self):
        import threading,time
        held=threading.Event(); release=threading.Event()
        def holder():
            with c.lock(self.root): held.set(); release.wait(30)
        t=threading.Thread(target=holder); t.start()
        try:
            self.assertTrue(held.wait(10))
            threading.Timer(11.0,release.set).start()
            started=time.monotonic()
            with c.lock(self.root): waited=time.monotonic()-started
            self.assertGreater(waited,10.0)
        finally:
            release.set(); t.join(30)
    def test_concurrent_capture(self):
        run=self.prepare(); fixture.handoff(self.root,run,'test','manual'); self.write('output.txt','One lamp.')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:w.capture(self.root,run,'output.txt','test'),range(2)))
        self.assertEqual(results[0],results[1])
    def test_idempotent_completion(self):
        run,done=self.finish(); self.assertEqual(done,w.complete(self.root,run))
    def test_no_new_artifact_after_completion(self):
        run,_=self.finish(); self.write('other.txt','Different')
        with self.assertRaises(ValueError): w.capture(self.root,run,'other.txt','new')
    def test_work_flags_alone_not_completion(self):
        ledger.step_done(self.root,1); ledger.step_done(self.root,2)
        with self.assertRaises(ValueError): ledger.finish(self.root)
    def test_complete_then_ledger_close_and_resume(self):
        run,done=self.finish(); ledger.step_done(self.root,1); ledger.step_done(self.root,2); ledger.finish(self.root)
        self.assertIsNone(ledger.read_current(self.root)); self.assertIsNone(w.status(self.root,run)['runs'][0]['next_action'])
    def test_wrong_task_completion(self):
        run,done=self.finish()
        with self.assertRaises(ValueError): w.verify_completion(self.root,run,'not-the-task')
    def test_unfinished_steps_still_block_finish(self):
        self.finish()
        with self.assertRaises(ValueError): ledger.finish(self.root)
    def test_unpublished_staging_has_no_phase_authority(self):
        run=self.prepare()
        pending=self.root/'production/staging/incomplete-operation'
        pending.mkdir(parents=True)
        (pending/'authorization.json').write_bytes(b'{"partial":')
        report=w.status(self.root,run)
        self.assertEqual(report['runs'][0]['next_action']['command'],'handoff')
        self.assertIn('incomplete-operation',report['staging'])
        self.assertEqual(w.load_run(self.root,run)[3],[])
    def test_staging_cleanup_is_owner_scoped_and_dry_run_by_default(self):
        from production_compiler import staging_cleanup
        staging=self.root/'production/staging/abandoned'
        staging.mkdir(parents=True)
        self.write('production/staging/abandoned/owner.json', {
            'operation_id':'op-abandoned','pid':99999999,'created_at':'2026-10-02T00:00:00+00:00','phase':'compiling'
        })
        report=staging_cleanup(self.root)
        self.assertTrue(report['items'][0]['eligible']);self.assertTrue(staging.exists())
        with self.assertRaises(ValueError):staging_cleanup(self.root,apply=True)
        other=staging_cleanup(self.root,operation_id='op-other',apply=True)
        self.assertEqual(other['deleted'],0);self.assertTrue(staging.exists())
        own=staging_cleanup(self.root,operation_id='op-abandoned',apply=True)
        self.assertEqual(own['deleted'],1);self.assertFalse(staging.exists())

    def test_staging_cleanup_protects_a_live_owner(self):
        from production_compiler import staging_cleanup
        staging=self.root/'production/staging/live'
        staging.mkdir(parents=True)
        self.write('production/staging/live/owner.json', {
            'operation_id':'op-live','pid':os.getpid(),'created_at':'2026-10-02T00:00:00+00:00','phase':'compiling'
        })
        report=staging_cleanup(self.root,operation_id='op-live',apply=True)
        self.assertEqual(report['deleted'],0);self.assertTrue(staging.exists())
        self.assertIn('active',report['items'][0]['reasons'][0])

    def test_idempotent_object(self):
        run=self.prepare(); path=w.run_dir(self.root,run); self.assertEqual(c.object_store(path,b'abc'),c.object_store(path,b'abc'))
    def no_hard_links(self):
        """The refusal of os.link on FAT and exFAT: ERROR_INVALID_FUNCTION on Windows, EPERM on Linux."""
        if os.name=='nt': return patch.object(c.os,'link',side_effect=OSError(None,'Incorrect function',None,1))
        return patch.object(c.os,'link',side_effect=PermissionError(errno.EPERM,'Operation not permitted'))
    def published(self):
        folder=self.root/'published'; folder.mkdir(exist_ok=True); return folder
    def test_exclusive_write_publishes_a_new_name_whole_without_hard_links(self):
        folder=self.published()
        with self.no_hard_links(): c.atomic(folder/'record.json',b'{"a":1}\n')
        self.assertEqual((folder/'record.json').read_bytes(),b'{"a":1}\n')
        self.assertEqual([p.name for p in folder.iterdir()],['record.json'])
    def test_exclusive_write_refuses_an_existing_name_with_and_without_hard_links(self):
        folder=self.published(); (folder/'record.json').write_bytes(b'first\n')
        with self.no_hard_links(), self.assertRaises(FileExistsError): c.atomic(folder/'record.json',b'second\n')
        with self.assertRaises(FileExistsError): c.atomic(folder/'record.json',b'second\n')
        self.assertEqual((folder/'record.json').read_bytes(),b'first\n')
        self.assertEqual([p.name for p in folder.iterdir()],['record.json'])
    def test_exclusive_write_raises_other_link_errors(self):
        folder=self.published()
        if os.name=='nt': failure=OSError(None,'Too many links',None,1142)
        else: failure=OSError(errno.EMLINK,'Too many links')
        with patch.object(c.os,'link',side_effect=failure):
            with self.assertRaises(OSError) as raised: c.atomic(folder/'record.json',b'{}\n')
        self.assertIs(raised.exception,failure); self.assertEqual(list(folder.iterdir()),[])
    def test_failed_publication_without_hard_links_leaves_no_file(self):
        folder=self.published()
        if os.name=='nt': failing=patch.object(c.os,'rename',side_effect=OSError(errno.EIO,'Input/output error'))
        else:
            real=os.fsync; calls=[]
            def second_fails(descriptor):
                calls.append(descriptor)
                if len(calls)==2: raise OSError(errno.EIO,'Input/output error')
                return real(descriptor)
            failing=patch.object(c.os,'fsync',side_effect=second_fails)
        with self.no_hard_links(), failing, self.assertRaises(OSError): c.atomic(folder/'record.json',b'x\n')
        self.assertEqual(list(folder.iterdir()),[])
    def test_object_store_works_without_hard_links(self):
        folder=self.published()
        with self.no_hard_links(): key=c.object_store(folder,b'payload'); again=c.object_store(folder,b'payload')
        self.assertEqual((key,c.object_read(folder,key)),(again,b'payload'))
    def test_skill_files_are_pinned_without_copies(self):
        run=self.prepare(); directory=w.run_dir(self.root,run); prepared=c.load(directory/'prepared.json')
        skill=[d for d in prepared['dependencies'] if d['space']=='skill']
        self.assertIn('scripts/production_workflow.py',{d['path'] for d in skill})
        self.assertEqual({p.name for p in (directory/'objects').iterdir()},
                         {d['sha256'] for d in prepared['dependencies'] if d['space']!='skill'})
        with tempfile.TemporaryDirectory() as temporary:
            copied=Path(temporary)
            for d in skill:
                target=copied/d['path']; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/d['path'],target)
            changed=copied/'scripts/production_workflow.py'
            with patch.object(w,'ROOT',copied):
                w.assert_current(self.root,run)
                changed.write_bytes(changed.read_bytes()+b'\n')
                from production_diagnostics import ProductionError
                with self.assertRaises(ProductionError) as caught: w.assert_current(self.root,run)
                self.assertEqual(caught.exception.diagnostic.code,'IMPLEMENTATION_CHANGED')
                self.assertEqual(caught.exception.diagnostic.file,'scripts/production_workflow.py')
                self.assertEqual(w.status(self.root,run)['runs'][0]['readiness'],'blocked')
    def clone_run(self,run,task_id=None):
        from pack_manager import generate_uuid7
        target=self.root/'production'/generate_uuid7(); shutil.copytree(w.run_dir(self.root,run),target)
        if task_id is not None:
            prepared=c.load(target/'prepared.json'); prepared['task']['task_id']=task_id
            prepared.pop('input_sha256'); prepared['input_sha256']=c.content_id(prepared)
            (target/'prepared.json').write_bytes(c.encoded(prepared))
        return target
    def test_reservations_skip_other_entries_and_other_tasks(self):
        run=self.prepare()
        (self.root/'production/.DS_Store').write_bytes(b'\x00\x01'); (self.root/'production/README').write_text('Notes.\n', encoding='utf-8')
        other=self.clone_run(run,task_id=str(uuid.uuid4())); next((other/'objects').iterdir()).write_bytes(b'damaged')
        self.assertEqual(fixture.handoff(self.root,run,'test','manual')['event'],'handoff')
    def test_damaged_run_is_reported_without_hiding_other_runs(self):
        run=self.prepare(); damaged=self.prepare()
        (w.run_dir(self.root,damaged)/'prepared.json').write_bytes(b'{}')
        report=w.status(self.root,budget=True)
        self.assertFalse(report['ok'])
        states={row['run']:row for row in report['runs']}
        self.assertEqual(states[run]['integrity'],'intact')
        self.assertEqual(states[damaged]['integrity'],'blocked')
        self.assertFalse(report['budget']['complete'])
        with self.assertRaises(ValueError): w.assert_current(self.root,damaged)
    @unittest.skipUnless(os.name=='nt','Windows byte-range lock')
    def test_lock_raises_an_error_other_than_contention(self):
        import errno,msvcrt
        calls=[]
        def failing(*args):
            calls.append(args)
            if len(calls)>1: raise AssertionError('a device error was retried as contention')
            raise OSError(errno.EIO,'synthetic device error')
        with patch.object(msvcrt,'locking',side_effect=failing):
            with self.assertRaises(OSError):
                with c.lock(self.root): pass
        real=msvcrt.locking; modes=[]
        def contended(descriptor,mode,size):
            modes.append(mode)
            if len(modes)==1: raise OSError(errno.EACCES,'synthetic contention')
            return real(descriptor,mode,size)
        with patch.object(msvcrt,'locking',side_effect=contended):
            with c.lock(self.root): pass
        self.assertEqual(modes,[msvcrt.LK_NBLCK,msvcrt.LK_NBLCK,msvcrt.LK_UNLCK])
    def test_cli_resolves_a_linked_root(self):
        run=self.prepare()
        with tempfile.TemporaryDirectory() as temporary:
            link=Path(temporary)/'linked-studio'
            try: link.symlink_to(self.root,target_is_directory=True)
            except OSError: self.skipTest('symbolic links are unavailable')
            out=io.StringIO()
            with patch('sys.argv',['production_workflow.py','status','--root',str(link),'--run',run]),contextlib.redirect_stdout(out):
                code=w.main()
        report=json.loads(out.getvalue())
        self.assertEqual(report['runs'][0]['integrity'],'intact',report); self.assertEqual(code,0)
    def test_finish_resumes_after_journal_publish(self):
        run,_=self.finish(); ledger.step_done(self.root,1); ledger.step_done(self.root,2)
        original=ledger.write_current
        def crash(root,value):
            if value is None: raise OSError('Synthetic crash before current removal')
            return original(root,value)
        with patch.object(ledger,'write_current',side_effect=crash):
            with self.assertRaises(OSError): ledger.finish(self.root)
        ledger.finish(self.root)
        self.assertEqual(len([e for e in ledger.read_ledger(self.root) if e['event']=='finished']),1)
    def test_concurrent_begin_has_one_owner(self):
        ledger.abandon(self.root,'Replace the fixture task.')
        def begin(_):
            try: return ledger.begin(self.root,'Concurrent task',['one'])['task_id']
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool: values=list(pool.map(begin,range(2)))
        self.assertEqual(sum(x is not None for x in values),1)
    def test_real_world_view_and_plan_only_change(self):
        source=ROOT/'examples/world-realization'
        for p in source.iterdir():
            if p.is_file(): shutil.copy2(p,self.root/p.name)
        import world_realization as world
        compiled=world.compile_plan(self.root,'plan.json'); world.publish(compiled,self.root/'bundle')
        u=compiled['units'][0]; v=u['views'][0]
        self.spec['route']='world-realization'; self.spec['world_views']=[{'plan':'plan.json','bundle':'bundle','unit_id':u['unit_id'],'view_id':v['view_id']}]; self.save_spec()
        run=self.prepare(); self.assertTrue(w.status(self.root,run)['ok'])
        plan=c.load(self.root/'plan.json'); plan['units'][0]['review_note']='Only this instruction changed.'; self.write('plan.json',plan)
        self.assertEqual(w.status(self.root,run)['runs'][0]['readiness'],'blocked')


class CopyProjectTests(unittest.TestCase):
    """The shared helper that gives each test its own copy of a prepared studio."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.origin=self.base/'origin';(self.origin/'nested').mkdir(parents=True)
        self.outside=self.base/'outside';self.outside.mkdir();(self.outside/'data.json').write_bytes(b'{}')

    def test_a_symbolic_link_is_copied_as_a_link(self):
        import production_case_fixtures as cases
        try:(self.origin/'nested/linked').symlink_to(self.outside,target_is_directory=True)
        except OSError:self.skipTest('symbolic links are unavailable')
        copied=cases.copy_studio(self.origin,self.base/'copy')
        self.assertTrue((copied/'nested/linked').is_symlink())
        self.assertEqual(os.readlink(copied/'nested/linked'),os.readlink(self.origin/'nested/linked'))

    @unittest.skipUnless(os.name=='nt','directory junctions are a Windows feature')
    def test_a_studio_holding_a_junction_is_refused_before_anything_is_copied(self):
        import subprocess
        import production_case_fixtures as cases
        made=subprocess.run(['cmd','/c','mklink','/J',str(self.origin/'nested/joined'),str(self.outside)],capture_output=True)
        if made.returncode!=0:self.skipTest('this file system makes no directory junction')
        with self.assertRaisesRegex(ValueError,'joined is a directory junction'):
            cases.copy_studio(self.origin,self.base/'copy')
        self.assertFalse((self.base/'copy').exists())


def cold(test):
    """Mark a test that builds its synthetic case from an empty folder instead of copying the class's prepared studio."""
    test.cold_setup=True
    return test


class PackageIntegrationTests(unittest.TestCase):
    """Full synthetic requests exercise the same compiler and execution as the CLI.

    The class builds the pack, runtime state, catalog cache, studio, prepared
    run and decision file once, and each test works on its own copy and home.
    No test here edits the pack or the runtime state. A test marked `cold`
    builds everything itself, so the uncopied setup stays covered end to end.
    Another suite's test that calls this setUp without the class setup also
    builds everything itself.
    """
    @staticmethod
    def build(base):
        import production_case_fixtures as cases
        case=cases.create(base/'studio',base/'runtime')
        spec=case['task']
        spec['recording'].update(slot='base.front',sheet_panel=True,subject_map={'robot':'robot'})
        spec['generation']['continuity']['robot']='undecided'
        spec['generation']['count']=2
        cases.write(case['root']/'task.json',spec)
        return case,spec,w.prepare(case['root'],'task.json')['run']

    @classmethod
    def setUpClass(cls):
        from catalog_cli import configure_pack_runtime
        from test_production_execution import decisions
        temp=tempfile.TemporaryDirectory();cls.addClassCleanup(temp.cleanup)
        base=Path(temp.name);cls.enterClassContext(fixture.scratch_home(base/'home'))
        cls.addClassCleanup(configure_pack_runtime,None)
        cls.case,cls.prepared_spec,cls.prepared_run=PackageIntegrationTests.build(base)
        cls.prepared_decisions=decisions(cls.case['root'],cls.prepared_run)

    def setUp(self):
        import production_case_fixtures as cases
        import production_execution as execution
        import transport_synthetic
        from catalog_cli import configure_pack_runtime
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.enterContext(fixture.scratch_home(self.base/'home'))
        self.addCleanup(configure_pack_runtime,None)
        if getattr(getattr(self,self._testMethodName),'cold_setup',False) or not hasattr(self,'prepared_run'):
            case,self.spec,self.run=PackageIntegrationTests.build(self.base)
            self.root=case['root'];self.decision_file=None
        else:
            configure_pack_runtime(self.case['settings'])
            self.root=cases.copy_studio(self.case['root'],self.base/'studio')
            self.spec=copy.deepcopy(self.prepared_spec);self.run=self.prepared_run;self.decision_file=self.prepared_decisions
        # Every copy carries the same request_id, so each test meets a synthetic service that has answered nothing.
        self.enterContext(patch.dict(transport_synthetic._ANSWERED,clear=True))
        self.data=execution.compiled(self.root,self.run)
        self.package=self.data[4];self.package_path=self.data[0]/'package.json'
        self.composition=self.package['composition_prompt']

    def execute(self):
        import production_execution as execution
        from test_production_execution import decisions
        return execution.execute(self.root,self.run,decisions_file=self.decision_file or decisions(self.root,self.run))

    def prepare_adopted_selection(self):
        import production_case_fixtures as cases
        import studio
        from visual_continuity import file_ref
        output=self.execute();candidate=output['runs'][0]['candidates'][0]
        row=studio.read_iterations(studio.character_dir(self.root,'robot'))[0]
        review=w.draft_review(self.root,self.run,candidate)
        review.update(reviewer=fixture.ACTOR,observations=[{'locator':{'kind':'whole'},
            'observation':'The actual local synthetic PNG was inspected.'}],conclusion='Synthetic fixture, not user approval.')
        fixture.observation(review)
        for check in review['checks']:check.update(verdict='pass',observation_indices=[0],reason='Actual fixture bytes exist.')
        cases.write(self.root/'review.json',review);w.review(self.root,self.run,'review.json')
        cases.write(self.root/'adoption-basis.txt','Explicit synthetic identity adoption. Not user consent.')
        approval={'scope':'sheet','influence':'identity','character':'robot','iteration_id':row['iteration_id'],
            'slot':row['slot'],'image_sha256':row['result']['sha256'],'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z',
            'continuity_decision':{'character_id':'robot','continuity':'recurring',
                'basis':file_ref(self.root,'adoption-basis.txt',locator='whole'),'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z'}}
        cases.write(self.root/'approval.json',approval)
        # Adoption starts from the run's current selection of the candidate.
        delivery=w.draft_selection(self.root,self.run,candidate)
        delivery.update(reason='Synthetic delivery selection before adoption.')
        fixture.selection(self.root,self.run,delivery)
        cases.write(self.root/'delivery-selection.json',delivery);w.select(self.root,self.run,'delivery-selection.json')
        intent=w.adoption_intent(self.root,self.run,candidate,'robot',row['iteration_id'],approval)
        auth=fixture.grant(self.root,self.run,intent)
        first=w.adopt(self.root,self.run,candidate,'robot',row['iteration_id'],'approval.json',auth)
        self.assertEqual(first,w.adopt(self.root,self.run,candidate,'robot',row['iteration_id'],'approval.json',auth))
        selection=w.draft_selection(self.root,self.run,candidate)
        selection.update(selector=fixture.ACTOR,reason='Actual synthetic owner connection.',scope='studio-adoption',
            adoption={'character':'robot','iteration_id':row['iteration_id'],'scope':'sheet'})
        fixture.selection(self.root,self.run,selection)
        cases.write(self.root/'selection.json',selection)
        return row,selection

    @cold
    def test_production_adoption_claims_separate_authority_and_completes(self):
        self.prepare_adopted_selection()
        self.assertTrue(any(r['event']=='adoption-claim' for r in w.load_run(self.root,self.run)[3]))
        w.select(self.root,self.run,'selection.json');w.complete(self.root,self.run)
        self.assertEqual(w.verify_completion(self.root,self.run,self.spec['task_id'])['event'],'completion')

    def test_owner_change_after_completion_is_not_current(self):
        row,_=self.prepare_adopted_selection();w.select(self.root,self.run,'selection.json');w.complete(self.root,self.run)
        (self.root/'characters/robot/adoptions'/f"{row['iteration_id']}.json").write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):w.verify_completion(self.root,self.run,self.spec['task_id'])

    def test_real_studio_adoption_matches_selected_bytes(self):
        self.prepare_adopted_selection();w.select(self.root,self.run,'selection.json')
        self.assertEqual(w.complete(self.root,self.run)['data']['scope'],'studio-adoption')

    def test_adoption_edit_invalidates_completion(self):
        row,_=self.prepare_adopted_selection();w.select(self.root,self.run,'selection.json')
        (self.root/'characters/robot/adoptions'/f"{row['iteration_id']}.json").write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):w.complete(self.root,self.run)

    def test_adoption_wrong_scope_not_selected(self):
        _,selection=self.prepare_adopted_selection();selection['adoption']['scope']='another scope'
        (self.root/'selection.json').write_bytes(c.encoded(selection))
        with self.assertRaises(ValueError):w.select(self.root,self.run,'selection.json')

    def test_real_verifier_bound_input(self):
        from verify_generation_payload import verify
        import runtime_snapshot
        descriptor=self.data[1]['runtime_snapshot'];directory=self.data[0]
        with runtime_snapshot.using(runtime_snapshot.path(self.root,descriptor),descriptor):
            self.assertTrue(verify(self.package,package_root=directory,studio=self.root,
                                  reading_ledgers=[directory/'reads.jsonl'])['verified'])

    def test_cross_run_binding(self):
        with self.assertRaises(ValueError):binding.validate_live(self.root,w.prepare(self.root,'task.json')['run'],self.package)

    def test_bound_dispatch_cannot_omit_context(self):
        with self.assertRaises(ValueError):binding.validate_live(None,None,self.package)

    def test_live_input_drift(self):
        (self.root/'prompt.txt').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):binding.validate_live(self.root,self.run,self.package)

    def test_claim_prevents_duplicate_send(self):
        import production_execution as execution
        import transport_synthetic
        self.execute()
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No second send')):
            with self.assertRaises(ValueError):execution.execute(self.root,self.run)
        self.assertEqual(sum(r['event']=='dispatch-claim' for r in w.load_run(self.root,self.run)[3]),1)

    def test_intent_names_inputs_by_hash_and_the_claim_checks_their_bytes(self):
        import production_execution as execution
        import reservation_lifecycle as accounting
        from test_production_execution import decisions
        from production_diagnostics import ProductionError
        plan=self.data[6];intent=plan['operations'][-1];snapshots=self.package['input_snapshots']
        self.assertEqual(intent['payload']['validation_inputs'],{path:item['sha256'] for path,item in snapshots.items()})
        self.assertNotIn('base64',c.encoded(intent).decode('utf-8'))
        unnamed=copy.deepcopy(intent);del unnamed['payload']['validation_inputs'][self.package['request_validation']['contract']['path']]
        with self.assertRaisesRegex(ValueError,'does not name the validation contract'):
            w.draft_authorization(self.root,self.run,'fixture-grant',unnamed)
        execution.authorize_decisions(self.root,self.run,decisions(self.root,self.run),self.data[1],plan)
        tokens=execution.receipts(self.root,self.data[1],w.load_run(self.root,self.run)[3],plan)
        journal,rendered=execution._journal(self.root,self.run,self.data)
        w.handoff(self.root,self.run,plan['handoff']['recipient'],'dispatcher',tokens['direction'],journal=journal.path)
        changed=copy.deepcopy(self.package);changed['input_snapshots'][sorted(snapshots)[0]]['sha256']='a'*64
        with self.assertRaises(ProductionError) as caught:
            w.claim_dispatch(self.root,self.run,changed,{},journal.path,intent,tokens['submit'],rendered=rendered)
        self.assertEqual(caught.exception.diagnostic.pointer,'$.package_sha256')
        self.assertEqual(accounting.all_states(self.root),[])

    def test_partial_acquisition_preserves_candidates_and_resumes(self):
        import dispatch,production_execution as execution,transport_synthetic
        original=dispatch.inline_image;seen=[]
        def once(raw):
            seen.append(raw)
            if len(seen)==2:raise OSError('Synthetic interruption of the second download')
            return original(raw)
        with patch.object(dispatch,'inline_image',side_effect=once):result=self.execute()
        self.assertEqual(result['runs'][0]['capture'],'partial')
        self.assertEqual(len(result['runs'][0]['candidates']),1)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('Resume must not send')):
            result=execution.resume(self.root,self.run)
        self.assertEqual(result['runs'][0]['capture'],'complete')
        self.assertEqual(len(result['runs'][0]['candidates']),2)

    def test_dispatch_then_recording_recovery_is_idempotent_without_resubmission(self):
        import dispatch,studio,production_execution as execution,transport_synthetic
        real=studio.iterate;calls=[]
        def fail_second(*a,**kw):
            calls.append(1)
            if len(calls)==2:raise OSError('Synthetic interruption after acquisition')
            return real(*a,**kw)
        with patch.object(studio,'iterate',side_effect=fail_second):result=self.execute()
        self.assertFalse(result['execution_completed'])
        self.assertEqual(len(result['runs'][0]['candidates']),2)
        (self.root/'prompt.txt').unlink()
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No resubmission')), \
             patch.object(dispatch,'api_key',side_effect=AssertionError('Recovery needs no API credential')):
            first=execution.resume(self.root,self.run);second=execution.resume(self.root,self.run)
        self.assertTrue(first['execution_completed']);self.assertTrue(second['execution_completed'])
        self.assertEqual(first['runs'][0]['candidates'],second['runs'][0]['candidates'])
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'robot'))),2)
        self.assertEqual(sum(r['event']=='dispatch-claim' for r in w.load_run(self.root,self.run)[3]),1)

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
