#!/usr/bin/env python3
"""Current-form offline tests for actual production evidence and execution edges."""
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
        elif isinstance(value,str): p.write_text(value,encoding='utf-8')
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
        run=self.prepare(); b=binding.create(self.root,run,'Describe one lamp.'); binding.validate(b,'Describe one lamp.')
    def test_wrong_delivery_binding(self):
        run=self.prepare()
        with self.assertRaises(ValueError): binding.create(self.root,run,'Another picture.')
    def test_binding_changed_without_digest(self):
        run=self.prepare(); b=binding.create(self.root,run,'Describe one lamp.'); b['consumer']['instructions']='changed'
        with self.assertRaises(ValueError): binding.validate(b,'Describe one lamp.')
    def test_authored_rendition_no_prefix(self):
        run=self.prepare(); b=binding.create(self.root,run,'Describe one lamp.')
        self.assertEqual(binding.effective(b,'TAG_1, TAG_2'),'TAG_1, TAG_2')
    def test_bounded_prefix_only_explicit_fields(self):
        self.spec['delivery']['transport']='bounded-context'; self.save_spec(); run=self.prepare()
        b=binding.create(self.root,run,'Describe one lamp.'); text=binding.effective(b,'prompt',context_transport='prompt-prefix')
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
        run=self.prepare(); self.write('brief.md','changed'); self.assertFalse(w.status(self.root,run)['ok'])
    def test_changed_delivery(self):
        run=self.prepare(); self.write('delivery.txt','changed'); self.assertFalse(w.status(self.root,run)['ok'])
    def test_changed_criteria(self):
        run=self.prepare(); self.spec['criteria'][0]['text']='changed'; self.save_spec(); self.assertFalse(w.status(self.root,run)['ok'])
    def test_changed_task_only_note(self):
        run=self.prepare(); self.spec['delivery']['translation_notes']='Different meaning'; self.save_spec(); self.assertFalse(w.status(self.root,run)['ok'])
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
        run,ca=self.candidate(); path=next((w.run_dir(self.root,run)/'records').iterdir()); path.write_text('{}',encoding='utf-8'); self.assertFalse(w.status(self.root,run)['ok'])
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
    def test_candidate_edit_after_review(self):
        run,ca=self.candidate(); self.record_review(run,ca); self.write('output.txt','Changed output')
        with self.assertRaises(ValueError): self.select(run,ca)
    def test_review_edit_after_recording(self):
        run,ca=self.candidate(); self.record_review(run,ca); self.write('review.json',{})
        with self.assertRaises(ValueError): self.select(run,ca)
    def test_selection_edit_after_recording(self):
        run,ca=self.candidate(); self.record_review(run,ca); self.select(run,ca); self.write('selection.json',{})
        with self.assertRaises(ValueError): w.complete(self.root,run)
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
        original=Path.rename; calls=[]
        def flaky(path,destination):
            calls.append(1)
            if len(calls)==1: raise PermissionError(13,'Permission denied')
            return original(path,destination)
        with patch.object(Path,'rename',flaky): c.publish_directory(staging,target)
        self.assertTrue(target.is_dir()); self.assertFalse(staging.exists()); self.assertEqual(len(calls),2)
    def test_publish_directory_raises_a_persistent_refusal(self):
        staging=self.root/'.pending-y'; staging.mkdir(); target=self.root/'never'
        def refused(path,destination): raise PermissionError(13,'Permission denied')
        with patch.object(Path,'rename',refused):
            with self.assertRaises(PermissionError): c.publish_directory(staging,target,patience=0.3)
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
        self.assertIsNone(ledger.read_current(self.root)); self.assertEqual(w.status(self.root,run)['next'],'done')
    def test_wrong_task_completion(self):
        run,done=self.finish()
        with self.assertRaises(ValueError): w.verify_completion(self.root,run,'not-the-task')
    def test_unfinished_steps_still_block_finish(self):
        self.finish()
        with self.assertRaises(ValueError): ledger.finish(self.root)
    def test_temp_receipt_has_no_phase_authority(self):
        run=self.prepare(); (w.run_dir(self.root,run)/'records/.pending-fixture').write_bytes(b'partial')
        self.assertEqual(w.status(self.root,run)['next'],'authorize-direction-and-handoff')
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
                         {d['sha256'] for d in prepared['dependencies'] if d['space']=='project'})
        # A copy of the pinned installation stands in for the skill, so one of its files can change.
        with tempfile.TemporaryDirectory() as temporary:
            copy=Path(temporary)
            for d in skill:
                target=copy/d['path']; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/d['path'],target)
            changed=copy/'scripts/production_workflow.py'
            with patch.object(w,'ROOT',copy):
                w.assert_current(self.root,run)
                raw=changed.read_bytes(); changed.write_bytes(raw[:-1]+(b'\n' if raw[-1:]==b' ' else b' '))
                with self.assertRaisesRegex(ValueError,'changed skill input: scripts/production_workflow.py'):
                    w.assert_current(self.root,run)
                self.assertFalse(w.status(self.root,run)['ok'])
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
    def test_damaged_run_of_this_task_fails_closed(self):
        run=self.prepare(); copy=self.clone_run(run); next((copy/'objects').iterdir()).write_bytes(b'damaged')
        with self.assertRaises(ValueError): fixture.handoff(self.root,run,'test','manual')
        (copy/'prepared.json').write_bytes(b'{}')
        with self.assertRaises(ValueError): fixture.handoff(self.root,run,'test','manual')
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
            link=Path(temporary)/'linked-project'
            try: link.symlink_to(self.root,target_is_directory=True)
            except OSError: self.skipTest('symbolic links are unavailable')
            out=io.StringIO()
            with patch('sys.argv',['production_workflow.py','status','--root',str(link),'--run',run]),contextlib.redirect_stdout(out):
                code=w.main()
        report=json.loads(out.getvalue())
        self.assertTrue(report['integrity']['ok'],report); self.assertEqual(code,0)
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
        self.assertFalse(w.status(self.root,run)['ok'])


class PackageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        from catalog_cli import configure_pack_runtime
        from pack_manager import default_settings
        configure_pack_runtime(default_settings(
            state_file=self.base/'pack-state.json', cache_dir=self.base/'cache',
            managed_root=self.base/'managed',
            default_enabled_packs=[c.load(ROOT/'packs/commons/pack.json')['pack_id']]))
        self.addCleanup(configure_pack_runtime, None)
        import studio
        self.root=studio.init(self.base/'studio','production-test','Offline production tests'); studio.add_character(self.root,'C01','')
        self.package=json.loads((ROOT/'examples/state-aware-pilot/generated/generation-package.json').read_text(encoding='utf-8'))
        self.composition=self.package['composition_prompt']
        task=ledger.begin(self.root,'Synthetic package test',['prepare','render'])
        (self.root/'delivery.txt').write_text(self.composition, encoding='utf-8')
        self.spec={'task_id':task['task_id'],'route':'development','features':[],'sources':[],
                   'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Use exact authored prompt.'},'criteria':[{'id':'bytes','strength':'hard','text':'Captured fixture bytes are actually available.'}],'world_views':[]}
        fixture.task(self.root,self.spec,artifact='binary',execution='dispatcher')
        (self.root/'task.json').write_bytes(c.encoded(self.spec)); self.run=w.prepare(self.root,'task.json')['run']
        self.package=fixture.bind_package(self.root,self.run,self.package)
        from build_generation_payload import generation_input_sha256
        key=generation_input_sha256(self.package); self.package['generation_input_sha256']=key; self.package['generation_contract']['generation_input_sha256']=key
        self.package_path=self.root/'package.json'; self.package_path.write_text(json.dumps(self.package), encoding='utf-8')

    def prepare_adopted_selection(self, *, through_production=False):
        self.spec['execution']='authored'
        (self.root/'task.json').write_bytes(c.encoded(self.spec))
        self.run=w.prepare(self.root,'task.json')['run']
        self.package=fixture.bind_package(self.root,self.run,self.package)
        from build_generation_payload import generation_input_sha256
        key=generation_input_sha256(self.package); self.package['generation_input_sha256']=key; self.package['generation_contract']['generation_input_sha256']=key
        self.package_path.write_text(json.dumps(self.package), encoding="utf-8")
        import studio,adoption_workflow as adoption
        from PIL import Image
        image=self.root/'fixture.png'; Image.new('RGB',(24,24)).save(image)
        row=studio.iterate(self.root,'C01','base.front',image,package=self.package_path,request=None,response=None,note='Synthetic fixture')
        approval={'scope':'sheet','influence':'identity','character':'C01','iteration_id':row['iteration_id'],'slot':row['slot'],
                  'image_sha256':row['result']['sha256'],'by':fixture.ACTOR,'at':'2026-09-16T00:00:00Z'}
        from visual_continuity import file_ref
        (self.root/'synthetic-continuity.txt').write_text('Synthetic fixture decision: this single-subject candidate represents C01 and may recur. Not user consent.\n', encoding='utf-8')
        approval['continuity_decision']={'character_id':'C01','continuity':'recurring',
            'basis':file_ref(self.root,'synthetic-continuity.txt',locator='whole'),
            'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z'}
        if not through_production:
            adoption.adopt(self.root,'C01',row['iteration_id'],approval)
        fixture.handoff(self.root,self.run,'test','manual')
        ca=w.capture(self.root,self.run,'fixture.png','Synthetic adopted fixture')
        d=w.draft_review(self.root,self.run,ca['sha256'])
        d.update(reviewer='Synthetic reviewer',observations=[{'locator':{'kind':'whole'},'observation':'Synthetic image fixture inspected.'}],conclusion='Test only.')
        fixture.observation(d)
        for check in d['checks']:
            check.update(verdict='pass',observation_indices=[0],reason='Actual captured fixture bytes exist.')
        (self.root/'review.json').write_bytes(c.encoded(d)); w.review(self.root,self.run,'review.json')
        if through_production:
            (self.root/'approval.json').write_bytes(c.encoded(approval))
            intent=w.adoption_intent(self.root,self.run,ca['sha256'],'C01',row['iteration_id'],approval)
            auth=fixture.grant(self.root,self.run,intent)
            result=w.adopt(self.root,self.run,ca['sha256'],'C01',row['iteration_id'],'approval.json',auth)
            self.assertEqual(result,w.adopt(self.root,self.run,ca['sha256'],'C01',row['iteration_id'],'approval.json',auth))
        d=w.draft_selection(self.root,self.run,ca['sha256'])
        d.update(selector='Synthetic selector',reason='Test actual owner connection.',scope='studio-adoption',adoption={'character':'C01','iteration_id':row['iteration_id'],'scope':'sheet'})
        fixture.selection(self.root,self.run,d)
        (self.root/'selection.json').write_bytes(c.encoded(d))
        return row,d
    def test_production_adoption_claims_separate_authority_and_completes(self):
        self.prepare_adopted_selection(through_production=True)
        rows=w.load_run(self.root,self.run)[3]
        self.assertTrue(any(r['event']=='adoption-claim' for r in rows))
        w.select(self.root,self.run,'selection.json');w.complete(self.root,self.run)
        self.assertEqual(w.verify_completion(self.root,self.run,self.spec['task_id'])['event'],'completion')
    def test_owner_change_after_completion_is_not_current(self):
        row,_=self.prepare_adopted_selection();w.select(self.root,self.run,'selection.json');w.complete(self.root,self.run)
        (self.root/'characters/C01/adoptions'/f"{row['iteration_id']}.json").write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):w.verify_completion(self.root,self.run,self.spec['task_id'])
    def test_real_studio_adoption_matches_selected_bytes(self):
        self.prepare_adopted_selection(); w.select(self.root,self.run,'selection.json')
        self.assertEqual(w.complete(self.root,self.run)['data']['scope'],'studio-adoption')
    def test_adoption_edit_invalidates_completion(self):
        row,_=self.prepare_adopted_selection(); w.select(self.root,self.run,'selection.json')
        (self.root/'characters/C01/adoptions'/f"{row['iteration_id']}.json").write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError): w.complete(self.root,self.run)
    def test_adoption_wrong_scope_not_selected(self):
        row,d=self.prepare_adopted_selection(); d['adoption']['scope']='another scope'
        (self.root/'selection.json').write_bytes(c.encoded(d))
        with self.assertRaises(ValueError): w.select(self.root,self.run,'selection.json')
    def test_real_verifier_bound_input(self):
        from verify_generation_payload import verify
        self.assertTrue(verify(self.package,package_root=ROOT/'examples/state-aware-pilot/generated',project=self.root)['verified'])
    def test_cross_run_binding(self):
        with self.assertRaises(ValueError): binding.validate_live(self.root,w.prepare(self.root,'task.json')['run'],self.package)
    def test_bound_dispatch_cannot_omit_context(self):
        with self.assertRaises(ValueError): binding.validate_live(None,None,self.package)
    def test_live_input_drift(self):
        (self.root/'delivery.txt').write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError): binding.validate_live(self.root,self.run,self.package)
    def test_claim_prevents_duplicate_send(self):
        fixture.handoff(self.root,self.run,'test transport','dispatcher'); journal=self.root/'runs'/'fixture'; journal.mkdir()
        v={'host_forwarding':{'effective_prompt_sha256':'a'*64}}
        fixture.claim(self.root,self.run,self.package,v,journal)
        with self.assertRaises(ValueError): fixture.claim(self.root,self.run,self.package,v,journal)
    def test_intent_names_inputs_by_hash_and_the_claim_checks_their_bytes(self):
        import base64
        fixture.handoff(self.root,self.run,'test transport','dispatcher'); journal=self.root/'runs'/'fixture'; journal.mkdir()
        rendered=fixture.rendered_request(self.package,seed=None,count=2); target=rendered['sealed']['target']
        intent=w.submission_intent(self.package,rendered=rendered,seed=None,count=2,service={},
                                   offering={'service':target['service'],'model_identifier':target['model_identifier']})
        snapshots=self.package['input_snapshots']
        self.assertEqual(intent['payload']['input_sha256'],{path:item['sha256'] for path,item in snapshots.items()})
        self.assertNotIn('base64',c.encoded(intent).decode('utf-8'))
        unnamed=copy.deepcopy(intent); del unnamed['payload']['input_sha256'][self.package['request_validation']['contract']['path']]
        with self.assertRaisesRegex(ValueError,'does not name the validation contract'):
            w.draft_authorization(self.root,self.run,'fixture-grant',unnamed)
        authorization=fixture.grant(self.root,self.run,intent)
        (journal/'request-contract.json').write_bytes(c.encoded(rendered))
        changed=copy.deepcopy(self.package); raw=b'{"synthetic": "other bytes"}\n'
        changed['input_snapshots'][sorted(snapshots)[0]]={'sha256':c.digest(raw),'size':len(raw),'base64':base64.b64encode(raw).decode('ascii')}
        v={'host_forwarding':{'effective_prompt_sha256':'a'*64}}
        with self.assertRaisesRegex(ValueError,'input bytes differ'):
            w.claim_dispatch(self.root,self.run,changed,v,journal,intent,authorization,rendered=rendered)
        self.assertEqual(w.claim_dispatch(self.root,self.run,self.package,v,journal,intent,authorization,rendered=rendered)['event'],'dispatch-claim')
    def test_partial_acquisition_cannot_be_recovered(self):
        fixture.handoff(self.root,self.run,'test transport','dispatcher'); journal=self.root/'runs'/'fixture'; journal.mkdir()
        fixture.claim(self.root,self.run,self.package,{'host_forwarding':{'effective_prompt_sha256':'a'*64}},journal)
        with self.assertRaises(ValueError): w.record_dispatch_results(self.root,self.run,self.package,journal,[],2)
        with self.assertRaises(ValueError): w.recover_recording(self.root,self.run)
    def test_dispatch_then_recording_recovery_is_offline_and_idempotent(self):
        import dispatch,studio
        fixture.handoff(self.root,self.run,'test transport','dispatcher')
        options=argparse.Namespace(package=self.package_path,character='C01',slot='base.front',service=None,profiles=None,seed=None,count=2,send=True,note=None)
        entries=[{'url':'https://example.invalid/1.png','id':'one','seed':1},{'url':'https://example.invalid/2.png','id':'two','seed':2}]
        transport=SimpleNamespace(media_paths=Mock(return_value=[]),upload=Mock(),build=Mock(return_value={'taskUUID':'test-request'}),send=Mock(return_value={'data':'fixture'}),rejections=Mock(return_value=[]),results=Mock(return_value=entries),observation_outcome=Mock(return_value='accepted'),RESULT_HOSTS=frozenset({'example.invalid'}))
        rendered=fixture.rendered_request(self.package,seed=None,count=2)
        target=rendered['sealed']['target']
        offering={'service':target['service'],'model_identifier':target['model_identifier'],'observed_at':'fixture'}
        options.production_authorization=fixture.grant(self.root,self.run,w.submission_intent(self.package,rendered=rendered,seed=None,count=2,offering=offering,service={}))
        real_iterate=studio.iterate; calls=[]
        def fail_second(*a,**kw):
            calls.append(1)
            if len(calls)==2: raise OSError('synthetic interruption after acquisition')
            return real_iterate(*a,**kw)
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO())); stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            stack.enter_context(patch.object(dispatch,'resolve_model_record',return_value=('fixture',{})))
            stack.enter_context(patch.object(dispatch,'select_offering',return_value=offering))
            stack.enter_context(patch.object(dispatch,'service_for',return_value=('test',{},transport)))
            stack.enter_context(patch.object(dispatch,'check_request'))
            # This test isolates durable recording; request compilation has separate transport tests.
            stack.enter_context(patch('request_renderer.generation',return_value=rendered))
            stack.enter_context(patch.object(dispatch,'api_key',return_value='not-a-real-key'))
            stack.enter_context(patch.object(dispatch,'save',side_effect=lambda url,p,hosts:p.write_bytes(url.encode())))
            stack.enter_context(patch.object(studio,'iterate',side_effect=fail_second))
            with self.assertRaises(OSError): dispatch.dispatch_generation(options,self.root)
        self.assertEqual(transport.send.call_count,1)
        first=w.recover_recording(self.root,self.run); second=w.recover_recording(self.root,self.run)
        self.assertEqual(first,second); self.assertEqual(first['network_calls'],0)
        original=(self.root/'delivery.txt').read_bytes()
        (self.root/'delivery.txt').write_text('Changed input after the recorded request completed.\n', encoding='utf-8')
        with patch.object(dispatch,'api_key',side_effect=AssertionError('recording recovery must remain offline')):
            self.assertEqual(w.recover_recording(self.root,self.run),first)
        (self.root/'delivery.txt').write_bytes(original)
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'C01'))),2)
        paths=w.find(w.load_run(self.root,self.run)[3],'dispatch-results')['data']['files']
        w.capture(self.root,self.run,paths[0]['path'],'Actual fixture output')


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
