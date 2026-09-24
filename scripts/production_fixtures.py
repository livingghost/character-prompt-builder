#!/usr/bin/env python3
"""Explicit synthetic fixtures for tests and executable examples, not approvals.

Only test/example programs import this module. Runtime commands never fill in
missing direction, authority, evidence or decisions on an author's behalf.
"""
from __future__ import annotations
from pathlib import Path
import execution_contract as c
from pack_manager import generate_uuid7

ACTOR = 'SYNTHETIC FIXTURE OPERATOR - NOT USER CONSENT'


def task(root: Path, spec: dict, *, artifact: str = 'text', execution: str = 'authored') -> dict:
    from reading_fixtures import task_reading
    task_reading(root, spec)
    spec.setdefault('production_id', generate_uuid7())
    spec['artifact'] = artifact
    spec['execution'] = execution
    spec['direction'] = {'purpose': 'Exercise an explicitly declared synthetic deliverable.',
                         'intended_effect': 'Make no claim of generated artwork or user approval.',
                         'basis': [], 'decisions': [], 'action_slice': None,
                         'limitations': ['Synthetic fixture only.']}
    for criterion in spec['criteria']:
        criterion['evidence'] = 'artifact'
    spec['authority'] = 'fixture-authority.json'
    authority = {'task_id': spec['task_id'], 'issuer': 'SYNTHETIC TEST FIXTURE',
                 'evidence': {'path': 'fixture-authority-basis.txt', 'locator': 'whole'},
                 'grants': [{'id': 'fixture-grant', 'actor': ACTOR, 'mode': 'direct',
                             'operations': ['direction', 'edit', 'submit', 'select', 'adopt'],
                             'targets': ['purpose', 'delivery', 'decision:expression', 'canon:sheet'],
                             'limits': {'uses': 100, 'outputs': 20, 'cost': {'currency': 'USD', 'amount': '100'}},
                             'protected_criteria': [], 'expires_at': None, 'request_scope': None,
                             'submission_validation_modes': ['target-schema', 'bounded-probe', 'observed-profile']}], 'stop_conditions': []}
    (root / spec['authority']).write_bytes(c.encoded(authority))
    (root / 'fixture-authority-basis.txt').write_text('Synthetic test declaration, not a real user instruction.\n', encoding='utf-8')
    return spec


def grant(root: Path, run: str, intent: dict, *, reason: str = 'Synthetic test operation only.',
          cost: dict | None = None) -> str:
    import production_workflow as w
    request = w.draft_authorization(root, run, 'fixture-grant', intent)
    request['reason'] = reason
    if intent['operation'] == 'submit':
        request['cost'] = cost or {'currency': 'USD', 'amount': '0', 'basis': 'Synthetic fixture; no service call.'}
        if 'request_decision' in request:
            from production_request import assessment_source
            prepared = w.load_run(root, run)[1]
            evidence = prepared['authority']['evidence']
            request['request_decision'] = {
                'case': None, 'assessments': [],
                'principal_approval': assessment_source(root, intent['payload'],
                    principal=prepared['authority']['issuer'], path=evidence['path'], locator=evidence['locator']),
                'rendition_review': {'request_sha256': intent['payload']['request_sha256'],
                    'reviewer': ACTOR, 'conclusion': 'satisfied',
                    'reason': 'Synthetic fixture assessment of declared bytes; not artistic or user approval.',
                    'binding_ids': ['reference:' + str(item['reference_number'])
                                    for item in intent['payload']['request_contract']['sealed']['bindings']]}}

    path = 'fixture-authorization-' + generate_uuid7() + '.json'
    (root / path).write_bytes(c.encoded(request))
    return w.authorize(root, run, path)['sha256']


def handoff(root: Path, run: str, recipient: str, method: str) -> dict:
    import production_workflow as w
    intent = w.handoff_intent(root, run, recipient, method)
    rows = w.load_run(root, run)[3]
    matching = [r for r in rows if r['event'] == 'handoff' and
                r['data']['recipient'] == recipient and r['data']['method'] == method]
    authorization = matching[-1]['data']['authorizations'][0] if matching else grant(root, run, intent)
    return w.handoff(root, run, recipient, method, authorization)


def observation(value: dict) -> dict:
    for item in value['observations']:
        item['evidence'] = 'candidate'
        item['interpretation'] = 'Synthetic fixture interpretation, not artistic evaluation.'
        item['limitations'] = ['Not a user acceptance or model-quality test.']
    return value


def selection(root: Path, run: str, value: dict) -> dict:
    import production_workflow as w
    value['selector'] = ACTOR
    value['authorization'] = grant(root, run, w.selection_intent(value))
    return value


def rendered_request(package: dict, *, seed: int | None, count: int) -> dict:
    """Create a declared synthetic request for isolated recording/authority tests."""
    import request_contract as rc
    record = package['request_validation']
    target = record['target']
    request = {'model': target['model_identifier'], 'operation': target['operation'],
               'text': package['composition_prompt'], 'count': count, 'taskUUID': 'synthetic-request'}
    fields = [{'id': 'model', 'field': ['model'], 'kind': 'fixed'},
              {'id': 'operation', 'field': ['operation'], 'kind': 'fixed'},
              {'id': 'text', 'field': ['text'], 'kind': 'content'},
              {'id': 'count', 'field': ['count'], 'kind': 'parameter'}]
    if seed is not None:
        request['seed'] = seed
        fields.append({'id': 'seed', 'field': ['seed'], 'kind': 'parameter'})
    layout = {'model': ['model'], 'operation': ['operation'], 'primary_text': ['text'],
              'negative_text': None, 'output_count': ['count'], 'fixed_output_count': None,
              'seed': ['seed'] if seed is not None else None, 'media': [],
              'management': [['taskUUID']], 'content': [{'id': 'text', 'field': ['text']}], 'fields': fields}
    execution = {key: record[key] for key in ('service_execution_sha256', 'offering_contract_sha256', 'transport_sha256')}
    visual = package['visual_continuity']
    return rc.seal(request, layout, [], target, execution, [], [],
                   {'subjects': visual['subjects'], 'purpose': visual['purpose'], 'output_kind': 'image'})


def claim(root: Path, run: str, package: dict, verified: dict, journal: Path, count: int = 2) -> dict:
    import production_workflow as w
    rendered = rendered_request(package, seed=None, count=count)
    target = rendered['sealed']['target']
    intent = w.submission_intent(package, rendered=rendered, seed=None, count=count,
                                 offering={'service': target['service'], 'model_identifier': target['model_identifier']}, service={})
    authorization = grant(root, run, intent)
    (journal / 'request-contract.json').write_bytes(c.encoded(rendered))
    return w.claim_dispatch(root, run, package, verified, journal, intent, authorization, rendered=rendered)


def prepare_dispatch(root: Path, prompt: str, *, route: str = 'generation',
                     artifact: str = 'image', sources: list | None = None) -> str:
    """Explicit local test setup; never imported by an operational entrypoint."""
    import work_ledger
    import production_workflow as w
    started = work_ledger.begin(root, 'Synthetic dispatch', ['prepare', 'render'])
    (root / 'fixture-delivery.txt').write_text(prompt, encoding='utf-8')
    spec = {'task_id': started['task_id'], 'route': route, 'features': [],
            'sources': sources or [], 'delivery': {'path': 'fixture-delivery.txt',
            'transport': 'authored-rendition', 'translation_notes': 'Exact synthetic test input.'},
            'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect actual received fixture bytes.'}],
            'world_views': []}
    task(root, spec, artifact=artifact, execution='dispatcher')
    (root / 'fixture-task.json').write_bytes(c.encoded(spec))
    run = w.prepare(root, 'fixture-task.json')['run']
    handoff(root, run, 'synthetic-transport', 'dispatcher')
    return run


def bind_package(root: Path, run: str, package: dict) -> dict:
    import copy
    import production_binding
    from build_generation_payload import generation_input_sha256
    value = copy.deepcopy(package)
    from visual_fixtures import fixture_visual
    from build_generation_payload import sha256_json
    value['visual_continuity'] = fixture_visual(value['production_spec'], root=root)
    value['visual_continuity_sha256'] = sha256_json(value['visual_continuity'])
    value['generation_contract']['visual_continuity_sha256'] = value['visual_continuity_sha256']
    from reading_fixtures import fixture_reading
    from build_generation_payload import sha256_json
    reading = fixture_reading(route=value['route_reading']['route'], features=value['route_reading']['features'])
    value['route_reading'] = reading
    value['route_reading_sha256'] = sha256_json(reading)
    value['generation_contract']['route_reading_sha256'] = sha256_json(reading)
    value['production_binding'] = production_binding.create(root, run, value['composition_prompt'])
    from request_validation_fixtures import fixture_validation
    import input_contracts
    validation = fixture_validation(root, value['model'], reference_mode='prompt-prefix')
    reader, _ = input_contracts.capture_validation(validation, root=root)
    reader.basis(value['visual_continuity']['basis'])
    input_contracts.attach(value, validation, reader)
    commitment = generation_input_sha256(value)
    value['generation_input_sha256'] = commitment
    value['generation_contract']['generation_input_sha256'] = commitment
    return value
