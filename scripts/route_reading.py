#!/usr/bin/env python3
"""Read complete route documents and bind authored applications to issued evidence."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, TextIO

import execution_contract as c
import execution_routes

ROOT = Path(__file__).resolve().parents[1]
_NO_MODEL = object()


def _hex(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length or any(x not in '0123456789abcdef' for x in value):
        raise ValueError(f'{label}: expected {length} lowercase hexadecimal characters')
    return value


def _normalized(value: str) -> str:
    return ' '.join(value.split())


def prose_blocks(document: str) -> list[str]:
    """Parse paragraph containers, excluding headings, tables, code and metadata.

    The parser preserves source spelling. Block markers describe Markdown
    syntax; no vocabulary classifies the subject or meaning of a paragraph.
    """
    result: list[str] = []
    paragraph: list[str] = []
    fence: tuple[str, int] | None = None
    table = False
    frontmatter = False
    html = False
    def flush() -> None:
        if paragraph:
            result.append(_normalized('\n'.join(paragraph)))
            paragraph.clear()
    for index, raw in enumerate(document.splitlines()):
        line = raw.strip()
        if index == 0 and line == '---':
            frontmatter = True
            continue
        if frontmatter:
            if line in {'---', '...'}:
                frontmatter = False
            continue
        probe = raw.lstrip(' ')
        indent = len(raw) - len(probe)
        # A block quote can contain a heading, fenced block or paragraph.
        while probe.startswith('>'):
            probe = probe[1:].lstrip(' ')
        if fence is not None:
            char, count = fence
            close = probe.rstrip()
            if len(close) >= count and all(x == char for x in close):
                fence = None
            continue
        if indent <= 3 and probe and probe[0] in {'`', '~'}:
            count = len(probe) - len(probe.lstrip(probe[0]))
            if count >= 3:
                flush(); table = False; fence = (probe[0], count)
                continue
        if not line:
            flush(); table = False; html = False
            continue
        if html:
            continue
        if probe.startswith('<') and not probe.startswith('<http'):
            flush(); html = True
            continue
        if raw.startswith('    ') or raw.startswith('\t'):
            flush()
            continue
        heading_marks = len(probe) - len(probe.lstrip('#'))
        if 1 <= heading_marks <= 6 and (len(probe) == heading_marks or probe[heading_marks].isspace()):
            flush(); table = False
            continue
        # Setext headings own their preceding paragraph. A delimiter row owns
        # the preceding table header and following table rows.
        if line and set(line) <= {'=', '-'}:
            paragraph.clear(); table = False
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        delimiter = '|' in line and bool(cells) and all(
            len(cell.strip(':')) >= 3 and set(cell.strip(':')) == {'-'} for cell in cells)
        if delimiter:
            paragraph.clear(); table = True
            continue
        if table:
            if '|' in line:
                continue
            table = False
        if len(line.replace(' ', '')) >= 3 and set(line.replace(' ', '')) in ({'*'}, {'_'}, {'-'}):
            flush()
            continue
        if probe.startswith('[') and ']:' in probe:
            flush()
            continue
        paragraph.append(raw)
    flush()
    return result


RESOURCE_FIELDS = {'resources'}
RECORD_RESOURCE_FIELDS = {'resources', 'resource_applied'}
GENERATION_ROUTES = {'generation', 'state-series', 'batch', 'repose', 'character-sheet'}


def _studio(path: Path | None) -> Path | None:
    if path is None:
        return None
    path = path.absolute()
    for folder in [path, *path.parents]:
        if (folder / 'studio.json').is_file():
            return folder
    return None


def ledger_candidates(*, project: Path | None = None, package_root: Path | None = None) -> list[Path]:
    explicit = os.environ.get('CPB_READS_LEDGER')
    if explicit is not None:
        if not explicit.strip():
            raise ValueError('CPB_READS_LEDGER must name a file')
        return [Path(explicit).absolute()]
    output = []
    if project is not None:
        output.append(project.absolute() / 'work/reads.jsonl')
    if package_root is not None:
        output.append(package_root.absolute() / 'reads.jsonl')
    for value in (Path.cwd(), package_root):
        studio = _studio(value)
        if studio is not None:
            output.append(studio / 'work/reads.jsonl')
    output.append(Path.home() / '.character-prompt-builder/reads.jsonl')
    return list(dict.fromkeys(output))


def _capture_resources(manifest: dict, bodies: list) -> None:
    manifest['resources'] = {}
    if 'prompt-dialect' not in manifest['features']:
        return
    from catalog_retrieval.runtime import load_pack_catalog
    from pack_cache import resource_warning
    catalog = load_pack_catalog()
    # A selected provider that failed is not an absent resource: refuse with
    # the one line that names the pack and its fix. Other packs' problems do not block a reading.
    for name in ('prompt-writing-guide', 'prompt-dialects'):
        problem = resource_warning(catalog, name)
        if problem:
            raise ValueError(problem)
    for name in ('prompt-writing-guide', 'prompt-dialects'):
        resource = catalog.resources.get(name)
        if resource is None:
            manifest['resources'][name] = {'status': 'unavailable'}
            continue
        path = Path(resource.path).absolute()
        roots = {entry.source_root.absolute() for entry in catalog.entries if entry.source_pack == resource.source_pack}
        if not roots:
            for folder in path.parents:
                candidate = folder / 'pack.json'
                if candidate.is_file() and c.load(candidate).get('pack_id') == resource.source_pack:
                    roots.add(folder); break
        if len(roots) != 1:
            raise ValueError('resource provider must identify exactly one pack root: ' + name)
        relative = path.relative_to(next(iter(roots))).as_posix()
        raw = c.read(c.local(next(iter(roots)), relative)); c.decode(raw)
        meta = {'status': 'present', 'source_pack': resource.source_pack, 'path': relative, 'sha256': c.digest(raw)}
        manifest['resources'][name] = meta
        bodies.append(({'kind': 'resource', 'resource': name, **meta}, raw))


def _validate_resources(value: dict) -> None:
    resources = value.get('resources')
    expected = {'prompt-writing-guide', 'prompt-dialects'} if 'prompt-dialect' in value['features'] else set()
    if not isinstance(resources, dict) or set(resources) != expected:
        raise ValueError('reading resource set differs from its feature requirements')
    for item in resources.values():
        if isinstance(item, dict) and item.get('status') == 'unavailable':
            c.exact(item, {'status'}, 'unavailable resource')
        else:
            c.exact(item, {'status', 'source_pack', 'path', 'sha256'}, 'reading resource')
            if item['status'] != 'present':
                raise ValueError('invalid resource status')
            c.sha(item['sha256']); c.text(item['source_pack'], 'resource provider')
            c.local(ROOT, item['path'], exists=False)


def _require_resource_applications(record: dict, bodies: list, dialect: str | None) -> None:
    applications = record['resource_applied']
    if not isinstance(applications, list):
        raise ValueError('resource applications must be an array')
    available = {meta['resource']: c.decode(raw) for meta, raw in bodies if meta['kind'] == 'resource'}
    if dialect is not _NO_MODEL and dialect is not None:
        ids = {x['id'] for x in available.get('prompt-dialects', {}).get('dialects', [])}
        if dialect not in ids:
            raise ValueError('model dialect is absent from the active resource: ' + dialect)
    for item in applications:
        c.exact(item, {'resource', 'pointer', 'quote', 'why'}, 'resource application')
        c.text(item['why'], 'resource application reason')
        if item['resource'] != 'prompt-writing-guide' or item['resource'] not in available:
            raise ValueError('resource application must refer to the active writing guide')
        parts = item['pointer'].split('/') if isinstance(item['pointer'], str) else []
        if len(parts) != 5 or parts[0] or parts[1] != 'sections' or parts[3] != 'rules':
            raise ValueError('guide pointer must select a section rule')
        try:
            i, j = int(parts[2]), int(parts[4])
            if str(i) != parts[2] or str(j) != parts[4] or i < 0 or j < 0:
                raise ValueError('noncanonical index')
            section = available[item['resource']]['sections'][i]
            rule = section['rules'][j]
        except (ValueError, IndexError, KeyError, TypeError) as exc:
            raise ValueError('guide pointer has no rule') from exc
        if not isinstance(rule, str) or item['quote'] != rule:
            raise ValueError('guide quote differs from the complete decoded rule')
        # With no selected model, a route reading may cite any real section.
        # Model-facing validation supplies the declared dialect and checks it.
        if dialect is not _NO_MODEL and section.get('dialects') and dialect not in section['dialects']:
            raise ValueError('guide section does not apply to the selected model dialect')
    if 'prompt-writing-guide' in available and not applications:
        raise ValueError('missing application for the active prompt-writing-guide')


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    from pack_runtime_cli import add_pack_runtime_arguments
    add_pack_runtime_arguments(parser)


def _configure_runtime(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict | None:
    from pack_runtime_cli import resolve_pack_runtime
    from catalog_retrieval.runtime import configure_pack_runtime
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    return {'state_file': str(runtime.settings.state_file), 'cache_dir': str(runtime.settings.cache_dir),
            'managed_root': str(runtime.settings.managed_root), 'extra_roots': [str(p) for p in runtime.pack_roots]}


def _restore_runtime(runtime: dict | None) -> None:
    if runtime is not None:
        from pack_manager import default_settings
        from catalog_retrieval.runtime import configure_pack_runtime
        configure_pack_runtime(default_settings(state_file=Path(runtime['state_file']), cache_dir=Path(runtime['cache_dir']),
            managed_root=Path(runtime['managed_root']), extra_roots=[Path(p) for p in runtime['extra_roots']]))



def ledger_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = c.read(path)
    if raw and not raw.endswith(b'\n'):
        raise ValueError(f'incomplete reading ledger: {path}')
    rows = []
    fields = {'at', 'route', 'features', 'key_sha256', 'documents', 'cwd'} | RESOURCE_FIELDS
    for line in raw.splitlines():
        if not line.strip():
            raise ValueError(f'empty reading ledger row: {path}')
        row = c.decode(line)
        c.exact(row, fields, 'reading ledger row')
        c.sha(row['key_sha256'])
        c.text(row['at'], 'reading timestamp'); c.text(row['cwd'], 'reading cwd')
        _validate_manifest(row)
        rows.append(row)
    return rows


def _validate_manifest(value: dict[str, Any]) -> None:
    c.text(value.get('route'), 'reading route')
    features = value.get('features')
    if not isinstance(features, list) or any(not isinstance(x, str) or not x for x in features):
        raise ValueError('reading features must be explicit strings')
    if features != sorted(set(features)):
        raise ValueError('reading features must be normalized and unique')
    documents = value.get('documents')
    if not isinstance(documents, list) or not documents:
        raise ValueError('reading documents must be a nonempty array')
    seen = set()
    for item in documents:
        c.exact(item, {'path', 'sha256'}, 'reading document')
        c.local(ROOT, item['path'], exists=False); c.sha(item['sha256'])
        if item['path'] in seen:
            raise ValueError('duplicate reading document')
        seen.add(item['path'])
    _validate_resources(value)


def capture(route: str, features: list[str] | None = None, *, root: Path = ROOT) -> tuple[dict, list[tuple[dict, bytes]]]:
    resolved = execution_routes.resolve(route, features, root=root)
    bodies = []
    for entry in resolved['reads']:
        raw = c.read(c.local(root, entry['path']))
        raw.decode('utf-8')
        if c.digest(raw) != entry['sha256']:
            raise ValueError('document changed while reading: ' + entry['path'])
        bodies.append(({'kind': 'document', **entry}, raw))
    manifest = {'route': resolved['route'], 'features': resolved['features'], 'documents': resolved['reads']}
    _capture_resources(manifest, bodies)
    return manifest, bodies


def _issue(manifest: dict, ledger: Path, *, key: str | None = None, at: str | None = None, cwd: str | None = None) -> dict:
    """Append under the caller's lock. Fixed values support synthetic fixtures."""
    key = _hex(key or secrets.token_hex(16), 32, 'reading key')
    row = {**manifest, 'at': at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'cwd': cwd if cwd is not None else str(Path.cwd()), 'key_sha256': c.digest(key.encode('ascii'))}
    existing = ledger_rows(ledger)
    for old in existing:
        if old['key_sha256'] == row['key_sha256'] and any(old[k] != row[k] for k in manifest):
            raise ValueError('reading key already belongs to different documents or route')
    if row in existing:
        return {'reading_key': key, 'row': row}
    c.atomic(ledger, b''.join(c.encoded(x) for x in existing) + c.encoded(row), replace=ledger.exists())
    return {'reading_key': key, 'row': row}


def issue(route: str, features: list[str] | None = None, *, root: Path = ROOT,
          project: Path | None = None, ledger: Path | None = None, stream: TextIO | None = None,
          key: str | None = None, at: str | None = None, cwd: str | None = None) -> dict:
    """Output all bytes before issuing evidence. Fixed key/time are fixture inputs."""
    stream = sys.stdout if stream is None else stream
    target = ledger if ledger is not None else ledger_candidates(project=project)[0]
    manifest, bodies = capture(route, features, root=root)
    for meta, raw in bodies:
        stream.write('--- ' + json.dumps(meta, ensure_ascii=False) + ' ---\n')
        stream.write(raw.decode('utf-8'))
        stream.write('\n')
    stream.flush()
    with c.lock(target.parent):
        current, _ = capture(route, features, root=root)
        if manifest != current:
            raise ValueError('reading sources changed; read the current documents')
        issued = _issue(manifest, target, key=key, at=at, cwd=cwd)
    stream.write('reading-key: ' + route + ' ' + issued['reading_key'] + '\n')
    stream.flush()
    return issued


def _find_row(record: dict, ledgers: list[Path]) -> dict:
    key_hash = c.digest(_hex(record.get('reading_key'), 32, 'reading key').encode('ascii'))
    matching = []
    for path in dict.fromkeys(ledgers):
        for row in ledger_rows(path):
            if row['key_sha256'] == key_hash:
                matching.append(row)
    if not matching:
        raise ValueError('reading key has no issuance row in the selected ledgers')
    fields = {'route', 'features', 'documents'} | RESOURCE_FIELDS
    if any(any(row[field] != record[field] for field in fields) for row in matching):
        raise ValueError('reading issuance differs from the supplied route, features or document versions')
    return matching[0]


def validate_record_content(record: Any) -> None:
    """Check the recorded contract without granting a current execution permission."""
    fields = {'route', 'features', 'reading_key', 'documents', 'applied'} | RECORD_RESOURCE_FIELDS
    c.exact(record, fields, 'route reading')
    _validate_manifest(record)
    _hex(record['reading_key'], 32, 'reading key')
    available = {item['path'] for item in record['documents']}
    if not isinstance(record['applied'], list):
        raise ValueError('reading applications must be an array')
    for item in record['applied']:
        c.exact(item, {'path', 'quote', 'why'}, 'document application')
        c.text(item['quote'], 'quotation')
        c.text(item['why'], 'application reason')
        if item['path'] not in available:
            raise ValueError('quotation document is absent from the recorded edition')
    if RECORD_RESOURCE_FIELDS:
        if not isinstance(record['resource_applied'], list):
            raise ValueError('resource applications must be an array')
        for item in record['resource_applied']:
            c.exact(item, {'resource', 'pointer', 'quote', 'why'}, 'resource application')
            for field in item:
                c.text(item[field], field)
            if item['resource'] not in record['resources']:
                raise ValueError('quotation resource is absent from the recorded edition')


def require_route_reading(record: Any, *, root: Path = ROOT, ledgers: list[Path] | None = None,
                          project: Path | None = None, package_root: Path | None = None,
                          routes: set[str] | None = None, features: list[str] | None = None,
                          dialect: Any = _NO_MODEL) -> dict:
    fields = {'route', 'features', 'reading_key', 'documents', 'applied'} | RECORD_RESOURCE_FIELDS
    validate_record_content(record)
    if routes is not None and record['route'] not in routes:
        raise ValueError('reading route must be one of: ' + ', '.join(sorted(routes)))
    if features is not None:
        expected_features = execution_routes.resolve(record['route'], features, root=root)['features']
        if expected_features != record['features']:
            raise ValueError('reading features do not match the execution features')
    current, bodies = capture(record['route'], record['features'], root=root)
    for field in current:
        if record[field] != current[field]:
            raise ValueError('reading ' + field + ' differs from the current sources; read again')
    row = _find_row(record, ledgers if ledgers is not None else ledger_candidates(project=project, package_root=package_root))
    applications = record['applied']
    if not isinstance(applications, list):
        raise ValueError('reading applications must be an array')
    required = {x['path'] for x in record['documents']} - set(c.load(c.local(root, execution_routes.MANIFEST))['always_read'])
    available = {meta['path']: raw.decode('utf-8') for meta, raw in bodies if meta['kind'] == 'document'}
    covered = set()
    for item in applications:
        c.exact(item, {'path', 'quote', 'why'}, 'document application')
        c.text(item['why'], 'application reason')
        quote = _normalized(c.text(item['quote'], 'quote'))
        if item['path'] not in available:
            raise ValueError('quote refers to a document outside this route')
        if len(quote.split()) < 12 or not any(quote in block for block in prose_blocks(available[item['path']])):
            raise ValueError('quote must contain at least twelve words of paragraph text: ' + item['path'])
        covered.add(item['path'])
    if required - covered:
        raise ValueError('missing application for: ' + ', '.join(sorted(required - covered)))
    _require_resource_applications(record, bodies, dialect)
    return row


def resolve_issuance(key: str, *, project: Path | None = None,
                     ledgers: list[Path] | None = None) -> dict:
    """Resolve a supplied key to one consistent locally issued document edition."""
    digest = c.digest(_hex(key, 32, 'reading key').encode('ascii'))
    matches = [row for path in dict.fromkeys(ledgers if ledgers is not None else ledger_candidates(project=project))
               for row in ledger_rows(path) if row['key_sha256'] == digest]
    if not matches:
        raise ValueError('reading key has no issuance row in the selected ledgers')
    fields = {'route', 'features', 'documents'} | RESOURCE_FIELDS
    if any(any(row[field] != matches[0][field] for field in fields) for row in matches[1:]):
        raise ValueError('reading key has conflicting issuance records')
    return {'reading_key': key, 'row': matches[0]}


def check_snapshot_issuance(snapshot: str, issued: dict, *, project: Path | None = None) -> None:
    """Check a supplied delivery selector without making retention a key condition."""
    _hex(snapshot, 64, 'reading snapshot')
    paths = [path.parent / 'reading-snapshots' / snapshot / 'snapshot.json'
             for path in ledger_candidates(project=project)]
    existing = [path for path in dict.fromkeys(paths) if path.is_file()]
    if not existing:
        # A completed delivery snapshot may be discarded. The issuance row
        # remains the authoritative key witness.
        return
    for path in existing:
        value = c.load(path)
        if c.content_id(value) != snapshot:
            raise ValueError('reading snapshot address mismatch')
        if any(issued['row'][key] != item for key, item in value['manifest'].items()):
            raise ValueError('selected delivery snapshot belongs to another reading')


def build_record(issued: dict, applications: dict, *, root: Path = ROOT,
                 project: Path | None = None, ledgers: list[Path] | None = None,
                 dialect: Any = _NO_MODEL) -> dict:
    c.exact(issued, {'reading_key', 'row'}, 'issued reading')
    row = issued['row']
    result = {key: row[key] for key in sorted({'route', 'features', 'documents'} | RESOURCE_FIELDS)}
    result.update(reading_key=issued['reading_key'], applied=applications['applied'])
    if RESOURCE_FIELDS:
        result['resource_applied'] = applications['resource_applied']
    require_route_reading(result, root=root, project=project, ledgers=ledgers, dialect=dialect)
    return result



def copy_issuance(record: dict, destination: Path, *, root: Path = ROOT, project: Path | None = None,
                  ledgers: list[Path] | None = None, package_root: Path | None = None) -> dict:
    """Copy a verified issuance row without issuing a key or an application."""
    row = require_route_reading(record, root=root, project=project, ledgers=ledgers, package_root=package_root)
    with c.lock(destination.parent):
        rows = ledger_rows(destination)
        matching = [old for old in rows if old['key_sha256'] == row['key_sha256']]
        fields = {'route', 'features', 'documents'} | RESOURCE_FIELDS
        if any(any(old[k] != row[k] for k in fields) for old in matching):
            raise ValueError('destination ledger has a conflicting issuance')
        if not matching:
            c.atomic(destination, b''.join(c.encoded(old) for old in rows) + c.encoded(row), replace=destination.exists())
    return row

def _snapshot_dir(ledger: Path, snapshot: str) -> Path:
    return c.local(ledger.parent, 'reading-snapshots/' + _hex(snapshot, 64, 'reading snapshot'))


def _cursor(ledger: Path, cursor: str) -> tuple[Path, dict, dict]:
    parts = cursor.split(':')
    if len(parts) != 2:
        raise ValueError('reading cursor must identify a snapshot and a delivered page')
    folder = _snapshot_dir(ledger, parts[0])
    snapshot = c.load(c.local(folder, 'snapshot.json'))
    if c.content_id(snapshot) != parts[0]:
        raise ValueError('reading snapshot address mismatch')
    receipt = c.load(c.local(folder, 'pages/' + _hex(parts[1], 64, 'reading page') + '.json'))
    if c.content_id(receipt) != parts[1] or receipt['snapshot'] != parts[0]:
        raise ValueError('reading page address mismatch')
    return folder, snapshot, receipt


def _position(snapshot: dict, offset: int) -> tuple[int, int]:
    for index, meta in enumerate(snapshot['bodies']):
        if offset < meta['size']:
            return index, offset
        offset -= meta['size']
    if offset:
        raise ValueError('reading cursor exceeds the snapshot')
    return len(snapshot['bodies']), 0


def read_page(*, route: str | None = None, features: list[str] | None = None,
              cursor: str | None = None, replay: bool = False, page_bytes: int = 16384,
              root: Path = ROOT, project: Path | None = None, ledger: Path | None = None,
              stream: TextIO | None = None, runtime: dict | None = None) -> dict:
    """Deliver an immutable page, then record its exact byte range under a lock."""
    if isinstance(page_bytes, bool) or not isinstance(page_bytes, int) or page_bytes < 4:
        raise ValueError('page-bytes must be an integer of at least four')
    stream = sys.stdout if stream is None else stream
    ledger = ledger if ledger is not None else ledger_candidates(project=project)[0]
    with c.lock(ledger.parent):
        if cursor is None:
            if route is None:
                raise ValueError('a route is required to start reading')
            manifest, bodies = capture(route, features, root=root)
            snapshot = {'manifest': manifest, 'root': str(root.absolute()), 'runtime': runtime,
                        'nonce': secrets.token_hex(16), 'bodies': [dict(meta, size=len(raw)) for meta, raw in bodies]}
            sid = c.content_id(snapshot)
            folder = c.local(ledger.parent, 'reading-snapshots/' + sid, exists=False)
            folder.mkdir(parents=True)
            c.atomic(folder / 'snapshot.json', c.encoded(snapshot))
            for _, raw in bodies:
                c.object_store(folder, raw)
            start = 0
        else:
            if route is not None or features:
                raise ValueError('a cursor fixes its route and features')
            folder, snapshot, page = _cursor(ledger, cursor)
            sid = c.content_id(snapshot)
            if str(root.absolute()) != snapshot['root']:
                raise ValueError('reading cursor belongs to a different skill root')
            _restore_runtime(snapshot['runtime'])
            start = page['start'] if replay else page['end']
        total = sum(x['size'] for x in snapshot['bodies'])
        if cursor is not None and start == total and not replay:
            raise ValueError('reading is complete; replay the final page to receive a new key')
        index, offset = _position(snapshot, start)
        budget = page_bytes
        end = start
        ranges = []
        pending = {'snapshot': sid, 'start': start, 'end': start, 'ranges': []}
        pending_id = c.content_id(pending)
        pending_path = folder / 'pages' / (pending_id + '.json')
        if not pending_path.exists():
            c.atomic(pending_path, c.encoded(pending))
        stream.write('reading-start: ' + sid + ':' + pending_id + '\n')
        stream.flush()
        while index < len(snapshot['bodies']) and budget:
            meta = snapshot['bodies'][index]
            raw = c.object_read(folder, meta['sha256'])
            stop = min(len(raw), offset + budget)
            while stop > offset and stop < len(raw) and raw[stop] & 0xC0 == 0x80:
                stop -= 1
            if stop == offset and offset < len(raw):
                break
            segment = raw[offset:stop]
            header = {'snapshot': sid, 'kind': meta['kind'], 'path': meta['path'],
                      'sha256': meta['sha256'], 'start': offset, 'end': stop, 'total': len(raw)}
            stream.write('--- ' + json.dumps(header, ensure_ascii=False) + ' ---\n')
            stream.write(segment.decode('utf-8')); stream.write('\n')
            ranges.append(header)
            end += len(segment); budget -= len(segment)
            if stop == len(raw):
                index += 1; offset = 0
            else:
                offset = stop
        stream.flush()
        page = {'snapshot': sid, 'start': start, 'end': end, 'ranges': ranges}
        page_id = c.content_id(page)
        page_path = folder / 'pages' / (page_id + '.json')
        if page_path.exists():
            if c.load(page_path) != page:
                raise ValueError('reading page collision')
        else:
            c.atomic(page_path, c.encoded(page))
        result = {'snapshot': sid, 'cursor': sid + ':' + page_id, 'delivered': ranges,
                  'remaining_bytes': total - end}
        if end == total:
            # Completion depends on a contiguous cover of committed deliveries.
            covered = sorted((p['start'], p['end']) for p in (c.load(x) for x in (folder / 'pages').glob('*.json')))
            reach = 0
            for low, high in covered:
                if low > reach:
                    raise ValueError('undelivered range in reading snapshot')
                reach = max(reach, high)
            if reach != total:
                raise ValueError('reading snapshot is incomplete')
            current, _ = capture(snapshot['manifest']['route'], snapshot['manifest']['features'], root=root)
            if current != snapshot['manifest']:
                raise ValueError('sources changed during reading; start a new read')
            result['issued'] = _issue(current, ledger)
    stream.write('reading-cursor: ' + result['cursor'] + '\n')
    if 'issued' in result:
        stream.write('reading-key: ' + snapshot['manifest']['route'] + ' ' + result['issued']['reading_key'] + '\n')
    stream.flush()
    return result


def add_read_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('route', nargs='?')
    parser.add_argument('--feature', action='append', default=[])
    parser.add_argument('--root', type=Path, help='Project or studio root for the reading ledger')
    parser.add_argument('--page-bytes', type=int)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--continue', dest='cursor')
    group.add_argument('--replay', dest='replay')
    _add_runtime_arguments(parser)


def read_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    runtime = _configure_runtime(args, parser)
    if args.cursor or args.replay or args.page_bytes is not None:
        return read_page(route=args.route, features=args.feature, cursor=args.cursor or args.replay,
                         replay=bool(args.replay), page_bytes=16384 if args.page_bytes is None else args.page_bytes,
                         project=args.root, runtime=runtime)
    if args.route is None:
        raise ValueError('read requires a route or a continuation cursor')
    return issue(args.route, args.feature, project=args.root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    try:
        row = require_route_reading(c.load(args.record), project=args.root, package_root=args.record.parent)
        print(json.dumps({'ok': True, 'route': row['route'], 'evidence': 'issuance and exact quotation'}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
