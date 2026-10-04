"""Current grant and request accounting under synthetic execution boundaries."""
from __future__ import annotations
import concurrent.futures
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_execution as execution
import production_permissions as permissions
import production_workflow as workflow
import production_store as store
import production_variation as variation
import reservation_lifecycle as accounting
import transport_synthetic
import work_ledger
from production_diagnostics import ProductionError
from production_fixtures import ACTOR, scratch_home_dir
from test_production_execution import decisions


PAID = {'currency': 'USD', 'amount': '0.25', 'final': True}


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.case=fixtures.create(base/'studio',base/'runtime');self.root=self.case['root']
        self.run=workflow.prepare(self.root,'task.json')['run']
        self.task_id=workflow.load_run(self.root,self.run)[1]['task']['task_id']

    def amend(self, **limits):
        return self.amend_grant(limits={**store.authority(self.root,self.task_id)['grants'][0]['limits'],**limits})

    def amend_grant(self, **fields):
        document=copy.deepcopy(store.authority(self.root,self.task_id))
        document['grants'][0].update(fields)
        fixtures.write(self.root/'amendment.json',document)
        previous=store.authority_record(self.root,self.task_id)
        return store.import_authority(self.root,'amendment.json',expected=previous['sha256'])

    def without_target(self, target):
        targets=[item for item in store.authority(self.root,self.task_id)['grants'][0]['targets'] if item!=target]
        return self.amend_grant(targets=targets)

    def pause_reserved(self, run=None):
        run=run or self.run
        packet=decisions(self.root,run)
        with patch.object(execution,'_transmit',return_value={'paused_before_effect':True}):
            execution.execute(self.root,run,decisions_file=packet)
        return accounting.all_states(self.root,run=run)[0]

    def release_request(self, state):
        request=accounting.draft_release(self.root,state['run'],state['reservation_id'])
        fixtures.write(self.root/'release-evidence.txt','Synthetic explicit release decision. Not user approval.')
        request.update(actor=state['actor'],reason='Synthetic no-effect reservation release.',
            evidence={'path':'release-evidence.txt','sha256':c.sha256_file(self.root/'release-evidence.txt'),'locator':'whole'})
        path='release-'+state['reservation_id']+'.json'
        fixtures.write(self.root/path,request)
        return path

    def test_limit_amendment_preserves_consumed_and_reserved(self):
        execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        child=variation.derive(self.root,self.run,prepare=True)['run']
        self.pause_reserved(child)
        before={r['run_id']:workflow.load_run(self.root,r['run_id'])[1]['input_sha256'] for r in store.runs(self.root)}
        self.amend(uses=9,outputs=9)
        after={r['run_id']:workflow.assert_current(self.root,r['run_id'])[1]['input_sha256'] for r in store.runs(self.root)}
        self.assertEqual(before,after)
        group=accounting.budget(self.root)['grants'][0]
        self.assertEqual(group['consumed']['uses'],1)
        self.assertEqual(group['outstanding_reserved']['uses'],1)
        self.assertEqual(group['remaining']['uses'],7)

    def test_limit_shrink_after_reservation_stops_before_send(self):
        state=self.pause_reserved()
        self.amend(uses=0)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No send after budget shrink')):
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'BUDGET_LIMIT_EXCEEDED')
        state=accounting.all_states(self.root)[0]
        self.assertEqual(state['steps'],[])
        self.assertTrue(accounting.releasable(state))
        self.assertEqual(execution.status(self.root,self.run)['runs'][0]['submission'],'reserved')
        outcome=workflow.find(store.event_rows(self.root,self.run),'execution-outcome')
        self.assertEqual(outcome['data']['submission'],'reserved')

    def test_receipts_do_not_reserve_or_double_count_uses(self):
        data=execution.compiled(self.root,self.run)
        execution.authorize_decisions(self.root,self.run,decisions(self.root,self.run),data[1],data[6])
        self.assertEqual(accounting.all_states(self.root),[])
        rows=store.event_rows(self.root,self.run)
        self.assertGreaterEqual(sum(r['event']=='authorization' for r in rows),2)
        execution.execute(self.root,self.run)
        self.assertEqual(accounting.budget(self.root)['grants'][0]['consumed']['uses'],1)

    def test_release_draft_shape_is_used_without_unwrap_and_once(self):
        state=self.pause_reserved();path=self.release_request(state)
        result=accounting.release(self.root,self.run,path)
        self.assertTrue(result['released']);self.assertFalse(result['already_released'])
        again=accounting.release(self.root,self.run,path)
        self.assertTrue(again['already_released'])
        self.assertEqual(sum(r['event']=='reservation-release' for r in store.event_rows(self.root,self.run)),1)
        self.assertEqual(accounting.budget(self.root)['grants'][0]['outstanding_reserved']['uses'],0)

    def test_unknown_outcome_cannot_release(self):
        with patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic timeout')):
            execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        state=accounting.all_states(self.root)[0]
        with self.assertRaises(ProductionError) as caught:
            accounting.release(self.root,self.run,self.release_request(state))
        self.assertEqual(caught.exception.diagnostic.code,'RESERVATION_NOT_RELEASABLE')
        self.assertEqual(accounting.budget(self.root)['grants'][0]['outstanding_reserved']['uses'],1)

    def test_unknown_actual_cost_is_not_zero(self):
        with patch.object(transport_synthetic,'usage',return_value=None):
            execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        state=accounting.all_states(self.root)[0]
        self.assertIsNone(state['actual_cost'])
        self.assertEqual(state['status'],'partially_settled')
        group=accounting.budget(self.root)['grants'][0]
        self.assertEqual(group['unknown_cost_reservations'],[state['reservation_id']])
        self.assertEqual(group['consumed']['cost'],{})

    def test_two_reservations_cannot_spend_same_remaining_use(self):
        self.amend(uses=1,outputs=1)
        child=variation.derive(self.root,self.run,prepare=True)['run']
        for run in (self.run,child):
            data=execution.compiled(self.root,run)
            execution.authorize_decisions(self.root,run,decisions(self.root,run),data[1],data[6])
        def reserve(run):
            rows=store.event_rows(self.root,run)
            token=next(r['sha256'] for r in rows if r['event']=='authorization' and r['data']['request']['operation']=='submit')
            try:
                return accounting.reserve(self.root,run,token)['reservation_id']
            except ProductionError as exc:
                return exc.diagnostic.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(reserve,(self.run,child)))
        self.assertEqual(outcomes.count('BUDGET_LIMIT_EXCEEDED'),1)
        self.assertEqual(len(accounting.all_states(self.root)),1)

    def test_no_studio_transaction_held_over_transport(self):
        # The transport waits for a second thread to commit a real grant event.
        # Holding the studio lock over network I/O would deadlock that writer.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            original=transport_synthetic.send
            def send(*args,**kwargs):
                future=pool.submit(self.amend,uses=99)
                future.result(timeout=10)
                return original(*args,**kwargs)
            with patch.object(transport_synthetic,'send',side_effect=send):
                result=execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        self.assertTrue(result['execution_completed'])

    def test_studio_grant_and_run_aggregates_share_same_events(self):
        with patch.object(transport_synthetic,'usage',return_value=PAID):
            execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        child=variation.derive(self.root,self.run,prepare=True)['run'];self.pause_reserved(child)
        total=accounting.budget(self.root)['grants'][0]
        grant=accounting.budget(self.root,grant='fixture-grant')['grants'][0]
        first=accounting.budget(self.root,run=self.run)['grants'][0]
        second=accounting.budget(self.root,run=child)['grants'][0]
        self.assertEqual(total,grant)
        # A run view keeps the grant-wide remaining amount and shows the run's share beside it.
        for view in (first,second):
            for key in ('limits','consumed','outstanding_reserved','remaining','overrun'):
                self.assertEqual(view[key],total[key])
        for section in ('consumed','outstanding_reserved'):
            for unit in ('uses','outputs'):
                self.assertEqual(total[section][unit],first['run_share'][section][unit]+second['run_share'][section][unit])
            shares=[{'currency':currency,'amount':value} for view in (first,second)
                    for currency,value in view['run_share'][section]['cost'].items()]
            self.assertEqual(total[section]['cost'],accounting._add_money(shares))
        self.assertEqual(total['consumed']['cost'],{'USD':'0.25'})
        limits=total['limits'];remaining=total['remaining']
        for unit in ('uses','outputs'):
            self.assertEqual(remaining[unit],limits[unit]-total['consumed'][unit]-total['outstanding_reserved'][unit])
        self.assertEqual(Decimal(remaining['cost']['USD']),Decimal(limits['cost']['amount'])
                         -Decimal(total['consumed']['cost']['USD'])-Decimal(total['outstanding_reserved']['cost'].get('USD','0')))
        self.assertEqual(remaining['cost'],{'USD':'99.75'})
        self.assertEqual(first['run_share']['reservations']+second['run_share']['reservations'],
                         [item['reservation_id'] for item in total['reservations']])

    def test_limit_below_consumption_is_overrun_without_changing_actuals(self):
        with patch.object(transport_synthetic,'usage',return_value=PAID):
            execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        before=accounting.budget(self.root)['grants'][0]
        self.assertEqual(before['overrun'],{'uses':False,'outputs':False,'cost':{'USD':False}})
        self.amend(uses=0,outputs=0,cost={'currency':'USD','amount':'0.1'})
        after=accounting.budget(self.root)['grants'][0]
        self.assertEqual(after['consumed'],before['consumed'])
        self.assertEqual(after['overrun'],{'uses':True,'outputs':True,'cost':{'USD':True}})
        self.assertEqual(after['remaining'],{'uses':-1,'outputs':-1,'cost':{'USD':'-0.15'}})

    def test_draft_release_file_is_the_release_request(self):
        from state_protocol import validate_against_schema
        state=self.pause_reserved()
        home=scratch_home_dir(Path(self.temp.name)/'home')
        environment={**os.environ,'CPB_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1'}
        def cli(*arguments):
            return subprocess.run([sys.executable,str(Path(workflow.__file__).resolve()),*arguments,'--root',str(self.root),'--run',self.run],
                                  capture_output=True,text=True,encoding='utf-8',env=environment,timeout=300)
        schema=c.load(workflow.ROOT/'schemas/authoring/production-release.schema.json')
        drafted=cli('draft-release','--reservation',state['reservation_id'],'--out','release.json')
        self.assertEqual(drafted.returncode,0,drafted.stdout+drafted.stderr)
        request=c.load(self.root/'release.json')
        self.assertEqual(validate_against_schema(request,schema),[])
        fixtures.write(self.root/'release-evidence.txt','Synthetic explicit release decision. Not user approval.')
        request.update(actor=state['actor'],reason='Synthetic no-effect reservation release.',
                       evidence={'path':'release-evidence.txt','sha256':c.sha256_file(self.root/'release-evidence.txt'),'locator':'whole'})
        fixtures.write(self.root/'release.json',request)
        self.assertEqual(validate_against_schema(request,schema),[])
        released=cli('release-reservation','--request','release.json')
        self.assertEqual(released.returncode,0,released.stdout+released.stderr)
        report=json.loads(released.stdout)
        self.assertTrue(report['released']);self.assertFalse(report['already_released'])
        files=report['receipt']['data']['files']
        self.assertEqual([(item['path'],item['purpose'],item['locator']) for item in files],
                         [('release.json','release-request','whole'),('release-evidence.txt','release-evidence','whole')])
        self.assertTrue(all(item['captured_at'] for item in files))
        self.assertEqual(accounting.budget(self.root)['grants'][0]['outstanding_reserved']['uses'],0)

    def test_abandon_keeps_an_unknown_outcome_reservation(self):
        with patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic timeout')):
            execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        reason='Synthetic abandonment after an unanswered send.'
        with self.assertRaises(ValueError):
            work_ledger.abandon(self.root,reason)
        self.assertIsNotNone(work_ledger.read_current(self.root))
        work_ledger.abandon(self.root,reason,actor=ACTOR)
        rows=store.event_rows(self.root,self.run)
        self.assertEqual([row['data'] for row in rows if row['event']=='abandoned'],[{'actor':ACTOR,'reason':reason}])
        self.assertFalse(any(row['event']=='reservation-release' for row in rows))
        state=accounting.all_states(self.root)[0]
        self.assertFalse(accounting.releasable(state))
        self.assertEqual(accounting.budget(self.root)['grants'][0]['outstanding_reserved']['uses'],1)
        with self.assertRaises(ProductionError) as caught:
            accounting.release(self.root,self.run,self.release_request(state))
        self.assertEqual(caught.exception.diagnostic.code,'RESERVATION_NOT_RELEASABLE')
        self.assertEqual(execution.status(self.root,self.run)['runs'][0]['task_disposition'],'abandoned')
        self.assertIsNone(work_ledger.read_current(self.root))
        self.assertEqual(work_ledger.read_ledger(self.root)[-1]['production_runs'],[self.run])

    def test_abandoned_run_starts_no_new_operation(self):
        path=decisions(self.root,self.run)
        work_ledger.abandon(self.root,'Synthetic abandonment before execution.',actor=ACTOR)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No send after abandonment')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run,decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code,'TASK_ABANDONED')
        self.assertEqual(accounting.all_states(self.root),[])

    def test_missing_decision_target_is_named_before_reservation(self):
        self.without_target('decision:expression')
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No send without scope')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        diagnostic=caught.exception.diagnostic
        self.assertEqual(diagnostic.code,'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(diagnostic.details['operation'],'direction')
        self.assertEqual(diagnostic.details['grant'],'fixture-grant')
        self.assertEqual(diagnostic.details['missing'],['decision:expression'])
        self.assertNotIn('decision:expression',diagnostic.details['granted'])
        self.assertEqual(diagnostic.pointer,'$.targets')
        self.assertEqual(diagnostic.required_action,permissions.SCOPE_ACTION)
        self.assertEqual(store.event_rows(self.root,self.run),[])
        self.assertEqual(accounting.all_states(self.root),[])

    def test_handoff_shortfall_is_planned_and_stops_before_reservation(self):
        self.without_target('decision:expression')
        child=variation.derive(self.root,self.run,prepare=True)['run']
        directory,prepared,_,_=workflow.load_run(self.root,child)
        plan=c.load(directory/'execution-plan.json')
        scope=[item for item in plan['readiness']['diagnostics'] if item['code']=='GRANT_SCOPE_EXCEEDED']
        self.assertEqual([item['pointer'] for item in scope],['$.operations.direction'])
        self.assertEqual(scope[0]['missing'],['decision:expression'])
        direction=next(item for item in plan['operations'] if item['operation']=='direction')
        self.assertEqual(permissions.target_coverage(prepared['authority'],'direction',direction['targets']),
                         [{'grant':'fixture-grant','granted':sorted(prepared['authority']['grants'][0]['targets']),
                           'missing':['decision:expression']}])
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No send without scope')):
            with self.assertRaises(ProductionError):
                execution.execute(self.root,child,decisions_file=decisions(self.root,child))
        self.assertEqual(accounting.all_states(self.root),[])

    def test_scope_reduced_after_receipts_stops_before_reservation(self):
        data=execution.compiled(self.root,self.run)
        execution.authorize_decisions(self.root,self.run,decisions(self.root,self.run),data[1],data[6])
        receipts=[row['sha256'] for row in store.event_rows(self.root,self.run) if row['event']=='authorization']
        self.assertEqual(len(receipts),2)
        self.without_target('decision:expression')
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No send outside the current scope')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(caught.exception.diagnostic.details['missing'],['decision:expression'])
        rows=store.event_rows(self.root,self.run)
        self.assertEqual([row['sha256'] for row in rows],receipts)
        self.assertEqual(accounting.all_states(self.root),[])

    def test_external_boundary_rechecks_live_pack_drift_past_the_operation_cache(self):
        import operation_context as operations
        import runtime_snapshot
        packet=decisions(self.root,self.run)
        descriptor=workflow.load_run(self.root,self.run)[1]['runtime_snapshot']
        models=self.case['pack']/'records/models.json'
        original_claim=workflow.claim_dispatch
        def drift_after_claim(*args,**kwargs):
            claim=original_claim(*args,**kwargs)
            document=c.load(models);document['records'][0]['label']='Synthetic live edit after the claim'
            fixtures.write(models,document)
            return claim
        operation=operations.Operation('synthetic-live-drift-boundary')
        token=operations._CURRENT.set(operation)
        try:
            # A passing comparison is cached for this operation before the live edit.
            self.assertEqual([row for row in runtime_snapshot.require_current(self.root,descriptor,run=self.run)
                              if row['severity']=='error'],[])
            with patch.object(workflow,'claim_dispatch',side_effect=drift_after_claim), \
                 patch.object(transport_synthetic,'send') as send:
                with self.assertRaises(ProductionError) as caught:
                    execution.execute(self.root,self.run,decisions_file=packet)
            send.assert_not_called()
        finally:
            operation.finish(0)
            operations._CURRENT.reset(token)
        self.assertEqual(caught.exception.diagnostic.code,'PACK_CONTENT_MISMATCH')
        self.assertFalse(any(row['event']=='external-step' for row in store.event_rows(self.root,self.run)))

    def test_revocation_after_send_start_cannot_undo_the_send(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            original=transport_synthetic.send
            def send(*args,**kwargs):
                pool.submit(self.amend_grant,revoked_at='2000-01-01T00:00:00Z').result(timeout=30)
                return original(*args,**kwargs)
            with patch.object(transport_synthetic,'send',side_effect=send):
                result=execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        self.assertTrue(result['execution_completed'])
        self.assertEqual(result['runs'][0]['capture'],'complete')
        self.assertIsNotNone(store.authority(self.root,self.task_id)['grants'][0]['revoked_at'])
        self.assertEqual(accounting.budget(self.root)['grants'][0]['consumed']['uses'],1)
        child=variation.derive(self.root,self.run,prepare=True)['run']
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No send after revocation')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,child,decisions_file=decisions(self.root,child))
        self.assertEqual(caught.exception.diagnostic.code,'GRANT_REVOKED')
        self.assertEqual(len(accounting.all_states(self.root)),1)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
