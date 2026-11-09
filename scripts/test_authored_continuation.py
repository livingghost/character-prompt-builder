"""Saved authored work and edited sources expose the same next action at each entry."""
from __future__ import annotations

from pathlib import Path
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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
