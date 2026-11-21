"""Public authoring diagnostics for sealed historical inputs, without migration.

These synthetic publications deliberately lack current task fields. Their
registered hashes and retained bytes are real; they establish no authority or
claim that an obsolete task can be prepared by the current compiler.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import execution_contract as c
from pack_manager import generate_uuid7
import production_authoring
import production_compiler
import production_fixtures
import production_operations as workflow
import production_store as store
import work_ledger
from test_production_report_view import resolved_action


SCRIPT = Path(__file__).with_name('production_workflow.py')


class RetainedInputPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.root = base / 'studio'
        self.root.mkdir()
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        work = work_ledger.begin(self.root, 'Inspect synthetic historical source.', ['Reopen the input.'])
        self.task_id = work['task_id']

    def publication(self, missing: str | None, *, wrong_input_digest: bool = False):
        """Seal historical bytes directly, as a previous producer would have."""
        run = generate_uuid7()
        task = production_authoring.seed(route='prompt-only', artifact='json', execution='authored',
                                          task_id=self.task_id)
        task['direction'].update(purpose='Synthetic retained document.', intended_effect='Test historical source diagnostics.')
        if missing is not None:
            del (task['direction'] if missing == 'source_allowances' else task)[missing]
        instructions = '{"synthetic":true}'
        raw = instructions.encode('utf-8')
        digest = c.digest(raw)
        consumer = {'instructions': instructions,
            'authored': {'state': 'finished', 'requirements': ['save'], 'completion_state': 'finished'}}
        prepared = {'run': run, 'task': task, 'task_path': 'historical-task.json',
            'dependencies': [{'space': 'studio', 'path': 'delivery.txt', 'sha256': digest, 'size': len(raw)}],
            'consumer_sha256': c.content_id(consumer), 'route_reading': {},
            'authored_revision': {'state': 'finished', 'input_verified': True,
                'artifact': {'path': 'delivery.txt', 'sha256': digest, 'size': len(raw)},
                'unresolved': [], 'choices': None}}
        prepared['input_sha256'] = ('0' * 64 if wrong_input_digest else
                                     production_compiler.input_digest(prepared, consumer))
        prepared['envelope_sha256'] = c.content_id(prepared)
        directory = self.root / 'production/runs' / run
        (directory / 'objects').mkdir(parents=True)
        files = []
        for name, content in {'prepared.json': c.encoded(prepared), 'consumer.json': c.encoded(consumer),
                              'objects/' + digest: raw}.items():
            (directory / name).write_bytes(content)
            files.append({'path': name, 'sha256': c.digest(content), 'size': len(content)})
        (directory / 'manifest.json').write_bytes(c.encoded({'complete': True, 'files': files}))
        store.register_run(self.root, run, prepared, directory)
        return run, directory

    def cli(self, command, run, *, view='full'):
        args = [sys.executable, str(SCRIPT), command, '--root', str(self.root),
                '--from-run', run, '--view', view]
        if command == 'draft-inputs':
            args += ['--operation', 'amend', '--out-dir', 'work/reopened']
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
        return result, json.loads(result.stdout)

    @staticmethod
    def contents(directory):
        return {path.relative_to(directory).as_posix(): path.read_bytes()
                for path in directory.rglob('*') if path.is_file()}

    def test_public_reopening_names_missing_delivery_before_authored_interpretation(self):
        run, directory = self.publication('delivery')
        before = self.contents(directory)
        registered = copy.deepcopy(store.registered_run(self.root, run))
        for command in ('inspect-inputs', 'draft-inputs'):
            for view in ('full', 'summary'):
                with self.subTest(command=command, view=view):
                    process, report = self.cli(command, run, view=view)
                    self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
                    self.assertFalse(report['ok'])
                    problem = report['diagnostics'][0]
                    self.assertEqual(problem['code'], 'INPUT_CONSISTENCY_ERROR')
                    self.assertEqual(problem['pointer'], '/delivery')
                    self.assertEqual(problem['file'], 'historical-task.json')
                    self.assertEqual(problem['selected_input']['run'], run)
                    self.assertEqual(problem['repair_owner'], {'kind': 'new-draft', 'file': None})
                    repair = resolved_action(report, problem['repair_action'])
                    self.assertEqual(repair['operation'], 'draft-inputs')
                    self.assertNotIn('--from-run', repair['argv'])
                    self.assertIn('Retain the selected run unchanged', problem['required_action'])
                    self.assertEqual(problem['expected']['type'], 'object')
        self.assertEqual(self.contents(directory), before)
        self.assertEqual(store.registered_run(self.root, run), registered)
        self.assertEqual(store.read_history(self.root, run).rows, [])
        self.assertFalse((self.root / 'work/reopened').exists())

    def test_readable_historical_input_is_checked_only_when_reopened(self):
        run, directory = self.publication('source_allowances')
        # Ordinary retained reading has no new current-schema requirement.
        loaded = workflow.read_run(self.root, run)
        self.assertNotIn('source_allowances', loaded.prepared['task']['direction'])
        before = self.contents(directory)
        for view in ('full', 'summary'):
            process, report = self.cli('inspect-inputs', run, view=view)
            self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
            problem = report['diagnostics'][0]
            self.assertEqual(problem['pointer'], '/direction/source_allowances')
            self.assertEqual(problem['repair_owner']['kind'], 'new-draft')
            self.assertEqual(problem['selected_input']['run'], run)
        self.assertEqual(self.contents(directory), before)

    def test_registered_manifest_corruption_precedes_current_structure_diagnostic(self):
        run, directory = self.publication('delivery')
        (directory / 'manifest.json').write_bytes((directory / 'manifest.json').read_bytes() + b'\n')
        before = self.contents(directory)
        process, report = self.cli('inspect-inputs', run)
        self.assertNotEqual(process.returncode, 0)
        problem = report['diagnostics'][0]
        self.assertEqual(problem['code'], 'ARTIFACT_MANIFEST_CORRUPT')
        self.assertNotIn('repair_owner', problem)
        self.assertEqual(self.contents(directory), before)

    def test_registered_input_digest_failure_precedes_current_structure_diagnostic(self):
        run, directory = self.publication('delivery', wrong_input_digest=True)
        before = self.contents(directory)
        process, report = self.cli('inspect-inputs', run)
        self.assertNotEqual(process.returncode, 0)
        problem = report['diagnostics'][0]
        self.assertEqual(problem['code'], 'INPUT_SNAPSHOT_CORRUPT')
        self.assertIn('creative input digest', problem['message'])
        self.assertNotIn('repair_owner', problem)
        self.assertEqual(self.contents(directory), before)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
