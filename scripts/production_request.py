"""Bind model requests, recorded validation, and explicit authority assessments."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import execution_contract as c
from input_evidence import InputEvidence
import request_contract as rc
import request_scope
import request_validation

PAYLOAD_FIELDS = {'package_sha256', 'seed', 'count', 'service', 'model_identifier',
                  'offering_sha256', 'service_sha256', 'request_sha256',
                  'request_contract', 'request_validation', 'input_snapshots'}
DECISION_FIELDS = {'case', 'assessments', 'principal_approval', 'rendition_review'}
REVIEW_FIELDS = {'request_sha256', 'reviewer', 'conclusion', 'reason', 'binding_ids'}


def _binding_ids(rendered: dict) -> list[str]:
    return ['reference:' + str(item['reference_number']) for item in rendered['sealed']['bindings']]


def intent(package: dict, rendered: dict, *, seed: int | None, count: int,
           offering: dict, service: dict) -> dict:
    """Describe an exact operation without granting permission or reserving a use."""
    payload = {
        'package_sha256': c.content_id(package),
        'seed': seed,
        'count': count,
        'service': offering['service'],
        'model_identifier': offering['model_identifier'],
        'offering_sha256': c.content_id(offering),
        'service_sha256': c.content_id(service),
        'request_sha256': rendered['request_sha256'],
        'request_contract': rc.receipt_projection(rendered),
        'request_validation': copy.deepcopy(package['request_validation']),
        'input_snapshots': copy.deepcopy(package['input_snapshots']),
    }
    validate_payload(payload)
    return {'operation': 'submit', 'targets': ['delivery'], 'payload': payload}


def validate_payload(payload: Any) -> dict:
    """Verify stored request evidence, independently of a live provider or filesystem."""
    c.exact(payload, PAYLOAD_FIELDS, 'model submission payload')
    for field in ('package_sha256', 'offering_sha256', 'service_sha256', 'request_sha256'):
        c.sha(payload[field])
    if type(payload['count']) is not int or payload['count'] < 1:
        raise ValueError('model submission needs a positive output count')
    if payload['seed'] is not None and type(payload['seed']) is not int:
        raise ValueError('model submission seed must be an integer or explicitly omitted')
    rendered = payload['request_contract']
    rc.validate_seal(rendered)
    if rendered != rc.receipt_projection(rendered):
        raise ValueError('model authorization requires the stable request receipt projection')
    if payload['request_sha256'] != rendered['request_sha256'] or payload['count'] != rendered['output_count']:
        raise ValueError('submission hash or output count differs from its rendered request')
    target = rendered['sealed']['target']
    if payload['service'] != target['service'] or payload['model_identifier'] != target['model_identifier']:
        raise ValueError('submission target differs from its rendered request')
    seed_path = rendered['layout']['seed']
    actual_seed = rc.get(rendered['request'], seed_path) if seed_path is not None else None
    if actual_seed != payload['seed']:
        raise ValueError('submission seed differs from its rendered request')
    from request_renderer import envelope_fields

    evidence = InputEvidence(None, snapshots=payload['input_snapshots'], live=False)
    return request_validation.require(
        payload['request_validation'],
        evidence,
        expected_target=target,
        execution=rendered['sealed']['execution'],
        rendered=rendered,
        envelope_fields=envelope_fields(rendered),
    )


def draft_decision(rendered: dict, *, actor: str | None) -> dict:
    """Derive request identifiers while leaving the actor's assessment unanswered."""
    rc.validate_seal(rendered)
    review = {
        'request_sha256': rendered['request_sha256'],
        'reviewer': actor,
        'conclusion': None,
        'reason': '',
        'binding_ids': _binding_ids(rendered),
    }
    return {'case': None, 'assessments': [], 'principal_approval': None, 'rendition_review': review}


def check_authorization(root: Path, prepared: dict, request: dict, grant: dict) -> tuple[dict, list[dict]]:
    """Check scope and the supplied review; leave semantic judgments with the actor."""
    payload = request['payload']
    report = validate_payload(payload)
    decision = request.get('request_decision')
    c.exact(decision, DECISION_FIELDS, 'model request decision')
    rendered = payload['request_contract']
    review = decision['rendition_review']
    c.exact(review, REVIEW_FIELDS, 'rendition review')
    if review['request_sha256'] != rendered['request_sha256']:
        raise ValueError('rendition review belongs to another final request')
    if review['reviewer'] != request['actor']:
        raise ValueError('the authorized actor must record the rendition assessment')
    c.text(review['reason'], 'rendition assessment reason')
    if review['conclusion'] != 'satisfied':
        raise ValueError('the rendition assessment is incomplete or not satisfied')
    bindings = _binding_ids(rendered)
    reviewed = review['binding_ids']
    distinct = (isinstance(reviewed, list)
                and all(isinstance(item, str) for item in reviewed)
                and len(set(reviewed)) == len(reviewed))
    if not distinct:
        raise ValueError('rendition review requires distinct declared binding IDs')
    if set(reviewed) != set(bindings):
        raise ValueError('rendition review does not cover every transported reference binding')
    principal = decision['principal_approval']
    if principal is not None:
        if not isinstance(principal, dict) or principal.get('principal') != prepared['authority']['issuer']:
            raise ValueError('exact-request approval does not name the authority issuer')
    reader = InputEvidence(root)
    request_scope.verify_sources(grant['request_scope'], principal, reader)
    scoped = request_scope.assess(
        grant['request_scope'],
        case_id=decision['case'],
        rendered=rendered,
        production=prepared['task']['production_id'],
        mode=report['mode'],
        modes=grant['submission_validation_modes'],
        assessments=decision['assessments'],
        principal_approval=principal,
    )
    if scoped['state'] != 'delegated-ready':
        blockers = scoped['scope_blockers'] or scoped['assessment_required']
        raise ValueError('model request authority: ' + scoped['state'] + '; ' + str(blockers))
    sources = [{'path': path, 'sha256': reader.snapshots[path]['sha256']}
               for path in sorted(reader.read_paths)]
    return {'validation': report, 'scope': scoped}, sources


def assessment_source(root: Path, payload: dict, *, principal: str, path: str, locator: str) -> dict:
    """Resolve an explicitly selected approval source without writing an authorization."""
    validate_payload(payload)
    c.text(principal, 'principal')
    reader = InputEvidence(root)
    evidence = {**reader.select(path), 'locator': c.text(locator, 'approval locator')}
    return {'request_sha256': payload['request_sha256'], 'principal': principal, 'evidence': evidence}
