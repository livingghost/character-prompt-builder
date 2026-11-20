"""Saved authored work and edited sources expose the same next action at each entry."""
from __future__ import annotations
import production_workflow as production_workflow_cli
import production_fixtures as authoring_fixtures

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_authoring_state as authoring
import production_fixtures as fixtures
import production_inputs as inputs
import production_operations as workflow
import session_entry_points
import studio_workspace as studio
import work_ledger


class AuthoredContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.enterContext(fixtures.scratch_home(base / 'home'))
        self.root = base / 'studio'
        studio.init(self.root, 'continuation-fixture', 'Synthetic authored continuation')
        task_id = work_ledger.begin(self.root, 'Write and deliver a synthetic description.',
                                    ['Compose the description.'])['task_id']
        task = {'task_id': task_id, 'route': 'development', 'features': [], 'sources': [],
            'delivery': {'path': 'description.txt', 'translation_notes': 'Retain the authored description.'},
            'criteria': [{'id': 'subject', 'strength': 'hard',
                          'text': 'The description identifies a brass key on a table.'}],
            'world_views': [], 'authored': {'requirements': ['save', 'delivery']}}
        fixtures.task(self.root, task)
        self.write('task.json', task)
        self.write('description.txt', 'A brass key rests on a wooden table.\n')
        drafted = authoring_fixtures.authoring_inputs(self.root, 'task.json', 'edit')
        self.choices_path = drafted['choices_file']
        self.choices = c.load(self.root / self.choices_path)
        self.choices['reading']['reading_key'] = c.load(self.root / task['route_reading'])['reading_key']
        self.write(self.choices_path, self.choices)

    def write(self, path, value):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(value.encode('utf-8') if isinstance(value, str) else c.encoded(value))

    def test_saved_delivery_is_the_same_continuation_in_work_and_production_status(self):
        saved = workflow.save(self.root, self.choices_path)
        current = authoring.current_task(self.root)
        self.assertEqual(current['focus'], 'authored')
        self.assertEqual(current['authoring']['saved']['run'], saved['run'])
        self.assertEqual(current['authoring']['saved']['authored']['missing'], ['delivery'])
        self.assertEqual(current['next_actions'][0]['command'], 'deliver')
        status = workflow.status(self.root)
        workflow.schema_check(status, 'status')
        projected = status['current_task']
        self.assertEqual(projected['focus'], current['focus'])
        self.assertEqual(projected['next_actions'][0]['argv'], current['next_actions'][0]['argv'])

    @unittest.skipUnless(os.name == 'nt', 'Windows 8.3 path aliases require Windows')
    def test_short_path_alias_uses_the_same_canonical_continuation(self):
        buffer = ctypes.create_unicode_buffer(1024)
        available = ctypes.windll.kernel32.GetShortPathNameW(str(self.root.parent), buffer, len(buffer))
        if not available:
            self.skipTest('8.3 short names are unavailable on this volume')
        alias = Path(buffer.value) / self.root.name
        workflow.save(alias, self.choices_path)
        current = authoring.current_task(alias)
        projected = workflow.status(alias)['current_task']
        self.assertEqual(projected['next_actions'][0]['argv'], current['next_actions'][0]['argv'])
        self.assertEqual(projected['next_actions'][0]['argv'][4], str(self.root.resolve()))

    def test_editing_the_source_takes_priority_over_delivering_the_previous_revision(self):
        saved = workflow.save(self.root, self.choices_path)
        self.write(self.choices['authoring']['delivery']['file'],
                   'A brass key rests beside a folded map on a wooden table.\n')
        current = authoring.current_task(self.root)
        self.assertEqual(current['focus'], 'authoring')
        self.assertTrue(current['authoring']['saved']['working_changes'])
        self.assertEqual(current['next_actions'][0]['command'], 'save')
        self.assertEqual(current['authoring']['saved']['run'], saved['run'])
        self.assertEqual(workflow.read_run(self.root, saved['run']).consumer['instructions'],
                         'A brass key rests on a wooden table.\n')

    def test_session_command_exposes_saved_text_without_suggesting_external_recovery(self):
        saved = workflow.save(self.root, self.choices_path)
        startup = session_entry_points.authoring_lines(self.root)
        command = next(line.partition(': ')[2] for line in startup if line.startswith('Inspect saved inputs: '))
        inspected = subprocess.run(command, shell=True, cwd=self.root.parent, capture_output=True,
                                   text=True, encoding='utf-8', check=False)
        self.assertEqual(inspected.returncode, 0, inspected.stdout + inspected.stderr)
        report = json.loads(inspected.stdout)
        self.assertEqual(report['saved']['run'], saved['run'])
        text = '\n'.join(authoring.session_lines(self.root, work_ledger.read_current(self.root), report=report))
        self.assertEqual(text.count('Saved input choices:'), 1)
        self.assertEqual(text.count('Saved authored revision: ' + saved['run']), 1)
        self.assertIn('Requested results still pending: delivery', text)
        self.assertIn('Continue saved work:', text)
        self.assertNotIn('production_workflow.py resume', text)

    def test_completed_revision_still_exposes_its_open_work_task_closure(self):
        saved = workflow.save(self.root, self.choices_path)
        workflow.deliver(self.root, saved['run'], destination='exports/description.txt')
        workflow.complete(self.root, saved['run'])
        current = authoring.current_task(self.root)
        self.assertEqual(current['authoring']['saved']['task_disposition'], 'completed')
        action = current['next_actions'][0]
        self.assertEqual(action['command'], 'finish')
        self.assertIn('--studio', action['argv'])
        work_ledger.step_done(self.root, 1)
        work_ledger.finish(self.root, saved['run'])
        self.assertIsNone(authoring.current_task(self.root))


class RegisteredRuntimeContinuationTests(unittest.TestCase):
    """A draft's registered runtime owns its current target and reading guidance."""

    def setUp(self):
        from catalog_retrieval import runtime
        import production_case_fixtures as cases
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.enterContext(fixtures.scratch_home(base / 'home'))
        self.enterContext(runtime.using_pack_runtime(None))
        self.case = cases.create(base / 'studio', base / 'runtime', with_alternate=True)
        self.root = self.case['root']
        self.task_path = cases.alternate_task(self.root)
        settings = self.case['settings']
        self.runtime_arguments = {'state-file': str(settings.state_file),
            'cache-dir': str(settings.cache_dir), 'managed-root': str(settings.managed_root),
            'pack-root': [str(self.case['pack'])]}
        self.model = cases.ALTERNATE_MODEL_ID

    @staticmethod
    def resolved_runtime(values):
        return {name: [str(Path(item).resolve()) for item in value] if isinstance(value, list)
                else str(Path(value).resolve()) for name, value in values.items()}

    def draft(self, directory='edit', *, source_run=None, registered=True):
        result = authoring_fixtures.authoring_inputs(self.root, self.task_path if source_run is None else None,
            directory, from_run=source_run,
            runtime_arguments=self.runtime_arguments if registered else None)
        self.assertEqual(result['unresolved'], [], result)
        return result['choices_file']

    def inspect_command(self, choices_path=None, *, runtime_arguments=None):
        command = [sys.executable, '-B', str(Path(production_workflow_cli.__file__)),
                   'inspect-inputs', '--root', str(self.root), '--view', 'full']
        if choices_path is not None:
            command.extend(('--choices', choices_path))
        for name, value in (runtime_arguments or {}).items():
            for item in value if isinstance(value, list) else [value]:
                command.extend(('--' + name, str(item)))
        return command

    def inspect_cli(self, choices_path=None, *, runtime_arguments=None):
        completed = subprocess.run(self.inspect_command(choices_path, runtime_arguments=runtime_arguments),
            cwd=self.root, env=dict(os.environ), capture_output=True, text=True, encoding='utf-8',
            check=False, timeout=45)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def follow_cli(self, argv):
        command = list(argv)
        if command[1] != '-B':
            command.insert(1, '-B')
        # The operator selects compact presentation; every source and runtime
        # argument is used exactly as the preceding public action supplied it.
        if '--view' not in command:
            command.extend(('--view', 'summary'))
        completed = subprocess.run(command, cwd=self.root, env=dict(os.environ), capture_output=True,
            text=True, encoding='utf-8', check=False, timeout=45)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertNotIn('unknown model', completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def source_snapshot(self):
        # Inspection may append its operation log; inputs, pointers, reading
        # records and every immutable run must keep their exact bytes.
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob('*')
                if path.is_file() and path.relative_to(self.root).parts[0] != 'logs'}

    def change_guidance(self):
        import pack_manager
        path = self.case['pack'] / 'records/models.json'
        models = c.load(path)
        next(row for row in models['records'] if row['id'] == self.model)['label'] = 'Current synthetic alternate guidance'
        c.atomic(path, c.encoded(models), replace=True)
        pack_manager.write_lock(self.case['pack'])

    def other_runtime_arguments(self):
        import pack_manager
        import production_case_fixtures as cases
        base = self.root.parent / 'other-runtime'
        pack = cases.create_pack(base / 'packs/example')
        settings = pack_manager.default_settings(state_file=base / 'state.json', cache_dir=base / 'cache',
            managed_root=base / 'managed', extra_roots=[pack])
        pack_manager.save_state(settings.state_file, c.load(self.case['settings'].state_file))
        return {'state-file': str(settings.state_file), 'cache-dir': str(settings.cache_dir),
                'managed-root': str(settings.managed_root), 'pack-root': [str(pack)]}

    def test_cli_explicit_runtime_observes_unbound_inputs_and_keeps_the_reading_action(self):
        saved = workflow.prepare(self.root, self.task_path)
        choices_path = self.draft('reopened', source_run=saved['run'], registered=False)
        self.change_guidance()
        original = self.source_snapshot()
        without_runtime = self.inspect_cli(choices_path)
        missing = next(row for row in without_runtime['inputs'] if row.get('choices') == choices_path)
        self.assertIn('target-evidence-required', [row.get('reason') for row in missing['unresolved']])
        report = self.inspect_cli(choices_path, runtime_arguments=self.runtime_arguments)
        draft = next(row for row in report['inputs'] if row.get('choices') == choices_path)
        self.assertIsNone(draft['runtime_arguments'])
        self.assertEqual(self.resolved_runtime(draft['assembly_basis']['runtime_arguments']),
                         self.resolved_runtime(self.runtime_arguments))
        self.assertEqual(draft['route_scope']['model'], self.model)
        self.assertNotIn('target-evidence-required', [row.get('reason') for row in draft['unresolved']])
        reading = next(row for row in draft['unresolved'] if row['code'] == 'TARGET_GUIDANCE_REQUIRED')
        action = reading['next_action']
        self.assertEqual(action['args']['model'], self.model)
        for key, value in self.runtime_arguments.items():
            self.assertEqual(self.resolved_runtime({key: action['args'][key]}),
                             self.resolved_runtime({key: value}))
            for item in value if isinstance(value, list) else [value]:
                self.assertIn(str(Path(item).resolve()),
                              [str(Path(arg).resolve()) for arg in action['argv']])
        self.assertTrue(report['pending'])
        self.assertEqual(self.source_snapshot(), original)

    def test_cli_registered_runtime_keeps_precedence_and_restores_the_caller(self):
        from catalog_retrieval import runtime
        choices_path = self.draft()
        self.change_guidance()
        other = self.other_runtime_arguments()
        original = self.source_snapshot()
        report = self.inspect_cli(choices_path, runtime_arguments=other)
        draft = next(row for row in report['inputs'] if row.get('choices') == choices_path)
        self.assertNotIn('target-evidence-required', [row.get('reason') for row in draft['unresolved']])
        reading = next(row for row in draft['unresolved'] if row['code'] == 'TARGET_GUIDANCE_REQUIRED')
        for key, value in self.runtime_arguments.items():
            self.assertEqual(reading['next_action']['args'][key], value)
        runtime.configure_pack_runtime(None)
        caller = runtime.selected_pack_settings()
        parser = production_workflow_cli.build_parser()
        args = parser.parse_args(self.inspect_command(choices_path, runtime_arguments=other)[3:])
        inputs.command(args, parser)
        self.assertEqual(runtime.selected_pack_settings(), caller)
        self.assertNotIn(self.model, [entry.record.get('id') for entry in runtime.load_pack_catalog().entries])
        self.assertEqual(self.source_snapshot(), original)

    def test_cli_unbound_ready_inputs_keep_runtime_in_the_preparation_action(self):
        choices_path = self.draft(registered=False)
        original = self.source_snapshot()
        report = self.inspect_cli(choices_path, runtime_arguments=self.runtime_arguments)
        draft = next(row for row in report['inputs'] if row.get('choices') == choices_path)
        self.assertEqual(draft['unresolved'], [])
        action = next(row for row in draft['next_actions'] if row['command'] == 'prepare')
        parsed = production_workflow_cli.build_parser().parse_args(action['argv'][2:])
        self.assertEqual(parsed.choices, choices_path)
        self.assertEqual(parsed.state_file, Path(self.runtime_arguments['state-file']))
        self.assertEqual(parsed.cache_dir, Path(self.runtime_arguments['cache-dir']))
        self.assertEqual(parsed.managed_root, Path(self.runtime_arguments['managed-root']))
        self.assertEqual([path.resolve() for path in parsed.pack_root],
                         [Path(value).resolve() for value in self.runtime_arguments['pack-root']])
        self.assertEqual(self.source_snapshot(), original)

    def test_public_inspect_check_prepare_and_fresh_status_keep_the_selected_runtime(self):
        choices_path = self.draft(registered=False)
        original = self.source_snapshot()
        report = self.inspect_cli(choices_path, runtime_arguments=self.runtime_arguments)
        source = next(row for row in report['inputs'] if row.get('choices') == choices_path)
        check = list(next(row for row in source['next_actions'] if row['command'] == 'prepare')['argv'])
        check[2] = 'check'
        checked = self.follow_cli(check)
        self.assertTrue(checked['ok'])
        self.assertTrue(checked['publishable'])
        prepared = self.follow_cli(checked['next_action']['argv'])
        self.assertTrue(prepared['ok'])
        self.assertEqual(prepared['next_action']['command'], 'status')
        self.assertNotIn('--state-file', prepared['next_action']['argv'])
        sealed = {path: raw for path, raw in self.source_snapshot().items()
                  if path.startswith('production/runs/')}
        status = self.follow_cli(prepared['next_action']['argv'])
        self.assertEqual(status['current_task']['focus'], 'execution')
        draft = next(row for row in status['current_task']['authoring']['inputs']
                     if row.get('choices') == choices_path)
        self.assertEqual(draft['diagnostic_ids'], [])
        self.assertEqual(draft['prepared_run'], prepared['run'])
        self.assertFalse(status['current_task']['authoring']['pending'])
        loaded = workflow.read_run(self.root, prepared['run'])
        self.assertEqual(loaded.prepared['runtime_snapshot']['settings']['state_file'],
                         self.runtime_arguments['state-file'])
        self.assertEqual(loaded.prepared['authoring']['choices_ref']['path'], choices_path)
        self.assertEqual(loaded.rows, [])
        for path, raw in original.items():
            if (path.startswith(str(Path(choices_path).parent) + '/') or '/authoring/' in path
                    or path in {'work/reads.jsonl', self.task_path}):
                self.assertEqual((self.root / path).read_bytes(), raw, path)
        discovered = self.inspect_cli(choices_path)
        current = next(row for row in discovered['inputs'] if row.get('choices') == choices_path)
        self.assertEqual(current['unresolved'], [])
        self.assertIsNone(current['runtime_arguments'])
        self.assertEqual(current['assembly_basis']['runtime_arguments']['state-file'],
                         self.runtime_arguments['state-file'])
        self.assertEqual({path: raw for path, raw in self.source_snapshot().items()
                          if path.startswith('production/runs/')}, sealed)

    def test_public_check_without_runtime_uses_the_registered_producer(self):
        choices_path = self.draft()
        checked = self.follow_cli([sys.executable, str(Path(production_workflow_cli.__file__)),
            'check', '--root', str(self.root), '--choices', choices_path])
        self.assertTrue(checked['publishable'])
        args = production_workflow_cli.build_parser().parse_args(checked['next_action']['argv'][2:])
        self.assertEqual(args.state_file, Path(self.runtime_arguments['state-file']))
        self.assertEqual([path.resolve() for path in args.pack_root], [Path(value).resolve() for value in self.runtime_arguments['pack-root']])
        prepared = self.follow_cli(checked['next_action']['argv'])
        status = self.follow_cli(prepared['next_action']['argv'])
        self.assertFalse(status['current_task']['authoring']['pending'])

    def test_prepared_runtime_applies_only_to_its_exact_choices_and_authored_files(self):
        from catalog_retrieval import runtime
        choices_path = self.draft('published', registered=False)
        other_choices = self.draft('other-branch', registered=False)
        saved = workflow.prepare(self.root, choices=choices_path)
        runtime.configure_pack_runtime(None)
        report = self.inspect_cli()
        branches = {row['choices']: row for row in report['inputs']}
        self.assertEqual(branches[choices_path]['unresolved'], [])
        self.assertIn('target-evidence-required',
            [row.get('reason') for row in branches[other_choices]['unresolved']])
        captured = self.source_snapshot()
        choices = c.load(self.root / choices_path)
        prompt = self.root / choices['authoring']['delivery']['file']
        prompt.write_text(prompt.read_text(encoding='utf-8') + '\nChanged current authored source.\n', encoding='utf-8')
        changed = self.inspect_cli(choices_path)
        current = next(row for row in changed['inputs'] if row.get('choices') == choices_path)
        self.assertIn('target-evidence-required', [row.get('reason') for row in current['unresolved']])
        self.assertIsNone(current['assembly_basis']['runtime_arguments'])
        for path, raw in captured.items():
            if path.startswith('production/') or '/authoring/' in path or path.endswith('/context.json'):
                self.assertEqual((self.root / path).read_bytes(), raw, path)
        self.assertEqual(workflow.read_run(self.root, saved['run']).rows, [])

    def test_cli_mixed_runtime_branches_keep_their_own_target_resolution(self):
        from catalog_retrieval import runtime
        import production_target
        saved = workflow.prepare(self.root, self.task_path)
        bound = self.draft('registered', source_run=saved['run'])
        unbound = self.draft('unbound', source_run=saved['run'], registered=False)
        bound_again = self.draft('registered-again', source_run=saved['run'])
        other = self.other_runtime_arguments()
        original = self.source_snapshot()
        report = self.inspect_cli(runtime_arguments=other)
        branches = {row['choices']: row for row in report['inputs']}
        self.assertEqual(branches[bound]['unresolved'], [])
        self.assertEqual(branches[bound_again]['unresolved'], [])
        self.assertIn('target-evidence-required', [row.get('reason') for row in branches[unbound]['unresolved']])
        self.assertEqual(self.resolved_runtime(branches[bound]['assembly_basis']['runtime_arguments']),
                         self.resolved_runtime(self.runtime_arguments))
        self.assertEqual(self.resolved_runtime(branches[unbound]['assembly_basis']['runtime_arguments']),
                         self.resolved_runtime(other))
        self.assertTrue(report['selection_required'])
        for option in report['input_options']:
            expected = other if option['choices'] == unbound else self.runtime_arguments
            args = production_workflow_cli.build_parser().parse_args(option['action']['argv'][2:])
            self.assertEqual(args.state_file, Path(expected['state-file']).resolve())
            self.assertEqual([path.resolve() for path in args.pack_root], [Path(value).resolve() for value in expected['pack-root']])
        source_observations, catalog_observations = [], []
        source_run, target_runtime = inputs._source_run, production_target._runtime
        def observe_source(root, selected, *, read_run=None):
            if selected is not None and not isinstance(read_run, inputs.SourceRuns):
                source_observations.append(selected)
            return source_run(root, selected, read_run=read_run)
        def observe_runtime(source):
            if source is None:
                catalog_observations.append(runtime.selected_pack_settings().state_file)
            return target_runtime(source)
        parser = production_workflow_cli.build_parser()
        args = parser.parse_args(self.inspect_command(runtime_arguments=other)[3:])
        with (patch.object(inputs, '_source_run', side_effect=observe_source),
              patch.object(production_target, '_runtime', side_effect=observe_runtime)):
            inputs.command(args, parser)
        self.assertEqual(source_observations, [saved['run']])
        self.assertCountEqual(catalog_observations,
            [Path(self.runtime_arguments['state-file']), Path(other['state-file'])])
        self.assertEqual(self.source_snapshot(), original)

    def test_cli_inspection_rejects_partial_runtime_selection(self):
        choices_path = self.draft(registered=False)
        original = self.source_snapshot()
        command = self.inspect_command(choices_path, runtime_arguments={
            'state-file': self.runtime_arguments['state-file']})
        completed = subprocess.run(command, cwd=self.root, env=dict(os.environ), capture_output=True,
            text=True, encoding='utf-8', check=False, timeout=45)
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn('--state-file, --cache-dir, and --managed-root must be supplied together', completed.stderr)
        self.assertEqual(self.source_snapshot(), original)

    def test_authoring_without_editable_choices_does_not_acquire_unrelated_runs(self):
        earlier = workflow.prepare(self.root, self.task_path)['run']
        current = workflow.prepare(self.root, self.task_path)['run']
        observed = []
        def acquire(identifier):
            observed.append(identifier)
            return workflow.read_run(self.root, identifier)
        report = authoring.inspect(self.root, read_run=acquire)
        self.assertEqual(report['inputs'], [])
        self.assertEqual(report['diagnostics'], [])
        self.assertEqual(set(observed), {current})
        self.assertNotIn(earlier, observed)

    def test_fresh_default_status_resolves_the_prepared_drafts_registered_model(self):
        choices_path = self.draft()
        saved = workflow.prepare(self.root, choices=choices_path)
        original = (self.root / choices_path).read_bytes()
        command = [sys.executable, str(Path(production_workflow_cli.__file__)), 'status', '--root', str(self.root),
                   '--run', saved['run']]
        completed = subprocess.run(command, cwd=self.root, env=dict(os.environ),
            capture_output=True, text=True, encoding='utf-8', check=False, timeout=45)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        status = json.loads(completed.stdout)
        current = status['current_task']
        draft = next(row for row in current['authoring']['inputs'] if row.get('choices') == choices_path)
        self.assertEqual(draft['route_scope']['model'], self.model)
        self.assertEqual(draft['diagnostic_ids'], [])
        self.assertEqual(draft['prepared_run'], saved['run'])
        self.assertFalse(current['authoring']['pending'])
        self.assertEqual(current['focus'], 'execution')
        self.assertEqual((self.root / choices_path).read_bytes(), original)
        self.assertEqual(workflow.read_run(self.root, saved['run']).rows, [])

    def test_reopened_choices_use_current_registered_guidance_and_restore_the_callers_runtime(self):
        from catalog_retrieval import runtime
        import pack_manager
        saved = workflow.prepare(self.root, self.task_path)
        choices_path = self.draft('reopened', source_run=saved['run'])
        original = (self.root / choices_path).read_bytes()
        ledger = self.root / 'work/reads.jsonl'
        prior_readings = ledger.read_bytes()
        models_path = self.case['pack'] / 'records/models.json'
        models = c.load(models_path)
        next(row for row in models['records'] if row['id'] == self.model)['label'] = 'Current synthetic alternate guidance'
        c.atomic(models_path, c.encoded(models), replace=True)
        pack_manager.write_lock(self.case['pack'])
        runtime.configure_pack_runtime(None)
        ambient = runtime.selected_pack_settings()
        report = inputs.inspect_inputs(self.root)
        draft = next(row for row in report['inputs'] if row.get('choices') == choices_path)
        self.assertNotIn('target-evidence-required', [row.get('reason') for row in draft['unresolved']])
        reading = next(row for row in draft['unresolved'] if row['code'] == 'TARGET_GUIDANCE_REQUIRED')
        action = reading['next_action']
        self.assertEqual(action['args']['model'], self.model)
        for key, value in self.runtime_arguments.items():
            self.assertEqual(action['args'][key], value)
        self.assertEqual(runtime.selected_pack_settings(), ambient)
        self.assertNotIn(self.model, [entry.record.get('id') for entry in runtime.load_pack_catalog().entries])
        self.assertEqual((self.root / choices_path).read_bytes(), original)
        self.assertEqual(ledger.read_bytes(), prior_readings)
        self.assertTrue(report['pending'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
