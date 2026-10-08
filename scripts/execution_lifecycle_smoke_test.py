#!/usr/bin/env python3
"""Execution ownership, irreversible boundaries and result evidence on synthetic inputs."""
from __future__ import annotations
import copy
import multiprocessing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import execution_contract as c
import execution_lifecycle as life
import production_fixtures as fixture
import production_store as store
import production_workflow as w
import work_ledger


def setup(root: Path):
    task = work_ledger.begin(root, 'Synthetic execution test', ['deliver'])
    (root / 'delivery.txt').write_text('Synthetic declared output.', encoding='utf-8')
    spec = {'task_id': task['task_id'], 'route': 'development', 'features': [], 'sources': [],
            'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition', 'translation_notes': 'Synthetic rendition.'},
            'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect actual bytes.'}], 'world_views': []}
    fixture.task(root, spec)
    (root / 'task.json').write_bytes(c.encoded(spec))
    run = w.prepare(root, 'task.json')['run']
    token = fixture.grant(root, run, {'operation': 'submit', 'targets': ['delivery'], 'payload': {'count': 1, 'test': 'synthetic'}})
    return run, token, fixture.ACTOR


def claim_in_process(root, run, token, barrier, results):
    try:
        barrier.wait(timeout=120)
        results.put(life.claim_execution(Path(root), run, token)['execution_id'])
    except BaseException as exc:
        results.put(type(exc).__name__ + ': ' + str(exc))


class ExecutionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run, self.token, self.actor = setup(self.root)

    def claim(self):
        state = life.claim_execution(self.root, self.run, self.token)
        directory, prepared, _, rows = w.load_run(self.root, self.run)
        row = w.append_record(directory, prepared, rows, 'external-claim',
            {'authorizations': [self.token], 'execution_id': state['execution_id']})
        return row['sha256']

    def start(self, *, step='send', operation='send'):
        claim = self.claim()
        life.begin_step(self.root, self.run, self.token, claim=claim, step=step, operation=operation)
        return claim

    def evidence(self):
        (self.root / 'receipt.json').write_bytes(c.encoded({'synthetic': True, 'received': True}))
        directory = w.run_dir(self.root, self.run)
        return [w.file_record(self.root, directory, 'receipt.json')]

    def test_authorization_alone_does_not_start_an_execution(self):
        self.assertEqual(life.all_states(self.root), [])
        self.assertEqual(life.summary(self.root)['submissions'], 0)

    def test_one_idempotent_owner_per_run(self):
        a = life.claim_execution(self.root, self.run, self.token)
        b = life.claim_execution(self.root, self.run, self.token)
        self.assertEqual(a, b)
        self.assertNotEqual(a['execution_id'], self.token)
        self.assertEqual((a['status'], a['requested_outputs']), ('claimed', 1))
        self.assertEqual(sum(r['event'] == 'execution-created' for r in store.event_rows(self.root, self.run)), 1)

    def test_same_claim_across_threads(self):
        barrier = threading.Barrier(2)
        results = []
        def worker():
            barrier.wait(timeout=30)
            results.append(life.claim_execution(self.root, self.run, self.token)['execution_id'])
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=120)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(len(life.all_states(self.root)), 1)

    def test_same_claim_across_processes(self):
        ctx = multiprocessing.get_context('spawn')
        barrier, results = ctx.Barrier(2), ctx.Queue()
        workers = [ctx.Process(target=claim_in_process, args=(str(self.root), self.run, self.token, barrier, results)) for _ in range(2)]
        try:
            for worker in workers: worker.start()
            values = [results.get(timeout=120) for _ in workers]
            for worker in workers:
                worker.join(timeout=120)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual(len(set(values)), 1)
            self.assertEqual(values[0], life.all_states(self.root)[0]['execution_id'])
        finally:
            for worker in workers:
                if worker.is_alive(): worker.terminate(); worker.join(timeout=10)
            results.close()

    def test_different_authorization_cannot_claim_same_run(self):
        life.claim_execution(self.root, self.run, self.token)
        other = fixture.grant(self.root, self.run, {'operation': 'submit', 'targets': ['delivery'], 'payload': {'count': 1, 'test': 'other'}})
        with self.assertRaisesRegex(ValueError, 'DISPATCH_ALREADY_CLAIMED'):
            life.claim_execution(self.root, self.run, other)

    def test_claim_rechecks_source_bytes(self):
        (self.root / 'delivery.txt').write_text('Changed source.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            life.claim_execution(self.root, self.run, self.token)
        self.assertEqual(life.all_states(self.root), [])

    def test_claim_rechecks_current_authority(self):
        document = copy.deepcopy(store.authority(self.root, w.load_run(self.root, self.run)[1]['task']['task_id']))
        document['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        (self.root / 'revoked.json').write_bytes(c.encoded(document))
        prior = store.authority_record(self.root, document['task_id'])
        store.import_authority(self.root, 'revoked.json', expected=prior['sha256'])
        with self.assertRaisesRegex(ValueError, 'GRANT_REVOKED'):
            life.claim_execution(self.root, self.run, self.token)

    def test_same_external_step_cannot_start_twice(self):
        claim = self.start()
        with self.assertRaises(ValueError):
            life.begin_step(self.root, self.run, self.token, claim=claim, step='send', operation='send')
        self.assertEqual(life.summary(self.root)['submissions'], 1)

    def test_new_step_rechecks_authorized_sources(self):
        claim = self.start(step='upload:0', operation='upload')
        (self.root / 'delivery.txt').write_text('Changed after upload.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
            life.begin_step(self.root, self.run, self.token, claim=claim, step='send', operation='send')
        self.assertEqual(life.summary(self.root)['submissions'], 0)

    def test_unknown_step_stays_durable(self):
        self.start()
        self.assertEqual(life.all_states(self.root)[0]['status'], 'started')
        self.assertFalse(life.summary(self.root)['usage_complete'])

    def test_final_result_does_not_require_reported_price(self):
        claim = self.start()
        evidence = self.evidence()
        life.record_effect(self.root, self.run, self.token, claim=claim, step='send', usage=None, evidence=evidence)
        life.record_result(self.root, self.run, self.token, outputs=1, cost=None, final=True, evidence=evidence)
        result = life.summary(self.root)
        self.assertEqual((result['submissions'], result['captured_outputs']), (1, 1))
        self.assertEqual(result['executions'][0]['status'], 'complete')
        self.assertFalse(result['usage_complete'])

    def test_partial_capture_can_grow_and_repeated_receipt_is_idempotent(self):
        self.start(); evidence = self.evidence()
        life.record_result(self.root, self.run, self.token, outputs=1, cost=None, final=False, evidence=evidence)
        self.assertEqual(life.all_states(self.root)[0]['status'], 'captured')
        a = life.record_result(self.root, self.run, self.token, outputs=2, cost=None, final=True, evidence=evidence)
        b = life.record_result(self.root, self.run, self.token, outputs=2, cost=None, final=True, evidence=evidence)
        self.assertEqual(a, b)
        self.assertEqual(life.summary(self.root)['captured_outputs'], 2)

    def test_result_cannot_erase_prior_images(self):
        self.start(); evidence = self.evidence()
        life.record_result(self.root, self.run, self.token, outputs=1, cost=None, final=False, evidence=evidence)
        with self.assertRaises(ValueError):
            life.record_result(self.root, self.run, self.token, outputs=0, cost=None, final=True, evidence=evidence)

    def test_usage_records_are_exact_decimals_per_currency(self):
        self.assertEqual(life._add_money([{'currency':'USD','amount':'0.1'}, {'currency':'USD','amount':'0.2'}, {'currency':'JPY','amount':'3'}]), {'USD':'0.3','JPY':'3'})
        for amount in ('-1', 'NaN', 'Infinity', '1e3'):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                life.validate_cost({'currency':'USD','amount':amount})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
