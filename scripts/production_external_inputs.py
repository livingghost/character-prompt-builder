"""Materialize authored external inputs through the shared image-input owner.

The authored reference owns its use and actual uploaded value. This module
derives the request's media positions and file bindings without performing an
upload, selecting a provider, or inventing evidence of an external effect.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
from typing import Any

import execution_contract as c
import image_input
import request_contract as rc

FIELDS = frozenset({'image_input', 'request', 'media_slots', 'source_files', 'source_uploads', 'reference_delivery'})
REQUEST_FIELDS = ('model_field', 'prompt_field', 'negative_field', 'count_field', 'operation_field')


def template() -> dict:
    """Leave the model, native interface and real evidence explicitly unselected."""
    return {'image_input': None, 'request': None, 'media_slots': [],
            'source_files': {}, 'source_uploads': [], 'reference_delivery': None}


def unresolved(selection: Any) -> list[dict]:
    if selection is None:
        return []
    if not isinstance(selection, dict):
        raise ValueError('external choices must be an object')
    if isinstance(selection.get('image_input'), str):
        c.exact(selection, {'image_input'}, 'external input file selection')
        return []
    c.exact(selection, set(FIELDS), 'external input choices')
    result = []

    def required(value, field):
        if value is None:
            result.append({'field': 'external.' + field, 'code': 'selection-required'})

    plan = selection['image_input']
    required(plan, 'image_input')
    required(selection['request'], 'request')
    if plan is not None and not isinstance(plan, dict):
        raise ValueError('external image_input must contain the selected plan')
    if isinstance(plan, dict):
        required(plan.get('model'), 'image_input.model')
        required(plan.get('external_request'), 'image_input.external_request')
        for index, row in enumerate(plan.get('references', []) if selection['reference_delivery'] is None else []):
            transport = row.get('transport')
            required(transport, f'image_input.references.{index}.transport')
            if isinstance(transport, dict):
                for key in ('value', 'evidence'):
                    required(transport.get(key), f'image_input.references.{index}.transport.{key}')
    return result


def draft(plan: dict, request: Any, *, prepared: dict | None = None,
          package_root: Path | None = None, root: Path | None = None) -> dict:
    """Extract editable content and retain the request's declared media slots.

    A transport stays beside the reference it sends. The repeated reference ID,
    request filename and hashes are written only into the built contract.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get('external_request'), dict):
        raise ValueError('select an image input plan with an external request')
    if not isinstance(request, (dict, list)):
        raise ValueError('external request controls must be a JSON object or array')
    selected = {key: copy.deepcopy(value) for key, value in plan.items() if key not in image_input.DERIVED}
    selected['artifact_type'] = 'image-input-plan'
    reference_delivery = None
    carriers = None
    if selected.get('prepared_references') is not None:
        prepared = prepared if prepared is not None else plan.get('prepared_reference_set')
        if prepared is None or package_root is None:
            raise ValueError('draft the prepared reference content with its package root')
        import production_reference_inputs
        from prepare_generation_references import resolve_prepared_reference_paths
        reference_delivery = production_reference_inputs.draft_external(
            plan, prepared, package_root=package_root, root=root)
        resolved = resolve_prepared_reference_paths(prepared, package_root=package_root)
        carriers = [resolved['single_board'] if resolved['transport_mode'] == 'single-board' else row['transport']
                    for row in resolved['selected_references']]
        selected.pop('prepared_references')
    external = selected['external_request']
    fields = external.pop('reference_fields')
    references = selected['references']
    if not isinstance(fields, list) or [row['reference'] for row in fields] != [row['id'] for row in references]:
        raise ValueError('external reference fields must cover every selected reference in order')
    slots, source_files, source_uploads = [], {}, []

    def pin(path, digest):
        if digest is not None:
            c.sha(digest)
            if path in source_files and source_files[path] != digest:
                raise ValueError('one selected external source has different recorded hashes')
            source_files[path] = digest

    def unpin(row, field='path'):
        pin(row[field], row.pop('sha256', None))

    unpin(selected['model']['evidence'])
    if external.get('model_identity') is not None:
        unpin(external['model_identity']['evidence'])
    for field in ('schema', 'vocabulary_record'):
        if external.get(field) is not None:
            unpin(external[field])
    native = copy.deepcopy(request)
    for index, (row, binding) in enumerate(zip(references, fields, strict=True)):
        row['transport'] = {key: copy.deepcopy(binding[key]) for key in ('field', 'value', 'evidence')}
        original_digest = row.get('sha256')
        evidence_digest = binding['evidence'].get('sha256')
        if root is not None:
            if original_digest is None:
                original_digest = c.sha256_file(c.local(root, row['file']))
            if evidence_digest is None:
                evidence_digest = c.sha256_file(c.local(root, binding['evidence']['path']))
        if carriers is not None:
            original_digest = carriers[index]['sha256']
        if original_digest is not None and evidence_digest is not None:
            source_uploads.append({'carrier_sha256': original_digest, 'evidence_sha256': evidence_digest,
                'locator': binding['evidence']['locator'], 'value': binding['value']})
        unpin(row['transport']['evidence'])
        uploaded = row['file']
        if carriers is not None:
            uploaded = Path(carriers[index]['resolved_path'])
            if root is not None:
                try:
                    uploaded = uploaded.relative_to(root.resolve()).as_posix()
                except ValueError:
                    uploaded = str(uploaded)
            else:
                uploaded = str(uploaded)
            pin(uploaded, carriers[index]['sha256'])
        row['transport']['uploaded_file'] = uploaded
        unpin(row, 'file')
        path = rc._path(binding['field'])
        if path not in slots:
            slots.append(copy.deepcopy(path))
        if rc.present(native, path):
            rc.put(native, path, None)
    for field in REQUEST_FIELDS:
        path = external.get(field)
        # Negative text has no separate owner in this external authoring input.
        if field != 'negative_field' and path is not None and rc.present(native, path):
            rc.put(native, path, None)
    for key in ('file', 'sha256', 'request', 'schema_validation', 'prompt_check'):
        external.pop(key, None)
    if reference_delivery is not None:
        selected['references'] = [{'id': row['id'], 'transport': row['transport']} for row in references]
    return {'image_input': selected, 'request': native, 'media_slots': slots,
            'source_files': source_files, 'source_uploads': source_uploads,
            'reference_delivery': reference_delivery}


def _at(value: Any, path: list) -> Any:
    return rc.get(value, path) if path else value


def _protected(external: dict) -> list[list]:
    result = [external[key] for key in REQUEST_FIELDS if external.get(key) is not None]
    control = (external.get('prompt_syntax') or {}).get('control')
    if control is not None:
        result.append(control['field'])
    return result


def _array_position(request: Any, path: list, protected: list[list]) -> tuple | None:
    """Find a media item, never an enclosing operation with independent fields."""
    for index in reversed(range(len(path))):
        if type(path[index]) is not int:
            continue
        prefix = path[:index]
        try:
            container = _at(request, prefix)
        except ValueError:
            continue
        if not isinstance(container, list):
            continue
        member = path[:index + 1]
        if any(rc.overlaps(member, field) for field in protected):
            continue
        return tuple(prefix), index
    return None


def _assign_transport_fields(request: Any, rows: list[dict], slots: list[list], external: dict) -> None:
    """A new reference can reuse one unambiguous already declared array shape."""
    protected = _protected(external)
    patterns = {}
    for path in slots + [row['field'] for row in rows if row.get('field') is not None]:
        rc._path(path)
        position = _array_position(request, path, protected)
        if position is not None:
            prefix, index = position
            patterns[(prefix, tuple(path[index + 1:]))] = path
    for row in rows:
        if row.get('field') is None:
            if len(patterns) != 1:
                raise ValueError('select a media field for this reference; the request has no unique declared media array')
            row['field'] = copy.deepcopy(next(iter(patterns.values())))
        rc._path(row['field'])
        if any(rc.overlaps(row['field'], path) for path in protected):
            raise ValueError('external media field overlaps an independently owned request field')


def _remove_leaf(value: Any, path: list) -> None:
    if not rc.present(value, path):
        return
    parent = _at(value, path[:-1])
    if isinstance(parent, list):
        raise ValueError('cannot remove a media array slot containing an independently bound request field')
    del parent[path[-1]]


def _move_field(path: list, prefix: list, positions: dict[int, int]) -> list:
    if path[:len(prefix)] == prefix and len(path) > len(prefix) and type(path[len(prefix)]) is int:
        old = path[len(prefix)]
        if old not in positions:
            raise ValueError('a removed media item contains another declared request field')
        return prefix + [positions[old]] + path[len(prefix) + 1:]
    return path


def _media(request: Any, rows: list[dict], slots: list[list], external: dict) -> tuple[Any, list[dict]]:
    """Rebuild declared media items, retaining every unrelated native value."""
    if not isinstance(slots, list):
        raise ValueError('external media_slots must be an array of field paths')
    for path in slots:
        rc._path(path)
    if len({tuple(path) for path in slots}) != len(slots):
        raise ValueError('external media_slots must contain unique declared fields')
    protected = _protected(external)
    if any(rc.overlaps(slot, field) for slot in slots for field in protected):
        raise ValueError('a saved media slot overlaps an independently owned request field')
    # Refuse undeclared values, including when the new selection is empty.
    # Deletion must not silently remove unknown inputs that happen to share a
    # similar container shape with the source's declared media.
    patterns = {tuple(None if type(part) is int else part for part in path) for path in slots}
    known = {tuple(path) for path in slots}
    for pattern in patterns:
        if any(path not in known for path in image_input._matching_media_paths(request, pattern)):
            raise ValueError('external media array contains a value outside its declared source slots')
    _assign_transport_fields(request, rows, slots, external)
    groups = {}
    scalar_slots = []
    scalar_rows = []
    for path in slots:
        location = _array_position(request, path, protected)
        if location is None:
            scalar_slots.append(path)
        else:
            groups.setdefault(location[0], {'slots': [], 'rows': []})['slots'].append(path)
    for row in rows:
        location = _array_position(request, row['field'], protected)
        if location is None:
            scalar_rows.append(row)
        else:
            groups.setdefault(location[0], {'slots': [], 'rows': []})['rows'].append(row)
    changes = []
    for prefix_tuple, group in sorted(groups.items(), key=lambda item: (-len(item[0]), json.dumps(item[0]))):
        prefix = list(prefix_tuple)
        old = copy.deepcopy(_at(request, prefix))
        offset = len(prefix)
        group_slots, group_rows = group['slots'], group['rows']
        # Several media leaves in the same item are a fixed native record. Only
        # its declared leaves are editable; remove none of its other fields.
        shapes = {tuple(path[offset + 1:]) for path in group_slots}
        shapes.update(tuple(row['field'][offset + 1:]) for row in group_rows)
        if len(shapes) > 1:
            current = {tuple(row['field']) for row in group_rows}
            for path in group_slots:
                if tuple(path) not in current:
                    _remove_leaf(request, path)
            for row in group_rows:
                rc.put(request, row['field'], row['value'])
            continue
        owned = {path[offset] for path in group_slots}
        # A newly authored array may have no saved slots. Existing items then
        # remain unrelated; explicit new fields cannot overwrite them.
        if not owned and old and group_rows:
            raise ValueError('declare the existing media slots before rebuilding a populated media array')
        items = []
        unique = {}
        for row in group_rows:
            field = row['field']
            identity = (tuple(field), row['value'])
            if identity in unique:
                items[unique[identity]]['rows'].append(row)
                continue
            position = field[offset]
            relative = field[offset + 1:]
            if position < len(old) and (position in owned or not owned):
                item = copy.deepcopy(old[position])
            elif owned:
                selected = min(index for index in owned if index < len(old)) if any(index < len(old) for index in owned) else None
                item = copy.deepcopy(old[selected]) if selected is not None else ({} if relative else None)
            else:
                item = {} if relative else None
            if relative:
                if not isinstance(item, (dict, list)):
                    raise ValueError('selected media array item has no declared native container')
                rc.put(item, relative, row['value'])
            else:
                item = row['value']
            unique[identity] = len(items)
            items.append({'value': item, 'relative': relative, 'rows': [row]})
        rebuilt, positions = [], {}
        cursor = 0

        def append_media(item):
            index = len(rebuilt)
            rebuilt.append(item['value'])
            for row in item['rows']:
                row['field'] = prefix + [index] + item['relative']

        last_owned = max(owned) if owned else -1
        for index, item in enumerate(old):
            if index in owned:
                if cursor < len(items):
                    append_media(items[cursor])
                    cursor += 1
            else:
                positions[index] = len(rebuilt)
                rebuilt.append(copy.deepcopy(item))
            if index == last_owned:
                for extra in items[cursor:]:
                    append_media(extra)
                cursor = len(items)
        for extra in items[cursor:]:
            append_media(extra)
        for key in REQUEST_FIELDS:
            if external.get(key) is not None:
                external[key] = _move_field(external[key], prefix, positions)
        control = (external.get('prompt_syntax') or {}).get('control')
        if control is not None:
            control['field'] = _move_field(control['field'], prefix, positions)
        group_ids = {id(row) for row in group_rows}
        for row in rows:
            if id(row) not in group_ids:
                row['field'] = _move_field(row['field'], prefix, positions)
        scalar_slots = [_move_field(path, prefix, positions) for path in scalar_slots]
        if prefix:
            rc.put(request, prefix, rebuilt)
        else:
            request = rebuilt
        if old != rebuilt:
            changes.append({'field': prefix, 'owner': 'reference-order', 'before': old, 'after': rebuilt})
    selected = {tuple(row['field']) for row in scalar_rows}
    for path in scalar_slots:
        if tuple(path) not in selected:
            _remove_leaf(request, path)
    assigned = {}
    for row in scalar_rows:
        field = tuple(row['field'])
        if field in assigned and assigned[field] != row['value']:
            raise ValueError('different reference values require distinct native request fields')
        assigned[field] = row['value']
        rc.put(request, row['field'], row['value'])
    return request, changes


def build(selection: dict, task: dict, reader, root: Path, out_dir: str,
          delivery: bytes) -> tuple[dict[str, bytes], dict]:
    """Build and validate one exact request; leave publication to its caller."""
    source = {'kind': 'authored', 'sha256': c.content_id(selection)}
    root = Path(root)
    generated = {}
    pins = {}

    def measured(row: dict, field: str = 'path') -> bytes:
        path = c.text(row.get(field), 'external evidence path')
        if path in generated:
            raw = generated[path]
        else:
            raw = reader.read(reader.select(path))
        digest = c.digest(raw)
        if any(expected != digest for expected in (row.get('sha256'), pins.get(path)) if expected is not None):
            raise ValueError('selected external evidence changed: ' + path)
        row['sha256'] = digest
        return raw

    def uploaded_hash(path: str) -> str:
        c.text(path, 'uploaded carrier file')
        if Path(path).is_absolute():
            from private_state import assert_public_path
            from production_store import stable_read
            assert_public_path(path)
            selected = Path(path)
            raw = stable_read(selected, path)
        else:
            raw = reader.read(reader.select(path))
        digest = c.digest(raw)
        if path in pins and pins[path] != digest:
            raise ValueError('selected uploaded carrier changed: ' + path)
        return digest

    if isinstance(selection.get('image_input'), str):
        c.exact(selection, {'image_input'}, 'external input file selection')
        source = reader.select(selection['image_input'])
        existing = copy.deepcopy(reader.json(source))
        external = existing.get('external_request')
        if not isinstance(external, dict):
            raise ValueError('select an image input plan with an external request')
        prepared_path = existing.get('prepared_references')
        prepared = reader.json(reader.select(prepared_path)) if prepared_path else None
        selection = draft(existing, c.decode(measured(external, 'file')), prepared=prepared,
            package_root=c.local(root, prepared_path).parent if prepared_path else None, root=root)
    missing = unresolved(selection)
    if missing:
        raise ValueError('external input requires selected choices: ' + ', '.join(row['field'] for row in missing))
    pins = copy.deepcopy(selection['source_files'])
    if not isinstance(pins, dict):
        raise ValueError('external source_files must contain the recorded source hashes')
    for path, digest in pins.items():
        c.text(path, 'recorded external source path')
        c.sha(digest)
    previous_uploads = selection['source_uploads']
    if not isinstance(previous_uploads, list):
        raise ValueError('external source_uploads must contain the recorded carrier bindings')
    for item in previous_uploads:
        c.exact(item, {'carrier_sha256', 'evidence_sha256', 'locator', 'value'}, 'recorded external upload')
        c.sha(item['carrier_sha256'])
        c.sha(item['evidence_sha256'])
        c.text(item['locator'], 'recorded upload evidence locator')
        c.text(item['value'], 'recorded provider media value')
    plan = copy.deepcopy(selection['image_input'])
    request = copy.deepcopy(selection['request'])
    if not isinstance(request, (dict, list)):
        raise ValueError('external request controls must be a JSON object or array')
    external = plan['external_request']
    if any(key in external for key in ('file', 'sha256', 'reference_fields', 'request', 'schema_validation', 'prompt_check')):
        raise ValueError('external request files and reference_fields are derived from the authored input')
    measured(plan['model']['evidence'])
    if external.get('model_identity') is not None:
        measured(external['model_identity']['evidence'])
    for field in ('schema', 'vocabulary_record'):
        if external.get(field) is not None:
            measured(external[field])
    with tempfile.TemporaryDirectory(prefix='external-reference-inputs-') as temporary:
        validation_root = root
        files = {}
        carriers = []
        canonical = selection['reference_delivery'] is not None
        transports = {}
        for reference in plan['references']:
            identifier = c.text(reference['id'], 'external reference id')
            if identifier in transports:
                raise ValueError('duplicate external reference transport id: ' + identifier)
            if canonical:
                c.exact(reference, {'id'} | ({'transport'} if 'transport' in reference else set()),
                        'prepared external reference transport')
            transports[identifier] = reference.pop('transport', None)
        if canonical:
            import production_reference_inputs
            validation_root = Path(temporary)
            output = c.local(validation_root, out_dir, exists=False)
            prepared = production_reference_inputs.build_external(selection['reference_delivery'],
                root=root, output_dir=output, publication_dir=out_dir, reader=reader)
            files = {path.relative_to(output).as_posix(): path.read_bytes()
                     for path in output.rglob('*') if path.is_file()}
            generated.update({(Path(out_dir) / name).as_posix(): raw for name, raw in files.items()})
            plan['references'] = prepared['references']
            plan['prepared_references'] = (Path(out_dir) / 'prepared-reference-set.json').as_posix()
            carriers = prepared['carriers']
        else:
            from production_evidence import inspect
            from PIL import Image
            for reference in plan['references']:
                raw = measured(reference, 'file')
                image_format = inspect(raw, 'image')['format']
                media_type = 'image/svg+xml' if image_format == 'SVG' else Image.MIME.get(image_format, 'application/octet-stream')
                carriers.append({'reference': reference['id'], 'path': reference['file'],
                                 'sha256': reference['sha256'], 'media_type': media_type})
        carrier_map = {row['reference']: row for row in carriers}
        rows, pending = [], []

        def evidence_matches(transport, carrier):
            measured(transport['evidence'])
            matching = [item for item in previous_uploads
                if item['evidence_sha256'] == transport['evidence']['sha256']
                and item['locator'] == transport['evidence']['locator']]
            if not matching:
                return True
            return any(item['carrier_sha256'] == carrier['sha256'] and item['value'] == transport['value']
                       for item in matching)

        def shared_transport(carrier):
            matches = {}
            for candidate in transports.values():
                if not isinstance(candidate, dict) or any(candidate.get(key) is None
                        for key in ('value', 'evidence', 'uploaded_file')):
                    continue
                try:
                    digest = uploaded_hash(candidate['uploaded_file'])
                    selected = copy.deepcopy(candidate)
                    accepted = digest == carrier['sha256'] and evidence_matches(selected, carrier)
                except (OSError, ValueError):
                    # An unused old upload is not selected by this carrier.
                    continue
                if accepted:
                    identity = c.content_id({key: value for key, value in candidate.items() if key != 'uploaded_file'})
                    matches[identity] = selected
            return copy.deepcopy(next(iter(matches.values()))) if len(matches) == 1 else None

        for reference in plan['references']:
            measured(reference, 'file')
            identifier = reference['id']
            carrier = carrier_map[identifier]
            transport = copy.deepcopy(transports.get(identifier))
            reason = None
            if transport is None or any(transport.get(key) is None for key in ('value', 'evidence')):
                reason = 'Select the actual uploaded carrier, provider media value and upload evidence.'
            else:
                required = {'value', 'evidence'}
                optional = {'field', 'uploaded_file'}
                c.exact(transport, required | (set(transport) & optional), 'external reference transport')
                c.text(transport['value'], 'external uploaded reference value')
                selected_file = transport.get('uploaded_file')
                if selected_file is None and not canonical:
                    selected_file = reference['file']
                if selected_file is None:
                    reason = 'Select the file actually uploaded for this prepared carrier.'
                else:
                    try:
                        uploaded = uploaded_hash(selected_file)
                    except (FileNotFoundError, OSError) as exc:
                        raise ValueError('selected uploaded carrier is unavailable: ' + selected_file) from exc
                    if uploaded != carrier['sha256']:
                        reason = 'The prepared carrier changed. Select its actual upload file, value and evidence.'
                    elif not evidence_matches(transport, carrier):
                        reason = 'The retained upload evidence does not match the carrier and provider media value. Select actual evidence for this upload.'
            if reason is not None and canonical:
                shared = shared_transport(carrier)
                if shared is not None:
                    transport, reason = shared, None
            if reason is None:
                c.exact(transport, {'value', 'evidence'} | (set(transport) & {'field', 'uploaded_file'}),
                        'external reference transport')
                transport.pop('uploaded_file', None)
                measured(transport['evidence'])
                rows.append({'reference': identifier, **transport})
            if reason is not None:
                pending.append({'field': 'external.image_input.references.' + identifier + '.transport',
                    'code': 'provider-upload-required', 'message': reason,
                    'carrier': {key: carrier[key] for key in ('path', 'sha256', 'media_type')}})
        if pending:
            image_input._model_contract(plan['model'])
            return files, {'source': source, 'state': 'reference-upload-required',
                'unresolved': pending, 'carriers': carriers, 'request': None, 'model': plan['model'],
                'references': plan['references'], 'changes': [], 'prompt_check': None,
                'schema_validation': None, 'dialect': plan['model'].get('prompt_dialect')}
        request, changes = _media(request, rows, copy.deepcopy(selection['media_slots']), external)
        external['reference_fields'] = rows

        def bind(path, value, owner):
            if path is None:
                return
            before = rc.get(request, path) if rc.present(request, path) else None
            rc.put(request, path, value)
            if before != value:
                changes.append({'field': path, 'owner': owner, 'before': before, 'after': value})

        bind(external['prompt_field'], delivery.decode('utf-8'), 'delivery')
        bind(external['model_field'], plan['model']['target']['model_identifier'], 'model.target')
        bind(external['operation_field'], plan['model']['target']['operation'], 'model.target')
        bind(external['count_field'], external['count'], 'external_request.count')
        raw = c.encoded(request)
        external.update(file=(Path(out_dir) / 'external-request.json').as_posix(), sha256=c.digest(raw))
        generated[external['file']] = raw

        def read(path):
            return generated[path] if path in generated else reader.read(reader.select(path))

        binding = image_input.validate(plan, validation_root, read=read)
        image_input._request(plan, external, request, prompt=delivery.decode('utf-8'))
        files.update({'external-request.json': raw, 'image-input.json': c.encoded(plan)})
        return files, {'source': source, 'state': 'materialized', 'unresolved': [],
            'carriers': carriers, 'request': request, 'model': binding['model'],
            'references': binding['references'], 'changes': changes,
            'prompt_check': binding['external_request']['prompt_check'],
            'schema_validation': binding['external_request']['schema_validation'],
            'dialect': plan['model'].get('prompt_dialect')}
