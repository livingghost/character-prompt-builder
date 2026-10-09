#!/usr/bin/env python3
"""Exact Studio acceptance at send boundaries and independent recorded recovery."""
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


class StudioExecutionTests(unittest.TestCase):
    def setUp(self):
        self.case = fixture.adopted_case(self)
        self.root = self.case.root
        self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        self.task, self.source = fixture.reference_task(self.case)
        self.run = workflow.prepare(self.root, self.task)['run']

    def withdraw(self):
        value = c.load(self.sheet)
        slot = value['slots'][self.case.row['slot']]
        slot['history'].append(slot['current']); slot['current'] = None
        value['sheet_status'] = __import__('character_sheet').sheet_status(value)
        c.atomic_write_json(self.sheet, value)

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

    def test_withdrawal_after_prepare_stops_before_a_new_send(self):
        approved=decisions(self.root,self.run)
        self.withdraw()
        with patch.object(transport,'send',side_effect=AssertionError('No send after identity withdrawal')):
            with self.assertRaises(ValueError):execution.execute(self.root,self.run,decisions_file=approved)
        self.assertFalse(any(row['event']=='external-step' for row in store.event_rows(self.root,self.run)))

    def test_identity_change_during_upload_stops_the_send_boundary(self):
        approved=decisions(self.root,self.run); original=transport.upload_bytes
        def upload(*args,**kwargs):
            result=original(*args,**kwargs); self.withdraw(); return result
        with patch.object(transport,'upload_bytes',side_effect=upload), patch.object(transport,'send',side_effect=AssertionError('Boundary must recheck Studio adoption')) as send:
            with self.assertRaisesRegex(ValueError,'STUDIO_REFERENCE_CHANGED'):
                execution.execute(self.root,self.run,decisions_file=approved)
        self.assertEqual(send.call_count,0)
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
