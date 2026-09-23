#!/usr/bin/env python3
"""Regression tests for complete material and caller-owned budgets.

Fixtures are synthetic bytes and a local Python process, not model-quality evidence.
Large dimensions are validated without allocating a large decoded canvas.
"""
from __future__ import annotations
import copy
import hashlib
import io
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

    def test_escaping_project_path_is_still_refused(self):
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
        path = ROOT / 'schemas/scene-persona-material.schema.json'
        if not path.exists(): path = ROOT / 'protocols/shared-state/schemas/scene-persona-material.schema.json'
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




class ValidationRegressionBudgetTests(unittest.TestCase):
    def test_regression_runs_to_completion_without_an_operator_deadline(self):
        import os, validate
        from types import SimpleNamespace
        from unittest.mock import patch
        seen = {}
        def fake_run(command, **kwargs):
            seen['timeout'] = kwargs.get('timeout')
            return SimpleNamespace(returncode=0, stdout='', stderr='Ran 3 tests in 0.001s')
        with patch.dict(os.environ, {}):
            os.environ.pop('VALIDATE_REGRESSION_TIMEOUT_SECONDS', None)
            with patch.object(validate.subprocess, 'run', fake_run):
                result = validate.run_standalone_regression(ROOT, 'x_smoke_test.py', output_format='unittest')
        self.assertIsNone(seen['timeout']); self.assertTrue(result['ok']); self.assertEqual(result['tests'], 3)

    def test_exceeded_operator_deadline_is_reported_not_raised(self):
        import os, subprocess, validate
        from unittest.mock import patch
        def timed_out(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs.get('timeout'), output='partial', stderr='')
        with patch.dict(os.environ, {'VALIDATE_REGRESSION_TIMEOUT_SECONDS': '0.5'}):
            with patch.object(validate.subprocess, 'run', timed_out):
                result = validate.run_standalone_regression(ROOT, 'x_smoke_test.py', output_format='json')
        self.assertFalse(result['ok']); self.assertIsNone(result['returncode'])
        self.assertIn('VALIDATE_REGRESSION_TIMEOUT_SECONDS', result['errors'][0]); self.assertEqual(result['stdout'], 'partial')


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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
