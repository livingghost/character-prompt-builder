"""Run-bound authority authoring, literal instructions and shared judgments.

Every instruction and approval here is an explicit synthetic fixture. The
transport is local; these checks establish no real user consent or live send.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_authority_drafts as drafts
import production_case_fixtures as fixtures
import production_decisions
import production_execution as execution
import production_operations as workflow
import production_store as store
import transport_synthetic
from production_diagnostics import ProductionError
from production_fixtures import ACTOR
from test_production_execution import decisions


class AuthorityDraftTests(unittest.TestCase):
    @staticmethod
    def build(base):
        case = fixtures.create(base / 'studio', base / 'runtime', with_upscale=True)
        return case, {'run': workflow.prepare(case['root'], 'task.json')['run']}

    @classmethod
    def setUpClass(cls):
        cls._case_template = fixtures.CaseTemplate.for_class(cls, cls.build)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case, metadata = fixtures.CaseTemplate.for_test(self, Path(temporary.name), self.build,
                                                           self._case_template)
        self.root, self.run = self.case['root'], metadata['run']
        self.loaded = workflow.read_run(self.root, self.run)
        self.task_id = self.loaded.prepared['task']['task_id']

    def authority(self):
        return store.read_authority(self.root, self.task_id)

    def import_full(self, value):
        fixtures.write(self.root / 'changed-authority.json', value)
        return store.import_authority(self.root, 'changed-authority.json', expected=self.authority().event['sha256'])

    def approval(self, *, approved=True):
        (self.root / 'actual-instruction.txt').write_bytes(
            b'Explicit synthetic principal instruction for this prepared request. Not user consent.\r\n')
        report = execution.draft_principal_approval(self.root, self.run, 'actual-instruction.txt',
                                                    self.authority().document['issuer'])
        value = report['choices']
        if approved is not None:
            value['approval'] = {'approved': approved, 'scope': 'Explicit synthetic approval of this one request.'}
        fixtures.write(self.root / 'principal-approval.json', value)
        return value

    def update(self, *, evidence='principal-approval.json'):
        report = execution.draft_authority_update(self.root, self.run, evidence)
        value = report['choices']
        for item in value['grants']:
            item.update(actor=ACTOR, mode='direct', reason='Explicit synthetic authority addition. Not user consent.')
            if item['operation'] == 'submit':
                item['submission_validation_modes'] = [report['required_validation_mode']]
        return value

    def import_update(self, value, *, expected=None, report_changes=False):
        fixtures.write(self.root / 'authority-update.json', value)
        return store.import_authority(self.root, 'authority-update.json',
            expected=expected or value['expected_event'], report_changes=report_changes)

    def stopped_decisions(self):
        value = copy.deepcopy(self.authority().document)
        value['stop_conditions'] = [
            {'id': 'single-trial', 'text': 'The synthetic instruction still permits this one trial.'},
            {'id': 'preserve-history', 'text': 'The existing synthetic preparation remains intact.'}]
        self.import_full(value)
        path = decisions(self.root, self.run)
        return path, c.load(self.root / path)

    def stopped_upscale(self):
        self.stopped_decisions()
        run = workflow.prepare(self.root, fixtures.upscale_task(self.root))['run']
        path = decisions(self.root, run)
        choices = c.load(self.root / path)
        for item in choices['shared_stop_assessments']:
            item.update(clear=True, evidence='Explicit synthetic evidence of the original condition for this upscale.')
        fixtures.write(self.root / path, choices)
        return run, path

    def change_stop_text(self):
        value = copy.deepcopy(self.authority().document)
        value['stop_conditions'][0]['text'] = 'A changed synthetic condition under the same id.'
        return self.import_full(value)

    def test_initial_authority_guidance_and_registered_update_keep_their_owners(self):
        import production_document_contracts as contracts
        held = self.authority()
        before = copy.deepcopy(held.event)
        with tempfile.TemporaryDirectory() as temporary:
            empty_root = Path(temporary)
            initial = store.authority_snapshot(empty_root, self.task_id, None)
            self.assertIsNone(initial['document'])
            self.assertIsNone(initial['event_sha256'])
            self.assertIsNone(initial['source_path'])
            action = initial['update_action']
            self.assertEqual(action['command'], 'authority-import')
            self.assertNotIn('--expected-event', action['argv'])
            explain = contracts.explain_action('authority')
            self.assertIn(explain['shown'], action['reason'])
            self.assertIn('first import', action['reason'])
            self.assertIn('draft-authority-update', action['reason'])
            completed = subprocess.run(explain['argv'], text=True, capture_output=True, encoding='utf-8')
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            contract = json.loads(completed.stdout)
            self.assertEqual(contract['schema'], 'schemas/authoring/production-authority.schema.json')
            self.assertIn('templates/realization/production-authority.json', contract['example_paths'])
            self.assertEqual(list(empty_root.iterdir()), [])
        current = store.authority_snapshot(self.root, self.task_id, held, run=self.run)
        action = current['update_action']
        self.assertEqual(action['command'], 'authority-import')
        self.assertEqual(action['argv'][action['argv'].index('--expected-event') + 1], before['sha256'])
        self.assertEqual(current['document'], held.document)
        self.assertEqual(current['event_sha256'], before['sha256'])
        self.assertIn('observed predecessor', action['reason'])
        self.assertNotIn('first import', action['reason'])
        self.assertEqual(self.authority().event, before)

    def protected_change(self):
        """Prepare an explicitly authored change, retaining a real same-series baseline."""
        from production_fixtures import bind_work_basis
        task = c.load(self.root / 'task.json')
        unchanged = copy.deepcopy(task['criteria'][0])
        changing = {**unchanged, 'id': 'changing', 'text': 'The original explicit synthetic requirement.'}
        removed = {**unchanged, 'id': 'removed', 'text': 'A former explicit synthetic requirement.'}
        baseline = None
        for name, criteria in (
                ('criteria-baseline.json', [unchanged, changing, removed]),
                ('criteria-changed.json', [unchanged, {**changing, 'text': 'The newly authorized synthetic requirement.'},
                    {**unchanged, 'id': 'added', 'text': 'An additional explicit hard synthetic requirement.'}])):
            value = copy.deepcopy(task)
            value['criteria'] = criteria
            bind_work_basis(self.root, value, request='Explicit synthetic requirements for ' + name + '. Not user consent.')
            fixtures.write(self.root / name, value)
            selected = workflow.prepare(self.root, name)['run']
            if baseline is None:
                baseline = selected
        self.run = selected
        self.loaded = workflow.read_run(self.root, self.run)
        current = copy.deepcopy(self.authority().document)
        current['grants'][0]['protected_criteria'] = ['output', 'changing', 'removed', 'added']
        self.import_full(current)
        return baseline

    def test_protected_criteria_are_visible_before_execute_and_refusal_keeps_every_record(self):
        import production_report_view
        import production_workspace
        baseline = self.protected_change()
        held = self.authority()
        original = workflow.read_run(self.root, baseline).prepared
        original_bytes = (workflow.run_dir(self.root, baseline) / 'prepared.json').read_bytes()
        report = execution.draft_execution(self.root, self.run, 'fixture-grant')
        requirements = report['authorization_requirements']
        direction = requirements['requirements'][0]
        self.assertEqual(requirements['state'], 'action-required')
        self.assertFalse(direction['eligible'])
        problem = direction['diagnostics'][0]
        self.assertEqual((problem['code'], problem['cause']), ('INPUT_CONSISTENCY_ERROR', 'protected-criteria-changed'))
        self.assertEqual((problem['grant'], problem['comparison_run'], problem['production_id']),
                         ('fixture-grant', baseline, original['task']['production_id']))
        self.assertEqual((problem['file'], problem['pointer']), ('changed-authority.json', '/grants/0/protected_criteria'))
        self.assertEqual(problem['repair_action']['command'], 'authority-import')
        before = {item['id']: item for item in original['task']['criteria']}
        after = {item['id']: item for item in self.loaded.prepared['task']['criteria']}
        self.assertEqual(problem['changes'], [{'id': key, 'before': before.get(key), 'after': after.get(key)}
                         for key in ('added', 'changing', 'removed')])
        for guidance in (
                production_workspace.workspace(self.root, self.run, phase='decision'),
                execution.draft_authority_update(self.root, self.run),
                execution.status(self.root, self.run)['runs'][0]):
            with self.subTest(view=sorted(guidance)):
                needs = guidance['authorization_requirements']
                self.assertEqual(needs['state'], 'action-required')
                self.assertEqual(needs['protected_criteria']['comparison_run'], baseline)
                compact = production_report_view.authorization_requirements(needs)
                self.assertEqual(compact['requirements'][0]['ineligible_reasons'], {'protected-criteria': 1})
                self.assertEqual(compact['requirements'][0]['missing_targets'], [])
                self.assertEqual(compact['protected_criteria']['changes'], problem['changes'])
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=path)
        send.assert_not_called()
        self.assertEqual(caught.exception.diagnostic.details['changes'], problem['changes'])
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(self.authority().event, held.event)
        self.assertEqual((workflow.run_dir(self.root, baseline) / 'prepared.json').read_bytes(), original_bytes)

    def test_authored_addition_can_preserve_invariants_and_authorize_the_actual_change(self):
        self.protected_change()
        previous = copy.deepcopy(self.authority().document['grants'][0])
        criteria = copy.deepcopy(self.loaded.prepared['task']['criteria'])
        self.approval()
        update = self.update()
        direction = next(item for item in update['grants'] if item['operation'] == 'direction')
        direction['protected_criteria'] = ['output']
        self.import_update(update)
        held = self.authority()
        self.assertEqual(held.document['grants'][0], previous)
        report = execution.draft_execution(self.root, self.run, 'fixture-grant')
        self.assertFalse(report['authorization_requirements']['requirements'][0]['eligible'])
        old = report['authorization_requirements']['requirements'][0]['diagnostics'][0]
        self.assertIsNone(old['file'])
        self.assertEqual(old['repair_owner']['event_sha256'], held.event['sha256'])
        self.assertEqual(old['repair_action']['command'], 'draft-authority-update')
        self.assertIn(self.run, old['repair_action']['argv'])
        value = c.load(self.root / decisions(self.root, self.run))
        for choice in value['decisions']:
            choice['grant'] = next(item['id'] for item in update['grants'] if item['operation'] == choice['operation'])
        fixtures.write(self.root / 'changed-decisions.json', value)
        with patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            result = execution.execute(self.root, self.run, decisions_file='changed-decisions.json')
        self.assertTrue(result['execution_completed'])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(workflow.read_run(self.root, self.run).prepared['task']['criteria'], criteria)
        self.assertTrue(all(item['strength'] == 'hard' for item in criteria))

    def test_revision_compares_its_parent_and_an_independent_series_has_no_prior_constraint(self):
        from pack_manager import generate_uuid7
        self.protected_change()
        revised = copy.deepcopy(self.loaded.prepared['task'])
        revised['criteria'][0]['text'] = 'A further explicit synthetic revision.'
        with self.assertRaises(ProductionError) as caught:
            workflow.validate_protected_criteria(self.root, self.loaded.prepared,
                self.authority().document['grants'][0], revised=revised, authority=self.authority())
        problem = caught.exception.diagnostic.as_dict()
        self.assertEqual((problem['comparison'], problem['comparison_run'], problem['operation']),
                         ('revision', self.run, 'edit'))
        self.assertEqual([item['id'] for item in problem['changes']], ['output'])
        task = c.load(self.root / 'criteria-changed.json')
        task['production_id'] = generate_uuid7()
        task['criteria'].append({**task['criteria'][0], 'id': 'removed',
                                'text': 'The independent series declares its own explicit requirement.'})
        fixtures.write(self.root / 'independent-series.json', task)
        separate = workflow.prepare(self.root, 'independent-series.json')['run']
        report = execution.draft_execution(self.root, separate, 'fixture-grant')
        self.assertEqual(report['authorization_requirements']['state'], 'covered')
        comparison = report['authorization_requirements']['protected_criteria']
        self.assertIsNone(comparison['comparison_run'])
        self.assertEqual(comparison['changes'], [])

    def test_instruction_bytes_and_derived_reference_bindings_are_retained_without_approval(self):
        raw = '\ufeff  明示した合成指示。\r\nKeep these exact spaces.  \r\n'.encode('utf-8')
        (self.root / 'literal.txt').write_bytes(raw)
        prior = self.authority().event
        report = execution.draft_principal_approval(self.root, self.run, 'literal.txt', prior['data']['authority']['issuer'])
        value = report['choices']
        self.assertEqual(value['instruction']['text'].encode('utf-8'), raw)
        self.assertEqual(value['instruction']['sha256'], c.digest(raw))
        self.assertEqual(value['approval'], {'approved': None, 'scope': ''})
        payload = self.loaded.artifacts['execution-plan.json']['operations'][-1]['payload']
        self.assertEqual(value['binding']['request_sha256'], payload['request_sha256'])
        self.assertEqual(value['binding']['target'], payload['request_contract']['sealed']['target'])
        self.assertEqual(value['binding']['references']['bindings'], payload['request_contract']['sealed']['bindings'])
        self.assertEqual(value['binding']['references']['media'], payload['request_contract']['sealed']['media'])
        self.assertEqual(self.authority().event, prior)
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_absent_empty_invalid_and_wrong_principal_instructions_cannot_produce_approval(self):
        for raw in (b'', b' \t\r\n', b'\xff'):
            with self.subTest(raw=raw):
                (self.root / 'invalid.txt').write_bytes(raw)
                with self.assertRaises(ProductionError):
                    execution.draft_principal_approval(self.root, self.run, 'invalid.txt',
                                                        self.authority().document['issuer'])
        with self.assertRaises(ProductionError):
            execution.draft_principal_approval(self.root, self.run, 'missing.txt', self.authority().document['issuer'])
        (self.root / 'instruction.txt').write_text('Explicit synthetic instruction.', encoding='utf-8')
        with self.assertRaises(ProductionError) as caught:
            execution.draft_principal_approval(self.root, self.run, 'instruction.txt', 'another-principal')
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.details['expected'], self.authority().document['issuer'])

    def test_public_summary_supplies_usable_principal_evidence_for_the_next_update(self):
        (self.root / 'instruction.txt').write_text('Explicit synthetic trial instruction. Not user consent.', encoding='utf-8')
        prior = self.authority().event
        argv = [sys.executable, str(Path(__file__).with_name('production_workflow.py')),
            'draft-principal-approval', '--root', str(self.root), '--run', self.run,
            '--instruction-file', 'instruction.txt', '--actor', self.authority().document['issuer'],
            '--out', 'work/approval.json', '--view', 'summary']
        completed = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        selection = report['approval_selection']
        self.assertEqual(selection['locator'], 'whole')
        approval = c.load(self.root / selection['path'])
        self.assertIsNone(approval['approval']['approved'])
        self.assertEqual(self.authority().event, prior)
        approval['approval'] = {'approved': True, 'scope': 'Explicit synthetic approval of this prepared trial request.'}
        fixtures.write(self.root / selection['path'], approval)
        updated = self.import_update(self.update(evidence=selection['path']))
        self.assertNotEqual(updated['sha256'], prior['sha256'])

    def test_unanswered_authority_draft_retains_issuer_operations_and_no_effect(self):
        prior = self.authority().event
        report = execution.draft_authority_update(self.root, self.run)
        value = report['choices']
        self.assertEqual(value['issuer'], prior['data']['authority']['issuer'])
        self.assertEqual(value['expected_event'], prior['sha256'])
        intents = self.loaded.artifacts['execution-plan.json']['operations']
        self.assertEqual([(item['operation'], item['targets']) for item in value['grants']],
                         [(item['operation'], item['targets']) for item in intents])
        self.assertTrue(all(item['actor'] is None and item['mode'] is None and item['reason'] == ''
                            for item in value['grants']))
        self.assertEqual(self.authority().event, prior)
        with self.assertRaises(ProductionError) as caught:
            self.import_update(value)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_REQUIRED')
        self.assertEqual(self.authority().event, prior)

    def test_declined_and_unanswered_structured_approvals_cannot_import_even_complete_grants(self):
        prior = self.authority().event
        for approved in (None, False):
            with self.subTest(approved=approved):
                self.approval(approved=approved)
                update = self.update()
                with self.assertRaises(ProductionError) as caught:
                    self.import_update(update)
                self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_REQUIRED')
                declaration = copy.deepcopy(prior['data']['authority'])
                declaration['evidence'] = {'path': 'principal-approval.json', 'locator': 'whole'}
                with self.assertRaises(ProductionError):
                    self.import_full(declaration)
                self.assertEqual(self.authority().event, prior)

    def test_import_adds_exact_grants_preserves_existing_authority_and_reports_only_changes(self):
        self.approval()
        prior = self.authority().event
        update = self.update()
        update['additional_stop_conditions'] = [{'id': 'new-condition', 'text': 'Explicit synthetic new restriction.'}]
        # The retained literal instruction and earlier authority evidence do not
        # depend on an original source file remaining available.
        (self.root / 'actual-instruction.txt').unlink()
        (self.root / prior['data']['authority']['evidence']['path']).unlink()
        report = self.import_update(update, report_changes=True)
        held = self.authority()
        self.assertEqual(held.document['issuer'], prior['data']['authority']['issuer'])
        self.assertEqual(held.document['grants'][:len(prior['data']['authority']['grants'])],
                         prior['data']['authority']['grants'])
        self.assertEqual([item['operations'] for item in held.document['grants'][-2:]], [['direction'], ['submit']])
        self.assertEqual(held.document['stop_conditions'], update['additional_stop_conditions'])
        self.assertEqual(report['changed_grants'], {'added': [item['id'] for item in update['grants']],
                                                   'updated': [], 'removed': [], 'revoked': []})
        self.assertNotIn('changed_grants', held.event)
        self.assertEqual(store.event_rows(self.root, self.run), [])
        snapshot = store.authority_snapshot(self.root, self.task_id, held, run=self.run)
        self.assertEqual(snapshot['update_action']['command'], 'draft-authority-update')
        self.assertIn(self.run, snapshot['update_action']['argv'])

    def test_current_issuer_and_both_predecessors_remain_required(self):
        self.approval()
        update = self.update()
        wrong = copy.deepcopy(update)
        wrong['issuer'] = 'replacement-principal'
        with self.assertRaises(ProductionError) as caught:
            self.import_update(wrong)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.pointer, '/issuer')
        changed = copy.deepcopy(self.authority().document)
        changed['grants'][0]['protected_criteria'] = ['identity']
        latest = self.import_full(changed)
        for expected in (update['expected_event'], latest['sha256']):
            with self.subTest(expected=expected), self.assertRaises(ProductionError) as caught:
                self.import_update(update, expected=expected)
            self.assertEqual(caught.exception.diagnostic.code, 'AUTHORITY_UPDATE_CONFLICT')
        self.assertEqual(self.authority().event['sha256'], latest['sha256'])

    def test_unchanged_delegated_grant_keeps_captured_scope_when_its_original_source_moves(self):
        from production_request import delegation_template
        value = copy.deepcopy(self.authority().document)
        scope = delegation_template(self.loaded.prepared, self.loaded.artifacts['execution-plan.json']['operations'],
                                     value)['scope']
        (self.root / 'delegation-plan.txt').write_text('Explicit synthetic scope instruction.', encoding='utf-8')
        scope['plan'] = {'path': 'delegation-plan.txt', 'locator': 'whole'}
        value['grants'][0]['request_scope'] = scope
        self.import_full(value)
        previous = copy.deepcopy(self.authority().document['grants'][0])
        self.approval()
        update = self.update()
        (self.root / 'delegation-plan.txt').unlink()
        self.import_update(update)
        held = self.authority()
        self.assertEqual(held.document['grants'][0], previous)
        evidence = next(item for item in held.evidence if item['path'] == 'delegation-plan.txt')
        self.assertEqual(c.digest(evidence['raw']), previous['request_scope']['plan']['sha256'])

    def test_additions_refuse_changed_run_targets_and_existing_grant_identifiers(self):
        self.approval()
        original = self.update()
        prior = self.authority().event
        for change in ('input', 'request', 'targets', 'grant-id'):
            with self.subTest(change=change):
                value = copy.deepcopy(original)
                if change in {'input', 'request'}:
                    value[change + '_sha256'] = '0' * 64
                elif change == 'targets':
                    value['grants'][0]['targets'] = ['purpose']
                else:
                    value['grants'][0]['id'] = prior['data']['authority']['grants'][0]['id']
                with self.assertRaises(ProductionError) as caught:
                    self.import_update(value)
                self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
                self.assertEqual(self.authority().event, prior)

    def test_changed_selected_instruction_is_not_silently_repinned(self):
        value = self.approval()
        update = self.update()
        value['approval']['scope'] += ' Additional synthetic scope.'
        fixtures.write(self.root / 'principal-approval.json', value)
        with self.assertRaises(ProductionError) as caught:
            self.import_update(update)
        self.assertEqual(caught.exception.diagnostic.pointer, '$.evidence.sha256')

    def test_principal_approval_is_rechecked_against_the_exact_run_before_a_send(self):
        approved = self.approval()
        path = decisions(self.root, self.run)
        value = c.load(self.root / path)
        value['decisions'][-1]['request_decision']['principal_approval'] = {
            'path': 'principal-approval.json', 'locator': 'whole'}
        fixtures.write(self.root / path, value)
        for change in ('run', 'request', 'references', 'actor', 'instruction', 'unapproved'):
            with self.subTest(change=change):
                altered = copy.deepcopy(approved)
                if change == 'run':
                    altered['binding']['run'] = 'another-run'
                elif change == 'request':
                    altered['binding']['request_sha256'] = '0' * 64
                elif change == 'references':
                    altered['binding']['references']['bindings'] = [{'reference_number': 1}]
                elif change == 'actor':
                    altered['actor'] = ACTOR
                elif change == 'instruction':
                    altered['instruction']['text'] += ' Changed words.'
                else:
                    altered['approval']['approved'] = None
                fixtures.write(self.root / 'principal-approval.json', altered)
                with patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError):
                    execution.execute(self.root, self.run, decisions_file=path)
                send.assert_not_called()
                self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_shared_judgments_expand_into_complete_independent_authorization_events(self):
        path, value = self.stopped_decisions()
        self.assertEqual([item['id'] for item in value['shared_stop_assessments']],
                         ['single-trial', 'preserve-history'])
        self.assertTrue(all(not item['clear'] and item['evidence'] == '' for item in value['shared_stop_assessments']))
        for item in value['shared_stop_assessments']:
            item.update(clear=True, evidence='Explicit shared synthetic assessment: ' + item['id'])
        override = {'id': 'single-trial', 'clear': True, 'evidence': 'Distinct synthetic submission evidence.'}
        value['decisions'][-1]['additional_stop_assessments'] = [override]
        fixtures.write(self.root / path, value)
        execution.execute(self.root, self.run, decisions_file=path)
        events = [item for item in store.event_rows(self.root, self.run) if item['event'] == 'authorization']
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['data']['request']['stop_assessments'], value['shared_stop_assessments'])
        expected = [override, value['shared_stop_assessments'][1]]
        self.assertEqual(events[1]['data']['request']['stop_assessments'], expected)
        self.assertTrue(all('shared_stop_assessments' not in item['data']['request'] for item in events))
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Recovery cannot resend')):
            execution.resume(self.root, self.run)

    def test_individual_false_judgment_overrides_clear_shared_judgment_without_partial_events(self):
        path, value = self.stopped_decisions()
        for item in value['shared_stop_assessments']:
            item.update(clear=True, evidence='Explicit shared synthetic assessment.')
        value['decisions'][-1]['additional_stop_assessments'] = [
            {'id': 'single-trial', 'clear': False, 'evidence': 'The synthetic submission condition is active.'}]
        fixtures.write(self.root / path, value)
        with patch.object(transport_synthetic, 'send') as send, self.assertRaises(ValueError):
            execution.execute(self.root, self.run, decisions_file=path)
        send.assert_not_called()
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_operation_specific_additions_cover_an_unshared_condition_and_duplicates_are_refused(self):
        path, value = self.stopped_decisions()
        second = value['shared_stop_assessments'].pop()
        value['shared_stop_assessments'][0].update(clear=True, evidence='Explicit shared synthetic trial evidence.')
        for choice in value['decisions']:
            choice['additional_stop_assessments'] = [{**second, 'clear': True,
                'evidence': 'Explicit synthetic preservation evidence for ' + choice['operation']}]
        requests = production_decisions.expand(self.root, self.run, value, self.loaded, self.authority())
        self.assertEqual([len(request['stop_assessments']) for request in requests], [2, 2])
        for duplicate_shared in (True, False):
            changed = copy.deepcopy(value)
            destination = (changed['shared_stop_assessments'] if duplicate_shared
                           else changed['decisions'][0]['additional_stop_assessments'])
            destination.append(copy.deepcopy(destination[0]))
            fixtures.write(self.root / path, changed)
            with patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError):
                execution.execute(self.root, self.run, decisions_file=path)
            send.assert_not_called()
            self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_same_condition_id_with_changed_text_requires_reassessment(self):
        path, choices = self.stopped_decisions()
        for item in choices['shared_stop_assessments']:
            item.update(clear=True, evidence='Explicit assessment of the original synthetic condition.')
        fixtures.write(self.root / path, choices)
        changed = copy.deepcopy(self.authority().document)
        changed['stop_conditions'][0]['text'] = 'Changed synthetic requirement with the same id.'
        self.import_full(changed)
        with patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=path)
        send.assert_not_called()
        self.assertEqual(caught.exception.diagnostic.pointer, '$.stop_conditions_sha256')
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_recorded_authorizations_refuse_changed_conditions_before_upload_and_accept_new_assessments(self):
        run, path = self.stopped_upscale()
        loaded = workflow.read_run(self.root, run)
        execution.authorize_decisions(self.root, run, path, loaded.prepared,
                                       loaded.artifacts['execution-plan.json'])
        recorded = store.event_rows(self.root, run)
        self.assertEqual([item['event'] for item in recorded], ['authorization', 'authorization'])
        self.change_stop_text()
        with patch.object(transport_synthetic, 'upload_media') as upload, \
                patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, run)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.pointer, '$.stop_assessments')
        upload.assert_not_called()
        send.assert_not_called()
        self.assertEqual(store.event_rows(self.root, run), recorded)
        refreshed = c.load(self.root / decisions(self.root, run))
        for item in refreshed['shared_stop_assessments']:
            item.update(clear=True, evidence='Explicit new synthetic assessment of the current condition text.')
        fixtures.write(self.root / path, refreshed)
        result = execution.execute(self.root, run, decisions_file=path)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(store.event_rows(self.root, run)[:len(recorded)], recorded)

    def test_changed_conditions_after_claim_refuse_the_first_upload(self):
        import execution_lifecycle
        run, path = self.stopped_upscale()
        begin = execution_lifecycle.begin_step

        def change_before_upload(*args, **kwargs):
            self.assertEqual(kwargs['operation'], 'upload')
            self.change_stop_text()
            return begin(*args, **kwargs)

        with patch.object(execution_lifecycle, 'begin_step', side_effect=change_before_upload), \
                patch.object(transport_synthetic, 'upload_media') as upload, \
                patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.pointer, '$.stop_assessments')
        upload.assert_not_called()
        send.assert_not_called()
        rows = store.event_rows(self.root, run)
        self.assertEqual(len([row for row in rows if row['event'] == 'dispatch-claim']), 1)
        self.assertFalse(any(row['event'] == 'external-step' for row in rows))

    def test_changed_condition_during_upload_refuses_send_and_keeps_original_receipts(self):
        run, path = self.stopped_upscale()
        upload = transport_synthetic.upload_media
        original_receipts = []

        def change_after_upload(*args, **kwargs):
            result = upload(*args, **kwargs)
            original_receipts.extend(row for row in store.event_rows(self.root, run) if row['event'] == 'authorization')
            self.change_stop_text()
            return result

        with patch.object(transport_synthetic, 'upload_media', side_effect=change_after_upload) as uploaded, \
                patch.object(transport_synthetic, 'send') as send, self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.pointer, '$.stop_assessments')
        self.assertEqual(uploaded.call_count, 1)
        send.assert_not_called()
        rows = store.event_rows(self.root, run)
        self.assertEqual([row for row in rows if row['event'] == 'authorization'], original_receipts)
        self.assertEqual([row['data']['operation'] for row in rows if row['event'] == 'external-step'], ['upload'])

    def test_unchanged_condition_definitions_in_new_authority_event_allow_send_once(self):
        run, path = self.stopped_upscale()
        upload = transport_synthetic.upload_media
        send = transport_synthetic.send

        def update_other_authority_after_upload(*args, **kwargs):
            result = upload(*args, **kwargs)
            value = copy.deepcopy(self.authority().document)
            value['stop_conditions'].reverse()
            value['grants'].append({**copy.deepcopy(value['grants'][0]), 'id': 'another-synthetic-grant',
                                    'actor': 'another-synthetic-actor'})
            self.import_full(value)
            return result

        with patch.object(transport_synthetic, 'upload_media', side_effect=update_other_authority_after_upload) as uploaded, \
                patch.object(transport_synthetic, 'send', wraps=send) as sent:
            result = execution.execute(self.root, run, decisions_file=path)
        self.assertTrue(result['execution_completed'])
        self.assertEqual((uploaded.call_count, sent.call_count), (1, 1))
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Recovery cannot resend')):
            execution.resume(self.root, run)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
