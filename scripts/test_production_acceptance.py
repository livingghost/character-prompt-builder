"""Existing-image acceptance and task closure use only synthetic local evidence."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

import adoption_workflow
import execution_contract as c
import execution_lifecycle as lifecycle
import production_acceptance as acceptance
import production_case_fixtures as fixtures
import production_execution as execution
import production_store as store
import production_workflow as workflow
import studio
import studio_activity
import validate_studio
import test_production_review as review_cases
import transport_synthetic
import work_ledger as work
from production_diagnostics import ProductionError


class AcceptanceTests(review_cases.ReviewCase):
    def author_choice(self, *, discrepancy: bool = True) -> tuple[dict, dict]:
        review = self.record_review([('output', 'pass'), ('palette', 'fail' if discrepancy else 'pass')])
        decisions = acceptance.draft(self.root, self.run, self.candidate, 'fixture-grant')
        decisions['reason'] = 'The synthetic author chooses this existing scene image.'
        if discrepancy:
            fixtures.write(self.root / 'owner-choice.txt',
                'Synthetic instruction: accept this exact image in its scene slot with the recorded palette discrepancy. '
                'This is fixture evidence, not actual user consent.')
            decisions['owner_acceptance'] = {
                'evidence': {'path': 'owner-choice.txt', 'locator': 'whole'},
                'criteria': ['palette'], 'unresolved_indices': [0],
                'reason': 'The synthetic owner explicitly tolerates the observed palette discrepancy for this image.'}
        fixtures.write(self.root / 'acceptance.json', decisions)
        return review, decisions

    def accept(self, *, supplied: bool = True):
        return acceptance.accept(self.root, self.run, decision_file='acceptance.json' if supplied else None)

    def events(self):
        return store.event_rows(self.root, self.run)

    def finish_steps(self):
        for step in work.require_open(self.root)['steps']:
            if not step['done_at']:
                work.step_done(self.root, step['n'])

    def imported(self):
        source = self.root / self.row(self.candidate)['result']['path']
        return studio.iterate(self.root, 'robot', 'candidate', source,
            package=None, request=None, response=None, note='A separately imported synthetic image.')

    def assert_one_acceptance(self):
        rows = self.events()
        for event in ('selection', 'slot-acceptance', 'completion'):
            self.assertEqual(sum(row['event'] == event for row in rows), 1, event)
        row = self.row(self.candidate)
        self.assertEqual(len(row['acceptances']), 1)
        self.assertEqual(row['status'], 'accepted')
        return row

    def test_compact_owner_acceptance_preserves_review_and_original_ownership(self):
        review, decisions = self.author_choice()
        before = {'runs': len(store.runs(self.root)), 'tasks': len(list((self.root / 'work/tasks').iterdir())),
                  'iterations': len(studio.read_iterations(self.home)),
                  'candidates': sum(row['event'] == 'candidate' for row in self.events()),
                  'submissions': lifecycle.summary(self.root)['submissions']}
        sheet = (self.home / 'sheet/sheet-data.json').read_bytes()
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Acceptance must not send')):
            result = self.accept()
        row = self.assert_one_acceptance()
        self.assertEqual(result['run'], self.run)
        self.assertEqual(row['production'], {'run': self.run, 'candidate': self.candidate})
        self.assertEqual((row['evaluation'], row['selection_basis']), ('nonconforming', 'owner-allowance'))
        self.assertEqual(workflow.latest_review(self.events(), self.candidate), review)
        self.assertEqual((self.home / 'sheet/sheet-data.json').read_bytes(), sheet)
        self.assertFalse((self.home / 'adoptions').exists())
        self.assertEqual(before, {'runs': len(store.runs(self.root)), 'tasks': len(list((self.root / 'work/tasks').iterdir())),
                  'iterations': len(studio.read_iterations(self.home)),
                  'candidates': sum(item['event'] == 'candidate' for item in self.events()),
                  'submissions': lifecycle.summary(self.root)['submissions']})
        self.assertEqual(work.require_open(self.root)['task_id'], result['task_id'])
        self.assertTrue(all(step['done_at'] is None for step in work.require_open(self.root)['steps']))
        self.assertNotIn('selector', decisions)
        self.assertNotIn('authorization', decisions)
        self.assertNotIn('sha256', decisions['owner_acceptance']['evidence'])
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_draft_is_read_only_and_never_supplies_an_allowance(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        before = self.events()
        draft = acceptance.draft(self.root, self.run, self.candidate, 'fixture-grant')
        self.assertEqual(self.events(), before)
        self.assertIsNone(draft['owner_acceptance'])
        self.assertEqual(draft['reason'], '')
        self.assertIsNone(draft['expected_slot'])

    def test_unassessed_hard_criterion_cannot_be_accepted_as_an_observed_discrepancy(self):
        _, choices = self.author_choice()
        review = self.record_review([('output', 'pass'), ('palette', 'not-assessed')])
        choices['review'] = review['sha256']
        choices['owner_acceptance']['unresolved_indices'] = []
        fixtures.write(self.root / 'acceptance.json', choices)
        with self.assertRaises(ValueError):
            self.accept()
        self.assertFalse(any(row['event'] in {'selection', 'slot-acceptance', 'completion'} for row in self.events()))

    def test_new_review_invalidates_the_draft_without_rebinding_its_choices(self):
        self.author_choice()
        self.record_review([('output', 'pass'), ('palette', 'indeterminate')])
        with self.assertRaises(ProductionError):
            self.accept()
        self.assertFalse(any(row['event'] == 'selection' for row in self.events()))

    def test_selection_commit_is_recovered_from_saved_owner_evidence(self):
        self.author_choice()
        with patch.object(studio, 'accept', side_effect=OSError('Synthetic stop before slot write')):
            with self.assertRaises(OSError):
                self.accept()
        report = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual(report['next_action']['command'], 'accept')
        self.assertFalse(any(row['event'] == 'completion' for row in self.events()))
        (self.root / 'owner-choice.txt').unlink()
        (self.root / 'acceptance.json').unlink()
        fixtures.write(self.root / 'prompt.txt', 'A later live prompt is unrelated to saved artifact recovery.')
        self.accept(supplied=False)
        self.assert_one_acceptance()

    def test_copy_then_ledger_interruption_recovers_one_acceptance(self):
        self.author_choice(discrepancy=False)
        with patch.object(studio, 'write_iterations', side_effect=OSError('Synthetic interruption after slot copy')):
            with self.assertRaises(OSError):
                self.accept()
        self.assertEqual(len(self.row(self.candidate)['acceptances']), 0)
        self.accept(supplied=False)
        self.assert_one_acceptance()

    def test_abandoned_pending_acceptance_starts_no_slot_effect(self):
        self.author_choice()
        with patch.object(studio, 'accept', side_effect=OSError('Synthetic stop before slot write')):
            with self.assertRaises(OSError):
                self.accept()
        work.abandon(self.root, 'Synthetic owner stops this pending acceptance.', actor='Synthetic fixture owner')
        before = self.events()
        with self.assertRaises(ProductionError) as caught:
            self.accept(supplied=False)
        self.assertEqual(caught.exception.diagnostic.code, 'TASK_ABANDONED')
        self.assertEqual(self.events(), before)
        self.assertEqual(self.row(self.candidate)['acceptances'], [])
        self.assertIsNone(studio.acceptance_state(self.root, 'robot', 'candidate'))

    def test_saved_studio_receipt_recovers_missing_production_result(self):
        self.author_choice()
        original = workflow.append_record
        def interrupted(directory, prepared, rows, event, data):
            if event == 'slot-acceptance':
                raise OSError('Synthetic interruption after the Studio receipt')
            return original(directory, prepared, rows, event, data)
        with patch.object(workflow, 'append_record', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.accept()
        self.assertEqual(len(self.row(self.candidate)['acceptances']), 1)
        self.assertEqual(validate_studio.validate(self.root), [])
        self.accept(supplied=False)
        self.assert_one_acceptance()

    def test_result_commit_recovers_completion_and_completed_retry_is_identical(self):
        self.author_choice(discrepancy=False)
        with patch.object(workflow, 'complete', side_effect=OSError('Synthetic interruption before completion')):
            with self.assertRaises(OSError):
                self.accept()
        first = self.accept(supplied=False)
        second = self.accept()
        self.assertEqual(first, second)
        self.assert_one_acceptance()

    def test_intervening_acceptance_prevents_recovery_from_replacing_newer_choice(self):
        self.author_choice()
        with patch.object(studio, 'accept', side_effect=OSError('Synthetic stop before slot write')):
            with self.assertRaises(OSError):
                self.accept()
        other = self.imported()
        studio.accept(self.root, 'robot', other['iteration_id'])
        report = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual(report['next_action']['command'], 'draft-acceptance')
        with self.assertRaises(ProductionError) as caught:
            self.accept(supplied=False)
        self.assertEqual(caught.exception.diagnostic.code, 'SLOT_ACCEPTANCE_CONFLICT')
        self.assertEqual(studio.acceptance_state(self.root, 'robot', 'candidate')['iteration_id'], other['iteration_id'])
        self.assertFalse(any(row['event'] == 'completion' for row in self.events()))

    def test_corrupt_accepted_copy_is_not_interpreted_as_success(self):
        self.author_choice()
        with patch.object(workflow, 'complete', side_effect=OSError('Synthetic interruption before completion')):
            with self.assertRaises(OSError):
                self.accept()
        row = self.row(self.candidate)
        (self.root / row['accepted_path']).write_bytes(b'not the accepted image')
        with self.assertRaises(ValueError):
            self.accept(supplied=False)
        self.assertFalse(any(event['event'] == 'completion' for event in self.events()))

    def test_normal_later_supersession_preserves_historical_completion(self):
        self.author_choice()
        first = self.accept()
        other = self.imported()
        studio.accept(self.root, 'robot', other['iteration_id'])
        before = studio.acceptance_state(self.root, 'robot', 'candidate')
        self.assertEqual(self.accept(supplied=False), first)
        self.assertEqual(studio.acceptance_state(self.root, 'robot', 'candidate'), before)
        done = workflow.verify_completion(self.root, self.run, first['task_id'])
        self.assertEqual(done['sha256'], first['completion'])
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_direct_reaccept_keeps_prior_completed_receipt_unique_and_verifiable(self):
        self.author_choice()
        first = self.accept()
        other = self.imported()
        studio.accept(self.root, 'robot', other['iteration_id'])
        restored = studio.accept(self.root, 'robot', self.iteration)
        self.assertEqual(restored['status'], 'accepted')
        self.assertEqual(len(restored['acceptances']), 2)
        self.assertNotIn('production_selection', restored['acceptances'][-1])
        self.assertEqual(sum(item.get('production_selection') == first['selection']
                             for item in restored['acceptances']), 1)
        self.assertEqual(workflow.verify_completion(self.root, self.run, first['task_id'])['sha256'], first['completion'])
        self.assertEqual(self.accept(supplied=False), first)
        self.assertEqual(len(self.row(self.candidate)['acceptances']), 2)
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_committed_slot_projection_warning_remains_in_acceptance_result(self):
        self.author_choice(discrepancy=False)
        original = studio_activity.changed
        warning = {'ok': False, 'message': 'Synthetic accepted-slot projection interruption'}
        def changed(path, event, **kwargs):
            return warning if event == 'iteration-accepted' else original(path, event, **kwargs)
        with patch.object(studio_activity, 'changed', side_effect=changed):
            result = self.accept()
        self.assertIn(warning, result['projection_warnings'])
        self.assert_one_acceptance()

    def test_finish_uses_chosen_run_and_retains_an_unrelated_active_task(self):
        self.author_choice()
        later = workflow.prepare(self.root, 'task.json')['run']
        self.assertEqual(work.require_open(self.root)['production_run'], later)
        result = self.accept()
        with self.assertRaisesRegex(ValueError, 'not done'):
            work.finish(self.root, self.run)
        self.finish_steps()
        work.suspend(self.root, reason='Synthetic switching to other work before closing the accepted result.')
        other = work.begin(self.root, 'Unrelated synthetic work', ['Do unrelated work'])
        closed = work.finish(self.root, self.run)
        self.assertEqual(closed['task_id'], result['task_id'])
        self.assertEqual(closed['production_run'], self.run)
        self.assertEqual(work.require_open(self.root), other)
        self.assertEqual(work.finish(self.root, self.run), closed)
        self.assertEqual(len([entry for entry in work.read_ledger(self.root) if entry['event'] == 'finished']), 1)

    def test_finish_recovers_after_durable_task_save_and_pointer_removal(self):
        self.author_choice(discrepancy=False)
        self.accept()
        self.finish_steps()
        original = work.write_current
        def interrupted(root, value):
            if value is None:
                raise OSError('Synthetic interruption before current pointer removal')
            return original(root, value)
        with patch.object(work, 'write_current', side_effect=interrupted):
            with self.assertRaises(OSError):
                work.finish(self.root, self.run)
        first = work.finish(self.root, self.run)
        self.assertIsNone(work.read_current(self.root))
        self.assertEqual(work.finish(self.root, self.run), first)
        self.assertEqual(len([entry for entry in work.read_ledger(self.root) if entry['event'] == 'finished']), 1)

    def test_production_adoption_preflight_refuses_imported_bytes_without_a_claim(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        imported = self.imported()
        approval = {'scope': 'sheet', 'influence': 'pose-camera', 'character': 'robot',
                    'iteration_id': imported['iteration_id'], 'slot': imported['slot'],
                    'image_sha256': imported['result']['sha256'], 'by': 'Synthetic fixture owner',
                    'at': '2000-01-01T00:00:00Z'}
        before = self.events()
        with self.assertRaises(ProductionError) as caught:
            workflow.adoption_intent(self.root, self.run, self.candidate, 'robot', imported['iteration_id'], approval)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_OWNER_MISMATCH')
        self.assertEqual(self.events(), before)
        accepted = studio.accept(self.root, 'robot', imported['iteration_id'])
        self.assertEqual(studio.accept(self.root, 'robot', imported['iteration_id']), accepted)
        self.assertEqual(len(accepted['acceptances']), 1)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
