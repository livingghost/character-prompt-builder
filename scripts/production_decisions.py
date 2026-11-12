"""Author execution judgments once; derive exact authorization records from the run."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError, compare_exact

SCHEMA = 'schemas/authoring/production-execution-decisions.schema.json'


def validate_shape(choices: Any) -> dict:
    """Check document structure without inspecting a run or granting authority."""
    from state_protocol import read_schema, validate_against_schema
    schema = read_schema(Path(__file__).resolve().parents[1] / SCHEMA)
    errors = validate_against_schema(choices, schema)
    return {'ok': not errors, 'errors': errors, 'schema': SCHEMA,
            'validation_scope': 'document-shape'}


def context(root: Path, run: str, *, fresh: bool = True):
    import production_workflow as workflow
    loaded = workflow.assert_current(root, run) if fresh else workflow.read_run(root, run)
    directory, prepared, consumer, rows = loaded
    plan = loaded.artifacts['execution-plan.json']
    if prepared['task']['execution'] not in {'dispatcher', 'external'} or not plan['operations']:
        raise ProductionError('EXECUTION_NOT_APPLICABLE', 'This operation needs a prepared model request.',
                              phase='execution', run=run,
                              required_action='Follow the next action of status --run; draft-execution and execute apply '
                                              'to a dispatcher run or an external image request.')
    return loaded


def _request_choices(request: dict) -> dict:
    decision = request['request_decision']
    result = {'rendition_review': {'assessments': copy.deepcopy(decision['rendition_review']['assessments'])}}
    if 'case' in decision:
        result.update(case=None, assessments=[], principal_approval=None)
    return result


def draft(root: Path, run: str, grant: str | None = None) -> dict:
    """Keep operation identity and authored answers, without copied request payloads."""
    import production_workflow as workflow
    loaded = context(root, run)
    prepared = loaded.prepared
    plan = loaded.artifacts['execution-plan.json']
    import production_permissions
    import production_request
    held = store.read_authority(root, prepared['task']['task_id'], required=False)
    authority = held.document if held is not None else None
    requirements = production_permissions.grant_requirements(authority, plan['operations'], grant=grant)
    decisions = []
    for intent, requirement in zip(plan['operations'], requirements['requirements']):
        choice = {'operation': intent['operation'], 'grant': requirement['selected_grant'],
            'reason': '', 'stop_assessments': [{'id': item['id'], 'clear': False, 'evidence': ''}
                for item in (authority or {}).get('stop_conditions', [])]}
        if intent['operation'] == 'submit':
            decision = None
            if prepared['task']['execution'] == 'dispatcher':
                decision = production_request.draft_decision(intent['payload']['request_contract'], actor=requirement['selected_actor'])
            elif prepared['task']['artifact'] == 'image':
                decision = production_request.draft_external_decision(loaded.consumer['image_input'], actor=requirement['selected_actor'])
            if decision is not None:
                choice['request_decision'] = _request_choices({'request_decision': decision})
        decisions.append(choice)
    result = {'choices': {'run': run, 'input_sha256': prepared['input_sha256'],
            'request_sha256': plan['request_sha256'], 'decisions': decisions},
            'authorization_requirements': requirements,
            'authority': store.authority_snapshot(root, prepared['task']['task_id'], held,
                                                  source_path=prepared['task'].get('authority')),
            'request_scope_template': production_request.delegation_template(prepared, plan['operations'], authority)}
    if prepared['task']['execution'] == 'external' and loaded.consumer.get('image_input') is not None:
        from image_input import external_delivery
        result['host_request'] = external_delivery(loaded.consumer['image_input'],
            run_directory=loaded.directory, read_object=loaded.evidence.read)
    return result


def _request_decision(root: Path, request: dict, choice: dict, authority: dict) -> dict:
    """Bind supplied judgments and explicitly selected approval evidence to this exact request."""
    from production_request import assessment_source
    result = request['request_decision']
    fields = {'rendition_review'} | ({'case', 'assessments', 'principal_approval'} if 'case' in result else set())
    c.exact(choice, fields, 'execution request choices')
    c.exact(choice['rendition_review'], {'assessments'}, 'rendition choices')
    result['rendition_review']['assessments'] = copy.deepcopy(choice['rendition_review']['assessments'])
    if 'case' in result:
        result['case'] = choice['case']
        if not isinstance(choice['assessments'], list):
            raise ValueError('scope assessments must be an array')
        result['assessments'] = []
        for assessment in choice['assessments']:
            c.exact(assessment, {'criterion', 'conclusion', 'reason'}, 'scope assessment choices')
            result['assessments'].append({**copy.deepcopy(assessment),
                                          'request_sha256': request['payload']['request_sha256']})
        approval = choice['principal_approval']
        if approval is not None:
            c.exact(approval, {'path', 'locator'}, 'selected principal approval')
            result['principal_approval'] = assessment_source(root, request['payload'],
                principal=authority['issuer'], path=approval['path'], locator=approval['locator'])
    return result


def expand(root: Path, run: str, choices: dict, loaded, authority) -> list[dict]:
    """Materialize separate authorizations without interpreting or approving their answers."""
    import production_workflow as workflow
    prepared = loaded.prepared
    plan = loaded.artifacts['execution-plan.json']
    report = validate_shape(choices)
    if not report['ok']:
        raise ValueError('production execution-decisions: ' + '; '.join(report['errors']))
    compare_exact({'run': run, 'input_sha256': prepared['input_sha256'], 'request_sha256': plan['request_sha256']},
                  {key: choices[key] for key in ('run', 'input_sha256', 'request_sha256')})
    selected = choices['decisions']
    if [item['operation'] for item in selected] != [item['operation'] for item in plan['operations']]:
        raise ProductionError('AUTHORIZATION_MISMATCH', 'Supply every prepared operation exactly once in its prepared order.',
                              phase='authorization', run=run, pointer='$.decisions',
                              required_action='Give $.decisions one entry for each prepared operation, in the order '
                                              'draft-execution writes them.')
    import production_permissions
    requirements = production_permissions.grant_requirements(authority.document, plan['operations'], selections=selected)
    production_permissions.require_grants(requirements)
    result = []
    for intent, choice, requirement in zip(plan['operations'], selected, requirements['requirements']):
        request = workflow.draft_authorization_from(loaded, authority, requirement['selected_grant'], intent)
        expected = {'operation', 'grant', 'reason', 'stop_assessments'}
        if 'request_decision' in request:
            expected.add('request_decision')
        c.exact(choice, expected, 'execution decision')
        request['reason'] = choice['reason']
        request['stop_assessments'] = copy.deepcopy(choice['stop_assessments'])
        if 'request_decision' in request:
            request['request_decision'] = _request_decision(root, request, choice['request_decision'], authority.document)
        result.append(request)
    return result


def authorize(root: Path, run: str, path: str, prepared: dict, plan: dict) -> None:
    import production_workflow as workflow
    raw = store.stable_bytes(root, path)
    with store.transaction(root):
        loaded = context(root, run)
        compare_exact(prepared['input_sha256'], loaded.prepared['input_sha256'], phase='authorization')
        compare_exact(plan, loaded.artifacts['execution-plan.json'], phase='authorization')
        authority = workflow.current_authority(root, loaded.prepared)
        _authorize_from(root,loaded,authority,path,plan,raw=raw)


def _authorize_from(root: Path, loaded, authority, path: str, plan: dict, *, raw: bytes | None = None) -> None:
    """Authorize from the command's current run, grant and exact decision bytes."""
    import production_workflow as workflow
    if raw is None:
        raw=store.stable_bytes(root,path)
    run=loaded.prepared['run']
    compare_exact(plan,loaded.artifacts['execution-plan.json'],phase='authorization')
    requests=expand(root,run,c.decode(raw),loaded,authority)
    for request in requests:
        workflow._authorize_value_from(root,loaded,authority,request,evidence_files=[path],
                                       expected_source=(path,c.digest(raw)))
        loaded=workflow.read_run(root,run)
