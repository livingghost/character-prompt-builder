#!/usr/bin/env python3
"""Continuous synthetic redo, owned folders, snapshot recovery and live gallery tests."""
from __future__ import annotations
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_workflow as workflow
import production_execution as execution
import sheet_batch as batch
import sheet_batch_smoke_test as fixture
import sheet_inventory
import studio
import transport_synthetic


class AttemptTests(unittest.TestCase):
    setUp = fixture.BatchTests.setUp
    prepare = fixture.BatchTests.prepare
    execute = fixture.BatchTests.execute

    def redo(self, *, name='redo', independent=False):
        task=c.load(self.root/'task.json')
        if independent:
            from pack_manager import generate_uuid7
            task['production_id']=generate_uuid7()
        parameters=c.load(self.root/task['generation']['parameters']); parameters['steps']+=1
        fixtures.write(self.root/f'{name}-parameters.json',parameters)
        task['generation']['parameters']=f'{name}-parameters.json'
        fixtures.write(self.root/f'{name}-task.json',task)
        plan=copy.deepcopy(self.plan); plan['panels'][0]['task']=f'{name}-task.json'
        fixtures.write(self.root/f'{name}-plan.json',plan)
        return batch.initialize(self.root,f'{name}-plan.json')

    def test_dated_attempts_separate_redo_outputs_and_latest_never_rolls_back_on_recovery(self):
        first=self.execute(); first_entry=first['panels']['canon.primary']
        first_png=self.root/first_entry['results']/'anchor.png'; before=c.sha256_file(first_png)
        redo=self.redo()
        self.assertIn('/panels/',redo['panels']['canon.primary']['results'])
        self.assertIn(redo['created_at'][:10],redo['home'])
        self.assertNotEqual(redo['panels']['canon.primary']['results'],first_entry['results'])
        prepared=batch.advance(self.root,redo['state'],grant='fixture-grant')['panels']['canon.primary']
        approved=fixtures.fill_decisions(self.root,prepared['run'],'redo-approved.json')
        result=batch.advance(self.root,redo['state'],decisions={'canon.primary':approved})
        self.assertTrue(result['ok'],result)
        entry=result['panels']['canon.primary']
        second_png=self.root/entry['results']/'anchor.png'
        self.assertTrue(second_png.is_file()); self.assertEqual(c.sha256_file(first_png),before)
        latest=c.load(self.root/self.plan['results']/'latest.json')['panels']['canon.primary']
        self.assertEqual(latest['run'],entry['run'])
        first_png.unlink()
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('no repeat send')):
            recovered=batch.advance(self.root,'batch.json',unreceived_only=True)
        self.assertTrue(recovered['ok']); self.assertEqual(c.sha256_file(first_png),before)
        self.assertEqual(c.load(self.root/self.plan['results']/'latest.json')['panels']['canon.primary'],latest)
        rows=c.load(self.root/'gallery.json')['entries']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['production']['run'],entry['run'])
        self.assertEqual(rows[1]['production']['run'],first_entry['run'])
        self.assertIsNone(studio.gallery_stale(self.root))

    def test_original_task_plan_manifest_may_be_removed_after_send_without_blocking_recovery(self):
        result=self.execute(); entry=result['panels']['canon.primary']
        image=self.root/entry['results']/'anchor.png'; original=image.read_bytes(); image.unlink()
        for name in ('task.json','batch-plan.json','panel-fill-requests.json'):
            (self.root/name).unlink()
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('no repeated send')):
            restored=batch.advance(self.root,'batch.json',unreceived_only=True)
        self.assertTrue(restored['ok'],restored)
        self.assertEqual(image.read_bytes(),original)

    def test_mismatched_plan_is_a_clear_preparation_conflict(self):
        redo=self.redo()
        with self.assertRaisesRegex(ValueError,'BATCH_PLAN_CONFLICT'):
            batch.initialize(self.root,'redo-plan.json','batch.json')
        self.assertEqual(batch.load(self.root,'batch.json')['plan'],'batch-plan.json')
        self.assertEqual(batch.initialize(self.root,'redo-plan.json',redo['state'])['batch_id'],redo['batch_id'])

    def test_preexisting_output_is_detected_before_dispatch(self):
        run=self.prepare()
        journal=batch.load(self.root,'batch.json')
        target=self.root/journal['panels']['canon.primary']['results']/'unexpected.png'
        target.write_bytes(b'synthetic foreign bytes')
        approved=fixtures.fill_decisions(self.root,run,'approved.json')
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('must not send')) as send:
            result=batch.advance(self.root,'batch.json',decisions={'canon.primary':approved})
        self.assertEqual(send.call_count,0)
        self.assertEqual(result['exit_code'],2)
        self.assertIn('BATCH_OUTPUT_CONFLICT',result['panels']['canon.primary']['diagnostic']['message'])

    def test_damaged_unrelated_old_run_does_not_block_preparing_a_new_owned_run(self):
        first=self.execute(); old=first['panels']['canon.primary']['run']
        manifest=workflow.run_dir(self.root,old)/'manifest.json'
        manifest.unlink()
        redo=self.redo(independent=True)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('awaiting approval')):
            result=batch.advance(self.root,redo['state'],grant='fixture-grant')
        self.assertEqual(result['exit_code'],3,result)
        self.assertEqual(result['panels']['canon.primary']['status'],'approval-required')
        # Existing damage is diagnosed on its gallery entry; the index is still rebuildable.
        import studio_activity
        self.assertTrue(studio_activity.refresh(self.root)['ok'])
        self.assertEqual(c.load(self.root/'gallery.json')['entries'][0]['availability'],'unavailable')

    def test_batch_listing_finds_dated_attempts_and_isolates_a_missing_journal(self):
        redo = self.redo()
        listing = batch.list_batches(self.root, limit=1)
        self.assertEqual(listing['total'], 2)
        self.assertEqual(listing['next_offset'], 1)
        self.assertEqual(listing['entries'][0]['batch_id'], redo['batch_id'])
        (self.root/'batch.json').unlink()
        old = batch.list_batches(self.root, limit=1, offset=1)
        self.assertEqual(old['entries'][0]['availability'], 'unavailable')
        self.assertEqual(batch.advance(self.root, redo['state'], grant='fixture-grant')['exit_code'], 3)

    def test_damaged_required_series_predecessor_still_blocks_without_sending(self):
        first = self.execute()
        (workflow.run_dir(self.root, first['panels']['canon.primary']['run'])/'manifest.json').unlink()
        redo = self.redo()
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('never bypass required evidence')) as send:
            result = batch.advance(self.root, redo['state'], grant='fixture-grant')
        self.assertEqual(result['panels']['canon.primary']['status'], 'blocked')
        self.assertEqual(send.call_count, 0)
        self.assertIn('required', str(result['panels']['canon.primary']['diagnostic']).lower())

    def test_prepare_commit_followed_by_lost_response_reuses_reserved_run(self):
        original=workflow.prepare
        def lose_response(*args,**kwargs):
            original(*args,**kwargs)
            raise OSError('synthetic loss after durable prepare')
        with patch.object(workflow,'prepare',side_effect=lose_response):
            failed=batch.advance(self.root,'batch.json',grant='fixture-grant')
        identity=failed['panels']['canon.primary']['run']
        self.assertTrue((workflow.run_dir(self.root,identity)/'manifest.json').exists())
        with patch.object(workflow,'prepare',side_effect=AssertionError('do not prepare another run')):
            resumed=batch.advance(self.root,'batch.json',grant='fixture-grant')
        self.assertEqual(resumed['panels']['canon.primary']['run'],identity)
        self.assertEqual(resumed['exit_code'],3,resumed)

    def test_existing_review_draft_is_pointed_to_instead_of_recreated(self):
        result=self.execute(); run=result['panels']['canon.primary']['run']
        status=execution.status(self.root,run)
        report=status['runs'][0] if 'runs' in status else status
        action=report['next_action']
        self.assertIn(run,action['draft'])
        candidate=report['candidates'][0]
        path=self.root/action['draft']; c.atomic(path,c.encoded(workflow.draft_review(self.root,run,candidate)))
        after=execution.status(self.root,run)
        report=after['runs'][0] if 'runs' in after else after
        follow=report['next_action']
        self.assertEqual(follow['draft'],action['draft'])
        self.assertTrue(follow['requires_author_input'])
        self.assertNotIn('draft-review',follow['command'])
        self.assertIn('--file',follow['argv'])

    def test_formal_not_selected_is_projected_without_deleting_candidate(self):
        result=self.execute(); entry=result['panels']['canon.primary']
        row=studio.read_iterations(studio.character_home(self.root,'robot'))[0]
        self.assertEqual(row['status'],'candidate')
        studio.reject(self.root,'robot',row['iteration_id'],'Synthetic author declines this candidate.',actor='Synthetic author')
        report=sheet_inventory.status(self.sheet,state_filter='candidate',disposition='not_selected')
        self.assertEqual(report['total'],1)
        self.assertEqual(report['entries'][0]['artifact_id'],entry['artifact']['artifact_id'])
        self.assertEqual(c.load(self.root/'gallery.json')['entries'][0]['disposition'],'not_selected')
        self.assertEqual(len(c.load(self.sheet)['slots']['canon.primary']['candidates']),1)


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
