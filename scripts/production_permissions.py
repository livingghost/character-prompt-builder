#!/usr/bin/env python3
"""Check current production grants and the exact terms of an operation.

The Production store owns the durable execution history. This module checks
who may perform the exact operation and the evidence of their permission.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import execution_contract as c
from production_diagnostics import ProductionError
from production_plan import strings

OPERATIONS = {'direction', 'edit', 'submit', 'select', 'adopt'}
def time_value(value: Any) -> datetime:
    c.text(value, 'UTC time')
    if not value.endswith('Z'):
        raise ValueError('authority time must end in Z')
    try:
        result = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError('invalid authority time') from exc
    return result


def validate(authority: Any, task_id: str) -> None:
    c.exact(authority, {'task_id', 'issuer', 'evidence', 'grants', 'stop_conditions'}, 'authority')
    if authority['task_id'] != task_id:
        raise ValueError('authority belongs to a different work task')
    c.text(authority['issuer'], 'authority issuer')
    c.exact(authority['evidence'], {'path', 'locator'}, 'authority evidence')
    for field in ('path', 'locator'):
        c.text(authority['evidence'][field], 'authority evidence ' + field)
    if not isinstance(authority['grants'], list):
        raise ValueError('authority grants must be a list')
    ids: set[str] = set()
    for grant in authority['grants']:
        c.exact(grant, {'id', 'actor', 'mode', 'operations', 'targets',
                        'protected_criteria', 'expires_at', 'request_scope', 'submission_validation_modes'} |
                        ({'revoked_at'} if 'revoked_at' in grant else set()) | ({'effective_at'} if 'effective_at' in grant else set()), 'grant')
        key = c.text(grant['id'], 'grant id')
        if key in ids:
            raise ValueError('duplicate grant id')
        ids.add(key)
        c.text(grant['actor'], 'grant actor')
        if grant['mode'] not in {'direct', 'delegated'}:
            raise ValueError('grant mode must be direct or delegated')
        if set(strings(grant['operations'], 'grant operations', nonempty=True)) - OPERATIONS:
            raise ValueError('unknown grant operation')
        import request_scope
        request_scope.validate(grant['request_scope'], submit='submit' in grant['operations'],
                               modes=grant['submission_validation_modes'])
        strings(grant['targets'], 'grant targets', nonempty=True)
        strings(grant['protected_criteria'], 'protected criteria')
        if grant['expires_at'] is not None:
            time_value(grant['expires_at'])
    if not isinstance(authority['stop_conditions'], list):
        raise ValueError('stop conditions must be a list')
    stops = set()
    for entry in authority['stop_conditions']:
        c.exact(entry, {'id', 'text'}, 'stop condition')
        for key in entry:
            c.text(entry[key], key)
        if entry['id'] in stops:
            raise ValueError('duplicate stop condition')
        stops.add(entry['id'])


def validate_request(request: Any) -> None:
    c.exact(request, {'grant', 'actor', 'operation', 'targets', 'payload', 'outputs',
                      'stop_assessments', 'reason'} | ({'request_decision'} if isinstance(request, dict) and 'request_decision' in request else set()), 'authorization request')
    for key in ('grant', 'actor', 'reason'):
        c.text(request[key], key)
    if request['operation'] not in OPERATIONS:
        raise ValueError('unknown authorization operation')
    strings(request['targets'], 'authorization targets', nonempty=True)
    if not isinstance(request['payload'], dict) or not request['payload']:
        raise ValueError('exact operation payload is required')
    if type(request['outputs']) is not int or request['outputs'] < 0:
        raise ValueError('outputs must be a nonnegative integer')
    if request['operation'] == 'submit':
        if request['outputs'] < 1:
            raise ValueError('submission needs a positive requested output count')
        if request['payload'].get('count') != request['outputs']:
            raise ValueError('submission output count differs from its exact payload')
    elif request['outputs']:
        raise ValueError('only a submission requests outputs')
    if not isinstance(request['stop_assessments'], list):
        raise ValueError('stop assessments must be a list')
    seen = set()
    for assessment in request['stop_assessments']:
        c.exact(assessment, {'id', 'clear', 'evidence'}, 'stop assessment')
        c.text(assessment['id'], 'stop id')
        c.text(assessment['evidence'], 'stop assessment evidence')
        if assessment['clear'] is not True:
            raise ValueError('a stop condition is active or unassessed')
        if assessment['id'] in seen:
            raise ValueError('repeated stop assessment')
        seen.add(assessment['id'])


SCOPE_ACTION = 'Obtain a current grant covering the missing targets; do not remove decisions or narrow targets.'
GRANT_ACTION = 'Obtain a current grant from the actual issuer; an expired or revoked grant is never reused.'


def grant_current(grant: dict, instant: datetime) -> bool:
    return (grant.get('revoked_at') is None
            and (grant.get('effective_at') is None or instant >= time_value(grant['effective_at']))
            and (grant['expires_at'] is None or instant < time_value(grant['expires_at'])))


def target_coverage(authority: dict, operation: str, targets: list[str], *, now: datetime | None = None) -> list[dict]:
    """For each current grant of the operation, the targets it grants and the targets it lacks.

    An empty `missing` list means that grant covers the whole prepared operation.
    """
    instant = now or datetime.now(timezone.utc)
    return [{'grant': grant['id'], 'granted': sorted(grant['targets']),
             'missing': sorted(set(targets) - set(grant['targets']))}
            for grant in authority['grants']
            if operation in grant['operations'] and grant_current(grant, instant)]


def check(authority: dict, request: dict, *, now: datetime | None = None) -> dict:
    """Verify current authority and the exact operation before recording its execution."""
    validate_request(request)
    terms={'operation':request['operation'],'grant':request['grant']}
    matches=[g for g in authority['grants'] if g['id']==request['grant']]
    if len(matches)!=1:
        raise ProductionError('GRANT_REVOKED','The current authority no longer contains this grant.',phase='authorization',
                              required_action=GRANT_ACTION,**terms)
    grant=matches[0];instant=now or datetime.now(timezone.utc)
    if grant.get('revoked_at') is not None:
        raise ProductionError('GRANT_REVOKED','The selected grant was revoked.',phase='authorization',actual=grant['revoked_at'],
                              required_action=GRANT_ACTION,**terms)
    if grant.get('effective_at') is not None and instant<time_value(grant['effective_at']):
        raise ProductionError('GRANT_NOT_EFFECTIVE','The grant is not yet effective.',phase='authorization',actual=grant['effective_at'],
                              required_action='Wait for the grant to take effect, or obtain a grant that is effective now.',**terms)
    if grant['expires_at'] is not None and instant>=time_value(grant['expires_at']):
        raise ProductionError('GRANT_REVOKED','The selected grant has expired.',phase='authorization',actual=grant['expires_at'],
                              required_action=GRANT_ACTION,**terms)
    if grant['actor']!=request['actor'] or request['operation'] not in grant['operations']:
        raise ProductionError('GRANT_SCOPE_EXCEEDED','Actor or operation is outside the current grant.',phase='authorization',
                              expected={'actor':request['actor'],'operation':request['operation']},
                              actual={'actor':grant['actor'],'operations':sorted(grant['operations'])},
                              required_action='Obtain a current grant naming this actor and operation; another actor cannot act on it.',**terms)
    missing=sorted(set(request['targets'])-set(grant['targets']))
    if missing:
        raise ProductionError('GRANT_SCOPE_EXCEEDED','The current grant does not cover all required targets.',phase='authorization',
                              pointer='$.targets',expected=sorted(request['targets']),actual=sorted(grant['targets']),
                              granted=sorted(grant['targets']),missing=missing,required_action=SCOPE_ACTION,**terms)
    if {x['id'] for x in request['stop_assessments']}!={x['id'] for x in authority['stop_conditions']}:
        raise ProductionError('AUTHORIZATION_REQUIRED','Every declared stop condition needs an actual current assessment.',phase='authorization',
                              pointer='$.stop_assessments',expected=sorted(x['id'] for x in authority['stop_conditions']),
                              actual=sorted(x['id'] for x in request['stop_assessments']),
                              required_action='Assess every current stop condition from actual evidence.',**terms)
    return grant
