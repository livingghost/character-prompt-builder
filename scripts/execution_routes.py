#!/usr/bin/env python3
"""Resolve task-scoped reads and verify artifact-bearing execution routes."""
from __future__ import annotations
import operation_context as _operation_context
import argparse
import ast
import json
from pathlib import Path
from typing import Any, Callable
from execution_contract import load, local, read, digest, content_id, decode
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'config/execution-routes.json'
OPERATIONS = ('author', 'save', 'prepare', 'execute', 'review', 'adopt')
EXECUTIONS = ('authored', 'external', 'dispatcher')


def require_scope(operation: str, execution: str) -> None:
    if operation not in OPERATIONS:
        raise ValueError('reading operation must be one of: ' + ', '.join(OPERATIONS))
    if execution not in EXECUTIONS:
        raise ValueError('reading execution must be one of: ' + ', '.join(EXECUTIONS))


def _require_name(manifest: dict[str, Any], kind: str, name: str) -> None:
    """Reject a misplaced or unknown name with its declared selection action."""
    choices = manifest[kind + 's']
    if name in choices:
        return
    other = 'feature' if kind == 'route' else 'route'
    if name in manifest[other + 's']:
        if kind == 'feature':
            action = f'{name!r} is a route; select route {name!r} and remove --feature {name}'
        else:
            action = (f'{name!r} is a feature; choose a route from: '
                      + ', '.join(sorted(choices)) + f'; include --feature {name}')
    else:
        action = f'choose a {kind} from: ' + (', '.join(sorted(choices)) or '(none declared)')
    raise ValueError(f'unknown {kind}: {name}; {action}. '
                     f'Route and feature names are declared separately in {MANIFEST}; '
                     'SKILL.md explains when to select them.')


def resolve(route: str, features: list[str] | None = None, *, execution: str,
            operation: str | None = None, root: Path = ROOT,
            read_source:Callable[[str],bytes]|None=None) -> dict[str, Any]:
    read_source=read_source or (lambda path:read(local(root,path)))
    raw=read_source(MANIFEST)
    manifest=decode(raw)
    _require_name(manifest, 'route', route)
    entry = manifest['routes'][route]
    operation = operation or entry['default_operation']
    require_scope(operation, execution)
    selected = set(entry['features'] + entry.get('execution_features', {}).get(execution, []) + (features or []))
    pending = list(selected)
    while pending:
        name = pending.pop()
        _require_name(manifest, 'feature', name)
        for dependency in manifest['features'][name].get('execution_features', {}).get(execution, []):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    selected = sorted(selected)
    if 'scene-persona' in selected:
        # Reuse is valid only after production verifies explicit scene_materials.
        selected = [f for f in selected if f not in {'persona', 'authorial-intent'}]
    context = manifest['operation_contexts'][operation]
    selections: dict[str, list[str]] = {}
    def include(paths: list[str], owner: str) -> None:
        for path in paths:
            selections.setdefault(path, []).append(owner)
    include(context['reads'], 'operation:' + operation)
    include(context['executions'][execution], 'execution:' + execution)
    include(entry['reads'], 'route:' + route)
    roles: set[str] = set()
    for feature in selected:
        f = manifest['features'][feature]
        include(f['reads'], 'feature:' + feature)
        roles.update(f['source_roles'])
    if 'scene-persona' in selected:
        roles.difference_update({'persona', 'authorial-intent'})
    return {'route':route,'operation':operation,'execution':execution,'features':selected,'source_roles':sorted(roles),
            'reads':[{'path':p,'sha256':digest(read_source(p))} for p in selections],
            'read_owners': selections,
            'stages':entry['stages'],'manifest_sha256':digest(raw)}


def unnamed(manifest: dict[str, Any], skill: str) -> list[str]:
    """Route and feature names SKILL.md omits; its route list is the one the agent reads."""
    return sorted(n for n in set(manifest['routes']) | set(manifest['features']) if f'`{n}`' not in skill)


def validate(root: Path = ROOT) -> dict[str, Any]:
    d=load(local(root,MANIFEST)); errors=[]
    stage_map={s['id']:s for s in d['stages']}
    if set(d['operation_contexts']) != set(OPERATIONS):
        errors.append('reading operations do not cover the current contract')
    for operation, context in d['operation_contexts'].items():
        if set(context['executions']) != set(EXECUTIONS):
            errors.append(f'{operation}: reading execution scopes do not cover the current contract')
    if len(stage_map)!=len(d['stages']): errors.append('duplicate stage')
    for name,route in d['routes'].items():
        try:
            for execution in EXECUTIONS:
                resolve(name, execution=execution, root=root)
            available=set(d['external_inputs'])
            ids=route['stages']
            if not ids:
                raise ValueError('route must name the operations that produce its result')
            for i,sid in enumerate(ids):
                s=stage_map[sid]
                if set(s['inputs'])-available: raise ValueError(f'{sid}: unavailable inputs')
                available.update(s['outputs'])
                wanted=ids[i+1] if i+1<len(ids) else 'done'
                if not isinstance(s['next'], list) or wanted not in s['next'] or s['on_failure'] not in stage_map:
                    raise ValueError(f'{sid}: disconnected success or failure path')
                script,fn=s['owner'].split(':')
                tree=ast.parse(read(local(root,script)).decode('utf-8'))
                funcs={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
                if fn not in funcs or 'main' not in funcs: raise ValueError(f'{sid}: missing implementation')
                if s['resume']!='status': raise ValueError(f'{sid}: invalid recovery entrypoint')
        except (ValueError,KeyError,OSError) as exc: errors.append(f'{name}: {exc}')
    for feature in d['features']:
        try:
            for execution in EXECUTIONS:
                resolve('development',[feature],execution=execution,root=root)
        except (ValueError,OSError) as exc: errors.append(str(exc))
    for operation in d['operation_contexts']:
        try:
            for execution in EXECUTIONS:
                resolve('development', operation=operation, execution=execution, root=root)
        except (ValueError, KeyError, OSError) as exc: errors.append(f'{operation}: {exc}')
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
    parser=_operation_context.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('inspect'); p.add_argument('route'); p.add_argument('--feature',action='append',default=[])
    p.add_argument('--operation', choices=OPERATIONS, help='Current operation; defaults to the route owner')
    p.add_argument('--execution', required=True, choices=EXECUTIONS, help='Execution kind selected by the task')
    reading = sub.add_parser('read', help='Index the selected knowledge; choose sections or --all for exact paged delivery')
    from route_reading import ReadingSourcesChanged, add_read_arguments, read_command
    add_read_arguments(reading)
    sub.add_parser('validate')
    a=parser.parse_args()
    try:
        if a.command == 'read':
            read_command(a, parser)
            return 0
        result=validate() if a.command=='validate' else resolve(a.route,a.feature,operation=a.operation,execution=a.execution)
        print(json.dumps(result,indent=2)); return 0 if result.get('ok',True) else 1
    except (ValueError,OSError) as exc:
        if not getattr(exc, 'reading_result_written', False):
            print(json.dumps({'ok':False,'error':str(exc),
                              **(exc.as_dict() if isinstance(exc, ReadingSourcesChanged) else {})}))
        return 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
