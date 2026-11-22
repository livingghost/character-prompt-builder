#!/usr/bin/env python3
"""Resolve task-scoped reads and verify artifact-bearing execution routes."""
from __future__ import annotations
import shlex
import operation_context as _operation_context
import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any, Callable
from execution_contract import load, local, read, digest, content_id, decode
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'config/execution-routes.json'
OPERATIONS = ('author', 'save', 'prepare', 'execute', 'review', 'adopt', 'withdraw')
EXECUTIONS = ('authored', 'external', 'dispatcher')
CURATION_SCOPES = ('delivery-only', 'studio-slot', 'sheet', 'catalog')
SOURCE_KINDS = ('production-candidate', 'imported-iteration')


def require_authoring_scope(value: dict | None, operation: str, execution: str) -> None:
    """A selected authoring stage refines only its actual input operation."""
    if value is None:
        return
    if operation not in {'author', 'save', 'prepare'}:
        raise ValueError('authoring choices select author, save or prepare knowledge; '
                         'use the next operation\'s own reading action for ' + operation)
    from production_reading_scope import validate
    validate(value, reading_operation=operation, execution=execution)


def require_scope(operation: str, execution: str, scope: str | None = None,
                  source_kind: str | None = None) -> None:
    if operation not in OPERATIONS:
        raise ValueError('reading operation must be one of: ' + ', '.join(OPERATIONS))
    if execution not in EXECUTIONS:
        raise ValueError('reading execution must be one of: ' + ', '.join(EXECUTIONS))
    if operation in {'adopt', 'withdraw'}:
        if scope not in CURATION_SCOPES or source_kind not in SOURCE_KINDS:
            raise ValueError(operation + ' reading requires --scope ' + ', '.join(CURATION_SCOPES)
                + ' and --source-kind ' + ', '.join(SOURCE_KINDS)
                + '; use the reading action returned by draft-acceptance or draft-adoption, '
                  'or select the actual sheet withdrawal destination and source owner')
        if operation == 'withdraw' and scope != 'sheet':
            raise ValueError('withdraw reading uses --scope sheet; sheet withdrawal does not revoke a catalog pack')
        if scope == 'delivery-only' and source_kind != 'production-candidate':
            raise ValueError('delivery-only selection belongs to a Production candidate; '
                             'an imported iteration uses --scope studio-slot, sheet or catalog')
    elif scope is not None or source_kind is not None:
        raise ValueError('--scope and --source-kind select adoption or withdrawal knowledge; '
                         'choose --operation adopt or withdraw for that retained result')


def markdown_headings(raw: bytes) -> list[tuple[int, str, int]]:
    """Locate actual Markdown headings and keep fenced examples as source text."""
    headings, offset, fence, previous = [], 0, None, None
    for line in raw.splitlines(keepends=True):
        text = line.decode('utf-8').rstrip('\r\n')
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', text)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            previous = None
        elif marker:
            fence = marker[1]
            previous = None
        else:
            heading = re.match(r'^ {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$', text)
            underline = re.match(r'^ {0,3}(=+|-+)[ \t]*$', text)
            if heading:
                title = re.sub(r'[ \t]+#+[ \t]*$', '', heading[2] or '').strip()
                headings.append((offset, title or 'Untitled heading', len(heading[1])))
            elif underline and previous is not None:
                headings.append((previous[0], previous[1], 1 if underline[1][0] == '=' else 2))
            previous = (offset, text.strip()) if text.strip() and not heading and not underline else None
        offset += len(line)
    return headings


def document_sections(raw: bytes) -> list[dict]:
    """Partition source bytes at headings; a selected section includes its full body.

    The manifest names prerequisites and child sections explicitly. Selecting a
    parent heading alone never silently includes or omits another required owner.
    """
    headings = markdown_headings(raw)
    if not headings or headings[0][0]:
        headings.insert(0, (0, 'Source opening', 0))
    seen, result = {}, []
    for index, (start, heading, level) in enumerate(headings):
        anchor = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        count = seen.get(anchor, 0)
        seen[anchor] = count + 1
        anchor += '-' + str(count) if count else ''
        end = headings[index + 1][0] if index + 1 < len(headings) else len(raw)
        result.append({'anchor': anchor, 'heading': heading, 'level': level,
                       'start': start, 'end': end, 'sha256': digest(raw[start:end])})
    return result


def curation_selections(operation: str) -> list[tuple[str, str]]:
    """The actual destinations and independent source owners a curation read serves."""
    if operation == 'withdraw':
        return [('sheet', source) for source in SOURCE_KINDS]
    return [(scope, source) for scope in CURATION_SCOPES for source in SOURCE_KINDS
            if scope != 'delivery-only' or source == 'production-candidate']


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
            scope: str | None = None, source_kind: str | None = None,
            authoring_scope: dict | None = None,
            read_source:Callable[[str],bytes]|None=None) -> dict[str, Any]:
    read_source=read_source or (lambda path:read(local(root,path)))
    manifest_raw=read_source(MANIFEST)
    manifest=decode(manifest_raw)
    _require_name(manifest, 'route', route)
    entry = manifest['routes'][route]
    if authoring_scope is not None:
        from production_reading_scope import validate as validate_authoring_scope
        validate_authoring_scope(authoring_scope)
    if operation is None and authoring_scope is not None:
        from production_reading_scope import operation as stage_operation
        operation = stage_operation(authoring_scope['stage'], execution)
    operation = operation or entry['default_operation']
    require_scope(operation, execution, scope, source_kind)
    require_authoring_scope(authoring_scope, operation, execution)
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
    profile_name = ('amendment' if authoring_scope is not None and 'change_scope' in authoring_scope
                    else 'authoring' if authoring_scope is not None else operation)
    profile = manifest.get('reading_scopes', {}).get(profile_name)
    if authoring_scope is not None and profile is None:
        raise ValueError('the route manifest has no scoped reading owner for authoring')
    if operation in {'adopt', 'withdraw'} and profile is None:
        raise ValueError('the route manifest has no scoped reading owner for ' + operation)
    managed = profile['documents'] if profile is not None else {}
    deferred = profile.get('deferred_documents', {}) if profile is not None else {}
    documents, owners, section_owners = [], {}, {}
    # Curation declares its source owners independently of the route defaults.
    # Other operations refine only documents the actual route/features selected;
    # a profile must never activate an otherwise unselected specialist.
    paths = [*selections, *managed] if operation in {'adopt', 'withdraw'} else selections
    for path in dict.fromkeys(paths):
        if path in deferred:
            continue
        selected_by = selections.get(path, [])
        rules = [rule for rule in managed.get(path, [])
                 if ('scopes' not in rule or scope in rule['scopes'])
                 and ('source_kinds' not in rule or source_kind in rule['source_kinds'])
                 and ('executions' not in rule or execution in rule['executions'])
                 and ('features_any' not in rule or set(selected) & set(rule['features_any']))
                 and (authoring_scope is None or _matches_authoring(rule, authoring_scope))]
        if path in managed and not rules and (operation in {'adopt', 'withdraw'} or authoring_scope is not None):
            continue
        raw = read_source(path)
        raw.decode('utf-8')
        source = {'path': path, 'sha256': digest(raw), 'size': len(raw)}
        complete = [rule for rule in rules if rule.get('whole_source')]
        if not rules or complete:
            ranges = [{'start': 0, 'end': len(raw), 'sha256': source['sha256']}]
            reasons = [{'anchor': None, **ranges[0], 'selected_by': selected_by,
                        'reason': (' '.join(dict.fromkeys(rule['reason'] for rule in complete))
                                   if complete else 'Complete source required by ' + ', '.join(selected_by) + '.')}]
        else:
            available = {row['anchor']: row for row in document_sections(raw)}
            wanted = {}
            for rule in rules:
                reason = rule.get('reason')
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError('scoped reading needs a section selection reason: ' + path)
                for anchor in rule['sections']:
                    if anchor not in available:
                        raise ValueError('required reading section is absent: ' + path + '#' + anchor)
                    wanted.setdefault(anchor, []).append(reason)
            selection = (['scope:' + scope, 'source-kind:' + source_kind]
                         if operation in {'adopt', 'withdraw'} else ['operation:' + operation])
            if authoring_scope is not None:
                selection.append('authoring-stage:' + authoring_scope['stage'])
                selection.extend('authoring-profile:' + name for name in authoring_scope.get('profiles', []))
            reasons = [{**available[anchor], 'selected_by': list(dict.fromkeys([*selected_by, *selection])),
                        'reason': ' '.join(dict.fromkeys(values))}
                       for anchor, values in wanted.items()]
            reasons.sort(key=lambda row: row['start'])
            ranges = [{key: row[key] for key in ('start', 'end', 'sha256')} for row in reasons]
            selected_by = list(dict.fromkeys([*selected_by, *selection]))
        if not ranges:
            continue
        documents.append({**source, 'ranges': ranges})
        owners[path] = selected_by
        section_owners[path] = reasons
    return {'route':route,'operation':operation,'execution':execution,'scope':scope,'source_kind':source_kind,
            **({'authoring_scope': authoring_scope} if authoring_scope is not None else {}),
            'features':selected,'source_roles':sorted(roles), 'reads':documents,
            'read_owners': owners, 'section_owners': section_owners,
            'stages':entry['stages'],'manifest_sha256':digest(manifest_raw)}


def _matches_authoring(rule: dict, selection: dict) -> bool:
    from production_reading_scope import matches
    return matches(rule, selection)


def unnamed(manifest: dict[str, Any], skill: str) -> list[str]:
    """Route and feature names SKILL.md omits; its route list is the one the agent reads."""
    return sorted(n for n in set(manifest['routes']) | set(manifest['features']) if f'`{n}`' not in skill)


def validate(root: Path = ROOT) -> dict[str, Any]:
    d=load(local(root,MANIFEST)); errors=[]
    implementations = {}

    def functions(script):
        if script not in implementations:
            tree = ast.parse(read(local(root, script)).decode('utf-8'))
            implementations[script] = {node.name for node in tree.body
                                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        return implementations[script]

    stage_map={s['id']:s for s in d['stages']}
    if set(d['operation_contexts']) != set(OPERATIONS):
        errors.append('reading operations do not cover the current contract')
    for operation, context in d['operation_contexts'].items():
        if set(context['executions']) != set(EXECUTIONS):
            errors.append(f'{operation}: reading execution scopes do not cover the current contract')
    for operation, profile in d.get('reading_scopes', {}).items():
        if operation not in (*OPERATIONS, 'authoring', 'amendment'):
            errors.append('unknown reading profile operation: ' + operation)
        deferred = profile.get('deferred_documents', {})
        if not isinstance(deferred, dict):
            errors.append(operation + ': deferred_documents must name documents and their other-phase ownership')
            deferred = {}
        for path, reason in deferred.items():
            if path in profile['documents'] or not isinstance(reason, str) or not reason.strip():
                errors.append(operation + ': a deferred document needs one reason and no selected section rules: ' + path)
            try:
                read(local(root, path)).decode('utf-8')
            except (ValueError, OSError, TypeError) as exc:
                errors.append(f'{operation}: {path}: {exc}')
        for path, rules in profile['documents'].items():
            try:
                available = {row['anchor'] for row in document_sections(read(local(root, path)))}
                for rule in rules:
                    allowed = {'sections', 'whole_source', 'reason', 'scopes', 'source_kinds', 'executions', 'features_any'}
                    if operation in {'authoring', 'amendment'}:
                        allowed.update({'stages', 'compositions', 'conditions_any', 'conditions_all', 'conditions_none'})
                    if operation == 'amendment':
                        allowed.update({'profiles_any', 'changes_any'})
                    if set(rule) - allowed:
                        raise ValueError('unknown reading selector fields')
                    if not isinstance(rule.get('reason'), str) or not rule['reason'].strip():
                        raise ValueError('a required source needs its selection reason')
                    whole = rule.get('whole_source', False)
                    if type(whole) is not bool or (whole and 'sections' in rule):
                        raise ValueError('choose whole_source or explicit sections')
                    if not whole and (not isinstance(rule.get('sections'), list) or not rule['sections']
                                      or set(rule['sections']) - available):
                        raise ValueError('required reading section is absent or empty')
                    for field, choices in (('scopes', CURATION_SCOPES), ('source_kinds', SOURCE_KINDS),
                                           ('executions', EXECUTIONS), ('features_any', d['features'])):
                        if field in rule and (not isinstance(rule[field], list) or not rule[field]
                                              or set(rule[field]) - set(choices)):
                            raise ValueError('invalid reading selector: ' + field)
                    if operation not in {'adopt', 'withdraw'} and {'scopes', 'source_kinds'} & set(rule):
                        raise ValueError('curation destination/source selectors do not select another operation')
                    if operation in {'authoring', 'amendment'}:
                        from production_reading_scope import STAGES, CONDITIONS
                        for field, choices in (('stages', STAGES), ('compositions', ('compose', 'amend')),
                                               ('conditions_any', CONDITIONS), ('conditions_all', CONDITIONS),
                                               ('conditions_none', CONDITIONS)):
                            if field in rule and (not isinstance(rule[field], list) or not rule[field]
                                                  or set(rule[field]) - set(choices)):
                                raise ValueError('invalid authoring reading selector: ' + field)
                        if 'profiles_any' in rule:
                            from production_reading_scope import PROFILES
                            if (not isinstance(rule['profiles_any'], list) or not rule['profiles_any']
                                    or set(rule['profiles_any']) - set(PROFILES)):
                                raise ValueError('invalid amendment reading profiles')
                        if 'changes_any' in rule:
                            from production_change_scope import CHANGE_SCOPES
                            if (not isinstance(rule['changes_any'], list) or not rule['changes_any']
                                    or set(rule['changes_any']) - set(CHANGE_SCOPES)):
                                raise ValueError('invalid amendment changed fields')
            except (ValueError, OSError, TypeError) as exc:
                errors.append(f'{operation}: {path}: {exc}')
    if len(stage_map)!=len(d['stages']): errors.append('duplicate stage')
    def resolve_scopes(route, features=None, *, operation=None, execution):
        chosen = operation or d['routes'][route]['default_operation']
        scopes = curation_selections(chosen) if chosen in {'adopt', 'withdraw'} else [(None, None)]
        for scope, source_kind in scopes:
            resolve(route, features, operation=chosen, execution=execution, root=root,
                    scope=scope, source_kind=source_kind)
    for name,route in d['routes'].items():
        try:
            for execution in EXECUTIONS:
                resolve_scopes(name, execution=execution)
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
                if fn not in functions(script): raise ValueError(f'{sid}: missing implementation')
                command = shlex.split(s['command'])
                if len(command) < 2 or command[0] not in {'python', 'python3'}:
                    raise ValueError(f'{sid}: invalid command entrypoint')
                if 'main' not in functions(command[1]):
                    raise ValueError(f'{sid}: missing command entrypoint')
                if s['resume']!='status': raise ValueError(f'{sid}: invalid recovery entrypoint')
        except (ValueError,KeyError,OSError) as exc: errors.append(f'{name}: {exc}')
    for feature in d['features']:
        try:
            for execution in EXECUTIONS:
                resolve_scopes('development',[feature],execution=execution)
        except (ValueError,OSError) as exc: errors.append(str(exc))
    for operation in d['operation_contexts']:
        try:
            for execution in EXECUTIONS:
                resolve_scopes('development', operation=operation, execution=execution)
        except (ValueError, KeyError, OSError) as exc: errors.append(f'{operation}: {exc}')
    for name, operation in d.get('operations', {}).items():
        try:
            script, function = operation['owner'].split(':')
            if function not in functions(script):
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
    p=sub.add_parser('inspect'); p.add_argument('route', nargs='?'); p.add_argument('--feature',action='append',default=[])
    p.add_argument('--operation', choices=OPERATIONS, help='Current operation; defaults to the route owner')
    p.add_argument('--execution', choices=EXECUTIONS, help='Execution kind selected by the task; derived with --choices')
    p.add_argument('--scope', choices=CURATION_SCOPES, help='Retained-result destination for adopt or withdraw')
    p.add_argument('--source-kind', choices=SOURCE_KINDS, help='Independent owner of the retained image or artifact')
    p.add_argument('--root', type=Path, help='Studio root when selecting editable --choices')
    p.add_argument('--choices', help='Studio-relative input choices; derive the current authoring stage and source conditions')
    reading = sub.add_parser('read', help='Index the selected knowledge; choose sections or --all for exact paged delivery')
    from route_reading import ReadingSourcesChanged, add_read_arguments, read_command
    add_read_arguments(reading)
    sub.add_parser('validate')
    a=parser.parse_args()
    try:
        if a.command == 'read':
            read_command(a, parser)
            return 0
        if a.command == 'validate':
            result = validate()
        else:
            authoring_scope = None
            if a.choices is not None:
                if a.root is None:
                    raise ValueError('--choices requires --root STUDIO to acquire the selected editable input')
                from production_reading_scope import from_choices, operation
                authoring_scope, task = from_choices(a.root, a.choices)
                for field in ('route', 'execution'):
                    supplied = getattr(a, field)
                    if supplied is not None and supplied != task[field]:
                        raise ValueError(field + ' differs from --choices; follow its current reading action')
                    setattr(a, field, task[field])
                a.feature = list(dict.fromkeys([*task.get('features', []), *a.feature]))
                a.operation = a.operation or operation(authoring_scope['stage'], a.execution)
            if a.route is None or a.execution is None:
                raise ValueError('inspect needs a route and --execution, or --root STUDIO --choices FILE')
            result = resolve(a.route,a.feature,operation=a.operation,execution=a.execution,
                             scope=a.scope,source_kind=a.source_kind,authoring_scope=authoring_scope)
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
