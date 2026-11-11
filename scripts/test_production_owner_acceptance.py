"""Candidate-local owner decisions over unchanged synthetic review evidence."""
from __future__ import annotations

import copy
import unittest

import execution_contract as c
import production_case_fixtures as fixtures
import production_execution as execution
import production_fixtures as fixture
import production_store as store
import production_workflow as workflow
import studio
from production_diagnostics import ProductionError
from test_production_review import ReviewCase


class OwnerAcceptanceTests(ReviewCase):
    def allowance(self, *, criteria=None, unresolved_indices=None):
        authority = store.authority(self.root, self.case['task']['task_id'])
        path = 'synthetic-owner-decision.txt'
        fixtures.write(self.root / path,
                       'Synthetic owner permits the named fixture limitation for this candidate. Not real user consent.')
        return {'principal': authority['issuer'],
                'evidence': {'path': path, 'sha256': c.sha256_file(self.root / path), 'locator': 'whole synthetic decision'},
                'criteria': ['palette'] if criteria is None else criteria,
                'unresolved_indices': [0] if unresolved_indices is None else unresolved_indices,
                'reason': 'Use this exact synthetic candidate with the explicitly observed limitation.'}

    def decision(self, acceptance):
        selection = workflow.draft_selection(self.root, self.run, self.candidate)
        selection.update(selector=fixture.ACTOR, reason='Explicit synthetic delivery decision.', owner_acceptance=acceptance)
        return selection

    def authorize(self, selection):
        selection['authorization'] = fixture.grant(self.root, self.run, workflow.selection_intent(selection))
        return selection

    def test_owner_selection_and_completion_preserve_the_failed_review_and_pixels(self):
        reviewed = self.record_review([('output', 'pass'), ('palette', 'fail')])
        task_bytes = (self.root / 'task.json').read_bytes()
        image = self.root / self.row(self.candidate)['result']['path']
        image_bytes = image.read_bytes()
        before = execution.status(self.root, self.run)['execution_records']
        selection = self.authorize(self.decision(self.allowance()))
        chosen = workflow.select_value(self.root, self.run, selection)
        self.assertEqual(workflow.select_value(self.root, self.run, selection), chosen)
        completed = workflow.complete(self.root, self.run)
        self.assertEqual(workflow.verify_completion(self.root, self.run, self.case['task']['task_id']), completed)
        _, _, _, rows = workflow.load_run(self.root, self.run)
        self.assertEqual(workflow.latest_review(rows, self.candidate), reviewed)
        self.assertEqual((self.root / 'task.json').read_bytes(), task_bytes)
        self.assertEqual(image.read_bytes(), image_bytes)
        self.assertEqual(sum(row['event'] == 'candidate' for row in rows), 1)
        self.assertEqual(sum(row['event'] == 'selection' for row in rows), 1)
        self.assertEqual(sum(row['event'] == 'completion' for row in rows), 1)
        self.assertEqual(len(studio.read_iterations(self.home)), 1)
        state = self.state()
        self.assertEqual((state['evaluation'], state['disposition'], state['selection_basis']),
                         ('nonconforming', 'selected', 'owner-allowance'))
        self.assertTrue(state['selection_current'])
        self.assertEqual(state['owner_acceptance'], selection['owner_acceptance'])
        after = execution.status(self.root, self.run)['execution_records']
        self.assertEqual((after['submissions'], after['captured_outputs']),
                         (before['submissions'], before['captured_outputs']))

    def test_each_assessed_nonpass_can_keep_its_actual_verdict(self):
        for verdict in ('fail', 'indeterminate', 'not-applicable'):
            with self.subTest(verdict=verdict):
                if verdict == 'fail':
                    # A failed review can retain a proposed improvement without
                    # making its execution a selection prerequisite.
                    data = self.review_data([('output', 'pass'), ('palette', verdict)])
                    data['unresolved'] = []
                    data['repairs'] = [{'id': 'optional-palette', 'decisions': [], 'observation_indices': [0],
                        'operation': 'Consider another palette only if desired.', 'targets': ['delivery'],
                        'reason': 'Optional synthetic improvement, not a condition of owner acceptance.'}]
                    fixtures.write(self.root / 'review.json', data)
                    review = workflow.review(self.root, self.run, 'review.json')
                else:
                    review = self.record_review([('output', 'pass'), ('palette', verdict)], unresolved=[])
                selected = self.authorize(self.decision(self.allowance(unresolved_indices=[])))
                workflow.select_value(self.root, self.run, selected)
                self.assertEqual(workflow.latest_review(store.event_rows(self.root, self.run), self.candidate), review)
                self.assertTrue(self.state()['selection_current'])

    def test_unresolved_issue_can_be_accepted_without_changing_passed_criteria(self):
        self.record_review([('output', 'pass'), ('palette', 'pass')],
                           unresolved=['The fixture edge has not been compared to an optional source.'])
        chosen = self.authorize(self.decision(self.allowance(criteria=[])))
        workflow.select_value(self.root, self.run, chosen)
        self.assertEqual((self.state()['evaluation'], self.state()['selection_basis']),
                         ('indeterminate', 'owner-allowance'))

    def test_incomplete_coverage_stays_a_decision_requirement(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        for criteria, issues in (([], [0]), (['palette'], [])):
            with self.subTest(criteria=criteria, issues=issues):
                selection = self.authorize(self.decision(self.allowance(criteria=criteria, unresolved_indices=issues)))
                self.assertCode('OWNER_ACCEPTANCE_REQUIRED', lambda: workflow.select_value(self.root, self.run, selection))
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))
        self.assertEqual(execution.status(self.root, self.run)['runs'][0]['next_action']['command'], 'draft-acceptance')

    def test_unassessed_hard_criterion_requires_review(self):
        self.record_review([('output', 'fail')])
        selection = self.authorize(self.decision(self.allowance(criteria=['output'])))
        self.assertCode('REVIEW_INCOMPLETE', lambda: workflow.select_value(self.root, self.run, selection))
        self.assertEqual(execution.status(self.root, self.run)['runs'][0]['next_action']['command'], 'draft-review')

    def test_exception_targets_must_be_known_nonpassing_assessments(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        for change in ({'criteria': ['output']}, {'criteria': ['unknown']},
                       {'criteria': ['palette', 'palette']}, {'unresolved_indices': [1]},
                       {'unresolved_indices': [True]}):
            with self.subTest(change=change):
                allowance = self.allowance()
                allowance.update(change)
                selection = self.decision(allowance)
                with self.assertRaises(ValueError):
                    self.authorize(selection)
                    workflow.select_value(self.root, self.run, selection)
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))

    def test_owner_identity_is_the_actual_authority_issuer(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        allowance = self.allowance()
        allowance['principal'] = fixture.ACTOR
        with self.assertRaisesRegex(ValueError, 'authority issuer'):
            self.authorize(self.decision(allowance))
        selection = self.authorize(self.decision(self.allowance()))
        authorization = workflow.find(store.event_rows(self.root, self.run), 'authorization', selection['authorization'])
        self.assertEqual(authorization['data']['authority'], {
            'event': store.authority_record(self.root, self.case['task']['task_id'])['sha256'],
            'issuer': selection['owner_acceptance']['principal']})

    def test_saved_approval_and_review_survive_live_source_changes(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        evidence = selection['owner_acceptance']['evidence']
        fixtures.write(self.root / evidence['path'], 'A later synthetic ledger reading contains other text.')
        (self.root / 'prompt.txt').unlink()
        workflow.select_value(self.root, self.run, selection)
        workflow.complete(self.root, self.run)
        self.assertTrue(self.state()['selection_current'])
        authorization = workflow.find(store.event_rows(self.root, self.run), 'authorization', selection['authorization'])
        witness = next(item for item in authorization['data']['files'] if item.get('purpose') == 'owner-acceptance')
        self.assertEqual((witness['sha256'], witness['locator']), (evidence['sha256'], evidence['locator']))
        self.assertNotEqual(c.sha256_file(self.root / evidence['path']), evidence['sha256'])

    def test_changed_instruction_before_authorization_is_not_accepted(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.decision(self.allowance())
        fixtures.write(self.root / selection['owner_acceptance']['evidence']['path'], 'Different synthetic source.')
        self.assertCode('SOURCE_CHANGED', lambda: self.authorize(selection))

    def test_corrupt_saved_witness_blocks_selection(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        saved = workflow.run_dir(self.root, self.run) / 'objects' / selection['owner_acceptance']['evidence']['sha256']
        saved.write_bytes(b'Changed saved evidence is not an owner instruction.')
        with self.assertRaises(ValueError):
            workflow.select_value(self.root, self.run, selection)
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))

    def unsaved_authorization(self, selection):
        """Record a copy of the selection's authorization that saved no owner-acceptance witness."""
        directory, prepared, _, rows = workflow.load_run(self.root, self.run)
        data = copy.deepcopy(workflow.find(rows, 'authorization', selection['authorization'])['data'])
        data['files'] = [item for item in data['files'] if item.get('purpose') != 'owner-acceptance']
        return workflow.append_record(directory, prepared, rows, 'authorization', data)

    def test_an_authorization_without_its_saved_owner_instruction_is_authorized_again(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        unsaved = self.unsaved_authorization(selection)
        refused = dict(selection, authorization=unsaved['sha256'])
        with self.assertRaises(ProductionError) as caught:
            workflow.select_value(self.root, self.run, refused)
        found = caught.exception.diagnostic.as_dict()
        evidence = selection['owner_acceptance']['evidence']
        self.assertEqual((found['code'], found['run'], found['event'], found['file'], found['expected']),
                         ('EVIDENCE_SNAPSHOT_MISSING', self.run, unsaved['sha256'], evidence['path'], evidence['sha256']))
        self.assertEqual(found['required_action'], workflow.UNSAVED_SELECTION_WITNESS.format(run=self.run))
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))
        # Another authorization of the same selection saves the cited instruction.
        workflow.select_value(self.root, self.run, self.authorize(copy.deepcopy(refused)))
        self.assertTrue(self.state()['selection_current'])

    def test_a_recorded_selection_without_its_saved_owner_instruction_names_a_new_run(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        unsaved = self.unsaved_authorization(selection)
        chosen = dict(selection, authorization=unsaved['sha256'])
        directory, prepared, _, rows = workflow.load_run(self.root, self.run)
        raw = c.encoded(chosen)
        key = c.object_store(directory, raw)
        workflow.append_record(directory, prepared, rows, 'selection', {
            'files': [{'path': f'production/runs/{self.run}/objects/{key}', 'sha256': key, 'size': len(raw)}],
            'selection': chosen, 'authorizations': [unsaved['sha256']]})
        with self.assertRaises(ProductionError) as caught:
            workflow.load_run(self.root, self.run)
        found = caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'], found['run'], found['event']),
                         ('EVIDENCE_SNAPSHOT_MISSING', self.run, unsaved['sha256']))
        self.assertEqual(found['required_action'], workflow.UNSAVED_SELECTION_RECORD.format(run=self.run))

    def test_exact_authorization_covers_the_allowance_reason(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        changed = copy.deepcopy(selection)
        changed['owner_acceptance']['reason'] = 'A different permission cannot reuse the original authorization.'
        with self.assertRaises(ValueError):
            workflow.select_value(self.root, self.run, changed)
        self.assertFalse(any(row['event'] == 'selection' for row in store.event_rows(self.root, self.run)))

    def test_new_review_and_withdrawal_require_new_selection(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        workflow.select_value(self.root, self.run, selection)
        self.not_selected()
        self.assertCode('SELECTION_WITHDRAWN', lambda: workflow.complete(self.root, self.run))
        self.record_review([('output', 'pass'), ('palette', 'indeterminate')])
        self.assertCode('SELECTION_REVIEW_CHANGED', lambda: workflow.select_value(self.root, self.run, selection))

    def test_committed_selection_is_historical_after_grant_revocation(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        selection = self.authorize(self.decision(self.allowance()))
        chosen = workflow.select_value(self.root, self.run, selection)
        authority = store.authority(self.root, self.case['task']['task_id'])
        authority['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        fixtures.write(self.root / 'revoked-authority.json', authority)
        store.import_authority(self.root, 'revoked-authority.json',
                               expected=store.authority_record(self.root, self.case['task']['task_id'])['sha256'])
        self.assertEqual(workflow.select_value(self.root, self.run, selection), chosen)
        self.assertEqual(workflow.complete(self.root, self.run)['event'], 'completion')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
