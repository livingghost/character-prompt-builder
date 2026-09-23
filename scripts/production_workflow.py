#!/usr/bin/env python3
"""Prepare, authorize, execute, observe, revise and complete a production task.

Every operation uses the current authored contract. Planning and observation do
not establish consent. Only explicit, scoped grants authorize actions; hashes
prove consistency of recorded bytes, never artistic success or user identity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

import execution_contract as c
import reservation_lifecycle as lifecycle
import execution_routes
from pack_manager import generate_uuid7
import production_evidence as media
import production_permissions as permissions
import production_plan as plan

ROOT = Path(__file__).resolve().parents[1]
EVENTS = {'authorization', 'handoff', 'external-claim', 'dispatch-claim',
          'dispatch-results', 'candidate', 'review', 'selection', 'edit',
          'adoption-claim', 'adoption-result', 'image-edit-claim', 'image-edit-output', 'completion'} | lifecycle.EVENTS


def run_identifier(run: Any) -> str:
    try:
        identifier = uuid.UUID(run)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError('run must be a UUIDv7') from exc
    if identifier.version != 7 or str(identifier) != run:
        raise ValueError('run must be a canonical UUIDv7')
    return run


def run_dir(root: Path, run: str, *, exists: bool = True) -> Path:
    return c.local(root, 'production/' + run_identifier(run), exists=exists)


def schema_check(value: Any, name: str) -> None:
    if name=='review' and isinstance(value,dict) and isinstance(value.get('checks'),list):
        if any(isinstance(x,dict) and x.get('verdict')=='fail' for x in value['checks']) and value.get('repairs')==[] and value.get('unresolved')==[]:
            raise ValueError('a failed review needs a concrete repair or unresolved issue')
    from state_protocol import validate_against_schema
    schema = c.load(ROOT / f'schemas/authoring/production-{name}.schema.json')
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('production ' + name + ': ' + '; '.join(errors))


def validate_task(task: Any) -> dict:
    schema_check(task, 'task')
    production_identifier(task['production_id'])
    route = execution_routes.resolve(task['route'], task['features'])
    plan.strings(task['features'], 'features')
    if bool(task.get('scene_materials', [])) != ('scene-persona' in route['features']):
        raise ValueError('scene-persona requires explicit scene_materials selectors and vice versa')
    ids: set[str] = set()
    roles: set[str] = set()
    for source in task['sources']:
        if source['id'] in ids:
            raise ValueError('duplicate source id')
        ids.add(source['id'])
        if source['disposition'] == 'applied':
            roles.add(source['role'])
    if set(route['source_roles']) - roles:
        raise ValueError('missing applied source roles: ' + ', '.join(sorted(set(route['source_roles']) - roles)))
    ids = set()
    for criterion in task['criteria']:
        if criterion['id'] in ids:
            raise ValueError('duplicate criterion id')
        ids.add(criterion['id'])
    if 'world-view' in route['features'] and not task['world_views']:
        raise ValueError('selected route requires a compiled world view')
    moments = task.get('moment_views', [])
    if bool(moments) != ('story-context' in route['features']):
        raise ValueError('story-context requires selected moment views and vice versa')
    for entries in (task['world_views'], moments):
        keys = [c.content_id(x) for x in entries]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate bounded view selector')
    plan.validate(task['direction'], task['sources'], task['criteria'])
    return route


def snapshot(root: Path, task_path: str) -> tuple[dict, dict, list[dict], dict[str, bytes]]:
    task_bytes = c.read(c.local(root, task_path))
    task = c.decode(task_bytes)
    route = validate_task(task)
    dependencies: dict[tuple[str, str], dict] = {}
    blobs: dict[str, bytes] = {}
    def add(base: Path, path: str, space: str = 'project') -> bytes:
        raw = c.read(c.local(base, path))
        key = c.digest(raw)
        dependencies[(space, path)] = {'space': space, 'path': path, 'sha256': key, 'size': len(raw)}
        blobs[key] = raw
        return raw
    if add(root, task_path) != task_bytes:
        raise ValueError('task changed during preparation')
    import route_reading
    reading = c.decode(add(root, task['route_reading']))
    issuance = route_reading.require_route_reading(reading, project=root, routes={task['route']}, features=task['features'])
    for source in task['sources']:
        add(root, source['path'])
    delivery = add(root, task['delivery']['path']).decode('utf-8')
    c.text(delivery, 'delivery')
    authority = c.decode(add(root, task['authority']))
    schema_check(authority, 'authority')
    permissions.validate(authority, task['task_id'])
    add(root, authority['evidence']['path'])
    from input_evidence import InputEvidence
    import request_scope
    scope_reader = InputEvidence(root)
    for grant in authority['grants']:
        request_scope.verify_sources(grant['request_scope'], None, scope_reader)
    for path in sorted(scope_reader.read_paths):
        add(root, path)
    known_criteria = {x['id'] for x in task['criteria']}
    for grant in authority['grants']:
        if set(grant['protected_criteria']) - known_criteria:
            raise ValueError('grant protects an undeclared criterion')
    views = []
    for spec in task['world_views']:
        import world_realization as world
        directory = c.local(root, spec['bundle'])
        checked = world.verify_bundle(root, spec['plan'], directory)
        if not checked['ok']:
            raise ValueError('world bundle is stale or invalid')
        compiled = world.compile_plan(root, spec['plan'])
        matches = [v for u in compiled['units'] if u['unit_id'] == spec['unit_id']
                   for v in u['views'] if v['view_id'] == spec['view_id']]
        if len(matches) != 1:
            raise ValueError('world selector must identify one view')
        views.append(matches[0])
        world_plan = c.decode(add(root, spec['plan']))
        for source in world_plan['sources']:
            add(root, source['path'])
        for file in sorted(directory.rglob('*')):
            if file.is_file() or file.is_symlink():
                add(root, file.relative_to(root).as_posix())
    moments = []
    for spec in task.get('moment_views', []):
        import story_context as moment
        directory = c.local(root, spec['bundle'])
        compiled = moment.materialize(root, spec['query'])
        if not moment.verify_output(compiled, directory)['content_ok']:
            raise ValueError('moment bundle is stale or invalid')
        matches = [v for v in compiled['views'] if v['view_id'] == spec['view_id']]
        if len(matches) != 1 or not matches[0]['requirements_ok']:
            raise ValueError('moment selector must identify a view with satisfied field requirements')
        moments.append(matches[0])
        if c.digest(add(root, spec['query'])) != compiled['author']['query_sha256']:
            raise ValueError('moment query changed during preparation')
        for source in compiled['author']['sources']:
            if c.digest(add(root, source['path'])) != source['sha256']:
                raise ValueError('moment source changed during preparation')
        for name, expected in moment.output_files(compiled).items():
            if add(root, (directory / name).relative_to(root).as_posix()) != expected:
                raise ValueError('moment bundle changed during preparation')
    import scene_persona
    authoring_materials = scene_persona.consume(root, task.get('scene_materials', []), add)
    # The installed implementation is pinned by digest; its bytes stay in the installation.
    skill_files = {execution_routes.MANIFEST, 'package-manifest.toml'} | {r['path'] for r in route['reads']}
    for parent, glob in [('scripts', '*.py'), ('scripts', '*.json'), ('schemas', '*.json')]:
        skill_files.update(f.relative_to(ROOT).as_posix() for f in (ROOT / parent).rglob(glob))
    for path in sorted(skill_files):
        key, size = c.file_digest(ROOT, path)
        dependencies[('skill', path)] = {'space': 'skill', 'path': path, 'sha256': key, 'size': size}
    consumer = {'route': task['route'], 'transport': task['delivery']['transport'],
                'instructions': delivery, 'criteria': task['criteria'],
                'direction': plan.consumer(task['direction']),
                'world_views': views, 'moment_views': moments, 'authoring_materials': authoring_materials}
    prepared = {'task_path': task_path, 'task': task, 'route': route, 'authority': authority,
                'route_reading': reading, 'route_reading_sha256': c.content_id(reading), 'reading_issuance': issuance,
                'dependencies': sorted(dependencies.values(), key=lambda x: (x['space'], x['path'])),
                'consumer_sha256': c.content_id(consumer)}
    return prepared, consumer, prepared['dependencies'], blobs


def production_identifier(value: Any) -> str:
    try:
        identifier = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('production_id must be an explicitly assigned UUIDv7') from exc
    if identifier.version != 7 or str(identifier) != value:
        raise ValueError('production_id must be a canonical UUIDv7')
    return value


def criteria_predecessor(root: Path, predecessor: str | None, task: dict) -> str | None:
    """Find the nearest immutable run in this work task and production series."""
    seen = set()
    current = predecessor
    while current is not None:
        if current in seen:
            raise ValueError('production predecessor chain is cyclic')
        seen.add(current)
        _, older, _, _ = load_run(root, current)
        if older['task']['task_id'] != task['task_id']:
            raise ValueError('predecessor crosses the work task boundary')
        if older['task']['production_id'] == task['production_id']:
            return current
        current = older['predecessor']
    return None


def validate_protected_criteria(root: Path, prepared: dict, grant: dict, *, revised: dict | None = None) -> None:
    """Compare protected criteria in one explicit production series."""
    if revised is not None:
        older, newer = prepared['task'], revised
        if older['production_id'] != newer['production_id']:
            raise ValueError('a revision preserves its production_id')
    else:
        expected = criteria_predecessor(root, prepared['predecessor'], prepared['task'])
        if expected != prepared['criteria_predecessor']:
            raise ValueError('criteria predecessor differs from the production series')
        if expected is None:
            return
        older, newer = load_run(root, expected)[1]['task'], prepared['task']
    before, after = ({x['id']: x for x in t['criteria']} for t in (older, newer))
    if any(before.get(key) != after.get(key) for key in grant['protected_criteria']):
        raise ValueError('protected criterion changed; obtain explicit authority for the change')


def _prepare(root: Path, task_path: str, *, parent: dict | None = None, identity: str | None = None) -> dict:
    """Called with the project lock held. Publish a complete immutable run."""
    import work_ledger
    prepared, consumer, _, blobs = snapshot(root, task_path)
    current = work_ledger.require_open(root)
    if current['task_id'] != prepared['task']['task_id']:
        raise ValueError('task is not the open work-ledger task')
    run = identity or generate_uuid7()
    prepared['parent'] = parent
    if parent is not None:
        original = load_run(root, parent['parent_run'])[1]
        if original['task']['production_id'] != prepared['task']['production_id']:
            raise ValueError('a revision preserves its production_id')
    prepared['predecessor'] = current.get('production_run')
    if prepared['predecessor'] == run:
        # A retried revision resumes the already published child, not itself.
        existing = load_run(root, run)
        if existing[1]['task'] != prepared['task'] or existing[1]['parent'] != parent:
            raise ValueError('revised child no longer matches the recorded edit')
        return {'run': run, 'input_sha256': existing[1]['input_sha256'],
                'consumer': str(existing[0] / 'consumer.json')}
    prepared['criteria_predecessor'] = criteria_predecessor(root, prepared['predecessor'], prepared['task'])
    prepared['input_sha256'] = c.content_id(prepared)
    production = c.local(root, 'production', exists=False)
    production.mkdir(exist_ok=True)
    target = run_dir(root, run, exists=False)
    if target.exists():
        loaded = load_run(root, run)
        if loaded[1] != prepared:
            raise ValueError('existing revised run differs from the exact preparation')
    else:
        staging = Path(tempfile.mkdtemp(prefix='.pending-', dir=production))
        try:
            for raw in blobs.values():
                c.object_store(staging, raw)
            c.atomic(staging / 'prepared.json', c.encoded(prepared))
            c.atomic(staging / 'consumer.json', c.encoded(consumer))
            (staging / 'records').mkdir()
            c.publish_directory(staging, target)
            c.fsync_dir(production)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    current['production_run'] = run
    work_ledger.write_current(root, current)
    work_ledger.append(root, {'at': work_ledger.now(), 'task_id': current['task_id'],
                             'event': 'note', 'text': 'prepared production run ' + run})
    return {'run': run, 'input_sha256': prepared['input_sha256'], 'consumer': str(target / 'consumer.json')}


def prepare(root: Path, task: str) -> dict:
    root = root.absolute()
    with c.lock(root):
        return _prepare(root, task)


def load_run(root: Path, run: str) -> tuple[Path, dict, dict, list[dict]]:
    directory = run_dir(root, run)
    prepared = c.load(c.local(directory, 'prepared.json'))
    consumer = c.load(c.local(directory, 'consumer.json'))
    check = dict(prepared)
    expected = check.pop('input_sha256', None)
    if c.content_id(check) != expected or c.content_id(consumer) != prepared['consumer_sha256']:
        raise ValueError('prepared input or consumer integrity mismatch')
    for dependency in prepared['dependencies']:
        if dependency['space'] == 'skill':
            continue
        raw = c.object_read(directory, dependency['sha256'])
        if len(raw) != dependency['size']:
            raise ValueError('source snapshot size mismatch')
    records = []
    previous = None
    for path in sorted((directory / 'records').iterdir()):
        if path.name.startswith('.pending-'):
            continue
        if not path.is_file() or path.is_symlink():
            raise ValueError('unexpected receipt path')
        row = c.load(path)
        value = dict(row)
        key = value.pop('sha256', None)
        if c.content_id(value) != key or row.get('previous') != previous or row.get('sequence') != len(records) + 1:
            raise ValueError('receipt chain integrity mismatch')
        if path.name != f'{len(records) + 1:06d}-{key}.json' or row.get('input_sha256') != prepared['input_sha256']:
            raise ValueError('receipt address or input mismatch')
        if row.get('event') not in EVENTS:
            raise ValueError('unknown receipt event')
        records.append(row)
        previous = key
    if prepared.get('predecessor')==run or prepared.get('criteria_predecessor')==run:
        raise ValueError('a production run cannot precede itself')
    lifecycle.completion_tail(records, prepared, run)
    for row in records:
        for item in row['data'].get('files', []) + row['data'].get('evidence', []):
            if len(c.object_read(directory,item['sha256']))!=item['size']:
                raise ValueError('recorded artifact snapshot size mismatch')
    return directory, prepared, consumer, records


def current_sha256(root: Path, dependency: dict) -> str:
    """Hash the current bytes behind one pinned dependency."""
    if dependency['space'] == 'skill':
        return c.file_digest(ROOT, dependency['path'])[0]
    return c.digest(c.read(c.local(root, dependency['path'])))


def assert_current(root: Path, run: str) -> tuple[Path, dict, dict, list[dict]]:
    loaded = load_run(root, run)
    directory, prepared, _, rows = loaded
    import route_reading
    route_reading.require_route_reading(prepared['route_reading'], project=root, routes={prepared['task']['route']}, features=prepared['task']['features'])
    for dependency in prepared['dependencies']:
        if current_sha256(root, dependency) != dependency['sha256']:
            raise ValueError(f'changed {dependency["space"]} input: {dependency["path"]}; prepare a new run')
    for row in rows:
        for item in row['data'].get('files', []) + row['data'].get('evidence', []):
            raw = c.read(c.local(root, item['path']))
            if c.digest(raw) != item['sha256'] or c.object_read(directory, item['sha256']) != raw:
                raise ValueError('changed recorded artifact: ' + item['path'])
    return loaded


def require_mutable(records: list[dict]) -> None:
    if any(row['event'] == 'completion' for row in records):
        raise ValueError('run is complete; prepare a new run for further work')


def append_record(directory: Path, prepared: dict, records: list[dict], event: str, data: dict) -> dict:
    for row in reversed(records):
        if row['event'] == event and row['data'] == data:
            return row
    if event != 'reservation-release':
        require_mutable(records)
    if event not in EVENTS:
        raise ValueError('unknown event')
    row = {'sequence': len(records) + 1, 'previous': records[-1]['sha256'] if records else None,
           'input_sha256': prepared['input_sha256'], 'event': event, 'data': data}
    row['sha256'] = c.content_id(row)
    lifecycle.completion_tail([*records,row],prepared,directory.name)
    c.atomic(directory / 'records' / f'{row["sequence"]:06d}-{row["sha256"]}.json', c.encoded(row))
    return row


def find(records: list[dict], event: str, identifier: str | None = None) -> dict:
    found = [row for row in records if row['event'] == event and (identifier is None or row['sha256'] == identifier)]
    if not found:
        raise ValueError('missing ' + event + ' evidence')
    return found[-1]


def file_record(root: Path, directory: Path, path: str) -> dict:
    raw = c.read(c.local(root, path))
    return {'path': path, 'sha256': c.object_store(directory, raw), 'size': len(raw)}


def run_task(root: Path, run: str) -> str | None:
    """Name the work task of a run whose preparation record is intact, or None."""
    try:
        prepared = c.load(c.local(run_dir(root, run), 'prepared.json'))
        check = dict(prepared)
        expected = check.pop('input_sha256', None)
        if c.content_id(check) != expected:
            return None
        return c.text(prepared['task']['task_id'], 'task_id')
    except (ValueError, OSError, KeyError, TypeError, UnicodeError):
        return None


def reservations(root: Path, task_id: str, *, exclude: str | None = None) -> list[dict]:
    """Collect the unreleased reservations of every run in one work task.

    Entries that are not run directories are skipped, and so is a run whose
    intact preparation names another task. Every other run is loaded in full,
    so damage to a run of this task, or to one that cannot be attributed, fails.
    """
    result = []
    folder = c.local(root, 'production', exists=False)
    if not folder.exists():
        return result
    for child in sorted(folder.iterdir()):
        try:
            run_identifier(child.name)
        except ValueError:
            continue
        owner = run_task(root, child.name)
        if owner is not None and owner != task_id:
            continue
        _, prepared, _, rows = load_run(root, child.name)
        if prepared['task']['task_id'] != task_id:
            continue
        states=lifecycle.derive(rows,prepared,child.name)
        for row in rows:
            if row['event'] == 'authorization' and row['sha256'] != exclude and states[row['sha256']]['status']!='released':
                result.append(row['data']['request'])
    return result


def assert_authority_current(root: Path, prepared: dict) -> None:
    """Edits may change source inputs, but may not reuse revoked authority."""
    paths = {prepared['task']['authority'], prepared['authority']['evidence']['path']}
    for entry in prepared['dependencies']:
        if entry['space'] == 'skill' or entry['path'] in paths:
            if current_sha256(root, entry) != entry['sha256']:
                raise ValueError(f'authority or implementation changed: {entry["path"]}; prepare with current authority')


def authorization_context(root: Path, run: str, operation: str) -> tuple:
    loaded = load_run(root, run) if operation == 'edit' else assert_current(root, run)
    assert_authority_current(root, loaded[1])
    return loaded


def authorize(root: Path, run: str, request_file: str) -> dict:
    with c.lock(root):
        request_bytes = c.read(c.local(root, request_file))
        request = c.decode(request_bytes)
        directory, prepared, _, rows = authorization_context(root, run, request.get('operation'))
        record = file_record(root, directory, request_file)
        if c.object_read(directory, record['sha256']) != request_bytes:
            raise ValueError('authorization changed during reservation')
        schema_check(request, 'authorization')
        files = [record]
        if prepared['task']['execution'] == 'dispatcher' and request['operation'] == 'submit':
            from production_request import check_authorization
            matches = [g for g in prepared['authority']['grants'] if g['id'] == request['grant']]
            if len(matches) != 1:
                raise ValueError('authorization must select one declared grant')
            _, refs = check_authorization(root, prepared, request, matches[0])
            files.extend(file_record(root, directory, ref['path']) for ref in refs if ref['path'] != request_file)
        elif request.get('request_decision') is not None:
            raise ValueError('only a model dispatcher submission carries a model request decision')
        data = {'files': files, 'request': request}
        for row in rows:
            if row['event'] == 'authorization' and row['data'] == data:
                lifecycle.require_active(rows,prepared,run,row['sha256'])
                return row
        require_mutable(rows)
        if any(r['event']=='reservation-release' for r in rows):
            raise ValueError('prepare a new run for authorization after a reservation release')
        grant = permissions.check(prepared['authority'], request, reservations(root, prepared['task']['task_id']))
        if request['operation'] == 'direction':
            validate_protected_criteria(root, prepared, grant)
        return append_record(directory, prepared, rows, 'authorization', data)


def _permission(root: Path, prepared: dict, rows: list[dict], identifier: str,
                operation: str, targets: list[str], payload: dict) -> dict:
    assert_authority_current(root, prepared)
    row = find(rows, 'authorization', identifier)
    if any(r['event']=='reservation-release' and r['data']['reservation']['authorization_sha256']==identifier for r in rows):
        raise ValueError('authorization reservation was released')
    for item in row['data']['files']:
        if c.digest(c.read(c.local(root, item['path']))) != item['sha256']:
            raise ValueError('authorization request changed')
    request = row['data']['request']
    if request['operation'] != operation or set(request['targets']) != set(targets) or request['payload'] != payload:
        raise ValueError('authorization does not match this exact operation')
    grant = permissions.check(prepared['authority'], request,
                              reservations(root, prepared['task']['task_id'], exclude=identifier))
    if operation == 'direction':
        validate_protected_criteria(root, prepared, grant)
    if operation == 'submit' and prepared['task']['execution'] == 'dispatcher':
        from production_request import check_authorization
        check_authorization(root, prepared, request, grant)
    return request


def handoff_intent(root: Path, run: str, recipient: str, method: str) -> dict:
    _, prepared, consumer, _ = assert_current(root, run)
    c.text(recipient, 'recipient')
    if method not in {'conversation', 'manual', 'dispatcher'}:
        raise ValueError('invalid handoff method')
    if (method == 'dispatcher') != (prepared['task']['execution'] == 'dispatcher'):
        raise ValueError('handoff method differs from the declared execution mode')
    return {'operation': 'direction', 'targets': plan.direction_targets(prepared['task']),
            'payload': {'consumer_sha256': c.content_id(consumer), 'recipient': recipient, 'method': method}}


def handoff(root: Path, run: str, recipient: str, method: str, authorization: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        intent = handoff_intent(root, run, recipient, method)
        _permission(root, prepared, rows, authorization, **intent)
        data = {**intent['payload'], 'authorizations': [authorization]}
        prior = [r for r in rows if r['event'] == 'handoff']
        if prior and prior[0]['data'] != data:
            raise ValueError('run already has a different handoff')
        return lifecycle.commit_effect(root,run,'handoff',data,[authorization],effect='external-handoff')


def external_intent(root: Path, run: str, count: int) -> dict:
    _, prepared, consumer, rows = assert_current(root, run)
    if prepared['task']['execution'] != 'external':
        raise ValueError('task is not an external execution')
    hand = find(rows, 'handoff')
    if type(count) is not int or count < 1:
        raise ValueError('positive output count required')
    return {'operation': 'submit', 'targets': ['delivery'],
            'payload': {'consumer_sha256': c.content_id(consumer), 'recipient': hand['data']['recipient'], 'count': count}}


def claim_external(root: Path, run: str, count: int, authorization: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        intent = external_intent(root, run, count)
        request = _permission(root, prepared, rows, authorization, **intent)
        data = {**intent['payload'], 'authorizations': [authorization], 'cost': request['cost']}
        previous = [r for r in rows if r['event'] == 'external-claim']
        if previous and previous[0]['data'] != data:
            raise ValueError('external call already claimed; resolve its outcome before new work')
        return lifecycle.commit_effect(root,run,'external-claim',data,[authorization],effect='external-handoff')


def capture(root: Path, run: str, artifact: str, note: str) -> dict:
    c.text(note, 'candidate provenance')
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        hand = find(rows, 'handoff')
        execution = prepared['task']['execution']
        if execution == 'dispatcher':
            results = find(rows, 'dispatch-results')
            if artifact not in {f['path'] for f in results['data']['files']}:
                raise ValueError('artifact is not a fully acquired dispatch result')
        if execution == 'external':
            claim = find(rows, 'external-claim')
            previous = {f['path'] for r in rows if r['event'] == 'candidate' for f in r['data']['files']}
            if artifact not in previous and len(previous) >= claim['data']['count']:
                raise ValueError('external output count exceeds its authorization')
        item = file_record(root, directory, artifact)
        measured = media.inspect(c.object_read(directory, item['sha256']), prepared['task']['artifact'])
        return append_record(directory, prepared, rows, 'candidate',
                             {'handoff': hand['sha256'], 'files': [item], 'media': measured, 'note': note})


def draft_review(root: Path, run: str, candidate: str) -> dict:
    directory, prepared, _, rows = assert_current(root, run)
    find(rows, 'candidate', candidate)
    from preset_consultation import review_questions
    questions = review_questions(root, prepared['task'], directory=directory, dependencies=prepared['dependencies'])
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate, 'reviewer': '',
            'evidence': [], 'observations': [],
            'checks': [{'criterion': x['id'], 'verdict': 'not-assessed', 'observation_indices': [],
                        'reason': '\n'.join(questions.get(x['id'], []))}
                       for x in prepared['task']['criteria']],
            'repairs': [], 'unresolved': [], 'conclusion': ''}


def validate_review(data: Any, prepared: dict, candidate: dict, raw: bytes,
                    evidence: dict[str, tuple[bytes, dict]] | None = None) -> None:
    schema_check(data, 'review')
    if data['input_sha256'] != prepared['input_sha256'] or data['candidate'] != candidate['sha256']:
        raise ValueError('review belongs to another input or candidate')
    material = {'candidate': (raw, candidate['data']['media']), **(evidence or {})}
    supported = []
    for observation in data['observations']:
        key = observation['evidence']
        if key not in material:
            raise ValueError('observation names missing evidence')
        contents, measured = material[key]
        supported.append(media.locator(observation['locator'], measured, contents))
    expected = {x['id']: x for x in prepared['task']['criteria']}
    seen = set()
    for check in data['checks']:
        if check['criterion'] in seen or check['criterion'] not in expected:
            raise ValueError('unknown or repeated review criterion')
        seen.add(check['criterion'])
        indices = check['observation_indices']
        if len(indices) != len(set(indices)) or any(type(i) is not int or not 0 <= i < len(supported) for i in indices):
            raise ValueError('review check must cite actual observation indices')
        if check['verdict'] in {'pass', 'fail'} and not indices:
            raise ValueError('a judged criterion must cite actual observations')
        requirement = expected[check['criterion']]['evidence']
        if check['verdict'] == 'pass' and not any(requirement in supported[i] for i in indices):
            raise ValueError('evidence medium or range cannot support the claimed pass')
    if seen != set(expected):
        raise ValueError('review must account for every declared criterion')
    decisions = {d['id'] for d in prepared['task']['direction']['decisions']}
    repairs = set()
    for repair in data['repairs']:
        if repair['id'] in repairs:
            raise ValueError('duplicate repair id')
        repairs.add(repair['id'])
        if set(repair['decisions']) - decisions:
            raise ValueError('repair names an unknown decision')
        if any(type(i) is not int or not 0 <= i < len(supported) for i in repair['observation_indices']):
            raise ValueError('repair must identify actual observations')
        plan.strings(repair['targets'], 'repair targets', nonempty=True)
    plan.strings(data['unresolved'], 'unresolved issues')
    if any(check['verdict'] == 'fail' for check in data['checks']) and not data['repairs'] and not data['unresolved']:
        raise ValueError('a failed review needs a concrete repair or unresolved issue')


def review(root: Path, run: str, review_file: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        item = file_record(root, directory, review_file)
        data = c.decode(c.object_read(directory, item['sha256']))
        schema_check(data, 'review')
        candidate = find(rows, 'candidate', data['candidate'])
        supplemental: dict[str, tuple[bytes, dict]] = {}
        records = []
        for spec in data['evidence']:
            if spec['id'] == 'candidate' or spec['id'] in supplemental:
                raise ValueError('duplicate or reserved evidence id')
            evidence_file = file_record(root, directory, spec['path'])
            contents = c.object_read(directory, evidence_file['sha256'])
            supplemental[spec['id']] = (contents, media.inspect(contents, spec['kind']))
            records.append(evidence_file)
        raw = c.object_read(directory, candidate['data']['files'][0]['sha256'])
        validate_review(data, prepared, candidate, raw, supplemental)
        return append_record(directory, prepared, rows, 'review',
                             {'candidate': candidate['sha256'], 'files': [item], 'evidence': records,
                              'media': {k: v[1] for k, v in supplemental.items()}, 'review': data})


def eligible(prepared: dict, reviewed: dict) -> None:
    data = reviewed['data']['review']
    if data['unresolved']:
        raise ValueError('review has unresolved issues')
    hard = {x['id'] for x in prepared['task']['criteria'] if x['strength'] == 'hard'}
    if any(x['criterion'] in hard and x['verdict'] != 'pass' for x in data['checks']):
        raise ValueError('a hard criterion has not passed')


def latest_review(rows: list[dict], candidate: str) -> dict:
    found = [r for r in rows if r['event'] == 'review' and r['data']['candidate'] == candidate]
    if not found:
        raise ValueError('candidate has no recorded review')
    return found[-1]


def draft_selection(root: Path, run: str, candidate: str) -> dict:
    _, prepared, _, rows = assert_current(root, run)
    find(rows, 'candidate', candidate)
    reviewed = latest_review(rows, candidate)
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate, 'review': reviewed['sha256'],
            'selector': '', 'reason': '', 'scope': 'delivery-only', 'adoption': None, 'authorization': ''}


def selection_intent(selection: dict) -> dict:
    # The reason and selecting actor are part of the exact decision, not merely
    # the image id. The authorization reference itself is excluded to avoid a cycle.
    return {'operation': 'select', 'targets': ['delivery'],
            'payload': {k: v for k, v in selection.items() if k != 'authorization'}}


def select(root: Path, run: str, selection_file: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        item = file_record(root, directory, selection_file)
        data = c.decode(c.object_read(directory, item['sha256']))
        schema_check(data, 'selection')
        if data['input_sha256'] != prepared['input_sha256']:
            raise ValueError('selection belongs to another input')
        candidate = find(rows, 'candidate', data['candidate'])
        reviewed = latest_review(rows, data['candidate'])
        if reviewed['sha256'] != data['review']:
            raise ValueError('selection must use the latest review of this candidate')
        eligible(prepared, reviewed)
        request = _permission(root, prepared, rows, data['authorization'], **selection_intent(data))
        if request['actor'] != data['selector']:
            raise ValueError('selector differs from the authorized actor')
        files = [item]
        if data['scope'] == 'delivery-only':
            if data['adoption'] is not None:
                raise ValueError('delivery-only selection cannot claim canonical adoption')
        else:
            if data['adoption'] is None:
                raise ValueError('Studio adoption requires its owned receipt')
            for path in confirm_studio_adoption(root, data['adoption'], candidate['data']['files'][0]['sha256']):
                files.append(file_record(root, directory, path.relative_to(root).as_posix()))
        return lifecycle.commit_effect(root,run,'selection',
            {'files':files,'selection':data,'authorizations':[data['authorization']]},
            [data['authorization']],effect='local-action')


def complete(root: Path, run: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        selection = find(rows, 'selection')
        chosen = selection['data']['selection']
        reviewed = latest_review(rows, chosen['candidate'])
        if reviewed['sha256'] != chosen['review']:
            raise ValueError('selected review is no longer current')
        eligible(prepared, reviewed)
        if chosen['scope'] == 'studio-adoption':
            candidate = find(rows, 'candidate', chosen['candidate'])
            confirm_studio_adoption(root, chosen['adoption'], candidate['data']['files'][0]['sha256'])
        return append_record(directory, prepared, rows, 'completion',
                             {'selection': selection['sha256'], 'candidate': chosen['candidate'],
                              'scope': chosen['scope'], 'task_id': prepared['task']['task_id'], 'run': run,
                              'limitations': [x for ob in reviewed['data']['review']['observations'] for x in ob['limitations']]})


def verify_completion(root: Path, run: str, task_id: str) -> dict:
    _, prepared, _, rows = assert_current(root, run)
    done = find(rows, 'completion')
    if prepared['task']['task_id'] != task_id or done['data']['task_id'] != task_id or done['data']['run'] != run:
        raise ValueError('completion belongs to another task')
    lifecycle.completion_tail(rows,prepared,run)
    if done['data']['selection'] != find(rows, 'selection')['sha256']:
        raise ValueError('completion is not the terminal selected state')
    selected = find(rows, 'selection')['data']['selection']
    reviewed = latest_review(rows, selected['candidate'])
    if reviewed['sha256'] != selected['review']:
        raise ValueError('completion does not use the latest selected review')
    eligible(prepared, reviewed)
    if selected['scope'] == 'studio-adoption':
        candidate = find(rows, 'candidate', selected['candidate'])
        confirm_studio_adoption(root, selected['adoption'], candidate['data']['files'][0]['sha256'])
    return done


def impact(root: Path, run: str) -> dict:
    """Read-only comparison against frozen inputs, including transitive decisions."""
    with c.lock(root):
        try:
            _, prepared, _, rows = load_run(root, run)
        except (ValueError, OSError, KeyError, UnicodeError) as exc:
            return {'ok': False, 'run': run, 'integrity_error': str(exc)}
        changes = []
        records = list(prepared['dependencies'])
        records += [{**f, 'space': 'artifact', 'receipt': row['sha256']}
                    for row in rows for f in row['data'].get('files', []) + row['data'].get('evidence', [])]
        for item in records:
            try:
                actual = current_sha256(root, item)
                if actual == item['sha256']:
                    continue
                changes.append({**item, 'actual_sha256': actual, 'status': 'changed'})
            except (ValueError, OSError) as exc:
                changes.append({**item, 'actual_sha256': None, 'status': 'unavailable', 'reason': str(exc)})
        paths = {x['path'] for x in changes if x['space'] == 'project'}
        sources = {s['id'] for s in prepared['task']['sources'] if s['path'] in paths}
        structural = any(x['space'] == 'skill' for x in changes) or bool(paths - {s['path'] for s in prepared['task']['sources']})
        affected = plan.affected(prepared['task'], sources, all_inputs=structural)
        affected['receipts'] = sorted({x['receipt'] for x in changes if 'receipt' in x})
        return {'ok': not changes, 'run': run, 'changes': changes, 'affected': affected,
                'limits': 'Declared dependencies only; no artistic inference and no automatic edits.'}


def status(root: Path, run: str) -> dict:
    from production_resume import report
    return report(root, run)


def changed_scopes(before: dict, after: dict) -> list[str]:
    """Conservative explicit edit scopes, never inferred aesthetic causality."""
    old, new = before['task'], after['task']
    scopes: set[str] = set()
    old_dependencies = {(x['space'], x['path']): x['sha256'] for x in before['dependencies']}
    new_dependencies = {(x['space'], x['path']): x['sha256'] for x in after['dependencies']}
    def same_file(a: str, b: str) -> bool:
        return a == b and old_dependencies.get(('project', a)) == new_dependencies.get(('project', b))
    if old['delivery'] != new['delivery'] or not same_file(old['delivery']['path'], new['delivery']['path']):
        scopes.add('delivery')
    for field in ('purpose', 'intended_effect', 'basis', 'action_slice', 'limitations'):
        if old['direction'][field] != new['direction'][field]:
            scopes.add('purpose')
    for field, prefix in (('sources', 'source:'), ('criteria', 'criterion:')):
        a = {x['id']: x for x in old[field]}
        b = {x['id']: x for x in new[field]}
        for key in a.keys() | b.keys():
            if a.get(key) != b.get(key) or (field == 'sources' and key in a and key in b and not same_file(a[key]['path'], b[key]['path'])):
                scopes.add(prefix + key)
    a = {x['id']: x for x in old['direction']['decisions']}
    b = {x['id']: x for x in new['direction']['decisions']}
    scopes.update('decision:' + key for key in a.keys() | b.keys() if a.get(key) != b.get(key))
    if old['authority'] != new['authority'] or before['authority'] != after['authority']:
        scopes.add('authority')
    if any(old.get(key) != new.get(key) for key in ('route', 'features', 'artifact', 'execution', 'world_views', 'moment_views', 'scene_materials')):
        scopes.add('execution')
    # Bundled worlds and story contexts may change without a selector changing.
    declared = {x['path'] for x in old['sources'] + new['sources']}
    declared.update((old['delivery']['path'], new['delivery']['path'], before['task_path'], after['task_path'],
                     old['authority'], new['authority'], before['authority']['evidence']['path'], after['authority']['evidence']['path']))
    if any(space == 'project' and path not in declared and old_dependencies.get((space, path)) != new_dependencies.get((space, path))
           for space, path in old_dependencies.keys() | new_dependencies.keys()):
        scopes.add('execution')
    return sorted(scopes)


def revision_intent(root: Path, run: str, task: str, candidate: str, repair: str) -> dict:
    _, prepared, _, rows = load_run(root, run)
    find(rows, 'candidate', candidate)
    reviewed = latest_review(rows, candidate)
    matches = [r for r in reviewed['data']['review']['repairs'] if r['id'] == repair]
    if len(matches) != 1:
        raise ValueError('revision must identify a repair in the latest candidate review')
    revised, _, _, _ = snapshot(root, task)
    if revised['task']['task_id'] != prepared['task']['task_id']:
        raise ValueError('revision must remain within the current work task')
    if revised['task']['production_id'] != prepared['task']['production_id']:
        raise ValueError('a revision preserves its production_id')
    scopes = changed_scopes(prepared, revised)
    if not scopes:
        raise ValueError('repair contains no changed production inputs')
    if set(scopes) - set(matches[0]['targets']):
        raise ValueError('repair changes targets outside its reviewed scope: ' + ', '.join(scopes))
    return {'operation': 'edit', 'targets': scopes,
            'payload': {'parent_run': run, 'candidate': candidate, 'review': reviewed['sha256'],
                        'repair': repair, 'prepared_sha256': c.content_id(revised)}}


def revise(root: Path, run: str, task: str, candidate: str, repair: str, authorization: str) -> dict:
    with c.lock(root):
        # Revised sources may intentionally differ. Read the parent's immutable
        # snapshots, but still verify the candidate and observation evidence used.
        directory, prepared, _, rows = load_run(root, run)
        require_mutable(rows)
        reviewed = latest_review(rows, candidate)
        chosen = find(rows, 'candidate', candidate)
        for row in (reviewed, chosen):
            for item in row['data'].get('files', []) + row['data'].get('evidence', []):
                if c.digest(c.read(c.local(root, item['path']))) != item['sha256']:
                    raise ValueError('revision evidence changed; review the actual artifact again')
        intent = revision_intent(root, run, task, candidate, repair)
        request = _permission(root, prepared, rows, authorization, **intent)
        grant = next(g for g in prepared['authority']['grants'] if g['id'] == request['grant'])
        new_task = c.load(c.local(root, task))
        validate_protected_criteria(root, prepared, grant, revised=new_task)
        existing = [r for r in rows if r['event'] == 'edit' and authorization in r['data']['authorizations']]
        if existing:
            edit = existing[-1]
            if edit['data']['intent'] != intent:
                raise ValueError('edit authorization was already used for different work')
        else:
            edit = lifecycle.commit_effect(root,run,'edit',
                {'intent':intent,'child':generate_uuid7(),'authorizations':[authorization]},[authorization],effect='local-action')
        parent = {**intent['payload'], 'edit': edit['sha256']}
        return _prepare(root, task, parent=parent, identity=edit['data']['child'])


def submission_intent(package: dict, *, rendered: dict, seed: int | None,
                      count: int, offering: dict, service: dict) -> dict:
    from production_request import intent
    return intent(package, rendered, seed=seed, count=count, offering=offering, service=service)


def claim_dispatch(root: Path, run: str, package: dict, verified: dict, journal: Path,
                   intent: dict, authorization: str, *, rendered: dict) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        hand = find(rows, 'handoff')
        if hand['data']['method'] != 'dispatcher' or prepared['task']['execution'] != 'dispatcher':
            raise ValueError('dispatcher handoff required')
        if any(r['event'] == 'dispatch-claim' for r in rows):
            raise ValueError('dispatch already claimed; inspect saved results instead of resending')
        from production_binding import validate_live, validate_upscale_live
        if package.get('artifact_type') == 'upscale-request':
            validate_upscale_live(root, run, package)
        else:
            validate_live(root, run, package)
        if intent.get('operation') != 'submit' or intent.get('targets') != ['delivery']:
            raise ValueError('dispatch requires a submission intent')
        payload = intent['payload']
        import request_contract as rc
        from production_request import validate_payload
        validate_payload(payload)
        if payload['request_contract'] != rc.receipt_projection(rendered):
            raise ValueError('claim differs from the rendered and reviewed request')
        if payload['package_sha256'] != c.content_id(package):
            raise ValueError('submission intent belongs to a different package')
        request = _permission(root, prepared, rows, authorization, **intent)
        relative = journal.absolute().relative_to(root.absolute()).as_posix()
        c.local(root, relative)
        return append_record(directory, prepared, rows, 'dispatch-claim',
                             {'package_sha256': c.content_id(package),
                              **({'upscale_request_sha256': c.content_id(package)}
                                 if package.get('artifact_type') == 'upscale-request' else
                                 {'effective_prompt_sha256': verified['host_forwarding']['effective_prompt_sha256']}),
                              'journal': relative, 'intent': intent, 'count': request['outputs'],
                              'cost': request['cost'], 'authorizations': [authorization]})


def record_dispatch_results(root: Path, run: str, package: dict, journal: Path,
                            result_paths: list[Path], expected_count: int) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = load_run(root, run)
        claim = find(rows, 'dispatch-claim')
        if c.content_id(package) != claim['data']['package_sha256']:
            raise ValueError('dispatch package changed')
        if type(expected_count) is not int or expected_count != claim['data']['count'] or len(result_paths) != expected_count:
            raise ValueError('acquired outputs differ from the authorized count')
        base = journal.absolute().relative_to(root.absolute()).as_posix()
        if base != claim['data']['journal']:
            raise ValueError('wrong dispatch journal')
        files = [file_record(root, directory, path.absolute().relative_to(root.absolute()).as_posix()) for path in result_paths]
        if len({f['path'] for f in files}) != len(files):
            raise ValueError('repeated dispatch output path')
        for item in files:
            media.inspect(c.object_read(directory, item['sha256']), prepared['task']['artifact'])
        import request_contract as rc
        rendered = c.load(journal / 'request-contract.json')
        if rc.receipt_projection(rendered) != claim['data']['intent']['payload']['request_contract']:
            raise ValueError('recorded request differs from the dispatch claim')
        media_ids = {}
        for index, item in enumerate(rendered['media']):
            upload = c.load(journal / f'upload-{index + 1:03d}.json')
            if upload.get('index') != index or upload.get('source_sha256') != item['sha256']:
                raise ValueError('upload receipt differs from the sealed input bytes')
            media_ids[index] = upload['provider_id']
        rc.validate_wire(rendered, c.load(journal / 'request.json'), media_ids)
        evidence = [file_record(root, directory, base + '/' + name)
                    for name in ('package.json', 'request-contract.json', 'request.json', 'answer.json')]
        evidence.extend(file_record(root, directory, base + f'/upload-{index + 1:03d}.json')
                        for index in range(len(rendered['media'])))
        if package.get('artifact_type') == 'upscale-request':
            if expected_count != 1:
                raise ValueError('one declared upscale permits exactly one result')
            from upscale_package import verify_upscale_package
            generated = c.load(journal / 'upscale-package-1.json')
            verify_upscale_package(generated, package_root=journal)
            if (generated['source_image']['sha256'] != package['source']['sha256']
                    or generated['output_image']['sha256'] != files[0]['sha256']
                    or generated['upscaler_model'] != package['model']
                    or generated['scale_factor'] != package['scale_factor']
                    or generated['settings'] != package['settings']
                    or generated['guidance_prompt'] != (package['guidance_prompt'].strip() if package['guidance_prompt'] else None)):
                raise ValueError('upscale result package differs from the authorized operation or acquired output')
            evidence.append(file_record(root, directory, base + '/upscale-package-1.json'))
        evidence.extend(file_record(root, directory, base + f'/response-{i + 1}.json') for i in range(expected_count))
        return append_record(directory, prepared, rows, 'dispatch-results',
                             {'claim': claim['sha256'], 'files': files, 'evidence': evidence, 'expected_count': expected_count})


def confirm_studio_adoption(root: Path, selector: dict[str,Any], target: str) -> list[Path]:
    import studio
    import adoption_workflow
    c.exact(selector,{'character','iteration_id','scope'},'Studio adoption selector')
    for value in selector.values(): c.text(value,'adoption field')
    home=studio.character_dir(root,selector['character'])
    owner_path=home/'adoptions'/f"{selector['iteration_id']}.json"
    owner=c.load(c.local(root,owner_path.relative_to(root).as_posix()))
    row=studio._find(studio.read_iterations(home),selector['iteration_id'])
    approval=adoption_workflow.validate_approval(owner['approval'],selector['character'],row)
    if approval['image_sha256']!=target or approval['scope']!=selector['scope'] or owner.get('next_action') or row['status']!='accepted':
        raise ValueError('Studio adoption is incomplete or targets a different image')
    reference=adoption_workflow.reference_index(root,selector['character'])
    if not reference['ok'] or not any(x['iteration_id']==selector['iteration_id'] and x['image_sha256']==target for x in reference['bindings']):
        raise ValueError('Studio reference index does not confirm the chosen image')
    paths=[owner_path,home/'iterations.jsonl',home/'sheet/sheet-data.json',c.local(root,row['result']['path'])]
    # Bind owned copies and the chosen binding sidecars as well as the journal.
    for field in ('result','package','request','response'):
        item=row.get(field)
        if item:
            path=c.local(root,item['path'])
            if c.digest(c.read(path))!=item['sha256']: raise ValueError('Studio evidence changed')
            paths.append(path)
    if row.get('accepted_path'): paths.append(c.local(root,row['accepted_path']))
    binding=home/'sheet'/'bindings'/selector['iteration_id']
    if binding.is_dir(): paths.extend(p for p in binding.rglob('*') if p.is_file() or p.is_symlink())
    return sorted(set(paths))



def recover_recording(root: Path, run: str) -> dict[str,Any]:
    """Finish recording a claimed dispatch from its saved answer; nothing is sent again.

    Images the answer names but the journal lacks are downloaded first. Studio
    bookkeeping is then restored only from completely acquired, pinned results.
    """
    import studio
    with c.lock(root):
        _,_,_,rows=load_run(root,run); claim=find(rows,'dispatch-claim')
        acquired=any(r['event']=='dispatch-results' and r['data'].get('claim')==claim['sha256'] for r in rows)
    downloads=0
    if not acquired:
        import dispatch
        downloads=dispatch.recover(root,run,c.local(root,claim['data']['journal']))
    with c.lock(root):
        directory,p,_,rows=load_run(root,run); claim=find(rows,'dispatch-claim'); result=find(rows,'dispatch-results')
        for item in result['data']['evidence']:
            if c.digest(c.read(c.local(root,item['path'])))!=item['sha256']:
                raise ValueError('dispatch evidence changed; cannot recover recording')
        journal=c.local(root,claim['data']['journal']); info=c.load(journal/'run.json')
        if info.get('operation') not in {'generation', 'upscale'}: raise ValueError('unsupported dispatch journal')
        package=c.load(journal/'package.json')
        if c.content_id(package)!=claim['data']['package_sha256']: raise ValueError('recovery package mismatch')
        if info['operation'] == 'generation':
            from build_generation_payload import validate_generation_package_carrier_paths
            from verify_generation_payload import verify_content
            verify_content(package,package_root=journal)
            companion=validate_generation_package_carrier_paths(package['prepared_reference_set'],package_root=journal)
            recorded_package = journal / 'package.json'
        else:
            from upscale_package import verify_upscale_package
            if len(result['data']['files']) != 1:
                raise ValueError('upscale recovery requires exactly one acquired output')
            recorded_package = journal / 'upscale-package-1.json'
            verify_upscale_package(c.load(recorded_package), package_root=journal)
            companion = 'upscale.references'
        # Match by exact request/result identity using the existing Studio index.
        ids=[]
        home=studio.character_dir(root,info['character'])
        with studio.recording_lock(root):
            existing=studio.read_iterations(home)
            request_sha=c.digest(c.read(journal/'request.json'))
            for index,item in enumerate(result['data']['files']):
                response=journal/f'response-{index+1}.json'
                response_sha=c.digest(c.read(response))
                found=[r for r in existing if (r.get('result') or {}).get('sha256')==item['sha256']
                       and (r.get('request') or {}).get('sha256')==request_sha
                       and (r.get('response') or {}).get('sha256')==response_sha
                       and r['character']==info['character'] and r['slot']==info['slot']]
                if len(found)>1: raise ValueError('ambiguous existing Studio result; review manually')
                if found:
                    for key in ('result','request','response','package'):
                        artifact=found[0][key]
                        if c.digest(c.read(c.local(root,artifact['path'])))!=artifact['sha256']:
                            raise ValueError('existing Studio artifact changed')
                    ids.append(found[0]['iteration_id']); continue
                row=studio._record_iteration(root,info['character'],info['slot'],c.local(root,item['path']),package=recorded_package,
                    request=journal/'request.json',response=response,note='Recovered from the saved dispatch; nothing was sent again.',
                    service=info.get('offering'),package_companion=(journal/companion) if companion else None,
                    layout=c.load(journal/'request-contract.json')['layout'])
                existing.append(row); ids.append(row['iteration_id'])
            studio.write_gallery(root)
        info.update(status='complete',iterations=ids)
        c.atomic(journal/'run.json',c.encoded(info),replace=True)
        return {'ok':True,'iterations':ids,'network_calls':downloads}



def adoption_intent(root: Path, run: str, candidate: str, character: str, iteration: str,
                    approval: dict, *, registration_record: dict | None = None,
                    pack_dir: Path | None = None) -> dict:
    _, _, _, rows = assert_current(root, run)
    chosen = find(rows, 'candidate', candidate)
    reviewed = latest_review(rows, candidate)
    from adoption_workflow import validate_approval
    import studio
    row = studio._find(studio.read_iterations(studio.character_dir(root, character)), iteration)
    validate_approval(approval, character, row)
    if row['result']['sha256'] != chosen['data']['files'][0]['sha256']:
        raise ValueError('adoption targets a different candidate')
    return {'operation': 'adopt', 'targets': ['canon:' + approval['scope']],
            'payload': {'candidate': candidate, 'review': reviewed['sha256'],
                        'character': character, 'iteration': iteration,
                        'approval_sha256': c.content_id(approval),
                        'registration_sha256': c.content_id(registration_record) if registration_record else None,
                        'pack_dir': str(pack_dir.absolute()) if pack_dir is not None else None}}


def adopt(root: Path, run: str, candidate: str, character: str, iteration: str,
          approval_file: str, authorization: str, *, registration_record: dict | None = None,
          pack_dir: Path | None = None, settings: Any = None) -> dict:
    """Invoke the owning adoption operation under a separate exact grant.

    A failed mutation is never interpreted as permission for a new one. The
    owner's durable adoption journal resumes the same already-claimed operation.
    """
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        item = file_record(root, directory, approval_file)
        approval = c.decode(c.object_read(directory, item['sha256']))
        intent = adoption_intent(root, run, candidate, character, iteration, approval,
                                 registration_record=registration_record, pack_dir=pack_dir)
        reviewed = latest_review(rows, candidate)
        eligible(prepared, reviewed)
        request = _permission(root, prepared, rows, authorization, **intent)
        if request['actor'] != approval['by']:
            raise ValueError('adoption approver differs from the authorized actor')
        data = {'intent': intent, 'files': [item], 'authorizations': [authorization]}
        prior = [r for r in rows if r['event'] == 'adoption-claim' and authorization in r['data']['authorizations']]
        if prior and prior[0]['data'] != data:
            raise ValueError('adoption authorization is already used for different work')
        claim = append_record(directory, prepared, rows, 'adoption-claim', data)
        if not prior:
            rows.append(claim)
        completed = [r for r in rows if r['event'] == 'adoption-result' and r['data']['claim'] == claim['sha256']]
        if completed:
            return completed[-1]
        if not prior:
            lifecycle.begin(root,run,authorization,effect='local-action',claim=claim['sha256'])
        elif lifecycle.require_active(rows,prepared,run,authorization)['status']!='started':
            lifecycle.begin(root,run,authorization,effect='local-action',claim=claim['sha256'])
        directory,prepared,_,rows=load_run(root,run)
        import adoption_workflow
        result = adoption_workflow.adopt(root, character, iteration, approval,
                                        registration_record=registration_record, pack_dir=pack_dir, settings=settings)
        return append_record(directory, prepared, rows, 'adoption-result',
                             {'claim': claim['sha256'], 'result': result})


def draft_authorization(root: Path, run: str, grant_id: str, intent: dict) -> dict:
    _, prepared, _, _ = authorization_context(root, run, intent.get('operation'))
    matches = [g for g in prepared['authority']['grants'] if g['id'] == grant_id]
    if len(matches) != 1:
        raise ValueError('unknown grant id')
    c.exact(intent, {'operation', 'targets', 'payload'}, 'operation intent')
    result = {'grant': grant_id, 'actor': matches[0]['actor'], **intent,
            'outputs': intent['payload'].get('count', 0) if intent['operation'] == 'submit' else 0,
            'cost': None, 'reason': '',
            'stop_assessments': [{'id': s['id'], 'clear': False, 'evidence': ''}
                                 for s in prepared['authority']['stop_conditions']]}
    if intent['operation'] == 'submit' and prepared['task']['execution'] == 'dispatcher':
        from production_request import draft_decision, validate_payload
        validate_payload(intent['payload'])
        result['request_decision'] = draft_decision(intent['payload']['request_contract'], actor=result['actor'])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    import production_inputs
    production_inputs.add_arguments(sub)
    import preset_consultation
    preset_consultation.add_arguments(sub)
    import production_variation
    production_variation.add_arguments(sub)
    sub.add_parser('new-production-id', help='Assign an explicit stable identity to a new production series.')
    commands = ['prepare', 'handoff-intent', 'handoff', 'external-intent', 'claim-external',
                'draft-authorization', 'authorize', 'capture', 'draft-review', 'review',
                'draft-selection', 'selection-intent', 'select', 'revision-intent', 'revise',
                'adoption-intent', 'adopt', 'complete', 'status', 'impact', 'resume', 'recover-recording',
                'release-reservation','draft-release']
    for name in commands:
        p = sub.add_parser(name)
        p.add_argument('--root', type=Path, required=True)
        if name != 'prepare':
            p.add_argument('--run', required=True)
        if name=='release-reservation':p.add_argument('--request',required=True)
        if name=='draft-release':
            p.add_argument('--reservation',required=True)
            p.add_argument('--out',required=True)
        if name in {'prepare', 'revision-intent', 'revise'}:
            p.add_argument('--task', required=True)
        if name in {'handoff', 'handoff-intent'}:
            p.add_argument('--recipient', required=True)
            p.add_argument('--method', required=True, choices=['conversation', 'manual', 'dispatcher'])
        if name in {'handoff', 'claim-external', 'revise', 'adopt'}:
            p.add_argument('--authorization', required=True)
        if name in {'external-intent', 'claim-external'}:
            p.add_argument('--count', type=int, required=True)
        if name in {'draft-review', 'draft-selection', 'revision-intent', 'revise', 'adopt', 'adoption-intent'}:
            p.add_argument('--candidate', required=True)
        if name in {'draft-review', 'draft-selection', 'draft-authorization'}:
            p.add_argument('--out', required=True)
        if name in {'authorize', 'review', 'select', 'selection-intent'}:
            p.add_argument('--file', required=True)
        if name == 'capture':
            p.add_argument('--artifact', required=True)
            p.add_argument('--note', required=True)
        if name == 'draft-authorization':
            p.add_argument('--grant', required=True)
            p.add_argument('--intent', required=True)
        if name in {'revision-intent', 'revise'}:
            p.add_argument('--repair', required=True)
        if name in {'adopt', 'adoption-intent'}:
            p.add_argument('--character', required=True)
            p.add_argument('--iteration', required=True)
            p.add_argument('--approval', required=True)
            p.add_argument('--registration-record')
            p.add_argument('--pack-dir', type=Path)
            from pack_runtime_cli import add_pack_runtime_arguments
            add_pack_runtime_arguments(p)
    args = parser.parse_args()
    if args.command == 'new-production-id':
        print(json.dumps({'production_id': generate_uuid7()}))
        return 0
    # Resolve once, so a symbolic link above the project (macOS /tmp) is not
    # mistaken for one inside it. Links inside the project are still refused.
    args.root = root = args.root.resolve()
    try:
        name = args.command
        if name in preset_consultation.COMMANDS:
            result = preset_consultation.command(args, parser)
        elif name == 'draft-variation':
            result = production_variation.command(args, parser)
        elif name in production_inputs.COMMANDS:
            result = production_inputs.command(args, parser)
        elif name=='release-reservation':
            result=lifecycle.release(root,args.run,args.request)
        elif name=='draft-release':
            result=lifecycle.draft_release(root,args.run,args.reservation)
            c.atomic(c.local(root,args.out,exists=False),c.encoded(result))
        elif name == 'prepare':
            result = prepare(root, args.task)
        elif name == 'handoff-intent':
            result = handoff_intent(root, args.run, args.recipient, args.method)
        elif name == 'handoff':
            result = handoff(root, args.run, args.recipient, args.method, args.authorization)
        elif name == 'external-intent':
            result = external_intent(root, args.run, args.count)
        elif name == 'claim-external':
            result = claim_external(root, args.run, args.count, args.authorization)
        elif name == 'draft-authorization':
            result = draft_authorization(root, args.run, args.grant, c.load(c.local(root, args.intent)))
            c.atomic(c.local(root, args.out, exists=False), c.encoded(result))
        elif name == 'authorize':
            result = authorize(root, args.run, args.file)
        elif name == 'capture':
            result = capture(root, args.run, args.artifact, args.note)
        elif name in {'draft-review', 'draft-selection'}:
            function = draft_review if name == 'draft-review' else draft_selection
            result = function(root, args.run, args.candidate)
            c.atomic(c.local(root, args.out, exists=False), c.encoded(result))
        elif name == 'review':
            result = review(root, args.run, args.file)
        elif name == 'selection-intent':
            result = selection_intent(c.load(c.local(root, args.file)))
        elif name == 'select':
            result = select(root, args.run, args.file)
        elif name == 'revision-intent':
            result = revision_intent(root, args.run, args.task, args.candidate, args.repair)
        elif name == 'revise':
            result = revise(root, args.run, args.task, args.candidate, args.repair, args.authorization)
        elif name in {'adopt', 'adoption-intent'}:
            approval = c.load(c.local(root, args.approval))
            registration = c.load(c.local(root, args.registration_record)) if args.registration_record else None
            if name == 'adoption-intent':
                result = adoption_intent(root, args.run, args.candidate, args.character, args.iteration, approval,
                                         registration_record=registration, pack_dir=args.pack_dir)
            else:
                from pack_runtime_cli import resolve_pack_runtime
                runtime = resolve_pack_runtime(parser, args) if approval['scope'] == 'catalog' else None
                result = adopt(root, args.run, args.candidate, args.character, args.iteration, args.approval, args.authorization,
                               registration_record=registration, pack_dir=args.pack_dir, settings=runtime.settings if runtime else None)
        elif name == 'complete':
            result = complete(root, args.run)
        elif name == 'recover-recording':
            result = recover_recording(root, args.run)
        elif name == 'impact':
            result = impact(root, args.run)
        else:
            result = status(root, args.run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok', True) else 1
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
