"""Author execution judgments once; derive exact authorization records from the run."""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError, compare_exact


def context(root: Path, run: str, *, fresh: bool = True) -> tuple:
    import production_workflow as workflow
    loaded = workflow.assert_current(root, run) if fresh else workflow.load_run(root, run)
    directory, prepared, consumer, rows = loaded
    plan = c.load(directory / 'execution-plan.json')
    if prepared['task']['execution'] not in {'dispatcher', 'external'} or not plan['operations']:
        raise ProductionError('EXECUTION_NOT_APPLICABLE', 'This operation needs a prepared model request.',
                              phase='execution', run=run)
    return directory, prepared, consumer, rows, plan


def _request_choices(request: dict) -> dict:
    decision = request['request_decision']
    result = {'rendition_review': {'assessments': copy.deepcopy(decision['rendition_review']['assessments'])}}
    if 'case' in decision:
        result.update(case=None, assessments=[], principal_approval=None)
    return result


def draft(root: Path, run: str, grant: str) -> dict:
    """Keep operation identity and authored answers, without copied request payloads."""
    import production_workflow as workflow
    _, prepared, _, _, plan = context(root, run)
    decisions = []
    for intent in plan['operations']:
        request = workflow.draft_authorization(root, run, grant, intent)
        choice = {key: copy.deepcopy(request[key]) for key in ('operation', 'grant', 'reason', 'stop_assessments')}
        if 'request_decision' in request:
            choice['request_decision'] = _request_choices(request)
        decisions.append(choice)
    return {'run': run, 'input_sha256': prepared['input_sha256'],
            'request_sha256': plan['request_sha256'], 'decisions': decisions}


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


def expand(root: Path, run: str, choices: dict, prepared: dict, plan: dict) -> list[dict]:
    """Materialize separate authorizations without interpreting or approving their answers."""
    import production_workflow as workflow
    workflow.schema_check(choices, 'execution-decisions')
    compare_exact({'run': run, 'input_sha256': prepared['input_sha256'], 'request_sha256': plan['request_sha256']},
                  {key: choices[key] for key in ('run', 'input_sha256', 'request_sha256')})
    selected = choices['decisions']
    if [item['operation'] for item in selected] != [item['operation'] for item in plan['operations']]:
        raise ProductionError('AUTHORIZATION_MISMATCH', 'Supply every prepared operation exactly once in its prepared order.',
                              phase='authorization', run=run, pointer='$.decisions')
    result = []
    for intent, choice in zip(plan['operations'], selected):
        request = workflow.draft_authorization(root, run, choice['grant'], intent)
        expected = {'operation', 'grant', 'reason', 'stop_assessments'}
        if 'request_decision' in request:
            expected.add('request_decision')
        c.exact(choice, expected, 'execution decision')
        request['reason'] = choice['reason']
        request['stop_assessments'] = copy.deepcopy(choice['stop_assessments'])
        if 'request_decision' in request:
            request['request_decision'] = _request_decision(root, request, choice['request_decision'], prepared['authority'])
        result.append(request)
    return result


def authorize(root: Path, run: str, path: str, prepared: dict, plan: dict) -> None:
    import production_workflow as workflow
    raw = store.stable_bytes(root, path)
    with store.transaction(root):
        workflow.assert_authority_current(root, prepared)
        requests = expand(root, run, c.decode(raw), prepared, plan)
        for request in requests:
            workflow.authorize_value(root, run, request, evidence_files=[path],
                                     expected_source=(path, c.digest(raw)))
