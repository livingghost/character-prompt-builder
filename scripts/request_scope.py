"""Match explicit delegation cases to the fields of one rendered request."""
from __future__ import annotations

import copy
import math
from typing import Any

import execution_contract as c
import request_contract as rc

MODES = {'target-schema', 'bounded-probe', 'observed-profile'}
CASE_FIELDS = {'id', 'productions', 'targets', 'fixed', 'variations', 'review_criteria'}
EXECUTION_HASH_FIELDS = {'service_execution_sha256', 'offering_contract_sha256', 'transport_sha256'}
CONCLUSIONS = {'satisfied', 'not-satisfied', 'unmeasured'}


def _strings(values: Any, label: str, *, empty: bool = True) -> list[str]:
    if not isinstance(values, list) or (not empty and not values):
        raise ValueError(label + ' must be an explicit array')
    for value in values:
        c.text(value, label)
    if len(set(values)) != len(values):
        raise ValueError(label + ' contains duplicate IDs')
    return values


def _basis(ref: Any) -> None:
    c.exact(ref, {'path', 'sha256', 'locator'}, 'delegation basis')
    c.text(ref['path'], 'basis path')
    c.sha(ref['sha256'])
    c.text(ref['locator'], 'basis locator')


def _validate_variation(rule: Any, criteria: list[str]) -> None:
    if not isinstance(rule, dict):
        raise ValueError('variation rule must be an object')
    kind = rule.get('kind')
    if kind == 'values':
        c.exact(rule, {'kind', 'values'}, 'finite variation')
        values = rule['values']
        if not isinstance(values, list) or not values:
            raise ValueError('finite variation requires explicit values')
        if len({c.content_id(value) for value in values}) != len(values):
            raise ValueError('variation values repeat')
    elif kind == 'range':
        c.exact(rule, {'kind', 'type', 'minimum', 'maximum'}, 'numeric variation')
        if rule['type'] not in {'integer', 'number'}:
            raise ValueError('numeric variation needs a declared type')
        for value in (rule['minimum'], rule['maximum']):
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError('variation bound must be finite numeric data')
            if rule['type'] == 'integer' and type(value) is not int:
                raise ValueError('integer variation bounds must be integers')
        if rule['minimum'] > rule['maximum']:
            raise ValueError('variation minimum exceeds maximum')
    elif kind == 'authored-content':
        c.exact(rule, {'kind', 'source', 'criterion'}, 'authored content variation')
        _basis(rule['source'])
        if rule['criterion'] not in criteria:
            raise ValueError('content variation requires a declared review criterion')
    else:
        raise ValueError('unknown explicit variation rule')


def _validate_case(case: Any, ids: set) -> None:
    c.exact(case, CASE_FIELDS, 'request scope case')
    c.text(case['id'], 'scope case ID')
    if case['id'] in ids:
        raise ValueError('duplicate request scope case ID')
    ids.add(case['id'])

    productions = case['productions']
    if not isinstance(productions, list) or not productions:
        raise ValueError('scope case requires explicit production selectors')
    for selected in productions:
        named = isinstance(selected, str) and selected != ''
        described = isinstance(selected, dict) and bool(selected)
        if not (named or described):
            raise ValueError('invalid production selector')
    if len({c.content_id(item) for item in productions}) != len(productions):
        raise ValueError('production selector repeats')

    targets = case['targets']
    if not isinstance(targets, list) or not targets:
        raise ValueError('scope requires explicit execution targets')
    for selected in targets:
        c.exact(selected, {'target', 'execution'}, 'delegated execution target')
        rc.target(selected['target'])
        c.exact(selected['execution'], EXECUTION_HASH_FIELDS, 'execution hashes')
        for value in selected['execution'].values():
            c.sha(value)
    if len({c.content_id(item) for item in targets}) != len(targets):
        raise ValueError('execution target repeats')

    fixed = case['fixed']
    variations = case['variations']
    if not isinstance(fixed, dict) or not isinstance(variations, dict):
        raise ValueError('scope needs fixed and variable field maps')
    if set(fixed) & set(variations):
        raise ValueError('a delegated field cannot be both fixed and variable')
    for name in set(fixed) | set(variations):
        c.text(name, 'declared field ID')
    criteria = _strings(case['review_criteria'], 'scope review criteria')
    for rule in variations.values():
        _validate_variation(rule, criteria)


def validate(scope: Any, *, submit: bool, modes: Any) -> None:
    _strings(modes, 'submission validation modes')
    if set(modes) - MODES:
        raise ValueError('unknown delegated validation mode')
    if not submit:
        if scope is not None or modes:
            raise ValueError('non-submit permission has no request scope or validation mode')
        return
    if not modes:
        raise ValueError('submit permission requires explicit validation modes')
    if scope is None:
        return
    c.exact(scope, {'plan', 'cases'}, 'request scope')
    _basis(scope['plan'])
    if not isinstance(scope['cases'], list) or not scope['cases']:
        raise ValueError('delegation requires at least one explicit case')
    ids = set()
    for case in scope['cases']:
        _validate_case(case, ids)


def build_case(rendered: dict, *, identifier: str, productions: list, variations: dict,
               review_criteria: list) -> dict:
    """Draft fixed values from a baseline; the principal still supplies the delegation."""
    rc.validate_seal(rendered)
    absent = set(variations) - set(rendered['fields'])
    if absent:
        raise ValueError('variation names undeclared request fields: ' + ', '.join(sorted(absent)))
    fixed = {key: copy.deepcopy(item['value']) for key, item in rendered['fields'].items() if key not in variations}
    return {
        'id': identifier,
        'productions': copy.deepcopy(productions),
        'targets': [{'target': rendered['sealed']['target'], 'execution': rendered['sealed']['execution']}],
        'fixed': fixed,
        'variations': copy.deepcopy(variations),
        'review_criteria': list(review_criteria),
    }


def _within_range(value: Any, rule: dict) -> bool:
    if type(value) not in {int, float} or not math.isfinite(value):
        return False
    if rule['type'] == 'integer' and type(value) is not int:
        return False
    return rule['minimum'] <= value <= rule['maximum']


def _case_blockers(case: dict, rendered: dict, production: Any, reasons: list[dict]) -> None:
    """Append each way the rendered request leaves the selected case."""
    if production not in case['productions']:
        reasons.append({'code': 'production-outside-scope', 'field': 'production', 'actual': production})
    selected = {'target': rendered['sealed']['target'], 'execution': rendered['sealed']['execution']}
    if selected not in case['targets']:
        reasons.append({'code': 'target-outside-scope', 'field': 'target', 'actual': selected})
    fields = rendered['fields']
    declared = set(case['fixed']) | set(case['variations'])
    if declared != set(fields):
        reasons.append({'code': 'request-field-set-changed', 'field': 'fields',
                        'missing': sorted(set(fields) - declared), 'extra': sorted(declared - set(fields))})
    for name, wanted in case['fixed'].items():
        if name in fields and fields[name]['value'] != wanted:
            reasons.append({'code': 'fixed-field-changed', 'field': name,
                            'actual': fields[name]['value'], 'expected': wanted})
    for name, rule in case['variations'].items():
        if name not in fields:
            continue
        item = fields[name]
        value = item['value']
        accepted = False
        if rule['kind'] == 'authored-content':
            if item['kind'] not in {'content', 'media'}:
                reasons.append({'code': 'noncontent-variation', 'field': name})
            else:
                accepted = True
        elif item['kind'] != 'parameter':
            reasons.append({'code': 'nonparameter-variation', 'field': name})
        elif rule['kind'] == 'values':
            accepted = any(type(value) is type(option) and value == option for option in rule['values'])
        else:
            accepted = _within_range(value, rule)
        already_reported = any(reason.get('field') == name for reason in reasons)
        if not accepted and not already_reported:
            reasons.append({'code': 'variation-outside-scope', 'field': name, 'actual': value})


def _unsatisfied_criteria(case: dict, rendered: dict, assessments: list[dict] | None) -> list[str]:
    supplied = {}
    for item in assessments or []:
        c.exact(item, {'criterion', 'request_sha256', 'conclusion', 'reason'}, 'scope criterion assessment')
        c.text(item['reason'], 'criterion reason')
        if item['criterion'] in supplied:
            raise ValueError('scope criterion assessment repeats')
        if item['criterion'] not in case['review_criteria']:
            raise ValueError('assessment names an undeclared criterion')
        if item['request_sha256'] != rendered['request_sha256']:
            raise ValueError('criterion assessment covers another request')
        if item['conclusion'] not in CONCLUSIONS:
            raise ValueError('unknown assessor conclusion')
        supplied[item['criterion']] = item
    return [key for key in case['review_criteria'] if supplied.get(key, {}).get('conclusion') != 'satisfied']


def assess(scope: dict | None, *, case_id: str | None, rendered: dict, production: Any, mode: str,
           modes: list[str], assessments: list[dict] | None = None,
           principal_approval: dict | None = None) -> dict:
    """Return structural eligibility separately from supplied human or actor judgments."""
    validate(scope, submit=True, modes=modes)
    rc.validate_seal(rendered)
    reasons = []
    needs = []
    if mode not in modes:
        reasons.append({'code': 'validation-mode-outside-scope', 'field': 'validation_mode', 'actual': mode})
    if scope is None:
        if case_id is not None:
            raise ValueError('a scope case was selected without a delegated plan')
        if principal_approval is None:
            reasons.append({'code': 'exact-principal-approval-required', 'field': 'principal_approval'})
        else:
            c.exact(principal_approval, {'request_sha256', 'principal', 'evidence'}, 'exact request approval')
            c.text(principal_approval['principal'], 'approving principal')
            _basis(principal_approval['evidence'])
            if principal_approval['request_sha256'] != rendered['request_sha256']:
                reasons.append({'code': 'principal-approval-request-mismatch', 'field': 'request_sha256'})
    else:
        cases = [item for item in scope['cases'] if item['id'] == case_id]
        if len(cases) != 1:
            raise ValueError('select one explicit delegation case; cases are not merged')
        case = cases[0]
        _case_blockers(case, rendered, production, reasons)
        needs = _unsatisfied_criteria(case, rendered, assessments)
    if reasons:
        state = 'principal-decision-required'
    elif needs:
        state = 'actor-assessment-required'
    else:
        state = 'delegated-ready'
    return {
        'state': state,
        'case': case_id,
        'request_sha256': rendered['request_sha256'],
        'scope_blockers': reasons,
        'assessment_required': needs,
        'limit': 'Structural scope matching records the supplied authority; '
                 'it does not authenticate a principal or judge creative meaning.',
    }


def verify_sources(scope: dict | None, approval: dict | None, reader) -> None:
    if scope is not None:
        reader.basis(scope['plan'])
        for case in scope['cases']:
            for rule in case['variations'].values():
                if rule['kind'] == 'authored-content':
                    reader.basis(rule['source'])
    if approval is not None:
        reader.basis(approval['evidence'])
