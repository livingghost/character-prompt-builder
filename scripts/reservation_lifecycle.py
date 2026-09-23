"""Derive reservation state from immutable receipts and fence external effects."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import execution_contract as c

EVENTS = {'reservation-start','reservation-release','external-step'}
TOKEN_FIELD = 'authorization_sha256'
RESERVATION_EVENT = 'authorization'


def selector(run: str, token: str) -> dict:
    c.sha(token)
    return {'run':run, TOKEN_FIELD:token}


def token_of(value: Any, run: str) -> str:
    c.exact(value, {'run',TOKEN_FIELD}, 'reservation selector')
    if value['run'] != run: raise ValueError('reservation belongs to another run')
    return c.sha(value[TOKEN_FIELD])


def original(data: dict, prepared: dict, previous: dict) -> dict:
    from production_permissions import validate_request
    request=data['request'];validate_request(request)
    matches=[g for g in prepared['authority']['grants'] if g['id']==request['grant']]
    if len(matches)!=1:raise ValueError('reservation refers to an absent grant')
    grant=matches[0]
    return {'actor':request['actor'],'operation':request['operation'],'request_sha256':c.content_id(request['payload']),
       'release_actors':sorted({request['actor'],prepared['authority']['issuer']}),
       'accounting_identity':{'task_id':prepared['task']['task_id'],'grant':request['grant']},
       'amounts':{'uses':1,'outputs':request['outputs'],'cost':request['cost']}}


def claim_owns(record: dict, token: str) -> bool:
    return record['event'] in {'dispatch-claim','adoption-claim','image-edit-claim','external-claim'} and token in record['data'].get('authorizations',[])


def used_by(record: dict, previous: dict) -> list[str]:
    event,data=record['event'],record['data']
    if event in {'handoff','external-claim','edit','image-edit-claim'}:return data.get('authorizations',[])
    if event=='selection':return [data['selection']['authorization']]
    if event in {'dispatch-results','adoption-result','image-edit-output'}:
        claim=previous.get(data.get('claim'))
        if claim is None:raise ValueError('effect names no preceding claim')
        return claim['data'].get('authorizations',[])
    return []


def accounting(root: Path, prepared: dict) -> list[dict]:
    import production_workflow as w
    return w.reservations(root,prepared['task']['task_id'])



def derive(records: list[dict], prepared: dict, run: str) -> dict[str,dict]:
    """Validate transitions and compute amounts from the original reservation."""
    states = {}; by_hash = {}
    for record in records:
        event, data = record['event'], record['data']
        if event == RESERVATION_EVENT:
            attributes = original(data, prepared, by_hash)
            states[record['sha256']] = {**attributes, 'reservation':selector(run,record['sha256']),
                'original_sha256':record['sha256'], 'status':'reserved', 'start':None, 'effect':None, 'release':None, 'steps':[]}
        elif event in EVENTS:
            token = token_of(data['reservation'],run)
            state = states.get(token)
            if state is None: raise ValueError('reservation event precedes its original receipt')
            if event == 'reservation-start':
                c.exact(data,{'reservation','claim','operation','effect','request_sha256'},'reservation start')
                if state['status'] != 'reserved': raise ValueError('reservation may start exactly once before release')
                if data['operation'] != state['operation'] or data['request_sha256'] != state['request_sha256']:
                    raise ValueError('start differs from the reserved operation or request')
                if data['effect'] not in {'external-io','external-handoff','local-action'}: raise ValueError('unknown start effect')
                if data['claim'] is not None:
                    claim=by_hash.get(c.sha(data['claim']))
                    if claim is None or not claim_owns(claim,token): raise ValueError('start claim does not own this reservation')
                state.update(status='started',start=record['sha256'],effect=data['effect'])
            elif event == 'reservation-release':
                c.exact(data,{'reservation','request','original_sha256','amounts','files'},'reservation release')
                if not releasable(state): raise ValueError('only a reservation with no send step or other effect can be released')
                if data['original_sha256'] != token or data['amounts'] != state['amounts']:
                    raise ValueError('release amount or original reservation differs')
                request=data['request'];validate_release_request(request)
                if request['reservation'] != data['reservation'] or request['actor'] not in state['release_actors']:
                    raise ValueError('release request does not identify this reservation and authorized actor')
                if not any(f['path']==request['evidence']['path'] and f['sha256']==request['evidence']['sha256'] for f in data['files']):
                    raise ValueError('release evidence is not stored in the receipt')
                state.update(status='released',release=record['sha256'])
            else:
                c.exact(data,{'reservation','start','claim','step','operation','request_sha256'},'external step')
                if state['status'] != 'started' or data['start'] != state['start']: raise ValueError('external step needs the live start boundary')
                if data['claim'] != by_hash[state['start']]['data']['claim']: raise ValueError('external step changes its claim')
                if data['request_sha256'] != state['request_sha256']: raise ValueError('external step changes its reserved request')
                if data['operation'] not in {'upload','send'}: raise ValueError('unknown external step operation')
                c.text(data['step'],'external step ID')
                if any(x['step']==data['step'] for x in state['steps']): raise ValueError('external step was already begun')
                state['steps'].append(data)
        else:
            for token in used_by(record,by_hash):
                if token not in states or states[token]['status'] != 'started':
                    raise ValueError('effect receipt requires a started, unreleased reservation')
        by_hash[record['sha256']]=record
    return states


def releasable(state: dict) -> bool:
    """A reservation is used once a send step or another effect began; uploads alone do not use it."""
    if state['status'] == 'reserved':
        return True
    return (state['status'] == 'started' and state['effect'] == 'external-io'
            and not any(step['operation'] == 'send' for step in state['steps']))


def require_active(records: list[dict], prepared: dict, run: str, token: str) -> dict:
    state=derive(records,prepared,run).get(c.sha(token))
    if state is None: raise ValueError('unknown reservation receipt')
    if state['status']=='released': raise ValueError('reservation was released; prepare a new run for another execution')
    return state


def begin(root: Path, run: str, token: str, *, effect: str, claim: str | None = None) -> dict:
    """Commit the boundary before returning permission to the current call only."""
    import production_workflow as w
    with c.lock(root):
        directory,p,_,rows=w.load_run(root,run)
        state=require_active(rows,p,run,token)
        if state['status']!='reserved': raise ValueError('operation already started; recover existing evidence instead of repeating it')
        data={'reservation':selector(run,token),'claim':claim,'operation':state['operation'],
              'effect':effect,'request_sha256':state['request_sha256']}
        return w.append_record(directory,p,rows,'reservation-start',data)


def begin_step(root: Path, run: str, token: str, *, claim: str, step: str, operation: str) -> dict:
    """Record each upload or send step before it happens; a recorded send ends release."""
    import production_workflow as w
    with c.lock(root):
        directory,p,_,rows=w.assert_current(root,run)
        state=require_active(rows,p,run,token)
        request=w.find(rows,'authorization',token)['data']['request']
        w._permission(root,p,rows,token,request['operation'],request['targets'],request['payload'])
        if state['status']=='reserved':
            begin(root,run,token,effect='external-io',claim=claim)
            directory,p,_,rows=w.load_run(root,run);state=require_active(rows,p,run,token)
        if any(x['step']==step for x in state['steps']): raise ValueError('external step already started; automatic resubmission is forbidden')
        data={'reservation':selector(run,token),'start':state['start'],'claim':claim,'step':step,
              'operation':operation,'request_sha256':state['request_sha256']}
        return w.append_record(directory,p,rows,'external-step',data)


def validate_release_request(request: Any) -> None:
    c.exact(request,{'reservation','actor','evidence','reason'},'release request')
    c.text(request['actor'],'release actor');c.text(request['reason'],'release reason')
    c.exact(request['evidence'],{'path','sha256','locator'},'release evidence')
    c.text(request['evidence']['path'],'release evidence path');c.text(request['evidence']['locator'],'release evidence locator');c.sha(request['evidence']['sha256'])


def release(root: Path, run: str, request_file: str) -> dict:
    """Cancel an unused reservation without reviving expired or revoked authority."""
    import production_workflow as w
    with c.lock(root):
        directory,p,_,rows=w.load_run(root,run)
        request=c.load(c.local(root,request_file));validate_release_request(request)
        token=token_of(request['reservation'],run);states=derive(rows,p,run)
        state=states.get(token)
        if state is None: raise ValueError('release names no reservation in this run')
        if request['actor'] not in state['release_actors']: raise ValueError('actor cannot release this reservation')
        if state['status']=='released':
            record=next(r for r in rows if r['sha256']==state['release'])
            return {'released':True,'receipt':record,'reservations':accounting(root,p)}
        if not releasable(state): raise ValueError('reservation was used by a send step or another effect and cannot be released')
        evidence=request['evidence'];raw=c.read(c.local(root,evidence['path']))
        if c.digest(raw)!=evidence['sha256']:raise ValueError('release evidence bytes changed')
        files=[w.file_record(root,directory,request_file),w.file_record(root,directory,evidence['path'])]
        data={'reservation':request['reservation'],'request':request,'original_sha256':token,
              'amounts':state['amounts'],'files':files}
        record=w.append_record(directory,p,rows,'reservation-release',data)
        return {'released':True,'receipt':record,'reservations':accounting(root,p)}


def draft_release(root: Path, run: str, token: str) -> dict:
    import production_workflow as w
    _,p,_,rows=w.load_run(root,run);states=derive(rows,p,run)
    state=states.get(c.sha(token))
    if state is None:raise ValueError('unknown reservation')
    return {'state':'draft','request':{'reservation':selector(run,token),'actor':'',
        'evidence':{'path':'','sha256':'','locator':''},'reason':''},
        'release_eligible':releasable(state),'amounts':state['amounts'],
        'execution_state':state['status'],'boundary_receipt':state['start'],
        'unresolved':['actor','evidence','reason']}


def completion_tail(records: list[dict], prepared: dict, run: str) -> None:
    derive(records,prepared,run)
    completions=[r for r in records if r['event']=='completion']
    if not completions:return
    if len(completions)!=1:raise ValueError('completion is not unique')
    after=[r for r in records if r['sequence']>completions[0]['sequence']]
    if any(r['event']!='reservation-release' for r in after):raise ValueError('only an unused reservation release may follow completion')


def commit_effect(root: Path, run: str, event: str, data: dict, tokens: list[str], *, effect: str) -> dict:
    """Start each selected authorization before publishing an effect receipt."""
    import production_workflow as w
    with c.lock(root):
        directory,p,_,rows=w.load_run(root,run)
        previous=[r for r in rows if r['event']==event and r['data']==data]
        if previous:
            for token in tokens:require_active(rows,p,run,token)
            return previous[-1]
        for token in tokens:
            begin(root,run,token,effect=effect)
        directory,p,_,rows=w.load_run(root,run)
        return w.append_record(directory,p,rows,event,data)
