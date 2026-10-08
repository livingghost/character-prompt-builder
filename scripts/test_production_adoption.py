"""Explicit canonical adoption is separate from synthetic generation and selection."""
from __future__ import annotations
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
import execution_lifecycle as accounting
import studio
from production_diagnostics import ProductionError
from test_production_execution import decisions
from visual_continuity import file_ref


class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        b=Path(self.temp.name);case=f.create(b/'studio',b/'runtime');self.root=case['root'];self.task=case['task']
        self.task['recording'].update(slot='base.front',sheet_panel=True,subject_map={'robot':'robot'})
        self.task['generation']['continuity']['robot']='undecided'
        f.write(self.root/'task.json',self.task)
        self.run=workflow.prepare(self.root,'task.json')['run']
        output=execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        self.candidate=output['runs'][0]['candidates'][0]
        self.row=studio.read_iterations(studio.character_home(self.root,'robot'))[0]
        review=workflow.draft_review(self.root,self.run,self.candidate)
        review.update(reviewer='Synthetic test reviewer',observations=[{'evidence':'candidate','locator':{'kind':'whole'},
            'observation':'A real local synthetic PNG was captured.','interpretation':'Protocol fixture only.',
            'limitations':['No generative quality or user approval is asserted.']}],conclusion='Synthetic test decision.')
        for check in review['checks']:check.update(verdict='pass',observation_indices=[0],reason='Explicit synthetic fixture assessment.')
        f.write(self.root/'review.json',review);workflow.review(self.root,self.run,'review.json')
        f.write(self.root/'adoption-basis.txt','Explicit synthetic author decision to adopt this fixture identity. Not user consent.')
        self.approval={'scope':'sheet','influence':'identity','character':'robot','iteration_id':self.row['iteration_id'],
            'slot':self.row['slot'],'image_sha256':self.row['result']['sha256'],'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z',
            'continuity_decision':{'character_id':'robot','continuity':'recurring',
                'basis':file_ref(self.root,'adoption-basis.txt',locator='whole'),'by':fixture.ACTOR,'at':'2000-01-01T00:00:00Z'}}
        f.write(self.root/'approval.json',self.approval)

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

    def adopt(self,token):
        return workflow.adopt(self.root,self.run,self.candidate,'robot',self.row['iteration_id'],'approval.json',token)

    def test_review_and_delivery_selection_do_not_adopt_identity(self):
        before=(studio.character_home(self.root,'robot')/'sheet/sheet-data.json').read_bytes()
        self.select()
        self.assertEqual(workflow.candidate_state(self.root,self.run,self.candidate)['disposition'],'selected')
        self.assertEqual((studio.character_home(self.root,'robot')/'sheet/sheet-data.json').read_bytes(),before)
        self.assertFalse((studio.character_home(self.root,'robot')/'adoptions').exists())

    def test_adoption_starts_from_the_current_selection(self):
        token=self.authorize_adoption()
        with self.assertRaises(ProductionError) as caught:self.adopt(token)
        self.assertEqual(caught.exception.diagnostic.code,'SELECTION_REQUIRED')
        self.assertFalse(any(r['event']=='adoption-claim' for r in store.event_rows(self.root,self.run)))

    def test_separate_authorized_adoption_and_completion(self):
        self.select()
        token=self.authorize_adoption();record=self.adopt(token)
        self.assertEqual(record['event'],'adoption-result');self.assertEqual(self.adopt(token),record)
        self.select_adoption();workflow.complete(self.root,self.run)
        self.assertEqual(workflow.verify_completion(self.root,self.run,self.task['task_id'])['event'],'completion')
        self.assertEqual(accounting.summary(self.root)['submissions'],1)
        self.assertIsNone(execution.status(self.root,self.run)['runs'][0]['next_action'])

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
