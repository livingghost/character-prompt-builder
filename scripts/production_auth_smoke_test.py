#!/usr/bin/env python3
"""Studio authentication through real preparation, claims and recovery owners.

The transport remains the local synthetic implementation. Tests temporarily
require authentication on that module to observe the value passed to send and
lookup. Every key and Studio belongs to the fixture;
no provider request or real host credential is used.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import dispatch
import execution_contract as c
import execution_lifecycle as accounting
import production_case_fixtures as cases
import production_compiler as compiler
import production_execution as execution
import production_fixtures
import production_store as store
import production_workflow as workflow
import service_auth
import transport_synthetic
from production_diagnostics import ProductionError
from test_production_execution import decisions


SERVICE = 'synthetic'
VARIABLE = 'CPB_SYNTHETIC_API_KEY'


class ProductionAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from catalog_retrieval import runtime
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        base = Path(temporary.name)
        cls.enterClassContext(production_fixtures.scratch_home(base / 'home'))
        user = base / 'user'
        user.mkdir()
        cls.enterClassContext(patch.object(Path, 'home', return_value=user))
        cls.enterClassContext(patch.dict(os.environ, {VARIABLE: ''}))
        cls.addClassCleanup(runtime.configure_pack_runtime, None)
        cls.case = cases.create(base / 'studio', base / 'runtime')
        cls.origin = cls.case['root']
        with patch.object(service_auth, 'resolve', side_effect=AssertionError('Preparation needs no key')):
            cls.prepared = workflow.prepare(cls.origin, 'task.json')
        cls.run_id = cls.prepared['run']
        cls.decision_file = decisions(cls.origin, cls.run_id)

    def setUp(self):
        from catalog_retrieval import runtime
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'home'
        self.enterContext(production_fixtures.scratch_home(self.home))
        self.user = self.base / 'user'
        self.user.mkdir()
        self.enterContext(patch.object(Path, 'home', return_value=self.user))
        self.enterContext(patch.dict(os.environ, {VARIABLE: ''}))
        runtime.configure_pack_runtime(self.case['settings'])
        self.root = cases.copy_studio(self.origin, self.base / 'studio')
        self.run = self.run_id
        self.enterContext(patch.dict(transport_synthetic._ANSWERED, clear=True))
        self.enterContext(patch.object(transport_synthetic, 'CREDENTIAL_FREE', False))
        self.actual_send = transport_synthetic.send
        self.send = self.enterContext(patch.object(transport_synthetic, 'send', wraps=self.actual_send))
        self.lookup = self.enterContext(patch.object(transport_synthetic, 'lookup', wraps=transport_synthetic.lookup))

    def set_key(self, value: str, *, root: Path | None = None) -> dict:
        return service_auth.set_value(root or self.root, SERVICE, value)['selection']

    def enter_key(self, entry: dict, value: str) -> bytes:
        path = Path(entry['path'])
        self.assertEqual(entry['format'], 'json')
        self.assertEqual(entry['encoding'], 'utf-8')
        self.assertEqual(entry['json_pointer'], '/' + SERVICE + '/api_key')
        document = json.loads(path.read_text(encoding='utf-8-sig'))
        document[SERVICE]['api_key'] = value
        raw = (json.dumps(document, indent=2) + '\n').encode('utf-8')
        path.write_bytes(raw)
        return raw

    def entered_value(self, entry: dict) -> str:
        self.assertEqual(entry['json_pointer'], '/' + SERVICE + '/api_key')
        document = json.loads(Path(entry['path']).read_text(encoding='utf-8-sig'))
        return document[SERVICE]['api_key']

    def call(self, *, root: Path | None = None) -> dict:
        return execution.execute(root or self.root, self.run, decisions_file=self.decision_file)

    def claim(self, *, root: Path | None = None) -> dict:
        return workflow.find(store.event_rows(root or self.root, self.run), 'dispatch-claim')

    def state(self) -> dict:
        report = execution.status(self.root, self.run)
        workflow.schema_check(report, 'status')
        self.assertTrue(report['ok'])
        return report['runs'][0]

    def sealed_bytes(self) -> dict[str, bytes]:
        directory = workflow.run_dir(self.root, self.run)
        return {name: (directory / name).read_bytes() for name in
                ('prepared.json', 'package.json', 'request-contract.json', 'execution-plan.json', 'execution-target.json')}

    def lose_answer(self) -> dict:
        def lost(request, service, key):
            self.actual_send(request, service, key)
            raise TimeoutError('Synthetic loss after the local service saved its answer')
        self.send.side_effect = lost
        result = self.call()
        self.assertEqual(result['runs'][0]['submission'], 'outcome_unknown')
        self.send.side_effect = AssertionError('Recovery must use lookup for this existing send')
        return result

    def interrupt_before_send(self) -> None:
        begin = accounting.begin_step
        def interrupted(*args, **kwargs):
            if kwargs['step'] == 'send':
                raise OSError('Synthetic interruption before the durable send boundary')
            return begin(*args, **kwargs)
        with patch.object(accounting, 'begin_step', side_effect=interrupted), self.assertRaises(OSError):
            self.call()
        self.send.assert_not_called()
        self.assertEqual(self.state()['submission'], 'claimed')

    def assert_no_published_secret(self, *values: str) -> None:
        for path in self.root.rglob('*'):
            if path.is_file() and path != self.root / service_auth.CONFIG_FILE:
                raw = path.read_bytes()
                for value in values:
                    self.assertNotIn(value.encode('utf-8'), raw, path.relative_to(self.root).as_posix())
                    self.assertNotIn(c.digest(value.encode('utf-8')).encode('ascii'), raw,
                                     path.relative_to(self.root).as_posix())

    def test_status_reports_local_availability_source_and_concrete_configuration(self):
        before = self.sealed_bytes()
        state = self.state()
        self.assertEqual(state['readiness'], 'configuration_required')
        self.assertTrue(state['authentication']['required'])
        self.assertFalse(state['authentication']['available'])
        self.assertEqual(state['authentication']['remote_validation'], 'not-performed')
        self.assertEqual(state['next_action']['command'], 'credentials-prepare')
        self.assertEqual(state['next_action']['argv'][2:5], ['credentials', 'prepare', SERVICE])
        self.assertIn(str(self.root.resolve()), state['next_action']['argv'])
        self.assertFalse(state['next_action']['requires_author_input'])
        self.assertEqual({item['code'] for item in state['readiness_diagnostics']},
                         {'AUTHORIZATION_REQUIRED', 'CREDENTIAL_UNAVAILABLE'})
        with self.assertRaises(ProductionError) as caught:
            self.call()
        self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
        selection = self.set_key('synthetic-status-key')
        state = self.state()
        self.assertEqual(state['authentication']['selection'], selection)
        self.assertTrue(state['authentication']['available'])
        self.assertEqual(state['readiness'], 'authorization_required')
        self.assertEqual(self.sealed_bytes(), before)
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.send.assert_not_called()
        self.lookup.assert_not_called()
        self.assert_no_published_secret('synthetic-status-key')

    def test_file_entry_executes_the_same_prepared_request_without_a_completion_command(self):
        before = self.sealed_bytes()
        prepared = service_auth.prepare(self.root, SERVICE)
        self.assertTrue(prepared['ok'])
        self.assertFalse(prepared['available'])
        selected = prepared['selection']
        path = Path(prepared['input']['path'])
        self.assertTrue(path.is_absolute())
        self.assertEqual(path, (self.root / service_auth.CONFIG_FILE).resolve())
        self.assertEqual(prepared['input']['json_pointer'], '/' + SERVICE + '/api_key')
        self.assertEqual(self.entered_value(prepared['input']), '')
        pending = self.state()
        self.assertEqual(pending['readiness'], 'configuration_required')
        self.assertEqual(pending['authentication']['selection'], selected)
        self.assertFalse(pending['authentication']['available'])
        action = pending['next_action']
        self.assertEqual(action['command'], 'credentials-status')
        self.assertTrue(action['requires_author_input'])
        self.assertEqual(action['input'], prepared['input'])
        self.assertEqual(action['input']['format'], 'json')
        self.assertEqual(action['input']['encoding'], 'utf-8')
        self.assertTrue(action['input']['instructions'])
        with self.assertRaises(ProductionError) as caught:
            self.call()
        self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(accounting.all_states(self.root), [])
        self.send.assert_not_called()
        self.lookup.assert_not_called()
        self.assertEqual(self.sealed_bytes(), before)
        repeated = service_auth.prepare(self.root, SERVICE)
        self.assertEqual(repeated['selection'], selected)
        self.assertEqual(repeated['input'], prepared['input'])
        self.assertEqual(self.entered_value(prepared['input']), '')
        self.enter_key(prepared['input'], ' \n\t ')
        self.assertTrue(self.state()['authentication']['available'])
        entered = 'synthetic-owner-entered-key\n'
        entered_document = self.enter_key(prepared['input'], entered)
        ready = self.state()
        self.assertTrue(ready['authentication']['available'])
        self.assertEqual(ready['authentication']['selection'], selected)
        self.assertEqual(ready['readiness'], 'authorization_required')
        for _ in range(2):
            retained = service_auth.prepare(self.root, SERVICE)
            self.assertTrue(retained['available'])
            self.assertEqual(retained['selection'], selected)
            self.assertIsNone(retained['next_action'])
            self.assertEqual(path.read_bytes(), entered_document)
        self.assertEqual(self.sealed_bytes(), before)
        result = self.call()
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], entered)
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['data']['authentication'], selected)
        self.assertEqual(self.claim()['data']['package_sha256'], c.content_id(c.decode(before['package.json'])))
        self.assertEqual(self.sealed_bytes(), before)
        self.assert_no_published_secret(entered)

    def test_status_schema_requires_a_complete_private_input_handoff(self):
        service_auth.prepare(self.root, SERVICE)
        report = execution.status(self.root, self.run)
        workflow.schema_check(report, 'status')
        self.assertEqual(report['runs'][0]['readiness'], 'configuration_required')
        self.assertEqual(report['runs'][0]['next_action']['command'], 'credentials-status')
        for path in ('/private/studio/credentials.json', r'C:\Users\owner\studio\credentials.json',
                     r'\\server\share\studio\credentials.json'):
            with self.subTest(absolute_path=path):
                portable = copy.deepcopy(report)
                portable['runs'][0]['next_action']['input']['path'] = path
                workflow.schema_check(portable, 'status')
        invalid_inputs = ({'path': 'relative/credentials.json'}, {'path': ''}, {'format': 'plain-text'},
                          {'json_pointer': 'synthetic/api_key'}, {'json_pointer': 1},
                          {'encoding': 'utf-16'}, {'instructions': ''}, {'value': 'synthetic-value'})
        for fields in invalid_inputs:
            with self.subTest(input_fields=fields):
                malformed = copy.deepcopy(report)
                malformed['runs'][0]['next_action']['input'].update(fields)
                with self.assertRaises(ValueError):
                    workflow.schema_check(malformed, 'status')
        for field in ('path', 'format', 'encoding', 'json_pointer', 'instructions'):
            with self.subTest(missing_field=field):
                malformed = copy.deepcopy(report)
                del malformed['runs'][0]['next_action']['input'][field]
                with self.assertRaises(ValueError):
                    workflow.schema_check(malformed, 'status')
        malformed = copy.deepcopy(report)
        malformed['runs'][0]['next_action']['requires_author_input'] = False
        with self.assertRaises(ValueError):
            workflow.schema_check(malformed, 'status')

    def test_check_and_prepare_do_not_resolve_or_freeze_authentication(self):
        with patch.object(service_auth, 'resolve', side_effect=AssertionError('Compilation needs no key')), \
                patch.object(service_auth, 'inspect', side_effect=AssertionError('Compilation does not observe credentials')):
            checked = compiler.check_task(self.root, 'task.json')
            prepared = workflow.prepare(self.root, 'task.json')
        self.assertTrue(checked['publishable'])
        self.assertTrue(prepared['formal_run_created'])
        self.assertNotIn('authentication', checked['readiness'])
        self.assertNotIn('authentication', prepared['execution_plan']['readiness'])
        self.set_key('synthetic-post-prepare-key')
        workflow.assert_current(self.root, prepared['run'])
        self.send.assert_not_called()
        self.lookup.assert_not_called()

    def test_two_studios_select_their_own_keys_across_working_directory_changes(self):
        second = cases.copy_studio(self.origin, self.base / 'second-studio')
        first_selection = self.set_key('synthetic-first-studio-key')
        second_selection = self.set_key('synthetic-second-studio-key', root=second)
        self.assertEqual(first_selection, second_selection)
        self.assertEqual(first_selection, {'service': SERVICE, 'source': 'api_key'})
        with contextlib.chdir(second):
            first = self.call()
        with contextlib.chdir(self.base):
            other = self.call(root=second)
        self.assertTrue(first['execution_completed'])
        self.assertTrue(other['execution_completed'])
        self.assertEqual([call.args[2] for call in self.send.call_args_list],
                         ['synthetic-first-studio-key', 'synthetic-second-studio-key'])
        self.assertEqual(self.claim()['data']['authentication'], first_selection)
        self.assertEqual(self.claim(root=second)['data']['authentication'], second_selection)
        self.lookup.assert_not_called()

    def test_saved_value_executes_without_key_environment_or_service_input_names(self):
        target = c.load(workflow.run_dir(self.root, self.run) / 'execution-target.json')
        self.assertEqual(target['offering']['service'], SERVICE)
        self.assertNotIn('env_var', target['service']['auth'])
        with patch.dict(os.environ, {'CPB_HOME': str(self.home)}, clear=True):
            selection = self.set_key('synthetic-directly-stored-key')
            result = self.call()
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], 'synthetic-directly-stored-key')
        self.assertEqual(self.claim()['data']['authentication'], selection)
        self.assertEqual(selection['source'], 'api_key')
        self.assertEqual(selection['service'], SERVICE)
        self.assert_no_published_secret('synthetic-directly-stored-key')

    def test_claim_rejects_another_services_selection_before_execution_accounting(self):
        data = execution.compiled(self.root, self.run)
        package, plan = data[4], data[6]
        execution.authorize_decisions(self.root, self.run, self.decision_file, data[1], plan)
        tokens = execution.receipts(self.root, data[1], workflow.load_run(self.root, self.run)[3], plan)
        journal, rendered = execution._journal(self.root, self.run, data)
        workflow.handoff(self.root, self.run, plan['handoff']['recipient'], 'dispatcher',
                         tokens['direction'], journal=journal.path)
        other = service_auth.set_value(self.root, 'another-service', 'synthetic-other-service-key')['selection']
        submission = next(item for item in plan['operations'] if item['operation'] == 'submit')
        with self.assertRaises(ValueError):
            workflow.claim_dispatch(self.root, self.run, package, {}, journal.path, submission,
                                    tokens['submit'], rendered=rendered, authentication=other)
        self.assertEqual(accounting.all_states(self.root), [])
        self.assertFalse(any(row['event'] == 'dispatch-claim' for row in store.event_rows(self.root, self.run)))
        self.send.assert_not_called()
        self.lookup.assert_not_called()

    def test_send_and_lookup_share_the_claimed_selection_without_resending(self):
        selection = self.set_key('synthetic-pinned-studio-key')
        self.lose_answer()
        claim = self.claim()
        self.assertEqual(claim['data']['authentication'], selection)
        result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.lookup.call_count, 1)
        self.assertEqual(self.send.call_args.args[2], 'synthetic-pinned-studio-key')
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-pinned-studio-key')
        self.assertEqual(self.lookup.call_args.args[0], self.send.call_args.args[0])
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assert_no_published_secret('synthetic-pinned-studio-key')

    def test_source_change_selects_new_work_while_prior_claim_requires_restoration(self):
        original = self.set_key('synthetic-first-stored-value')
        before = self.sealed_bytes()
        self.lose_answer()
        claim = self.claim()
        with patch.dict(os.environ, {VARIABLE: 'synthetic-new-work-environment-value'}):
            alternate = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            state = self.state()
            self.assertFalse(state['authentication']['available'])
            self.assertEqual(state['authentication']['diagnostics'][0]['expected_selection'], original)
            with self.assertRaises(ProductionError):
                execution.resume(self.root, self.run)
            self.lookup.assert_not_called()
            self.send.side_effect = None
            next_run = workflow.prepare(self.root, 'task.json')['run']
            result = execution.execute(self.root, next_run, decisions_file=decisions(self.root, next_run))
            self.assertTrue(result['execution_completed'])
            self.assertEqual(self.send.call_args.args[2], 'synthetic-new-work-environment-value')
            next_claim = workflow.find(store.event_rows(self.root, next_run), 'dispatch-claim')
            self.assertEqual(next_claim['data']['authentication'], alternate)
            prepared = service_auth.prepare(self.root, SERVICE, stored=True)
            self.enter_key(prepared['input'], 'synthetic-restored-stored-value')
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-restored-stored-value')
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.claim()['data']['authentication'], original)
        self.assertEqual(self.sealed_bytes(), before)
        self.assert_no_published_secret('synthetic-first-stored-value', 'synthetic-new-work-environment-value',
                                        'synthetic-restored-stored-value')

    def test_before_send_resume_uses_rotated_value_of_the_claimed_environment_variable(self):
        with patch.dict(os.environ, {VARIABLE: 'synthetic-environment-before-send'}):
            selected = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            self.interrupt_before_send()
            claim = self.claim()
            os.environ[VARIABLE] = 'synthetic-environment-rotated-before-send'
            result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], 'synthetic-environment-rotated-before-send')
        self.assertEqual(self.claim()['data']['authentication'], selected)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.send.call_count, 1)
        self.lookup.assert_not_called()
        self.assert_no_published_secret('synthetic-environment-before-send',
                                        'synthetic-environment-rotated-before-send')

    def test_rotation_in_the_selected_entry_preserves_the_request_and_lookup(self):
        first = self.set_key('synthetic-original-entry-value')
        before = self.sealed_bytes()
        self.lose_answer()
        rotated = self.set_key('synthetic-rotated-entry-value')
        self.assertEqual(rotated, first)
        workflow.assert_current(self.root, self.run)
        self.assertEqual(self.sealed_bytes(), before)
        result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-rotated-entry-value')
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['data']['authentication'], first)
        self.assert_no_published_secret('synthetic-original-entry-value', 'synthetic-rotated-entry-value')

    def test_before_send_resume_uses_rotation_in_the_existing_entry(self):
        selected = self.set_key('synthetic-before-send-value')
        self.interrupt_before_send()
        before = self.sealed_bytes()
        self.assertEqual(self.set_key('synthetic-before-send-rotated'), selected)
        result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.send.call_args.args[2], 'synthetic-before-send-rotated')
        self.assertEqual(self.sealed_bytes(), before)
        self.lookup.assert_not_called()

    def test_before_send_resume_waits_for_file_entry_and_keeps_the_existing_claim(self):
        prepared = service_auth.prepare(self.root, SERVICE)
        selected = prepared['selection']
        path = Path(prepared['input']['path'])
        self.enter_key(prepared['input'], 'synthetic-before-interruption')
        self.interrupt_before_send()
        claim = self.claim()
        before = self.sealed_bytes()
        self.enter_key(prepared['input'], '')
        pending = self.state()
        self.assertEqual(pending['readiness'], 'configuration_required')
        self.assertEqual(pending['next_action']['command'], 'credentials-status')
        self.assertTrue(pending['next_action']['requires_author_input'])
        self.assertEqual(Path(pending['next_action']['input']['path']), path)
        with self.assertRaises(ProductionError) as caught:
            execution.resume(self.root, self.run)
        self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
        self.send.assert_not_called()
        self.lookup.assert_not_called()
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.enter_key(prepared['input'], 'synthetic-entered-after-interruption')
        result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], 'synthetic-entered-after-interruption')
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['data']['authentication'], selected)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)

    def test_removed_claimed_service_prepares_its_direct_input_before_lookup(self):
        selected = self.set_key('synthetic-selected-before-removal')
        self.lose_answer()
        claim = self.claim()
        before = self.sealed_bytes()
        service_auth.remove(self.root, SERVICE)
        with patch.dict(os.environ, {VARIABLE: 'synthetic-unselected-environment-value'}):
            state = self.state()
            self.assertEqual(state['readiness'], 'configuration_required')
            self.assertEqual(state['authentication']['diagnostics'][0]['expected_selection'], selected)
            self.assertEqual(state['next_action']['command'], 'credentials-prepare')
            self.assertFalse(state['next_action']['requires_author_input'])
            self.assertIn('--stored', state['next_action']['argv'])
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root, self.run)
            self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
        self.assertEqual(self.send.call_count, 1)
        self.lookup.assert_not_called()
        restored = service_auth.prepare(self.root, SERVICE, stored=True)
        self.assertFalse(restored['available'])
        self.assertEqual(restored['selection'], selected)
        self.assertEqual(self.entered_value(restored['input']), '')
        pending = self.state()
        self.assertEqual(pending['authentication']['selection'], selected)
        self.assertTrue(pending['next_action']['requires_author_input'])
        with self.assertRaises(ProductionError):
            execution.resume(self.root, self.run)
        self.lookup.assert_not_called()
        self.enter_key(restored['input'], 'synthetic-service-restored-for-lookup')
        self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-service-restored-for-lookup')
        self.assertEqual(self.lookup.call_args.args[0], self.send.call_args.args[0])
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)
        self.assert_no_published_secret('synthetic-selected-before-removal',
                                        'synthetic-service-restored-for-lookup')

    def test_environment_to_stored_switch_blocks_lookup_until_claimed_source_is_restored(self):
        with patch.dict(os.environ, {VARIABLE: 'synthetic-environment-account'}):
            selected = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            self.lose_answer()
            self.assertEqual(self.claim()['data']['authentication'], selected)
            self.assertEqual(selected, {'service': SERVICE, 'source': 'api_key_env', 'variable': VARIABLE})
            self.set_key('synthetic-other-studio-account')
            state = self.state()
            self.assertEqual(state['readiness'], 'configuration_required')
            self.assertEqual(state['next_action']['command'], 'credentials-prepare')
            self.assertTrue(state['next_action']['requires_author_input'])
            self.assertEqual(state['authentication']['diagnostics'][0]['expected_selection'], selected)
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root, self.run)
            self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
            self.lookup.assert_not_called()
            self.assertEqual(self.send.call_count, 1)
            service_auth.prepare(self.root, SERVICE, environment=VARIABLE)
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-environment-account')

    def test_stored_to_environment_switch_guides_direct_file_input_before_lookup(self):
        selected = self.set_key('synthetic-original-stored-value')
        self.lose_answer()
        claim = self.claim()
        before = self.sealed_bytes()
        with patch.dict(os.environ, {VARIABLE: 'synthetic-other-environment-value'}):
            changed = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            self.assertNotEqual(changed, selected)
            state = self.state()
            self.assertEqual(state['next_action']['command'], 'credentials-prepare')
            self.assertTrue(state['next_action']['requires_author_input'])
            self.assertIn('--stored', state['next_action']['argv'])
            self.assertEqual(service_auth.prepare(self.root, SERVICE)['selection'], changed)
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root, self.run)
            self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
            self.lookup.assert_not_called()
            restored = service_auth.prepare(self.root, SERVICE, stored=True)
            self.assertFalse(restored['available'])
            self.assertEqual(restored['selection'], selected)
            pending = self.state()
            self.assertEqual(pending['next_action']['command'], 'credentials-status')
            self.assertEqual(pending['next_action']['input'], restored['input'])
            with self.assertRaises(ProductionError):
                execution.resume(self.root, self.run)
            self.lookup.assert_not_called()
            self.enter_key(restored['input'], 'synthetic-restored-stored-value')
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-restored-stored-value')
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)

    def test_removed_environment_configuration_restores_its_name_and_waits_for_process_value(self):
        with patch.dict(os.environ, {VARIABLE: 'synthetic-environment-before-loss'}):
            selected = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            self.lose_answer()
            claim = self.claim()
            before = self.sealed_bytes()
            service_auth.remove(self.root, SERVICE)
            os.environ.pop(VARIABLE)
            missing = self.state()
            self.assertEqual(missing['next_action']['command'], 'credentials-prepare')
            argv = missing['next_action']['argv']
            self.assertEqual(argv[argv.index('--environment') + 1], VARIABLE)
            with self.assertRaises(ProductionError):
                execution.resume(self.root, self.run)
            restored = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)
            self.assertFalse(restored['available'])
            self.assertIsNone(restored['input'])
            self.assertEqual(restored['selection'], selected)
            pending = self.state()
            self.assertEqual(pending['next_action']['command'], 'credentials-status')
            self.assertTrue(pending['next_action']['requires_author_input'])
            self.assertIn(VARIABLE, pending['authentication']['diagnostics'][0]['message'])
            self.lookup.assert_not_called()
            os.environ[VARIABLE] = 'synthetic-environment-after-restoration'
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-environment-after-restoration')
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)
        path = self.root / service_auth.CONFIG_FILE
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {SERVICE: {'api_key_env': VARIABLE}})

    def test_before_send_resume_rejects_a_changed_source_until_it_is_restored(self):
        selected = self.set_key('synthetic-initial-presend-key')
        self.interrupt_before_send()
        claim = self.claim()
        with patch.dict(os.environ, {VARIABLE: 'synthetic-changed-presend-key'}):
            service_auth.prepare(self.root, SERVICE, environment=VARIABLE)
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root, self.run)
            self.assertEqual(caught.exception.diagnostic.code, 'CREDENTIAL_UNAVAILABLE')
            self.send.assert_not_called()
            self.lookup.assert_not_called()
            self.assertEqual(self.claim()['data']['authentication'], selected)
            prepared = service_auth.prepare(self.root, SERVICE, stored=True)
            self.enter_key(prepared['input'], 'synthetic-restored-presend-key')
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.send.call_args.args[2], 'synthetic-restored-presend-key')
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.lookup.assert_not_called()

    def test_changed_environment_name_blocks_lookup_even_with_the_same_value(self):
        alternate = 'CPB_SYNTHETIC_ALTERNATE_KEY'
        with patch.dict(os.environ, {VARIABLE: 'synthetic-original-environment-value',
                                     alternate: 'synthetic-original-environment-value'}):
            selected = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            before = self.sealed_bytes()
            self.lose_answer()
            claim = self.claim()
            service_auth.prepare(self.root, SERVICE, environment=alternate)
            state = self.state()
            action = state['next_action']
            self.assertEqual(action['command'], 'credentials-prepare')
            self.assertTrue(action['requires_author_input'])
            self.assertEqual(action['argv'][action['argv'].index('--environment') + 1], VARIABLE)
            with self.assertRaises(ProductionError):
                execution.resume(self.root, self.run)
            self.lookup.assert_not_called()
            os.environ[VARIABLE] = 'synthetic-rotated-original-environment-value'
            restored = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)
            self.assertEqual(restored['selection'], selected)
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.lookup.call_args.args[2], 'synthetic-rotated-original-environment-value')
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)
        self.assert_no_published_secret('synthetic-original-environment-value',
                                        'synthetic-rotated-original-environment-value')

    def test_missing_private_document_prepares_its_claimed_service_before_send(self):
        selected = self.set_key('synthetic-before-document-loss')
        self.interrupt_before_send()
        claim = self.claim()
        before = self.sealed_bytes()
        (self.root / service_auth.CONFIG_FILE).unlink()
        state = self.state()
        action = state['next_action']
        self.assertEqual(action['command'], 'credentials-prepare')
        self.assertFalse(action['requires_author_input'])
        self.assertIn('--stored', action['argv'])
        prepared = service_auth.prepare(self.root, SERVICE, stored=True)
        self.assertEqual(prepared['selection'], selected)
        self.assertEqual(prepared['input']['path'], str((self.root / service_auth.CONFIG_FILE).resolve()))
        self.assertEqual(prepared['input']['json_pointer'], '/' + SERVICE + '/api_key')
        with self.assertRaises(ProductionError):
            execution.resume(self.root, self.run)
        self.send.assert_not_called()
        self.enter_key(prepared['input'], 'synthetic-restored-before-send')
        self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], 'synthetic-restored-before-send')
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)
        self.lookup.assert_not_called()

    def test_unrelated_invalid_key_entry_preserves_selected_readiness_and_execution(self):
        selected = self.set_key('synthetic-valid-selected-key')
        path = self.root / service_auth.CONFIG_FILE
        document = json.loads(path.read_text(encoding='utf-8'))
        document['other-service'] = {'api_key': {'unexpected': 'synthetic-invalid-unrelated-key'}}
        path.write_text(json.dumps(document), encoding='utf-8')
        before = path.read_bytes()
        state = self.state()
        self.assertTrue(state['authentication']['available'])
        self.assertEqual(state['authentication']['selection'], selected)
        self.assertTrue(self.call()['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], 'synthetic-valid-selected-key')
        self.assertEqual(path.read_bytes(), before)
        self.assert_no_published_secret('synthetic-valid-selected-key', 'synthetic-invalid-unrelated-key')

    def test_saved_final_answer_recovers_without_resolving_a_key(self):
        selected = self.set_key('synthetic-saved-answer-key')
        with patch.object(execution, '_acknowledge', side_effect=OSError('Synthetic interruption after saving the answer')), \
                self.assertRaises(OSError):
            self.call()
        service_auth.remove(self.root, SERVICE)
        with patch.object(service_auth, 'resolve', side_effect=AssertionError('Saved answer needs no credential')), \
                patch.object(service_auth, 'inspect', side_effect=AssertionError('Saved answer needs no credential inspection')):
            state = self.state()
            self.assertEqual(state['authentication'], {'required': False, 'available': None, 'selection': selected,
                'diagnostics': [], 'remote_validation': 'not-performed'})
            result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_count, 1)
        self.lookup.assert_not_called()

    def test_saved_terminal_observation_recovers_without_resolving_a_key(self):
        selected = self.set_key('synthetic-terminal-observation-key')
        with patch.object(dispatch, 'keep_answer', side_effect=OSError('Synthetic interruption before publishing answer.json')), \
                self.assertRaises(OSError):
            self.call()
        journal = c.local(self.root, self.claim()['data']['journal'])
        self.assertTrue((journal / 'send-observation.json').is_file())
        self.assertFalse((journal / 'answer.json').exists())
        service_auth.remove(self.root, SERVICE)
        with patch.object(service_auth, 'resolve', side_effect=AssertionError('Saved observation needs no credential')), \
                patch.object(service_auth, 'inspect', side_effect=AssertionError('Saved observation needs no credential inspection')):
            self.assertFalse(self.state()['authentication']['required'])
            result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.send.call_count, 1)
        self.lookup.assert_not_called()

    def test_credential_free_transport_records_null_and_skips_authentication(self):
        with patch.object(transport_synthetic, 'CREDENTIAL_FREE', True), \
                patch.object(service_auth, 'resolve', side_effect=AssertionError('Synthetic transport needs no credential')), \
                patch.object(service_auth, 'inspect', side_effect=AssertionError('Synthetic transport needs no inspection')):
            self.assertFalse(self.state()['authentication']['required'])
            result = self.call()
            self.assertIsNone(self.claim()['data']['authentication'])
            self.assertTrue(result['execution_completed'])
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.send.call_args.args[2], '')
        self.assertEqual(self.send.call_count, 1)
        self.lookup.assert_not_called()


    def test_saved_value_reaches_send_and_recovery_unchanged_after_editor_save(self):
        value = "  synthetic-opaque-stored\tkey\x00with-newline\r\n"
        selected = self.set_key(value)
        path = self.root / service_auth.CONFIG_FILE
        path.chmod(0o644)
        before = self.sealed_bytes()
        self.assertTrue(self.state()['authentication']['available'])
        self.lose_answer()
        self.assertEqual(self.send.call_args.args[2], value)
        claim = self.claim()
        rotated = "  synthetic-opaque-rotation\n" + "x" * 20000 + " \t"
        document = json.loads(path.read_text(encoding='utf-8'))
        document[SERVICE]['api_key'] = rotated
        document['other-service'] = {'api_key_env': []}
        replacement = self.root / 'editor-pending.json'
        replacement.write_text(json.dumps(document), encoding='utf-8')
        replacement.chmod(0o644)
        os.replace(replacement, path)
        self.assertTrue(self.state()['authentication']['available'])
        self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
        self.assertEqual(self.lookup.call_args.args[2], rotated)
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.lookup.call_count, 1)
        self.assertEqual(self.claim()['data']['authentication'], selected)
        self.assertEqual(self.claim()['sha256'], claim['sha256'])
        self.assertEqual(self.sealed_bytes(), before)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), document)
        self.assert_no_published_secret(value, rotated)

    def test_environment_value_reaches_send_and_recovery_without_trimming(self):
        value = '  synthetic-environment-with-space\tand-newline\r\n'
        with patch.dict(os.environ, {VARIABLE: value}):
            selected = service_auth.prepare(self.root, SERVICE, environment=VARIABLE)['selection']
            before = self.sealed_bytes()
            self.lose_answer()
            self.assertEqual(self.send.call_args.args[2], value)
            rotated = ' \t synthetic-current-environment-value  \n'
            os.environ[VARIABLE] = rotated
            self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])
            self.assertEqual(self.lookup.call_args.args[2], rotated)
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.lookup.call_count, 1)
        self.assertEqual(self.claim()['data']['authentication'], selected)
        self.assertEqual(self.sealed_bytes(), before)
        self.assert_no_published_secret(value, rotated)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
