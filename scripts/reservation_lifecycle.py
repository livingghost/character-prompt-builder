"""Execution-bound reservations, durable effect boundaries and Decimal accounting.

Authorization receipts are not budget reservations. Only a distinct external
request reserves one use. Every transition is stored in the Production database;
all budget views derive from those same events.
"""
from __future__ import annotations
from decimal import Decimal, localcontext
from pathlib import Path
import sqlite3
from typing import Any
import execution_contract as c
import production_store as store
from production_diagnostics import ProductionError
from pack_manager import generate_uuid7

EVENTS={'reservation-created','reservation-start','reservation-release','reservation-settled','external-step','external-effect-result','operation-start'}
CLAIM_EVENTS={'dispatch-claim','external-claim','adoption-claim','image-edit-claim'}


def derive(records: list[dict], prepared: dict, run: str) -> dict[str,dict]:
    states={};authorizations={};seen_steps=set()
    for row in records:
        data=row['data'];event=row['event']
        if event=='authorization':authorizations[row['sha256']]=data['request']
        elif event=='reservation-created':
            identifier=data['reservation_id']
            if identifier in states or data['authorization_sha256'] not in authorizations:
                raise ProductionError('RESERVATION_CORRUPT','Reservation identity or authorization is invalid.',phase='integrity',run=run)
            request=authorizations[data['authorization_sha256']]
            if request['operation']!='submit' or data['amounts']['uses']!=1 or data['amounts']['outputs']!=request['outputs'] or data['amounts']['cost']!=request['cost']:
                raise ProductionError('RESERVATION_CORRUPT','Reserved amounts differ from the exact submission.',phase='integrity',run=run)
            states[identifier]={**data,'run':run,'created_event':row['sha256'],'status':'reserved','start':None,'effect':None,
                                'steps':[],'effect_results':{},'release':None,'settlement':None,'actual_cost':None,'captured_outputs':0,'consumed_uses':0}
        elif event in EVENTS-{'operation-start'}:
            identifier=data.get('reservation_id');state=states.get(identifier)
            if state is None:raise ProductionError('RESERVATION_CORRUPT','Reservation transition has no prior creation.',phase='integrity',run=run)
            if event=='reservation-start':
                if state['status']!='reserved':raise ProductionError('RESERVATION_CORRUPT','Reservation was started twice.',phase='integrity')
                state.update(status='started',start=row['sha256'],effect=data['effect'],claim=data.get('claim'))
            elif event=='external-step':
                if state['status'] not in {'started','partially_settled'}:raise ProductionError('RESERVATION_CORRUPT','External step is outside its live reservation.',phase='integrity')
                key=(identifier,data['step'])
                if key in seen_steps:raise ProductionError('RESERVATION_CORRUPT','An external step was repeated.',phase='integrity')
                seen_steps.add(key);state['steps'].append(data)
            elif event=='external-effect-result':
                step=data.get('step')
                boundary=next((item for item in state['steps'] if item['step']==step),None)
                if boundary is None or boundary['claim']!=data.get('claim') or step in state['effect_results']:
                    raise ProductionError('RESERVATION_CORRUPT','External result has no unique matching boundary.',phase='integrity',run=run)
                validate_usage(data.get('usage'))
                if not data.get('evidence'):
                    raise ProductionError('RESERVATION_CORRUPT','External result lacks its saved response.',phase='integrity',run=run)
                if 'outcome' in data and (data['outcome'] not in NO_EFFECT_OUTCOMES or data['usage'] is not None):
                    raise ProductionError('RESERVATION_CORRUPT','A no-effect result names an unknown outcome or a charge.',phase='integrity',run=run)
                state['effect_results'][step]=data
            elif event=='reservation-release':
                if not releasable(state):raise ProductionError('RESERVATION_CORRUPT','Release follows an external-effect boundary.',phase='integrity')
                state.update(status='released',release=row['sha256'])
            elif event=='reservation-settled':
                if state['status']=='released':raise ProductionError('RESERVATION_CORRUPT','A released reservation was settled.',phase='integrity')
                if data['outputs']<state['captured_outputs'] or data['uses']<state['consumed_uses']:
                    raise ProductionError('RESERVATION_CORRUPT','Settlement cannot erase recorded actuals.',phase='integrity')
                if state['actual_cost'] is not None and data['cost']!=state['actual_cost']:
                    raise ProductionError('RESERVATION_CORRUPT','Confirmed cost was changed by a second settlement.',phase='integrity')
                state.update(settlement=row['sha256'],captured_outputs=data['outputs'],consumed_uses=data['uses'],actual_cost=data['cost'],
                             status='settled' if data['final'] and data['cost'] is not None else 'partially_settled')
    return states


def validate_usage(usage: Any) -> None:
    if usage is None:
        return
    from production_permissions import cost
    c.exact(usage,{'currency','amount','final'},'external-effect usage')
    cost({'currency':usage['currency'],'amount':usage['amount']})
    if type(usage['final']) is not bool:
        raise ValueError('external-effect usage final must be a boolean')


def known_effect_costs(state: dict) -> list[dict]:
    return [{'currency':item['usage']['currency'],'amount':item['usage']['amount']}
            for item in state['effect_results'].values()
            if item['usage'] is not None and item['usage']['final']]


def effect_total(state: dict) -> tuple[dict | None, bool]:
    """Only a complete set of final, same-currency effect receipts closes billing."""
    if not state['steps'] or any(item['step'] not in state['effect_results'] for item in state['steps']):
        return None,False
    costs=known_effect_costs(state)
    if len(costs)!=len(state['steps']):
        return None,False
    sums=_add_money(costs)
    if len(sums)!=1:
        return None,False
    currency,amount=next(iter(sums.items()))
    return {'currency':currency,'amount':amount},True


def outstanding_cost(state: dict) -> dict | None:
    quote=state['amounts']['cost']
    if state['actual_cost'] is not None or quote is None:
        return None
    known=_add_money(known_effect_costs(state))
    with localcontext() as context:
        context.prec=max([len(quote['amount'])]+[len(value) for value in known.values()]+[64])+16
        left=max(Decimal('0'),Decimal(quote['amount'])-Decimal(known.get(quote['currency'],'0')))
    return {'currency':quote['currency'],'amount':format(left,'f')}


def record_effect(root: Path, run: str, authorization: str, *, claim: str,
                  step: str, usage: dict | None, evidence: list[dict]) -> dict:
    """A durable response for one external step; idempotent, never inferred from a quote."""
    import production_workflow as w
    validate_usage(usage)
    if not evidence:
        raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED','An effect receipt requires the saved response.',phase='settlement')
    with store.transaction(root):
        directory,prepared,_,rows=w.load_run(root,run)
        state=require_active(rows,prepared,run,authorization)
        boundary=next((item for item in state['steps'] if item['step']==step and item['claim']==claim),None)
        if boundary is None:
            raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED','No exact external boundary supports this receipt.',phase='settlement',run=run)
        data={'reservation_id':state['reservation_id'],'claim':claim,'step':step,
              'usage':usage,'evidence':evidence}
        previous=state['effect_results'].get(step)
        if previous is not None:
            if previous!=data:
                raise ProductionError('SETTLEMENT_CONFLICT','The saved receipt for this effect differs.',phase='settlement',run=run)
            return next(row for row in rows if row['event']=='external-effect-result' and row['data']==data)
        return w.append_record(directory,prepared,rows,'external-effect-result',data)


def by_authorization(records: list[dict], prepared: dict, run: str, authorization: str) -> dict | None:
    matches=[state for state in derive(records,prepared,run).values() if state['authorization_sha256']==authorization]
    if len(matches)>1:raise ProductionError('RESERVATION_CORRUPT','One authorization owns several reservations.',phase='integrity')
    return matches[0] if matches else None


def claim_owns(record: dict, token: str) -> bool:
    return record['event'] in CLAIM_EVENTS and token in record['data'].get('authorizations',[])


def require_active(records: list[dict], prepared: dict, run: str, authorization: str) -> dict:
    state=by_authorization(records,prepared,run,authorization)
    if state is None:
        raise ProductionError('RESERVATION_REQUIRED','This submission has no execution-bound reservation.',phase='execution',run=run)
    if state['status']=='released':
        raise ProductionError('RESERVATION_NOT_RELEASABLE','Reservation is already released; use a new run for another execution.',phase='execution',run=run)
    return state


NO_EFFECT_OUTCOMES={'rejected','not_executed'}


def releasable(state: dict) -> bool:
    """A reservation is releasable while no started step can have had an external effect.

    Recording an external boundary is conservative: an interrupted upload may
    have an effect or a fee. Only a step whose saved result evidences that it
    made nothing (`rejected` by the provider, or `not_executed`) counts as unused.
    """
    return (state['status'] in {'reserved','started'} and not state['consumed_uses']
            and all((state['effect_results'].get(item['step']) or {}).get('outcome') in NO_EFFECT_OUTCOMES
                    for item in state['steps']))


INSPECTION_ERRORS=(ValueError,OSError,KeyError,TypeError,sqlite3.DatabaseError)


def all_states(root: Path, *, task_id: str | None=None, grant: str | None=None, run: str | None=None,
               blocked: list[dict] | None=None) -> list[dict]:
    """Reservation states derived from each run's formal events.

    Without `blocked`, an unreadable run raises. With it, that run is skipped
    and its diagnostic is appended to `blocked`, so one damaged run cannot hide
    the others; the caller reports the totals as incomplete.
    """
    import production_workflow as w
    from production_diagnostics import from_exception
    output=[]
    for item in store.runs(root,task_id=task_id):
        if run is not None and item['run_id']!=run:continue
        try:
            _,prepared,_,rows=w.load_run(root,item['run_id'])
            states=derive(rows,prepared,item['run_id'])
        except INSPECTION_ERRORS as exc:
            if blocked is None:raise
            blocked.append({**from_exception(exc,phase='budget'),'run':item['run_id'],'task_id':item['task_id']})
            continue
        for state in states.values():
            if grant is None or state['grant']==grant:output.append(state)
    return output


def _add_money(values: list[dict | None]) -> dict[str,str]:
    from production_permissions import amount
    sums:dict[str,Decimal]={}
    with localcontext() as context:
        context.prec=max([len(v['amount']) for v in values if v]+[64])+len(str(len(values)+1))+16
        for value in values:
            if value is None:continue
            sums[value['currency']]=sums.get(value['currency'],Decimal(0))+amount(value['amount'])
    return {currency:format(value,'f') for currency,value in sorted(sums.items())}


def _totals(states: list[dict]) -> tuple[dict, dict]:
    """Consumed and outstanding amounts of live reservations, per unit and per currency."""
    consumed={'uses':sum(s['consumed_uses'] for s in states),'outputs':sum(s['captured_outputs'] for s in states),
              'cost':_add_money([value for s in states for value in ([s['actual_cost']] if s['actual_cost'] is not None else known_effect_costs(s))])}
    reserved={'uses':sum(max(0,s['amounts']['uses']-s['consumed_uses']) for s in states),
              'outputs':sum(max(0,s['amounts']['outputs']-s['captured_outputs']) for s in states if s['status']!='settled'),
              'cost':_add_money([outstanding_cost(s) for s in states])}
    return consumed,reserved


def _remaining(limits: dict, consumed: dict, reserved: dict) -> tuple[dict, dict]:
    """remaining = limit - consumed - outstanding, and overrun where consumption alone exceeds the limit.

    Money is exact Decimal arithmetic on decimal strings and is never rounded.
    A currency the limit does not name has a limit of zero.
    """
    from production_permissions import amount
    ceiling={limits['cost']['currency']:amount(limits['cost']['amount'])} if limits['cost'] else {}
    currencies=sorted(set(ceiling)|set(consumed['cost'])|set(reserved['cost']))
    with localcontext() as context:
        digits=[len(v) for v in [*consumed['cost'].values(),*reserved['cost'].values()]]
        digits+=[len(limits['cost']['amount'])] if limits['cost'] else []
        # Enough digits for the exact difference of every operand, so nothing rounds.
        context.prec=sum(digits)+64
        remaining={'uses':limits['uses']-consumed['uses']-reserved['uses'],
                   'outputs':limits['outputs']-consumed['outputs']-reserved['outputs'],
                   'cost':{currency:format(ceiling.get(currency,Decimal(0))-Decimal(consumed['cost'].get(currency,'0'))
                                           -Decimal(reserved['cost'].get(currency,'0')),'f') for currency in currencies}}
        overrun={'uses':consumed['uses']>limits['uses'],'outputs':consumed['outputs']>limits['outputs'],
                 'cost':{currency:Decimal(consumed['cost'].get(currency,'0'))>ceiling.get(currency,Decimal(0)) for currency in currencies}}
    return remaining,overrun


def budget(root: Path, *, task_id: str | None=None, grant: str | None=None, run: str | None=None,
           isolate: bool=False) -> dict:
    """Budget per task and grant, derived from formal reservation and settlement events.

    `remaining` is always grant-wide. With `run`, the view keeps only that run's
    task and adds `run_share`, the run's own consumed and outstanding amounts.
    With `isolate`, an unreadable run or authority is listed in `diagnostics`
    instead of raising, and `complete` is false: the totals then omit it.
    """
    from production_diagnostics import from_exception
    if run is not None:
        owner=store.registered_run(root,run)['task_id']
        if task_id is not None and task_id!=owner:
            raise ProductionError('INPUT_CONSISTENCY_ERROR','The run belongs to another work task.',phase='budget',run=run,
                                  expected=task_id,actual=owner)
        task_id=owner
    diagnostics:list[dict]=[]
    states=all_states(root,task_id=task_id,grant=grant,blocked=diagnostics if isolate else None)
    tasks=sorted({row['task_id'] for row in store.runs(root,task_id=task_id)}|({task_id} if task_id else set()))
    groups=[]
    for task in tasks:
        try:
            current=store.authority(root,task,required=False)
        except INSPECTION_ERRORS as exc:
            if not isolate:raise
            diagnostics.append({**from_exception(exc,phase='budget'),'task_id':task})
            current=None
        declared={item['id']:item for item in current['grants']} if current else {}
        ids=set(declared)|{s['grant'] for s in states if s['task_id']==task}
        for identifier in sorted(ids):
            if grant is not None and identifier!=grant:continue
            selected=[s for s in states if s['task_id']==task and s['grant']==identifier and s['status']!='released']
            consumed,reserved=_totals(selected)
            limits=declared[identifier]['limits'] if identifier in declared else None
            remaining,overrun=_remaining(limits,consumed,reserved) if limits is not None else (None,None)
            group={'task_id':task,'grant':identifier,'limits':limits,'consumed':consumed,'outstanding_reserved':reserved,
                   'remaining':remaining,'overrun':overrun,
                   # A skipped run of this task may hold consumption these totals omit.
                   'complete':not any(item.get('task_id')==task for item in diagnostics),
                   'unknown_cost_reservations':[s['reservation_id'] for s in selected if s['actual_cost'] is None and _unpriced(s)],
                   'reservations':[{**s,'release_eligible':releasable(s),'release_reason':release_reason(s)} for s in selected]}
            if run is not None:
                own=[s for s in selected if s['run']==run]
                own_consumed,own_reserved=_totals(own)
                group['run_share']={'run':run,'consumed':own_consumed,'outstanding_reserved':own_reserved,
                                    'reservations':[s['reservation_id'] for s in own]}
            groups.append(group)
    return {'grants':groups,'complete':not diagnostics,'diagnostics':diagnostics,
            'units':{'uses':'distinct external generation requests','outputs':'requested or captured outputs','cost':'separate decimal amount per currency'},
            'basis':'Formal Production reservation and settlement events; not receipt count.'}


def release_reason(state: dict) -> str:
    """Why a reservation can or cannot be released, in one sentence."""
    if not releasable(state):
        return 'An external effect, unsettled charge or terminal transition prevents release.'
    if not state['steps']:
        return 'No external-effect boundary was recorded.'
    return 'The saved provider evidence shows that every started step was rejected or not executed.'


def _unpriced(state: dict) -> bool:
    """A started step whose charge is not known: no final usage, and no evidenced no-effect outcome."""
    for item in state['steps']:
        result=state['effect_results'].get(item['step']) or {}
        if result.get('outcome') in NO_EFFECT_OUTCOMES:continue
        if result.get('usage') is None or not result['usage']['final']:return True
    return False


def accounting(root: Path, prepared: dict) -> dict:
    return budget(root,task_id=prepared['task']['task_id'])


def reserve(root: Path, run: str, authorization: str) -> dict:
    import production_workflow as w
    from production_permissions import amount
    with store.transaction(root):
        directory,prepared,_,rows=w.assert_current(root,run)
        request=w.find(rows,'authorization',authorization)['data']['request']
        w._permission(root,prepared,rows,authorization,request['operation'],request['targets'],request['payload'])
        previous=by_authorization(rows,prepared,run,authorization)
        if previous is not None:
            if previous['status']=='released':raise ProductionError('RESERVATION_REQUIRED','A released reservation cannot be revived.',phase='reservation')
            return previous
        if request['operation']!='submit':raise ProductionError('RESERVATION_NOT_APPLICABLE','Only an external submission consumes generation budget.',phase='reservation')
        totals=budget(root,task_id=prepared['task']['task_id'],grant=request['grant'])
        group=next((g for g in totals['grants'] if g['grant']==request['grant']),None)
        if group is None:raise ProductionError('GRANT_REVOKED','Current grant is unavailable.',phase='reservation')
        remaining=group['remaining'];quote=request['cost']
        if quote is None:raise ProductionError('COST_UNCONFIRMED','Unknown cost cannot be reserved as zero.',phase='reservation')
        allowed=remaining and remaining['uses']>=1 and remaining['outputs']>=request['outputs']
        ceiling=(remaining or {}).get('cost',{}).get(quote['currency'],'0')
        allowed=allowed and Decimal(ceiling)>=amount(quote['amount'])
        if not allowed:
            raise ProductionError('BUDGET_LIMIT_EXCEEDED','Current consumed and outstanding amounts leave insufficient budget.',phase='reservation',
                expected={'uses':1,'outputs':request['outputs'],'cost':quote},actual=remaining,
                required_action='Inspect status --budget, release only unused reservations, or obtain a real grant update.')
        identifier=generate_uuid7()
        data={'reservation_id':identifier,'authorization_sha256':authorization,'grant':request['grant'],
              'task_id':prepared['task']['task_id'],'actor':request['actor'],'release_actors':sorted({request['actor'],prepared['authority']['issuer']}),
              'operation':'submit','request_sha256':request['payload'].get('request_sha256',c.content_id(request['payload'])),
              'amounts':{'uses':1,'outputs':request['outputs'],'cost':quote},'created_at':c.now()}
        row=w.append_record(directory,prepared,rows,'reservation-created',data)
        return derive([*rows,row],prepared,run)[identifier]


def begin(root: Path, run: str, authorization: str, *, effect: str, claim: str | None=None) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory,prepared,_,rows=w.load_run(root,run)
        request=w.find(rows,'authorization',authorization)['data']['request']
        if request['operation']!='submit':
            return w.append_record(directory,prepared,rows,'operation-start',{'authorization_sha256':authorization,'effect':effect,'claim':claim})
        state=by_authorization(rows,prepared,run,authorization)
        if state is None:
            state=reserve(root,run,authorization);directory,prepared,_,rows=w.load_run(root,run)
        if state['status']!='reserved':raise ProductionError('DISPATCH_ALREADY_CLAIMED','Execution start already exists; inspect or resume it.',phase='execution',run=run)
        return w.append_record(directory,prepared,rows,'reservation-start',{'reservation_id':state['reservation_id'],'claim':claim,
            'operation':'submit','effect':effect,'request_sha256':state['request_sha256'],'started_at':c.now()})


def begin_step(root: Path, run: str, authorization: str, *, claim: str, step: str, operation: str,
               identifiers: list[dict] | None = None) -> dict:
    """Commit one external-step boundary before its I/O.

    `identifiers` lists the request fields the service knows this request by,
    each `{"field": [...], "value": ...}` as sent, so a lost answer can be asked
    for again. They are part of the durable pre-send record.
    """
    import production_workflow as w
    from operation_context import current
    if identifiers is not None:
        if not isinstance(identifiers,list):raise ValueError('step identifiers must be a list')
        for item in identifiers:
            c.exact(item,{'field','value'},'step identifier')
            if not isinstance(item['field'],list) or not item['field']:raise ValueError('step identifier field must be a nonempty path')
    with store.transaction(root):
        # The boundary before an external effect checks each studio root's
        # whole ancestry again.
        c.recheck_roots()
        directory,prepared,_,rows=w.assert_current(root,run,force=True)
        request=w.find(rows,'authorization',authorization)['data']['request']
        w._permission(root,prepared,rows,authorization,request['operation'],request['targets'],request['payload'])
        state=require_active(rows,prepared,run,authorization)
        # A budget amendment does not rebuild inputs, but it can stop an effect
        # that has not started. Reserved quantities remain visible and are not
        # erased to make the amended ceiling appear satisfied.
        totals = budget(root, task_id=prepared['task']['task_id'], grant=request['grant'])
        group = next(item for item in totals['grants'] if item['grant'] == request['grant'])
        remaining = group['remaining']
        if (remaining is None or remaining['uses'] < 0 or remaining['outputs'] < 0
                or any(Decimal(value) < 0 for value in remaining['cost'].values())):
            raise ProductionError('BUDGET_LIMIT_EXCEEDED', 'Current grant limits are below committed consumption and reservations.',
                                  phase='before-send', run=run, actual=remaining,
                                  required_action='Obtain a real limit amendment or release eligible unused reservations; no external effect was started by this step.')
        if any(item['step']==step for item in state['steps']):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED','This exact external step was already started.',phase='before-send',run=run,
                                  required_action='Use resume to inspect or recover the original result; never remove the claim to resend.')
        descriptor = prepared.get('runtime_snapshot')
        if descriptor is not None:
            import runtime_snapshot
            # The last check before I/O hashes both the fixed runtime and the
            # live packs again; an earlier cached comparison does not stand in for it.
            runtime_snapshot.read(runtime_snapshot.path(root, descriptor), descriptor, force_verify=True)
            runtime_snapshot.require_current(root, descriptor, run=run, force=True)
        if current():current().durable()
        if state['status']=='reserved':
            begin(root,run,authorization,effect='external-io',claim=claim)
            directory,prepared,_,rows=w.load_run(root,run);state=require_active(rows,prepared,run,authorization)
        data={'reservation_id':state['reservation_id'],'claim':claim,'step':step,'operation':operation,
              'request_sha256':state['request_sha256'],'started_at':c.now()}
        if identifiers is not None:data['identifiers']=identifiers
        return w.append_record(directory,prepared,rows,'external-step',data)


def settle(root: Path, run: str, authorization: str, *, outputs: int, cost: dict | None, final: bool,
           evidence: list[dict] | None=None) -> dict:
    import production_workflow as w
    from production_permissions import cost as validate_cost
    if type(outputs) is not int or outputs<0:raise ValueError('settled outputs must be a nonnegative integer')
    if cost is not None:validate_cost(cost)
    with store.transaction(root):
        directory,prepared,_,rows=w.load_run(root,run);state=require_active(rows,prepared,run,authorization)
        if not any(step['operation']=='send' for step in state['steps']):
            raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED','No send boundary supports this settlement.',phase='settlement')
        data={'reservation_id':state['reservation_id'],'uses':1,'outputs':outputs,'cost':cost,'final':final,'evidence':evidence or []}
        if state['settlement'] is not None:
            previous=next(row for row in rows if row['sha256']==state['settlement'])
            if previous['data']==data:return previous
            if state['status']=='settled' or outputs<state['captured_outputs'] or (state['actual_cost'] is not None and state['actual_cost']!=cost):
                raise ProductionError('SETTLEMENT_CONFLICT','Confirmed actuals cannot be erased or settled twice with different values.',phase='settlement')
        return w.append_record(directory,prepared,rows,'reservation-settled',data)


def validate_release_request(request: Any, *, complete: bool = True) -> None:
    """Check a release request against `production-release.schema.json`.

    `draft-release` writes the same document with the actor's fields empty.
    `complete` also requires the filled actor, reason and evidence.
    """
    import production_workflow as w
    try:
        w.schema_check(request,'release')
    except ValueError as exc:
        raise ProductionError('INPUT_SCHEMA_INVALID',str(exc),phase='release',
                              required_action='Fill the file written by draft-release and pass it unchanged in shape.') from exc
    if complete:
        c.text(request['actor'],'release actor');c.text(request['reason'],'release reason')
        c.sha(request['evidence']['sha256']);c.text(request['evidence']['path'],'evidence path');c.text(request['evidence']['locator'],'evidence locator')


def draft_release(root: Path, run: str, reservation_id: str) -> dict:
    import production_workflow as w
    _,prepared,_,rows=w.load_run(root,run)
    state=derive(rows,prepared,run).get(reservation_id)
    if state is None:raise ProductionError('RESERVATION_NOT_FOUND','Unknown reservation ID.',phase='release',run=run)
    draft={'reservation_id':reservation_id,'actor':'','evidence':{'path':'','sha256':'','locator':''},'reason':''}
    validate_release_request(draft,complete=False)
    return draft


def release(root: Path, run: str, request_file: str) -> dict:
    """Release an unused reservation from the filled draft-release file.

    The request and its evidence are each read once; the stored bytes are the
    bytes that were checked.
    """
    import production_workflow as w
    with store.transaction(root):
        directory,prepared,_,rows=w.load_run(root,run)
        raw_request=store.stable_bytes(root,request_file)
        request=c.decode(raw_request);validate_release_request(request)
        state=derive(rows,prepared,run).get(request['reservation_id'])
        if state is None:raise ProductionError('RESERVATION_NOT_FOUND','Unknown reservation ID in this run.',phase='release',run=run)
        if request['actor'] not in state['release_actors']:
            raise ProductionError('AUTHORIZATION_MISMATCH','Actor cannot release this reservation.',phase='release',run=run,
                                  expected=state['release_actors'],actual=request['actor'])
        if state['status']=='released':return {'released':True,'already_released':True,'reservation_id':state['reservation_id']}
        if not releasable(state):
            raise ProductionError('RESERVATION_NOT_RELEASABLE','An external-effect boundary or uncertain charge prevents release.',phase='release',run=run,
                                  reservation=state['reservation_id'],
                                  required_action='Resume or settle the execution from its saved provider evidence; an external effect is never released.')
        evidence=request['evidence']
        raw=store.stable_bytes(root,evidence['path'])
        if c.digest(raw)!=evidence['sha256']:
            raise ProductionError('SOURCE_CHANGED','Release evidence differs.',phase='release',file=evidence['path'],
                                  expected=evidence['sha256'],actual=c.digest(raw),
                                  required_action='Cite the release evidence by its current digest, or restore the cited bytes.')
        files=[store.capture_evidence(root,directory,request_file,locator='whole',purpose='release-request',raw=raw_request),
               store.capture_evidence(root,directory,evidence['path'],locator=evidence['locator'],purpose='release-evidence',raw=raw)]
        row=w.append_record(directory,prepared,rows,'reservation-release',{'reservation_id':state['reservation_id'],'request':request,'files':files,'released_at':c.now()})
        return {'released':True,'already_released':False,'reservation_id':state['reservation_id'],'receipt':row,'budget':budget(root,task_id=prepared['task']['task_id'])}


def completion_tail(records: list[dict], prepared: dict, run: str) -> None:
    derive(records,prepared,run)
    completions=[row for row in records if row['event']=='completion']
    if len(completions)>1:raise ProductionError('EVENT_CHAIN_CORRUPT','The run has more than one completion.',phase='integrity')
    if completions and any(row['event'] not in {'reservation-release','reservation-settled','external-effect-result'} for row in records if row['sequence']>completions[0]['sequence']):
        raise ProductionError('EVENT_CHAIN_CORRUPT','Only accounting closure may follow completion.',phase='integrity')


def commit_effect(root: Path, run: str, event: str, data: dict, tokens: list[str], *, effect: str) -> dict:
    import production_workflow as w
    with store.transaction(root):
        directory,prepared,_,rows=w.load_run(root,run)
        previous=[row for row in rows if row['event']==event and row['data']==data]
        if previous:return previous[-1]
        for authorization in tokens:begin(root,run,authorization,effect=effect)
        directory,prepared,_,rows=w.load_run(root,run)
        return w.append_record(directory,prepared,rows,event,data)
