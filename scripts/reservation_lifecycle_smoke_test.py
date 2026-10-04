#!/usr/bin/env python3
"""Exercise execution-bound reservations and SQLite transitions, without network I/O."""
from __future__ import annotations
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import execution_contract as c
import production_workflow as w
import production_store as store
import reservation_lifecycle as life
import production_fixtures as fixture
import work_ledger


def setup(root):
    task=work_ledger.begin(root,'Synthetic reservation test',['deliver'])
    (root/'delivery.txt').write_text('Synthetic declared output.',encoding='utf-8')
    spec={'task_id':task['task_id'],'route':'development','features':[],'sources':[],
          'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Synthetic rendition.'},
          'criteria':[{'id':'output','strength':'hard','text':'Inspect actual bytes.'}],'world_views':[]}
    fixture.task(root,spec)
    (root/'task.json').write_bytes(c.encoded(spec))
    run=w.prepare(root,'task.json')['run']
    token=fixture.grant(root,run,{'operation':'submit','targets':['delivery'],'payload':{'count':1,'test':'synthetic'}})
    return run,token,fixture.ACTOR


def reserve_in_process(root,run,token,barrier,results):
    """Reserve from a separate interpreter; only the studio lock and SQLite order the two writers."""
    try:
        barrier.wait(timeout=120)
        results.put(life.reserve(Path(root),run,token)['reservation_id'])
    except ValueError as exc:
        diagnostic=getattr(exc,'diagnostic',None)
        results.put(diagnostic.code if diagnostic is not None else repr(exc))
    except BaseException as exc:
        results.put(repr(exc))


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.run,self.token,self.actor=setup(self.root)
        self.assertEqual(life.all_states(self.root),[])
        # This is the execution boundary, not receipt creation.
        self.state=life.reserve(self.root,self.run,self.token)
        self.id=self.state['reservation_id']
        (self.root/'cancel.txt').write_text('Synthetic explicit cancellation request.\n',encoding='utf-8')
        self.request=life.draft_release(self.root,self.run,self.id)
        self.request.update(actor=self.actor,reason='Cancel this unused synthetic reservation.',
            evidence={'path':'cancel.txt','sha256':c.sha256_file(self.root/'cancel.txt'),'locator':'whole'})
        self.save_request()
    def save_request(self):
        (self.root/'release.json').write_bytes(c.encoded(self.request))
    def states(self):
        _,p,_,rows=w.load_run(self.root,self.run)
        return life.derive(rows,p,self.run)
    def release(self):
        return life.release(self.root,self.run,'release.json')
    def start(self):
        return life.begin(self.root,self.run,self.token,effect='external-io')
    def claim(self):
        directory,p,_,rows=w.load_run(self.root,self.run)
        return w.append_record(directory,p,rows,'dispatch-claim',
            {'authorizations':[self.token],'reservation_id':self.id})['sha256']
    def test_reserved_amount_comes_from_exact_submission(self):
        self.assertEqual(self.states()[self.id]['status'],'reserved')
        self.assertEqual(self.states()[self.id]['amounts']['outputs'],1)
        self.assertNotEqual(self.id,self.token)
    def test_release_restores_exact_reservation(self):
        self.assertTrue(self.release()['released'])
        self.assertEqual(self.states()[self.id]['status'],'released')
        self.assertEqual(life.budget(self.root)['grants'][0]['outstanding_reserved']['uses'],0)
    def test_idempotent_release(self):
        self.assertFalse(self.release()['already_released'])
        self.assertTrue(self.release()['already_released'])
        self.assertEqual(sum(r['event']=='reservation-release' for r in store.event_rows(self.root,self.run)),1)
    def test_release_has_no_spending_event(self):
        self.release()
        self.assertEqual(sum(r['event']=='reservation-created' for r in store.event_rows(self.root,self.run)),1)
        self.assertFalse(any(r['event']=='external-step' for r in store.event_rows(self.root,self.run)))
    def test_other_actor_rejected(self):
        self.request['actor']='unassigned synthetic actor';self.save_request()
        with self.assertRaises(ValueError):self.release()
    def test_other_run_rejected(self):
        other=w.prepare(self.root,'task.json')['run']
        with self.assertRaisesRegex(ValueError,'RESERVATION_NOT_FOUND'):
            life.release(self.root,other,'release.json')
    def test_unknown_reservation_rejected(self):
        self.request['reservation_id']='unregistered-reservation';self.save_request()
        with self.assertRaisesRegex(ValueError,'RESERVATION_NOT_FOUND'):self.release()
    def test_changing_refund_amount_is_not_an_input(self):
        self.request['amounts']={'outputs':20};self.save_request()
        with self.assertRaises(ValueError):self.release()
    def test_evidence_bytes_must_match(self):
        (self.root/'cancel.txt').write_text('Different evidence',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.release()
    def test_source_change_does_not_prevent_cancellation(self):
        (self.root/'delivery.txt').write_text('Revised synthetic delivery',encoding='utf-8')
        self.assertTrue(self.release()['released'])
    def test_start_without_external_boundary_can_be_released(self):
        self.start();self.assertTrue(self.release()['released'])
    def test_start_after_release_rejected(self):
        self.release()
        with self.assertRaises(ValueError):self.start()
    def test_second_start_rejected(self):
        self.start()
        with self.assertRaises(ValueError):self.start()
    def test_local_claim_without_effect_can_be_cancelled(self):
        self.claim();self.assertTrue(self.release()['released'])
    def test_unanswered_upload_keeps_the_budget(self):
        claim=self.claim()
        life.begin_step(self.root,self.run,self.token,claim=claim,step='upload:0',operation='upload')
        self.assertFalse(life.releasable(self.states()[self.id]))
        with self.assertRaisesRegex(ValueError,'RESERVATION_NOT_RELEASABLE'):self.release()
    def test_send_step_prevents_cancel(self):
        claim=self.claim()
        life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        with self.assertRaisesRegex(ValueError,'RESERVATION_NOT_RELEASABLE'):self.release()
        self.assertEqual(life.budget(self.root)['grants'][0]['outstanding_reserved']['uses'],1)
    def test_same_external_step_not_reissued(self):
        claim=self.claim()
        life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        with self.assertRaises(ValueError):
            life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
    def test_different_steps_share_one_reservation(self):
        claim=self.claim()
        for step,operation in [('upload:0','upload'),('send','send')]:
            life.begin_step(self.root,self.run,self.token,claim=claim,step=step,operation=operation)
        self.assertEqual(len(self.states()[self.id]['steps']),2)
        self.assertEqual(len(self.states()),1)
    def test_important_record_failure_prevents_external_call(self):
        sent=[];original=store.append
        def fail(root,scope,digest,event,data,**options):
            if event=='reservation-start':raise OSError('synthetic durable record failure')
            return original(root,scope,digest,event,data,**options)
        with patch.object(store,'append',side_effect=fail):
            with self.assertRaises(OSError):
                self.start();sent.append(True)
        self.assertEqual(sent,[])
        self.assertEqual(self.states()[self.id]['status'],'reserved')
    def test_release_commit_failure_retains_amount(self):
        original=store.append
        def fail(root,scope,digest,event,data,**options):
            if event=='reservation-release':raise OSError('synthetic receipt commit failure')
            return original(root,scope,digest,event,data,**options)
        with patch.object(store,'append',side_effect=fail):
            with self.assertRaises(OSError):self.release()
        self.assertEqual(self.states()[self.id]['status'],'reserved')
    def test_lost_release_response_does_not_double_return(self):
        self.release();before=store.event_rows(self.root,self.run)
        self.assertTrue(self.release()['already_released'])
        self.assertEqual(before,store.event_rows(self.root,self.run))
    def test_released_authorization_cannot_restart(self):
        self.release()
        _,prepared,_,rows=w.load_run(self.root,self.run)
        request=w.find(rows,'authorization',self.token)['data']['request']
        with self.assertRaises(ValueError):
            w._permission(self.root,prepared,rows,self.token,request['operation'],request['targets'],request['payload'])
    def test_corrupt_chain_is_not_unused(self):
        with store.transaction(self.root) as connection:
            connection.execute("UPDATE events SET body=? WHERE scope=? AND event='reservation-created'",
                               (b'{}',self.run))
        with self.assertRaisesRegex(ValueError,'EVENT_CHAIN_CORRUPT'):self.release()
    def test_read_only_draft_does_not_spend_or_cancel(self):
        before=store.event_rows(self.root,self.run)
        draft=life.draft_release(self.root,self.run,self.id)
        self.assertEqual(draft['actor'],'')
        self.assertEqual(draft['reservation_id'],self.id)
        self.assertEqual(before,store.event_rows(self.root,self.run))
    def test_concurrent_send_and_release_have_one_winner(self):
        claim=self.claim();barrier=threading.Barrier(2);result=[]
        def send():
            life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        def run(action):
            barrier.wait()
            try:action();result.append('success')
            except ValueError:result.append('rejected')
        one=threading.Thread(target=run,args=(send,));two=threading.Thread(target=run,args=(self.release,))
        one.start();two.start();one.join();two.join()
        self.assertCountEqual(result,['success','rejected'])
        self.assertIn(self.states()[self.id]['status'],{'started','released'})
    def test_reserve_is_idempotent_at_the_execution_boundary(self):
        before=store.event_rows(self.root,self.run)
        self.assertEqual(life.reserve(self.root,self.run,self.token)['reservation_id'],self.id)
        self.assertEqual(before,store.event_rows(self.root,self.run))


class ProcessReservationTests(unittest.TestCase):
    def test_two_processes_cannot_spend_one_remaining_use(self):
        import multiprocessing
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            first,first_token,_=setup(root)
            task_id=w.load_run(root,first)[1]['task']['task_id']
            document=store.authority(root,task_id);document['grants'][0]['limits']['uses']=1
            (root/'one-use.json').write_bytes(c.encoded(document))
            store.import_authority(root,'one-use.json',expected=store.authority_record(root,task_id)['sha256'])
            second=w.prepare(root,'task.json')['run']
            second_token=fixture.grant(root,second,{'operation':'submit','targets':['delivery'],'payload':{'count':1,'test':'synthetic'}})
            context=multiprocessing.get_context('spawn')
            barrier=context.Barrier(2);results=context.Queue()
            workers=[context.Process(target=reserve_in_process,args=(str(root),run,token,barrier,results))
                     for run,token in ((first,first_token),(second,second_token))]
            for worker in workers:worker.start()
            outcomes=[results.get(timeout=300) for _ in workers]
            for worker in workers:worker.join(timeout=60)
            self.assertEqual(sorted(outcome=='BUDGET_LIMIT_EXCEEDED' for outcome in outcomes),[False,True],outcomes)
            states=life.all_states(root)
            self.assertEqual([state['reservation_id'] for state in states],[outcome for outcome in outcomes if outcome!='BUDGET_LIMIT_EXCEEDED'])


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
