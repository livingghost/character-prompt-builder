"""Accept one existing Production image in its Studio slot, with recoverable evidence.

The author supplies decisions once. The run supplies its candidate, review,
authority, destination and immutable evidence. Selection is the durable intent;
the Studio owns its acceptance history and the run records the verified result.
No task, generation, candidate, review or iteration is created here.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError, compare_exact


def slot_state(root: Path, character: str, slot: str) -> dict | None:
    """The current recorded slot receipt used to guard an interrupted replacement."""
    import studio
    return studio.acceptance_state(root, character, slot)


def _target(root: Path, run: str, candidate: str, *, loaded: tuple | None = None) -> tuple[dict, dict]:
    import production_workflow as workflow
    import studio
    loaded = loaded or workflow.load_run(root, run)
    _, prepared, _, rows = loaded
    chosen = workflow.find(rows, 'candidate', candidate)
    recording = prepared['task'].get('recording')
    if prepared['task']['artifact'] != 'image' or not recording:
        raise ProductionError('SLOT_ACCEPTANCE_NOT_APPLICABLE',
            'Slot acceptance needs an image run with its existing Studio recording.',
            phase='acceptance', run=run, candidate=candidate,
            required_action='Use ordinary selection for a delivery without a Studio slot.')
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
                              phase='acceptance', run=run, file=result['path'], expected=expected, actual=actual)
    return target, row


def validate_slot(root: Path, run: str, candidate: str, slot: dict, *, loaded: tuple | None = None) -> dict:
    """Verify a formal selection's exact existing destination and return its iteration."""
    target, row = _target(root, run, candidate, loaded=loaded)
    compare_exact(target, slot, phase='acceptance', pointer='$.slot')
    return row


def draft(root: Path, run: str, candidate: str, grant: str) -> dict:
    """Pin the existing candidate and prior slot state without supplying a judgment."""
    import production_workflow as workflow
    loaded = workflow.load_run(root, run)
    _, prepared, _, rows = loaded
    workflow.require_mutable(rows)
    workflow.require_open_task(rows, run)
    reviewed = workflow.latest_review(rows, candidate)
    target, _ = _target(root, run, candidate, loaded=loaded)
    workflow.assert_authority_current(root, prepared)
    matches = [item for item in prepared['authority']['grants'] if item['id'] == grant]
    if len(matches) != 1:
        raise ValueError('unknown grant id')
    return {'run': run, 'input_sha256': prepared['input_sha256'], 'candidate': candidate,
            'review': reviewed['sha256'], 'expected_slot': slot_state(root, target['character'], target['slot']),
            'grant': grant, 'reason': '',
            'stop_assessments': [{'id': item['id'], 'clear': False, 'evidence': ''}
                                 for item in prepared['authority']['stop_conditions']],
            'owner_acceptance': None}


def _expand(root: Path, run: str, decisions: dict, loaded: tuple) -> tuple[dict, dict]:
    """Derive the exact selection and authorization from explicitly authored choices."""
    import production_workflow as workflow
    workflow.schema_check(decisions, 'acceptance')
    _, prepared, _, rows = loaded
    reviewed = workflow.latest_review(rows, decisions['candidate'])
    compare_exact({'run': run, 'input_sha256': prepared['input_sha256'], 'review': reviewed['sha256']},
                  {key: decisions[key] for key in ('run', 'input_sha256', 'review')}, phase='acceptance')
    target, _ = _target(root, run, decisions['candidate'], loaded=loaded)
    current = slot_state(root, target['character'], target['slot'])
    if decisions['expected_slot'] != current:
        raise ProductionError('SLOT_ACCEPTANCE_CONFLICT', 'The slot changed after this acceptance decision was drafted.',
            phase='acceptance', run=run, expected=decisions['expected_slot'], actual=current,
            required_action='Inspect the current slot and draft a new decision if this replacement is still intended.')
    workflow.assert_authority_current(root, prepared)
    grants = [item for item in prepared['authority']['grants'] if item['id'] == decisions['grant']]
    if len(grants) != 1:
        raise ProductionError('GRANT_REVOKED', 'The selected grant is not current.', phase='authorization', run=run)
    allowance = decisions['owner_acceptance']
    if allowance is not None:
        source = allowance['evidence']
        raw = store.stable_bytes(root, source['path'])
        allowance = {**copy.deepcopy(allowance), 'principal': prepared['authority']['issuer'],
                     'evidence': {**source, 'sha256': c.digest(raw)}}
    selection = {'input_sha256': prepared['input_sha256'], 'candidate': decisions['candidate'],
                 'review': decisions['review'], 'selector': grants[0]['actor'], 'reason': decisions['reason'],
                 'scope': 'studio-slot', 'adoption': None, 'slot': target,
                 'owner_acceptance': allowance, 'authorization': ''}
    request = workflow.draft_authorization(root, run, decisions['grant'], workflow.selection_intent(selection))
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
        rows = workflow.load_run(root, run)[3]
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


def accept(root: Path, run: str, *, decision_file: str | None = None) -> dict:
    """Select, accept and complete the original run, or recover its exact committed intent."""
    import production_workflow as workflow
    import studio
    import work_ledger
    from cli_invocation import python_argv, shown
    with c.lock(root):
        loaded = workflow.load_run(root, run)
        directory, prepared, _, rows = loaded
        selections = [row for row in rows if row['event'] == 'selection']
        selected = selections[-1] if selections else None
        if decision_file is not None:
            raw = store.stable_bytes(root, decision_file)
            prior = [row for row in selections if any(item['sha256'] == c.digest(raw)
                     for item in row['data'].get('files', []))]
            if prior:
                if selected['sha256'] != prior[-1]['sha256']:
                    raise ProductionError('SELECTION_REPLACED', 'A newer selection replaced this acceptance decision.',
                                          phase='acceptance', run=run)
                selected = prior[-1]
            else:
                with store.transaction(root):
                    loaded = workflow.load_run(root, run)
                    directory, prepared, _, rows = loaded
                    workflow.require_mutable(rows)
                    workflow.require_open_task(rows, run)
                    selection, request = _expand(root, run, c.decode(raw), loaded)
                    authorization = workflow.authorize_value(root, run, request, evidence_files=[decision_file],
                                                             expected_source=(decision_file, c.digest(raw)))
                    selection['authorization'] = authorization['sha256']
                    item = {'path': decision_file, 'sha256': c.object_store(directory, raw), 'size': len(raw)}
                    selected = workflow.select_value(root, run, selection, files=[item])
        if selected is None or selected['data']['selection']['scope'] != 'studio-slot':
            raise ProductionError('SLOT_SELECTION_REQUIRED', 'Accept needs an exact studio-slot selection.',
                phase='acceptance', run=run,
                required_action='Draft the actual choices with draft-acceptance and supply the completed file.')
        directory, prepared, _, rows = workflow.load_run(root, run)
        current, chosen, _ = workflow.current_selection(prepared, rows)
        if current['sha256'] != selected['sha256']:
            raise ProductionError('SELECTION_REPLACED', 'The acceptance decision is no longer the current selection.',
                                  phase='acceptance', run=run)
        completed = [row for row in rows if row['event'] == 'completion']
        studio_result = {}
        if completed:
            result = verify_slot(root, run, selected, rows=rows)
            done = workflow.verify_completion(root, run, prepared['task']['task_id'])
        else:
            workflow.require_open_task(rows, run)
            target = chosen['slot']
            studio_result = studio.accept(root, target['character'], target['iteration_id'],
                                          production_selection=selected['sha256'])
            data = _receipt(root, run, selected, require_current=True)
            directory, prepared, _, rows = workflow.load_run(root, run)
            result = workflow.append_record(directory, prepared, rows, 'slot-acceptance', data)
            done = workflow.complete(root, run)
        answer = {'ok': True, 'run': run, 'selection': selected['sha256'],
                  'slot_acceptance': result['sha256'], 'completion': done['sha256'], 'slot': chosen['slot'],
                  'task_id': prepared['task']['task_id'],
                  'finish_command': shown(python_argv(work_ledger.SCRIPT, 'finish', '--studio', str(root.resolve()), '--run', run))}
        warnings = [item['projection_warning'] for item in (selected, studio_result, done) if item.get('projection_warning')]
        if warnings:
            answer['projection_warnings'] = warnings
        return answer
