#!/usr/bin/env python3
"""Compile scoped realizations from the existing state ledger, without creating canon.

    python scripts/world_realization.py inspect --root PROJECT --plan plan.json
    python scripts/world_realization.py build --root PROJECT --plan plan.json --out NEW_DIR
    python scripts/world_realization.py verify --root PROJECT --plan plan.json --bundle DIR
    python scripts/world_realization.py impact --root PROJECT --plan plan.json

Only current local, hash-pinned inputs are read. No network, rendering, implicit
state propagation, approval, semantic inference, source writes or format migration.
See references/runtime/world-realization.md for the contract and review limits.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Sequence

from authorial_intent_audit import parse_document as parse_intents
from state_protocol import (ENTITY_BUCKETS, canonical_json, parse_json, resolve_world,
                            sha256_json, validate_against_schema, validate_artifact, validate_temporal_inputs)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/authoring/world-realization-plan.schema.json'
from io_budget import read_stream
from execution_contract import publish_directory
EVIDENCE_KEYS = {'source_id', 'locator', 'basis'}
EVIDENCE_BASES = {'source-explicit', 'author-decision', 'inference', 'observation'}


def local_path(root: Path, supplied: str) -> Path:
    """A portable, literal, project-relative file. No URL decoding or path guessing."""
    if (not supplied or '\\' in supplied or '\x00' in supplied
            or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', supplied)):
        raise ValueError('expected a literal relative local path')
    rel = Path(supplied)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('input path escapes its root')
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symbolic links are not accepted as inputs')
    if not current.is_file():
        raise ValueError(f'input is not a regular file: {supplied}')
    return current


def read_bytes(path: Path, maximum: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError('expected a regular input file')
    with path.open('rb') as stream:
        return read_stream(stream, maximum, label=str(path))


def tokens(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('expected a non-root JSON Pointer')
    parts = pointer[1:].split('/')
    if any(re.search(r'~(?![01])', part) for part in parts):
        raise ValueError('invalid JSON Pointer escape')
    return [part.replace('~1', '/').replace('~0', '~') for part in parts]


def at_pointer(value: Any, pointer: str) -> tuple[bool, Any]:
    current = value
    for part in tokens(pointer):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and re.fullmatch(r'0|[1-9][0-9]*', part):
            index = int(part)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, copy.deepcopy(current)


def leaf(value: Any, pointer: str, *, required: bool = False) -> dict[str, Any]:
    parts = tokens(pointer)
    minimum = 2 if parts and parts[0] == 'world' else 3
    if len(parts) < minimum or parts[0] not in ENTITY_BUCKETS.values():
        raise ValueError('select a field below an explicit entity or the aggregate world bucket')
    exists, selected = at_pointer(value, pointer)
    if isinstance(selected, (dict, list)) and exists:
        raise ValueError('consumer fields and reference facets must be scalar leaves, not containers')
    if required and not exists:
        raise ValueError(f'required field is not established: {pointer}')
    result: dict[str, Any] = {'pointer': pointer, 'present': exists}
    if exists:
        result['value'] = selected
    return result


def leaf_paths(value: Any, prefix: str = '') -> list[str]:
    if isinstance(value, dict):
        return [p for key, item in value.items()
                for p in leaf_paths(item, prefix + '/' + key.replace('~', '~0').replace('/', '~1'))]
    if isinstance(value, list):
        return [p for index, item in enumerate(value) for p in leaf_paths(item, prefix + f'/{index}')]
    return [prefix]


def unique(rows: list[dict[str, Any]], key: str, context: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError(f'duplicate {context}: {row[key]}')
        result[row[key]] = row
    return result


def load_plan(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    raw = read_bytes(local_path(root, relative))
    value = parse_json(raw.decode('utf-8'))
    errors = validate_against_schema(value, parse_json(SCHEMA.read_text(encoding='utf-8')))
    if errors:
        raise ValueError('invalid realization plan: ' + '; '.join(errors))
    return value, hashlib.sha256(raw).hexdigest()


def source_inventory(root: Path, plan: dict[str, Any], *, strict: bool) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    unique(plan['sources'], 'source_id', 'source ID')
    blobs: dict[str, bytes] = {}
    rows = []
    total = 0
    for source in plan['sources']:
        row = dict(source)
        try:
            raw = read_bytes(local_path(root, source['path']))
            total += len(raw)
            digest = hashlib.sha256(raw).hexdigest()
            row.update(actual_sha256=digest, size_bytes=len(raw), matches=digest == source['sha256'])
            if not row['matches'] and strict:
                raise ValueError(f'source fingerprint changed: {source["source_id"]}')
            blobs[source['source_id']] = raw
        except (OSError, ValueError, RuntimeError) as exc:
            if strict:
                raise ValueError(f'{source["source_id"]}: {exc}') from exc
            row.update(matches=False, error=str(exc))
        rows.append(row)
    return blobs, rows


def decode_json(blobs: dict[str, bytes], identifier: str) -> Any:
    if identifier not in blobs:
        raise ValueError(f'unresolved source: {identifier}')
    raw = blobs[identifier]
    return parse_json(raw.decode('utf-8'))


def decode_events(blobs: dict[str, bytes], identifier: str) -> list[dict[str, Any]]:
    if identifier not in blobs:
        raise ValueError(f'unresolved source: {identifier}')
    values = []
    for number, line in enumerate(blobs[identifier].decode('utf-8').splitlines(), 1):
        if line.strip():
            value = parse_json(line)
            if not isinstance(value, dict):
                raise ValueError(f'event line {number} is not an object')
            values.append(value)
    return values


def evidence_refs(evidence: list[Any], blobs: dict[str, bytes], *, needed: bool) -> set[str]:
    if needed and not evidence:
        raise ValueError('established state needs explicit evidence locators')
    refs = set()
    for entry in evidence:
        if not isinstance(entry, dict) or set(entry) != EVIDENCE_KEYS:
            raise ValueError('evidence requires source_id, locator and basis')
        if entry['source_id'] not in blobs:
            raise ValueError(f'unresolved evidence source: {entry["source_id"]}')
        if not isinstance(entry['locator'], str) or not entry['locator'].strip():
            raise ValueError('evidence needs a nonblank source locator')
        if entry['basis'] not in EVIDENCE_BASES:
            raise ValueError('unrecognized evidence basis')
        refs.add(entry['source_id'])
    return refs


def load_timeline(spec: dict[str, Any], blobs: dict[str, bytes]) -> dict[str, Any]:
    base = decode_json(blobs, spec['base_source'])
    if not isinstance(base, dict) or set(base) != set(ENTITY_BUCKETS.values()):
        raise ValueError('base must explicitly contain the five state-protocol buckets')
    for bucket, entities in base.items():
        if not isinstance(entities, dict) or (bucket != 'world' and any(not isinstance(x, dict) for x in entities.values())):
            raise ValueError(f'{bucket}: entities must be explicitly keyed objects')
    deps = {spec['base_source'], spec['events_source'], spec['processes_source']}
    proved = []
    for row in spec['base_provenance']:
        parts = tokens(row['pointer'])
        if (len(parts) < 2 and parts != ['world']) or parts[0] not in ENTITY_BUCKETS.values():
            raise ValueError('base provenance needs an entity or a more specific field')
        if not at_pointer(base, row['pointer'])[0]:
            raise ValueError('base provenance targets a missing state field')
        if row['pointer'] in proved:
            raise ValueError('duplicate base provenance pointer')
        proved.append(row['pointer'])
        deps.update(evidence_refs(row['evidence'], blobs, needed=True))
    missing = [p for p in leaf_paths(base)
               if not any(tokens(p)[:len(tokens(a))] == tokens(a) for a in proved)]
    if missing:
        raise ValueError('base state has no recorded basis: ' + ', '.join(missing))
    events = decode_events(blobs, spec['events_source'])
    processes = decode_json(blobs, spec['processes_source'])
    if not isinstance(processes, list):
        raise ValueError('process source must be an explicit JSON array')
    for expected, records in [('state-event', events), ('state-process', processes)]:
        for record in records:
            if not isinstance(record, dict) or record.get('artifact_type') != expected:
                raise ValueError(f'expected {expected} input')
            report = validate_artifact(record)
            if not report['ok']:
                raise ValueError(f'{expected}: ' + '; '.join(report['errors']))
            deps.update(evidence_refs(record['evidence'], blobs, needed=record['canon_status'] == 'approved'))
    temporal_errors = validate_temporal_inputs(events=events, processes=processes)
    if temporal_errors:
        raise ValueError('invalid event/process graph: ' + '; '.join(temporal_errors[:8]))
    return {'base':base, 'events':events, 'processes':processes, 'dependencies':deps,
            'base_provenance':spec['base_provenance']}


def require_sources(identifiers: list[str], blobs: dict[str, bytes]) -> None:
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('duplicate source dependency')
    for identifier in identifiers:
        if identifier not in blobs:
            raise ValueError(f'unresolved source: {identifier}')


def compile_plan(root: Path, relative: str) -> dict[str, Any]:
    """Resolve independent boundaries, then construct only explicitly selected views."""
    plan, digest = load_plan(root, relative)
    blobs, sources = source_inventory(root, plan, strict=True)
    source_map = {s['source_id']: s for s in sources}
    timelines = {key:load_timeline(spec, blobs) for key, spec in
                 unique(plan['timelines'], 'timeline_id', 'timeline ID').items()}
    unique(plan['units'], 'unit_id', 'unit ID')
    notes = ['Hashes and declared status do not establish adoption, source truth, intent applicability or artistic quality.',
             'All snapshots and diagnostics are author-facing. Export only individually reviewed consumer files.',
             'Evidence locators are retained, not interpreted or verified against source meaning.']
    if not plan['units']:
        notes.append('Empty plan: no realization or intentional absence has been established.')
    units = []
    compiled_bytes = 0
    for unit in plan['units']:
        if unit['timeline_id'] not in timelines:
            raise ValueError(f'unresolved timeline: {unit["timeline_id"]}')
        timeline = timelines[unit['timeline_id']]
        deps = set(timeline['dependencies'])
        require_sources(unit['portrayal_sources'], blobs)
        deps.update(unit['portrayal_sources'])
        intents = []
        for binding in unit['intent_refs']:
            identifier = binding['source_id']
            require_sources([identifier], blobs)
            parsed = parse_intents(blobs[identifier].decode('utf-8'))
            target = parsed['intents'].get(binding['intent_id'])
            if parsed['errors'] or target is None:
                raise ValueError(f'unresolved or malformed intent: {identifier}#{binding["intent_id"]}')
            intents.append({**binding, 'declared_status':target['declared_status']})
            deps.add(identifier)
            if target['declared_status'] not in {'adopted','user-anchor'}:
                notes.append(f'{unit["unit_id"]}: intent {binding["intent_id"]} is not recorded as adopted; review before execution.')
            if parsed['gaps']:
                notes.append(f'{unit["unit_id"]}: intent source contains drafting gaps; structure is not readiness.')
        boundaries = {}
        for which in ('opening','closing'):
            point = unit[which]
            snapshot = resolve_world(base_state=timeline['base'], events=timeline['events'], processes=timeline['processes'],
                timeline_id=unit['timeline_id'], story_order=point['story_order'], story_time=point['story_time'],
                snapshot_id=f'{plan["plan_id"]}-{unit["unit_id"]}-{which}', scene_context_id=unit['scene_context_id'])
            checked = validate_artifact(snapshot)
            if not checked['ok']:
                raise ValueError('resolved snapshot is invalid: ' + '; '.join(checked['errors']))
            boundaries[which] = snapshot
        queries = {}
        unique(unit['reference_queries'], 'query_id', 'reference query ID')
        for query in unit['reference_queries']:
            entity_parts = tokens(query['entity_pointer'])
            if (len(entity_parts) != 2 and entity_parts != ['world']) or entity_parts[0] not in ENTITY_BUCKETS.values():
                raise ValueError('reference query must name an explicit entity')
            if len(query['facets']) != len(set(query['facets'])):
                raise ValueError('reference query contains duplicate facets')
            facets = []
            state = boundaries[query['at']]['entities']
            for pointer in sorted(query['facets']):
                if tokens(pointer)[:len(entity_parts)] != entity_parts:
                    raise ValueError('reference query facet belongs to another entity')
                facets.append(leaf(state, pointer, required=True))
            key_payload = {'timeline_id':unit['timeline_id'], 'entity_pointer':query['entity_pointer'],
                           'role':query['role'], 'facets':facets}
            queries[query['query_id']] = {**query, 'facet_values':facets, 'state_key':sha256_json(key_payload)}
        unique(unit['views'], 'view_id', 'consumer view ID')
        views = []
        for view in unit['views']:
            selected = []
            seen = set()
            for selection in view['state_fields']:
                key = (selection['at'], selection['pointer'])
                if key in seen:
                    raise ValueError('duplicate consumer field selection')
                seen.add(key)
                selected.append({'at':selection['at'], **leaf(boundaries[selection['at']]['entities'], selection['pointer'])})
            if len(view['reference_query_ids']) != len(set(view['reference_query_ids'])):
                raise ValueError('duplicate consumer reference query')
            query_keys = []
            for identifier in view['reference_query_ids']:
                if identifier not in queries:
                    raise ValueError(f'unknown reference query: {identifier}')
                # Facet values, source paths and author-only rationales are deliberately not exported.
                q = queries[identifier]
                query_keys.append({'query_id':identifier, 'role':q['role'], 'state_key':q['state_key']})
            packet = {'artifact_type':'realization-consumer-view', 'unit_id':unit['unit_id'], 'view_id':view['view_id'],
                      'recipient':view['recipient'], 'purpose':view['purpose'], 'medium':unit['medium'],
                      'state_fields':selected, 'reference_keys':query_keys, 'instructions':copy.deepcopy(view['instructions'])}
            packet['view_sha256'] = sha256_json(packet)
            views.append(packet)
        applied = set(boundaries['opening']['applied_event_ids']) | set(boundaries['closing']['applied_event_ids'])
        active_process_ids = {m.split('@epoch-', 1)[0] for b in boundaries.values() for m in b['applied_process_milestones']}
        units.append({'unit_id':unit['unit_id'], 'medium':unit['medium'], 'timeline_id':unit['timeline_id'],
                      'boundaries':boundaries, 'intent_refs':intents,
                      'dependencies':[{'source_id':s,'sha256':source_map[s]['sha256']} for s in sorted(deps)],
                      'base_provenance':copy.deepcopy(timeline['base_provenance']),
                      'event_basis':[{'event_id':e['event_id'], 'cause':e['cause'], 'evidence':e['evidence']}
                                     for e in timeline['events'] if e['event_id'] in applied],
                      'process_basis':[{'process_id':p['process_id'], 'evidence':p['evidence']}
                                       for p in timeline['processes'] if p['process_id'] in active_process_ids],
                      'reference_queries':list(queries.values()), 'views':views, 'review_note':unit['review_note']})
        compiled_bytes += len(canonical_json(units[-1]).encode('utf-8'))
    by_id = {u['unit_id']:u for u in units}
    diagnostics = []
    for link in plan['links']:
        if link['from_unit'] not in by_id or link['to_unit'] not in by_id:
            raise ValueError('continuity link names a missing unit')
        left = by_id[link['from_unit']]['boundaries']['closing']
        right = by_id[link['to_unit']]['boundaries']['opening']
        if link['relation']=='continuous' and (left['timeline_id'] != right['timeline_id'] or left['story_order'] > right['story_order']):
            raise ValueError('continuous link needs the same timeline and nondecreasing boundary orders; use an explicitly authored relation for other links')
        if link['relation']=='continuous' and not link['assertions']:
            notes.append(f'{link["from_unit"]} -> {link["to_unit"]}: continuous link has no authored field checks.')
        for assertion in link['assertions']:
            a = leaf(left['entities'], assertion['from_pointer'])
            b = leaf(right['entities'], assertion['to_pointer'])
            known = a['present'] and b['present']
            equal = known and canonical_json(a['value']) == canonical_json(b['value'])
            passed = known and (equal if assertion['comparison']=='equal' else not equal)
            diagnostics.append({**link, 'assertion':assertion, 'passed':bool(passed),
                                'reason':'declared comparison holds' if passed else 'missing field or declared comparison does not hold'})
    result = {'artifact_type':'world-realization-bundle', 'plan_id':plan['plan_id'], 'plan_status':plan['status'],
              'plan_sha256':digest, 'ok':all(d['passed'] for d in diagnostics), 'sources':sources,
              'presentation_order':[u['unit_id'] for u in units], 'units':units, 'continuity_checks':diagnostics,
              'review_notes':notes, 'semantics_and_adoption':'not_assessed'}
    result['bundle_sha256'] = sha256_json(result)
    return result


def impact(root: Path, relative: str) -> dict[str, Any]:
    plan, digest = load_plan(root, relative)
    blobs, rows = source_inventory(root, plan, strict=False)
    changed = {r['source_id'] for r in rows if not r['matches']}
    # An evidence source can support any state in a timeline. Conservative review
    # deliberately does not claim that a changed source is irrelevant to an earlier scene.
    timeline_deps = {}
    for t in plan['timelines']:
        deps = {t['base_source'],t['events_source'],t['processes_source']}
        for record in t['base_provenance']:
            deps.update(e['source_id'] for e in record['evidence'])
        for source, loader in [(t['events_source'],decode_events),(t['processes_source'],decode_json)]:
            try:
                for record in loader(blobs, source):
                    deps.update(e['source_id'] for e in record.get('evidence',[]) if isinstance(e,dict) and 'source_id' in e)
            except (ValueError, UnicodeError, TypeError, KeyError):
                deps.update(changed)  # unreadable history requires broad re-review, not inferred safety
        timeline_deps[t['timeline_id']] = deps
    affected = []
    for u in plan['units']:
        deps = timeline_deps.get(u['timeline_id'],set()) | set(u['portrayal_sources']) | {i['source_id'] for i in u['intent_refs']}
        reasons = sorted(deps & changed)
        if reasons:
            affected.append({'unit_id':u['unit_id'],'changed_source_ids':reasons,'view_ids':[v['view_id'] for v in u['views']]})
    return {'ok':not changed, 'plan_sha256':digest, 'sources':rows, 'affected_units':affected,
            'scope':'conservative source dependency impact; no automatic approval change or canon update'}


def bundle_files(bundle: dict[str, Any]) -> dict[str, bytes]:
    def encoded(value: Any) -> bytes:
        return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
    files = {'world-realization-bundle.json':encoded(bundle)}
    for unit in bundle['units']:
        for name, snapshot in unit['boundaries'].items():
            files[f'snapshots/{unit["unit_id"]}-{name}.json'] = encoded(snapshot)
        for view in unit['views']:
            files[f'consumer/{unit["unit_id"]}--{view["view_id"]}.json'] = encoded(view)
    return files


def publish(bundle: dict[str, Any], target: Path) -> None:
    if not bundle['ok']:
        raise ValueError('cannot publish failed explicit continuity checks')
    target = target.absolute()
    if target.exists() or target.is_symlink():
        raise ValueError('output directory must not already exist')
    for parent in target.parents:
        if parent.is_symlink():
            raise ValueError('output parents must not be symbolic links')
    target.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.realization-',dir=target.parent))
    try:
        for relative, raw in bundle_files(bundle).items():
            p=staging/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(raw)
        if target.exists():
            raise ValueError('output destination appeared during build')
        publish_directory(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_bundle(root: Path, relative: str, directory: Path) -> dict[str, Any]:
    if directory.is_symlink():
        raise ValueError('bundle directory must not be a symbolic link')
    bundle = compile_plan(root, relative)
    mismatches=[]
    expected = bundle_files(bundle)
    for name, raw in expected.items():
        try:
            actual = read_bytes(local_path(directory.absolute(),name))
            if actual != raw:
                mismatches.append(name)
        except (ValueError,OSError):
            mismatches.append(name)
    # Reject extras, including a leaked full author source next to consumer views.
    actual_names={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    mismatches.extend(sorted(actual_names-set(expected)))
    return {'ok':bundle['ok'] and not mismatches, 'bundle_sha256':bundle['bundle_sha256'],
            'mismatched_files':sorted(set(mismatches)), 'continuity_ok':bundle['ok'],
            'scope':'exact current-input rebuild and consumer output inventory, not semantic or adoption approval'}


def main(argv: Sequence[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('command',choices=('inspect','build','verify','impact'))
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--plan',required=True,help='literal path relative to root')
    parser.add_argument('--out',type=Path,help='new output directory for build')
    parser.add_argument('--bundle',type=Path,help='existing output directory for verify')
    args=parser.parse_args(argv)
    if (args.command=='build') != (args.out is not None) or (args.command=='verify') != (args.bundle is not None):
        parser.error('--out is required only for build; --bundle is required only for verify')
    try:
        if args.root.is_symlink():
            raise ValueError('project root must not be a symbolic link')
        root=args.root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('project root must be a directory')
        if args.command=='impact':
            result=impact(root,args.plan)
        elif args.command=='verify':
            result=verify_bundle(root,args.plan,args.bundle)
        else:
            result=compile_plan(root,args.plan)
            if args.command=='build':
                publish(result,args.out)
                result={'ok':True,'out':str(args.out.absolute()),'bundle_sha256':result['bundle_sha256'],
                        'written':sorted(bundle_files(result)), 'review_notes':result['review_notes']}
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0 if result['ok'] else 1
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,RecursionError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)],'source_mutation':False},ensure_ascii=False,indent=2))
        return 1


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
