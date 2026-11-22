"""Continue a commissioned result through its existing production owners.

A plan retains the selected source and destination. Answers contain only the
judgment currently needed. The runtime binds, records and recovers its effects.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
from production_diagnostics import ProductionError, from_exception

TYPE = 'production-work-plan'
SCOPES = ('save', 'prepared-input', 'delivery-only', 'studio-slot', 'sheet', 'catalog', 'withdraw')
SCRIPT = Path(__file__).with_name('production_workflow.py')


def add_request_arguments(parser) -> None:
    """Select an ordinary single result without a handwritten JSON envelope."""
    from reference_contract import INTENDED_INFLUENCES
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--run', help='Retained Production run to use; this selects no candidate or approval.')
    source.add_argument('--choices', help='Studio-relative editable input choices for the requested result.')
    source.add_argument('--request-file', help='Studio-relative UTF-8 commission for new or revised work.')
    source.add_argument('--batch', help='Studio-relative saved sheet batch to continue through its intended result.')
    parser.add_argument('--scope', choices=SCOPES, help='Commissioned result of this source; required with a source option.')
    parser.add_argument('--candidate', help='Explicit candidate of --run; omit to retain the normal candidate choice.')
    parser.add_argument('--influence', choices=INTENDED_INFLUENCES,
                        help='Intended canonical influence; required for sheet or catalog scope.')
    parser.add_argument('--goal', help='Actual goal when opening a new task for retained work.')
    parser.add_argument('--route', help='Route for --request-file; required unless --from-run supplies it.')
    parser.add_argument('--execution', choices=('authored', 'dispatcher', 'external'),
                        help='Execution kind for --request-file; defaults to authored or the retained source.')
    parser.add_argument('--from-run', help='Retained input to revise under --request-file.')
    parser.add_argument('--operation', choices=('compose', 'amend'),
                        help='Authoring operation for --request-file; otherwise derived from the selected source.')
    from production_cli_arguments import add_change_scope_arguments
    add_change_scope_arguments(parser)
    parser.add_argument('--model', help='Selected model for --request-file; omission preserves a retained target.')
    parser.add_argument('--service', help='Selected service for --request-file; omission preserves a retained target.')
    parser.add_argument('--feature', action='append', default=[],
                        help='Applicable knowledge feature for --request-file; repeat for independent features.')
    parser.add_argument('--registration-file', help='Studio-relative registration record for catalog scope.')
    parser.add_argument('--pack-dir', help='Actual destination pack directory for catalog scope.')
    parser.add_argument('--delivery-path', help='Studio-relative local delivery destination for save scope, when requested.')


def request_from_arguments(root: Path, args) -> dict | None:
    """Derive syntax only; source meaning, use and authority remain authored."""
    source_names = {'run': 'run', 'choices': 'choices', 'request_file': 'request', 'batch': 'batch'}
    source_values = {name: getattr(args, name, None) for name in source_names}
    source_options = {name: value for name, value in source_values.items() if value is not None}
    request_names = ('route', 'execution', 'from_run', 'operation', 'model', 'service')
    from production_cli_arguments import change_scope_from_arguments
    change_scope = change_scope_from_arguments(args)
    result_names = {'influence': 'influence', 'registration_file': 'registration_file',
                    'pack_dir': 'pack_dir', 'delivery_path': 'path'}
    selected_options = source_options or any(getattr(args, name, None) is not None
        for name in (*request_names, *result_names, 'scope', 'candidate', 'goal')) or args.feature or change_scope is not None
    if not selected_options:
        return None
    if args.file is not None:
        raise ValueError('Use --file for a saved plan or multi-item request, or select one source and --scope directly.')
    if len(source_options) != 1 or args.scope is None:
        raise ValueError('Select one of --run, --choices, --request-file or --batch together with --scope.')
    source = {source_names[name]: value for name, value in source_options.items()}
    if 'request' not in source and (any(getattr(args, name, None) is not None for name in request_names)
                                    or args.feature or change_scope is not None):
        raise ValueError('Route, execution, authoring operation, target, features and change scope apply to --request-file.')
    if args.candidate is not None:
        if 'run' not in source:
            raise ValueError('--candidate selects a result of --run.')
        source['candidate'] = args.candidate
    if 'request' in source:
        source.update({name: getattr(args, name) for name in request_names if getattr(args, name) is not None})
        if args.feature:
            source['features'] = list(dict.fromkeys(args.feature))
        if change_scope is not None:
            source['change_scope'] = change_scope
    result = {'scope': args.scope,
              **{field: getattr(args, name) for name, field in result_names.items() if getattr(args, name) is not None}}
    from production_binding import studio_file
    for owner, names in ((source, ('choices', 'request', 'batch')), (result, ('registration_file', 'path'))):
        for name in names:
            if name in owner:
                path = studio_file(root, owner[name], option='--' + name.replace('_', '-'), exists=name != 'path')
                owner[name] = path.resolve().relative_to(root.resolve()).as_posix()
    request = {'source': source, 'result': result}
    if args.goal is not None:
        request['goal'] = args.goal
    _request_shape(request)
    return request


def action(root: Path, path: str, *, command: str = 'advance', reason: str = '') -> dict:
    from cli_invocation import python_argv
    return {'command': command, 'argv': python_argv(SCRIPT, command, '--root', str(root), '--file', path),
            'reason': reason or 'Continue this saved plan from its current evidence and completed answers.'}


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _save(path: Path, value: dict) -> None:
    c.atomic(path, c.encoded(value), replace=path.exists())


def _runtime_selection() -> dict:
    from dataclasses import asdict
    from catalog_retrieval.runtime import selected_pack_settings
    value = asdict(selected_pack_settings())
    for key in ('state_file', 'cache_dir', 'managed_root', 'quarantine_root'):
        value[key] = str(value[key])
    value['roots'] = [str(path) for path in value['roots']]
    return value


def _runtime(value: dict):
    from runtime_paths import PackSettings
    value = copy.deepcopy(value)
    for key in ('state_file', 'cache_dir', 'managed_root', 'quarantine_root'):
        value[key] = Path(value[key])
    value['roots'] = tuple(Path(path) for path in value['roots'])
    for key in ('default_enabled_packs', 'protected_pack_ids'):
        value[key] = tuple(value[key])
    return PackSettings(**value)


def _task(root: Path, task_id: str) -> dict:
    import work_ledger
    return c.load(work_ledger.task_path(root, task_id))


def _load(root: Path, path: str) -> tuple[Path, dict, dict]:
    file = c.local(root, path)
    state = c.load(file)
    if state.get('artifact_type') != TYPE:
        raise ValueError('Select the plan.json returned by plan, or use plan to create the requested work.')
    definition = c.load(file.parent / 'definition.json')
    if c.content_id(definition) != state['definition_sha256']:
        raise ValueError('The saved plan definition changed. Create a new plan for a changed result or source.')
    return file, state, definition


def _current_path(root: Path) -> str | None:
    import work_ledger
    task = work_ledger.read_current(root)
    return task.get('production_plan') if task else None


def _source_task(root: Path, source: dict) -> str | None:
    if 'run' in source:
        import production_operations as operations
        return operations.read_run(root, source['run']).prepared['task']['task_id']
    if 'choices' in source:
        import production_reading_scope
        return production_reading_scope.from_choices(root, source['choices'])[1]['task_id']
    if 'batch' in source:
        import sheet_batch
        state = sheet_batch.load(root, source['batch'])
        for entry in state['panels'].values():
            if entry.get('run'):
                return _source_task(root, {'run': entry['run']})
    return None


def _request_shape(request: dict) -> list[dict]:
    from state_protocol import read_schema, validate_against_schema
    schema_path = Path(__file__).resolve().parents[1] / 'schemas/authoring/production-work-request.schema.json'
    errors = validate_against_schema(request, read_schema(schema_path))
    if errors:
        raise ValueError('Work request: ' + '; '.join(errors))
    if not isinstance(request, dict):
        raise ValueError('A work request is an object containing source and result, or items.')
    allowed = {'source', 'result', 'items', 'goal', 'work_steps'}
    if set(request) - allowed:
        raise ValueError('Unknown work request fields: ' + ', '.join(sorted(set(request) - allowed)))
    if 'items' in request:
        if 'source' in request or 'result' in request:
            raise ValueError('Use source/result for one item or items for several independently selected results.')
        items = copy.deepcopy(request['items'])
    else:
        items = [{'source': copy.deepcopy(request.get('source')), 'result': copy.deepcopy(request.get('result'))}]
    if not isinstance(items, list) or not items:
        raise ValueError('A work request needs at least one result.')
    names = set()
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) - {'name', 'source', 'result', 'after'}:
            raise ValueError('Each item contains source, result and optional name/after dependencies.')
        item.setdefault('name', 'item-' + str(number))
        item.setdefault('after', [])
        name = c.text(item['name'], 'item name')
        if name in names or not all(char.isalnum() or char in '-_' for char in name):
            raise ValueError('Item names must be unique letters, numbers, hyphens or underscores.')
        names.add(name)
        source, result = item.get('source'), item.get('result')
        if not isinstance(source, dict) or not isinstance(result, dict):
            raise ValueError('Choose the source and result for ' + name + '.')
        if result.get('scope') not in SCOPES:
            raise ValueError('Choose a result scope: ' + ', '.join(SCOPES) + '.')
        modes = [key for key in ('choices', 'run', 'batch', 'request') if key in source]
        if source.get('kind') in {'imported', 'sheet'}:
            if modes:
                raise ValueError('An imported source names its existing owner, not a production input.')
        elif len(modes) != 1:
            raise ValueError('Choose one source: choices, run, batch, request or an imported/sheet owner.')
        if 'change_scope' in source:
            from production_reading_scope import validate_change_scope
            validate_change_scope(source['change_scope'])
            if ('request' not in source or not source.get('from_run')
                    or source.get('operation', 'amend') != 'amend'):
                raise ValueError('A change scope belongs to a request amending from_run. '
                                 'Edit work-basis.json for an existing choices source.')
        if not isinstance(item['after'], list) or any(not isinstance(value, str) for value in item['after']):
            raise ValueError('Dependencies are item names in after.')
    done = set()
    while len(done) < len(items):
        ready = [item['name'] for item in items if item['name'] not in done and set(item['after']).issubset(done)]
        if not ready:
            raise ValueError('Plan dependencies contain a cycle or an unknown item name.')
        done.update(ready)
    return items


def _request_template(root: Path) -> dict:
    import work_ledger
    task = work_ledger.read_current(root)
    source = {'request': 'request.txt', 'route': 'prompt-only', 'execution': 'authored'}
    if task and task.get('production_run'):
        source = {'run': task['production_run']}
    request = {'source': source, 'result': {'scope': None}}
    path = c.local(root, 'work/plan-request.json', exists=False)
    if not path.exists():
        _save(path, request)
    return {'ok': True, 'state': 'choose-result', 'request_file': _relative(root, path),
            'scopes': list(SCOPES),
            'schema': 'schemas/authoring/production-work-request.schema.json',
            'required_action': 'Select the actual source and commissioned result in this small request. '
                'Use choices for editable work, run for retained output, request for new work, batch for a sheet batch, '
                'or an imported/sheet owner for existing artwork.',
            'next_action': action(root, _relative(root, path), command='plan', reason='Create this selected work plan.')}


def _result_applicability(root: Path, items: list[dict]) -> None:
    """Check selected owner/result combinations before opening any work."""
    for item in items:
        source, result = item['source'], item['result']
        scope = result['scope']
        if source.get('kind') in {'imported', 'sheet'}:
            if scope in {'save', 'prepared-input'}:
                raise ValueError('Retained artwork uses delivery-only, studio-slot, sheet, catalog or withdraw.')
            if source['kind'] == 'sheet' and scope not in {'sheet', 'withdraw'}:
                raise ValueError('A local sheet artifact uses sheet adoption or withdrawal.')
            continue
        if 'batch' in source:
            if scope == 'save':
                raise ValueError('Choose the intended image result for this batch.')
            continue
        if 'run' in source or 'from_run' in source:
            import production_operations as operations
            task = operations.read_run(root, source.get('run', source.get('from_run'))).prepared['task']
        elif 'choices' in source:
            import production_reading_scope
            task = production_reading_scope.from_choices(root, source['choices'])[1]
        else:
            task = {'execution': source.get('execution', 'authored')}
        execution = source.get('execution', task['execution'])
        if execution == 'authored' and scope not in {'save', 'prepared-input'}:
            raise ValueError('Authored work uses save, including its declared delivery/review obligations, or prepared-input.')
        if execution != 'authored' and scope == 'save':
            raise ValueError('Image execution uses delivery-only, studio-slot, sheet, catalog or prepared-input.')
        if result.get('path') and scope != 'save':
            raise ValueError('A local authored delivery path belongs to result scope save.')


def create(root: Path, request_file: str | None = None, *, request: dict | None = None) -> dict:
    import work_ledger
    from pack_manager import generate_uuid7
    root = c._root(root)
    if request_file is not None and request is not None:
        raise ValueError('Select a request file or a directly constructed request.')
    if request_file is None and request is None:
        current = _current_path(root)
        return refresh(root, current) if current else _request_template(root)
    request = c.load(c.local(root, request_file)) if request is None else copy.deepcopy(request)
    if request.get('artifact_type') == TYPE:
        return refresh(root, request_file)
    items = _request_shape(request)
    import production_curation
    for item in items:
        if item['source'].get('kind') == 'sheet':
            source = production_curation.resolve_source(root, item['source'])
            item['source'] = ({key: value for key, value in source.items() if key != 'kind'}
                              if source.get('kind') == 'production' else source)
    _result_applicability(root, items)
    task_ids = {value for item in items if (value := _source_task(root, item['source'])) is not None}
    active = work_ledger.read_current(root)
    if len(task_ids) > 1:
        raise ValueError('One plan belongs to one work task. Use separate plans for independently owned tasks.')
    task_id = next(iter(task_ids), active['task_id'] if active else None)
    owns_steps = False
    if task_id is None:
        goal = request.get('goal')
        if not goal:
            sources = [item['source'] for item in items if 'request' in item['source']]
            goal = c.read(c.local(root, sources[0]['request'])).decode('utf-8').strip() if sources else None
        if not goal:
            raise ValueError('New work needs its actual request or a goal describing the intended result.')
        work = work_ledger.begin(root, goal, ['Prepare the selected work.', 'Complete its commissioned results.',
                                             'Verify the saved results and Studio views.'])
        task_id, owns_steps = work['task_id'], True
    else:
        work = _task(root, task_id)
        if work.get('work_state') not in {'active', 'suspended'}:
            # Later curation belongs to its own work, while the originating run
            # retains the task and completion it actually established.
            goal = request.get('goal')
            if not goal:
                raise ValueError('Later use of completed work needs the new goal in this request.')
            if active is not None and active['task_id'] != task_id:
                work = active
                task_id = work['task_id']
            else:
                work = work_ledger.begin(root, goal, ['Prepare the selected work.', 'Complete its commissioned results.',
                                                     'Verify the saved results and Studio views.'])
                task_id, owns_steps = work['task_id'], True
    if work.get('production_plan'):
        previous = c.load(c.local(root, work['production_plan']))
        if previous.get('status') != 'complete':
            if previous.get('request_sha256') == c.content_id(request):
                return inspect(root, work['production_plan'])
            raise ValueError('This work already has a plan. Continue it, or open separate work for a new branch.')
    identifier = generate_uuid7()
    directory = c.local(root, 'work/plans/' + identifier, exists=False)
    directory.mkdir(parents=True)
    _save(directory / 'request.json', request)
    definition = {'task_id': task_id, 'items': items,
                  'work_steps': ({'1': 'prepared', '2': 'results', '3': 'verified'} if owns_steps
                                 else copy.deepcopy(request.get('work_steps', {})))}
    _save(directory / 'definition.json', definition)
    state = {'artifact_type': TYPE, 'plan_id': identifier, 'task_id': task_id,
             'definition_sha256': c.content_id(definition), 'request_sha256': c.content_id(request),
             'status': 'active', 'items': {}, 'created_at': c.now(), 'verification': None,
             'runtime': _runtime_selection()}
    for item in items:
        source = item['source']
        state['items'][item['name']] = {'source': copy.deepcopy(source), 'run': source.get('run'),
            'candidate': source.get('candidate'), 'phase': 'source', 'status': 'pending',
            'answers': {}, 'evidence': {}}
    path = directory / 'plan.json'
    _save(path, state)
    work_ledger.bind_plan(root, task_id, _relative(root, path), definition['work_steps'])
    return inspect(root, _relative(root, path))


def _answer(root: Path, directory: Path, entry: dict, key: str, draft: dict) -> tuple[dict | None, dict]:
    record = entry['answers'].get(key)
    if record is None:
        path = directory / (key + '.json')
        _save(path, draft['choices'])
        record = {'file': _relative(root, path), 'initial_sha256': c.content_id(draft['choices']),
                  'binding': copy.deepcopy(draft.get('binding')), 'context': {
                      name: copy.deepcopy(value) for name, value in draft.items() if name not in {'choices', 'binding'}}}
        entry['answers'][key] = record
        return None, record
    value = c.load(c.local(root, record['file']))
    if c.content_id(value) == record['initial_sha256']:
        return None, record
    return value, record


def _waiting(entry: dict, phase: str, record: dict, *, reason: str) -> None:
    entry.update(phase=phase, status='needs-input', current={'answer_file': record['file'],
                 'reason': reason, **copy.deepcopy(record['context'])})


def _input(root: Path, directory: Path, entry: dict, spec: dict, *, advance: bool) -> bool:
    import production_inputs
    import production_operations as operations
    from production_input_adapters import using_runtime
    from production_authoring_state import registered_runtime_arguments
    source = entry['source']
    if 'choices' not in source:
        return True
    runtime = registered_runtime_arguments(root, source['choices'])
    with using_runtime(runtime):
        view = production_inputs.authoring_view(root, source['choices'], runtime_arguments=runtime)
        stage = view['authoring_stage']
        if stage['stage'] != 'prepare':
            if advance and entry.get('phase') == 'authoring' and stage['structural_ready']:
                following = stage['next_stage']
                production_inputs.stage_inputs(root, source['choices'], following, runtime_arguments=runtime)
                view = production_inputs.authoring_view(root, source['choices'], runtime_arguments=runtime)
                stage = view['authoring_stage']
            entry.update(phase='authoring', status='needs-input', current={
                'choices': source['choices'], 'stage': stage['stage'], 'purpose': stage['purpose'],
                'change_scope': view['authoring_scope'].get('change_scope'),
                'remaining_stages': stage['remaining_stages'],
                'unresolved': stage['unresolved'],
                'inspection': production_inputs.inspect_inputs(root, choices_path=source['choices']),
                'reason': 'Read the current stage and complete its authored files, then advance to the next stage.'})
            return False
        if not advance or not stage['structural_ready']:
            entry.update(phase='authoring', status='needs-input', current={
                'choices': source['choices'], 'stage': stage['stage'], 'unresolved': stage['unresolved'],
                'change_scope': view['authoring_scope'].get('change_scope'),
                'remaining_stages': stage['remaining_stages'],
                'inspection': production_inputs.inspect_inputs(root, choices_path=source['choices']),
                'reason': 'Complete the current preparation reading and inputs, then advance to publish this revision.'})
            return False
        from pack_manager import generate_uuid7
        entry.setdefault('reserved_run', generate_uuid7())
        # The caller saves the reserved identity before publication.
        entry['publication_ready'] = True
    return True


def _new_source(root: Path, directory: Path, entry: dict, spec: dict, task_id: str) -> None:
    import production_inputs
    source = entry['source']
    if 'request' not in source:
        return
    allowed = {'request', 'route', 'execution', 'model', 'service', 'features', 'operation',
               'from_run', 'artifact', 'source_image', 'scale', 'purpose', 'focus', 'change_scope'}
    if set(source) - allowed:
        raise ValueError('Unknown new-work source fields: ' + ', '.join(sorted(set(source) - allowed)))
    out = directory / 'inputs'
    if (out / 'choices.json').exists():
        entry['source'] = {'choices': _relative(root, out / 'choices.json')}
        return
    previous = None
    if source.get('from_run'):
        import production_operations as operations
        previous = operations.read_run(root, source['from_run']).prepared['task']
    execution = source.get('execution', previous['execution'] if previous else 'authored')
    result = production_inputs.draft_inputs(root, None, _relative(root, out),
        from_run=source.get('from_run'), task_id=task_id,
        operation=source.get('operation', 'amend' if source.get('from_run') else 'compose'),
        request_file=source['request'], route=source.get('route'), execution=execution,
        artifact=source.get('artifact', previous['artifact'] if previous else
                            'text' if execution == 'authored' else 'image'),
        model=source.get('model'), service=source.get('service'), features=source.get('features'),
        source_image=Path(source['source_image']) if source.get('source_image') else None,
        scale=source.get('scale'), purpose=source.get('purpose'), focus=source.get('focus'),
        change_scope=source.get('change_scope'))
    entry['source'] = {'choices': _relative(root, out / 'choices.json')}


def _publish(root: Path, entry: dict) -> None:
    import production_operations as operations
    from production_authoring_state import registered_runtime_arguments
    from production_input_adapters import using_runtime
    run = entry['reserved_run']
    directory = operations.run_dir(root, run, exists=False)
    if directory.exists():
        try:
            loaded = operations.read_run(root, run)
        except ValueError:
            from production_compiler import recover_publication
            recover_publication(root, run)
            loaded = operations.read_run(root, run)
        entry['run'] = loaded.prepared['run']
    else:
        runtime = registered_runtime_arguments(root, entry['source']['choices'])
        with using_runtime(runtime):
            operations.prepare(root, choices=entry['source']['choices'], identity=run)
        entry['run'] = run
    entry.pop('publication_ready', None)
    entry['evidence']['prepared'] = {'run': run}


def _review(root: Path, directory: Path, entry: dict, run: str, candidate: str | None) -> bool:
    import production_operations as operations
    import production_work_review
    loaded = operations.read_run(root, run)
    reviews = [row for row in loaded.rows if (row['event'] == 'authored-review' if candidate is None
               else row['event'] == 'review' and row['data']['candidate'] == candidate)]
    def ready(current):
        if candidate is None:
            import production_authored
            return 'review' not in production_authored.pending(current.prepared, current.rows)
        return not operations.candidate_state(root, run, candidate)['unassessed_criteria']

    if reviews and ready(loaded):
        return True
    key = 'review-' + (candidate[:16] if candidate else 'text')
    observation_key = 'observe-' + (candidate[:16] if candidate else 'text')
    first = entry['evidence'].get(observation_key)
    if first is None:
        observation = production_work_review.observe(root, run, candidate)
        answers, record = _answer(root, directory, entry, observation_key, observation)
        if answers is None:
            _waiting(entry, 'observe', record, reason='Inspect the artifact before receiving its assessment basis.')
            return False
        first = production_work_review.observed(answers)
        first_file = directory / ('observed-' + c.content_id(first) + '.json')
        if not first_file.exists():
            c.atomic(first_file, c.encoded(first))
        entry['evidence'][observation_key] = {'file': _relative(root, first_file), 'sha256': c.sha256_file(first_file)}
    else:
        first_file = c.local(root, first['file'])
        if c.sha256_file(first_file) != first['sha256']:
            raise ValueError('The retained first observation changed; preserve its original evidence.')
        first = c.load(first_file)
    draft = production_work_review.draft(root, run, candidate)
    draft['choices'].update(copy.deepcopy(first))
    for check in draft['choices']['checks'].values():
        check['supports'] = [first['observations'][0]['id']]
    draft['first_observation'] = copy.deepcopy(entry['evidence'][observation_key])
    answers, record = _answer(root, directory, entry, key, draft)
    if answers is None:
        _waiting(entry, 'review', record, reason='Observe this exact artifact and complete its criterion judgments.')
        return False
    if record.get('applied_sha256') == c.content_id(answers):
        _waiting(entry, 'review', record, reason='Complete the remaining criterion judgments in the same review answer.')
        return False
    receipt = production_work_review.apply(root, directory, answers, binding=record['binding'])
    entry['evidence'][key] = receipt
    record['applied_sha256'] = c.content_id(answers)
    if ready(operations.read_run(root, run)):
        return True
    _waiting(entry, 'review', record, reason='Complete the remaining criterion judgments in the same review answer.')
    return False


def _run(root: Path, directory: Path, entry: dict, spec: dict) -> bool:
    import production_operations as operations
    import production_execution as execution
    loaded = operations.read_run(root, entry['run'])
    run, prepared, rows = entry['run'], loaded.prepared, loaded.rows
    events = {row['event'] for row in rows}
    scope = spec['result']['scope']
    entry['evidence'].setdefault('prepared', {'run': run})
    if scope == 'prepared-input':
        entry.update(phase='complete', status='complete', current=None)
        return True
    if prepared['task']['execution'] == 'authored':
        import production_authored
        if 'authored-save' not in events:
            production_authored.record_save(root, run)
            loaded = operations.read_run(root, run)
            rows = loaded.rows
        pending = production_authored.pending(prepared, rows)
        if 'delivery' in pending:
            destination = spec['result'].get('path')
            if destination:
                operations.deliver(root, run, destination=destination)
            else:
                draft = {'choices': {'receipt_file': None},
                    'instructions': 'Provide the saved receipt of the actual external presentation or attachment.'}
                answers, record = _answer(root, directory, entry, 'delivery', draft)
                if answers is None:
                    _waiting(entry, 'delivery', record, reason='Record the actual delivery required by this saved artifact.')
                    return False
                operations.deliver(root, run, answers['receipt_file'])
        if 'review' in pending and not _review(root, directory, entry, run, None):
            return False
        receipt = operations.complete(root, run)
        entry['evidence']['result'] = {'run': run, 'completion': receipt}
        entry.update(phase='complete', status='complete', current=None)
        return True

    candidates = [row for row in rows if row['event'] == 'candidate']
    started = bool(events.intersection({'dispatch-claim', 'external-claim'}))
    report = execution.status(root, run)
    status = next(item for item in report['runs'] if item['run'] == run)
    if not candidates or status.get('settlement_open'):
        if started:
            if prepared['task']['execution'] == 'external':
                draft = {'choices': {'response': None, 'artifacts': [], 'reason': '', 'final': True},
                    'instructions': 'Recover the already claimed host call and select its actual saved response and media. '
                        'The request was handed off once; this form records its result.'}
                answers, record = _answer(root, directory, entry, 'external-result', draft)
                if answers is None:
                    _waiting(entry, 'external-result', record, reason='Receive the result of the existing host call.')
                    if entry.get('host_request'):
                        entry['current']['host_request'] = entry['host_request']
                    return False
                receipt_identity = c.content_id({'answer': answers,
                    'response': c.sha256_file(c.local(root, answers['response'])),
                    'artifacts': [c.sha256_file(c.local(root, path)) for path in answers['artifacts']]})
                if record.get('received_sha256') != receipt_identity:
                    operations.receive_external(root, run, response_file=answers['response'], artifacts=answers['artifacts'],
                                                final=answers['final'], reason=answers['reason'])
                    record['received_sha256'] = receipt_identity
            else:
                result = execution.resume(root, run)
                refreshed = operations.read_run(root, run)
                if not any(row['event'] == 'candidate' for row in refreshed.rows):
                    entry.update(phase='recovery', status='pending', current={
                        'reason': 'Continue recovery of the existing provider task.',
                        'run': run, 'status': result})
                    return False
        else:
            import production_work_execution
            draft = production_work_execution.draft(root, run)
            answers, record = _answer(root, directory, entry, 'execution', draft)
            if answers is None:
                _waiting(entry, 'execution', record, reason='Judge the exact saved request and its actual authorization once.')
                from production_workspace import workspace
                entry['current']['workspace'] = workspace(root, run, phase='decision')
                return False
            records = (c.local(root, record['records_directory'], exists=False)
                       if record.get('records_directory') else directory / 'execution-records')
            result = production_work_execution.apply(root, records, answers, binding=record['binding'])
            if result.get('host_request'):
                entry['host_request'] = result['host_request']
            entry['evidence']['execution'] = {'run': run}
        loaded = operations.read_run(root, run)
        candidates = [row for row in loaded.rows if row['event'] == 'candidate']
        refreshed_status = next(item for item in execution.status(root, run)['runs'] if item['run'] == run)
        if not candidates or refreshed_status.get('settlement_open'):
            external_record = entry['answers'].get('external-result')
            entry.update(phase='recovery', status='pending', current={
                'reason': 'The existing execution is awaiting its actual result.',
                'status': {'ok': True, 'runs': [refreshed_status]},
                **({'answer_file': external_record['file'], **copy.deepcopy(external_record['context'])}
                   if external_record else {}),
                **({'host_request': entry['host_request']} if entry.get('host_request') else {})})
            return False

    # The author chooses among actual alternatives; ordering is never selection.
    reviewed_candidates = candidates
    if entry.get('candidate') is not None:
        reviewed_candidates = [row for row in candidates if row['sha256'] == entry['candidate']]
        if not reviewed_candidates:
            raise ValueError('The selected candidate must belong to this exact retained run.')
    for candidate in reviewed_candidates:
        if not _review(root, directory, entry, run, candidate['sha256']):
            return False
    if entry.get('candidate') is None:
        if len(candidates) == 1:
            entry['candidate'] = candidates[0]['sha256']
        else:
            draft = {'choices': {'candidate': None}, 'candidates': [
                {'number': index, 'candidate': row['sha256'],
                 'evaluation': operations.candidate_state(root, run, row['sha256'])}
                for index, row in enumerate(candidates, 1)],
                'instructions': 'Choose one reviewed result by its displayed number.'}
            answers, record = _answer(root, directory, entry, 'candidate', draft)
            if answers is None:
                _waiting(entry, 'selection', record, reason='Choose the result that satisfies this commissioned use.')
                return False
            number = answers['candidate']
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(candidates):
                raise ValueError('Select one displayed candidate number.')
            entry['candidate'] = candidates[number - 1]['sha256']
    source = {'kind': 'production', 'run': run, 'candidate': entry['candidate']}
    return _curate(root, directory, entry, source, spec['result'])


def _curate(root: Path, directory: Path, entry: dict, source: dict, destination: dict) -> bool:
    import production_curation
    record = entry['answers'].get('curation')
    draft = (production_curation.draft(root, source, destination) if record is None else
             {'choices': {}, 'binding': record['binding'], **record['context']})
    answers, record = _answer(root, directory, entry, 'curation', draft)
    if answers is None:
        _waiting(entry, 'curation', record, reason='Record the actual choice and approval for this destination once.')
        return False
    from catalog_retrieval.runtime import selected_pack_settings
    receipt = production_curation.apply(root, directory / 'curation-records', answers,
        binding=record['binding'], settings=selected_pack_settings() if destination['scope'] == 'catalog' else None)
    entry['evidence']['result'] = receipt
    entry.update(phase='complete', status='complete', current=None)
    return True


def _batch(root: Path, directory: Path, entry: dict, spec: dict) -> bool:
    import sheet_batch
    state_path = entry['source']['batch']
    report = sheet_batch.advance(root, state_path, unreceived_only=True)
    batch = sheet_batch.load(root, state_path)
    entry.setdefault('panels', {})
    entry['expected_panels'] = list(batch['panels'])
    progressed = False
    waiting = []
    for name, panel in batch['panels'].items():
        if not panel.get('run'):
            continue
        import production_operations as operations
        if not operations.run_dir(root, panel['run'], exists=False).exists():
            # The batch has reserved this identity but its own preparation is
            # unfinished. Preserve that owner's diagnostic and other panels.
            continue
        child = entry['panels'].setdefault(name, {'source': {'run': panel['run']}, 'run': panel['run'],
            'candidate': None, 'phase': 'source', 'status': 'pending', 'answers': {}, 'evidence': {}})
        if child['status'] == 'complete':
            continue
        target = directory / name
        target.mkdir(parents=True, exist_ok=True)
        try:
            if _run(root, target, child, spec):
                progressed = True
                child.pop('diagnostic', None)
                continue
        except (ValueError, OSError, KeyError, TypeError) as exc:
            child['status'] = 'blocked'
            child['diagnostic'] = from_exception(exc, phase='work-plan-panel',
                required_action='Correct this panel through its saved answer or source; other panels remain independent.')
            child.setdefault('current', {})
            if child['current'] is None:
                child['current'] = {}
            child['current']['diagnostic'] = child['diagnostic']
        if child['status'] != 'complete':
            waiting.append((name, child))
    if progressed:
        report = sheet_batch.advance(root, state_path, unreceived_only=True)
        batch = sheet_batch.load(root, state_path)
    if len(entry['panels']) == len(batch['panels']) and all(
            value['status'] == 'complete' for value in entry['panels'].values()):
        entry['evidence']['result'] = {'batch': state_path,
            'panels': {name: value['evidence'] for name, value in entry['panels'].items()}}
        entry.update(phase='complete', status='complete', current=None)
        return True
    if waiting:
        name, child = waiting[0]
        entry.update(phase='batch', status=child['status'], current={'panel': name, **(child.get('current') or {}),
            'other_panels': [{'panel': other, 'phase': value['phase'], 'state': value['status'],
                **{key: value['current'][key] for key in ('answer_file', 'reason') if key in (value.get('current') or {})}}
                for other, value in waiting[1:]]})
        return False
    entry.update(phase='batch', status='pending', current={'batch': state_path, 'report': report,
        'reason': 'The batch continues with reviewed adoption and the resulting reference dependencies.'})
    return False


def _finish(root: Path, state: dict, definition: dict) -> None:
    import work_ledger
    import validate_studio
    all_prepared = all(entry.get('run') or entry['source'].get('kind') in {'imported', 'sheet'}
        or (entry.get('expected_panels') and set(entry.get('panels', {})) == set(entry['expected_panels'])
            and all(child.get('run') for child in entry['panels'].values())) for entry in state['items'].values())
    if all_prepared:
        work_ledger.record_plan_stage(root, state['task_id'], 'prepared', state['plan_id'],
            {name: value['evidence'].get('prepared', {'source': value['source']})
             for name, value in state['items'].items()})
    if not all(entry['status'] == 'complete' for entry in state['items'].values()):
        return
    for spec in definition['items']:
        _verify_entry(root, state['items'][spec['name']], spec)
    work_ledger.record_plan_stage(root, state['task_id'], 'results', state['plan_id'],
        {name: value['evidence'] for name, value in state['items'].items()})
    import studio_activity
    projection = studio_activity.refresh(root)
    errors = validate_studio.validate(root)
    if errors:
        state['verification'] = {'ok': False, 'errors': errors, 'projection': projection}
        state['status'] = 'verification-required'
        return
    state['verification'] = {'ok': True}
    work_ledger.record_plan_stage(root, state['task_id'], 'verified', state['plan_id'], state['verification'])
    work = _task(root, state['task_id'])
    remaining = [step for step in work['steps'] if not step.get('done_at')]
    if remaining:
        directory = c.local(root, work['production_plan']).parent
        state.setdefault('answers', {})
        draft = {'choices': {'steps': {str(row['n']): None for row in remaining}},
            'steps': [{'number': row['n'], 'text': row['text']} for row in remaining],
            'milestones': {'prepared': 'The selected complete inputs are retained.',
                'results': 'Every commissioned result has its independently verified formal record.',
                'verified': 'Those results and the Studio views passed validation.'},
            'instructions': 'Match a step to a milestone only when that result fulfills the step. '
                'Leave independent work null and complete that work through its own owner.'}
        answers, record = _answer(root, directory, state, 'work-steps', draft)
        if answers is not None:
            c.exact(answers, {'steps'}, 'work step answers')
            chosen = {number: stage for number, stage in answers['steps'].items() if stage is not None}
            existing = {**work.get('plan_steps', {}), **chosen}
            work_ledger.bind_plan(root, state['task_id'], work['production_plan'], existing)
            proofs = {'prepared': {name: value['evidence'].get('prepared', {'source': value['source']})
                                  for name, value in state['items'].items()},
                      'results': {name: value['evidence'] for name, value in state['items'].items()},
                      'verified': state['verification']}
            for stage in set(chosen.values()):
                work_ledger.record_plan_stage(root, state['task_id'], stage, state['plan_id'], proofs[stage])
            work = _task(root, state['task_id'])
            remaining = [step for step in work['steps'] if not step.get('done_at')]
        state['work_input'] = {'answer_file': record['file'], **record['context']}
    if remaining or work.get('blocked_on') or any(q['state'] == 'open' for q in work.get('questions', [])):
        state['status'] = 'work-required'
        state['remaining_work'] = {'steps': remaining, 'questions': [q for q in work.get('questions', []) if q['state'] == 'open'],
                                   'blocked_on': work.get('blocked_on')}
        return
    work_ledger.finish_plan(root, state['task_id'], state['plan_id'],
        {name: value['evidence'] for name, value in state['items'].items()}, state['verification'])
    state['status'] = 'complete'
    state.pop('remaining_work', None)
    state.pop('work_input', None)


def _verify_entry(root: Path, entry: dict, spec: dict) -> None:
    """Check formal result owners before counting a saved plan flag as progress."""
    if 'panels' in entry:
        import sheet_batch
        panels = sheet_batch.load(root, entry['source']['batch'])['panels']
        if set(panels) != set(entry['panels']) or any(
                panel.get('run') != entry['panels'][name].get('run') for name, panel in panels.items()):
            raise ValueError('Verify every actual batch panel and its retained run before completing the work.')
        for child in entry['panels'].values():
            _verify_entry(root, child, spec)
        return
    record = entry.get('answers', {}).get('curation')
    if record is not None:
        import production_curation
        directory = c.local(root, record['file']).parent / 'curation-records'
        result = production_curation.verify(root, directory, binding=record['binding'])
        entry['current_use'] = result['current_use']
        return
    if entry.get('run'):
        import production_operations as operations
        loaded = operations.read_run(root, entry['run'])
        if spec['result']['scope'] == 'prepared-input':
            import work_ledger
            work_ledger._prepared_input_evidence(loaded)
        else:
            operations.verify_completion(root, entry['run'], loaded.prepared['task']['task_id'])
        return
    raise ValueError('Completed work lacks a formal result to verify.')


def _project(root: Path, path: str, state: dict, definition: dict) -> dict:
    from production_report_view import present, diagnostic

    def diagnostic_view(value: dict, pointer: str) -> dict:
        import sys
        shown = diagnostic(value)
        owner = path + '#' + pointer

        def locate(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key == 'full_report' and isinstance(child, str) and (
                            child == 'full_report' or child.startswith('full_report#')):
                        item[key] = owner + child[len('full_report'):].removeprefix('#')
                    else:
                        locate(child)
            elif isinstance(item, list):
                for child in item:
                    locate(child)

        locate(shown)
        shown['full_report'] = owner
        shown['full_report_action'] = {'command': 'read-report',
            'argv': [sys.executable, '-m', 'json.tool', str(root / path)],
            'reason': 'Read the retained plan and the exact diagnostic at its displayed JSON pointer.'}
        return shown

    def current_view(entry: dict, number: int, name: str) -> dict:
        current = copy.deepcopy(entry['current'])
        # Owners retain the complete reports, while a resumed plan exposes the
        # current judgment through the same projection as their public command.
        # Rebase local action pointers because each report is embedded here.
        for key, command in (('inspection', 'inspect-inputs'), ('workspace', 'workspace'),
                             ('status', 'status'), ('compilation', 'check'), ('report', 'sheet-batch')):
            report = current.get(key)
            if not isinstance(report, dict):
                continue
            if key == 'report' and not isinstance(report.get('panels'), dict):
                continue
            compact = present(root, report, command=command,
                run=report.get('run') or entry.get('run'),
                choices=(current.get('choices') or entry.get('source', {}).get('choices'))
                        if command in {'inspect-inputs', 'check'} else None)
            prefix = '#/items/' + str(number) + '/current/' + key

            def rebase(value):
                if isinstance(value, dict):
                    for name, child in value.items():
                        if name == 'action_ref' and isinstance(child, str) and child.startswith('#/'):
                            value[name] = prefix + child[1:]
                        else:
                            rebase(child)
                elif isinstance(value, list):
                    for child in value:
                        rebase(child)

            rebase(compact)
            current[key] = compact
            if (key == 'workspace' and 'requirements' in current
                    and current['requirements'] == report.get('authorization_requirements')):
                current['requirements'] = {
                    'owner': prefix + '/authorization_requirements',
                    'full_report': (compact['full_report'] + '#/authorization_requirements'
                                    if compact.get('full_report') else prefix + '/complete_report/authorization_requirements'),
                    'meaning': 'The current authorization requirements appear once in the workspace.'}
            if key == 'workspace' and 'criteria' in current:
                criteria_pointer = '/basis/criteria' if 'basis' in compact else '/criteria'
                if current['criteria'] == (compact.get('basis') or compact).get('criteria'):
                    current['criteria'] = {'owner': prefix + criteria_pointer,
                        'meaning': 'Every current criterion appears once in this review workspace.'}
            if (key == 'inspection' and 'unresolved' in current
                    and current['unresolved'] == (report.get('authoring_stage') or {}).get('unresolved')):
                current['unresolved_summary'] = {'total': len(current.pop('unresolved')),
                    'owner': prefix + '/authoring_stage',
                    'meaning': 'Current unresolved findings appear in the inspection diagnostic index.'}
        if isinstance(current.get('diagnostic'), dict):
            current['diagnostic'] = diagnostic_view(current['diagnostic'],
                '/items/' + name.replace('~', '~0').replace('/', '~1') + '/current/diagnostic')
        return current

    result = {'ok': state['status'] not in {'blocked', 'verification-required'}, 'plan': path,
        'task_id': state['task_id'], 'state': state['status'], 'items': [],
        'next_action': None if state['status'] == 'complete' else action(root, path),
        'verification': copy.deepcopy(state.get('verification'))}
    for number, spec in enumerate(definition['items']):
        entry = state['items'][spec['name']]
        shown = {'name': spec['name'], 'result': spec['result'], 'phase': entry['phase'],
                 'state': entry['status'], 'run': entry.get('run')}
        if entry.get('current_use'):
            shown['current_use'] = entry['current_use']
        if entry.get('current'):
            shown['current'] = current_view(entry, number, spec['name'])
        if entry.get('diagnostic'):
            shown['diagnostic'] = diagnostic_view(entry['diagnostic'],
                '/items/' + spec['name'].replace('~', '~0').replace('/', '~1') + '/diagnostic')
        result['items'].append(shown)
    if state.get('remaining_work'):
        result['remaining_work'] = copy.deepcopy(state['remaining_work'])
        result['required_action'] = ('Finish the listed independent work. Bind a step to prepared, results or verified '
            'only when that recorded result actually fulfills its meaning.')
        if state.get('work_input'):
            result['current'] = copy.deepcopy(state['work_input'])
    return result


def inspect(root: Path, path: str | None = None) -> dict:
    path = path or _current_path(root)
    if path is None:
        return _request_template(root)
    _, state, definition = _load(root, path)
    for spec in definition['items']:
        entry = state['items'][spec['name']]
        if entry['status'] == 'complete':
            _verify_entry(root, entry, spec)
    return _project(root, path, state, definition)


def _renew_answer(root: Path, directory: Path, entry: dict, key: str, draft: dict) -> None:
    previous = entry['answers'][key]
    history = entry.setdefault('answer_history', {}).setdefault(key, [])
    history.append(copy.deepcopy(previous))
    filename = directory / (key + '-revision-' + str(len(history) + 1) + '.json')
    choices = copy.deepcopy(draft['choices'])
    if 'reason' in choices:
        choices['reason'] = ''
    _save(filename, choices)
    record = {'file': _relative(root, filename), 'initial_sha256': c.content_id(choices),
        'binding': copy.deepcopy(draft.get('binding')), 'context': {
            name: copy.deepcopy(value) for name, value in draft.items() if name not in {'choices', 'binding'}}}
    record['context']['previous_answer'] = previous['file']
    if key == 'execution':
        record['records_directory'] = _relative(root,
            directory / 'execution-records' / 'revisions' / c.content_id(record['binding']))
    entry['answers'][key] = record
    _waiting(entry, key, record,
             reason='Assess the current displayed conditions. The previous answer and committed records are retained.')
    entry.pop('diagnostic', None)


def _refresh_entry(root: Path, directory: Path, entry: dict, spec: dict) -> None:
    if entry['status'] == 'complete':
        return
    if 'panels' in entry:
        for name, child in entry['panels'].items():
            _refresh_entry(root, directory / name, child, spec)
        waiting = [(name, child) for name, child in entry['panels'].items() if child.get('current')]
        if waiting:
            name, child = waiting[0]
            entry.update(phase='batch', status=child['status'], current={'panel': name, **child['current']})
        return
    record = entry['answers'].get('curation')
    if record is not None:
        import production_curation as curation
        records = directory / 'curation-records'
        progress = curation._directory(records, record['binding']) / 'progress.json'
        if progress.exists():
            if entry['status'] != 'blocked':
                return
            draft = curation.reassess(root, records, binding=record['binding'])
        else:
            draft = curation.draft(root, record['binding']['source'], spec['result'])
            if draft['binding'] == record['binding']:
                return
        _renew_answer(root, directory, entry, 'curation', draft)
        return
    record = entry['answers'].get('execution')
    if record is not None:
        import production_operations as operations
        import production_work_execution
        loaded = operations.read_run(root, entry['run'])
        if any(row['event'] in {'dispatch-claim', 'external-claim'} for row in loaded.rows):
            return
        draft = production_work_execution.draft(root, entry['run'])
        before, after = copy.deepcopy(record['binding']), copy.deepcopy(draft['binding'])
        # An unrelated authority event does not invalidate unchanged terms.
        before.pop('authority', None)
        after.pop('authority', None)
        if before != after:
            _renew_answer(root, directory, entry, 'execution', draft)


def refresh(root: Path, path: str) -> dict:
    """Refresh current answer bindings without sending or replaying completed effects."""
    file, initial, _ = _load(root, path)
    if _task(root, initial['task_id']).get('production_plan') != path:
        return inspect(root, path)
    from catalog_retrieval.runtime import using_pack_runtime
    with using_pack_runtime(_runtime(initial['runtime'])), c.file_lock(file):
        file, state, definition = _load(root, path)
        for spec in definition['items']:
            entry = state['items'][spec['name']]
            if entry['status'] == 'complete':
                _verify_entry(root, entry, spec)
            else:
                _refresh_entry(root, file.parent / spec['name'], entry, spec)
        if state['status'] == 'blocked' and not any(entry['status'] == 'blocked' for entry in state['items'].values()):
            state['status'] = 'active'
        _save(file, state)
        return _project(root, path, state, definition)


def advance(root: Path, path: str | None = None) -> dict:
    root = c._root(root)
    path = path or _current_path(root)
    if path is None:
        return _request_template(root)
    file, initial, _ = _load(root, path)
    from catalog_retrieval.runtime import using_pack_runtime
    with using_pack_runtime(_runtime(initial['runtime'])), c.file_lock(file):
        file, state, definition = _load(root, path)
        if state['status'] == 'complete':
            for spec in definition['items']:
                _verify_entry(root, state['items'][spec['name']], spec)
            return _project(root, path, state, definition)
        if _task(root, state['task_id']).get('production_plan') != path:
            raise ValueError('This historical plan belongs to earlier work. Continue the current task\'s bound plan.')
        for spec in definition['items']:
            entry = state['items'][spec['name']]
            if entry['status'] == 'complete':
                continue
            if any(state['items'][name]['status'] != 'complete' for name in spec['after']):
                entry.update(phase='dependency', status='pending', current={'waiting_for': spec['after']})
                continue
            directory = file.parent / spec['name']
            directory.mkdir(parents=True, exist_ok=True)
            try:
                _new_source(root, directory, entry, spec, state['task_id'])
                if 'batch' in entry['source']:
                    _batch(root, directory, entry, spec)
                elif entry['source'].get('kind') in {'imported', 'sheet'}:
                    _curate(root, directory, entry, entry['source'], spec['result'])
                else:
                    if entry.get('run') is None:
                        ready = _input(root, directory, entry, spec, advance=True)
                        _save(file, state)
                        if not ready:
                            continue
                        _publish(root, entry)
                        _save(file, state)
                    _run(root, directory, entry, spec)
                entry.pop('diagnostic', None)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                from production_diagnostics import CompilationError
                entry['status'] = 'blocked'
                entry['diagnostic'] = from_exception(exc, phase='work-plan',
                    required_action='Correct the named current answer or source, then advance the same plan. '
                                    'For changed approval, review or placement, use refresh_action to assess '
                                    'the current basis while preserving committed effects.')
                entry.setdefault('current', {})
                if entry['current'] is None:
                    entry['current'] = {}
                if isinstance(exc, CompilationError):
                    entry['current']['compilation'] = copy.deepcopy(exc.report)
                entry['current']['refresh_action'] = action(root, path, command='plan',
                    reason='Refresh changed current judgments while retaining the previous answer and effects.')
            _save(file, state)
        _finish(root, state, definition)
        if state['status'] != 'complete' and any(entry['status'] == 'blocked' for entry in state['items'].values()):
            state['status'] = 'blocked'
        elif state['status'] == 'blocked':
            state['status'] = 'active'
        _save(file, state)
        return _project(root, path, state, definition)
