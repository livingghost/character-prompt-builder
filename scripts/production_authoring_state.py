"""Discover an open task's saved input choices and reading progress without rebuilding them."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import execution_contract as c
from cli_invocation import python_argv, shown

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/production_workflow.py'
READ_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError)


def active_task_id(root: Path | None) -> str | None:
    if root is None:
        return None
    import work_ledger
    task = work_ledger.read_current(root)
    return task['task_id'] if task is not None else None


def current_task(root: Path, *, task: dict | None = None, report: dict | None = None,
                 read_run=None) -> dict | None:
    """Expose one continuation from the current work and its actual saved state."""
    import work_ledger
    from production_diagnostics import from_exception
    try:
        task = work_ledger.read_current(root) if task is None else task
    except READ_ERRORS as exc:
        return {'task_id': None, 'goal': None, 'next': None, 'production_run': None,
                'diagnostics': [from_exception(exc, phase='status', file='work/current.json')]}
    if task is None:
        return None
    authoring = inspect(root, task, read_run=read_run) if report is None else report
    focus = ('authoring' if authoring['pending'] or not task.get('production_run') else
             'authored' if authoring['saved'] is not None else 'execution')
    return {'task_id': task.get('task_id'), 'goal': task.get('goal'), 'next': task.get('next'),
            'production_run': task.get('production_run'), 'focus': focus,
            'next_actions': authoring['next_actions'], 'authoring': authoring}


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
                    runtime_arguments: dict | None = None, context_sha256: str | None = None) -> None:
    if active_task_id(root) != task['task_id']:
        return
    if kind not in {'draft-inputs', 'build-inputs'}:
        raise ValueError('unknown input publication kind')
    c.local(root, out_dir, exists=False)
    details = {'directory': out_dir, 'source_task': task_path, 'source_run': from_run,
               'choices': choices_path, 'runtime_arguments': runtime_arguments}
    if context_sha256 is not None:
        details['context_sha256'] = c.sha(context_sha256)
    if kind == 'draft-inputs' and task_path is None and from_run is None:
        details['initial_task'] = task
    _remember(root, task['task_id'], kind, out_dir, details)


def require_input_context(root: Path, task_id: str, out_dir: str, raw: bytes, *, required: bool = True) -> None:
    """Check a draft's derived source evidence against its existing publication pointer."""
    try:
        directory = _directory(root, task_id)
    except ValueError:
        # Production task IDs need not be work-ledger UUIDs. An optional check
        # has no registered draft owner in that case; identity work requires one.
        if not required:
            return
        raise
    path = directory / ('draft-inputs-' + c.content_id(out_dir) + '.json')
    if not path.is_file():
        if not required:
            return
        raise ValueError('identity authoring needs the registered draft source context')
    pointer = c.load(path)
    if pointer['details'].get('context_sha256') != c.digest(raw):
        raise ValueError('identity draft source context changed; draft current sources again')


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
    argv = python_argv(SCRIPT, command, '--root', str(root.absolute()), *arguments)
    return {'command': command, 'argv': argv, 'shown': shown(argv), 'reason': reason}


def _arguments(values: dict) -> list[str]:
    return [part for name, value in values.items() for item in (value if isinstance(value, list) else [value])
            for part in ('--' + name, str(item))]


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


def _scope(task: dict, *, root: Path, choices: dict | None = None) -> dict:
    import execution_routes
    operation = 'author' if task.get('execution') == 'authored' else 'prepare'
    resolved = execution_routes.resolve(task['route'], task['features'], operation=operation,
                                        execution=task['execution'])
    authored = (choices or {}).get('authoring') or {}
    target = (authored.get('generation') or authored.get('upscale') or task.get('generation')
              or task.get('upscale') or (task.get('authored') or {}).get('target') or {})
    model = target.get('model')
    specification = (authored.get('documents') or {}).get('production_spec')
    if model is None and isinstance(specification, dict):
        model = specification.get('target_model')
    if model is None and target.get('model_file'):
        model = c.load(c.local(root, target['model_file'])).get('id')
    if model is None and target.get('production_spec'):
        path = c.local(root, target['production_spec'], exists=False)
        if path.is_file():
            model = c.load(path).get('target_model')
    return {'route': resolved['route'], 'operation': operation, 'execution': task['execution'],
            'features': resolved['features'],
            'documents': resolved['reads'], 'model': model, 'service': target.get('service')}


def _source_arguments(details: dict, *, initial_task: dict | None = None) -> list[str]:
    if details['source_task']:
        return ['--task', details['source_task']]
    if details['source_run']:
        return ['--from-run', details['source_run']]
    if initial_task is None:
        return []
    return ['--route', initial_task['route'], '--artifact', initial_task['artifact'],
            '--execution', initial_task['execution'], '--task-id', initial_task['task_id'],
            *[part for feature in initial_task['features'] for part in ('--feature', feature)]]


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
            if value['kind'] not in {'draft-inputs', 'build-inputs', 'route-reading', 'reading-record'}:
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
        selected = next((action for action in report['next_actions'] if action['operation'] == 'prepare'), None)
        if selected is None:
            raise ValueError('saved input report has no preparation action')
        arguments = {key: value for key, value in selected['args'].items() if key != 'root'}
        result['next_actions'] = [_action(root, 'prepare', *_arguments(arguments),
                                          reason='Prepare the saved built task and its current inputs.')]
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
    context_path = (choices.parent / 'context.json' if choices is not None
                    and not details['source_task'] and not details['source_run']
                    else directory / 'context.json')
    context = c.load(context_path) if context_path.is_file() else None
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
        raise ValueError('saved input source belongs to another work task')
    if choices is not None and choices.is_file():
        import production_inputs
        result.update(state='choices', choices=choices.relative_to(root).as_posix())
        result['next_actions'] = [{'command': 'edit-choices', 'path': str(choices),
                                  'reason': 'Continue the editable source files and unresolved choices.'}]
        try:
            view = production_inputs.authoring_view(root, result['choices'],
                task_path=details['source_task'], from_run=details['source_run'], read_run=read_run)
            selected = view['resolved_choices']
            chosen = view['task']
            result['unresolved'] = view['unresolved']
            result['editable_locations'] = view['source_map']
            if chosen is not None:
                result['route_scope'] = _scope(chosen, root=root, choices=selected)
        except READ_ERRORS as exc:
            result['unresolved'] = [{'field': 'choices', 'code': 'authored-input-unreadable',
                                    'path': result['choices'], 'message': str(exc)}]
            return result
        result['assembly_basis'] = {'task': task_basis,
            'choices': view['choices_ref'],
            'runtime_arguments': _runtime_basis(details['runtime_arguments'])}
        if not result['unresolved'] and result['source_available']:
            command = 'save' if chosen.get('execution') == 'authored' else 'prepare'
            result['next_actions'] = [_action(root, command, '--choices', result['choices'],
                *_arguments(details['runtime_arguments'] or {}),
                reason='Compile the current editable sources and ' + ('save their authored revision.' if command == 'save' else 'prepare their exact model input.'))]
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
                           '--root', str(root.absolute()),
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
    total = sum(item['size'] for item in snapshot['bodies'])
    pages = []
    for path in (folder / 'pages').glob('*.json'):
        page = c.load(path)
        if c.content_id(page) != path.stem or page['snapshot'] != details['snapshot']:
            raise ValueError('reading page differs from its saved address')
        if (type(page['start']) is not int or type(page['end']) is not int
                or not 0 <= page['start'] <= page['end'] <= total):
            raise ValueError('reading page has an invalid delivered range')
        pages.append((page['start'], page['end'], path.stem))
    reach = 0
    for start, end, _ in sorted(pages):
        if start > reach:
            break
        reach = max(reach, end)
    result = {**base,
              'delivered_bytes': reach, 'remaining_bytes': total - reach,
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
    cursors = [(start, end, page) for start, end, page in pages if end == reach]
    if not cursors:
        return restart('The snapshot has no delivered page receipt. Start its declared route reading; the existing snapshot stays available for inspection.')
    _, _, page = max(cursors)
    result['cursor'] = details['snapshot'] + ':' + page
    actions = route_reading._reading_actions(result, ledger=ledger, studio=root,
                                            page_bytes=details['page_bytes'])
    result.update(state='partial' if reach < total else 'delivered', actions=actions)
    result['next_actions'] = [actions['continue'] if 'continue' in actions else actions['replay']]
    if reach == total:
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


def inspect(root: Path, task: dict | None = None, *, read_run=None) -> dict:
    """Describe saved work for this ledger task, without producing inputs, keys or permissions."""
    import work_ledger
    root = Path(root).absolute()
    task = work_ledger.read_current(root) if task is None else task
    result = {'state': 'authoring-state', 'task_id': task['task_id'] if task else None,
              'inputs': [], 'readings': [], 'last_check': None, 'diagnostics': [],
              'next_actions': [], 'pending': False, 'context': None, 'saved': None,
              'external_effect': False}
    if task is None:
        return result
    try:
        records = _records(root, task['task_id'], result['diagnostics'])
    except READ_ERRORS as exc:
        records = []
        result['diagnostics'].append(_problem('work/tasks/' + task['task_id'] + '/authoring', exc))
    latest_input = max((row for row in records if row['kind'] in {'draft-inputs', 'build-inputs'}),
                       key=lambda row: row['created_at'], default=None)
    if read_run is None:
        run_cache = {}
        read_run = lambda identifier: _run(root, identifier, run_cache)
    for row in records:
        try:
            if row['kind'] in {'draft-inputs', 'build-inputs'}:
                result['inputs'].append(_input(root, row, include_working=row is latest_input, read_run=read_run))
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
    candidates = [row for row in result['inputs'] if not row.get('assembled_task')]
    selected_input = max(candidates, key=lambda row: row['created_at'], default=None)
    scope = (selected_input or {}).get('route_scope')
    applicable = [row for row in result['readings']
                  if scope is None or (row['route'] == scope['route'] and set(scope['features']) <= set(row['features'])
                     and row['execution'] == scope['execution']
                     and all(item in row.get('documents', []) for item in scope['documents'])
                     and (not row['model'] or (row['model']['id'] == scope['model']
                          and (row['model']['service'] is None or row['model']['service'] == scope['service']))))]
    selected_reading = max(applicable, key=lambda row: row['created_at'], default=None)
    result['pending'] = bool(selected_input and
                             (not selected_input.get('prepared_run') or selected_input.get('working_copy')
                              or selected_input.get('changed_since_save') or selected_input['unresolved']))
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
