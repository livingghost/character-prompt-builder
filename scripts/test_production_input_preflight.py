"""Current input discovery names an executable repair before deriving a draft."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import execution_contract as c
import production_authoring
import production_fixtures as fixtures
import production_input_preflight as preflight
import production_inputs
from production_diagnostics import ProductionError
import work_ledger
from test_production_report_view import resolved_action


class InputPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.root = base / 'studio'
        self.root.mkdir()
        self.enterContext(fixtures.scratch_home(base / 'home'))
        work = work_ledger.begin(self.root, 'Develop a quiet traveler.', ['Compose the character.'])
        self.task = production_authoring.seed(route='prompt-only', artifact='text', execution='authored',
                                              task_id=work['task_id'])

    def test_missing_fields_name_current_owner_pointer_and_repair_before_writing(self):
        for field, pointer in [('delivery', '/delivery'), ('source_allowances', '/direction/source_allowances')]:
            with self.subTest(field=field):
                task = copy.deepcopy(self.task)
                (task['direction'] if field == 'source_allowances' else task).pop(field)
                path = self.root / 'selected-task.json'
                path.write_bytes(c.encoded(task))
                before = path.read_bytes()
                with self.assertRaises(ProductionError) as caught:
                    production_inputs.draft_inputs(self.root, 'selected-task.json', 'work/revision', operation='compose')
                report = caught.exception.diagnostic.as_dict()
                self.assertEqual(report['pointer'], pointer)
                self.assertEqual(report['file'], 'selected-task.json')
                self.assertEqual(report['current_operation'], 'draft-inputs')
                self.assertEqual(report['guidance']['schema'], preflight.TASK_SCHEMA)
                self.assertEqual(report['repair_owner']['file'], 'selected-task.json')
                self.assertIn('type', report['expected'])
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((self.root / 'work/revision').exists())
        # The offered command creates a current scaffold without modifying the
        # selected invalid input or inventing its unanswered creative choices.
        run = subprocess.run(report['repair_action']['argv'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        rebuilt = json.loads(run.stdout)
        choices = c.load(self.root / rebuilt['choices_file'])
        self.assertIn('source_allowances', choices['authoring']['task']['direction'])
        self.assertEqual((self.root / 'selected-task.json').read_bytes(), before)

    def test_saved_task_repair_targets_new_work_and_preserves_meaningful_scope(self):
        task = copy.deepcopy(self.task)
        task.pop('delivery')
        with self.assertRaises(ProductionError) as caught:
            preflight.require_shape(task, schema_path=preflight.TASK_SCHEMA, file='saved/task.json',
                root=self.root, operation='draft-inputs', source_run='retained-run')
        report = caught.exception.diagnostic.as_dict()
        self.assertEqual(report['selected_input']['run'], 'retained-run')
        self.assertEqual(report['repair_owner']['kind'], 'new-draft')
        self.assertIsNone(report['repair_owner']['file'])
        self.assertEqual(report['preservation']['historical_run'], 'retained unchanged')
        self.assertNotIn('--from-run', report['repair_action']['argv'])

    def test_public_cli_serializes_nested_schema_repairs_in_full_and_summary(self):
        cli = Path(__file__).with_name('production_workflow.py')
        for field, pointer in [('delivery', '/delivery'), ('source_allowances', '/direction/source_allowances')]:
            task = copy.deepcopy(self.task)
            (task['direction'] if field == 'source_allowances' else task).pop(field)
            path = self.root / 'selected-task.json'
            path.write_bytes(c.encoded(task))
            original = path.read_bytes()
            for command in ('inspect-inputs', 'draft-inputs'):
                for view in ('full', 'summary'):
                    with self.subTest(field=field, command=command, view=view):
                        argv = [sys.executable, str(cli), command, '--root', str(self.root),
                                '--task', 'selected-task.json', '--view', view]
                        if command == 'draft-inputs':
                            argv.extend(['--operation', 'compose', '--out-dir', 'work/new-input'])
                        completed = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8')
                        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                        report = json.loads(completed.stdout)
                        problem = report['diagnostics'][0]
                        self.assertEqual(problem['pointer'], pointer)
                        self.assertEqual(problem['file'], 'selected-task.json')
                        self.assertEqual(problem['repair_owner']['file'], 'selected-task.json')
                        self.assertIn('type', problem['expected'])
                        repair = resolved_action(report, problem['repair_action'])
                        self.assertIn('draft-inputs', repair['argv'])
                        if view == 'summary':
                            complete = c.load(self.root / report['full_report'])
                            self.assertEqual(complete['diagnostics'][0]['pointer'], pointer)
                        self.assertEqual(path.read_bytes(), original)
                        self.assertFalse((self.root / 'work/new-input').exists())

    def test_choices_delivery_and_direction_gaps_have_public_pointers(self):
        for field, pointer in [('delivery', '/authoring/delivery'),
                              ('source_allowances', '/authoring/task/direction/source_allowances')]:
            with self.subTest(field=field):
                choices = production_inputs.draft_choices(self.task)
                owner = choices['authoring'] if field == 'delivery' else choices['authoring']['task']['direction']
                owner.pop(field)
                with self.assertRaises(ProductionError) as caught:
                    production_inputs.read_choices(choices, file='work/draft/choices.json', root=self.root)
                report = caught.exception.diagnostic.as_dict()
                self.assertEqual(report['pointer'], pointer)
                self.assertIn('repair_action', report)

    def test_repair_opens_needed_work_before_the_scaffold_in_an_inactive_studio(self):
        root = self.root / 'inactive-studio'
        root.mkdir()
        task = copy.deepcopy(self.task)
        task.pop('delivery')
        selected = root / 'selected-task.json'
        selected.write_bytes(c.encoded(task))
        original = selected.read_bytes()
        cli = Path(__file__).with_name('production_workflow.py')
        diagnosed = subprocess.run([sys.executable, str(cli), 'inspect-inputs', '--root', str(root),
            '--task', 'selected-task.json', '--view', 'summary'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(diagnosed.returncode, 2, diagnosed.stdout + diagnosed.stderr)
        report = json.loads(diagnosed.stdout)
        problem = report['diagnostics'][0]
        action = resolved_action(report, problem['repair_action'])
        self.assertEqual(action['operation'], 'begin-work')
        self.assertIsNone(work_ledger.read_current(root))
        opened = subprocess.run(action['argv'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(opened.returncode, 0, opened.stdout + opened.stderr)
        scaffold = subprocess.run(resolved_action(report, action['next_action'])['argv'],
                                  capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(scaffold.returncode, 0, scaffold.stdout + scaffold.stderr)
        choices = c.load(root / json.loads(scaffold.stdout)['choices_file'])
        self.assertIn('source_allowances', choices['authoring']['task']['direction'])
        self.assertEqual(selected.read_bytes(), original)
        self.assertFalse((root / 'production/records.sqlite3').exists())

    def test_route_role_gap_is_early_and_uses_source_acquisition(self):
        result = production_inputs.draft_inputs(self.root, None, 'work/intent', operation='compose',
            route='prompt-only', artifact='text', execution='authored', features=['authorial-intent'])
        gaps = [row for row in result['unresolved'] if row.get('cause') == 'missing-applied-source-role']
        self.assertEqual([row['role'] for row in gaps], ['authorial-intent'])
        gap = gaps[0]
        self.assertEqual(gap['source_row_example']['disposition'], 'applied')
        self.assertIn('acquire-source', gap['repair_action']['argv'])
        self.assertIn('work/intent/choices.json', gap['repair_action']['argv'])
        self.assertEqual(result['authoring_guide']['source_requirements']['missing'], ['authorial-intent'])
        task = copy.deepcopy(self.task)
        task['features'] = ['authorial-intent']
        task['sources'] = [dict(gap['source_row_example'], disposition='considered-not-used')]
        self.assertEqual(preflight.source_roles(self.root, task)['missing'], ['authorial-intent'])
        task['sources'][0]['disposition'] = 'applied'
        self.assertEqual(preflight.source_roles(self.root, task)['missing'], [])

    def test_standalone_and_retained_sources_do_not_offer_unregistered_choices(self):
        task = copy.deepcopy(self.task)
        task['features'] = ['authorial-intent']
        standalone = preflight.missing_source_roles(self.root, task, task_path='selected-task.json')[0]
        self.assertEqual(standalone['repair_owner'],
            {'kind': 'production-task', 'file': 'selected-task.json', 'pointer': '/sources'})
        self.assertNotIn('--choices', standalone['repair_action']['argv'])
        self.assertIn('selected-task.json', standalone['required_action'])
        retained = preflight.missing_source_roles(self.root, task, source_run='retained-run')[0]
        self.assertEqual(retained['repair_owner']['kind'], 'new-draft')
        self.assertIn('--from-run', retained['repair_action']['argv'])
        self.assertIn('retained-run', retained['repair_action']['argv'])
        self.assertNotIn('--choices', retained['repair_action']['argv'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
