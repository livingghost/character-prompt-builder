"""Acquire Studio sources and project the common authoring work into production inputs.

The common core owns the actual candidate and its selected applications. Studio
owns task identity, source roles, publication and compilation of that candidate.
"""
from __future__ import annotations

import copy
from pathlib import Path

import authoring_work
import execution_contract as c
import production_authoring as authoring
from production_diagnostics import ProductionError


SOURCE_GUIDANCE = {
    'document_path': 'references/runtime/production-authoring.md#discover-input-structures',
    'schema': 'schemas/authoring/production-task.schema.json',
}


def source_action(*, root: Path | None, choices_path: str, source_row_path: str) -> dict:
    """Locate the public source acquisition owner without inventing source scope."""
    from cli_invocation import python_argv, shown
    argv = python_argv(Path(__file__).with_name('production_workflow.py'), 'acquire-source',
        '--root', str(root) if root is not None else 'STUDIO', '--choices', choices_path,
        '--source-row', source_row_path)
    return {'command': 'acquire-source', 'argv': argv, 'shown': shown(argv)}


def validate_source_row(source: dict, *, file: str | None = None) -> None:
    """Check the public ProductionTask source shape and its declared identity scope."""
    from state_protocol import read_schema, validate_against_schema
    schema = read_schema(Path(__file__).resolve().parents[1] / SOURCE_GUIDANCE['schema'])
    source_schema = schema['properties']['sources']['items']
    errors = validate_against_schema(source, source_schema, _root_schema=schema)
    if errors:
        missing = [key for key in source_schema['required'] if isinstance(source, dict) and key not in source]
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The source descriptor does not satisfy the public ProductionTask source-row contract.',
            phase='source-acquisition', file=file, pointer='/' + missing[0] if missing else '',
            cause='source-row-invalid', errors=errors, guidance=SOURCE_GUIDANCE,
            expected={'required': list(source_schema['required']), 'schema_pointer': '/properties/sources/items'},
            repair_owner={'file': file, 'pointer': ''},
            required_action='Correct the named field in the source-row descriptor using the source schema, '
                'then run acquire-source with that descriptor again.')
    import identity_coverage
    try:
        identity_coverage.validate_task({'sources': [source], 'criteria': []})
    except ProductionError as error:
        diagnostic = error.diagnostic
        raise ProductionError(diagnostic.code, diagnostic.message, phase='source-acquisition',
            file=file, pointer='/identity', cause='source-identity-invalid',
            source=source['id'], guidance=SOURCE_GUIDANCE,
            repair_owner={'file': file, 'pointer': '/identity'},
            required_action='Correct identity.subject_ids and identity.selectors in the source-row descriptor, '
                'preserving its actual source authority, then run acquire-source again.') from error


def acquire_record(source: dict, raw: bytes, *, file: str | None = None,
                   kind: str = 'studio-source') -> dict:
    """Capture one source row and the exact original bytes selected by it."""
    validate_source_row(source, file=file)
    path = (source.get('origin') or {}).get('path', source['path'])
    origin = {'kind': kind, 'source': copy.deepcopy(source)}
    if file is not None:
        origin['source_row'] = {'file': file}
    if source.get('definition_owner') is not None:
        origin.update(kind='task-subject', subject_id=source['definition_owner']['subject_id'])
    try:
        record = authoring_work.acquire_source(raw, format=_format(path, raw), origin=origin)
    except (UnicodeError, TypeError, ValueError) as error:
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The selected source bytes do not satisfy their acquisition format.',
            phase='source-acquisition', file=file, pointer='/path',
            cause='source-content-invalid', source=source['id'], source_file=path,
            detail=str(error), guidance=SOURCE_GUIDANCE,
            repair_owner={'file': file, 'pointer': '/path'},
            required_action='Correct the selected source content or choose its intended original file '
                'in the source-row descriptor, then run acquire-source again.') from error
    if source.get('origin') is not None and source['origin']['sha256'] != record['sha256']:
        raise ProductionError('IDENTITY_SOURCE_CHANGED',
            'The selected original differs from the source-row acquisition digest.',
            phase='source-acquisition', file=file, pointer='/origin/sha256',
            source=source['id'], cause='source-origin-changed',
            expected=source['origin']['sha256'], actual=record['sha256'], guidance=SOURCE_GUIDANCE,
            repair_owner={'file': file, 'pointer': '/origin'},
            required_action='Select the intended current original in the source-row descriptor and reassess '
                'its source scope before acquiring it again. Retain the earlier captured source unchanged.')
    try:
        applications, subjects, _ = _applications({source['id']: record}, {source['id']})
    except (TypeError, ValueError) as error:
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The source descriptor cannot form distinct current applications.',
            phase='source-acquisition', file=file, pointer='/applications',
            cause='source-applications-invalid', source=source['id'],
            detail=str(error), guidance=SOURCE_GUIDANCE,
            repair_owner={'file': file, 'pointer': '/applications'},
            required_action='Correct application IDs and selections in the source-row descriptor, '
                'then run acquire-source again.') from error
    identity = source.get('identity')
    if identity is not None and (
            {item['pointer'] for item in applications.values()} != set(identity['selectors'])
            or set(subjects) != set(identity['subject_ids'])):
        raise ProductionError('IDENTITY_CONTRACT_INVALID',
            'Source applications do not match the descriptor identity selectors and subject scope.',
            phase='source-acquisition', file=file, pointer='/applications',
            cause='source-applications-mismatch', source=source['id'], guidance=SOURCE_GUIDANCE,
            expected=copy.deepcopy(identity), actual={'applications': copy.deepcopy(source.get('applications'))},
            repair_owner={'file': file, 'pointer': '/applications'},
            required_action='Omit applications to derive them from identity.selectors and identity.subject_ids, '
                'or correct the descriptor applications to represent that same selection, then acquire it again.')
    for ident, application in applications.items():
        try:
            authoring_work.source_value(record, application['pointer'])
        except (TypeError, ValueError) as error:
            raise ProductionError('IDENTITY_SELECTOR_MISSING' if identity is not None else 'INPUT_CONSISTENCY_ERROR',
                'A source application does not resolve against the acquired original.',
                phase='source-acquisition', file=file, pointer='/identity/selectors' if identity else '/applications',
                source=source['id'], application=ident, selector=application['pointer'],
                cause='source-selector-missing', source_file=path, detail=str(error), guidance=SOURCE_GUIDANCE,
                repair_owner={'file': file, 'pointer': '/identity/selectors' if identity else '/applications'},
                required_action='Correct the source-row selector or select the intended original file, '
                    'then run acquire-source again. The previous acquired source is unchanged.') from error
    return record


def acquire_source_row(basis: dict, source: dict, raw: bytes, *, file: str | None = None) -> dict:
    """Replace one logical source and its applications while retaining prior acquisitions."""
    record = acquire_record(source, raw, file=file)
    ident = source['id']
    sources = copy.deepcopy(basis['sources'])
    _retain_acquisition(sources, ident, record)
    removed = {key for key, row in basis['applications'].items() if row['source'] == ident}
    applications = {key: copy.deepcopy(row) for key, row in basis['applications'].items() if key not in removed}
    subjects = {key: [application for application in selected if application not in removed]
                for key, selected in basis['subjects'].items()}
    subjects = {key: selected for key, selected in subjects.items() if selected}
    requirements = [key for key in basis['requirements'] if key not in removed]
    selected = {ident} if source['disposition'] == 'applied' else set()
    added, assigned, required = _applications({ident: record}, selected)
    conflicts = sorted(set(added) & set(applications))
    if conflicts:
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The source applications reuse IDs already owned by another current source.',
            phase='source-acquisition', file=file, pointer='/applications',
            source=ident, cause='source-application-id-collision', applications=conflicts,
            repair_owner={'file': file, 'pointer': '/applications'}, guidance=SOURCE_GUIDANCE,
            required_action='Choose distinct application IDs in the source-row descriptor, '
                'or a distinct source ID when deriving applications, then acquire it again.')
    applications.update(added)
    for subject, selected_apps in assigned.items():
        subjects[subject] = [*subjects.get(subject, []), *selected_apps]
    requirements.extend(required)
    try:
        return authoring_work.revise_basis(basis, sources=sources, applications=applications,
                                          subjects=subjects, requirements=requirements)
    except authoring_work.AuthoringWorkError as error:
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The acquired source cannot form a valid current authoring selection.',
            phase='source-acquisition', file=file, pointer='', source=ident,
            cause='source-selection-invalid', errors=error.report['errors'], guidance=SOURCE_GUIDANCE,
            repair_owner={'file': file, 'pointer': ''},
            required_action='Correct the descriptor selection using the reported source or subject defect, '
                'then run acquire-source again. No draft files have been changed.') from error


def requires_subject(task: dict) -> bool:
    return task['route'] not in {'upscale', 'adoption'}


def _retain_acquisition(sources: dict, ident: str, record: dict) -> None:
    """Keep the exact prior acquisition when a logical source is reassessed."""
    previous = sources.get(ident)
    if previous is not None and previous != record:
        captured = ident + ':captured:' + c.content_id(previous)
        if captured in sources and sources[captured] != previous:
            raise ValueError('an acquired source record differs from its content address: ' + captured)
        sources[captured] = copy.deepcopy(previous)
    sources[ident] = record


def bind_task_subjects(basis: dict, choices: dict) -> dict:
    """Acquire task-local identity from the actual Production Specification owner."""
    specification = (choices.get('authoring') or {}).get('documents', {}).get('production_spec')
    sources = copy.deepcopy(basis['sources'])
    applications = copy.deepcopy(basis['applications'])
    subjects = copy.deepcopy(basis['subjects'])
    for ident, selected in list(subjects.items()):
        derived = [key for key in selected
                   if (sources[applications[key]['source']].get('origin') or {}).get('kind') == 'task-subject']
        if derived:
            subjects[ident] = [key for key in selected if key not in derived]
            if not subjects[ident]:
                del subjects[ident]
            for key in derived:
                if not any(key in other for other in subjects.values()) and key not in basis['requirements']:
                    applications.pop(key)
    if not isinstance(specification, dict) or not isinstance(specification.get('subjects'), list):
        return authoring_work.revise_basis(basis, applications=applications, subjects=subjects)
    for subject in specification['subjects']:
        ident = subject.get('id')
        if not isinstance(ident, str) or not subject.get('identity'):
            continue
        current = subjects.get(ident, [])
        if current and any((sources[applications[key]['source']].get('origin') or {}).get('kind') != 'task-subject'
                           for key in current):
            continue
        source = 'task-subject:' + ident
        acquired = authoring_work.acquire_source(c.encoded(subject), format='json',
            origin={'kind': 'task-subject', 'subject_id': ident})
        _retain_acquisition(sources, source, acquired)
        applications[source] = {'source': source, 'pointer': '/identity'}
        subjects[ident] = [source]
    return authoring_work.revise_basis(basis, sources=sources, applications=applications, subjects=subjects)


def _format(path: str, raw: bytes) -> str:
    if Path(path).suffix.lower() == '.json':
        c.decode(raw)
        return 'json'
    try:
        raw.decode('utf-8')
    except UnicodeError:
        return 'binary'
    return 'text'


def _applications(sources: dict, selected: set[str]) -> tuple[dict, dict, list[str]]:
    applications, subjects, requirements = {}, {}, []
    for ident, record in sources.items():
        if ident not in selected:
            continue
        source = (record.get('origin') or {}).get('source', {})
        identity = source.get('identity')
        pointers = identity['selectors'] if identity else ['']
        selections = source.get('applications')
        if selections is None:
            selections = [{'id': ident if len(pointers) == 1 else ident + ':' + str(index + 1),
                'pointer': pointer, 'subjects': (identity or {}).get('subject_ids', []), 'requirement': False}
                for index, pointer in enumerate(pointers)]
        for item in selections:
            key = item['id']
            if key in applications:
                raise ValueError('source applications repeat the same id: ' + key)
            applications[key] = {'source': ident, 'pointer': item['pointer']}
            for subject in item['subjects']:
                subjects.setdefault(subject, []).append(key)
            if item['requirement']:
                requirements.append(key)
    return applications, subjects, requirements


def _protected(task: dict, protected: set[str]) -> tuple[list, list, set[str]]:
    criteria = set(protected)
    retained = set()
    pending = True
    while pending:
        pending = False
        for item in task['direction']['source_allowances']:
            scope = item['scope']
            applicable = scope['kind'] == 'source' or scope['task_id'] == task['task_id']
            if applicable and item['id'] not in retained and criteria.intersection(item['criteria']):
                retained.add(item['id'])
                criteria.update(item['criteria'])
                pending = True
    allowances = [copy.deepcopy(item) for item in task['direction']['source_allowances'] if item['id'] in retained]
    selected = {item['source'] for item in allowances}
    selected.update(item['scope']['source'] for item in allowances if item['scope']['kind'] == 'source')
    return ([copy.deepcopy(item) for item in task['criteria'] if item['id'] in criteria],
            allowances, selected)


def begin(choices: dict, *, task: dict, operation: str, request: str | None,
          read_source, prior_basis: dict | None = None, applied_sources: list[str] | None = None,
          protected_criteria: set[str] = frozenset(), route: str | None = None,
          artifact: str | None = None, execution: str | None = None,
          features: list[str] | None = None, initial: bool = False,
          focus: str | None = None) -> tuple[dict, dict, dict]:
    """Acquire one starting point; selected source uses are separate from the catalog."""
    previous = copy.deepcopy(choices)
    sources = copy.deepcopy((prior_basis or {}).get('sources', {}))
    old_request_sources = {ident for ident, item in sources.items()
                           if (item.get('origin') or {}).get('kind') == 'current-request'}
    if prior_basis is not None and prior_basis['request'] is not None:
        old_request_sources.add('request:' + c.digest(prior_basis['request'].encode('utf-8')))
    source_rows = task.get('sources', [])
    for source in source_rows:
        path = (source.get('origin') or {}).get('path', source['path'])
        raw = read_source(path)
        _retain_acquisition(sources, source['id'], acquire_record(source, raw,
            kind='current-request' if source['id'] in old_request_sources else 'studio-source'))
    if request is None and prior_basis is not None:
        request = prior_basis['request']
    selected = {item['id'] for item in source_rows if item['disposition'] == 'applied'} - old_request_sources
    selected.update(applied_sources or [])
    unknown = selected - set(sources)
    if unknown:
        raise ValueError('selected authoring sources were not acquired: ' + ', '.join(sorted(unknown)))
    # The selected candidate supplies meaningful authored content for either
    # operation. Compose gives its source selection a new owner; it does not
    # discard the prompt, controls or independently authored review criteria.
    current, current_task = copy.deepcopy(choices), copy.deepcopy(task)
    for key, value in {'route': route, 'artifact': artifact, 'execution': execution,
                       'features': features}.items():
        if value is not None:
            current_task[key] = copy.deepcopy(value)
            current['authoring']['task'][key] = copy.deepcopy(value)
    current_task.pop('execution_decisions', None)
    current['authoring']['task'].pop('execution_decisions', None)
    if current_task.get('route') == 'upscale' and current_task.get('execution') == 'dispatcher':
        if current['authoring'].get('upscale') is None:
            current['authoring']['upscale'] = authoring.blank(current_task)['upscale']
    else:
        current['authoring']['upscale'] = None
    if operation == 'compose' and not initial:
        current_task['authority'] = None
        current['authoring']['task']['authority'] = None
    applications, subjects, selected_requirements = _applications(sources, selected)
    if prior_basis is not None and not initial:
        # Preserve explicit scopes, including task-local subjects, from the one
        # application owner. The current request is selected separately below.
        applications = copy.deepcopy(prior_basis['applications'])
        subjects = copy.deepcopy(prior_basis['subjects'])
        more, more_subjects, more_requirements = _applications(sources, set(applied_sources or []))
        applications.update(more)
        selected_requirements.extend(more_requirements)
        for ident, rows in more_subjects.items():
            subjects[ident] = list(dict.fromkeys([*subjects.get(ident, []), *rows]))
    if request is not None:
        raw = request.encode('utf-8')
        ident = 'request:' + c.digest(raw)
        _retain_acquisition(sources, ident, authoring_work.acquire_source(raw, origin={'kind': 'current-request'}))
    retained_requirements = prior_basis['requirements'] if prior_basis is not None and not initial else []
    requirements = list(dict.fromkeys([*retained_requirements, *selected_requirements]))
    # Preserve the actual protected source, rather than stamping edited criteria
    # as a new historical requirement when a live candidate is composed again.
    protected_ids = set()
    for application in requirements:
        selection = applications[application]
        record = sources[selection['source']]
        if (record.get('origin') or {}).get('kind') == 'protected-requirements':
            value = authoring_work.source_value(record, selection['pointer'])
            if isinstance(value, dict):
                protected_ids.add(value.get('id'))
    newly_protected = set(protected_criteria) - protected_ids
    criteria, _, _ = _protected(task, newly_protected)
    if criteria:
        source = 'protected-requirements:' + c.content_id(criteria)
        _retain_acquisition(sources, source, authoring_work.acquire_source(c.encoded(criteria),
            format='json', origin={'kind': 'protected-requirements', 'task_id': task['task_id']}))
        for index, criterion in enumerate(criteria):
            ident = 'protected-requirement:' + criterion['id']
            applications[ident] = {'source': source, 'pointer': '/' + str(index)}
            if ident not in requirements:
                requirements.append(ident)
    work = authoring_work.begin_work(operation=operation, request=request, sources=sources,
        applications=applications, subjects=subjects, requirements=requirements,
        baseline=None if initial else previous, content=current if operation == 'compose' else None,
        focus=focus or (prior_basis or {}).get('focus', 'character'))
    if operation == 'amend':
        work = authoring_work.replace_content(work, current)
    work['basis'] = bind_task_subjects(work['basis'], work['content'])
    return work['content'], work['basis'], current_task


def project(basis: dict, choices: dict, out_dir: str) -> tuple[dict, dict[str, bytes], dict | None]:
    """Derive task sources from actual selected applications, retaining every source byte in basis."""
    authoring_work.resolve_work({'basis': basis, 'content': choices}, complete=False)
    selected = {}
    for ident, application in sorted(basis['applications'].items()):
        source = application['source']
        row = selected.setdefault(source, {'pointers': [], 'subjects': [], 'applications': []})
        row['pointers'].append(application['pointer'])
        subjects = sorted(subject for subject, applications in basis['subjects'].items() if ident in applications)
        row['subjects'].extend(subjects)
        row['applications'].append({'id': ident, 'pointer': application['pointer'], 'subjects': subjects,
                                    'requirement': ident in basis['requirements']})
    rows, files, witnesses = [], {}, {}
    request = None
    request_source = None if basis['request'] is None else 'request:' + c.digest(basis['request'].encode('utf-8'))
    for ident, selection in selected.items():
        record = basis['sources'][ident]
        raw = authoring_work.source_bytes(record)
        original_raw = raw
        origin = record.get('origin') or {}
        original = origin.get('source')
        if origin.get('kind') == 'protected-requirements':
            continue
        scoped = selection['pointers'] != [''] and not (original or {}).get('identity')
        if scoped:
            values = [authoring_work.source_value(record, pointer) for pointer in selection['pointers']]
            raw = c.encoded(values[0] if len(values) == 1 else values)
        extension = '.json' if scoped or record['format'] == 'json' else '.txt' if record['format'] == 'text' else '.bin'
        if original and not scoped and Path(original['path']).suffix:
            extension = Path(original['path']).suffix
        name = 'work-sources/' + c.digest(raw) + extension
        path = (Path(out_dir) / name).as_posix()
        files[name] = raw
        source = copy.deepcopy(original) if original is not None else {
            'id': ident, 'role': 'definition' if selection['subjects'] else 'reference',
            'disposition': 'applied', 'locator': 'whole source',
            'reason': 'Current authoring application of the acquired source.'}
        source.update(id=ident, path=path, disposition='applied')
        source.pop('origin', None)
        source.pop('definition_owner', None)
        if origin.get('kind') == 'task-subject':
            source['definition_owner'] = {'document': 'production_spec', 'subject_id': origin['subject_id']}
        source['applications'] = copy.deepcopy(selection['applications'])
        if scoped:
            source['locator'] = 'Selected source pointers: ' + ', '.join(selection['pointers'])
            original_name = 'work-catalog/' + record['sha256'] + ('.json' if record['format'] == 'json' else '.txt')
            files[original_name] = original_raw
            source['origin'] = {'path': (Path(out_dir) / original_name).as_posix(), 'sha256': record['sha256']}
        if selection['subjects'] and (original or {}).get('identity'):
            source['identity'] = {**source.get('identity', {}),
                'subject_ids': list(dict.fromkeys(selection['subjects'])),
                'selectors': list(dict.fromkeys(selection['pointers']))}
        else:
            source.pop('identity', None)
        rows.append(source)
        witnesses[path] = c.digest(raw)
    if request_source is not None:
        raw = basis['request'].encode('utf-8')
        name = 'work-sources/' + c.digest(raw) + '.txt'
        path = (Path(out_dir) / name).as_posix()
        files[name] = raw
        rows = [row for row in rows if row['id'] != request_source]
        rows.append({'id': request_source, 'path': path, 'role': 'brief', 'disposition': 'applied',
                     'locator': 'whole text', 'reason': 'Current request acquired as exact UTF-8 text.',
                     'applications': []})
        witnesses[path] = c.digest(raw)
        request = {'source': request_source, 'path': path, 'text': basis['request']}
    result = copy.deepcopy(choices)
    authored = result['authoring']
    authored['task']['work_basis'] = (Path(out_dir) / 'work-basis.json').as_posix()
    authored['task']['sources'] = rows
    authored['source_files'] = {**authored['source_files'], **witnesses}
    if request_source is not None:
        previous_requests = {ident for ident, item in basis['sources'].items()
                             if (item.get('origin') or {}).get('kind') == 'current-request'}
        direction = authored['task']['direction']
        direction['basis'] = [ident for ident in direction['basis'] if ident not in previous_requests]
        direction['basis'].append(request_source)
    return result, files, request


def projection_diagnostics(basis: dict, choices: dict, *, projected: dict | None = None,
                           root: Path | None = None, choices_path: str | None = None,
                           basis_path: str | None = None) -> list[dict]:
    """Explain identity metadata loss at its acquisition owner before compilation.

    Generic acquisitions remain valid for ordinary sources. A Production
    descriptor is required when an actual criterion binds that source's
    identity. Unknown source IDs and subject-scope mistakes keep their own
    identity diagnostics rather than becoming acquisition failures.
    """
    choices_path = choices_path or 'choices.json'
    folder = Path(choices_path).parent
    basis_path = basis_path or (folder / 'work-basis.json').as_posix()
    if projected is None:
        projected, _, _ = project(basis, choices, folder.as_posix())
    authored_task = choices['authoring']['task']
    projected_task = projected['authoring']['task']
    previous = {row['id']: row for row in authored_task.get('sources', [])}
    selected = {row['id']: (index, row) for index, row in enumerate(projected_task['sources'])}
    bound = {}
    for criterion in authored_task.get('criteria', []):
        for binding in criterion.get('identity_bindings', []):
            if isinstance(binding, dict) and isinstance(binding.get('source'), str):
                bound.setdefault(binding['source'], []).append((criterion['id'], binding))
    diagnostics = []
    for ident, bindings in bound.items():
        if ident not in selected or ident not in basis['sources']:
            continue
        index, current = selected[ident]
        if current.get('identity') is not None:
            continue
        record = basis['sources'][ident]
        origin = record.get('origin') or {}
        original = origin.get('source')
        if original is None:
            cause = 'source-metadata-not-acquired'
            message = ('The selected source has no acquired Production source-row metadata. '
                       'Its projected source therefore has no identity selection for the declared binding.')
        elif original.get('identity') is None:
            cause = 'source-identity-not-declared'
            message = ('The acquired Production source row does not declare identity. '
                       'Its projected source cannot resolve the declared identity binding.')
        else:
            cause = 'source-applications-mismatch'
            message = ('The current applications assign no subject to this acquired identity source. '
                       'Projection therefore has no current identity selection for the declared binding.')
        applications = copy.deepcopy(current['applications'])
        subjects = sorted({subject for row in applications for subject in row['subjects']})
        owner_path = (origin.get('source_row') or {}).get('file')
        owner_path = owner_path or (folder / ('source-row-' + c.content_id(ident)[:12] + '.json')).as_posix()
        repair_owner = {'file': owner_path, 'pointer': ''}
        authored_source = previous.get(ident)
        template = copy.deepcopy(original or authored_source or {})
        template.update(id=ident,
            path=(current.get('origin') or {}).get('path', current['path']),
            role=template.get('role', 'identity-contract'), disposition='applied',
            locator=template.get('locator', 'Selected identity from the acquired original'),
            reason=template.get('reason', 'The declared source scope supplies this identity comparison.'))
        template.pop('applications', None)
        template.pop('origin', None)
        template.pop('definition_owner', None)
        identity = copy.deepcopy((original or authored_source or {}).get('identity') or {})
        identity.update(subject_ids=subjects or sorted({subject for _, binding in bindings
                            for subject in binding.get('subject_ids', [])}),
                        selectors=list(dict.fromkeys(row['pointer'] for row in applications)))
        template['identity'] = identity
        dropped = [field for field in ('identity', 'role', 'disposition', 'locator', 'reason')
                   if field in (authored_source or {}) and authored_source[field] != current.get(field)]
        action = source_action(root=root, choices_path=choices_path, source_row_path=owner_path)
        pointer = '/authoring/task/sources/' + str(index) + '/identity'
        diagnostics.append({'field': 'authoring.task.sources', 'code': 'IDENTITY_CONTRACT_INVALID',
            'severity': 'error', 'phase': 'authoring-projection', 'file': choices_path, 'pointer': pointer,
            'source': ident, 'criteria': sorted({criterion for criterion, _ in bindings}),
            'cause': cause, 'message': message, 'guidance': dict(SOURCE_GUIDANCE),
            'required_action': 'Save the proposed source_row in ' + owner_path +
                ' after choosing its identity scope from the actual source authority, then run the supplied '
                'acquire-source command. Task sources are regenerated from the acquired descriptor; '
                'editing their projected identity will not repair the acquisition.',
            'repair_owner': repair_owner, 'repair_action': action, 'source_row': template,
            'projection': {'authored_source': copy.deepcopy(authored_source),
                'acquired_origin_kind': origin.get('kind'),
                'origin_has_source_metadata': original is not None,
                'acquired_source': {'file': basis_path,
                    'pointer': '/sources/' + ident.replace('~', '~0').replace('/', '~1') + '/origin/source'},
                'applications': applications, 'subjects': subjects,
                'projected_source_path': current['path'], 'projected_identity': None,
                'dropped_fields': dropped, 'repair_owner': repair_owner}})
    return diagnostics


def amend_task(basis: dict, *, task: dict, baseline: dict, request: str | None,
               delivery: str, documents: dict, read_source, out_dir: str) -> tuple[dict, dict[str, bytes]]:
    """Acquire a bounded task edit through the same current-application owner.

    The task carries the explicitly edited source selections. Prior acquired
    bytes remain catalog evidence; only the current rows become applications.
    A document replacement can therefore change its selected source without
    letting a saved basis silently reapply the previous value.
    """
    sources = copy.deepcopy(basis['sources'])
    selected_records, selected = {}, set()
    previous_request = None if basis['request'] is None else 'request:' + c.digest(basis['request'].encode('utf-8'))
    for row in task['sources']:
        ident = row['id']
        if ident == previous_request and not row.get('applications'):
            continue
        path = (row.get('origin') or {}).get('path', row['path'])
        raw = read_source(path)
        record = acquire_record(row, raw)
        previous = sources.get(ident)
        if previous is not None and previous['sha256'] == record['sha256']:
            # Keep the original acquisition locator while applying the current
            # published relationships and editorial descriptions.
            previous_origin = previous.get('origin') or {}
            original_source = previous_origin.get('source')
            if original_source is not None:
                record['origin']['source']['path'] = original_source['path']
            if previous_origin.get('kind') == 'retained-definition':
                record['origin']['kind'] = 'retained-definition'
        _retain_acquisition(sources, ident, record)
        selected_records[ident] = {**record, 'origin': {**record['origin'], 'source': copy.deepcopy(row)}}
        if row['disposition'] == 'applied':
            selected.add(ident)
    applications, subjects, requirements = _applications(selected_records, selected)
    for ident in basis['requirements']:
        application = basis['applications'][ident]
        if (sources[application['source']].get('origin') or {}).get('kind') == 'protected-requirements':
            applications[ident] = copy.deepcopy(application)
            requirements.append(ident)
    if request is not None:
        request_id = 'request:' + c.digest(request.encode('utf-8'))
        _retain_acquisition(sources, request_id, authoring_work.acquire_source(request, origin={'kind': 'current-request'}))
    work = authoring_work.begin_work(operation='amend', request=request, sources=sources,
        applications=applications, subjects=subjects, requirements=list(dict.fromkeys(requirements)),
        baseline=baseline, focus=basis['focus'])
    work = authoring_work.replace_content(work, {'task': copy.deepcopy(task),
        'delivery': delivery, 'documents': copy.deepcopy(documents)})
    choices = {'authoring': {'task': copy.deepcopy(task), 'documents': copy.deepcopy(documents),
        'delivery': {'content': delivery, 'translation_notes': None}, 'source_files': {}}}
    work['basis'] = bind_task_subjects(work['basis'], choices)
    projected, files, _ = project(work['basis'], choices, out_dir)
    files['work-basis.json'] = c.encoded(work['basis'])
    return projected['authoring']['task'], files


def protected_requirement_diagnostics(basis: dict, task: dict, *, basis_path: str | None = None,
                                      choices_path: str | None = None, root: Path | None = None,
                                      criteria_pointer: str | None = None) -> list[dict]:
    """Compare retained requirements at their actual owner before publication.

    This is the same exact comparison the completed-task reader performs. The
    author chooses whether a changed request permits different requirements;
    this view does not remove a selection or infer permission from prose.
    """
    from cli_invocation import python_argv, shown
    basis_path = basis_path or task.get('work_basis')
    criteria = {item['id']: (index, item) for index, item in enumerate(task.get('criteria') or [])
                if isinstance(item, dict) and 'id' in item}
    result = []
    for index, application in enumerate(basis['requirements']):
        selection = basis['applications'][application]
        record = basis['sources'][selection['source']]
        if (record.get('origin') or {}).get('kind') != 'protected-requirements':
            continue
        expected = authoring_work.source_value(record, selection['pointer'])
        criterion = expected.get('id') if isinstance(expected, dict) else None
        current_index, actual = criteria.get(criterion, (None, None))
        if isinstance(expected, dict) and actual == expected:
            continue
        current_pointer = criteria_pointer or ('/authoring/task/criteria' if choices_path is not None else '/criteria')
        if current_index is not None:
            current_pointer += '/' + str(current_index)
        application_pointer = '/applications/' + application.replace('~', '~0').replace('/', '~1')
        help_argv = python_argv(Path(__file__).with_name('authoring_work.py'), 'context', '--help')
        context_argv = None
        if basis_path is not None:
            location = str(root / basis_path) if root is not None else basis_path
            context_argv = python_argv(Path(__file__).with_name('authoring_work.py'),
                                       'context', location, '--basis-only')
        result.append({'field': 'authoring_work.requirements', 'code': 'AUTHORING_WORK_MISMATCH',
            'phase': 'authoring-work', 'cause': 'protected-requirement-changed',
            'message': 'A protected requirement differs from its actual task criterion.',
            'file': basis_path, 'pointer': '/requirements/' + str(index),
            'application': application, 'criterion': criterion,
            'expected': copy.deepcopy(expected), 'actual': copy.deepcopy(actual),
            'repair_owner': {'file': basis_path, 'pointer': '/requirements',
                'application_pointer': application_pointer,
                'source': selection['source'], 'source_pointer': selection['pointer']},
            'current_criterion_owner': {'file': choices_path, 'pointer': current_pointer},
            'guidance': {'document_path': 'references/runtime/authoring-work.md#apply-sources-to-this-candidate'},
            'next_action': {'command': 'authoring-work-context-help', 'argv': help_argv,
                            'shown': shown(help_argv), 'external_effect': False},
            **({'context_edit': {'argv_prefix': context_argv, 'shown_prefix': shown(context_argv),
                'requires_author_input': True,
                'selection_arguments': '--source ID=FILE; --application APP=SOURCE#POINTER; repeated --requirement APP',
                'meaning': 'Supply the complete intended current requirement selection. The acquired source catalog remains.'}}
               if context_argv is not None else {}),
            'required_action': 'Compare the retained requirement with the current criterion at the displayed owners. '
                'Restore the criterion if the requirement remains binding. If an actual instruction authorizes '
                'the change, use authoring_work.py context on the editable basis with --basis-only to acquire '
                'the explicit current requirement sources and select their applications with repeated --requirement. '
                'Those flags replace the current requirement selection; preserve every other binding requirement '
                'and retain the original source catalog. Do not rewrite a saved run or silently drop protection. '
                'Then inspect the same draft again. This selection grants no execution authority.'})
    return result


def unresolved(basis: dict, choices: dict, *, require_subject: bool = False,
               root: Path | None = None, choices_path: str | None = None,
               basis_path: str | None = None) -> list[dict]:
    report = authoring_work.validate_work({'basis': basis, 'content': choices}, complete=True,
                                           require_subject=require_subject)
    specification = choices['authoring']['documents'].get('production_spec')
    if require_subject and basis['focus'] == 'character' and isinstance(specification, dict):
        actual_subjects = {row.get('id') for row in specification.get('subjects', []) if isinstance(row, dict)}
        if not actual_subjects:
            report['errors'].append({'path': '/content/authoring/documents/production_spec/subjects',
                'message': 'The current character depiction has no Production Specification subject.'})
        for ident in actual_subjects - set(basis['subjects']):
            report['errors'].append({'path': '/basis/subjects',
                'message': 'The current subject ' + str(ident) + ' has no applied character definition.'})
    result = [{'field': 'authoring_work' + item['path'], 'code': 'AUTHORING_WORK_INCOMPLETE',
             'phase': 'authoring', 'message': item['message'],
             'required_action': 'Complete the named current request or source application in work-basis.json.',
             'guidance': {'document_path': 'references/runtime/authoring-work.md'}}
            for item in report['errors']]
    # Invalid applications already have their owning core diagnostics. Compare
    # criteria only after those selections can be resolved without guessing.
    if not report['errors']:
        changes = choices.get('task_changes') or {}
        task = {**choices['authoring']['task'], **changes}
        result.extend(protected_requirement_diagnostics(basis, task, root=root,
            choices_path=choices_path, basis_path=basis_path,
            criteria_pointer='/task_changes/criteria' if 'criteria' in changes else None))
        if root is not None and basis.get('change_scope') is not None:
            import production_change_scope
            scope = production_change_scope.evaluate(root, choices, task, basis)
            result.extend(production_change_scope.diagnostics(scope, basis_path=basis_path))
    return result


def publish_sources(root: Path, out_dir: str, files: dict[str, bytes]) -> None:
    """Materialize content-addressed selected sources for the existing compiler."""
    for name, raw in files.items():
        path = c.local(root, (Path(out_dir) / name).as_posix(), exists=False)
        if path.exists():
            if c.read(path) != raw:
                raise ValueError('an acquired authoring source differs from its content address: ' + str(path))
        else:
            c.atomic(path, raw)


def resolve_task_work(task: dict, *, basis: dict, delivery: str, documents: dict,
                      read_source) -> dict:
    """Check completed task content against its acquired request and source applications.

    This consumes actual task files. It does not authorize a meaning, decide a
    medium or treat selected source text as evidence that the prompt conveys it.
    """
    from production_diagnostics import ProductionError
    guidance = {'document_path': 'references/runtime/authoring-work.md'}
    repair = ('Continue the actual authoring work and update its request, selected definitions or applications. '
              'Export the current task and basis together, then check or prepare that task again.')

    def mismatch(message, *, file=None, pointer=None, **details):
        raise ProductionError('AUTHORING_WORK_MISMATCH', message, phase='authoring-work',
            file=file or task.get('work_basis'), pointer=pointer, required_action=repair,
            guidance=guidance, **details)

    content = {'task': copy.deepcopy(task), 'delivery': delivery, 'documents': copy.deepcopy(documents)}
    try:
        resolved = authoring_work.resolve_work({'basis': basis, 'content': content}, complete=True,
                                               require_subject=requires_subject(task))
    except authoring_work.AuthoringWorkError as error:
        raise ProductionError('AUTHORING_WORK_INCOMPLETE',
            'The acquired authoring work is incomplete or inconsistent.', phase='authoring-work',
            file=task.get('work_basis'), required_action=repair, guidance=guidance,
            errors=error.report['errors']) from error

    specifications = []
    if isinstance(documents.get('production_spec'), dict):
        specifications.append(documents['production_spec'])
    else:
        for source in task['sources']:
            if source['disposition'] == 'applied' and source['role'] == 'production-spec':
                specifications.append(c.decode(read_source(source['path'])))
    character_focus = requires_subject(task) and basis['focus'] == 'character'
    actual = {}
    for specification in specifications:
        subjects = specification.get('subjects', [])
        if character_focus and not subjects:
            mismatch('The current character depiction has no Production Specification subject.',
                     pointer='$.subjects')
        for subject in subjects:
            ident = subject.get('id')
            if character_focus and ident not in basis['subjects']:
                mismatch('The current subject has no selected character definition.',
                         pointer='$.subjects', subject=ident)
            actual.setdefault(ident, []).append(subject.get('identity'))
    for ident, applications in basis['subjects'].items():
        for application in applications:
            selection = basis['applications'][application]
            record = basis['sources'][selection['source']]
            if (record.get('origin') or {}).get('kind') != 'task-subject':
                continue
            selected = authoring_work.source_value(record, selection['pointer'])
            if ident not in actual or any(value != selected for value in actual[ident]):
                mismatch('The acquired task-local definition differs from the current subject identity.',
                         pointer='$.subjects', subject=ident, application=application)

    # The common projector supplies the operative source relationship. Storage
    # paths and explanatory locators do not become a second source of meaning.
    projected, files, _ = project(basis, {'authoring': {'task': copy.deepcopy(task),
        'source_files': {}}}, '.')
    expected = {source['id']: source for source in projected['authoring']['task']['sources']}
    actual = {source['id']: source for source in task['sources']}
    if actual.keys() != expected.keys():
        mismatch('The task sources differ from the current acquired applications.', pointer='$.sources',
                 expected_sources=sorted(expected), actual_sources=sorted(actual))
    for ident, source in actual.items():
        wanted = expected[ident]
        for field in ('role', 'disposition', 'identity', 'definition_owner'):
            if source.get(field) != wanted.get(field):
                mismatch('A task source has a different operative source relationship.',
                         file=source['path'], source=ident, field=field)
        applications = source.get('applications', [])
        if applications != wanted['applications']:
            mismatch('A task source has different applications from the acquired work.',
                     file=source['path'], source=ident)
        raw = read_source(source['path'])
        if wanted.get('origin') is not None:
            original = source.get('origin')
            record = basis['sources'][ident]
            if (original is None or original['sha256'] != record['sha256']
                    or read_source(original['path']) != authoring_work.source_bytes(record)):
                mismatch('A projected task source has different original bytes from its acquisition.',
                         file=source['path'], source=ident)
            if c.encoded(c.decode(raw)) != files[wanted['path']]:
                mismatch('A task source differs from its selected acquired values.', file=source['path'], source=ident)
        elif source.get('origin') is not None or raw != files[wanted['path']]:
            mismatch('A task source differs from its exact acquired content.', file=source['path'], source=ident)
    protected = protected_requirement_diagnostics(basis, task)
    if protected:
        diagnostic = protected[0]
        raise ProductionError(diagnostic['code'], diagnostic['message'],
            **{key: value for key, value in diagnostic.items() if key not in {'code', 'message'}})
    return {'basis': task['work_basis'], 'content_sha256': authoring_work.digest(resolved['content']),
            'sources': sorted(actual), 'subjects': sorted(basis['subjects'])}
