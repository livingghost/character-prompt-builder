#!/usr/bin/env python3
"""Regression tests for complete material and caller-owned budgets.

Fixtures are synthetic bytes and a local Python process, not model-quality evidence.
Large dimensions are validated without allocating a large decoded canvas.
"""
from __future__ import annotations
import copy
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import agent_evaluation as agent
import artifact_review
import authorial_intent_audit as intent
import execution_contract as contract
import io_budget as budget
import material_support as material


ROOT = Path(__file__).resolve().parents[1]


class CompleteMaterialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_source_above_32_mib_is_not_rejected_or_clipped(self):
        raw = b'a' * (33 * 1024 * 1024) + b'\nAUTHOR-END'
        path = self.root / 'source.txt'; path.write_bytes(raw)
        self.assertEqual(material.read(path), raw)
        self.assertEqual(contract.read(path), raw)
        self.assertEqual(budget.file_identity(path), {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})

    def test_large_json_keeps_last_property(self):
        data = {'definition': 'a' * (33 * 1024 * 1024), 'final_condition': 'must survive'}
        path = self.root / 'document.json'; path.write_bytes(material.encoded(data))
        self.assertEqual(material.load(self.root, 'document.json'), data)
        self.assertEqual(contract.load(path), data)

    def test_explicit_read_budget_refuses_instead_of_returning_prefix(self):
        path = self.root / 'source'; path.write_bytes(b'abcdef')
        self.assertEqual(material.read(path, 6), b'abcdef')
        with self.assertRaisesRegex(ValueError, 'explicitly supplied'):
            material.read(path, 5)
        self.assertEqual(path.read_bytes(), b'abcdef')

    def test_invalid_read_budgets_rejected(self):
        for value in (True, False, 0, -1, 1.5, '20'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.read_stream(io.BytesIO(b'abc'), value)

    def test_explicit_deadline_validation(self):
        for value in (True, False, 0, -1, float('nan'), float('inf'), '4'):
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                budget.optional_seconds(value, 'deadline')
        self.assertIsNone(budget.optional_seconds(None, 'deadline'))
        self.assertEqual(budget.optional_seconds(200000, 'deadline'), 200000)

    def test_environment_deadline_has_no_guessed_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(budget.environment_seconds('PRODUCTION_HTTP_TIMEOUT_SECONDS'))
        with patch.dict(os.environ, {'PRODUCTION_HTTP_TIMEOUT_SECONDS': '15.5'}):
            self.assertEqual(budget.environment_seconds('PRODUCTION_HTTP_TIMEOUT_SECONDS'), 15.5)
        with patch.dict(os.environ, {'PRODUCTION_HTTP_TIMEOUT_SECONDS': 'NaN'}):
            with self.assertRaises(ValueError): budget.environment_seconds('PRODUCTION_HTTP_TIMEOUT_SECONDS')

    def test_streaming_identity_does_not_call_read_bytes(self):
        path = self.root / 'source'; path.write_bytes(b'x' * 2097153)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('whole-file allocation')):
            self.assertEqual(budget.file_identity(path)['bytes'], 2097153)

    def test_symbolic_link_input_is_still_refused(self):
        path = self.root / 'source'; path.write_bytes(b'actual')
        link = self.root / 'link'
        try: link.symlink_to(path)
        except (OSError, NotImplementedError): self.skipTest('symbolic links unavailable')
        with self.assertRaises(ValueError): material.read(link)
        with self.assertRaises(ValueError): budget.file_identity(link)

    def test_escaping_studio_path_is_refused(self):
        with self.assertRaises(ValueError): material.local(self.root, '../outside')

    def test_complete_review_text_and_original_attachment(self):
        text = '정의와 예외.' * 8000 + '\nFINAL-EXCEPTION'
        raw = text.encode('utf-8'); files = {}
        item = {'path': 'candidate.txt', 'sha256': material.digest(raw), 'size': len(raw)}
        with patch.object(contract, 'object_read', return_value=raw):
            view = artifact_review._object_file(self.root, item, files)
        self.assertEqual(view['preview'], text)
        self.assertFalse(view['preview_truncated'])
        self.assertEqual(files[view['download']], raw)

    def test_explicit_preview_counts_unicode_characters_not_bytes(self):
        raw = '甲乙丙丁'.encode('utf-8'); files = {}
        item = {'path': 'candidate.txt', 'sha256': material.digest(raw), 'size': len(raw)}
        with patch.object(contract, 'object_read', return_value=raw):
            view = artifact_review._object_file(self.root, item, files, preview_chars=2)
        self.assertEqual(view['preview'], '甲乙')
        self.assertTrue(view['preview_truncated'])
        self.assertEqual(files[view['download']], raw)

    def test_complete_authorial_dependency_closure_over_128_files(self):
        # The author explicitly supplied the scope, so no discovery inference is tested.
        for i in range(130): (self.root / f'intent-{i}.md').write_text('# Authored scope\n', encoding='utf-8')
        names = [f'intent-{i}.md' for i in range(130)]
        result = intent.audit(self.root, names)
        self.assertTrue(result['ok'], result['errors'])
        self.assertEqual(len(result['files']), 130)
        limited = intent.audit(self.root, names, max_files=3)
        self.assertFalse(limited['ok'])
        self.assertEqual(len(limited['files']), 3)
        self.assertIn('audit incomplete', json.dumps(limited['errors']))

    def test_large_authorial_document_is_read_to_end(self):
        path = self.root / 'intent.md'; path.write_text('# Source\n' + 'a' * (5 * 1024 * 1024) + '\nEND', encoding='utf-8')
        result = intent.audit(self.root, ['intent.md'])
        self.assertTrue(result['ok'], result['errors'])
        self.assertEqual(result['files'][0]['size_bytes'], path.stat().st_size)

    def test_large_definition_is_valid_without_schema_text_ceiling(self):
        # Test the actual schema fragments for open-ended authored strings.
        import state_protocol
        path = ROOT / 'protocols/shared-state/schemas/scene-persona-material.schema.json'
        schema = json.loads(path.read_text(encoding="utf-8"))
        def nodes(value):
            if isinstance(value, dict):
                yield value
                for v in value.values(): yield from nodes(v)
            elif isinstance(value, list):
                for v in value: yield from nodes(v)
        strings = [v for v in nodes(schema) if v.get('type') == 'string' and not any(k in v for k in ('enum','const','pattern','format'))]
        self.assertTrue(strings)
        text = 'authored condition ' * 10000
        for node in strings:
            self.assertNotIn('maxLength', node)
            self.assertEqual(state_protocol.validate_against_schema(text, node), [])


class ExecutionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name)
        (self.root / 'prompt.txt').write_text('Fixture only.', encoding='utf-8')
        (self.root / 'host.py').write_text("import pathlib,sys\npathlib.Path(sys.argv[1], 'result.txt').write_text('complete', encoding='utf-8')\n", encoding='utf-8')
        self.study = {'purpose':'Synthetic budget mechanics, not model performance','repetitions':1,
            'cases':[{'id':'case','prompt':'prompt.txt','inputs':['host.py'],'expected_outputs':['result.txt'],'criteria':['Human review remains separate']}],
            'conditions':[{'id':'host','host_label':'Python fixture','model_label':'none','argv':[sys.executable,'inputs/host.py','{outputs}'],'skill':None,'timeout_seconds':None,
                'metrics':{'match_pointer':'/event','match_value':'metrics','pointers':{'total_tokens':'/total_tokens'}}}]}

    def tearDown(self): self.temporary.cleanup()

    def run_fixture(self):
        (self.root / 'study.json').write_bytes(material.encoded(self.study))
        _, plan = agent.plan_study(self.root, 'study.json', 'evaluation')
        result = agent.run_study(self.root, 'study.json', 'evaluation', plan['content_sha256'])
        return result, material.load(self.root, result['runs'][0]['result'])

    def test_declared_repetitions_and_deadline_are_not_capped(self):
        self.study['repetitions'] = 101
        self.study['conditions'][0]['timeout_seconds'] = 200000
        agent.validate_study(self.study)
        self.study['conditions'][0]['timeout_seconds'] = None
        agent.validate_study(self.study)
        # No model or 101-process benchmark is launched by plan validation.

    def test_invalid_log_budget_is_not_silently_coerced(self):
        for value in (False,0,-1,'32',3.5):
            self.study['conditions'][0]['max_log_bytes'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): agent.validate_study(self.study)

    def test_log_over_32_mib_preserves_tail_metric_and_output(self):
        script = """import json,pathlib,sys
out=pathlib.Path(sys.argv[1]); (out/'result.txt').write_text('complete output', encoding='utf-8')
for _ in range(33): sys.stdout.write('x'*1048576+'\\n')
print(json.dumps({'event':'metrics','total_tokens':123}))
"""
        (self.root / 'host.py').write_text(script, encoding='utf-8')
        result, receipt = self.run_fixture()
        self.assertTrue(result['ok'], receipt)
        log = receipt['logs'][0]
        self.assertGreater(log['bytes'], 32 * 1024 * 1024)
        self.assertFalse(log['truncated']); self.assertFalse(log['operator_budget_exceeded'])
        self.assertEqual(receipt['measurements']['total_tokens'], 123)
        self.assertEqual(receipt['quality_verdict'], 'not-reviewed')
        self.assertEqual(budget.file_identity(self.root / log['path'])['sha256'], log['sha256'])

    def test_explicit_small_log_budget_keeps_emitted_bytes_and_fails(self):
        (self.root / 'host.py').write_text("import pathlib,sys\npathlib.Path(sys.argv[1],'result.txt').write_text('complete', encoding='utf-8')\nsys.stdout.buffer.write(b'x'*4096+b'\\n')\n", encoding='utf-8')
        self.study['conditions'][0]['max_log_bytes'] = 64
        result, receipt = self.run_fixture()
        self.assertFalse(result['ok']); self.assertEqual(receipt['status'], 'log-limit')
        self.assertEqual((self.root / receipt['logs'][0]['path']).read_bytes(), b'x'*4096+b'\n')
        self.assertFalse(receipt['logs'][0]['truncated'])
        self.assertTrue(receipt['logs'][0]['operator_budget_exceeded'])


class ProductConstraintTests(unittest.TestCase):
    def test_real_tuple_geometry_still_has_fixed_arity(self):
        import state_protocol
        schema = {'type':'array','minItems':4,'maxItems':4,'items':{'type':'number'}}
        self.assertEqual(state_protocol.validate_against_schema([0,0,1,1],schema), [])
        self.assertTrue(state_protocol.validate_against_schema([0,0,1],schema))

    def test_specific_service_constraint_is_preserved(self):
        import state_protocol
        schema = {'type':'integer','minimum':128,'maximum':2048}
        self.assertTrue(state_protocol.validate_against_schema(4096,schema))
        self.assertEqual(state_protocol.validate_against_schema(1024,schema), [])

    def test_image_plan_no_universal_pixel_ceiling(self):
        if not (ROOT/'scripts/image_edit.py').exists(): self.skipTest('not a still-image editor')
        import image_edit
        self.assertEqual(image_edit.dimensions(10000,10000),(10000,10000))
        with self.assertRaises(ValueError): image_edit.dimensions(0,100)
        with self.assertRaises(ValueError): image_edit.dimensions(True,100)

    def test_search_variations_are_not_silently_shortened(self):
        if not (ROOT/'scripts/search_discovery.py').exists(): self.skipTest('no record-discovery adapter')
        import search_discovery
        values = [f'authored variation {i}' for i in range(50)]
        self.assertEqual(search_discovery._compact_variations(values), values)




class ChildProcessDeadlineTests(unittest.TestCase):
    def isolated_worker(self, environment, run):
        import search_regression
        from types import SimpleNamespace
        with patch.dict(os.environ, environment):
            if not environment:
                os.environ.pop('SEARCH_REGRESSION_TIMEOUT_SECONDS', None)
            with patch.object(search_regression.subprocess, 'run', run):
                return search_regression._run_isolated_worker(0, 1, SimpleNamespace(command_arguments=list))

    def test_search_worker_runs_to_completion_without_an_operator_deadline(self):
        from types import SimpleNamespace
        seen = {}
        def completed(command, **kwargs):
            seen['timeout'] = kwargs.get('timeout')
            return SimpleNamespace(returncode=0, stdout='{"ok": true, "cases": 1}', stderr='')
        result = self.isolated_worker({}, completed)
        self.assertIsNone(seen['timeout']); self.assertEqual((0, {'ok': True, 'cases': 1}), (result[2], result[5]))

    def test_search_worker_stops_at_the_operator_deadline(self):
        import subprocess
        seen = {}
        def timed_out(command, **kwargs):
            seen['timeout'] = kwargs.get('timeout')
            raise subprocess.TimeoutExpired(command, kwargs.get('timeout'))
        result = self.isolated_worker({'SEARCH_REGRESSION_TIMEOUT_SECONDS': '0.5'}, timed_out)
        self.assertEqual(0.5, seen['timeout']); self.assertEqual((-1, None), (result[2], result[5]))

    def test_example_commands_and_search_workers_set_no_deadline_of_their_own(self):
        import ast
        fixed = []
        for path in [*sorted(ROOT.glob('examples/*/*.py')), ROOT / 'scripts/search_regression.py',
                     ROOT / 'scripts/validate_state_protocol.py', ROOT / 'scripts/production_evidence.py']:
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.keyword) and node.arg == 'timeout' and isinstance(node.value, ast.Constant) and node.value.value is not None:
                    fixed.append(f'{path.relative_to(ROOT).as_posix()}:{node.value.lineno}')
        self.assertEqual([], fixed)


class TransientRefusalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_refusal_classification(self):
        self.assertTrue(contract._transient_refusal(PermissionError(13, 'denied')))
        locked = OSError('locked'); locked.winerror = 32
        self.assertTrue(contract._transient_refusal(locked))
        self.assertFalse(contract._transient_refusal(FileExistsError(17, 'exists')))

    def test_patiently_retries_a_transient_refusal(self):
        calls = []
        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError(13, 'denied')
        with patch.object(contract.time, 'sleep', lambda _: None):
            contract._patiently(flaky)
        self.assertEqual(2, len(calls))

    def test_patiently_gives_up_after_the_budget(self):
        def refused():
            raise PermissionError(13, 'denied')
        moments = itertools.chain([0.0, 5.0], itertools.repeat(20.0))
        with patch.object(contract.time, 'sleep', lambda _: None), \
             patch.object(contract.time, 'monotonic', lambda: next(moments)):
            with self.assertRaises(PermissionError):
                contract._patiently(refused)

    def test_patiently_raises_other_errors_at_once(self):
        def broken():
            raise FileExistsError(17, 'exists')
        with self.assertRaises(FileExistsError):
            contract._patiently(broken)

    def test_atomic_replace_outlasts_a_transient_rename_refusal(self):
        target = self.root / 'rows.jsonl'
        target.write_bytes(b'old\n')
        real_replace = os.replace
        calls = []
        def flaky(source, destination):
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError(13, 'Access is denied')
            return real_replace(source, destination)
        with patch.object(contract.os, 'replace', flaky), patch.object(contract.time, 'sleep', lambda _: None):
            contract.atomic(target, b'new\n', replace=True)
        self.assertEqual(b'new\n', target.read_bytes())
        self.assertEqual(2, len(calls))

def _file_lock_process(path, pipe, hold=False):
    """Coordinate the process test through a pipe, using only its real data file."""
    try:
        pipe.send('waiting')
        with contract.file_lock(Path(path)):
            pipe.send('acquired')
            if hold:
                pipe.recv()
    finally:
        pipe.close()


class DataFileLockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'state.json'
        self.path.write_bytes(b'{"value":0}\n')

    @unittest.skipUnless(os.name == 'nt', 'Windows path aliases')
    def test_lock_key_normalizes_short_parent_names(self):
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(str(self.root), buffer, len(buffer))
        alias = Path(buffer.value) if length else self.root
        self.assertEqual(contract._file_lock_key(alias / self.path.name),
                         contract._file_lock_key(self.path))

    def test_nested_updates_keep_data_and_release_all_handles(self):
        streams = []
        original = contract._open_lock_stream
        def opening(path, **options):
            stream = original(path, **options); streams.append(stream); return stream
        with patch.object(contract, '_open_lock_stream', opening):
            with contract.file_lock(self.path):
                for value in range(8):
                    with contract.file_lock(self.path):
                        contract.atomic_write_json(self.path, {'value': value})
                    self.assertLessEqual(sum(not stream.closed for stream in streams), 2)
                self.assertEqual(contract.load(self.path), {'value': 7})
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertEqual({path.name for path in self.root.iterdir()}, {'state.json'})

    def test_thread_waits_through_atomic_replacement(self):
        import threading
        acquired = threading.Event()
        errors = []

        def waiting():
            try:
                with contract.file_lock(self.path):
                    acquired.set()
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=waiting, daemon=True)
        with contract.file_lock(self.path):
            thread.start()
            self.assertFalse(acquired.wait(0.05))
            contract.atomic_write_json(self.path, {'value': 2})
            self.assertFalse(acquired.wait(0.05))
        self.assertTrue(acquired.wait(5))
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(contract.load(self.path), {'value': 2})

    def test_waiters_follow_replacements_until_the_update_finishes(self):
        import threading
        opened, current_opened = threading.Event(), threading.Event()
        entered, fresh_entered = threading.Event(), threading.Event()
        errors = []
        original = contract._open_lock_stream
        old_stream = None
        first = True
        def opening(path, **options):
            nonlocal first
            if Path(path) == self.path and threading.current_thread().name == 'old-inode-waiter':
                if first:
                    first = False; opened.set(); return old_stream
                current_opened.set()
            return original(path, **options)
        def waiting(done):
            try:
                with contract.file_lock(self.path): done.set()
            except BaseException as exc:
                errors.append(exc)
        old = threading.Thread(target=waiting, args=(entered,), name='old-inode-waiter', daemon=True)
        fresh = threading.Thread(target=waiting, args=(fresh_entered,), daemon=True)
        try:
            with patch.object(contract, '_open_lock_stream', opening):
                with contract.file_lock(self.path):
                    old_stream = original(self.path)
                    old.start(); self.assertTrue(opened.wait(5))
                    contract.atomic_write_json(self.path, {'value': 1})
                    contract.atomic_write_json(self.path, {'value': 2})
                    self.assertTrue(current_opened.wait(5))
                    fresh.start()
                    self.assertFalse(entered.wait(0.03)); self.assertFalse(fresh_entered.wait(0.03))
                self.assertTrue(entered.wait(5)); self.assertTrue(fresh_entered.wait(5))
        finally:
            for thread in (old, fresh):
                if thread.ident is not None: thread.join(5)
            if old_stream is not None and not old_stream.closed: old_stream.close()
        self.assertFalse(old.is_alive()); self.assertFalse(fresh.is_alive()); self.assertEqual(errors, [])
        self.assertEqual(contract.load(self.path), {'value': 2})

    def test_failed_replacement_keeps_the_current_owner_and_can_retry(self):
        before = self.path.read_bytes()
        with contract.file_lock(self.path):
            with patch.object(contract, 'replace_file', side_effect=OSError(5, 'synthetic rename failure')):
                with self.assertRaises(OSError): contract.atomic_write_json(self.path, {'value': 1})
            self.assertEqual(self.path.read_bytes(), before)
            contract.atomic_write_json(self.path, {'value': 2})
        self.assertEqual(contract.load(self.path), {'value': 2})
        self.assertEqual({path.name for path in self.root.iterdir()}, {'state.json'})

    def test_release_failure_still_closes_every_owned_handle(self):
        streams = []
        original_open = contract._open_lock_stream
        original_release = contract._release_file_lock
        def opening(path, **options):
            stream = original_open(path, **options); streams.append(stream); return stream
        failed = False
        def releasing(stream):
            nonlocal failed
            original_release(stream)
            if not failed:
                failed = True
                raise OSError(5, 'synthetic unlock failure')
        with patch.object(contract, '_open_lock_stream', opening):
            with self.assertRaisesRegex(OSError, 'synthetic unlock failure'):
                with patch.object(contract, '_release_file_lock', releasing):
                    with contract.file_lock(self.path):
                        contract.atomic_write_json(self.path, {'value': 1})
        self.assertTrue(all(stream.closed for stream in streams))
        with contract.file_lock(self.path):
            self.assertEqual(contract.load(self.path), {'value': 1})

    def _process_exclusion(self, method):
        import multiprocessing
        context = multiprocessing.get_context(method)
        parent, child = context.Pipe()
        process = context.Process(target=_file_lock_process, args=(str(self.path), child))
        try:
            with contract.file_lock(self.path):
                process.start(); child.close()
                self.assertTrue(parent.poll(10)); self.assertEqual(parent.recv(), 'waiting')
                self.assertFalse(parent.poll(0.05))
                contract.atomic_write_json(self.path, {'value': 1})
                self.assertFalse(parent.poll(0.05))
            self.assertTrue(parent.poll(10)); self.assertEqual(parent.recv(), 'acquired')
            process.join(10); self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive(): process.terminate(); process.join(5)
            parent.close(); child.close()

    def test_process_waits_through_atomic_replacement(self):
        self._process_exclusion('spawn')

    @unittest.skipUnless(hasattr(os, 'fork'), 'POSIX fork ownership')
    def test_forked_child_reacquires_without_unlocking_parent(self):
        self._process_exclusion('fork')

    def test_terminated_owner_releases_the_real_data_file(self):
        import multiprocessing
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        process = context.Process(target=_file_lock_process, args=(str(self.path), child, True))
        try:
            process.start(); child.close()
            for expected in ('waiting', 'acquired'):
                self.assertTrue(parent.poll(10)); self.assertEqual(parent.recv(), expected)
            process.terminate(); process.join(10); self.assertFalse(process.is_alive())
            with contract.file_lock(self.path):
                contract.atomic_write_json(self.path, {'value': 3})
            self.assertEqual(contract.load(self.path), {'value': 3})
        finally:
            if process.is_alive(): process.terminate(); process.join(5)
            parent.close(); child.close()

    def test_missing_data_is_not_initialized_by_synchronization(self):
        missing = self.root / 'missing' / 'document.json'
        with self.assertRaises(FileNotFoundError):
            with contract.file_lock(missing): pass
        self.assertFalse(missing.parent.exists())

    def test_first_publication_without_hard_links_publishes_complete_bytes(self):
        import errno
        destination = self.root / 'first.json'
        raw = b'{"complete":true}\n'
        original = contract._rename_exclusive
        seen = []
        def publish(staging, target):
            self.assertFalse(target.exists())
            self.assertEqual(staging.read_bytes(), raw)
            seen.append(target)
            return original(staging, target)
        with patch.object(contract.os, 'link', side_effect=OSError(errno.EPERM, 'no hard links')), \
             patch.object(contract, '_rename_exclusive', side_effect=publish):
            contract.atomic(destination, raw)
        self.assertEqual(seen, [destination]); self.assertEqual(destination.read_bytes(), raw)

    def test_first_publication_keeps_a_competing_complete_file(self):
        import errno
        destination = self.root / 'first.json'
        original = contract._rename_exclusive
        def competitor(staging, target):
            target.write_bytes(b'{"writer":"other"}\n')
            return original(staging, target)
        with patch.object(contract.os, 'link', side_effect=OSError(errno.EPERM, 'no hard links')), \
             patch.object(contract, '_rename_exclusive', side_effect=competitor), \
             self.assertRaises(FileExistsError):
            contract.atomic(destination, b'{"writer":"this"}\n')
        self.assertEqual(destination.read_bytes(), b'{"writer":"other"}\n')
        self.assertEqual({path.name for path in self.root.iterdir()}, {'state.json', 'first.json'})

    @unittest.skipUnless(os.name == 'nt', 'Windows data byte-range locking')
    def test_windows_lock_allows_reading_and_atomic_replacement(self):
        before = self.path.read_bytes()
        with contract.file_lock(self.path):
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.path.stat().st_size, len(before))
            contract.atomic_write_json(self.path, {'value': 4})
            self.assertEqual(contract.load(self.path), {'value': 4})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
