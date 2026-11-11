"""Existing-image acceptance and task closure use only synthetic local evidence."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

import adoption_workflow
import execution_contract as c
import execution_lifecycle as lifecycle
import production_acceptance as acceptance
import production_case_fixtures as fixtures
import production_fixtures as fixture
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
        decisions = acceptance.draft(self.root, self.run, self.candidate, 'fixture-grant', scope='studio-slot')
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
        draft = acceptance.draft(self.root, self.run, self.candidate, 'fixture-grant', scope='studio-slot')
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
        _, decisions = self.author_choice()
        latest = self.record_review([('output', 'pass'), ('palette', 'indeterminate')])
        with self.assertRaises(ProductionError) as caught:
            self.accept()
        diagnostic = caught.exception.diagnostic.as_dict()
        self.assertEqual((diagnostic['code'], diagnostic['pointer'], diagnostic['expected'], diagnostic['actual']),
                         ('SELECTION_REVIEW_CHANGED', '$.review', latest['sha256'], decisions['review']))
        self.assertIn(f'draft-acceptance --run {self.run} --candidate {self.candidate} --scope studio-slot '
                      '--grant fixture-grant --out FILE', diagnostic['required_action'])
        self.assertFalse(any(row['event'] == 'selection' for row in self.events()))

    def test_selection_recorded_during_the_slot_acceptance_names_both_continuations(self):
        self.author_choice(discrepancy=False)
        original = studio.accept
        def newer_selection_first(*args, **kwargs):
            choice = workflow.draft_selection(self.root, self.run, self.candidate)
            choice['reason'] = 'Another synthetic delivery decision recorded meanwhile.'
            fixture.selection(self.root, self.run, choice)
            fixtures.write(self.root / 'meanwhile.json', choice)
            workflow.select(self.root, self.run, 'meanwhile.json')
            return original(*args, **kwargs)
        with patch.object(studio, 'accept', side_effect=newer_selection_first):
            with self.assertRaises(ProductionError) as caught:
                self.accept()
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, 'SLOT_ACCEPTANCE_MISMATCH')
        for part in ('status --run ' + self.run, 'accept --run ' + self.run + ' to ',
                     'accept --run ' + self.run + ' --file FILE'):
            self.assertIn(part, diagnostic.required_action)
        self.assertEqual(self.row(self.candidate)['acceptances'], [])
        result = self.accept()
        selections = [row for row in self.events() if row['event'] == 'selection']
        self.assertEqual([row['data']['selection']['replaces'] for row in selections],
                         [None, selections[0]['sha256'], selections[1]['sha256']])
        self.assertEqual((result['selection'], result['scope']), (selections[2]['sha256'], 'studio-slot'))
        self.assertEqual(self.row(self.candidate)['acceptances'][0]['production_selection'], result['selection'])

    def test_slot_acceptance_of_an_iteration_without_its_production_origin_names_its_line(self):
        self.author_choice(discrepancy=False)
        with patch.object(studio, 'accept', side_effect=OSError('Synthetic stop before slot write')):
            with self.assertRaises(OSError):
                self.accept()
        rows = studio.read_iteration_records(self.home)
        next(row for row in rows if row['iteration_id'] == self.iteration).pop('production')
        studio.write_iterations(self.home, rows)
        with self.assertRaises(ProductionError) as caught:
            self.accept(supplied=False)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, 'SLOT_ACCEPTANCE_MISMATCH')
        self.assertIn(self.iteration, diagnostic.message)
        self.assertIn('characters/robot/iterations.jsonl', diagnostic.required_action)
        self.assertNotIn('accept --run', diagnostic.required_action)

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


class DeliveryAcceptanceTests(review_cases.ReviewCase):
    """The common decision owner completes delivery without requiring Studio adoption."""

    def choice(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        value = acceptance.draft(self.root, self.run, self.candidate)
        value['reason'] = 'The synthetic owner selects this reviewed result for delivery.'
        fixtures.write(self.root / 'delivery-choice.json', value)
        return value

    def apply(self, supplied=True):
        return acceptance.accept(self.root, self.run,
                                 decision_file='delivery-choice.json' if supplied else None)

    def import_authority(self, authority):
        fixtures.write(self.root / 'changed-authority.json', authority)
        task_id = workflow.read_run(self.root, self.run).prepared['task']['task_id']
        return store.import_authority(self.root, 'changed-authority.json',
                                      expected=store.authority_record(self.root, task_id)['sha256'])

    def authority(self):
        prepared = workflow.read_run(self.root, self.run).prepared
        return copy.deepcopy(workflow.current_authority(self.root, prepared).document)

    def test_common_delivery_decision_uses_current_grant_and_exposes_remaining_work(self):
        choice = self.choice()
        self.assertEqual(choice['scope'], 'delivery-only')
        self.assertEqual(choice['grant'], 'fixture-grant')
        self.assertNotIn('expected_slot', choice)
        before = studio.read_iterations(self.home, project=False)
        with patch.object(studio, 'accept', side_effect=AssertionError('Delivery has no slot effect')):
            result = self.apply()
        rows = store.event_rows(self.root, self.run)
        selected = workflow.find(rows, 'selection')
        request = workflow.find(rows, 'authorization', selected['data']['selection']['authorization'])
        self.assertEqual(selected['data']['selection']['scope'], 'delivery-only')
        self.assertEqual(request['data']['request']['payload']['reason'], choice['reason'])
        self.assertEqual(request['data']['request']['actor'], fixture.ACTOR)
        self.assertEqual(result['scope'], 'delivery-only')
        self.assertEqual(result['work']['work_state'], 'active')
        self.assertFalse(result['work']['ready_to_finish'])
        self.assertFalse(result['work']['finished'])
        self.assertTrue(result['work']['incomplete_steps'])
        self.assertNotIn('slot_acceptance', result)
        self.assertFalse(any(row['event'] == 'slot-acceptance' for row in rows))
        self.assertEqual(studio.read_iterations(self.home, project=False), before)
        self.assertEqual(workflow.verify_completion(self.root, self.run, result['task_id'])['sha256'], result['completion'])

    def test_changed_selected_grant_refuses_silent_rebinding(self):
        self.choice()
        changed = self.authority()
        changed['grants'][0]['actor'] = 'Another synthetic authorized actor'
        self.import_authority(changed)
        before = store.event_rows(self.root, self.run)
        self.assertCode('ACCEPTANCE_AUTHORITY_CHANGED', self.apply)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_revoked_or_narrowed_grant_blocks_the_actual_decision(self):
        self.choice()
        original = self.authority()
        for update, code in (({'revoked_at': '2000-01-01T00:00:00Z'}, 'GRANT_REVOKED'),
                             ({'targets': ['purpose']}, 'GRANT_SCOPE_EXCEEDED')):
            with self.subTest(update=update):
                changed = copy.deepcopy(original)
                changed['grants'][0].update(update)
                self.import_authority(changed)
                before = store.event_rows(self.root, self.run)
                self.assertCode(code, self.apply)
                self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_unrelated_grant_change_keeps_the_existing_authored_decision(self):
        choice = self.choice()
        changed = self.authority()
        changed['grants'][0]['targets'].append('canon:catalog')
        changed['grants'][0]['protected_criteria'] = ['palette']
        changed['grants'].append({**copy.deepcopy(changed['grants'][0]), 'id': 'other-work',
                                  'operations': ['select'], 'targets': ['delivery'],
                                  'submission_validation_modes': []})
        imported = self.import_authority(changed)
        self.assertCode('AUTHORIZATION_REQUIRED',
                        lambda: acceptance.draft(self.root, self.run, self.candidate))
        result = self.apply()
        rows = store.event_rows(self.root, self.run)
        selected = workflow.find(rows, 'selection', result['selection'])
        authorization = workflow.find(rows, 'authorization', selected['data']['selection']['authorization'])
        self.assertEqual(authorization['data']['authority']['event'], imported['sha256'])
        self.assertEqual(selected['data']['selection']['reason'], choice['reason'])

    def test_changed_source_instruction_requires_a_current_decision(self):
        self.choice()
        changed = self.authority()
        fixtures.write(self.root / changed['evidence']['path'],
                       'Different synthetic owner instruction behind the same declared grant terms.')
        self.import_authority(changed)
        before = store.event_rows(self.root, self.run)
        self.assertCode('ACCEPTANCE_AUTHORITY_CHANGED', self.apply)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_stop_definition_change_requires_current_assessment(self):
        changed = self.authority()
        changed['stop_conditions'] = [{'id': 'condition', 'text': 'Synthetic condition at drafting.'}]
        self.import_authority(changed)
        choice = self.choice()
        self.assertEqual(choice['stop_assessments'], [{'id': 'condition', 'clear': False, 'evidence': ''}])
        choice['stop_assessments'][0].update(clear=True, evidence='Synthetic explicit assessment of the first definition.')
        fixtures.write(self.root / 'delivery-choice.json', choice)
        changed['stop_conditions'][0]['text'] = 'A different synthetic condition requiring a new judgment.'
        self.import_authority(changed)
        self.assertCode('ACCEPTANCE_AUTHORITY_CHANGED', self.apply)
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))

    def test_recovery_after_selection_uses_saved_evidence_without_another_decision(self):
        self.choice()
        with patch.object(workflow, 'complete', side_effect=OSError('Synthetic stop after delivery selection')):
            with self.assertRaises(OSError):
                self.apply()
        selected = workflow.find(store.event_rows(self.root, self.run), 'selection')
        (self.root / 'delivery-choice.json').unlink()
        (self.root / 'prompt.txt').unlink()
        changed = self.authority()
        changed['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        self.import_authority(changed)
        first = self.apply(supplied=False)
        second = self.apply(supplied=False)
        self.assertEqual(first, second)
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([row['sha256'] for row in rows if row['event'] == 'selection'], [selected['sha256']])
        self.assertEqual(sum(row['event'] == 'completion' for row in rows), 1)

    def decided(self, path: str, reason: str) -> str:
        value = acceptance.draft(self.root, self.run, self.candidate)
        value['reason'] = reason
        fixtures.write(self.root / path, value)
        return path

    def interrupted(self, path: str) -> None:
        with patch.object(workflow, 'complete', side_effect=OSError('Synthetic stop after the selection commit')):
            with self.assertRaises(OSError):
                acceptance.accept(self.root, self.run, decision_file=path)

    def test_earlier_decision_applied_again_replaces_the_current_selection(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        first = self.decided('first-choice.json', 'The synthetic owner selects this reviewed result for delivery.')
        self.interrupted(first)
        self.interrupted(self.decided('second-choice.json', 'The synthetic owner selects it for another stated reason.'))
        result = acceptance.accept(self.root, self.run, decision_file=first)
        rows = store.event_rows(self.root, self.run)
        selections = [row for row in rows if row['event'] == 'selection']
        self.assertEqual([row['data']['selection']['replaces'] for row in selections],
                         [None, selections[0]['sha256'], selections[1]['sha256']])
        self.assertEqual(result['selection'], selections[2]['sha256'])
        self.assertEqual(selections[2]['data']['files'], selections[0]['data']['files'])
        self.assertEqual(workflow.candidate_state(self.root, self.run, self.candidate)['decision'], result['selection'])
        authorizations = [workflow.find(rows, 'authorization', row['data']['selection']['authorization'])
                          for row in selections]
        self.assertEqual(len({row['sha256'] for row in authorizations}), 3)
        self.assertEqual(authorizations[2]['data']['request']['payload']['replaces'], selections[1]['sha256'])
        self.assertEqual(workflow.verify_completion(self.root, self.run, result['task_id'])['data']['selection'],
                         result['selection'])
        self.assertEqual(acceptance.accept(self.root, self.run, decision_file=first), result)
        self.assertEqual(store.event_rows(self.root, self.run), rows)

    def test_decision_applied_again_after_its_withdrawal_records_a_new_selection(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        choice = self.decided('withdrawn-choice.json', 'The synthetic owner selects this reviewed result for delivery.')
        self.interrupted(choice)
        value = workflow.draft_disposition(self.root, self.run, self.candidate)
        value.update(disposition='pending', actor='Synthetic fixture selector',
                     reason='The synthetic owner reconsiders this selection.')
        fixtures.write(self.root / 'disposition.json', value)
        workflow.disposition(self.root, self.run, 'disposition.json')
        self.assertCode('SELECTION_WITHDRAWN', lambda: self.apply(supplied=False))
        result = acceptance.accept(self.root, self.run, decision_file=choice)
        selections = [row for row in store.event_rows(self.root, self.run) if row['event'] == 'selection']
        self.assertEqual([row['data']['selection']['replaces'] for row in selections], [None, selections[0]['sha256']])
        self.assertEqual(result['selection'], selections[1]['sha256'])

    def test_decision_applied_again_after_a_newer_review_names_a_new_draft(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        first = self.decided('first-choice.json', 'The synthetic owner selects this reviewed result for delivery.')
        self.interrupted(first)
        second = self.decided('second-choice.json', 'The synthetic owner selects it for another stated reason.')
        self.interrupted(second)
        newer = self.review_data([('output', 'pass'), ('palette', 'pass')])
        newer['conclusion'] = 'A second synthetic review of the same candidate.'
        fixtures.write(self.root / 'review.json', newer)
        latest = workflow.review(self.root, self.run, 'review.json')
        before = store.event_rows(self.root, self.run)
        for path in (first, second):
            with self.subTest(path=path), self.assertRaises(ProductionError) as caught:
                acceptance.accept(self.root, self.run, decision_file=path)
            diagnostic = caught.exception.diagnostic.as_dict()
            self.assertEqual((diagnostic['code'], diagnostic['expected'], diagnostic['actual']),
                             ('SELECTION_REVIEW_CHANGED', latest['sha256'], c.load(self.root / path)['review']))
            self.assertIn(f'draft-acceptance --run {self.run} --candidate {self.candidate} --scope delivery-only '
                          '--grant fixture-grant --out FILE', diagnostic['required_action'])
        self.assertEqual(store.event_rows(self.root, self.run), before)
        result = acceptance.accept(self.root, self.run, decision_file=self.decided(
            'current-choice.json', 'The synthetic owner selects it against its latest review.'))
        rows = store.event_rows(self.root, self.run)
        self.assertEqual(workflow.find(rows, 'selection', result['selection'])['data']['selection']['review'], latest['sha256'])
        self.assertEqual(workflow.verify_completion(self.root, self.run, result['task_id'])['sha256'], result['completion'])

    def test_completed_delivery_retains_its_result_after_later_disposition_and_source_edit(self):
        self.choice()
        first = self.apply()
        self.not_selected()
        fixtures.write(self.root / 'prompt.txt', 'A later creative revision has different instructions.')
        second = self.apply(supplied=False)
        self.assertEqual(second['selection'], first['selection'])
        self.assertEqual(second['completion'], first['completion'])
        self.assertEqual(workflow.candidate_state(self.root, self.run, self.candidate)['disposition'], 'not_selected')
        self.assertEqual(workflow.verify_completion(self.root, self.run, first['task_id'])['sha256'], first['completion'])

    def test_finish_state_uses_actual_work_questions_and_exact_task_owner(self):
        self.choice()
        result = self.apply()
        for step in work.require_open(self.root)['steps']:
            work.step_done(self.root, step['n'])
        work.block(self.root, 'Synthetic unanswered delivery question.')
        state = work.finish_state(self.root, self.run)
        self.assertEqual(state['incomplete_steps'], [])
        self.assertEqual(len(state['open_questions']), 1)
        self.assertFalse(state['ready_to_finish'])
        with self.assertRaisesRegex(ValueError, 'open author questions'):
            work.finish(self.root, self.run)
        work.respond(self.root, state['open_questions'][0]['question_id'], 'Synthetic owner answer.', actor=fixture.ACTOR)
        work.suspend(self.root, reason='Synthetic switch before finishing the chosen result.')
        other = work.begin(self.root, 'Other synthetic work', ['An unrelated step'])
        ready = work.finish_state(self.root, self.run)
        self.assertTrue(ready['ready_to_finish'])
        self.assertEqual(ready['work_state'], 'suspended')
        self.assertEqual(work.require_open(self.root), other)
        closed = work.finish(self.root, self.run)
        state = work.finish_state(self.root, self.run)
        self.assertTrue(state['finished'])
        self.assertFalse(state['ready_to_finish'])
        self.assertEqual(closed['task_id'], result['task_id'])
        self.assertEqual(work.require_open(self.root), other)

    def test_public_delivery_commands_need_no_transcribed_intent_or_authorization(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')])
        script = str(Path(workflow.__file__))
        def call(*args):
            completed = subprocess.run([sys.executable, script, *args, '--root', str(self.root), '--run', self.run],
                cwd=self.root.parent, capture_output=True, text=True, encoding='utf-8', timeout=120,
                env=os.environ.copy())
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            return json.loads(completed.stdout)
        draft = call('draft-acceptance', '--candidate', self.candidate, '--out', 'cli-choice.json')
        self.assertEqual(draft['scope'], 'delivery-only')
        value = c.load(self.root / 'cli-choice.json')
        value['reason'] = 'Synthetic explicit choice through the public delivery command.'
        fixtures.write(self.root / 'cli-choice.json', value)
        result = call('accept', '--file', 'cli-choice.json')
        self.assertEqual(result['scope'], 'delivery-only')
        self.assertEqual(call('accept')['completion'], result['completion'])


class RepeatedDecisionStatusTests(review_cases.ReviewCase):
    """Status continues a saved decision after another candidate's selection."""
    count = 2

    def options(self) -> dict:
        action = execution.status(self.root, self.run)['runs'][0]['next_action']
        actions = action['alternatives'] if action['command'] == 'status' else [action]
        return {item['read_context'][0]['argv'][-1]: item for item in actions}

    def cli(self, argv: list[str]) -> dict:
        completed = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, encoding='utf-8',
                                   timeout=120, env=os.environ.copy())
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def decide(self, candidate: str) -> str:
        """Follow the draft action status offers, then stop the acceptance after its selection commit."""
        action = self.options()[candidate]
        self.assertEqual(action['command'], 'draft-acceptance')
        self.cli(action['argv'])
        value = c.load(self.root / action['draft'])
        value['reason'] = 'The synthetic owner selects this reviewed candidate for delivery.'
        fixtures.write(self.root / action['draft'], value)
        with patch.object(workflow, 'complete', side_effect=OSError('Synthetic stop after the selection commit')):
            with self.assertRaises(OSError):
                acceptance.accept(self.root, self.run, decision_file=action['draft'])
        return action['draft']

    def withdraw(self, candidate: str, disposition: str) -> None:
        value = workflow.draft_disposition(self.root, self.run, candidate)
        value.update(disposition=disposition, actor='Synthetic fixture selector',
                     reason='The synthetic owner reconsiders this selection.')
        fixtures.write(self.root / 'disposition.json', value)
        workflow.disposition(self.root, self.run, 'disposition.json')

    def test_status_action_for_the_first_candidate_records_a_new_selection(self):
        first, second = self.candidates
        for candidate in self.candidates:
            self.record_review([('output', 'pass'), ('palette', 'pass')], candidate)
        earlier = self.decide(first)
        self.withdraw(first, 'pending')
        self.decide(second)
        self.withdraw(second, 'not_selected')
        action = self.options()[first]
        self.assertEqual((action['command'], action['draft']), ('accept', earlier))
        result = self.cli(action['argv'])
        rows = store.event_rows(self.root, self.run)
        selections = [row for row in rows if row['event'] == 'selection']
        self.assertEqual([row['data']['selection']['candidate'] for row in selections], [first, second, first])
        self.assertEqual(selections[2]['data']['selection']['replaces'], selections[1]['sha256'])
        self.assertEqual((result['selection'], result['completion']),
                         (selections[2]['sha256'], workflow.find(rows, 'completion')['sha256']))


class TextAcceptanceTests(unittest.TestCase):
    """An externally supplied text result uses the same reviewed delivery owner."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'studio'
        self.root.mkdir()
        self.enterContext(fixture.scratch_home(Path(temporary.name) / 'home'))
        task = work.begin(self.root, 'Select a synthetic supplied text.', ['Assess and deliver the text.'])
        self.task_id = task['task_id']
        spec = {'task_id': self.task_id, 'route': 'development', 'features': [], 'sources': [],
                'delivery': {'path': 'instructions.txt', 'translation_notes': 'Synthetic literal text.'},
                'criteria': [{'id': 'content', 'strength': 'hard', 'text': 'The text describes one lamp.'}],
                'world_views': []}
        fixture.task(self.root, spec, artifact='text', execution='external')
        fixtures.write(self.root / 'instructions.txt', 'Describe one lamp.')
        fixtures.write(self.root / 'task.json', spec)
        self.run = workflow.prepare(self.root, 'task.json')['run']
        fixture.handoff(self.root, self.run, 'Synthetic delegated text author', 'manual')
        token = fixture.grant(self.root, self.run, workflow.external_intent(self.root, self.run, 1))
        workflow.claim_external(self.root, self.run, 1, token)
        fixtures.write(self.root / 'text-result.txt', 'One lamp lights a table.')
        captured = workflow.capture(self.root, self.run, 'text-result.txt', 'Synthetic supplied text result.')
        self.candidate = captured['sha256']
        fixtures.write(self.root / 'host-receipt.json', {'synthetic': True, 'status': 'received'})
        workflow.receive_external(self.root, self.run, response_file='host-receipt.json',
                                  artifacts=['text-result.txt'], final=True,
                                  reason='Synthetic text delivery was received.')
        review = workflow.draft_review(self.root, self.run, self.candidate)
        review.update(reviewer=fixture.ACTOR, observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
            'observation': 'The synthetic text names one lamp lighting a table.',
            'interpretation': 'The text covers the synthetic requested subject.',
            'limitations': ['No image or provider quality is assessed.']}],
            checks=[{'criterion': 'content', 'verdict': 'pass', 'observation_indices': [0],
                     'reason': 'An explicit synthetic assessment of the supplied sentence.'}],
            conclusion='Synthetic text assessment.', unresolved=[])
        fixtures.write(self.root / 'text-review.json', review)
        workflow.review(self.root, self.run, 'text-review.json')

    def test_text_delivery_finishes_without_image_or_studio_slot_fields(self):
        choice = acceptance.draft(self.root, self.run, self.candidate)
        choice['reason'] = 'The synthetic owner chooses this reviewed sentence for delivery.'
        fixtures.write(self.root / 'choice.json', choice)
        result = acceptance.accept(self.root, self.run, decision_file='choice.json')
        self.assertEqual(result['scope'], 'delivery-only')
        self.assertNotIn('expected_slot', choice)
        self.assertNotIn('slot', result)
        self.assertFalse((self.root / studio.MANIFEST).exists())
        work.step_done(self.root, 1)
        self.assertTrue(work.finish_state(self.root, self.run)['ready_to_finish'])
        self.assertEqual(work.finish(self.root, self.run)['task_id'], self.task_id)
        recovered = acceptance.accept(self.root, self.run)
        self.assertEqual(recovered['completion'], result['completion'])
        self.assertTrue(recovered['work']['finished'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
