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
                             'protected_criteria': [], 'expires_at': None, 'request_scope': None,
                             'submission_validation_modes': ['target-schema', 'bounded-probe', 'observed-profile']}], 'stop_conditions': []}
    (root / spec['authority']).write_bytes(c.encoded(authority))
    (root / 'fixture-authority-basis.txt').write_text('Synthetic test declaration, not a real user instruction.\n', encoding='utf-8')
    return spec


def grant(root: Path, run: str, intent: dict, *, reason: str = 'Synthetic test operation only.') -> str:
    import production_workflow as w
    request = w.draft_authorization(root, run, 'fixture-grant', intent)
    request['reason'] = reason
    if intent['operation'] == 'submit' and 'request_decision' in request:
        if w.load_run(root, run)[1]['task']['execution'] == 'dispatcher':
            from production_request import assessment_source
            prepared = w.load_run(root, run)[1]
            evidence = prepared['authority']['evidence']
            request['request_decision']['principal_approval'] = assessment_source(root, intent['payload'],
                principal=prepared['authority']['issuer'], path=evidence['path'], locator=evidence['locator'])
        assess_rendition(request['request_decision']['rendition_review'])

    path = 'fixture-authorization-' + generate_uuid7() + '.json'
    (root / path).write_bytes(c.encoded(request))
    return w.authorize(root, run, path)['sha256']


def assess_rendition(review: dict) -> None:
    """Author the three explicit judgments of the labeled synthetic fixture actor."""
    reasons = {
        'finished-image': 'Synthetic depiction fixture assessed across every actual text field; not image quality or user approval.',
        'supplied-inputs': 'Synthetic supplied-media assignments and input-use directions were assessed against this exact input.',
        'ownership': 'Synthetic fixture keeps production bookkeeping separate from model image text and native controls.',
    }
    for item in review['assessments']:
        item.update(conclusion='satisfied', reason=reasons[item['criterion']])


def external_image_input(root: Path, spec: dict, *, count: int = 1) -> str:
    """Author a reference-free exact external request for a synthetic image task."""
    model = 'synthetic-external-image'
    specification = (spec.get('generation') or {}).get('production_spec')
    if specification is None:
        specification = next((row['path'] for row in spec['sources']
                              if row['role'] == 'production-spec' and row['disposition'] == 'applied'), None)
    if specification is not None:
        model = c.load(root / specification)['target_model']
    stem = 'fixture-external-' + generate_uuid7()
    request_file, evidence_file, input_file = (stem + suffix for suffix in ('-request.json', '-evidence.txt', '-input.json'))
    prompt = (root / spec['delivery']['path']).read_bytes().decode('utf-8')
    (root / request_file).write_bytes(c.encoded({'model': model, 'prompt': prompt, 'count': count}))
    (root / evidence_file).write_text('Synthetic external request contract; no real provider claim.\n', encoding='utf-8')
    value = {'artifact_type': 'image-input-plan',
             'model': {'requested': model, 'catalog_status': 'missing', 'catalog_model': None,
                       'target': {'service': 'synthetic', 'model_identifier': model, 'operation': 'generation'},
                       'evidence': {'path': evidence_file, 'sha256': c.sha256_file(root / evidence_file), 'locator': 'whole'}},
             'references': [],
             'external_request': {'file': request_file, 'model_field': ['model'], 'prompt_field': ['prompt'],
                                  'count_field': ['count'], 'operation_field': None, 'count': count, 'reference_fields': []}}
    (root / input_file).write_bytes(c.encoded(value))
    spec['image_input'] = input_file
    return input_file


def handoff(root: Path, run: str, recipient: str, method: str) -> dict:
    import production_workflow as w
    intent = w.handoff_intent(root, run, recipient, method)
    rows = w.load_run(root, run)[3]
    matching = [r for r in rows if r['event'] == 'handoff' and
                r['data']['recipient'] == recipient and r['data']['method'] == method]
    authorization = matching[-1]['data']['authorizations'][0] if matching else grant(root, run, intent)
    return w.handoff(root, run, recipient, method, authorization)


def scratch_home_dir(folder: Path) -> Path:
    """`folder` as a configuration directory whose pack state enables the shipped default packs alone.

    A command started with CPB_HOME at this folder reads that state, never the
    pack state of the person running the suite or the packs beside the shipped ones.
    """
    import shutil
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'config' / 'default-pack-state.json', folder / 'pack-state.json')
    return folder


def scratch_home(folder: Path):
    """A patch that points CPB_HOME at `folder`, prepared by `scratch_home_dir`.

    Operation logs and the home reading ledger of one test then stay in that folder.
    """
    import os
    from unittest.mock import patch
    scratch_home_dir(folder)
    return patch.dict(os.environ, {'CPB_HOME': str(folder)})


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


def prepare_external_delivery(root: Path, prompt: str, *, route: str = 'generation',
                     artifact: str = 'image', sources: list | None = None) -> str:
    """Explicit local test setup; never imported by an operational entrypoint."""
    import work_ledger
    import production_workflow as w
    started = work_ledger.begin(root, 'Synthetic external package construction', ['prepare', 'inspect'])
    (root / 'fixture-delivery.txt').write_text(prompt, encoding='utf-8')
    spec = {'task_id': started['task_id'], 'route': route, 'features': [],
            'sources': sources or [], 'delivery': {'path': 'fixture-delivery.txt',
             'translation_notes': 'Exact synthetic test input.'},
            'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect actual received fixture bytes.'}],
            'world_views': []}
    if artifact == 'image':
        external_image_input(root, spec)
    task(root, spec, artifact=artifact, execution='external')
    (root / 'fixture-task.json').write_bytes(c.encoded(spec))
    run = w.prepare(root, 'fixture-task.json')['run']
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
    validation = fixture_validation(root, value['model'], reference_mode='authored-rendition')
    reader, _ = input_contracts.capture_validation(validation, root=root)
    reader.basis(value['visual_continuity']['basis'])
    input_contracts.attach(value, validation, reader)
    commitment = generation_input_sha256(value)
    value['generation_input_sha256'] = commitment
    value['generation_contract']['generation_input_sha256'] = commitment
    return value
