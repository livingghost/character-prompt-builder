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

    def withdraw_adoption(self):
        import sheet_artifacts as fills
        from sheet_artifacts_smoke_test import withdrawal_decision
        sheet = studio.character_home(self.root, 'robot') / 'sheet/sheet-data.json'
        choice = withdrawal_decision(sheet, studio.placement_slot(self.row))
        return fills.withdraw(sheet, choice, evidence_root=sheet.parent)

    def test_withdrawal_preserves_production_selection_acceptance_and_historical_completion(self):
        self.select()
        self.adopt(self.authorize_adoption())
        self.select_adoption()
        completed = workflow.complete(self.root, self.run)
        rows = store.event_rows(self.root, self.run)
        iterations = (studio.character_home(self.root, 'robot') / 'iterations.jsonl').read_bytes()
        source = studio_reference.current_source(self.root, 'robot', self.row['slot'])
        self.withdraw_adoption()
        self.assertEqual(store.event_rows(self.root, self.run), rows)
        self.assertEqual((studio.character_home(self.root, 'robot') / 'iterations.jsonl').read_bytes(), iterations)
        self.assertEqual(workflow.verify_completion(self.root, self.run, self.task['task_id']), completed)
        with self.assertRaisesRegex(ValueError, 'no current accepted'):
            studio_reference.validate_source(source)
        index = adoption_workflow.reference_index(self.root, 'robot')
        self.assertTrue(index['ok'], index['errors'])
        self.assertEqual(index['bindings'][0]['status'], 'withdrawn')
        self.assertIsNone(index['bindings'][0]['image_path'])

    def test_withdrawal_of_superseded_production_adoption_preserves_its_completed_evidence(self):
        self.select()
        self.adopt(self.authorize_adoption())
        self.select_adoption()
        completed = workflow.complete(self.root, self.run)
        records = store.event_rows(self.root, self.run)
        home = studio.character_home(self.root, 'robot')
        journal = home / 'adoptions' / (self.row['iteration_id'] + '.json')
        original_journal = journal.read_bytes()
        source = studio_reference.current_source(self.root, 'robot', self.row['slot'])
        replacement = studio.iterate(self.root, 'robot', self.row['slot'], self.root / self.row['result']['path'],
            package=None, request=None, response=None, note='Synthetic later acceptance has its own import origin.')
        studio.accept(self.root, 'robot', replacement['iteration_id'])
        accepted = studio.acceptance_state(self.root, 'robot', self.row['slot'])
        iterations = (home / 'iterations.jsonl').read_bytes()
        with self.assertRaisesRegex(ValueError, 'incomplete or no longer accepted'):
            studio_reference.validate_source(source)
        self.withdraw_adoption()
        self.assertEqual(studio.acceptance_state(self.root, 'robot', self.row['slot']), accepted)
        self.assertEqual((home / 'iterations.jsonl').read_bytes(), iterations)
        self.assertEqual(journal.read_bytes(), original_journal)
        self.assertEqual(store.event_rows(self.root, self.run), records)
        self.assertEqual(workflow.verify_completion(self.root, self.run, self.task['task_id']), completed)

    def test_new_approval_after_withdrawal_retains_old_result_and_old_retry_cannot_restore_it(self):
        self.select()
        original_token = self.authorize_adoption()
        original_result = self.adopt(original_token)
        original_rows = store.event_rows(self.root, self.run)
        old_source = studio_reference.current_source(self.root, 'robot', self.row['slot'])
        self.withdraw_adoption()
        new_approval = {**self.approval, 'at': '2026-11-11T03:00:00Z',
                        'note': 'Synthetic author makes a new canonical decision after withdrawal.'}
        f.write(self.root / 'new-approval.json', new_approval)
        intent = workflow.adoption_intent(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'], new_approval)
        token = fixture.grant(self.root, self.run, intent)
        workflow.adopt(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'], 'new-approval.json', token)
        new_source = studio_reference.current_source(self.root, 'robot', self.row['slot'])
        self.assertEqual(new_source['artifact_id'], old_source['artifact_id'])
        self.assertNotEqual(new_source['acceptance_sha256'], old_source['acceptance_sha256'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual(rows[:len(original_rows)], original_rows)
        self.assertEqual(sum(row['event'] == 'adoption-result' for row in rows), 2)
        self.assertEqual(self.adopt(original_token), original_result)
        self.assertEqual(studio_reference.current_source(self.root, 'robot', self.row['slot']), new_source)
        self.assertEqual(len(studio.read_iterations(studio.character_home(self.root, 'robot'))), 1)

    def test_withdrawal_then_placement_correction_uses_a_new_adoption_of_the_same_candidate(self):
        import studio_placement
        self.select()
        self.adopt(self.authorize_adoption())
        original = store.event_rows(self.root, self.run)
        self.withdraw_adoption()
        move = studio_placement.draft(self.root, 'robot', self.row['iteration_id'], 'canon.corrected')
        move.update(by=fixture.ACTOR, at='2026-11-11T04:00:00Z',
                    reason='Synthetic author corrects placement while preserving the original recorded slot.')
        studio_placement.reassign(self.root, move)
        approval = adoption_workflow.draft_approval(self.root, 'robot', self.row['iteration_id'],
                                                   scope='sheet', influence='identity')
        approval.update(by=fixture.ACTOR, at='2026-11-11T05:00:00Z',
                        continuity_decision=self.approval['continuity_decision'])
        self.assertEqual(approval['slot'], 'canon.corrected')
        f.write(self.root / 'corrected-approval.json', approval)
        intent = workflow.adoption_intent(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'], approval)
        token = fixture.grant(self.root, self.run, intent)
        workflow.adopt(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'], 'corrected-approval.json', token)
        source = studio_reference.current_source(self.root, 'robot', 'canon.corrected')
        self.assertEqual(source['sha256'], self.row['result']['sha256'])
        self.assertEqual(studio.read_iteration_records(studio.character_home(self.root, 'robot'))[0]['slot'], self.row['slot'])
        self.assertEqual(store.event_rows(self.root, self.run)[:len(original)], original)
        self.select_adoption()
        completed = workflow.complete(self.root, self.run)
        self.assertEqual(workflow.verify_completion(self.root, self.run, self.task['task_id']), completed)

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
        decision=acceptance.draft(self.root,self.run,self.candidate,'fixture-grant',scope='studio-slot')
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
        self.select_adoption();completed=acceptance.accept(self.root,self.run)
        self.assertEqual(completed['scope'],'studio-adoption')
        self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id'])['sha256'],completed['completion'])
        self.assertEqual(acceptance.accept(self.root,self.run)['completion'],completed['completion'])
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
        action = caught.exception.diagnostic.required_action
        self.assert_names_adopt(caught.exception, token, 'ADOPTION_RESULT_MISSING')
        with self.assertRaises(ProductionError) as current:
            studio_reference.current_source(self.root, 'robot', 'base.front')
        self.assertEqual((current.exception.diagnostic.code, current.exception.diagnostic.required_action),
                         ('ADOPTION_RESULT_MISSING', action))
        import sheet_artifacts as fills
        with self.assertRaises(ProductionError) as withdrawal:
            fills.draft_withdrawal(studio.character_home(self.root, 'robot') / 'sheet/sheet-data.json', 'base.front')
        self.assertEqual((withdrawal.exception.diagnostic.code, withdrawal.exception.diagnostic.required_action),
                         ('ADOPTION_RESULT_MISSING', action))
        binding = adoption_workflow.reference_index(self.root, 'robot')['bindings'][0]
        self.assertEqual((binding['next_action'], binding['adoption']['diagnostics'][-1]['required_action']),
                         ('record-adoption-result', action))
        self.assertEqual(self.adopt(token)['event'], 'adoption-result')
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([sum(row['event'] == event for row in rows) for event in ('adoption-claim', 'adoption-result')], [1, 1])
        self.assertEqual(self.select_adoption()['event'], 'selection')

    def test_studio_adoption_selection_names_the_adopt_that_finishes_a_stopped_adoption(self):
        self.select()
        token = self.authorize_adoption()
        with patch.object(adoption_workflow, '_bind_sheet', side_effect=OSError('Synthetic stop before the sheet binding.')):
            with self.assertRaises(OSError):
                self.adopt(token)
        with self.assertRaises(ProductionError) as caught:
            self.select_adoption()
        self.assert_names_adopt(caught.exception, token, 'ADOPTION_RESULT_MISSING')
        self.assertEqual(self.adopt(token)['event'], 'adoption-result')
        self.assertEqual(self.select_adoption()['event'], 'selection')

    def test_completion_refuses_a_selection_that_saved_an_unfinished_adoption_record(self):
        token, record, path = self.adopted_record()
        promote, _ = self.catalog_promotion()
        with patch.object(adoption_workflow, 'adopt', side_effect=OSError('Synthetic stop before the owner starts.')):
            with self.assertRaises(OSError):
                promote()
        later = workflow.find(store.event_rows(self.root, self.run), 'adoption-claim')
        confirm = workflow.confirm_studio_adoption
        def rewritten_meanwhile(*args, **kwargs):
            paths = confirm(*args, **kwargs)
            c.atomic_write_json(path, {**c.load(path), 'production_claim': later['sha256']})
            return paths
        with patch.object(workflow, 'confirm_studio_adoption', side_effect=rewritten_meanwhile):
            selected = self.select_adoption()
        with self.assertRaises(ProductionError) as caught:
            workflow.complete(self.root, self.run)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, 'ADOPTION_RESULT_MISSING')
        self.assertIn(selected['sha256'], diagnostic.required_action)
        self.assertIn('draft-selection --run ' + self.run + ' --candidate ' + self.candidate, diagnostic.required_action)
        self.assertNotIn('production_workflow.py adopt', diagnostic.required_action)

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

    def adopted_record(self):
        """Adopt the selected candidate; return its authorization, recorded result row and Studio adoption record."""
        self.select()
        token = self.authorize_adoption()
        record = self.adopt(token)
        path = adoption_workflow._journal_path(studio.character_home(self.root, 'robot'), self.row['iteration_id'])
        return token, record, path

    def catalog_promotion(self):
        """Authorize promoting the sheet adoption to catalog scope; return the adopt call and its authorization."""
        from revision_contract import digest
        registration = {'id':'adopted-test-character','label':'Adopted fixture','curation_status':'curated',
            'category':'species','prompt':'a fictional test character','domains':['shared'],'tags':['fixture','character'],
            'search_terms':[{'phrase':'adopted test character','facet':'species','weight':1.0,'source':'author'}],
            'scaffold':{'family':'direct-geometry-required','confidence':'fallback'}}
        approval = {**self.approval, 'scope':'catalog', 'registration_record_sha256':digest(registration)}
        pack = Path(self.temp.name) / 'registered-pack'
        f.write(self.root / 'catalog-approval.json', approval)
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['targets'].append('canon:catalog')
        self.import_authority(authority)
        token = fixture.grant(self.root, self.run, workflow.adoption_intent(self.root, self.run, self.candidate,
            'robot', self.row['iteration_id'], approval, registration_record=registration, pack_dir=pack))
        return (lambda: workflow.adopt(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'],
                    'catalog-approval.json', token, registration_record=registration, pack_dir=pack,
                    settings=self.settings)), token

    def assert_names_adopt(self, error, token, code, approval='approval.json'):
        diagnostic = error.diagnostic
        self.assertEqual(diagnostic.code, code)
        claim = next(row for row in store.event_rows(self.root, self.run)
                     if row['event'] == 'adoption-claim' and token in row['data']['authorizations'])
        for part in ('production_workflow.py adopt --run ' + self.run, '--claim ' + claim['sha256']):
            self.assertIn(part, diagnostic.required_action)

    def assert_names_restoring_adopt(self, error, token, approval='approval.json'):
        self.assert_names_adopt(error, token, 'ADOPTION_RECORD_CORRUPT', approval)

    def assert_readers_name_restoring_adopt(self, token, message):
        """Every reader of the adoption record reports ADOPTION_RECORD_CORRUPT with the adopt command that restores it."""
        reads = (lambda: studio_reference.current_source(self.root, 'robot', 'base.front'), self.select_adoption,
                 lambda: workflow.adoption_intent(self.root, self.run, self.candidate, 'robot',
                                                  self.row['iteration_id'], self.approval))
        for read in reads:
            with self.subTest(read=read), self.assertRaises(ProductionError) as caught:
                read()
            self.assert_names_restoring_adopt(caught.exception, token)
            self.assertIn(message, caught.exception.diagnostic.message)
        binding = adoption_workflow.reference_index(self.root, 'robot')['bindings'][0]
        self.assertEqual(binding['next_action'], 'repair-reference')
        diagnostic = binding['adoption']['diagnostics'][-1]
        self.assertEqual((diagnostic['code'], diagnostic['required_action']),
                         ('ADOPTION_RECORD_CORRUPT', caught.exception.diagnostic.required_action))
        self.assertIn(caught.exception.diagnostic.required_action, studio.status(self.root))

    def assert_repeated_adopt_restores(self, token, record, path):
        recorded = {key: value for key, value in record['data']['result'].items() if key != 'ok'}
        events = store.event_rows(self.root, self.run)
        with (patch.object(adoption_workflow, 'adopt', side_effect=AssertionError('The owner adoption must not run again')),
              patch.object(adoption_workflow, '_bind_sheet', side_effect=AssertionError('The sheet must not be bound again'))):
            self.assertEqual(self.adopt(token), record)
        self.assertEqual(c.load(path), recorded)
        self.assertEqual(store.event_rows(self.root, self.run), events)
        studio_reference.validate_source(studio_reference.current_source(self.root, 'robot', 'base.front'))
        index = adoption_workflow.reference_index(self.root, 'robot')
        self.assertTrue(index['ok'], index['errors'])
        self.assertEqual(self.select_adoption()['event'], 'selection')

    def test_repeated_adopt_restores_a_deleted_adoption_record(self):
        token, record, path = self.adopted_record()
        path.unlink()
        for read in (lambda: studio_reference.current_source(self.root, 'robot', 'base.front'), self.select_adoption):
            with self.subTest(read=read), self.assertRaises(ProductionError) as caught:
                read()
            self.assert_names_restoring_adopt(caught.exception, token)
        binding = adoption_workflow.reference_index(self.root, 'robot')['bindings'][0]
        self.assertEqual(binding['next_action'], 'repair-reference')
        self.assertEqual(binding['adoption']['diagnostics'][-1]['code'], 'ADOPTION_RECORD_CORRUPT')
        self.assert_repeated_adopt_restores(token, record, path)

    def test_repeated_adopt_restores_a_truncated_adoption_record(self):
        token, record, path = self.adopted_record()
        path.write_bytes(path.read_bytes()[:40])
        reads = (lambda: studio_reference.current_source(self.root, 'robot', 'base.front'), self.select_adoption,
                 lambda: workflow.adoption_intent(self.root, self.run, self.candidate, 'robot',
                                                  self.row['iteration_id'], self.approval))
        for read in reads:
            with self.subTest(read=read), self.assertRaises(ProductionError) as caught:
                read()
            self.assert_names_restoring_adopt(caught.exception, token)
        binding = adoption_workflow.reference_index(self.root, 'robot')['bindings'][0]
        self.assertEqual(binding['next_action'], 'repair-reference')
        diagnostic = binding['adoption']['diagnostics'][-1]
        self.assertEqual((diagnostic['code'], diagnostic['required_action']),
                         ('ADOPTION_RECORD_CORRUPT', caught.exception.diagnostic.required_action))
        self.assertIn(caught.exception.diagnostic.required_action, studio.status(self.root))
        self.assert_repeated_adopt_restores(token, record, path)

    def test_repeated_adopt_restores_the_record_of_a_superseded_iteration(self):
        token, record, path = self.adopted_record()
        imported = studio.iterate(self.root, 'robot', 'base.front', self.root / self.row['result']['path'],
            package=None, request=None, response=None, note='Another explicit synthetic slot choice with separate ownership.')
        studio.accept(self.root, 'robot', imported['iteration_id'])
        path.write_bytes(path.read_bytes()[:40])
        errors = adoption_workflow.reference_index(self.root, 'robot')['errors']
        claim = next(row for row in store.event_rows(self.root, self.run)
                     if row['event'] == 'adoption-claim' and token in row['data']['authorizations'])
        self.assertTrue(any(path.name in error and '--claim ' + claim['sha256'] in error for error in errors), errors)
        with patch.object(adoption_workflow, 'adopt', side_effect=AssertionError('The owner adoption must not run again')):
            self.assertEqual(self.adopt(token), record)
        self.assertEqual(c.load(path), {key: value for key, value in record['data']['result'].items() if key != 'ok'})
        errors = adoption_workflow.reference_index(self.root, 'robot')['errors']
        self.assertFalse(any(path.name in error for error in errors), errors)

    def test_repeated_adopt_restores_a_changed_adoption_record(self):
        token, record, path = self.adopted_record()
        recorded = c.load(path)
        changes = {
            'approval': lambda value: value['approval'].update(by='Another approver'),
            'status': lambda value: value.update(status='candidate-accepted', next_action='bind-sheet'),
            'sheet_decision': lambda value: value['sheet_decision'].update(reason='Another synthetic reason.'),
            'production_claim': lambda value: value.update(production_claim='f' * 64),
        }
        for field, change in changes.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(recorded)
                change(changed)
                c.atomic_write_json(path, changed)
                self.assert_readers_name_restoring_adopt(
                    token, 'names no adoption claim' if field == 'production_claim' else 'differs from the result')
                self.assert_repeated_adopt_restores(token, record, path)

    def test_an_earlier_adoption_result_in_place_of_the_latest_one_is_restored(self):
        token, record, path = self.adopted_record()
        promote, catalog_token = self.catalog_promotion()
        promoted = promote()
        c.atomic_write_json(path, {key: value for key, value in record['data']['result'].items() if key != 'ok'})
        with self.assertRaises(ProductionError) as caught:
            studio_reference.current_source(self.root, 'robot', 'base.front')
        self.assert_names_restoring_adopt(caught.exception, catalog_token, 'catalog-approval.json')
        self.assertIn('earlier adoption', caught.exception.diagnostic.message)
        self.assertIn('pack runtime arguments', caught.exception.diagnostic.required_action)
        self.assertEqual(adoption_workflow.reference_index(self.root, 'robot')['bindings'][0]['next_action'],
                         'repair-reference')
        with patch.object(adoption_workflow, 'adopt', side_effect=AssertionError('The owner adoption must not run again')):
            self.assertEqual(promote(), promoted)
        self.assertEqual(c.load(path), {key: value for key, value in promoted['data']['result'].items() if key != 'ok'})
        studio_reference.validate_source(studio_reference.current_source(self.root, 'robot', 'base.front'))

    def test_an_unfinished_catalog_adoption_resumes_after_its_earlier_record_is_restored(self):
        token, record, path = self.adopted_record()
        promote, catalog_token = self.catalog_promotion()
        with patch.object(adoption_workflow, 'add_pack_root', side_effect=OSError('Synthetic stop after the pack is written.')):
            with self.assertRaises(OSError):
                promote()
        pack = Path(c.load(path)['registration_target'])
        created = c.load(pack / 'pack.json')['pack_id']
        path.unlink()
        for read in (lambda: studio_reference.current_source(self.root, 'robot', 'base.front'), promote):
            with self.subTest(read=read), self.assertRaises(ProductionError) as caught:
                read()
            self.assert_names_restoring_adopt(caught.exception, token)
        self.assertEqual(self.adopt(token), record)
        self.assertEqual(c.load(path), {key: value for key, value in record['data']['result'].items() if key != 'ok'})
        promoted = promote()
        result = promoted['data']['result']
        self.assertEqual((result['status'], result['registration']['pack_id']), ('catalog-registered', created))
        self.assertEqual(c.load(pack / 'pack.json')['pack_id'], created)
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([sum(row['event'] == event for row in rows) for event in ('adoption-claim', 'adoption-result')], [2, 2])
        self.assertEqual(c.load(path), {key: value for key, value in result.items() if key != 'ok'})
        studio_reference.validate_source(studio_reference.current_source(self.root, 'robot', 'base.front'))
        self.assertTrue(adoption_workflow.reference_index(self.root, 'robot')['ok'])

    def test_repeated_adopt_leaves_an_intact_adoption_record(self):
        token, record, path = self.adopted_record()
        raw = path.read_bytes()
        with (patch.object(adoption_workflow, 'adopt', side_effect=AssertionError('The owner adoption must not run again')),
              patch.object(adoption_workflow, 'atomic_write_json', side_effect=AssertionError('An intact record is not written'))):
            self.assertEqual(self.adopt(token), record)
        self.assertEqual(path.read_bytes(), raw)

    def test_repeated_adopt_keeps_the_record_of_a_later_adoption_of_the_iteration(self):
        from revision_contract import digest
        token, record, path = self.adopted_record()
        registration = {'id':'adopted-test-character','label':'Adopted fixture','curation_status':'curated',
            'category':'species','prompt':'a fictional test character','domains':['shared'],'tags':['fixture','character'],
            'search_terms':[{'phrase':'adopted test character','facet':'species','weight':1.0,'source':'author'}],
            'scaffold':{'family':'direct-geometry-required','confidence':'fallback'}}
        approval = {**self.approval, 'scope':'catalog', 'registration_record_sha256':digest(registration)}
        pack = Path(self.temp.name) / 'registered-pack'
        f.write(self.root / 'catalog-approval.json', approval)
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['targets'].append('canon:catalog')
        self.import_authority(authority)
        catalog_token = fixture.grant(self.root, self.run, workflow.adoption_intent(self.root, self.run, self.candidate,
            'robot', self.row['iteration_id'], approval, registration_record=registration, pack_dir=pack))
        promote = lambda: workflow.adopt(self.root, self.run, self.candidate, 'robot', self.row['iteration_id'],
            'catalog-approval.json', catalog_token, registration_record=registration, pack_dir=pack, settings=self.settings)
        promoted = promote()
        later = {key: value for key, value in promoted['data']['result'].items() if key != 'ok'}
        raw = path.read_bytes()
        self.assertEqual(self.adopt(token), record)
        self.assertEqual(path.read_bytes(), raw)
        path.unlink()
        self.assertEqual(self.adopt(token), record)
        self.assertFalse(path.exists())
        with self.assertRaises(ProductionError) as caught:
            studio_reference.current_source(self.root, 'robot', 'base.front')
        claim = next(row for row in store.event_rows(self.root, self.run)
                     if row['event'] == 'adoption-claim' and catalog_token in row['data']['authorizations'])
        self.assertIn('--claim ' + claim['sha256'], caught.exception.diagnostic.required_action)
        self.assertIn('pack runtime arguments', caught.exception.diagnostic.required_action)
        with patch.object(adoption_workflow, 'adopt', side_effect=AssertionError('The owner adoption must not run again')):
            self.assertEqual(promote(), promoted)
        self.assertEqual(c.load(path), later)
        studio_reference.validate_source(studio_reference.current_source(self.root, 'robot', 'base.front'))

    def test_changed_iteration_slot_names_the_record_that_disagrees(self):
        _, _, path = self.adopted_record()
        raw = path.read_bytes()
        home = studio.character_home(self.root, 'robot')
        rows = studio.read_iteration_records(home)
        rows[0]['slot'] = 'base.side'
        studio.write_iterations(home, rows)
        with self.assertRaises(ProductionError) as caught:
            self.select_adoption()
        diagnostic = caught.exception.diagnostic.as_dict()
        self.assertEqual(diagnostic['code'], 'ADOPTION_RECORD_CORRUPT')
        self.assertEqual(diagnostic['expected'], {'slot':'base.front', 'image_sha256':self.row['result']['sha256']})
        self.assertEqual(diagnostic['actual'], {'slot':'base.side', 'image_sha256':self.row['result']['sha256']})
        self.assertIn('characters/robot/iterations.jsonl', diagnostic['required_action'])
        self.assertNotIn('production_workflow.py', diagnostic['required_action'])
        self.assertEqual(path.read_bytes(), raw)


class RecordedAdoptionEvidenceTests(unittest.TestCase):
    """A recorded studio-adoption selection is verified from the snapshots it saved; synthetic records only."""

    def test_a_studio_adoption_selection_without_a_saved_file_names_a_new_run(self):
        run = 'synthetic-run'
        candidate = {'sequence': 1, 'event': 'candidate', 'sha256': 'c' * 64, 'data': {'files': [{'sha256': 'e' * 64}]}}
        selection = {'sequence': 2, 'event': 'selection', 'sha256': 'd' * 64, 'data': {'files': [], 'selection': {
            'scope': 'studio-adoption', 'candidate': candidate['sha256'],
            'adoption': {'character': 'robot', 'iteration_id': 'synthetic-iteration', 'scope': 'sheet'}}}}
        with self.assertRaises(ProductionError) as caught:
            workflow._recorded_studio_adoption(run, selection, [candidate, selection], lambda key: b'')
        found = caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'], found['file'], found['run'], found['event']),
                         ('EVIDENCE_SNAPSHOT_MISSING', 'characters/robot/adoptions/synthetic-iteration.json',
                          run, selection['sha256']))
        # The record names no snapshot of the file, so there are no saved bytes to restore.
        self.assertNotIn('expected', found)
        self.assertEqual(found['required_action'], workflow.UNSAVED_SELECTION_RECORD.format(run=run))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
