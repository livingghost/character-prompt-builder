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


def _load_recorded(source:dict):
    """Use the product's recorded-content reader, including its receipt state checks."""
    import production_workflow as w
    c.exact(source,{'artifact_type','run','prepared','consumer','records','objects','journal'},'observation source')
    if source['artifact_type']!='model-observation-source':raise ValueError('expected a complete recorded dispatch source')
    w.run_identifier(source['run'])
    if not isinstance(source['objects'],dict) or not isinstance(source['records'],list) or not isinstance(source['journal'],dict):
        raise ValueError('recorded dispatch requires objects, receipts and journal byte witnesses')
    with tempfile.TemporaryDirectory(prefix='observation-check-') as temporary:
        root=Path(temporary);directory=w.run_dir(root,source['run'],exists=False);directory.mkdir(parents=True);(directory/'records').mkdir()
        c.atomic(directory/'prepared.json',c.encoded(source['prepared']));c.atomic(directory/'consumer.json',c.encoded(source['consumer']))
        for key,value in source['objects'].items():
            c.sha(key);raw=_read_object(value)
            if c.object_store(directory,raw)!=key:raise ValueError('observation object is stored at the wrong address')
        for row in source['records']:
            sequence=row.get('sequence')
            if type(sequence) is not int or sequence<1:raise ValueError('invalid observation receipt sequence')
            c.atomic(directory/'records'/f'{sequence:06d}-{c.sha(row["sha256"])}.json',c.encoded(row))
        _,prepared,consumer,rows=w.load_run(root,source['run'])
    journal={}
    for name,value in source['journal'].items():
        if not isinstance(name,str) or Path(name).name!=name:raise ValueError('observation journal needs exact file names')
        journal[name]=_read_object(value)
    return prepared,consumer,rows,journal


def _derive(source:dict)->dict:
    import production_workflow as w
    import reservation_lifecycle as lifecycle
    prepared,consumer,rows,journal=_load_recorded(source)
    claims=[r for r in rows if r['event']=='dispatch-claim']
    if len(claims)!=1:raise ValueError('observation requires exactly one recorded dispatch claim')
    claim=claims[0];token=_reservation(claim);state=lifecycle.require_active(rows,prepared,source['run'],token)
    if state['operation']!='submit' or state['status']!='started' or not any(s['operation']=='send' for s in state['steps']):
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
    if len(results)>1:raise ValueError('dispatch has conflicting result observations')
    if results:
        result=results[0]
        if outcome=='rejected' or response is None:raise ValueError('completed results conflict with the saved provider response')
        if result['data']['expected_count']!=1 or len(result['data']['files'])!=1:raise ValueError('one complete output is required')
        required={c.digest(journal[name]) for name in ('request-contract.json','request.json','answer.json')}
        if not required<={f['sha256'] for f in result['data']['evidence']}:raise ValueError('result receipt does not bind the rendered request and response')
        for item in result['data']['files']:
            raw=_read_object(source['objects'][item['sha256']])
            _inspect_output(raw,item,prepared)
            outputs.append(item['sha256'])
        outcome='completed'
    return {'target':rendered['sealed']['target'],'outcome':outcome,'request':rendered,'claim':claim['sha256'],
        'reservation':lifecycle.selector(source['run'],token),'results':outputs}


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
        claim=w.find(rows,'dispatch-claim');journal=_journal(root,directory,prepared,rows,claim)
        keys={d['sha256'] for d in prepared['dependencies'] if d['space']!='skill'}
        for row in rows:
            for item in row['data'].get('files',[])+row['data'].get('evidence',[]):keys.add(item['sha256'])
        source={'artifact_type':'model-observation-source','run':run,'prepared':prepared,'consumer':consumer,'records':rows,
            'objects':{key:_object(c.object_read(directory,key)) for key in sorted(keys)},
            'journal':{name:_object(raw) for name,raw in journal.items()}}
        _derive(source)
        return source


def bundle(root:Path,run:str,*,relative_prefix:str)->tuple[dict,dict]:
    """Assemble the complete evidence before publishing any visible directory."""
    source=capture(root,run);derived=_derive(source);files={}
    def put(name, value):
        raw=c.encoded(value);files[name]=raw
        return {'path':relative_prefix+'/'+name,'sha256':c.digest(raw)}
    source_ref=put('source.json',source)
    value={'artifact_type':'model-request-observation',**derived,'source':source_ref,
        'observed_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'limitations':LIMITATIONS}
    observed=put('observation.json',value)
    profile_ref=None
    if derived['outcome']=='completed':
        profile={'artifact_type':'observed-request-profile','target':derived['target'],
            'execution':derived['request']['sealed']['execution'],'observation':observed,
            'profile':derived['request']['profile'],'profile_sha256':derived['request']['profile_sha256']}
        profile_ref=put('profile.json',profile)
    result={'observation':observed,'profile':profile_ref,'target':derived['target'],'outcome':derived['outcome']}
    put('manifest.json',{'artifact_type':'local-request-evidence',**result,
        'files':[{'path':relative_prefix+'/'+name,'sha256':c.digest(raw)} for name,raw in sorted(files.items())]})
    return files,result


def publish(root:Path,run:str,out_dir:Path,*,relative_prefix:str)->dict:
    """Publish the complete local bundle; no upload, send or reservation occurs."""
    files,result=bundle(root,run,relative_prefix=relative_prefix)
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


def _journal(root,directory,prepared,rows,claim)->dict:
    base=c.local(root,claim['data']['journal']);names=['request-contract.json','request.json','answer.json','transport-outcome.json']
    rendered=c.load(c.local(base,'request-contract.json'))
    names += [f'upload-{i+1:03d}.json' for i in range(len(rendered['media']))]
    output={name:c.read(c.local(base,name)) for name in names if (base/name).is_file()}
    for name,raw in output.items():
        matches=[item for row in rows if row['event']=='dispatch-results' for item in row['data']['evidence'] if item['path']==(base/name).relative_to(root).as_posix()]
        if matches and any(item['sha256']!=c.digest(raw) for item in matches):raise ValueError('recorded dispatch journal was modified')
    return output
