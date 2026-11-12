#!/usr/bin/env python3
"""Saved Studio reference media, current placement notices and recorded recovery."""
from __future__ import annotations
import copy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import execution_contract as c
import studio_reference as sr
import studio_reference_fixtures as fixture
import production_execution as execution
import production_workflow as workflow
import production_store as store
import transport_synthetic as transport
from test_production_execution import decisions
from sheet_artifacts_smoke_test import make_artifact, decision
import sheet_artifacts as fills
import runtime_snapshot


class StudioExecutionTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.adopted_case(self)
        self.root = self.case.root
        self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        self.task, self.source = fixture.reference_task(self.case)
        self.run = workflow.prepare(self.root, self.task)['run']

    def withdraw(self):
        from sheet_artifacts_smoke_test import withdrawal_decision
        decision = withdrawal_decision(self.sheet, self.case.row['slot'])
        fills.withdraw(self.sheet, decision, evidence_root=self.sheet.parent)

    def test_preparation_pins_the_exact_acceptance_and_portable_proof(self):
        directory, prepared, _, _ = workflow.load_run(self.root, self.run)
        self.assertEqual(prepared['studio_reference_sources'], [self.source])
        self.assertTrue(list(directory.glob('package.*.references/studio/*/proof.json')))
        from verify_generation_payload import verify_content
        self.assertTrue(verify_content(c.load(directory/'package.json'),package_root=directory)['content_verified'])

    def test_candidate_addition_and_unrelated_adoption_keep_preparation_current(self):
        extra = make_artifact(self.sheet, marker='unrelated')
        fills.register_candidates(self.sheet,[(self.case.row['slot'],extra),('unrelated.panel',extra)])
        fills.adopt(self.sheet,decision(self.sheet,'unrelated.panel',extra),evidence_root=self.sheet.parent)
        workflow.assert_current(self.root,self.run,force=True)
        with patch.object(transport,'send',wraps=transport.send) as send:
            result=execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        self.assertEqual(send.call_count,1)
        self.assertTrue(result['execution_completed'])

    def test_withdrawal_after_prepare_sends_the_saved_media_and_reports_current_placement(self):
        approved=decisions(self.root,self.run)
        self.withdraw()
        with patch.object(transport,'send',wraps=transport.send) as send, \
             patch.object(transport,'upload_media',wraps=transport.upload_media) as upload:
            result=execution.execute(self.root,self.run,decisions_file=approved)
        self.assertEqual(send.call_count,1)
        self.assertEqual(c.digest(upload.call_args.args[0]),self.source['sha256'])
        self.assertTrue(result['execution_completed'])
        self.assertEqual(result['runs'][0]['freshness_diagnostics'],[])
        self.assertIn(('STUDIO_REFERENCE_CHANGED','warning'),
            [(item['code'],item['severity']) for item in result['runs'][0]['freshness_notices']])

    def test_reference_replacement_is_observed_without_replacing_saved_media(self):
        extra = make_artifact(self.sheet, marker='explicit-replacement')
        fills.register_candidates(self.sheet, [(self.case.row['slot'], extra)])
        # A new navigation observation sees the replacement within this same
        # call; the selected run still owns its original reference media.
        with runtime_snapshot.public_call(), store.transaction(self.root):
            saved=workflow.assert_current(self.root,self.run)
            self.assertEqual(workflow.freshness(self.root,self.run),([],[]))
            fills.adopt(self.sheet, decision(self.sheet, self.case.row['slot'], extra),
                        evidence_root=self.sheet.parent)
            current=workflow.assert_current(self.root,self.run)
            self.assertEqual(current.prepared,saved.prepared)
            failures,notices=workflow.freshness(self.root,self.run)
            self.assertEqual(failures,[])
            self.assertIn('STUDIO_REFERENCE_CHANGED',[item['code'] for item in notices])

    def test_identity_change_during_upload_preserves_the_saved_send(self):
        approved=decisions(self.root,self.run); original=transport.upload_media
        def upload(*args,**kwargs):
            result=original(*args,**kwargs); self.withdraw(); return result
        with patch.object(transport,'upload_media',side_effect=upload) as uploaded, \
             patch.object(transport,'send',wraps=transport.send) as send:
            result=execution.execute(self.root,self.run,decisions_file=approved)
        self.assertEqual(c.digest(uploaded.call_args.args[0]),self.source['sha256'])
        self.assertEqual(send.call_count,1)
        self.assertTrue(result['execution_completed'])
        self.assertIn('STUDIO_REFERENCE_CHANGED',[item['code'] for item in result['runs'][0]['freshness_notices']])
        steps=[row for row in store.event_rows(self.root,self.run) if row['event']=='external-step']
        self.assertEqual([row['data']['operation'] for row in steps],['upload','send','delete'])

    def test_imported_authority_revocation_during_upload_stops_the_send(self):
        from production_diagnostics import ProductionError
        approved=decisions(self.root,self.run)
        original=transport.upload_media
        def revoke_after_upload(*args,**kwargs):
            result=original(*args,**kwargs)
            task=workflow.read_run(self.root,self.run).prepared['task']['task_id']
            authority=copy.deepcopy(store.authority(self.root,task))
            for grant in authority['grants']:
                grant['revoked_at']='2000-01-01T00:00:00Z'
            prior=store.authority_record(self.root,task)
            (self.root/'revoked-during-upload.json').write_bytes(c.encoded(authority))
            store.import_authority(self.root,'revoked-during-upload.json',expected=prior['sha256'])
            return result
        with patch.object(transport,'upload_media',side_effect=revoke_after_upload), \
             patch.object(transport,'send') as send:
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run,decisions_file=approved)
        self.assertEqual(caught.exception.diagnostic.code,'GRANT_REVOKED')
        send.assert_not_called()
        steps=[row for row in store.event_rows(self.root,self.run) if row['event']=='external-step']
        self.assertEqual([row['data']['operation'] for row in steps],['upload'])

    def test_saved_answer_recovery_survives_identity_withdrawal(self):
        approved=decisions(self.root,self.run)
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic interruption after answer')):
            with self.assertRaises(OSError):execution.execute(self.root,self.run,decisions_file=approved)
        self.withdraw()
        with patch.object(transport,'send',side_effect=AssertionError('Recovery must never resend')):
            result=execution.resume(self.root,self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(len(result['runs'][0]['candidates']),1)

    def test_saved_answer_recovery_survives_original_image_and_approval_removal(self):
        approved=decisions(self.root,self.run)
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic interruption after answer')):
            with self.assertRaises(OSError):execution.execute(self.root,self.run,decisions_file=approved)
        shutil.rmtree(self.sheet.parent/'.fills')
        with patch.object(transport,'send',side_effect=AssertionError('Recovery must use frozen proof')):
            result=execution.resume(self.root,self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(len(result['runs'][0]['candidates']),1)

    def test_completed_run_content_survives_later_replacement(self):
        result=execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        self.assertTrue(result['execution_completed'])
        self.withdraw()
        with patch.object(transport,'send',side_effect=AssertionError('Completed run cannot resend')):
            again=execution.resume(self.root,self.run)
        self.assertTrue(again['execution_completed'])


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
