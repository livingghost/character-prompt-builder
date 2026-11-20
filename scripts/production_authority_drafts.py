"""Draft run-bound authority choices and retain literal principal instructions.

The drafts carry derived identities and unanswered decisions. Import compiles
additional grants against the observed current authority; it never replaces an
issuer or changes an existing grant. The host still evaluates the actual
instruction and permission. Local hashes identify bytes, not their author.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import execution_contract as c
import read_context
from input_evidence import EvidenceAcquisition
from production_diagnostics import ProductionError

APPROVAL_TYPE = 'production-principal-approval'
UPDATE_TYPE = 'production-authority-update'
APPROVAL_SCHEMA = 'schemas/authoring/production-principal-approval.schema.json'
UPDATE_SCHEMA = 'schemas/authoring/production-authority-update.schema.json'


def validate_shape(document: Any, *, kind: str) -> dict:
    """Inspect a draft's fields without approving its instruction or importing it."""
    from state_protocol import read_schema, validate_against_schema
    schema_path = {APPROVAL_TYPE: APPROVAL_SCHEMA, UPDATE_TYPE: UPDATE_SCHEMA}[kind]
    errors = validate_against_schema(document, read_schema(Path(__file__).resolve().parents[1] / schema_path))
    return {'ok': not errors, 'errors': errors, 'schema': schema_path,
            'validation_scope': 'document-shape'}


def validate_principal_shape(document: Any) -> dict:
    return validate_shape(document, kind=APPROVAL_TYPE)


def validate_update_shape(document: Any) -> dict:
    return validate_shape(document, kind=UPDATE_TYPE)


def _shape(document: Any, kind: str, *, file: str | None = None) -> None:
    report = validate_shape(document, kind=kind)
    if not report['ok']:
        raise ProductionError('INPUT_SCHEMA_INVALID', '; '.join(report['errors']),
            phase='authority-evidence', file=file,
            required_action='Correct the fields named in ' + report['schema'] + '; retain the derived run binding.')


def _match(expected: Any, actual: Any, *, pointer: str, file: str | None = None,
           message: str = 'The authority draft no longer matches its prepared run or current issuer.') -> None:
    if c.encoded(expected) != c.encoded(actual):
        raise ProductionError('AUTHORIZATION_MISMATCH', message, phase='authority-evidence', file=file,
            pointer=pointer, expected=expected, actual=actual,
            required_action='Inspect the selected run and current authority. Draft the matching evidence or update '
                            'again, and carry forward only decisions the actual instruction still supports.')


def request_binding(prepared: dict, payload: dict) -> dict:
    """Project exact dispatcher input and transported reference identities from owned values."""
    sealed = payload['request_contract']['sealed']
    return {'task_id': prepared['task']['task_id'], 'run': prepared['run'],
            'input_sha256': prepared['input_sha256'], 'request_sha256': payload['request_sha256'],
            'target': copy.deepcopy(sealed['target']),
            'references': {'bindings': copy.deepcopy(sealed['bindings']),
                           'media': copy.deepcopy(sealed['media'])}}


def _dispatcher_payload(loaded) -> dict:
    if loaded.prepared['task']['execution'] != 'dispatcher':
        raise ProductionError('EXECUTION_NOT_APPLICABLE',
            'Principal approval is an exact dispatcher request decision.', phase='authorization',
            run=loaded.prepared['run'],
            required_action='For an external request, use its direction and submission decisions from draft-execution. '
                            'Select a dispatcher run for draft-principal-approval.')
    return next(item['payload'] for item in loaded.artifacts['execution-plan.json']['operations']
                if item['operation'] == 'submit')


def _instruction(raw: bytes, path: str) -> str:
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ProductionError('INPUT_SCHEMA_INVALID', 'The actual instruction file must contain valid UTF-8.',
            phase='authority-evidence', file=path,
            required_action='Provide the actual instruction as UTF-8 without replacing undecodable bytes.') from exc
    if not text.strip('\ufeff \t\r\n'):
        raise ProductionError('AUTHORIZATION_REQUIRED', 'No actual instruction is present in the selected file.',
            phase='authority-evidence', file=path,
            required_action='Select a nonempty file containing the actual instruction. A draft cannot supply consent.')
    return text


@read_context.operation
def draft_principal_approval(root: Path, run: str, instruction_file: str, actor: str) -> dict:
    """Retain exact UTF-8 instruction bytes while leaving approval and scope unanswered."""
    import production_decisions
    import production_store as store
    from production_binding import studio_file
    loaded = production_decisions.context(root, run)
    payload = _dispatcher_payload(loaded)
    held = store.read_authority(root, loaded.prepared['task']['task_id'])
    c.text(actor, 'actual instruction actor')
    _match(held.document['issuer'], actor, pointer='$.actor',
           message='A principal instruction must name the current authority issuer.')
    source = studio_file(root, instruction_file, option='--instruction-file')
    raw = store.stable_read(source, instruction_file)
    text = _instruction(raw, instruction_file)
    choices = {'artifact_type': APPROVAL_TYPE, 'binding': request_binding(loaded.prepared, payload),
               'actor': actor, 'instruction': {'path': instruction_file, 'sha256': c.digest(raw),
                   'encoding': 'utf-8', 'text': text}, 'approval': {'approved': None, 'scope': ''}}
    _shape(choices, APPROVAL_TYPE)
    return {'choices': choices, 'state': 'unapproved', 'schema': APPROVAL_SCHEMA,
            'unanswered': ['$.approval.approved', '$.approval.scope'],
            'required_action': 'Read the actual instruction and exact prepared input. Set approval.approved and '
                'describe its scope only when that instruction approves this request. Select the saved file with '
                'locator whole as principal_approval in the execution decisions.',
            'limit': 'The retained text is literal source evidence. Drafting does not approve the request, '
                     'authenticate its speaker, import authority or send anything.'}


def principal_document(raw: bytes) -> dict | None:
    """Recognize the explicit structured draft while leaving ordinary evidence in its own format."""
    try:
        value = c.decode(raw)
    except (UnicodeDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) and value.get('artifact_type') == APPROVAL_TYPE else None


def validate_principal_approval(document: dict, prepared: dict, payload: dict, issuer: str, *,
                                file: str | None = None, require_approval: bool = True) -> None:
    """Check the draft's literal evidence and binding without judging the words' meaning."""
    _shape(document, APPROVAL_TYPE, file=file)
    _match(request_binding(prepared, payload), document['binding'], pointer='$.binding', file=file)
    _match(issuer, document['actor'], pointer='$.actor', file=file,
           message='The selected principal instruction names a different authority issuer.')
    instruction = document['instruction']
    raw = instruction['text'].encode('utf-8')
    _instruction(raw, instruction['path'])
    _match(c.digest(raw), instruction['sha256'], pointer='$.instruction.sha256', file=file,
           message='The retained instruction text differs from the bytes its digest identifies.')
    if require_approval and (document['approval']['approved'] is not True
                             or not document['approval']['scope'].strip()):
        raise ProductionError('AUTHORIZATION_REQUIRED', 'The selected principal approval is unanswered or declined.',
            phase='authority-evidence', file=file, pointer='$.approval',
            required_action='Assess the actual instruction and its scope. Complete this approval only if it authorizes '
                            'the exact prepared request; otherwise retain it as unapproved evidence.')


def check_approval_evidence(root: Path, raw: bytes, *, task_id: str, issuer: str, file: str,
                            loaded=None, require_approval: bool = True) -> dict | None:
    """Validate a selected structured approval against its owned run, leaving other evidence opaque."""
    document = principal_document(raw)
    if document is None:
        return None
    _shape(document, APPROVAL_TYPE, file=file)
    if loaded is None:
        import production_decisions
        loaded = production_decisions.context(root, document['binding']['run'])
    _match(loaded.prepared['task']['task_id'], task_id, pointer='$.binding.task_id', file=file)
    validate_principal_approval(document, loaded.prepared, _dispatcher_payload(loaded), issuer,
                                file=file, require_approval=require_approval)
    return document


def _update_binding(loaded, held) -> dict:
    return {'task_id': loaded.prepared['task']['task_id'], 'issuer': held.document['issuer'],
            'run': loaded.prepared['run'], 'input_sha256': loaded.prepared['input_sha256'],
            'request_sha256': loaded.artifacts['execution-plan.json']['request_sha256'],
            'expected_event': held.event['sha256']}


def _validation_mode(loaded) -> str:
    if loaded.prepared['task']['execution'] == 'dispatcher':
        return _dispatcher_payload(loaded)['request_validation']['mode']
    return loaded.consumer['image_input']['external_request']['schema_validation']['mode']


def _update_scope(root: Path, run: str, phase: str, candidate: str | None):
    """Acquire the selected operation from its owner without supplying its judgments."""
    import production_decisions
    import production_operations as workflow
    if phase not in {'execution', 'selection'}:
        raise ProductionError('INPUT_SCHEMA_INVALID', 'Authority drafting needs a known operation phase.',
            phase='authority-evidence', actual=phase, expected=['execution', 'selection'],
            required_action='Choose --phase execution for direction/submission, or --phase selection with --candidate ID.')
    if phase == 'execution':
        if candidate is not None:
            raise ProductionError('INPUT_SCHEMA_INVALID', 'A candidate belongs to the explicit selection phase.',
                phase='authority-evidence', candidate=candidate,
                required_action='Use --phase selection --candidate ID for authority to select a reviewed result.')
        loaded = production_decisions.context(root, run)
        return loaded, loaded.artifacts['execution-plan.json']['operations'], None, None
    if not candidate:
        raise ProductionError('INPUT_SCHEMA_INVALID', 'Selection authority needs an explicitly named candidate.',
            phase='authority-evidence', run=run,
            required_action='Inspect status --run and supply --phase selection --candidate ID for the intended reviewed result.')
    # Selection uses retained result evidence, just as authorization_context does;
    # a generation runtime is not required to judge an already captured image.
    loaded = workflow.read_run(root, run)
    selection = workflow.draft_selection(root, run, candidate)
    reviewed = workflow.find(loaded.rows, 'review', selection['review'])
    requirements = workflow.selection_requirements(loaded.prepared, reviewed)
    if requirements['unassessed_hard_criteria']:
        raise ProductionError('REVIEW_INCOMPLETE', 'Required criteria have not been assessed: ' +
            ', '.join(requirements['unassessed_hard_criteria']), phase='selection', run=run, candidate=candidate,
            required_action='Observe and review each unassessed required criterion before drafting selection authority.')
    binding = {key: selection[key] for key in ('candidate', 'review', 'replaces')}
    return loaded, [workflow.selection_intent(selection)], binding, requirements


def selection_update_action(root: Path, run: str, candidate: str, current) -> dict:
    """Navigate from an inspected candidate to unanswered select authority choices."""
    from cli_invocation import python_argv
    identity = c.content_id({'candidate': candidate, 'authority': current.event['sha256']})[:24]
    stem = f'production/authority-updates/{run}/selection-{identity}'
    out, number = stem + '.json', 2
    while c.local(root, out, exists=False).exists():
        out, number = stem + '-' + str(number) + '.json', number + 1
    return {'command': 'draft-authority-update',
        'argv': python_argv(Path(__file__).with_name('production_workflow.py'), 'draft-authority-update',
            '--root', str(root), '--run', run, '--phase', 'selection', '--candidate', candidate, '--out', out),
        'draft': out, 'requires_author_input': True,
        'reason': 'No current grant covers selection of this reviewed result. Draft select/delivery authority, '
                  'complete it only from the actual instruction, then import it and inspect status for this run. '
                  'The draft supplies no actor, permission, owner acceptance or selection.'}


@read_context.operation
def draft_authority_update(root: Path, run: str, approval_evidence: str | None = None, *,
                           phase: str = 'execution', candidate: str | None = None) -> dict:
    """Draft independent additional grants; current grants and stop definitions stay owned by authority."""
    import production_operations as workflow
    import production_store as store
    loaded, operations, selection, selection_requirements = _update_scope(root, run, phase, candidate)
    held = store.read_authority(root, loaded.prepared['task']['task_id'])
    evidence = {'path': None, 'locator': None, 'sha256': None}
    if approval_evidence is not None:
        inputs = EvidenceAcquisition(root)
        selected = inputs.select(approval_evidence)
        raw = inputs.bytes[selected['path']]
        if not raw.strip():
            raise ProductionError('AUTHORIZATION_REQUIRED', 'The selected approval evidence is empty.',
                phase='authority-evidence', file=approval_evidence,
                required_action='Select the actual nonempty instruction evidence, or leave the draft evidence unanswered.')
        principal = principal_document(raw)
        if principal is not None:
            validate_principal_approval(principal, loaded.prepared, _dispatcher_payload(loaded),
                                        held.document['issuer'], file=approval_evidence, require_approval=False)
        evidence = {**selected, 'locator': 'whole'}
    identifiers = {item['id'] for item in held.document['grants']}
    grants = []
    for intent in operations:
        stem = 'run-' + run + '-' + intent['operation']
        identifier, number = stem, 2
        while identifier in identifiers:
            identifier = stem + '-' + str(number)
            number += 1
        identifiers.add(identifier)
        grants.append({'id': identifier, 'operation': intent['operation'], 'targets': copy.deepcopy(intent['targets']),
                       'actor': None, 'mode': None, 'reason': '', 'protected_criteria': [], 'expires_at': None,
                       'request_scope': None, 'submission_validation_modes': []})
    choices = {'artifact_type': UPDATE_TYPE, **_update_binding(loaded, held), 'evidence': evidence,
               'grants': grants, 'additional_stop_conditions': []}
    if selection is not None:
        choices['selection'] = selection
    _shape(choices, UPDATE_TYPE)
    return {'choices': choices, 'state': 'unapproved', 'schema': UPDATE_SCHEMA, 'phase': phase,
            'authorization_requirements': workflow.authorization_requirements(root, loaded.prepared, held, operations),
            **({'required_validation_mode': _validation_mode(loaded)} if phase == 'execution' else
               {'selection_requirements': selection_requirements}),
            'current_stop_conditions': copy.deepcopy(held.document['stop_conditions']),
            'unanswered': ([] if approval_evidence is not None else ['$.evidence.path', '$.evidence.locator']) +
                [f'$.grants[{index}].{field}' for index in range(len(grants)) for field in ('actor', 'mode', 'reason')] +
                [f'$.grants[{index}].submission_validation_modes' for index, item in enumerate(grants)
                 if item['operation'] == 'submit'],
            'expected_event': held.event['sha256'],
            'required_action': 'Complete only authority supplied by the actual instruction. ' +
                ('Choose each grant\'s protected_criteria using authorization_requirements.protected_criteria: it '
                 'declares unchanged criteria across runs, while task.criteria retains the hard review requirements. '
                 if phase == 'execution' else
                 'This draft covers select/delivery for the named reviewed candidate. A selection decision, its '
                 'stop assessments and any explicit owner allowance remain separate. ') + 'Import this file with '
                'authority-import --expected-event ' + held.event['sha256'] + '. The import checks this same '
                'predecessor and keeps every existing grant; inspect and reconcile any concurrent update.',
            'limit': 'This is an additional-grant draft, not current authority. Issuer, run, targets and predecessor '
                     'are derived. Selection also pins its candidate, latest review and replaced selection. '
                     'Existing grants and stop conditions cannot be edited through this draft.'}


def materialize_update(root: Path, choices: dict, current, inputs: EvidenceAcquisition, *, file: str) -> dict:
    """Compile authored additions under the transaction's current authority and saved run."""
    import production_permissions
    _shape(choices, UPDATE_TYPE, file=file)
    chosen = choices.get('selection')
    loaded, intents, selection, _ = _update_scope(root, choices['run'],
        'selection' if chosen is not None else 'execution', chosen['candidate'] if chosen is not None else None)
    if chosen is not None:
        _match(selection, chosen, pointer='$.selection', file=file,
            message='The candidate, latest review or replaced selection changed after this authority draft.')
    expected = _update_binding(loaded, current)
    _match(expected, {key: choices[key] for key in expected}, pointer='$', file=file)
    evidence = choices['evidence']
    if not evidence['path'] or not evidence['locator']:
        raise ProductionError('AUTHORIZATION_REQUIRED', 'The authority update has no actual instruction evidence.',
            phase='authority-evidence', file=file, pointer='$.evidence',
            required_action='Select the actual instruction evidence path and locator. Drafting cannot grant authority.')
    selected = inputs.select(evidence['path'])
    raw = inputs.bytes[selected['path']]
    if not raw.strip():
        raise ProductionError('AUTHORIZATION_REQUIRED', 'The authority update evidence is empty.',
            phase='authority-evidence', file=evidence['path'],
            required_action='Select nonempty actual instruction evidence before importing additional grants.')
    if evidence['sha256'] is not None:
        _match(evidence['sha256'], selected['sha256'], pointer='$.evidence.sha256', file=file,
               message='The selected instruction evidence changed after the authority draft acquired it.')
    principal = principal_document(raw)
    if principal is not None:
        validate_principal_approval(principal, loaded.prepared, _dispatcher_payload(loaded),
                                   current.document['issuer'], file=evidence['path'])
    _match([{'operation': item['operation'], 'targets': item['targets']} for item in intents],
           [{'operation': item['operation'], 'targets': item['targets']} for item in choices['grants']],
           pointer='$.grants', file=file)
    existing_ids = {item['id'] for item in current.document['grants']}
    additions = []
    for index, choice in enumerate(choices['grants']):
        if choice['id'] in existing_ids:
            raise ProductionError('AUTHORIZATION_MISMATCH', 'An additional grant cannot replace an existing grant id.',
                phase='authority-evidence', file=file, pointer=f'$.grants[{index}].id', actual=choice['id'],
                required_action='Keep the existing grant and select a distinct new id. Use the complete authority '
                                'declaration for an actually authorized replacement or revocation.')
        existing_ids.add(choice['id'])
        for field in ('actor', 'mode', 'reason'):
            if not isinstance(choice[field], str) or not choice[field].strip():
                raise ProductionError('AUTHORIZATION_REQUIRED', 'An additional grant still has an unanswered author choice.',
                    phase='authority-evidence', file=file, pointer=f'$.grants[{index}].{field}',
                    required_action='Complete the actor, direct/delegated mode and permission reason from actual '
                                    'instruction evidence. Derived targets are not permission.')
        grant = {key: copy.deepcopy(value) for key, value in choice.items()
                 if key not in {'operation', 'reason'}}
        grant['operations'] = [choice['operation']]
        if choice['operation'] == 'submit' and _validation_mode(loaded) not in grant['submission_validation_modes']:
            raise ProductionError('GRANT_SCOPE_EXCEEDED', 'The additional submission grant does not allow this validation mode.',
                phase='authorization', file=file, pointer=f'$.grants[{index}].submission_validation_modes',
                expected=_validation_mode(loaded), actual=grant['submission_validation_modes'],
                required_action='Include the prepared request validation mode only when the actual instruction permits it.')
        additions.append(grant)
    added = {'task_id': current.task_id, 'issuer': current.document['issuer'],
             'evidence': {'path': selected['path'], 'locator': evidence['locator']},
             'grants': additions, 'stop_conditions': copy.deepcopy(choices['additional_stop_conditions'])}
    acquired = production_permissions.acquire(added, current.task_id, inputs)
    result = copy.deepcopy(current.document)
    result['evidence'] = acquired['evidence']
    result['grants'].extend(acquired['grants'])
    result['stop_conditions'].extend(acquired['stop_conditions'])
    production_permissions.validate(result, current.task_id)
    return result


def changed_grants(prior: dict | None, current: dict) -> dict:
    """Report the actual grant change without altering the formal authority event."""
    old = {item['id']: item for item in (prior or {}).get('grants', [])}
    new = {item['id']: item for item in current['grants']}
    common = old.keys() & new.keys()
    revoked = {key for key in common if old[key].get('revoked_at') is None
               and new[key].get('revoked_at') is not None}
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'revoked': sorted(revoked),
            'updated': sorted(key for key in common - revoked if c.encoded(old[key]) != c.encoded(new[key]))}
