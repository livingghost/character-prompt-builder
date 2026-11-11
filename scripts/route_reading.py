#!/usr/bin/env python3
"""Deliver complete operation knowledge and retain its exact source scope."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import datetime
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

import execution_contract as c
import execution_routes
from cli_invocation import python_argv, shown

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE_BYTES = 16384
_NO_MODEL = object()
# A reading made without a model holds every family's guide sections.


def _hex(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length or any(x not in '0123456789abcdef' for x in value):
        raise ValueError(f'{label}: expected {length} lowercase hexadecimal characters')
    return value


MANIFEST_FIELDS = {'route', 'operation', 'execution', 'features', 'documents', 'resources', 'model'}
GENERATION_ROUTES = {'generation', 'state-series', 'batch', 'repose', 'character-sheet'}


class ReadingSourcesChanged(ValueError):
    """Name the source differences that require a current complete delivery."""

    def __init__(self, changes: list[dict], message: str = 'reading sources changed; read the current sources',
                 *, actions: dict | None = None):
        self.changes = changes
        self.actions = actions or {}
        self.required_action = 'Read the current complete material for the requested operation and select its issued reading key.'
        names = ', '.join(str(row.get('path') or row.get('resource') or row.get('id') or row['kind'])
                          for row in changes)
        super().__init__(message + (': ' + names if names else ''))

    def as_dict(self) -> dict:
        return {'code': 'READING_SOURCES_CHANGED', 'changes': self.changes,
                'required_action': self.required_action, 'actions': self.actions}


def source_changes(previous: dict, current: dict, *, required_only: bool = False,
                   include_model: bool = True) -> list[dict]:
    """Compare acquired source identities, retaining each affected owner."""
    changes = []
    for field, key, label in (('documents', 'path', 'document'), ('resources', 'resource', 'resource')):
        before = ({row['path']: row['sha256'] for row in previous.get(field, [])}
                  if field == 'documents' else previous.get(field, {}))
        after = ({row['path']: row['sha256'] for row in current.get(field, [])}
                 if field == 'documents' else current.get(field, {}))
        for name in sorted(set(after) if required_only else set(before) | set(after)):
            if before.get(name) != after.get(name):
                changes.append({'kind': label, key: name,
                                'change': 'added' if name not in before else 'removed' if name not in after else 'modified',
                                'before': before.get(name), 'after': after.get(name)})
    before = set(previous.get('features', [])); after = set(current.get('features', []))
    for name in sorted(after - before if required_only else before ^ after):
        changes.append({'kind': 'feature', 'id': name,
                        'change': 'added' if name in after else 'removed'})
    if include_model and previous.get('model') != current.get('model'):
        changes.append({'kind': 'model', 'id': (current.get('model') or previous.get('model') or {}).get('id'),
                        'before': previous.get('model'), 'after': current.get('model')})
    return changes


def _read_once(root: Path, reader: Callable[[str], bytes] | None = None):
    source = reader or (lambda path: c.read(c.local(root, path)))
    acquired = {}
    def read(path: str) -> bytes:
        if path not in acquired:
            acquired[path] = source(path)
        return acquired[path]
    return read


def _studio(path: Path | None) -> Path | None:
    if path is None:
        return None
    path = path.absolute()
    for folder in [path, *path.parents]:
        if (folder / 'studio.json').is_file():
            return folder
    return None


def ledger_candidates(*, studio: Path | None = None, package_root: Path | None = None,
                      ledger: Path | None = None) -> list[Path]:
    if ledger is not None:
        return [ledger.absolute()]
    explicit = os.environ.get('CPB_READS_LEDGER')
    if explicit is not None:
        if not explicit.strip():
            raise ValueError('CPB_READS_LEDGER must name a file')
        return [Path(explicit).absolute()]
    output = []
    if studio is not None:
        output.append(studio.absolute() / 'work/reads.jsonl')
    if package_root is not None:
        output.append(package_root.absolute() / 'reads.jsonl')
    for value in (Path.cwd(), package_root):
        found = _studio(value)
        if found is not None:
            output.append(found / 'work/reads.jsonl')
    import pack_manager
    output.append(pack_manager.user_data_home() / 'reads.jsonl')
    return list(dict.fromkeys(output))


def _family(name: str, value: dict, dialect: str | None) -> bytes:
    """The resource as one model family reads it. Another family's section keeps its name and families."""
    if name == 'prompt-writing-guide':
        value = {**value, 'sections': [section if not section.get('dialects') or dialect in section['dialects']
                                       else {'id': section['id'], 'dialects': section['dialects']}
                                       for section in value['sections']]}
    else:
        value = {**value, 'dialects': [row for row in value['dialects'] if row['id'] == dialect]}
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def bound_dialect(value: dict) -> Any:
    """The declared model family, or None for interface-neutral guidance."""
    found = {json.dumps(item['dialect']) for item in value['resources'].values() if 'dialect' in item}
    if len(found) > 1:
        raise ValueError('reading resources name different model families')
    return json.loads(found.pop()) if found else None


def _live_resource_reader():
    """Acquire the live catalogue at the route API's input boundary."""
    from catalog_retrieval.runtime import load_pack_catalog
    from pack_cache import resource_warning
    catalog = load_pack_catalog()
    if catalog.resource_reader is not None:
        return catalog.resource_reader
    def read_named(name):
        problem = resource_warning(catalog, name)
        if problem:
            raise ValueError(problem)
        resource = catalog.resources.get(name)
        if resource is None:
            return None
        if resource.source_pack not in catalog.pack_roots:
            raise ValueError(f'named resource {name} comes from a pack without an active root: {resource.source_pack}')
        base=Path(catalog.pack_roots[resource.source_pack])
        if catalog.inputs is not None:
            from production_store import stable_bytes
            acquired=catalog.inputs.packs[resource.source_pack].files[resource.relative_path]
            raw=acquired.bytes_for_capture(lambda relative:stable_bytes(base,relative))
        else:
            raw=c.read(c.local(base,resource.relative_path))
        return {'source_pack':resource.source_pack,'path':resource.relative_path,'sha256':c.digest(raw)},raw
    return read_named


def _capture_resources(manifest: dict, bodies: list, dialect: Any, resource_reader) -> None:
    manifest['resources'] = {}
    if 'prompt-dialect' not in manifest['features']:
        if dialect is not None:
            raise ValueError('a model or prompt family selects writing guide sections; add --feature prompt-dialect')
        return
    selected={name:resource_reader(name) for name in ('prompt-writing-guide','prompt-dialects')}
    for name,resource in selected.items():
        if resource is None:
            manifest['resources'][name]={'status':'unavailable'}
            continue
        origin,raw=resource
        meta={'status':'present',**origin}
        value=c.decode(raw)
        if name == 'prompt-dialects' and dialect is not None:
            from pack_manager import PackError
            from prompt_dialect import validate_dialects
            try:
                validate_dialects(value)
                carried={str(item['id']) for item in value['dialects']}
                if dialect not in carried:
                    raise PackError(f"unknown dialect {dialect!r}; the prompt-dialects resource carries: "+', '.join(sorted(carried)))
            except PackError as exc:
                raise ValueError(str(exc)) from None
        meta['dialect'] = dialect
        raw = _family(name, value, dialect)
        manifest['resources'][name] = meta
        # The delivered bytes carry their own digest; the manifest binds the source file.
        bodies.append(({'kind': 'resource', 'resource': name, **meta,
                        'source_sha256': meta['sha256'], 'sha256': c.digest(raw)}, raw))


def _validate_resources(value: dict) -> None:
    resources = value.get('resources')
    expected = {'prompt-writing-guide', 'prompt-dialects'} if 'prompt-dialect' in value['features'] else set()
    if not isinstance(resources, dict) or set(resources) != expected:
        raise ValueError('reading resource set differs from its feature requirements')
    fields = {'status', 'source_pack', 'path', 'sha256'}
    for item in resources.values():
        if isinstance(item, dict) and item.get('status') == 'unavailable':
            c.exact(item, {'status'}, 'unavailable resource')
        else:
            c.exact(item, fields | {'dialect'}, 'reading resource')
            if item['status'] != 'present':
                raise ValueError('invalid resource status')
            c.sha(item['sha256']); c.text(item['source_pack'], 'resource pack')
            c.local(ROOT, item['path'], exists=False)
            if item['dialect'] is not None:
                c.text(item['dialect'], 'reading model family')
    bound_dialect(value)


def _require_dialect(record: dict, bodies: list, dialect: Any) -> None:
    bound = bound_dialect(record)
    if dialect is not _NO_MODEL and bound != dialect:
        raise ValueError(f'the delivered writing guide is scoped to {bound!r}; read the current model or prompt family')
    if dialect is not _NO_MODEL and dialect is not None:
        available = {meta['resource']: c.decode(raw) for meta, raw in bodies if meta['kind'] == 'resource'}
        ids = {row['id'] for row in available.get('prompt-dialects', {}).get('dialects', [])}
        if dialect not in ids:
            raise ValueError('model dialect is absent from the delivered resource: ' + dialect)


def _model_material(record: dict, service: str | None) -> tuple[dict, bytes]:
    from render_contract_lib import model_card
    identifier = c.text(record.get('id'), 'reading model id')
    offerings = list(record.get('offerings') or [])
    if service is not None:
        offerings = [row for row in offerings if row['service'] == service]
        if len(offerings) != 1:
            raise ValueError('selected model has no unique offering for service: ' + service)
    cards = [model_card(record, row) for row in offerings] if offerings else [model_card(record)]
    raw = (json.dumps(cards, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    return {'id': identifier, 'record_sha256': c.content_id(record), 'service': service,
            'guidance_sha256': c.digest(raw)}, raw


def _validate_model(value: Any) -> None:
    if value is None:
        return
    c.exact(value, {'id', 'record_sha256', 'service', 'guidance_sha256'}, 'reading model')
    c.text(value['id'], 'reading model id')
    c.sha(value['record_sha256']); c.sha(value['guidance_sha256'])
    if value['service'] is not None:
        c.text(value['service'], 'reading model service')


def require_model_reading(record: dict, *, dialect: Any = _NO_MODEL, resource_reader,
                          model_record: dict | None = None, service: str | None = None) -> None:
    """Check delivered guidance against the model and resources acquired by its consumer.

    A family-only delivery serves work whose target remains at that scope.
    A selected model requires its exact model edition and offering guidance.
    Complete all-offering guidance covers any one of those offerings. This
    records source delivery; it never certifies an author's understanding.
    """
    _validate_resources(record)
    _validate_model(record['model'])
    manifest = {'features': record['features']}
    bodies = []
    _capture_resources(manifest, bodies, bound_dialect(record), resource_reader)
    if manifest['resources'] != record['resources']:
        raise ReadingSourcesChanged(source_changes(record, manifest, required_only=True, include_model=False),
                                    'reading resources differ from the acquired sources; read again')
    if model_record is not None:
        dialect = model_record.get('prompt_dialect')
        if record['model'] is None:
            raise ReadingSourcesChanged([{'kind': 'model', 'id': model_record.get('id'),
                                          'change': 'added'}],
                                        'read the complete selected model guidance with --model before using this target')
        selected = record['model']['service']
        if selected is not None and service is not None and selected != service:
            raise ReadingSourcesChanged([{'kind': 'model', 'id': model_record.get('id'),
                                          'before': selected, 'after': service}],
                                        'delivered model guidance belongs to a different service')
        if (record['model']['id'] != model_record.get('id') or
                record['model']['record_sha256'] != c.content_id(model_record)):
            raise ReadingSourcesChanged([{'kind': 'model', 'id': model_record.get('id'),
                                          'before': record['model']['record_sha256'],
                                          'after': c.content_id(model_record)}],
                                        'delivered model guidance differs from the selected model edition')
        if selected is not None and len([row for row in model_record.get('offerings', [])
                                         if row.get('service') == selected]) != 1:
            raise ValueError('delivered model guidance names no unique offering in the acquired model')
        current, _ = _model_material(model_record, selected)
        if record['model']['guidance_sha256'] != current['guidance_sha256']:
            raise ReadingSourcesChanged([{'kind': 'model', 'id': current['id'],
                                          'before': record['model'], 'after': current}],
                                        'delivered model guidance differs from the current guidance')
    _require_dialect(record, bodies, dialect)


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


def _runtime_context(runtime: dict | None):
    """Resolve the exact runtime paths captured with a reading snapshot."""
    if runtime is None:
        return None
    from pack_manager import default_settings
    from pack_runtime_cli import PackRuntimeContext
    roots = tuple(Path(p) for p in runtime['extra_roots'])
    settings = default_settings(state_file=Path(runtime['state_file']), cache_dir=Path(runtime['cache_dir']),
                                managed_root=Path(runtime['managed_root']), extra_roots=roots)
    return PackRuntimeContext(settings, roots)


def _restore_runtime(runtime: dict | None) -> None:
    context = _runtime_context(runtime)
    if context is not None:
        from catalog_retrieval.runtime import configure_pack_runtime
        configure_pack_runtime(context.settings)



def ledger_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = c.read(path)
    if raw and not raw.endswith(b'\n'):
        raise ValueError(f'incomplete reading ledger: {path}')
    rows = []
    fields = MANIFEST_FIELDS | {'at', 'key_sha256', 'cwd', 'delivery'}
    for line in raw.splitlines():
        if not line.strip():
            raise ValueError(f'empty reading ledger row: {path}')
        row = c.decode(line)
        c.exact(row, fields, 'reading ledger row')
        c.sha(row['key_sha256'])
        c.text(row['at'], 'reading timestamp'); c.text(row['cwd'], 'reading cwd')
        _validate_manifest(row)
        _validate_delivery(row)
        rows.append(row)
    return rows


def _body_identity(metadata: dict) -> str:
    """Identify delivered bytes together with their exact source and model scope."""
    return c.content_id(metadata)


def _validate_body_scope(manifest: dict, metadata: list[dict]) -> None:
    """Require exactly the complete bodies named by this operation's manifest."""
    required = {('document', item['path']): item for item in manifest['documents']}
    required.update({('resource', name): value for name, value in manifest['resources'].items()
                     if value['status'] == 'present'})
    if manifest['model'] is not None:
        required[('model', 'model-guidance/' + manifest['model']['id'])] = manifest['model']
    seen = set()
    for item in metadata:
        kind = item.get('kind')
        identity = (kind, item.get('resource') if kind == 'resource' else item.get('path'))
        if identity not in required or identity in seen:
            raise ValueError('reading delivery body differs from its required source scope')
        seen.add(identity)
        expected = required[identity]
        if type(item.get('size')) is not int or item['size'] < 0:
            raise ValueError('reading delivery body has an invalid byte size')
        if kind == 'document':
            c.exact(item, {'kind', 'path', 'sha256', 'size'}, 'delivered document')
            valid = item['sha256'] == expected['sha256']
        elif kind == 'resource':
            c.exact(item, {'kind', 'resource', 'status', 'source_pack', 'path', 'sha256',
                           'source_sha256', 'dialect', 'size'}, 'delivered resource')
            valid = all(item[field] == expected[field]
                        for field in ('status', 'source_pack', 'path', 'dialect'))
            valid = valid and item['source_sha256'] == expected['sha256']
        else:
            c.exact(item, {'kind', 'path', 'sha256', 'size', 'id', 'record_sha256',
                           'service', 'guidance_sha256'}, 'delivered model')
            valid = all(item[field] == expected[field] for field in expected)
            valid = valid and item['sha256'] == expected['guidance_sha256']
        c.sha(item['sha256'])
        if not valid:
            raise ValueError('reading delivery body differs from its manifest')
    if seen != set(required):
        raise ValueError('reading delivery does not cover all required bodies')


def _validate_delivery(row: dict) -> None:
    delivery = row['delivery']
    c.exact(delivery, {'snapshot', 'known_readings', 'bodies'}, 'reading delivery')
    if delivery['snapshot'] is not None:
        c.sha(delivery['snapshot'])
    known = delivery['known_readings']
    if not isinstance(known, list) or known != sorted(set(known)):
        raise ValueError('known readings must be unique key hashes')
    for key in known:
        c.sha(key)
    if not isinstance(delivery['bodies'], list):
        raise ValueError('reading delivery bodies must be an array')
    for item in delivery['bodies']:
        c.exact(item, {'body', 'origin', 'reused_from'}, 'reading body provenance')
        c.exact(item['origin'], {'key_sha256', 'snapshot'}, 'reading body origin')
        c.sha(item['origin']['key_sha256'])
        if item['origin']['snapshot'] is not None:
            c.sha(item['origin']['snapshot'])
        if item['reused_from'] is None:
            if item['origin'] != {'key_sha256': row['key_sha256'], 'snapshot': delivery['snapshot']}:
                raise ValueError('newly delivered body has a different issuance origin')
        elif item['reused_from'] not in known:
            raise ValueError('reused body has no explicit same-context source reading')
    _validate_body_scope(row, [item['body'] for item in delivery['bodies']])


def _known_bodies(keys: list[str], ledger: Path) -> tuple[list[str], dict[str, dict]]:
    """Select only complete issued readings explicitly asserted by this context."""
    if not keys:
        return [], {}
    rows = _issuance_index(ledger_rows(ledger))
    known, bodies = [], {}
    for key in dict.fromkeys(keys):
        digest = c.digest(_hex(key, 32, 'reading key').encode('ascii'))
        row = rows.get(digest)
        if row is None:
            raise ValueError('reading key has no issuance row in the selected ledgers')
        known.append(row['key_sha256'])
        for item in row['delivery']['bodies']:
            bodies[_body_identity(item['body'])] = {
                'body': item['body'], 'origin': item['origin'], 'reused_from': row['key_sha256']}
    return sorted(known), bodies


def _issuance_index(rows: list[dict]) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        key = row['key_sha256']
        if key in indexed and any(row[field] != indexed[key][field] for field in MANIFEST_FIELDS | {'delivery'}):
            raise ValueError('reading key has conflicting issuance records')
        indexed[key] = row
    return indexed


def _check_reused_bodies(snapshot: dict, ledger: Path) -> None:
    """Recheck issuance provenance without treating saved pages as known content."""
    rows = _issuance_index(ledger_rows(ledger)) if snapshot['reused_bodies'] else {}
    for item in snapshot['reused_bodies']:
        key = item['reused_from']
        if key not in snapshot['known_readings'] or key not in rows:
            raise ValueError('same-context body has no complete source issuance')
        available = {_body_identity(previous['body']): previous
                     for previous in rows[key]['delivery']['bodies']}
        previous = available.get(_body_identity(item['body']))
        if previous is None or previous['origin'] != item['origin']:
            raise ValueError('same-context body differs from its complete source issuance')
    selected = [item['body'] for item in snapshot['reused_bodies']] + snapshot['bodies']
    if sorted(map(_body_identity, selected)) != sorted(map(_body_identity, snapshot['required_bodies'])):
        raise ValueError('reading snapshot does not cover its required bodies')
    _validate_body_scope(snapshot['manifest'], snapshot['required_bodies'])


def _validate_manifest(value: dict[str, Any]) -> None:
    c.text(value.get('route'), 'reading route')
    execution_routes.require_scope(value.get('operation'), value.get('execution'))
    _validate_model(value.get('model'))
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


def capture(route: str, features: list[str] | None = None, *, execution: str, root: Path = ROOT,
            operation: str | None = None, dialect: str | None = None, resource_reader=None,
            model: str | None = None, service: str | None = None, model_record: dict | None = None,
            model_file: Path | None = None,
            read_source: Callable[[str], bytes] | None = None) -> tuple[dict, list[tuple[dict, bytes]]]:
    if model_file is not None:
        if model is not None or model_record is not None:
            raise ValueError('select one catalog model or acquired model file')
        model_record = c.load(model_file)
    if model is not None:
        if model_record is None:
            model, model_record = _selected_model(model)
        elif model_record.get('id') != model:
            raise ValueError('acquired model differs from the requested reading target')
    if model_record is not None:
        family = model_record.get('prompt_dialect')
        if dialect is not None and dialect != family:
            raise ValueError('selected model and prompt family differ')
        dialect = family
    if service is not None and model_record is None:
        raise ValueError('a service selection requires a selected model')
    read_once = _read_once(root, read_source)
    resolved = execution_routes.resolve(route, features, operation=operation, execution=execution,
                                        root=root, read_source=read_once)
    bodies = []
    for entry in resolved['reads']:
        raw = read_once(entry['path'])
        raw.decode('utf-8')
        if c.digest(raw) != entry['sha256']:
            raise ValueError('document changed while reading: ' + entry['path'])
        bodies.append(({'kind': 'document', **entry}, raw))
    manifest = {'route': resolved['route'], 'operation': resolved['operation'], 'execution': resolved['execution'],
                'features': resolved['features'],
                'documents': resolved['reads'], 'model': None}
    if resource_reader is None and 'prompt-dialect' in resolved['features']:
        resource_reader = _live_resource_reader()
    _capture_resources(manifest, bodies, dialect, resource_reader)
    if model_record is not None:
        metadata, raw = _model_material(model_record, service)
        manifest['model'] = metadata
        bodies.append(({'kind': 'model', 'path': 'model-guidance/' + metadata['id'],
                        'sha256': c.digest(raw), **metadata}, raw))
    return manifest, bodies


def _issue(manifest: dict, ledger: Path, *, bodies: list[dict], reused: list[dict] | None = None,
           known_readings: list[str] | None = None, snapshot: str | None = None,
           key: str | None = None, at: str | None = None, cwd: str | None = None) -> dict:
    """Serialize only the ledger read and append. Fixed values support fixtures."""
    key = _hex(key or secrets.token_hex(16), 32, 'reading key')
    row = {**manifest, 'at': at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'cwd': cwd if cwd is not None else str(Path.cwd()), 'key_sha256': c.digest(key.encode('ascii'))}
    row['delivery'] = {'snapshot': snapshot, 'known_readings': known_readings or [],
                       'bodies': [*({'body': metadata,
                                    'origin': {'key_sha256': row['key_sha256'], 'snapshot': snapshot},
                                    'reused_from': None} for metadata in bodies), *(reused or [])]}
    _validate_delivery(row)
    with c.lock(ledger.parent):
        existing = ledger_rows(ledger)
        for old in existing:
            if old['key_sha256'] == row['key_sha256'] and any(old[k] != row[k] for k in MANIFEST_FIELDS | {'delivery'}):
                raise ValueError('reading key already belongs to different documents or route')
        if row in existing:
            return {'reading_key': key, 'row': row}
        c.atomic(ledger, b''.join(c.encoded(x) for x in existing) + c.encoded(row), replace=ledger.exists())
        return {'reading_key': key, 'row': row}


def _begin_output(stream: TextIO, body: list[dict], metadata: dict) -> None:
    """Flush actual source text before publishing its successful delivery."""
    stream.write('{"metadata": ' + json.dumps(metadata, ensure_ascii=False))
    stream.write(', "body": ' + json.dumps(body, ensure_ascii=False))
    stream.flush()


def _finish_output(stream: TextIO, result: dict) -> None:
    visible = {key: value for key, value in result.items() if key not in {'body', 'metadata', 'issued', 'delivered'}}
    stream.write(', ' + json.dumps(visible, ensure_ascii=False)[1:] + '\n')
    stream.flush()


def _failed_output(stream: TextIO, exc: Exception) -> None:
    """Finish an already begun structured response without a successful receipt."""
    value = {'ok': False, 'error': str(exc), 'reading': None,
             **(exc.as_dict() if isinstance(exc, ReadingSourcesChanged) else {})}
    try:
        _finish_output(stream, value)
    except OSError:
        return
    exc.reading_result_written = True


def issue(route: str, features: list[str] | None = None, *, execution: str, root: Path = ROOT,
          studio: Path | None = None, ledger: Path | None = None, stream: TextIO | None = None,
          key: str | None = None, at: str | None = None, cwd: str | None = None,
          dialect: str | None = None, operation: str | None = None,
          model: str | None = None, service: str | None = None,
          model_file: Path | None = None, model_record: dict | None = None) -> dict:
    """Output all bytes before issuing evidence. Fixed key/time are fixture inputs."""
    stream = sys.stdout if stream is None else stream
    target = ledger if ledger is not None else ledger_candidates(studio=studio)[0]
    ledger_rows(target)
    manifest, bodies = capture(route, features, root=root, dialect=dialect, operation=operation, execution=execution, model=model,
                               service=service, model_file=model_file, model_record=model_record)
    _begin_output(stream, [{'metadata': meta, 'text': raw.decode('utf-8')} for meta, raw in bodies], manifest)
    try:
        current, _ = capture(route, features, root=root, dialect=dialect, operation=operation, execution=execution,
                             model=model, service=service, model_file=model_file, model_record=model_record)
        if manifest != current:
            raise ReadingSourcesChanged(source_changes(manifest, current))
        issued = _issue(manifest, target, bodies=[dict(meta, size=len(raw)) for meta, raw in bodies],
                        key=key, at=at, cwd=cwd)
    except (ValueError, OSError) as exc:
        _failed_output(stream, exc)
        raise
    _finish_output(stream, {'ok': True, 'reading': {'key': issued['reading_key'], 'record': None},
                            'actions': {'continue': None}})
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
    if any(any(row[field] != record[field] for field in MANIFEST_FIELDS) for row in matching):
        raise ValueError('reading issuance differs from the supplied route, features or document versions')
    if any(row['delivery'] != matching[0]['delivery'] for row in matching[1:]):
        raise ValueError('reading key has conflicting delivery provenance')
    return matching[0]


def validate_record_content(record: Any) -> None:
    """Validate a source-delivery receipt without claiming understanding or authority."""
    c.exact(record, MANIFEST_FIELDS | {'reading_key'}, 'route reading')
    _validate_manifest(record)
    _hex(record['reading_key'], 32, 'reading key')


def require_route_reading(record: Any, *, root: Path = ROOT, ledgers: list[Path] | None = None,
                          studio: Path | None = None, package_root: Path | None = None,
                          routes: set[str] | None = None, features: list[str] | None = None,
                          operation: str | None = None, execution: str | None = None,
                          dialect: Any = _NO_MODEL, resource_reader=None,
                          model_record: dict | None = None, service: str | None = None,
                          read_source: Callable[[str], bytes] | None = None) -> dict:
    """Verify actual full delivery and coverage of the current operation.

    A delivered superset can cover a narrower operation only when all its
    required source editions match. Consumers supply the task's actual execution
    kind; integrity-only copies retain the delivered scope. A prior receipt remains a delivery fact,
    not evidence that a new agent has read or understood those documents.
    """
    validate_record_content(record)
    if routes is not None and record['route'] not in routes:
        raise ValueError('reading route must be one of: ' + ', '.join(sorted(routes)))
    row = _find_row(record, ledgers if ledgers is not None else ledger_candidates(studio=studio, package_root=package_root))
    selected_features = features if features is not None else record['features']
    read_source = _read_once(root, read_source)
    expected = execution_routes.resolve(record['route'], selected_features,
                                        operation=operation or record['operation'],
                                        execution=execution if execution is not None else record['execution'],
                                        root=root, read_source=read_source)
    current, bodies = capture(record['route'], selected_features, root=root,
                              operation=expected['operation'], execution=expected['execution'],
                              dialect=bound_dialect(record) if 'prompt-dialect' in expected['features'] else None,
                              resource_reader=resource_reader, read_source=read_source)
    changes = source_changes(record, current, required_only=True, include_model=False)
    if changes:
        missing_features = any(change['kind'] == 'feature' for change in changes)
        message = ('reading features do not cover the execution features' if missing_features else
                   'reading documents do not cover the current operation and execution; read their complete contract')
        raise ReadingSourcesChanged(changes, message)
    _require_dialect(record, bodies, dialect)
    if model_record is not None:
        require_model_reading(record, model_record=model_record, service=service,
                              resource_reader=resource_reader or _live_resource_reader())
    return row


def resolve_issuance(key: str, *, studio: Path | None = None,
                     ledgers: list[Path] | None = None) -> dict:
    """Resolve a supplied key to one consistent locally issued document edition."""
    digest = c.digest(_hex(key, 32, 'reading key').encode('ascii'))
    matches = [row for path in dict.fromkeys(ledgers if ledgers is not None else ledger_candidates(studio=studio))
               for row in ledger_rows(path) if row['key_sha256'] == digest]
    if not matches:
        raise ValueError('reading key has no issuance row in the selected ledgers')
    fields = MANIFEST_FIELDS | {'delivery'}
    if any(any(row[field] != matches[0][field] for field in fields) for row in matches[1:]):
        raise ValueError('reading key has conflicting issuance records')
    return {'reading_key': key, 'row': matches[0]}


def check_snapshot_issuance(snapshot: str, issued: dict, *, studio: Path | None = None) -> None:
    """Check a supplied delivery selector without making retention a key condition."""
    _hex(snapshot, 64, 'reading snapshot')
    paths = [path.parent / 'reading-snapshots' / snapshot / 'snapshot.json'
             for path in ledger_candidates(studio=studio)]
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


def build_record(issued: dict, *, root: Path = ROOT, studio: Path | None = None,
                 ledgers: list[Path] | None = None, dialect: Any = _NO_MODEL,
                 operation: str | None = None, execution: str | None = None,
                 features: list[str] | None = None) -> dict:
    """Resolve the delivery record from its issuance; the author copies no source metadata."""
    c.exact(issued, {'reading_key', 'row'}, 'issued reading')
    result = draft_record(issued)
    require_route_reading(result, root=root, studio=studio, ledgers=ledgers, dialect=dialect,
                          operation=operation, execution=execution, features=features)
    return result


def copy_issuance(record: dict, destination: Path, *, root: Path = ROOT, studio: Path | None = None,
                  ledgers: list[Path] | None = None, package_root: Path | None = None) -> dict:
    """Copy issuance integrity; the consumer checks applicability to its own scope."""
    validate_record_content(record)
    row = _find_row(record, ledgers if ledgers is not None else ledger_candidates(studio=studio, package_root=package_root))
    with c.lock(destination.parent):
        rows = ledger_rows(destination)
        matching = [old for old in rows if old['key_sha256'] == row['key_sha256']]
        fields = MANIFEST_FIELDS | {'delivery'}
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


def _publish_page(path: Path, value: dict) -> None:
    """Commit a content-addressed page once, accepting an identical publisher."""
    raw = c.encoded(value)
    try:
        c.atomic(path, raw)
    except FileExistsError:
        if c.read(path) != raw:
            raise ValueError('reading page collision')


def read_page(*, route: str | None = None, features: list[str] | None = None,
              cursor: str | None = None, replay: bool = False, page_bytes: int = DEFAULT_PAGE_BYTES,
              root: Path = ROOT, studio: Path | None = None, ledger: Path | None = None,
              stream: TextIO | None = None, runtime: dict | None = None,
              dialect: str | None = None, operation: str | None = None, execution: str | None = None,
              model: str | None = None, service: str | None = None,
              model_file: Path | None = None, known_reading_keys: list[str] | None = None,
              publish_record: bool = False) -> dict:
    """Deliver a complete current scope from explicit known bodies and new pages."""
    if isinstance(page_bytes, bool) or not isinstance(page_bytes, int) or page_bytes < 4:
        raise ValueError('page-bytes must be an integer of at least four')
    stream = sys.stdout if stream is None else stream
    ledger = ledger if ledger is not None else ledger_candidates(studio=studio)[0]
    authoring_studio = studio or _studio(ledger.parent)
    if cursor is None:
        if route is None:
            raise ValueError('a route is required to start reading')
        # The reading ends by appending to this ledger. Report a ledger that
        # cannot be read before any body is delivered.
        ledger_rows(ledger)
        manifest, acquired = capture(route, features, root=root, dialect=dialect, operation=operation,
                                    execution=execution, model=model, service=service, model_file=model_file)
        context_keys = list(dict.fromkeys(known_reading_keys or []))
        known, available = _known_bodies(context_keys, ledger)
        required = [dict(meta, size=len(raw)) for meta, raw in acquired]
        reused = [available[_body_identity(meta)] for meta in required if _body_identity(meta) in available]
        bodies = [meta for meta in required if _body_identity(meta) not in available]
        import production_authoring_state
        task_id = production_authoring_state.active_task_id(authoring_studio)
        snapshot = {'manifest': manifest, 'root': str(root.absolute()), 'runtime': runtime,
                    'task_id': task_id, 'model_file': str(model_file.absolute()) if model_file is not None else None,
                    'nonce': secrets.token_hex(16), 'bodies': bodies, 'required_bodies': required,
                    'reused_bodies': reused, 'known_readings': known, 'context_keys': context_keys}
        _validate_body_scope(manifest, required)
        sid = c.content_id(snapshot)
        production_authoring_state.remember_reading(authoring_studio, ledger, sid, snapshot, page_bytes)
        folder = c.local(ledger.parent, 'reading-snapshots/' + sid, exists=False)
        folder.mkdir(parents=True)
        c.atomic(folder / 'snapshot.json', c.encoded(snapshot))
        pending_hashes = {meta['sha256'] for meta in bodies}
        for meta, raw in acquired:
            if meta['sha256'] in pending_hashes:
                c.object_store(folder, raw)
        start = 0
    else:
        if (route is not None or features or dialect is not None or operation is not None or execution is not None
                or model is not None or service is not None or model_file is not None or known_reading_keys):
            raise ValueError('a cursor fixes its route, operation, execution, features, model scope and known readings')
        folder, snapshot, page = _cursor(ledger, cursor)
        sid = c.content_id(snapshot)
        if str(root.absolute()) != snapshot['root']:
            raise ValueError('reading cursor belongs to a different skill root')
        _restore_runtime(snapshot['runtime'])
        _check_reused_bodies(snapshot, ledger)
        start = page['start'] if replay else page['end']
    total = sum(item['size'] for item in snapshot['bodies'])
    if cursor is not None and start == total and not replay:
        raise ValueError('reading is complete; replay the final page to receive a new key')
    index, offset = _position(snapshot, start)
    budget, end = page_bytes, start
    ranges, body = [], []
    pending = {'snapshot': sid, 'start': start, 'end': start, 'ranges': []}
    pending_id = c.content_id(pending)
    _publish_page(folder / 'pages' / (pending_id + '.json'), pending)
    while index < len(snapshot['bodies']) and budget:
        meta = snapshot['bodies'][index]
        raw = c.object_read(folder, meta['sha256'])
        if len(raw) != meta['size']:
            raise ValueError('reading source size differs from its snapshot')
        stop = min(len(raw), offset + budget)
        while stop > offset and stop < len(raw) and raw[stop] & 0xC0 == 0x80:
            stop -= 1
        if stop == offset and offset < len(raw):
            break
        segment = raw[offset:stop]
        header = {**meta, 'snapshot': sid, 'start': offset, 'end': stop, 'total': len(raw)}
        ranges.append(header)
        body.append({'metadata': header, 'text': segment.decode('utf-8')})
        end += len(segment)
        budget -= len(segment)
        if stop == len(raw):
            index += 1
            offset = 0
        else:
            offset = stop
    page = {'snapshot': sid, 'start': start, 'end': end, 'ranges': ranges}
    page_id = c.content_id(page)
    reused_bytes = sum(item['body']['size'] for item in snapshot['reused_bodies'])
    result = {'ok': True, 'snapshot': sid, 'cursor': sid + ':' + page_id,
              'body': body, 'delivered': ranges, 'remaining_bytes': total - end,
              'metadata': {key: snapshot['manifest'][key] for key in ('route', 'operation', 'execution', 'features', 'model')},
              'progress': {'page_start': start, 'page_end': end, 'delivered_bytes': end,
                           'total_bytes': total, 'remaining_bytes': total - end,
                           'required_bytes': total + reused_bytes, 'reused_bytes': reused_bytes,
                           'required_bodies': len(snapshot['required_bodies']),
                           'reused_bodies': len(snapshot['reused_bodies'])},
              'reading': None, 'context_reuse': None,
              'same_context_required': bool(snapshot['context_keys'])}
    # Only a successfully flushed body becomes a committed delivery page.
    _begin_output(stream, body, result['metadata'])
    try:
        _publish_page(folder / 'pages' / (page_id + '.json'), page)
        result['actions'] = _reading_actions(result, ledger=ledger, studio=studio, page_bytes=page_bytes)
        if end == total:
            covered = []
            for path in (folder / 'pages').glob('*.json'):
                observed = c.load(path)
                if c.content_id(observed) != path.stem or observed['snapshot'] != sid:
                    raise ValueError('reading page address mismatch')
                low, high = observed['start'], observed['end']
                if type(low) is not int or type(high) is not int or not 0 <= low <= high <= total:
                    raise ValueError('reading page has an invalid delivered range')
                covered.append((low, high))
            reach = 0
            for low, high in sorted(covered):
                if low > reach:
                    raise ValueError('undelivered range in reading snapshot')
                reach = max(reach, high)
            if reach != total:
                raise ValueError('reading snapshot is incomplete')
            current, acquired = capture(snapshot['manifest']['route'], snapshot['manifest']['features'], root=root,
                                 dialect=bound_dialect(snapshot['manifest']), operation=snapshot['manifest']['operation'],
                                 execution=snapshot['manifest']['execution'],
                                 model=(snapshot['manifest']['model'] or {}).get('id') if snapshot['model_file'] is None else None,
                                 model_file=Path(snapshot['model_file']) if snapshot['model_file'] is not None else None,
                                 service=(snapshot['manifest']['model'] or {}).get('service'))
            current_bodies = [dict(meta, size=len(raw)) for meta, raw in acquired]
            if current != snapshot['manifest'] or current_bodies != snapshot['required_bodies']:
                raise ReadingSourcesChanged(source_changes(snapshot['manifest'], current),
                    'sources changed during reading; start a new read',
                    actions={'restart': result['actions']['restart']})
            _check_reused_bodies(snapshot, ledger)
            result['issued'] = _issue(current, ledger, bodies=snapshot['bodies'], reused=snapshot['reused_bodies'],
                                      known_readings=snapshot['known_readings'], snapshot=sid)
            issued = result['issued']
            result['reading'] = {'key': issued['reading_key'], 'record': None}
            if publish_record:
                path = write_draft(issued, ledger, studio=studio, snapshot=sid)
                location = (path.relative_to(studio).as_posix()
                            if studio is not None and path.is_relative_to(studio) else str(path))
                result['reading']['record'] = location
                result['reading']['record_absolute'] = str(path.absolute())
            result['context_reuse'] = _context_reuse(result, snapshot=snapshot, ledger=ledger,
                                                       studio=studio, page_bytes=page_bytes)
    except (ValueError, OSError) as exc:
        _failed_output(stream, exc)
        raise
    _finish_output(stream, result)
    return result


def draft_record(issued: dict) -> dict:
    """Return the complete machine-owned delivery record from its issued scope."""
    row = issued['row']
    return {**{field: row[field] for field in sorted(MANIFEST_FIELDS)}, 'reading_key': issued['reading_key']}


def write_draft(issued: dict, ledger: Path, *, studio: Path | None = None,
                snapshot: str | None = None) -> Path:
    """Publish the derived delivery record beside its issuance ledger."""
    row = issued['row']
    path = ledger.parent / 'readings' / (row['route'] + '-' + row['key_sha256'][:16] + '.json')
    raw = (json.dumps(draft_record(issued), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    import production_authoring_state
    task_id = (c.load(_snapshot_dir(ledger, snapshot) / 'snapshot.json').get('task_id')
               if snapshot is not None else None)
    production_authoring_state.remember_reading_record(studio or _studio(ledger.parent), ledger, path,
                                                       snapshot=snapshot, task_id=task_id)
    try:
        c.atomic(path, raw)
    except FileExistsError:
        if c.read(path) != raw:
            raise ValueError('saved delivery record differs from its issuance')
    return path


def _selected_model(model: str) -> tuple[str, dict]:
    """Resolve the selected model or return an actionable catalog/family choice."""
    from catalog_retrieval.runtime import load_pack_catalog
    from prepare_generation_references import resolve_model_record
    try:
        return resolve_model_record(model)
    except ValueError as exc:
        catalog = load_pack_catalog()
        models = sorted({str(entry.record['id']) for entry in catalog.entries
                         if entry.kind == 'model' and entry.record.get('id')})
        resource = catalog.resources.get('prompt-dialects')
        families = sorted(row['id'] for row in c.load(Path(resource.path))['dialects']) if resource else []
        raise ValueError(f"{exc}; model ids: {', '.join(models) or 'none'}; a prompt-only read can name "
                         f"the prompt family instead with --dialect ID: {', '.join(families) or 'none'}") from None


def add_read_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('route', nargs='?', help='Route to begin; a cursor supplies the saved route for continuation')
    parser.add_argument('--feature', action='append', default=[], help='Feature to include when beginning a route')
    parser.add_argument('--root', type=Path, help='Studio root for the reading ledger')
    parser.add_argument('--operation', choices=execution_routes.OPERATIONS,
                        help='Current operation; defaults to the route owner')
    parser.add_argument('--execution', choices=execution_routes.EXECUTIONS,
                        help='Execution kind selected by the task; required for a new reading')
    parser.add_argument('--service', help='Selected offering service; with --model, omit to compare all offerings')
    family = parser.add_mutually_exclusive_group()
    family.add_argument('--model', help="Deliver the selected model guidance and its complete applicable writing guide")
    family.add_argument('--model-file', type=Path, help='Acquired model definition, relative to the Studio or absolute')
    family.add_argument('--dialect', metavar='ID',
                        help='Read only the writing guide sections for this prompt family, without a model record')
    parser.add_argument('--page-bytes', type=int, default=DEFAULT_PAGE_BYTES,
                        help=f'Maximum source bytes delivered per page (default: {DEFAULT_PAGE_BYTES})')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--continue', dest='cursor',
                       help='Continue the saved route, features and prompt family using the emitted action')
    group.add_argument('--replay', dest='replay', metavar='CURSOR',
                       help='Read the selected snapshot page again using the emitted action')
    group.add_argument('--restart', metavar='CURSOR',
                       help='Read the current sources using the saved route and runtime selections')
    parser.add_argument('--known-reading', action='append', default=[], metavar='KEY',
                        help='Complete reading still known in this context; repeat to combine readings and deliver only missing current bodies')
    parser.add_argument('--reading-ledger', type=Path,
                        help='Reading ledger for the selected Studio or explicit continuation context')
    _add_runtime_arguments(parser)


def _reading_actions(result: dict, *, ledger: Path, studio: Path | None, page_bytes: int) -> dict:
    """Build executable next actions from the delivered snapshot's own context."""
    _, snapshot, _ = _cursor(ledger, result['cursor'])
    context = _runtime_context(snapshot['runtime'])
    base = python_argv(ROOT / 'scripts' / 'execution_routes.py', 'read',
                       '--reading-ledger', str(ledger.absolute()), '--page-bytes', str(page_bytes))
    if studio is not None:
        base.extend(('--root', str(studio.absolute())))
    if context is not None:
        base.extend(context.command_arguments())

    def action(option: str, reason: str) -> dict:
        argv = [*base, option, result['cursor']]
        return {'argv': argv, 'command': shown(argv), 'reason': reason}

    actions = {'continue': None}
    if result['remaining_bytes']:
        actions['continue'] = action('--continue', f"Read the remaining {result['remaining_bytes']} source bytes.")
    actions['replay'] = action('--replay', 'Read this delivered page again; reduce --page-bytes if the host truncated it.')
    actions['restart'] = action('--restart', 'Begin a complete reading of the current sources with these selections.')
    return actions


def _context_reuse(result: dict, *, snapshot: dict, ledger: Path,
                   studio: Path | None, page_bytes: int) -> dict:
    """Offer complete read invocations without inferring a later context's knowledge."""
    keys = list(dict.fromkeys([*snapshot['context_keys'], result['issued']['reading_key']]))
    arguments = [word for key in keys for word in ('--known-reading', key)]
    manifest = snapshot['manifest']
    base = python_argv(ROOT / 'scripts/execution_routes.py', 'read', manifest['route'],
                       '--reading-ledger', str(ledger.absolute()), '--page-bytes', str(page_bytes),
                       '--execution', manifest['execution'])
    if studio is not None:
        base.extend(('--root', str(studio.absolute())))
    for feature in manifest['features']:
        base.extend(('--feature', feature))
    if snapshot['model_file'] is not None:
        base.extend(('--model-file', snapshot['model_file']))
    elif manifest['model'] is not None:
        base.extend(('--model', manifest['model']['id']))
    elif bound_dialect(manifest) is not None:
        base.extend(('--dialect', bound_dialect(manifest)))
    if manifest['model'] is not None and manifest['model']['service'] is not None:
        base.extend(('--service', manifest['model']['service']))
    runtime = _runtime_context(snapshot['runtime'])
    if runtime is not None:
        base.extend(runtime.command_arguments())
    operations = {}
    for operation in execution_routes.OPERATIONS:
        argv = [*base, '--operation', operation, *arguments]
        operations[operation] = {'argv': argv, 'command': shown(argv),
            'reason': 'Read the current ' + operation + ' contract, reusing only complete material still known in this context.'}
    return {'same_context_required': True, 'known_reading_keys': keys,
            'arguments': arguments, 'operations': operations,
            'fresh_context': result['actions']['restart']}


def read_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    """Deliver one structured page and publish its record on complete current coverage."""
    continuation = args.cursor is not None or args.replay is not None or args.restart is not None
    if continuation and (args.route is not None or args.feature or args.model is not None or args.model_file is not None or args.dialect is not None
                         or args.operation is not None or args.execution is not None or args.service is not None or args.known_reading):
        raise ValueError('a cursor fixes its route, operation, execution, features, model scope and known readings; execute its complete reading action')
    if not continuation and args.execution is None:
        raise ValueError('a new reading requires --execution authored, external or dispatcher from the task')
    runtime = _configure_runtime(args, parser)
    ledger = ledger_candidates(studio=args.root, ledger=args.reading_ledger)[0]
    studio = args.root.absolute() if args.root is not None else (_studio(Path.cwd()) or _studio(ledger.parent))
    dialect = args.dialect
    if not continuation and args.route is None:
        raise ValueError('read requires a route or a continuation cursor')
    page_bytes = DEFAULT_PAGE_BYTES if args.page_bytes is None else args.page_bytes
    cursor = args.cursor if args.cursor is not None else args.replay
    model_file = args.model_file
    if model_file is not None and not model_file.is_absolute():
        model_file = (studio or Path.cwd()) / model_file
    if args.restart is not None:
        _, snapshot, _ = _cursor(ledger, args.restart)
        if snapshot['root'] != str(ROOT.absolute()):
            raise ValueError('reading cursor belongs to a different skill root')
        _restore_runtime(snapshot['runtime'])
        manifest = snapshot['manifest']
        result = read_page(route=manifest['route'], features=manifest['features'],
            operation=manifest['operation'], execution=manifest['execution'],
            dialect=bound_dialect(manifest), model_file=Path(snapshot['model_file']) if snapshot['model_file'] else None,
            model=(manifest['model'] or {}).get('id') if snapshot['model_file'] is None else None,
            service=(manifest['model'] or {}).get('service'), page_bytes=page_bytes,
            ledger=ledger, studio=studio, runtime=snapshot['runtime'], publish_record=True)
    else:
        result = read_page(route=args.route, features=args.feature, cursor=cursor,
                           replay=args.replay is not None, page_bytes=page_bytes,
                           ledger=ledger, studio=studio, runtime=runtime, dialect=dialect,
                           operation=args.operation, execution=args.execution, model=args.model, service=args.service,
                           model_file=model_file, known_reading_keys=args.known_reading, publish_record=True)
    return result


def main() -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    try:
        row = require_route_reading(c.load(args.record), studio=args.root, package_root=args.record.parent)
        print(json.dumps({'ok': True, 'route': row['route'], 'operation': row['operation'],
                          'execution': row['execution'], 'evidence': 'complete source delivery'}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc),
                         **(exc.as_dict() if isinstance(exc, ReadingSourcesChanged) else {})})); return 1


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
