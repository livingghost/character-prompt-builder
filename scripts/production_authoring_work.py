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
        origin = {'kind': 'current-request' if source['id'] in old_request_sources else 'studio-source',
                  'source': copy.deepcopy(source)}
        if source.get('definition_owner') is not None:
            origin.update(kind='task-subject', subject_id=source['definition_owner']['subject_id'])
        _retain_acquisition(sources, source['id'], authoring_work.acquire_source(raw,
            format=_format(path, raw), origin=origin))
    if request is None and prior_basis is not None:
        request = prior_basis['request']
    if initial:
        selected = {item['id'] for item in source_rows if item['disposition'] == 'applied'} - old_request_sources
    elif operation == 'amend':
        selected = {item['id'] for item in source_rows if item['disposition'] == 'applied'} - old_request_sources
    else:
        selected = {item['id'] for item in source_rows if item.get('identity')}
    selected.update(applied_sources or [])
    unknown = selected - set(sources)
    if unknown:
        raise ValueError('selected authoring sources were not acquired: ' + ', '.join(sorted(unknown)))
    if operation == 'compose' and not initial:
        criteria, allowances, required_sources = _protected(task, protected_criteria)
        selected.update(required_sources)
        current_task = authoring.seed(route=route or task['route'], artifact=artifact or task['artifact'],
            execution=execution or task['execution'], task_id=task['task_id'], features=features)
        current_task['production_id'] = task['production_id']
        current_task['criteria'] = criteria
        current_task['direction']['source_allowances'] = allowances
        current_task['direction']['basis'] = sorted(required_sources)
        current = {'target': None, 'reading': {'reading_key': None}, 'visual': None,
                   'validation': None, 'task_changes': {}, 'external': None,
                   'authoring': authoring.blank(current_task)}
        if current_task['execution'] == 'external':
            import production_external_inputs
            current['external'] = production_external_inputs.template()
    else:
        current, current_task = copy.deepcopy(choices), copy.deepcopy(task)
        for key, value in {'route': route, 'artifact': artifact, 'execution': execution,
                           'features': features}.items():
            if value is not None:
                current_task[key] = copy.deepcopy(value)
                current['authoring']['task'][key] = copy.deepcopy(value)
    applications, subjects, selected_requirements = _applications(sources, selected)
    if prior_basis is not None and operation == 'amend':
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
    requirements = list(dict.fromkeys(selected_requirements))
    if operation == 'compose' and not initial and current_task['criteria']:
        source = 'protected-requirements:' + c.content_id(current_task['criteria'])
        _retain_acquisition(sources, source, authoring_work.acquire_source(c.encoded(current_task['criteria']),
            format='json', origin={'kind': 'protected-requirements', 'task_id': task['task_id']}))
        for index in range(len(current_task['criteria'])):
            ident = 'protected-requirement:' + str(index + 1)
            applications[ident] = {'source': source, 'pointer': '/' + str(index)}
            requirements.append(ident)
    elif prior_basis is not None and operation == 'amend':
        requirements = list(dict.fromkeys([*prior_basis['requirements'], *requirements]))
    work = authoring_work.begin_work(operation=operation, request=request, sources=sources,
        applications=applications, subjects=subjects, requirements=requirements,
        baseline=None if initial else previous, content=current if operation == 'compose' else None,
        focus=focus or (prior_basis or {}).get('focus', 'character'))
    if operation == 'amend':
        work = authoring_work.replace_content(work, current)
    if operation == 'compose' and not initial and prior_basis is not None:
        applications = copy.deepcopy(work['basis']['applications'])
        subjects = copy.deepcopy(work['basis']['subjects'])
        sources = copy.deepcopy(work['basis']['sources'])
        for subject, selected_apps in prior_basis['subjects'].items():
            for key in selected_apps:
                applications[key] = copy.deepcopy(prior_basis['applications'][key])
                record = sources[applications[key]['source']]
                if (record.get('origin') or {}).get('kind') == 'task-subject':
                    record['origin']['kind'] = 'retained-definition'
            subjects[subject] = list(selected_apps)
        work['basis'] = authoring_work.revise_basis(work['basis'], sources=sources,
                                                  applications=applications, subjects=subjects)
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
        origin = {'kind': 'studio-source', 'source': copy.deepcopy(row)}
        if row.get('definition_owner') is not None:
            origin.update(kind='task-subject', subject_id=row['definition_owner']['subject_id'])
        record = authoring_work.acquire_source(raw, format=_format(path, raw), origin=origin)
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


def unresolved(basis: dict, choices: dict, *, require_subject: bool = False) -> list[dict]:
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
    return [{'field': 'authoring_work' + item['path'], 'code': 'AUTHORING_WORK_INCOMPLETE',
             'phase': 'authoring', 'message': item['message'],
             'required_action': 'Complete the named current request or source application in work-basis.json.',
             'guidance': {'document_path': 'references/runtime/authoring-work.md'}}
            for item in report['errors']]


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
    criteria = {item['id']: item for item in task['criteria']}
    for application in basis['requirements']:
        selection = basis['applications'][application]
        record = basis['sources'][selection['source']]
        if (record.get('origin') or {}).get('kind') == 'protected-requirements':
            value = authoring_work.source_value(record, selection['pointer'])
            if not isinstance(value, dict) or criteria.get(value.get('id')) != value:
                mismatch('A protected requirement differs from its actual task criterion.',
                         pointer='$.criteria', application=application)
    return {'basis': task['work_basis'], 'content_sha256': authoring_work.digest(resolved['content']),
            'sources': sorted(actual), 'subjects': sorted(basis['subjects'])}
