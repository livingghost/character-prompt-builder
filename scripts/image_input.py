"""Bind image inputs and exact external requests for ordinary generation or editing.

This is the shared input owner. Semantic editing adds change/preserve meaning;
the prepared-reference-set remains the owner of selected source provenance.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import execution_contract as c
import request_contract as rc

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/authoring/image-input-plan.schema.json'
DERIVED = {'plan_sha256', 'binding_sha256', 'status', 'prepared_reference_set',
           'prepared_references_sha256'}


def _structure(plan: Any) -> None:
    from state_protocol import validate_against_schema
    errors = validate_against_schema(plan, c.load(SCHEMA))
    if errors:
        raise ValueError('image input plan: ' + '; '.join(errors))
    model = plan['model']
    if (model['catalog_status'] == 'defined') != (model['catalog_model'] is not None):
        raise ValueError('defined models name their catalog record; missing models record null')
    ids = [row['id'] for row in plan['references']]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate reference id')
    from reference_delivery import validate_authority_scope, validate_subject_uses
    for row in plan['references']:
        validate_authority_scope({'controls': row['use_for'], 'must_not_control': row['do_not_transfer']})
        validate_subject_uses(row.get('subject_uses', []))
    external = plan['external_request']
    if external is None:
        return
    if [row['reference'] for row in external['reference_fields']] != ids:
        raise ValueError('external reference fields must cover every selected reference in order')
    paths = [external[key] for key in ('model_field', 'prompt_field', 'count_field', 'operation_field')
             if external[key] is not None]
    for index, path in enumerate(paths):
        if any(rc.overlaps(path, other) for other in paths[:index]):
            raise ValueError('external request fields overlap')
    media = []
    refs = {row['id']: row for row in plan['references']}
    for row in external['reference_fields']:
        path = row['field']
        for other in paths:
            if rc.overlaps(path, other):
                raise ValueError('external request fields overlap: '
                    f"reference {row['reference']!r} at {json.dumps(path, ensure_ascii=False)} "
                    f'conflicts with request field {json.dumps(other, ensure_ascii=False)}')
        for other in media:
            if rc.overlaps(path, other['field']):
                left, right = refs[row['reference']], refs[other['reference']]
                same_bytes = (left.get('sha256') is not None and left.get('sha256') == right.get('sha256')) or left['file'] == right['file']
                if path != other['field'] or row['value'] != other['value'] or not same_bytes:
                    raise ValueError('external media fields overlap without identical bytes and value: '
                        f"reference {row['reference']!r} at {json.dumps(path, ensure_ascii=False)} conflicts with "
                        f"reference {other['reference']!r} at {json.dumps(other['field'], ensure_ascii=False)}")
        media.append(row)


def _reference_bindings(plan: dict, external: dict, *, prepared: dict | None = None) -> list[dict]:
    rows = [
        {'reference_number': index, 'request_field': list(field['field']),
         'region_pixels': None, 'role': reference['role'],
         'controls': list(reference['use_for']),
         'must_not_control': list(reference['do_not_transfer']),
         'subject_uses': copy.deepcopy(reference.get('subject_uses', []))}
        for index, (reference, field) in enumerate(zip(plan['references'], external['reference_fields']), 1)
    ]
    prepared = prepared if prepared is not None else plan.get('prepared_reference_set')
    if prepared is not None:
        for row, selected in zip(rows, prepared['selected_references']):
            if 'subject_id' in selected:
                row['subject_id'] = selected['subject_id']
    return rows


def reference_bindings(plan: dict, *, base: Path | None = None) -> list[dict]:
    """Project authored scopes onto exact external fields before request authoring."""
    _structure(plan)
    if plan['external_request'] is None:
        raise ValueError('external reference instructions require an external_request binding')
    prepared = None
    if plan.get('prepared_references') is not None:
        if base is None:
            raise ValueError('prepared reference instructions require the Studio base directory')
        import production_store
        from prepare_generation_references import validate_prepared_reference_set
        base = Path(base)
        c.local(base, plan['prepared_references'])
        prepared = validate_prepared_reference_set(c.decode(production_store.stable_bytes(base, plan['prepared_references'])))
        _reference_rows(plan, prepared, require_hash=False)
    return _reference_bindings(plan, plan['external_request'], prepared=prepared)


def _matching_media_paths(value: Any, pattern: tuple, prefix: tuple = ()):
    """Visit declared media field shapes across every actual array position."""
    if not pattern:
        yield prefix
    elif pattern[0] is None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                yield from _matching_media_paths(item, pattern[1:], prefix + (index,))
    elif isinstance(value, dict) and pattern[0] in value:
        yield from _matching_media_paths(value[pattern[0]], pattern[1:], prefix + (pattern[0],))


def _request(plan: dict, external: dict, request: Any, *, prompt: str | None = None) -> None:
    if not isinstance(request, dict):
        raise ValueError('external request must be one JSON object')
    target = plan['model']['target']
    if external['model_field'] is not None and rc.get(request, external['model_field']) != target['model_identifier']:
        raise ValueError('external request substitutes the selected model identifier')
    if external['operation_field'] is not None and rc.get(request, external['operation_field']) != target['operation']:
        raise ValueError('external request operation differs from the selected target')
    actual_prompt = rc.get(request, external['prompt_field'])
    c.text(actual_prompt, 'external instruction prompt')
    if prompt is not None and actual_prompt != prompt:
        raise ValueError('external request prompt differs from the production delivery')
    if external['count_field'] is not None:
        actual_count = rc.get(request, external['count_field'])
        if type(actual_count) is not int or actual_count != external['count']:
            raise ValueError('external output count differs from its declared request')
    fields = {tuple(row['field']) for row in external['reference_fields']}
    patterns = set()
    for row in external['reference_fields']:
        if rc.get(request, row['field']) != row['value']:
            raise ValueError('external request reference is missing or changed: ' + row['reference'])
        path = row['field']
        patterns.add(tuple(None if type(part) is int else part for part in path))
    for pattern in patterns:
        if any(path not in fields for path in _matching_media_paths(request, pattern)):
            raise ValueError('external media array contains an undeclared or missing reference')


def _reference_rows(binding: dict, prepared: dict, *, require_hash: bool = True) -> None:
    selected = prepared['selected_references']
    if len(selected) != len(binding['references']):
        raise ValueError('image input reference count differs from prepared delivery')
    if selected and prepared['transport_mode'] not in {'multi-image', 'single-board'}:
        raise ValueError('image inputs require model-facing references')
    for expected, actual in zip(binding['references'], selected):
        expected_hash = expected.get('sha256')
        if (require_hash or expected_hash is not None) and actual['source']['sha256'] != expected_hash:
            raise ValueError('image input reference bytes, role or order differ from prepared delivery')
        if actual['role'] != expected['role']:
            raise ValueError('image input reference bytes, role or order differ from prepared delivery')
        if actual['authority'] != {'controls': expected['use_for'], 'must_not_control': expected['do_not_transfer']}:
            raise ValueError('image input reference authority differs from prepared delivery')
        if actual.get('subject_uses', []) != expected.get('subject_uses', []):
            raise ValueError('image input subject uses differ from prepared delivery')


def validate(plan: dict, base: Path, *, read=None) -> dict:
    """Read each input once and pin prepared provenance and exact request bytes."""
    _structure(plan)
    base = Path(base)
    result = copy.deepcopy(plan)
    cache = {}

    def file(path: str, expected: str | None = None) -> bytes:
        c.local(base, path)
        if path not in cache:
            if read is None:
                import production_store
                cache[path] = production_store.stable_bytes(base, path)
            else:
                cache[path] = read(path)
        raw = cache[path]
        if expected is not None and c.digest(raw) != expected:
            raise ValueError('image input file checksum mismatch: ' + path)
        return raw

    def evidence(value: dict) -> None:
        file(value['path'], value['sha256'])

    evidence(result['model']['evidence'])
    from production_evidence import inspect
    image_metadata = {}
    for row in result['references']:
        raw = file(row['file'], row.get('sha256'))
        image_metadata[row['id']] = {**inspect(raw, 'image'), 'size': len(raw)}
        row['sha256'] = c.digest(raw)
    # Recheck shared attachment identity using the measured bytes, including
    # plans that supply hashes before the files have been read.
    _structure(result)
    if result.get('prepared_references') is not None:
        from prepare_generation_references import validate_prepared_reference_set
        raw = file(result['prepared_references'])
        prepared = validate_prepared_reference_set(c.decode(raw))
        _reference_rows(result, prepared)
        result['prepared_reference_set'] = prepared
        result['prepared_references_sha256'] = c.digest(raw)
    external = result['external_request']
    if external is not None:
        raw = file(external['file'], external.get('sha256'))
        request = c.decode(raw)
        _request(result, external, request)
        if external.get('model_identity') is not None:
            evidence(external['model_identity']['evidence'])
        for row in external['reference_fields']:
            evidence(row['evidence'])
        selector = external.get('schema')
        if selector is None:
            validation = {'mode': 'bounded-probe', 'unmeasured': ['schema-unavailable']}
        else:
            document = c.decode(file(selector['path'], selector['sha256']))
            schema = rc.get(document, selector['pointer']) if selector['pointer'] else document
            if isinstance(schema, str):
                schema = c.decode(schema.encode('utf-8'))
            if not isinstance(schema, dict):
                raise ValueError('external schema selector must resolve to an acquired JSON Schema')
            metadata = {}
            for row in external['reference_fields']:
                path = row['field']
                if type(path[-1]) is int and all(isinstance(part, str) for part in path[:-1]):
                    key = '.'.join(path[:-1])
                    values = metadata.setdefault(key, [None] * len(rc.get(request, path[:-1])))
                    values[path[-1]] = image_metadata[row['reference']]
                elif all(isinstance(part, str) for part in path):
                    metadata['.'.join(path)] = [image_metadata[row['reference']]]
            from model_schema_numeric import validate_against_schema, unsupported_schema_keywords
            errors = validate_against_schema(request, schema, media=metadata)
            if errors:
                raise ValueError('external request violates acquired schema: ' + '; '.join(errors))
            validation = {'mode': 'target-schema',
                          'unmeasured': unsupported_schema_keywords(schema, value=request, media=metadata)}
        external.update(sha256=c.digest(raw), request=request, schema_validation=validation)
    result.update(artifact_type='image-input-binding', plan_sha256=c.content_id(plan), status='prepared-not-generated')
    result['binding_sha256'] = c.content_id(result)
    validate_binding(result)
    return result


def validate_binding(binding: Any) -> None:
    """Validate an immutable input snapshot without consulting mutable sources."""
    if not isinstance(binding, dict) or binding.get('artifact_type') != 'image-input-binding':
        raise ValueError('image input binding required')
    c.sha(binding.get('binding_sha256'))
    if c.content_id({key: value for key, value in binding.items() if key != 'binding_sha256'}) != binding['binding_sha256']:
        raise ValueError('image input binding integrity mismatch')
    c.sha(binding.get('plan_sha256'))
    if binding.get('status') != 'prepared-not-generated':
        raise ValueError('an image input binding records preparation, not generation success')
    plan = {key: copy.deepcopy(value) for key, value in binding.items() if key not in DERIVED}
    plan['artifact_type'] = 'image-input-plan'
    external = plan.get('external_request')
    request = external.pop('request', None) if external is not None else None
    validation = external.pop('schema_validation', None) if external is not None else None
    _structure(plan)
    for row in plan['references']:
        c.sha(row.get('sha256'))
    if plan.get('prepared_references') is not None:
        c.sha(binding.get('prepared_references_sha256'))
        _reference_rows(binding, binding['prepared_reference_set'])
    elif 'prepared_reference_set' in binding or 'prepared_references_sha256' in binding:
        raise ValueError('prepared source evidence requires its declared input file')
    if external is not None:
        c.sha(external.get('sha256'))
        _request(binding, external, request)
        c.exact(validation, {'mode', 'unmeasured'}, 'external schema validation')
        if validation['mode'] != ('target-schema' if external.get('schema') else 'bounded-probe'):
            raise ValueError('external schema validation mode differs from its evidence')
        if not isinstance(validation['unmeasured'], list) or any(not isinstance(x, str) or not x for x in validation['unmeasured']):
            raise ValueError('external schema limitations must be explicit strings')


def task_binding(root: Path, task: dict, add) -> dict | None:
    path = task.get('image_input')
    if path is None:
        return None
    result = validate(c.decode(add(root, path)), root, read=lambda name: add(root, name))
    external = result['external_request']
    if task['execution'] == 'external':
        if external is None:
            raise ValueError('external image input requires its exact request binding')
        prompt = add(root, task['delivery']['path']).decode('utf-8')
        _request(result, external, external['request'], prompt=prompt)
    elif external is not None:
        raise ValueError('dispatcher image input uses its compiled request, not an external request')
    return result


def external_documents(root: Path, task: dict, add, *, inputs: dict | None = None) -> dict:
    """Apply the same authored specification and render intent checks externally.

    Source roles select contracts explicitly. Tasks without these documents or
    subject assignments remain ordinary external work; no empty plan is needed.
    """
    if task['execution'] != 'external' or task['artifact'] != 'image':
        return {}
    import production_spec
    from render_contract_lib import validate_intent
    from reference_delivery import validate_reference_subjects, validate_reference_selection_subjects
    prompt = add(root, task['delivery']['path']).decode('utf-8')
    selected = {row['path']: row['role'] for row in task['sources']
                if row['disposition'] == 'applied' and row['role'] in {'production-spec', 'render-intent'}}
    if (task.get('generation') or {}).get('production_spec'):
        selected[task['generation']['production_spec']] = 'production-spec'
    graph_path = (task.get('generation') or {}).get('state_graphs')
    graphs = c.decode(add(root, graph_path)) if graph_path is not None else None
    specs, intents = [], []
    for path, role in selected.items():
        value = c.decode(add(root, path))
        if role == 'production-spec':
            production_spec.require(value)
            validate_intent(value['render_intent'], prompt=prompt)
            if inputs is not None:
                model = inputs['model']
                if value['target_model'] not in {model['requested'], model['catalog_model'], model['target']['model_identifier']}:
                    raise ValueError('external Production Specification target differs from the selected model')
                validate_reference_subjects(inputs['references'], value)
            prepared = inputs.get('prepared_reference_set') if inputs is not None else None
            validate_reference_selection_subjects(prepared['reference_selection'] if prepared is not None else None, value)
            if graphs is not None or value['state_context']['mode'] == 'state-aware':
                from state_protocol import validate_subject_state_graphs
                validate_subject_state_graphs(graphs if graphs is not None else [], production_spec=value,
                    reference_selection=prepared['reference_selection'] if prepared is not None else None)
            specs.append(value)
        else:
            validate_intent(value, prompt=prompt)
            intents.append(value)
    if specs and any(value != specs[0] for value in specs[1:]):
        raise ValueError('external image task has conflicting applied Production Specifications')
    if intents and any(value != intents[0] for value in intents[1:]):
        raise ValueError('external image task has conflicting applied render intents')
    if specs and any(value != specs[0]['render_intent'] for value in intents):
        raise ValueError('external render intent differs from the applied Production Specification')
    if inputs is not None and any(row.get('subject_uses') for row in inputs['references']) and not specs:
        raise ValueError('subject-assigned external references require an applied Production Specification')
    if graphs is not None and not specs:
        raise ValueError('external state graphs require their Production Specification')
    return {'production_specifications': specs, 'render_intents': intents}


def require_live(root: Path, task: dict, binding: dict) -> None:
    import production_store
    current = task_binding(root, task, lambda base, path: production_store.stable_bytes(base, path))
    if current != binding:
        raise ValueError('image inputs differ from the prepared binding')


def require_external_authority(binding: dict, grant: dict) -> None:
    from production_diagnostics import ProductionError
    validate_binding(binding)
    external = binding['external_request']
    if external is None:
        raise ValueError('external submission requires its request binding')
    mode = external['schema_validation']['mode']
    if mode not in grant['submission_validation_modes']:
        raise ProductionError('GRANT_SCOPE_EXCEEDED',
            'The external request validation mode is outside this grant.', phase='authorization',
            grant=grant['id'], expected=grant['submission_validation_modes'], actual=mode,
            required_action='Use a grant covering this mode, based on the principal\'s actual authorization.')
    if grant['request_scope'] is not None:
        raise ProductionError('GRANT_SCOPE_EXCEEDED',
            'A dispatcher request scope cannot authorize an external request.', phase='authorization',
            grant=grant['id'],
            required_action='Use exact-operation authority with request_scope null, based on the principal\'s actual authorization.')


def require_prepared(binding: dict, prepared: dict, *, model_id: str, target: dict) -> None:
    validate_binding(binding)
    if 'image_input_binding' in prepared and prepared['image_input_binding'] != binding:
        raise ValueError('prepared image input binding differs from the production task plan')
    if binding['model']['target'] != target or binding['model']['catalog_model'] != model_id:
        raise ValueError('image input model differs from the compiled target')
    if binding['model']['catalog_status'] != 'defined':
        raise ValueError('a missing model uses a recorded external trial until its profile is defined')
    _reference_rows(binding, prepared)
    if binding.get('prepared_reference_set') is not None:
        from reference_delivery import prepared_origin_projection
        if prepared_origin_projection(binding['prepared_reference_set']) != prepared_origin_projection(prepared):
            raise ValueError('declared prepared reference set differs from the dispatcher input')


def request_context(binding: dict) -> dict:
    validate_binding(binding)
    refs = [{**{key: copy.deepcopy(row[key]) for key in ('id', 'role', 'sha256', 'use_for', 'do_not_transfer')},
             'subject_uses': copy.deepcopy(row.get('subject_uses', []))} for row in binding['references']]
    if binding.get('prepared_reference_set') is not None:
        for row, selected in zip(refs, binding['prepared_reference_set']['selected_references']):
            row['source'] = copy.deepcopy(selected['source'])
            if 'subject_id' in selected:
                row['subject_id'] = selected['subject_id']
    return {'binding_sha256': binding['binding_sha256'], 'model': copy.deepcopy(binding['model']['target']),
            'references': refs}


def submission_evidence(binding: dict | None, selector: dict | None, read) -> dict:
    """Compare an actual recorded host call, never infer sending from saved input.

    Evidence remains an actor-attested host record; matching proves the recorded
    arguments, not visual influence, provider execution or output acceptance.
    """
    if selector is None:
        return {'status': 'not-provided'}
    if binding is None or binding.get('external_request') is None:
        raise ValueError('submission comparison requires a prepared external request')
    raw = read(selector['path'])
    if c.digest(raw) != selector['sha256']:
        raise ValueError('external submission evidence checksum mismatch')
    if selector['path'] == binding['external_request']['file'] or selector['sha256'] == binding['external_request']['sha256']:
        raise ValueError('the prepared request is not evidence of an actual host call')
    document = c.decode(raw)
    request = rc.get(document, selector['request_pointer']) if selector['request_pointer'] else document
    external = binding['external_request']
    if c.content_id(request) != c.content_id(external['request']):
        raise ValueError('recorded external call differs from the prepared request')
    identity = external.get('model_identity')
    pointer = selector['model_identity_pointer']
    if identity is not None:
        if pointer is None or rc.get(document, pointer) != identity['value']:
            raise ValueError('recorded external endpoint or tool differs from the selected model identity')
    elif pointer is not None:
        raise ValueError('request-field model identity does not declare an endpoint or tool selector')
    return {'status': 'matched-recorded-call', 'submission_sha256': selector['sha256'],
            'image_input_sha256': binding['binding_sha256'], 'request_sha256': external['sha256']}
