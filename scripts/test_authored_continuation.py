"""Saved authored work and edited sources expose the same next action at each entry."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import execution_contract as c
import production_authoring_state as authoring
import production_fixtures as fixtures
import production_inputs as inputs
import production_workflow as workflow
import session_entry_points
import studio
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
        drafted = inputs.draft_inputs(self.root, 'task.json', 'edit')
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

    def test_session_exposes_saved_text_once_without_suggesting_external_recovery(self):
        saved = workflow.save(self.root, self.choices_path)
        text = '\n'.join(session_entry_points.authoring_lines(self.root))
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

    def draft(self, directory='edit', *, source_run=None):
        result = inputs.draft_inputs(self.root, self.task_path if source_run is None else None,
            directory, from_run=source_run, runtime_arguments=self.runtime_arguments)
        self.assertEqual(result['unresolved'], [], result)
        return result['choices_file']

    def test_fresh_default_status_resolves_the_prepared_drafts_registered_model(self):
        choices_path = self.draft()
        saved = workflow.prepare(self.root, choices=choices_path)
        original = (self.root / choices_path).read_bytes()
        command = [sys.executable, str(Path(workflow.__file__)), 'status', '--root', str(self.root),
                   '--run', saved['run']]
        completed = subprocess.run(command, cwd=self.root, env=dict(os.environ),
            capture_output=True, text=True, encoding='utf-8', check=False, timeout=45)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        status = json.loads(completed.stdout)
        current = status['current_task']
        draft = next(row for row in current['authoring']['inputs'] if row.get('choices') == choices_path)
        self.assertEqual(draft['route_scope']['model'], self.model)
        self.assertEqual(draft['unresolved'], [])
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
        self.assertNotIn('target-evidence-required', [row['code'] for row in draft['unresolved']])
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
