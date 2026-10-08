"""Public CLI diagnostics remain visible, safe, complete and studio-scoped."""
from __future__ import annotations
import argparse
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import operation_context as ops
from production_diagnostics import ProductionError

import production_fixtures


SCRIPTS = Path(__file__).resolve().parent


def disk_full(*_args, **_kwargs):
    raise OSError(errno.ENOSPC, 'No space left on device')


def events_of(folder: Path) -> list[dict]:
    return [json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines()]


def every_log_text(folder: Path) -> str:
    return ''.join(path.read_text(encoding='utf-8') for path in folder.rglob('*') if path.is_file())


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        env = production_fixtures.scratch_home(self.home)
        env.start(); self.addCleanup(env.stop)
        # A runner that records its own operation, such as validate.py, passes its id down.
        os.environ.pop(ops.PARENT_VARIABLE, None)

    def invoke(self, function):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ops.run_cli(function)
        return code, stdout.getvalue(), stderr.getvalue()

    def records(self, root=None):
        rows = ops.list_operations(root)
        self.assertEqual(len(rows), 1)
        folder = Path(rows[0]['path'])
        return rows[0], folder, [json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_formal_event_kind_is_a_payload_not_a_call_argument(self):
        def command():
            ops.current().event('formal_event_staged', kind='authorization',
                                phase='storage', event_sha256='a' * 64)
        code, stdout, stderr = self.invoke(command)
        self.assertEqual((code, stdout, stderr), (0, '', ''))
        event = next(e for e in self.records()[2] if e['event'] == 'formal_event_staged')
        self.assertEqual(event['kind'], 'authorization')
        self.assertEqual(event['phase'], 'storage')
        self.assertEqual(event['event_sha256'], 'a' * 64)

    def test_domain_facts_cannot_replace_event_envelope(self):
        def command():
            ops.current().event('domain_evidence', event='completed', at='invented timestamp')
        self.assertEqual(self.invoke(command)[0], 0)
        event = next(e for e in self.records()[2] if e['event'] == 'domain_evidence')
        self.assertNotEqual(event['at'], 'invented timestamp')
        self.assertTrue(event['at'].endswith('Z') or '+00:00' in event['at'])

    def test_postparse_validation_keeps_actionable_diagnostic(self):
        def command():
            parser=ops.ArgumentParser(prog='synthetic-validator')
            parser.parse_args([])
            parser.error('results are missing variants: fixture#01')
        code,stdout,stderr=self.invoke(command)
        self.assertEqual(code,2)
        self.assertIn('missing variants',stderr)
        _,folder,events=self.records()
        self.assertIn('missing variants',(folder/'stderr.log').read_text(encoding='utf-8'))
        self.assertTrue(any(event['event']=='validation_error' for event in events))

    def test_input_exception_keeps_json_and_human_diagnostic(self):
        def command(): raise ValueError('results are missing variants: fixture#01')
        code,stdout,stderr=self.invoke(command)
        self.assertEqual(code,2)
        document=json.loads(stdout)
        self.assertEqual(document['diagnostics'][0]['code'],'INPUT_CONSISTENCY_ERROR')
        self.assertIn('missing variants',stderr)
        row,folder,_=self.records()
        self.assertEqual(row['exit_code'],2)
        self.assertIn('missing variants',(folder/'stderr.log').read_text(encoding='utf-8'))

    def test_text_exit_is_shown_and_recorded(self):
        def command(): raise SystemExit('selected model has no offering on this service')
        code, stdout, stderr = self.invoke(command)
        self.assertEqual(code, 1); self.assertEqual(stdout, '')
        self.assertIn('no offering', stderr)
        row, folder, events = self.records()
        self.assertEqual((folder/'stderr.log').read_text(encoding='utf-8'), stderr)
        self.assertEqual(events[-1]['exit_code'], 1)
        self.assertTrue(row['complete'])

    def test_text_exit_redacts_known_credential_everywhere(self):
        secret = 'synthetic-private-key-not-an-actual-credential'
        def command(): raise SystemExit('request denied with '+secret)
        with patch.dict(os.environ, {'CPB_TEST_API_KEY': secret}):
            code, stdout, stderr = self.invoke(command)
        self.assertEqual(code, 1); self.assertNotIn(secret, stdout+stderr)
        _, folder, _ = self.records()
        for path in folder.iterdir(): self.assertNotIn(secret, path.read_text(encoding='utf-8'))
        self.assertIn('[REDACTED]', stderr)

    def test_none_exit_is_success(self):
        def command(): raise SystemExit()
        self.assertEqual(self.invoke(command), (0, '', ''))
        self.assertEqual(self.records()[0]['exit_code'], 0)

    def test_numeric_exit_does_not_duplicate_emitted_diagnostic(self):
        def command():
            import sys
            print('explicit diagnostic', file=sys.stderr)
            raise SystemExit(2)
        code, stdout, stderr = self.invoke(command)
        self.assertEqual((code, stdout, stderr), (2, '', 'explicit diagnostic\n'))
        self.assertEqual((self.records()[1]/'stderr.log').read_text(encoding='utf-8'), stderr)

    def test_structured_exception_preserves_phase_in_stdout_and_log(self):
        def command():
            raise ProductionError('CONTROL_NOT_AVAILABLE', 'Requested control is unavailable.', phase='request-compilation')
        code, stdout, stderr = self.invoke(command)
        self.assertEqual(code, 1); self.assertEqual(stderr, 'error: Requested control is unavailable.\n')
        result = json.loads(stdout)
        self.assertEqual(result['diagnostics'][0]['code'], 'CONTROL_NOT_AVAILABLE')
        self.assertEqual(result['diagnostics'][0]['phase'], 'request-compilation')
        _, folder, events = self.records()
        self.assertEqual(json.loads((folder/'stdout.log').read_text(encoding='utf-8')), result)
        self.assertEqual(events[-1]['diagnostic']['code'], 'CONTROL_NOT_AVAILABLE')

    def new_studio(self):
        root = self.home/'日本語 studio'; root.mkdir()
        (root/'studio.json').write_text('{}', encoding='utf-8')
        return root

    def test_production_root_routes_logs_to_existing_studio(self):
        root = self.new_studio()
        def command():
            parser = ops.ArgumentParser(); parser.add_argument('--production-root', type=Path)
            parser.parse_args(['--production-root', str(root)])
        self.assertEqual(self.invoke(command)[0], 0)
        row, _, _ = self.records(root)
        # The recorded studio is the Studio's real location, whatever link named it.
        self.assertEqual(row['metadata']['context']['studio'], str(root.resolve()))
        self.assertEqual(ops.list_operations(), [])
        self.assertFalse((root/'production').exists())

    def test_nested_studio_locator_routes_to_owning_studio(self):
        root = self.new_studio(); nested = root/'characters/C01'; nested.mkdir(parents=True)
        def command():
            parser=ops.ArgumentParser(); parser.add_argument('--studio', type=Path)
            parser.parse_args(['--studio', str(nested)])
        self.assertEqual(self.invoke(command)[0], 0)
        self.assertEqual(self.records(root)[0]['metadata']['context']['studio'], str(root.resolve()))

    def test_uncreated_output_is_not_a_studio(self):
        root = self.home/'not yet created'
        def command():
            parser=ops.ArgumentParser(); parser.add_argument('--root'); parser.parse_args(['--root', str(root)])
        self.assertEqual(self.invoke(command)[0], 0)
        self.assertFalse(root.exists()); self.assertTrue(self.records()[0]['complete'])

    def test_internal_nested_call_shares_one_operation(self):
        ids=[]
        def child():
            ids.append(ops.current().id)
            with ops.stage('nested-step'): print('{"ok":true}')
        def parent():
            ids.append(ops.current().id)
            return ops.run_cli(child)
        code, stdout, stderr = self.invoke(parent)
        self.assertEqual(code, 0); self.assertTrue(json.loads(stdout)['ok'])
        self.assertEqual(len(set(ids)), 1)
        events=self.records()[2]
        self.assertEqual(sum(e['event']=='started' for e in events), 1)
        self.assertEqual(sum(e['event']=='completed' for e in events), 1)

    def _fake_operation(self, root, ident, *, completed=True, run=None, created='2000-01-01T00:00:00Z', exit_code=0, pid=0):
        folder=root/'logs/operations'/created[:10]/ident;folder.mkdir(parents=True)
        metadata={'operation_id':ident,'parent_operation':None,'command':'synthetic','created_at':created,'pid':pid,'arguments':{},'context':{}}
        if run is not None:metadata['context']['run']=run
        (folder/'operation.json').write_text(json.dumps(metadata),encoding='utf-8')
        events=[{'event':'started','at':created}]
        if completed:events.append({'event':'completed','at':created,'exit_code':exit_code,'complete':True})
        (folder/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events),encoding='utf-8')
        for name in ('stdout.log','stderr.log'): (folder/name).write_text('',encoding='utf-8')
        (folder/'artifacts.json').write_text('[]',encoding='utf-8')
        return folder

    def test_logs_cleanup_is_dry_run_then_deletes_only_completed_owned_logs(self):
        root=self.new_studio();eligible=self._fake_operation(root,'eligible');protected=self._fake_operation(root,'incomplete',completed=False)
        plan=ops.cleanup_logs(root,before='2001-01-01',apply=False)
        self.assertEqual([x['operation_id'] for x in plan['candidates']],['eligible'])
        self.assertEqual([x['reason'] for x in plan['protected']],['incomplete-operation'])
        self.assertTrue(eligible.exists());self.assertTrue(protected.exists())
        applied=ops.cleanup_logs(root,before='2001-01-01',apply=True)
        self.assertEqual(applied['deleted'],['eligible']);self.assertFalse(eligible.exists());self.assertTrue(protected.exists())
        self.assertFalse(applied['formal_artifacts_deleted'])

    def test_logs_cleanup_protects_the_operation_performing_cleanup(self):
        root=self.new_studio();captured={}
        def command():
            parser=ops.ArgumentParser();parser.add_argument('--root',type=Path);parser.parse_args(['--root',str(root)])
            captured.update(ops.cleanup_logs(root,before='2999-01-01',apply=True))
        self.assertEqual(self.invoke(command)[0],0)
        self.assertTrue(any(row['reason']=='active-operation' for row in captured['protected']))
        rows=ops.list_operations(root);self.assertEqual(len(rows),1);self.assertTrue(rows[0]['complete'])

    def test_nested_and_scalar_sensitive_values_are_not_logged(self):
        document = {'token': {'nested': ['PRIVATE TOKEN', {'x': 'ANOTHER SECRET'}]},
                    'base64': ['BINARY CONTENT'], 'password': 123456789,
                    'code': 'EXPECTED_CODE'}
        output=io.StringIO(); writer=ops.RedactingWriter(output.write,())
        data=json.dumps(document)
        for char in data:writer.write(char)
        writer.flush(final=True)
        restored=json.loads(output.getvalue())
        self.assertEqual(restored['token'],'[REDACTED]')
        self.assertEqual(restored['base64'],'[REDACTED]')
        self.assertEqual(restored['password'],'[REDACTED]')
        self.assertEqual(restored['code'],'EXPECTED_CODE')

    def test_escaped_sensitive_key_is_redacted(self):
        output=io.StringIO();writer=ops.RedactingWriter(output.write,())
        for char in '{"api\\u005fkey":"PRIVATE","ok":true}':writer.write(char)
        writer.flush(final=True)
        self.assertNotIn('PRIVATE',output.getvalue())
        self.assertTrue(json.loads(output.getvalue())['ok'])

    def test_long_raw_auth_token_does_not_leak_its_tail(self):
        for prefix in ('Bearer ', 'https://example.invalid/a?signature='):
            output=io.StringIO();writer=ops.RedactingWriter(output.write,())
            secret='sensitive-segment-'*2000
            text=prefix+secret+' end'
            for offset in range(0,len(text),61):writer.write(text[offset:offset+61])
            writer.flush(final=True)
            self.assertNotIn('sensitive-segment',output.getvalue())
            self.assertIn('[REDACTED]',output.getvalue())
            self.assertTrue(output.getvalue().endswith(' end'))

    def test_unknown_argument_value_is_not_saved_or_echoed(self):
        private='synthetic-credential-only-in-argv'
        def command():
            parser=ops.ArgumentParser()
            parser.parse_args(['--unknown-password',private])
        code,stdout,stderr=self.invoke(command)
        self.assertEqual(code,2)
        self.assertNotIn(private,stdout+stderr)
        for path in self.records()[1].iterdir():
            self.assertNotIn(private,path.read_text(encoding='utf-8'))

    def test_cleanup_keeps_unowned_file_in_diagnostic_directory(self):
        root=self.new_studio();folder=self._fake_operation(root,'owned')
        (folder/'request.json').write_text('{"formal":"evidence"}', encoding='utf-8')
        plan=ops.cleanup_logs(root,operation_id='owned',apply=True)
        self.assertEqual(plan['deleted'],[])
        self.assertTrue((folder/'request.json').is_file())

    def test_cleanup_rejects_redirected_diagnostic_root(self):
        root=self.new_studio();outside=self.home/'outside';outside.mkdir()
        (root/'logs').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ProductionError,'LOG_PATH_UNSAFE'):
            ops.cleanup_logs(root,before='2999-01-01',apply=True)
        self.assertTrue(outside.is_dir())

    def test_cleanup_checks_formal_accounting_even_with_complete_capture(self):
        root=self.new_studio();folder=self._fake_operation(root,'fee',run='synthetic-run')
        with patch.object(ops,'_run_has_unresolved_external_effect',return_value=True):
            result=ops.cleanup_logs(root,operation_id='fee',apply=True)
        self.assertEqual(result['deleted'],[])
        self.assertEqual(result['protected'][0]['reason'],'remote-outcome-unresolved')
        self.assertTrue(folder.is_dir())

    def test_export_is_redacted_and_does_not_follow_log_file_link(self):
        root=self.new_studio();folder=self._fake_operation(root,'export')
        private=self.home/'private.txt';private.write_text('NOT A DIAGNOSTIC', encoding='utf-8')
        (folder/'stdout.log').unlink()
        (folder/'stdout.log').symlink_to(private)
        result=ops.export_logs(root,root/'diagnostics')
        self.assertTrue(result['omissions'])
        self.assertNotIn('NOT A DIAGNOSTIC',''.join(p.read_text(encoding='utf-8') for p in (root/'diagnostics').rglob('*') if p.is_file()))
        self.assertEqual(private.read_text(encoding='utf-8'),'NOT A DIAGNOSTIC')

    def test_export_cannot_write_inside_source_logs(self):
        root=self.new_studio();self._fake_operation(root,'source')
        with self.assertRaisesRegex(ProductionError,'LOG_EXPORT_PATH_INVALID'):
            ops.export_logs(root,root/'logs/operations/diagnostics')

    def test_forced_exit_leaves_detectable_incomplete_operation(self):
        import subprocess,sys
        code="import operation_context as o,os;op=o.Operation('synthetic-force-exit');os._exit(0)"
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join([str(Path(__file__).resolve().parent), env.get('PYTHONPATH', '')])
        result=subprocess.run([sys.executable,'-c',code],env=env,timeout=15)
        self.assertEqual(result.returncode,0)
        rows=ops.list_operations()
        self.assertEqual(len(rows),1);self.assertFalse(rows[0]['complete'])

    def test_unwritable_user_directory_record_is_rebuilt_in_the_studio(self):
        root = self.new_studio()
        blocked = self.home/'blocked'; blocked.write_text('a file, not a directory', encoding='utf-8')
        warnings = io.StringIO()
        def command():
            parser = ops.ArgumentParser(); parser.add_argument('--root', type=Path)
            parser.parse_args(['--root', str(root)])
            ops.current().durable()
            print(json.dumps({'ok': True}))
        with patch.dict(os.environ, {'CPB_HOME': str(blocked/'home')}), \
                patch.object(sys, '__stderr__', warnings):
            code, stdout, stderr = self.invoke(command)
        self.assertEqual((code, json.loads(stdout), stderr), (0, {'ok': True}, ''))
        self.assertEqual(warnings.getvalue(), '')
        row, folder, events = self.records(root)
        self.assertEqual({path.name for path in folder.iterdir()}, ops._LOG_FILES)
        self.assertTrue(row['log_complete'])
        self.assertEqual([e['event'] for e in events][:2], ['started', 'stage_started'])
        self.assertIn('user_log_unavailable', [e['event'] for e in events])
        self.assertEqual(json.loads((folder/'stdout.log').read_text(encoding='utf-8')), {'ok': True})

    def test_help_and_argument_errors_are_exits_not_stage_failures(self):
        def help_command():
            parser = ops.ArgumentParser(prog='synthetic'); parser.add_argument('--root'); parser.parse_args(['--help'])
        code, stdout, _ = self.invoke(help_command)
        self.assertEqual(code, 0); self.assertIn('--root', stdout)
        events = self.records()[2]
        self.assertNotIn('stage_failed', [e['event'] for e in events])
        self.assertNotIn('diagnostic', events[-1])
        self.assertEqual(events[-1]['exit_code'], 0)
        for folder in self.home.glob('logs/operations/*/*'):
            for path in folder.iterdir(): path.unlink()
            folder.rmdir()
        def wrong_command():
            parser = ops.ArgumentParser(prog='synthetic'); parser.add_argument('--root', required=True); parser.parse_args([])
        self.assertEqual(self.invoke(wrong_command)[0], 2)
        events = self.records()[2]
        self.assertNotIn('stage_failed', [e['event'] for e in events])
        exited = next(e for e in events if e['event'] == 'stage_exited')
        self.assertEqual(exited['exit_code'], 2)
        self.assertEqual(events[-1]['exit_code'], 2)
        self.assertEqual((events[-1]['diagnostic']['code'], events[-1]['diagnostic']['message']),
                         ('INPUT_ARGUMENT_INVALID', 'Arguments do not match the command interface; consult --help.'))

    def test_child_process_records_its_parent_operation(self):
        parent = {}
        def command():
            parent['id'] = ops.current_operation_id()
            env = dict(os.environ)
            env['PYTHONPATH'] = os.pathsep.join([str(SCRIPTS), env.get('PYTHONPATH', '')])
            child = 'import operation_context as o\nraise SystemExit(o.run_cli(lambda: 0))'
            subprocess.run([sys.executable, '-c', child], env=env, timeout=60, check=True)
        self.assertEqual(self.invoke(command)[0], 0)
        self.assertNotIn(ops.PARENT_VARIABLE, os.environ)
        rows = {row['operation_id']: row['metadata'] for row in ops.list_operations()}
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[parent['id']]['parent_operation'])
        child = next(value for key, value in rows.items() if key != parent['id'])
        self.assertEqual(child['parent_operation'], parent['id'])

    def test_candidate_and_execution_links_accumulate(self):
        def command():
            operation = ops.current()
            for candidate, execution in (('a' * 64, 'r-1'), ('b' * 64, 'r-2'), ('a' * 64, 'r-1')):
                operation.link(run='synthetic-run', candidate=candidate, execution=execution)
        self.assertEqual(self.invoke(command)[0], 0)
        context = self.records()[0]['metadata']['context']
        self.assertEqual(context['candidates'], ['a' * 64, 'b' * 64])
        self.assertEqual(context['executions'], ['r-1', 'r-2'])
        self.assertEqual(context['run'], 'synthetic-run')

    def test_registered_credential_is_absent_from_logs_and_export(self):
        root = self.new_studio()
        key = 'synthetic-host-config-key-0123456789abcdef'
        def command():
            parser = ops.ArgumentParser(); parser.add_argument('--root', type=Path)
            parser.parse_args(['--root', str(root)])
            ops.register_secret(key)
            sys.stdout.write('{"note": "sent with ' + key[:11]); sys.stdout.write(key[11:] + '"}\n')
            print('provider said ' + key, file=sys.stderr)
            ops.current().event('transport_detail', detail='header carried ' + key)
            with ops.stage('provider-wait'):
                raise ValueError('provider rejected ' + key)
        code, stdout, stderr = self.invoke(command)
        self.assertEqual(code, 2)
        self.assertNotIn(key, json.loads(stdout.splitlines()[-1])['diagnostics'][0]['message'])
        _, folder, events = self.records(root)
        self.assertNotIn(key, every_log_text(folder))
        self.assertIn('[REDACTED]', (folder/'stdout.log').read_text(encoding='utf-8'))
        self.assertTrue(any(e['event'] == 'stage_failed' for e in events))
        ops.export_logs(root, root/'diagnostics')
        self.assertNotIn(key, every_log_text(root/'diagnostics'))

    def test_credential_names_and_values_do_not_over_redact(self):
        for name in ('OPENAI_API_KEY', 'Authorization', 'x-amz-security-token', 'client_secret', 'accessToken', 'apiKey'):
            self.assertTrue(ops.secret_name(name), name)
        for name in ('max_tokens', 'prompt_tokens', 'TOKENIZERS_PARALLELISM', 'sort_key', 'tokenizer'):
            self.assertFalse(ops.secret_name(name), name)
        values = {'TOKENIZERS_PARALLELISM': 'false', 'CPB_SYNTHETIC_TOKEN': '1234567890',
                  'CPB_SYNTHETIC_SECRET': 'short', 'CPB_SYNTHETIC_PASSWORD': 'synthetic-long-password'}
        with patch.dict(os.environ, values):
            known = ops.known_secrets()
            self.assertIn('synthetic-long-password', known)
            self.assertFalse({'false', '1234567890', 'short'} & set(known))
            def command():
                print(json.dumps({'max_tokens': 4096, 'enabled': 'false', 'count': 1234567890, 'access_token': 'abc'}))
            self.assertEqual(self.invoke(command)[0], 0)
        logged = json.loads((self.records()[1]/'stdout.log').read_text(encoding='utf-8'))
        self.assertEqual(logged, {'max_tokens': 4096, 'enabled': 'false', 'count': 1234567890, 'access_token': '[REDACTED]'})

    def test_work_content_fields_are_omitted(self):
        names = ('terms', 'rendition', 'prompt_expression', 'negative', 'positive', 'lines', 'chunk', 'definition')
        document = {name: 'PRIVATE WORK TEXT' for name in names} | {'code': 'TAG_CHECKED'}
        self.assertEqual({k: v for k, v in ops.safe_value(document).items() if v == 'PRIVATE WORK TEXT'}, {})
        output = io.StringIO(); writer = ops.RedactingWriter(output.write, ())
        writer.write(json.dumps(document)); writer.flush(final=True)
        self.assertNotIn('PRIVATE WORK TEXT', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['code'], 'TAG_CHECKED')

    def test_chunked_and_whole_redaction_agree(self):
        document = json.dumps({'name': '한국어 캐릭터', 'api\\key': 'PRIVATE-A', 'nested': {'password': [1, {'x': '"]}'}], 'ok': True},
                               'escaped': 'quote \\" and colon : here', 'prompt': {'text': ['PRIVATE-B']}, 'count': 3,
                               'url': 'https://example.invalid/a?signature=PRIVATE-C&size=2'}, ensure_ascii=False)
        results = []
        for size in (1, 7, 64, len(document)):
            output = io.StringIO(); writer = ops.RedactingWriter(output.write, ())
            for offset in range(0, len(document), size): writer.write(document[offset:offset + size])
            writer.flush(final=True); results.append(output.getvalue())
        self.assertEqual(len(set(results)), 1)
        restored = json.loads(results[0])
        self.assertEqual(restored['name'], '한국어 캐릭터')
        self.assertEqual((restored['nested']['password'], restored['nested']['ok']), ('[REDACTED]', True))
        self.assertEqual((restored['prompt'], restored['count']), ('[REDACTED]', 3))
        self.assertEqual(restored['escaped'], 'quote \\" and colon : here')
        self.assertNotIn('PRIVATE', results[0])

    def test_export_states_console_content_and_can_leave_streams_out(self):
        root = self.new_studio(); folder = self._fake_operation(root, 'printed')
        secret = 'synthetic-api-key-written-before-registration'
        (folder/'stdout.log').write_text('tag check terms: red scarf, ' + secret + '\n', encoding='utf-8')
        with patch.dict(os.environ, {'CPB_SYNTHETIC_API_KEY': secret}):
            full = ops.export_logs(root, root/'full')
            lean = ops.export_logs(root, root/'lean', include_streams=False)
        self.assertIn('printed/stdout.log', full['included'])
        self.assertIn('stdout.log', full['work_content'])
        self.assertNotIn(secret, every_log_text(root/'full'))
        self.assertIn('red scarf', (root/'full/printed/stdout.log').read_text(encoding='utf-8'))
        self.assertEqual(sorted(path.name for path in (root/'lean/printed').iterdir()),
                         ['artifacts.json', 'events.jsonl', 'operation.json'])
        self.assertIn('stdout.log and stderr.log console output', lean['excluded'])
        self.assertFalse(any(name.endswith('.log') for name in lean['included']))
        for manifest in (full, lean):
            self.assertEqual(set(manifest), {'included', 'excluded', 'work_content', 'redaction', 'limitations',
                                             'incomplete_operations', 'omissions'})
        self.assertEqual(json.loads((root/'lean/export.json').read_text(encoding='utf-8')), lean)

    def test_query_of_a_run_is_not_an_operation_of_that_run(self):
        import production_workflow
        root = self.new_studio(); self._fake_operation(root, 'prepared-it', run='synthetic-run')
        argv = ['production_workflow.py', 'logs', '--root', str(root), '--run', 'synthetic-run']
        listed = []
        for _ in range(2):
            with patch.object(sys, 'argv', argv):
                code, stdout, _ = self.invoke(production_workflow.main)
            self.assertEqual(code, 0)
            listed.append([row['operation_id'] for row in json.loads(stdout)['operations']])
        self.assertEqual(listed, [['prepared-it'], ['prepared-it']])
        queries = [row for row in ops.list_operations(root) if row['operation_id'] != 'prepared-it']
        self.assertEqual(len(queries), 2)
        for row in queries:
            self.assertEqual(row['metadata']['context']['query_run'], 'synthetic-run')
            self.assertNotIn('run', row['metadata']['context'])

    def test_failed_listing_leaves_out_operations_waiting_for_authority(self):
        root = self.new_studio()
        for name, code in (('succeeded', 0), ('invalid', 2), ('waiting', ops.WAITING_EXIT), ('incomplete-send', 4)):
            self._fake_operation(root, name, exit_code=code)
        self._fake_operation(root, 'killed', completed=False)
        failed = sorted(row['operation_id'] for row in ops.list_operations(root, failed=True))
        self.assertEqual(failed, ['incomplete-send', 'invalid', 'killed'])

    def test_user_directory_logs_are_listed_exported_and_cleaned_without_a_studio(self):
        self._fake_operation(self.home, 'outside-studio')
        self.assertEqual([row['operation_id'] for row in ops.list_operations(None)], ['outside-studio'])
        manifest = ops.export_logs(None, self.home/'shared diagnostics')
        self.assertIn('outside-studio/events.jsonl', manifest['included'])
        with self.assertRaisesRegex(ProductionError, 'LOG_EXPORT_PATH_INVALID'):
            ops.export_logs(None, self.home/'logs/operations/inside')
        result = ops.cleanup_logs(None, before='2001-01-01', apply=True)
        self.assertEqual(result['deleted'], ['outside-studio'])
        self.assertEqual(ops.list_operations(None), [])

    def dead_pid(self):
        process = subprocess.Popen([sys.executable, '-c', 'pass']); process.wait()
        return process.pid

    def test_killed_operation_before_cutoff_is_closed_once_its_process_ended(self):
        root = self.new_studio(); pid = self.dead_pid()
        killed = self._fake_operation(root, 'killed', completed=False, pid=pid)
        (killed/'.operation.json.tmp').write_text('{"partial', encoding='utf-8')
        self._fake_operation(root, 'running', completed=False, pid=os.getpid())
        self._fake_operation(root, 'killed-during-send', completed=False, pid=pid, run='synthetic-run')
        self._fake_operation(root, 'killed-today', completed=False, pid=pid, created=ops.timestamp())
        with patch.object(ops, '_run_has_unresolved_external_effect', return_value=True):
            by_operation = ops.cleanup_logs(root, operation_id='killed')
            plan = ops.cleanup_logs(root, before='2001-01-01')
            applied = ops.cleanup_logs(root, before='2001-01-01', apply=True)
        self.assertEqual(by_operation['protected'][0]['reason'], 'incomplete-operation')
        reasons = {row['operation_id']: row['reason'] for row in plan['candidates'] + plan['protected']}
        self.assertEqual(reasons, {'killed': 'abandoned-incomplete', 'running': 'incomplete-operation',
                                   'killed-during-send': 'remote-outcome-unresolved'})
        self.assertEqual(applied['deleted'], ['killed']); self.assertFalse(killed.exists())
        self.assertEqual(sorted(row['operation_id'] for row in ops.list_operations(root)),
                         ['killed-during-send', 'killed-today', 'running'])

    def test_interrupted_metadata_rewrite_keeps_the_previous_file(self):
        warnings = io.StringIO()
        def command():
            with patch.object(ops, '_replace', side_effect=disk_full):
                ops.current().link(task='synthetic-task')
        with patch.object(sys, '__stderr__', warnings):
            self.assertEqual(self.invoke(command)[0], 0)
        row, folder, events = self.records()
        self.assertNotIn('task', row['metadata']['context'])
        self.assertEqual(sorted(path.name for path in folder.iterdir()), sorted(ops._LOG_FILES))
        self.assertEqual((events[-1]['complete'], events[-1]['log_failures']), (False, ['OSError:ENOSPC']))
        self.assertIn('LOG_WRITE_FAILED', warnings.getvalue())

    def test_registered_artifacts_follow_a_published_directory(self):
        import execution_contract as c
        staging, target = self.home/'staging/compile-synthetic', self.home/'runs/synthetic'
        def command():
            c.atomic(staging/'manifest.json', b'{"synthetic": true}\n')
            c.atomic(staging/'objects/item.json', b'{"bytes": 2}\n')
            target.parent.mkdir(parents=True)
            c.publish_directory(staging, target)
            ops.relocate_artifacts(staging, target)
        self.assertEqual(self.invoke(command)[0], 0)
        _, folder, events = self.records()
        listed = json.loads((folder/'artifacts.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(entry['path'] for entry in listed),
                         [str(target/'manifest.json'), str(target/'objects/item.json')])
        for entry in listed:
            self.assertEqual(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest(), entry['sha256'])
        self.assertNotIn('artifacts_withdrawn', [e['event'] for e in events])


class ProductionOperationTests(unittest.TestCase):
    """Operation records around real synthetic prepare and execute calls."""

    def setUp(self):
        import production_case_fixtures as fixtures
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        env = production_fixtures.scratch_home(base/'home')
        env.start(); self.addCleanup(env.stop)
        self.root = fixtures.create(base/'studio', base/'runtime')['root']
        self.warnings = io.StringIO()
        warnings = patch.object(sys, '__stderr__', self.warnings)
        warnings.start(); self.addCleanup(warnings.stop)

    def cli(self, *arguments):
        import production_workflow
        stdout = io.StringIO()
        with patch.object(sys, 'argv', ['production_workflow.py', *arguments]), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = ops.run_cli(production_workflow.main)
        return code, stdout.getvalue()

    def test_prepare_records_stages_and_existing_artifacts(self):
        code, stdout = self.cli('prepare', '--root', str(self.root), '--task', 'task.json')
        self.assertEqual(code, 0, stdout)
        run = json.loads(stdout)['run']
        rows = ops.list_operations(self.root, run=run)
        self.assertEqual(len(rows), 1); self.assertTrue(rows[0]['log_complete'])
        folder = Path(rows[0]['path'])
        names = [e['event'] for e in events_of(folder)]
        self.assertEqual((names[0], names[-1]), ('started', 'completed'))
        self.assertIn('stage_completed', names)
        listed = json.loads((folder/'artifacts.json').read_text(encoding='utf-8'))
        for entry in listed:
            self.assertEqual(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest(), entry['sha256'], entry['path'])
        published = {Path(entry['path']).name for entry in listed if Path(entry['path']).parent.name == run}
        self.assertLessEqual({'manifest.json', 'package.json', 'request-preview.json', 'execution-plan.json', 'prepared.json'}, published)

    def test_console_log_failure_after_the_result_keeps_the_formal_run(self):
        import production_execution
        import production_store as store
        original = ops.Operation._store
        def store_without_console(operation, name, raw, *, append):
            if name == 'stdout.log' and raw:
                disk_full()
            return original(operation, name, raw, append=append)
        with patch.object(ops.Operation, '_store', store_without_console):
            code, stdout = self.cli('prepare', '--root', str(self.root), '--task', 'task.json')
        self.assertEqual(code, 0, stdout)
        run = json.loads(stdout)['run']
        self.assertEqual([row['run_id'] for row in store.runs(self.root)], [run])
        self.assertEqual(production_execution.status(self.root, run)['runs'][0]['integrity'], 'intact')
        row = ops.list_operations(self.root, run=run)[0]
        self.assertEqual((row['complete'], row['exit_code'], row['log_complete']), (True, 0, False))
        self.assertEqual(events_of(Path(row['path']))[-1]['log_failures'], ['OSError:ENOSPC'])
        self.assertEqual([r['operation_id'] for r in ops.list_operations(self.root, failed=True)], [row['operation_id']])

    def test_disk_full_before_send_stops_execution_and_stays_incomplete(self):
        import production_execution as execution
        import production_store as store
        import production_workflow as workflow
        import transport_synthetic
        from test_production_execution import decisions
        run = workflow.prepare(self.root, 'task.json')['run']
        path = decisions(self.root, run)
        original = ops.Operation._store
        state = {'full': False}
        def store_until_full(operation, name, raw, *, append):
            if state['full']:
                disk_full()
            return original(operation, name, raw, append=append)
        def command():
            state['full'] = True
            execution.execute(self.root, run, decisions_file=path)
        stdout = io.StringIO()
        with patch.object(ops.Operation, '_store', store_until_full), \
                patch.object(transport_synthetic, 'send', side_effect=AssertionError('no send after a log failure')), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = ops.run_cli(command)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())['diagnostics'][0]['code'], 'LOG_WRITE_FAILED')
        self.assertFalse(any(row['event'] == 'dispatch-claim' for row in store.event_rows(self.root, run)))
        rows = ops.list_operations()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['complete'], rows[0]['log_complete']), (False, False))
        self.assertNotIn('completed', [e['event'] for e in events_of(Path(rows[0]['path']))])
        self.assertIn('LOG_WRITE_FAILED', self.warnings.getvalue())

    def cleanup_candidates(self, root, run, name):
        folder = OperationTests._fake_operation(self, root, name, run=run)
        listed = ops.cleanup_logs(root, operation_id=folder.name)
        return [row['operation_id'] for row in listed['candidates']]

    def test_send_evidenced_as_not_executed_releases_log_protection(self):
        import production_case_fixtures as fixtures
        import production_execution as execution
        import production_store as store
        import production_workflow as workflow
        import execution_lifecycle as accounting
        import transport_synthetic
        import execution_contract as c
        from test_production_execution import decisions
        run = workflow.prepare(self.root, 'task.json')['run']
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic timeout')):
            execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertTrue(ops._run_has_unresolved_external_effect(self.root, run))
        self.assertEqual(self.cleanup_candidates(self.root, run, 'timed-out-send'), [])
        statement = execution.draft_outcome(self.root, run)
        fixtures.write(self.root/'provider-task-list.txt', 'Synthetic provider task export: no task with this identifier.\n')
        actor = store.authority(self.root, workflow.load_run(self.root, run)[1]['task']['task_id'])['issuer']
        statement.update(actor=actor, reason='The provider task list holds no task for this request.',
                         evidence={'path': 'provider-task-list.txt', 'locator': 'whole export',
                                   'sha256': c.sha256_file(self.root/'provider-task-list.txt')})
        fixtures.write(self.root/'outcome.json', statement)
        execution.resume(self.root, run, outcome_file='outcome.json')
        self.assertFalse(ops._run_has_unresolved_external_effect(self.root, run))
        self.assertEqual(self.cleanup_candidates(self.root, run, 'stated-not-executed'), ['stated-not-executed'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
