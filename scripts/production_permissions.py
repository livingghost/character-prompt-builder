#!/usr/bin/env python3
"""Check explicit production grants and cumulative reservations.

The production run's receipt chain is the only execution ledger. This module
neither authenticates an issuer nor infers consent from prose or a budget.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Any
import execution_contract as c
from production_plan import strings

OPERATIONS = {'direction', 'edit', 'submit', 'select', 'adopt'}
MONEY = re.compile(r'^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')


def amount(value: Any) -> Decimal:
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        raise ValueError('money must be a nonnegative finite decimal string')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid money') from exc
    return number


def cost(value: Any, *, quoted: bool = False) -> Decimal:
    if value is None:
        return Decimal(0)
    c.exact(value, {'currency', 'amount', 'basis'} if quoted else {'currency', 'amount'}, 'cost')
    if not isinstance(value['currency'], str) or not re.fullmatch(r'[A-Z]{3}', value['currency']):
        raise ValueError('currency must be an explicit three-letter code')
    if quoted:
        c.text(value['basis'], 'cost basis')
    return amount(value['amount'])


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
        c.exact(grant, {'id', 'actor', 'mode', 'operations', 'targets', 'limits',
                        'protected_criteria', 'expires_at'}, 'grant')
        key = c.text(grant['id'], 'grant id')
        if key in ids:
            raise ValueError('duplicate grant id')
        ids.add(key)
        c.text(grant['actor'], 'grant actor')
        if grant['mode'] not in {'direct', 'delegated'}:
            raise ValueError('grant mode must be direct or delegated')
        if set(strings(grant['operations'], 'grant operations', nonempty=True)) - OPERATIONS:
            raise ValueError('unknown grant operation')
        strings(grant['targets'], 'grant targets', nonempty=True)
        strings(grant['protected_criteria'], 'protected criteria')
        limits = grant['limits']
        c.exact(limits, {'uses', 'outputs', 'cost'}, 'grant limits')
        for key in ('uses', 'outputs'):
            if type(limits[key]) is not int or limits[key] < (1 if key == 'uses' else 0):
                raise ValueError('grant limits require nonnegative integers and positive uses')
        cost(limits['cost'])
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
                      'cost', 'stop_assessments', 'reason'}, 'authorization request')
    for key in ('grant', 'actor', 'reason'):
        c.text(request[key], key)
    if request['operation'] not in OPERATIONS:
        raise ValueError('unknown authorization operation')
    strings(request['targets'], 'authorization targets', nonempty=True)
    if not isinstance(request['payload'], dict) or not request['payload']:
        raise ValueError('exact operation payload is required')
    if type(request['outputs']) is not int or request['outputs'] < 0:
        raise ValueError('outputs must be a nonnegative integer')
    cost(request['cost'], quoted=True)
    if request['operation'] == 'submit':
        if request['cost'] is None or request['outputs'] < 1:
            raise ValueError('submission needs an explicit cost basis and positive output count')
        if request['payload'].get('count') != request['outputs']:
            raise ValueError('submission output count differs from its exact payload')
    elif request['outputs'] or request['cost'] is not None:
        raise ValueError('only a submission reserves outputs and cost')
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


def check(authority: dict, request: dict, reservations: list[dict], *, now: datetime | None = None) -> dict:
    validate_request(request)
    matches = [g for g in authority['grants'] if g['id'] == request['grant']]
    if len(matches) != 1:
        raise ValueError('authorization must name a declared grant')
    grant = matches[0]
    if grant['actor'] != request['actor'] or request['operation'] not in grant['operations']:
        raise ValueError('actor or operation is outside the grant')
    if set(request['targets']) - set(grant['targets']):
        raise ValueError('authorization targets exceed the grant scope')
    if {x['id'] for x in request['stop_assessments']} != {x['id'] for x in authority['stop_conditions']}:
        raise ValueError('every declared stop condition must be explicitly assessed')
    if grant['expires_at'] is not None and (now or datetime.now(timezone.utc)) >= time_value(grant['expires_at']):
        raise ValueError('grant has expired')
    previous = [r for r in reservations if r['grant'] == grant['id']]
    # A grant id stays an accounting identity even if a new authority document is
    # explicitly supplied for a revised run. Re-preparation never resets usage.
    limits = grant['limits']
    if len(previous) + 1 > limits['uses']:
        raise ValueError('grant use limit exceeded')
    if sum(r['outputs'] for r in previous) + request['outputs'] > limits['outputs']:
        raise ValueError('grant output limit exceeded')
    quote = request['cost']
    ceiling = limits['cost']
    if quote is not None:
        if ceiling is None:
            if cost(quote, quoted=True) != 0:
                raise ValueError('grant permits no paid submission')
        elif quote['currency'] != ceiling['currency']:
            raise ValueError('currency differs from the grant')
    paid = [r['cost'] for r in previous if r['cost'] is not None]
    if any(cost(x, quoted=True) and (ceiling is None or x['currency'] != ceiling['currency']) for x in paid):
        raise ValueError('changed grant cannot erase earlier reserved spending')
    # Preserve every supported decimal digit across all cumulative reservations.
    # The default Decimal context is too short for the accepted money format.
    with localcontext() as context:
        context.prec = 170 + len(str(len(paid) + 1))
        total = sum((cost(x, quoted=True) for x in paid), Decimal(0)) + cost(quote, quoted=True)
    if total > cost(ceiling):
        raise ValueError('grant cost limit exceeded')
    return grant
