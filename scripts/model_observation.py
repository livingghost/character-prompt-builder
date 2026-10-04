"""Attach an existing dispatch's byte evidence without uploading or sending work."""
from __future__ import annotations
import base64
import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import execution_contract as c
import request_contract as rc
from input_evidence import InputEvidence


def _object(raw:bytes)->dict:
    return {'sha256':c.digest(raw),'size':len(raw),'base64':base64.b64encode(raw).decode('ascii')}


def _read_object(value:dict)->bytes:
    c.exact(value,{'sha256','size','base64'},'observation byte witness')
    try:raw=base64.b64decode(value['base64'],validate=True)
    except (ValueError,TypeError) as exc:raise ValueError('invalid observation byte encoding') from exc
    if type(value['size']) is not int or value['size']!=len(raw) or value['sha256']!=c.digest(raw):raise ValueError('observation byte witness changed')
    return raw


def _load_recorded(source: dict):
    """Validate the exported formal content, without fabricating a local database."""
    import production_workflow as w
    c.exact(source, {'artifact_type', 'run', 'prepared', 'consumer', 'records', 'objects', 'journal'}, 'observation source')
    if source['artifact_type'] != 'model-observation-source':
        raise ValueError('expected a complete recorded dispatch source')
    if not isinstance(source['objects'], dict) or not isinstance(source['records'], list) or not isinstance(source['journal'], dict):
        raise ValueError('recorded dispatch requires objects, receipts and journal byte witnesses')
    objects = {}
    for key, value in source['objects'].items():
        c.sha(key)
        raw = _read_object(value)
        if c.digest(raw) != key:
            raise ValueError('observation object is stored at the wrong address')
        objects[key] = raw
    w.validate_run_content(source['run'], source['prepared'], source['consumer'], source['records'], objects.__getitem__)
    journal = {}
    for name, value in source['journal'].items():
        if not isinstance(name, str) or Path(name).name != name or '\\' in name or name in {'.', '..'}:
            raise ValueError('observation journal needs exact file names')
        journal[name] = _read_object(value)
    return source['prepared'], source['consumer'], source['records'], journal


def _derive(source:dict)->dict:
    import production_workflow as w
    import reservation_lifecycle as lifecycle
    prepared,consumer,rows,journal=_load_recorded(source)
    claims=[r for r in rows if r['event']=='dispatch-claim']
    if len(claims)!=1:raise ValueError('observation requires exactly one recorded dispatch claim')
    claim=claims[0];token=_reservation(claim);state=lifecycle.require_active(rows,prepared,source['run'],token)
    if state['operation']!='submit' or state['status'] not in {'started','partially_settled','settled'} or not any(s['operation']=='send' for s in state['steps']):
        raise ValueError('observation requires the recorded send boundary for this reservation')
    for name in ('request-contract.json','request.json'):
        if name not in journal:raise ValueError('observation lacks recorded '+name)
    rendered=c.decode(journal['request-contract.json']);rc.validate_seal(rendered)
    if _claim_request_hash(claim)!=rendered['request_sha256']:raise ValueError('request observation differs from the claimed request')
    if rendered['output_count']!=1:raise ValueError('request observations record one-output trials')
    upload_ids={}
    for index,item in enumerate(rendered['media']):
        name=f'upload-{index+1:03d}.json'
        if name not in journal:raise ValueError('observation lacks an uploaded input receipt')
        upload=c.decode(journal[name])
        if upload.get('index')!=index or upload.get('source_sha256')!=item['sha256']:raise ValueError('upload evidence differs from the sealed input order')
        c.text(upload.get('provider_id'),'provider input identifier');upload_ids[index]=upload['provider_id']
    rc.validate_wire(rendered,c.decode(journal['request.json']),upload_ids)
    response=journal.get('answer.json');outcome='indeterminate';outputs=[]
    if 'transport-outcome.json' in journal:
        value=c.decode(journal['transport-outcome.json'])
        c.exact(value,{'outcome','response_sha256'},'transport observation')
        if value['outcome'] not in {'rejected','accepted','indeterminate'}:raise ValueError('invalid pre-completion transport outcome')
        if response is None or c.digest(response)!=value['response_sha256']:raise ValueError('transport result differs from its response bytes')
        outcome=value['outcome']
    results=[row for row in rows if row['event']=='dispatch-results' and row['data']['claim']==claim['sha256']]
    known_outputs={};previous_indices=set();invalid=set();returned=None
    for result in results:
        data=result['data']
        if response is None or data['expected_count']!=1:
            raise ValueError('result observation lacks its exact one-output request and response')
        if returned is not None and returned!=data['returned_count']:
            raise ValueError('one saved provider response has conflicting output counts')
        returned=data['returned_count']
        required={c.digest(journal[name]) for name in ('request-contract.json','request.json','answer.json')}
        if not required<={f['sha256'] for f in data['evidence']}:
            raise ValueError('result receipt does not bind the rendered request and response')
        indices=data['output_indices']
        if len(indices)!=len(data['files']) or len(set(indices))!=len(indices) or not previous_indices.issubset(indices):
            raise ValueError('capture progress cannot erase or duplicate prior output positions')
        if data['complete']!=(len(indices)==returned==1):
            raise ValueError('capture completeness differs from the recorded output counts')
        for index,item in zip(indices,data['files']):
            if type(index) is not int or index<1 or index>returned:
                raise ValueError('captured output index is outside the provider response')
            if index in known_outputs and known_outputs[index]!=item['sha256']:
                raise ValueError('the same provider output position changed its captured bytes')
            responses=[f['sha256'] for f in data['evidence'] if f['path'].endswith(f'/response-{index}.json')]
            named=c.decode(_read_object(source['objects'][responses[0]])) if len(responses)==1 and responses[0] in source['objects'] else None
            if not isinstance(named,dict) or named.get('answer_sha256')!=c.digest(response) or named.get('index')!=index:
                raise ValueError('result receipt does not bind its image to the saved provider response')
            raw=_read_object(source['objects'][item['sha256']]);_inspect_output(raw,item,prepared)
            known_outputs[index]=item['sha256']
        invalid.update(data['invalid_output_indices'])
        previous_indices=set(indices)
    if results:
        outputs=[known_outputs[index] for index in sorted(known_outputs)]
        last=results[-1]['data']
        if outcome!='rejected':
            outcome='completed' if last['complete'] and last['contract_valid'] and not invalid else 'indeterminate'
    # Observation time belongs to the recorded execution, not to a later
    # export. Re-exporting the same evidence must not invent a newer observation.
    milestones = [row for row in rows if
        (row['event'] == 'dispatch-results' and row['data'].get('claim') == claim['sha256'])
        or (row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256'])
        or (row['event'] == 'external-step' and row['data'].get('operation') == 'send')]
    if not milestones:
        raise ValueError('observation lacks a recorded send or capture timestamp')
    observed_at = milestones[-1]['created_at']
    try:
        observed_time = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise ValueError('recorded observation time is invalid') from exc
    if observed_time.tzinfo is None:
        raise ValueError('recorded observation time must include a timezone')
    return {'target':rendered['sealed']['target'],'outcome':outcome,'request':rendered,'claim':claim['sha256'],
        'reservation':state['reservation_id'],'results':outputs,'observed_at':observed_at}



def _captured_json(source:dict,path:str)->dict:
    matches=[item for item in source['prepared'].get('dependencies',[]) if item.get('path')==path]
    if len(matches)!=1:raise ValueError('trial evidence does not contain the declared authored source '+path)
    digest=matches[0]['sha256']
    if digest not in source['objects']:raise ValueError('trial evidence is missing captured bytes for '+path)
    return c.decode(_read_object(source['objects'][digest]))

def trial_plan(source:dict,derived:dict)->dict:
    task=source['prepared'].get('task',{})
    generation=task.get('generation') if isinstance(task,dict) else None
    if isinstance(generation,dict) and generation.get('request_validation'):
        record=_captured_json(source,generation['request_validation'])
    elif isinstance(task.get('upscale'),dict):
        authored=_captured_json(source,task['delivery']['path'])
        record=authored.get('request_validation')
        if not isinstance(record,dict):
            raise ValueError('upscale trial lacks its recorded request validation')
    else:
        raise ValueError('observed profile adoption requires the prepared request validation record')
    if record.get('mode')!='bounded-probe':raise ValueError('observed profile adoption requires a bounded-probe trial')
    contract=record.get('contract')
    if not isinstance(contract,dict) or not isinstance(contract.get('path'),str):raise ValueError('bounded probe validation lacks its trial plan reference')
    plan=_captured_json(source,contract['path'])
    from request_validation import validate_trial_plan
    validate_trial_plan(plan,derived['target'])
    # The plan's quantity is what the run did: one dispatch claim, and the request's output count.
    claims=sum(row['event']=='dispatch-claim' for row in source['records'])
    if claims!=plan['quantity']['uses'] or derived['request']['output_count']!=plan['quantity']['outputs']:
        raise ValueError('the recorded run differs from the planned trial quantity')
    return plan

def validate_adoption(value:dict,*,target:dict,results:list[str],question:str,purpose:str,run:str|None=None)->dict:
    """Check an explicit profile adoption decision against the trial it adopts.

    schemas/authoring/model-profile-adoption.schema.json holds its fields. The
    decision must name this run, target, question and purpose, and only outputs
    this trial captured. A hypothesis or a provider statement alone supports
    nothing, and a visual question needs an observed output or a measurement.
    """
    from request_validation import authored_schema, _unknowns
    authored_schema(value,'model-profile-adoption','observed profile adoption')
    if run is not None and value['run']!=run:raise ValueError('profile adoption belongs to another run')
    if value['target']!=target:raise ValueError('profile adoption belongs to another target')
    if value['question']!=question:raise ValueError('profile adoption does not answer the bounded trial question')
    if value['purpose'] != purpose:raise ValueError('profile adoption purpose differs from the bounded trial')
    informative=False
    visual_observation=False
    for item in value['observations']:
        if item['kind'] in {'observed_output','measurement'}:
            if item['result_sha256'] not in results:raise ValueError('profile adoption observation names an output outside this trial')
            informative=True
            visual_observation=True
        else:
            informative = informative or item['kind']=='request_acceptance'
    if not informative:raise ValueError('a hypothesis alone or provider statement cannot support profile adoption')
    if purpose in {'visual_effect','reference_influence','output_quality'} and not visual_observation:
        raise ValueError('request acceptance alone cannot establish a visual trial conclusion')
    _unknowns(value['unmeasured'])
    return value

def validate_observation(value:dict,reader:InputEvidence)->dict:
    c.exact(value,{'artifact_type','target','observed_at','outcome','request','source','claim','reservation','results','limitations'},'request observation')
    if value['artifact_type']!='model-request-observation':raise ValueError('expected a recorded request observation')
    try:stamp=datetime.fromisoformat(value['observed_at'].replace('Z','+00:00'))
    except (ValueError,AttributeError) as exc:raise ValueError('observation needs an ISO timestamp') from exc
    if stamp.tzinfo is None:raise ValueError('observation timestamp must include a timezone')
    derived=_derive(reader.json(value['source']))
    if any(value[key]!=item for key,item in derived.items()):raise ValueError('observation does not follow its recorded dispatch evidence')
    if value['limitations']!=LIMITATIONS:raise ValueError('observation must retain its measurement limits')
    return value


LIMITATIONS=[
    'The source records a request to the declared target, not the provider internal weights.',
    'Receipt hashes establish recorded byte consistency, not a principal identity or artistic acceptance.',
    'Only the recorded parameter tuple and input form were tried; other tuples and new content remain unmeasured.',
]


def capture(root:Path,run:str)->dict:
    """Read one existing run. The caller decides where local observation data is saved."""
    import production_workflow as w
    with c.lock(root):
        directory,prepared,consumer,rows=w.load_run(root,run)
        claim=w.find(rows,'dispatch-claim');journal=_journal(directory,rows,claim)
        keys={d['sha256'] for d in prepared['dependencies'] if d['space']!='skill'}
        for row in rows:
            for item in row['data'].get('files',[])+row['data'].get('evidence',[]):keys.add(item['sha256'])
        source={'artifact_type':'model-observation-source','run':run,'prepared':prepared,'consumer':consumer,'records':rows,
            'objects':{key:_object(c.object_read(directory,key)) for key in sorted(keys)},
            'journal':{name:_object(raw) for name,raw in journal.items()}}
        _derive(source)
        return source


def bundle(root:Path,run:str,*,relative_prefix:str,adoption:dict|None=None)->tuple[dict,dict]:
    """Assemble immutable dispatch evidence; profile adoption is a separate authored decision."""
    source=capture(root,run);derived=_derive(source);files={}
    def put(name, value):
        raw=c.encoded(value);files[name]=raw
        return {'path':relative_prefix+'/'+name,'sha256':c.digest(raw)}
    source_ref=put('source.json',source)
    value={'artifact_type':'model-request-observation',**derived,'source':source_ref,
        'limitations':LIMITATIONS}
    observed=put('observation.json',value)
    profile_ref=None
    if adoption is not None:
        if derived['outcome']!='completed':raise ValueError('an observed profile requires one completed captured output')
        plan=trial_plan(source,derived)
        validate_adoption(adoption,target=derived['target'],results=derived['results'],question=plan['question'],purpose=plan['purpose'],run=run)
        adoption_ref=put('adoption.json',adoption)
        profile={'artifact_type':'observed-request-profile','target':derived['target'],
            'execution':derived['request']['sealed']['execution'],'observation':observed,'adoption':adoption_ref,
            'question':plan['question'],'unmeasured':adoption['unmeasured'],
            'profile':derived['request']['profile'],'profile_sha256':derived['request']['profile_sha256']}
        profile_ref=put('profile.json',profile)
    result={'observation':observed,'profile':profile_ref,'target':derived['target'],'outcome':derived['outcome']}
    put('manifest.json',{'artifact_type':'local-request-evidence',**result,
        'files':[{'path':relative_prefix+'/'+name,'sha256':c.digest(raw)} for name,raw in sorted(files.items())]})
    return files,result


def publish(root:Path,run:str,out_dir:Path,*,relative_prefix:str,adoption:dict|None=None)->dict:
    """Publish a complete local observation bundle; no observed profile appears without explicit adoption."""
    files,result=bundle(root,run,relative_prefix=relative_prefix,adoption=adoption)
    if out_dir.exists():raise ValueError('observation destination must be new')
    out_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pending-observation-',dir=out_dir.parent) as temporary:
        staging=Path(temporary)
        for name,raw in files.items():c.atomic(staging/name,raw)
        c.publish_directory(staging,out_dir);c.fsync_dir(out_dir.parent)
    return result


def _reservation(claim:dict)->str:
    values=claim['data']['authorizations']
    if len(values)!=1:raise ValueError('dispatch observation needs its exact submit reservation')
    return values[0]


def _claim_request_hash(claim:dict)->str:
    return claim['data']['intent']['payload']['request_sha256']


def _inspect_output(raw:bytes,item:dict,prepared:dict)->None:
    import production_evidence
    production_evidence.inspect(raw,prepared['task']['artifact'])


def _journal(directory, rows, claim) -> dict:
    """The dispatch journal files the run's formal events hold as evidence, by file name.

    Execution registers the request contract, the request, the answer, the
    transport outcome and each upload receipt as event evidence when it writes
    them, so the run's own object store holds every byte read here.
    """
    base = claim['data']['journal']
    witnesses = {}
    for row in rows:
        for item in row['data'].get('evidence', []):
            if item['path'].startswith(base + '/'):
                name = item['path'][len(base) + 1:]
                if '/' in name:
                    continue
                raw = c.object_read(directory, item['sha256'])
                if name in witnesses and witnesses[name] != raw:
                    raise ValueError('conflicting committed dispatch journal bytes')
                witnesses[name] = raw
    if 'request-contract.json' not in witnesses:
        raise ValueError('observation is missing its recorded request contract')
    rendered = c.decode(witnesses['request-contract.json'])
    names = ['request-contract.json', 'request.json', 'answer.json', 'transport-outcome.json']
    names += [f'upload-{i + 1:03d}.json' for i in range(len(rendered['media']))]
    return {name: witnesses[name] for name in names if name in witnesses}
