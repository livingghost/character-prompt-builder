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
from owned_json import FrozenList, freeze
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


class EventHistory(FrozenList):
    """An immutable event history carrying its already derived lifecycle."""

    __slots__ = ('lifecycle',)

    def __new__(cls, rows, lifecycle):
        result = list.__new__(cls)
        list.__init__(result, rows)
        object.__setattr__(result, 'lifecycle', lifecycle)
        return result

    def __init__(self, rows, lifecycle):
        pass

    def __setattr__(self, name, value):
        raise TypeError('an event history is read-only')

    def __delattr__(self, name):
        raise TypeError('an event history is read-only')


class ReplayState:
    """The parsed lifecycle and lookup indices of one ordered event history.

    Each committed row advances this state once. Append validation reads the
    same state without changing it; only the committed row advances it. The
    owner retains this value internally, alongside its verified event history.
    """
    __slots__ = ('prepared', 'run', 'rows', 'executions', '_events', '_latest', '_reviews',
                 '_decisions', '_adoption_tokens', '_operation_tokens', '_operation_starts',
                 '_adoption_results', '_steps', '_delete_indices', '_delete_limits', '_send_steps',
                 '_failed_uploads', '_execution_authorizations', 'closed', '_sealed')

    def __setattr__(self, name, value):
        if getattr(self, '_sealed', False):
            raise TypeError('a verified lifecycle state is read-only')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if getattr(self, '_sealed', False):
            raise TypeError('a verified lifecycle state is read-only')
        object.__delattr__(self, name)

    def __init__(self, prepared: dict, run: str):
        self._sealed = False
        self.prepared = prepared
        self.run = run
        self.rows: list[dict] = []
        self.executions: dict[str, dict] = {}
        self._events: dict[tuple[str, str], dict] = {}
        self._latest: dict[str, dict] = {}
        self._reviews: dict[str, dict] = {}
        self._decisions: dict[str, dict] = {}
        self._adoption_tokens: set[str] = set()
        self._operation_tokens: set[str] = set()
        self._operation_starts: dict[tuple[str, str | None], int] = {}
        self._adoption_results: set[str] = set()
        self._steps: dict[str, dict[str, dict]] = {}
        self._delete_indices: dict[str, set[int]] = {}
        self._delete_limits: dict[str, int] = {}
        self._send_steps: dict[str, str] = {}
        self._failed_uploads: set[str] = set()
        self._execution_authorizations: dict[str, str] = {}
        self.closed: str | None = None

    def seal(self) -> ReplayState:
        """Publish this replayed state as immutable values, including all indexes.

        The replay owner alone advances a mutable state. Once published, its
        event rows and index entries share the same frozen objects. A write
        produces a new event history while existing readers retain their observation.
        """
        if self._sealed:
            return self
        values = freeze({name: getattr(self, name) for name in self.__slots__ if name != '_sealed'})
        for name, value in values.items():
            setattr(self, name, value)
        self.rows = EventHistory(self.rows, self)
        self._sealed = True
        return self

    @property
    def tail(self) -> str | None:
        return self.rows[-1]['sha256'] if self.rows else None

    def find(self, event: str, identifier: str | None = None) -> dict:
        row = self._latest.get(event) if identifier is None else self._events.get((event, identifier))
        if row is None:
            if event == 'handoff':
                raise ProductionError('HANDOFF_REQUIRED', 'No recorded handoff gives this run its recipient.', phase='handoff',
                                      required_action='Record the handoff of the consumer to its recipient under an exact '
                                                      'direction authorization; execute records a dispatcher handoff itself.')
            raise ValueError('missing ' + event + ' evidence')
        return row

    def latest(self, event: str) -> dict | None:
        return self._latest.get(event)

    def review(self, candidate: str) -> dict | None:
        return self._reviews.get(candidate)

    def decision(self, candidate: str) -> dict | None:
        return self._decisions.get(candidate)

    def selection_context(self) -> list[dict]:
        """The exact facts needed by the selection owner's current-state policy."""
        selected = self._latest.get('selection')
        if selected is None:
            return []
        chosen = selected['data']['selection']
        rows = [selected, *self.closure_context()]
        for row in (self._reviews.get(chosen['candidate']),
                    self._decisions.get(chosen['candidate']),
                    self._events.get(('authorization', chosen['authorization']))):
            if row is not None and row is not selected:
                rows.append(row)
        return sorted(rows, key=lambda row: row['sequence'])

    def closure_context(self) -> list[dict]:
        return [self._latest[event] for event in ('completion', 'abandoned') if event in self._latest]

    def execution_for(self, authorization: str) -> dict | None:
        identifier = self._execution_authorizations.get(authorization)
        return self.executions.get(identifier)

    def _invalid_execution(self, message: str) -> None:
        raise ProductionError('EXECUTION_RECORD_CORRUPT', message, phase='integrity', run=self.run)

    def _cleanup_ready(self, identifier: str, state: dict) -> bool:
        send = self._send_steps.get(identifier)
        if send is not None:
            return (state['status'] == 'complete'
                    or state['effect_results'].get(send, {}).get('outcome') in NO_EFFECT_OUTCOMES)
        return identifier in self._failed_uploads

    def check_execution(self, event: str, data: dict) -> None:
        """Check an execution transition without altering the verified state."""
        invalid = self._invalid_execution
        if event == 'execution-created':
            identifier = data['execution_id']
            authorization = self._events.get(('authorization', data['authorization_sha256']))
            request = authorization['data']['request'] if authorization is not None else None
            if self.executions or request is None:
                invalid('Execution needs one unique owner and its prior authorization.')
            if (request['operation'] != 'submit' or data['requested_outputs'] != request['outputs']
                    or data['grant'] != request['grant'] or data['actor'] != request['actor']
                    or data['task_id'] != self.prepared['task']['task_id']
                    or data['request_sha256'] != request['payload'].get('request_sha256', c.content_id(request['payload']))):
                invalid('Execution identity differs from the exact authorized submission.')
            return
        if event not in EVENTS - {'operation-start'}:
            return
        identifier = data.get('execution_id')
        state = self.executions.get(identifier)
        if state is None:
            invalid('Execution transition has no prior owner.')
        if event == 'execution-start':
            if state['status'] != 'claimed':
                invalid('Execution was started twice.')
        elif event == 'external-step':
            cleanup = data['operation'] == 'delete'
            if ((not cleanup and state['status'] != 'started')
                    or (cleanup and not self._cleanup_ready(identifier, state))
                    or data['step'] in self._steps[identifier]):
                invalid('An external step is repeated or outside its active execution.')
            if data['request_sha256'] != state['request_sha256']:
                invalid('External step belongs to a different request.')
            if cleanup:
                index = data.get('upload_index')
                if type(index) is not int or not 0 <= index < self._delete_limits[identifier]:
                    invalid('Cleanup names an input outside its exact submission authorization.')
                receipt = state['effect_results'].get(f'upload:{index}')
                if (receipt is None or 'outcome' in receipt or not any(
                        item['sha256'] == data.get('upload_receipt_sha256') for item in receipt['evidence'])):
                    invalid('Cleanup has no owned upload receipt.')
                if data['step'] != f'delete:{index}' or index in self._delete_indices[identifier]:
                    invalid('An uploaded input has only one deletion boundary.')
            if data['operation'] == 'send' and state['submissions']:
                invalid('An execution has more than one send boundary.')
        elif event == 'external-effect-result':
            step = data.get('step')
            boundary = self._steps[identifier].get(step)
            if boundary is None or boundary['claim'] != data.get('claim') or step in state['effect_results']:
                invalid('External result has no unique matching boundary.')
            validate_usage(data.get('usage'))
            if not data.get('evidence'):
                invalid('External result lacks its saved response.')
            if 'outcome' in data and (data['outcome'] not in NO_EFFECT_OUTCOMES or data['usage'] is not None):
                invalid('A no-effect result has an unknown outcome or a charge.')
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

    def _advance_execution(self, row: dict) -> None:
        event, data = row['event'], row['data']
        identifier = data.get('execution_id')
        if event == 'execution-created':
            request = self.find('authorization', data['authorization_sha256'])['data']['request']
            effects = request['payload'].get('external_effects', [])
            self.executions[identifier] = {**data, 'run': self.run, 'created_event': row['sha256'],
                'status': 'claimed', 'start': None, 'effect': None, 'steps': [],
                'effect_results': {}, 'result': None, 'actual_cost': None,
                'captured_outputs': 0, 'submissions': 0, 'authorized_effects': effects}
            self._steps[identifier] = {}
            self._delete_indices[identifier] = set()
            self._delete_limits[identifier] = next((item['count'] for item in effects if item['operation'] == 'delete'), 0)
            self._execution_authorizations[data['authorization_sha256']] = identifier
        elif event == 'execution-start':
            self.executions[identifier].update(status='started', start=row['sha256'], effect=data['effect'], claim=data.get('claim'))
        elif event == 'external-step':
            state = self.executions[identifier]
            state['steps'].append(data)
            self._steps[identifier][data['step']] = data
            if data['operation'] == 'send':
                self._send_steps[identifier] = data['step']
                state['submissions'] += 1
            elif data['operation'] == 'delete':
                self._delete_indices[identifier].add(data['upload_index'])
        elif event == 'external-effect-result':
            self.executions[identifier]['effect_results'][data['step']] = data
            if (self._steps[identifier][data['step']]['operation'] == 'upload'
                    and data.get('outcome') in NO_EFFECT_OUTCOMES):
                self._failed_uploads.add(identifier)
        elif event == 'execution-result':
            self.executions[identifier].update(result=row['sha256'], captured_outputs=data['outputs'], actual_cost=data['cost'],
                                               status='complete' if data['final'] else 'captured')

    def advance(self, row: dict) -> None:
        """Retain a row after its transition has passed the owning policy."""
        if self._sealed:
            raise TypeError('a verified lifecycle state is read-only')
        self._advance_execution(row)
        event, data = row['event'], row['data']
        self.rows.append(row)
        self._events[(event, row['sha256'])] = row
        self._latest[event] = row
        if event in {'completion', 'abandoned'}:
            self.closed = event
        elif event == 'review':
            self._reviews[data['candidate']] = row
        elif event in {'selection', 'disposition'}:
            self._decisions[data[event]['candidate']] = row
        elif event == 'adoption-claim':
            self._adoption_tokens.update(data['authorizations'])
        elif event == 'operation-start':
            token = data['authorization_sha256']
            self._operation_tokens.add(token)
            key = (token, data['claim'])
            self._operation_starts[key] = self._operation_starts.get(key, 0) + 1
        elif event == 'adoption-result':
            self._adoption_results.add(data['claim'])


def _indexed(records: list[dict] | ReplayState, prepared: dict, run: str) -> ReplayState:
    if isinstance(records, EventHistory) and records.lifecycle.prepared is prepared:
        records = records.lifecycle
    if isinstance(records, ReplayState):
        if records.run != run:
            raise ValueError('replay state belongs to another run')
        return records
    state = ReplayState(prepared, run)
    for row in records:
        state.check_execution(row['event'], row['data'])
        state.advance(row)
    return state


def derive(records: list[dict] | ReplayState, prepared: dict, run: str) -> dict[str, dict]:
    """Project execution accounting from the same parsed lifecycle state."""
    return _indexed(records, prepared, run).executions


def cleanup_ready(state: dict) -> bool:
    """Deletion waits for captured terminal outputs or a proven no-generation outcome."""
    send = next((item for item in state['steps'] if item['operation'] == 'send'), None)
    if send is not None:
        return (state['status'] == 'complete'
                or state['effect_results'].get(send['step'], {}).get('outcome') in NO_EFFECT_OUTCOMES)
    return any(item['operation'] == 'upload' and
               state['effect_results'].get(item['step'], {}).get('outcome') in NO_EFFECT_OUTCOMES
               for item in state['steps'])


def by_authorization(records: list[dict] | ReplayState, prepared: dict, run: str, authorization: str) -> dict | None:
    return _indexed(records, prepared, run).execution_for(authorization)


def claim_owns(record: dict, token: str) -> bool:
    return record['event'] in CLAIM_EVENTS and token in record['data'].get('authorizations', [])


def require_operation(records: list[dict] | ReplayState, prepared: dict, run: str,
                      operation: str, targets: list[str], payload: dict) -> None:
    """Closing production preserves its selected artifact for a separate adoption.

    This checks the operation's lifecycle, not its current permission. Writers
    still check the current grant immediately before an effect; replay checks
    the exact recorded links without renewing historical permission.
    """
    import production_workflow as w
    state = _indexed(records, prepared, run)
    if operation == 'adopt':
        c.exact(payload, {'candidate', 'review', 'character', 'iteration', 'approval_sha256',
                          'registration_sha256', 'pack_dir'}, 'adoption payload')
        if targets not in (['canon:sheet'], ['canon:catalog']):
            raise ValueError('adoption requires one exact sheet or catalog target')
        for key in ('candidate', 'review', 'approval_sha256'):
            c.sha(payload[key])
        for key in ('character', 'iteration'):
            c.text(payload[key], 'adoption ' + key)
        if targets == ['canon:sheet']:
            if payload['registration_sha256'] is not None or payload['pack_dir'] is not None:
                raise ValueError('sheet adoption cannot register a catalog pack')
        else:
            c.sha(payload['registration_sha256'])
            c.text(payload['pack_dir'], 'catalog pack directory')
        selected = w.require_selected(prepared, state.selection_context(), payload['candidate'], run=run)
        if payload['review'] != selected['data']['selection']['review']:
            raise ValueError('adoption must use the current selected review')
        return
    closed = state.closure_context()
    w.require_mutable(closed)
    w.require_open_task(closed, run)


def _adoption_approval(state: ReplayState, request: dict, payload: dict, approval: dict) -> None:
    import adoption_workflow
    candidate = state.find('candidate', payload['candidate'])
    target = candidate['data']['files'][0]['sha256']
    adoption_workflow.validate_approval(approval, payload['character'],
        {'iteration_id': payload['iteration'], 'slot': approval['slot'], 'result': {'sha256': target}})
    if (c.content_id(approval) != payload['approval_sha256'] or approval['by'] != request['actor']
            or request['targets'] != ['canon:' + approval['scope']]):
        raise ValueError('adoption approval differs from its exact authorized artifact and scope')


def _validate_disposition(state: ReplayState, prepared: dict, run: str, data: dict) -> None:
    """Bind a candidate decision to its input, review and preceding decision.

    Nonselection records the disposition of retained output. It changes neither
    the run's completed delivery nor its evaluation, and grants no new work.
    """
    import production_workflow as w
    c.exact(data, {'disposition', 'files', 'previous_decision'}, 'candidate disposition event')
    decision = data['disposition']
    w.schema_check(decision, 'disposition')
    for name in ('actor', 'reason'):
        c.text(decision[name], name)
    if decision['input_sha256'] != prepared['input_sha256']:
        raise ValueError('disposition belongs to another input')
    state.find('candidate', decision['candidate'])
    if decision['review'] is not None:
        reviewed = state._reviews.get(decision['candidate'])
        if reviewed is None or decision['review'] != reviewed['sha256']:
            raise ProductionError('REVIEW_MISMATCH', 'Disposition must cite the actual latest review.',
                                  phase='disposition', run=run)
    previous = state._decisions.get(decision['candidate'])
    if data['previous_decision'] != (previous['sha256'] if previous else None):
        raise ValueError('disposition does not follow the candidate\'s previous decision')


def validate_transition(records: list[dict] | ReplayState, prepared: dict, run: str, event: str, data: dict, *,
                        read_object) -> None:
    """Check append and replay against the same accumulated state and indices."""
    import production_workflow as w
    state = _indexed(records, prepared, run)
    adoption = False
    if event == 'authorization':
        request = data['request']
        require_operation(state, prepared, run, request['operation'], request['targets'], request['payload'])
        adoption = request['operation'] == 'adopt'
    elif event == 'disposition':
        _validate_disposition(state, prepared, run, data)
    elif event == 'adoption-claim':
        c.exact(data, {'intent', 'files', 'authorizations'}, 'adoption claim')
        intent = data['intent']
        c.exact(intent, {'operation', 'targets', 'payload'}, 'adoption intent')
        if (intent['operation'] != 'adopt' or not isinstance(data['authorizations'], list)
                or len(data['authorizations']) != 1 or not isinstance(data['files'], list) or len(data['files']) != 1):
            raise ValueError('adoption needs its one exact authorization and saved approval')
        require_operation(state, prepared, run, **intent)
        token = data['authorizations'][0]
        c.sha(token)
        request = state.find('authorization', token)['data']['request']
        if intent != {key: request[key] for key in ('operation', 'targets', 'payload')}:
            raise ValueError('adoption claim differs from its prior authorization')
        if token in state._adoption_tokens:
            raise ValueError('an adoption authorization owns only one claim')
        _adoption_approval(state, request, intent['payload'], c.decode(read_object(data['files'][0]['sha256'])))
        adoption = True
    elif event == 'operation-start':
        c.exact(data, {'authorization_sha256', 'effect', 'claim'}, 'operation start')
        token = data['authorization_sha256']
        c.sha(token)
        request = state.find('authorization', token)['data']['request']
        if request['operation'] == 'submit':
            raise ValueError('submission starts its owned execution, not a local operation')
        require_operation(state, prepared, run, request['operation'], request['targets'], request['payload'])
        if request['operation'] == 'adopt':
            c.sha(data['claim'])
            claim = state.find('adoption-claim', data['claim'])
            if data['effect'] != 'local-action' or not claim_owns(claim, token):
                raise ValueError('adoption start needs its exact prior claim and local effect')
            if token in state._operation_tokens:
                raise ValueError('an adoption claim starts only once')
            adoption = True
    elif event == 'adoption-result':
        c.exact(data, {'claim', 'result'}, 'adoption result')
        c.sha(data['claim'])
        claim = state.find('adoption-claim', data['claim'])
        token = claim['data']['authorizations'][0]
        if state._operation_starts.get((token, data['claim']), 0) != 1 or data['claim'] in state._adoption_results:
            raise ValueError('adoption result needs its unique prior start and no previous result')
        request = state.find('authorization', token)['data']['request']
        payload, result = claim['data']['intent']['payload'], data['result']
        if not isinstance(result, dict):
            raise ValueError('adoption result must retain its completed owner receipt')
        approval = result['approval']
        _adoption_approval(state, request, payload, approval)
        if (result.get('ok') is not True or result.get('artifact_type') != 'studio-adoption'
                or result.get('production_claim') != data['claim'] or result['next_action'] is not None
                or result.get('status') != ('catalog-registered' if approval['scope'] == 'catalog' else 'sheet-bound')):
            raise ValueError('adoption result differs from its exact authorized artifact and approval')
        adoption = True
    state.check_execution(event, data)
    closed = state.closed
    if closed is None or adoption:
        return
    if closed == 'completion' and event == 'disposition' and data['disposition']['disposition'] == 'not_selected':
        # Retiring a retained candidate leaves the completed delivery intact.
        # Pending would reopen candidate attention and needs an open run.
        return
    if (event in {'external-effect-result', 'execution-result', 'cleanup-observation'}
            or (event == 'external-step' and data.get('operation') == 'delete')):
        return
    # Abandoning work does not discard a response from an execution already
    # started. Its capture remains evidence, without reopening review/selection.
    if (closed == 'abandoned' and event in {'dispatch-results', 'candidate', 'capture-status',
                                          'execution-outcome', 'image-edit-output'}
            and 'execution-start' in state._latest):
        return
    if closed == 'completion':
        w.require_mutable(state.closure_context())
    w.require_open_task(state.closure_context(), run)


def require_active(records: list[dict], prepared: dict, run: str, authorization: str) -> dict:
    state = by_authorization(records, prepared, run, authorization)
    if state is None:
        raise ProductionError('EXECUTION_CLAIM_REQUIRED', 'The submission has no durable execution owner.',
                              phase='execution', run=run)
    return state


def claim_execution(root: Path, run: str, authorization: str) -> dict:
    import production_workflow as w
    with store.transaction(root):
        loaded = w.assert_current(root, run)
        authority = w.current_authority(root, loaded.prepared)
        return _claim_execution_from(root, loaded, authority, authorization)


def _claim_execution_from(root: Path, loaded, authority, authorization: str) -> dict:
    """Claim from the current inputs and authority acquired by this transaction."""
    import production_workflow as w
    directory, prepared, _, rows = loaded
    run = prepared['run']
    request = w.find(rows, 'authorization', authorization)['data']['request']
    w._permission(root, prepared, rows, authorization, request['operation'], request['targets'], request['payload'],
                  authority=authority, loaded=loaded)
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
            'outcome_actors': sorted({request['actor'], authority.document['issuer']}),
            'request_sha256': request['payload'].get('request_sha256', c.content_id(request['payload'])),
            'requested_outputs': request['outputs'], 'created_at': c.now()}
    w.append_record(directory, prepared, rows, 'execution-created', data)
    return w.read_run(root, run).lifecycle.executions[identifier]


def begin(root: Path, run: str, authorization: str, *, effect: str, claim: str | None = None) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory, prepared, _, rows = w.read_run(root, run)
        request = w.find(rows, 'authorization', authorization)['data']['request']
        if request['operation'] != 'submit':
            w._permission(root, prepared, rows, authorization,
                          request['operation'], request['targets'], request['payload'])
            return w.append_record(directory, prepared, rows, 'operation-start',
                {'authorization_sha256': authorization, 'effect': effect, 'claim': claim})
        state = by_authorization(rows, prepared, run, authorization)
        if state is None:
            state = claim_execution(root, run, authorization)
            directory, prepared, _, rows = w.read_run(root, run)
        if state['status'] != 'claimed':
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'Execution start already exists; inspect or resume it.',
                                  phase='execution', run=run)
        return w.append_record(directory, prepared, rows, 'execution-start',
            {'execution_id': state['execution_id'], 'claim': claim, 'effect': effect,
             'request_sha256': state['request_sha256'], 'started_at': c.now()})


def begin_step(root: Path, run: str, authorization: str, *, claim: str, step: str, operation: str,
               identifiers: list[dict] | None = None, previous_runtime=None) -> dict:
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
        directory, prepared, _, rows = w.assert_current(root, run, force=True,previous_runtime=previous_runtime)
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
        if current():
            current().durable()
        if state['status'] == 'claimed':
            begin(root, run, authorization, effect='external-io', claim=claim)
            directory, prepared, _, rows = w.read_run(root, run)
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
        directory, prepared, _, rows = w.read_run(root, run)
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


def begin_cleanup_step(root: Path, run: str, authorization: str, *, claim: str,
                       upload_index: int, provider_id: str, request: dict) -> dict:
    """Delete a run-owned upload under its saved submit scope, without reopening generation.

    The original permission includes this lifecycle operation. Source-file
    freshness and a new submission approval cannot alter that recorded scope.
    The exact delete request and upload response are durable before I/O.
    """
    import production_workflow as w
    import production_request
    from operation_context import current
    with store.transaction(root):
        c.recheck_roots()
        directory, prepared, _, rows = w.read_run(root, run)
        authorization_row = w.find(rows, 'authorization', authorization)
        authorized = authorization_row['data']['request']
        production_request.validate_payload(authorized['payload'])
        state = require_active(rows, prepared, run, authorization)
        if (authorized['operation'] != 'submit' or not cleanup_ready(state)
                or not any(row['sha256'] == claim and claim_owns(row, authorization) for row in rows)):
            raise ProductionError('CLEANUP_NOT_READY', 'Cleanup needs its exact owned execution and a known terminal result.',
                                  phase='input-cleanup', run=run)
        limit = next((item['count'] for item in authorized['payload']['external_effects']
                      if item['operation'] == 'delete'), 0)
        if type(upload_index) is not int or not 0 <= upload_index < limit:
            raise ProductionError('AUTHORIZATION_MISMATCH', 'No delete scope covers this uploaded input.', phase='input-cleanup', run=run)
        upload = state['effect_results'].get(f'upload:{upload_index}')
        if upload is None or 'outcome' in upload or len(upload['evidence']) != 1:
            raise ProductionError('CLEANUP_OWNERSHIP_REQUIRED', 'A successful upload receipt from this run is required.',
                                  phase='input-cleanup', run=run)
        receipt_ref = upload['evidence'][0]
        receipt = c.decode(c.object_read(directory, receipt_ref['sha256']))
        if receipt['index'] != upload_index or receipt['provider_id'] != provider_id:
            raise ProductionError('CLEANUP_OWNERSHIP_REQUIRED', 'The delete target differs from this run\'s upload response.',
                                  phase='input-cleanup', run=run)
        c.exact(request, {'path', 'sha256', 'size'}, 'delete request evidence')
        raw = c.object_read(directory, request['sha256'])
        if len(raw) != request['size'] or not isinstance(c.decode(raw), dict):
            raise ValueError('delete request evidence is not the saved request object')
        step = f'delete:{upload_index}'
        data = {'execution_id': state['execution_id'], 'claim': claim, 'step': step, 'operation': 'delete',
                'request_sha256': state['request_sha256'], 'started_at': c.now(),
                'upload_index': upload_index, 'provider_id': provider_id,
                'upload_receipt_sha256': receipt_ref['sha256'], 'delete_request_sha256': request['sha256'],
                'evidence': [request]}
        # Each owned input has one deletion request. A definitive failure is
        # terminal; an unknown outcome is looked up by that original request.
        _indexed(rows, prepared, run).check_execution('external-step', data)
        if current():
            current().durable()
        return w.append_record(directory, prepared, rows, 'external-step', data)


def record_result(root: Path, run: str, authorization: str, *, outputs: int, cost: dict | None,
                  final: bool, evidence: list[dict]) -> dict:
    """Capture outputs monotonically; completion depends on results, not billing."""
    import production_workflow as w
    if type(outputs) is not int or outputs < 0 or type(final) is not bool or not evidence:
        raise ValueError('a result needs output count, completion state and saved evidence')
    if cost is not None:
        validate_cost(cost)
    with store.transaction(root):
        directory, prepared, _, rows = w.read_run(root, run)
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


def effect_total(state: dict, *, operations: set[str] | None = None) -> tuple[dict | None, bool]:
    """A retrospective total exists only for complete, same-currency usage evidence."""
    if operations is not None:
        steps = [item for item in state['steps'] if item['operation'] in operations]
        names = {item['step'] for item in steps}
        state = {**state, 'steps': steps,
                 'effect_results': {name: result for name, result in state['effect_results'].items() if name in names}}
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
            _, prepared, _, rows = w.read_run(root, item['run_id'])
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
    return summarize_states(states, diagnostics=diagnostics)


def summarize_states(states, *, diagnostics: list[dict] | None = None) -> dict:
    """Project accounting from already acquired lifecycle states without I/O."""
    states = list(states)
    diagnostics = [] if diagnostics is None else list(diagnostics)
    return {'complete': not diagnostics, 'diagnostics': diagnostics,
            'submissions': sum(s['submissions'] for s in states),
            'captured_outputs': sum(s['captured_outputs'] for s in states),
            'reported_cost': _add_money([v for s in states for v in known_effect_costs(s)]),
            'usage_complete': all(len(known_effect_costs(s)) == len(s['steps']) for s in states),
            'executions': states}


def completion_tail(records: list[dict], prepared: dict, run: str, *, read_object) -> ReplayState:
    """Replay each event once, retaining the verified state for later consumers."""
    state = ReplayState(prepared, run)
    for row in records:
        try:
            validate_transition(state, prepared, run, row['event'], row['data'], read_object=read_object)
            state.advance(row)
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ProductionError) and exc.diagnostic.code == 'EXECUTION_RECORD_CORRUPT':
                raise
            raise ProductionError('EVENT_CHAIN_CORRUPT', 'Invalid recorded lifecycle transition: ' + str(exc),
                                  phase='integrity', run=run, event=row['sha256']) from exc
    return state


def commit_effect(root: Path, run: str, event: str, data: dict, tokens: list[str], *, effect: str) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory, prepared, _, rows = w.read_run(root, run)
        previous = [row for row in rows if row['event'] == event and row['data'] == data]
        if previous:
            return previous[-1]
        for authorization in tokens:
            begin(root, run, authorization, effect=effect)
        directory, prepared, _, rows = w.read_run(root, run)
        return w.append_record(directory, prepared, rows, event, data)
