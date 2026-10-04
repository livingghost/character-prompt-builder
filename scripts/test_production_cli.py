"""Run the public generation commands and every example scenario from another CWD without a real service."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import production_fixtures


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/generation/build_example.py'
CLI = [sys.executable, str(ROOT / 'scripts/production_workflow.py')]


class PublicCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpb-cli-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        home = production_fixtures.scratch_home_dir(self.base / 'home')
        self.env = {**os.environ, 'CPB_HOME': str(home)}

    def call(self, args, *, code=0, stdin=None):
        result = subprocess.run(args, cwd=self.base, env=self.env, capture_output=True, text=True, timeout=300,
                                encoding='utf-8', input=stdin)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_example_prepare_check_status_variant_repeat_from_another_cwd(self):
        workspace = self.base / 'synthetic case'
        example = self.call([sys.executable, str(EXAMPLE), '--out', str(workspace)])
        args = example['prepare_argv']
        check = args.copy()
        check[2] = 'check'
        self.assertTrue(self.call(check)['publishable'])
        studio = workspace / 'studio'
        self.assertFalse((studio / 'production/records.sqlite3').exists())
        prepared = self.call(args)
        # Every file the prepare operation recorded is at its published place, with its content.
        prepare_log = next(row for row in self.call(CLI + ['logs', '--root', str(studio), '--run', prepared['run']])['operations']
                           if row['metadata']['arguments']['command'] == 'prepare')
        artifacts = json.loads((Path(prepare_log['path']) / 'artifacts.json').read_text(encoding='utf-8'))
        import hashlib
        self.assertTrue(any(Path(item['path']).name == 'prepared.json' for item in artifacts))
        for item in artifacts:
            self.assertEqual(hashlib.sha256(Path(item['path']).read_bytes()).hexdigest(), item['sha256'], item['path'])
        status = self.call(CLI + ['status', '--root', str(studio), '--budget'])
        self.assertEqual(status['runs'][0]['run'], prepared['run'])
        (studio / 'changes.json').write_text(json.dumps({'changes': {'parameter:steps': 22}, 'reason': 'Synthetic CLI fixture.'}), encoding='utf-8')
        varied = self.call(CLI + ['variant', '--root', str(studio), '--from', prepared['run'], '--changes-file', 'changes.json', '--prepare'])
        self.assertEqual(varied['request_preview']['steps'], 22)
        repeated = self.call(CLI + ['repeat', '--root', str(studio), '--from', prepared['run'], '--prepare'])
        self.assertEqual(repeated['input_sha256'], prepared['input_sha256'])
        self.assertNotEqual(repeated['run'], prepared['run'])
        logs = self.call(CLI + ['logs', '--root', str(studio)])
        self.assertGreaterEqual(len(logs['operations']), 5)
        # A draft never replaces an existing file.
        draft = CLI + ['draft-execution', '--root', str(studio), '--run', prepared['run'], '--grant', 'fixture-grant', '--out', 'decisions.json']
        self.call(draft)
        refused = self.call(draft, code=2)['diagnostics'][0]
        self.assertEqual((refused['code'], refused['file'], refused['required_action']), ('OUTPUT_ALREADY_EXISTS', 'decisions.json', 'Choose a new --out.'))
        broken = self.call(CLI + ['check', '--root', str(studio), '--task', 'missing-task.json'], code=2)
        self.assertEqual(broken['diagnostics'][0]['code'], 'INPUT_UNREADABLE')

    def test_every_command_and_option_has_help(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import production_workflow
        parser = production_workflow.build_parser()
        commands = next(action for action in parser._actions if action.dest == 'command').choices
        self.assertEqual([(name, action.dest) for name, child in commands.items() for action in child._actions
                          if action.dest != 'help' and not action.help], [])
        self.assertEqual(len({commands[name].description for name in ('variant', 'repeat', 'retarget')}), 3)
        self.assertTrue(all(child.description for child in commands.values()))

    def scenario(self, name: str) -> list[tuple[list[str], int, dict]]:
        """Build one example scenario and run the commands it prints, in order."""
        out = self.base / name
        built = self.call([sys.executable, str(EXAMPLE), '--out', str(out), '--include-' + name])
        results = []
        for argv in built['scenario']['next']:
            if argv[2] == 'release-reservation':
                sys.path.insert(0, str(ROOT / 'scripts'))
                import production_case_fixtures as fixtures
                root = Path(argv[argv.index('--root') + 1])
                draft = json.loads((root / 'release/request.json').read_text(encoding='utf-8'))
                fixtures.write(root / 'release/request.json',
                               fixtures.fill_release(root, draft, actor=built['scenario']['release_actor'], evidence='release/evidence.txt'))
            completed = subprocess.run(argv, cwd=self.base, env=self.env, capture_output=True, text=True, timeout=300, encoding='utf-8')
            results.append((argv, completed.returncode, json.loads(completed.stdout) if completed.stdout.strip() else {}))
        return results

    def test_each_example_scenario(self):
        names = ['prompt-change', 'reference', 'sheet', 'scope-shortage', 'budget-change', 'outcome-unknown',
                 'partial-review', 'release', 'log-export']
        with ThreadPoolExecutor(max_workers=3) as pool:
            done = dict(zip(names, pool.map(self.scenario, names)))
        codes = {name: [code for _, code, _ in rows] for name, rows in done.items()}
        self.assertEqual(codes, {'prompt-change': [0], 'reference': [0], 'sheet': [0], 'scope-shortage': [0, 3],
                                 'budget-change': [0, 0], 'outcome-unknown': [4, 0], 'partial-review': [0, 0, 0],
                                 'release': [0, 0, 0], 'log-export': [0, 0, 0]})
        output = {name: [value for _, _, value in rows] for name, rows in done.items()}
        self.assertTrue(output['prompt-change'][0]['request_preview']['prompt'].endswith('stays alone in the frame.'))
        self.assertEqual(len(output['reference'][0]['request_preview']['inputs']['references']), 1)
        sheet = output['sheet'][0]['runs'][0]
        self.assertEqual((sheet['registration'], output['sheet'][0]['execution_completed']), ('registered', True))
        self.assertEqual(output['scope-shortage'][1]['diagnostics'][0]['missing'], ['decision:expression'])
        self.assertEqual(output['budget-change'][1]['budget']['grants'][0]['limits']['cost']['amount'], '250')
        self.assertEqual(output['outcome-unknown'][0]['runs'][0]['submission'], 'outcome_unknown')
        self.assertEqual(output['outcome-unknown'][1]['outcome'], 'not_executed')
        self.assertEqual([row['disposition'] for row in (output['partial-review'][0], output['partial-review'][2])], ['pending', 'not_selected'])
        self.assertEqual(output['partial-review'][2]['unassessed_criteria'], ['output'])
        self.assertEqual((output['release'][2]['released'], output['release'][2]['already_released']), (True, False))
        self.assertEqual(output['log-export'][2]['excluded'][-1], 'stdout.log and stderr.log console output')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
