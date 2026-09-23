"""Build and seal requests from declared transport fields and verified media bytes."""
from __future__ import annotations

import copy
import io
import mimetypes
from pathlib import Path
from typing import Any, Iterable

import execution_contract as c

# These fields are declared display or audit data. Every unclassified field stays
# in the execution projection, including prose used to direct request construction.
DISPLAY_FIELDS = {
    'service': frozenset({'label', 'documentation', 'observed_at', 'source'}),
    'offering': frozenset({'observed_at', 'parameter_observations', 'reference_schemas', 'label'}),
    'model': frozenset({'label', 'description', 'aliases', 'search_profile', 'search_terms', 'tags', 'domains',
                        'curation_status', 'offerings', 'verified_on', 'recommended_uses', 'avoid_uses'}),
    'policy': frozenset({'label', 'observed_at', 'parameter_observations', 'reference_schemas'}),
}
COST_FIELDS = {
    'service': frozenset({'pricing'}),
    'offering': frozenset({'pricing'}),
    'model': frozenset(),
    'policy': frozenset(),
}
MANAGEMENT_VALUE = '00000000-0000-4000-8000-000000000000'
LAYOUT_FIELDS = {'model', 'operation', 'primary_text', 'negative_text', 'output_count', 'fixed_output_count',
                 'seed', 'media', 'management', 'content', 'fields'}
RENDERED_FIELDS = {'request', 'layout', 'media', 'sealed', 'request_sha256', 'profile', 'profile_sha256',
                   'request_trace', 'fields', 'output_count'}
PROFILE_BINDING_FIELDS = {'reference_number', 'attachment_number', 'region_pixels', 'role'}


def execution_projection(value: dict, kind: str) -> dict:
    if kind not in DISPLAY_FIELDS or not isinstance(value, dict):
        raise ValueError('unknown execution record kind')
    excluded = DISPLAY_FIELDS[kind] | COST_FIELDS[kind]
    return copy.deepcopy({key: item for key, item in value.items() if key not in excluded})


def execution_hashes(service: dict, offering: dict, transport_file: Path, *,
                     model: dict | None = None, policy: dict | None = None) -> dict:
    service_sha256 = c.content_id(execution_projection(service, 'service'))
    contract = {
        'offering': execution_projection(offering, 'offering'),
        'model': execution_projection(model or {}, 'model'),
        'policy': execution_projection(policy or {}, 'policy'),
    }
    return {
        'service_execution_sha256': service_sha256,
        'offering_contract_sha256': c.content_id(contract),
        'transport_sha256': c.digest(c.read(transport_file)),
    }


def file_ref(root: Path, path: str) -> dict:
    raw = c.read(c.local(root, path))
    return {'path': path, 'sha256': c.digest(raw)}


def read_ref(root: Path, ref: Any) -> bytes:
    c.exact(ref, {'path', 'sha256'}, 'file reference')
    c.sha(ref['sha256'])
    raw = c.read(c.local(root, ref['path']))
    if c.digest(raw) != ref['sha256']:
        raise ValueError('file reference content changed: ' + ref['path'])
    return raw


def target(value: Any) -> dict:
    c.exact(value, {'service', 'model_identifier', 'operation'}, 'request target')
    for key, item in value.items():
        c.text(item, 'target ' + key)
    return value


def path_parts(value: str) -> list[str]:
    """Read the dot-separated request-key syntax, not the meaning of its spelling."""
    if not isinstance(value, str) or not value or any(not part for part in value.split('.')):
        raise ValueError('request key requires nonempty path components')
    return value.split('.')


def _path(path: Any) -> list:
    if not isinstance(path, list) or not path:
        raise ValueError('request field path must be a nonempty array')
    for part in path:
        is_key = isinstance(part, str) and part != ''
        is_index = type(part) is int and part >= 0
        if not (is_key or is_index):
            raise ValueError('invalid request field component')
    return path


def get(value: Any, path: list) -> Any:
    for part in _path(path):
        if isinstance(value, list):
            if type(part) is not int or part >= len(value):
                raise ValueError('request list field is absent')
        elif isinstance(value, dict):
            if not isinstance(part, str) or part not in value:
                raise ValueError('request object field is absent')
        else:
            raise ValueError('request field crosses a scalar')
        value = value[part]
    return value


def present(value: Any, path: list) -> bool:
    try:
        get(value, path)
    except ValueError:
        return False
    return True


def put(value: Any, path: list, item: Any) -> None:
    path = _path(path)
    node = value
    for index, part in enumerate(path[:-1]):
        if isinstance(node, dict) and isinstance(part, str):
            if part not in node:
                node[part] = [] if type(path[index + 1]) is int else {}
            node = node[part]
        elif isinstance(node, list) and type(part) is int and part < len(node):
            node = node[part]
        else:
            raise ValueError('request field crosses an incompatible container')
    last = path[-1]
    if isinstance(node, dict) and isinstance(last, str):
        node[last] = copy.deepcopy(item)
    elif isinstance(node, list) and type(last) is int and last < len(node):
        node[last] = copy.deepcopy(item)
    else:
        raise ValueError('request field has no declared location')


def remove(value: Any, path: list) -> None:
    node = value
    for part in path[:-1]:
        node = node[part]
    if isinstance(node, list):
        raise ValueError('management fields cannot remove a positional list entry')
    node.pop(path[-1], None)


def overlaps(one: list, two: list) -> bool:
    shared = min(len(one), len(two))
    return one[:shared] == two[:shared]


class RequestWriter:
    """Record the source of each assigned leaf while preserving explicit values."""

    def __init__(self):
        self.request = {}
        self.trace = []
        self.written = []

    def write(self, path: list, value: Any, *, source_kind: str,
              source_refs: list, transform_id: str,
              binding_ids: list | None = None, same: bool = False):
        _path(path)
        assignments = []

        def collect(location, item):
            # Objects contain independent fields. Arrays remain ordered values.
            if isinstance(item, dict) and item:
                if any(not isinstance(key, str) for key in item):
                    raise ValueError('request object keys must be strings')
                for key, child in sorted(item.items()):
                    collect(location + [key], child)
            else:
                assignments.append((location, item))

        collect(list(path), value)
        for location, item in assignments:
            conflict = any(overlaps(previous, location) for previous in self.written)
            if conflict and not (same and present(self.request, location)
                                 and c.encoded(get(self.request, location)) == c.encoded(item)):
                raise ValueError('two inputs write the same request field: ' + str(location))

        # Stage the write so a malformed container cannot leave a partial request.
        result = copy.deepcopy(self.request)
        for location, item in assignments:
            put(result, location, item)
        self.request = result
        for location, item in assignments:
            self.written.append(location)
            self.trace.append({
                'source_kind': source_kind,
                'source_refs': copy.deepcopy(source_refs),
                'transform_id': transform_id,
                'target_field': location,
                'target_range': {'start': 0, 'end': len(item)} if isinstance(item, str) else None,
                'binding_ids': list(binding_ids or []),
            })

    def defaults(self, value: dict, source_refs: list, prefix: list | None = None):
        """Fill absent object fields; an explicit scalar or list keeps its value."""
        for key, item in sorted(value.items()):
            path = (prefix or []) + [key]
            if present(self.request, path):
                current = get(self.request, path)
                if isinstance(item, dict) and isinstance(current, dict):
                    if not current and item:
                        # The empty object records a container, not ownership of
                        # keys introduced later by the declared defaults.
                        self.written = [p for p in self.written if p != path]
                        self.trace = [row for row in self.trace if row['target_field'] != path]
                    self.defaults(item, source_refs, path)
            else:
                self.write(path, item, source_kind='model-setting',
                           source_refs=source_refs, transform_id='declared-default')


def media_metadata(path: Path, *, role: str, binding_ids: list[str] | None = None) -> dict:
    raw = c.read(path)
    c.text(role, 'media role')
    media_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    result = {
        'path': str(path),
        'sha256': c.digest(raw),
        'size': len(raw),
        'media_type': media_type,
        'role': role,
        'binding_ids': list(binding_ids or []),
        'dimensions': None,
    }
    if media_type.split('/', 1)[0] == 'image':
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            result['dimensions'] = {'width': image.width, 'height': image.height}
            actual = Image.MIME.get(image.format)
            if actual is not None and actual != media_type:
                raise ValueError('media bytes differ from their declared file format')
    return result


def output_count(request: dict, layout: dict) -> int:
    if layout['output_count'] is None:
        count = layout['fixed_output_count']
    else:
        if layout['fixed_output_count'] is not None:
            raise ValueError('count must have one declared source')
        count = get(request, layout['output_count'])
    if type(count) is not int or count < 1:
        raise ValueError('a positive declared output count is required')
    return count


def validate_layout(request: dict, layout: dict, media: list[dict], expected_target: dict) -> None:
    c.exact(layout, LAYOUT_FIELDS, 'transport layout')
    # A service that takes the model or the operation in its address has no field for it.
    declared_target = (('model', expected_target['model_identifier']),
                       ('operation', expected_target['operation']))
    for slot, value in declared_target:
        if layout[slot] is not None and get(request, layout[slot]) != value:
            raise ValueError('the built request changes its declared target')
    output_count(request, layout)
    if layout['primary_text'] is not None and not isinstance(get(request, layout['primary_text']), str):
        raise ValueError('primary text must be a string')
    if layout['negative_text'] is not None and not isinstance(get(request, layout['negative_text']), str):
        raise ValueError('negative text must be a string')

    destinations = []
    for entry in layout['media']:
        c.exact(entry, {'index', 'field'}, 'media field')
        if type(entry['index']) is not int or not 0 <= entry['index'] < len(media):
            raise ValueError('media field selects an absent input')
        _path(entry['field'])
        get(request, entry['field'])
        if any(overlaps(entry['field'], other) for other in destinations):
            raise ValueError('media fields overlap')
        destinations.append(entry['field'])
    if {entry['index'] for entry in layout['media']} != set(range(len(media))):
        raise ValueError('every media input must reach the actual request')

    content_ids = set()
    text_channels = [layout['primary_text'], layout['negative_text']]
    for entry in layout['content']:
        c.exact(entry, {'id', 'field'}, 'authored content slot')
        c.text(entry['id'], 'content slot ID')
        if entry['id'] in content_ids:
            raise ValueError('duplicate content slot ID')
        content_ids.add(entry['id'])
        get(request, entry['field'])
        if entry['field'] not in text_channels:
            raise ValueError('content slots are limited to declared text channels')

    target_fields = (layout['model'], layout['operation'], layout['output_count'])
    protected = [field for field in target_fields if field is not None]
    protected += destinations
    protected += [entry['field'] for entry in layout['content']]
    if layout['seed'] is not None:
        protected.append(layout['seed'])
    for management in layout['management']:
        _path(management)
        get(request, management)
        if any(overlaps(management, field) for field in protected):
            raise ValueError('management fields overlap meaningful request inputs')

    for entry in layout['fields']:
        c.exact(entry, {'id', 'field', 'kind'}, 'semantic request field')
        c.text(entry['id'], 'semantic field ID')
        if entry['kind'] not in {'fixed', 'parameter', 'content', 'media'}:
            raise ValueError('unknown semantic field kind')
        get(request, entry['field'])
    if len({entry['id'] for entry in layout['fields']}) != len(layout['fields']):
        raise ValueError('duplicate semantic field ID')


def _profile(sealed: dict, layout: dict) -> dict:
    """The sealed request with authored content and media replaced by their slots."""
    profile = copy.deepcopy(sealed)
    profile['context'] = {key: value for key, value in profile['context'].items() if key == 'output_kind'}
    for item in layout['content']:
        put(profile['request'], item['field'], {'content_slot': item['id']})
    for item in layout['media']:
        put(profile['request'], item['field'], {'media_index': item['index']})
    for item in profile['media']:
        item.pop('sha256')
        item.pop('size')
        item.pop('binding_ids')
    profile['bindings'] = [
        {key: value for key, value in binding.items() if key in PROFILE_BINDING_FIELDS}
        for binding in profile['bindings']
    ]
    return profile


def _record_remaining(node: Any, path: list, excluded: list[list], fields: dict) -> None:
    """Record every leaf outside the declared and management fields as a fixed field."""
    if any(path[:len(prefix)] == prefix for prefix in excluded):
        return
    if isinstance(node, dict) and node:
        for key, value in node.items():
            _record_remaining(value, path + [key], excluded, fields)
    elif isinstance(node, list) and node:
        for index, value in enumerate(node):
            _record_remaining(value, path + [index], excluded, fields)
    elif path:
        identifier = 'fixed:' + c.encoded(path).decode('utf-8').strip()
        fields[identifier] = {'kind': 'fixed', 'value': copy.deepcopy(node), 'field': list(path)}


def _semantic_fields(request: dict, normal: dict, layout: dict, sealed: dict) -> dict:
    fields = {
        entry['id']: {
            'kind': entry['kind'],
            'value': copy.deepcopy(get(normal, entry['field'])),
            'field': entry['field'],
        }
        for entry in layout['fields']
    }
    declared_paths = [item['field'] for item in layout['fields']]
    _record_remaining(normal, [], [*declared_paths, *layout['management']], fields)
    if layout['output_count'] is None:
        fields['count'] = {'kind': 'fixed', 'value': output_count(request, layout), 'field': None}
    for key, value in sealed['context'].items():
        if key not in {'subjects', 'purpose', 'output_kind'}:
            raise ValueError('unknown semantic context field')
        fields[key] = {'kind': 'fixed', 'value': copy.deepcopy(value), 'field': None}
    fields['reference_bindings'] = {'kind': 'fixed', 'value': sealed['bindings'], 'field': None}
    return fields


def seal(request: dict, layout: dict, media: list[dict], expected_target: dict, execution: dict,
         trace: list[dict], bindings: list[dict] | None = None, context: dict | None = None) -> dict:
    """Seal the request and build a profile without generalizing parameter values."""
    target(expected_target)
    validate_layout(request, layout, media, expected_target)
    wire = copy.deepcopy(request)
    normal = copy.deepcopy(request)
    for path in layout['management']:
        remove(normal, path)
    for item in layout['media']:
        index = item['index']
        put(normal, item['field'], {'media_index': index, 'sha256': media[index]['sha256']})
    public_media = [{key: copy.deepcopy(value) for key, value in item.items() if key != 'path'}
                    for item in media]
    sealed = {
        'target': copy.deepcopy(expected_target),
        'execution': copy.deepcopy(execution),
        'request': normal,
        'output_count': output_count(request, layout),
        'media': public_media,
        'bindings': copy.deepcopy(bindings or []),
        'context': copy.deepcopy(context or {}),
    }
    profile = _profile(sealed, layout)
    fields = _semantic_fields(request, normal, layout, sealed)
    return {
        'request': wire,
        'layout': copy.deepcopy(layout),
        'media': copy.deepcopy(media),
        'sealed': sealed,
        'request_sha256': c.content_id(sealed),
        'profile': profile,
        'profile_sha256': c.content_id(profile),
        'request_trace': copy.deepcopy(trace),
        'fields': fields,
        'output_count': output_count(request, layout),
    }


def validate_seal(rendered: Any) -> None:
    c.exact(rendered, RENDERED_FIELDS, 'rendered request')
    sealed = rendered['sealed']
    rebuilt = seal(rendered['request'], rendered['layout'], rendered['media'], sealed['target'],
                   sealed['execution'], rendered['request_trace'], sealed['bindings'], sealed['context'])
    if rebuilt != rendered:
        raise ValueError('rendered request no longer matches its sealed projection')


def materialize(rendered: dict, media_ids: dict[int, str]) -> dict:
    """Replace only the declared media positions after upload; keep all authored bytes."""
    validate_seal(rendered)
    if set(media_ids) != set(range(len(rendered['media']))):
        raise ValueError('upload results do not cover the sealed input set')
    request = copy.deepcopy(rendered['request'])
    for entry in rendered['layout']['media']:
        identifier = media_ids[entry['index']]
        c.text(identifier, 'uploaded media identifier')
        put(request, entry['field'], identifier)
    return request


def validate_wire(rendered: dict, request: dict, media_ids: dict[int, str]) -> None:
    if materialize(rendered, media_ids) != request:
        raise ValueError('wire request differs from the previewed and authorized request')


def verify_media_bytes(rendered: dict) -> None:
    for item in rendered['media']:
        raw = c.read(Path(item['path']))
        if len(raw) != item['size'] or c.digest(raw) != item['sha256']:
            raise ValueError('sealed media input changed')


def receipt_projection(rendered: dict) -> dict:
    validate_seal(rendered)
    layout = rendered['layout']
    sealed = rendered['sealed']
    request = copy.deepcopy(rendered['request'])
    for path in layout['management']:
        put(request, path, MANAGEMENT_VALUE)
    for item in layout['media']:
        put(request, item['field'], MANAGEMENT_VALUE)
    media = [{**item, 'path': 'sha256:' + item['sha256']} for item in rendered['media']]
    return seal(request, layout, media, sealed['target'], sealed['execution'],
                rendered['request_trace'], sealed['bindings'], sealed['context'])
