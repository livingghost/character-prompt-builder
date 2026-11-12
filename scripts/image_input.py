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
import prompt_weighting
from model_prompt_input import resolve_prompt_input

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/authoring/image-input-plan.schema.json'
DERIVED = {'plan_sha256', 'binding_sha256', 'status', 'prepared_reference_set',
           'prepared_references_sha256'}
PROMPT_CONSTRAINTS = ('max_positive_prompt_chars', 'max_negative_prompt_chars',
                      'supports_negative_prompt')


def _structure(plan: Any) -> None:
    from state_protocol import validate_against_schema
    errors = validate_against_schema(plan, c.load(SCHEMA))
    if errors:
        raise ValueError('image input plan: ' + '; '.join(errors))
    model = plan['model']
    contract = resolve_prompt_input(model)
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
    if contract['mode'] != 'tag-based' and 'vocabulary_record' in external:
        raise ValueError('a vocabulary record belongs to a tag-based external input')
    paths = [external[key] for key in ('model_field', 'prompt_field', 'negative_field', 'count_field', 'operation_field')
             if external.get(key) is not None]
    declaration = external.get('prompt_syntax')
    if declaration is not None:
        prompt_weighting.validate_declaration(declaration)
        if declaration['control'] is not None:
            paths.append(declaration['control']['field'])
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
                prepared_origin = plan.get('prepared_references') is not None
                if (path != other['field'] or row['value'] != other['value']
                        or row.get('local_file') != other.get('local_file') or not (same_bytes or prepared_origin)):
                    raise ValueError('external media fields overlap without identical bytes and value: '
                        f"reference {row['reference']!r} at {json.dumps(path, ensure_ascii=False)} conflicts with "
                        f"reference {other['reference']!r} at {json.dumps(other['field'], ensure_ascii=False)}")
        media.append(row)


def _reference_bindings(plan: dict, external: dict, *, prepared: dict | None = None) -> list[dict]:
    prepared = prepared if prepared is not None else plan.get('prepared_reference_set')
    if prepared is not None:
        from reference_delivery import bindings
        rows = bindings(prepared['transport_mode'], prepared['selected_references'], prepared['single_board'])
        for row, field in zip(rows, external['reference_fields'], strict=True):
            row['request_field'] = list(field['field'])
            row.setdefault('subject_uses', [])
        return rows
    rows = [
        {'reference_number': index, 'request_field': list(field['field']),
         'region_pixels': None, 'role': reference['role'],
         'controls': list(reference['use_for']),
         'must_not_control': list(reference['do_not_transfer']),
         'subject_uses': copy.deepcopy(reference.get('subject_uses', []))}
        for index, (reference, field) in enumerate(zip(plan['references'], external['reference_fields']), 1)
    ]
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
        prepared_path = c.local(base, plan['prepared_references'])
        prepared = validate_prepared_reference_set(
            c.decode(production_store.stable_bytes(base, plan['prepared_references'])),
            package_root=prepared_path.parent)
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


def _request(plan: dict, external: dict, request: Any, *, prompt: str | None = None,
             delivery_file: str | None = None) -> None:
    if not isinstance(request, (dict, list)):
        raise ValueError('external request must be one JSON object or array')
    target = plan['model']['target']
    if external['model_field'] is not None and rc.get(request, external['model_field']) != target['model_identifier']:
        raise ValueError('external request substitutes the selected model identifier')
    if external['operation_field'] is not None and rc.get(request, external['operation_field']) != target['operation']:
        raise ValueError('external request operation differs from the selected target')
    actual_prompt = rc.get(request, external['prompt_field'])
    c.text(actual_prompt, 'external instruction prompt')
    mode = resolve_prompt_input(plan['model'])['mode']
    if mode == 'unresolved':
        raise ValueError('resolve the external model prompt input before preparing its request')
    if mode == 'none':
        raise ValueError('the selected model has no instruction prompt surface')
    if external.get('negative_field') is not None:
        if not isinstance(rc.get(request, external['negative_field']), str):
            raise ValueError('external negative prompt must be text')
    if 'prompt_syntax' in external:
        prompt_weighting.selected(request, external['prompt_syntax'])
    if prompt is not None and actual_prompt != prompt:
        from production_diagnostics import ProductionError
        def newlines(value):
            pairs = value.count('\r\n')
            return {'crlf': pairs, 'lf': value.count('\n') - pairs, 'cr': value.count('\r') - pairs}
        def lf(value):
            return value.replace('\r\n', '\n').replace('\r', '\n')
        raise ProductionError('PROMPT_DELIVERY_MISMATCH',
            'external request prompt differs from the production delivery', phase='image-input',
            file=external['file'],
            pointer='$' + ''.join('[' + json.dumps(part, ensure_ascii=False) + ']' for part in external['prompt_field']),
            delivery_file=delivery_file, comparison='exact-utf8-text',
            request_newlines=newlines(actual_prompt), delivery_newlines=newlines(prompt),
            newline_only_difference=lf(actual_prompt) == lf(prompt),
            guidance={'document_path': 'references/runtime/production-external-inputs.md#exact-target-and-provider-schema',
                      'schema': 'schemas/authoring/image-input-plan.schema.json'},
            required_action='Use build-inputs to derive the request from the single delivery source. '
                            'Exact text includes every newline; write manual delivery bytes as UTF-8 with LF, '
                            'because Windows text-mode writes may introduce CRLF.')
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


def _model_contract(model: dict) -> tuple[dict, dict | None]:
    """Resolve catalog identities exactly; external evidence never overrides one."""
    from catalog_retrieval.runtime import load_pack_catalog
    from model_contract import select_offering
    from prepare_generation_references import resolve_model_record

    declared = resolve_prompt_input(model)
    target = model['target']
    if model['catalog_status'] == 'defined':
        model_id, record = resolve_model_record(model['catalog_model'])
        offering = select_offering(record, target['service'])
        if offering is None or offering['model_identifier'] != target['model_identifier']:
            raise ValueError('image input target differs from the selected catalog offering')
    else:
        matches = [(entry.record['id'], entry.record, offering)
                   for entry in load_pack_catalog().entries if entry.kind == 'model'
                   for offering in entry.record.get('offerings', [])
                   if offering['service'] == target['service']
                   and offering['model_identifier'] == target['model_identifier']]
        if not matches:
            return {'id': target['model_identifier'],
                    'prompt_input': copy.deepcopy(declared),
                    **({'prompt_dialect': model['prompt_dialect']}
                       if 'prompt_dialect' in model else {})}, None
        if len(matches) != 1:
            raise ValueError('the external target matches several catalog records; select its canonical model')
        model_id, record, offering = matches[0]
    if declared != resolve_prompt_input(record) or model.get('prompt_dialect') != record.get('prompt_dialect'):
        raise ValueError('image input prompt contract differs from the resolved catalog model')
    model.update(catalog_status='defined', catalog_model=model_id)
    return record, offering


def _offering_text_fields(external: dict, request: Any, offering: dict | None) -> None:
    """Use declared provider role paths, not guesses based on field wording."""
    if offering is None:
        return
    roles = offering.get('request_keys', {})
    prompts = [rc.path_parts(key) for key in roles.get('prompt', [])]
    if prompts and external['prompt_field'] not in prompts:
        raise ValueError('external prompt field differs from the selected offering')
    if 'negative_field' in external:
        negatives = [rc.path_parts(key) for key in roles.get('negative prompt', [])]
        selected = external['negative_field']
        if selected is not None and selected not in negatives:
            raise ValueError('external negative field differs from the selected offering')
        if any(rc.present(request, path) and path != selected for path in negatives):
            raise ValueError('external request contains an unbound negative prompt field')


def _require_prompt_findings(report: dict) -> None:
    findings = report.get('findings')
    if not isinstance(findings, list) or any(not isinstance(row, dict) for row in findings):
        raise ValueError('external prompt check requires its recorded findings')
    problems = [row.get('message', row.get('check', 'unspecified prompt problem'))
                for row in findings if row.get('severity') == 'problem']
    if problems:
        raise ValueError('external prompt violates its declared target: ' + '; '.join(map(str, problems)))


def _inspect_prompt(prompt: str, negative: str, syntax: str, constraints: dict,
                    dialect: dict | None) -> dict:
    """Use the same grammar and declared limits for preparation and saved inputs."""
    from check_tag_prompt import inspect
    report = inspect(prompt, negative, None, constraints, dialect, syntax=syntax)
    _require_prompt_findings(report)
    return report


def _prompt_check(external: dict, request: Any, model_record: dict, file) -> dict:
    """Inspect actual external text; tag input also searches its vocabulary."""
    prompt = rc.get(request, external['prompt_field'])
    negative = rc.get(request, external['negative_field']) if external.get('negative_field') is not None else ''
    declaration = external.get('prompt_syntax', {'default': 'literal', 'control': None})
    grammar = prompt_weighting.selected(request, declaration)
    selection = None
    if resolve_prompt_input(model_record)['mode'] == 'tag-based':
        from prompt_vocabulary_selection import require_for_model
        from state_protocol import validate_against_schema
        selector = external['vocabulary_record']
        receipt = c.decode(file(selector['path'], selector['sha256']))
        errors = validate_against_schema(receipt, c.load(ROOT / 'schemas/prompt-retrieval-record.schema.json'))
        if errors:
            raise ValueError('external vocabulary record: ' + '; '.join(errors))
        selection = require_for_model(receipt, prompt=prompt, negative=negative,
                                      model_record=model_record, syntax=grammar)
    constraints = {key: copy.deepcopy(model_record[key]) for key in PROMPT_CONSTRAINTS
                   if key in model_record}
    inspection = _inspect_prompt(prompt, negative, grammar, constraints,
                                  selection['dialect_guidance'] if selection is not None else None)
    return {'state': 'vocabulary-checked' if selection is not None else 'syntax-checked',
            'model': model_record['id'], 'model_constraints': constraints,
            'vocabulary': selection, **inspection}


def _bound_prompt_check(plan: dict, external: dict, request: Any, report: Any) -> None:
    """Check a saved report against immutable inputs; live preparation re-searches."""
    from state_protocol import validate_against_schema
    model = plan['model']
    contract = resolve_prompt_input(model)
    tagged = contract['mode'] == 'tag-based'
    expected_state = 'vocabulary-checked' if tagged else 'syntax-checked'
    if not isinstance(report, dict) or report.get('state') != expected_state:
        raise ValueError('external binding requires its ' + ('vocabulary check' if tagged else 'prompt check'))
    _require_prompt_findings(report)
    selection = report.get('vocabulary')
    model_id = model['catalog_model'] if model['catalog_status'] == 'defined' else model['target']['model_identifier']
    if report.get('model') != model_id:
        raise ValueError('external prompt check differs from its bound model')
    prompt = rc.get(request, external['prompt_field'])
    negative = rc.get(request, external['negative_field']) if external.get('negative_field') is not None else ''
    declaration = external.get('prompt_syntax', {'default': 'literal', 'control': None})
    grammar = prompt_weighting.selected(request, declaration)
    if tagged:
        errors = validate_against_schema(selection, c.load(ROOT / 'schemas/prompt-vocabulary-selection.schema.json'))
        if errors:
            raise ValueError('external vocabulary check: ' + '; '.join(errors))
        context = selection['context']
        expected = {'model': model_id,
                    'prompt_input_sha256': c.digest(c.encoded(contract).rstrip(b'\n')),
                    'dialect': model['prompt_dialect'],
                    'prompt_sha256': c.digest(prompt.encode('utf-8')),
                    'negative_sha256': c.digest(negative.encode('utf-8')),
                    'syntax': grammar}
        if (any(context[key] != value for key, value in expected.items())
                or selection['vocabularies'] != contract['vocabularies']
                or selection['unresolved'] or any(row['choice'] is None for row in selection['entries'])):
            raise ValueError('external vocabulary check differs from its bound text, model or selections')
    elif selection is not None:
        raise ValueError('external vocabulary check requires tag-based input')
    constraints = report.get('model_constraints')
    if not isinstance(constraints, dict) or set(constraints) - set(PROMPT_CONSTRAINTS):
        raise ValueError('external prompt check requires its bound model constraints')
    for key, value in constraints.items():
        valid = value is None or (type(value) is bool if key == 'supports_negative_prompt'
                                  else type(value) is int and value >= 0)
        if not valid:
            raise ValueError('invalid bound prompt constraint: ' + key)
    checked = _inspect_prompt(prompt, negative, grammar, constraints,
                              selection['dialect_guidance'] if selection is not None else None)
    if any(report.get(key) != value for key, value in checked.items()):
        raise ValueError('external prompt check differs from inspection of its bound input')


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
    external = binding.get('external_request')
    if external is not None:
        carriers = {}
        for reference, field in zip(selected, external['reference_fields'], strict=True):
            carrier = prepared['single_board'] if prepared['transport_mode'] == 'single-board' else reference['transport']
            c.sha(carrier['sha256'])
            identity = (carrier['media_type'], carrier['sha256'])
            key = tuple(field['field'])
            if key in carriers and carriers[key] != identity:
                raise ValueError('external media fields overlap without identical prepared carriers')
            carriers[key] = identity


def _request_image_metadata(binding: dict, source_metadata: dict) -> dict:
    """Measure the exact delivered carriers for external request constraints."""
    prepared = binding.get('prepared_reference_set')
    if prepared is None:
        return source_metadata
    from prepare_generation_references import host_reference_transports
    from production_evidence import inspect
    from production_store import stable_bytes
    measured = {}
    for carrier in host_reference_transports(prepared):
        path = Path(carrier['resolved_path'])
        raw = stable_bytes(path.parent, path.name)
        if c.digest(raw) != carrier['sha256']:
            raise ValueError('prepared external reference carrier checksum mismatch: ' + str(path))
        measured[(carrier['media_type'], carrier['sha256'])] = {**inspect(raw, 'image'), 'size': len(raw)}
    result = {}
    for reference, selected in zip(binding['references'], prepared['selected_references'], strict=True):
        carrier = prepared['single_board'] if prepared['transport_mode'] == 'single-board' else selected['transport']
        result[reference['id']] = measured[(carrier['media_type'], carrier['sha256'])]
    return result


def _delivery_carriers(binding: dict) -> list[dict]:
    """Select actual delivered bytes, keeping source images distinct from boards."""
    prepared = binding.get('prepared_reference_set')
    if prepared is None:
        return [{'sha256': row['sha256'], 'resolved_path': row['file']} for row in binding['references']]
    if prepared['transport_mode'] == 'single-board':
        return [prepared['single_board'] for _ in binding['references']]
    return [row['transport'] for row in prepared['selected_references']]


def _schema_media_metadata(request: Any, external: dict, image_metadata: dict) -> dict:
    metadata = {}
    for row in external['reference_fields']:
        path = row['field']
        if type(path[-1]) is int and all(isinstance(part, str) for part in path[:-1]):
            key = '.'.join(path[:-1])
            values = metadata.setdefault(key, [None] * len(rc.get(request, path[:-1])))
            values[path[-1]] = image_metadata[row['reference']]
        elif all(isinstance(part, str) for part in path):
            metadata['.'.join(path)] = [image_metadata[row['reference']]]
    return metadata


def validate(plan: dict, base: Path, *, read=None) -> dict:
    """Read each input once and pin prepared provenance and exact request bytes.

    A supplied reader owns acquisition, including staged generated bytes. Every
    locator must still remain inside the declared base. Without a reader, each
    locator must name an existing ordinary file read by the evidence store.
    """
    _structure(plan)
    base = Path(base)
    result = copy.deepcopy(plan)
    cache = {}

    def file(path: str, expected: str | None = None) -> bytes:
        c.local(base, path, exists=read is None)
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
    model_record, offering = _model_contract(result['model'])
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
        from prepare_generation_references import resolve_prepared_reference_paths
        raw = file(result['prepared_references'])
        prepared_path = c.local(base, result['prepared_references'], exists=read is None)
        prepared = resolve_prepared_reference_paths(c.decode(raw), package_root=prepared_path.parent)
        _reference_rows(result, prepared)
        result['prepared_reference_set'] = prepared
        result['prepared_references_sha256'] = c.digest(raw)
    external = result['external_request']
    if external is not None:
        raw = file(external['file'], external.get('sha256'))
        request = c.decode(raw)
        _request(result, external, request)
        _offering_text_fields(external, request, offering)
        if external.get('model_identity') is not None:
            evidence(external['model_identity']['evidence'])
        from production_store import stable_bytes
        for row, carrier in zip(external['reference_fields'], _delivery_carriers(result), strict=True):
            if row.get('local_file') is True:
                selected = Path(row['value'])
                if selected.is_absolute():
                    try:
                        relative = selected.relative_to(base).as_posix()
                    except ValueError:
                        raw_media = stable_bytes(selected.parent, selected.name)
                    else:
                        raw_media = file(relative)
                else:
                    raw_media = file(row['value'])
                if c.digest(raw_media) != carrier['sha256']:
                    raise ValueError('external local file differs from its selected delivery carrier: ' + row['reference'])
            else:
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
            image_metadata = _request_image_metadata(result, image_metadata)
            metadata = _schema_media_metadata(request, external, image_metadata)
            from model_schema_numeric import validate_against_schema, unsupported_schema_keywords
            errors = validate_against_schema(request, schema, media=metadata)
            if errors:
                raise ValueError('external request violates acquired schema: ' + '; '.join(errors))
            validation = {'mode': 'target-schema',
                          'unmeasured': unsupported_schema_keywords(schema, value=request, media=metadata)}
        prompt_check = _prompt_check(external, request, model_record, file)
        external.update(sha256=c.digest(raw), request=request, schema_validation=validation,
                        prompt_check=prompt_check)
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
    prompt_check = external.pop('prompt_check', None) if external is not None else None
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
        _bound_prompt_check(binding, external, request, prompt_check)
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
        _request(result, external, external['request'], prompt=prompt, delivery_file=task['delivery']['path'])
    elif external is not None:
        raise ValueError('dispatcher image input uses its compiled request, not an external request')
    return result


def revision_scopes(before: Any, after: Any) -> dict | None:
    """Compare bound external inputs by their actual text and execution values.

    File locations and derived checks are owned representations of these values.
    Only validated, fully captured external inputs can account for those files;
    other input kinds leave dependency classification with the caller.
    """
    if not all(isinstance(value, dict) and value.get('external_request') is not None
               for value in (before, after)):
        return None
    try:
        validate_binding(before)
        validate_binding(after)
    except (KeyError, TypeError, ValueError):
        return None

    def projection(binding: dict) -> tuple[dict, dict, set[str]]:
        value = copy.deepcopy(binding)
        for key in DERIVED - {'prepared_reference_set'}:
            value.pop(key, None)
        paths: set[str] = set()

        def evidence(selector: dict | None) -> None:
            if selector is not None:
                paths.add(selector.pop('path'))

        evidence(value['model']['evidence'])
        # Image bytes and their use remain exact. A different media path also
        # remains an execution difference unless its delivery owner proves it.
        paths.update(row['file'] for row in value['references'])
        if value.get('prepared_references') is not None:
            paths.add(value['prepared_references'])
        external = value['external_request']
        paths.add(external.pop('file'))
        external.pop('sha256')
        evidence(external.get('schema'))
        identity = external.get('model_identity')
        if identity is not None:
            evidence(identity['evidence'])
        for row in external['reference_fields']:
            if 'evidence' in row:
                evidence(row['evidence'])
        vocabulary = external.pop('vocabulary_record', None)
        if vocabulary is not None:
            paths.add(vocabulary['path'])
        check = external.pop('prompt_check')
        external['prompt_constraints'] = check['model_constraints']
        # A validated vocabulary selection and grammar report describe these
        # exact words. Changing words necessarily changes their derived record.
        text: dict[str, str] = {}
        for role, field in (('prompt', 'prompt_field'), ('negative', 'negative_field')):
            path = external.get(field)
            if path is not None:
                text[role] = rc.get(external['request'], path)
                rc.put(external['request'], path, None)
        return value, text, paths

    old, old_text, old_paths = projection(before)
    new, new_text, new_paths = projection(after)
    scopes = []
    if old_text != new_text:
        scopes.append('delivery')
    if old != new:
        scopes.append('execution')
    return {'scopes': scopes, 'paths': sorted(old_paths | new_paths)}


def external_document_sources(task: dict) -> list[dict]:
    """Select document owners from declared roles, including independently checkable inputs."""
    if task.get('execution') != 'external' or task.get('artifact') != 'image':
        return []
    sources = task.get('sources')
    sources = sources if isinstance(sources, list) else []
    selected = {row['path']: row['role'] for row in sources
                if isinstance(row, dict) and isinstance(row.get('path'), str)
                and row.get('disposition') == 'applied' and row.get('role') in ('production-spec', 'render-intent')}
    generation = task.get('generation')
    if isinstance(generation, dict) and isinstance(generation.get('production_spec'), str):
        selected[generation['production_spec']] = 'production-spec'
    return [{'path': path, 'role': role} for path, role in selected.items()]


def validate_external_document(value: Any, role: str) -> None:
    """Validate one complete source without depending on the other sources or request."""
    if role == 'production-spec':
        from production_spec import require
        require(value)
    elif role == 'render-intent':
        from render_contract_lib import validate_intent
        validate_intent(value)
    else:
        raise ValueError('external document role must be production-spec or render-intent')


def external_documents(root: Path, task: dict, add, *, inputs: dict | None = None,
                       documents: list[dict] | None = None) -> dict:
    """Apply the same authored specification and render intent checks externally.

    Source roles select contracts explicitly. An external image request uses its
    exact input binding even when no image reference was selected.
    """
    if task['execution'] != 'external' or task['artifact'] != 'image':
        return {}
    from render_contract_lib import validate_intent
    from reference_delivery import validate_reference_subjects, validate_reference_selection_subjects
    prompt = add(root, task['delivery']['path']).decode('utf-8')
    selected = external_document_sources(task)
    if documents is None:
        documents = []
        for source in selected:
            value = c.decode(add(root, source['path']))
            validate_external_document(value, source['role'])
            validate_intent(value['render_intent'] if source['role'] == 'production-spec' else value,
                            prompt=prompt)
            documents.append({**source, 'value': value})
    elif [{'path': row['path'], 'role': row['role']} for row in documents] != selected:
        raise ValueError('validated external documents differ from the selected source owners')
    else:
        # The compiler already checked each document and its prompt projection.
        # Retain their exact captured bytes in this contract's source evidence.
        for source in selected:
            add(root, source['path'])
    graph_path = (task.get('generation') or {}).get('state_graphs')
    graphs = c.decode(add(root, graph_path)) if graph_path is not None else None
    specs, intents = [], []
    for document in documents:
        role, value = document['role'], document['value']
        if role == 'production-spec':
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
    chosen_intent = specs[0]['render_intent'] if specs else intents[0] if intents else None
    if (inputs is not None and chosen_intent is not None
            and inputs['model']['catalog_status'] == 'defined'):
        record, offering = _model_contract(copy.deepcopy(inputs['model']))
        if offering is not None and offering.get('execution_profile') is not None:
            from render_contract_lib import selected_profile
            profile = selected_profile(record, offering)
            mode = profile['modes'].get(chosen_intent['execution_mode'])
            if mode is None:
                raise ValueError('external render mode is not exposed by the selected offering')
            external = inputs['external_request']
            declared = external.get('prompt_syntax', {'default': 'literal', 'control': None})
            actual = prompt_weighting.selected(external['request'], declared)
            expected = prompt_weighting.selected(external['request'], mode['prompt_syntax'])
            if actual != expected:
                raise ValueError('external prompt grammar differs from the selected offering and render mode')
    return {'production_specifications': specs, 'render_intents': intents}


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


def external_delivery(binding: dict, *, run_directory: Path, read_object) -> dict:
    """Project an external call from saved bytes through explicitly typed media fields.

    Provider values remain opaque even when they look like local paths. Only a
    field declared ``local_file: true`` receives a path to its saved carrier.
    The saved authored request and binding remain the provenance of this call.
    """
    from production_evidence import inspect

    validate_binding(binding)
    external = binding['external_request']
    if external is None:
        raise ValueError('external delivery requires its prepared request binding')
    request = copy.deepcopy(external['request'])
    references, media, carriers = [], {}, _delivery_carriers(binding)
    metadata = {}

    def saved(key: str) -> tuple[str, bytes]:
        raw = read_object(key)
        if c.digest(raw) != key:
            raise ValueError('saved external media checksum mismatch')
        return str(run_directory / 'objects' / key), raw

    for reference, field, carrier in zip(binding['references'], external['reference_fields'], carriers, strict=True):
        source, _ = saved(reference['sha256'])
        references.append({**copy.deepcopy(reference), 'file': source})
        key = carrier['sha256']
        if key not in media:
            path, raw = saved(key)
            media[key] = {'path': path, 'sha256': key, 'size': len(raw),
                          'request_fields': [], 'media': inspect(raw, 'image')}
        item = media[key]
        if field['field'] not in item['request_fields']:
            item['request_fields'].append(list(field['field']))
        metadata[reference['id']] = {**item['media'], 'size': item['size']}
        if field.get('local_file') is True:
            rc.put(request, field['field'], item['path'])

    # Native constraints apply to the actual field values handed to the host.
    # Their captured evidence remains usable after authoring files change.
    selector = external.get('schema')
    if selector is not None and request != external['request']:
        _, raw_schema = saved(selector['sha256'])
        document = c.decode(raw_schema)
        schema = rc.get(document, selector['pointer']) if selector['pointer'] else document
        if isinstance(schema, str):
            schema = c.decode(schema.encode('utf-8'))
        from model_schema_numeric import validate_against_schema
        errors = validate_against_schema(request, schema,
            media=_schema_media_metadata(request, external, metadata))
        if errors:
            raise ValueError('saved external delivery violates acquired schema: ' + '; '.join(errors))
    identity = copy.deepcopy(external.get('model_identity'))
    if identity is not None:
        identity['evidence']['path'], _ = saved(identity['evidence']['sha256'])
    return {'target': copy.deepcopy(binding['model']['target']), 'request': request,
            'request_sha256': c.content_id(request), 'references': references, 'media': list(media.values()),
            'reference_bindings': _reference_bindings(binding, external), 'model_identity': identity}


def submission_evidence(binding: dict | None, selector: dict | None, read, *, expected_request: Any = None) -> dict:
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
    if isinstance(document, dict) and document.get('artifact_type') == 'external-execution-instruction':
        raise ValueError('a prepared host instruction is not evidence of an actual host call')
    request = rc.get(document, selector['request_pointer']) if selector['request_pointer'] else document
    external = binding['external_request']
    expected = external['request'] if expected_request is None else expected_request
    if c.content_id(request) != c.content_id(expected):
        raise ValueError('recorded external call differs from the prepared request')
    identity = external.get('model_identity')
    pointer = selector['model_identity_pointer']
    if identity is not None:
        if pointer is None or rc.get(document, pointer) != identity['value']:
            raise ValueError('recorded external endpoint or tool differs from the selected model identity')
    elif pointer is not None:
        raise ValueError('request-field model identity does not declare an endpoint or tool selector')
    return {'status': 'matched-recorded-call', 'submission_sha256': selector['sha256'],
            'image_input_sha256': binding['binding_sha256'], 'request_sha256': external['sha256'],
            'submitted_request_sha256': c.content_id(expected)}
