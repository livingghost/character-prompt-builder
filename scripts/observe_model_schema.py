#!/usr/bin/env python3
"""Publish attributed schema or existing trial evidence in a new locked local pack."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile

import execution_contract as c
from input_evidence import InputEvidence
import model_observation
import pack_manager as pm
import schema_observation


def _selection(pack: Path, model_id: str, service: str) -> tuple[Path, dict, int, int]:
    manifest = c.load(pack/'pack.json')
    matches = []
    files = {path for pattern in manifest['content']['record_globs'] for path in pack.glob(pattern)}
    for path in sorted(files):
        c.local(pack,path.relative_to(pack).as_posix())
        document = c.load(path)
        for index,record in enumerate(document.get('records', [])):
            if record.get('id') == model_id:
                offerings=[i for i,value in enumerate(record.get('offerings',[])) if value['service']==service]
                if len(offerings)!=1:raise ValueError('select one exact declared model offering')
                matches.append((path,document,index,offerings[0]))
    if len(matches)!=1:raise ValueError('select one canonical model ID from this pack')
    return matches[0]


def publish(args) -> dict:
    pack=args.pack.resolve(strict=True); destination=args.out_pack.absolute()
    if destination.exists() or pack==destination or pack in destination.parents:
        raise ValueError('select a new pack destination outside the source pack')
    source=pm.validate_pack(pack,require_lock=True,verify_lock=True)
    if not source.valid:raise ValueError('source pack must pass its normal validation')
    path,document,index,offering_index=_selection(pack,args.model,args.service)
    record=document['records'][index];offering=record['offerings'][offering_index]
    target={'service':args.service,'model_identifier':offering['model_identifier'],'operation':args.operation}
    original={p.relative_to(pack).as_posix():c.digest(c.read(p)) for p in sorted(pack.rglob('*')) if p.is_file()}
    if any(p.is_symlink() for p in pack.rglob('*')):raise ValueError('pack evidence cannot follow symlinks')
    prefix='resources/model-evidence/'+c.text(args.entry,'evidence entry ID')
    c.local(pack,prefix,exists=False)
    if '/' in args.entry or '\\' in args.entry or args.entry in {'.','..'}:
        raise ValueError('entry must be one path component')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.observed-pack-',dir=destination.parent) as temp:
        staging=Path(temp)/'pack';shutil.copytree(pack,staging)
        if (staging/prefix).exists():raise FileExistsError('select a new evidence entry')
        updated=copy.deepcopy(document);chosen=updated['records'][index]['offerings'][offering_index]
        if args.command=='attach-probe':
            source=model_observation.capture(args.root.resolve(strict=True),args.run)
            actual=model_observation._derive(source)
            if actual['target']!=target:raise ValueError('trial target differs from the selected offering')
            result=model_observation.publish(args.root.resolve(strict=True),args.run,staging/prefix,relative_prefix=prefix)
            chosen.setdefault('parameter_observations',[]).append(result)
        else:
            relationship=None
            if args.command=='reference':
                reader=InputEvidence(args.root.resolve(strict=True))
                relationship=dict(reader.select(args.relationship),locator=args.locator)
            files,result=schema_observation.assemble(args.root.resolve(strict=True),target=target,
                acquisition=args.acquisition,pointer=args.pointer,prefix=prefix,kind=args.command,
                relationship=relationship,overlay=args.overlay if args.command=='schema' else None)
            schema_observation.publish(staging,prefix,files)
            if args.command=='schema':
                contract=c.decode(files['contract.json']); acquisition=c.decode(files['acquisition.json'])
                wrapper={'artifact_type':'observed-parameter-schema','model_id':args.model,
                    'service':args.service,'model_identifier':target['model_identifier'],
                    'observed_at':acquisition['acquired_at'][:10], 'source':acquisition['source']['identifier'],
                    'schema':contract['schema']}
                c.atomic(staging/prefix/'observed-schema.json',c.encoded(wrapper))
                chosen['schema_snapshot']=prefix+'/observed-schema.json'
                chosen['schema_contract']=result['contract']
                chosen['schema_acquisition']=result['evidence']
                chosen['observed_at']=c.decode(files['acquisition.json'])['acquired_at'][:10]
            else:chosen.setdefault('reference_schemas',[]).append(result['contract'])
        pm.atomic_write_json(staging/path.relative_to(pack),updated)
        manifest=c.load(staging/'pack.json');manifest['release']=args.release
        pm.atomic_write_json(staging/'pack.json',manifest)
        lock=pm.write_lock(staging)
        checked=pm.validate_pack(staging,require_lock=True,verify_lock=True)
        if not checked.valid:raise ValueError('observed pack failed validation: '+ '; '.join(x.message for x in checked.issues if x.severity=='error'))
        with c.lock(destination.parent):
            current={p.relative_to(pack).as_posix():c.digest(c.read(p)) for p in sorted(pack.rglob('*')) if p.is_file()}
            if current!=original:raise ValueError('source pack changed while preparing the evidence')
            if destination.exists():raise FileExistsError('pack destination already exists')
            c.publish_directory(staging,destination);c.fsync_dir(destination.parent)
    return {'ok':True,'pack':str(destination),'release':args.release,'target':target,'evidence':result,
            'lock_sha256':c.content_id(lock),'activation_required':True,'external_effect':False,'budget_effect':'none'}


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('schema','reference','attach-probe'):
        sub=commands.add_parser(name)
        sub.add_argument('--root',type=Path,required=True,help='Project containing the acquisition or existing run.')
        sub.add_argument('--pack',type=Path,required=True,help='Validated source pack; retained unchanged.')
        sub.add_argument('--out-pack',type=Path,required=True,help='New local pack directory; activate it explicitly afterwards.')
        sub.add_argument('--release',required=True,help='Explicit CalVer for the new pack content.')
        sub.add_argument('--model',required=True);sub.add_argument('--service',required=True)
        sub.add_argument('--operation',required=True);sub.add_argument('--entry',required=True)
        if name=='attach-probe':sub.add_argument('--run',required=True)
        else:
            sub.add_argument('--acquisition',required=True,help='Project-relative acquisition JSON with original response witness.')
            sub.add_argument('--pointer',default='',help='JSON Pointer into the acquired response.')
            if name=='schema':sub.add_argument('--overlay',help='Separate local envelope overlay JSON.')
            else:
                sub.add_argument('--relationship',required=True);sub.add_argument('--locator',required=True)
    args=parser.parse_args(argv)
    try:result=publish(args)
    except (ValueError,OSError,KeyError,TypeError,pm.PackError) as exc:parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
