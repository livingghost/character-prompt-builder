#!/usr/bin/env python3
"""Prepare, authorize, execute, observe, revise and complete a production task.

Every operation uses the current authored contract. Planning and observation do
not establish consent. Only explicit, scoped grants authorize actions; hashes
prove consistency of recorded bytes, never artistic success or user identity.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError, compare_exact
import execution_lifecycle as lifecycle
import execution_routes
from pack_manager import generate_uuid7
import production_evidence as media
import production_permissions as permissions
import production_plan as plan
import runtime_snapshot
from production_read_model import RunReader, RunSnapshot, RunView
from owned_json import mutable

ROOT = Path(__file__).resolve().parents[1]
EVENTS = {'authorization', 'handoff', 'external-claim', 'dispatch-claim',
          'dispatch-results', 'candidate', 'review', 'selection', 'edit',
          'adoption-claim', 'adoption-result', 'image-edit-claim', 'image-edit-output', 'completion',
          'disposition', 'handoff-ready', 'capture-status', 'execution-outcome', 'abandoned',
          'slot-acceptance', 'cleanup-observation', 'authored-save', 'authored-delivery', 'authored-review'} | lifecycle.EVENTS


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
    from state_protocol import read_schema, validate_against_schema
    schema = read_schema(ROOT / f'schemas/authoring/production-{name}.schema.json')
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('production ' + name + ': ' + '; '.join(errors))


def validate_task(task: Any) -> dict:
    if isinstance(task, dict):
        production_identifier(task.get('production_id'))
    schema_check(task, 'task')
    if task.get('authored') is not None and task['execution'] != 'authored':
        raise ValueError('authored completion and target choices belong to an authored task')
    if task.get('authored_basis') is not None and task['execution'] != 'authored':
        raise ValueError('an authored assessment basis belongs to an authored task')
    route = execution_routes.resolve(task['route'], task['features'], execution=task['execution'],
        operation='author' if task['execution']=='authored' else 'prepare')
    plan.strings(task['features'], 'features')
    if bool(task.get('semantic_edit')) != ('semantic-instruction-edit' in route['features']):
        raise ValueError('semantic-instruction-edit requires an explicit semantic_edit plan and vice versa')
    if task.get('semantic_edit') and (task['artifact'] != 'image' or task['execution'] not in {'external', 'dispatcher'}):
        raise ValueError('semantic editing uses an image task with a declared model execution')
    if task.get('semantic_edit') and not task.get('image_input'):
        raise ValueError('semantic editing requires a shared image_input plan')
    if task.get('image_input') and (task['artifact'] != 'image' or task['execution'] not in {'external', 'dispatcher'}):
        raise ValueError('image inputs use an image task with a declared model execution')
    if task['artifact'] == 'image' and task['execution'] == 'external' and not task.get('image_input'):
        raise ValueError('external image tasks require an exact image_input request, including reference-free generation')
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
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'story-context requires selected moment views and vice versa',
            phase='task-contract', pointer='$.moment_views',
            guidance={'document_path': 'references/runtime/story-context.md#use-the-moment-in-production'},
            required_action='Select the verified moment views needed by this task and its matching features. '
                            'When features change, issue the route reading for that selection and apply it to the task.')
    for entries in (task['world_views'], moments):
        keys = [c.content_id(x) for x in entries]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate bounded view selector')
    plan.validate(task['direction'], task['sources'], task['criteria'], task_id=task['task_id'])
    import identity_coverage
    identity_coverage.validate_task(task)
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
            phase='implementation', file=dependency['path'], run=run, expected=dependency.get('selection_sha256', dependency['sha256']), actual=actual,
            required_action='Prepare the task again with the current installation; the creative input is unchanged.')
    if actual is None:
        return ProductionError('SOURCE_CHANGED', 'A live creative source is unavailable.', phase=phase,
                               file=dependency['path'], run=run, expected=dependency.get('selection_sha256', dependency['sha256']), actual=None)
    return ProductionError('SOURCE_CHANGED', 'A live creative source changed after preparation.', phase=phase,
                           file=dependency['path'], run=run, expected=dependency.get('selection_sha256', dependency['sha256']), actual=actual,
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
        from sheet_artifacts import dependency
        dependencies[(space, path)] = dependency(space, path, raw)
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
        issuance = route_reading.require_route_reading(reading, studio=root, routes={task['route']},
                                                       features=task['features'], execution=task['execution'])
    for source in task['sources']:
        add(root, source['path'])
    for source in (task.get('authored_basis') or {}).get('sources', []):
        item = source['file']
        raw = add(root, item['path'])
        if c.digest(raw) != item['sha256'] or len(raw) != item['size']:
            raise ValueError('authored original source differs from its exported bytes: ' + item['path'])
    for source in task.get('upload_sources', []):
        add(root, source['file'])
    plan.validate_variation_bindings(task, {source['id']: c.digest(captured[source['path']]) for source in task['sources']})
    delivery = add(root, task['delivery']['path']).decode('utf-8')
    c.text(delivery, 'delivery')
    held_authority = store.read_authority(root, task['task_id'], required=False)
    authority = mutable(held_authority.document) if held_authority is not None else None
    if held_authority is not None:
        for item in store.captured_authority_inputs(held_authority):
            raw, key = item['raw'], item['sha256']
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
    if generation is not None and generation.get('mask_binding') is not None:
        if 'scene-mask-binding' in checked:
            mask_inputs = checked['scene-mask-binding']['inputs']
        else:
            import scene_mask_planner
            binding = c.decode(add(root, generation['mask_binding']))
            mask_inputs = scene_mask_planner.check_task(root, task, binding, read=lambda path: add(root, path))['inputs']
        for path, raw in mask_inputs.items():
            record('studio', path, raw)
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
    import image_input
    import semantic_edit_plan
    inputs = bounded('image-input', image_input.task_binding)
    semantic_edit = bounded('semantic-edit', lambda base, value, add:
        semantic_edit_plan.task_binding(base, value, add, inputs=inputs))
    if task['execution'] == 'external':
        bounded('external-image-contract', lambda base, value, add:
            image_input.external_documents(base, value, add, inputs=inputs))
    # The installed implementation is pinned by digest; its bytes stay in the installation.
    skill_files = set(implementation_files()) | {r['path'] for r in route['reads']}
    for path in sorted(skill_files):
        key, size = c.file_digest(ROOT, path)
        dependencies[('skill', path)] = {'space': 'skill', 'path': path, 'sha256': key, 'size': size}
    consumer = {'route': task['route'],
                'instructions': delivery, 'criteria': task['criteria'],
                'direction': plan.consumer(task['direction']),
                'world_views': views, 'moment_views': moments, 'authoring_materials': materials}
    if inputs is not None:
        consumer['image_input'] = inputs
    if semantic_edit is not None:
        consumer['semantic_edit'] = semantic_edit
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
    """Find this series at its immutable registration boundary, not by scanning other runs."""
    if predecessor is None:
        return None
    selected = store.latest_run(root, task['task_id'], production_id=task['production_id'], through=predecessor)
    if selected is not None:
        try:
            _, older, _, _ = read_run(root, selected)
        except (ValueError, OSError) as exc:
            raise ProductionError('PREDECESSOR_UNAVAILABLE',
                'The required prior run in this production series is unavailable.', phase='criteria',
                run=selected, cause=str(exc), required_action='Repair this required run; do not skip its protected criteria.') from exc
        if (older['task']['task_id'], older['task']['production_id']) != (task['task_id'], task['production_id']):
            raise ValueError('criteria predecessor differs from its registered ownership')
    return selected


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
        older, newer = read_run(root, expected)[1]['task'], prepared['task']
    before, after = ({x['id']: x for x in t['criteria']} for t in (older, newer))
    if any(before.get(key) != after.get(key) for key in grant['protected_criteria']):
        raise ValueError('protected criterion changed; obtain explicit authority for the change')


def _prepare(root: Path, task_path: str, *, parent: dict | None = None, identity: str | None = None) -> dict:
    """Compile one task and publish only its complete, verified result."""
    from production_compiler import prepare_task
    result = prepare_task(c._root(root), task_path, parent=parent, identity=identity)
    if read_run(root, result['run']).prepared['task']['execution'] == 'authored':
        from production_authored import record_save
        result.update(record_save(root, result['run']))
    return result


@runtime_snapshot.operation
def prepare(root: Path, task: str | None = None, *, choices: str | None = None,
            identity: str | None = None) -> dict:
    """Compile the selected editing source and publish its exact verified input."""
    root = c._root(root)
    if (task is None) == (choices is None):
        raise ValueError('prepare selects exactly one task or editable choices file')
    if choices is None:
        return _prepare(root, task, identity=identity)
    from production_inputs import compile_choices
    from production_compiler import publish_compilation
    compiled = compile_choices(root, choices, persist=True, identity=identity)
    result = publish_compilation(root, compiled)
    if compiled.prepared['task']['execution'] == 'authored':
        from production_authored import record_save
        result.update(record_save(root, result['run']))
    return result


@runtime_snapshot.operation
def save(root: Path, choices: str, *, draft: bool = False) -> dict:
    """Save one authored revision, retaining unfinished choices when requested."""
    from production_authored import save as save_revision
    return save_revision(c._root(root), choices, draft=draft)


@runtime_snapshot.operation
def deliver(root: Path, run: str, receipt: str | None = None, *, destination: str | None = None) -> dict:
    """Deliver exact saved bytes locally, or record an actual external handoff."""
    from production_authored import deliver as record_delivery
    return record_delivery(c._root(root), run, receipt, destination=destination)


@runtime_snapshot.operation
def review_authored(root: Path, run: str, review_file: str) -> dict:
    """Record the observed authored artifact against its independent criteria."""
    from production_authored import review as record_review
    return record_review(c._root(root), run, review_file)


def _validate_publication_content(run: str, prepared: dict, consumer: dict, read_object,
                                  known: dict[str, int]) -> None:
    """Check decoded immutable inputs using evidence supplied by their reader."""
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
    from production_authored import validate_publication
    validate_publication(prepared, consumer, read_object)


def _validate_run_history(run: str, prepared: dict, history, read_object,
                          known: dict[str, int]):
    """Check event meaning once after the storage boundary verifies its chain."""
    if isinstance(history, store.VerifiedHistory):
        if history.scope != run:
            raise ValueError('verified history belongs to another run')
        rows = history.rows
    else:
        rows = history
        store.validate_event_chain(rows, run)
    for row in rows:
        if row['input_sha256'] != prepared['input_sha256'] or row['event'] not in EVENTS:
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'An event belongs to another input or has an undeclared kind.',
                                  phase='integrity', run=run, event=row['sha256'], impact=store.RUN_EVIDENCE_IMPACT,
                                  required_action='Restore the exact committed event from verified evidence; do not recreate approval.')
        if row['event'] == 'dispatch-claim':
            import service_auth
            try:
                authentication = row['data']['authentication']
                if authentication is not None:
                    service_auth.validate_selection(authentication)
            except (KeyError, ValueError, TypeError) as exc:
                raise ProductionError('EVENT_CHAIN_CORRUPT', 'The dispatch claim has an invalid authentication declaration.',
                                      phase='integrity', run=run, event=row['sha256'], impact=store.RUN_EVIDENCE_IMPACT,
                                      required_action='Restore the complete committed dispatch claim.') from exc
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
    state = lifecycle.completion_tail(rows, prepared, run, read_object=read_object)
    for row in rows:
        if row['event'] == 'selection':
            chosen = row['data']['selection']
            reviewed = state.find('review', chosen['review'])
            authorization = state.find('authorization', chosen['authorization'])
            _recorded_selection_basis(prepared, [authorization], row, reviewed)
            if row['data']['selection']['scope'] == 'studio-adoption':
                _recorded_studio_adoption(run, row, rows, read_object)
    return state


def validate_run_content(run: str, prepared: dict, consumer: dict, rows: list[dict], read_object, *,
                         verified: dict[str, int] | None = None) -> None:
    """Verify a complete read-only export without trusting its event provenance.

    The registered store has a separate VerifiedHistory boundary. An ordinary
    list, including an imported export, always receives the full chain check.
    """
    known = {} if verified is None else verified
    store.validate_event_chain(rows, run)
    _validate_publication_content(run, prepared, consumer, read_object, known)
    _validate_run_history(run, prepared, store.VerifiedHistory(run, rows), read_object, known)


def read_run(root: Path, run: str, *, force: bool = False) -> RunView:
    """Share the immutable publication and indexed event history for this read.

    New operations and transactions reacquire current stored contents. Force
    replaces both the retained publication and history at an effect boundary.
    """
    return RunReader(root, _validate_publication_content, _validate_run_history).read(
        run_identifier(run), force=force)


def load_run(root: Path, run: str, *, force: bool = False) -> RunSnapshot:
    """Export independent editable documents from a verified read state.

    Internal projections use read_run and share immutable values. This boundary
    is for callers that need to author changes or deliver an editable export.
    A new operation, transaction or forced read checks the stored state again.
    """
    return read_run(root, run, force=force).snapshot()


def current_sha256(root: Path, dependency: dict, *, read=None) -> str:
    """Hash the current bytes behind one pinned dependency."""
    if read is not None:
        source=read.dependency(dependency)
        raw=source.content
        if not dependency.get('selection_kind'):
            return source.sha256
    else:
        if dependency['space'] == 'skill':
            return c.file_digest(ROOT, dependency['path'])[0]
        raw=c.read(c.local(root,dependency['path']))
    if dependency.get('selection_kind'):
        from sheet_artifacts import selection_bytes
        projection = selection_bytes(dependency['path'], raw)
        if projection is None or projection[0] != dependency['selection_kind']:
            raise ValueError('invalid selection dependency')
        return c.digest(projection[1])
    return c.digest(raw)


@dataclass(frozen=True)
class CurrentRunRead:
    """The actual run and source inputs acquired at one command boundary."""

    view: RunView
    sources: Any
    runtime: runtime_snapshot.FixedRuntimeRead | None
    reference_proofs: tuple


def _current_source_inputs(root: Path, run: str, prepared: dict, *, force: bool = False,
                           previous_runtime: runtime_snapshot.FixedRuntimeRead | None = None):
    """Acquire current inputs and their diagnostics without retaining success."""
    import route_reading
    import runtime_snapshot
    from live_source_read import LiveSourceRead
    sources=LiveSourceRead(root,ROOT,prepared['dependencies'])
    failures=[]
    descriptor=prepared.get('runtime_snapshot')
    fixed=None
    try:
        if descriptor is not None:
            fixed=runtime_snapshot.require_current_read(root,descriptor,run=run,force=force,
                                                        previous=previous_runtime)
    except (ValueError,OSError) as exc:
        failures.append(exc)
    try:
        if descriptor is not None and fixed is None:
            # A live pack error still permits an independent report about the
            # issued route reading. A broken fixed input fails this read too.
            fixed=runtime_snapshot.acquire_runtime(runtime_snapshot.path(root,descriptor),descriptor,
                                                   previous=previous_runtime)
        route_reading.require_route_reading(prepared['route_reading'],studio=root,
            routes={prepared['task']['route']},features=prepared['task']['features'],
            execution=prepared['task']['execution'],
            resource_reader=fixed.read_resource if fixed is not None else None,
            read_source=sources.skill_bytes)
    except (ValueError,OSError) as exc:
        failures.append(exc)
    for dependency in prepared['dependencies']:
        if dependency['space'] == 'evidence': continue
        try: actual=current_sha256(root,dependency,read=sources)
        except (ValueError,OSError) as exc:
            error=freshness_error(dependency,None,run=run)
            error.__cause__=exc
            failures.append(error)
            continue
        if actual!=dependency.get('selection_sha256', dependency['sha256']):
            failures.append(freshness_error(dependency,actual,run=run))
    from studio_reference import ReferenceReads, validate_source
    reference_reads = ReferenceReads()
    proofs=[]
    for source in prepared.get('studio_reference_sources', []):
        try:
            proofs.append(validate_source(source, read=reference_reads.studio(Path(source['studio_root']))))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            failures.append(ProductionError('STUDIO_REFERENCE_CHANGED',
                'The exact accepted Studio reference is no longer current or verifiable.',
                phase='source-freshness', run=run, file=source['sheet'], expected=source['proof_sha256'],
                character=source['character'], slot=source['slot'], artifact_id=source['artifact_id'],
                required_action='Select the current accepted artwork and prepare a new approved request; resume a sent run to recover its recorded result.',
                cause=str(exc)))
    return sources,fixed,tuple(proofs),failures


def _freshness_failures(root: Path, run: str, prepared: dict, *, rows: list[dict] | None = None,
                        force: bool = False,
                        previous_runtime: runtime_snapshot.FixedRuntimeRead | None = None):
    """Inspect every current source and return failures in their check order."""
    yield from _current_source_inputs(root,run,prepared,force=force,previous_runtime=previous_runtime)[3]


def read_current(root: Path, run: str, *, force: bool = False,
                 previous_runtime: runtime_snapshot.FixedRuntimeRead | None = None) -> CurrentRunRead:
    """Acquire actual live inputs for one command or external effect boundary.

    Internal steps receive these values explicitly. Another call checks actual
    current bytes again, including after a failed earlier acquisition. A prior
    runtime can supply immutable metadata only after its actual bytes match.
    """
    loaded=read_run(root,run,force=force)
    sources,fixed,proofs,failures=_current_source_inputs(root,run,loaded.prepared,force=force,
                                                      previous_runtime=previous_runtime)
    if failures:
        raise failures[0]
    return CurrentRunRead(loaded,sources,fixed,proofs)


def assert_current(root: Path, run: str, *, force: bool = False,
                   previous_runtime: runtime_snapshot.FixedRuntimeRead | None = None) -> RunView:
    """The loaded run after acquiring and checking its actual current sources.

    `force` loads the run and checks its live sources again, even inside a
    caller's transaction, as the check before an external effect does.
    """
    # Event evidence is checked against owned snapshots by read_run, not its
    # deletable provenance locator. Current grants are checked separately.
    return read_current(root,run,force=force,previous_runtime=previous_runtime).view


def freshness_diagnostics(root: Path, run: str, *, loaded: tuple | None = None,
                          previous_runtime: runtime_snapshot.FixedRuntimeRead | None = None) -> list[dict]:
    """Every freshness problem of the run's live sources as a diagnostic, without stopping at the first."""
    from production_diagnostics import from_exception
    loaded=loaded or read_run(root,run)
    return [from_exception(failure,phase='freshness') for failure in
            _freshness_failures(root,run,loaded[1],rows=loaded[3],previous_runtime=previous_runtime)]


def require_mutable(records: list[dict]) -> None:
    if any(row['event'] == 'completion' for row in records):
        raise ValueError('run is complete; prepare a new run for further work')


def append_record(directory: Path, prepared: dict, records: list[dict], event: str, data: dict) -> dict:
    for row in reversed(records):
        if row['event']==event and row['data']==data:return row
    if event not in EVENTS:raise ValueError('unknown production event')
    root=directory.parents[2]
    scope = runtime_snapshot.check_scope(root)
    held = None if scope is None else scope.get(('verified-run', str(root.resolve()), directory.name))
    owned_values = held is not None and held.rows is records and held.prepared is prepared
    state = held.lifecycle if owned_values and held.lifecycle is not None else records
    read_object = held.evidence.read if held is not None else lambda sha: c.object_read(directory, sha)
    lifecycle.validate_transition(state, prepared, directory.name, event, data, read_object=read_object)
    previous=records[-1]['sha256'] if records else None
    return store.append(root,directory.name,prepared['input_sha256'],event,data,
                        expected_previous=previous,check_previous=True)


def find(records: list[dict], event: str, identifier: str | None = None) -> dict:
    if isinstance(records, lifecycle.EventHistory):
        return records.lifecycle.find(event, identifier)
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



def current_authority(root: Path, prepared: dict) -> store.CurrentAuthority:
    """Acquire the current grant state independently of frozen run input."""
    return store.read_authority(root, prepared['task']['task_id'])


@runtime_snapshot.operation
def authorization_context(root: Path, run: str, operation: str) -> tuple[RunView, store.CurrentAuthority]:
    loaded = read_run(root, run) if operation in {'edit', 'select', 'adopt'} else assert_current(root, run)
    return loaded, current_authority(root, loaded.prepared)


@runtime_snapshot.operation
def authorize(root: Path, run: str, request_file: str) -> dict:
    raw = store.stable_bytes(root, request_file)
    return authorize_value(root, run, c.decode(raw), evidence_files=[request_file],
                           expected_source=(request_file, c.digest(raw)))


def require_open_task(rows: list[dict], run: str) -> None:
    """An abandoned work task starts no new production operation."""
    if any(row['event'] == 'abandoned' for row in rows):
        raise ProductionError('TASK_ABANDONED', 'The work task of this run was abandoned; its production decisions are closed.',
                              phase='authorization', run=run,
                              required_action='Open a new work task for new production. Recorded effects remain recoverable; '
                                              'the selected candidate may be adopted under a separate current adopt grant.')


def protected_criteria_record(prepared: dict, authority: dict, grant_id: str) -> dict:
    """The criteria a grant protects, by ID and by the digest of their current definitions."""
    grants = [g for g in authority['grants'] if g['id'] == grant_id]
    ids = sorted(grants[0]['protected_criteria']) if len(grants) == 1 else []
    criteria = {x['id']: x for x in prepared['task']['criteria']}
    return {'ids': ids, 'sha256': c.content_id([criteria.get(key) for key in ids])}


@runtime_snapshot.operation
def authorize_value(root: Path, run: str, request: dict, *, evidence_files: list[str],
                    expected_source: tuple[str, str] | None = None) -> dict:
    """Store actual supplied decisions through the same API used by every CLI.

    Each evidence file is read once and stored with its locator, capture time
    and purpose. Approval evidence is kept by path and SHA-256, so a cited
    reading of a growing ledger stays valid after later appends.
    """
    with store.transaction(root):
        loaded, authority = authorization_context(root, run, request.get('operation'))
        return _authorize_value_from(root, loaded, authority, request,
                                     evidence_files=evidence_files, expected_source=expected_source)


def _authorize_value_from(root: Path, loaded: RunView, authority: store.CurrentAuthority,
                          request: dict, *, evidence_files: list[str],
                          expected_source: tuple[str, str] | None = None) -> dict:
    """Record supplied decisions from this transaction's acquired input values."""
    run = loaded.prepared['run']
    directory, prepared, consumer, rows = loaded
    grants = authority.document
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
        matches = [g for g in grants['grants'] if g['id'] == request['grant']]
        if len(matches) != 1:
            raise ProductionError('GRANT_REVOKED', 'Select one current grant.', phase='authorization', grant=request['grant'],
                                  required_action='Select a grant that the current authority declares.')
        _, witnesses = check_authorization(root, prepared, request, matches[0], authority=authority)
        held = {(item['path'], item['sha256']) for item in files}
        for item in witnesses:
            if (item['path'], item['sha256']) in held:
                continue
            held.add((item['path'], item['sha256']))
            files.append(store.capture_evidence(root, directory, item['path'], locator=item['locator'],
                                                purpose=item['purpose'], raw=item['raw'], rows=rows))
    elif (prepared['task']['execution'] == 'external' and prepared['task']['artifact'] == 'image'
            and request['operation'] == 'submit'):
        from production_request import check_external_authorization
        grant = permissions.check(grants, request)
        check_external_authorization(consumer, request, grant)
    elif request.get('request_decision') is not None:
        raise ValueError('only a model image submission carries a model request decision')
    if request['operation'] == 'select':
        selection = {**request['payload'], 'authorization': '0' * 64}
        schema_check(selection, 'selection')
        if selection['selector'] != request['actor']:
            raise ValueError('selector differs from the authorized actor')
        acceptance = selection['owner_acceptance']
        if acceptance is not None:
            for witness in _owner_acceptance_witnesses(root, prepared, authority, acceptance):
                files.append(store.capture_evidence(root, directory, witness['path'], locator=witness['locator'],
                    purpose='owner-acceptance', raw=witness['raw'], rows=rows))
    data = {'files': files, 'request': request,
            'authority': {'event': authority.event['sha256'], 'issuer': grants['issuer']},
            'protected_criteria': protected_criteria_record(prepared, grants, request['grant'])}
    for row in rows:
        if row['event'] == 'authorization' and row['data'] == data:
            return row
    lifecycle.require_operation(rows, prepared, run, request['operation'], request['targets'], request['payload'])
    grant = permissions.check(grants, request)
    if request['operation'] == 'direction':
        validate_protected_criteria(root, prepared, grant)
    return append_record(directory, prepared, rows, 'authorization', data)


def _permission(root: Path, prepared: dict, rows: list[dict], identifier: str,
                operation: str, targets: list[str], payload: dict, *,
                authority: store.CurrentAuthority | None = None, loaded: RunView | None = None) -> dict:
    authority = authority or current_authority(root, prepared)
    if authority.task_id != prepared['task']['task_id']:
        raise ValueError('current authority belongs to another work task')
    grants = authority.document
    row = find(rows, 'authorization', identifier)
    request = row['data']['request']
    compare_exact({'operation':operation,'targets':sorted(targets),'payload':payload},
                  {'operation':request['operation'],'targets':sorted(request['targets']),'payload':request['payload']},
                  intent={'operation': operation, 'targets': sorted(targets), 'run': prepared['run'], 'authorization': identifier})
    lifecycle.require_operation(rows, prepared, prepared['run'], operation, targets, payload)
    grant = permissions.check(grants, request)
    if operation == 'direction':
        validate_protected_criteria(root, prepared, grant)
    if operation == 'submit' and prepared['task']['execution'] == 'dispatcher':
        from production_request import check_authorization
        read_object = (loaded or read_run(root, prepared['run'])).evidence.read
        recorded = [(item['path'], read_object(item['sha256'])) for item in row['data']['files']]
        check_authorization(root, prepared, request, grant, authority=authority, recorded=recorded)
    elif (operation == 'submit' and prepared['task']['execution'] == 'external'
            and prepared['task']['artifact'] == 'image'):
        from production_request import check_external_authorization
        consumer = (loaded or read_run(root, prepared['run'])).consumer
        check_external_authorization(consumer, request, grant)
    elif operation == 'select' and request['payload']['owner_acceptance'] is not None:
        acceptance = request['payload']['owner_acceptance']
        if acceptance['principal'] != grants['issuer']:
            raise ValueError('owner acceptance does not name the current authority issuer')
        _require_owner_witness(acceptance, row)
    return request


@runtime_snapshot.operation
def abandon_task(root: Path, task_id: str, *, actor: str, reason: str) -> list[dict]:
    """Record that a work task stops, as an `abandoned` event on each of its open runs.

    The event data is `{"actor": ..., "reason": ...}`. Claims and unknown
    outcomes remain recorded; recovery preserves every received result.
    A completed run keeps its completion. Returns the abandoned event of each run.
    """
    c.text(actor, 'abandoning actor')
    c.text(reason, 'abandon reason')
    data = {'actor': actor, 'reason': reason}
    recorded = []
    with store.transaction(root):
        for item in store.runs(root, task_id=task_id):
            directory, prepared, _, rows = read_run(root, item['run_id'])
            if any(row['event'] == 'completion' for row in rows):
                continue
            prior = [row for row in rows if row['event'] == 'abandoned']
            recorded.append(prior[-1] if prior else append_record(directory, prepared, rows, 'abandoned', data))
    return recorded


@runtime_snapshot.operation
def handoff_intent(root: Path, run: str, recipient: str, method: str) -> dict:
    return _handoff_intent_from(assert_current(root, run), recipient, method)


def _handoff_intent_from(loaded: RunView, recipient: str, method: str) -> dict:
    _, prepared, consumer, _ = loaded
    c.text(recipient, 'recipient')
    if method not in {'conversation', 'manual', 'dispatcher'}:
        raise ValueError('invalid handoff method')
    if (method == 'dispatcher') != (prepared['task']['execution'] == 'dispatcher'):
        raise ValueError('handoff method differs from the declared execution mode')
    if prepared['task']['execution'] == 'dispatcher':
        execution_plan = loaded.artifacts['execution-plan.json']
        compare_exact({key: execution_plan['handoff'][key] for key in ('recipient', 'method')},
                      {'recipient': recipient, 'method': method}, pointer='$.handoff')
    return {'operation': 'direction', 'targets': plan.direction_targets(prepared['task']),
            'payload': {'consumer_sha256': c.content_id(consumer), 'recipient': recipient, 'method': method}}


@runtime_snapshot.operation
def handoff(root: Path, run: str, recipient: str, method: str, authorization: str, *,
            journal: Path | None = None) -> dict:
    """Record a handoff that has happened.

    A dispatcher receives the consumer when execute copies it into the dispatch
    journal, so a dispatcher handoff names that journal and is recorded by execute.
    """
    with store.transaction(root):
        loaded = assert_current(root, run)
        authority = current_authority(root, loaded.prepared)
        return _handoff_from(root, loaded, authority, recipient, method, authorization, journal=journal)


def _handoff_from(root: Path, loaded: RunView, authority: store.CurrentAuthority,
                  recipient: str, method: str, authorization: str, *, journal: Path | None = None) -> dict:
    """Record the performed handoff using this command's current source values."""
    directory, prepared, _, rows = loaded
    run = prepared['run']
    intent = _handoff_intent_from(loaded, recipient, method)
    if method == 'dispatcher':
        copied = None if journal is None else Path(journal) / 'consumer.json'
        expected = next(item for item in loaded.manifest['files'] if item['path'] == 'consumer.json')
        if copied is None or not copied.is_file() or c.digest(c.read(copied)) != expected['sha256']:
            raise ProductionError('HANDOFF_NOT_PERFORMED', 'The dispatcher has not received the consumer.',
                                  phase='handoff', run=run,
                                  required_action=f'Run python scripts/production_workflow.py execute --root ROOT --run {run}; '
                                                  'it records the dispatcher handoff when it hands the consumer over.')
    _permission(root, prepared, rows, authorization, **intent, authority=authority, loaded=loaded)
    data = {**intent['payload'], 'authorizations': [authorization]}
    prior = [r for r in rows if r['event'] == 'handoff']
    if prior and prior[0]['data'] != data:
        raise ValueError('run already has a different handoff')
    return lifecycle.commit_effect(root,run,'handoff',data,[authorization],effect='external-handoff')


@runtime_snapshot.operation
def external_intent(root: Path, run: str, count: int) -> dict:
    return _external_intent_from(root, assert_current(root, run), count)


def _external_intent_from(root: Path, loaded: RunView, count: int) -> dict:
    _, prepared, consumer, rows = loaded
    if prepared['task']['execution'] != 'external':
        raise ValueError('task is not an external execution')
    hand = find(rows, 'handoff')
    if type(count) is not int or count < 1:
        raise ValueError('positive output count required')
    payload = {'consumer_sha256': c.content_id(consumer), 'recipient': hand['data']['recipient'], 'count': count}
    if consumer.get('image_input'):
        from image_input import require_live
        binding = consumer['image_input']
        require_live(root, prepared['task'], binding)
        external = binding['external_request']
        if count != external['count']:
            raise ValueError('external claim count differs from the image input request')
        payload.update(image_input_sha256=binding['binding_sha256'], external_request_sha256=external['sha256'],
                       target=binding['model']['target'])
    return {'operation': 'submit', 'targets': ['delivery'], 'payload': payload}


@runtime_snapshot.operation
def claim_external(root: Path, run: str, count: int, authorization: str) -> dict:
    """Commit the handoff-to-host boundary before the host invokes its tool.

    Returning a claim never proves the host obtained a result. Re-reading the
    same receipt is idempotent; it is not permission to invoke the tool twice.
    """
    with store.transaction(root):
        loaded = assert_current(root, run)
        authority = current_authority(root, loaded.prepared)
        return _claim_external_from(root, loaded, authority, count, authorization)


def _claim_external_from(root: Path, loaded: RunView, authority: store.CurrentAuthority,
                         count: int, authorization: str) -> dict:
    """Claim a host invocation from the command's current inputs and authority."""
    directory, prepared, _, rows = loaded
    run = prepared['run']
    intent = _external_intent_from(root, loaded, count)
    request = _permission(root, prepared, rows, authorization, **intent, authority=authority, loaded=loaded)
    data = {**intent['payload'], 'authorizations': [authorization]}
    previous = [r for r in rows if r['event'] == 'external-claim']
    if previous:
        if previous[0]['data'] != data:
            raise ProductionError('DISPATCH_ALREADY_CLAIMED',
                'An external tool call is already claimed; recover it, or prepare a new run for a new call.',
                phase='before-send', run=run)
        return previous[0]
    lifecycle._claim_execution_from(root, loaded, authority, authorization)
    claim = lifecycle.commit_effect(root, run, 'external-claim', data, [authorization], effect='external-handoff')
    lifecycle.begin_step(root, run, authorization, claim=claim['sha256'],
                         step='external-send', operation='send')
    return claim


@runtime_snapshot.operation
def capture(root: Path, run: str, artifact: str, note: str) -> dict:
    c.text(note, 'candidate provenance')
    loaded = read_run(root, run)
    raw = store.stable_bytes(root, artifact)
    item = {'path': artifact, 'sha256': c.object_store(loaded.directory, raw), 'size': len(raw)}
    measured = media.inspect(raw, loaded.prepared['task']['artifact'])
    with store.transaction(root):
        directory, prepared, _, rows = read_run(root, run)
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
        if execution == 'external':
            claim = find(rows, 'external-claim')
            previous = [row for row in rows if row['event'] == 'candidate']
            same = [row for row in previous if any(f['sha256'] == item['sha256'] for f in row['data']['files'])]
            if same:
                return same[0]
            states = lifecycle.derive(rows, prepared, run)
            if any(state['status'] == 'complete' for state in states.values()):
                raise ProductionError('SETTLEMENT_CONFLICT', 'The external result was finalized; a new output cannot alter that receipt.', phase='capture', run=run)
            if len(previous) >= claim['data']['count']:
                raise ValueError('external output count exceeds its authorization')
        return append_record(directory, prepared, rows, 'candidate',
                             {'handoff': hand['sha256'], 'files': [item], 'media': measured, 'note': note})


@runtime_snapshot.operation
def receive_external(root: Path, run: str, *, response_file: str, artifacts: list[str] | None = None,
                     image_pointers: list[list[str | int]] | None = None, final: bool, reason: str,
                     submission_file: str | None = None, request_pointer: list[str | int] | None = None,
                     model_identity_pointer: list[str | int] | None = None,
                     cost_pointer: list[str | int] | None = None) -> dict:
    """Receive actual host results; derive hashes, counts and the result receipt."""
    from production_external import receive_external as receive
    return receive(root, run, response_file=response_file, artifacts=artifacts, image_pointers=image_pointers,
                   final=final, reason=reason, submission_file=submission_file, request_pointer=request_pointer,
                   model_identity_pointer=model_identity_pointer, cost_pointer=cost_pointer)


def _review_delivered_reference_evidence(directory: Path, run: str, package: dict | None,
                                        read_object, binding: dict | None = None) -> list[dict]:
    """Expose saved delivery carriers without reopening their original sources."""
    external = binding.get('external_request') if binding is not None else None
    prefix = 'production/runs/' + run + '/'
    if external is not None:
        prepared = binding.get('prepared_reference_set')
        origin = prefix + 'consumer.json#/image_input/prepared_reference_set'
    else:
        if package is None:
            return []
        prepared = package.get('prepared_reference_set')
        origin = prefix + 'package.json#/prepared_reference_set'
    if prepared is None:
        return []
    from reference_delivery import bindings
    scopes = bindings(prepared['transport_mode'], prepared['selected_references'], prepared['single_board'])
    if not scopes:
        return []
    paths = {}
    if external is not None:
        for reference, scope, field in zip(prepared['selected_references'], scopes,
                                            external['reference_fields'], strict=True):
            carrier = prepared['single_board'] if prepared['transport_mode'] == 'single-board' else reference['transport']
            number = scope['attachment_number']
            if number not in paths:
                read_object(carrier['sha256'])
                paths[number] = prefix + 'objects/' + carrier['sha256']
            scope['request_field'] = list(field['field'])
    else:
        from prepare_generation_references import host_reference_transports
        for number, carrier in enumerate(host_reference_transports(prepared, package_root=directory), 1):
            relative = Path(carrier['resolved_path']).resolve().relative_to(directory.resolve()).as_posix()
            if c.digest(c.read(c.local(directory, relative))) != carrier['sha256']:
                raise ValueError('prepared review carrier checksum mismatch')
            paths[number] = prefix + relative
    evidence = []
    for index, (reference, scope) in enumerate(zip(prepared['selected_references'], scopes, strict=True)):
        provenance = origin + '/selected_references/' + str(index)
        evidence.append({'id': 'delivered-reference:' + str(index + 1),
            'path': paths[scope['attachment_number']], 'kind': 'image',
            'relation': 'Compare this prepared delivery carrier using its source assignment: '
                        + json.dumps({'delivery': scope, 'source': reference['source'],
                                      'derivation': reference['transport']['derivation']},
                                     ensure_ascii=False, sort_keys=True),
            'limitations': ['This item preserves prepared delivery pixels, which may be a crop, rasterization or board. '
                            'Original source and transform: ' + provenance + '. '
                            'Use recorded submission evidence to establish the actual host call.']})
    return evidence


def _review_identity_evidence(run: str, prepared: dict, read_object) -> list[dict]:
    """Keep original identity owners available independently of their rendition."""
    evidence = []
    prefix = 'production/runs/' + run + '/objects/'
    for source in prepared.get('identity_coverage', {}).get('sources', []):
        raw = read_object(source['sha256'])
        kind = source['format'] if source['format'] in media.KINDS else 'binary'
        if kind in {'text', 'binary'}:
            try:
                media.inspect(raw, 'image')
            except ValueError:
                pass
            else:
                kind = 'image'
        scope = {key: source[key] for key in
                 ('id', 'path', 'source_pointer', 'subject_ids', 'selectors')}
        evidence.append({'id': 'identity-source:' + source['id'],
            'path': prefix + source['sha256'],
            'kind': kind,
            'relation': 'Compare the original identity source in its authored scope: '
                        + json.dumps(scope, ensure_ascii=False, sort_keys=True),
            'limitations': ['The saved original defines the comparison basis. Its selected scene treatments '
                            'and actual-input carriers are recorded in identity_coverage; neither establishes '
                            'what the candidate visibly preserves.']})
    return evidence


def _review_reference_evidence(directory: Path, run: str, consumer: dict, prepared: dict, *,
                               artifacts: dict, read_object) -> list[dict]:
    """Make original identity and prepared image references available at saved bytes."""
    evidence = _review_identity_evidence(run, prepared, read_object)
    package = artifacts.get('package.json')
    binding = consumer.get('image_input')
    if binding is None:
        return evidence + _review_delivered_reference_evidence(directory, run, package, read_object)
    from image_input import request_context
    prefix = 'production/runs/' + run + '/'
    for index, reference in enumerate(request_context(binding)['references']):
        read_object(reference['sha256'])
        scope = {'role': reference['role'], 'use_for': reference['use_for'],
                 'do_not_transfer': reference['do_not_transfer'],
                 'subject_uses': reference.get('subject_uses', [])}
        if 'subject_id' in reference:
            scope['subject_id'] = reference['subject_id']
        if binding['external_request'] is not None:
            carrier = prefix + 'consumer.json#/image_input/external_request/reference_fields/' + str(index)
            if binding.get('prepared_reference_set') is not None:
                carrier += '; prepared media: ' + prefix + 'consumer.json#/image_input/prepared_reference_set'
        else:
            carrier = prefix + 'package.json#/prepared_reference_set'
        evidence.append({'id': 'input-reference:' + reference['id'],
            'path': prefix + 'objects/' + reference['sha256'],
            'kind': 'image',
            'relation': 'Compare this prepared source within its assigned scope: '
                        + json.dumps(scope, ensure_ascii=False, sort_keys=True),
            'limitations': ['This item preserves source pixels. Compare delivered media and its assignment at ' + carrier + '.']})
    evidence.extend(_review_delivered_reference_evidence(directory, run, package, read_object, binding))
    return evidence


def _review_criterion(task: dict, criterion: dict, craft_questions: list[str]) -> dict:
    """Expose the prepared criterion and its chosen means without authoring a verdict."""
    realizations = []
    for decision in task['direction']['decisions']:
        if criterion['id'] not in decision['criteria']:
            continue
        selected = next(option for option in decision['options'] if option['id'] == decision['selected'])
        realizations.append({'decision': decision['id'], 'expression': selected['expression'],
            'instructions': selected['realization']['instructions'], 'basis': decision['basis'],
            'accepted_variations': [variation for variation in decision.get('accepted_variations', [])
                                    if criterion['id'] in variation['criteria']]})
    return {**criterion, 'realizations': realizations, 'craft_questions': craft_questions}


@runtime_snapshot.operation
def review_basis(root: Path, run: str, candidate: str | None = None) -> dict:
    """Read frozen assessment context separately from the reviewer's editable answers."""
    loaded = read_run(root, run)
    directory, prepared, consumer, rows = loaded
    if prepared['task']['execution'] == 'authored':
        if candidate is not None:
            raise ValueError('an authored review assesses its saved revision')
        from production_authored import review_basis as authored_basis
        return authored_basis(loaded)
    if candidate is not None:
        find(rows, 'candidate', candidate)
    from craft_consultation import review_questions
    questions = review_questions(root, prepared['task'], directory=directory, dependencies=prepared['dependencies'])
    task = prepared['task']
    result = {'purpose': task['direction']['purpose'], 'intended_effect': task['direction']['intended_effect'],
              'criteria': [_review_criterion(task, item, questions.get(item['id'], [])) for item in task['criteria']],
              'evidence': _review_reference_evidence(directory, run, consumer, prepared,
                  artifacts=loaded.artifacts, read_object=loaded.evidence.read)}
    if 'identity_coverage' in prepared:
        result['identity_coverage'] = prepared['identity_coverage']
        result['identity_instruction'] = (
            'Use applicable adopted identity definitions, conditions and relations from the frozen '
            'originals for every subject and scope they govern, including definitions carried into later '
            'requests. Assess their authored meaning, scope and importance, keeping necessary identity '
            'obligations strict. Compare each whole depicted subject with the frozen originals '
            'independently of the prompt and extracted criteria. Use the coverage map to trace each '
            'treatment into its actual text or reference carrier. Judge selected treatments by how they '
            'realize the source requirements; coherent alternatives can satisfy the same criterion. '
            'Record a pass when the candidate meets the criterion, and record shortfalls and uncertainty '
            'at their affected scope, including findings beyond the extracted criteria. Retain original '
            'definitions for not-exposed and not-applicable scopes, and describe the scene treatment and '
            'visibility limits. Place nonblocking uncertainty in observations, limitations or advisory '
            'checks, and offer useful optional repairs as proposals. Reserve review.unresolved for '
            'questions that need resolution or explicit acceptance to select the candidate against the '
            'required outcome. Resolve an authored unresolved binding at its owning source or scene '
            'choice, then prepare the revised input.')
    return result


@runtime_snapshot.operation
def draft_review(root: Path, run: str, candidate: str | None = None) -> dict:
    _, prepared, _, rows = read_run(root, run)
    if prepared['task']['execution'] == 'authored':
        if candidate is not None:
            raise ValueError('an authored review assesses its saved revision')
        from production_authored import draft_review as authored_draft
        return authored_draft(prepared)
    if candidate is None:
        raise ValueError('a generated result review requires its candidate')
    find(rows, 'candidate', candidate)
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate, 'reviewer': '',
            'evidence': [], 'observations': [],
            'checks': [{'criterion': x['id'], 'verdict': 'not-assessed', 'observation_indices': [],
                        'reason': ''}
                       for x in prepared['task']['criteria']],
            'repairs': [], 'unresolved': [], 'conclusion': ''}


def _unresolved_identity_criteria(prepared: dict) -> set[str]:
    """Use effective source coverage, including narrower authored treatments."""
    report = prepared.get('identity_coverage', {})
    criteria, subjects = set(), set()
    bindings = report.get('bindings', [])
    for source in report.get('sources', []):
        for terminal in source['terminals']:
            for coverage in terminal['coverage']:
                if coverage['treatment'] != 'unresolved':
                    continue
                subjects.add(coverage['subject_id'])
                criteria.update(bindings[index]['criterion'] for index in coverage['bindings'])
    criteria.update(row['criterion'] for row in report.get('whole_reviews', [])
                    if subjects.intersection(row['subject_ids']))
    return criteria


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
    unresolved_identity = _unresolved_identity_criteria(prepared)
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
        if check['verdict'] == 'pass':
            if check['criterion'] in unresolved_identity:
                raise ValueError('an unresolved identity obligation cannot support a passing review criterion')
            criterion = expected[check['criterion']]
            if (criterion.get('identity_review') or criterion.get('identity_bindings')) and not any(
                    data['observations'][i]['evidence'] == 'candidate' and requirement in supported[i]
                    for i in indices):
                raise ValueError('a passing identity review must cite the actual candidate in the required medium')
    # Omitted criteria remain unassessed. Selection separately requires a
    # supported pass or an explicit owner allowance for each assessed nonpass.
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


@runtime_snapshot.operation
def review(root: Path, run: str, review_file: str) -> dict:
    with store.transaction(root):
        loaded = read_run(root, run)
        directory, prepared, consumer, rows = loaded
        item = file_record(root, directory, review_file)
        data = c.decode(c.object_read(directory, item['sha256']))
        schema_check(data, 'review')
        candidate = find(rows, 'candidate', data['candidate'])
        data['evidence'] = _review_reference_evidence(directory, run, consumer, prepared,
            artifacts=loaded.artifacts, read_object=loaded.evidence.read) + data['evidence']
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


def selection_requirements(prepared: dict, reviewed: dict) -> dict:
    """Derive remaining decisions without changing the recorded assessment."""
    data = reviewed['data']['review']
    hard = {item['id'] for item in prepared['task']['criteria'] if item['strength'] == 'hard'}
    checks = {item['criterion']: item['verdict'] for item in data['checks']}
    return {
        'unassessed_hard_criteria': sorted(key for key in hard if checks.get(key, 'not-assessed') == 'not-assessed'),
        'nonpassing_hard_criteria': sorted(key for key in hard if checks.get(key) in {'fail', 'indeterminate', 'not-applicable'}),
        'unresolved_indices': list(range(len(data['unresolved']))),
    }


def eligible(prepared: dict, reviewed: dict, owner_acceptance: dict | None = None) -> str:
    """Check the exact selection basis; an allowance never changes a verdict."""
    needed = selection_requirements(prepared, reviewed)
    if needed['unassessed_hard_criteria']:
        raise ProductionError('REVIEW_INCOMPLETE', 'Required criteria have not been assessed: ' +
                              ', '.join(needed['unassessed_hard_criteria']), phase='selection',
                              required_action='Observe and review each unassessed required criterion before selection.')
    accepted_criteria, accepted_issues = set(), set()
    if owner_acceptance is not None:
        # The formal selection schema owns the complete shape. This check also
        # serves callers deriving eligibility directly from an authored basis.
        acceptance_schema = c.load(ROOT / 'schemas/authoring/production-selection.schema.json')['$defs']['owner_acceptance']
        from state_protocol import validate_against_schema
        errors = validate_against_schema(owner_acceptance, acceptance_schema)
        if errors:
            raise ValueError('owner acceptance: ' + '; '.join(errors))
        accepted_criteria = set(owner_acceptance['criteria'])
        accepted_issues = set(owner_acceptance['unresolved_indices'])
        checks = {item['criterion']: item['verdict'] for item in reviewed['data']['review']['checks']}
        if any(checks.get(key) not in {'fail', 'indeterminate', 'not-applicable'} for key in accepted_criteria):
            raise ValueError('owner acceptance must name explicitly assessed nonpassing criteria')
        if accepted_issues - set(needed['unresolved_indices']):
            raise ValueError('owner acceptance names an unknown unresolved issue')
        if not accepted_criteria and not accepted_issues:
            raise ValueError('owner acceptance must identify an assessed exception or unresolved issue')
    missing = sorted(set(needed['nonpassing_hard_criteria']) - accepted_criteria)
    unresolved = sorted(set(needed['unresolved_indices']) - accepted_issues)
    if missing or unresolved:
        raise ProductionError('OWNER_ACCEPTANCE_REQUIRED',
                              'Selection needs explicit owner acceptance of the recorded exceptions.',
                              phase='selection', criteria=missing, unresolved_indices=unresolved,
                              required_action='Record the owner\'s explicit allowance for these reviewed exceptions, '
                                              'or continue the authorized work; do not rewrite their verdicts as passes.')
    return 'owner-allowance' if owner_acceptance is not None else 'review-pass'


def _owner_acceptance_witnesses(root: Path, prepared: dict, authority: store.CurrentAuthority,
                                acceptance: dict) -> list[dict]:
    """Capture an explicitly cited owner instruction; do not infer its meaning."""
    if authority.task_id != prepared['task']['task_id']:
        raise ValueError('current authority belongs to another work task')
    if acceptance['principal'] != authority.document['issuer']:
        raise ValueError('owner acceptance does not name the current authority issuer')
    from production_request import EvidenceWitnesses
    items = [(item['path'], item['raw']) for item in store.captured_authority_inputs(authority)]
    reader = EvidenceWitnesses(root, items, live=True, run=prepared['run'])
    ref = acceptance['evidence']
    raw = reader.basis(ref)
    return [{**ref, 'raw': raw}]


def _require_owner_witness(acceptance: dict, authorization: dict) -> dict:
    """The authorizing event must retain the exact cited reading as evidence."""
    ref = acceptance['evidence']
    matches = [item for item in authorization['data']['files']
               if item.get('purpose') == 'owner-acceptance'
               and all(item.get(key) == ref[key] for key in ('path', 'sha256', 'locator'))]
    if not matches:
        raise store.evidence_error('EVIDENCE_SNAPSHOT_MISSING',
                                  'The selection authorization holds no saved owner-acceptance witness.',
                                  file=ref['path'], expected=ref['sha256'], event=authorization['sha256'])
    return matches[0]


def _recorded_selection_basis(prepared: dict, rows: list[dict], selection: dict, reviewed: dict) -> str:
    """Validate a saved effect without renewing the grant that already authorized it.

    read_run verifies every saved evidence object's bytes. This verifies the
    exact authorization link and witness attribution within that verified log.
    """
    chosen = selection['data']['selection']
    schema_check(chosen, 'selection')
    if chosen['input_sha256'] != prepared['input_sha256'] or reviewed['sha256'] != chosen['review'] \
            or reviewed['data']['candidate'] != chosen['candidate']:
        raise ValueError('selection belongs to another input, candidate or review')
    authorization = find(rows, 'authorization', chosen['authorization'])
    request = authorization['data']['request']
    compare_exact(selection_intent(chosen), {key: request[key] for key in ('operation', 'targets', 'payload')},
                  phase='selection')
    if request['actor'] != chosen['selector']:
        raise ValueError('selector differs from the recorded authorized actor')
    if authorization['sequence'] >= selection['sequence'] or reviewed['sequence'] >= selection['sequence']:
        raise ValueError('selection must follow its recorded review and authorization')
    acceptance = chosen['owner_acceptance']
    if acceptance is not None:
        if acceptance['principal'] != authorization['data']['authority']['issuer']:
            raise ValueError('owner acceptance does not name the recorded authority issuer')
        _require_owner_witness(acceptance, authorization)
    return eligible(prepared, reviewed, acceptance)


def latest_review(rows: list[dict], candidate: str) -> dict:
    if isinstance(rows, lifecycle.EventHistory):
        row = rows.lifecycle.review(candidate)
        if row is None:
            raise ValueError('candidate has no recorded review')
        return row
    found = [r for r in rows if r['event'] == 'review' and r['data']['candidate'] == candidate]
    if not found:
        raise ValueError('candidate has no recorded review')
    return found[-1]


def review_evaluation(criteria: list[dict], review: dict | None) -> tuple[str, list[str]]:
    """Summarize actual criterion coverage without treating a review event as a verdict."""
    expected = {item['id'] for item in criteria}
    checks = review['checks'] if review is not None else []
    verdicts = {item['verdict'] for item in checks}
    assessed = {item['criterion'] for item in checks if item['verdict'] != 'not-assessed'}
    unassessed = sorted(expected - assessed)
    if not assessed:
        evaluation = 'unreviewed'
    elif 'fail' in verdicts:
        evaluation = 'nonconforming'
    elif 'indeterminate' in verdicts or review['unresolved']:
        evaluation = 'indeterminate'
    elif unassessed:
        evaluation = 'partially_reviewed'
    else:
        evaluation = 'conforming'
    return evaluation, unassessed


@runtime_snapshot.operation
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
    _, prepared, _, rows = loaded if loaded is not None else read_run(root, run)
    state = lifecycle._indexed(rows, prepared, run)
    chosen = state.find('candidate', candidate)
    latest = state.review(candidate)
    evaluation, unassessed = review_evaluation(
        prepared['task']['criteria'], latest['data']['review'] if latest else None)
    decision = state.decision(candidate)
    disposition_value = ('pending' if decision is None else 'selected' if decision['event'] == 'selection'
                         else decision['data']['disposition']['disposition'])
    decision_data = decision['data'].get('disposition', decision['data'].get('selection')) if decision else None
    diagnostics = []
    selection_basis = None
    owner_acceptance = None
    if disposition_value == 'selected':
        from production_diagnostics import from_exception
        owner_acceptance = decision_data['owner_acceptance']
        selection_basis = 'owner-allowance' if owner_acceptance is not None else 'review-pass'
        if latest is None or decision_data['review'] != latest['sha256']:
            diagnostics.append(from_exception(_selection_review_changed(run), phase='selection'))
        else:
            try:
                _recorded_selection_basis(prepared, rows, decision, latest)
            except (ValueError, KeyError, TypeError) as exc:
                diagnostics.append(from_exception(exc, phase='selection'))
        if state.latest('selection')['sequence'] > decision['sequence']:
            diagnostics.append(from_exception(ProductionError(
                'SELECTION_REPLACED', 'A later selection of another candidate replaced this selection.',
                phase='selection', run=run, required_action='Read the current selection of the run with status.'), phase='selection'))
    return {'run': run, 'candidate': candidate, 'candidate_sha256': chosen['data']['files'][0]['sha256'],
            'evaluation': evaluation, 'disposition': disposition_value,
            'unassessed_criteria': unassessed, 'review': latest['sha256'] if latest else None,
            'decision': decision['sha256'] if decision else None, 'decision_detail': decision_data,
            'reviewed_at': latest['created_at'] if latest else None,
            'decided_at': decision['created_at'] if decision else None,
            'selection_basis': selection_basis, 'owner_acceptance': owner_acceptance,
            'selection_requirements': selection_requirements(prepared, latest) if latest else {
                'unassessed_hard_criteria': sorted(item['id'] for item in prepared['task']['criteria'] if item['strength'] == 'hard'),
                'nonpassing_hard_criteria': [], 'unresolved_indices': []},
            'selection_current': not diagnostics if disposition_value == 'selected' else None,
            'selection_diagnostics': diagnostics}


@runtime_snapshot.operation
def draft_disposition(root: Path, run: str, candidate: str) -> dict:
    _, prepared, _, rows = read_run(root, run)
    find(rows, 'candidate', candidate)
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate,
            'disposition': 'not_selected', 'actor': '', 'reason': '', 'review': None}


@runtime_snapshot.operation
def disposition_value(root: Path, run: str, data: dict, *, files: list[dict] | None = None) -> dict:
    """Record an explicit disposition; selection has its own gate.

    A disposition recorded after a selection withdraws its current use. A
    completed run can record nonselection of retained candidates without
    changing its historical completion or reopening pending work. The image a
    Studio accepted for its slot keeps its selection until the author accepts
    another image for the slot.
    """
    with store.transaction(root):
        loaded = read_run(root, run)
        directory, prepared, _, rows = loaded
        schema_check(data, 'disposition')
        for name in ('actor', 'reason'):
            c.text(data[name], name)
        compare_exact({'input_sha256': prepared['input_sha256']},
                      {'input_sha256': data['input_sha256']}, phase='disposition')
        current_state = candidate_state(root, run, data['candidate'], loaded=loaded)
        accepted = _studio_accepted(root, prepared, run, data['candidate'])
        if accepted:
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


@runtime_snapshot.operation
def disposition(root: Path, run: str, decision_file: str) -> dict:
    directory, _, _, _ = read_run(root, run)
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
    """A committed decision stays committed if a rebuildable display is unavailable."""
    import studio
    import studio_activity as activity
    from execution_contract import content_id
    if not (root / studio.MANIFEST).is_file():
        return receipt
    projection = activity.changed(root, 'production-decision',
                                  subject=str(receipt.get('run') or receipt.get('candidate') or 'production'),
                                  revision=content_id(receipt), details=receipt)
    return receipt if projection.get('ok') else {**receipt, 'projection_warning': projection}


@runtime_snapshot.operation
def draft_selection(root: Path, run: str, candidate: str) -> dict:
    _, prepared, _, rows = read_run(root, run)
    find(rows, 'candidate', candidate)
    reviewed = latest_review(rows, candidate)
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate, 'review': reviewed['sha256'],
            'selector': '', 'reason': '', 'scope': 'delivery-only', 'adoption': None, 'slot': None,
            'owner_acceptance': None, 'authorization': ''}


def selection_intent(selection: dict) -> dict:
    # The reason and selecting actor are part of the exact decision, not merely
    # the image id. The authorization reference itself is excluded to avoid a cycle.
    return {'operation': 'select', 'targets': ['delivery'],
            'payload': {k: v for k, v in selection.items() if k != 'authorization'}}


@runtime_snapshot.operation
def select(root: Path, run: str, selection_file: str) -> dict:
    directory, _, _, _ = read_run(root, run)
    item = file_record(root, directory, selection_file)
    data = c.decode(c.object_read(directory, item['sha256']))
    return select_value(root, run, data, files=[item])


@runtime_snapshot.operation
def select_value(root: Path, run: str, data: dict, *, files: list[dict] | None = None) -> dict:
    """Select an exact reviewed result through either a file or a compact owner decision.

    Existing captured results use their saved input and review. Source freshness
    remains a boundary for new creative execution, not a reason to regenerate
    pixels merely to record their selection.
    """
    with store.transaction(root):
        directory, prepared, _, rows = read_run(root, run)
        data = c.decode(c.encoded(data))
        schema_check(data, 'selection')
        if data['input_sha256'] != prepared['input_sha256']:
            raise ValueError('selection belongs to another input')
        candidate = find(rows, 'candidate', data['candidate'])
        reviewed = latest_review(rows, data['candidate'])
        if reviewed['sha256'] != data['review']:
            raise _selection_review_changed(run)
        eligible(prepared, reviewed, data['owner_acceptance'])
        previous = [row for row in rows if row['event'] == 'selection' and row['data']['selection'] == data]
        if previous:
            selected, _, _ = current_selection(prepared, rows)
            if selected['sha256'] != previous[-1]['sha256']:
                raise ProductionError('SELECTION_REPLACED', 'The recorded selection is no longer the current decision.',
                                      phase='selection', run=run,
                                      required_action='Record a new exact selection decision before changing the selected result.')
            row = selected
        else:
            _require_no_other_selection(rows, data['candidate'], run)
            request = _permission(root, prepared, rows, data['authorization'], **selection_intent(data))
            if request['actor'] != data['selector']:
                raise ValueError('selector differs from the authorized actor')
            if files is None:
                raw = c.encoded(data)
                key = c.object_store(directory, raw)
                files = [{'path': f'production/runs/{run}/objects/{key}', 'sha256': key, 'size': len(raw)}]
            else:
                files = list(files)
            effect = {'files': files, 'selection': data, 'authorizations': [data['authorization']]}
            if data['scope'] == 'delivery-only':
                if data['adoption'] is not None:
                    raise ValueError('delivery-only selection cannot claim canonical adoption')
            elif data['scope'] == 'studio-slot':
                import production_acceptance
                production_acceptance.validate_slot(root, run, data['candidate'], data['slot'],
                                                    loaded=(directory, prepared, None, rows))
                effect['slot_state'] = production_acceptance.slot_state(root, data['slot']['character'], data['slot']['slot'])
            else:
                if data['adoption'] is None:
                    raise ValueError('Studio adoption requires its owned receipt')
                for path in confirm_studio_adoption(root, data['adoption'], candidate['data']['files'][0]['sha256'], rows):
                    files.append(file_record(root, directory, path.relative_to(root).as_posix()))
            row = lifecycle.commit_effect(root, run, 'selection', effect,
                                          [data['authorization']], effect='local-action')
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
    if isinstance(rows, lifecycle.EventHistory):
        rows = rows.lifecycle.selection_context()
    selection = find(rows, 'selection')
    chosen = selection['data']['selection']
    reviewed = latest_review(rows, chosen['candidate'])
    if reviewed['sha256'] != chosen['review']:
        raise _selection_review_changed()
    if any(row['event'] == 'disposition' and row['sequence'] > selection['sequence']
           and row['data']['disposition']['candidate'] == chosen['candidate'] for row in rows):
        closed = any(row['event'] in {'completion', 'abandoned'} for row in rows)
        raise ProductionError('SELECTION_WITHDRAWN', 'A later disposition withdrew this selection.', phase='selection',
                              required_action=('This run is closed. Its recorded completion or abandonment remains unchanged; '
                                               'prepare a new run for a new selection.' if closed else
                                               'Record a new exact selection decision before accepting or completing this result.'))
    _recorded_selection_basis(prepared, rows, selection, reviewed)
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


@runtime_snapshot.operation
def complete(root: Path, run: str) -> dict:
    loaded = read_run(root, run)
    if any(row['event'] == 'completion' for row in loaded.rows):
        row = verify_completion(root, run, loaded.prepared['task']['task_id'])
    else:
        with store.transaction(root):
            directory, prepared, _, rows = read_run(root, run)
            if any(item['event'] == 'completion' for item in rows):
                row = verify_completion(root, run, prepared['task']['task_id'])
            elif prepared['task']['execution'] == 'authored':
                from production_authored import completion_data
                row = append_record(directory, prepared, rows, 'completion', completion_data(prepared, rows))
            else:
                selection, chosen, reviewed = current_selection(prepared, rows)
                if chosen['scope'] == 'studio-adoption':
                    candidate = find(rows, 'candidate', chosen['candidate'])
                    confirm_studio_adoption(root, chosen['adoption'], candidate['data']['files'][0]['sha256'], rows)
                elif chosen['scope'] == 'studio-slot':
                    from production_acceptance import verify_slot
                    verify_slot(root, run, selection, rows=rows, require_current=True)
                row = append_record(directory, prepared, rows, 'completion',
                    {'selection': selection['sha256'], 'candidate': chosen['candidate'],
                     'scope': chosen['scope'], 'task_id': prepared['task']['task_id'], 'run': run,
                     'limitations': [x for ob in reviewed['data']['review']['observations'] for x in ob['limitations']]})
    return _refresh_studio_projection(root, row)


@runtime_snapshot.operation
def verify_completion(root: Path, run: str, task_id: str) -> dict:
    _, prepared, _, rows = read_run(root, run)
    done = find(rows, 'completion')
    if prepared['task']['task_id'] != task_id or done['data']['task_id'] != task_id or done['data']['run'] != run:
        raise ValueError('completion belongs to another task')
    completed = [row for row in rows if row['sequence'] < done['sequence']]
    if prepared['task']['execution'] == 'authored':
        from production_authored import completion_data
        if done['data'] != completion_data(prepared, completed):
            raise ValueError('authored completion differs from its recorded results')
        return done
    selection, selected, reviewed = current_selection(prepared, completed)
    expected = {'selection': selection['sha256'], 'candidate': selected['candidate'],
                'scope': selected['scope'], 'task_id': task_id, 'run': run,
                'limitations': [x for ob in reviewed['data']['review']['observations'] for x in ob['limitations']]}
    if done['data'] != expected:
        raise ValueError('completion differs from its recorded selected state')
    if selected['scope'] == 'studio-adoption':
        verify_studio_adoption_receipt(root, run, selection, rows=completed)
    elif selected['scope'] == 'studio-slot':
        from production_acceptance import verify_slot
        verify_slot(root, run, selection, rows=rows)
    return done


@runtime_snapshot.operation
def impact(root: Path, run: str) -> dict:
    """Read-only comparison against frozen inputs, including transitive decisions.

    A changed creative source is a change and reaches decisions and criteria.
    Evidence sources and files recorded by events are provenance: the run keeps
    their verified snapshots, so a grown ledger or a replaced file is listed
    under `provenance` as `provenance_changed` with the snapshot intact. A
    changed file of the installed implementation is listed under
    `implementation`; it reaches no creative decision, and the task is prepared again.
    """
    try:
        _, prepared, _, rows = read_run(root, run)
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
            if actual == item.get('selection_sha256', item['sha256']):
                continue
            entry = {**item, 'actual_sha256': actual, 'status': 'changed'}
        except (ValueError, OSError) as exc:
            entry = {**item, 'actual_sha256': None, 'status': 'unavailable', 'reason': str(exc)}
        if item['space'] in {'evidence', 'artifact'}:
            # read_run verified every saved snapshot before this comparison.
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


@runtime_snapshot.operation
def execute(root: Path, run: str, *, decisions_file: str | None = None) -> dict:
    from production_execution import execute as run_execution
    return run_execution(root, run, decisions_file=decisions_file)


@runtime_snapshot.operation
def resume(root: Path, run: str, *, outcome_file: str | None = None) -> dict:
    from production_execution import resume as recover_execution
    return recover_execution(root, run, outcome_file=outcome_file)


@runtime_snapshot.operation
def status(root: Path, run: str | None = None) -> dict:
    from production_execution import status as report
    return report(root, run)


def changed_scopes(before: dict, after: dict, *, before_inputs: dict | None = None,
                   after_inputs: dict | None = None) -> list[str]:
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
    from image_input import revision_scopes
    image_changes = revision_scopes(before_inputs, after_inputs)
    if image_changes is not None:
        scopes.update(image_changes['scopes'])
        declared.update(image_changes['paths'])
        declared.update(path for path in (old.get('image_input'), new.get('image_input'))
                        if path is not None)
    if any(space == 'studio' and path not in declared and old_dependencies.get((space, path)) != new_dependencies.get((space, path))
           for space, path in old_dependencies.keys() | new_dependencies.keys()):
        scopes.add('execution')
    return sorted(scopes)


@runtime_snapshot.operation
def revision_intent(root: Path, run: str, task: str, candidate: str, repair: str) -> dict:
    _, prepared, consumer, rows = read_run(root, run)
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
    scopes = changed_scopes(prepared, revised, before_inputs=consumer.get('image_input'),
                            after_inputs=revised_consumer.get('image_input'))
    if not scopes:
        raise ValueError('repair contains no changed production inputs')
    if set(scopes) - set(matches[0]['targets']):
        raise ValueError('repair changes targets outside its reviewed scope: ' + ', '.join(scopes))
    from production_compiler import input_digest
    return {'operation': 'edit', 'targets': scopes,
            'payload': {'parent_run': run, 'candidate': candidate, 'review': reviewed['sha256'],
                        'repair': repair, 'revised_input_sha256': input_digest(revised, revised_consumer)}}


@runtime_snapshot.operation
def revise(root: Path, run: str, task: str, candidate: str, repair: str, authorization: str) -> dict:
    with store.transaction(root):
        # Revised sources may intentionally differ. Read the parent's immutable
        # snapshots, but still verify the candidate and observation evidence used.
        directory, prepared, _, rows = read_run(root, run)
        require_mutable(rows)
        reviewed = latest_review(rows, candidate)
        chosen = find(rows, 'candidate', candidate)
        for row in (reviewed, chosen):
            for item in row['data'].get('files', []) + row['data'].get('evidence', []):
                if c.digest(c.read(c.local(root, item['path']))) != item['sha256']:
                    raise ValueError('revision evidence changed; review the actual artifact again')
        intent = revision_intent(root, run, task, candidate, repair)
        authority = current_authority(root, prepared)
        request = _permission(root, prepared, rows, authorization, **intent, authority=authority)
        grant = next(g for g in authority.document['grants'] if g['id'] == request['grant'])
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


def validate_dispatch_authentication(value: dict | None, transport: Any, service_id: str) -> dict | None:
    """Validate the claim's source identity against its sealed service and transport."""
    import service_auth
    import transport_contract
    if transport_contract.credential_free(transport):
        if value is not None:
            raise ValueError('A credential-free dispatch claim uses a null authentication selection.')
        return None
    return service_auth.validate_selection(value, service=service_id)


@runtime_snapshot.operation
def claim_dispatch(root: Path, run: str, package: dict, verified: dict, journal: Path,
                   intent: dict, authorization: str, *, rendered: dict, authentication: dict | None) -> dict:
    with store.transaction(root):
        current = read_current(root, run)
        authority = current_authority(root, current.view.prepared)
        return _claim_dispatch_from(root, current.view, authority, package, verified, journal,
                                    intent, authorization, rendered=rendered, authentication=authentication,
                                    input_source=current.runtime)


def _claim_dispatch_from(root: Path, loaded: RunView, authority: store.CurrentAuthority,
                         package: dict, verified: dict, journal: Path, intent: dict,
                         authorization: str, *, rendered: dict, authentication: dict | None,
                         input_source) -> dict:
    """Claim the exact compiled request from acquired current inputs and grants."""
    directory, prepared, _, rows = loaded
    run = prepared['run']
    hand = find(rows, 'handoff')
    if hand['data']['method'] != 'dispatcher' or prepared['task']['execution'] != 'dispatcher':
        raise ValueError('dispatcher handoff required')
    if any(r['event'] == 'dispatch-claim' for r in rows):
        raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already owns a request.', phase='execution', run=run, required_action='Use resume, variant or repeat according to the intended operation.')
    # A low-level caller cannot introduce a second request contract for
    # this run. Compare the same sealed input used by execute before any
    # authorization accounting or claim is committed.
    from production_execution import compiled
    fixed = compiled(root, run, loaded=loaded)
    fixed_package, fixed_rendered, fixed_plan = fixed[4:7]
    authentication = validate_dispatch_authentication(authentication, fixed[8], fixed[7]['offering']['service'])
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
    from production_binding import _validate_live_from, _validate_upscale_live_from
    if package.get('artifact_type') == 'upscale-request':
        _validate_upscale_live_from(root, loaded, package, input_source=input_source)
    else:
        _validate_live_from(loaded, package)
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
    request = _permission(root, prepared, rows, authorization, **intent, authority=authority, loaded=loaded)
    execution = lifecycle._claim_execution_from(root, loaded, authority, authorization)
    directory, prepared, _, rows = read_run(root, run)
    relative = journal.absolute().relative_to(root.absolute()).as_posix()
    c.local(root, relative)
    return append_record(directory, prepared, rows, 'dispatch-claim',
                         {'package_sha256': c.content_id(package),
                          **({'upscale_request_sha256': c.content_id(package)}
                             if package.get('artifact_type') == 'upscale-request' else
                             {'effective_prompt_sha256': verified['host_forwarding']['effective_prompt_sha256']}),
                          'journal': relative, 'intent': intent, 'count': request['outputs'],
                          'authentication': authentication,
                          'authorizations': [authorization], 'execution_id': execution['execution_id']})


@runtime_snapshot.operation
def record_dispatch_results(root: Path, run: str, package: dict, journal: Path,
                            result_paths: list[Path], expected_count: int, *,
                            indices: list[int] | None = None, returned_count: int | None = None,
                            upscale_packages: dict[int, Path] | None = None,
                            invalid_output_indices: set[int] | None = None,
                            answer_name: str = 'answer.json', provider_complete: bool = True) -> dict:
    with store.transaction(root):
        loaded=read_run(root,run)
        directory, prepared, _, rows = loaded
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
        prior = [row['data'] for row in rows if row['event'] == 'dispatch-results' and row['data']['claim'] == claim['sha256']]
        known = {index: item['sha256'] for receipt in prior for index, item in zip(receipt['output_indices'], receipt['files'])}
        if not set(known).issubset(indices) or any(index in known and known[index] != item['sha256']
                                                 for index, item in zip(indices, files)):
            raise ProductionError('PROVIDER_OUTPUT_CHANGED', 'A provider output cannot lose or change its first captured bytes.',
                                  phase='result-capture', run=run,
                                  required_action='Restore the recorded output from its Production snapshot; do not resend.')
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
        c.local(journal, answer_name)
        evidence = [file_record(root, directory, base + '/' + name)
                    for name in ('package.json', 'request-contract.json', 'request.json', answer_name)]
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
                verify_upscale_package(generated,package_root=journal,
                                       model_record=loaded.artifacts['execution-target.json']['model'])
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
        for index in indices:
            response = c.load(journal / f'response-{index}.json')
            source = c.local(journal, response['answer'])
            if c.sha256_file(source) != response['answer_sha256']:
                raise ProductionError('RESPONSE_CORRUPT', 'The output response differs from its original observation.',
                                      phase='result-capture', run=run)
            for name in (f'response-{index}.json', f'acquisition-{index}.json', response['answer']):
                item = file_record(root, directory, base + '/' + name)
                if item not in evidence:
                    evidence.append(item)
        known_evidence = {item['path']: item['sha256'] for receipt in prior for item in receipt['evidence']}
        if any(item['path'] in known_evidence and item['sha256'] != known_evidence[item['path']] for item in evidence):
            raise ProductionError('RESPONSE_CORRUPT', 'Previously recorded provider evidence changed.',
                                  phase='result-capture', run=run)
        return append_record(directory, prepared, rows, 'dispatch-results',
                             {'claim': claim['sha256'], 'files': files, 'evidence': evidence, 'expected_count': expected_count,
                              'output_indices': indices, 'returned_count': returned_count,
                              'answer': answer_name, 'provider_complete': provider_complete,
                              'complete': provider_complete and len(files) == returned_count == expected_count,
                              'contract_valid': not invalid_output_indices,
                              'invalid_output_indices': sorted(invalid_output_indices)})


def _studio_adoption_result(selector: dict, target: str, rows: list[dict], owner: dict, iteration: dict) -> dict:
    """Match an owner's receipt to its exact completed Production operation."""
    import adoption_workflow
    if not isinstance(owner, dict) or owner.get('artifact_type') != 'studio-adoption' or not isinstance(owner.get('approval'), dict):
        raise ProductionError('ADOPTION_RECORD_CORRUPT', 'The canonical adoption record is incomplete or malformed.',
                              phase='adoption-integrity', expected=target)
    claims = {row['sha256']: row['data']['intent']['payload'] for row in rows if row['event'] == 'adoption-claim'}
    results = []
    for row in rows:
        if row['event'] != 'adoption-result' or row['data']['claim'] != owner.get('production_claim'):
            continue
        payload = claims.get(row['data']['claim'])
        if (payload and payload['character'] == selector['character'] and payload['iteration'] == selector['iteration_id']
                and payload['approval_sha256'] == c.content_id(owner['approval'])
                and row['data']['result'] == {'ok': True, **owner}):
            results.append(row)
    if len(results) != 1:
        raise ProductionError('ADOPTION_RESULT_MISSING', 'This run records no exact completed adoption of the cited Studio iteration.',
            phase='adoption-integrity', expected=target,
            required_action='Adopt the selected candidate with production_workflow.py adopt under its own adopt authorization.')
    try:
        approval = adoption_workflow.validate_approval(owner['approval'], selector['character'], iteration)
    except (ValueError, KeyError, TypeError) as exc:
        raise ProductionError('ADOPTION_RECORD_CORRUPT', 'The canonical adoption approval differs from its selected artifact.',
                              phase='adoption-integrity', expected=target) from exc
    accepted = iteration.get('adoption_status') if iteration.get('production') else iteration.get('status')
    if (approval['image_sha256'] != target or approval['scope'] != selector['scope']
            or owner.get('next_action') or accepted != 'accepted'):
        raise ValueError('Studio adoption is incomplete or targets a different image')
    return results[0]


def _recorded_studio_adoption(run: str, selection: dict, rows: list[dict], read_object) -> dict:
    """Verify only the immutable evidence captured by this adoption selection."""
    import sheet_artifacts
    from character_sheet import validate_sidecar
    chosen = selection['data']['selection']
    if chosen['scope'] != 'studio-adoption':
        raise ValueError('adoption receipt verification needs a studio-adoption selection')
    selector = chosen['adoption']
    c.exact(selector, {'character', 'iteration_id', 'scope'}, 'Studio adoption selector')
    prior = [row for row in rows if row['sequence'] < selection['sequence']]
    target = find(prior, 'candidate', chosen['candidate'])['data']['files'][0]['sha256']
    files = {}
    for item in selection['data']['files']:
        if item['path'] in files and files[item['path']] != item:
            raise ValueError('adoption selection records conflicting snapshots of one file')
        files[item['path']] = item

    def saved(path: str, expected: str | None = None) -> bytes:
        item = files.get(path)
        if item is None:
            raise store.evidence_error('EVIDENCE_SNAPSHOT_MISSING', 'The adoption selection lacks its bound snapshot.',
                                       file=path, run=run, event=selection['sha256'], expected=expected)
        raw = read_object(item['sha256'])
        if c.digest(raw) != item['sha256'] or len(raw) != item['size'] or (expected is not None and item['sha256'] != expected):
            raise store.evidence_error('EVIDENCE_SNAPSHOT_CORRUPT', 'The saved adoption evidence differs from its receipt.',
                                       file=path, run=run, event=selection['sha256'], expected=expected or item['sha256'])
        return raw

    home = Path('characters') / selector['character']
    owner = c.decode(saved((home / 'adoptions' / (selector['iteration_id'] + '.json')).as_posix()))
    iterations = [c.decode(line) for line in saved((home / 'iterations.jsonl').as_posix()).splitlines() if line.strip()]
    matches = [row for row in iterations if row['iteration_id'] == selector['iteration_id']]
    if len(matches) != 1 or matches[0].get('production') != {'run': run, 'candidate': chosen['candidate']}:
        raise ValueError('saved Studio iteration differs from its selected Production candidate')
    iteration = matches[0]
    result = _studio_adoption_result(selector, target, prior, owner, iteration)
    for field in ('result', 'package', 'request', 'response', 'answer'):
        if iteration.get(field):
            saved(iteration[field]['path'], iteration[field]['sha256'])
    saved(iteration['accepted_path'], target)
    sheet = home / 'sheet'
    sidecar = validate_sidecar(c.decode(saved((sheet / 'sheet-data.json').as_posix())), verify_files=False)
    accepted = sidecar['slots'][iteration['slot']]['current']
    if (accepted is None or accepted['artifact']['image']['sha256'] != target
            or owner['sheet_binding']['current'] != accepted):
        raise ValueError('saved sheet adoption differs from its selected image')
    sheet_artifacts.verify_acceptance(accepted, sheet, iteration['slot'],
        read_source=lambda base, relative, load: saved((base / relative).as_posix()))
    decision = c.decode(saved((sheet / accepted['approval']['decision_path']).as_posix()))
    if decision != owner['sheet_decision']:
        raise ValueError('saved sheet approval differs from the completed adoption')
    basis = decision['basis']
    claim = find(prior, 'adoption-claim', basis['claim'])
    payload = claim['data']['intent']['payload']
    if (basis['kind'] != 'production' or payload['candidate'] != chosen['candidate']
            or payload['character'] != selector['character'] or payload['iteration'] != selector['iteration_id']
            or payload['approval_sha256'] != c.content_id(basis['approval'])):
        raise ValueError('saved sheet approval differs from its Production adoption claim')
    return result


@runtime_snapshot.operation
def verify_studio_adoption_receipt(root: Path, run: str, selection: dict, *, rows: list[dict] | None = None) -> dict:
    """Historical verification never substitutes today's canonical destination."""
    held = read_run(root, run)
    if rows is None:
        rows = held.rows
    return _recorded_studio_adoption(run, selection, rows, held.evidence.read)


def confirm_studio_adoption(root: Path, selector: dict[str,Any], target: str, rows: list[dict]) -> list[Path]:
    """Confirm the Studio adoption a selection cites and return the files that bind it.

    The run must record the completed Production adoption of that iteration
    under the approval the Studio's adoption record holds.
    """
    import studio
    c.exact(selector,{'character','iteration_id','scope'},'Studio adoption selector')
    for value in selector.values(): c.text(value,'adoption field')
    home=studio.character_dir(root,selector['character'])
    read = studio.StudioRead(root)
    owner_path=home/'adoptions'/f"{selector['iteration_id']}.json"
    owner=read.journal(selector['character'], selector['iteration_id'])
    row=studio._find(read.iterations(selector['character']),selector['iteration_id'])
    _studio_adoption_result(selector, target, rows, owner, row)
    reference=read.reference_index(selector['character'])
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
    import sheet_artifacts
    sidecar = read.sheet(selector['character'])
    accepted = sidecar['slots'][row['slot']]['current']
    def retained(base: Path, relative: str, load) -> bytes:
        paths.append(base / relative)
        return load()
    sheet_artifacts.verify_acceptance(accepted, home / 'sheet', row['slot'], read_source=retained)
    return sorted(set(paths))



@runtime_snapshot.operation
def adoption_intent(root: Path, run: str, candidate: str, character: str, iteration: str,
                    approval: dict, *, registration_record: dict | None = None,
                    pack_dir: Path | None = None) -> dict:
    _, _, _, rows = read_run(root, run)
    chosen = find(rows, 'candidate', candidate)
    reviewed = latest_review(rows, candidate)
    from adoption_workflow import preflight
    preflight(root, character, iteration, approval, expected_production={'run': run, 'candidate': candidate},
              expected_image=chosen['data']['files'][0]['sha256'],
              registration_record=registration_record, pack_dir=pack_dir)
    return {'operation': 'adopt', 'targets': ['canon:' + approval['scope']],
            'payload': {'candidate': candidate, 'review': reviewed['sha256'],
                        'character': character, 'iteration': iteration,
                        'approval_sha256': c.content_id(approval),
                        'registration_sha256': c.content_id(registration_record) if registration_record else None,
                        'pack_dir': str(pack_dir.absolute()) if pack_dir is not None else None}}


@runtime_snapshot.operation
def adopt(root: Path, run: str, candidate: str, character: str, iteration: str,
          approval_file: str, authorization: str, *, registration_record: dict | None = None,
          pack_dir: Path | None = None, settings: Any = None) -> dict:
    """Commit one recoverable adoption and publish its derived views once."""
    import studio_activity as activity
    with activity.operation(root) as projection:
        result = _adopt(root, run, candidate, character, iteration, approval_file, authorization,
                        registration_record=registration_record, pack_dir=pack_dir, settings=settings)
    return activity.project_result(result, projection)


def _adopt(root: Path, run: str, candidate: str, character: str, iteration: str,
          approval_file: str, authorization: str, *, registration_record: dict | None = None,
          pack_dir: Path | None = None, settings: Any = None) -> dict:
    """Invoke the owning adoption operation under a separate exact grant.

    A failed mutation is never interpreted as permission for a new one. The
    owner's durable adoption journal resumes the same already-claimed operation.
    The candidate must hold the run's current selection, and the owner checks
    the claim this operation records before it changes the Studio.
    """
    with store.transaction(root):
        directory, prepared, _, rows = read_run(root, run)
        item = file_record(root, directory, approval_file)
        approval = c.decode(c.object_read(directory, item['sha256']))
        intent = adoption_intent(root, run, candidate, character, iteration, approval,
                                 registration_record=registration_record, pack_dir=pack_dir)
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
            rows = read_run(root, run).rows
        completed = [r for r in rows if r['event'] == 'adoption-result' and r['data']['claim'] == claim['sha256']]
        if completed:
            row = completed[-1]
    if not completed:
        import adoption_workflow
        result = adoption_workflow.adopt(root, character, iteration, approval,
                                        registration_record=registration_record, pack_dir=pack_dir, settings=settings,
                                        production_claim=claim['sha256'])
        with store.transaction(root):
            directory, prepared, _, rows = read_run(root, run)
            row = append_record(directory, prepared, rows, 'adoption-result',
                                {'claim': claim['sha256'], 'result': result})
    return _refresh_studio_projection(root, row)


@runtime_snapshot.operation
def draft_authorization(root: Path, run: str, grant_id: str, intent: dict) -> dict:
    loaded, authority = authorization_context(root, run, intent.get('operation'))
    return draft_authorization_from(loaded, authority, grant_id, intent)


def draft_authorization_from(loaded: RunView, authority: store.CurrentAuthority,
                             grant_id: str, intent: dict) -> dict:
    """Build editable choices from an owned run and checked current grants."""
    _, prepared, consumer, _ = loaded
    if authority.task_id != prepared['task']['task_id']:
        raise ValueError('current authority belongs to another work task')
    grants = authority.document
    matches = [g for g in grants['grants'] if g['id'] == grant_id]
    if len(matches) != 1:
        raise ValueError('unknown grant id')
    c.exact(intent, {'operation', 'targets', 'payload'}, 'operation intent')
    result = {'grant': grant_id, 'actor': matches[0]['actor'], **mutable(intent),
            'outputs': intent['payload'].get('count', 0) if intent['operation'] == 'submit' else 0,
            'reason': '',
            'stop_assessments': [{'id': s['id'], 'clear': False, 'evidence': ''}
                                 for s in grants['stop_conditions']]}
    if intent['operation'] == 'submit' and prepared['task']['execution'] == 'dispatcher':
        from production_request import draft_decision, validate_payload
        validate_payload(intent['payload'])
        result['request_decision'] = draft_decision(intent['payload']['request_contract'], actor=result['actor'])
    elif (intent['operation'] == 'submit' and prepared['task']['execution'] == 'external'
            and prepared['task']['artifact'] == 'image'):
        from production_request import draft_external_decision
        result['request_decision'] = draft_external_decision(consumer['image_input'], actor=result['actor'])
    return result


COMMAND_HELP = {
    'check': 'Check a task and show its request preview and execution plan without creating a run.',
    'prepare': 'Check a task and publish it as a prepared run with its exact request and execution plan.',
    'save': 'Save an authored revision from its editable choices, retaining unresolved input when --draft is selected.',
    'record-save': 'Record the saved authored revision after an interrupted publication.',
    'deliver': 'Copy this saved authored revision to a local destination, or record actual external presentation or attachment evidence.',
    'review-authored': 'Record an evidence-backed review of the saved authored artifact against its independent assessment basis.',
    'draft-execution': 'Write the unanswered execution decision file for every operation of a prepared run.',
    'execute': 'Apply the separate execution decisions, then dispatch or hand the exact request to its external host once.',
    'resume': 'Recover the same execution without sending it again where a send has started.',
    'draft-outcome': "Write the statement to fill when the provider's records hold no task for a started send.",
    'status': 'Report each run by preparation, readiness, submission, capture, review and disposition.',
    'authority-import': 'Import the grant file of the named work task, or replace the current one.',
    'recover-publication': 'Register a verified publication whose registration was interrupted.',
    'staging-cleanup': "List one ended operation's unpublished staging, unclaimed journals and unrecoverable publications.",
    'logs': 'List automatic operation logs of the studio, or of the configuration directory without --root.',
    'logs-export': 'Copy operation logs to a new directory with a manifest of what it includes.',
    'logs-cleanup': 'List diagnostic operation logs that may be deleted; production records stay.',
    'handoff-intent': 'Show the exact direction operation that a handoff needs authorized.',
    'handoff': 'Record a conversation or manual handoff that happened under an exact direction authorization.',
    'external-intent': 'Show the exact submission operation that an external host call needs authorized.',
    'claim-external': 'Commit the boundary before an external host invokes its tool under an exact authorization.',
    'receive-external': 'Receive actual response files and images, derive their receipt and settle the existing host call.',
    'workspace': 'Read the exact input, decision basis, candidate observation or review context without editing records.',
    'draft-authorization': 'Write an unanswered authorization request for one exact operation intent.',
    'authorize': 'Record a completed authorization request for one exact operation of a run.',
    'capture': 'Record a received result file as a candidate of the run.',
    'draft-review': 'Write the unanswered review form of a saved authored revision or one generated candidate.',
    'review': 'Record a completed review of one candidate.',
    'draft-disposition': 'Write the form that records a candidate as not selected.',
    'disposition': 'Record an explicit decision that a candidate is not selected.',
    'candidate-status': "Show one candidate's evaluation and disposition.",
    'draft-selection': 'Write the selection form of one reviewed candidate.',
    'draft-acceptance': 'Write a compact owner decision for an existing reviewed image and its Studio slot.',
    'accept': 'Record or resume the exact owner decision, Studio slot acceptance and completion.',
    'selection-intent': 'Show the exact selection operation that a selection file needs authorized.',
    'select': 'Record an authorized selection of a reviewed candidate.',
    'revision-intent': 'Show the exact edit operation that a reviewed repair needs authorized.',
    'revise': 'Prepare a revised task as a new run under an authorized edit of a reviewed repair.',
    'adoption-intent': 'Show the exact adoption operation that a canonical adoption needs authorized.',
    'adopt': 'Adopt a selected candidate as canon under its own exact authorization.',
    'complete': 'Complete the work task with its required authored results or current selected execution result.',
    'impact': 'Compare a run with its current sources and list what each change affects.',
}
# One sentence for each option, by destination; a (command, destination) entry is more specific.
OPTION_HELP = {
    'root': 'The studio directory that holds the production records.',
    'run': 'ID of the prepared run.',
    'task': 'Studio-relative task JSON file; a file only, not stdin.',
    'out': 'New studio-relative file to write; an existing file is never replaced.',
    'out_dir': 'New studio-relative directory to write.',
    'decisions_file': 'Completed execution decision file from draft-execution, or - for stdin.',
    'outcome_file': "Statement from draft-outcome that the provider's records hold no task for the started send, or - for stdin.",
    'grant': 'ID of the grant the drafted decisions use.',
    'expected_event': 'Digest of the current authority event that this import replaces.',
    'failed': 'Only operations that failed or did not finish.',
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
    'choices': 'Editable choices file from draft-inputs.',
    'draft': 'Save unfinished authored text with its unresolved choices instead of claiming finished model input.',
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
    ('deliver', 'file'): 'Receipt identifying actual presentation or attachment evidence, or - for stdin.',
    ('review-authored', 'file'): 'Completed common review form from draft-review, with observed evidence and limitations, or - for stdin.',
    ('select', 'file'): 'Completed selection file from draft-selection, or - for stdin.',
    ('accept', 'file'): 'Completed owner decision from draft-acceptance, or - for stdin; omit to resume the recorded selection.',
    ('selection-intent', 'file'): 'Completed selection file from draft-selection, or - for stdin.',
    ('disposition', 'file'): 'Completed disposition file from draft-disposition, or - for stdin.',
    ('revise', 'task'): 'Studio-relative revised task JSON file; a file only, not stdin.',
    ('revision-intent', 'task'): 'Studio-relative revised task JSON file; a file only, not stdin.',
}
# Arguments that name one JSON input file and accept - for stdin.
STDIN_INPUTS = ('decisions_file', 'file', 'request', 'intent', 'approval', 'outcome_file', 'registration_record', 'changes_file')
# Arguments that name a studio file.
FILE_ARGUMENTS = STDIN_INPUTS + ('task', 'choices', 'artifact', 'response_file', 'submission_file')


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
        if name not in {'prepare', 'check', 'save', 'authority-import', 'staging-cleanup', 'logs', 'logs-export', 'logs-cleanup', 'status'}:
            p.add_argument('--run', required=True)
        if name in {'status', 'logs', 'logs-export'}:
            p.add_argument('--run')
        if name == 'execute':
            p.add_argument('--decisions-file')
        if name == 'resume':
            p.add_argument('--outcome-file')
        if name in {'draft-outcome', 'draft-execution', 'logs-export', 'draft-review', 'draft-selection',
                    'draft-authorization', 'draft-disposition', 'draft-acceptance'}:
            p.add_argument('--out', required=True)
        if name in {'draft-execution', 'draft-authorization', 'draft-acceptance'}:
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
        if name in {'revision-intent', 'revise'}:
            p.add_argument('--task', required=True)
        if name in {'check', 'prepare'}:
            source = p.add_mutually_exclusive_group(required=True)
            source.add_argument('--task')
            source.add_argument('--choices')
        if name == 'save':
            p.add_argument('--choices', required=True)
            p.add_argument('--draft', action='store_true')
        if name in {'prepare', 'check', 'save'}:
            from pack_runtime_cli import add_pack_runtime_arguments
            add_pack_runtime_arguments(p)
        if name in {'handoff', 'handoff-intent'}:
            p.add_argument('--recipient', required=True)
            p.add_argument('--method', required=True, choices=['conversation', 'manual', 'dispatcher'])
        if name in {'handoff', 'claim-external', 'revise', 'adopt'}:
            p.add_argument('--authorization', required=True)
        if name in {'external-intent', 'claim-external'}:
            p.add_argument('--count', type=int, required=True)
        if name in {'draft-selection', 'draft-acceptance', 'draft-disposition', 'candidate-status', 'revision-intent', 'revise', 'adopt', 'adoption-intent'}:
            p.add_argument('--candidate', required=True)
        if name == 'draft-review':
            p.add_argument('--candidate', help='Actual candidate for a generated result; omit for an authored revision.')
        if name == 'deliver':
            delivery = p.add_mutually_exclusive_group(required=True)
            delivery.add_argument('--to', help='Studio-relative local destination; an existing different file is a conflict.')
            delivery.add_argument('--file', help='Actual external presentation or attachment evidence, or - for stdin.')
        if name in {'authorize', 'review', 'select', 'selection-intent', 'disposition', 'review-authored'}:
            p.add_argument('--file', required=True)
        if name == 'accept':
            p.add_argument('--file')
        if name == 'capture':
            p.add_argument('--artifact', required=True)
            p.add_argument('--note', required=True)
        if name == 'workspace':
            p.add_argument('--phase', required=True, choices=['input', 'decision', 'observe', 'review'],
                           help='The context to read; observe exposes candidate evidence before the assessment basis.')
            p.add_argument('--candidate', help='Candidate event ID for observe or review.')
        if name == 'receive-external':
            p.add_argument('--response', dest='response_file', required=True, help='Actual saved host response file.')
            p.add_argument('--artifact', dest='artifacts', action='append', default=[], help='Received file; repeat for several files.')
            p.add_argument('--image-pointer', dest='image_pointers', action='append', type=json.loads, default=[],
                           help='JSON array of keys/indices selecting a base64 image or image data URL in the response; repeat as needed.')
            p.add_argument('--call', dest='submission_file', help='Actual saved host call, when available.')
            p.add_argument('--request-pointer', type=json.loads, help='JSON key/index array selecting the request in --call; [] selects its root.')
            p.add_argument('--model-identity-pointer', type=json.loads, help='JSON key/index array selecting observed model identity in --call.')
            p.add_argument('--cost-pointer', type=json.loads, help='JSON key/index array selecting actual {currency, amount} in the response.')
            p.add_argument('--pending', action='store_true', help='The host has not delivered its final outcome yet.')
            p.add_argument('--reason', required=True, help='Executor explanation of the observed final or pending outcome.')
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
        if name in {'prepare', 'check', 'save', 'retarget'}:
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
        elif name == 'draft-disposition':
            result = draft_disposition(root, args.run, args.candidate)
            _write_new(root, args.out, result)
        elif name == 'disposition':
            result = disposition(root, args.run, args.file)
        elif name == 'candidate-status':
            result = candidate_state(root, args.run, args.candidate)
        elif name == 'check':
            from production_compiler import check_task
            if args.choices:
                compiled_choices = production_inputs.compile_choices(root, args.choices)
                try:
                    result = compiled_choices.report
                    if result.get('execution_plan') is not None:
                        result['execution_plan']['run'] = None
                finally:
                    if compiled_choices.directory is not None:
                        shutil.rmtree(compiled_choices.directory)
            else:
                result = check_task(root, args.task)
        elif name == 'save':
            result = save(root, args.choices, draft=args.draft)
        elif name == 'record-save':
            from production_authored import record_save
            result = record_save(root, args.run)
        elif name == 'deliver':
            result = deliver(root, args.run, args.file, destination=args.to)
        elif name == 'review-authored':
            result = review_authored(root, args.run, args.file)
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
            result = prepare(root, args.task, choices=args.choices)
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
        elif name == 'receive-external':
            from production_binding import studio_file
            artifacts = [studio_file(root, path, option='--artifact').relative_to(root).as_posix()
                         for path in args.artifacts]
            result = receive_external(root, args.run, response_file=args.response_file, artifacts=artifacts,
                image_pointers=args.image_pointers, final=not args.pending, reason=args.reason,
                submission_file=args.submission_file, request_pointer=args.request_pointer,
                model_identity_pointer=args.model_identity_pointer, cost_pointer=args.cost_pointer)
        elif name == 'workspace':
            from production_workspace import workspace
            result = workspace(root, args.run, phase=args.phase, candidate=args.candidate)
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
        elif name == 'draft-acceptance':
            from production_acceptance import draft
            result = draft(root, args.run, args.candidate, args.grant)
            _write_new(root, args.out, result)
        elif name == 'accept':
            from production_acceptance import accept
            result = accept(root, args.run, decision_file=args.file)
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
            result = status(root, args.run)
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
