#!/usr/bin/env python3
"""Synthetic single-panel dispatch, approval stops, recovery and batch provenance."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import sheet_batch as batch
import sheet_artifacts as fills
import transport_synthetic


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = self.case['root']
        task = c.load(self.root / 'task.json')
        task['recording'].update(slot='canon.primary', sheet_panel=True, subject_map={'robot': 'robot'})
        fixtures.write(self.root / 'task.json', task)
        self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        self.manifest = {'requests': [{'request_id': 'canon.primary', 'resolved_slot_id': 'canon.primary',
                         'result_file': 'anchor.png', 'target': {'generation_w':32, 'generation_h':32}, 'generation_stage': 1, 'required_accepted_reference_results': []}]}
        fixtures.write(self.root / 'panel-fill-requests.json', self.manifest)
        self.plan = {'artifact_type': 'sheet-fill-plan', 'manifest': 'panel-fill-requests.json',
                     'sheet': self.sheet.relative_to(self.root).as_posix(), 'results': 'model-fill/results',
                     'panels': [{'request_id': 'canon.primary', 'task': 'task.json', 'references': []}]}
        fixtures.write(self.root / 'batch-plan.json', self.plan)
        batch.initialize(self.root, 'batch-plan.json', 'batch.json')

    def prepare(self):
        result = batch.advance(self.root, 'batch.json', grant='fixture-grant')
        entry = result['panels']['canon.primary']
        self.assertEqual(entry['status'], 'approval-required', entry)
        return entry['run']

    def execute(self):
        run = self.prepare()
        decisions = fixtures.fill_decisions(self.root, run, 'approved.json')
        result = batch.advance(self.root, 'batch.json', decisions={'canon.primary': decisions})
        self.assertTrue(result['ok'], result)
        return result

    def test_preparation_drafts_but_does_not_send_or_accept(self):
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('no approval')):
            self.prepare()
        self.assertIsNone(c.load(self.sheet)['slots'].get('canon.primary', {}).get('current'))

    def test_execute_exports_full_result_package_and_exchange_as_candidate(self):
        result = self.execute()
        folder = self.root / result['panels']['canon.primary']['results']
        for name in ('anchor.png', 'anchor.package.json', 'anchor.request.json', 'anchor.response.json', 'anchor.answer.json', 'anchor.artifact.json'):
            self.assertTrue((folder / name).is_file(), name)
        artifact = result['panels']['canon.primary']['artifact']
        self.assertEqual(c.sha256_file(folder / 'anchor.png'), artifact['image']['sha256'])
        slot = c.load(self.sheet)['slots']['canon.primary']
        self.assertIsNone(slot['current'])
        self.assertEqual(slot['candidates'], [artifact])

    def test_unreceived_recovery_repairs_export_without_resending(self):
        original = self.execute()
        (self.root / original['panels']['canon.primary']['results'] / 'anchor.png').unlink()
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('no repeat send')):
            result = batch.advance(self.root, 'batch.json', unreceived_only=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['panels']['canon.primary']['artifact'], original['panels']['canon.primary']['artifact'])
        self.assertTrue((self.root / result['panels']['canon.primary']['results'] / 'anchor.png').is_file())

    def test_unknown_response_is_not_a_retry_permission(self):
        run = self.prepare(); decisions = fixtures.fill_decisions(self.root, run, 'approved.json')
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('synthetic unknown')) as send:
            first = batch.advance(self.root, 'batch.json', decisions={'canon.primary': decisions})
            second = batch.advance(self.root, 'batch.json', unreceived_only=True)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(first['panels']['canon.primary']['status'], 'recovery-required')
        self.assertFalse(second['ok'])

    def test_changed_task_requires_a_distinct_redo_plan(self):
        task = c.load(self.root / 'task.json'); task['generation']['seed'] = 72
        fixtures.write(self.root / 'task.json', task)
        result = batch.advance(self.root, 'batch.json')
        self.assertEqual(result['exit_code'], 2)
        self.assertIn('batch task changed', result['panels']['canon.primary']['diagnostic']['message'])

    def test_duplicate_result_names_are_refused_before_any_preparation(self):
        bad = copy.deepcopy(self.manifest); second = copy.deepcopy(bad['requests'][0]); second['request_id'] = 'other'
        bad['requests'].append(second); fixtures.write(self.root / 'panel-fill-requests.json', bad)
        with self.assertRaisesRegex(ValueError, 'unique plain PNG'):
            batch.read_plan(self.root, 'batch-plan.json')

    def test_missing_accepted_anchor_stops_before_dispatch(self):
        self.manifest['requests'][0]['required_accepted_reference_results'] = ['canon.primary']
        fixtures.write(self.root / 'panel-fill-requests.json', self.manifest)
        (self.root / 'batch.json').unlink(); batch.initialize(self.root, 'batch-plan.json', 'batch.json')
        result = batch.advance(self.root, 'batch.json', grant='fixture-grant')
        self.assertEqual(result['panels']['canon.primary']['status'], 'blocked')
        self.assertIn('accepted anchor', result['panels']['canon.primary']['diagnostic']['message'])

    def test_dimensions_are_checked_before_any_send(self):
        self.manifest['requests'][0]['target']['generation_w'] = 64
        fixtures.write(self.root / 'panel-fill-requests.json', self.manifest)
        (self.root / 'batch.json').unlink(); batch.initialize(self.root, 'batch-plan.json', 'batch.json')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('wrong geometry')):
            result = batch.advance(self.root, 'batch.json', grant='fixture-grant')
        self.assertEqual(result['panels']['canon.primary']['status'], 'blocked')
        self.assertIn('dimensions', result['panels']['canon.primary']['diagnostic']['message'])

    def test_reference_stage_pins_one_accepted_anchor_and_copies_companion(self):
        from sheet_artifacts_smoke_test import accepted
        spec = c.load(self.root / 'spec.json')
        spec['render_intent']['execution_mode'] = 'reference-guided'
        fixtures.write(self.root / 'spec.json', spec)
        task = c.load(self.root / 'task.json')
        task['recording']['slot'] = 'canon.side'
        fixtures.write(self.root / 'side-task.json', task)
        self.manifest['requests'].append({'request_id':'canon.side', 'resolved_slot_id':'canon.side',
            'result_file':'side.png','target':{'generation_w':32,'generation_h':32},
            'generation_stage':2,'required_accepted_reference_results':['canon.primary']})
        self.plan['panels'] = [{'request_id':'canon.side','task':'side-task.json',
                               'references':[{'slot':'canon.primary','artifact_id':None,'role':'identity'}]}]
        fixtures.write(self.root / 'panel-fill-requests.json', self.manifest)
        fixtures.write(self.root / 'batch-plan.json', self.plan)
        (self.root / 'batch.json').unlink(); batch.initialize(self.root, 'batch-plan.json', 'batch.json')
        blocked = batch.advance(self.root, 'batch.json', grant='fixture-grant')['panels']['canon.side']
        self.assertEqual(blocked['status'], 'blocked')
        anchor = accepted(self.sheet, size=(32,32))
        entry = batch.advance(self.root, 'batch.json', grant='fixture-grant')['panels']['canon.side']
        self.assertEqual(entry['status'], 'approval-required', entry)
        self.assertEqual(entry['selected_references'][0]['artifact'], anchor)
        approved = fixtures.fill_decisions(self.root, entry['run'], 'side-approved.json')
        result = batch.advance(self.root, 'batch.json', decisions={'canon.side':approved})
        self.assertTrue(result['ok'], result)
        from verify_generation_payload import verify
        package_path = self.root / result['panels']['canon.side']['results'] / 'side.package.json'
        package = c.load(package_path)
        self.assertEqual(len(package['prepared_reference_set']['selected_references']), 1)
        from build_generation_payload import validate_generation_package_carrier_paths
        companion = validate_generation_package_carrier_paths(package['prepared_reference_set'], package_root=package_path.parent)
        self.assertTrue((package_path.parent / companion).is_dir())
        from production_workflow import load_run
        directory, prepared, _, _ = load_run(self.root, entry['run'])
        import runtime_snapshot
        with runtime_snapshot.using(runtime_snapshot.path(self.root,prepared['runtime_snapshot']),prepared['runtime_snapshot']):
            verify(package, package_root=package_path.parent, studio=self.root, reading_ledgers=[directory/'reads.jsonl'])

    def test_partial_export_cannot_overwrite_different_pixels(self):
        initial = self.execute(); fixtures.write(self.root / initial['panels']['canon.primary']['results'] / 'anchor.png', 'not the captured image')
        result = batch.advance(self.root, 'batch.json', unreceived_only=True)
        self.assertEqual(result['panels']['canon.primary']['status'], 'blocked')
        self.assertIn('different bytes', result['panels']['canon.primary']['diagnostic']['message'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
