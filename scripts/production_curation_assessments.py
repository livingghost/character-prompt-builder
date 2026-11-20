"""Own authored stop judgments and evidenced reuse between selection and adoption.

The selection's formal authorization is the single source of a proposed shared
judgment. Adoption confirms its applicability and may replace complete judgments
for its own operation. The resulting authorization always retains every current
stop assessment; a shared value never supplies an adoption grant or approval.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError


def authority_terms(authority, grant: str, operation: str, scope: str | None = None) -> dict:
    """Project the actual terms used by one curation operation, retaining their text."""
    document = authority.document
    selected = next(item for item in document['grants'] if item['id'] == grant)
    terms = {key: selected.get(key) for key in
             ('id', 'actor', 'mode', 'effective_at', 'expires_at', 'revoked_at')}
    if operation == 'select':
        terms.update(operation='select', operation_granted='select' in selected['operations'],
                     targets=['delivery'], delivery_granted='delivery' in selected['targets'])
    elif operation == 'adopt':
        target = 'canon:' + scope
        terms.update(operation='adopt', operation_granted='adopt' in selected['operations'],
                     target=target, target_granted=target in selected['targets'])
    else:
        raise ValueError('curation assessments belong to select or adopt')
    declaration = [{key: item[key] for key in ('path', 'locator', 'sha256')}
                   for item in authority.evidence if item['purpose'] == 'authority-declaration']
    return {'task_id': authority.task_id, 'issuer': document['issuer'], 'grant': terms,
            'declaration': declaration,
            'stop_conditions': sorted(document['stop_conditions'], key=lambda item: item['id'])}


def unanswered(authority, *, describe: bool = False) -> list[dict]:
    """Show the actual current conditions without judging them."""
    return [{'id': item['id'], **({'condition': item['text']} if describe else {}),
             'clear': False, 'evidence': ''} for item in authority.document['stop_conditions']]


def selection_assessments(authority, values: list[dict]) -> list[dict]:
    """Selection authors the complete judgments that its authorization will retain."""
    return _merge(authority, [], values, describe=False)


def _changed(message: str, *, pointer: str = '$.shared_stop_assessments', **details) -> None:
    raise ProductionError('ADOPTION_DECISION_CHANGED', message, phase='adoption', pointer=pointer,
        required_action='Inspect the current selection, destination, instruction and authority. Use draft-adoption '
            'again; confirm shared assessments only where the retained instruction and current operation support '
            'them, and author the remaining judgments separately.', **details)


def _recorded_authority(root: Path, authority, identifier: str):
    """Acquire the selection's actual authority event and its retained instruction bytes."""
    import production_operations as workflow
    if identifier == authority.event['sha256']:
        return authority
    history = store.read_history(root, 'authority:' + authority.task_id)
    event = workflow.find(history.rows, 'authority-updated', identifier)
    retained = {(item['path'], item['locator'], item['sha256'], item['size'], item['purpose']): item['raw']
                for item in authority.evidence}
    evidence = []
    for item in event['data']['evidence']:
        identity = (item['path'], item['locator'], item['sha256'], item['size'], item['purpose'])
        raw = retained.get(identity)
        if raw is None:
            raw = store.verify_evidence(root, item, event=identifier, impact=store.AUTHORITY_EVIDENCE_IMPACT)
        evidence.append({**item, 'raw': raw})
    return store.CurrentAuthority(authority.task_id, event, tuple(evidence))


def _proposal(root: Path, loaded, authority, value: dict) -> dict | None:
    """Derive a proposal only from this selection's unchanged, fully evidenced judgments."""
    import production_operations as workflow
    selected, choice, _ = workflow.current_selection(loaded.prepared, loaded.rows)
    if selected['sha256'] != value['selection'] or choice['candidate'] != value['candidate'] \
            or choice['review'] != value['review']:
        return None
    # Slot acceptance supplies an exact earlier destination for reuse. A
    # delivery-only selection has made no judgment of a canonical destination.
    destination = {'character': value['character'], 'iteration_id': value['iteration'], 'slot': value['slot']}
    if choice['scope'] != 'studio-slot' or choice['slot'] != destination:
        return None
    authorization = workflow.find(loaded.rows, 'authorization', choice['authorization'])
    request = authorization['data']['request']
    recorded = _recorded_authority(root, authority, authorization['data']['authority']['event'])
    grant = request['grant']
    if not any(item['id'] == grant for item in authority.document['grants']):
        return None
    prior_terms = authority_terms(recorded, grant, 'select')
    current_terms = authority_terms(authority, grant, 'select')
    if c.encoded(prior_terms) != c.encoded(current_terms):
        return None
    # Read back the actual captured instruction, not merely an editable digest.
    # Different authority events can retain the same evidence and select terms.
    instruction = authority.document['evidence']
    previous_instruction = recorded.document['evidence']
    if c.encoded(instruction) != c.encoded(previous_instruction):
        return None
    current_sources = {(item['path'], item['locator'], item['sha256']): item['raw']
                       for item in authority.evidence if item['purpose'] == 'authority-declaration'}
    previous_sources = {(item['path'], item['locator'], item['sha256']): item['raw']
                        for item in recorded.evidence if item['purpose'] == 'authority-declaration'}
    if current_sources != previous_sources:
        return None
    conditions = {item['id']: item['text'] for item in authority.document['stop_conditions']}
    if not conditions:
        return None
    assessments = _merge(authority, [], request['stop_assessments'], describe=False)
    basis = {key: copy.deepcopy(value[key]) for key in ('candidate', 'review', 'selection', 'character',
        'iteration', 'slot', 'image_sha256', 'source_state', 'scope', 'influence', 'registration')}
    basis.update(selection_authority=prior_terms,
                 adoption_authority=authority_terms(authority, value['grant'], 'adopt', value['scope']),
                 instruction_evidence=copy.deepcopy(instruction))
    return {'authorization': authorization['sha256'], 'authority_event': recorded.event['sha256'],
            'basis': basis, 'confirmed': None,
            'assessments': [{**item, 'condition': conditions[item['id']]}
                            for item in sorted(assessments, key=lambda item: item['id'])]}


def adoption_draft(root: Path, loaded, authority, value: dict) -> dict:
    """Offer prior judgments once, with their applicability explicitly unanswered."""
    shared = _proposal(root, loaded, authority, value)
    return {'shared_stop_assessments': shared,
            'additional_stop_assessments': [] if shared is not None else unanswered(authority, describe=True)}


def _merge(authority, shared: list[dict], additional: list[dict], *, describe: bool) -> list[dict]:
    conditions = {item['id']: item['text'] for item in authority.document['stop_conditions']}
    merged = {}
    for title, values in (('shared', shared), ('additional', additional)):
        seen = set()
        for item in values:
            if item['id'] in seen:
                raise ValueError('repeated ' + title + ' stop assessment: ' + item['id'])
            seen.add(item['id'])
            if item['id'] not in conditions or (describe and item['condition'] != conditions[item['id']]):
                if not describe:
                    raise ProductionError('AUTHORIZATION_REQUIRED', 'The selection assessment names an unknown current stop condition.',
                        phase='authorization', pointer='$.stop_assessments', expected=sorted(conditions), actual=item['id'],
                        required_action='Use draft-acceptance for the current selection authority and assess its actual stop conditions.')
                _changed('The authored assessment names a different current stop definition.',
                         pointer='$.additional_stop_assessments', expected=conditions, actual=item)
            merged[item['id']] = {key: copy.deepcopy(item[key]) for key in ('id', 'clear', 'evidence')}
    if set(merged) != set(conditions):
        raise ProductionError('AUTHORIZATION_REQUIRED', 'Every declared stop condition needs an actual current assessment.',
            phase='authorization', pointer='$.additional_stop_assessments' if describe else '$.stop_assessments',
            expected=sorted(conditions), actual=sorted(merged),
            required_action='Assess each missing current condition from actual evidence. A shared proposal must be '
                            'confirmed before it can supply its unchanged judgments.')
    return [merged[item['id']] for item in authority.document['stop_conditions']]


def adoption_assessments(root: Path, loaded, authority, value: dict) -> list[dict]:
    """Validate the immutable selection basis before deriving a full adoption authorization."""
    shared = value['shared_stop_assessments']
    if shared is not None:
        if 'claim' in value:
            _changed('A retained claim reassessment requires actual current judgments of that exact claim.')
        expected = _proposal(root, loaded, authority, value)
        if expected is None or c.encoded({key: shared[key] for key in expected if key != 'confirmed'}) != \
                c.encoded({key: item for key, item in expected.items() if key != 'confirmed'}):
            _changed('The proposed shared judgments no longer match the retained selection, instruction or current adoption basis.')
        if shared['confirmed'] is not True:
            raise ProductionError('AUTHORIZATION_REQUIRED', 'The shared selection judgments have not been confirmed for this adoption.',
                phase='adoption', pointer='$.shared_stop_assessments.confirmed',
                required_action='Read the retained instruction, proposed judgments and exact canonical use. Set confirmed '
                    'to true only when they apply; record any operation-specific replacement as a complete additional_stop_assessments entry.')
    return _merge(authority, shared['assessments'] if shared is not None else [],
                  value['additional_stop_assessments'], describe=True)
