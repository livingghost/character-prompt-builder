#!/usr/bin/env python3
"""Inspect, export and verify the installed public contract using public data only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
import protocol_contract as contract

ROOT = Path(__file__).resolve().parents[1]
from io_budget import read_stream
from execution_contract import publish_directory
HEX = re.compile(r'^[0-9a-f]{64}$')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def project_path(root: Path, rel: str, *, exists: bool = True) -> Path:
    root = root.resolve(strict=True)
    if not root.is_dir() or not isinstance(rel,str) or not rel or '\\' in rel:
        raise ValueError('expected a project and a nonempty relative path')
    path = Path(rel)
    if path.is_absolute() or '..' in path.parts or '.' == rel:
        raise ValueError('path must remain within the supplied project')
    target = root/path
    current = root
    for part in path.parts:
        current = current/part
        if current.is_symlink(): raise ValueError('symbolic links are not exchange inputs')
    if not target.resolve().is_relative_to(root): raise ValueError('path escapes project')
    if exists and not target.exists(): raise ValueError('missing exchange input: '+rel)
    return target


def read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file(): raise ValueError('expected a regular file')
    with path.open('rb') as handle:
        return read_stream(handle)


def decode(raw: bytes) -> dict:
    value = contract.parse_json(raw.decode('utf-8'))
    if not isinstance(value,dict): raise ValueError('exchange metadata must be an object')
    return value


def refs(value: Any):
    if isinstance(value,dict):
        if '$ref' in value: yield value['$ref']
        for item in value.values(): yield from refs(item)
    elif isinstance(value,list):
        for item in value: yield from refs(item)


def check_installed() -> dict:
    registry = contract.registry()
    rows=registry['schemas']
    names={row['schema'].split('/',1)[1]:row['schema'] for row in rows}
    if len(names)!=len(rows): raise ValueError('duplicate schema basenames')
    errors=[]
    for row in rows:
        schema = contract.schema_named(row['schema'].split('/',1)[1])
        for ref in refs(schema):
            try: contract._resolve_ref(ref,schema)
            except (ValueError,KeyError,OSError) as exc:errors.append(f"{row['schema']}: {exc}")
    for kind,row in registry['artifacts'].items():
        schema=contract.schema_for({'artifact_type':kind})
        if schema.get('properties',{}).get('artifact_type',{}).get('const')!=kind:
            errors.append(f'{kind}: registry and schema artifact type disagree')
        field=row['self_hash_field']
        if field and field not in schema.get('properties',{}):errors.append(f'{kind}: missing self-hash declaration')
    if errors: raise ValueError('; '.join(errors))
    return {'ok':True,'contract_set_sha256':registry['contract_set_sha256'],
            'schemas':len(rows),'public_artifacts':len(registry['artifacts']),
            'semantic_contract_sha256':registry['semantics']['sha256']}


def describe(kind: str) -> dict:
    registry=contract.registry()
    if kind not in registry['artifacts']: raise ValueError('unknown public artifact')
    pending=[registry['artifacts'][kind]['schema']];members={}
    by_name={row['schema'].split('/',1)[1]:row['schema'] for row in registry['schemas']}
    while pending:
        key=pending.pop()
        if key in members:continue
        schema=contract.schema_named(key.split('/',1)[1])
        members[key]=digest(read(contract.schema_path(key)))
        for ref in refs(schema):
            name=ref.split('#',1)[0]
            contract._resolve_ref(ref,schema)
            if name:pending.append(by_name[name])
    value={'public_type':kind,'schemas':[{'schema':k,'sha256':v} for k,v in sorted(members.items())],
           'semantics_sha256':registry['semantics']['sha256']}
    value['contract_sha256']=contract.sha256_json(value)
    return value


def inspect_artifact(root:Path,path:str,expected_contract:str|None=None) -> dict:
    raw=read(project_path(root,path));v=decode(raw)
    report=contract.validate_artifact(v)
    if not report['ok']:raise ValueError('invalid public artifact: '+'; '.join(report['errors']))
    descriptor=describe(v['artifact_type'])
    if expected_contract and decode(read(project_path(root,expected_contract)))!=descriptor:
        raise ValueError('supplied contract does not match the installed public contract')
    return {'artifact_sha256':digest(raw),'artifact_content_sha256':report['content_sha256'],
            'contract':descriptor}


def _fsync_dir(path:Path) -> None:
    if os.name=='posix':
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)


def export(root:Path,path:str,out:str,expected_contract:str|None=None) -> dict:
    inspected=inspect_artifact(root,path,expected_contract)
    target=project_path(root,out,exists=False)
    if target.exists():raise ValueError('exchange output already exists')
    target.parent.mkdir(parents=True,exist_ok=True)
    guard=target.parent/('.'+target.name+'.exchange-lock')
    try:fd=os.open(guard,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:raise ValueError('exchange output is reserved; inspect the interrupted operation before retrying') from exc
    stage=None
    try:
        os.close(fd)
        if target.exists():raise ValueError('exchange output already exists')
        raw=read(project_path(root,path))
        if digest(raw)!=inspected['artifact_sha256']:raise ValueError('artifact changed during export')
        descriptor=encoded(inspected['contract'])
        manifest={'files':[{'path':'artifact.json','sha256':digest(raw)},
                           {'path':'contract.json','sha256':digest(descriptor)}],
                  'contract_sha256':inspected['contract']['contract_sha256']}
        stage=Path(tempfile.mkdtemp(prefix='.exchange-pending-',dir=target.parent))
        for name,data in [('artifact.json',raw),('contract.json',descriptor),('manifest.json',encoded(manifest))]:
            with (stage/name).open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        _fsync_dir(stage)
        # This also rechecks installed schema bytes immediately before publication.
        verify_bundle(root,stage.relative_to(root.resolve()).as_posix())
        publish_directory(stage,target);_fsync_dir(target.parent)
    finally:
        if stage is not None and stage.exists():shutil.rmtree(stage)
        guard.unlink(missing_ok=True);_fsync_dir(target.parent)
    return {'ok':True,'out':out,**inspected,'canonical_adoption':False}


def verify_bundle(root:Path,bundle:str) -> dict:
    target=project_path(root,bundle)
    if not target.is_dir():raise ValueError('exchange bundle must be a directory')
    expected={'artifact.json','contract.json','manifest.json'}
    if {p.name for p in target.iterdir()}!=expected:raise ValueError('exchange bundle member set is not exact')
    manifest=decode(read(project_path(target,'manifest.json')))
    if set(manifest)!={'files','contract_sha256'}:raise ValueError('invalid exchange manifest fields')
    rows=manifest['files']
    if not isinstance(rows,list) or len(rows)!=2:raise ValueError('invalid exchange file commitments')
    commits={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'path','sha256'}:raise ValueError('invalid exchange commitment')
        name=row['path'];sha=row['sha256']
        if name not in {'artifact.json','contract.json'} or name in commits or not isinstance(sha,str) or not HEX.fullmatch(sha):raise ValueError('invalid exchange member commitment')
        raw=read(project_path(target,name))
        if digest(raw)!=sha:raise ValueError(name+': exact byte hash mismatch')
        commits[name]=raw
    offered=decode(commits['contract.json']);value=decode(commits['artifact.json'])
    current=describe(value.get('artifact_type'))
    if offered!=current or manifest['contract_sha256']!=current['contract_sha256']:
        raise ValueError('bundle contract does not match the installed contract')
    report=contract.validate_artifact(value)
    if not report['ok']:raise ValueError('received artifact failed validation: '+'; '.join(report['errors']))
    return {'ok':True,'public_type':value['artifact_type'],'artifact_sha256':digest(commits['artifact.json']),
            'artifact_content_sha256':report['content_sha256'],'contract_sha256':current['contract_sha256'],
            'canonical_adoption':False,'referenced_media_verified':False}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['check-installed','describe','inspect','export','verify'])
    p.add_argument('--type');p.add_argument('--root');p.add_argument('--artifact');p.add_argument('--contract');p.add_argument('--out');p.add_argument('--bundle');a=p.parse_args()
    try:
        if a.command=='check-installed':result=check_installed()
        elif a.command=='describe':result=describe(a.type)
        else:
            if not a.root:raise ValueError('--root is required')
            root=Path(a.root).resolve(strict=True)
            if a.command=='verify':
                if not a.bundle:raise ValueError('--bundle is required')
                result=verify_bundle(root,a.bundle)
            else:
                if not a.artifact:raise ValueError('--artifact is required')
                if a.command=='export':
                    if not a.out:raise ValueError('--out is required')
                    result=export(root,a.artifact,a.out,a.contract)
                else:result=inspect_artifact(root,a.artifact,a.contract)
        print(json.dumps({'ok':True,**result},ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,TypeError,KeyError,UnicodeError,RecursionError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},ensure_ascii=False));return 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
