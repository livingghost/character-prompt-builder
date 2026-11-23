"""Measure synthetic operation records without promoting diagnostics to authority."""
from __future__ import annotations

import json
import os
import contextlib
import copy
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import operation_context as operations
import operation_metrics as metrics
from production_diagnostics import Diagnostic, FAILURE_CATEGORIES


class MetricsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def record(self, name, command, events, *, parent=None, run='run-1', complete=True):
        folder = self.root / 'logs/operations/2026-11-23' / name
        folder.mkdir(parents=True)
        metadata = {'operation_id': name, 'command': 'production_workflow.py',
            'arguments': {'command': command}, 'context': {'run': run},
            'parent_operation': parent, 'created_at': '2026-11-23T00:00:00Z'}
        (folder / 'operation.json').write_text(json.dumps(metadata), encoding='utf-8')
        raw = ''.join(json.dumps(row) + '\n' for row in events)
        if not complete:
            raw += '{"event":"unfinished'
        (folder / 'events.jsonl').write_text(raw, encoding='utf-8')
        return folder

    def end(self, seconds, code=0, **extra):
        return {'event': 'completed', 'duration_seconds': seconds, 'exit_code': code,
                'complete': True, **extra}

    def logged(self, function, *, command='advance'):
        with patch.dict(os.environ, {'CPB_HOME': str(self.root)}), \
                patch.object(sys, 'argv', ['production_workflow.py', command]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            def invoke():
                operations.current().arguments(SimpleNamespace(command=command))
                return function()
            code = operations.run_cli(invoke)
        folder, = list(operations._log_folders(self.root))
        events = [json.loads(line) for line in (folder / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        return code, output.getvalue(), events

    def test_commands_stages_reading_edits_and_recovery_are_separate_units(self):
        self.record('first', 'advance', [
            {'event': 'reading_progress', 'delivered_pages': 1, 'delivered_bytes': 100,
             'reused_bytes': 200, 'snapshot': 'snapshot-a'},
            {'event': 'stage_completed', 'phase': 'provider-wait', 'duration_seconds': 4},
            {'event': 'stage_completed', 'phase': 'command', 'duration_seconds': 10},
            self.end(10)])
        self.record('second', 'resume', [
            {'event': 'reading_progress', 'delivered_pages': 1, 'delivered_bytes': 50,
             'reused_bytes': 0, 'snapshot': 'snapshot-a'}, self.end(3)], parent='first')
        self.record('third', 'edit-choices', [
            {'event': 'authored_edit', 'choices': 'draft/choices.json',
             'pointer': '/authoring/task/criteria', 'changed': True}, self.end(1)])
        self.record('waiting', 'execute', [self.end(2, 3)])
        self.record('refused', 'execute', [self.end(1, 4,
            diagnostic={'code': 'PROVIDER_REJECTION'})])
        result = metrics.summarize(self.root)
        self.assertEqual(result['totals']['calls'], 5)
        self.assertEqual(result['totals']['seconds'], 17)
        self.assertEqual(result['totals']['top_level_seconds'], 14)
        self.assertEqual(result['totals']['failed_calls'], 1)
        self.assertEqual(result['totals']['waiting_calls'], 1)
        self.assertEqual(result['totals']['recovery_calls'], 1)
        self.assertEqual(result['reading'], {'delivered_pages': 2, 'delivered_bytes': 150,
            'reused_bytes': 200, 'reported_calls': 2, 'snapshots': 1})
        self.assertEqual(result['editing']['targets'], [{'choices': 'draft/choices.json',
            'pointer': '/authoring/task/criteria', 'calls': 1}])
        self.assertEqual(result['provider']['stages'][0]['seconds'], 4)
        self.assertIsNone(result['provider']['external_host_seconds'])
        self.assertIsNone(result['judgment_pending']['active_author_seconds'])
        self.assertEqual(result['failures_by_category'], {'provider': 1})

    def test_incomplete_and_corrupt_records_remain_visible_without_invented_time(self):
        self.record('incomplete', 'prepare', [{'event': 'started'}], complete=False)
        folder = self.record('corrupt', 'prepare', [])
        (folder / 'events.jsonl').write_text('invalid JSON\n', encoding='utf-8')
        self.record('finished', 'prepare', [self.end(5)])
        result = metrics.summarize(self.root)
        self.assertFalse(result['ok'])
        self.assertTrue(result['partial'])
        self.assertEqual(result['totals']['calls'], 2)
        self.assertEqual(result['totals']['incomplete_calls'], 1)
        self.assertEqual(result['totals']['seconds'], 5)
        self.assertEqual(result['diagnostics'][0]['operation_id'], 'corrupt')
        self.assertIsNone(result['judgment_pending']['seconds'])

    def test_scope_and_observation_leave_all_log_bytes_unchanged(self):
        self.record('selected', 'prepare', [self.end(1)])
        self.record('other', 'prepare', [self.end(2)], run='run-2')
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = metrics.summarize(self.root, run='run-1')
        self.assertEqual(result['totals']['calls'], 1)
        self.assertEqual(metrics.summarize(self.root, operation_id='other')['totals']['seconds'], 2)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_pending_interval_is_once_per_answer_and_latest_plan_is_observed(self):
        common = {'plan_id': 'plan-1', 'item': 'portrait', 'answer_file': 'review.json'}
        self.record('first', 'advance', [
            {'event': 'judgment_pending', 'at': '2026-11-23T00:00:00Z', **common},
            {'event': 'judgment_pending', 'at': '2026-11-23T00:00:05Z', **common},
            {'event': 'plan_continuation', 'plan_id': 'plan-1', 'choices': 'old.json',
             'at': '2026-11-23T00:00:00Z'}, self.end(1)])
        self.record('second', 'advance', [
            {'event': 'judgment_answered', 'at': '2026-11-23T00:00:10Z', **common},
            {'event': 'plan_continuation', 'plan_id': 'plan-1', 'choices': 'current.json',
             'at': '2026-11-23T00:00:10Z', 'unchanged_since_previous': True}, self.end(1)])
        result = metrics.summarize(self.root)
        self.assertEqual(result['judgment_pending']['seconds'], 10)
        self.assertEqual(result['judgment_pending']['completed_intervals'], 1)
        self.assertEqual(result['plans'][0]['choices'], 'current.json')
        self.assertEqual(result['totals']['unchanged_continuations'], 1)

    def test_superseded_wait_is_separate_from_answered_time(self):
        common = {'plan_id': 'plan-1', 'phase': 'review'}
        self.record('revision', 'plan', [
            {'event': 'judgment_pending', 'at': '2026-11-23T00:00:00Z',
             'answer_file': 'original.json', **common},
            {'event': 'judgment_superseded', 'at': '2026-11-23T00:00:10Z',
             'answer_file': 'original.json', 'successor_answer_file': 'current.json', **common},
            {'event': 'judgment_pending', 'at': '2026-11-23T00:00:10Z',
             'answer_file': 'current.json', **common},
            {'event': 'judgment_answered', 'at': '2026-11-23T00:00:25Z',
             'answer_file': 'current.json', **common},
            {'event': 'judgment_superseded', 'at': '2026-11-23T00:00:30Z',
             'answer_file': 'current.json', 'successor_answer_file': 'later.json', **common},
            {'event': 'judgment_pending', 'at': '2026-11-23T00:00:30Z',
             'answer_file': 'later.json', **common}, self.end(1)])
        pending = metrics.summarize(self.root)['judgment_pending']
        self.assertEqual(pending['completed_intervals'], 1)
        self.assertEqual(pending['seconds'], 15)
        self.assertEqual(pending['superseded_intervals'], 1)
        self.assertEqual(pending['superseded_seconds'], 10)
        self.assertEqual(pending['open_intervals'], 1)

    def test_actual_answer_renewal_emits_its_own_pending_without_exposing_answers(self):
        import execution_contract as c
        import production_work_plan as plans
        directory = self.root / 'plan'
        directory.mkdir()
        entry = {'answers': {}, 'evidence': {}, 'phase': 'review', 'status': 'needs-input'}
        draft = {'choices': {'reason': '', 'checks': []}, 'binding': {'review': 'original'}}

        def invoke():
            operations.current().link(plan_id='plan-1')
            plans._answer(self.root, directory, entry, 'review', draft)
            plans._renew_answer(self.root, directory, entry, 'review',
                {**draft, 'binding': {'review': 'current'}})
            path = self.root / entry['answers']['review']['file']
            path.write_bytes(c.encoded({'reason': 'Private authored review marker.', 'checks': []}))
            plans._answer(self.root, directory, entry, 'review', draft)
            plans._answer(self.root, directory, entry, 'review', draft)
            return 0

        code, _, events = self.logged(invoke, command='plan')
        self.assertEqual(code, 0)
        judgments = [event for event in events if event['event'].startswith('judgment_')]
        self.assertEqual([event['event'] for event in judgments],
            ['judgment_pending', 'judgment_superseded', 'judgment_pending', 'judgment_answered'])
        self.assertEqual(judgments[0]['answer_file'], judgments[1]['answer_file'])
        self.assertEqual(judgments[1]['successor_answer_file'], judgments[2]['answer_file'])
        self.assertEqual(judgments[2]['answer_file'], judgments[3]['answer_file'])
        self.assertNotIn('Private authored review marker.', json.dumps(events))
        pending = metrics.summarize(self.root)['judgment_pending']
        self.assertEqual((pending['completed_intervals'], pending['superseded_intervals'], pending['open_intervals']),
                         (1, 1, 0))

    def test_plan_failure_codes_ignore_nested_history_and_keep_the_cli_outcome(self):
        import production_workflow as workflow
        authority = Diagnostic('AUTHORIZATION_REQUIRED', 'Current approval is missing.').as_dict()
        report = {'ok': False, 'state': 'blocked', 'items': [
            {'state': 'blocked', 'diagnostic': authority, 'current': {'diagnostic': authority,
                'inspection': {'diagnostics': [Diagnostic('PROVIDER_REJECTION', 'Historical report.').as_dict()]}}},
            {'state': 'complete', 'diagnostic': Diagnostic('INPUT_SCHEMA_INVALID', 'Stale historical report.').as_dict()}]}
        original = copy.deepcopy(report)

        def invoke():
            workflow._print_report(SimpleNamespace(view='full', root=self.root, command='advance'), report)
            return 2

        code, output, events = self.logged(invoke)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output), original)
        self.assertEqual(report, original)
        command = next(event for event in events if event['event'] == 'command_result')
        self.assertEqual(command['failure_codes'], ['AUTHORIZATION_REQUIRED'])
        self.assertFalse(command['unclassified_failure'])
        self.assertEqual(events[-1]['exit_code'], 2)
        self.assertEqual(events[-1]['diagnostic']['code'], 'AUTHORIZATION_REQUIRED')
        measured = metrics.summarize(self.root)
        self.assertEqual(measured['failures_by_category'], {'authority': 1})
        self.assertEqual(measured['totals']['failed_calls'], 1)

    def test_verification_text_stays_unclassified_and_does_not_enter_metric_events(self):
        import production_workflow as workflow
        report = {'ok': False, 'state': 'verification-required', 'verification': {
            'ok': False, 'errors': ['Uncoded validation detail marker.'],
            'projection': {'ok': False, 'diagnostics': [
                Diagnostic('STUDIO_PROJECTION_FAILED', 'Current view could not publish.').as_dict()]}}}

        def invoke():
            workflow._print_report(SimpleNamespace(view='full', root=self.root, command='advance'), report)
            return 2

        code, _, events = self.logged(invoke)
        self.assertEqual(code, 2)
        self.assertNotIn('Uncoded validation detail marker.', json.dumps(events))
        measured = metrics.summarize(self.root)
        self.assertEqual(measured['failures_by_category'], {'environment': 1, 'unclassified': 1})

    def test_uncoded_failure_does_not_invent_an_input_diagnostic(self):
        import production_workflow as workflow

        def invoke():
            workflow._print_report(SimpleNamespace(view='full', root=self.root, command='advance'),
                {'ok': False, 'state': 'verification-required', 'verification': {
                    'ok': False, 'errors': ['Unclassified validation finding.']}})
            return 2

        code, _, events = self.logged(invoke)
        self.assertEqual(code, 2)
        self.assertNotIn('diagnostic', events[-1])
        self.assertEqual(metrics.summarize(self.root)['failures_by_category'], {'unclassified': 1})

    def test_waiting_exit_remains_waiting_after_capturing_a_nested_diagnostic(self):
        import production_workflow as workflow

        def invoke():
            workflow._print_report(SimpleNamespace(view='full', root=self.root, command='advance'),
                {'ok': False, 'state': 'blocked', 'items': [{'state': 'blocked',
                    'diagnostic': Diagnostic('AUTHORIZATION_REQUIRED', 'Current approval is missing.').as_dict()}]})
            return operations.WAITING_EXIT

        code, _, events = self.logged(invoke)
        self.assertEqual(code, operations.WAITING_EXIT)
        self.assertEqual(events[-1]['exit_code'], operations.WAITING_EXIT)
        measured = metrics.summarize(self.root)
        self.assertEqual(measured['totals']['waiting_calls'], 1)
        self.assertEqual(measured['totals']['failed_calls'], 0)
        self.assertEqual(measured['failures_by_category'], {})

    def test_symlink_stream_is_not_read_and_secret_text_remains_redacted(self):
        external = self.root / 'external-events.jsonl'
        external.write_text(json.dumps(self.end(99)) + '\n', encoding='utf-8')
        folder = self.record('linked', 'prepare', [])
        (folder / 'events.jsonl').unlink()
        try:
            (folder / 'events.jsonl').symlink_to(external)
        except (OSError, NotImplementedError):
            return
        with patch.dict(os.environ, {'TEST_API_KEY': 'private-metric-key'}):
            self.record('private-metric-key', 'prepare', [self.end(1)])
            result = metrics.summarize(self.root)
        self.assertTrue(result['partial'])
        self.assertEqual(result['totals']['seconds'], 1)
        self.assertNotIn('private-metric-key', json.dumps(result))


class DiagnosticCategoryTests(unittest.TestCase):
    def test_continuation_observation_detects_real_owner_edits_without_mutating_them(self):
        import execution_contract as c
        import production_work_plan as plans
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'draft').mkdir()
            (root / 'draft/choices.json').write_bytes(c.encoded({'choice': 'first'}))
            (root / 'draft/context.json').write_bytes(c.encoded({'authoring_work': {'basis': 'draft/basis.json'}}))
            (root / 'draft/basis.json').write_bytes(c.encoded({'request': 'same commission'}))
            state = {'status': 'active', 'items': {'one': {'source': {'choices': 'draft/choices.json'},
                'run': None, 'phase': 'authoring', 'status': 'needs-input', 'evidence': {}, 'current': {}}}}
            plans._observe_continuation(root, state)
            plans._observe_continuation(root, state)
            self.assertTrue(state['continuation_observation']['unchanged_since_previous'])
            (root / 'draft/basis.json').write_bytes(c.encoded({'request': 'changed commission'}))
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])
            (root / 'draft/choices.json').unlink()
            plans._observe_continuation(root, state)
            self.assertIsNone(state['continuation_observation']['unchanged_since_previous'])
            self.assertEqual(state['continuation_observation']['unavailable'][0]['file'], 'draft/choices.json')
            self.assertFalse((root / 'draft/choices.json').exists())

    def test_batch_observation_tracks_later_panels_and_the_batch_owner(self):
        import execution_contract as c
        import production_work_plan as plans
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('first', 'second'):
                (root / (name + '.json')).write_bytes(c.encoded({'reason': ''}))
            (root / 'batch.json').write_bytes(c.encoded({'panels': ['first', 'second']}))
            panels = {name: {'source': {'run': name}, 'run': name, 'candidate': 'candidate-' + name,
                'phase': 'curation', 'status': 'needs-input', 'evidence': {},
                'current': {'answer_file': name + '.json'}} for name in ('first', 'second')}
            entry = {'source': {'batch': 'batch.json'}, 'run': None, 'phase': 'batch',
                'status': 'needs-input', 'evidence': {}, 'panels': panels,
                'current': {'panel': 'first', 'answer_file': 'first.json'}}
            state = {'status': 'active', 'items': {'batch': entry}}
            original = {path: path.read_bytes() for path in root.iterdir()}
            plans._observe_continuation(root, state)
            plans._observe_continuation(root, state)
            self.assertTrue(state['continuation_observation']['unchanged_since_previous'])
            self.assertEqual(state['continuation_observation']['tracked_files'],
                             ['batch.json', 'first.json', 'second.json'])
            self.assertEqual({path: path.read_bytes() for path in original}, original)
            (root / 'second.json').write_bytes(c.encoded({'reason': 'Current second-panel answer.'}))
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])
            plans._observe_continuation(root, state)
            panels['second'].update(phase='complete', status='complete', current=None,
                                    evidence={'result': {'adoption': 'retained second-panel result'}})
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])
            plans._observe_continuation(root, state)
            (root / 'batch.json').write_bytes(c.encoded({'panels': ['first', 'second', 'third']}))
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])
            (root / 'first.json').unlink()
            plans._observe_continuation(root, state)
            self.assertIsNone(state['continuation_observation']['unchanged_since_previous'])
            self.assertIn('first.json', [row['file'] for row in state['continuation_observation']['unavailable']])

    def test_completion_observation_tracks_work_answers_and_current_findings(self):
        import execution_contract as c
        import production_work_plan as plans
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            answer = root / 'work-steps.json'
            answer.write_bytes(c.encoded({'steps': {'1': None, '2': None}}))
            state = {'status': 'work-required', 'items': {'one': {
                'source': {'run': 'run-one'}, 'run': 'run-one', 'phase': 'complete',
                'status': 'complete', 'evidence': {'result': 'retained'}, 'current': None}},
                'work_input': {'answer_file': 'work-steps.json'},
                'remaining_work': {'steps': [1, 2]}, 'verification': {'ok': True}}
            plans._observe_continuation(root, state)
            plans._observe_continuation(root, state)
            self.assertTrue(state['continuation_observation']['unchanged_since_previous'])
            answer.write_bytes(c.encoded({'steps': {'1': 'results', '2': None}}))
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])
            plans._observe_continuation(root, state)
            state['remaining_work']['steps'] = [2]
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])
            plans._observe_continuation(root, state)
            state['verification'] = {'ok': False, 'errors': ['Current changed view finding.']}
            plans._observe_continuation(root, state)
            self.assertFalse(state['continuation_observation']['unchanged_since_previous'])

    def test_repair_roles_and_source_locations_remain_independent_of_exit_status(self):
        cases = {'INPUT_SCHEMA_INVALID': 'input', 'AUTHORIZATION_REQUIRED': 'authority',
            'PLACEMENT_CONFLICT': 'state-conflict', 'DEPENDENCY_UNAVAILABLE': 'environment',
            'PROVIDER_REJECTION': 'provider'}
        for code, category in cases.items():
            with self.subTest(code=code):
                result = Diagnostic(code, 'Synthetic failure.', file='draft/choices.json',
                    pointer='/target', required_action='Correct the target at its source.').as_dict()
                self.assertEqual(result['category'], category)
                self.assertEqual(result['repair_responsibility'], FAILURE_CATEGORIES[category])
                self.assertEqual((result['file'], result['pointer']), ('draft/choices.json', '/target'))

    def test_summary_public_cli_rejects_an_ambiguous_failed_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, 'CPB_HOME': folder}
            command = [sys.executable, str(Path(__file__).with_name('production_workflow.py')),
                       'logs', '--summary', '--failed']
            result = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 2, result.stderr)
        diagnostic = json.loads(result.stdout)['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'INPUT_ARGUMENT_INVALID')
        self.assertIn('Omit --failed', diagnostic['required_action'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
