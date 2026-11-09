"""Explicit canonical adoption is separate from synthetic generation and selection."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adoption_workflow
import execution_contract as c
import production_case_fixtures as f
import production_fixtures as fixture
import production_execution as execution
import production_workflow as workflow
import production_store as store
import production_acceptance as acceptance
import execution_lifecycle as accounting
import studio
import studio_reference
import transport_synthetic
from production_diagnostics import ProductionError
from test_production_execution import decisions
from visual_continuity import file_ref


class AdoptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        b=Path(cls.temp.name)
        cls.enterClassContext(fixture.scratch_home(b/'home'))
        from catalog_retrieval import runtime
        cls.addClassCleanup(runtime.configure_pack_runtime,None)
        case=f.create(b/'studio',b/'runtime');cls.root=case['root'];cls.task=case['task'];cls.settings=case['settings']
        cls.task['recording'].update(slot='base.front',sheet_panel=True,subject_map={'robot':'robot'})
        cls.task['generation']['continuity']['robot']='undecided'
        f.write(cls.root/'task.json',cls.task)
        cls.prepared_run=workflow.prepare(cls.root,'task.json')['run']
        output=execution.execute(cls.root,cls.prepared_run,decisions_file=decisions(cls.root,cls.prepared_run))
        cls.candidate=output['runs'][0]['candidates'][0]
        cls.row=studio.read_iterations(studio.character_home(cls.root,'robot'))[0]
        review=workflow.draft_review(cls.root,cls.prepared_run,cls.candidate)
        review.update(reviewer='Synthetic test reviewer',observations=[{'evidence':'candidate','locator':{'kind':'whole'},
            'observation':'A real local synthetic PNG was captured.','interpretation':'Protocol fixture only.',
            'limitations':['No generative quality or user approval is asserted.']}],conclusion='Synthetic test decision.')
        for check in review['checks']:check.update(verdict='pass',observation_indices=[0],reason='Explicit synthetic fixture assessment.')
        f.write(cls.root/'review.json',review);workflow.review(cls.root,cls.prepared_run,'review.json')
        f.write(cls.root/'adoption-basis.txt','Explicit synthetic author decision to adopt this fixture identity. Not user consent.')
        cls.approval={'scope':'sheet','influence':'identity','character':'robot','iteration_id':cls.row['iteration_id'],
            'slot':cls.row['slot'],'image_sha256':cls.row['result']['sha256'],'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z',
            'continuity_decision':{'character_id':'robot','continuity':'recurring',
                'basis':file_ref(cls.root,'adoption-basis.txt',locator='whole'),'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z'}}
        f.write(cls.root/'approval.json',cls.approval)

        cls.runtime_state = cls.settings.state_file.read_bytes()

    def setUp(self):
        # Build and execute the synthetic protocol case once. Each test receives
        # its own Studio/SQLite/files; immutable runtime packs stay at their
        # sealed paths. Catalog promotion may change only this class's temporary
        # state file, restored before the next sequential unittest case.
        template = type(self)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.enterContext(fixture.scratch_home(base / 'home'))
        from catalog_retrieval import runtime
        self.addCleanup(runtime.configure_pack_runtime, None)
        c.atomic(template.settings.state_file, template.runtime_state, replace=True)
        runtime.configure_pack_runtime(template.settings)
        self.root = f.copy_studio(template.root, base / 'studio')
        self.run = template.prepared_run
        self.task = copy.deepcopy(template.task)
        self.row = copy.deepcopy(template.row)
        self.approval = copy.deepcopy(template.approval)

    def select(self,**changes):
        choice=workflow.draft_selection(self.root,self.run,self.candidate)
        choice.update({'reason':'Synthetic delivery-only selection.',**changes})
        fixture.selection(self.root,self.run,choice);f.write(self.root/'selection.json',choice)
        return workflow.select(self.root,self.run,'selection.json')

    def select_adoption(self):
        return self.select(reason='Explicit synthetic adoption selection.',scope='studio-adoption',
                           adoption={'character':'robot','iteration_id':self.row['iteration_id'],'scope':'sheet'})

    def authorize_adoption(self):
        intent=workflow.adoption_intent(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],self.approval)
        return fixture.grant(self.root,self.run,intent)

    def test_approval_draft_derives_the_exact_existing_subject_without_approval(self):
        self.select();before=store.event_rows(self.root,self.run)
        draft=adoption_workflow.draft_approval(self.root,'robot',self.row['iteration_id'],scope='sheet',influence='identity')
        self.assertEqual({key:draft[key] for key in ('character','iteration_id','slot','image_sha256')},
                         {key:self.approval[key] for key in ('character','iteration_id','slot','image_sha256')})
        self.assertIsNone(draft['by']);self.assertIsNone(draft['at'])
        with self.assertRaises(ValueError):adoption_workflow.validate_approval(draft,'robot',self.row)
        self.assertEqual(store.event_rows(self.root,self.run),before)

    def test_managed_batch_keeps_review_selection_and_adoption_separate(self):
        from build_batch_plan import project_managed_batch
        reviewed=project_managed_batch(self.root,[self.run])
        self.assertEqual(reviewed['summary']['evaluation'],{'conforming':1})
        self.assertEqual(reviewed['summary']['current_selections'],0)
        self.select()
        selected=project_managed_batch(self.root,[self.run])
        self.assertEqual(selected['summary']['current_selections'],1)
        self.assertEqual(selected['jobs'][0]['adoptions'],[])
        self.adopt(self.authorize_adoption())
        adopted=project_managed_batch(self.root,[self.run])
        self.assertEqual(len(adopted['jobs'][0]['adoptions']),1)
        self.assertEqual(adopted['summary']['captured_candidates'],1)

    def test_catalog_draft_derives_the_selected_registration_record_hash(self):
        from revision_contract import digest
        self.select()
        record={'id':'adopted-test-character','label':'Adopted fixture','curation_status':'curated',
            'category':'species','prompt':'a fictional test character','domains':['shared'],'tags':['fixture','character'],
            'search_terms':[{'phrase':'adopted test character','facet':'species','weight':1.0,'source':'author'}],
            'scaffold':{'family':'direct-geometry-required','confidence':'fallback'}}
        draft=adoption_workflow.draft_approval(self.root,'robot',self.row['iteration_id'],scope='catalog',
                                             influence='identity',registration_record=record)
        self.assertEqual(draft['registration_record_sha256'],digest(record))
        self.assertIsNone(draft['by']);self.assertIsNone(draft['at'])

    def adopt(self,token):
        return workflow.adopt(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],'approval.json',token)

    def close_selected(self,kind):
        self.select()
        studio.accept(self.root,'robot',self.row['iteration_id'])
        if kind=='completed':
            workflow.complete(self.root,self.run)
        else:
            workflow.abandon_task(self.root,self.task['task_id'],actor=fixture.ACTOR,
                reason='Synthetic production work stops; no canonical adoption was requested yet.')
        return store.event_rows(self.root,self.run)

    def import_authority(self,authority):
        f.write(self.root/'updated-authority.json',authority)
        store.import_authority(self.root,'updated-authority.json',
            expected=store.authority_record(self.root,self.task['task_id'])['sha256'])

    def assert_later_adoption(self,kind):
        original=self.close_selected(kind)
        before=c.encoded(original)
        iterations=studio.read_iterations(studio.character_home(self.root,'robot'),project=False)
        reference=adoption_workflow.reference_index(self.root,'robot')['bindings'][0]
        self.assertEqual(reference['next_action'],'adopt-production-candidate')
        self.assertTrue(reference['adoption']['source_ready'])
        with (patch.object(transport_synthetic,'send',side_effect=AssertionError('Adoption must not generate')),
              patch.object(studio,'iterate',side_effect=AssertionError('Adoption must keep the existing iteration'))):
            token=self.authorize_adoption()
            result=self.adopt(token)
            self.assertEqual(self.adopt(token),result)
        rows=store.event_rows(self.root,self.run)
        self.assertEqual(c.encoded(rows[:len(original)]),before)
        self.assertEqual([row['event'] for row in rows[len(original):]],
                         ['authorization','adoption-claim','operation-start','adoption-result'])
        self.assertEqual(sum(row['event']=='selection' for row in rows),1)
        self.assertEqual(sum(row['event']=='completion' for row in rows),int(kind=='completed'))
        self.assertEqual(sum(row['event']=='candidate' for row in rows),1)
        self.assertEqual(len(store.runs(self.root)),1)
        self.assertEqual(studio.read_iterations(studio.character_home(self.root,'robot'),project=False),iterations)
        self.assertEqual(accounting.summary(self.root)['submissions'],1)
        index=adoption_workflow.reference_index(self.root,'robot')
        self.assertTrue(index['ok'],index['errors'])
        self.assertIsNone(index['bindings'][0]['next_action'])
        source=studio_reference.current_source(self.root,'robot','base.front')
        self.assertEqual(source['sha256'],self.row['result']['sha256'])
        studio_reference.validate_source(source)
        status=execution.status(self.root,self.run)['runs'][0]
        self.assertEqual(status['task_disposition'],kind)
        self.assertIsNone(status['next_action'])
        if kind=='completed':
            done=workflow.find(original,'completion')
            self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id']),done)
            self.assertEqual(workflow.complete(self.root,self.run),done)
        selection=workflow.find(rows,'selection')['data']['selection']
        with self.assertRaises(ValueError):
            accounting.begin(self.root,self.run,selection['authorization'],effect='local-action')
        self.assertEqual(store.event_rows(self.root,self.run),rows)

    def test_completed_selection_can_be_adopted_without_reopening_production(self):
        self.assert_later_adoption('completed')

    def test_abandoned_selection_can_be_adopted_without_reopening_production(self):
        self.assert_later_adoption('abandoned')

    def test_completed_slot_acceptance_can_be_adopted_later(self):
        decision=acceptance.draft(self.root,self.run,self.candidate,'fixture-grant')
        decision['reason']='Synthetic author accepts this existing image for delivery.'
        f.write(self.root/'slot-decision.json',decision)
        acceptance.accept(self.root,self.run,decision_file='slot-decision.json')
        before=store.event_rows(self.root,self.run)
        self.adopt(self.authorize_adoption())
        self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id']),workflow.find(before,'completion'))
        rows=store.event_rows(self.root,self.run)
        self.assertEqual(rows[:len(before)],before)
        for event in ('candidate','selection','slot-acceptance','completion'):
            self.assertEqual(sum(row['event']==event for row in rows),1,event)

    def assert_revocation_blocks_later_adoption(self,kind):
        self.select()
        token=self.authorize_adoption()
        studio.accept(self.root,'robot',self.row['iteration_id'])
        if kind=='completed':workflow.complete(self.root,self.run)
        else:workflow.abandon_task(self.root,self.task['task_id'],actor=fixture.ACTOR,reason='Synthetic work closure.')
        authority=store.authority(self.root,self.task['task_id'])
        authority['grants'][0]['revoked_at']='2000-01-01T00:00:00Z'
        self.import_authority(authority)
        before=store.event_rows(self.root,self.run)
        for operation in (lambda:self.adopt(token),self.authorize_adoption):
            with self.assertRaises(ProductionError) as caught:operation()
            self.assertEqual(caught.exception.diagnostic.code,'GRANT_REVOKED')
        self.assertEqual(store.event_rows(self.root,self.run),before)
        self.assertFalse((studio.character_home(self.root,'robot')/'adoptions').exists())

    def test_completed_adoption_checks_current_grant_after_authorization(self):
        self.assert_revocation_blocks_later_adoption('completed')

    def test_abandoned_adoption_checks_current_grant_after_authorization(self):
        self.assert_revocation_blocks_later_adoption('abandoned')

    def test_revocation_between_claim_and_owner_start_keeps_only_the_claim(self):
        self.select()
        token = self.authorize_adoption()
        owner = adoption_workflow.adopt
        def revoke_before_owner(*args, **kwargs):
            authority = store.authority(self.root, self.task['task_id'])
            authority['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
            self.import_authority(authority)
            return owner(*args, **kwargs)
        with patch.object(adoption_workflow, 'adopt', side_effect=revoke_before_owner):
            with self.assertRaises(ProductionError) as caught:
                self.adopt(token)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_REVOKED')
        rows = store.event_rows(self.root, self.run)
        claim = workflow.find(rows, 'adoption-claim')
        self.assertFalse(any(row['event'] == 'operation-start' and row['data'].get('claim') == claim['sha256']
                             for row in rows))
        self.assertFalse((studio.character_home(self.root, 'robot') / 'adoptions').exists())

    def test_closed_adoption_recovers_the_same_claim_after_a_sheet_save_failure(self):
        before=self.close_selected('completed')
        token=self.authorize_adoption()
        with patch.object(adoption_workflow,'_bind_sheet',side_effect=OSError('Synthetic adoption interruption')):
            with self.assertRaises(OSError):self.adopt(token)
        claimed=store.event_rows(self.root,self.run)
        claim=workflow.find(claimed,'adoption-claim')
        self.assertEqual(self.adopt(token)['data']['claim'],claim['sha256'])
        rows=store.event_rows(self.root,self.run)
        self.assertEqual(rows[:len(before)],before)
        for event in ('adoption-claim','operation-start','adoption-result'):
            self.assertEqual(sum(row['event']==event for row in rows[len(before):]),1,event)
        self.assertEqual(accounting.summary(self.root)['submissions'],1)

    def test_abandoned_adoption_recovers_a_saved_effect_before_its_result_commit(self):
        before=self.close_selected('abandoned')
        token=self.authorize_adoption()
        append=workflow.append_record
        def interrupted(*args,**kwargs):
            if args[3]=='adoption-result':raise OSError('Synthetic interruption before adoption result')
            return append(*args,**kwargs)
        with patch.object(workflow,'append_record',side_effect=interrupted):
            with self.assertRaises(OSError):self.adopt(token)
        with self.assertRaises(ValueError):studio_reference.current_source(self.root,'robot','base.front')
        claim=workflow.find(store.event_rows(self.root,self.run),'adoption-claim')
        self.assertEqual(self.adopt(token)['data']['claim'],claim['sha256'])
        rows=store.event_rows(self.root,self.run)
        self.assertEqual(rows[:len(before)],before)
        for event in ('adoption-claim','operation-start','adoption-result'):
            self.assertEqual(sum(row['event']==event for row in rows[len(before):]),1,event)
        studio_reference.current_source(self.root,'robot','base.front')

    def assert_rejected_transition(self,event,data):
        directory,prepared,_,before=workflow.load_run(self.root,self.run)
        with self.assertRaises(ValueError):workflow.append_record(directory,prepared,before,event,data)
        self.assertEqual(store.event_rows(self.root,self.run),before)
        with self.assertRaises(ProductionError) as caught:
            with store.transaction(self.root):
                store.append(self.root,self.run,prepared['input_sha256'],event,data)
                workflow.load_run(self.root,self.run,force=True)
        self.assertEqual(caught.exception.diagnostic.code,'EVENT_CHAIN_CORRUPT')
        self.assertEqual(store.event_rows(self.root,self.run),before)

    def test_append_and_replay_refuse_closed_production_and_unlinked_adoption(self):
        self.close_selected('completed')
        token=self.authorize_adoption()
        rows=store.event_rows(self.root,self.run)
        selection=workflow.find(rows,'selection')['data']['selection']
        unrelated=copy.deepcopy(workflow.find(rows,'authorization',selection['authorization'])['data'])
        unrelated['request']['reason']='A forged new production operation must remain closed.'
        review=copy.deepcopy(workflow.find(rows,'review')['data'])
        review['review']['conclusion']='A new review must not change the completed decision.'
        intent=workflow.adoption_intent(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],self.approval)
        directory=workflow.run_dir(self.root,self.run)
        approval=workflow.file_record(self.root,directory,'approval.json')
        cases=[('authorization',unrelated),('review',review),
            ('adoption-claim',{'intent':intent,'files':[approval],'authorizations':[selection['authorization']]}),
            ('operation-start',{'authorization_sha256':token,'effect':'local-action','claim':'f'*64}),
            ('adoption-result',{'claim':'f'*64,'result':{}})]
        for event,data in cases:
            with self.subTest(event=event):self.assert_rejected_transition(event,data)
        loaded=workflow.load_run(self.root,self.run)
        claim=workflow.append_record(loaded[0],loaded[1],loaded[3],'adoption-claim',
            {'intent':intent,'files':[approval],'authorizations':[token]})
        self.assert_rejected_transition('adoption-result',{'claim':claim['sha256'],'result':{}})
        self.assertEqual(self.adopt(token)['data']['claim'],claim['sha256'])

    def test_closed_adoption_does_not_authorize_an_unselected_candidate(self):
        self.close_selected('abandoned')
        intent=workflow.adoption_intent(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],self.approval)
        intent['payload']['candidate']='f'*64
        before=store.event_rows(self.root,self.run)
        with self.assertRaises(ProductionError) as caught:fixture.grant(self.root,self.run,intent)
        self.assertEqual(caught.exception.diagnostic.code,'SELECTION_REQUIRED')
        self.assertEqual(store.event_rows(self.root,self.run),before)

    def test_historical_adoption_completion_survives_later_slot_supersession(self):
        self.select();self.adopt(self.authorize_adoption());self.select_adoption()
        done=workflow.complete(self.root,self.run)
        before=store.event_rows(self.root,self.run)
        imported=studio.iterate(self.root,'robot','base.front',self.root/self.row['result']['path'],
            package=None,request=None,response=None,note='Another explicit synthetic slot choice with separate ownership.')
        studio.accept(self.root,'robot',imported['iteration_id'])
        self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id']),done)
        self.assertEqual(workflow.complete(self.root,self.run),done)
        self.assertEqual(store.event_rows(self.root,self.run),before)
        self.assertTrue(execution.status(self.root,self.run)['runs'][0]['selection_ready'])
        with self.assertRaises(ValueError):studio_reference.current_source(self.root,'robot','base.front')

    def test_historical_completion_requires_its_saved_adoption_receipt(self):
        self.select();self.adopt(self.authorize_adoption());selected=self.select_adoption()
        workflow.complete(self.root,self.run)
        path='characters/robot/adoptions/'+self.row['iteration_id']+'.json'
        snapshot=next(item for item in selected['data']['files'] if item['path']==path)
        self.assertTrue((self.root/path).is_file())
        (workflow.run_dir(self.root,self.run)/'objects'/snapshot['sha256']).unlink()
        with self.assertRaises(ProductionError) as caught:
            workflow.verify_completion(self.root,self.run,self.task['task_id'])
        self.assertEqual(caught.exception.diagnostic.code,'EVIDENCE_SNAPSHOT_MISSING')

    def test_sheet_completion_survives_separately_authorized_catalog_promotion(self):
        from revision_contract import digest
        self.select();self.adopt(self.authorize_adoption());self.select_adoption()
        done=workflow.complete(self.root,self.run)
        original=store.event_rows(self.root,self.run)
        source=studio_reference.current_source(self.root,'robot','base.front')
        record={'id':'adopted-test-character','label':'Adopted fixture','curation_status':'curated',
            'category':'species','prompt':'a fictional test character','domains':['shared'],'tags':['fixture','character'],
            'search_terms':[{'phrase':'adopted test character','facet':'species','weight':1.0,'source':'author'}],
            'scaffold':{'family':'direct-geometry-required','confidence':'fallback'}}
        approval={**self.approval,'scope':'catalog','registration_record_sha256':digest(record)}
        pack=Path(self.temp.name)/'registered-pack'
        f.write(self.root/'catalog-approval.json',approval)
        intent=workflow.adoption_intent(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],approval,
                                       registration_record=record,pack_dir=pack)
        with self.assertRaises(ProductionError) as caught:fixture.grant(self.root,self.run,intent)
        self.assertEqual(caught.exception.diagnostic.code,'GRANT_SCOPE_EXCEEDED')
        self.assertEqual(store.event_rows(self.root,self.run),original)
        authority=store.authority(self.root,self.task['task_id'])
        authority['grants'][0]['targets'].append('canon:catalog')
        self.import_authority(authority)
        token=fixture.grant(self.root,self.run,intent)
        result=workflow.adopt(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],'catalog-approval.json',token,
            registration_record=record,pack_dir=pack,settings=self.settings)
        self.assertEqual(result['data']['result']['status'],'catalog-registered')
        self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id']),done)
        self.assertEqual(workflow.complete(self.root,self.run),done)
        rows=store.event_rows(self.root,self.run)
        self.assertEqual(rows[:len(original)],original)
        self.assertEqual(sum(row['event']=='completion' for row in rows),1)
        self.assertEqual(accounting.summary(self.root)['submissions'],1)
        current=studio_reference.current_source(self.root,'robot','base.front')
        self.assertEqual(current['artifact_id'],source['artifact_id'])
        self.assertNotEqual(current['proof_sha256'],source['proof_sha256'])
        self.assertTrue(execution.status(self.root,self.run)['runs'][0]['selection_ready'])

    def test_review_and_delivery_selection_do_not_adopt_identity(self):
        before=(studio.character_home(self.root,'robot')/'sheet/sheet-data.json').read_bytes()
        self.select()
        self.assertEqual(workflow.candidate_state(self.root,self.run,self.candidate)['disposition'],'selected')
        self.assertEqual((studio.character_home(self.root,'robot')/'sheet/sheet-data.json').read_bytes(),before)
        self.assertFalse((studio.character_home(self.root,'robot')/'adoptions').exists())

    def test_adoption_starts_from_the_current_selection(self):
        with self.assertRaises(ProductionError) as caught:self.authorize_adoption()
        self.assertEqual(caught.exception.diagnostic.code,'SELECTION_REQUIRED')
        self.assertFalse(any(r['event']=='adoption-claim' for r in store.event_rows(self.root,self.run)))

    def test_owner_accepted_failure_can_be_adopted_under_its_separate_authority(self):
        review=c.load(self.root/'review.json')
        review['checks'][0].update(verdict='fail',reason='The synthetic shape differs from the commissioned shape.')
        review['unresolved']=['The owner must decide whether to use this observed synthetic shape.']
        f.write(self.root/'failed-review.json',review)
        recorded=workflow.review(self.root,self.run,'failed-review.json')
        acceptance={'principal':store.authority(self.root,self.task['task_id'])['issuer'],
            'evidence':{'path':'adoption-basis.txt','sha256':c.sha256_file(self.root/'adoption-basis.txt'),'locator':'whole'},
            'criteria':['output'],'unresolved_indices':[0],
            'reason':'The synthetic owner accepts this reviewed shape for the explicitly approved reference.'}
        self.select(owner_acceptance=acceptance)
        token=self.authorize_adoption()
        self.assertEqual(self.adopt(token)['event'],'adoption-result')
        self.select(scope='studio-adoption',owner_acceptance=acceptance,
            adoption={'character':'robot','iteration_id':self.row['iteration_id'],'scope':'sheet'})
        workflow.complete(self.root,self.run)
        state=workflow.candidate_state(self.root,self.run,self.candidate)
        self.assertEqual((state['evaluation'],state['selection_basis']),('nonconforming','owner-allowance'))
        self.assertEqual(workflow.latest_review(store.event_rows(self.root,self.run),self.candidate),recorded)

    def test_imported_copy_is_diagnosed_before_an_adoption_claim(self):
        self.select()
        imported=studio.iterate(self.root,'robot','base.front',self.root/self.row['result']['path'],
            package=None,request=None,response=None,
            note='Synthetic external import with identical pixels and distinct ownership.')
        self.assertIsNone(imported.get('production'))
        self.assertNotEqual(imported['iteration_id'], self.row['iteration_id'])
        approval={**self.approval,'iteration_id':imported['iteration_id']}
        before=store.event_rows(self.root,self.run)
        with self.assertRaises(ProductionError) as caught:
            workflow.adoption_intent(self.root,self.run,self.candidate,'robot',imported['iteration_id'],approval)
        self.assertEqual(caught.exception.diagnostic.code,'ADOPTION_OWNER_MISMATCH')
        self.assertEqual(store.event_rows(self.root,self.run),before)

    def test_separate_authorized_adoption_and_completion(self):
        self.select()
        token=self.authorize_adoption();record=self.adopt(token)
        self.assertEqual(record['event'],'adoption-result');self.assertEqual(self.adopt(token),record)
        self.select_adoption();workflow.complete(self.root,self.run)
        self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id'])['event'],'completion')
        self.assertEqual(accounting.summary(self.root)['submissions'],1)
        self.assertIsNone(execution.status(self.root,self.run)['runs'][0]['next_action'])

    def test_adoption_publishes_views_once_after_its_production_result(self):
        import studio_activity as activity
        self.select()
        token = self.authorize_adoption()
        refreshed = []
        original = activity.refresh

        def refresh(root, **kwargs):
            records = store.event_rows(root, self.run)
            self.assertTrue(any(row['event'] == 'adoption-result' for row in records))
            refreshed.append(True)
            return original(root, **kwargs)

        with patch.object(activity, 'refresh', side_effect=refresh):
            self.adopt(token)
        self.assertEqual(len(refreshed), 1)
        self.assertTrue(adoption_workflow.reference_index(self.root, 'robot')['ok'])

    def test_status_and_current_reference_share_one_run_read_per_operation(self):
        self.select()
        self.adopt(self.authorize_adoption())
        for action in (lambda: studio_reference.current_source(self.root, 'robot', 'base.front'),
                       lambda: adoption_workflow.reference_index(self.root, 'robot'),
                       lambda: studio.status(self.root)):
            with self.subTest(action=action), patch.object(workflow, 'read_run', wraps=workflow.read_run) as load:
                action()
                self.assertEqual(load.call_count, 1)

    def test_destination_validation_does_not_project_production(self):
        with patch.object(workflow, 'read_run', side_effect=AssertionError('destination validation must only read stored rows')):
            self.assertEqual(studio.validate_recording_target(self.root, 'robot', 'base.front'),
                             studio.character_home(self.root, 'robot'))

    def test_accept_resolves_a_short_root_before_recording(self):
        self.select()
        alias = self.root.parent / 'alias-studio'
        original = Path.resolve

        def resolve(path, *, strict=False):
            if path == alias:
                return self.root
            return original(path, strict=strict)

        with patch.object(Path, 'resolve', new=resolve):
            accepted = studio.accept(alias, 'robot', self.row['iteration_id'])
            home = studio.character_home(alias, 'robot')
        self.assertEqual(accepted['accepted_path'], 'characters/robot/accepted/base.front.png')
        self.assertEqual(home, self.root / 'characters' / 'robot')

    def test_low_level_adoption_needs_the_production_claim(self):
        self.select()
        with self.assertRaisesRegex(ValueError,'production_workflow.py adopt'):
            adoption_workflow.adopt(self.root,'robot',self.row['iteration_id'],self.approval)
        with self.assertRaisesRegex(ValueError,'does not name this candidate'):
            adoption_workflow.adopt(self.root,'robot',self.row['iteration_id'],self.approval,production_claim='0'*64)
        self.assertFalse((studio.character_home(self.root,'robot')/'adoptions').exists())
        self.assertEqual(studio.read_iterations(studio.character_home(self.root,'robot'))[0]['status'],'candidate')

    def test_studio_adoption_selection_needs_the_run_adoption_result(self):
        self.select()
        token=self.authorize_adoption()
        append=workflow.append_record
        def interrupted(*args, **kwargs):
            if args[3]=='adoption-result':
                raise OSError('Synthetic interruption after Studio adoption.')
            return append(*args, **kwargs)
        with patch.object(workflow,'append_record',side_effect=interrupted):
            with self.assertRaises(OSError): self.adopt(token)
        with self.assertRaises(ProductionError) as caught:self.select_adoption()
        self.assertEqual(caught.exception.diagnostic.code,'ADOPTION_RESULT_MISSING')

    def test_interrupted_local_adoption_reuses_generation_execution(self):
        self.select()
        token=self.authorize_adoption()
        with patch.object(adoption_workflow,'_bind_sheet',side_effect=OSError('Synthetic adoption save interruption')):
            with self.assertRaises(OSError):self.adopt(token)
        result=self.adopt(token)
        self.assertEqual(result['event'],'adoption-result')
        rows=store.event_rows(self.root,self.run)
        self.assertEqual(sum(r['event']=='adoption-claim' for r in rows),1)
        self.assertEqual(len(accounting.all_states(self.root)),1)
        self.assertEqual(accounting.summary(self.root)['submissions'],1)

    def test_different_continuity_evidence_cannot_be_substituted(self):
        self.select()
        token=self.authorize_adoption();f.write(self.root/'adoption-basis.txt','Other content must not be treated as the recorded approval.')
        with self.assertRaises(ValueError):self.adopt(token)
        self.assertFalse(any(r['event']=='adoption-result' for r in store.event_rows(self.root,self.run)))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
