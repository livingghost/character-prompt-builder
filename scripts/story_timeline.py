#!/usr/bin/env python3
"""Project an authored story ledger and shared-resolver views into one read-only HTML.

    python scripts/story_timeline.py --studio STUDIO
    python scripts/story_timeline.py --studio STUDIO --timeline main --story-order 20 --story-time chapter:2 --scene-context-id SC2

state/timeline-view.json selects input files, named viewpoints, evidence sources
and explicit scene-to-current-artwork bindings. External source edits need sync.
"""
from __future__ import annotations
import operation_context as _operation_context

from collections import Counter
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import story_flow
from typing import Any, Callable, Sequence
from urllib.parse import quote, urlsplit

import execution_contract as c
from builder_inputs import BuilderInputs, capture as capture_implementation
from protocol_contract import canonical_json, parse_json, validate_against_schema
from state_ledger import Ledger

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'state/timeline-view.json'
OUTPUT = 'timeline.html'
MARKER = '<!-- CPB story timeline -->'
DEFAULT = {'artifact_type': 'story-timeline-view', 'base_state': 'state/world-state-base.json',
           'events': 'state/events.jsonl', 'processes': None, 'views': [], 'scene_artwork': [], 'evidence_sources': []}


def configured(root: Path) -> bool:
    """Activate for authored state or story sources, not an empty scaffold directory."""
    if any((root / path).exists() or (root / path).is_symlink()
           for path in (CONFIG, DEFAULT['base_state'], DEFAULT['events'])):
        return True
    return story_flow.has_sources(Inputs(root, root / OUTPUT))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _literal_path(name: str) -> str:
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', name):
        raise ValueError('expected a literal Studio-relative path: ' + repr(name))
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('path must stay within the Studio: ' + repr(name))
    return name


def _path(root: Path, name: str, *, exists: bool = True) -> Path:
    return c.local(root, _literal_path(name), exists=exists)


def _href(path: Path, output: Path) -> str:
    return quote(os.path.relpath(path, output.parent).replace(os.sep, '/'), safe='/')


@dataclass
class _Observation:
    fact: dict
    raw: bytes | None
    error: Exception | None
    load: Callable[[], bytes | None]


class Inputs:
    """Observe each path/access contract once and recheck it before publication."""
    def __init__(self, root: Path, output: Path) -> None:
        self.root, self.output = root, output
        self._observations: dict[tuple[str, str], _Observation] = {}
        self.collections: dict[str, list[str]] = {}

    def _members(self, name: str) -> list[str]:
        directory = _path(self.root, name, exists=False)
        if not directory.exists():
            return []
        if not directory.is_dir():
            raise ValueError('scene collection is not a directory: ' + name)
        found = []
        def unreadable(error: OSError) -> None:
            raise error
        for parent, dirs, files in os.walk(directory, followlinks=False, onerror=unreadable):
            # Never traverse a symbolic directory. Report its path as an unreadable
            # source instead of dropping it or reading outside the Studio.
            for child in list(dirs):
                path = Path(parent) / child
                if path.is_symlink():
                    found.append(path.relative_to(self.root).as_posix())
                    dirs.remove(child)
            for child in files:
                path = Path(parent) / child
                if path.suffix.lower() == '.json':
                    found.append(path.relative_to(self.root).as_posix())
        return sorted(found)

    def collection(self, name: str) -> list[str]:
        if name not in self.collections:
            self.collections[name] = self._members(name)
        return list(self.collections[name])

    def _source_path(self, path: Path) -> None:
        if path == self.output or path == self.output.with_suffix('.status.json') or path == self.output.with_suffix('.last-good.html'):
            raise ValueError('a timeline projection cannot be its own input')

    def _load(self, name: str) -> bytes | None:
        path = _path(self.root, name, exists=False)
        self._source_path(path)
        if not path.exists():
            return None
        return c.read(path)

    @staticmethod
    def _observe(name: str, contract: dict | None, load: Callable[[], bytes | None]) -> _Observation:
        fact = {'path': name, 'status': 'missing', 'sha256': None}
        if contract is not None:
            fact['read_contract'] = copy.deepcopy(contract)
        try:
            raw = load()
        except (ValueError, OSError, TypeError) as exc:
            fact.update(status='failed', failure={
                'type': type(exc).__module__ + '.' + type(exc).__qualname__, 'message': str(exc),
                'errno': getattr(exc, 'errno', None), 'winerror': getattr(exc, 'winerror', None)})
            return _Observation(fact, None, exc, load)
        if raw is not None:
            fact.update(status='present', sha256=c.digest(raw), bytes=len(raw))
        return _Observation(fact, raw, None, load)

    def _read(self, name: str, load: Callable[[], bytes | None], *,
              optional: bool = False, contract: dict | None = None) -> bytes | None:
        key = (name, canonical_json(contract) if contract is not None else '')
        if key not in self._observations:
            self._observations[key] = self._observe(name, contract, load)
        observed = self._observations[key]
        if observed.error is not None:
            raise observed.error
        if observed.raw is None and not optional:
            raise ValueError('required story input is missing: ' + name)
        return observed.raw

    def read(self, name: str, *, optional: bool = False) -> bytes | None:
        _literal_path(name)
        return self._read(name, lambda: self._load(name), optional=optional)

    def read_sheet(self, root: Path, relative: str, load: Callable[[], bytes]) -> bytes:
        """Observe the verifier's sheet-boundary access, including its refusal."""
        boundary = root.relative_to(self.root).as_posix()
        name = (root / relative).relative_to(self.root).as_posix()
        contract = {'kind': 'sheet', 'root': boundary, 'relative': relative}
        def access() -> bytes:
            self._source_path(root / relative)
            return load()
        return self._read(name, access, contract=contract)

    def fact(self, name: str) -> dict:
        """The ordinary Studio access fact; another boundary cannot substitute."""
        observed = self._observations.get((name, ''))
        return copy.deepcopy(observed.fact) if observed is not None else {}

    def facts(self) -> list[dict]:
        return [copy.deepcopy(observed.fact) for _, observed in sorted(self._observations.items())]

    def json(self, name: str, *, optional: bool = False):
        raw = self.read(name, optional=optional)
        return parse_json(raw.decode('utf-8-sig')) if raw is not None else None

    def recheck(self) -> None:
        for name, members in self.collections.items():
            if self._members(name) != members:
                raise ValueError('story scene collection changed during projection: ' + name)
        for (name, _), observed in self._observations.items():
            current = self._observe(name, observed.fact.get('read_contract'), observed.load)
            if current.fact != observed.fact:
                change = 'appeared' if observed.fact['status'] == 'missing' and current.fact['status'] == 'present' else 'changed'
                raise ValueError('story input ' + change + ' during projection: ' + name)

    def matches(self, facts: list[dict], collections: list[dict]) -> bool:
        """Acquire a saved display's complete dependencies under their own boundaries.

        Matching contents can reuse a derived picture of the ledger. This
        reader supplies no event, adoption or permission evidence to another
        operation. Missing and failed sources remain observations to compare.
        """
        if not isinstance(facts, list) or not isinstance(collections, list):
            return False
        for fact in facts:
            name = _literal_path(fact['path'])
            contract = fact.get('read_contract')
            try:
                if contract is None:
                    self.read(name, optional=True)
                else:
                    c.exact(contract, {'kind', 'root', 'relative'}, 'story input access')
                    if contract['kind'] != 'sheet':
                        return False
                    from sheet_artifacts import _source_bytes
                    boundary = _path(self.root, contract['root'], exists=False)
                    if (boundary / contract['relative']).relative_to(self.root).as_posix() != name:
                        return False
                    _source_bytes(boundary, contract['relative'], read_source=self.read_sheet)
            except (ValueError, OSError, KeyError, TypeError):
                # The same observed refusal may support the same diagnostic
                # display. A refusal before observation leaves a mismatch.
                pass
        for collection in collections:
            c.exact(collection, {'path', 'members'}, 'story source collection')
            if self.collection(collection['path']) != collection['members']:
                return False
        return self.facts() == facts and self.collection_facts() == collections

    def collection_facts(self) -> list[dict]:
        return [{'path': name, 'members': members} for name, members in sorted(self.collections.items())]


def _events(raw: bytes) -> tuple[list[dict], list[int]]:
    rows, lines = [], []
    for number, line in enumerate(raw.decode('utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = parse_json(line)
        except ValueError as exc:
            raise ValueError(f'events JSONL line {number}: {exc}') from exc
        if not isinstance(value, dict):
            raise ValueError(f'events JSONL line {number} must be an object')
        rows.append(value); lines.append(number)
    return rows, lines


def _config(inputs: Inputs, name: str, implementation: BuilderInputs) -> dict:
    value = inputs.json(name, optional=name == CONFIG)
    if value is None:
        value = copy.deepcopy(DEFAULT)
        if inputs.read('state/processes.json', optional=True) is not None:
            value['processes'] = 'state/processes.json'
    schema = parse_json(implementation.read_bytes('schemas/authoring/story-timeline-view.schema.json').decode('utf-8'))
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError('invalid story-timeline-view: ' + '; '.join(errors))
    for key, identifier in [('views', 'view_id'), ('evidence_sources', 'source_id')]:
        ids = [row[identifier] for row in value[key]]
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate ' + identifier + ' in ' + key)
    return value


def _reference(inputs: Inputs, raw: dict, sources: dict[str, dict]) -> dict:
    """Resolve an explicitly declared local path or HTTP(S) link; never guess a filename."""
    result = {'record': copy.deepcopy(raw), 'status': 'unbound', 'href': None}
    source = sources.get(raw.get('source_id')) if isinstance(raw.get('source_id'), str) else None
    path = raw.get('path') if 'path' in raw else (source or {}).get('path')
    expected = raw.get('sha256') or (source or {}).get('sha256')
    if path is not None:
        try:
            data = inputs.read(path, optional=True)
            if data is None:
                result.update(status='unavailable', message='Declared evidence file is missing.')
            elif expected is not None and c.digest(data) != expected:
                result.update(status='unavailable', message='Evidence bytes differ from the declared hash.')
            else:
                result.update(status='local', href=_href(_path(inputs.root, path), inputs.output), sha256=c.digest(data))
        except (ValueError, OSError, TypeError) as exc:
            result.update(status='unsafe-or-unavailable', message=str(exc))
    elif raw.get('url') is not None:
        try:
            url = raw['url']
            if not isinstance(url, str) or any(ord(ch) < 32 for ch in url):
                raise ValueError('invalid external evidence URL')
            parsed = urlsplit(url)
            if parsed.scheme not in {'https', 'http'} or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('only an explicit HTTP(S) evidence URL without credentials can be linked')
            result.update(status='external-unverified', href=url)
        except (ValueError, TypeError) as exc:
            result.update(status='unsafe-or-unavailable', message=str(exc))
    return result


def _scene_images(inputs: Inputs, config: dict, diagnostics: list[dict]) -> list[dict]:
    """Only an explicitly mapped currently adopted artifact supplies a scene image."""
    import studio
    import sheet_artifacts as fills
    states, verification = {}, {}
    output = []
    for spec in config['scene_artwork']:
        row = {**copy.deepcopy(spec), 'status': 'unavailable', 'href': None, 'artifact_id': None}
        try:
            if not studio.valid_character_id(spec['character']) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', spec['slot']):
                raise ValueError('invalid scene artwork character or slot')
            name = f"characters/{spec['character']}/sheet/sheet-data.json"
            if name not in states:
                from character_sheet import validate_sidecar
                value = inputs.json(name)
                studio.character_home(inputs.root, spec['character'], read_bytes=inputs.read)
                states[name] = validate_sidecar(value)
            sheet_root = _path(inputs.root, name, exists=False).parent
            current = states[name]['slots'].get(spec['slot'], {}).get('current')
            if current is None:
                row.update(status='not-adopted', message='This explicit slot has no current accepted artwork.')
            else:
                fills.verify_acceptance(current, sheet_root, spec['slot'],
                                        cache=verification.setdefault(name, {}), read_source=inputs.read_sheet)
                art = current['artifact']
                approval = current['approval']
                row.update(status='adopted', artifact_id=art['artifact_id'], image_sha256=art['image']['sha256'],
                           href=_href(sheet_root / art['image']['path'], inputs.output),
                           provenance_href=_href(sheet_root / art['provenance']['path'], inputs.output),
                           adoption_sha256=approval['decision_sha256'])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            row['message'] = str(exc)
        if row['status'] == 'unavailable':
            diagnostics.append({'code': 'SCENE_ARTWORK_UNAVAILABLE', 'severity': 'warning',
                'timeline_id': spec['timeline_id'], 'scene_context_id': spec['scene_context_id'],
                'message': row.get('message', 'Declared artwork is unavailable.'), 'character': spec['character'], 'slot': spec['slot']})
        output.append(row)
    return output


def _fields(value: Any, prefix: str = '') -> list[dict]:
    if isinstance(value, dict) and value:
        return [row for key, child in value.items() for row in _fields(child, prefix + '/' + key.replace('~', '~0').replace('/', '~1'))]
    if isinstance(value, list) and value:
        return [row for index, child in enumerate(value) for row in _fields(child, prefix + '/' + str(index))]
    return [{'path': prefix, 'value': value}]


def build_model(root: Path, output: Path, *, config_path: str = CONFIG, selection: dict | None = None,
                implementation: BuilderInputs | None = None) -> tuple[dict, Inputs]:
    # Canonicalize spelling first: a Windows 8.3 or junction-spelled root must
    # match the resolved paths the dependency readers return.
    root = root.resolve(strict=True)
    output = output.resolve()
    implementation = implementation or capture_implementation(ROOT)
    inputs = Inputs(root, output)
    config = _config(inputs, config_path, implementation)
    narrative_sources = story_flow.read_sources(inputs)
    inputs.read(config['base_state'], optional=True)
    inputs.read(config['events'], optional=True)
    narrative_status = inputs.fact(narrative_sources['narrative_source']['path']).get('status')
    # A selected narrative retains its read failure before a state ledger exists.
    # Once either state member exists, the complete pair remains required.
    narrative_only = (config_path == CONFIG and inputs.fact(config_path).get('status') == 'missing'
        and inputs.fact(config['base_state']).get('status') == 'missing'
        and inputs.fact(config['events']).get('status') == 'missing'
        and (narrative_status in {'present', 'failed'} or narrative_sources['scenes']))
    if narrative_only:
        base, events, lines = {}, [], []
    else:
        base = inputs.json(config['base_state'])
        events, lines = _events(inputs.read(config['events']))
    processes = inputs.json(config['processes']) if config['processes'] is not None else []
    if isinstance(processes, dict) and processes.get('artifact_type') == 'state-process':
        processes = [processes]
    ledger = Ledger(base, events, processes)
    audit = ledger.audit()
    diagnostics = copy.deepcopy(audit['diagnostics'])
    sources = {row['source_id']: row for row in config['evidence_sources']}
    cards = []
    for index, event in enumerate(events):
        references = [_reference(inputs, row, sources) for row in event.get('evidence', []) if isinstance(row, dict)] if isinstance(event.get('evidence'), list) else []
        for ref in references:
            if ref['status'] in {'unavailable', 'unsafe-or-unavailable'}:
                diagnostics.append({'code': 'EVIDENCE_UNAVAILABLE', 'severity': 'warning',
                    'event_ids': [event.get('event_id')], 'pointer': f'/events/{index}/evidence',
                    'message': ref.get('message', 'Evidence link unavailable.')})
        changes = event.get('changes') if isinstance(event.get('changes'), list) else []
        cards.append({'event': copy.deepcopy(event), 'line': lines[index], 'references': references,
                      'entity_types': sorted({c['entity_type'] for c in changes if isinstance(c, dict) and isinstance(c.get('entity_type'), str)}),
                      'revision_ids': sorted(ledger.revisions.get(event.get('event_id'), [])),
                      'anchor': 'event-' + c.content_id({'line': lines[index], 'id': event.get('event_id')})[:20]})
    cards.sort(key=lambda card: (str(card['event'].get('timeline_id', '')), card['event'].get('effective_order') if type(card['event'].get('effective_order')) is int else 0, card['line']))
    views = copy.deepcopy(config['views'])
    if selection is not None:
        views = [selection] + [v for v in views if v['view_id'] != selection['view_id']]
    if not views:
        views = ledger.default_views()
    resolved, cache = [], {}
    for view in views:
        query = {key: view[key] for key in ('timeline_id', 'story_order', 'story_time', 'scene_context_id')}
        identity = canonical_json(query)
        if identity not in cache:
            cache[identity] = ledger.resolve(**query, view_id=c.content_id(query))
        answer = copy.deepcopy(cache[identity])
        if answer['ok']:
            answer['fields'] = _fields(answer['snapshot']['entities'])
        else:
            answer['fields'] = []
            diagnostics.extend(answer['diagnostics'])
        resolved.append({'view': view, **answer})
    images = _scene_images(inputs, config, diagnostics)
    # Preserve invalid records for inspection, but never assert a resolved state for them.
    unique = {canonical_json(item): item for item in diagnostics}
    diagnostics = list(unique.values())
    payload = {'artifact_type': 'story-timeline-projection', 'input_config': config,
        'source_paths': {'base': config['base_state'], 'events': config['events'], 'processes': config['processes']},
        'source_links': {'base': None if narrative_only else _href(_path(root, config['base_state']), output),
                         'events': None if narrative_only else _href(_path(root, config['events']), output)},
        'base': base, 'events': cards, 'processes': processes, 'views': resolved,
        'scene_artwork': images, 'diagnostics': diagnostics, 'coverage': audit['coverage'],
        'ok': not any(row['severity'] == 'error' for row in diagnostics),
        'inputs': inputs.facts(),
        'source_collections': inputs.collection_facts(),
        'semantics': {'axis': 'effective_order', 'text_labels': ['effective_from', 'recorded_at', 'disclosed_at', 'story_time'],
            'supersession': 'whole earlier event, from the strictly later editorial revision order; earlier snapshots retain it',
            'scene_local': 'only the explicit selected scene; no inferred scene duration',
            'normal_changes': 'later state changes need no supersedes link',
            'disclosure': 'recorded separately; no untyped label is compared as a date'},
        'implementation_sha256': implementation.fingerprint,
        'publication_request': {'config_path': config_path, 'selection': copy.deepcopy(selection)}}
    payload['flow'] = story_flow.build(payload, narrative_sources)
    # Story drafting/link notices supplement, but do not redefine ledger validity.
    # A structurally valid state is not a verdict on dramatic or semantic coherence.
    payload['projection_id'] = c.content_id(payload)
    return payload, inputs


def render_html(model: dict, generated_at: str, *, implementation: BuilderInputs | None = None) -> str:
    implementation = implementation or capture_implementation(ROOT)
    if implementation.fingerprint != model['implementation_sha256']:
        raise ValueError('story implementation changed after the model was built')
    def text(name: str) -> str:
        return implementation.read_bytes('templates/' + name).decode('utf-8')
    template = text('story-timeline.html')
    template = template.replace('/*CPB_FLOW_CSS*/', text('story-flow.css'))
    template = template.replace('/*CPB_FLOW_JS*/', text('story-flow.js'))
    template = template.replace('/*CPB_GRAPH_CSS*/', text('story-graph.css'))
    template = template.replace('/*CPB_GRAPH_JS*/', text('story-graph.js'))
    # JSON inside a script data block must not be able to terminate that block.
    data = json.dumps({**model, 'generated_at': generated_at}, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return template.replace('/*CPB_DATA*/', data)


def _publication_target(root: Path, out: Path | None) -> Path:
    target = out if out is not None else root / OUTPUT
    if not target.is_absolute():
        target = root / target
    try:
        relative = target.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError('timeline output must be inside the Studio') from exc
    path = _path(root, relative, exists=False)
    if path.suffix.lower() != '.html':
        raise ValueError('timeline output must end in .html')
    if path.exists() and MARKER.encode('ascii') not in c.read(path)[:200]:
        raise ValueError('refusing to replace a file not owned by the story timeline: ' + relative)
    previous = path.with_suffix('.last-good.html')
    if previous.exists() and MARKER.encode('ascii') not in c.read(previous)[:200]:
        raise ValueError('last-good path is not owned by the story timeline')
    status = path.with_suffix('.status.json')
    if status.exists():
        try:
            value = c.load(status)
        except ValueError:
            # A truncated derived receipt is repairable when its companion
            # still establishes this publisher's ownership. An unrelated
            # readable document is never treated as a cache entry.
            if path.exists() and MARKER.encode('ascii') in c.read(path)[:200]:
                return path
            raise
        if not isinstance(value, dict) or value.get('artifact_type') != 'story-timeline-publication' or value.get('output') != relative:
            raise ValueError('publication status path is not owned by the story timeline')
    return path


def _failure(root: Path, output: Path, exc: Exception) -> dict:
    """Publish an explicit unavailable page; retain the previous successful view as stale."""
    status_path = output.with_suffix('.status.json')
    try:
        old = c.load(status_path) if status_path.exists() else {}
    except (ValueError, OSError):
        old = {}
    preserved = None
    if output.exists() and old.get('status') == 'current' and c.sha256_file(output) == old.get('html_sha256'):
        preserved = output.with_suffix('.last-good.html')
        previous = c.read(output).decode('utf-8')
        banner = '<aside role="alert" style="padding:1rem;background:#ffe0b2;color:#222">STALE: a newer timeline update failed. This is the last successful projection, not current state.</aside>'
        c.atomic(preserved, previous.replace('<body>', '<body>' + banner, 1).encode('utf-8'), replace=True)
    elif old.get('last_good'):
        candidate = _path(root, old['last_good'], exists=False)
        if candidate.is_file(): preserved = candidate
    message = str(exc)
    link = ('<p><a href="' + html.escape(_href(preserved, output), quote=True) + '">Inspect last successful view (stale)</a></p>') if preserved else ''
    failed = MARKER + '<!doctype html><html lang="en"><meta charset="utf-8"><title>Story timeline update failed</title><body><h1>Story timeline update failed</h1><p role="alert">No current state is asserted. Canonical files were not changed.</p><pre>' + html.escape(message) + '</pre>' + link + '<p>Repair the named input and run studio.py sync.</p></body></html>'
    c.atomic(output, failed.encode('utf-8'), replace=True)
    result = {'artifact_type': 'story-timeline-publication', 'ok': False, 'code': 'STORY_TIMELINE_UPDATE_FAILED', 'status': 'unavailable', 'message': message,
              'generated_at': _now(), 'output': output.relative_to(root).as_posix(), 'last_good': preserved.relative_to(root).as_posix() if preserved else None,
              'last_success_projection_id': old.get('projection_id') or old.get('last_success_projection_id'),
              'html_sha256': c.sha256_file(output)}
    c.atomic_write_json(status_path, result)
    return result


def _receipt(root: Path, output: Path, model: dict, generated: str, raw: bytes) -> dict:
    return {'artifact_type': 'story-timeline-publication', 'ok': True, 'status': 'current',
            'ledger_ok': model['ok'], 'written': True, 'output': output.relative_to(root).as_posix(),
            'projection_id': model['projection_id'], 'generated_at': generated, 'html_sha256': c.digest(raw),
            'inputs': model['inputs'], 'source_collections': model['source_collections'],
            'implementation_sha256': model['implementation_sha256'],
            'publication_request': model['publication_request'],
            'events': len(model['events']), 'views': len(model['views']),
            'diagnostics': dict(Counter(row['severity'] for row in model['diagnostics']))}


def _read_publication(root: Path, output: Path) -> tuple[dict, dict] | None:
    """Read a complete owned display; malformed derived data is a cache miss."""
    try:
        old = c.load(output.with_suffix('.status.json'))
        if old.get('status') != 'current':
            return None
        raw = c.read(output)
        if c.digest(raw) != old['html_sha256']:
            return None
        matched = re.search(r'<script id="timeline-data" type="application/json">(.*?)</script>',
                            raw.decode('utf-8'), re.S)
        if matched is None:
            return None
        model = parse_json(matched.group(1))
        generated = model.pop('generated_at')
        identity = model.pop('projection_id')
        if c.content_id(model) != identity:
            return None
        model['projection_id'] = identity
        if old != _receipt(root, output, model, generated, raw):
            return None
        return old, model
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return None


def _current_publication(root: Path, output: Path, projection_id: str) -> dict | None:
    """Read a complete matching publication without acquiring a writer lock."""
    current = _read_publication(root, output)
    return {**current[0], 'written': False} if current and current[0]['projection_id'] == projection_id else None


def _reuse_publication(root: Path, output: Path, request: dict, implementation: BuilderInputs) -> dict | None:
    current = _read_publication(root, output)
    if current is None:
        return None
    receipt, model = current
    if (model['implementation_sha256'] != implementation.fingerprint
            or model['publication_request'] != request):
        return None
    inputs = Inputs(root, output)
    try:
        if not inputs.matches(model['inputs'], model['source_collections']):
            return None
        inputs.recheck()
        _require_implementation(implementation)
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return None
    return {**receipt, 'written': False}


def _require_implementation(implementation: BuilderInputs) -> None:
    if capture_implementation(ROOT).fingerprint != implementation.fingerprint:
        raise ValueError('story implementation changed during projection')


def _publish_failure(root: Path, output: Path, exc: Exception) -> dict:
    """Update recovery files while the caller holds the publication owner lock."""
    try:
        return _failure(root, output, exc)
    except (ValueError, OSError) as publication_error:
        # The owner records a durable pending marker when publication is unavailable.
        return {'ok': False, 'status': 'publication-failed', 'code': 'STORY_TIMELINE_UPDATE_FAILED',
                'message': str(exc), 'publication_error': str(publication_error),
                'output': output.relative_to(root).as_posix()}


def refresh(root: Path, *, out: Path | None = None, config_path: str = CONFIG,
            selection: dict | None = None) -> dict:
    root = root.resolve(strict=True)
    output = _publication_target(root, out)
    owner = output.parent / ('.' + output.stem + '.publication')
    try:
        implementation = capture_implementation(ROOT)
        request = {'config_path': config_path, 'selection': copy.deepcopy(selection)}
        current = _reuse_publication(root, output, request, implementation)
        if current is not None:
            return current
        model, inputs = build_model(root, output, config_path=config_path, selection=selection,
                                    implementation=implementation)
        current = _current_publication(root, output, model['projection_id'])
        inputs.recheck()
        _require_implementation(implementation)
        if current is not None:
            return current
        generated = _now()
        raw = render_html(model, generated, implementation=implementation).encode('utf-8')
    except (ValueError, OSError, KeyError, TypeError) as exc:
        with c.lock(owner):
            _publication_target(root, output)
            return _publish_failure(root, output, exc)

    with c.lock(owner):
        # A competing writer may have completed this projection while we built
        # or waited. Recheck ownership, its receipt and the observed inputs.
        _publication_target(root, output)
        try:
            current = _current_publication(root, output, model['projection_id'])
            inputs.recheck()
            _require_implementation(implementation)
            if current is not None:
                return current
            # One atomic document contains its data and all resolved states.
            c.atomic(output, raw, replace=True)
            result = _receipt(root, output, model, generated, raw)
            c.atomic_write_json(output.with_suffix('.status.json'), result)
            from studio_activity import event
            event(root, 'story-timeline-refreshed', result['output'], revision=model['projection_id'],
                  details={'projection_id': model['projection_id'], 'ledger_ok': model['ok'], 'diagnostics': result['diagnostics']})
            return result
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return _publish_failure(root, output, exc)


def notify_state_write(path: Path) -> None:
    """Known CLI writes refresh this projection; external editors explicitly call sync."""
    import studio
    root = studio.studio_root(path.parent)
    if root is None or not configured(root):
        return
    from studio_activity import changed
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    watched = {CONFIG, DEFAULT['base_state'], DEFAULT['events'], 'state/processes.json'}
    try:
        config = c.load(root / CONFIG) if (root / CONFIG).is_file() else DEFAULT
        watched.update(config[key] for key in ('base_state', 'events', 'processes') if config.get(key))
        watched.update(row['path'] for row in config.get('evidence_sources', []))
    except (ValueError, OSError, KeyError, TypeError):
        pass
    # Ordinary narrative/scene writes are projection inputs as well. They do
    # not need a second synopsis or a Flow-only authoring file.
    try:
        status = c.load(root / OUTPUT.replace('.html', '.status.json'))
        watched.update(row['path'] for row in status.get('inputs', []) if isinstance(row.get('path'), str))
    except (ValueError, OSError, KeyError, TypeError):
        pass
    if relative in watched or any(relative == narrative_path or relative.startswith(scenes_path + '/')
                                  for _, narrative_path, scenes_path in story_flow.source_locations()):
        changed(path, 'story-input-written', revision=c.sha256_file(path), details={'path': relative})


def main(argv: Sequence[str] | None = None) -> int:
    import studio
    parser = _operation_context.ArgumentParser(description=__doc__)
    parser.add_argument('--studio', type=Path, required=True)
    parser.add_argument('--out', type=Path, help='Studio-relative HTML path; replaces only a timeline-owned page')
    parser.add_argument('--config', default=CONFIG, help='Studio-relative story-timeline-view JSON')
    parser.add_argument('--timeline')
    parser.add_argument('--story-order', type=int)
    parser.add_argument('--story-time')
    parser.add_argument('--scene-context-id')
    parser.add_argument('--inspect', action='store_true', help='Print the projection JSON without writing a view')
    args = parser.parse_args(argv)
    try:
        root = studio.require_studio(args.studio)
        selection = None
        supplied = [args.timeline is not None, args.story_order is not None, args.story_time is not None]
        if any(supplied) or args.scene_context_id is not None:
            if not all(supplied):
                raise ValueError('a selected state requires --timeline, --story-order and --story-time together')
            selection = {'view_id': 'cli-selected', 'label': 'Explicit CLI selection', 'timeline_id': args.timeline,
                         'story_order': args.story_order, 'story_time': args.story_time, 'scene_context_id': args.scene_context_id}
        if args.inspect:
            result, _ = build_model(root, _publication_target(root, args.out), config_path=args.config, selection=selection)
            print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result['ok'] else 1
        result = refresh(root, out=args.out, config_path=args.config, selection=selection)
        # Also project the newly recorded operator event without inventing a story event.
        from studio_activity import write_timeline
        write_timeline(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['ok'] and result.get('ledger_ok', True) else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'code': 'STORY_TIMELINE_INPUT_INVALID', 'message': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
