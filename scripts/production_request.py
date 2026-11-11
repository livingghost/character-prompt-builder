"""Bind model requests, recorded validation, and explicit authority assessments."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, TYPE_CHECKING

import execution_contract as c
from input_evidence import InputEvidence
import request_contract as rc
import request_scope
import request_validation
import model_rendition

if TYPE_CHECKING:
    from production_store import CurrentAuthority

PAYLOAD_FIELDS = {'package_sha256', 'seed', 'count', 'service', 'model_identifier',
                  'offering_sha256', 'service_sha256', 'request_sha256',
                  'request_contract', 'request_validation', 'validation_inputs', 'external_effects'}
DECISION_FIELDS = {'case', 'assessments', 'principal_approval', 'rendition_review'}


def _binding_ids(rendered: dict) -> list[str]:
    return ['reference:' + str(item['reference_number']) for item in rendered['sealed']['bindings']]


def input_hashes(snapshots: dict) -> dict[str, str]:
    """The path and SHA-256 of every input file the request validation read."""
    return {path: item['sha256'] for path, item in snapshots.items()}


def external_effects(rendered: dict, count: int, transport) -> list[dict]:
    """The generation's inputs belong to this execution through their cleanup."""
    effects = []
    if rendered['media']:
        effects.append({'operation': 'upload', 'count': len(rendered['media'])})
    effects.append({'operation': 'send', 'count': 1, 'outputs': count})
    if rendered['media'] and callable(getattr(transport, 'prepare_delete', None)):
        effects.append({'operation': 'delete', 'count': len(rendered['media'])})
    return effects


def intent(package: dict, rendered: dict, *, seed: int | None, count: int,
           offering: dict, service: dict) -> dict:
    """Describe an exact operation without granting permission or reserving a use."""
    import transport_contract
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
        'external_effects': external_effects(rendered, count, transport_contract.load(service['transport'])),
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
    if any(isinstance(item, dict) and item.get('operation') == 'delete' for item in effects):
        if not payload['request_contract']['media']:
            raise ValueError('only this execution\'s uploaded inputs can be deleted')
        expected_effects.append({'operation': 'delete', 'count': len(payload['request_contract']['media'])})
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
    review = model_rendition.draft_review(rendered['request_sha256'], actor=actor,
                                         binding_ids=_binding_ids(rendered))
    return {'case': None, 'assessments': [], 'principal_approval': None, 'rendition_review': review}


def delegation_template(prepared: dict, operations: list[dict], authority: dict | None) -> dict | None:
    """Expose the exact scope shape; its source and permission are still unanswered."""
    if prepared['task']['execution'] != 'dispatcher':
        return None
    intent = next((item for item in operations if item['operation'] == 'submit'), None)
    if intent is None:
        return None
    rendered = intent['payload']['request_contract']
    case = request_scope.build_case(rendered, identifier='exact-request',
        productions=[prepared['task']['production_id']], variations={}, review_criteria=[])
    sources = []
    if authority is not None:
        sources.append({**copy.deepcopy(authority['evidence']), 'role': 'current-authority-evidence'})
        for grant in authority['grants']:
            if grant['request_scope'] is not None:
                sources.append({**copy.deepcopy(grant['request_scope']['plan']),
                                'role': 'current-delegation-source', 'grant': grant['id']})
    return {'state': 'unapproved', 'request_sha256': rendered['request_sha256'],
        'schema': str(Path(__file__).resolve().parents[1] / 'schemas/authoring/request-scope.schema.json'),
        'scope': {'plan': {'path': None, 'locator': None}, 'cases': [case]},
        'source_candidates': sources,
        'instruction': 'Use this shape only when the actual issuer delegated these operations. Select the real instruction path and locator; the runtime derives its digest. Fixed fields describe this prepared request. Broaden variations or add review criteria only where the instruction grants that scope. This template creates no authority and selects no grant or case.'}


def draft_external_decision(binding: dict, *, actor: str | None) -> dict:
    """Use the exact external image binding as the identity of the input under review."""
    import image_input
    image_input.validate_binding(binding)
    if binding['external_request'] is None:
        raise ValueError('external image review requires the exact request binding')
    review = model_rendition.draft_review(binding['binding_sha256'], actor=actor,
        binding_ids=['reference:' + str(index) for index in range(1, len(binding['references']) + 1)])
    return {'rendition_review': review}


def external_intent(consumer: dict, recipient: str) -> dict:
    """Derive the exact external image operation before its handoff is performed."""
    import image_input
    c.text(recipient, 'external recipient')
    binding = consumer['image_input']
    image_input.validate_binding(binding)
    external = binding['external_request']
    if external is None:
        raise ValueError('external image execution requires the exact request binding')
    return {'operation': 'submit', 'targets': ['delivery'], 'payload': {
        'consumer_sha256': c.content_id(consumer), 'recipient': recipient,
        'count': external['count'], 'image_input_sha256': binding['binding_sha256'],
        'external_request_sha256': external['sha256'], 'target': binding['model']['target']}}


def check_external_authorization(consumer: dict, request: dict, grant: dict) -> None:
    """Check the actor's whole-input review under the existing exact-operation authority."""
    import image_input
    binding = consumer['image_input']
    image_input.require_external_authority(binding, grant)
    external = binding['external_request']
    payload = request['payload']
    c.exact(payload, {'consumer_sha256', 'recipient', 'count', 'image_input_sha256',
                      'external_request_sha256', 'target'}, 'external image submission payload')
    expected = {'consumer_sha256': c.content_id(consumer), 'count': external['count'],
                'image_input_sha256': binding['binding_sha256'], 'external_request_sha256': external['sha256'],
                'target': binding['model']['target']}
    if any(c.encoded(payload[key]) != c.encoded(value) for key, value in expected.items()):
        raise ValueError('external image authorization differs from the prepared complete model input')
    c.text(payload['recipient'], 'external recipient')
    decision = request.get('request_decision')
    c.exact(decision, {'rendition_review'}, 'external image request decision')
    model_rendition.validate_review(decision['rendition_review'], input_sha256=binding['binding_sha256'],
        actor=request['actor'], binding_ids=['reference:' + str(index) for index in range(1, len(binding['references']) + 1)])


# The repair when a recorded authorization cites a reading that no saved bytes hold.
UNSAVED_AUTHORIZATION_EVIDENCE = (
    'A recorded authorization is not corrected in place, and using it reads only the readings saved with it and with '
    'the current authority. Record a new authorization of the prepared operation, which saves each reading it cites: '
    'run draft-execution --run {run} --out FILE, fill FILE from the actual approval or delegation, then run '
    'execute --run {run} --decisions-file FILE.')


class EvidenceWitnesses:
    """Readings of approval and scope sources, keyed by path and SHA-256.

    A growing source such as a work ledger keeps every reading a record cites,
    so a later append never invalidates an earlier capture. While authorizing,
    a cited reading that no snapshot holds is captured once from the current
    file. While consuming a receipt, only saved bytes count; `authorization`
    names the receipt's event.
    """

    def __init__(self, root: Path, items: list[tuple[str, bytes]], *, live: bool, run: str | None = None,
                 authorization: str | None = None):
        self.root = root
        self.live = live
        self.run = run
        self.authorization = authorization
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
                raise ProductionError(
                    'EVIDENCE_SNAPSHOT_MISSING',
                    'Neither the authorization record nor the current authority holds a saved reading of this '
                    'evidence, which the authorization cites.',
                    phase='authorization', file=ref['path'], run=self.run, event=self.authorization,
                    expected=ref['sha256'], required_action=UNSAVED_AUTHORIZATION_EVIDENCE.format(run=self.run))
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
                        authority: CurrentAuthority,
                        recorded: list[tuple[str, bytes]] | None = None,
                        authorization: str | None = None) -> tuple[dict, list[dict]]:
    """Check scope and the supplied review; leave semantic judgments with the actor.

    `recorded` holds the bytes saved with the authorization receipt whose event
    `authorization` names. Without it, the check runs at authorization and
    captures each cited reading once. Returns the scope assessment and every
    evidence reading it used, with path, SHA-256, locator, purpose and the
    verified bytes under `raw`.
    """
    if authority.task_id != prepared['task']['task_id']:
        raise ValueError('current authority belongs to another work task')
    payload = request['payload']
    validate_payload(payload)
    decision = request.get('request_decision')
    c.exact(decision, DECISION_FIELDS, 'model request decision')
    rendered = payload['request_contract']
    model_rendition.validate_review(decision['rendition_review'], input_sha256=rendered['request_sha256'],
                                   actor=request['actor'], binding_ids=_binding_ids(rendered))
    principal = decision['principal_approval']
    if principal is not None:
        if not isinstance(principal, dict) or principal.get('principal') != authority.document['issuer']:
            raise ValueError('exact-request approval does not name the authority issuer')
        c.exact(principal, {'request_sha256', 'principal', 'evidence'}, 'exact request approval')
    import production_store
    items = [(item['path'], item['raw']) for item in production_store.captured_authority_inputs(authority)]
    reader = EvidenceWitnesses(root, items + list(recorded or []), live=recorded is None, run=prepared.get('run'),
                               authorization=authorization)
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
