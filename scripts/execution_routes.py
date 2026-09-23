#!/usr/bin/env python3
"""Resolve task-scoped reads and verify artifact-bearing execution routes."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
from typing import Any
from execution_contract import load, local, read, digest, content_id
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'config/execution-routes.json'


def resolve(route: str, features: list[str] | None = None, *, root: Path = ROOT) -> dict[str, Any]:
    manifest = load(local(root, MANIFEST))
    if route not in manifest['routes']:
        raise ValueError(f'unknown route: {route}')
    entry = manifest['routes'][route]
    selected = sorted(set(entry['features'] + (features or [])))
    if 'scene-persona' in selected:
        # Reuse is valid only after production verifies explicit scene_materials.
        selected = [f for f in selected if f not in {'persona', 'authorial-intent'}]
    paths = list(manifest['always_read']) + entry['reads']
    roles: set[str] = set()
    for feature in selected:
        if feature not in manifest['features']:
            raise ValueError(f'unknown feature: {feature}')
        f = manifest['features'][feature]
        paths += f['reads']
        roles.update(f['source_roles'])
    if 'scene-persona' in selected:
        roles.difference_update({'persona', 'authorial-intent'})
    paths = list(dict.fromkeys(paths))
    return {'route':route,'features':selected,'source_roles':sorted(roles),
            'reads':[{'path':p,'sha256':digest(read(local(root,p)))} for p in paths],
            'stages':entry['stages'],'manifest_sha256':digest(read(local(root,MANIFEST)))}


def unnamed(manifest: dict[str, Any], skill: str) -> list[str]:
    """Route and feature names SKILL.md omits; its route list is the one the agent reads."""
    return sorted(n for n in set(manifest['routes']) | set(manifest['features']) if f'`{n}`' not in skill)


def validate(root: Path = ROOT) -> dict[str, Any]:
    d=load(local(root,MANIFEST)); errors=[]
    stage_map={s['id']:s for s in d['stages']}
    if len(stage_map)!=len(d['stages']): errors.append('duplicate stage')
    for name,route in d['routes'].items():
        try:
            resolve(name, root=root)
            available=set(d['external_inputs'])
            ids=route['stages']
            if not ids or ids[0]!='prepare' or ids[-1]!='complete':
                raise ValueError('route must bind preparation and completion')
            for i,sid in enumerate(ids):
                s=stage_map[sid]
                if set(s['inputs'])-available: raise ValueError(f'{sid}: unavailable inputs')
                available.update(s['outputs'])
                wanted=ids[i+1] if i+1<len(ids) else 'done'
                if s['next']!=wanted or s['on_failure'] not in ids:
                    raise ValueError(f'{sid}: disconnected success or failure path')
                script,fn=s['owner'].split(':')
                tree=ast.parse(read(local(root,script)).decode('utf-8'))
                funcs={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
                if fn not in funcs or 'main' not in funcs: raise ValueError(f'{sid}: missing implementation')
                if s['resume']!='status': raise ValueError(f'{sid}: invalid recovery entrypoint')
        except (ValueError,KeyError,OSError) as exc: errors.append(f'{name}: {exc}')
    for feature in d['features']:
        try: resolve('development',[feature],root=root)
        except (ValueError,OSError) as exc: errors.append(str(exc))
    for name, operation in d.get('operations', {}).items():
        try:
            script, function = operation['owner'].split(':')
            tree = ast.parse(read(local(root, script)).decode('utf-8'))
            if function not in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}:
                raise ValueError('missing operation implementation')
        except (ValueError, KeyError, OSError) as exc:
            errors.append(f'{name}: {exc}')
    for p in d['regression']:
        if not local(root,p,exists=False).is_file(): errors.append(f'missing regression: {p}')
    skill = read(local(root, 'SKILL.md')).decode('utf-8')
    errors += [f'SKILL.md names no route or feature `{name}`' for name in unnamed(d, skill)]
    return {'ok':not errors,'routes':len(d['routes']),'features':len(d['features']),'stages':len(stage_map),'errors':errors}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('inspect'); p.add_argument('route'); p.add_argument('--feature',action='append',default=[])
    reading = sub.add_parser('read', help='Read the complete route documents and record issuance')
    from route_reading import add_read_arguments, read_command
    add_read_arguments(reading)
    sub.add_parser('validate')
    a=parser.parse_args()
    try:
        if a.command == 'read':
            read_command(a, parser)
            return 0
        result=validate() if a.command=='validate' else resolve(a.route,a.feature)
        print(json.dumps(result,indent=2)); return 0 if result.get('ok',True) else 1
    except (ValueError,OSError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)})); return 1
if __name__=='__main__': raise SystemExit(main())
