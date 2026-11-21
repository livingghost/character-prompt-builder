"""One actual decision produces separately checked execution records.

All approvals and provider calls in this suite are explicit synthetic fixtures.
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as f
import production_fixtures as fixtures
import production_store as store
import production_work_execution as work
import transport_synthetic
import test_production_authority_drafts as authority_cases


class WorkExecutionTests(unittest.TestCase):
    build = staticmethod(authority_cases.AuthorityDraftTests.build)
    setUpClass = classmethod(authority_cases.AuthorityDraftTests.setUpClass.__func__)
    setUp = authority_cases.AuthorityDraftTests.setUp
    authority = authority_cases.AuthorityDraftTests.authority
    import_full = authority_cases.AuthorityDraftTests.import_full

    def answer(self, draft):
        value = copy.deepcopy(draft['choices'])
        value['reason'] = 'The explicit synthetic instruction approves this exact saved request.'
        for assessment in value['stop_assessments']:
            assessment.update(clear=True, evidence='Explicit current synthetic evidence.')
        if 'approval' in value:
            value['approval'].update(actor=fixtures.ACTOR, mode='direct',
                evidence=copy.deepcopy(self.authority().document['evidence']))
        else:
            value['request_decision']['principal_approval'] = copy.deepcopy(self.authority().document['evidence'])
        fixtures.assess_rendition(value['request_decision']['rendition_review'])
        return value

    def apply(self, draft, answer=None):
        return work.apply(self.root, self.root / 'work/execution-answer', answer or self.answer(draft),
                          binding=draft['binding'])

    def test_existing_grants_create_two_authorizations_and_one_provider_call(self):
        draft = work.draft(self.root, self.run)
        self.assertNotIn('approval', draft['choices'])
        before = self.authority().event['sha256']
        with patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            result = self.apply(draft)
        self.assertEqual(result['runs'][0]['capture'], 'complete', result)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(self.authority().event['sha256'], before)
        rows = store.event_rows(self.root, self.run)
        requests = [row['data']['request'] for row in rows if row['event'] == 'authorization']
        self.assertEqual([row['operation'] for row in requests], ['direction', 'submit'])
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('A retry must recover.')):
            self.apply(draft)
        self.assertEqual(rows, store.event_rows(self.root, self.run))

    def test_one_approval_supplies_only_missing_grants_and_exact_principal_evidence(self):
        held = copy.deepcopy(self.authority().document)
        held['grants'] = []
        self.import_full(held)
        draft = work.draft(self.root, self.run)
        answer = self.answer(draft)
        self.assertIsNone(answer['request_decision']['principal_approval'])
        result = self.apply(draft, answer)
        self.assertEqual(result['runs'][0]['capture'], 'complete', result)
        grants = self.authority().document['grants']
        self.assertEqual([grant['operations'] for grant in grants], [['direction'], ['submit']])
        requests = [row['data']['request'] for row in store.event_rows(self.root, self.run)
                    if row['event'] == 'authorization']
        self.assertEqual(requests[1]['request_decision']['principal_approval']['evidence']['path'],
                         answer['approval']['evidence']['path'])

    def test_ambiguous_existing_grants_are_chosen_by_number_without_new_permission(self):
        held = copy.deepcopy(self.authority().document)
        alternate = copy.deepcopy(held['grants'][0])
        alternate['id'] = 'second-synthetic-grant'
        held['grants'].append(alternate)
        self.import_full(held)
        draft = work.draft(self.root, self.run)
        answer = self.answer(draft)
        self.assertNotIn('approval', answer)
        answer['grant_choices'] = {'direction': 2, 'submit': 2}
        before = self.authority().event['sha256']
        result = self.apply(draft, answer)
        self.assertEqual(result['runs'][0]['capture'], 'complete', result)
        self.assertEqual(self.authority().event['sha256'], before)
        requests = [row['data']['request'] for row in store.event_rows(self.root, self.run)
                    if row['event'] == 'authorization']
        self.assertEqual([row['grant'] for row in requests], [alternate['id'], alternate['id']])

    def test_revoked_selected_grant_requires_a_new_current_decision(self):
        draft = work.draft(self.root, self.run)
        answer = self.answer(draft)
        held = copy.deepcopy(self.authority().document)
        held['grants'][0]['revoked_at'] = c.now()
        self.import_full(held)
        before = store.event_rows(self.root, self.run)
        with self.assertRaisesRegex(ValueError, 'authority terms changed'):
            self.apply(draft, answer)
        self.assertEqual(before, store.event_rows(self.root, self.run))
        fresh = work.draft(self.root, self.run)
        self.assertIsNone(fresh['choices']['approval']['evidence']['path'])

    def test_unrelated_authority_addition_keeps_the_selected_terms(self):
        draft = work.draft(self.root, self.run)
        answer = self.answer(draft)
        held = copy.deepcopy(self.authority().document)
        unrelated = copy.deepcopy(held['grants'][0])
        unrelated.update(id='independent-unselected-grant', operations=['select'], targets=['delivery'],
                         submission_validation_modes=[])
        held['grants'].append(unrelated)
        self.import_full(held)
        result = self.apply(draft, answer)
        self.assertEqual(result['runs'][0]['capture'], 'complete', result)

    def test_interruption_after_authority_import_recovers_without_duplicate_grants(self):
        held = copy.deepcopy(self.authority().document)
        held['grants'] = []
        self.import_full(held)
        draft = work.draft(self.root, self.run)
        answer = self.answer(draft)
        original = c.atomic

        def fail_receipt(path, *args, **kwargs):
            if path.name == 'authority.json':
                raise OSError('Synthetic interruption after formal authority import.')
            return original(path, *args, **kwargs)

        with patch.object(c, 'atomic', side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError, 'after formal authority'):
                self.apply(draft, answer)
        event = self.authority().event['sha256']
        self.assertFalse(any(row['event'] == 'dispatch-claim' for row in store.event_rows(self.root, self.run)))
        result = self.apply(draft, answer)
        self.assertEqual(result['runs'][0]['capture'], 'complete', result)
        self.assertEqual(self.authority().event['sha256'], event)
        self.assertEqual(len(self.authority().document['grants']), 2)

    def test_changed_or_active_stop_condition_prevents_the_external_effect(self):
        held = copy.deepcopy(self.authority().document)
        held['stop_conditions'] = [{'id': 'permission-current', 'text': 'This synthetic trial is still permitted.'}]
        self.import_full(held)
        draft = work.draft(self.root, self.run)
        answer = self.answer(draft)
        answer['stop_assessments'][0]['clear'] = False
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No send with an active stop.')):
            with self.assertRaises(ValueError):
                self.apply(draft, answer)
        self.assertFalse(any(row['event'] == 'dispatch-claim' for row in store.event_rows(self.root, self.run)))
        held['stop_conditions'][0]['text'] = 'A changed condition with the same identifier.'
        self.import_full(held)
        with self.assertRaisesRegex(ValueError, 'authority terms changed'):
            self.apply(draft, self.answer(draft))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
