"""Durable execution claims, irreversible effect boundaries and result records.

Each run owns one execution. Authorization records permission; a claim records
ownership. Every external step is committed before I/O and can start only once.
Provider usage is optional audit evidence and never determines execution readiness.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
import re
import sqlite3
from typing import Any
import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError
from pack_manager import generate_uuid7

EVENTS = {'execution-created', 'execution-start', 'execution-result',
          'external-step', 'external-effect-result', 'operation-start'}
CLAIM_EVENTS = {'dispatch-claim', 'external-claim', 'adoption-claim', 'image-edit-claim'}
NO_EFFECT_OUTCOMES = {'rejected', 'not_executed'}
INSPECTION_ERRORS = (ValueError, OSError, KeyError, TypeError, sqlite3.DatabaseError)


def validate_cost(value: Any) -> None:
    """Check a provider's reported amount without using it as permission."""
    c.exact(value, {'currency', 'amount'}, 'reported cost')
    if not isinstance(value['currency'], str) or not re.fullmatch(r'[A-Z]{3}', value['currency']):
        raise ValueError('reported currency must be a three-letter code')
    if not isinstance(value['amount'], str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value['amount']):
        raise ValueError('reported amount must be a nonnegative finite decimal string')


def validate_usage(usage: Any) -> None:
    if usage is None:
        return
    c.exact(usage, {'currency', 'amount', 'final'}, 'external-effect usage')
    validate_cost({key: usage[key] for key in ('currency', 'amount')})
    if type(usage['final']) is not bool:
        raise ValueError('external-effect usage final must be a boolean')


def derive(records: list[dict], prepared: dict, run: str) -> dict[str, dict]:
    states: dict[str, dict] = {}
    authorizations: dict[str, dict] = {}
    def invalid(message: str):
        raise ProductionError('EXECUTION_RECORD_CORRUPT', message, phase='integrity', run=run)
    for row in records:
        data, event = row['data'], row['event']
        if event == 'authorization':
            authorizations[row['sha256']] = data['request']
        elif event == 'execution-created':
            identifier = data['execution_id']
            request = authorizations.get(data['authorization_sha256'])
            if states or request is None:
                invalid('Execution needs one unique owner and its prior authorization.')
            if (request['operation'] != 'submit' or data['requested_outputs'] != request['outputs']
                    or data['grant'] != request['grant'] or data['actor'] != request['actor']
                    or data['task_id'] != prepared['task']['task_id']
                    or data['request_sha256'] != request['payload'].get('request_sha256', c.content_id(request['payload']))):
                invalid('Execution identity differs from the exact authorized submission.')
            states[identifier] = {**data, 'run': run, 'created_event': row['sha256'],
                'status': 'claimed', 'start': None, 'effect': None, 'steps': [],
                'effect_results': {}, 'result': None, 'actual_cost': None,
                'captured_outputs': 0, 'submissions': 0}
        elif event in EVENTS - {'operation-start'}:
            state = states.get(data.get('execution_id'))
            if state is None:
                invalid('Execution transition has no prior owner.')
            if event == 'execution-start':
                if state['status'] != 'claimed':
                    invalid('Execution was started twice.')
                state.update(status='started', start=row['sha256'], effect=data['effect'], claim=data.get('claim'))
            elif event == 'external-step':
                if state['status'] != 'started' or any(s['step'] == data['step'] for s in state['steps']):
                    invalid('An external step is repeated or outside its active execution.')
                if data['request_sha256'] != state['request_sha256']:
                    invalid('External step belongs to a different request.')
                state['steps'].append(data)
                if data['operation'] == 'send':
                    state['submissions'] += 1
                    if state['submissions'] > 1:
                        invalid('An execution has more than one send boundary.')
            elif event == 'external-effect-result':
                step = data.get('step')
                boundary = next((s for s in state['steps'] if s['step'] == step), None)
                if boundary is None or boundary['claim'] != data.get('claim') or step in state['effect_results']:
                    invalid('External result has no unique matching boundary.')
                validate_usage(data.get('usage'))
                if not data.get('evidence'):
                    invalid('External result lacks its saved response.')
                if 'outcome' in data and (data['outcome'] not in NO_EFFECT_OUTCOMES or data['usage'] is not None):
                    invalid('A no-effect result has an unknown outcome or a charge.')
                state['effect_results'][step] = data
            elif event == 'execution-result':
                if not state['submissions'] or type(data['outputs']) is not int or data['outputs'] < state['captured_outputs']:
                    invalid('Result cannot erase captured outputs or precede the send boundary.')
                if type(data['final']) is not bool or not data.get('evidence'):
                    invalid('Result needs completion state and saved evidence.')
                if state['status'] == 'complete':
                    invalid('A final result was changed.')
                if data['cost'] is not None:
                    validate_cost(data['cost'])
                if state['actual_cost'] is not None and data['cost'] != state['actual_cost']:
                    invalid('A confirmed provider charge was changed.')
                state.update(result=row['sha256'], captured_outputs=data['outputs'], actual_cost=data['cost'],
                             status='complete' if data['final'] else 'captured')
    return states


def by_authorization(records: list[dict], prepared: dict, run: str, authorization: str) -> dict | None:
    return next((s for s in derive(records, prepared, run).values()
                 if s['authorization_sha256'] == authorization), None)


def claim_owns(record: dict, token: str) -> bool:
    return record['event'] in CLAIM_EVENTS and token in record['data'].get('authorizations', [])


def require_active(records: list[dict], prepared: dict, run: str, authorization: str) -> dict:
    state = by_authorization(records, prepared, run, authorization)
    if state is None:
        raise ProductionError('EXECUTION_CLAIM_REQUIRED', 'The submission has no durable execution owner.',
                              phase='execution', run=run)
    return state


def claim_execution(root: Path, run: str, authorization: str) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory, prepared, _, rows = w.assert_current(root, run)
        request = w.find(rows, 'authorization', authorization)['data']['request']
        w._permission(root, prepared, rows, authorization, request['operation'], request['targets'], request['payload'])
        previous = by_authorization(rows, prepared, run, authorization)
        if previous is not None:
            return previous
        if request['operation'] != 'submit':
            raise ValueError('only a submission owns an external execution')
        if derive(rows, prepared, run):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already owns an execution.', phase='execution', run=run)
        identifier = generate_uuid7()
        data = {'execution_id': identifier, 'authorization_sha256': authorization, 'grant': request['grant'],
                'task_id': prepared['task']['task_id'], 'actor': request['actor'],
                'outcome_actors': sorted({request['actor'], prepared['authority']['issuer']}),
                'request_sha256': request['payload'].get('request_sha256', c.content_id(request['payload'])),
                'requested_outputs': request['outputs'], 'created_at': c.now()}
        row = w.append_record(directory, prepared, rows, 'execution-created', data)
        return derive([*rows, row], prepared, run)[identifier]


def begin(root: Path, run: str, authorization: str, *, effect: str, claim: str | None = None) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory, prepared, _, rows = w.load_run(root, run)
        request = w.find(rows, 'authorization', authorization)['data']['request']
        if request['operation'] != 'submit':
            return w.append_record(directory, prepared, rows, 'operation-start',
                {'authorization_sha256': authorization, 'effect': effect, 'claim': claim})
        state = by_authorization(rows, prepared, run, authorization)
        if state is None:
            state = claim_execution(root, run, authorization)
            directory, prepared, _, rows = w.load_run(root, run)
        if state['status'] != 'claimed':
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'Execution start already exists; inspect or resume it.',
                                  phase='execution', run=run)
        return w.append_record(directory, prepared, rows, 'execution-start',
            {'execution_id': state['execution_id'], 'claim': claim, 'effect': effect,
             'request_sha256': state['request_sha256'], 'started_at': c.now()})


def begin_step(root: Path, run: str, authorization: str, *, claim: str, step: str, operation: str,
               identifiers: list[dict] | None = None) -> dict:
    """Commit one exact external boundary after fresh consent and runtime checks."""
    import production_workflow as w
    from operation_context import current
    c.text(step, 'external step')
    if operation not in {'upload', 'send'}:
        raise ValueError('external operation must be upload or send')
    if identifiers is not None:
        if not isinstance(identifiers, list):
            raise ValueError('step identifiers must be a list')
        for item in identifiers:
            c.exact(item, {'field', 'value'}, 'step identifier')
            if not isinstance(item['field'], list) or not item['field']:
                raise ValueError('step identifier field must be a nonempty path')
    with store.transaction(root):
        c.recheck_roots()
        directory, prepared, _, rows = w.assert_current(root, run, force=True)
        request = w.find(rows, 'authorization', authorization)['data']['request']
        w._permission(root, prepared, rows, authorization, request['operation'], request['targets'], request['payload'])
        state = require_active(rows, prepared, run, authorization)
        if not any(row['sha256'] == claim and claim_owns(row, authorization) for row in rows):
            raise ProductionError('EXECUTION_CLAIM_REQUIRED', 'The external step needs its exact committed claim.', phase='before-send', run=run)
        if (state['status'] not in {'claimed', 'started'} or any(s['step'] == step for s in state['steps'])
                or (operation == 'send' and state['submissions'])):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This exact external step was already started.',
                phase='before-send', run=run,
                required_action='Use resume to recover the original result; never remove a claim to resend.')
        descriptor = prepared.get('runtime_snapshot')
        if descriptor is not None:
            import runtime_snapshot
            runtime_snapshot.read(runtime_snapshot.path(root, descriptor), descriptor, force_verify=True)
            runtime_snapshot.require_current(root, descriptor, run=run, force=True)
        if current():
            current().durable()
        if state['status'] == 'claimed':
            begin(root, run, authorization, effect='external-io', claim=claim)
            directory, prepared, _, rows = w.load_run(root, run)
        data = {'execution_id': state['execution_id'], 'claim': claim, 'step': step, 'operation': operation,
                'request_sha256': state['request_sha256'], 'started_at': c.now()}
        if identifiers is not None:
            data['identifiers'] = identifiers
        return w.append_record(directory, prepared, rows, 'external-step', data)


def record_effect(root: Path, run: str, authorization: str, *, claim: str,
                  step: str, usage: dict | None, evidence: list[dict]) -> dict:
    """Save a provider response once. Usage may be unknown without blocking capture."""
    import production_workflow as w
    validate_usage(usage)
    if not evidence:
        raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED', 'An effect receipt needs a saved response.', phase='result-capture')
    with store.transaction(root):
        directory, prepared, _, rows = w.load_run(root, run)
        state = require_active(rows, prepared, run, authorization)
        if not any(s['step'] == step and s['claim'] == claim for s in state['steps']):
            raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED', 'No exact external boundary supports this receipt.', phase='result-capture', run=run)
        data = {'execution_id': state['execution_id'], 'claim': claim, 'step': step, 'usage': usage, 'evidence': evidence}
        previous = state['effect_results'].get(step)
        if previous is not None:
            if previous != data:
                raise ProductionError('SETTLEMENT_CONFLICT', 'The saved receipt for this effect differs.', phase='result-capture', run=run)
            return next(row for row in rows if row['event'] == 'external-effect-result' and row['data'] == data)
        return w.append_record(directory, prepared, rows, 'external-effect-result', data)


def record_result(root: Path, run: str, authorization: str, *, outputs: int, cost: dict | None,
                  final: bool, evidence: list[dict]) -> dict:
    """Capture outputs monotonically; completion depends on results, not billing."""
    import production_workflow as w
    if type(outputs) is not int or outputs < 0 or type(final) is not bool or not evidence:
        raise ValueError('a result needs output count, completion state and saved evidence')
    if cost is not None:
        validate_cost(cost)
    with store.transaction(root):
        directory, prepared, _, rows = w.load_run(root, run)
        state = require_active(rows, prepared, run, authorization)
        if not state['submissions']:
            raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED', 'No send boundary supports this result.', phase='result-capture')
        data = {'execution_id': state['execution_id'], 'outputs': outputs, 'cost': cost, 'final': final, 'evidence': evidence}
        if state['result'] is not None:
            previous = next(row for row in rows if row['sha256'] == state['result'])
            if previous['data'] == data:
                return previous
            if (state['status'] == 'complete' or outputs < state['captured_outputs']
                    or (state['actual_cost'] is not None and state['actual_cost'] != cost)):
                raise ProductionError('SETTLEMENT_CONFLICT', 'Captured results cannot be erased or finalized differently.', phase='result-capture')
        return w.append_record(directory, prepared, rows, 'execution-result', data)


def _add_money(values: list[dict]) -> dict[str, str]:
    sums: dict[str, Decimal] = {}
    with localcontext() as context:
        context.prec = sum(len(v['amount']) for v in values) + 64
        for value in values:
            validate_cost(value)
            sums[value['currency']] = sums.get(value['currency'], Decimal(0)) + Decimal(value['amount'])
    return {currency: format(value, 'f') for currency, value in sorted(sums.items())}


def known_effect_costs(state: dict) -> list[dict]:
    return [{key: item['usage'][key] for key in ('currency', 'amount')}
            for item in state['effect_results'].values() if item['usage'] is not None and item['usage']['final']]


def effect_total(state: dict) -> tuple[dict | None, bool]:
    """A retrospective total exists only for complete, same-currency usage evidence."""
    costs = known_effect_costs(state)
    if not state['steps'] or len(costs) != len(state['steps']):
        return None, False
    sums = _add_money(costs)
    if len(sums) != 1:
        return None, False
    currency, amount = next(iter(sums.items()))
    return {'currency': currency, 'amount': amount}, True


def all_states(root: Path, *, task_id: str | None = None, grant: str | None = None, run: str | None = None,
               blocked: list[dict] | None = None) -> list[dict]:
    import production_workflow as w
    from production_diagnostics import from_exception
    output = []
    for item in store.runs(root, task_id=task_id):
        if run is not None and item['run_id'] != run:
            continue
        try:
            _, prepared, _, rows = w.load_run(root, item['run_id'])
            states = derive(rows, prepared, item['run_id'])
        except INSPECTION_ERRORS as exc:
            if blocked is None:
                raise
            blocked.append({**from_exception(exc, phase='execution-records'), 'run': item['run_id'], 'task_id': item['task_id']})
            continue
        output.extend(s for s in states.values() if grant is None or s['grant'] == grant)
    return output


def summary(root: Path, *, task_id: str | None = None, grant: str | None = None,
            run: str | None = None, isolate: bool = False) -> dict:
    """Read actual sends, captured outputs and provider usage from the same events."""
    diagnostics: list[dict] = []
    states = all_states(root, task_id=task_id, grant=grant, run=run, blocked=diagnostics if isolate else None)
    return {'complete': not diagnostics, 'diagnostics': diagnostics,
            'submissions': sum(s['submissions'] for s in states),
            'captured_outputs': sum(s['captured_outputs'] for s in states),
            'reported_cost': _add_money([v for s in states for v in known_effect_costs(s)]),
            'usage_complete': all(len(known_effect_costs(s)) == len(s['steps']) for s in states),
            'executions': states}


def completion_tail(records: list[dict], prepared: dict, run: str) -> None:
    derive(records, prepared, run)
    completions = [row for row in records if row['event'] == 'completion']
    if len(completions) > 1:
        raise ProductionError('EVENT_CHAIN_CORRUPT', 'The run has more than one completion.', phase='integrity')
    if completions and any(row['event'] not in {'execution-result', 'external-effect-result'}
            for row in records if row['sequence'] > completions[0]['sequence']):
        raise ProductionError('EVENT_CHAIN_CORRUPT', 'Only received result evidence may follow completion.', phase='integrity')


def commit_effect(root: Path, run: str, event: str, data: dict, tokens: list[str], *, effect: str) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory, prepared, _, rows = w.load_run(root, run)
        previous = [row for row in rows if row['event'] == event and row['data'] == data]
        if previous:
            return previous[-1]
        for authorization in tokens:
            begin(root, run, authorization, effect=effect)
        directory, prepared, _, rows = w.load_run(root, run)
        return w.append_record(directory, prepared, rows, event, data)
