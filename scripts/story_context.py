#!/usr/bin/env python3
"""Resolve a chosen story moment and select evidence for a production task.

    python scripts/story_context.py inspect --root PROJECT --query query.json
    python scripts/story_context.py build --root PROJECT --query query.json --out NEW_DIR
    python scripts/story_context.py verify --root PROJECT --query query.json --bundle DIR

See references/runtime/story-context.md for authoring, views and production use.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Sequence

import world_realization as wr
from state_protocol import canonical_json, parse_json, resolve_world, sha256_json, validate_against_schema, validate_artifact
from authorial_intent_audit import parse_document as parse_intents
from execution_contract import fsync_dir, publish_directory

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/authoring/story-context-query.schema.json'


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')


def load_query(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    raw = wr.read_bytes(wr.local_path(root, relative))
    query = parse_json(raw.decode('utf-8'))
    errors = validate_against_schema(query, parse_json(SCHEMA.read_text(encoding='utf-8')))
    if errors:
        raise ValueError('invalid story context query: '+'; '.join(errors))
    for field, key in [('indexes','index_id'),('requirements','requirement_id'),('author_bindings','binding_id'),('views','view_id')]:
        wr.unique(query.get(field, []), key, key)
    for requirement in query.get('requirements', []):
        if (requirement['test']=='equals') != ('value' in requirement):
            raise ValueError('only equals requirements take an explicit value')
    return query, hashlib.sha256(raw).hexdigest()


def _coverage(query: dict, timeline: dict, blobs: dict) -> dict:
    value = wr.decode_json(blobs, query['coverage_source_id'])
    fields = {'timeline_id','start_order','through_order','basis'}
    if not isinstance(value, dict) or set(value)!=fields:
        raise ValueError('coverage requires timeline_id, start_order, through_order and basis')
    if (type(value['start_order']) is not int or type(value['through_order']) is not int
            or value['start_order']>value['through_order'] or not isinstance(value['basis'],str) or not value['basis'].strip()):
        raise ValueError('invalid authored coverage')
    tid = query['timeline']['timeline_id']
    if value['timeline_id']!=tid:
        raise ValueError('coverage is for another timeline')
    if not value['start_order']<=query['at']['story_order']<=value['through_order']:
        raise ValueError('moment is outside the authored coverage')
    for kind, key in [('events','effective_order'),('processes','started_order')]:
        if any(row['timeline_id']==tid and row[key]<value['start_order'] for row in timeline[kind]):
            raise ValueError('history precedes the declared base; select an unambiguous base and history')
    return value


def _selection(raw: bytes, selector: dict) -> tuple[Any, str | None]:
    text = raw.decode('utf-8')
    kind = selector['kind']
    if kind=='document':
        return text, None
    if kind=='json-pointer':
        present, value = wr.at_pointer(parse_json(text), selector['pointer'])
        if not present:
            raise ValueError('author binding selects an absent JSON field: '+selector['pointer'])
        return value, None
    if kind=='intent':
        parsed = parse_intents(text)
        if parsed['errors'] or selector['intent_id'] not in parsed['intents']:
            raise ValueError('author binding selects an unresolved or malformed intent')
        record = parsed['intents'][selector['intent_id']]
        selected, _ = _selection(raw, {'kind':'section','heading':'### Intent '+selector['intent_id']})
        return selected, record['declared_status']
    lines = text.splitlines()
    indices = [i for i,line in enumerate(lines) if line.strip()==selector['heading']]
    if len(indices)!=1 or not re.match(r'^#{1,6} ',selector['heading']):
        raise ValueError('section selector requires one exact Markdown heading')
    start = indices[0]; level = len(selector['heading'].split(' ',1)[0]); end=len(lines)
    for i in range(start+1,len(lines)):
        heading=re.match(r'^(#{1,6}) ',lines[i])
        if heading and len(heading[1])<=level:
            end=i;break
    return '\n'.join(lines[start:end]), None


def _indexes(query: dict, states: dict) -> dict:
    result = {}; total = 0
    for spec in query.get('indexes', []):
        exists, records = wr.at_pointer(states[spec['scene_context_id']]['entities'],spec['pointer'])
        item = {'scene_context_id':spec['scene_context_id'],'pointer':spec['pointer'],'present':exists}
        if exists:
            if not isinstance(records,dict) or any(not isinstance(v,dict) for v in records.values()):
                raise ValueError('an index needs an ID-keyed collection of objects: '+spec['pointer'])
            groups: dict[str,list[str]] = {};unclassified=[]
            for key,record in sorted(records.items()):
                found,value=wr.at_pointer(record,spec['group_by'])
                if not found or not isinstance(value,str):unclassified.append(key)
                else:groups.setdefault(value,[]).append(key)
            item.update(groups=groups,unclassified=unclassified,record_count=len(records))
        total += len(encoded(item))

        result[spec['index_id']]=item
    return result


def materialize(root: Path, relative: str) -> dict[str, Any]:
    if root.is_symlink():
        raise ValueError('project root must not be a symbolic link')
    root=root.resolve(strict=True)
    if not root.is_dir():raise ValueError('project root must be a directory')
    query, fingerprint=load_query(root,relative)
    blobs, sources=wr.source_inventory(root,query,strict=True)
    timeline=wr.load_timeline(query['timeline'],blobs)
    coverage=_coverage(query,timeline,blobs)
    contexts=query.get('scene_context_ids',[])
    selected={None,*contexts}
    for spec in query.get('indexes',[])+query.get('requirements',[])+query.get('views',[]):
        if spec['scene_context_id'] not in selected:
            raise ValueError('unselected scene context: '+str(spec['scene_context_id']))
    states={};total=0
    for context in [None,*sorted(contexts)]:
        identity=sha256_json({'query':fingerprint,'context':context})
        snapshot=resolve_world(base_state=timeline['base'],events=timeline['events'],processes=timeline['processes'],
            timeline_id=query['timeline']['timeline_id'],story_order=query['at']['story_order'],story_time=query['at']['story_time'],
            snapshot_id='MOMENT-'+identity,scene_context_id=context)
        checked=validate_artifact(snapshot)
        if not checked['ok']:raise ValueError('invalid resolved snapshot: '+'; '.join(checked['errors']))
        states[context]=snapshot;total+=len(encoded(snapshot))

    requirements=[]
    for row in query.get('requirements',[]):
        found,value=wr.at_pointer(states[row['scene_context_id']]['entities'],row['pointer'])
        passed=found
        if row['test']=='non_null':passed=found and value is not None
        elif row['test']=='equals':passed=found and canonical_json(value)==canonical_json(row['value'])
        checked={**copy.deepcopy(row),'present':found,'passed':passed,**({'actual_value':value} if found else {})}
        total+=len(encoded(checked))

        requirements.append(checked)
    bindings={};source_map={s['source_id']:s for s in sources};order=query['at']['story_order']
    for binding in query.get('author_bindings',[]):
        if binding['source_id'] not in blobs:raise ValueError('unknown author source: '+binding['source_id'])
        end=binding['end_order']
        if end is not None and end<=binding['start_order']:raise ValueError('author binding has an empty applicability interval')
        applies=binding['start_order']<=order and (end is None or order<end)
        row={**copy.deepcopy(binding),'source_sha256':source_map[binding['source_id']]['sha256'],'applicable_at_moment':applies}
        if applies:
            value,status=_selection(blobs[binding['source_id']],binding['selector'])
            row['selected_content']=value
            if status is not None:row['declared_status']=status
        total+=len(encoded(row))

        bindings[binding['binding_id']]=row
    author={'artifact_type':'story-context','query_id':query['query_id'],'query_sha256':fingerprint,
        'timeline_id':query['timeline']['timeline_id'],**query['at'],'coverage':coverage,'sources':sources,
        'global_snapshot':states[None],'context_snapshots':{k:v for k,v in states.items() if k is not None},
        'indexes':_indexes(query,states),'requirements':requirements,'requirements_ok':all(r['passed'] for r in requirements),
        'author_bindings':bindings,'base_provenance':timeline['base_provenance']}
    author['context_sha256']=sha256_json(author)
    by_req={r['requirement_id']:r for r in requirements};views=[]
    for spec in query.get('views',[]):
        context=spec['scene_context_id'];basis={};guidance=[]
        for group in spec['guidance']:
            for identifier in group['binding_ids']:
                if identifier not in bindings:raise ValueError('unknown author binding: '+identifier)
                binding=bindings[identifier]
                if not binding['applicable_at_moment'] or (binding['scene_context_ids'] and context not in binding['scene_context_ids']):
                    raise ValueError('author binding is not applicable to this view: '+identifier)
                if 'declared_status' in binding and binding['declared_status'] not in {'adopted','user-anchor'}:
                    raise ValueError('view guidance requires adopted intent: '+identifier)
                basis[identifier]={k:copy.deepcopy(binding[k]) for k in ['binding_id','role','source_sha256','selector','start_order','end_order']}
            guidance.append(copy.deepcopy(group))
        checks=[]
        for identifier in spec['requirement_ids']:
            if identifier not in by_req:raise ValueError('view names an unknown requirement: '+identifier)
            check=by_req[identifier]
            if check['scene_context_id']!=context:raise ValueError('view requirement belongs to another context')
            # Conditions can concern secrets; export their result, not their values or wording.
            checks.append({'requirement_id':identifier,'passed':check['passed']})
        packet={'artifact_type':'story-context-consumer-view','view_id':spec['view_id'],'recipient':spec['recipient'],
            'purpose':spec['purpose'],'timeline_id':query['timeline']['timeline_id'],**query['at'],'scene_context_id':context,
            'source_world_state_sha256':states[context]['world_state_sha256'],
            'fields':[wr.leaf(states[context]['entities'],p) for p in spec['fields']],
            'guidance':guidance,'basis':list(basis.values()),'instructions':copy.deepcopy(spec['instructions']),
            'requirements':checks,'requirements_ok':all(c['passed'] for c in checks)}
        packet['view_sha256']=sha256_json(packet)
        total+=len(encoded(packet))

        views.append(packet)
    result={'author':author,'views':views}

    return result


def report(bundle: dict) -> dict:
    author=bundle['author']
    return {'ok':True,'query_id':author['query_id'],'context_sha256':author['context_sha256'],
        'story_order':author['story_order'],'scene_context_ids':sorted(author['context_snapshots']),
        'context_files':{key:'contexts/'+hashlib.sha256(key.encode('utf-8')).hexdigest()+'.json' for key in sorted(author['context_snapshots'])},
        'requirements_ok':author['requirements_ok'],'requirements':author['requirements'],
        'indexes':author['indexes'],'applicable_binding_ids':[k for k,v in author['author_bindings'].items() if v['applicable_at_moment']],
        'view_status':[{'view_id':v['view_id'],'requirements_ok':v['requirements_ok'],
                        'file':'consumer/'+hashlib.sha256(v['view_id'].encode('utf-8')).hexdigest()+'.json'} for v in bundle['views']],
        'review':'Coverage and predicates are declared checks, not evidence of completeness or approval.'}


def output_files(bundle: dict) -> dict[str,bytes]:
    author=bundle['author'];files={'story-context.json':encoded(author),'world-state-snapshot.json':encoded(author['global_snapshot']),
                                 'report.json':encoded(report(bundle))}
    for context,snapshot in author['context_snapshots'].items():
        files['contexts/'+hashlib.sha256(context.encode('utf-8')).hexdigest()+'.json']=encoded(snapshot)
    for view in bundle['views']:
        files['consumer/'+hashlib.sha256(view['view_id'].encode('utf-8')).hexdigest()+'.json']=encoded(view)
    return files


def publish(bundle: dict, target: Path) -> None:
    target=target.absolute()
    if target.exists() or target.is_symlink():raise ValueError('output directory must not already exist')
    if any(p.is_symlink() for p in target.parents):raise ValueError('output parent must not be a symbolic link')
    target.parent.mkdir(parents=True,exist_ok=True)
    lock=target.parent/('.'+target.name+'.story-context-lock');staging=None
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        os.close(fd)
        staging=Path(tempfile.mkdtemp(prefix='.moment-',dir=target.parent))
        for name,raw in output_files(bundle).items():
            p=staging/name;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        for p in [*(x for x in staging.iterdir() if x.is_dir()),staging]:fsync_dir(p)
        if target.exists() or target.is_symlink():raise ValueError('output appeared during build')
        publish_directory(staging,target);fsync_dir(target.parent)
    finally:
        if staging is not None and staging.exists():shutil.rmtree(staging)
        lock.unlink(missing_ok=True)


def verify_output(bundle: dict, directory: Path, *, require_fields: bool=False) -> dict:
    if directory.is_symlink() or not directory.is_dir():raise ValueError('bundle must be a directory')
    expected=output_files(bundle);mismatches=[]
    for name,raw in expected.items():
        try:
            if wr.read_bytes(wr.local_path(directory,name))!=raw:mismatches.append(name)
        except (OSError,ValueError):mismatches.append(name)
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    mismatches.extend(actual-set(expected))
    result=report(bundle)
    result.update(content_ok=not mismatches,mismatched_files=sorted(set(mismatches)),
                  ok=not mismatches and (not require_fields or result['requirements_ok']))
    return result



def verify(root: Path, relative: str, directory: Path, *, require_fields: bool=False) -> dict:
    return verify_output(materialize(root,relative),directory,require_fields=require_fields)


def main(argv: Sequence[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command',choices=['inspect','build','verify'])
    parser.add_argument('--root',required=True,type=Path);parser.add_argument('--query',required=True)
    parser.add_argument('--out',type=Path);parser.add_argument('--bundle',type=Path)
    parser.add_argument('--require-fields',action='store_true',help='Require all declared predicates; applies to inspect, build and verify')
    args=parser.parse_args(argv)
    if (args.command=='build')!=(args.out is not None) or (args.command=='verify')!=(args.bundle is not None):
        parser.error('--out is used only for build; --bundle is used only for verify')
    try:
        if args.command=='verify':result=verify(args.root,args.query,args.bundle,require_fields=args.require_fields)
        else:
            bundle=materialize(args.root,args.query);result=report(bundle)
            result['ok']=not args.require_fields or result['requirements_ok']
            if args.command=='build' and result['ok']:
                publish(bundle,args.out);result['written']=sorted(output_files(bundle))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 1
    except (ValueError,OSError,KeyError,TypeError,UnicodeError,RuntimeError,RecursionError) as exc:
        result={'ok':False,'error':str(exc)}
        if hasattr(exc,'conflicts'):result['conflicts']=exc.conflicts
        print(json.dumps(result,ensure_ascii=False,indent=2));return 1


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
