"""Select and complete an existing reviewed result, with recoverable evidence.

The author supplies decisions once. The run supplies its candidate, review,
authority, destination and immutable evidence. Selection is the durable intent;
the requested scope decides which existing owner records its verified result.
No task, generation, candidate, review or iteration is created here.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_permissions as permissions
import production_store as store
import runtime_snapshot
from production_diagnostics import ProductionError, compare_exact


def slot_state(root: Path, character: str, slot: str) -> dict | None:
    """The current recorded slot receipt used to guard an interrupted replacement."""
    import studio
    return studio.acceptance_state(root, character, slot)


def _target(root: Path, run: str, candidate: str, *, loaded: tuple | None = None) -> tuple[dict, dict]:
    import production_workflow as workflow
    import studio
    loaded = loaded or workflow.read_run(root, run)
    _, prepared, _, rows = loaded
    chosen = workflow.find(rows, 'candidate', candidate)
    recording = prepared['task'].get('recording')
    if prepared['task']['artifact'] != 'image' or not recording:
        raise ProductionError('SLOT_ACCEPTANCE_NOT_APPLICABLE',
            'Slot acceptance needs an image run with its existing Studio recording.',
            phase='acceptance', run=run, candidate=candidate,
            required_action='Use draft-acceptance --scope delivery-only for delivery without a Studio slot.')
    home = studio.character_home(root, recording['character'])
    origin = {'run': run, 'candidate': candidate}
    matches = [row for row in studio.read_iterations(home, project=False) if row.get('production') == origin]
    if len(matches) != 1:
        raise ProductionError('STUDIO_CANDIDATE_REQUIRED',
            'The exact Production candidate needs its one existing Studio iteration.',
            phase='acceptance', run=run, candidate=candidate,
            required_action='Resume the existing run to recover its recorded candidate; do not import its image again.')
    row = matches[0]
    target = {'character': recording['character'], 'iteration_id': row['iteration_id'], 'slot': recording['slot']}
    if row.get('character') != target['character'] or row.get('slot') != target['slot']:
        raise ProductionError('SLOT_ACCEPTANCE_MISMATCH', 'The iteration differs from its prepared recording destination.',
                              phase='acceptance', run=run, expected=target)
    result = row.get('result')
    expected = chosen['data']['files'][0]['sha256']
    if not result or result.get('sha256') != expected:
        raise ProductionError('SLOT_ACCEPTANCE_MISMATCH', 'The iteration differs from its exact Production image.',
                              phase='acceptance', run=run, candidate=candidate, expected=expected)
    actual = c.sha256_file(c.local(root, result['path']))
    if actual != expected:
        raise ProductionError('SLOT_ACCEPTANCE_MISMATCH', 'The recorded Studio image bytes have changed.',
                              phase='acceptance', run=run, file=result['path'], expected=expected, actual=actual,
                              required_action='Copy production/runs/' + run + '/objects/' + expected + ' to ' + result['path']
                                              + '; the run keeps the candidate bytes there.')
    return target, row


def validate_slot(root: Path, run: str, candidate: str, slot: dict, *, loaded: tuple | None = None) -> dict:
    """Verify a formal selection's exact existing destination and return its iteration."""
    target, row = _target(root, run, candidate, loaded=loaded)
    compare_exact(target, slot, phase='acceptance', pointer='$.slot')
    return row


def authority_basis(authority: store.CurrentAuthority, grant: str) -> str:
    """Bind only this grant's terms, source authority and current stop definitions."""
    document = authority.document
    selected = next(item for item in document['grants'] if item['id'] == grant)
    terms = {key: selected.get(key) for key in
             ('id', 'actor', 'mode', 'effective_at', 'expires_at', 'revoked_at')}
    terms.update(operation='select', operation_granted='select' in selected['operations'],
                 targets=['delivery'], delivery_granted='delivery' in selected['targets'])
    declaration = [{key: item[key] for key in ('path', 'locator', 'sha256')}
                   for item in authority.evidence if item['purpose'] == 'authority-declaration']
    return c.content_id({'task_id': authority.task_id, 'issuer': document['issuer'],
                         'grant': terms, 'declaration': declaration,
                         'stop_conditions': sorted(document['stop_conditions'], key=lambda item: item['id'])})


def _grant(authority: store.CurrentAuthority, grant: str | None) -> str:
    requirements = permissions.grant_requirements(authority.document,
        [{'operation': 'select', 'targets': ['delivery']}], grant=grant)
    permissions.require_grants(requirements)
    return requirements['requirements'][0]['selected_grant']


@runtime_snapshot.operation
def draft(root: Path, run: str, candidate: str, grant: str | None = None, *, scope: str = 'delivery-only') -> dict:
    """Pin the retained result and applicable authority without supplying a judgment."""
    import production_workflow as workflow
    loaded = workflow.read_run(root, run)
    _, prepared, _, rows = loaded
    workflow.require_mutable(rows)
    workflow.require_open_task(rows, run)
    reviewed = workflow.latest_review(rows, candidate)
    if scope not in {'delivery-only', 'studio-slot'}:
        raise ValueError('acceptance scope must be delivery-only or studio-slot')
    authority = workflow.current_authority(root, prepared)
    grant = _grant(authority, grant)
    result = {'run': run, 'input_sha256': prepared['input_sha256'], 'candidate': candidate,
            'review': reviewed['sha256'], 'scope': scope,
            'authority_sha256': authority_basis(authority, grant), 'grant': grant, 'reason': '',
            'stop_assessments': [{'id': item['id'], 'clear': False, 'evidence': ''}
                                 for item in authority.document['stop_conditions']],
            'owner_acceptance': None}
    if scope == 'studio-slot':
        target, _ = _target(root, run, candidate, loaded=loaded)
        result['expected_slot'] = slot_state(root, target['character'], target['slot'])
    return result


def _expand(root: Path, run: str, decisions: dict, loaded: tuple) -> tuple[dict, dict]:
    """Derive the exact selection and authorization from explicitly authored choices.

    The selection replaces the run's latest selection in `loaded`, so its
    authorization states which selection it replaces.
    """
    import production_workflow as workflow
    workflow.schema_check(decisions, 'acceptance')
    _, prepared, _, rows = loaded
    compare_exact({'run': run, 'input_sha256': prepared['input_sha256']},
                  {key: decisions[key] for key in ('run', 'input_sha256')}, phase='acceptance')
    reviewed = workflow.latest_review(rows, decisions['candidate'])
    if decisions['review'] != reviewed['sha256']:
        candidate = decisions['candidate']
        raise ProductionError('SELECTION_REVIEW_CHANGED',
            'The decision selects against a review that is no longer the candidate\'s latest.',
            phase='acceptance', run=run, pointer='$.review', expected=reviewed['sha256'], actual=decisions['review'],
            required_action=(f'Read the latest review with production_workflow.py candidate-status --run {run} '
                f'--candidate {candidate}. Draft a decision against it with draft-acceptance --run {run} --candidate '
                f'{candidate} --scope {decisions["scope"]} --grant {decisions["grant"]} --out FILE, keep the '
                'judgments of this decision only where that review still supports them, and apply it with accept '
                f'--run {run} --file FILE.'))
    target = None
    if decisions['scope'] == 'studio-slot':
        target, _ = _target(root, run, decisions['candidate'], loaded=loaded)
        current = slot_state(root, target['character'], target['slot'])
        if decisions['expected_slot'] != current:
            raise ProductionError('SLOT_ACCEPTANCE_CONFLICT', 'The slot changed after this acceptance decision was drafted.',
                phase='acceptance', run=run, expected=decisions['expected_slot'], actual=current,
                required_action='Inspect the current slot and draft a new decision if this replacement is still intended.')
    authority = workflow.current_authority(root, prepared)
    grant = _grant(authority, decisions['grant'])
    current_basis = authority_basis(authority, grant)
    if decisions['authority_sha256'] != current_basis:
        raise ProductionError('ACCEPTANCE_AUTHORITY_CHANGED',
            'The selected grant, source authority or stop conditions changed after this decision was drafted.',
            phase='acceptance', run=run, pointer='$.authority_sha256',
            expected=decisions['authority_sha256'], actual=current_basis,
            required_action='Read the changed authority and draft a new acceptance decision; retain judgments only where their basis still applies.')
    actor = next(item['actor'] for item in authority.document['grants'] if item['id'] == grant)
    allowance = decisions['owner_acceptance']
    if allowance is not None:
        source = allowance['evidence']
        raw = store.stable_bytes(root, source['path'])
        allowance = {**copy.deepcopy(allowance), 'principal': authority.document['issuer'],
                     'evidence': {**source, 'sha256': c.digest(raw)}}
    selection = {'input_sha256': prepared['input_sha256'], 'candidate': decisions['candidate'],
                 'review': decisions['review'], 'selector': actor, 'reason': decisions['reason'],
                 'scope': decisions['scope'], 'adoption': None, 'slot': target,
                 'owner_acceptance': allowance, 'authorization': '',
                 'replaces': workflow.replaced_selection(rows)}
    request = workflow.draft_authorization_from(loaded, authority, decisions['grant'], workflow.selection_intent(selection))
    request['reason'] = decisions['reason']
    request['stop_assessments'] = copy.deepcopy(decisions['stop_assessments'])
    return selection, request


def _receipt(root: Path, run: str, selection: dict, *, require_current: bool) -> dict:
    import studio
    chosen = selection['data']['selection']
    row = validate_slot(root, run, chosen['candidate'], chosen['slot'])
    entries = [item for item in row.get('acceptances', []) if item.get('production_selection') == selection['sha256']]
    if len(entries) != 1:
        if not entries and require_current:
            current = slot_state(root, chosen['slot']['character'], chosen['slot']['slot'])
            if current != selection['data'].get('slot_state'):
                raise ProductionError('SLOT_ACCEPTANCE_CONFLICT', 'The slot changed after this exact selection.',
                    phase='acceptance', run=run, expected=selection['data'].get('slot_state'), actual=current,
                    required_action='Inspect the current slot and record a new explicit selection if replacement is still intended.')
        raise ProductionError('SLOT_ACCEPTANCE_REQUIRED', 'The Studio has no unique receipt of this exact slot acceptance.',
            phase='acceptance', run=run,
            required_action='Resume the same acceptance with production_workflow.py accept --run ' + run + '.')
    receipt = entries[0]
    c.exact(receipt, {'at', 'supersedes', 'production_selection'}, 'Studio acceptance receipt')
    if require_current:
        current = slot_state(root, chosen['slot']['character'], chosen['slot']['slot'])
        expected = {'iteration_id': row['iteration_id'], 'image_sha256': row['result']['sha256'],
                    'acceptance_sha256': c.content_id(receipt)}
        if current != expected:
            raise ProductionError('SLOT_ACCEPTANCE_CONFLICT', 'Another slot acceptance replaced this operation.',
                phase='acceptance', run=run, expected=expected, actual=current,
                required_action='Inspect the newer acceptance; recovery does not replace a later decision.')
        studio.verify_accepted_file(root, row)
    return {'selection': selection['sha256'], 'candidate': chosen['candidate'], 'slot': chosen['slot'],
            'image_sha256': row['result']['sha256'], 'acceptance': receipt}


def verify_slot(root: Path, run: str, selection_receipt: dict, *, rows: list[dict] | None = None,
                require_current: bool = False) -> dict:
    """Verify a committed receipt; later ordinary supersession preserves past completion."""
    import production_workflow as workflow
    if rows is None:
        rows = workflow.read_run(root, run)[3]
    if selection_receipt['data']['selection']['scope'] != 'studio-slot':
        raise ValueError('slot receipt verification needs a studio-slot selection')
    expected = _receipt(root, run, selection_receipt, require_current=require_current)
    results = [row for row in rows if row['event'] == 'slot-acceptance'
               and row['data'].get('selection') == selection_receipt['sha256']]
    if len(results) != 1:
        raise ProductionError('SLOT_ACCEPTANCE_REQUIRED', 'The run has no unique verified slot-acceptance result.',
            phase='acceptance', run=run,
            required_action='Resume the same acceptance with production_workflow.py accept --run ' + run + '.')
    compare_exact(expected, results[0]['data'], phase='acceptance')
    return results[0]


@runtime_snapshot.operation
def accept(root: Path, run: str, *, decision_file: str | None = None) -> dict:
    """Apply or recover one exact reviewed decision and rebuild its views once."""
    import studio_activity as activity
    with activity.operation(root) as projection:
        result = _accept(root, run, decision_file=decision_file)
    return activity.project_result(result, projection)


def _selected(rows: list[dict]) -> dict | None:
    """A completed run retains its established selection when later use changes."""
    selections = [row for row in rows if row['event'] == 'selection']
    completed = [row for row in rows if row['event'] == 'completion']
    if completed:
        identifier = completed[-1]['data'].get('selection')
        return next((row for row in selections if row['sha256'] == identifier), None)
    return selections[-1] if selections else None


def _resumed(rows: list[dict], digest: str) -> dict | None:
    """The run's selection that a decision file with this digest recorded, while it is in force.

    A completed run keeps the selection its completion names. In an open run the
    latest selection is in force until a later disposition of its candidate
    withdraws it or a newer review of its candidate ends it. The same decision
    is then applied as a new decision, as it is after a later selection replaced
    the one it recorded.
    """
    import production_workflow as workflow
    selected = _selected(rows)
    if selected is None or not any(item['sha256'] == digest for item in selected['data']['files']):
        return None
    chosen = selected['data']['selection']
    if not any(row['event'] == 'completion' for row in rows) and (
            workflow.selection_withdrawn(rows, selected)
            or workflow.latest_review(rows, chosen['candidate'])['sha256'] != chosen['review']):
        return None
    return selected


def _accept(root: Path, run: str, *, decision_file: str | None = None) -> dict:
    """Select and complete the requested scope, or recover its exact committed intent.

    A decision file that recorded the selection in force resumes it. Any other
    decision, including one that recorded an earlier selection, is applied as
    a new selection that replaces the run's latest one.
    """
    import production_workflow as workflow
    import studio
    import work_ledger
    loaded = workflow.read_run(root, run)
    directory, prepared, _, rows = loaded
    selected = _selected(rows)
    if decision_file is not None:
        raw = store.stable_bytes(root, decision_file)
        with store.transaction(root):
            loaded = workflow.read_run(root, run)
            directory, prepared, _, rows = loaded
            selected = _resumed(rows, c.digest(raw))
            if selected is None:
                workflow.require_mutable(rows)
                workflow.require_open_task(rows, run)
                selection, request = _expand(root, run, c.decode(raw), loaded)
                authorization = workflow.authorize_value(root, run, request, evidence_files=[decision_file],
                                                         expected_source=(decision_file, c.digest(raw)))
                selection['authorization'] = authorization['sha256']
                item = {'path': decision_file, 'sha256': c.object_store(directory, raw), 'size': len(raw)}
                selected = workflow.select_value(root, run, selection, files=[item])
    if selected is None:
        raise ProductionError('SELECTION_REQUIRED', 'Accept needs an exact reviewed selection.',
            phase='acceptance', run=run,
            required_action='Draft the actual choices with draft-acceptance and supply the completed file.')
    directory, prepared, _, rows = workflow.read_run(root, run)
    current = _selected(rows)
    if current['sha256'] != selected['sha256']:
        action = ('Read the current selection with production_workflow.py status --run ' + run + '. Run accept --run '
                  + run + ' to resume that selection')
        action += (', or accept --run ' + run + ' --file ' + decision_file + ' again to record this decision as a '
                   'new selection that replaces it.' if decision_file is not None else '.')
        raise ProductionError('SELECTION_REPLACED',
            'Another operation recorded a newer selection of this run while this acceptance was applied.',
            phase='acceptance', run=run, expected=selected['sha256'], actual=current['sha256'],
            required_action=action)
    completed = [row for row in rows if row['event'] == 'completion']
    chosen = selected['data']['selection']
    studio_result = {}
    result = None
    if completed:
        done = workflow.verify_completion(root, run, prepared['task']['task_id'])
        if chosen['scope'] == 'studio-slot':
            result = next(row for row in rows if row['event'] == 'slot-acceptance'
                          and row['data']['selection'] == selected['sha256'])
    else:
        workflow.current_selection(prepared, rows)
        workflow.require_open_task(rows, run)
        if chosen['scope'] == 'studio-slot':
            target = chosen['slot']
            studio_result = studio.accept(root, target['character'], target['iteration_id'],
                                          production_selection=selected['sha256'])
            data = _receipt(root, run, selected, require_current=True)
            directory, prepared, _, rows = workflow.read_run(root, run)
            result = workflow.append_record(directory, prepared, rows, 'slot-acceptance', data)
        done = workflow.complete(root, run)
    work = work_ledger.finish_state(root, run)
    answer = {'ok': True, 'run': run, 'selection': selected['sha256'],
              'scope': chosen['scope'], 'completion': done['sha256'],
              'task_id': prepared['task']['task_id'], 'work': work,
              'finish_command': work['finish_command']}
    if result is not None:
        answer.update(slot_acceptance=result['sha256'], slot=chosen['slot'])
    warnings = [item['projection_warning'] for item in (selected, studio_result, done) if item.get('projection_warning')]
    if warnings:
        answer['projection_warnings'] = warnings
    return answer
