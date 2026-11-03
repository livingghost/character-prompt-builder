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
                    runtime_arguments: dict | None = None) -> None:
    if active_task_id(root) != task['task_id']:
        return
    if kind not in {'draft-inputs', 'build-inputs'}:
        raise ValueError('unknown input publication kind')
    c.local(root, out_dir, exists=False)
    _remember(root, task['task_id'], kind, out_dir,
              {'directory': out_dir, 'source_task': task_path, 'source_run': from_run,
               'choices': choices_path, 'runtime_arguments': runtime_arguments})


def remember_reading(root: Path | None, ledger: Path, snapshot_id: str, snapshot: dict,
                     page_bytes: int) -> None:
    if root is not None:
        import route_reading
        _remember(root, snapshot['task_id'], 'route-reading', snapshot_id,
                  {'ledger': str(ledger.absolute()), 'snapshot': snapshot_id, 'page_bytes': page_bytes,
                   'route': snapshot['manifest']['route'], 'features': snapshot['manifest']['features'],
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


def _scope(task: dict) -> dict:
    import execution_routes
    resolved = execution_routes.resolve(task['route'], task['features'])
    return {'route': resolved['route'], 'features': resolved['features']}


def _build_action(root: Path, row: dict, choices: str, basis: dict) -> dict:
    details = row['details']
    original = Path(details['directory'])
    target = (original.with_name(original.name + '-built-' + c.content_id(basis)[:12])
              if row['kind'] == 'draft-inputs' else original)
    candidate = target
    number = 2
    while c.local(root, candidate.as_posix(), exists=False).exists():
        candidate = target.with_name(target.name + '-' + str(number))
        number += 1
    source = ['--task', details['source_task']] if details['source_task'] else ['--from-run', details['source_run']]
    return _action(root, 'build-inputs', *source, '--choices', choices, '--out-dir', candidate.as_posix(),
                   *_arguments(details['runtime_arguments'] or {}),
                   reason='Build from the saved choices and source into this unused directory after assessing the authored judgments.')


def _problem(path: str, exc: BaseException) -> dict:
    return {'code': 'AUTHORING_STATE_UNREADABLE', 'file': path, 'message': str(exc)}


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


def _input(root: Path, row: dict) -> dict:
    details = row['details']
    directory = c.local(root, details['directory'], exists=False)
    result = {**details, 'kind': row['kind'], 'operation_id': row['operation_id'],
              'created_at': row['created_at'], 'published': directory.is_dir(),
              'unresolved': [], 'next_actions': []}
    task_path = directory / 'production-task.json'
    report_path = directory / 'input-report.json'
    if row['kind'] == 'build-inputs' and task_path.is_file() and report_path.is_file():
        task = c.load(task_path)
        report = c.load(report_path)
        if task.get('task_id') != row['task_id']:
            raise ValueError('saved production task belongs to another work task')
        result.update(state='built', task=task_path.relative_to(root).as_posix(),
                      report=report_path.relative_to(root).as_posix(),
                      route_scope=_scope(task), task_sha256=c.content_id(task),
                      assembly_basis={'task': report['derived_from']['task'],
                                      'choices': report['derived_from']['choices'],
                                      'runtime_arguments': details['runtime_arguments']},
                      assessment_required=report.get('assessment_required', []))
        selected = next((action for action in report['next_actions'] if action['operation'] == 'prepare'), None)
        if selected is None:
            raise ValueError('saved input report has no preparation action')
        arguments = {key: value for key, value in selected['args'].items() if key != 'root'}
        result['next_actions'] = [_action(root, 'prepare', *_arguments(arguments),
                                          reason='Prepare the saved built task and its current inputs.')]
        return result
    context_path = directory / 'context.json'
    choices = directory / 'choices.json' if row['kind'] == 'draft-inputs' else (
        c.local(root, details['choices'], exists=False) if details['choices'] else None)
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
        else:
            import production_workflow
            _, prepared, _, _ = production_workflow.load_run(root, details['source_run'])
            task = prepared['task']
            task_basis = {'run': details['source_run'], 'input_sha256': prepared['input_sha256']}
    except READ_ERRORS as exc:
        task = context['task_content'] if context is not None else None
        task_basis = context['derived_from']['task'] if context is not None else None
        result.update(source_available=False, source_diagnostic=str(exc))
    if task is not None and task.get('task_id') != row['task_id']:
        raise ValueError('saved input source belongs to another work task')
    if choices is not None and choices.is_file():
        import production_inputs
        selected = production_inputs.read_choices(c.load(choices))
        result.update(state='choices', choices=choices.relative_to(root).as_posix())
        chosen = production_inputs._chosen_task(task, selected) if task is not None else None
        result['unresolved'] = (production_inputs._unresolved(selected, chosen) if chosen is not None
                                else production_inputs._missing(selected))
        if chosen is not None:
            result['route_scope'] = _scope(chosen)
        result['assembly_basis'] = {'task': task_basis,
            'choices': {'path': result['choices'], 'sha256': c.sha256_file(choices)},
            'runtime_arguments': details['runtime_arguments']}
        result['next_actions'] = [{'command': 'edit-choices', 'path': str(choices),
                                  'reason': 'Continue the saved choices and assess their declared applications.'}]
        if not result['unresolved'] and result['source_available']:
            result['next_actions'] = [_build_action(root, row, result['choices'], result['assembly_basis'])]
    else:
        result['state'] = 'unpublished'
        if row['kind'] == 'draft-inputs' and not directory.exists() and result['source_available']:
            source = (['--task', details['source_task']] if details['source_task']
                      else ['--from-run', details['source_run']])
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
            'route': details['route'], 'features': details['features'], 'next_actions': []}
    def restart(reason):
        argv = python_argv(Path(details['skill_root']) / 'scripts/execution_routes.py', 'read', details['route'],
                           '--root', str(root.absolute()), '--page-bytes', str(details['page_bytes']))
        for feature in details['features']:
            argv.extend(('--feature', feature))
        if details['dialect'] is not None:
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
                   for key in ('route', 'features', 'documents', 'resources')):
                raise ValueError('saved reading record differs from its snapshot')
            route_reading._find_row(record, [ledger])
        result.update(state='recorded', records=present)
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


def inspect(root: Path, task: dict | None = None) -> dict:
    """Describe saved work for this ledger task, without producing inputs, keys or permissions."""
    import work_ledger
    root = Path(root).absolute()
    task = work_ledger.read_current(root) if task is None else task
    result = {'state': 'authoring-state', 'task_id': task['task_id'] if task else None,
              'inputs': [], 'readings': [], 'last_check': None, 'diagnostics': [],
              'next_actions': [], 'external_effect': False}
    if task is None:
        return result
    try:
        records = _records(root, task['task_id'], result['diagnostics'])
    except READ_ERRORS as exc:
        records = []
        result['diagnostics'].append(_problem('work/tasks/' + task['task_id'] + '/authoring', exc))
    for row in records:
        try:
            if row['kind'] in {'draft-inputs', 'build-inputs'}:
                result['inputs'].append(_input(root, row))
            elif row['kind'] == 'route-reading':
                result['readings'].append(_reading(root, row, records))
            elif row['kind'] == 'reading-record' and row['details']['snapshot'] is None:
                import route_reading
                path = Path(row['details']['path'])
                value = c.load(path)
                route_reading.validate_record_content(value)
                route_reading._find_row(value, [Path(row['details']['ledger'])])
                result['readings'].append({'state': 'recorded', 'route': value['route'],
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
            import production_workflow
            _, prepared, _, _ = production_workflow.load_run(root, task['production_run'])
            for row in result['inputs']:
                if (row['state'] == 'built' and row['task'] == prepared['task_path']
                        and row['task_sha256'] == c.content_id(prepared['task'])):
                    row.update(prepared_run=task['production_run'], next_actions=[])
        except READ_ERRORS as exc:
            result['diagnostics'].append(_problem('production/' + task['production_run'], exc))
    candidates = [row for row in result['inputs'] if not row.get('assembled_task')]
    selected_input = max(candidates, key=lambda row: row['created_at'], default=None)
    scope = (selected_input or {}).get('route_scope')
    applicable = [row for row in result['readings']
                  if scope is None or (row['route'] == scope['route'] and row['features'] == scope['features'])]
    selected_reading = max(applicable, key=lambda row: row['created_at'], default=None)
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
    return result


def session_lines(root: Path, task: dict) -> list[str]:
    report = inspect(root, task)
    lines = []
    for row in (item for item in report['inputs'] if item['current']):
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
            lines.extend('Saved reading applications: ' + path for path in row['records'])
        elif row['next_actions']:
            if row['state'] == 'unpublished':
                lines.append('Saved reading attempt: ' + row['snapshot'] + '; ' + row['publication_diagnostic'])
            lines.append('Resume route reading: ' + row['next_actions'][0]['command'])
    if report['last_check']:
        check = report['last_check']
        lines.append('Last check of ' + str(root / check['task']) + ': exit code ' +
                     str(check['exit_code']) + '; logs: ' + check['log_directory'] + '; current inputs not rechecked.')
    for diagnostic in report['diagnostics']:
        lines.append('Saved authoring state needs inspection: ' + diagnostic['file'] + ': ' + diagnostic['message'])
    if lines:
        lines.append('Inspect saved inputs: ' + _action(root, 'inspect-inputs', reason='Read saved authoring state.')['shown'])
    return lines
