#!/usr/bin/env python3
"""Prepare, authorize, execute, observe, revise and complete a production task.

Every operation uses the current authored contract. Planning and observation do
not establish consent. Only explicit, scoped grants authorize actions; hashes
prove consistency of recorded bytes, never artistic success or user identity.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError, compare_exact
import reservation_lifecycle as lifecycle
import execution_routes
from pack_manager import generate_uuid7
import production_evidence as media
import production_permissions as permissions
import production_plan as plan

ROOT = Path(__file__).resolve().parents[1]
EVENTS = {'authorization', 'handoff', 'external-claim', 'dispatch-claim',
          'dispatch-results', 'candidate', 'review', 'selection', 'edit',
          'adoption-claim', 'adoption-result', 'image-edit-claim', 'image-edit-output', 'completion',
          'disposition', 'handoff-ready', 'capture-status', 'execution-outcome', 'abandoned'} | lifecycle.EVENTS


def run_identifier(run: Any) -> str:
    try:
        identifier = uuid.UUID(run)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError('run must be a UUIDv7') from exc
    if identifier.version != 7 or str(identifier) != run:
        raise ValueError('run must be a canonical UUIDv7')
    return run


def run_dir(root: Path, run: str, *, exists: bool = True) -> Path:
    return c.local(root, 'production/runs/' + run_identifier(run), exists=exists)


def schema_check(value: Any, name: str) -> None:
    from state_protocol import validate_against_schema
    schema = c.load(ROOT / f'schemas/authoring/production-{name}.schema.json')
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('production ' + name + ': ' + '; '.join(errors))


def validate_task(task: Any) -> dict:
    if isinstance(task, dict):
        production_identifier(task.get('production_id'))
    schema_check(task, 'task')
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


def world_views(root: Path, task: dict, add) -> list[dict]:
    """The selected compiled world views, each verified against its current bundle."""
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
    return views


def moment_views(root: Path, task: dict, add) -> list[dict]:
    """The selected story moment views, each with its query and sources unchanged."""
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
    return moments


def authoring_materials(root: Path, task: dict, add) -> list[dict]:
    """The accepted scene and persona material in its declared scope."""
    import scene_persona
    return scene_persona.consume(root, task.get('scene_materials', []), add, task['artifact'])


# Entry modules of compile and execute; the implementation pinned by a run is what they import.
ENTRY_MODULES = ('production_workflow', 'production_compiler', 'production_execution')
_IMPORTS: dict[tuple[str, int, int], tuple[set[str], set[str]]] = {}


def _module_files(scripts: Path, name: str) -> list[Path]:
    """The files that importing `name` from the scripts directory loads."""
    parts = name.split('.')
    found = []
    for index in range(1, len(parts) + 1):
        base = scripts.joinpath(*parts[:index])
        if (base / '__init__.py').is_file():
            found.append(base / '__init__.py')
        elif index == len(parts) and base.with_suffix('.py').is_file():
            found.append(base.with_suffix('.py'))
        elif not base.is_dir():
            break
    return found


def _imports(path: Path, package: str) -> tuple[set[str], set[str]]:
    """Module names a source file imports, and the string literals it contains."""
    import ast
    info = path.stat()
    key = (str(path), info.st_mtime_ns, info.st_size)
    if key not in _IMPORTS:
        tree = ast.parse(c.read(path).decode('utf-8'))
        names, literals = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parent = package.split('.')[:len(package.split('.')) - node.level + 1] if package else []
                    base = '.'.join([*parent, *([base] if base else [])])
                if base:
                    names.add(base)
                names.update(f'{base}.{alias.name}' if base else alias.name for alias in node.names)
            elif isinstance(node, ast.Call) and getattr(node.func, 'attr', getattr(node.func, 'id', None)) == 'import_module':
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    names.add(node.args[0].value)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.add(node.value)
        _IMPORTS[key] = (names, literals)
    return _IMPORTS[key]


IMPLEMENTATION_INDEX = 'config/implementation-files.json'


def implementation_files() -> list[str]:
    """The installed files a prepared run depends on, relative to the Skill directory.

    `scripts/rebuild_metadata.py` writes the list from `implementation_closure`
    into `config/implementation-files.json` with the digest of each module it
    read, so a preparation reads one file instead of parsing every module
    again. The index is part of the list. An index is stale, and refused, when
    a listed module changed since it was written, because a changed module may
    import other files, or when the schema directory holds other files.
    """
    try:
        value = c.load(ROOT / IMPLEMENTATION_INDEX)
        files = value['files']
        sources = value['sources']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f'{IMPLEMENTATION_INDEX} is missing or invalid; run scripts/rebuild_metadata.py') from exc
    if (not isinstance(files, list) or any(not isinstance(item, str) or not item for item in files)
            or not isinstance(sources, dict)
            or any(not isinstance(key, str) or not isinstance(digest, str) for key, digest in sources.items())):
        raise ValueError(f'{IMPLEMENTATION_INDEX} must list file paths and module digests; run scripts/rebuild_metadata.py')
    if sorted(sources) != sorted(path for path in files if path.endswith('.py')):
        raise ValueError(f'{IMPLEMENTATION_INDEX} does not record a digest for each listed module; run scripts/rebuild_metadata.py')
    rebuild = 'Run scripts/rebuild_metadata.py so the index matches the installation, then prepare again.'
    for path, expected in sorted(sources.items()):
        try:
            actual = c.file_digest(ROOT, path)[0]
        except (OSError, ValueError):
            actual = None
        if actual != expected:
            raise ProductionError('IMPLEMENTATION_CHANGED',
                                  f'A module of the installed implementation differs from {IMPLEMENTATION_INDEX}.',
                                  phase='implementation', file=path, expected=expected, actual=actual, required_action=rebuild)
    for parent in ('schemas', 'protocols'):
        listed = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / parent).rglob('*.json'))
        if listed != [path for path in files if path.startswith(parent + '/')]:
            raise ProductionError('IMPLEMENTATION_CHANGED',
                                  f'The {parent} directory differs from the files {IMPLEMENTATION_INDEX} lists for it.',
                                  phase='implementation', file=parent, required_action=rebuild)
    return sorted(set(files) | {IMPLEMENTATION_INDEX})


def implementation_closure() -> list[str]:
    """Compute the implementation list from the source: the modules that compile
    and execute import, the schemas, the data files those modules name, and the
    route manifest. Tests, smoke tests and release metadata are left out.
    """
    scripts = ROOT / 'scripts'
    pending = list(ENTRY_MODULES)
    modules, literals = set(), set()
    while pending:
        name = pending.pop()
        for path in _module_files(scripts, name):
            relative = path.relative_to(ROOT).as_posix()
            if relative in modules or path.name.startswith('test_') or path.name.endswith('_smoke_test.py'):
                continue
            modules.add(relative)
            # The package a relative import starts from: the directory holding the file.
            package = '.'.join(path.relative_to(scripts).with_suffix('').parts[:-1])
            found, strings = _imports(path, package)
            literals.update(strings)
            pending.extend(found)
    files = set(modules) | {execution_routes.MANIFEST, IMPLEMENTATION_INDEX}
    # Validators choose schema files by computed names, so every schema and every
    # protocol record is part of the implementation.
    for parent in ('schemas', 'protocols'):
        files.update(f.relative_to(ROOT).as_posix() for f in (ROOT / parent).rglob('*.json'))
    files.update(f.relative_to(ROOT).as_posix() for f in scripts.glob('*.json') if f.name in literals)
    return sorted(files)


def freshness_error(dependency: dict, actual: str | None, *, run: str | None, phase: str = 'freshness') -> ProductionError:
    """A pinned file that changed or disappeared: the installed implementation, or a creative source."""
    if dependency['space'] == 'skill':
        return ProductionError('IMPLEMENTATION_CHANGED',
            'The installed implementation changed after preparation.' if actual is not None
            else 'A file of the installed implementation is unavailable.',
            phase='implementation', file=dependency['path'], run=run, expected=dependency['sha256'], actual=actual,
            required_action='Prepare the task again with the current installation; the creative input is unchanged.')
    if actual is None:
        return ProductionError('SOURCE_CHANGED', 'A live creative source is unavailable.', phase=phase,
                               file=dependency['path'], run=run, expected=dependency['sha256'], actual=None)
    return ProductionError('SOURCE_CHANGED', 'A live creative source changed after preparation.', phase=phase,
                           file=dependency['path'], run=run, expected=dependency['sha256'], actual=actual,
                           required_action='Review the source change and prepare a variant for the current creative scope.')


def snapshot(root: Path, task_path: str, *, captured: dict[str, bytes] | None = None,
             checked: dict | None = None) -> tuple[dict, dict, list[dict], dict[str, bytes]]:
    """Capture the task and everything it depends on as one immutable input.

    `captured` holds bytes already read in this compilation, by studio path,
    so each file is read once. `checked` holds results of the compiler's input
    checks (task contract, route reading, bounded views and scene material),
    which are reused instead of being computed again.
    """
    from production_compiler import GENERATION_FILES, dependency_space
    captured = {} if captured is None else captured
    checked = checked or {}
    def read(base: Path, path: str) -> bytes:
        if Path(base) == root and path in captured:
            return captured[path]
        raw = store.stable_bytes(base, path)
        if Path(base) == root:
            captured[path] = raw
        return raw
    task_bytes = read(root, task_path)
    task = c.decode(task_bytes)
    route = checked['task-contract'] if 'task-contract' in checked else validate_task(task)
    dependencies: dict[tuple[str, str], dict] = {}
    blobs: dict[str, bytes] = {}
    def record(space: str, path: str, raw: bytes) -> None:
        if space == 'studio':
            space = dependency_space(path)
        key = c.digest(raw)
        dependencies[(space, path)] = {'space': space, 'path': path, 'sha256': key, 'size': len(raw)}
        blobs[key] = raw
    def add(base: Path, path: str, space: str = 'studio') -> bytes:
        raw = read(base, path)
        record(space, path, raw)
        return raw
    add(root, task_path, 'task-source')
    import route_reading
    reading = c.decode(add(root, task['route_reading']))
    if 'route-reading' in checked:
        issuance = checked['route-reading']
    else:
        issuance = route_reading.require_route_reading(reading, studio=root, routes={task['route']}, features=task['features'])
    for source in task['sources']:
        add(root, source['path'])
    delivery = add(root, task['delivery']['path']).decode('utf-8')
    c.text(delivery, 'delivery')
    authority = store.authority(root, task['task_id'], required=False)
    authority_event = store.authority_record(root, task['task_id'])
    if authority_event is not None:
        for item in authority_event['data']['evidence']:
            raw = store.verify_evidence(root, item, event=authority_event['sha256'])
            key = c.digest(raw)
            dependencies[('evidence',item['path'])] = {'space':'evidence','path':item['path'],'sha256':key,'size':len(raw)}
            blobs[key] = raw
    elif task.get('authority') is not None:
        authority = c.decode(add(root, task['authority'], 'evidence'))
        schema_check(authority, 'authority')
        permissions.validate(authority, task['task_id'])
        add(root, authority['evidence']['path'], 'evidence')
        from input_evidence import InputEvidence
        import request_scope
        scope_reader = InputEvidence(root)
        for grant in authority['grants']:
            request_scope.verify_sources(grant['request_scope'], None, scope_reader)
        # Pin the scope bytes the verifier read, not a second reading of the files.
        for path in sorted(scope_reader.read_paths):
            raw = InputEvidence._decode(scope_reader.snapshots[path])
            key = c.digest(raw)
            dependencies[('evidence', path)] = {'space': 'evidence', 'path': path, 'sha256': key, 'size': len(raw)}
            blobs[key] = raw
    if authority is not None:
        known_criteria = {x['id'] for x in task['criteria']}
        for grant in authority['grants']:
            if set(grant['protected_criteria']) - known_criteria:
                raise ValueError('grant protects an undeclared criterion')
    generation = task.get('generation')
    if generation is not None:
        for field in GENERATION_FILES:
            if generation.get(field) is not None:
                add(root,generation[field])
    def bounded(name: str, function):
        # The compiler's check already read these files; record exactly what it read.
        if name in checked:
            value, reads = checked[name]
            for (space, path), raw in reads.items():
                record(space, path, raw)
            return value
        return function(root, task, add)
    views = bounded('world-views', world_views)
    moments = bounded('moment-views', moment_views)
    materials = bounded('scene-materials', authoring_materials)
    # The installed implementation is pinned by digest; its bytes stay in the installation.
    skill_files = set(implementation_files()) | {r['path'] for r in route['reads']}
    for path in sorted(skill_files):
        key, size = c.file_digest(ROOT, path)
        dependencies[('skill', path)] = {'space': 'skill', 'path': path, 'sha256': key, 'size': size}
    consumer = {'route': task['route'], 'transport': task['delivery']['transport'],
                'instructions': delivery, 'criteria': task['criteria'],
                'direction': plan.consumer(task['direction']),
                'world_views': views, 'moment_views': moments, 'authoring_materials': materials}
    prepared = {'task_path': task_path, 'task': task, 'route': route, 'authority': authority,
                'route_reading': reading, 'route_reading_sha256': c.content_id(reading), 'reading_issuance': issuance,
                'dependencies': sorted(dependencies.values(), key=lambda x: (x['space'], x['path'])),
                'consumer_sha256': c.content_id(consumer)}
    return prepared, consumer, prepared['dependencies'], blobs


def production_identifier(value: Any) -> str:
    """The series a preparation belongs to, which decides the run its protected criteria are compared with."""
    try:
        identifier = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        identifier = None
    if identifier is None or identifier.version != 7 or str(identifier) != value:
        raise ValueError('production_id must be a UUIDv7: copy the one '
                         '`python scripts/production_workflow.py new-production-id` prints, '
                         'or keep the id of the series this task continues')
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
    """Compile one task and publish only its complete, verified result."""
    from production_compiler import prepare_task
    return prepare_task(c._root(root), task_path, parent=parent, identity=identity)


def prepare(root: Path, task: str) -> dict:
    return _prepare(c._root(root), task)


def validate_run_content(run: str, prepared: dict, consumer: dict, rows: list[dict], read_object, *,
                         verified: dict[str, int] | None = None) -> None:
    """Validate immutable run content from storage or a read-only evidence export.

    This does not register a run, recreate authorizations or consult live sources.
    The caller separately verifies the publication and its registered envelope.
    `verified` maps each object digest the caller already checked, such as the
    objects of the publication manifest it just verified, to its size. Each
    object read and checked here is added to it.
    """
    known = {} if verified is None else verified
    run_identifier(run)
    check = dict(prepared)
    expected = check.pop('envelope_sha256', None)
    if prepared.get('run') != run or c.content_id(check) != expected:
        raise ProductionError('INPUT_SNAPSHOT_CORRUPT', 'The run envelope differs from its digest or run.',
                              phase='integrity', run=run, file='prepared.json', expected=expected,
                              impact=store.RUN_EVIDENCE_IMPACT, required_action=store.RESTORE_EVIDENCE)
    if c.content_id(consumer) != prepared['consumer_sha256']:
        raise ProductionError('INPUT_SNAPSHOT_CORRUPT', 'The consumer snapshot differs from its digest.',
                              phase='integrity', run=run, file='consumer.json', expected=prepared['consumer_sha256'],
                              actual=c.content_id(consumer), impact=store.RUN_EVIDENCE_IMPACT, required_action=store.RESTORE_EVIDENCE)
    from production_compiler import input_digest
    if input_digest(prepared, consumer) != prepared['input_sha256']:
        raise ProductionError('INPUT_SNAPSHOT_CORRUPT', 'The creative input digest differs.', phase='integrity', run=run,
                              expected=prepared['input_sha256'], impact=store.RUN_EVIDENCE_IMPACT, required_action=store.RESTORE_EVIDENCE)
    for dependency in prepared['dependencies']:
        if dependency['space'] == 'skill':
            continue
        key = dependency['sha256']
        if known.get(key) == dependency['size']:
            continue
        try:
            raw = read_object(key)
        except (ValueError, OSError, KeyError) as exc:
            raise store.evidence_error('EVIDENCE_SNAPSHOT_MISSING', 'A stored source snapshot is unavailable or corrupt.',
                                       file=dependency['path'], run=run, expected=key, space=dependency['space'],
                                       artifact='objects/' + key) from exc
        if c.digest(raw) != key or len(raw) != dependency['size']:
            raise store.evidence_error('EVIDENCE_SNAPSHOT_CORRUPT', 'Source snapshot size or digest differs.',
                                       file=dependency['path'], run=run, expected=key, actual=c.digest(raw),
                                       space=dependency['space'], artifact='objects/' + key)
        known[key] = len(raw)
    store.validate_event_chain(rows, run)
    for row in rows:
        if row['input_sha256'] != prepared['input_sha256'] or row['event'] not in EVENTS:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'An event belongs to another input or has an undeclared kind.',
                                  phase='integrity', run=run, event=row['sha256'], impact=store.RUN_EVIDENCE_IMPACT,
                                  required_action='Restore the exact committed event from verified evidence; do not recreate approval.')
        for item in row['data'].get('files', []) + row['data'].get('evidence', []):
            if known.get(item['sha256']) == item['size']:
                continue
            try:
                raw = read_object(item['sha256'])
            except (ValueError, OSError, KeyError) as exc:
                raise store.evidence_error('EVIDENCE_SNAPSHOT_MISSING', 'Event evidence cannot be read.',
                                           file=item['path'], run=run, event=row['sha256'], expected=item['sha256'],
                                           kind=row['event'], artifact='objects/' + item['sha256']) from exc
            if c.digest(raw) != item['sha256'] or len(raw) != item['size']:
                raise store.evidence_error('EVIDENCE_SNAPSHOT_CORRUPT', 'Event evidence size or digest differs.',
                                           file=item['path'], run=run, event=row['sha256'], expected=item['sha256'],
                                           actual=c.digest(raw), kind=row['event'], artifact='objects/' + item['sha256'])
            known[item['sha256']] = len(raw)
    lifecycle.completion_tail(rows, prepared, run)


def load_run(root: Path, run: str, *, force: bool = False) -> tuple[Path, dict, dict, list[dict]]:
    """The registered run with its verified publication, envelope, consumer and event chain.

    One check scope (`runtime_snapshot.check_scope`) reads the insert-only run
    registration once, verifies the publication of its manifest digest once,
    and checks each stored object once by its digest. Every call reads the
    committed events and returns its own copies. `force` reads and verifies
    everything again, as the check before an external effect does.
    """
    import runtime_snapshot
    scope = runtime_snapshot.check_scope(root)
    reuse = scope if scope is not None and not force else {}
    place = ('run-registration', str(Path(root).absolute()), run_identifier(run))
    registered = reuse.get(place)
    if registered is None:
        registered = store.registered_run(root, run)
    directory = c.local(root, registered['directory'])
    key = ('run-content', str(directory), registered['manifest_sha256'])
    held = reuse.get(key)
    if held is None:
        from production_compiler import verify_publication
        manifest = verify_publication(directory, expected=registered['manifest_sha256'])
        # The manifest objects stored under their own digest were hashed just now.
        held = {'prepared': c.read(c.local(directory, 'prepared.json')),
                'consumer': c.read(c.local(directory, 'consumer.json')),
                'verified': {item['sha256']: item['size'] for item in manifest['files']
                             if item['path'] == 'objects/' + item['sha256']}}
    prepared = c.decode(held['prepared'])
    consumer = c.decode(held['consumer'])
    if (prepared['envelope_sha256'] != registered['envelope_sha256']
            or prepared['input_sha256'] != registered['input_sha256']):
        raise ProductionError('INPUT_SNAPSHOT_CORRUPT', 'Run content differs from the registered envelope.',
                              phase='integrity', run=run, file='prepared.json', expected=registered['envelope_sha256'],
                              actual=prepared['envelope_sha256'], impact=store.RUN_EVIDENCE_IMPACT,
                              required_action=store.RESTORE_EVIDENCE)
    rows = store.event_rows(root, run)
    validate_run_content(run, prepared, consumer, rows, lambda key: c.object_read(directory, key),
                         verified=held['verified'])
    if scope is not None:
        scope[place] = registered
        scope[key] = held
    return directory, prepared, consumer, rows


def current_sha256(root: Path, dependency: dict) -> str:
    """Hash the current bytes behind one pinned dependency."""
    if dependency['space'] == 'skill':
        return c.file_digest(ROOT, dependency['path'])[0]
    return c.digest(c.read(c.local(root, dependency['path'])))


def _freshness_failures(root: Path, run: str, prepared: dict, *, rows: list[dict] | None = None, force: bool = False):
    """Yield each freshness failure of the run's live sources, in check order, as an exception.

    A check scope (`runtime_snapshot.check_scope`) that found these sources
    current yields nothing again. Outside a transaction, that result holds only
    until the run commits another event, so `rows` names the last one. A new
    transaction, or `force`, checks the sources again.
    """
    import route_reading
    import runtime_snapshot
    from contextlib import nullcontext
    scope=runtime_snapshot.check_scope(root)
    envelope=prepared.get('envelope_sha256')
    in_transaction=store._CONNECTIONS.get().get(str(Path(root).resolve())) is not None
    tail=None if in_transaction or not rows else rows[-1]['sha256']
    key=('live-sources',str(Path(root).absolute()),run,envelope,tail)
    if scope is not None and key in scope and not force:
        return
    failed=False
    descriptor=prepared.get('runtime_snapshot')
    try:
        if descriptor is not None:runtime_snapshot.require_current(root,descriptor,run=run)
    except (ValueError,OSError) as exc:
        failed=True
        yield exc
    try:
        with (runtime_snapshot.using(runtime_snapshot.path(root,descriptor),descriptor) if descriptor else nullcontext()):
            route_reading.require_route_reading(prepared['route_reading'],studio=root,routes={prepared['task']['route']},features=prepared['task']['features'])
    except (ValueError,OSError) as exc:
        failed=True
        yield exc
    for dependency in prepared['dependencies']:
        if dependency['space'] == 'evidence': continue
        try: actual=current_sha256(root,dependency)
        except (ValueError,OSError) as exc:
            error=freshness_error(dependency,None,run=run)
            error.__cause__=exc
            failed=True
            yield error
            continue
        if actual!=dependency['sha256']:
            failed=True
            yield freshness_error(dependency,actual,run=run)
    if scope is not None and not failed and envelope is not None:
        scope[key]=True


def assert_current(root: Path, run: str, *, force: bool = False) -> tuple[Path, dict, dict, list[dict]]:
    """The loaded run once its live sources are current; one check scope checks them once.

    `force` loads the run and checks its live sources again, even inside a
    caller's transaction, as the check before an external effect does.
    """
    loaded=load_run(root,run,force=force)
    for failure in _freshness_failures(root,run,loaded[1],rows=loaded[3],force=force):
        raise failure
    # Event evidence is checked against owned snapshots by load_run, not its
    # deletable provenance locator. Current grants are checked separately.
    return loaded


def freshness_diagnostics(root: Path, run: str, *, loaded: tuple | None = None) -> list[dict]:
    """Every freshness problem of the run's live sources as a diagnostic, without stopping at the first."""
    from production_diagnostics import from_exception
    loaded=loaded or load_run(root,run)
    return [from_exception(failure,phase='freshness') for failure in _freshness_failures(root,run,loaded[1],rows=loaded[3])]


def require_mutable(records: list[dict]) -> None:
    if any(row['event'] == 'completion' for row in records):
        raise ValueError('run is complete; prepare a new run for further work')


def append_record(directory: Path, prepared: dict, records: list[dict], event: str, data: dict) -> dict:
    for row in reversed(records):
        if row['event']==event and row['data']==data:return row
    if event not in {'reservation-release','reservation-settled'}:require_mutable(records)
    if event not in EVENTS:raise ValueError('unknown production event')
    root=directory.parents[2]
    previous=records[-1]['sha256'] if records else None
    return store.append(root,directory.name,prepared['input_sha256'],event,data,
                        expected_previous=previous,check_previous=True)


def find(records: list[dict], event: str, identifier: str | None = None) -> dict:
    found = [row for row in records if row['event'] == event and (identifier is None or row['sha256'] == identifier)]
    if not found:
        if event == 'handoff':
            raise ProductionError('HANDOFF_REQUIRED', 'No recorded handoff gives this run its recipient.', phase='handoff',
                                  required_action='Record the handoff of the consumer to its recipient under an exact '
                                                  'direction authorization; execute records a dispatcher handoff itself.')
        raise ValueError('missing ' + event + ' evidence')
    return found[-1]


def file_record(root: Path, directory: Path, path: str) -> dict:
    raw = store.stable_bytes(root, path)
    return {'path': path, 'sha256': c.object_store(directory, raw), 'size': len(raw)}


def run_task(root: Path, run: str) -> str | None:
    try:return store.registered_run(root,run)['task_id']
    except (ValueError,OSError):return None


def run_ids(root: Path) -> list[str]:
    return [row['run_id'] for row in store.runs(root)]


def reservations(root: Path, task_id: str, *, exclude: str | None = None) -> list[dict]:
    """Read actual execution reservations, never count authorization receipts."""
    return [state for state in lifecycle.all_states(root,task_id=task_id)
            if state['status']!='released' and state['authorization_sha256']!=exclude]


def assert_authority_current(root: Path, prepared: dict) -> None:
    """Use the current committed grant state, without changing creative inputs."""
    prepared['authority']=store.authority(root,prepared['task']['task_id'])


def authorization_context(root: Path, run: str, operation: str) -> tuple:
    loaded = load_run(root, run) if operation == 'edit' else assert_current(root, run)
    assert_authority_current(root, loaded[1])
    return loaded


def authorize(root: Path, run: str, request_file: str) -> dict:
    raw = store.stable_bytes(root, request_file)
    return authorize_value(root, run, c.decode(raw), evidence_files=[request_file],
                           expected_source=(request_file, c.digest(raw)))


def require_open_task(rows: list[dict], run: str) -> None:
    """An abandoned work task starts no new operation; recorded effects keep their accounting."""
    if any(row['event'] == 'abandoned' for row in rows):
        raise ProductionError('TASK_ABANDONED', 'The work task of this run was abandoned; it starts no new operation.',
                              phase='authorization', run=run,
                              required_action='Open a new work task and prepare a new run; recorded reservations stay until settled or released.')


def protected_criteria_record(prepared: dict, grant_id: str) -> dict:
    """The criteria a grant protects, by ID and by the digest of their current definitions."""
    grants = [g for g in prepared['authority']['grants'] if g['id'] == grant_id]
    ids = sorted(grants[0]['protected_criteria']) if len(grants) == 1 else []
    criteria = {x['id']: x for x in prepared['task']['criteria']}
    return {'ids': ids, 'sha256': c.content_id([criteria.get(key) for key in ids])}


def authorize_value(root: Path, run: str, request: dict, *, evidence_files: list[str],
                    expected_source: tuple[str, str] | None = None) -> dict:
    """Store actual supplied decisions through the same API used by every CLI.

    Each evidence file is read once and stored with its locator, capture time
    and purpose. Approval evidence is kept by path and SHA-256, so a cited
    reading of a growing ledger stays valid after later appends.
    """
    with store.transaction(root):
        directory, prepared, _, rows = authorization_context(root, run, request.get('operation'))
        schema_check(request, 'authorization')
        files = [store.capture_evidence(root, directory, path, locator='whole', purpose='authorization-request', rows=rows)
                 for path in evidence_files]
        if expected_source is not None and not any(item['path'] == expected_source[0] and item['sha256'] == expected_source[1] for item in files):
            raise ProductionError('SOURCE_CHANGED', 'Authorization source changed during capture.', phase='authorization',
                                  file=expected_source[0], expected=expected_source[1],
                                  actual=next((item['sha256'] for item in files if item['path'] == expected_source[0]), None),
                                  required_action='Finish editing the decision file, then authorize the complete file again.')
        if prepared['task']['execution'] == 'dispatcher' and request['operation'] == 'submit':
            from production_request import check_authorization
            matches = [g for g in prepared['authority']['grants'] if g['id'] == request['grant']]
            if len(matches) != 1:
                raise ProductionError('GRANT_REVOKED', 'Select one current grant.', phase='authorization', grant=request['grant'],
                                      required_action='Select a grant that the current authority declares.')
            _, witnesses = check_authorization(root, prepared, request, matches[0])
            held = {(item['path'], item['sha256']) for item in files}
            for item in witnesses:
                if (item['path'], item['sha256']) in held:
                    continue
                held.add((item['path'], item['sha256']))
                files.append(store.capture_evidence(root, directory, item['path'], locator=item['locator'],
                                                    purpose=item['purpose'], raw=item['raw'], rows=rows))
        elif request.get('request_decision') is not None:
            raise ValueError('only a model dispatcher submission carries a model request decision')
        data = {'files': files, 'request': request,
                'protected_criteria': protected_criteria_record(prepared, request['grant'])}
        for row in rows:
            if row['event'] == 'authorization' and row['data'] == data:
                return row
        require_mutable(rows)
        require_open_task(rows, run)
        if any(r['event'] == 'reservation-release' for r in rows):
            raise ProductionError('RESERVATION_REQUIRED', 'Prepare a new run after releasing its execution.', phase='authorization')
        grant = permissions.check(prepared['authority'], request)
        if request['operation'] == 'direction':
            validate_protected_criteria(root, prepared, grant)
        return append_record(directory, prepared, rows, 'authorization', data)


def _permission(root: Path, prepared: dict, rows: list[dict], identifier: str,
                operation: str, targets: list[str], payload: dict) -> dict:
    assert_authority_current(root, prepared)
    require_open_task(rows, prepared['run'])
    row = find(rows, 'authorization', identifier)
    prior_reservation=lifecycle.by_authorization(rows,prepared,prepared['run'],identifier)
    if prior_reservation is not None and prior_reservation['status']=='released':
        raise ProductionError('RESERVATION_REQUIRED','Authorization belongs to a released execution; prepare a new run.',phase='authorization')
    request = row['data']['request']
    compare_exact({'operation':operation,'targets':sorted(targets),'payload':payload},
                  {'operation':request['operation'],'targets':sorted(request['targets']),'payload':request['payload']},
                  intent={'operation': operation, 'targets': sorted(targets), 'run': prepared['run'], 'authorization': identifier})
    grant = permissions.check(prepared['authority'], request)
    if operation == 'direction':
        validate_protected_criteria(root, prepared, grant)
    if operation == 'submit' and prepared['task']['execution'] == 'dispatcher':
        from production_request import check_authorization
        directory=run_dir(root,prepared['run'])
        recorded=[(item['path'],c.object_read(directory,item['sha256'])) for item in row['data']['files']]
        check_authorization(root, prepared, request, grant, recorded=recorded)
    return request


def abandon_task(root: Path, task_id: str, *, actor: str, reason: str) -> list[dict]:
    """Record that a work task stops, as an `abandoned` event on each of its open runs.

    The event data is `{"actor": ..., "reason": ...}`. Abandoning is not
    releasing: reservations, claims and unknown outcomes stay as recorded, and
    `release-reservation` or settlement closes each of them on its own evidence.
    A completed run keeps its completion. Returns the abandoned event of each run.
    """
    c.text(actor, 'abandoning actor')
    c.text(reason, 'abandon reason')
    data = {'actor': actor, 'reason': reason}
    recorded = []
    with store.transaction(root):
        for item in store.runs(root, task_id=task_id):
            directory, prepared, _, rows = load_run(root, item['run_id'])
            if any(row['event'] == 'completion' for row in rows):
                continue
            prior = [row for row in rows if row['event'] == 'abandoned']
            recorded.append(prior[-1] if prior else append_record(directory, prepared, rows, 'abandoned', data))
    return recorded


def handoff_intent(root: Path, run: str, recipient: str, method: str) -> dict:
    _, prepared, consumer, _ = assert_current(root, run)
    c.text(recipient, 'recipient')
    if method not in {'conversation', 'manual', 'dispatcher'}:
        raise ValueError('invalid handoff method')
    if (method == 'dispatcher') != (prepared['task']['execution'] == 'dispatcher'):
        raise ValueError('handoff method differs from the declared execution mode')
    if prepared['task']['execution'] == 'dispatcher':
        execution_plan = c.load(run_dir(root, run) / 'execution-plan.json')
        compare_exact({key: execution_plan['handoff'][key] for key in ('recipient', 'method')},
                      {'recipient': recipient, 'method': method}, pointer='$.handoff')
    return {'operation': 'direction', 'targets': plan.direction_targets(prepared['task']),
            'payload': {'consumer_sha256': c.content_id(consumer), 'recipient': recipient, 'method': method}}


def handoff(root: Path, run: str, recipient: str, method: str, authorization: str, *,
            journal: Path | None = None) -> dict:
    """Record a handoff that has happened.

    A dispatcher receives the consumer when execute copies it into the dispatch
    journal, so a dispatcher handoff names that journal and is recorded by execute.
    """
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        intent = handoff_intent(root, run, recipient, method)
        if method == 'dispatcher':
            copied = None if journal is None else Path(journal) / 'consumer.json'
            if copied is None or not copied.is_file() or c.read(copied) != c.read(directory / 'consumer.json'):
                raise ProductionError('HANDOFF_NOT_PERFORMED', 'The dispatcher has not received the consumer.',
                                      phase='handoff', run=run,
                                      required_action=f'Run python scripts/production_workflow.py execute --root ROOT --run {run}; '
                                                      'it records the dispatcher handoff when it hands the consumer over.')
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
    """Commit the handoff-to-host boundary before the host invokes its tool.

    Returning a claim never proves the host obtained a result. Re-reading the
    same receipt is idempotent; it is not permission to invoke the tool twice.
    """
    import production_store as store
    with store.transaction(root):
        directory, prepared, _, rows = assert_current(root, run)
        intent = external_intent(root, run, count)
        request = _permission(root, prepared, rows, authorization, **intent)
        data = {**intent['payload'], 'authorizations': [authorization], 'cost': request['cost']}
        previous = [r for r in rows if r['event'] == 'external-claim']
        if previous:
            if previous[0]['data'] != data:
                raise ProductionError('DISPATCH_ALREADY_CLAIMED',
                    'An external tool call is already claimed; recover it, or prepare a new run for a new call.',
                    phase='before-send', run=run)
            return previous[0]
        claim = lifecycle.commit_effect(root, run, 'external-claim', data, [authorization], effect='external-handoff')
        lifecycle.begin_step(root, run, authorization, claim=claim['sha256'],
                             step='external-send', operation='send')
        return claim


def capture(root: Path, run: str, artifact: str, note: str) -> dict:
    c.text(note, 'candidate provenance')
    with c.lock(root):
        directory, prepared, _, rows = load_run(root, run)
        execution = prepared['task']['execution']
        if execution != 'external':
            directory, prepared, _, rows = assert_current(root, run)
        # Receiving an already delegated result must not re-authorize sending
        # or require mutable source files which were preserved at preparation.
        hand = find(rows, 'handoff')
        if execution == 'dispatcher':
            results = find(rows, 'dispatch-results')
            if artifact not in {f['path'] for f in results['data']['files']}:
                raise ValueError('artifact is not a fully acquired dispatch result')
        item = file_record(root, directory, artifact)
        if execution == 'external':
            claim = find(rows, 'external-claim')
            previous = [row for row in rows if row['event'] == 'candidate']
            same = [row for row in previous if any(f['sha256'] == item['sha256'] for f in row['data']['files'])]
            if same:
                return same[0]
            states = lifecycle.derive(rows, prepared, run)
            if any(state['status'] == 'settled' for state in states.values()):
                raise ProductionError('SETTLEMENT_CONFLICT', 'The external result was finalized; a new output cannot alter that receipt.', phase='capture', run=run)
            if len(previous) >= claim['data']['count']:
                raise ValueError('external output count exceeds its authorization')
        measured = media.inspect(c.object_read(directory, item['sha256']), prepared['task']['artifact'])
        return append_record(directory, prepared, rows, 'candidate',
                             {'handoff': hand['sha256'], 'files': [item], 'media': measured, 'note': note})


def settle_external(root: Path, run: str, receipt_file: str) -> dict:
    """Record a host's evidenced result and actual bill, never a price estimate.

    This is recovery only, with no host invocation. Unknown costs stay reserved.
    The response and signed-by-actor declaration are saved as immutable evidence.
    """
    import production_store as store
    with store.transaction(root):
        directory, prepared, _, rows = load_run(root, run)
        if prepared['task']['execution'] != 'external':
            raise ProductionError('INPUT_CONSISTENCY_ERROR', 'This run does not delegate execution to an external host.', phase='settlement', run=run)
        receipt = c.load(c.local(root, receipt_file))
        schema_check(receipt, 'external-receipt')
        claim = find(rows, 'external-claim', receipt['claim'])
        authorization = claim['data']['authorizations'][0]
        request = find(rows, 'authorization', authorization)['data']['request']
        if receipt['actor'] != request['actor']:
            raise ProductionError('AUTHORIZATION_MISMATCH', 'External receipt actor differs from the delegated executor.', phase='settlement', run=run)
        acquired = [row for row in rows if row['event'] == 'candidate']
        if receipt['outputs'] != len(acquired):
            raise ProductionError('INPUT_CONSISTENCY_ERROR', 'External receipt output count differs from the saved candidates.', phase='settlement', run=run,
                                  expected=len(acquired), actual=receipt['outputs'])
        response = file_record(root, directory, receipt['response']['path'])
        if response['sha256'] != receipt['response']['sha256']:
            raise ProductionError('EVIDENCE_SNAPSHOT_CORRUPT', 'External response does not match the declared digest.', phase='settlement', run=run,
                                  expected=receipt['response']['sha256'], actual=response['sha256'])
        evidence = [file_record(root, directory, receipt_file), response]
        if receipt['final'] and receipt['cost'] is not None:
            lifecycle.record_effect(root, run, authorization, claim=claim['sha256'], step='external-send',
                usage={**receipt['cost'], 'final': True}, evidence=evidence)
        row = lifecycle.settle(root, run, authorization, outputs=receipt['outputs'], cost=receipt['cost'],
                               final=receipt['final'], evidence=evidence)
        return {'settled': receipt['final'] and receipt['cost'] is not None,
                'execution_completed': receipt['final'] and receipt['outputs'] == claim['data']['count'],
                'receipt': row, 'external_effect': False, 'budget': lifecycle.budget(root, run=run)}


def draft_review(root: Path, run: str, candidate: str) -> dict:
    directory, prepared, _, rows = load_run(root, run)
    find(rows, 'candidate', candidate)
    from craft_consultation import review_questions
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
        if check['verdict'] in {'pass', 'fail', 'indeterminate'} and not indices:
            raise ValueError('a judged criterion must cite actual observations')
        requirement = expected[check['criterion']]['evidence']
        if check['verdict'] == 'pass' and not any(requirement in supported[i] for i in indices):
            raise ValueError('evidence medium or range cannot support the claimed pass')
    # Omitted criteria remain unassessed. Selection separately requires every
    # hard criterion to have an actual supported pass.
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
    with store.transaction(root):
        directory, prepared, _, rows = load_run(root, run)
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
        recorded = {'candidate': candidate['sha256'], 'files': [item], 'evidence': records,
                    'media': {k: v[1] for k, v in supplemental.items()}, 'review': data}
        reviews = [r for r in rows if r['event'] == 'review' and r['data']['candidate'] == candidate['sha256']]
        latest = reviews[-1] if reviews else None
        # Submitting the latest review again records nothing new. Any other
        # submission, even one equal to an earlier review, becomes the latest; the
        # link to the review it follows keeps the two events distinct.
        if latest is not None and {k: v for k, v in latest['data'].items() if k != 'previous_review'} == recorded:
            row = latest
        else:
            row = append_record(directory, prepared, rows, 'review',
                                {**recorded, 'previous_review': latest['sha256'] if latest else None})
    return _refresh_studio_projection(root, row)


def eligible(prepared: dict, reviewed: dict) -> None:
    data = reviewed['data']['review']
    if data['unresolved']:
        raise ValueError('review has unresolved issues')
    hard = {x['id'] for x in prepared['task']['criteria'] if x['strength'] == 'hard'}
    passed = {x['criterion'] for x in data['checks'] if x['verdict'] == 'pass'}
    if hard - passed:
        raise ProductionError('REVIEW_INCOMPLETE', 'Required criteria have not passed: ' + ', '.join(sorted(hard - passed)),
                              phase='selection', required_action='Observe and review each required criterion before selection.')


def latest_review(rows: list[dict], candidate: str) -> dict:
    found = [r for r in rows if r['event'] == 'review' and r['data']['candidate'] == candidate]
    if not found:
        raise ValueError('candidate has no recorded review')
    return found[-1]


def candidate_state(root: Path, run: str, candidate: str, *, loaded: tuple | None = None) -> dict:
    """Project evaluation and disposition from the one official event stream.

    Capturing bytes is not an observation. Not selecting an image is not a
    statement about its quality. A Studio ledger cannot override this result.

    The latest review sets the evaluation. A review that assesses no criterion
    leaves the candidate `unreviewed`. Any `fail` makes it `nonconforming`. An
    authored `indeterminate` verdict or an unresolved issue makes it
    `indeterminate`. Criteria left unassessed make it `partially_reviewed`.
    Otherwise every criterion passed or does not apply, and it is `conforming`.
    A selection stops being current when a newer review of the candidate or a
    later selection of another candidate exists.
    """
    _, prepared, _, rows = loaded if loaded is not None else load_run(root, run)
    chosen = find(rows, 'candidate', candidate)
    reviews = [r for r in rows if r['event'] == 'review' and r['data']['candidate'] == candidate]
    latest = reviews[-1] if reviews else None
    expected = {x['id'] for x in prepared['task']['criteria']}
    checks = latest['data']['review']['checks'] if latest else []
    verdicts = {x['verdict'] for x in checks}
    assessed = {x['criterion'] for x in checks if x['verdict'] != 'not-assessed'}
    unassessed = sorted(expected - assessed)
    if not assessed:
        evaluation = 'unreviewed'
    elif 'fail' in verdicts:
        evaluation = 'nonconforming'
    elif 'indeterminate' in verdicts or latest['data']['review']['unresolved']:
        evaluation = 'indeterminate'
    elif unassessed:
        evaluation = 'partially_reviewed'
    else:
        evaluation = 'conforming'
    disposition_value = 'pending'
    decision = None
    position = None
    for index, event in enumerate(rows):
        if event['event'] == 'disposition' and event['data']['disposition']['candidate'] == candidate:
            decision, position = event, index
            disposition_value = event['data']['disposition']['disposition']
        elif event['event'] == 'selection' and event['data']['selection']['candidate'] == candidate:
            decision, position = event, index
            disposition_value = 'selected'
    decision_data = decision['data'].get('disposition', decision['data'].get('selection')) if decision else None
    diagnostics = []
    if disposition_value == 'selected':
        from production_diagnostics import from_exception
        if latest is None or decision_data['review'] != latest['sha256']:
            diagnostics.append(from_exception(_selection_review_changed(run), phase='selection'))
        if any(row['event'] == 'selection' for row in rows[position + 1:]):
            diagnostics.append(from_exception(ProductionError(
                'SELECTION_REPLACED', 'A later selection of another candidate replaced this selection.',
                phase='selection', run=run, required_action='Read the current selection of the run with status.'), phase='selection'))
    return {'run': run, 'candidate': candidate, 'candidate_sha256': chosen['data']['files'][0]['sha256'],
            'evaluation': evaluation, 'disposition': disposition_value,
            'unassessed_criteria': unassessed, 'review': latest['sha256'] if latest else None,
            'decision': decision['sha256'] if decision else None, 'decision_detail': decision_data,
            'reviewed_at': latest['created_at'] if latest else None,
            'decided_at': decision['created_at'] if decision else None,
            'selection_current': not diagnostics if disposition_value == 'selected' else None,
            'selection_diagnostics': diagnostics}


def draft_disposition(root: Path, run: str, candidate: str) -> dict:
    _, prepared, _, rows = load_run(root, run)
    find(rows, 'candidate', candidate)
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate,
            'disposition': 'not_selected', 'actor': '', 'reason': '', 'review': None}


def disposition_value(root: Path, run: str, data: dict, *, files: list[dict] | None = None) -> dict:
    """Record an explicit disposition; selection has its own gate.

    A disposition recorded after a selection withdraws that selection. The image
    a Studio accepted for its slot keeps its selection until the author accepts
    another image for the slot.
    """
    with store.transaction(root):
        loaded = load_run(root, run)
        directory, prepared, _, rows = loaded
        schema_check(data, 'disposition')
        for name in ('actor', 'reason'):
            c.text(data[name], name)
        compare_exact({'input_sha256': prepared['input_sha256']},
                      {'input_sha256': data['input_sha256']}, phase='disposition')
        current_state = candidate_state(root, run, data['candidate'], loaded=loaded)
        accepted = _studio_accepted(root, prepared, run, data['candidate'])
        if current_state['disposition'] == 'selected' and accepted:
            raise ProductionError('SELECTED_CANDIDATE', 'The Studio holds this selected candidate as its accepted image.',
                                  phase='disposition', run=run, iterations=accepted,
                                  required_action='Accept another image for the slot before withdrawing this selection.')
        if data['review'] is not None:
            actual = latest_review(rows, data['candidate'])
            if data['review'] != actual['sha256']:
                raise ProductionError('REVIEW_MISMATCH', 'Disposition must cite the actual latest review.', phase='disposition', run=run)
        if current_state['decision_detail'] == data:
            row = next(row for row in rows if row['sha256'] == current_state['decision'])
        else:
            if files is None:
                raw = c.encoded(data)
                key = c.object_store(directory, raw)
                files = [{'path': f'production/runs/{run}/objects/{key}', 'sha256': key, 'size': len(raw)}]
            row = append_record(directory, prepared, rows, 'disposition', {'disposition': data, 'files': files, 'previous_decision': current_state['decision']})
    return _refresh_studio_projection(root, row)


def disposition(root: Path, run: str, decision_file: str) -> dict:
    with store.transaction(root):
        directory, _, _, _ = load_run(root, run)
        item = file_record(root, directory, decision_file)
    return disposition_value(root, run, c.decode(c.object_read(directory, item['sha256'])), files=[item])


def _studio_accepted(root: Path, prepared: dict, run: str, candidate: str) -> list[str]:
    """The iterations a Studio at this root holds as accepted images of this candidate."""
    import studio
    character = (prepared['task'].get('recording') or {}).get('character')
    if not (root / studio.MANIFEST).is_file() or not studio.valid_character_id(character):
        return []
    rows = studio.read_iterations(studio.character_dir(root, character), project=False)
    return [row['iteration_id'] for row in rows
            if row.get('production') == {'run': run, 'candidate': candidate} and row.get('adoption_status') == 'accepted']


def _refresh_studio_projection(root: Path, receipt: dict) -> dict:
    """Rewrite the Studio gallery after a formal decision when the root is a Studio.

    The decision is already durable. A failed display adds `projection_warning`
    to the returned receipt; `studio.py gallery` rebuilds it from the records.
    """
    import studio
    if not (root / studio.MANIFEST).is_file():
        return receipt
    try:
        studio.write_gallery(root)
    except (ValueError, OSError) as exc:
        from production_diagnostics import from_exception
        return {**receipt, 'projection_warning': from_exception(exc, phase='studio-projection')}
    return receipt


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
        _require_no_other_selection(rows, data['candidate'], run)
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
            for path in confirm_studio_adoption(root, data['adoption'], candidate['data']['files'][0]['sha256'], rows):
                files.append(file_record(root, directory, path.relative_to(root).as_posix()))
        row = lifecycle.commit_effect(root,run,'selection',
            {'files':files,'selection':data,'authorizations':[data['authorization']]},
            [data['authorization']],effect='local-action')
    return _refresh_studio_projection(root, row)


def _require_no_other_selection(rows: list[dict], candidate: str, run: str) -> None:
    """Refuse selecting a candidate while another one holds the run's current selection.

    A candidate holds it while its latest decision is a selection made against
    its latest review. A disposition of that candidate, or a newer review of it,
    releases it first.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        if row['event'] == 'disposition':
            latest[row['data']['disposition']['candidate']] = row
        elif row['event'] == 'selection':
            latest[row['data']['selection']['candidate']] = row
    for other, row in latest.items():
        if other != candidate and row['event'] == 'selection' \
                and row['data']['selection']['review'] == latest_review(rows, other)['sha256']:
            raise ProductionError('SELECTION_CONFLICT', 'Another candidate holds the current selection of this run.',
                                  phase='selection', run=run, candidate=other,
                                  required_action='Record a disposition of the selected candidate, or a newer review of it, before selecting another one.')


def _selection_review_changed(run: str | None = None) -> ProductionError:
    return ProductionError('SELECTION_REVIEW_CHANGED', 'The selected review is no longer current.', phase='selection', run=run,
                           required_action='Review and explicitly select against the latest evidence.')


def current_selection(prepared: dict, rows: list[dict]) -> tuple[dict, dict, dict]:
    selection = find(rows, 'selection')
    chosen = selection['data']['selection']
    reviewed = latest_review(rows, chosen['candidate'])
    if reviewed['sha256'] != chosen['review']:
        raise _selection_review_changed()
    eligible(prepared, reviewed)
    return selection, chosen, reviewed


def require_selected(prepared: dict, rows: list[dict], candidate: str, *, run: str) -> dict:
    """Return the run's current selection when it names this candidate.

    Accepting a Production candidate in the Studio, and adopting it, start from
    this selection.
    """
    if any(row['event'] == 'selection' for row in rows):
        selection, chosen, _ = current_selection(prepared, rows)
        if chosen['candidate'] == candidate:
            return selection
    raise ProductionError('SELECTION_REQUIRED', 'The candidate is not the current selection of its run.',
                          phase='selection', run=run, candidate=candidate,
                          required_action='Select the candidate with production_workflow.py select first.')


def complete(root: Path, run: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        selection, chosen, reviewed = current_selection(prepared, rows)
        if chosen['scope'] == 'studio-adoption':
            candidate = find(rows, 'candidate', chosen['candidate'])
            confirm_studio_adoption(root, chosen['adoption'], candidate['data']['files'][0]['sha256'], rows)
        row = append_record(directory, prepared, rows, 'completion',
                            {'selection': selection['sha256'], 'candidate': chosen['candidate'],
                             'scope': chosen['scope'], 'task_id': prepared['task']['task_id'], 'run': run,
                             'limitations': [x for ob in reviewed['data']['review']['observations'] for x in ob['limitations']]})
    return _refresh_studio_projection(root, row)


def verify_completion(root: Path, run: str, task_id: str) -> dict:
    _, prepared, _, rows = assert_current(root, run)
    done = find(rows, 'completion')
    if prepared['task']['task_id'] != task_id or done['data']['task_id'] != task_id or done['data']['run'] != run:
        raise ValueError('completion belongs to another task')
    lifecycle.completion_tail(rows,prepared,run)
    if done['data']['selection'] != find(rows, 'selection')['sha256']:
        raise ValueError('completion is not the terminal selected state')
    _, selected, reviewed = current_selection(prepared, rows)
    if selected['scope'] == 'studio-adoption':
        candidate = find(rows, 'candidate', selected['candidate'])
        confirm_studio_adoption(root, selected['adoption'], candidate['data']['files'][0]['sha256'], rows)
    return done


def impact(root: Path, run: str) -> dict:
    """Read-only comparison against frozen inputs, including transitive decisions.

    A changed creative source is a change and reaches decisions and criteria.
    Evidence sources and files recorded by events are provenance: the run keeps
    their verified snapshots, so a grown ledger or a replaced file is listed
    under `provenance` as `provenance_changed` with the snapshot intact. A
    changed file of the installed implementation is listed under
    `implementation`; it reaches no creative decision, and the task is prepared again.
    """
    with c.lock(root):
        try:
            _, prepared, _, rows = load_run(root, run)
        except (ValueError, OSError, KeyError, UnicodeError) as exc:
            return {'ok': False, 'run': run, 'integrity_error': str(exc)}
        changes = []
        provenance = []
        implementation = []
        records = list(prepared['dependencies'])
        records += [{**f, 'space': 'artifact', 'receipt': row['sha256']}
                    for row in rows for f in row['data'].get('files', []) + row['data'].get('evidence', [])]
        for item in records:
            try:
                actual = current_sha256(root, item)
                if actual == item['sha256']:
                    continue
                entry = {**item, 'actual_sha256': actual, 'status': 'changed'}
            except (ValueError, OSError) as exc:
                entry = {**item, 'actual_sha256': None, 'status': 'unavailable', 'reason': str(exc)}
            if item['space'] in {'evidence', 'artifact'}:
                # load_run verified every saved snapshot before this comparison.
                provenance.append({**entry, 'status': 'provenance_changed', 'snapshot': 'intact'})
            elif item['space'] == 'skill':
                implementation.append(entry)
            else:
                changes.append(entry)
        paths = {x['path'] for x in changes if x['space'] == 'studio'}
        sources = {s['id'] for s in prepared['task']['sources'] if s['path'] in paths}
        structural = bool(paths - {s['path'] for s in prepared['task']['sources']})
        affected = plan.affected(prepared['task'], sources, all_inputs=structural)
        affected['receipts'] = sorted({x['receipt'] for x in provenance if 'receipt' in x})
        return {'ok': not changes and not implementation, 'run': run, 'changes': changes, 'provenance': provenance,
                'implementation': implementation, 'affected': affected,
                'limits': 'Declared dependencies only; no artistic inference and no automatic edits.'}


def execute(root: Path, run: str, *, decisions_file: str | None = None) -> dict:
    from production_execution import execute as run_execution
    return run_execution(root, run, decisions_file=decisions_file)


def resume(root: Path, run: str, *, outcome_file: str | None = None) -> dict:
    from production_execution import resume as recover_execution
    return recover_execution(root, run, outcome_file=outcome_file)


def status(root: Path, run: str | None = None, *, budget: bool = False) -> dict:
    from production_execution import status as report
    return report(root, run, budget=budget)


def changed_scopes(before: dict, after: dict) -> list[str]:
    """Conservative explicit edit scopes, never inferred aesthetic causality."""
    old, new = before['task'], after['task']
    scopes: set[str] = set()
    old_dependencies = {(x['space'], x['path']): x['sha256'] for x in before['dependencies']}
    new_dependencies = {(x['space'], x['path']): x['sha256'] for x in after['dependencies']}
    def same_file(a: str, b: str) -> bool:
        return a == b and old_dependencies.get(('studio', a)) == new_dependencies.get(('studio', b))
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
    # Grant updates are authorization state, not a creative edit scope.
    # Their validity is checked against the committed authority at consumption.
    if any(old.get(key) != new.get(key) for key in ('route', 'features', 'artifact', 'execution', 'world_views', 'moment_views', 'scene_materials')):
        scopes.add('execution')
    # Bundled worlds and story contexts may change without a selector changing.
    declared = {x['path'] for x in old['sources'] + new['sources']}
    declared.update((old['delivery']['path'], new['delivery']['path'],
                     before['task_path'], after['task_path']))
    if any(space == 'studio' and path not in declared and old_dependencies.get((space, path)) != new_dependencies.get((space, path))
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
    revised, revised_consumer, _, _ = snapshot(root, task)
    if revised['task']['task_id'] != prepared['task']['task_id']:
        raise ValueError('revision must remain within the current work task')
    if revised['task']['production_id'] != prepared['task']['production_id']:
        raise ValueError('a revision preserves its production_id')
    scopes = changed_scopes(prepared, revised)
    if not scopes:
        raise ValueError('repair contains no changed production inputs')
    if set(scopes) - set(matches[0]['targets']):
        raise ValueError('repair changes targets outside its reviewed scope: ' + ', '.join(scopes))
    from production_compiler import input_digest
    return {'operation': 'edit', 'targets': scopes,
            'payload': {'parent_run': run, 'candidate': candidate, 'review': reviewed['sha256'],
                        'repair': repair, 'revised_input_sha256': input_digest(revised, revised_consumer)}}


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
    with store.transaction(root):
        directory, prepared, _, rows = assert_current(root, run)
        hand = find(rows, 'handoff')
        if hand['data']['method'] != 'dispatcher' or prepared['task']['execution'] != 'dispatcher':
            raise ValueError('dispatcher handoff required')
        if any(r['event'] == 'dispatch-claim' for r in rows):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already owns a request.', phase='execution', run=run, required_action='Use resume, variant or repeat according to the intended operation.')
        # A low-level caller cannot introduce a second request contract for
        # this run. Compare the same sealed input used by execute before any
        # authorization accounting or claim is committed.
        from production_execution import compiled
        fixed = compiled(root, run)
        fixed_package, fixed_rendered, fixed_plan = fixed[4:7]
        import request_contract as rc
        compare_exact(c.content_id(fixed_package), c.content_id(package),
                      pointer='$.package_sha256', phase='execution')
        compare_exact(rc.receipt_projection(fixed_rendered), rc.receipt_projection(rendered),
                      pointer='$.request_contract', phase='execution')
        submission = next(item for item in fixed_plan['operations'] if item['operation'] == 'submit')
        compare_exact(submission, intent, pointer='$.submission', phase='execution')
        compare_exact({key: fixed_plan['handoff'][key] for key in ('consumer_sha256', 'recipient', 'method')},
                      {key: hand['data'][key] for key in ('consumer_sha256', 'recipient', 'method')},
                      pointer='$.handoff', phase='execution')
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
        validate_payload(payload, snapshots=package['input_snapshots'])
        if payload['request_contract'] != rc.receipt_projection(rendered):
            raise ValueError('claim differs from the rendered and reviewed request')
        if payload['package_sha256'] != c.content_id(package):
            raise ValueError('submission intent belongs to a different package')
        request = _permission(root, prepared, rows, authorization, **intent)
        reservation = lifecycle.reserve(root, run, authorization)
        directory, prepared, _, rows = load_run(root, run)
        relative = journal.absolute().relative_to(root.absolute()).as_posix()
        c.local(root, relative)
        return append_record(directory, prepared, rows, 'dispatch-claim',
                             {'package_sha256': c.content_id(package),
                              **({'upscale_request_sha256': c.content_id(package)}
                                 if package.get('artifact_type') == 'upscale-request' else
                                 {'effective_prompt_sha256': verified['host_forwarding']['effective_prompt_sha256']}),
                              'journal': relative, 'intent': intent, 'count': request['outputs'],
                              'cost': request['cost'], 'authorizations': [authorization],
                              'reservation_id': reservation['reservation_id']})


def record_dispatch_results(root: Path, run: str, package: dict, journal: Path,
                            result_paths: list[Path], expected_count: int, *,
                            indices: list[int] | None = None, returned_count: int | None = None,
                            upscale_packages: dict[int, Path] | None = None,
                            invalid_output_indices: set[int] | None = None) -> dict:
    with store.transaction(root):
        directory, prepared, _, rows = load_run(root, run)
        claim = find(rows, 'dispatch-claim')
        if c.content_id(package) != claim['data']['package_sha256']:
            raise ValueError('dispatch package changed')
        if type(expected_count) is not int or expected_count != claim['data']['count']:
            raise ValueError('expected outputs differ from the authorized count')
        indices = indices if indices is not None else list(range(1, len(result_paths) + 1))
        returned_count = returned_count if returned_count is not None else len(result_paths)
        if len(indices) != len(result_paths) or len(set(indices)) != len(indices) or any(type(i) is not int or i < 1 or i > returned_count for i in indices):
            raise ValueError('every captured result needs a distinct valid provider output index')
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
        if (journal/'transport-outcome.json').is_file():
            evidence.append(file_record(root,directory,base+'/transport-outcome.json'))
        invalid_output_indices = set(invalid_output_indices or ())
        if not invalid_output_indices.issubset(set(indices)):
            raise ValueError('invalid output indices must name captured provider outputs')
        if package.get('artifact_type') == 'upscale-request':
            if expected_count != 1:
                raise ValueError('one declared upscale permits exactly one result')
            from upscale_package import verify_upscale_package
            upscale_packages = dict(upscale_packages or {})
            if set(upscale_packages).intersection(invalid_output_indices):
                raise ValueError('an upscale output cannot be both valid and contract-invalid')
            if set(upscale_packages).union(invalid_output_indices) != set(indices):
                raise ValueError('every captured upscale output needs either a verified package or an explicit contract-invalid status')
            for index,item in zip(indices,files):
                if index in invalid_output_indices:
                    continue
                generated_path = upscale_packages[index]
                try:
                    name = generated_path.absolute().relative_to(journal.absolute()).as_posix()
                except ValueError as exc:
                    raise ValueError('upscale result package must be owned by the dispatch journal') from exc
                generated=c.load(generated_path)
                verify_upscale_package(generated,package_root=journal)
                if (generated['source_image']['sha256']!=package['source']['sha256']
                        or generated['output_image']['sha256']!=item['sha256']
                        or generated['upscaler_model']!=package['model']
                        or generated['scale_factor']!=package['scale_factor']
                        or generated['settings']!=package['settings']
                        or generated['guidance_prompt']!=package['guidance_prompt']):
                    raise ValueError('upscale result package differs from the authorized operation or acquired output')
                evidence.append(file_record(root,directory,base+'/'+name))
        elif upscale_packages or invalid_output_indices:
            raise ValueError('upscale result metadata is only valid for an upscale request')
        evidence.extend(file_record(root, directory, base + f'/response-{i}.json') for i in indices)
        return append_record(directory, prepared, rows, 'dispatch-results',
                             {'claim': claim['sha256'], 'files': files, 'evidence': evidence, 'expected_count': expected_count,
                              'output_indices': indices, 'returned_count': returned_count,
                              'complete': len(files) == returned_count == expected_count,
                              'contract_valid': not invalid_output_indices,
                              'invalid_output_indices': sorted(invalid_output_indices)})


def confirm_studio_adoption(root: Path, selector: dict[str,Any], target: str, rows: list[dict]) -> list[Path]:
    """Confirm the Studio adoption a selection cites and return the files that bind it.

    The run must record the completed Production adoption of that iteration
    under the approval the Studio's adoption record holds.
    """
    import studio
    import adoption_workflow
    c.exact(selector,{'character','iteration_id','scope'},'Studio adoption selector')
    for value in selector.values(): c.text(value,'adoption field')
    home=studio.character_dir(root,selector['character'])
    owner_path=home/'adoptions'/f"{selector['iteration_id']}.json"
    owner=c.load(c.local(root,owner_path.relative_to(root).as_posix()))
    if not isinstance(owner, dict) or owner.get('artifact_type') != 'studio-adoption' or not isinstance(owner.get('approval'), dict):
        raise ProductionError('ADOPTION_RECORD_CORRUPT', 'The canonical adoption record is incomplete or malformed.',
            phase='adoption-integrity', file=owner_path.relative_to(root).as_posix(),
            expected=target, required_action='Restore the exact approved adoption record and its bound artifacts; selection alone is not adoption.')
    claims={row['sha256']:row['data']['intent']['payload'] for row in rows if row['event']=='adoption-claim'}
    adopted=[claims.get(row['data']['claim']) for row in rows if row['event']=='adoption-result']
    if not any(item and item['character']==selector['character'] and item['iteration']==selector['iteration_id']
               and item['approval_sha256']==c.content_id(owner['approval']) for item in adopted):
        raise ProductionError('ADOPTION_RESULT_MISSING', 'This run records no completed adoption of the cited Studio iteration.',
            phase='adoption-integrity', file=owner_path.relative_to(root).as_posix(), expected=target,
            required_action='Adopt the selected candidate with production_workflow.py adopt under its own adopt authorization.')
    row=studio._find(studio.read_iterations(home),selector['iteration_id'])
    try:
        approval=adoption_workflow.validate_approval(owner['approval'],selector['character'],row)
    except (ValueError, KeyError, TypeError) as exc:
        raise ProductionError('ADOPTION_RECORD_CORRUPT', 'The canonical adoption approval no longer matches its selected artifact.',
            phase='adoption-integrity', file=owner_path.relative_to(root).as_posix(), expected=target) from exc
    if approval['image_sha256']!=target or approval['scope']!=selector['scope'] or owner.get('next_action') or row['status']!='accepted':
        raise ValueError('Studio adoption is incomplete or targets a different image')
    reference=adoption_workflow.reference_index(root,selector['character'])
    if not reference['ok'] or not any(x['iteration_id']==selector['iteration_id'] and x['image_sha256']==target for x in reference['bindings']):
        raise ValueError('Studio reference index does not confirm the chosen image')
    paths=[owner_path,home/'iterations.jsonl',home/'sheet/sheet-data.json',c.local(root,row['result']['path'])]
    # Bind owned copies and the chosen binding sidecars as well as the journal.
    for field in ('result','package','request','response','answer'):
        item=row.get(field)
        if item:
            path=c.local(root,item['path'])
            if c.digest(c.read(path))!=item['sha256']: raise ValueError('Studio evidence changed')
            paths.append(path)
    if row.get('accepted_path'): paths.append(c.local(root,row['accepted_path']))
    binding=home/'sheet'/'bindings'/selector['iteration_id']
    if binding.is_dir(): paths.extend(p for p in binding.rglob('*') if p.is_file() or p.is_symlink())
    return sorted(set(paths))



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
    The candidate must hold the run's current selection, and the owner checks
    the claim this operation records before it changes the Studio.
    """
    with c.lock(root):
        directory, prepared, _, rows = assert_current(root, run)
        item = file_record(root, directory, approval_file)
        approval = c.decode(c.object_read(directory, item['sha256']))
        intent = adoption_intent(root, run, candidate, character, iteration, approval,
                                 registration_record=registration_record, pack_dir=pack_dir)
        reviewed = latest_review(rows, candidate)
        eligible(prepared, reviewed)
        require_selected(prepared, rows, candidate, run=run)
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
            row = completed[-1]
        else:
            if not prior:
                lifecycle.begin(root,run,authorization,effect='local-action',claim=claim['sha256'])
            elif not any(row['event'] == 'operation-start' and row['data']['authorization_sha256'] == authorization
                         and row['data'].get('claim') == claim['sha256'] for row in rows):
                lifecycle.begin(root,run,authorization,effect='local-action',claim=claim['sha256'])
            directory,prepared,_,rows=load_run(root,run)
            import adoption_workflow
            result = adoption_workflow.adopt(root, character, iteration, approval,
                                            registration_record=registration_record, pack_dir=pack_dir, settings=settings,
                                            production_claim=claim['sha256'])
            row = append_record(directory, prepared, rows, 'adoption-result',
                                {'claim': claim['sha256'], 'result': result})
    return _refresh_studio_projection(root, row)


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


COMMAND_HELP = {
    'check': 'Check a task and show its request preview and execution plan without creating a run.',
    'prepare': 'Check a task and publish it as a prepared run with its exact request and execution plan.',
    'draft-execution': 'Write the unanswered execution decision file for every operation of a prepared run.',
    'execute': 'Authorize, reserve, send and record the one request a prepared run owns.',
    'resume': 'Recover the same execution without sending it again where a send has started.',
    'draft-outcome': "Write the statement to fill when the provider's records hold no task for a started send.",
    'status': 'Report each run by preparation, readiness, submission, capture, review and disposition.',
    'authority-import': 'Import the grant file of the open work task, or replace the current one.',
    'recover-publication': 'Register a verified publication whose registration was interrupted.',
    'staging-cleanup': "List one ended operation's unpublished staging, unclaimed journals and unrecoverable publications.",
    'logs': 'List automatic operation logs of the studio, or of the configuration directory without --root.',
    'logs-export': 'Copy operation logs to a new directory with a manifest of what it includes.',
    'logs-cleanup': 'List diagnostic operation logs that may be deleted; production records stay.',
    'handoff-intent': 'Show the exact direction operation that a handoff needs authorized.',
    'handoff': 'Record a conversation or manual handoff that happened under an exact direction authorization.',
    'external-intent': 'Show the exact submission operation that an external host call needs authorized.',
    'claim-external': 'Commit the boundary before an external host invokes its tool under an exact authorization.',
    'settle-external': "Record an external host's evidenced result and actual charge.",
    'draft-authorization': 'Write an unanswered authorization request for one exact operation intent.',
    'authorize': 'Record a completed authorization request for one exact operation of a run.',
    'capture': 'Record a received result file as a candidate of the run.',
    'draft-review': 'Write the review form of one candidate with a question for each criterion.',
    'review': 'Record a completed review of one candidate.',
    'draft-disposition': 'Write the form that records a candidate as not selected.',
    'disposition': 'Record an explicit decision that a candidate is not selected.',
    'candidate-status': "Show one candidate's evaluation and disposition.",
    'draft-selection': 'Write the selection form of one reviewed candidate.',
    'selection-intent': 'Show the exact selection operation that a selection file needs authorized.',
    'select': 'Record an authorized selection of a reviewed candidate.',
    'revision-intent': 'Show the exact edit operation that a reviewed repair needs authorized.',
    'revise': 'Prepare a revised task as a new run under an authorized edit of a reviewed repair.',
    'adoption-intent': 'Show the exact adoption operation that a canonical adoption needs authorized.',
    'adopt': 'Adopt a selected candidate as canon under its own exact authorization.',
    'complete': 'Complete the work task with its current selection.',
    'impact': 'Compare a run with its current sources and list what each change affects.',
    'release-reservation': 'Release an unused reservation with a completed release request.',
    'draft-release': 'Write the release request form of one reservation.',
}
# One sentence for each option, by destination; a (command, destination) entry is more specific.
OPTION_HELP = {
    'root': 'The studio directory that holds the production records.',
    'run': 'ID of the prepared run.',
    'task': 'Studio-relative task JSON file; a file only, not stdin.',
    'out': 'New studio-relative file to write; an existing file is never replaced.',
    'out_dir': 'New studio-relative directory to write.',
    'budget': 'Add each grant budget with its reservations and remaining amount.',
    'decisions_file': 'Completed execution decision file from draft-execution, or - for stdin.',
    'outcome_file': "Statement from draft-outcome that the provider's records hold no task for the started send, or - for stdin.",
    'grant': 'ID of the grant the drafted decisions use.',
    'expected_event': 'Digest of the current authority event that this import replaces.',
    'failed': 'Only operations that failed or did not finish.',
    'request': 'Completed release request from draft-release, or - for stdin.',
    'reservation': 'ID of the reservation to release.',
    'recipient': 'Who receives the consumer.',
    'method': 'How the consumer is handed over.',
    'authorization': 'Digest of the authorization event that covers this operation.',
    'count': 'Number of outputs the host call makes.',
    'candidate': 'Digest of the candidate event.',
    'artifact': 'Studio-relative file that was received; a file only, not stdin.',
    'note': 'Where the received file came from.',
    'intent': 'Operation intent JSON from an intent command, or - for stdin.',
    'repair': 'ID of the repair in the latest review of the candidate.',
    'character': 'Studio character ID.',
    'iteration': 'Studio iteration ID of the candidate.',
    'approval': 'Adoption approval file, or - for stdin.',
    'registration_record': 'Catalog registration record of a catalog adoption, or - for stdin.',
    'pack_dir': 'Pack directory that receives a catalog adoption.',
    'without_streams': 'Leave stdout.log and stderr.log out of the export.',
    'from_run': 'Saved run of the same work task and production to start from.',
    'choices': 'Completed choices file from draft-inputs.',
    'focus': 'Craft layer to consult.',
    'inspect': 'Craft asset IDs to show in full.',
    'consultation': 'Studio-relative craft consultation report to apply.',
    'decisions': 'Studio-relative decisions about the consulted craft assets.',
    'spec': 'Studio-relative production specification the decisions annotate.',
    ('status', 'run'): 'Report only this run.',
    ('logs', 'run'): 'Only operations linked to this run.',
    ('logs-export', 'run'): 'Only operations linked to this run.',
    ('logs', 'root'): 'Studio whose logs to list; without it, the configuration directory.',
    ('logs-export', 'root'): 'Studio whose logs to export; without it, the configuration directory.',
    ('logs-cleanup', 'root'): 'Studio whose logs to assess; without it, the configuration directory.',
    ('logs-export', 'out'): 'New directory for the export; relative to --root, or absolute without --root.',
    ('logs', 'operation'): 'Only this operation ID.',
    ('staging-cleanup', 'operation'): 'Owner operation ID whose items --apply removes.',
    ('staging-cleanup', 'apply'): 'Remove the eligible items of --operation; without it, only list them.',
    ('authority-import', 'file'): 'Grant file of the work task, or - for stdin.',
    ('authorize', 'file'): 'Completed authorization request file, or - for stdin.',
    ('review', 'file'): 'Completed review file from draft-review, or - for stdin.',
    ('select', 'file'): 'Completed selection file from draft-selection, or - for stdin.',
    ('selection-intent', 'file'): 'Completed selection file from draft-selection, or - for stdin.',
    ('disposition', 'file'): 'Completed disposition file from draft-disposition, or - for stdin.',
    ('settle-external', 'file'): 'Evidenced external receipt file, or - for stdin.',
    ('revise', 'task'): 'Studio-relative revised task JSON file; a file only, not stdin.',
    ('revision-intent', 'task'): 'Studio-relative revised task JSON file; a file only, not stdin.',
}
# Arguments that name one JSON input file and accept - for stdin.
STDIN_INPUTS = ('decisions_file', 'file', 'request', 'intent', 'approval', 'outcome_file', 'registration_record', 'changes_file')
# Arguments that name a studio file.
FILE_ARGUMENTS = STDIN_INPUTS + ('task', 'artifact')


def build_parser():
    """The complete command interface, each command and option with its one-sentence help."""
    parser = _operation_context.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    import production_inputs
    production_inputs.add_arguments(sub)
    import craft_consultation
    craft_consultation.add_arguments(sub)
    import production_variation
    production_variation.add_arguments(sub)
    sub.add_parser('new-production-id', help='Assign an explicit stable identity to a new production series.',
                   description='Assign an explicit stable identity to a new production series.')
    for name in COMMAND_HELP:
        p = sub.add_parser(name, help=COMMAND_HELP[name], description=COMMAND_HELP[name])
        p.add_argument('--root', type=Path, required=name not in {'logs', 'logs-export', 'logs-cleanup'})
        if name not in {'prepare', 'check', 'authority-import', 'staging-cleanup', 'logs', 'logs-export', 'logs-cleanup', 'status'}:
            p.add_argument('--run', required=True)
        if name in {'status', 'logs', 'logs-export'}:
            p.add_argument('--run')
        if name == 'status':
            p.add_argument('--budget', action='store_true')
        if name == 'execute':
            p.add_argument('--decisions-file')
        if name == 'resume':
            p.add_argument('--outcome-file')
        if name in {'draft-outcome', 'draft-execution', 'logs-export', 'draft-release', 'draft-review', 'draft-selection',
                    'draft-authorization', 'draft-disposition'}:
            p.add_argument('--out', required=True)
        if name in {'draft-execution', 'draft-authorization'}:
            p.add_argument('--grant', required=True)
        if name == 'authority-import':
            p.add_argument('--file', required=True)
            p.add_argument('--expected-event')
        if name == 'staging-cleanup':
            p.add_argument('--operation')
            p.add_argument('--apply', action='store_true')
        if name == 'logs':
            p.add_argument('--failed', action='store_true')
            p.add_argument('--operation')
        if name == 'logs-export':
            p.add_argument('--without-streams', action='store_true')
        if name == 'logs-cleanup':
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument('--before', help='Select completed diagnostic operations created before YYYY-MM-DD.')
            group.add_argument('--operation', help='Select one operation ID for cleanup assessment.')
            p.add_argument('--apply', action='store_true', help='Delete eligible diagnostic logs. Omit for a dry-run plan.')
        if name == 'release-reservation':
            p.add_argument('--request', required=True)
        if name == 'draft-release':
            p.add_argument('--reservation', required=True)
        if name in {'check', 'prepare', 'revision-intent', 'revise'}:
            p.add_argument('--task', required=True)
            if name in {'prepare', 'check'}:
                from pack_runtime_cli import add_pack_runtime_arguments
                add_pack_runtime_arguments(p)
        if name in {'handoff', 'handoff-intent'}:
            p.add_argument('--recipient', required=True)
            p.add_argument('--method', required=True, choices=['conversation', 'manual', 'dispatcher'])
        if name in {'handoff', 'claim-external', 'revise', 'adopt'}:
            p.add_argument('--authorization', required=True)
        if name in {'external-intent', 'claim-external'}:
            p.add_argument('--count', type=int, required=True)
        if name in {'draft-review', 'draft-selection', 'draft-disposition', 'candidate-status', 'revision-intent', 'revise', 'adopt', 'adoption-intent'}:
            p.add_argument('--candidate', required=True)
        if name in {'authorize', 'review', 'select', 'selection-intent', 'disposition', 'settle-external'}:
            p.add_argument('--file', required=True)
        if name == 'capture':
            p.add_argument('--artifact', required=True)
            p.add_argument('--note', required=True)
        if name == 'draft-authorization':
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
    for command, child in sub.choices.items():
        if child.description is None:
            child.description = next(action.help for action in sub._choices_actions if action.dest == command)
        for action in child._actions:
            if action.help is None and action.dest != 'help':
                action.help = OPTION_HELP.get((command, action.dest), OPTION_HELP.get(action.dest))
    return parser


def _studio_arguments(root: Path, args) -> None:
    """Name every file argument relative to the studio root, refusing other forms with the form to use.

    An absolute path is accepted when it lies inside the studio.
    """
    from production_binding import studio_file
    for name in FILE_ARGUMENTS:
        value = getattr(args, name, None)
        if value is None or value == '-':
            continue
        option = '--' + name.replace('_', '-')
        # A missing input file is named here; the compiler reports an unreadable task in its own report.
        path = studio_file(root, value, option=option, exists=name != 'task')
        try:
            setattr(args, name, path.resolve().relative_to(root).as_posix() if Path(value).is_absolute() else value)
        except ValueError as exc:
            raise ProductionError('INPUT_SCHEMA_INVALID', f'{option} names a file outside the studio: {value}',
                                  phase='arguments', file=str(value), option=option,
                                  required_action=f'Copy the file into the studio and name it relative to --root.') from exc


def _new_output(root: Path | None, out: str) -> Path:
    """The --out destination, refused when anything already occupies it."""
    from production_binding import new_output
    return new_output(root, out, option='--out')


def _write_new(root: Path, out: str, value: Any) -> None:
    from production_binding import write_new
    write_new(_new_output(root, out), c.encoded(value), option='--out', value=out)


def _stdin_inputs(root: Path, args) -> None:
    """Store a JSON input read from stdin as an object of its run, and name it by that object's path.

    Standard input feeds one input per call. Every other JSON input is a file.
    """
    from production_binding import single_stdin
    single_stdin({'--' + name.replace('_', '-'): getattr(args, name, None) for name in STDIN_INPUTS})
    dashed = [name for name in STDIN_INPUTS if getattr(args, name, None) == '-']
    if not dashed or dashed[0] == 'changes_file':
        return
    raw = c.read_input_bytes('-')
    try:
        c.decode(raw)
    except ValueError as exc:
        raise ProductionError('INPUT_SCHEMA_INVALID', 'Standard input is not UTF-8 JSON.', phase='arguments', file='-',
                              pointer='$', cause=str(exc), required_action='Supply one complete JSON document on stdin.') from exc
    base = run_dir(root, args.run) if getattr(args, 'run', None) else c.local(root, 'production', exists=False)
    key = c.object_store(base, raw)
    setattr(args, dashed[0], (base / 'objects' / key).relative_to(root).as_posix())


def main() -> int:
    from production_diagnostics import CompilationError, EXIT_EXECUTION, EXIT_INPUT, exit_code, from_exception, result_exit
    parser = build_parser()
    args = parser.parse_args()
    if args.command == 'new-production-id':
        print(json.dumps({'production_id': generate_uuid7()}))
        return 0
    name = args.command
    try:
        # The user's explicit CLI root may be a volume/system alias. Resolve that
        # choice once, then recheck the canonical ancestors at every internal use.
        # Paths beneath it never gain permission to follow symbolic links.
        args.root = root = c._root(args.root.resolve()) if args.root is not None else None
        if getattr(args, 'out', None) is not None:
            _new_output(root, args.out)
        if root is not None:
            _studio_arguments(root, args)
            _stdin_inputs(root, args)
        if name in {'prepare', 'check', 'retarget'}:
            from pack_runtime_cli import resolve_pack_runtime, has_pack_runtime_arguments
            if has_pack_runtime_arguments(args):
                from catalog_retrieval import runtime
                runtime.configure_pack_runtime(resolve_pack_runtime(parser, args).settings)
        import craft_consultation, production_inputs, production_variation
        if name in craft_consultation.COMMANDS:
            result = craft_consultation.command(args, parser)
        elif name in {'variant', 'repeat', 'retarget'}:
            result = production_variation.command(args, parser)
        elif name in production_inputs.COMMANDS:
            result = production_inputs.command(args, parser)
        elif name=='release-reservation':
            result=lifecycle.release(root,args.run,args.request)
        elif name=='draft-release':
            result=lifecycle.draft_release(root,args.run,args.reservation)
            _write_new(root, args.out, result)
        elif name == 'draft-disposition':
            result = draft_disposition(root, args.run, args.candidate)
            _write_new(root, args.out, result)
        elif name == 'disposition':
            result = disposition(root, args.run, args.file)
        elif name == 'candidate-status':
            result = candidate_state(root, args.run, args.candidate)
        elif name == 'check':
            from production_compiler import check_task
            result = check_task(root, args.task)
        elif name == 'draft-execution':
            from production_execution import draft_execution
            result = draft_execution(root, args.run, args.grant)
            _write_new(root, args.out, result)
        elif name == 'execute':
            from production_execution import execute
            result = execute(root, args.run, decisions_file=args.decisions_file)
        elif name == 'authority-import':
            result = store.import_authority(root, args.file, expected=args.expected_event)
        elif name == 'recover-publication':
            from production_compiler import recover_publication
            result = recover_publication(root, args.run)
        elif name == 'staging-cleanup':
            from production_compiler import staging_cleanup
            result = staging_cleanup(root, operation_id=args.operation, apply=args.apply)
        elif name == 'logs':
            result = {'operations': _operation_context.list_operations(root, run=args.run, failed=args.failed, operation_id=args.operation)}
        elif name == 'logs-export':
            result = _operation_context.export_logs(root, _new_output(root, args.out), run=args.run,
                                                     include_streams=not args.without_streams)
        elif name == 'logs-cleanup':
            result = _operation_context.cleanup_logs(root, before=args.before, operation_id=args.operation, apply=args.apply)
        elif name == 'resume':
            from production_execution import resume
            result = resume(root, args.run, outcome_file=args.outcome_file)
        elif name == 'draft-outcome':
            from production_execution import draft_outcome
            result = draft_outcome(root, args.run)
            _write_new(root, args.out, result)
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
            _write_new(root, args.out, result)
        elif name == 'authorize':
            result = authorize(root, args.run, args.file)
        elif name == 'settle-external':
            result = settle_external(root, args.run, args.file)
        elif name == 'capture':
            result = capture(root, args.run, args.artifact, args.note)
        elif name in {'draft-review', 'draft-selection'}:
            function = draft_review if name == 'draft-review' else draft_selection
            result = function(root, args.run, args.candidate)
            _write_new(root, args.out, result)
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
        elif name == 'impact':
            result = impact(root, args.run)
        else:
            result = status(root, args.run, budget=args.budget)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get('ok', True):
            return 0
        return result_exit(result.get('diagnostics') or [], failure=EXIT_EXECUTION if name in {'execute', 'resume'} else EXIT_INPUT)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        if isinstance(exc, CompilationError):
            print(json.dumps(exc.report, ensure_ascii=False))
            return result_exit(exc.report['diagnostics'])
        diagnostic = from_exception(exc, phase='cli')
        print(json.dumps({'ok': False, 'diagnostics': [diagnostic]}, ensure_ascii=False))
        return exit_code(diagnostic['code'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
