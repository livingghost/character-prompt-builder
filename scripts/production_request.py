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
                  'request_contract', 'request_validation', 'validation_inputs', 'external_effects'}
DECISION_FIELDS = {'case', 'assessments', 'principal_approval', 'rendition_review'}
REVIEW_FIELDS = {'request_sha256', 'reviewer', 'conclusion', 'reason', 'binding_ids'}


def _binding_ids(rendered: dict) -> list[str]:
    return ['reference:' + str(item['reference_number']) for item in rendered['sealed']['bindings']]


def input_hashes(snapshots: dict) -> dict[str, str]:
    """The path and SHA-256 of every input file the request validation read."""
    return {path: item['sha256'] for path, item in snapshots.items()}


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
        'validation_inputs': input_hashes(package['input_snapshots']),
        'external_effects': ([{'operation': 'upload', 'count': len(rendered['media'])}] if rendered['media'] else [])
                            + [{'operation': 'send', 'count': 1, 'outputs': count}],
    }
    validate_payload(payload, snapshots=package['input_snapshots'])
    return {'operation': 'submit', 'targets': ['delivery'], 'payload': payload}


def validate_payload(payload: Any, *, snapshots: dict | None = None) -> None:
    """Verify a submission payload without sending it; also check any supplied input bytes against the request.

    The payload names each input file by path and SHA-256. The dispatcher holds
    the bytes in the package, so it verifies them when it writes the intent and
    again when it claims the authorization, before any upload or send.
    """
    c.exact(payload, PAYLOAD_FIELDS, 'model submission payload')
    for field in ('package_sha256', 'offering_sha256', 'service_sha256', 'request_sha256'):
        c.sha(payload[field])
    if type(payload['count']) is not int or payload['count'] < 1:
        raise ValueError('model submission needs a positive output count')
    if payload['seed'] is not None and type(payload['seed']) is not int:
        raise ValueError('model submission seed must be an integer or explicitly omitted')
    effects = payload['external_effects']
    if not isinstance(effects, list) or not effects:
        raise ValueError('model submission external_effects must name every irreversible external step')
    expected_effects = ([{'operation': 'upload', 'count': len(payload['request_contract']['media'])}]
                        if payload['request_contract']['media'] else []) + [
                            {'operation': 'send', 'count': 1, 'outputs': payload['count']}
                        ]
    if effects != expected_effects:
        raise ValueError('model submission external_effects differ from the sealed request transport steps')
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
    record = request_validation.validate_content(payload['request_validation'])
    if record['target'] != target:
        raise ValueError('validation target differs from selected execution')
    if any(record[key] != value for key, value in rendered['sealed']['execution'].items()):
        raise ValueError('validation was prepared for a different execution contract')
    hashes = payload['validation_inputs']
    if not isinstance(hashes, dict):
        raise ValueError('validation_inputs maps each input path to its SHA-256')
    for path, key in hashes.items():
        c.text(path, 'input path')
        c.sha(key)
    for field in ('contract', 'evidence', 'execution_policy'):
        ref = record[field]
        if ref is not None and hashes.get(ref['path']) != ref['sha256']:
            raise ValueError(f"validation_inputs does not name the validation {field} {ref['path']} with its SHA-256")
    if snapshots is None:
        return
    if input_hashes(snapshots) != hashes:
        raise ValueError('input bytes differ from the SHA-256 the submission intent names')
    from request_renderer import envelope_fields

    request_validation.require(
        record,
        InputEvidence(None, snapshots=copy.deepcopy(snapshots), live=False),
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


class EvidenceWitnesses:
    """Readings of approval and scope sources, keyed by path and SHA-256.

    A growing source such as a work ledger keeps every reading a record cites,
    so a later append never invalidates an earlier capture. While authorizing,
    a cited reading that no snapshot holds is captured once from the current
    file. While consuming a receipt, only saved bytes count.
    """

    def __init__(self, root: Path, items: list[tuple[str, bytes]], *, live: bool, run: str | None = None):
        self.root = root
        self.live = live
        self.run = run
        self.items = {(path, c.digest(raw)): raw for path, raw in items}
        self.read: dict[tuple[str, str], str] = {}

    def basis(self, ref: Any) -> bytes:
        import production_store
        from production_diagnostics import ProductionError
        c.exact(ref, {'path', 'sha256', 'locator'}, 'source basis')
        c.text(ref['path'], 'evidence path')
        c.sha(ref['sha256'])
        c.text(ref['locator'], 'source locator')
        key = (ref['path'], ref['sha256'])
        if key not in self.items:
            if not self.live:
                raise production_store.evidence_error(
                    'EVIDENCE_SNAPSHOT_MISSING', 'The authorization record holds no saved bytes for this cited evidence.',
                    file=ref['path'], expected=ref['sha256'], run=self.run)
            raw = production_store.stable_bytes(self.root, ref['path'])
            actual = c.digest(raw)
            if actual != ref['sha256']:
                raise ProductionError('SOURCE_CHANGED', 'Cited evidence differs from the digest the decision names.',
                                      phase='authorization', file=ref['path'], expected=ref['sha256'], actual=actual,
                                      required_action='Cite the evidence by its current digest, or restore the exact cited bytes.')
            self.items[key] = raw
        self.read.setdefault(key, ref['locator'])
        return self.items[key]


def check_authorization(root: Path, prepared: dict, request: dict, grant: dict, *,
                        recorded: list[tuple[str, bytes]] | None = None) -> tuple[dict, list[dict]]:
    """Check scope and the supplied review; leave semantic judgments with the actor.

    `recorded` holds the bytes saved with an authorization receipt. Without it,
    the check runs at authorization and captures each cited reading once.
    Returns the scope assessment and every evidence reading it used, with
    path, SHA-256, locator, purpose and the verified bytes under `raw`.
    """
    payload = request['payload']
    validate_payload(payload)
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
        c.exact(principal, {'request_sha256', 'principal', 'evidence'}, 'exact request approval')
    import production_store
    items = [(item['path'], item['raw']) for item in production_store.captured_authority_inputs(root, prepared['task']['task_id'])]
    reader = EvidenceWitnesses(root, items + list(recorded or []), live=recorded is None, run=prepared.get('run'))
    request_scope.verify_sources(grant['request_scope'], principal, reader)
    scoped = request_scope.assess(
        grant['request_scope'],
        case_id=decision['case'],
        rendered=rendered,
        production=prepared['task']['production_id'],
        mode=payload['request_validation']['mode'],
        modes=grant['submission_validation_modes'],
        assessments=decision['assessments'],
        principal_approval=principal,
    )
    if scoped['state'] != 'delegated-ready':
        blockers = scoped['scope_blockers'] or scoped['assessment_required']
        raise ValueError('model request authority: ' + scoped['state'] + '; ' + str(blockers))
    approval = (principal['evidence']['path'], principal['evidence']['sha256']) if principal is not None else None
    sources = [{'path': path, 'sha256': key, 'locator': locator,
                'purpose': 'principal-approval' if (path, key) == approval else 'request-scope',
                'raw': reader.items[(path, key)]}
               for (path, key), locator in sorted(reader.read.items())]
    return {'scope': scoped}, sources


def assessment_source(root: Path, payload: dict, *, principal: str, path: str, locator: str) -> dict:
    """Resolve an explicitly selected approval source without writing an authorization."""
    validate_payload(payload)
    c.text(principal, 'principal')
    reader = InputEvidence(root)
    evidence = {**reader.select(path), 'locator': c.text(locator, 'approval locator')}
    return {'request_sha256': payload['request_sha256'], 'principal': principal, 'evidence': evidence}
