"""Pure lifecycle replay and SQLite ownership under concurrent callers.

All records in this module are neutral synthetic fixtures. No pack discovery,
publication construction or external service is needed for these contracts.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import execution_contract as c
import execution_lifecycle as lifecycle
import production_store as store
from production_diagnostics import ProductionError


PREPARED = {'task': {'task_id': 'synthetic-task', 'criteria': []}, 'input_sha256': 'a' * 64}
RUN = 'synthetic-run'
REQUEST = 'b' * 64
EVIDENCE = [{'sha256': 'c' * 64}]


def append_fixture(rows: list[dict], event: str, data: dict) -> dict:
    row = {'sequence': len(rows) + 1, 'previous': rows[-1]['sha256'] if rows else None,
           'input_sha256': PREPARED['input_sha256'], 'event': event, 'data': data,
           'created_at': '2026-01-01T00:00:00Z'}
    row['sha256'] = c.content_id(row)
    rows.append(row)
    return row


def execution_fixture(*, send: bool = True, result: bool = False) -> list[dict]:
    rows = []
    request = {'operation': 'submit', 'targets': ['service:synthetic'], 'outputs': 1,
               'grant': 'synthetic-grant', 'actor': 'Synthetic author',
               'payload': {'request_sha256': REQUEST, 'external_effects': [
                   {'operation': 'upload', 'count': 1}, {'operation': 'send', 'count': 1},
                   {'operation': 'delete', 'count': 1}]}}
    authorization = append_fixture(rows, 'authorization', {'request': request})
    append_fixture(rows, 'execution-created', {'execution_id': 'synthetic-execution',
        'authorization_sha256': authorization['sha256'], 'requested_outputs': 1,
        'grant': request['grant'], 'actor': request['actor'], 'task_id': PREPARED['task']['task_id'],
        'request_sha256': REQUEST})
    append_fixture(rows, 'execution-start', {'execution_id': 'synthetic-execution', 'effect': 'external-io', 'claim': 'd' * 64})
    append_fixture(rows, 'external-step', {'execution_id': 'synthetic-execution', 'step': 'upload:0',
        'operation': 'upload', 'claim': 'd' * 64, 'request_sha256': REQUEST})
    append_fixture(rows, 'external-effect-result', {'execution_id': 'synthetic-execution', 'step': 'upload:0',
        'claim': 'd' * 64, 'usage': None, 'evidence': EVIDENCE})
    if send:
        append_fixture(rows, 'external-step', {'execution_id': 'synthetic-execution', 'step': 'send',
            'operation': 'send', 'claim': 'd' * 64, 'request_sha256': REQUEST})
    if result:
        append_fixture(rows, 'execution-result', {'execution_id': 'synthetic-execution', 'outputs': 1,
            'cost': None, 'final': True, 'evidence': EVIDENCE})
    return rows


def replay(rows):
    return lifecycle.completion_tail(rows, PREPARED, RUN, read_object=lambda digest: b'{}')


class ReplayTests(unittest.TestCase):
    def test_owned_history_keeps_read_only_indexes_without_replaying(self):
        source = execution_fixture(result=True)
        state = replay(source).seal()
        self.assertIs(state.rows.lifecycle, state)
        self.assertIs(state.find('authorization'), state.rows[0])
        self.assertIs(state.executions['synthetic-execution']['steps'][0], state.rows[3]['data'])
        with patch.object(lifecycle.ReplayState, '__init__', side_effect=AssertionError('history is already indexed')):
            self.assertIs(lifecycle.derive(state.rows, state.prepared, RUN), state.executions)
        source[0]['data']['request']['actor'] = 'Mutated source'
        self.assertEqual(state.find('authorization')['data']['request']['actor'], 'Synthetic author')
        with self.assertRaises(TypeError):
            state.executions['synthetic-execution']['steps'].append({})
        with self.assertRaises(TypeError):
            state.rows[0]['data']['request']['actor'] = 'Mutated view'
        with self.assertRaises(TypeError):
            state.advance(source[-1])

    def test_replay_retains_execution_and_chain_head(self):
        rows = execution_fixture(result=True)
        state = replay(rows)
        execution = state.executions['synthetic-execution']
        self.assertEqual((execution['status'], execution['submissions'], execution['captured_outputs']), ('complete', 1, 1))
        self.assertEqual(state.tail, rows[-1]['sha256'])
        self.assertEqual(state.find('authorization'), rows[0])
        self.assertIs(lifecycle.derive(state, PREPARED, RUN), state.executions)
        self.assertEqual(lifecycle.derive(rows, PREPARED, RUN), state.executions)

    def test_append_and_replay_refuse_the_same_execution_failures(self):
        rows = execution_fixture(result=True)
        cases = [
            ('execution-start', {'execution_id': 'synthetic-execution', 'effect': 'external-io'}),
            ('external-step', {'execution_id': 'synthetic-execution', 'step': 'send-again',
                'operation': 'send', 'request_sha256': REQUEST}),
            ('external-effect-result', {'execution_id': 'synthetic-execution', 'step': 'upload:0',
                'claim': 'd' * 64, 'usage': None, 'evidence': EVIDENCE}),
            ('execution-result', {'execution_id': 'synthetic-execution', 'outputs': 0,
                'cost': None, 'final': True, 'evidence': EVIDENCE}),
            ('external-step', {'execution_id': 'synthetic-execution', 'step': 'delete:0',
                'operation': 'delete', 'request_sha256': REQUEST, 'upload_index': 0,
                'upload_receipt_sha256': 'f' * 64}),
        ]
        for event, data in cases:
            with self.subTest(event=event, data=data):
                state = replay(rows)
                original = copy.deepcopy(state.executions)
                with self.assertRaisesRegex(ProductionError, 'EXECUTION_RECORD_CORRUPT'):
                    lifecycle.validate_transition(state, PREPARED, RUN, event, data, read_object=lambda digest: b'{}')
                self.assertEqual(state.executions, original)
                self.assertEqual(state.rows, rows)
                corrupt = list(rows)
                append_fixture(corrupt, event, data)
                with self.assertRaisesRegex(ProductionError, 'EXECUTION_RECORD_CORRUPT'):
                    replay(corrupt)

    def test_closed_run_retains_owned_cleanup_and_rejects_new_work(self):
        rows = execution_fixture(result=True)
        append_fixture(rows, 'completion', {'synthetic': 'closed'})
        cleanup = {'execution_id': 'synthetic-execution', 'step': 'delete:0', 'operation': 'delete',
                   'claim': 'd' * 64, 'request_sha256': REQUEST, 'upload_index': 0,
                   'upload_receipt_sha256': EVIDENCE[0]['sha256']}
        state = replay(rows)
        lifecycle.validate_transition(state, PREPARED, RUN, 'external-step', cleanup, read_object=lambda digest: b'{}')
        append_fixture(rows, 'external-step', cleanup)
        self.assertEqual(replay(rows).executions['synthetic-execution']['steps'][-1]['step'], 'delete:0')
        with self.assertRaisesRegex(ValueError, 'run is complete'):
            lifecycle.validate_transition(state, PREPARED, RUN, 'review', {}, read_object=lambda digest: b'{}')

    def test_abandonment_retains_response_capture_without_reopening_review(self):
        rows = execution_fixture()
        append_fixture(rows, 'abandoned', {'reason': 'Synthetic closure'})
        append_fixture(rows, 'candidate', {'files': []})
        append_fixture(rows, 'execution-result', {'execution_id': 'synthetic-execution', 'outputs': 1,
                                                'cost': None, 'final': True, 'evidence': EVIDENCE})
        state = replay(rows)
        self.assertEqual(state.executions['synthetic-execution']['captured_outputs'], 1)
        with self.assertRaisesRegex(ProductionError, 'TASK_ABANDONED'):
            lifecycle.validate_transition(state, PREPARED, RUN, 'review', {}, read_object=lambda digest: b'{}')

    def test_adoption_uses_current_review_and_disposition_from_indices(self):
        rows = []
        candidate = append_fixture(rows, 'candidate', {'files': [{'sha256': 'e' * 64}]})
        review = append_fixture(rows, 'review', {'candidate': candidate['sha256'],
                                               'review': {'checks': [], 'unresolved': []}})
        selection = {'input_sha256': PREPARED['input_sha256'], 'candidate': candidate['sha256'],
                     'review': review['sha256'], 'selector': 'Synthetic author', 'reason': 'Synthetic choice',
                     'scope': 'delivery-only', 'adoption': None, 'slot': None, 'owner_acceptance': None}
        authorization = append_fixture(rows, 'authorization', {'request': {'operation': 'select', 'targets': ['delivery'],
            'payload': dict(selection), 'actor': 'Synthetic author'}})
        selection['authorization'] = authorization['sha256']
        selected = append_fixture(rows, 'selection', {'selection': selection})
        append_fixture(rows, 'completion', {'synthetic': 'closed'})
        request = {'operation': 'adopt', 'targets': ['canon:sheet'], 'payload': {
            'candidate': candidate['sha256'], 'review': review['sha256'], 'character': 'synthetic-character',
            'iteration': 'synthetic-iteration', 'approval_sha256': 'f' * 64, 'registration_sha256': None, 'pack_dir': None}}
        state = replay(rows)
        lifecycle.require_operation(state, PREPARED, RUN, **request)
        disposition = {'disposition': {'input_sha256': PREPARED['input_sha256'],
            'candidate': candidate['sha256'], 'disposition': 'not_selected',
            'actor': 'Synthetic author', 'reason': 'Retire the synthetic candidate.', 'review': review['sha256']},
            'files': [], 'previous_decision': selected['sha256']}
        # Open-run review and disposition changes both affect later adoption.
        for event, data, message in [
            ('review', {'candidate': candidate['sha256'], 'review': {'checks': [], 'unresolved': []}}, 'SELECTION_REVIEW_CHANGED'),
            ('disposition', disposition, 'SELECTION_WITHDRAWN'),
        ]:
            with self.subTest(event=event):
                changed = list(rows[:-1])
                append_fixture(changed, event, data)
                with self.assertRaisesRegex(ProductionError, message):
                    lifecycle.require_operation(replay(changed), PREPARED, RUN, **request)
        # Completion retains its original delivery, while a later nonselection
        # withdraws the candidate from a new adoption of those retained bytes.
        retired = list(rows)
        append_fixture(retired, 'disposition', disposition)
        retired_state = replay(retired)
        self.assertEqual(retired_state.closed, 'completion')
        with self.assertRaisesRegex(ProductionError, 'SELECTION_WITHDRAWN') as refusal:
            lifecycle.require_operation(retired_state, PREPARED, RUN, **request)
        self.assertIn('run is closed', refusal.exception.diagnostic.required_action)

    def test_completed_nonselection_does_not_reopen_candidate_or_production_work(self):
        rows = []
        candidate = append_fixture(rows, 'candidate', {'files': [{'sha256': 'e' * 64}]})
        done = append_fixture(rows, 'completion', {'synthetic': 'closed'})
        data = {'disposition': {'input_sha256': PREPARED['input_sha256'], 'candidate': candidate['sha256'],
                'disposition': 'not_selected', 'actor': 'Synthetic author', 'reason': 'Another output is preferred.',
                'review': None}, 'files': [], 'previous_decision': None}
        state = replay(rows)
        lifecycle.validate_transition(state, PREPARED, RUN, 'disposition', data, read_object=lambda digest: b'{}')
        retired = append_fixture(rows, 'disposition', data)
        state = replay(rows)
        self.assertEqual(state.closed, 'completion')
        self.assertEqual(state.find('completion'), done)
        pending = copy.deepcopy(data)
        pending['disposition']['disposition'] = 'pending'
        pending['previous_decision'] = retired['sha256']
        blocked = [('disposition', pending), ('candidate', {}), ('review', {}), ('selection', {}),
                   ('authorization', {'request': {'operation': 'submit', 'targets': [], 'payload': {}}})]
        for event, value in blocked:
            with self.subTest(event=event):
                with self.assertRaisesRegex(ValueError, 'run is complete'):
                    lifecycle.validate_transition(state, PREPARED, RUN, event, value, read_object=lambda digest: b'{}')
                invalid = list(rows)
                append_fixture(invalid, event, value)
                with self.assertRaisesRegex(ProductionError, 'EVENT_CHAIN_CORRUPT'):
                    replay(invalid)

    def test_disposition_replay_checks_candidate_input_review_and_previous_decision(self):
        rows = []
        candidate = append_fixture(rows, 'candidate', {'files': [{'sha256': 'e' * 64}]})
        earlier = append_fixture(rows, 'review', {'candidate': candidate['sha256']})
        latest = append_fixture(rows, 'review', {'candidate': candidate['sha256']})
        append_fixture(rows, 'completion', {'synthetic': 'closed'})
        data = {'disposition': {'input_sha256': PREPARED['input_sha256'], 'candidate': candidate['sha256'],
                'disposition': 'not_selected', 'actor': 'Synthetic author', 'reason': 'Retire a synthetic output.',
                'review': latest['sha256']}, 'files': [], 'previous_decision': None}
        state = replay(rows)
        lifecycle.validate_transition(state, PREPARED, RUN, 'disposition', data, read_object=lambda digest: b'{}')
        for field, value in [('input_sha256', 'd' * 64), ('candidate', 'f' * 64),
                             ('review', earlier['sha256']), ('actor', ' '), ('disposition', 'selected'),
                             ('previous_decision', 'c' * 64)]:
            with self.subTest(field=field):
                changed = copy.deepcopy(data)
                if field == 'previous_decision':
                    changed[field] = value
                else:
                    changed['disposition'][field] = value
                with self.assertRaises(ValueError):
                    lifecycle.validate_transition(state, PREPARED, RUN, 'disposition', changed, read_object=lambda digest: b'{}')
                invalid = list(rows)
                append_fixture(invalid, 'disposition', changed)
                with self.assertRaisesRegex(ProductionError, 'EVENT_CHAIN_CORRUPT'):
                    replay(invalid)

    def test_abandonment_keeps_candidate_disposition_closed(self):
        rows = []
        candidate = append_fixture(rows, 'candidate', {'files': [{'sha256': 'e' * 64}]})
        append_fixture(rows, 'abandoned', {'reason': 'Synthetic closure'})
        data = {'disposition': {'input_sha256': PREPARED['input_sha256'], 'candidate': candidate['sha256'],
                'disposition': 'not_selected', 'actor': 'Synthetic author', 'reason': 'Attempt after abandonment.',
                'review': None}, 'files': [], 'previous_decision': None}
        with self.assertRaisesRegex(ProductionError, 'TASK_ABANDONED'):
            lifecycle.validate_transition(replay(rows), PREPARED, RUN, 'disposition', data, read_object=lambda digest: b'{}')

    def test_replay_work_grows_linearly_with_history(self):
        class CountedRecord(dict):
            reads = 0
            def __getitem__(self, key):
                if key == 'event':
                    type(self).reads += 1
                return super().__getitem__(key)

        def reads_for(count):
            rows = []
            for number in range(count):
                row = append_fixture(rows, 'candidate', {'synthetic': number})
                rows[-1] = CountedRecord(row)
            CountedRecord.reads = 0
            state = replay(rows)
            self.assertEqual(len(state.rows), count)
            return CountedRecord.reads

        small, large = reads_for(250), reads_for(1000)
        self.assertLessEqual(large, 4 * small + 100)
        self.assertLess(large, 20 * 1000)


class StoredHistoryTests(unittest.TestCase):
    def test_first_operation_rollback_keeps_an_empty_readable_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, 'Synthetic interruption'):
                with store.transaction(root) as connection:
                    store.append(root, RUN, None, 'synthetic-event', {'number': 1})
                    connection.execute('INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (RUN, 'synthetic-task', 'synthetic-production', 'a' * 64, 'b' * 64,
                         'c' * 64, 'production/runs/' + RUN, '2026-01-01T00:00:00Z'))
                    raise RuntimeError('Synthetic interruption')
            self.assertEqual(store.read_history(root, RUN).rows, [])
            self.assertEqual(store.runs(root), [])
            self.assertIsNone(store.authority(root, 'synthetic-task', required=False))
            event = store.append(root, RUN, None, 'synthetic-event', {'number': 2})
            self.assertEqual((event['sequence'], event['previous']), (1, None))

    def test_uninitialized_database_is_an_empty_read_without_creating_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = store.database(root)
            path.parent.mkdir(parents=True)
            sqlite3.connect(path).close()
            original = path.read_bytes()
            self.assertEqual(store.read_history(root, RUN).rows, [])
            self.assertEqual(store.runs(root), [])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(store.append(root, RUN, None, 'synthetic-event', {})['sequence'], 1)

    def test_incomplete_or_removed_schema_is_not_reinitialized(self):
        for removed in (False, True):
            with self.subTest(removed=removed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = store.database(root)
                path.parent.mkdir(parents=True)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute('CREATE TABLE events (marker TEXT)')
                    if removed:
                        connection.execute('DROP TABLE events')
                with self.assertRaisesRegex(sqlite3.DatabaseError, 'schema is incomplete'):
                    store.read_history(root, RUN)
                with self.assertRaisesRegex(sqlite3.DatabaseError, 'schema is incomplete'):
                    with store.transaction(root):
                        self.fail('A malformed store must not begin an operation')
                with closing(sqlite3.connect(path)) as connection, connection:
                    tables = list(connection.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
                self.assertEqual(tables, [] if removed else [('events',)])

    def test_one_hash_pass_and_independent_export_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for number in range(5):
                store.append(root, RUN, None, 'synthetic-event', {'number': number})
            with patch.object(c, 'content_id', wraps=c.content_id) as digest:
                history = store.read_history(root, RUN)
            self.assertIsInstance(history, store.VerifiedHistory)
            self.assertEqual((history.scope, len(history.rows), digest.call_count), (RUN, 5, 5))
            self.assertEqual(history.tail, history.rows[-1]['sha256'])
            exported = copy.deepcopy(history.rows)
            exported[0]['data']['number'] = 42
            with self.assertRaisesRegex(ProductionError, 'EVENT_CHAIN_CORRUPT'):
                store.validate_event_chain(exported, RUN)
            self.assertEqual(store.read_history(root, RUN).rows, history.rows)

    def test_store_rejects_rehashed_shape_and_column_corruption(self):
        changes = [lambda row: row.update(sequence=True), lambda row: row.update(extra='undeclared'),
                   lambda row: row.update(data=[]), lambda row: row.update(previous='e' * 64)]
        for number, change in enumerate(changes):
            with self.subTest(case=number), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                row = store.append(root, RUN, None, 'synthetic-event', {'number': number})
                change(row)
                row['sha256'] = c.content_id({key: value for key, value in row.items() if key != 'sha256'})
                with store.transaction(root) as connection:
                    connection.execute('UPDATE events SET body=?, sha256=? WHERE scope=?', (c.encoded(row), row['sha256'], RUN))
                with self.assertRaisesRegex(ProductionError, 'EVENT_CHAIN_CORRUPT'):
                    store.read_history(root, RUN)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store.append(root, RUN, None, 'synthetic-event', {})
            with store.transaction(root) as connection:
                connection.execute('UPDATE events SET event=? WHERE scope=?', ('changed-column', RUN))
            with self.assertRaisesRegex(ProductionError, 'EVENT_CHAIN_CORRUPT'):
                store.read_history(root, RUN)

    def test_concurrent_empty_database_claim_has_one_owner(self):
        connect = sqlite3.connect
        for attempt in range(4):
            with self.subTest(attempt=attempt), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                ready = threading.Barrier(6)
                opened = threading.Barrier(6)
                class OpeningConnection(sqlite3.Connection):
                    def execute(self, sql, parameters=()):
                        if sql == 'PRAGMA journal_mode=WAL' and not getattr(self, 'configured', False):
                            self.configured = True
                            opened.wait(timeout=10)
                        return super().execute(sql, parameters)

                def synchronized_connection(*args, **kwargs):
                    return connect(*args, **kwargs, factory=OpeningConnection)

                def claim(number):
                    ready.wait(timeout=10)
                    try:
                        store.append(root, RUN, None, 'dispatch-claim', {'owner': number})
                        return 'committed'
                    except ProductionError as exc:
                        return exc.diagnostic.code
                with patch.object(sqlite3, 'connect', side_effect=synchronized_connection), \
                     ThreadPoolExecutor(max_workers=6) as workers:
                    results = list(workers.map(claim, range(6)))
                self.assertEqual(results.count('committed'), 1)
                self.assertEqual(results.count('DISPATCH_ALREADY_CLAIMED'), 5)
                self.assertEqual(len(store.read_history(root, RUN).rows), 1)

    def test_concurrent_expected_tail_has_one_successor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            head = store.append(root, RUN, None, 'synthetic-event', {'revision': 0})
            ready = threading.Barrier(4)
            def append(number):
                ready.wait(timeout=10)
                try:
                    store.append(root, RUN, None, 'synthetic-event', {'revision': number},
                                 expected_previous=head['sha256'], check_previous=True)
                    return 'committed'
                except ProductionError as exc:
                    return exc.diagnostic.code
            with ThreadPoolExecutor(max_workers=4) as workers:
                results = list(workers.map(append, range(1, 5)))
            self.assertEqual(results.count('committed'), 1)
            self.assertEqual(results.count('EVENT_CONFLICT'), 3)
            self.assertEqual(len(store.read_history(root, RUN).rows), 2)

    def test_authority_state_and_history_share_one_reader_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = 'synthetic-task'
            scope = 'authority:' + task

            def commit_authority(revision):
                document = {'synthetic_revision': revision}
                with store.transaction(root) as connection:
                    event = store.append(root, scope, None, 'authority-updated', {'authority': document, 'evidence': []})
                    connection.execute('INSERT INTO authority_states VALUES (?, ?, ?) '
                        'ON CONFLICT(task_id) DO UPDATE SET content_sha256=excluded.content_sha256, event_sha256=excluded.event_sha256',
                        (task, c.content_id(document), event['sha256']))

            commit_authority(1)
            selected, committed = threading.Event(), threading.Event()
            connect = sqlite3.connect

            class PausingConnection(sqlite3.Connection):
                def execute(self, sql, parameters=()):
                    cursor = super().execute(sql, parameters)
                    if sql.startswith('SELECT * FROM authority_states'):
                        selected.set()
                        if not committed.wait(timeout=10):
                            raise AssertionError('Concurrent writer could not commit during a reader snapshot')
                    return cursor

            def pausing_connection(*args, **kwargs):
                return connect(*args, **kwargs, factory=PausingConnection)

            def update():
                if not selected.wait(timeout=10):
                    raise AssertionError('Authority reader did not reach its state query')
                try:
                    commit_authority(2)
                finally:
                    committed.set()

            with patch.object(sqlite3, 'connect', side_effect=pausing_connection), ThreadPoolExecutor(max_workers=1) as worker:
                writer = worker.submit(update)
                self.assertEqual(store.authority(root, task), {'synthetic_revision': 1})
                writer.result(timeout=10)
            self.assertEqual(store.authority(root, task), {'synthetic_revision': 2})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
