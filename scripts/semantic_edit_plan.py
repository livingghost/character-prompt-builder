#!/usr/bin/env python3
"""Bind an instruction edit, its exact model and every scoped reference.

python scripts/semantic_edit_plan.py PLAN.json --root STUDIO --out BINDING.json
Production tasks name PLAN.json as semantic_edit. Preparation reads the same
validator, and external claims recheck its pinned input bytes before handoff.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import execution_contract as c
import request_contract as rc

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'schemas/authoring/semantic-edit-plan.schema.json'
DERIVED = {'plan_sha256', 'binding_sha256', 'status'}


def _structure(plan: Any) -> None:
    from state_protocol import validate_against_schema
    errors = validate_against_schema(plan, c.load(SCHEMA))
    if errors:
        raise ValueError('semantic edit plan: ' + '; '.join(errors))
    model = plan['model']
    if (model['catalog_status'] == 'defined') != (model['catalog_model'] is not None):
        raise ValueError('defined models name their catalog record; missing models record null')
    ids = [row['id'] for row in plan['references']]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate reference id')
    selected = next((row for row in plan['references'] if row['id'] == plan['source']), None)
    if selected is None or selected['role'] != 'scene':
        raise ValueError('source must name a reference with the scene role')
    missing = set(plan['edit']['required_reference_roles']) - {row['role'] for row in plan['references']}
    if missing:
        raise ValueError('missing required reference roles: ' + ', '.join(sorted(missing)))
    for row in plan['references']:
        from reference_delivery import validate_authority_scope
        validate_authority_scope({'controls': row['use_for'], 'must_not_control': row['do_not_transfer']})
    external = plan['external_request']
    if external is not None:
        if [row['reference'] for row in external['reference_fields']] != ids:
            raise ValueError('external reference fields must cover every selected reference in order')
        paths = [external['model_field'], external['prompt_field']]
        paths += [external[key] for key in ('count_field', 'operation_field') if external[key] is not None]
        paths += [row['field'] for row in external['reference_fields']]
        for index, path in enumerate(paths):
            if any(rc.overlaps(path, other) for other in paths[:index]):
                raise ValueError('external request fields overlap')


def _request(plan: dict, external: dict, request: Any, *, prompt: str | None = None) -> None:
    if not isinstance(request, dict):
        raise ValueError('external request must be one JSON object')
    target = plan['model']['target']
    if rc.get(request, external['model_field']) != target['model_identifier']:
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
    for row in external['reference_fields']:
        if rc.get(request, row['field']) != row['value']:
            raise ValueError('external request reference is missing or changed: ' + row['reference'])
    arrays = {}
    for row in external['reference_fields']:
        path = row['field']
        if type(path[-1]) is int:
            arrays.setdefault(tuple(path[:-1]), []).append(path[-1])
    for path, indices in arrays.items():
        values = rc.get(request, list(path))
        if not isinstance(values, list) or sorted(indices) != list(range(len(values))):
            raise ValueError('external media array contains an undeclared or missing reference')


def validate(plan: dict, base: Path, *, read=None) -> dict:
    """Read each declared file and retain the source-to-request reference order.

    Paths are relative to the supplied Studio root. A caller can supply its
    snapshot reader so validation and publication use the same bytes.
    """
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
            raise ValueError('semantic edit file checksum mismatch: ' + path)
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
    external = result['external_request']
    if external is not None:
        raw = file(external['file'], external.get('sha256'))
        request = c.decode(raw)
        _request(result, external, request)
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
        external.update(sha256=c.digest(raw), request=request)
        external['schema_validation'] = validation
    result.update(artifact_type='semantic-edit-binding', plan_sha256=c.content_id(plan), status='prepared-not-generated')
    result['binding_sha256'] = c.content_id(result)
    validate_binding(result)
    return result


def validate_binding(binding: Any) -> None:
    """Check an immutable binding without requiring the original live files."""
    if not isinstance(binding, dict) or binding.get('artifact_type') != 'semantic-edit-binding':
        raise ValueError('semantic edit binding required')
    expected = binding.get('binding_sha256')
    c.sha(expected)
    if c.content_id({key: value for key, value in binding.items() if key != 'binding_sha256'}) != expected:
        raise ValueError('semantic edit binding integrity mismatch')
    c.sha(binding.get('plan_sha256'))
    if binding.get('status') != 'prepared-not-generated':
        raise ValueError('a semantic edit binding records preparation, not generation success')
    plan = {key: copy.deepcopy(value) for key, value in binding.items() if key not in DERIVED}
    plan['artifact_type'] = 'semantic-edit-plan'
    external = plan.get('external_request')
    request = external.pop('request', None) if external is not None else None
    validation = external.pop('schema_validation', None) if external is not None else None
    _structure(plan)
    for row in plan['references']:
        c.sha(row.get('sha256'))
    if external is not None:
        c.sha(external.get('sha256'))
        _request(plan, external, request)
        c.exact(validation, {'mode', 'unmeasured'}, 'external schema validation')
        if validation['mode'] != ('target-schema' if external.get('schema') else 'bounded-probe'):
            raise ValueError('external schema validation mode differs from its evidence')
        if not isinstance(validation['unmeasured'], list) or any(not isinstance(x, str) or not x for x in validation['unmeasured']):
            raise ValueError('external schema limitations must be explicit strings')


def task_binding(root: Path, task: dict, add) -> dict | None:
    """Resolve the task's edit through the ordinary production snapshot reader."""
    path = task.get('semantic_edit')
    if path is None:
        return None
    plan = c.decode(add(root, path))
    result = validate(plan, root, read=lambda name: add(root, name))
    source = next(row for row in result['references'] if row['id'] == result['source'])
    if not any(row['path'] == source['file'] and row['role'] == 'accepted-source'
               and row['disposition'] == 'applied' for row in task['sources']):
        raise ValueError('semantic edit source must be the applied accepted-source in the task')
    criteria = {row['id'] for row in task['criteria']}
    if not set(result['review_criteria']) <= criteria:
        raise ValueError('semantic edit names an undeclared production review criterion')
    external = result['external_request']
    if task['execution'] == 'external':
        if external is None:
            raise ValueError('external semantic editing requires its exact request binding')
        prompt = add(root, task['delivery']['path']).decode('utf-8')
        _request(result, external, external['request'], prompt=prompt)
    elif external is not None:
        raise ValueError('dispatcher semantic editing uses its compiled request, not an external request')
    return result


def require_live(root: Path, task: dict, binding: dict) -> None:
    """Recheck current pins at the external-send boundary, without sending."""
    import production_store
    current = task_binding(root, task, lambda base, path: production_store.stable_bytes(base, path))
    if current != binding:
        raise ValueError('semantic edit inputs differ from the prepared binding')


def require_external_authority(binding: dict, grant: dict) -> None:
    """Keep an external request within its exact grant and validation mode."""
    from production_diagnostics import ProductionError
    validate_binding(binding)
    external = binding['external_request']
    if external is None:
        raise ValueError('external semantic submission requires its request binding')
    mode = external['schema_validation']['mode']
    if mode not in grant['submission_validation_modes']:
        raise ProductionError('GRANT_SCOPE_EXCEEDED',
            'The external request validation mode is outside this grant.', phase='authorization',
            grant=grant['id'], expected=grant['submission_validation_modes'], actual=mode,
            required_action='Use a grant covering this mode, based on the principal\'s actual authorization.')
    if grant['request_scope'] is not None:
        raise ProductionError('GRANT_SCOPE_EXCEEDED',
            'A dispatcher request scope cannot authorize an external semantic request.', phase='authorization',
            grant=grant['id'],
            required_action='Use exact-operation authority with request_scope null, based on the principal\'s actual authorization.')


def require_prepared(binding: dict, prepared: dict, *, model_id: str, target: dict) -> None:
    """Reject an omitted, reordered or rescoped reference before dispatch."""
    validate_binding(binding)
    if 'semantic_edit_binding' in prepared and prepared['semantic_edit_binding'] != binding:
        raise ValueError('prepared semantic edit binding differs from the production task plan')
    if binding['model']['target'] != target or binding['model']['catalog_model'] != model_id:
        raise ValueError('semantic edit model differs from the compiled target')
    if binding['model']['catalog_status'] != 'defined':
        raise ValueError('a missing model uses a recorded external trial until its profile is defined')
    if prepared['transport_mode'] not in {'multi-image', 'single-board'}:
        raise ValueError('semantic editing requires model-facing references')
    selected = prepared['selected_references']
    if len(selected) != len(binding['references']):
        raise ValueError('semantic edit reference count differs from prepared delivery')
    for expected, actual in zip(binding['references'], selected):
        if actual['source']['sha256'] != expected['sha256'] or actual['role'] != expected['role']:
            raise ValueError('semantic edit reference bytes, role or order differ from prepared delivery')
        if actual['authority'] != {'controls': expected['use_for'], 'must_not_control': expected['do_not_transfer']}:
            raise ValueError('semantic edit reference authority differs from prepared delivery')


def request_context(binding: dict) -> dict:
    """Expose stable edit meaning and original media hashes in the request seal."""
    validate_binding(binding)
    return {'binding_sha256': binding['binding_sha256'], 'source': binding['source'],
            'edit': copy.deepcopy(binding['edit']), 'model': copy.deepcopy(binding['model']['target']),
            'references': [{key: copy.deepcopy(row[key]) for key in ('id', 'role', 'sha256', 'use_for', 'do_not_transfer')}
                           for row in binding['references']]}


def main() -> int:
    from production_binding import report_failure, new_output, write_new
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        source = args.plan if args.plan.is_absolute() else c.local(args.root, str(args.plan))
        output = new_output(args.root, args.out, option='--out')
        result = validate(c.load(source), args.root)
        write_new(output, c.encoded(result), option='--out', value=str(args.out))
        print(json.dumps({'ok': True, 'binding': str(output), 'binding_sha256': result['binding_sha256'],
                          'status': result['status']}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return report_failure(exc, phase='semantic-edit')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
