"""Transactional production records and immutable evidence.

SQLite is the sole editable record of runs, grants and execution events. JSON
files inside published run directories are immutable content addressed by that
record. JSONL/HTML views are projections, never another editable ledger.
"""
from __future__ import annotations
import read_context
import contextlib
import contextvars
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from typing import Any, Iterator

import execution_contract as c
from production_diagnostics import ProductionError
from private_state import PrivateStateError, assert_public_path
from owned_json import freeze, mutable, json_value

_CONNECTIONS: contextvars.ContextVar[dict[str, sqlite3.Connection]] = contextvars.ContextVar('production_connections', default={})
_READERS: contextvars.ContextVar[dict[str, sqlite3.Connection]] = contextvars.ContextVar('production_readers', default={})
_DDL = '''
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, production_id TEXT NOT NULL, input_sha256 TEXT NOT NULL,
 envelope_sha256 TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, directory TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 scope TEXT NOT NULL, sequence INTEGER NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 previous TEXT, input_sha256 TEXT, event TEXT NOT NULL, body BLOB NOT NULL,
 PRIMARY KEY(scope, sequence)
);
CREATE UNIQUE INDEX IF NOT EXISTS single_dispatch ON events(scope, event)
 WHERE event IN ('dispatch-claim','external-claim','completion');
CREATE TABLE IF NOT EXISTS authority_states (
 task_id TEXT PRIMARY KEY, content_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL
);
'''
_REQUIRED_SCHEMA = {('table', 'runs'), ('table', 'events'), ('table', 'authority_states'),
                    ('index', 'single_dispatch')}


def database(root: Path) -> Path:
    return c.local(root, 'production/records.sqlite3', exists=False)


def _enable_wal(connection: sqlite3.Connection) -> None:
    """Let concurrent first writers finish SQLite's journal-mode transition.

    SQLite may return BUSY immediately while another connection changes an
    empty database's journal mode. Retry that configuration step only, before
    any application transaction or event exists on this connection.
    """
    deadline = time.monotonic() + 30
    while True:
        try:
            connection.execute('PRAGMA journal_mode=WAL').fetchone()
            return
        except sqlite3.OperationalError as exc:
            code = getattr(exc, 'sqlite_errorcode', 0) & 0xff
            remaining = deadline - time.monotonic()
            if code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))


def _schema_objects(connection: sqlite3.Connection) -> set[tuple[str, str]]:
    return {(row['type'], row['name']) for row in connection.execute(
        "SELECT type, name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'")}


def _require_schema(objects: set[tuple[str, str]]) -> None:
    if not _REQUIRED_SCHEMA <= objects:
        missing = ', '.join(name for kind, name in sorted(_REQUIRED_SCHEMA - objects))
        raise sqlite3.DatabaseError('Production record database schema is incomplete: ' + missing)


def _begin_transaction(connection: sqlite3.Connection) -> None:
    """Publish a new schema once, independently of the first operation's fate."""
    connection.execute('BEGIN IMMEDIATE')
    objects = _schema_objects(connection)
    if objects or connection.execute('PRAGMA schema_version').fetchone()[0] != 0:
        _require_schema(objects)
        return
    # The writer transaction excludes another initializer until the complete
    # schema is committed. User rollback must never remove these empty tables.
    for statement in _DDL.split(';'):
        if statement.strip():
            connection.execute(statement)
    connection.commit()
    connection.execute('BEGIN IMMEDIATE')


@dataclass(frozen=True, slots=True)
class VerifiedHistory:
    """Decoded events whose shape, chain and stored columns were checked together.

    The read boundary owns these rows. Consumers retain this value internally
    and copy rows when returning editable exports to a caller.
    """
    scope: str
    rows: list[dict]
    connection: sqlite3.Connection | None = field(default=None, repr=False, compare=False)
    owner: object | None = field(default=None, repr=False, compare=False)

    @property
    def tail(self) -> str | None:
        return self.rows[-1]['sha256'] if self.rows else None


@dataclass(frozen=True, slots=True)
class EventAppend:
    """Canonical event bytes proposed against one acquired writer history."""

    history: VerifiedHistory
    row: dict
    raw: bytes | None


@dataclass
class _StoreSession:
    """One operation's connection and observed external-commit boundary.

    SQLite's data_version is compared only on the same live connection. Its
    own commits do not advance that value; commits by any other connection do.
    Keeping the handle does not keep a transaction or a write lock open.
    """

    root: Path
    connection: sqlite3.Connection | None = None
    writable: bool = False
    identity: tuple[int, int] | None = None
    version: int | None = None

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _path(self, *, write: bool) -> Path | None:
        path = database(self.root)
        if not path.is_file():
            if self.connection is not None:
                self.close()
                self.identity = self.version = None
                read_context.invalidate_runs(self.root, source_boundary=True)
            if not write:
                self.identity = self.version = None
                return None
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            if self.identity is not None and self.identity != identity:
                self.close()
                self.version = None
                read_context.invalidate_runs(self.root, source_boundary=True)
            self.identity = identity
        return path

    def observe(self) -> None:
        version = self.connection.execute('PRAGMA data_version').fetchone()[0]
        if self.version is not None and version != self.version:
            read_context.invalidate_runs(self.root)
        self.version = version

    def read(self) -> sqlite3.Connection | None:
        path = self._path(write=False)
        if path is None:
            return None
        if self.connection is None:
            self.connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                              timeout=30, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.writable = False
            self.version = None
        return self.connection

    def begin(self) -> sqlite3.Connection:
        path = self._path(write=True)
        previous = self.connection
        if previous is not None and self.writable:
            try:
                _begin_transaction(previous)
                self.observe()
            except BaseException:
                previous.rollback()
                raise
            return previous
        connection = sqlite3.connect(path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            _enable_wal(connection)
            connection.execute('PRAGMA synchronous=FULL')
            _begin_transaction(connection)
            # The writer lock excludes another commit while a read-only
            # observation is transferred to this writable connection.
            if previous is not None:
                self.observe()
            self.connection = connection
            self.writable = True
            self.version = connection.execute('PRAGMA data_version').fetchone()[0]
            info = path.stat()
            self.identity = (info.st_dev, info.st_ino)
        except BaseException:
            connection.close()
            raise
        if previous is not None:
            previous.close()
        return connection


def _session(root: Path) -> _StoreSession:
    return read_context.resource(('production-store', str(root.resolve())),
                                 lambda: _StoreSession(root.resolve()))


def refresh_observation(root: Path) -> None:
    """Observe external commits without rereading unchanged owned documents."""
    with reader(root):
        pass


@contextlib.contextmanager
def transaction(root: Path) -> Iterator[sqlite3.Connection]:
    identity = str(root.resolve())
    independent = identity in _READERS.get() and identity not in _CONNECTIONS.get()
    with read_context.public_call(isolated=independent):
        with _transaction(root) as connection:
            yield connection


@contextlib.contextmanager
def _transaction(root: Path) -> Iterator[sqlite3.Connection]:
    root = root.resolve()
    key = str(root)
    existing = _CONNECTIONS.get().get(key)
    if existing is not None:
        savepoint = 's' + uuid.uuid4().hex
        before = read_context.transaction_checkpoint(existing)
        existing.execute('SAVEPOINT ' + savepoint)
        try:
            yield existing
            existing.execute('RELEASE ' + savepoint)
        except BaseException:
            existing.execute('ROLLBACK TO ' + savepoint)
            existing.execute('RELEASE ' + savepoint)
            read_context.restore_transaction(existing, before)
            read_context.invalidate_studio(root)
            raise
        return
    connection = _session(root).begin()
    token = None
    try:
        read_context.begin_transaction(connection)
        before = dict(read_context._transaction_scope(connection))
        token = _CONNECTIONS.set({**_CONNECTIONS.get(), key: connection})
        yield connection
        connection.commit()
        read_context.commit_transaction(connection, before)
        from operation_context import current
        if current():
            current().event('formal_transaction_committed', database=str(database(root)), phase='storage')
    except BaseException:
        connection.rollback()
        read_context.invalidate_studio(root)
        from operation_context import current
        if current():
            current().event('formal_transaction_rolled_back', database=str(database(root)), phase='storage')
        raise
    finally:
        if token is not None:
            _CONNECTIONS.reset(token)
        read_context.release_transaction(connection)


@contextlib.contextmanager
def reader(root: Path) -> Iterator[sqlite3.Connection | None]:
    with read_context.public_call():
        with _reader(root) as connection:
            yield connection


@contextlib.contextmanager
def _reader(root: Path) -> Iterator[sqlite3.Connection | None]:
    identity = str(root.resolve())
    connection = _CONNECTIONS.get().get(identity) or _READERS.get().get(identity)
    if connection is not None:
        yield connection; return
    session = _session(root)
    connection = session.read()
    if connection is None:
        yield None; return
    token = None
    try:
        # All reads made through this handle see one WAL snapshot. This does
        # not serialize readers or prevent another connection from writing.
        connection.execute('BEGIN')
        objects = _schema_objects(connection)
        if not objects and connection.execute('PRAGMA schema_version').fetchone()[0] == 0:
            # A first writer may have opened the file before publishing its
            # schema. Only a wholly empty schema represents an empty store.
            yield None
            return
        _require_schema(objects)
        session.observe()
        token = _READERS.set({**_READERS.get(), identity: connection})
        yield connection
    finally:
        if token is not None:
            _READERS.reset(token)
        connection.rollback()
        session.observe()


EXPORT_AGAIN = ('Take the event export again from the Studio that holds this run, with observe_model_schema.py '
                'attach-probe for a request observation; an edited export is refused.')


def validate_event_chain(rows: list[dict], scope: str) -> None:
    """Validate a read-only event export using the same chain as the store."""
    if not isinstance(rows, list):
        raise ProductionError('EVENT_CHAIN_CORRUPT', 'Event records must be a list.', phase='integrity', run=scope,
                              required_action=EXPORT_AGAIN)
    previous = None
    for sequence, row in enumerate(rows, 1):
        try:
            c.exact(row, {'sequence', 'previous', 'input_sha256', 'event', 'data', 'created_at', 'sha256'}, 'formal event')
            body = {key: value for key, value in row.items() if key != 'sha256'}
            valid = (type(row['sequence']) is int and row['sequence'] == sequence
                     and row['previous'] == previous and isinstance(row['data'], dict)
                     and c.content_id(body) == row['sha256'])
        except (ValueError, TypeError, KeyError) as exc:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'Event export is malformed.',
                                  phase='integrity', run=scope, event=sequence, required_action=EXPORT_AGAIN) from exc
        if not valid:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'Event export differs from its recorded chain.',
                                  phase='integrity', run=scope, event=sequence, expected=row.get('sha256'),
                                  required_action=EXPORT_AGAIN)
        previous = row['sha256']


@read_context.operation
def read_history(root: Path, scope: str) -> VerifiedHistory:
    """Read and verify stored rows once, retaining their verified chain boundary."""
    with reader(root) as connection:
        if connection is None:
            return VerifiedHistory(scope, freeze([]))
        owner = read_context.check_scope(root)
        key = ('verified-history', str(root.resolve()), scope)
        if owner is not None and key in owner:
            held = bind_history(root, owner[key])
            owner[key] = held
            return held
        entries = list(connection.execute('SELECT * FROM events WHERE scope=? ORDER BY sequence', (scope,)))
        writer = connection if _CONNECTIONS.get().get(str(root.resolve())) is connection else None
        held = _verified_history(scope, entries, connection=writer)
        if owner is not None:
            owner[key] = held
        return held


def bind_history(root: Path, history: VerifiedHistory) -> VerifiedHistory:
    """Bind acquired rows to this writer without replaying or decoding them."""
    connection = _CONNECTIONS.get().get(str(root.resolve()))
    owner = read_context.transaction_token(connection) if connection is not None else None
    return history if history.connection is connection and history.owner is owner else replace(
        history, connection=connection, owner=owner)


def _verified_history(scope: str, entries: list[sqlite3.Row], *,
                      connection: sqlite3.Connection | None = None) -> VerifiedHistory:
    """Decode rows captured from one SQLite snapshot and check their stored chain."""
    result = []
    previous = None
    for entry in entries:
        try:
            row = c.decode(bytes(entry['body']), owned=True)
            c.exact(row, {'sequence', 'previous', 'input_sha256', 'event', 'data', 'created_at', 'sha256'}, 'formal event')
            content = dict(row)
            digest = content.pop('sha256', None)
            consistent = (type(row['sequence']) is int and isinstance(row['data'], dict)
                and c.content_id(content) == digest and entry['sha256'] == digest
                and row['previous'] == previous == entry['previous']
                and row['sequence'] == len(result) + 1 == entry['sequence']
                and row['event'] == entry['event']
                and row['input_sha256'] == entry['input_sha256'])
        except (ValueError, TypeError, KeyError) as exc:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'Formal event content is unreadable or incomplete.',
                phase='integrity', run=scope, event=entry['sequence'], expected=entry['sha256'],
                required_action='Restore the exact committed event from verified evidence; do not recreate approval.') from exc
        if not consistent:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'Formal event chain differs from its committed contents.',
                phase='integrity', run=scope, event=entry['sequence'], expected=entry['sha256'],
                required_action='Restore the exact committed event from verified evidence; do not recreate approval.')
        previous = digest
        result.append(row)
    return VerifiedHistory(scope, freeze(result), connection,
                           read_context.transaction_token(connection) if connection is not None else None)


def event_rows(root: Path, scope: str) -> list[dict]:
    """Return an editable event export from a freshly verified storage read."""
    return mutable(read_history(root, scope).rows)


def owns_history(root: Path, history: VerifiedHistory) -> bool:
    """Whether this observation belongs to the currently open writer."""
    return (history.connection is not None
            and _CONNECTIONS.get().get(str(root.resolve())) is history.connection
            and read_context.transaction_token(history.connection) is history.owner)


def propose_append(history: VerifiedHistory, input_sha256: str | None,
                   event: str, data: dict, *, expected_previous: str | None = None,
                   check_previous: bool = False) -> EventAppend:
    """Construct one event from acquired rows, retaining its exact stored form."""
    data = json_value(data)
    for row in reversed(history.rows):
        if row['event'] == event and row['data'] == data:
            return EventAppend(history, row, None)
    previous = history.tail
    if check_previous and previous != expected_previous:
        raise ProductionError('EVENT_CONFLICT', 'Another operation committed first; reload the current state.',
            phase='storage', run=history.scope,
            required_action='Read the run again with status --run, then repeat this command if its step is still open.')
    row = {'sequence': len(history.rows) + 1, 'previous': previous, 'input_sha256': input_sha256,
           'event': event, 'data': data, 'created_at': c.now()}
    row['sha256'] = c.content_id(row)
    raw = c.encoded(row)
    return EventAppend(history, freeze(row), raw)


def commit_append(root: Path, proposal: EventAppend) -> VerifiedHistory:
    """Insert a checked event without acquiring its already verified prefix again.

    The owning writer and current SQL predecessor must still match. Callers
    publish a successor read state only after this insert succeeds.
    """
    history, row = proposal.history, proposal.row
    if not owns_history(root, history):
        raise ValueError('event history does not belong to the current writer')
    connection = history.connection
    tail = connection.execute('SELECT sequence, sha256 FROM events WHERE scope=? ORDER BY sequence DESC LIMIT 1',
                              (history.scope,)).fetchone()
    actual = (tail['sequence'], tail['sha256']) if tail is not None else (0, None)
    if actual != (len(history.rows), history.tail):
        raise ProductionError('EVENT_CONFLICT', 'Another operation changed the acquired event history.',
            phase='storage', run=history.scope,
            required_action='Read the run again with status --run, then repeat this command if its step is still open.')
    if proposal.raw is None:
        return history
    try:
        connection.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',
            (history.scope, row['sequence'], row['sha256'], row['previous'], row['input_sha256'], row['event'], proposal.raw))
    except sqlite3.IntegrityError as exc:
        raise ProductionError('DISPATCH_ALREADY_CLAIMED' if 'claim' in row['event'] else 'EVENT_CONFLICT',
            'The run already has this committed operation.', phase='storage', run=history.scope,
            required_action='Use resume for the same execution, variant for changed input, or repeat for an intentional additional run.') from exc
    from operation_context import current
    operation = current()
    if operation:
        data = row['data']
        links = {'run': history.scope} if row['input_sha256'] is not None else {}
        if data.get('execution_id'):
            links['execution'] = data['execution_id']
        if row['event'] == 'authorization':
            links['grant'] = data['request']['grant']
        if row['event'] == 'candidate':
            links['candidate'] = row['sha256']
        operation.link(**links)
        operation.event('formal_event_staged', phase='storage', scope=history.scope,
                        kind=row['event'], event_sha256=row['sha256'], input_sha256=row['input_sha256'])
    successor = VerifiedHistory(history.scope, freeze([*history.rows, row]), connection, history.owner)
    scope = read_context.check_scope(root)
    if scope is not None:
        scope[('verified-history', str(root.resolve()), history.scope)] = successor
    return successor


def append(root: Path, scope: str, input_sha256: str | None, event: str, data: dict,
           *, expected_previous: str | None = None, check_previous: bool = False) -> dict:
    with transaction(root):
        history = read_history(root, scope)
        proposal = propose_append(history, input_sha256, event, data,
                                  expected_previous=expected_previous, check_previous=check_previous)
        commit_append(root, proposal)
        if proposal.raw is None:
            return mutable(proposal.row)
        owned = read_context.check_scope(root)
        if owned is not None:
            identity = str(root.resolve())
            owned.pop(('verified-run', identity, scope), None)
            owned.pop(('run-decisions', identity, scope), None)
        read_context.invalidate_studio(root)
        return mutable(proposal.row)


def register_run(root: Path, run: str, prepared: dict, directory: Path) -> None:
    with transaction(root) as connection:
        connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
            (run,prepared['task']['task_id'],prepared['task']['production_id'],prepared['input_sha256'],prepared['envelope_sha256'],
             c.sha256_file(directory/'manifest.json'),directory.relative_to(root).as_posix(),c.now()))
        owned = read_context.check_scope(root)
        if owned is not None:
            identity = str(root.resolve())
            for kind in ('verified-run', 'verified-publication', 'run-decisions', 'verified-history'):
                owned.pop((kind, identity, run), None)
        read_context.invalidate_studio(root)


def latest_run(root: Path, task_id: str, *, production_id: str | None = None,
               through: str | None = None) -> str | None:
    """Look up registered order, optionally within a series and a fixed boundary.

    This index answers ownership without opening unrelated historical manifests.
    A selected run is still fully verified by its consumer before use.
    """
    with reader(root) as connection:
        if connection is None: return None
        conditions, arguments = ['task_id=?'], [task_id]
        if production_id is not None:
            conditions.append('production_id=?'); arguments.append(production_id)
        if through is not None:
            boundary = connection.execute('SELECT rowid, task_id FROM runs WHERE run_id=?',(through,)).fetchone()
            if boundary is None or boundary['task_id'] != task_id:
                raise ValueError('predecessor is not registered in this work task')
            conditions.append('rowid<=?'); arguments.append(boundary['rowid'])
        row = connection.execute('SELECT run_id FROM runs WHERE ' + ' AND '.join(conditions)
                                 + ' ORDER BY rowid DESC LIMIT 1', arguments).fetchone()
    return row['run_id'] if row else None


def runs(root: Path, *, task_id: str | None = None) -> list[dict]:
    with reader(root) as connection:
        if connection is None: return []
        if task_id is None:
            rows = connection.execute('SELECT * FROM runs ORDER BY rowid')
        else:
            rows = connection.execute('SELECT * FROM runs WHERE task_id=? ORDER BY rowid',(task_id,))
        return [dict(row) for row in rows]


def registered_run(root: Path, run: str) -> dict:
    with reader(root) as connection:
        row = connection.execute('SELECT * FROM runs WHERE run_id=?',(run,)).fetchone() if connection else None
    if row is None:
        raise ProductionError('RUN_NOT_REGISTERED', 'No formal run is registered with this ID.', phase='integrity', run=run,
                              required_action='Inspect staging and unreferenced published artifacts; recover a verified manifest or prepare a new run.')
    return dict(row)


# The repair of each cause that keeps a file from being read as evidence.
CAPTURE_MISSING = ('No file exists at this path below the root it is read from. Correct the path where it is given, '
                   'or put the file there, then run the command again.')
CAPTURE_LINK = ('This path is a symbolic link, and a link is never followed. Give the path of the regular file itself, '
                'or replace the link with a copy of that file, then run the command again.')
CAPTURE_DIRECTORY = 'This path is a directory. Give the path of one regular file, then run the command again.'
CAPTURE_NOT_REGULAR = ('This path is neither a regular file nor a directory. Give the path of a regular file, '
                       'then run the command again.')
CAPTURE_PRIVATE = ('This path names private Studio authentication state, credentials.json or a .pending-auth- file, '
                   'which is never read as an input, evidence or artifact. Give another file, then run the command again.')
CAPTURE_PATH_REFUSED = ('The path is refused before any file is opened, for the reason cause gives. Write it relative to '
                        'the root it is read from, with / separators and no . or .. segment, with no symbolic link in '
                        'that root or below it and no entry redirected outside it, then run the command again.')
CAPTURE_DENIED = ('The operating system denied reading this file. Grant read permission on it, or close the program that '
                  'holds it open, then run the command again.')
CAPTURE_OS_ERROR = ('The operating system could not read this file; cause gives its error. Resolve that condition, '
                    'then run the command again.')
CAPTURE_JSONL_LINE = ('Line {line} of this JSONL file is not one JSON value, for the reason cause gives, so the file is '
                      'not read. Correct that line so that it holds one complete JSON value, or name another file where '
                      'this one is given, then run the command again.')


class _NotEvidence(ValueError):
    """What `stable_read` found in place of a regular file, with the repair that fits it."""

    def __init__(self, cause: str, repair: str, **details: Any):
        super().__init__(cause)
        self.repair = repair
        self.details = details


def _capture_failed(path: str, exc: BaseException) -> ProductionError:
    """The diagnostic of a file that was not read: `cause` states why, and the repair fits that cause."""
    details = {}
    if isinstance(exc, _NotEvidence):
        repair = exc.repair
        details = exc.details
    elif isinstance(exc, PrivateStateError):
        repair = CAPTURE_PRIVATE
    elif isinstance(exc, PermissionError):
        repair = CAPTURE_DENIED
    elif isinstance(exc, OSError):
        repair = CAPTURE_OS_ERROR
    else:
        repair = CAPTURE_PATH_REFUSED
    return ProductionError('EVIDENCE_CAPTURE_FAILED', 'Evidence could not be read as one stable file.', file=path,
                           phase='input-capture', cause=str(exc), required_action=repair, **details)


def _jsonl_records(data: bytes) -> None:
    """Refuse JSONL whose nonblank line is not one JSON value, naming the line by its 1-based number."""
    for number, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        try:
            c.decode(line)
        except UnicodeDecodeError:
            reason = 'it is not UTF-8 text'
        except json.JSONDecodeError as exc:
            reason = f'{exc.msg} at column {exc.colno}'
        except ValueError as exc:
            reason = str(exc)
        else:
            continue
        raise _NotEvidence(f'line {number} is not one JSON value: {reason}',
                           CAPTURE_JSONL_LINE.format(line=number), line=number)


def stable_bytes(root: Path, path: str) -> bytes:
    """Read a studio file through one handle and detect replacement or in-flight writes.

    The path is checked against the root first. `stable_read` then reports
    what it finds at that path, including an absent file.
    """
    try:
        selected = c.local(root, path, exists=False)
    except (OSError, ValueError) as exc:
        raise _capture_failed(path, exc) from exc
    return stable_read(selected, path)


def stable_read(selected: Path, path: str) -> bytes:
    """Read an already resolved regular file as one stable content; `path` names it in diagnostics."""
    try:
        assert_public_path(selected)
        assert_public_path(path)
        if selected.is_symlink():
            raise _NotEvidence('symbolic link: ' + path, CAPTURE_LINK)
        if not selected.exists():
            raise _NotEvidence('missing file: ' + path, CAPTURE_MISSING)
        if selected.is_dir():
            raise _NotEvidence('directory: ' + path, CAPTURE_DIRECTORY)
        if not selected.is_file():
            raise _NotEvidence('not a regular file: ' + path, CAPTURE_NOT_REGULAR)
        with selected.open('rb') as stream:
            before = os.fstat(stream.fileno())
            data = stream.read()
            after = os.fstat(stream.fileno())
        current = selected.stat()
    except (OSError, ValueError) as exc:
        raise _capture_failed(path, exc) from exc
    # File identity, size and last write. Windows reports different change times
    # for a handle and a path, so the change time is not part of the identity.
    identity = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if identity(before) != identity(after) or identity(after) != identity(current) or len(data) != after.st_size:
        raise ProductionError('SOURCE_CHANGED', 'Source changed during capture.', file=path, phase='input-capture',
                              required_action='Finish the source write, then capture the complete evidence again.')
    if path.endswith('.jsonl'):
        if data and not data.endswith(b'\n'):
            raise ProductionError('EVIDENCE_INCOMPLETE', 'JSONL evidence has an incomplete final record.', file=path, phase='input-capture',
                                  required_action='Finish the write of this JSONL file so that its last record ends with a newline, then run the same command again.')
        try:
            _jsonl_records(data)
        except _NotEvidence as exc:
            raise _capture_failed(path, exc) from exc
    return data


RESTORE_EVIDENCE = ('Restore the exact bytes matching the expected digest; this run is stopped until then; '
                    'never recreate different evidence.')
RUN_EVIDENCE_IMPACT = ('This run cannot be loaded, authorized, executed, resumed or reviewed until the exact bytes '
                       'are restored. Other runs keep their own records.')
AUTHORITY_EVIDENCE_IMPACT = ('Every run of this work task stops authorizing and executing until the exact bytes '
                             'are restored. Recorded runs and their history stay readable.')


def evidence_error(code: str, message: str, *, file: str | None, expected: str, actual: str | None = None,
                   run: str | None = None, event: str | None = None, impact: str = RUN_EVIDENCE_IMPACT,
                   **details: Any) -> ProductionError:
    """A missing or corrupt saved snapshot: what is gone, where it belongs, its effect and the one repair."""
    return ProductionError(code, message, phase='integrity', file=file, run=run, event=event, expected=expected,
                           actual=actual, impact=impact, required_action=RESTORE_EVIDENCE, **details)


def evidence_snapshot(root: Path, path: str, locator: str, *, purpose: str, raw: bytes | None = None) -> dict:
    """Store evidence bytes, read once, with their origin; `raw` keeps bytes another reader already verified."""
    c.text(locator,'evidence locator'); c.text(purpose,'evidence purpose')
    assert_public_path(path)
    raw = stable_bytes(root,path) if raw is None else raw
    digest = c.object_store(root/'production',raw)
    return {'path':path,'locator':locator,'sha256':digest,'size':len(raw),'captured_at':c.now(),'purpose':purpose}


def capture_evidence(root: Path, directory: Path, path: str, *, locator: str, purpose: str,
                     raw: bytes | None = None, rows: list[dict] = ()) -> dict:
    """Store one evidence file in a run, with its locator, capture time and purpose.

    The bytes are read once with `stable_bytes`, or taken from `raw` when a
    verifier already read them. A capture identical to one already recorded in
    `rows` returns that record, so a repeated request records the same evidence.
    """
    c.text(locator,'evidence locator'); c.text(purpose,'evidence purpose')
    assert_public_path(path)
    raw = stable_bytes(root,path) if raw is None else raw
    digest = c.object_store(directory,raw)
    for row in rows:
        for item in row['data'].get('files',[])+row['data'].get('evidence',[]):
            if (item.get('path'),item.get('sha256'),item.get('locator'),item.get('purpose'))==(path,digest,locator,purpose):
                return dict(item)
    return {'path':path,'sha256':digest,'size':len(raw),'locator':locator,'captured_at':c.now(),'purpose':purpose}


def verify_evidence(root: Path, snapshot: dict, *, run: str | None = None, event: str | None = None,
                    impact: str = RUN_EVIDENCE_IMPACT) -> bytes:
    assert_public_path(snapshot['path'])
    key = snapshot['sha256']
    path = c.local(root,'production/objects/'+c.sha(key),exists=False)
    if not path.is_file():
        raise evidence_error('EVIDENCE_SNAPSHOT_MISSING','Stored evidence is missing.',file=str(path),
                             run=run,event=event,expected=key,impact=impact,source=snapshot.get('path'))
    data = c.read(path)
    if c.digest(data) != key or len(data) != snapshot['size']:
        raise evidence_error('EVIDENCE_SNAPSHOT_CORRUPT','Stored evidence no longer matches its digest.',
                             file=str(path),run=run,event=event,expected=key,actual=c.digest(data),impact=impact,
                             source=snapshot.get('path'))
    return data


@dataclass(frozen=True, slots=True)
class CurrentAuthority:
    """A checked grant event and the exact evidence bytes read with it.

    Each effect checks the current SQL grant state. Its unchanged immutable
    event and evidence are shared by the operation that already acquired them.
    """

    task_id: str
    event: dict
    evidence: tuple[dict, ...]

    @property
    def document(self) -> dict:
        return self.event['data']['authority']


@read_context.operation
def read_authority(root: Path, task_id: str, *, required: bool = True) -> CurrentAuthority | None:
    """Read and verify one current grant state without changing run input."""
    scope = 'authority:' + task_id
    with reader(root) as connection:
        state = connection.execute('SELECT * FROM authority_states WHERE task_id=?',(task_id,)).fetchone() if connection else None
        owner = read_context.check_scope(root)
        cache_key = ('current-authority', str(root.resolve()), task_id)
        if state is not None:
            observed = dict(state)
            previous = owner.get(cache_key) if owner is not None else None
            if previous is not None and previous[0] == observed:
                return previous[1]
            rows = read_history(root, scope).rows
    if state is None:
        if not required: return None
        raise ProductionError('AUTHORIZATION_REQUIRED','The work task has no registered current authority.',phase='authorization',
                              required_action='Import an actual authority declaration with its evidence before execution.')
    matches = [row for row in rows if row['sha256'] == state['event_sha256']]
    if len(matches) != 1 or matches[0] != rows[-1]:
        raise ProductionError('AUTHORITY_STATE_CORRUPT','Authority state is not the terminal committed event.',phase='integrity')
    data = matches[0]['data']
    if c.content_id(data['authority']) != state['content_sha256']:
        raise ProductionError('AUTHORITY_STATE_CORRUPT','Authority content digest does not match.',phase='integrity')
    objects: dict[str, bytes] = {}
    evidence = []
    for item in data['evidence']:
        assert_public_path(item['path'])
        key = c.sha(item['sha256'])
        if key not in objects:
            objects[key] = verify_evidence(root, item, event=state['event_sha256'],
                                           impact=AUTHORITY_EVIDENCE_IMPACT)
        raw = objects[key]
        # Several locators or purposes may name the same content object. Its
        # bytes were checked once, while every row still has to name its size.
        if len(raw) != item['size']:
            raise evidence_error('EVIDENCE_SNAPSHOT_CORRUPT', 'Stored evidence no longer matches its digest.',
                file=str(c.local(root, 'production/objects/' + key, exists=False)), event=state['event_sha256'],
                expected=key, actual=key, impact=AUTHORITY_EVIDENCE_IMPACT, source=item['path'])
        evidence.append(freeze({**item, 'raw': raw}))
    held = CurrentAuthority(task_id, freeze(matches[0]), tuple(evidence))
    if owner is not None:
        owner[cache_key] = (freeze(observed), held)
    return held


def authority(root: Path, task_id: str, *, required: bool = True) -> dict | None:
    """Export an editable current grant document for an external caller."""
    held = read_authority(root, task_id, required=required)
    return mutable(held.document) if held is not None else None


def authority_record(root: Path, task_id: str) -> dict | None:
    rows=event_rows(root,'authority:'+task_id)
    return rows[-1] if rows else None


def edited_authority_source(root: Path, current: CurrentAuthority | None) -> dict | None:
    """The authority file of the latest import, when its bytes now differ from the bytes that import recorded.

    Execution reads the imported authority, so an edit of that file takes effect
    only through authority-import. A missing file changes nothing and is None.
    """
    if current is None:
        return None
    sources = [item for item in current.evidence if item['purpose'] == 'authority-source']
    if not sources:
        return None
    imported = sources[-1]
    path = Path(imported['path'])
    try:
        path = path if path.is_absolute() else c.local(root, imported['path'], exists=False)
        if not path.is_file():
            return None
        actual = c.digest(path.read_bytes())
    except (OSError, ValueError):
        return None
    if actual == imported['sha256']:
        return None
    return {'path': imported['path'], 'imported_sha256': imported['sha256'], 'current_sha256': actual}


def authority_snapshot(root: Path, task_id: str, current: CurrentAuthority | None, *,
                       source_path: str | None = None, run: str | None = None) -> dict:
    """Expose the already acquired authority and its exact update predecessor.

    `source_edited` names the authority file when it changed after its import;
    the update action then imports that edit.
    """
    from cli_invocation import python_argv
    compact_source = None
    if current is not None and current.task_id != task_id:
        raise ValueError('current authority belongs to another work task')
    if current is not None:
        sources = [item for item in current.evidence if item['purpose'] == 'authority-source']
        if sources:
            source_path = sources[-1]['path']
            source = c.decode(sources[-1]['raw'])
            if source.get('artifact_type') == 'production-authority-update':
                compact_source = source
    arguments = ['authority-import', '--root', str(root), '--file', source_path or '<authority-file>']
    if current is not None:
        arguments += ['--expected-event', current.event['sha256']]
    edited = edited_authority_source(root, current)
    reason = ('Edit the current declaration from actual authority, then import it with this observed predecessor. '
              'Author input can be supplied by the acting agent from already-established user authorization; '
              'ask the user only if necessary authority remains unresolved. Reinspect if another update wins.')
    if edited is not None:
        reason = (f'{edited["path"]} changed after its import, and draft-execution, execute and status read the '
                  'imported authority. Import the edit with this command when it records an actual authority change; '
                  'otherwise restore the imported content. ' + reason)
    command = 'authority-import'
    if compact_source is not None:
        selected_run = run or compact_source['run']
        out = f'production/authority-updates/{selected_run}/{current.event["sha256"][:24]}.json'
        number, stem = 2, out[:-5]
        while c.local(root, out, exists=False).exists():
            out = stem + '-' + str(number) + '.json'
            number += 1
        command = 'draft-authority-update'
        arguments = [command, '--root', str(root), '--run', selected_run, '--out', out]
        reason = ('The latest authority source is a run-bound addition already imported under its observed predecessor. '
                  'Draft a new update against the current event, then apply actual instruction evidence. '
                  'Existing grants and stop conditions remain current; an edited earlier draft does not replace them.')
    return {'document': mutable(current.document) if current is not None else None,
        'event_sha256': current.event['sha256'] if current is not None else None,
        'source_path': source_path,
        'source_edited': edited,
        'update_action': {'command': command,
            'argv': python_argv(Path(__file__).with_name('production_workflow.py'), *arguments),
            'reason': reason,
            'requires_author_input': True}}


def import_authority(root: Path, file: str, *, expected: str | None = None, initial: bool = False,
                     report_changes: bool = False) -> dict:
    import production_permissions as permissions
    import production_authority_drafts as drafts
    from state_protocol import validate_against_schema
    raw=stable_bytes(root,file); document=c.decode(raw)
    compact = isinstance(document, dict) and document.get('artifact_type') == drafts.UPDATE_TYPE
    schema = drafts.UPDATE_SCHEMA if compact else 'schemas/authoring/production-authority.schema.json'
    errors=validate_against_schema(document,c.load(Path(__file__).resolve().parents[1]/schema))
    if errors:
        raise ProductionError('INPUT_SCHEMA_INVALID','; '.join(errors),file=file,phase='authority-import',
                              required_action='Correct the fields the message names in this authority declaration, following '
                                              f'{schema}, then run the command again.')
    with transaction(root) as connection:
        prior=authority_record(root,document['task_id'])
        if initial and prior is not None:
            return prior
        if prior is not None and expected != prior['sha256']:
            raise ProductionError('AUTHORITY_UPDATE_CONFLICT','An update must name the current authority event digest.',phase='authority-import',
                                  expected=prior['sha256'],actual=expected,
                                  required_action='Read the current authority, reconcile changes, and supply --expected-event.')
        if compact and (prior is None or document['expected_event'] != prior['sha256']):
            raise ProductionError('AUTHORITY_UPDATE_CONFLICT',
                'The run-bound update does not name the current authority event.', phase='authority-import', file=file,
                pointer='$.expected_event', expected=prior['sha256'] if prior else None, actual=document['expected_event'],
                required_action='Inspect the current authority and use draft-authority-update for this run again. '
                                'Reconcile its actual new authority; changing only --expected-event cannot update the draft.')
        if prior is not None and document['issuer']!=prior['data']['authority']['issuer']:
            issuer=prior['data']['authority']['issuer']
            raise ProductionError('AUTHORIZATION_MISMATCH','An authority update cannot silently replace its issuer.',
                phase='authority-import',file=file,pointer='/issuer',expected=issuer,actual=document['issuer'],
                current_authority={'task_id':document['task_id'],'issuer':issuer,'event':prior['sha256']},
                required_action=f'Keep issuer {issuer!r} for this work task. Edit grants and their actual evidence in '
                                f'{file}, then retry authority-import with --expected-event {prior["sha256"]}. '
                                'A different issuing principal requires its own work-task authority; do not rename the current issuer.')
        from input_evidence import EvidenceAcquisition
        inputs=EvidenceAcquisition(root)
        held = read_authority(root, document['task_id']) if compact else None
        document = (drafts.materialize_update(root, document, held, inputs, file=file) if compact
                    else permissions.acquire(document,document['task_id'],inputs))
        declaration = inputs.select(document['evidence']['path'])
        if not inputs.bytes[declaration['path']].strip():
            raise ProductionError('AUTHORIZATION_REQUIRED', 'The authority declaration evidence is empty.',
                phase='authority-evidence', file=document['evidence']['path'],
                required_action='Select nonempty actual instruction evidence before importing authority.')
        if not compact:
            drafts.check_approval_evidence(root, inputs.bytes[declaration['path']], task_id=document['task_id'],
                                           issuer=document['issuer'], file=document['evidence']['path'])
        evidence=[evidence_snapshot(root,document['evidence']['path'],document['evidence']['locator'],
            purpose='authority-declaration',raw=inputs.bytes[declaration['path']])]
        if held is not None:
            # Unchanged grants keep their captured evidence even if the original
            # scope files moved or changed. New additions acquire their own bytes.
            evidence.extend({key: value for key, value in item.items() if key != 'raw'}
                            for item in held.evidence if item['purpose'] != 'authority-source')
        # Store the scope bytes the verifier read, not a second reading of the files.
        for path in sorted(inputs.locators):
            evidence.append(evidence_snapshot(root,path,inputs.locators.get(path,'whole'),purpose='request-scope',
                                              raw=inputs.bytes[path]))
        # The declaration itself is also immutable evidence of this update.
        evidence.append(evidence_snapshot(root,file,'whole',purpose='authority-source',raw=raw))
        evidence = list({(item['path'], item['sha256'], item['locator'], item['purpose']): item
                         for item in evidence}.values())
        row=append(root,'authority:'+document['task_id'],None,'authority-updated',
                   {'authority':document,'evidence':evidence,'previous_state':prior['sha256'] if prior else None,'effective_at':c.now()})
        connection.execute('INSERT INTO authority_states VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET content_sha256=excluded.content_sha256,event_sha256=excluded.event_sha256',
                           (document['task_id'],c.content_id(document),row['sha256']))
        read_context.invalidate_studio(root)
        return ({**row, 'changed_grants': drafts.changed_grants(prior['data']['authority'] if prior else None, document)}
                if report_changes else row)


def captured_authority_inputs(authority: CurrentAuthority) -> tuple[dict, ...]:
    """Return this checked authority's evidence, without another storage read.

    Keep each item by path and SHA-256: a source such as a work ledger grows,
    so one path can hold several valid readings. These immutable rows retain
    the exact bytes verified with the owning grant event under ``raw``.
    """
    return authority.evidence
