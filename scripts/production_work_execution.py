"""Bind one execution answer to separate direction and submission records."""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c


def draft(root: Path, run: str) -> dict:
    import production_execution as execution
    import production_operations as operations
    import production_store as store
    value = execution.draft_execution(root, run)
    choices = value['choices']
    loaded = operations.read_run(root, run)
    held = store.read_authority(root, loaded.prepared['task']['task_id'])
    requirements = value['authorization_requirements']['requirements']
    available = {row['operation']: [item['grant'] for item in row['candidates'] if item['eligible']]
                 for row in requirements}
    missing = [operation for operation, grants in available.items() if not grants]
    ambiguous = {operation: grants for operation, grants in available.items() if len(grants) > 1}
    result = {'reason': '', 'stop_assessments': copy.deepcopy(choices['shared_stop_assessments'])}
    request = next((row['request_decision'] for row in choices['decisions'] if 'request_decision' in row), None)
    if request is not None:
        result['request_decision'] = copy.deepcopy(request)
    if missing:
        result['approval'] = {'evidence': {'path': None, 'locator': 'whole'},
                              'actor': None, 'mode': None}
    if ambiguous:
        result['grant_choices'] = {operation: None for operation in ambiguous}
    selected = {identifier for identifiers in available.values() for identifier in identifiers}
    grants = {row['id']: row for row in held.document['grants']}
    options = {operation: [{'number': number, 'grant': identifier,
        **{key: copy.deepcopy(grants[identifier][key]) for key in
           ('actor', 'mode', 'targets', 'scope_cases', 'protected_criteria', 'expires_at') if key in grants[identifier]}}
        for number, identifier in enumerate(identifiers, 1)] for operation, identifiers in ambiguous.items()}
    from route_reading import operation_reading_action
    from cli_invocation import python_argv
    return {'choices': result, 'binding': {'run': run, 'input_sha256': loaded.prepared['input_sha256'],
                'authority': held.event['sha256'], 'decisions': choices,
                'missing_operations': missing, 'grant_options': ambiguous,
                'issuer': held.document['issuer'],
                'grant_terms': {row['id']: copy.deepcopy(row) for row in held.document['grants'] if row['id'] in selected},
                'stop_conditions': copy.deepcopy(held.document['stop_conditions'])},
            'reading_action': operation_reading_action(root, run, operation='execute', loaded=loaded),
            'input_action': {'command': 'workspace', 'argv': python_argv(
                Path(__file__).with_name('production_workflow.py'), 'workspace', '--root', str(root),
                '--run', run, '--phase', 'input'),
                'reason': 'Read the exact retained request and its supplied media before judging it.'},
            'requirements': value['authorization_requirements'],
            **({'grant_options': options} if options else {}),
            'stop_conditions': copy.deepcopy(held.document['stop_conditions']),
            'instructions': 'Assess the exact saved request and its rendition. State the actual authorization reason once. '
                'When approval is present, select the real instruction and actual actor/mode once for the prepared '
                'direction and submission. Choose a displayed grant number only where several are eligible. '
                'The runtime derives separate authorization records and adds only missing grants.'}


def _write(directory: Path, label: str, value: dict) -> Path:
    path = directory / (label + '-' + c.content_id(value) + '.json')
    if not path.exists():
        c.atomic(path, c.encoded(value))
    return path


def _selected(answers: dict, binding: dict) -> dict:
    selected = {row['operation']: row['grant'] for row in binding['decisions']['decisions']
                if row['grant'] is not None}
    options = binding['grant_options']
    if options:
        supplied = answers.get('grant_choices')
        c.exact(supplied, set(options), 'execution grant choices')
        for operation, identifiers in options.items():
            number = supplied[operation]
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(identifiers):
                raise ValueError('Choose one displayed grant number for ' + operation + '.')
            selected[operation] = identifiers[number - 1]
    return selected


def apply(root: Path, directory: Path, answers: dict, *, binding: dict) -> dict:
    import production_authority_drafts as authority_drafts
    import production_execution as execution
    import production_operations as operations
    import production_store as store
    directory.mkdir(parents=True, exist_ok=True)
    loaded = operations.read_run(root, binding['run'])
    if loaded.prepared['input_sha256'] != binding['input_sha256']:
        raise ValueError('Execution answers belong to another saved input.')
    if any(row['event'] in {'dispatch-claim', 'external-claim'} for row in loaded.rows):
        return execution.resume(root, binding['run'])
    c.text(answers.get('reason'), 'execution reason')
    expected = {'reason', 'stop_assessments'}
    if any('request_decision' in row for row in binding['decisions']['decisions']):
        expected.add('request_decision')
    missing = binding['missing_operations']
    if missing:
        expected.add('approval')
    if binding['grant_options']:
        expected.add('grant_choices')
    c.exact(answers, expected, 'execution answers')
    selected = _selected(answers, binding)
    held = store.read_authority(root, loaded.prepared['task']['task_id'])
    current = {row['id']: row for row in held.document['grants']}
    if (held.document['issuer'] != binding['issuer']
            or held.document['stop_conditions'] != binding['stop_conditions']
            or any(current.get(identifier) != binding['grant_terms'][identifier] for identifier in selected.values())):
        raise ValueError('The selected authority terms changed; refresh and assess the current execution answer.')
    imported = directory / 'authority.json'
    if missing and not imported.exists():
        approval = answers['approval']
        c.exact(approval, {'evidence', 'actor', 'mode'}, 'execution approval')
        c.exact(approval['evidence'], {'path', 'locator'}, 'execution approval evidence')
        c.text(approval['actor'], 'approval actor')
        c.text(approval['evidence']['path'], 'approval evidence path')
        c.text(approval['evidence']['locator'], 'approval evidence locator')
        if approval['mode'] not in {'direct', 'delegated'}:
            raise ValueError('Approval mode must be direct or delegated, as the actual instruction permits.')
        pending = directory / 'authority-pending.json'
        if pending.exists():
            previous = c.load(pending)
            supplied = c.load(c.local(root, previous['input']))
            current = authority_drafts.current_update(held)
            if current is not None and c.encoded(current) == c.encoded(supplied):
                c.atomic(imported, c.encoded({'input': previous['input'], 'recovered': True}))
            elif held.event['sha256'] != binding['authority']:
                raise ValueError('Current authority changed; inspect the current grants and refresh this execution answer.')
        elif held.event['sha256'] != binding['authority']:
            raise ValueError('Current authority changed; inspect the current grants and refresh this execution answer.')
        if imported.exists():
            return _execute_bound(root, directory, answers, binding)
        update = authority_drafts.draft_authority_update(root, binding['run'], approval['evidence']['path'])
        value = update['choices']
        value['grants'] = [grant for grant in value['grants'] if grant['operation'] in missing]
        value['evidence']['locator'] = approval['evidence']['locator']
        for grant in value['grants']:
            grant.update(actor=approval['actor'], mode=approval['mode'], reason=answers['reason'])
            if grant['operation'] == 'submit':
                grant['submission_validation_modes'] = [update['required_validation_mode']]
        path = _write(directory, 'authority-input', value)
        if not pending.exists():
            c.atomic(pending, c.encoded({'input': path.relative_to(root).as_posix()}))
        receipt = store.import_authority(root, path.relative_to(root).as_posix(),
                                         expected=value['expected_event'], report_changes=True)
        c.atomic(imported, c.encoded({'input': path.relative_to(root).as_posix(), 'result': receipt}))
    return _execute_bound(root, directory, answers, binding)


def _execute_bound(root: Path, directory: Path, answers: dict, binding: dict) -> dict:
    import production_execution as execution
    import production_operations as operations
    import production_store as store
    loaded = operations.read_run(root, binding['run'])
    held = store.read_authority(root, loaded.prepared['task']['task_id'])

    value = execution.draft_execution(root, binding['run'])['choices']
    if held.document['stop_conditions'] != binding['stop_conditions']:
        raise ValueError('The execution stop conditions changed; refresh and assess the current conditions.')
    value['shared_stop_assessments'] = copy.deepcopy(answers['stop_assessments'])
    selected = _selected(answers, binding)
    pending = directory / 'authority-pending.json'
    if pending.exists():
        original = c.load(c.local(root, c.load(pending)['input']))
        selected.update({row['operation']: row['id'] for row in original['grants']})
    for decision in value['decisions']:
        if decision['operation'] in selected:
            decision['grant'] = selected[decision['operation']]
        if decision['grant'] is None:
            raise ValueError('The current grants require an explicit selection; inspect the authorization requirements.')
        decision['reason'] = answers['reason']
        if 'request_decision' in decision:
            decision['request_decision'] = copy.deepcopy(answers['request_decision'])
            chosen = decision['request_decision']
            approval = answers.get('approval')
            if (approval and approval['mode'] == 'direct'
                    and 'principal_approval' in chosen and chosen['principal_approval'] is None
                    and chosen.get('case') is None):
                chosen['principal_approval'] = copy.deepcopy(approval['evidence'])
    path = _write(directory, 'execution', value)
    return execution.execute(root, binding['run'], decisions_file=path.relative_to(root).as_posix())
