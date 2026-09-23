#!/usr/bin/env python3
"""Exercise resume reports against synthetic immutable records without network I/O."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import execution_contract as c
import production_workflow as w
import reservation_lifecycle as lifecycle
import route_reading
from reading_fixtures import task_reading

RUN = '01900000-0000-7000-8000-000000000001'
TASK = '01900000-0000-7000-8000-000000000002'
ACTOR = 'synthetic operator'


class ResumeFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'production' / RUN
        (self.directory / 'records').mkdir(parents=True)
        (self.root / 'source.txt').write_text('Synthetic source material.\n', encoding='utf-8')
        (self.root / 'delivery.txt').write_text('Synthetic retained instructions.\n', encoding='utf-8')
        task = make_task(self.root)
        task_reading(self.root, task)
        reading = c.load(self.root / task['route_reading'])
        consumer = {'instructions': 'Synthetic retained instructions.'}
        dependencies = []
        for name in ('source.txt', 'delivery.txt', task['route_reading']):
            raw = c.read(self.root / name)
            key = c.object_store(self.directory, raw)
            dependencies.append({'space': 'project', 'path': name, 'sha256': key, 'size': len(raw)})
        self.prepared = {'task_path': 'task.json', 'task': task, 'route': {'reads': []},
            'dependencies': dependencies, 'consumer_sha256': c.content_id(consumer),
            'route_reading': reading, 'route_reading_sha256': c.content_id(reading)}
        add_authority(self.prepared)
        self.prepared['input_sha256'] = c.content_id(self.prepared)
        c.atomic(self.directory / 'prepared.json', c.encoded(self.prepared))
        c.atomic(self.directory / 'consumer.json', c.encoded(consumer))
        with c.lock(self.root):
            pass
        self.token = add_reservation(self)

    def append(self, event, data):
        directory, prepared, _, rows = w.load_run(self.root, RUN)
        return w.append_record(directory, prepared, rows, event, data)

    def claim(self):
        self.handoff = self.append('handoff', {'recipient': 'synthetic receiver', 'method': 'dispatcher',
                                              'consumer_sha256': self.prepared['consumer_sha256']})
        self.claim_record = self.append('dispatch-claim', claim_data(self.token))
        return self.claim_record

    def step(self, operation):
        if not hasattr(self, 'claim_record'):
            self.claim()
        if not hasattr(self, 'boundary'):
            self.boundary = lifecycle.begin(self.root, RUN, self.token, effect='external-io', claim=self.claim_record['sha256'])
        return self.append('external-step', {'reservation': lifecycle.selector(RUN, self.token),
            'start': self.boundary['sha256'], 'claim': self.claim_record['sha256'], 'step': operation,
            'operation': operation, 'request_sha256': self.boundary['data']['request_sha256']})

    def start(self):
        return self.step('send')

    def outputs(self):
        self.start()
        (self.root / 'result.txt').write_text('Synthetic acquired output.\n', encoding='utf-8')
        item = w.file_record(self.root, self.directory, 'result.txt')
        return self.append('dispatch-results', {'claim': self.claim_record['sha256'], 'files': [item],
                                               'evidence': [], 'expected_count': 1})

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}



class ResumeTests(ResumeFixture, unittest.TestCase):
    def test_missing_reading_is_not_current_evidence(self):
        import production_resume
        prepared = copy.deepcopy(self.prepared)
        del prepared['route_reading']
        result = production_resume._freshness(self.root, prepared, [])
        self.assertFalse(result['current'])
        self.assertFalse(result['reading']['current'])

    def test_current_report_is_read_only(self):
        before = self.files()
        report = w.status(self.root, RUN)
        self.assertTrue(report['integrity']['ok'])
        self.assertTrue(report['freshness']['current'])
        self.assertEqual(report['freshness']['reading'], {'current': True})
        self.assertEqual(self.files(), before)
        self.assertFalse(report['execution']['new_submission_allowed_by_this_report'])

    def test_changed_source_keeps_saved_reservations(self):
        (self.root / 'source.txt').write_text('Changed synthetic premise.', encoding='utf-8')
        report = w.status(self.root, RUN)
        self.assertFalse(report['ok'])
        self.assertTrue(report['integrity']['ok'])
        self.assertEqual(report['next'], 'inspect-impact-and-refresh-inputs')
        self.assertEqual(report['reservations'][0]['original_sha256'], self.token)
        self.assertIn('draft-release', [a['operation'] for a in report['next_actions']])

    def test_changed_source_does_not_hide_uncertain_send(self):
        self.start()
        (self.root / 'source.txt').write_text('Changed synthetic premise.', encoding='utf-8')
        report = w.status(self.root, RUN)
        self.assertEqual(report['next'], 'recover-recording-or-resolve-remote-status')
        self.assertEqual(report['execution']['state'], 'boundary-recorded-outcome-unconfirmed')
        self.assertFalse(report['execution']['provider_charge']['confirmed'])
        self.assertNotIn('prepare', [a['operation'] for a in report['next_actions']])
        self.assertNotIn('draft-release', [a['operation'] for a in report['next_actions']])

    def test_retained_outputs_take_priority_over_new_preparation(self):
        result = self.outputs()
        (self.root / 'source.txt').write_text('Changed synthetic premise.', encoding='utf-8')
        report = w.status(self.root, RUN)
        self.assertEqual(report['next'], 'recover-recording')
        self.assertEqual(report['execution']['result_receipt'], result['sha256'])
        action = next(a for a in report['next_actions'] if a['operation'] == 'recover-recording')
        self.assertEqual(action['external_effect'], 'none')
        self.assertEqual(action['budget_effect'], 'none')
        self.assertTrue(any(a['event'] == 'dispatch-results' for a in report['artifacts']))

    def test_boundary_is_not_reported_as_provider_completion(self):
        self.start()
        report = w.status(self.root, RUN)
        self.assertIsNone(report['execution']['result_receipt'])
        self.assertEqual(len(report['execution']['boundaries']), 1)
        self.assertFalse(report['execution']['provider_charge']['confirmed'])

    def test_local_claim_is_distinct_from_started(self):
        self.claim()
        report = w.status(self.root, RUN)
        self.assertEqual(report['execution']['state'], 'claimed-before-send')
        self.assertEqual(report['next'], 'inspect-unsent-claim')
        self.assertEqual(report['reservations'][0]['status'], 'reserved')

    def test_upload_without_send_offers_release(self):
        self.step('upload')
        report = w.status(self.root, RUN)
        self.assertEqual(report['execution']['state'], 'claimed-before-send')
        self.assertIn('draft-release', [a['operation'] for a in report['next_actions']])

    def test_report_reads_only_recorded_event_names(self):
        import ast
        import production_resume
        tree = ast.parse(Path(production_resume.__file__).read_text(encoding='utf-8'))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Subscript) \
                    and isinstance(node.left.slice, ast.Constant) and node.left.slice.value == 'event':
                for value in node.comparators:
                    items = value.elts if isinstance(value, (ast.Set, ast.Tuple, ast.List)) else [value]
                    names.update(x.value for x in items if isinstance(x, ast.Constant))
        self.assertTrue(names)
        self.assertLessEqual(names, w.EVENTS)

    def test_missing_source_is_a_freshness_issue_not_an_empty_run(self):
        self.start()
        (self.root / 'source.txt').unlink()
        report = w.status(self.root, RUN)
        self.assertTrue(report['integrity']['ok'])
        self.assertFalse(report['freshness']['current'])
        self.assertEqual(report['execution']['claim'], self.claim_record['sha256'])

    def test_corrupt_chain_is_not_reported_as_unstarted(self):
        path = sorted((self.directory / 'records').iterdir())[-1]
        path.write_bytes(b'{}')
        report = w.status(self.root, RUN)
        self.assertFalse(report['integrity']['ok'])
        self.assertEqual(report['execution']['state'], 'unknown')
        self.assertIsNone(report['reservations'])
        self.assertEqual(report['next_actions'], [])

    def test_missing_frozen_source_is_an_integrity_failure(self):
        (self.directory / 'objects' / self.prepared['dependencies'][0]['sha256']).unlink()
        report = w.status(self.root, RUN)
        self.assertFalse(report['integrity']['ok'])
        self.assertEqual(report['next'], 'inspect-integrity')

    def test_status_does_not_call_live_execution_verifier(self):
        with patch.object(w, 'assert_current', side_effect=AssertionError('status called live execution')):
            report = w.status(self.root, RUN)
        self.assertTrue(report['integrity']['ok'])

    def test_stale_reading_is_separate_from_external_evidence(self):
        self.start()
        with patch.object(route_reading, 'require_route_reading', side_effect=ValueError('Synthetic document update.')):
            report = w.status(self.root, RUN)
        self.assertFalse(report['freshness']['reading']['current'])
        self.assertEqual(report['execution']['claim'], self.claim_record['sha256'])
        self.assertEqual(report['next'], 'recover-recording-or-resolve-remote-status')

    def test_cli_resume_reports_stale_run_without_writing(self):
        self.start()
        (self.root / 'source.txt').write_text('Changed synthetic premise.', encoding='utf-8')
        before = self.files()
        result = subprocess.run([sys.executable, str(Path(w.__file__)), 'resume', '--root', str(self.root), '--run', RUN],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['integrity']['ok'])
        self.assertEqual(report['execution']['claim'], self.claim_record['sha256'])
        self.assertEqual(self.files(), before)


def make_task(root):
    return {'task_id': TASK, 'route': 'development', 'features': [], 'execution': 'dispatcher',
            'artifact': 'text', 'sources': [], 'criteria': [], 'authority': 'authority.json'}


def add_authority(prepared):
    prepared['authority'] = {'issuer': 'synthetic principal', 'stop_conditions': [],
                             'grants': [{'id': 'synthetic-grant', 'actor': ACTOR}]}


def add_reservation(test):
    request = {'grant': 'synthetic-grant', 'actor': ACTOR, 'operation': 'submit', 'targets': ['delivery'],
        'payload': {'count': 1, 'synthetic': True}, 'outputs': 1,
        'cost': {'currency': 'USD', 'amount': '0', 'basis': 'Synthetic local test; no service call.'},
        'stop_assessments': [], 'reason': 'Synthetic recorded authorization.'}
    return test.append('authorization', {'request': request})['sha256']


def claim_data(token):
    return {'authorizations': [token], 'journal': 'runs/synthetic-journal'}


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
