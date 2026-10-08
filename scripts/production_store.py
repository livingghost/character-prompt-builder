"""Transactional production records and immutable evidence.

SQLite is the sole editable record of runs, grants and execution events. JSON
files inside published run directories are immutable content addressed by that
record. JSONL/HTML views are projections, never another editable ledger.
"""
from __future__ import annotations
import contextlib
import contextvars
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Iterator

import execution_contract as c
from production_diagnostics import ProductionError

_CONNECTIONS: contextvars.ContextVar[dict[str, sqlite3.Connection]] = contextvars.ContextVar('production_connections', default={})
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


def database(root: Path) -> Path:
    return c.local(root, 'production/records.sqlite3', exists=False)


@contextlib.contextmanager
def transaction(root: Path) -> Iterator[sqlite3.Connection]:
    root = root.resolve()
    key = str(root)
    existing = _CONNECTIONS.get().get(key)
    if existing is not None:
        savepoint = 's' + uuid.uuid4().hex
        existing.execute('SAVEPOINT ' + savepoint)
        try:
            yield existing
            existing.execute('RELEASE ' + savepoint)
        except BaseException:
            existing.execute('ROLLBACK TO ' + savepoint)
            existing.execute('RELEASE ' + savepoint)
            raise
        return
    with c.lock(root):
        path = database(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        token = None
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=FULL')
            connection.executescript(_DDL)
            connection.execute('BEGIN IMMEDIATE')
            token = _CONNECTIONS.set({**_CONNECTIONS.get(), key: connection})
            yield connection
            connection.commit()
            from operation_context import current
            if current():
                current().event('formal_transaction_committed', database=str(path), phase='storage')
        except BaseException:
            connection.rollback()
            from operation_context import current
            if current():
                current().event('formal_transaction_rolled_back', database=str(path), phase='storage')
            raise
        finally:
            if token is not None: _CONNECTIONS.reset(token)
            connection.close()


@contextlib.contextmanager
def reader(root: Path) -> Iterator[sqlite3.Connection | None]:
    connection = _CONNECTIONS.get().get(str(root.resolve()))
    if connection is not None:
        yield connection; return
    path = database(root)
    if not path.exists():
        yield None; return
    connection = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def validate_event_chain(rows: list[dict], scope: str) -> None:
    """Validate a read-only event export using the same chain as the store."""
    if not isinstance(rows, list):
        raise ProductionError('EVENT_CHAIN_CORRUPT', 'Event records must be a list.', phase='integrity', run=scope)
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
                                  phase='integrity', run=scope, event=sequence) from exc
        if not valid:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'Event export differs from its recorded chain.',
                                  phase='integrity', run=scope, event=sequence, expected=row.get('sha256'))
        previous = row['sha256']


def event_rows(root: Path, scope: str) -> list[dict]:
    with reader(root) as connection:
        if connection is None: return []
        entries = list(connection.execute('SELECT * FROM events WHERE scope=? ORDER BY sequence', (scope,)))
    result = []
    previous = None
    for entry in entries:
        try:
            row = c.decode(bytes(entry['body']))
            if not isinstance(row, dict):
                raise ValueError('Event body must be an object.')
            content = dict(row)
            digest = content.pop('sha256', None)
            consistent = (c.content_id(content) == digest and entry['sha256'] == digest
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
                                  phase='integrity', run=scope, event=entry['sequence'], expected=entry['sha256'])
        previous = digest
        result.append(row)
    validate_event_chain(result, scope)
    return result


def append(root: Path, scope: str, input_sha256: str | None, event: str, data: dict,
           *, expected_previous: str | None = None, check_previous: bool = False) -> dict:
    with transaction(root) as connection:
        rows = event_rows(root, scope)
        for row in reversed(rows):
            if row['event'] == event and row['data'] == data: return row
        previous = rows[-1]['sha256'] if rows else None
        if check_previous and previous != expected_previous:
            raise ProductionError('EVENT_CONFLICT', 'Another operation committed first; reload the current state.', phase='storage', run=scope)
        row = {'sequence': len(rows)+1, 'previous': previous, 'input_sha256': input_sha256,
               'event': event, 'data': data, 'created_at': c.now()}
        row['sha256'] = c.content_id(row)
        try:
            connection.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',
                (scope,row['sequence'],row['sha256'],previous,input_sha256,event,c.encoded(row)))
        except sqlite3.IntegrityError as exc:
            raise ProductionError('DISPATCH_ALREADY_CLAIMED' if 'claim' in event else 'EVENT_CONFLICT',
                'The run already has this committed operation.', phase='storage', run=scope,
                required_action='Use resume for the same execution, variant for changed input, or repeat for an intentional additional run.') from exc
        from operation_context import current
        operation = current()
        if operation:
            links = {'run': scope} if input_sha256 is not None else {}
            if data.get('execution_id'):
                links['execution'] = data['execution_id']
            if event == 'authorization':
                links['grant'] = data['request']['grant']
            if event == 'candidate':
                links['candidate'] = row['sha256']
            operation.link(**links)
            operation.event('formal_event_staged', phase='storage', scope=scope,
                            kind=event, event_sha256=row['sha256'], input_sha256=input_sha256)
        return row


def register_run(root: Path, run: str, prepared: dict, directory: Path) -> None:
    with transaction(root) as connection:
        connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
            (run,prepared['task']['task_id'],prepared['task']['production_id'],prepared['input_sha256'],prepared['envelope_sha256'],
             c.sha256_file(directory/'manifest.json'),directory.relative_to(root).as_posix(),c.now()))


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


def stable_bytes(root: Path, path: str) -> bytes:
    """Read a studio file through one handle and detect replacement or in-flight writes."""
    try:
        selected = c.local(root,path)
    except (OSError, ValueError) as exc:
        raise ProductionError('EVIDENCE_CAPTURE_FAILED', 'Evidence could not be read as one stable file.', file=path, phase='input-capture') from exc
    return stable_read(selected, path)


def stable_read(selected: Path, path: str) -> bytes:
    """Read an already resolved regular file as one stable content; `path` names it in diagnostics."""
    try:
        if selected.is_symlink() or not selected.is_file():
            raise ValueError('not a regular file')
        with selected.open('rb') as stream:
            before = os.fstat(stream.fileno())
            data = stream.read()
            after = os.fstat(stream.fileno())
        current = selected.stat()
    except (OSError, ValueError) as exc:
        raise ProductionError('EVIDENCE_CAPTURE_FAILED', 'Evidence could not be read as one stable file.', file=path, phase='input-capture') from exc
    # File identity, size and last write. Windows reports different change times
    # for a handle and a path, so the change time is not part of the identity.
    identity = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if identity(before) != identity(after) or identity(after) != identity(current) or len(data) != after.st_size:
        raise ProductionError('SOURCE_CHANGED', 'Source changed during capture.', file=path, phase='input-capture',
                              required_action='Finish the source write, then capture the complete evidence again.')
    if path.endswith('.jsonl'):
        if data and not data.endswith(b'\n'):
            raise ProductionError('EVIDENCE_INCOMPLETE', 'JSONL evidence has an incomplete final record.', file=path, phase='input-capture')
        for line in data.splitlines():
            if line.strip(): c.decode(line)
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
    raw = stable_bytes(root,path) if raw is None else raw
    digest = c.object_store(directory,raw)
    for row in rows:
        for item in row['data'].get('files',[])+row['data'].get('evidence',[]):
            if (item.get('path'),item.get('sha256'),item.get('locator'),item.get('purpose'))==(path,digest,locator,purpose):
                return dict(item)
    return {'path':path,'sha256':digest,'size':len(raw),'locator':locator,'captured_at':c.now(),'purpose':purpose}


def verify_evidence(root: Path, snapshot: dict, *, run: str | None = None, event: str | None = None,
                    impact: str = RUN_EVIDENCE_IMPACT) -> bytes:
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


def authority(root: Path, task_id: str, *, required: bool = True) -> dict | None:
    with reader(root) as connection:
        state = connection.execute('SELECT * FROM authority_states WHERE task_id=?',(task_id,)).fetchone() if connection else None
    if state is None:
        if not required: return None
        raise ProductionError('AUTHORIZATION_REQUIRED','The work task has no registered current authority.',phase='authorization',
                              required_action='Import an actual authority declaration with its evidence before execution.')
    rows = event_rows(root,'authority:'+task_id)
    matches = [row for row in rows if row['sha256'] == state['event_sha256']]
    if len(matches) != 1 or matches[0] != rows[-1]:
        raise ProductionError('AUTHORITY_STATE_CORRUPT','Authority state is not the terminal committed event.',phase='integrity')
    data = matches[0]['data']
    if c.content_id(data['authority']) != state['content_sha256']:
        raise ProductionError('AUTHORITY_STATE_CORRUPT','Authority content digest does not match.',phase='integrity')
    for item in data['evidence']:
        verify_evidence(root,item,event=state['event_sha256'],impact=AUTHORITY_EVIDENCE_IMPACT)
    return {**data['authority']}


def authority_record(root: Path, task_id: str) -> dict | None:
    rows=event_rows(root,'authority:'+task_id)
    return rows[-1] if rows else None


def import_authority(root: Path, file: str, *, expected: str | None = None, initial: bool = False) -> dict:
    import production_permissions as permissions
    from state_protocol import validate_against_schema
    raw=stable_bytes(root,file); document=c.decode(raw)
    errors=validate_against_schema(document,c.load(Path(__file__).resolve().parents[1]/'schemas/authoring/production-authority.schema.json'))
    if errors: raise ProductionError('INPUT_SCHEMA_INVALID','; '.join(errors),file=file,phase='authority-import')
    permissions.validate(document,document['task_id'])
    with transaction(root) as connection:
        prior=authority_record(root,document['task_id'])
        if initial and prior is not None:
            return prior
        if prior is not None and expected != prior['sha256']:
            raise ProductionError('AUTHORITY_UPDATE_CONFLICT','An update must name the current authority event digest.',phase='authority-import',
                                  expected=prior['sha256'],actual=expected,
                                  required_action='Read the current authority, reconcile changes, and supply --expected-event.')
        if prior is not None and document['issuer']!=prior['data']['authority']['issuer']:
            raise ProductionError('AUTHORIZATION_MISMATCH','An authority update cannot silently replace its issuer.',phase='authority-import')
        evidence=[evidence_snapshot(root,document['evidence']['path'],document['evidence']['locator'],purpose='authority-declaration')]
        import request_scope
        from input_evidence import InputEvidence
        inputs=InputEvidence(root)
        for grant in document['grants']:
            request_scope.verify_sources(grant['request_scope'],None,inputs)
        # Store the scope bytes the verifier read, not a second reading of the files.
        for path in sorted(inputs.read_paths):
            evidence.append(evidence_snapshot(root,path,inputs.locators.get(path,'whole'),purpose='request-scope',
                                              raw=InputEvidence._decode(inputs.snapshots[path])))
        # The declaration itself is also immutable evidence of this update.
        evidence.append(evidence_snapshot(root,file,'whole',purpose='authority-source',raw=raw))
        row=append(root,'authority:'+document['task_id'],None,'authority-updated',
                   {'authority':document,'evidence':evidence,'previous_state':prior['sha256'] if prior else None,'effective_at':c.now()})
        connection.execute('INSERT INTO authority_states VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE SET content_sha256=excluded.content_sha256,event_sha256=excluded.event_sha256',
                           (document['task_id'],c.content_id(document),row['sha256']))
        return row


def captured_authority_inputs(root: Path, task_id: str) -> list[dict]:
    """Every evidence snapshot of the current authority, with its verified bytes under `raw`.

    Keep each item by path and SHA-256: a source such as a work ledger grows,
    so one path can hold several valid readings.
    """
    record=authority_record(root,task_id)
    if record is None:return []
    return [{**item,'raw':verify_evidence(root,item,event=record['sha256'],impact=AUTHORITY_EVIDENCE_IMPACT)}
            for item in record['data']['evidence']]
