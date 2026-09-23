#!/usr/bin/env python3
"""Synthetic receipt, cancellation, durability and race tests without network I/O."""
import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import execution_contract as c
import production_workflow as w
import reservation_lifecycle as life
import work_ledger

import production_fixtures as fixture

def setup(root):
    task=work_ledger.begin(root,'Synthetic reservation test',['deliver'])
    (root/'delivery.txt').write_text('Synthetic declared output.')
    spec={'task_id':task['task_id'],'route':'development','features':[],'sources':[],
        'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Synthetic rendition.'},
        'criteria':[{'id':'output','strength':'hard','text':'Inspect actual bytes.'}],'world_views':[]}
    fixture.task(root,spec)
    (root/'task.json').write_bytes(c.encoded(spec));run=w.prepare(root,'task.json')['run']
    token=fixture.grant(root,run,{'operation':'submit','targets':['delivery'],'payload':{'count':1,'test':'synthetic'}})
    return run,token,fixture.ACTOR

def claim_data(token):return {'authorizations':[token]}

def repeat(root,run,token):
    _,p,_,rows=w.load_run(root,run);request=w.find(rows,'authorization',token)['data']['request']
    w._permission(root,p,rows,token,request['operation'],request['targets'],request['payload'])


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.run,self.token,self.actor=setup(self.root)
        (self.root/'cancel.txt').write_text('Synthetic explicit cancellation request.\n')
        self.request={'reservation':life.selector(self.run,self.token),'actor':self.actor,
            'evidence':{'path':'cancel.txt','sha256':c.digest(c.read(self.root/'cancel.txt')),'locator':'whole'},
            'reason':'Cancel this unused synthetic reservation.'}
        self.save_request()
    def save_request(self):
        (self.root/'release.json').write_bytes(c.encoded(self.request))
    def states(self):
        _,p,_,rows=w.load_run(self.root,self.run)
        return life.derive(rows,p,self.run)
    def release(self):return life.release(self.root,self.run,'release.json')
    def start(self):return life.begin(self.root,self.run,self.token,effect='external-io')
    def claim(self):
        directory,p,_,rows=w.load_run(self.root,self.run)
        return w.append_record(directory,p,rows,'dispatch-claim',claim_data(self.token))['sha256']
    def test_reserved_amount_comes_from_original(self):
        self.assertEqual(self.states()[self.token]['status'],'reserved')
        self.assertEqual(self.states()[self.token]['amounts']['outputs'],1)
    def test_release_restores_exact_reservation(self):
        result=self.release();self.assertTrue(result['released']);self.assertEqual(result['reservations'],[])
        self.assertEqual(self.states()[self.token]['status'],'released')
    def test_idempotent_release(self):
        first=self.release();second=self.release();self.assertEqual(first,second)
    def test_release_has_no_spending_event(self):
        self.release();_,_,_,rows=w.load_run(self.root,self.run)
        self.assertEqual(len([r for r in rows if r['event']==life.RESERVATION_EVENT]),1)
    def test_other_actor_rejected(self):
        self.request['actor']='unassigned synthetic actor';self.save_request()
        with self.assertRaises(ValueError):self.release()
    def test_other_run_rejected(self):
        self.request['reservation']['run']='unrelated';self.save_request()
        with self.assertRaises(ValueError):self.release()
    def test_unknown_token_rejected(self):
        self.request['reservation'][life.TOKEN_FIELD]='f'*64;self.save_request()
        with self.assertRaises(ValueError):self.release()
    def test_changing_refund_amount_is_not_an_input(self):
        self.request['amounts']={'outputs':20};self.save_request()
        with self.assertRaises(ValueError):self.release()
    def test_evidence_bytes_must_match(self):
        (self.root/'cancel.txt').write_text('Different evidence')
        with self.assertRaises(ValueError):self.release()
    def test_source_change_does_not_prevent_cancellation(self):
        (self.root/'delivery.txt').write_text('Revised synthetic delivery')
        self.assertTrue(self.release()['released'])
    def test_other_effect_cannot_be_released(self):
        life.begin(self.root,self.run,self.token,effect='local-action')
        with self.assertRaises(ValueError):self.release()
    def test_start_without_a_step_can_be_released(self):
        self.start();self.assertTrue(self.release()['released'])
    def test_start_after_release_rejected(self):
        self.release()
        with self.assertRaises(ValueError):self.start()
    def test_second_start_rejected(self):
        self.start()
        with self.assertRaises(ValueError):self.start()
    def test_local_claim_can_be_cancelled(self):
        self.claim();self.assertTrue(self.release()['released'])
    def test_failed_upload_returns_the_budget(self):
        claim=self.claim();life.begin_step(self.root,self.run,self.token,claim=claim,step='upload:0',operation='upload')
        self.assertTrue(life.draft_release(self.root,self.run,self.token)['release_eligible'])
        self.assertEqual(self.release()['reservations'],[])
        with self.assertRaises(ValueError):life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
    def test_send_step_prevents_cancel(self):
        claim=self.claim();life.begin_step(self.root,self.run,self.token,claim=claim,step='upload:0',operation='upload')
        life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        self.assertFalse(life.draft_release(self.root,self.run,self.token)['release_eligible'])
        with self.assertRaises(ValueError):self.release()
        self.assertEqual(len(w.reservations(self.root,w.load_run(self.root,self.run)[1]['task']['task_id'])),1)
    def test_same_external_step_not_reissued(self):
        claim=self.claim();life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        with self.assertRaises(ValueError):life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
    def test_different_steps_share_one_boundary(self):
        claim=self.claim();life.begin_step(self.root,self.run,self.token,claim=claim,step='upload:0',operation='upload')
        life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        self.assertEqual(len(self.states()[self.token]['steps']),2)
    def test_fsync_failure_prevents_external_call(self):
        sent=[]
        with patch.object(c,'atomic',side_effect=OSError('synthetic persistence failure')):
            with self.assertRaises(OSError):
                self.start();sent.append(True)
        self.assertEqual(sent,[]);self.assertEqual(self.states()[self.token]['status'],'reserved')
    def test_release_commit_failure_retains_amount(self):
        # Fail only the receipt commit, after immutable evidence can be stored.
        actual=c.atomic
        def fail(path,data,*args,**kw):
            if path.parent.name=='records':raise OSError('synthetic receipt commit failure')
            return actual(path,data,*args,**kw)
        with patch.object(c,'atomic',side_effect=fail):
            with self.assertRaises(OSError):self.release()
        self.assertEqual(self.states()[self.token]['status'],'reserved')
    def test_lost_release_response_does_not_double_return(self):
        receipt=self.release()['receipt'];self.assertEqual(self.release()['receipt'],receipt)
    def test_released_permission_rejected_by_authority_path(self):
        self.release()
        with self.assertRaises(ValueError):repeat(self.root,self.run,self.token)
    def test_corrupt_chain_is_not_unused(self):
        _,_,_,rows=w.load_run(self.root,self.run);row=rows[-1]
        path=w.run_dir(self.root,self.run)/'records'/f"{row['sequence']:06d}-{row['sha256']}.json"
        path.write_bytes(b'{}')
        with self.assertRaises((ValueError,KeyError)):self.release()
    def test_read_only_draft_does_not_spend_or_cancel(self):
        before=w.load_run(self.root,self.run)[3]
        data=life.draft_release(self.root,self.run,self.token)
        self.assertEqual(data['request']['actor'],'');self.assertEqual(w.load_run(self.root,self.run)[3],before)
    def test_concurrent_send_and_release_have_one_winner(self):
        claim=self.claim();barrier=threading.Barrier(2);result=[]
        def send():life.begin_step(self.root,self.run,self.token,claim=claim,step='send',operation='send')
        def run(action):
            barrier.wait()
            try:action();result.append('success')
            except ValueError:result.append('rejected')
        one=threading.Thread(target=run,args=(send,));two=threading.Thread(target=run,args=(self.release,))
        one.start();two.start();one.join();two.join()
        self.assertCountEqual(result,['success','rejected'])
        self.assertIn(self.states()[self.token]['status'],{'started','released'})

if __name__=='__main__':unittest.main()
