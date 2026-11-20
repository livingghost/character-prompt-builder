"""Public selection-authority recovery using explicit synthetic instructions only."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import execution_contract as c
import production_case_fixtures as fixtures
import production_fixtures as fixture
import production_operations as workflow
import production_store as store
import test_production_acceptance as acceptance_cases
from test_production_review import ReviewCase


class SelectionAuthorityTests(ReviewCase):
    share_prepared_case = True
    count = 2

    def invoke(self, argv, *, expected=0):
        result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def cli(self, command, *arguments, expected=0):
        return self.invoke([sys.executable, str(Path(__file__).with_name('production_workflow.py')),
            command, '--root', str(self.root), *arguments], expected=expected)

    def authority(self):
        task_id = workflow.read_run(self.root, self.run).prepared['task']['task_id']
        return store.read_authority(self.root, task_id)

    def import_full(self, value):
        before = self.authority()
        fixtures.write(self.root / 'authority-current.json', value)
        return self.cli('authority-import', '--file', 'authority-current.json',
                        '--expected-event', before.event['sha256'], '--view', 'full')

    def limit_to_execution(self):
        value = copy.deepcopy(self.authority().document)
        for grant in value['grants']:
            grant['operations'] = [operation for operation in grant['operations'] if operation != 'select']
        value['grants'].append({**copy.deepcopy(value['grants'][0]), 'id': 'revoked-selection',
            'operations': ['select'], 'targets': ['delivery'], 'request_scope': None,
            'submission_validation_modes': [], 'revoked_at': '2026-01-01T00:00:00Z'})
        value['stop_conditions'] = [{'id': 'actual-choice',
            'text': 'The explicit synthetic instruction still selects the reviewed fixture.'}]
        self.import_full(value)
        return self.authority()

    def pass_review(self, candidate=None):
        return self.record_review([('output', 'pass'), ('palette', 'pass')], candidate)

    @staticmethod
    def actions(value):
        yield value
        for alternative in value.get('alternatives', []):
            yield from SelectionAuthorityTests.actions(alternative)

    def candidate_action(self, report, command, candidate=None):
        candidate = candidate or self.candidate
        choices = [action for action in self.actions(report['runs'][0]['next_action'])
                   if action['command'] == command and '--candidate' in action['argv']
                   and action['argv'][action['argv'].index('--candidate') + 1] == candidate
                   and (command != 'draft-acceptance' or
                        action['argv'][action['argv'].index('--scope') + 1] == 'delivery-only')]
        self.assertEqual(len(choices), 1, report['runs'][0]['next_action'])
        return choices[0]

    def authored_update(self, *, out='selection-authority.json', candidate=None):
        self.cli('draft-authority-update', '--run', self.run, '--phase', 'selection',
                 '--candidate', candidate or self.candidate, '--out', out, '--view', 'full')
        value = c.load(self.root / out)
        instruction = 'Explicit synthetic authority to select this fixture for delivery. This is not real user consent.'
        fixtures.write(self.root / 'actual-selection.txt', instruction)
        value['evidence'] = {'path': 'actual-selection.txt', 'locator': 'whole',
                             'sha256': c.sha256_file(self.root / 'actual-selection.txt')}
        for grant in value['grants']:
            grant.update(actor=fixture.ACTOR, mode='direct', reason=instruction)
        fixtures.write(self.root / out, value)
        return value

    def import_update(self, value, *, out='selection-authority.json', expected=0, predecessor=None):
        fixtures.write(self.root / out, value)
        return self.cli('authority-import', '--file', out, '--expected-event',
                        predecessor or value['expected_event'], '--view', 'full', expected=expected)

    def test_public_status_and_refusal_lead_to_selection_grant_then_acceptance(self):
        review = self.pass_review()
        held = self.limit_to_execution()
        events = store.event_rows(self.root, self.run)
        state = self.cli('status', '--run', self.run, '--view', 'summary')
        action = self.candidate_action(state, 'draft-authority-update')
        self.assertEqual(action['argv'][action['argv'].index('--phase') + 1], 'selection')
        self.candidate_action(state, 'draft-review', self.candidates[1])
        full = self.cli('status', '--run', self.run, '--view', 'full')
        self.assertEqual(self.candidate_action(full, 'draft-authority-update')['argv'], action['argv'])
        blocked = self.cli('draft-acceptance', '--run', self.run, '--candidate', self.candidate,
                           '--out', 'blocked-acceptance.json', expected=3)
        problem = blocked['diagnostics'][0]
        self.assertEqual(problem['code'], 'AUTHORIZATION_REQUIRED')
        self.assertEqual(problem['next_action']['argv'], action['argv'])
        self.assertFalse((self.root / 'blocked-acceptance.json').exists())
        report = self.invoke(action['argv'] + ['--view', 'summary'])
        value = c.load(self.root / report['draft_file'])
        self.assertEqual(report['phase'], 'selection')
        self.assertEqual(report['binding']['selection'],
                         {'candidate': self.candidate, 'review': review['sha256'], 'replaces': None})
        self.assertEqual([(item['operation'], item['targets']) for item in value['grants']],
                         [('select', ['delivery'])])
        self.assertTrue(all(item['actor'] is None and item['mode'] is None and item['reason'] == ''
                            for item in value['grants']))
        self.assertEqual(value['evidence'], {'path': None, 'locator': None, 'sha256': None})
        self.assertEqual(value['additional_stop_conditions'], [])
        self.assertNotIn('required_validation_mode', report)
        self.invoke(report['next_action']['argv'], expected=3)
        self.assertEqual(self.authority().event, held.event)
        self.assertEqual(store.event_rows(self.root, self.run), events)
        # The acting author records the supplied synthetic instruction explicitly.
        fixtures.write(self.root / 'actual-choice.txt', 'Explicit synthetic delivery selection authority; not user consent.')
        value['evidence'].update(path='actual-choice.txt', locator='whole')
        value['grants'][0].update(actor=fixture.ACTOR, mode='direct',
                                 reason='The synthetic principal explicitly permits this selection.')
        fixtures.write(self.root / report['draft_file'], value)
        imported = self.invoke(report['next_action']['argv'] + ['--view', 'summary'])
        self.assertEqual(imported['changed_grants']['added']['ids'], [value['grants'][0]['id']])
        current = self.authority()
        self.assertEqual(current.document['grants'][:-1], held.document['grants'])
        self.assertEqual(current.document['stop_conditions'], held.document['stop_conditions'])
        self.assertEqual(store.event_rows(self.root, self.run), events)
        following = self.invoke(imported['next_action']['argv'] + ['--view', 'summary'])
        acceptance = self.candidate_action(following, 'draft-acceptance')
        choices = self.invoke(acceptance['argv'])['choices']
        self.assertEqual(choices['grant'], value['grants'][0]['id'])
        self.assertEqual(choices['reason'], '')
        self.assertIsNone(choices['owner_acceptance'])
        self.assertEqual(choices['stop_assessments'], [{'id': 'actual-choice', 'clear': False, 'evidence': ''}])
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_default_still_derives_only_prepared_execution_operations(self):
        self.pass_review()
        report = self.cli('draft-authority-update', '--run', self.run,
                          '--out', 'execution-authority.json', '--view', 'full')
        intents = workflow.read_run(self.root, self.run).artifacts['execution-plan.json']['operations']
        self.assertEqual([(item['operation'], item['targets']) for item in report['choices']['grants']],
                         [(item['operation'], item['targets']) for item in intents])
        self.assertEqual(report['phase'], 'execution')
        self.assertNotIn('selection', report['choices'])
        self.assertIn('required_validation_mode', report)

    def test_execution_authority_draft_cannot_replace_request_digest_with_null(self):
        report = self.cli('draft-authority-update', '--run', self.run,
                          '--out', 'execution-authority.json', '--view', 'full')
        value = report['choices']
        self.assertNotIn('selection', value)
        value['request_sha256'] = None
        held = self.authority().event
        blocked = self.import_update(value, expected=2)
        self.assertEqual(blocked['diagnostics'][0]['code'], 'INPUT_SCHEMA_INVALID')
        self.assertIn('request_sha256', blocked['diagnostics'][0]['message'])
        self.assertEqual(self.authority().event, held)

    def test_explicit_phase_and_recorded_assessed_candidate_are_required(self):
        for index, arguments in enumerate((
                ['--phase', 'unknown'], ['--phase', 'selection'],
                ['--candidate', self.candidate],
                ['--phase', 'selection', '--candidate', '0' * 64],
                ['--phase', 'selection', '--candidate', self.candidate])):
            with self.subTest(arguments=arguments):
                out = f'invalid-{index}.json'
                self.cli('draft-authority-update', '--run', self.run, *arguments, '--out', out, expected=2)
                self.assertFalse((self.root / out).exists())
        self.record_review([('output', 'pass'), ('palette', 'not-assessed')])
        blocked = self.cli('draft-authority-update', '--run', self.run, '--phase', 'selection',
            '--candidate', self.candidate, '--out', 'unassessed.json', expected=2)
        self.assertEqual(blocked['diagnostics'][0]['code'], 'REVIEW_INCOMPLETE')
        self.assertFalse((self.root / 'unassessed.json').exists())

    def test_candidate_and_operation_changes_cannot_retarget_the_draft(self):
        self.pass_review()
        self.pass_review(self.candidates[1])
        original = self.authored_update()
        held = self.authority().event
        for change in ('candidate', 'operation', 'targets', 'request-null'):
            with self.subTest(change=change):
                value = copy.deepcopy(original)
                if change == 'candidate':
                    value['selection']['candidate'] = self.candidates[1]
                elif change == 'operation':
                    value['grants'][0]['operation'] = 'submit'
                elif change == 'targets':
                    value['grants'][0]['targets'] = ['purpose']
                else:
                    value['request_sha256'] = None
                blocked = self.import_update(value, expected=3)
                self.assertEqual(blocked['diagnostics'][0]['code'], 'AUTHORIZATION_MISMATCH')
                self.assertEqual(self.authority().event, held)

    def test_new_review_requires_a_new_selection_authority_draft(self):
        self.pass_review()
        value = self.authored_update()
        held = self.authority().event
        changed = self.review_data([('output', 'pass'), ('palette', 'pass')])
        changed['conclusion'] = 'A new explicit synthetic review supersedes the earlier review.'
        fixtures.write(self.root / 'review.json', changed)
        self.cli('review', '--run', self.run, '--file', 'review.json')
        events = store.event_rows(self.root, self.run)
        blocked = self.import_update(value, expected=3)
        self.assertEqual(blocked['diagnostics'][0]['pointer'], '$.selection')
        self.assertEqual(self.authority().event, held)
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_replaced_selection_is_rechecked_without_changing_current_authority(self):
        self.pass_review()
        value = self.authored_update()
        held = self.authority().event
        self.select()
        events = store.event_rows(self.root, self.run)
        blocked = self.import_update(value, expected=3)
        self.assertEqual(blocked['diagnostics'][0]['pointer'], '$.selection')
        self.assertEqual(self.authority().event, held)
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_issuer_and_both_authority_predecessors_still_guard_selection_import(self):
        self.pass_review()
        value = self.authored_update()
        wrong = copy.deepcopy(value)
        wrong['issuer'] = 'unrelated-synthetic-principal'
        blocked = self.import_update(wrong, expected=3)
        self.assertEqual(blocked['diagnostics'][0]['pointer'], '/issuer')
        current = copy.deepcopy(self.authority().document)
        current['stop_conditions'].append({'id': 'later-stop', 'text': 'A later explicit synthetic authority restriction.'})
        latest = self.import_full(current)
        for predecessor in (value['expected_event'], latest['sha256']):
            with self.subTest(predecessor=predecessor):
                blocked = self.import_update(value, predecessor=predecessor, expected=2)
                self.assertEqual(blocked['diagnostics'][0]['code'], 'AUTHORITY_UPDATE_CONFLICT')
                self.assertEqual(self.authority().event['sha256'], latest['sha256'])

    def test_selection_grant_does_not_supply_owner_allowance_or_override_revocation(self):
        self.record_review([('output', 'pass'), ('palette', 'fail')])
        self.limit_to_execution()
        value = self.authored_update()
        self.import_update(value)
        decisions = self.cli('draft-acceptance', '--run', self.run, '--candidate', self.candidate,
                             '--out', 'acceptance.json')['choices']
        self.assertIsNone(decisions['owner_acceptance'])
        decisions['reason'] = 'An explicit synthetic choice without the required discrepancy allowance.'
        for assessment in decisions['stop_assessments']:
            assessment.update(clear=True, evidence='The explicit synthetic selection instruction still applies.')
        fixtures.write(self.root / 'acceptance.json', decisions)
        events = store.event_rows(self.root, self.run)
        blocked = self.cli('accept', '--run', self.run, '--file', 'acceptance.json', expected=2)
        self.assertEqual(blocked['diagnostics'][0]['code'], 'OWNER_ACCEPTANCE_REQUIRED')
        self.assertEqual(store.event_rows(self.root, self.run), events)
        authority = copy.deepcopy(self.authority().document)
        next(item for item in authority['grants'] if item['id'] == decisions['grant'])['revoked_at'] = '2026-01-01T00:00:00Z'
        self.import_full(authority)
        blocked = self.cli('accept', '--run', self.run, '--file', 'acceptance.json', expected=3)
        self.assertEqual(blocked['diagnostics'][0]['code'], 'GRANT_REVOKED')
        self.assertEqual(store.event_rows(self.root, self.run), events)


class TextSelectionAuthorityTests(unittest.TestCase):
    """Retain a text result's absent request digest through the same public recovery."""
    setUp = acceptance_cases.TextAcceptanceTests.setUp
    invoke = SelectionAuthorityTests.invoke
    cli = SelectionAuthorityTests.cli
    authority = SelectionAuthorityTests.authority
    import_full = SelectionAuthorityTests.import_full
    limit_to_execution = SelectionAuthorityTests.limit_to_execution

    def test_public_text_selection_authority_action_reaches_acceptance(self):
        held = self.limit_to_execution()
        events = store.event_rows(self.root, self.run)
        status = self.cli('status', '--run', self.run, '--view', 'summary')
        action = status['runs'][0]['next_action']
        self.assertEqual(action['command'], 'draft-authority-update')
        self.assertEqual(action['argv'][action['argv'].index('--candidate') + 1], self.candidate)
        drafted = self.invoke(action['argv'] + ['--view', 'full'])
        value = drafted['choices']
        self.assertIsNone(value['request_sha256'])
        self.assertEqual(value['selection']['candidate'], self.candidate)
        self.assertEqual([(item['operation'], item['targets']) for item in value['grants']],
                         [('select', ['delivery'])])
        self.assertEqual(self.authority().event, held.event)
        self.assertEqual(store.event_rows(self.root, self.run), events)
        fixtures.write(self.root / 'text-choice.txt',
            'Explicit synthetic authority to select this reviewed sentence. This is not real user consent.')
        value['evidence'] = {'path': 'text-choice.txt', 'locator': 'whole',
                            'sha256': c.sha256_file(self.root / 'text-choice.txt')}
        value['grants'][0].update(actor=fixture.ACTOR, mode='direct',
            reason='The synthetic principal permits selection of the reviewed sentence for delivery.')
        fixtures.write(self.root / drafted['draft_file'], value)
        imported = self.invoke(drafted['next_action']['argv'] + ['--view', 'summary'])
        self.assertEqual(imported['changed_grants']['added']['ids'], [value['grants'][0]['id']])
        current = self.authority()
        self.assertEqual(current.document['grants'][:-1], held.document['grants'])
        self.assertEqual(current.document['stop_conditions'], held.document['stop_conditions'])
        following = self.invoke(imported['next_action']['argv'] + ['--view', 'summary'])
        action = following['runs'][0]['next_action']
        self.assertEqual(action['command'], 'draft-acceptance')
        choices = self.invoke(action['argv'])['choices']
        self.assertEqual(choices['candidate'], self.candidate)
        self.assertEqual(choices['grant'], value['grants'][0]['id'])
        self.assertEqual(choices['reason'], '')
        self.assertIsNone(choices['owner_acceptance'])
        self.assertEqual(choices['stop_assessments'], [{'id': 'actual-choice', 'clear': False, 'evidence': ''}])
        self.assertEqual(store.event_rows(self.root, self.run), events)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
