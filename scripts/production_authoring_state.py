"""Discover an open task's saved input choices and reading progress without rebuilding them."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

import execution_contract as c
from cli_invocation import python_argv, shown

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/production_workflow.py'
READ_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError)
DECISION_KINDS = frozenset({'execution', 'review', 'selection', 'acceptance', 'adoption', 'outcome'})
_ANY_CONTEXT = object()


def active_task_id(root: Path | None) -> str | None:
    if root is None:
        return None
    import work_ledger
    task = work_ledger.read_current(root)
    return task['task_id'] if task is not None else None


def current_task(root: Path, *, task: dict | None = None, report: dict | None = None,
                 read_run=None, run: str | None = None) -> dict | None:
    """Expose one continuation from the current work and its actual saved state.

    With `run`, the authoring state covers the drafts of that run alone, as
    inspect describes, and `authoring_action` names the view of the whole work task.
    """
    import work_ledger
    from production_diagnostics import from_exception
    try:
        task = work_ledger.read_current(root) if task is None else task
    except READ_ERRORS as exc:
        return {'task_id': None, 'goal': None, 'next': None, 'production_run': None,
                'diagnostics': [from_exception(exc, phase='status', file='work/current.json')]}
    if task is None:
        return None
    authoring = inspect(root, task, read_run=read_run, run=run) if report is None else report
    focus = ('authoring' if authoring['pending'] or not task.get('production_run') else
             'authored' if authoring['saved'] is not None else 'execution')
    result = {'task_id': task.get('task_id'), 'goal': task.get('goal'), 'next': task.get('next'),
              'production_run': task.get('production_run'), 'focus': focus,
              'next_actions': authoring['next_actions'], 'authoring': authoring}
    if run is not None:
        result['authoring_action'] = {'command': 'status',
            'argv': python_argv(ROOT / 'scripts/production_workflow.py', 'status', '--root', str(c._root(root))),
            'reason': f'This view inspected the drafts of run {run} alone. status without --run inspects every draft '
                      'of this work task, its readings and its last check.'}
    return result


def _directory(root: Path, task_id: str) -> Path:
    import work_ledger
    return work_ledger.task_path(root, task_id).parent / 'authoring'


def _remember(root: Path, task_id: str | None, kind: str, identity: str, details: dict) -> None:
    """Save the discovery pointer before its producer publishes the artifact."""
    if task_id is None:
        return
    import operation_context
    folder = _directory(root, task_id)
    owner = c.load(folder.parent / 'task.json')
    if owner['task_id'] != task_id:
        raise ValueError('authoring pointer belongs to another work task')
    path = folder / (kind + '-' + c.content_id(identity) + '.json')
    value = {'artifact_type': 'production-authoring-pointer', 'task_id': task_id,
             'kind': kind, 'created_at': operation_context.timestamp(),
             'operation_id': operation_context.current_operation_id(), 'details': details}
    try:
        c.atomic(path, c.encoded(value))
    except FileExistsError:
        old = c.load(path)
        if any(old.get(key) != value[key] for key in ('artifact_type', 'task_id', 'kind', 'details')):
            if kind in {'draft-inputs', 'build-inputs'} and not c.local(root, details['directory'], exists=False).exists():
                c.atomic(path, c.encoded(value), replace=True)
            else:
                raise ValueError('saved authoring pointer differs from its producer: ' + str(path))


def remember_inputs(root: Path, task: dict, kind: str, out_dir: str, *,
                    task_path: str | None, from_run: str | None, choices_path: str | None = None,
                    runtime_arguments: dict | None = None, context_sha256: str | None = None,
                    input_arguments: dict | None = None, publication: dict | None = None) -> None:
    if active_task_id(root) != task['task_id']:
        return
    if kind not in {'draft-inputs', 'build-inputs'}:
        raise ValueError('unknown input publication kind')
    c.local(root, out_dir, exists=False)
    details = {'directory': out_dir, 'source_task': task_path, 'source_run': from_run,
               'choices': choices_path, 'runtime_arguments': runtime_arguments}
    if context_sha256 is not None:
        details['context_sha256'] = c.sha(context_sha256)
    if publication is not None:
        details['publication'] = publication
    if kind == 'draft-inputs' and task_path is None and from_run is None:
        details['initial_task'] = task
        if input_arguments:
            details['input_arguments'] = input_arguments
    _remember(root, task['task_id'], kind, out_dir, details)


def published_draft(root: Path, task: dict, out_dir: str) -> None:
    """Record that a registered draft published its directory.

    A registration without this mark was interrupted before publication and
    is resumed. Once the mark exists, removing the directory withdraws the
    draft from the work task.
    """
    if active_task_id(root) != task['task_id']:
        return
    path = _directory(root, task['task_id']) / ('draft-inputs-' + c.content_id(out_dir) + '.json')
    value = c.load(path)
    value['details'] = {**value['details'], 'directory_published': True}
    c.atomic(path, c.encoded(value), replace=True)


def _withdrawn(root: Path, row: dict) -> bool:
    """Whether the author removed the directory of a published draft."""
    details = row['details']
    return (row['kind'] == 'draft-inputs' and details.get('directory_published') is True
            and not c.local(root, details['directory'], exists=False).exists())


def input_publication(root: Path, task_id: str, task_path: str) -> dict | None:
    """Read the exact registered export boundary without trusting a neighboring report."""
    folder = Path(task_path).parent.as_posix()
    pointer = _directory(root, task_id) / ('build-inputs-' + c.content_id(folder) + '.json')
    pointer = c.local(root, pointer.relative_to(root).as_posix(), exists=False)
    if not pointer.is_file():
        return None
    value = c.load(pointer)
    c.exact(value, {'artifact_type', 'task_id', 'kind', 'created_at', 'operation_id', 'details'},
            'input publication pointer')
    if (value['artifact_type'] != 'production-authoring-pointer' or value['task_id'] != task_id
            or value['kind'] != 'build-inputs' or value['details']['directory'] != folder):
        raise ValueError('input publication differs from its registered owner')
    publication = value['details'].get('publication')
    if publication is None or publication.get('task') != task_path:
        raise ValueError('the input export has no registered complete publication; rebuild from its editable choices')
    return publication


def remember_decision_draft(root: Path, task_id: str, run: str, kind: str, path: str,
                            *, context: dict | None = None) -> None:
    """Remember the producer's target and basis without copying editable answers."""
    from production_binding import studio_file
    if kind not in DECISION_KINDS:
        raise ValueError('unknown decision draft kind')
    path = studio_file(root, path, option='--out', exists=False).relative_to(root).as_posix()
    details = {'run': run, 'path': path}
    if context is not None:
        details['context'] = context
    identity = run + ':' + path + (':' + c.content_id(context) if context is not None else '')
    _remember(root, task_id, kind + '-draft', identity, details)


def decision_drafts(root: Path, task_id: str, *, kind: str | None = None, run: str | None = None,
                    context: object = _ANY_CONTEXT, records: list[dict] | None = None) -> list[dict]:
    """Resolve producer-owned draft locations without reading their unfinished answers."""
    if kind is not None and kind not in DECISION_KINDS:
        raise ValueError('unknown decision draft kind')
    rows = _records(root, task_id, []) if records is None else records
    result = []
    for row in rows:
        decision_kind = row['kind'].removesuffix('-draft')
        if decision_kind not in DECISION_KINDS or (kind is not None and decision_kind != kind):
            continue
        details = row['details']
        c.exact(details, {'run', 'path'} | ({'context'} if 'context' in details else set()),
                'decision draft pointer')
        if run is not None and details['run'] != run:
            continue
        if context is not _ANY_CONTEXT and details.get('context') != context:
            continue
        path = c.local(root, details['path'], exists=False)
        result.append({**details, 'kind': decision_kind, 'available': path.is_file(),
                       'created_at': row['created_at']})
    return result


def decision_file_state(root: Path, path: str, expected: dict, *, required: set[str] = frozenset()) -> str:
    """Inspect ownership fields only; unfinished answers never choose their own target."""
    try:
        value = c.load(c.local(root, path))
    except READ_ERRORS:
        return 'unfinished'
    if not isinstance(value, dict) or not (expected.keys() | required) <= value.keys():
        return 'unfinished'
    return 'current' if all(value[key] == expected[key] for key in expected) else 'other-target'


def _input_registration(root: Path, task_id: str, out_dir: str) -> dict | None:
    path = _directory(root, task_id) / ('draft-inputs-' + c.content_id(out_dir) + '.json')
    if not path.is_file():
        return None
    value = c.load(path)
    c.exact(value, {'artifact_type', 'task_id', 'kind', 'created_at', 'operation_id', 'details'},
            'authoring pointer')
    if (value['artifact_type'] != 'production-authoring-pointer' or value['task_id'] != task_id
            or value['kind'] != 'draft-inputs' or value['details']['directory'] != out_dir):
        raise ValueError('draft registration does not identify this task and input directory')
    c.sha(value['details']['context_sha256'])
    return value


def _input_recovery(root: Path, task_id: str, out_dir: str, code: str,
                    registration: dict | None) -> dict:
    """Derive a recovery command only from the owning registration, never the failed context."""
    inspect = _action(root, 'inspect-inputs',
        reason='Locate the registered authoring source and continue its owning work task.')
    if registration is None or active_task_id(root) != task_id:
        return inspect
    details = registration['details']
    source = _source_arguments(details, initial_task=details.get('initial_task'))
    if not source:
        return inspect
    if code == 'IDENTITY_SOURCE_UNAVAILABLE' or (
            code == 'IDENTITY_SOURCE_CHANGED' and details.get('source_run')):
        selected = ['--task', details['source_task']] if details.get('source_task') else (
            ['--from-run', details['source_run']] if details.get('source_run') else [])
        return _action(root, 'inspect-inputs', *selected,
            reason='Inspect the owning evidence and resolve its current source before drafting its application again.')
    folder = Path(out_dir)
    stem = (folder.name or 'draft') + '-current'
    destination = folder if not c.local(root, out_dir, exists=False).exists() else folder.parent / stem
    number = 2
    while c.local(root, destination.as_posix(), exists=False).exists():
        destination = folder.parent / (stem + '-' + str(number))
        number += 1
    if details.get('source_task') or details.get('source_run'):
        source += ['--task-id', task_id]
    return _action(root, 'draft-inputs', *source, '--out-dir', destination.as_posix(),
        *_arguments(details.get('runtime_arguments') or {}),
        reason='Create a registered draft from its owning source, then reassess the application and criteria; existing choices remain available.')


def input_context_error(root: Path, task_id: str, out_dir: str, *, code: str,
                        message: str, file: str | None = None,
                        pointer: str | None = 'authoring.task.sources',
                        phase: str = 'authoring-context', registration: dict | None = None,
                        **details: Any):
    """Report the failed evidence boundary with an executable source-owned recovery."""
    from production_diagnostics import ProductionError
    try:
        registration = registration or _input_registration(root, task_id, out_dir)
        action = _input_recovery(root, task_id, out_dir, code, registration)
    except READ_ERRORS:
        action = _action(root, 'inspect-inputs',
            reason='Inspect the work task and repair its registered authoring source before continuing.')
    return ProductionError(code, message, phase=phase,
        file=file or (Path(out_dir) / 'context.json').as_posix(), pointer=pointer,
        required_action=action['reason'], task_id=task_id, draft_directory=out_dir,
        next_action=action, next_actions=[action], **details)


def require_input_context(root: Path, task_id: str, out_dir: str, raw: bytes, *,
                          required: bool = True) -> dict | None:
    """Check the registered location and exact context independently of identity judgment."""
    try:
        _directory(root, task_id)
    except (ValueError, TypeError) as exc:
        if not required:
            return None
        raise input_context_error(root, task_id, out_dir, code='AUTHORING_DRAFT_UNREGISTERED',
            message='The draft has no registered work-task owner.', pointer='$', cause=str(exc)) from exc
    try:
        registration = _input_registration(root, task_id, out_dir)
    except READ_ERRORS as exc:
        path = _directory(root, task_id) / ('draft-inputs-' + c.content_id(out_dir) + '.json')
        raise input_context_error(root, task_id, out_dir, code='AUTHORING_DRAFT_REGISTRATION_INVALID',
            message='The saved draft registration cannot establish its source context.',
            file=path.relative_to(root).as_posix(), pointer='$', cause=str(exc)) from exc
    if registration is None:
        if not required:
            return None
        raise input_context_error(root, task_id, out_dir, code='AUTHORING_DRAFT_UNREGISTERED',
            message='This input directory is not a registered draft of the work task.', pointer='$')
    if not raw:
        raise input_context_error(root, task_id, out_dir, code='AUTHORING_CONTEXT_MISSING',
            message='The registered draft source context is missing or empty.',
            pointer='$', registration=registration)
    expected = registration['details']['context_sha256']
    actual = c.digest(raw)
    if expected != actual:
        raise input_context_error(root, task_id, out_dir, code='AUTHORING_CONTEXT_MISMATCH',
            message='The draft source context differs from its registered publication.',
            pointer='$', registration=registration, expected_sha256=expected, actual_sha256=actual)
    return registration


def remember_reading(root: Path | None, ledger: Path, snapshot_id: str, snapshot: dict,
                     page_bytes: int) -> None:
    if root is not None:
        import route_reading
        _remember(root, snapshot['task_id'], 'route-reading', snapshot_id,
                  {'ledger': str(ledger.absolute()), 'snapshot': snapshot_id, 'page_bytes': page_bytes,
                   'route': snapshot['manifest']['route'], 'features': snapshot['manifest']['features'],
                   'operation': snapshot['manifest']['operation'],
                   'execution': snapshot['manifest']['execution'], 'model': snapshot['manifest']['model'],
                   'model_file': snapshot['model_file'],
                   'dialect': route_reading.bound_dialect(snapshot['manifest']),
                   'skill_root': snapshot['root'], 'runtime': snapshot['runtime']})


def remember_reading_record(root: Path | None, ledger: Path, path: Path, *,
                            snapshot: str | None = None, task_id: str | None = None) -> None:
    if root is not None:
        _remember(root, task_id or active_task_id(root), 'reading-record', str(path.absolute()),
                  {'ledger': str(ledger.absolute()), 'path': str(path.absolute()), 'snapshot': snapshot})


def _action(root: Path, command: str, *arguments: str, reason: str) -> dict:
    argv = python_argv(SCRIPT, command, '--root', str(c._root(root)), *arguments)
    return {'command': command, 'argv': argv, 'shown': shown(argv), 'reason': reason}


def _arguments(values: dict) -> list[str]:
    result = []
    for name, value in values.items():
        if value is True:
            result.append('--' + name)
        elif value is not None and value is not False:
            for item in value if isinstance(value, list) else [value]:
                result.extend(('--' + name, str(item)))
    return result


def _runtime_basis(values: dict | None) -> dict | None:
    if values is None:
        return None
    result = {}
    for name, value in values.items():
        if name in {'state-file', 'cache-dir', 'managed-root'}:
            value = str(Path(value).resolve())
        elif name == 'pack-root':
            value = [str(Path(item).resolve()) for item in value]
        result[name] = value
    return result


def _input_runtime(values: dict | None):
    """Inspect current choices within their producer's selected live runtime."""
    if not values:
        return nullcontext()
    from catalog_retrieval.runtime import using_pack_runtime
    from pack_manager import default_settings
    settings = default_settings(state_file=Path(values['state-file']), cache_dir=Path(values['cache-dir']),
        managed_root=Path(values['managed-root']), extra_roots=[Path(path) for path in values.get('pack-root', [])])
    return using_pack_runtime(settings)


def _scope(task: dict, *, root: Path, choices: dict | None = None) -> dict:
    import execution_routes
    operation = 'author' if task.get('execution') == 'authored' else 'prepare'
    resolved = execution_routes.resolve(task['route'], task['features'], operation=operation,
                                        execution=task['execution'])
    if choices is not None:
        target = choices.get('target') or {}
        kind = target.get('kind')
        model, service = None, target.get('service')
        if kind == 'catalog':
            model = target.get('model')
        elif kind == 'acquired' and target.get('model_file'):
            model = c.load(c.local(root, target['model_file'])).get('id')
        elif kind == 'external':
            external = (target.get('model') or {}).get('target') or {}
            model, service = external.get('model_identifier'), external.get('service')
    else:
        target = (task.get('generation') or task.get('upscale')
                  or (task.get('authored') or {}).get('target') or {})
        model, service = target.get('model'), target.get('service')
        if model is None and target.get('model_file'):
            model = c.load(c.local(root, target['model_file'])).get('id')
        if model is None and target.get('production_spec'):
            path = c.local(root, target['production_spec'], exists=False)
            if path.is_file():
                model = c.load(path).get('target_model')
    return {'route': resolved['route'], 'operation': operation, 'execution': task['execution'],
            'features': resolved['features'],
            'documents': resolved['reads'], 'model': model, 'service': service}


def _source_arguments(details: dict, *, initial_task: dict | None = None) -> list[str]:
    if details['source_task']:
        return ['--task', details['source_task']]
    if details['source_run']:
        return ['--from-run', details['source_run']]
    if initial_task is None:
        return []
    return ['--route', initial_task['route'], '--artifact', initial_task['artifact'],
            '--execution', initial_task['execution'], '--task-id', initial_task['task_id'],
            *[part for feature in initial_task['features'] for part in ('--feature', feature)],
            *_arguments(details.get('input_arguments') or {})]


def _problem(path: str, exc: BaseException) -> dict:
    return {'code': 'AUTHORING_STATE_UNREADABLE', 'file': path, 'message': str(exc)}


def _run(root: Path, identifier: str, cache: dict | None) -> tuple:
    import production_workflow
    if cache is None:
        return production_workflow.read_run(root, identifier)
    if identifier not in cache:
        cache[identifier] = production_workflow.read_run(root, identifier)
    return cache[identifier]


def _records(root: Path, task_id: str, diagnostics: list) -> list[dict]:
    folder = _directory(root, task_id)
    result = []
    for path in sorted(folder.glob('*.json')):
        try:
            value = c.load(c.local(root, path.relative_to(root).as_posix()))
            c.exact(value, {'artifact_type', 'task_id', 'kind', 'created_at', 'operation_id', 'details'},
                    'authoring pointer')
            if value['artifact_type'] != 'production-authoring-pointer' or value['task_id'] != task_id:
                raise ValueError('authoring pointer belongs to another work task')
            if value['kind'] not in ({'draft-inputs', 'build-inputs', 'route-reading', 'reading-record'}
                                     | {kind + '-draft' for kind in DECISION_KINDS}):
                raise ValueError('unknown authoring pointer kind')
            c.text(value['created_at'], 'authoring pointer time')
            if not isinstance(value['details'], dict):
                raise ValueError('authoring pointer details must be an object')
            result.append(value)
        except READ_ERRORS as exc:
            diagnostics.append(_problem(path.relative_to(root).as_posix(), exc))
    return sorted(result, key=lambda row: (row['created_at'], row['kind']))


def _input_location(root: Path, row: dict) -> tuple[Path, dict]:
    details = row['details']
    directory = c.local(root, details['directory'], exists=False)
    result = {**details, 'kind': row['kind'], 'operation_id': row['operation_id'],
              'created_at': row['created_at'], 'published': directory.is_dir(),
              'unresolved': [], 'next_actions': []}
    return directory, result


def _input(root: Path, row: dict, *, include_working: bool = True, read_run=None) -> dict:
    details = row['details']
    directory, result = _input_location(root, row)
    task_path = directory / 'production-task.json'
    report_path = directory / 'input-report.json'
    if row['kind'] == 'build-inputs' and task_path.is_file() and report_path.is_file():
        task = c.load(task_path)
        report = c.load(report_path)
        if task.get('task_id') != row['task_id']:
            raise ValueError('saved production task belongs to another work task')
        result.update(state='built', task=task_path.relative_to(root).as_posix(),
                      report=report_path.relative_to(root).as_posix(),
                      route_scope=_scope(task, root=root), task_sha256=c.content_id(task),
                      assembly_basis={'task': report['derived_from']['task'],
                                      'choices': report['derived_from']['choices'],
                                      'runtime_arguments': _runtime_basis(details['runtime_arguments'])},
                      assessment_required=report.get('assessment_required', []))
        selected = next((action for action in report['next_actions']
                         if action['operation'] in {'prepare', 'retarget', 'save'}), None)
        if selected is None:
            raise ValueError('saved input report has no preparation action')
        arguments = {key: value for key, value in selected['args'].items() if key != 'root'}
        result['next_actions'] = [_action(root, selected['operation'], *_arguments(arguments),
                                          reason=selected.get('reason', 'Prepare the saved built task and its current inputs.'))]
        if selected.get('requires_author_input'):
            result['next_actions'][0]['requires_author_input'] = True
        # The published directory is immutable. Its editable source may have
        # changed since publication, including after this task was prepared.
        # Keep both states visible and resume those choices before offering the
        # older materialized task as the continuation of current authoring.
        choices = c.local(root, details['choices'], exists=False) if details['choices'] else None
        if include_working and choices is not None and choices.is_file():
            working = _authored_input(root, row, read_run=read_run)
            source_basis = working.get('assembly_basis')
            choices_changed = (source_basis is None or
                source_basis['choices'] != result['assembly_basis']['choices'])
            task_changed = (working.get('source_available') and source_basis is not None and
                source_basis['task'] != result['assembly_basis']['task'])
            if choices_changed or task_changed:
                result.update(working_copy=working, unresolved=working['unresolved'],
                              next_actions=working['next_actions'])
                if working.get('route_scope') is not None:
                    result['route_scope'] = working['route_scope']
        return result
    return _authored_input(root, row, read_run=read_run)


def _authored_input(root: Path, row: dict, *, read_run=None) -> dict:
    details = row['details']
    directory, result = _input_location(root, row)
    choices = directory / 'choices.json' if row['kind'] == 'draft-inputs' else (
        c.local(root, details['choices'], exists=False) if details['choices'] else None)
    context_path = (choices.parent if choices is not None else directory) / 'context.json'
    try:
        raw = c.read(context_path) if context_path.is_file() else b''
        require_input_context(root, row['task_id'], context_path.parent.relative_to(root).as_posix(),
                              raw, required=row['kind'] == 'draft-inputs')
        context = c.decode(raw) if raw else None
    except READ_ERRORS as exc:
        from production_diagnostics import from_exception
        diagnostic = from_exception(exc, phase='authoring-context',
                                    file=context_path.relative_to(root).as_posix())
        result.update(state='choices' if choices is not None and choices.is_file() else 'unpublished',
            source_available=False, source_diagnostic=diagnostic['message'],
            unresolved=[{**diagnostic, 'field': 'context'}], diagnostics=[diagnostic],
            next_actions=diagnostic.get('next_actions', [_action(root, 'inspect-inputs',
                reason='Resolve the current draft source context before continuing authoring.')]))
        if choices is not None:
            result['choices'] = choices.relative_to(root).as_posix()
        return result
    if context is not None:
        result['context'] = context_path.relative_to(root).as_posix()
    result['source_available'] = True
    try:
        if details['source_task']:
            path = c.local(root, details['source_task'])
            raw = c.read(path)
            task = c.decode(raw)
            task_basis = {'path': details['source_task'], 'sha256': c.digest(raw)}
        elif details['source_run']:
            _, prepared, _, _ = read_run(details['source_run'])
            task = prepared['task']
            task_basis = {'run': details['source_run'], 'input_sha256': prepared['input_sha256']}
        elif context is not None and choices is not None:
            from production_inputs import _choice_source, InputEvidence
            task, task_basis, _, _, _ = _choice_source(
                root, choices.relative_to(root).as_posix(), InputEvidence(root), read_run=read_run)
        elif row['kind'] == 'draft-inputs' and not directory.exists() and details.get('initial_task'):
            task = details['initial_task']
            task_basis = {'initial': True, 'task_id': task['task_id']}
        else:
            raise ValueError('initial authoring needs its saved source context')
    except READ_ERRORS as exc:
        task = context['task_content'] if context is not None else None
        task_basis = context['derived_from']['task'] if context is not None else None
        result.update(source_available=False, source_diagnostic=str(exc))
    if task is not None and task.get('task_id') != row['task_id']:
        if context is None or context.get('task_binding') != {'task_id': row['task_id']}:
            raise ValueError('saved input source belongs to another work task')
        from production_inputs import _bind_task
        task = _bind_task(task, row['task_id'])
    if choices is not None and choices.is_file():
        import production_inputs
        result.update(state='choices', choices=choices.relative_to(root).as_posix())
        result['next_actions'] = [{'command': 'edit-choices', 'path': str(choices),
                                  'reason': 'Continue the editable source files and unresolved choices.'}]
        try:
            with _input_runtime(details['runtime_arguments']):
                view = production_inputs.authoring_view(root, result['choices'],
                    task_path=details['source_task'], from_run=details['source_run'], read_run=read_run,
                    runtime_arguments=details['runtime_arguments'])
            selected = view['resolved_choices']
            chosen = view['task']
            result['unresolved'] = view['unresolved']
            result['editable_locations'] = view['source_map']
            if chosen is not None:
                result['route_scope'] = _scope(chosen, root=root, choices=selected)
        except READ_ERRORS as exc:
            from production_diagnostics import from_exception
            diagnostic = from_exception(exc, phase='authoring', file=result['choices'],
                                        code='authored-input-unreadable')
            result['unresolved'] = [{**diagnostic, 'field': 'choices', 'path': result['choices']}]
            result['diagnostics'] = [diagnostic]
            if diagnostic.get('next_actions'):
                result['next_actions'] = diagnostic['next_actions']
            return result
        result['assembly_basis'] = {'task': task_basis,
            'choices': view['choices_ref'],
            'runtime_arguments': _runtime_basis(details['runtime_arguments'])}
        if not result['unresolved'] and result['source_available']:
            result['next_actions'] = [production_inputs.continuation_action(root, chosen, result['choices'],
                details['runtime_arguments'], view['source_run'], view['target_identity'])]
        elif chosen is not None and chosen.get('execution') == 'authored':
            result['next_actions'].append(_action(root, 'save', '--choices', result['choices'], '--draft',
                *_arguments(details['runtime_arguments'] or {}),
                reason='Save the unfinished authored revision with these unresolved choices.'))
    else:
        result['state'] = 'unpublished'
        if row['kind'] == 'draft-inputs' and not directory.exists() and result['source_available']:
            source = _source_arguments(details, initial_task=task)
            result['next_actions'] = [_action(root, 'draft-inputs', *source,
                '--out-dir', details['directory'], *_arguments(details['runtime_arguments'] or {}),
                reason='Resume the unpublished draft using its saved source and unused directory; authored choices remain unanswered.')]
        elif choices is not None:
            result['unresolved'] = [{'field': 'choices', 'code': 'authored-input-missing',
                                     'path': choices.relative_to(root).as_posix()}]
        else:
            result['assessment_required'] = ['Restore the declared authored choices before building inputs.']
    return result


def _reading(root: Path, row: dict, records: list[dict]) -> dict:
    import route_reading
    details = row['details']
    ledger = Path(details['ledger'])
    folder = c.local(ledger.parent, 'reading-snapshots/' +
                     route_reading._hex(details['snapshot'], 64, 'reading snapshot'), exists=False)
    base = {'snapshot': details['snapshot'], 'ledger': details['ledger'], 'created_at': row['created_at'],
            'route': details['route'], 'operation': details['operation'],
            'execution': details['execution'], 'model': details['model'],
            'features': details['features'], 'next_actions': []}
    def restart(reason):
        argv = python_argv(Path(details['skill_root']) / 'scripts/execution_routes.py', 'read', details['route'],
                           '--operation', details['operation'], '--execution', details['execution'],
                           '--reading-ledger', details['ledger'],
                           '--root', str(c._root(root)),
                           '--page-bytes', str(details['page_bytes']))
        for feature in details['features']:
            argv.extend(('--feature', feature))
        if details['model'] is not None:
            argv.extend(('--model-file', details['model_file']) if details['model_file'] is not None
                        else ('--model', details['model']['id']))
            if details['model']['service'] is not None:
                argv.extend(('--service', details['model']['service']))
        elif details['dialect'] is not None:
            argv.extend(('--dialect', details['dialect']))
        runtime = route_reading._runtime_context(details['runtime'])
        if runtime is not None:
            argv.extend(runtime.command_arguments())
        action = {'argv': argv, 'command': shown(argv), 'reason': reason}
        return {**base, 'state': 'unpublished', 'publication_diagnostic': reason,
                'next_actions': [action], 'actions': {'restart': action}}
    if not (folder / 'snapshot.json').is_file():
        return restart('The reading attempt has no published snapshot. Start its declared route reading; no receipt or key is reconstructed.')
    snapshot = c.load(folder / 'snapshot.json')
    if c.content_id(snapshot) != details['snapshot'] or snapshot.get('task_id') != row['task_id']:
        raise ValueError('reading snapshot differs from its saved task pointer')
    base['documents'] = snapshot['manifest']['documents']
    coverage = route_reading.snapshot_coverage(folder, snapshot)
    pages = coverage['pages']
    total, delivered = coverage['total_bytes'], coverage['delivered_bytes']
    result = {**base,
              'delivered_bytes': delivered, 'remaining_bytes': total - delivered,
              'required_bytes': sum(item['size'] for item in snapshot['required_bodies']),
              'reused_bytes': sum(item['body']['size'] for item in snapshot['reused_bodies']),
              'same_context_required': bool(snapshot['context_keys'] or delivered),
              'source_freshness': 'not-rechecked',
              'next_actions': []}
    saved = [item['details']['path'] for item in records if item['kind'] == 'reading-record'
             and item['details']['snapshot'] == details['snapshot']]
    present = [path for path in saved if Path(path).is_file()]
    if present:
        for path in present:
            record = c.load(Path(path))
            route_reading.validate_record_content(record)
            if any(record[key] != snapshot['manifest'][key]
                   for key in route_reading.MANIFEST_FIELDS):
                raise ValueError('saved reading record differs from its snapshot')
            route_reading._find_row(record, [ledger])
        fresh = restart('Deliver the complete current contract when this agent or context has not read it.')
        result.update(state='recorded', records=present, fresh_context_action=fresh['next_actions'][0])
        return result
    if not pages:
        return restart('The snapshot has no delivered page receipt. Start its declared route reading; the existing snapshot stays available for inspection.')
    continuation = folder / 'continuation.json'
    if not continuation.is_file():
        argv = python_argv(Path(details['skill_root']) / 'scripts/execution_routes.py', 'read',
            '--snapshot', details['snapshot'], '--reading-ledger', details['ledger'],
            '--root', str(c._root(root)), '--page-bytes', str(details['page_bytes']))
        runtime = route_reading._runtime_context(details['runtime'])
        if runtime is not None:
            argv.extend(runtime.command_arguments())
        action = {'argv': argv, 'command': shown(argv),
                  'reason': 'No delivery continuation is selected; inspect the exact retained coverage and choose a source or section.'}
        result.update(state='partial' if delivered < total else 'delivered', mode='index',
                      actions={'index': action}, next_actions=[action],
                      fresh_context_action=restart('Index current sources when their text is no longer available in this context.')['next_actions'][0])
        return result
    selected = c.load(continuation)
    c.exact(selected, {'snapshot', 'page'}, 'selected reading continuation')
    page_id = route_reading._hex(selected['page'], 64, 'reading page')
    page = dict(pages).get(page_id)
    if selected['snapshot'] != details['snapshot'] or page is None:
        raise ValueError('selected reading continuation has no matching delivery page')
    result['cursor'] = details['snapshot'] + ':' + page_id
    actions = route_reading._reading_actions(result, ledger=ledger, studio=root,
        page_bytes=page.get('page_bytes', details['page_bytes']),
        acquired=(folder, snapshot, page), coverage=coverage)
    result.update(state='partial' if delivered < total else 'delivered', actions=actions,
                  mode='index' if page.get('index') else 'section' if 'section' in page else 'all')
    result['next_actions'] = [actions['continue'] or actions['next'] or actions['all']]
    result['fresh_context_action'] = restart(
        'Read the complete current contract after a context change; saved receipts and pages do not establish retained knowledge.')['next_actions'][0]
    if delivered == total:
        result['assessment_required'] = ['No saved reading record is available. Replaying the final page is an explicit reading action.']
    return result


def _last_check(root: Path, task_id: str) -> dict | None:
    from operation_context import list_operations
    matching = []
    for row in list_operations(root):
        metadata = row.get('metadata') or {}
        args = metadata.get('arguments') or {}
        if args.get('command') != 'check' or not isinstance(args.get('task'), str):
            continue
        try:
            task = c.load(c.local(root, args['task']))
        except READ_ERRORS:
            continue
        if task.get('task_id') == task_id:
            matching.append(row)
    if not matching:
        return None
    row = max(matching, key=lambda item: item['metadata'].get('created_at', ''))
    return {'task': row['metadata']['arguments']['task'], 'operation_id': row['operation_id'],
            'created_at': row['metadata']['created_at'], 'complete': row['complete'],
            'exit_code': row['exit_code'], 'log_directory': row['path'],
            'freshness': 'not-rechecked',
            'meaning': 'Saved diagnostic result only; current inputs and execution authority are checked by their owning commands.'}


def _source_links(root: Path, task: dict, *, source_run: str | None, read_run) -> list[dict]:
    """Keep each source's authored role and both current and saved locations."""
    directory, dependencies = None, {}
    if source_run is not None:
        directory, prepared, _, _ = read_run(source_run)
        dependencies = {item['path']: item for item in prepared['dependencies'] if item['space'] != 'skill'}
    result = []
    for source in task.get('sources', []):
        entry = dict(source)
        name = source['path']
        if name.startswith('@skill/'):
            path = c.local(ROOT, name[len('@skill/'):], exists=False)
        elif name.startswith('@'):
            path = None
        else:
            path = c.local(root, name, exists=False)
        entry['current_file'] = str(path) if path is not None else None
        entry['current_available'] = path.is_file() if path is not None else None
        saved = dependencies.get(name)
        if saved is not None:
            entry['source_run_file'] = {'path': str(directory / 'objects' / saved['sha256']),
                                        'sha256': saved['sha256'], 'run': source_run}
        result.append(entry)
    return result


def _context(root: Path, task: dict, selected: dict | None, *, read_run) -> dict:
    """Gather the active judgment and its evidence without changing any artifact."""
    import work_ledger
    result = {'work': {key: task.get(key) for key in
                       ('task_id', 'goal', 'steps', 'next', 'notes', 'questions', 'blocked_on', 'production_run')},
              'work_file': str(work_ledger.task_path(root, task['task_id'])),
              'input': None}
    if selected is None:
        return result
    row = selected.get('working_copy', selected)
    current = {'state': row['state'], 'directory': str(root / row['directory']),
               'source_task': str(c.local(root, row['source_task'], exists=False)) if row.get('source_task') else None,
               'source_run': row.get('source_run'),
               'unresolved': row['unresolved'], 'assessment_required': row.get('assessment_required', []),
               'choices_file': str(root / row['choices']) if row.get('choices') else None,
               'published_task': str(root / selected['task']) if selected.get('task') else None,
               'prepared_run': selected.get('prepared_run'),
               'changed_since_build': bool(selected.get('working_copy') or selected.get('changed_since_save')),
               'editable_locations': row.get('editable_locations', {})}
    result['input'] = current
    choices = None
    if row.get('choices'):
        import production_inputs
        try:
            choices = production_inputs.read_choices(c.load(c.local(root, row['choices'])))
            current['choices'] = choices
        except READ_ERRORS as exc:
            current['choices_diagnostic'] = str(exc)
    source = None
    try:
        if row.get('source_task'):
            source = c.load(c.local(root, row['source_task']))
        elif row.get('source_run'):
            _, prepared, _, _ = read_run(row['source_run'])
            source = prepared['task']
    except READ_ERRORS as exc:
        current['source_diagnostic'] = str(exc)
    if source is None and row.get('context'):
        source = c.load(c.local(root, row['context'])).get('task_content')
    if source is not None:
        if choices is not None:
            import production_inputs
            try:
                if row.get('context'):
                    context = c.load(c.local(root, row['context']))
                    if context.get('task_binding') == {'task_id': task['task_id']}:
                        source = production_inputs._bind_task(source, task['task_id'])
                source = production_inputs._chosen_task(source, choices)
            except READ_ERRORS as exc:
                current['task_diagnostic'] = str(exc)
                source = None
    if source is not None:
        current['task_content'] = source
        try:
            current['sources'] = _source_links(root, source, source_run=row.get('source_run'), read_run=read_run)
        except READ_ERRORS as exc:
            current['sources_diagnostic'] = str(exc)
    current['instruction'] = ('Continue the selected choices and resolve the named judgments. '
        'Use the source locations to inspect their actual contents. The published task and existing run '
        'retain their exact input; saving or preparation compiles the current editable sources.')
    return result


def _run_draft_directories(read_run, run: str) -> set[str]:
    """The folders of the draft or export whose choices or task prepared `run`."""
    prepared = read_run(run).prepared
    folders = {Path(prepared['task_path']).parent.as_posix()}
    choices = (prepared.get('authoring') or {}).get('choices_ref')
    if choices is not None:
        folders.add(Path(choices['path']).parent.as_posix())
    return folders


def inspect(root: Path, task: dict | None = None, *, read_run=None, choices: str | None = None,
            run: str | None = None) -> dict:
    """Describe saved work for this ledger task, without producing inputs, keys or permissions.

    With `run`, only the drafts of that run are inspected: those reopened from
    it and the draft or export whose choices or task prepared it. The other
    drafts and the work task's last check are left out, so `status --run` does
    not compile every draft of the work task again.
    """
    import work_ledger
    root = c._root(root)
    task = work_ledger.read_current(root) if task is None else task
    result = {'state': 'authoring-state', 'task_id': task['task_id'] if task else None,
              'inputs': [], 'readings': [], 'decision_drafts': [], 'last_check': None, 'diagnostics': [],
              'next_actions': [], 'pending': False, 'context': None, 'saved': None,
              'selection_required': False, 'input_options': [],
              'external_effect': False}
    if task is None:
        return result
    try:
        records = _records(root, task['task_id'], result['diagnostics'])
    except READ_ERRORS as exc:
        records = []
        result['diagnostics'].append(_problem('work/tasks/' + task['task_id'] + '/authoring', exc))
    try:
        result['decision_drafts'] = decision_drafts(root, task['task_id'], records=records)
    except READ_ERRORS as exc:
        result['diagnostics'].append(_problem('decision draft locations', exc))
    if read_run is None:
        run_cache = {}
        read_run = lambda identifier: _run(root, identifier, run_cache)
    # Several drafts reopened from one run share that run's observation here.
    from production_inputs import SourceRuns
    if not isinstance(read_run, SourceRuns):
        read_run = SourceRuns(read_run)
    run_folders = None
    if run is not None:
        try:
            run_folders = _run_draft_directories(read_run, run)
        except READ_ERRORS as exc:
            run_folders = set()
            result['diagnostics'].append(_problem('production/' + run, exc))

    def of_run(row: dict) -> bool:
        details = row['details']
        return run_folders is None or details.get('source_run') == run or details['directory'] in run_folders

    for row in records:
        try:
            if row['kind'] in {'draft-inputs', 'build-inputs'}:
                # A published draft whose directory the author removed is no longer a branch of this work.
                if not _withdrawn(root, row) and of_run(row):
                    result['inputs'].append(_input(root, row, include_working=True, read_run=read_run))
            elif row['kind'] == 'route-reading':
                result['readings'].append(_reading(root, row, records))
            elif row['kind'] == 'reading-record' and row['details']['snapshot'] is None:
                import route_reading
                path = Path(row['details']['path'])
                value = c.load(path)
                route_reading.validate_record_content(value)
                route_reading._find_row(value, [Path(row['details']['ledger'])])
                result['readings'].append({'state': 'recorded', 'route': value['route'],
                                           'operation': value['operation'], 'model': value['model'],
                                           'execution': value['execution'],
                                           'documents': value['documents'],
                                           'features': value['features'], 'created_at': row['created_at'],
                                           'records': [str(path)], 'remaining_bytes': 0, 'next_actions': []})
        except READ_ERRORS as exc:
            result['diagnostics'].append(_problem(str(row['details']), exc))
    if run is None:
        try:
            result['last_check'] = _last_check(root, task['task_id'])
        except READ_ERRORS as exc:
            result['diagnostics'].append(_problem('logs/operations', exc))
    built = {c.content_id(row['assembly_basis']): row for row in result['inputs'] if row['state'] == 'built'}
    for row in result['inputs']:
        prior = built.get(c.content_id(row.get('assembly_basis')))
        if row['state'] == 'choices' and prior is not None:
            row.update(assembled_task=prior['task'], next_actions=[])
    if task.get('production_run'):
        try:
            loaded = read_run(task['production_run'])
            _, prepared, _, _ = loaded
            if prepared['task']['execution'] == 'authored':
                import production_authored
                saved = production_authored.status(root, loaded)
                result['saved'] = {'run': saved['run'], 'task_id': saved['task_id'],
                    'task_disposition': saved['task_disposition'],
                    'authored': saved['authored'], 'next_action': saved['next_action']}
                if (saved['task_disposition'] == 'completed'
                        and task.get('work_state') in {'active', 'suspended'}):
                    result['saved']['next_action'] = {'command': 'finish',
                        'argv': python_argv(ROOT / 'scripts/work_ledger.py', 'finish',
                            '--studio', str(root), '--run', saved['run']),
                        'reason': 'The authored revision is complete; close its owning work task after resolving its open author questions.'}
            for row in result['inputs']:
                if (row['state'] == 'built' and row['task'] == prepared['task_path']
                        and row['task_sha256'] == c.content_id(prepared['task'])):
                    row['prepared_run'] = task['production_run']
                    if not row.get('working_copy'):
                        row['next_actions'] = []
                current = row.get('working_copy', row)
                source = (current.get('assembly_basis') or {}).get('choices')
                saved = (prepared.get('authoring') or {}).get('choices_ref')
                if source is not None and saved is not None and source['path'] == saved['path']:
                    row['prepared_run'] = task['production_run']
                    row['changed_since_save'] = source != saved
                    if source == saved and not current['unresolved']:
                        row['next_actions'] = []
        except READ_ERRORS as exc:
            result['diagnostics'].append(_problem('production/' + task['production_run'], exc))
    branches = {}
    for row in result['inputs']:
        if row.get('assembled_task'):
            continue
        current = row.get('working_copy', row)
        identity = ('choices', current['choices']) if current.get('choices') else ('directory', row['directory'])
        previous = branches.get(identity)
        # Several immutable exports of the same editor are one editable
        # branch. Prefer that editor's own pointer, then its latest export.
        priority = (row['kind'] == 'draft-inputs', row['created_at'])
        if previous is None or priority > (previous['kind'] == 'draft-inputs', previous['created_at']):
            branches[identity] = row
    candidates = list(branches.values())
    # Prepared choices remain history even when another branch became the
    # task's latest run. Compare those publications only when an editable
    # choices source needs that history; unrelated runs do not inform an
    # authoring view with no such source.
    import production_store
    publications = []
    has_choice_sources = any((row.get('working_copy', row).get('assembly_basis') or {}).get('choices')
                             is not None for row in candidates)
    if has_choice_sources:
        for saved_run in production_store.runs(root, task_id=task['task_id']):
            try:
                prepared = read_run(saved_run['run_id']).prepared
                publication = prepared.get('authoring') or {}
                if publication.get('choices_ref') is not None:
                    publications.append((saved_run['run_id'], publication['choices_ref']))
            except READ_ERRORS as exc:
                result['diagnostics'].append(_problem('production/' + saved_run['run_id'], exc))
    for row in candidates:
        current = row.get('working_copy', row)
        source = (current.get('assembly_basis') or {}).get('choices')
        matches = [run for run, ref in publications if source == ref]
        if matches and not current['unresolved']:
            row['prepared_runs'] = matches
            row.setdefault('prepared_run', matches[-1])
            row['changed_since_save'] = False
            if not row.get('working_copy'):
                row['next_actions'] = []
    def pending(row):
        return bool(not row.get('prepared_run') or row.get('working_copy')
                    or row.get('changed_since_save') or row['unresolved'])
    pending_inputs = [row for row in candidates if pending(row)]
    if choices is not None:
        selected = [row for row in candidates if row.get('working_copy', row).get('choices') == choices]
        if len(selected) != 1:
            raise ValueError('select one registered editable choices path shown by inspect-inputs')
        selected_input = selected[0]
    elif len(pending_inputs) == 1:
        selected_input = pending_inputs[0]
    elif len(pending_inputs) > 1:
        selected_input = None
        result['selection_required'] = True
        for row in pending_inputs:
            current = row.get('working_copy', row)
            path = current.get('choices')
            if path is not None:
                action = _action(root, 'inspect-inputs', '--choices', path,
                    reason='Continue this explicitly selected editable branch.')
            else:
                action = next(iter(current['next_actions']), _action(root, 'inspect-inputs',
                    reason='Inspect this unfinished input publication.'))
            result['input_options'].append({'choices': path, 'directory': row['directory'],
                'source_run': row.get('source_run'), 'unresolved': current['unresolved'], 'action': action})
            result['next_actions'].append(action)
    else:
        selected_input = next((row for row in candidates if row.get('prepared_run') == task.get('production_run')), None)
        if selected_input is None and len(candidates) == 1:
            selected_input = candidates[0]
    scope = (selected_input or {}).get('route_scope')
    applicable = [row for row in result['readings']
                  if scope is None or (row['route'] == scope['route'] and set(scope['features']) <= set(row['features'])
                     and row['execution'] == scope['execution']
                     and all(item in row.get('documents', []) for item in scope['documents'])
                     and (not row['model'] or (row['model']['id'] == scope['model']
                          and (row['model']['service'] is None or row['model']['service'] == scope['service']))))]
    selected_reading = None if result['selection_required'] else max(applicable, key=lambda row: row['created_at'], default=None)
    result['pending'] = result['selection_required'] or bool(selected_input and pending(selected_input))
    for row in result['inputs']:
        row['current'] = row is selected_input
        if row['current']:
            result['next_actions'].extend(row['next_actions'])
    for row in result['readings']:
        row['current'] = row is selected_reading
        row['applicability'] = ('current-task-route' if row['current'] and scope else
                                'latest-reading' if row['current'] else 'historical')
        if row['current']:
            result['next_actions'] = row['next_actions'] + result['next_actions']
    if selected_reading and selected_reading['next_actions']:
        result['pending'] = True
    if result['saved'] is not None:
        result['saved']['working_changes'] = bool(selected_input and
            (selected_input.get('working_copy') or selected_input.get('changed_since_save')))
        if not result['pending'] and not result['next_actions'] and result['saved']['next_action']:
            action = dict(result['saved']['next_action'])
            if action.get('argv'):
                action['shown'] = shown(action['argv'])
            result['next_actions'] = [action]
    try:
        result['context'] = _context(root, task, selected_input, read_run=read_run)
    except READ_ERRORS as exc:
        result['diagnostics'].append(_problem('current authoring context', exc))
    return result


def session_lines(root: Path, task: dict, *, report: dict | None = None, read_run=None) -> list[str]:
    report = inspect(root, task, read_run=read_run) if report is None else report
    lines = []
    if report.get('selection_required'):
        lines.append('Several editable branches are pending. Select the intended branch before continuing:')
        for option in report['input_options']:
            lines.append((option['choices'] or option['directory']) + ': ' + option['action']['shown'])
    for saved in (item for item in report['inputs'] if item['current']):
        row = saved.get('working_copy', saved)
        if saved.get('working_copy'):
            lines.append('The editable input source has changed since ' + str(root / saved['task']) +
                         '. Continue these choices before preparing their next version.')
        if row['state'] == 'built':
            lines.append('Saved production task: ' + str(root / row['task']) +
                         '; input report: ' + str(root / row['report']))
        elif row.get('choices'):
            unanswered = ', '.join(item['field'] for item in row['unresolved']) or 'current application judgments'
            lines.append('Saved input choices: ' + str(root / row['choices']) + '; review: ' + unanswered)
        else:
            lines.append('Input publication is unfinished: ' + str(root / row['directory']))
        for action in row['next_actions']:
            if action.get('shown'):
                lines.append('Continue authoring: ' + action['shown'])
    for row in (item for item in report['readings'] if item['current']):
        if row['state'] == 'recorded':
            lines.extend('Saved source delivery: ' + path for path in row['records'])
            if row.get('fresh_context_action'):
                lines.append('Read the complete contract for a new context: ' + row['fresh_context_action']['command'])
        elif row['next_actions']:
            if row['state'] == 'unpublished':
                lines.append('Saved reading attempt: ' + row['snapshot'] + '; ' + row['publication_diagnostic'])
            lines.append('Resume route reading: ' + row['next_actions'][0]['command'])
    if report['saved'] is not None:
        saved = report['saved']
        revision = saved['authored']
        lines.append('Saved authored revision: ' + saved['run'] + '; state: ' + revision['state'] +
                     '; artifact: ' + revision['artifact'])
        if revision['missing']:
            lines.append('Requested results still pending: ' + ', '.join(revision['missing']))
        if not report['pending']:
            for action in report['next_actions']:
                if action.get('argv'):
                    lines.append('Continue saved work: ' + shown(action['argv']))
    if report['last_check']:
        check = report['last_check']
        lines.append('Last check of ' + str(root / check['task']) + ': exit code ' +
                     str(check['exit_code']) + '; logs: ' + check['log_directory'] + '; current inputs not rechecked.')
    for diagnostic in report['diagnostics']:
        lines.append('Saved authoring state needs inspection: ' + diagnostic['file'] + ': ' + diagnostic['message'])
    if lines:
        lines.append('Inspect saved inputs: ' + _action(root, 'inspect-inputs', reason='Read saved authoring state.')['shown'])
    return lines
