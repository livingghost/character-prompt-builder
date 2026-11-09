"""Own one editable target and derive its production representations.

The author selects a model, offering or evidenced external interface. This
module acquires that selection once and projects identifiers and knowledge to
the existing builders. It supplies no reading receipt, artistic assessment,
upload evidence or authorization.
"""
from __future__ import annotations

import copy
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import execution_contract as c


AUTHORED_FIELDS = frozenset({'execution_mode', 'parameters', 'syntax', 'vocabulary_record'})
COMMON_FIELDS = frozenset({'assessment'})
CATALOG_FIELDS = frozenset({'kind', 'model', 'service', 'operation'}) | AUTHORED_FIELDS | COMMON_FIELDS
ACQUIRED_FIELDS = frozenset({'kind', 'model_file', 'service'}) | AUTHORED_FIELDS | COMMON_FIELDS
EXTERNAL_FIELDS = frozenset({'kind', 'model', 'reference_model'}) | COMMON_FIELDS


@dataclass(frozen=True)
class AcquiredTarget:
    """A supplied model definition or external interface, without a dispatcher."""

    model_id: str
    model: dict
    offering: dict | None = None
    service: dict | None = None
    transport: Any = None
    parameter_schema: dict | None = None
    model_space: str | None = None
    transport_sha256: str | None = None
    external_model: dict | None = None


def _specifications(authored: dict) -> list[dict]:
    """Select specification owners by their declared role, never a source ID."""
    result = []
    value = authored.get('documents', {}).get('production_spec')
    if isinstance(value, dict) and not set(value) <= {'file', 'field'}:
        result.append(value)
    for source in authored.get('task', {}).get('sources', []):
        if source.get('role') != 'production-spec' or source.get('identity'):
            continue
        item = authored.get('sources', {}).get(source['id'])
        if isinstance(item, dict) and item.get('format') == 'json' and isinstance(item.get('content'), dict):
            result.append(item['content'])
    return result


def _reference_choices(authored: dict, external: dict | None):
    value = authored.get('references')
    if isinstance(value, dict):
        yield value
    value = (external or {}).get('reference_delivery')
    if isinstance(value, dict) and isinstance(value.get('choices'), dict):
        yield value['choices']


def extract(task: dict, authored: dict, external: dict | None) -> dict | None:
    """Export the selection from a compiled task and remove editable duplicates.

    The caller passes independent editing copies. Original run sources and
    public artifacts keep their complete target declarations.
    """
    owned_task = authored.get('task', {})
    execution = owned_task.get('execution', task.get('execution'))
    route = owned_task.get('route', task.get('route'))
    specifications = _specifications(authored)
    generation = authored.get('generation', {})
    selected = None
    if execution == 'authored':
        old = (owned_task.get('authored') or {}).pop('target', None)
        if old is None:
            old = (task.get('authored') or {}).get('target')
        if old is not None:
            selected = {'kind': 'acquired' if old.get('model_file') is not None else 'catalog',
                        'service': old.get('service')}
            field = 'model_file' if selected['kind'] == 'acquired' else 'model'
            selected[field] = old.get(field)
            selected.update({key: copy.deepcopy(old[key]) for key in AUTHORED_FIELDS if key in old})
    elif execution == 'external':
        plan = (external or {}).get('image_input')
        model = plan.pop('model', None) if isinstance(plan, dict) else None
        if model is not None:
            if model.get('catalog_status') == 'defined':
                selected = {'kind': 'catalog', 'model': model.get('catalog_model'),
                            'service': model['target']['service'], 'operation': model['target']['operation']}
            else:
                selected = {'kind': 'external', 'model': {key: copy.deepcopy(value)
                    for key, value in model.items() if key not in {'catalog_status', 'catalog_model'}}}
        reference = (external or {}).get('reference_delivery')
        if isinstance(reference, dict):
            preparation = reference.pop('target_model', None)
            if selected is not None and selected['kind'] == 'external' and preparation is not None:
                selected['reference_model'] = preparation
    elif execution == 'dispatcher':
        if route == 'upscale':
            upscale = authored.get('upscale') or {}
            model = upscale.pop('model', None)
            service = (owned_task.get('upscale') or task.get('upscale') or {}).get('service')
        else:
            model = generation.get('model')
            specified = [value.get('target_model') for value in specifications if value.get('target_model') is not None]
            if model is None and specified:
                model = specified[0]
            if model is not None and any(value != model for value in specified):
                raise ValueError('compiled specification targets disagree with the selected model')
            service = generation.get('service') or (task.get('generation') or {}).get('service')
        selected = {'kind': 'catalog', 'model': model, 'service': service}
    for value in (generation, task.get('generation'), owned_task.get('generation')):
        if isinstance(value, dict):
            value.pop('model', None)
            value.pop('service', None)
    for value in (task.get('upscale'), owned_task.get('upscale')):
        if isinstance(value, dict):
            value.pop('service', None)
    for value in (task.get('authored'), owned_task.get('authored')):
        if isinstance(value, dict):
            value.pop('target', None)
    for specification in specifications:
        specification.pop('target_model', None)
    for references in _reference_choices(authored, external):
        plan = references.get('image_input')
        if isinstance(plan, dict):
            plan.pop('model', None)
    return selected


def unresolved(selection: Any, task: dict) -> list[dict]:
    """Report missing target choices without selecting an offering or control."""
    result = []
    def missing(field, message):
        result.append({'field': field, 'code': 'target-selection-required', 'message': message})
    execution = task.get('execution')
    if selection is None:
        if execution != 'authored':
            missing('target', 'Select the model and actual service for this image request.')
        return result
    if not isinstance(selection, dict):
        raise ValueError('target must be an authored selection or null')
    kind = selection.get('kind')
    allowed = {'catalog': CATALOG_FIELDS, 'acquired': ACQUIRED_FIELDS, 'external': EXTERNAL_FIELDS}.get(kind)
    if allowed is None or set(selection) - allowed:
        raise ValueError('target requires one declared catalog, acquired or external selection')
    if kind == 'catalog':
        if not selection.get('model'):
            missing('target.model', 'Select one canonical catalog model.')
        if execution != 'authored' and not selection.get('service'):
            missing('target.service', 'Select the service whose offering will receive this request.')
        if execution == 'external' and not selection.get('operation'):
            missing('target.operation', 'Select the exact wire operation from the external interface evidence.')
    elif kind == 'acquired':
        if execution != 'authored':
            missing('target.kind', 'A supplied model definition is an authored-text target; select the actual image interface.')
        if not selection.get('model_file'):
            missing('target.model_file', 'Select the acquired model definition file.')
    else:
        if execution != 'external':
            missing('target.kind', 'An evidenced external interface requires external execution.')
        model = selection.get('model')
        if not isinstance(model, dict):
            missing('target.model', 'Supply the exact external model identity and its acquired evidence.')
        else:
            if set(model) - {'requested', 'target', 'evidence', 'prompt_input', 'prompt_dialect'}:
                raise ValueError('external target model contains derived or unknown fields')
            for field in ('requested', 'evidence', 'prompt_input'):
                if model.get(field) is None:
                    missing('target.model.' + field, 'Supply the selected external model ' + field + '.')
            target = model.get('target')
            if not isinstance(target, dict):
                missing('target.model.target', 'Supply the actual external service, model identifier and operation.')
            else:
                for field in ('service', 'model_identifier', 'operation'):
                    if not target.get(field):
                        missing('target.model.target.' + field, 'Select the actual external ' + field + '.')
    return result


def _runtime(source):
    if source is not None:
        return source
    from catalog_retrieval.runtime import load_pack_catalog, selected_pack_settings
    from runtime_snapshot import CompileRuntime
    return CompileRuntime.from_catalog(load_pack_catalog(), selected_pack_settings())


def _resolve(selection: dict, task: dict, root: Path, reader, source):
    from model_contract import select_offering
    from model_prompt_input import resolve_prompt_input
    kind = selection['kind']
    if kind == 'catalog':
        import build_generation_payload as builder
        source = _runtime(source)
        if task['execution'] == 'dispatcher':
            resolved = builder.resolve_target(selection['model'], selection['service'], source=source)
        elif task['execution'] == 'external' or selection.get('service') is not None:
            resolved = builder.resolve_package_target(selection['model'], selection.get('service'), source=source)
        else:
            model_id, record = builder._selected_model(selection['model'], source)
            resolved = AcquiredTarget(model_id, copy.deepcopy(record), model_space=source.model_space(model_id))
        return resolved, source
    if kind == 'acquired':
        record = reader.json(reader.select(selection['model_file']))
        c.text(record.get('id'), 'acquired model identity')
        resolve_prompt_input(record)
        offering = select_offering(record, selection['service']) if selection.get('service') is not None else None
        return AcquiredTarget(record['id'], record, offering), source
    model = copy.deepcopy(selection['model'])
    evidence = model['evidence']
    selected = reader.select(evidence['path'])
    if evidence.get('sha256') is not None and evidence['sha256'] != selected['sha256']:
        raise ValueError('selected external model evidence changed')
    model['evidence'] = {**selected, 'locator': c.text(evidence['locator'], 'external model evidence locator')}
    resolve_prompt_input(model)
    source = _runtime(source)
    from image_input import _model_contract
    with source.using():
        model.update(catalog_status='missing', catalog_model=None)
        record, offering = _model_contract(model)
    return AcquiredTarget(record['id'], record, offering, external_model=model), source


def _knowledge(resolved, selection: dict, source) -> dict:
    """Expose full acquired guidance; this is not a route delivery receipt."""
    import render_contract_lib
    from model_prompt_input import prompt_input_card
    record = resolved.model
    offerings = ([resolved.offering] if resolved.offering is not None else
                 list(record.get('offerings') or [None]))
    knowledge = {'model': resolved.model_id, 'model_record': copy.deepcopy(record),
                 'offering': copy.deepcopy(resolved.offering),
                 'parameter_schema': copy.deepcopy(resolved.parameter_schema),
                 'model_cards': [render_contract_lib.model_card(record, offering) for offering in offerings],
                 **prompt_input_card(record), 'resources': {}, 'assessment': None}
    if source is not None:
        from route_reading import _family
        for name in ('prompt-dialects', 'prompt-writing-guide'):
            selected = source.read_resource(name)
            if selected is not None:
                origin, raw = selected
                knowledge['resources'][name] = {'source': origin,
                    'content': c.decode(_family(name, c.decode(raw), record.get('prompt_dialect')))}
    assessment = selection.get('assessment')
    if assessment is not None:
        import model_suitability
        c.exact(assessment, {'use_cases', 'mode', 'reference_count'} |
                ({'operation'} if 'operation' in assessment else set()), 'target assessment conditions')
        knowledge['assessment'] = [model_suitability.assess(record, offering, **assessment)
                                   for offering in offerings]
    return knowledge


def _external_model(selection: dict, resolved, out_dir: str, files: dict) -> dict:
    if selection['kind'] == 'external':
        value = copy.deepcopy(resolved.external_model)
        value.update(catalog_status='defined' if resolved.offering is not None else 'missing',
                     catalog_model=resolved.model_id if resolved.offering is not None else None)
        return value
    offering = resolved.offering
    if offering is None:
        raise ValueError('an image target needs one selected offering')
    from model_prompt_input import resolve_prompt_input
    raw = c.encoded(resolved.model)
    files['target/model.json'] = raw
    operation = selection.get('operation')
    if resolved.transport is not None:
        operation = resolved.transport.OPERATIONS[resolved.model.get('operation_kind', 'generation')]
    if not operation:
        raise ValueError('the external wire operation remains unselected')
    value = {'requested': resolved.model_id, 'catalog_status': 'defined', 'catalog_model': resolved.model_id,
        'target': {'service': offering['service'], 'model_identifier': offering['model_identifier'], 'operation': operation},
        'evidence': {'path': (Path(out_dir) / 'target/model.json').as_posix(),
                     'sha256': c.digest(raw), 'locator': 'The selected canonical model record.'},
        'prompt_input': copy.deepcopy(resolve_prompt_input(resolved.model))}
    if resolved.model.get('prompt_dialect') is not None:
        value['prompt_dialect'] = resolved.model['prompt_dialect']
    return value


def project(choices: dict, task: dict, root: Path, reader, out_dir: str, source=None) -> dict:
    """Project one current target into copied builder inputs and exact local files.

    Returned files use paths relative to ``out_dir``. The caller makes these
    bytes available to downstream reference builders through its staging owner.
    Generic source content, decisions, prompt bytes and permissions are kept.
    """
    choices, task = copy.deepcopy(choices), copy.deepcopy(task)
    result = {'task': task, 'choices': choices, 'files': {}, 'unresolved': [],
              'resolved_target': None, 'knowledge': None}
    external = choices.get('external')
    if task.get('execution') == 'external' and isinstance((external or {}).get('image_input'), str):
        from production_external_inputs import read_selection
        try:
            external, _ = read_selection(external, reader, root)
            choices['external'] = external
            prior = extract(copy.deepcopy(task), {'task': copy.deepcopy(task)}, external)
            if choices.get('target') is None:
                choices['target'] = prior
            elif choices['target'].get('kind') == 'external' and prior and prior.get('reference_model') is not None:
                choices['target'].setdefault('reference_model', prior['reference_model'])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result['unresolved'].append({'field': 'external.image_input',
                'code': 'selection-evidence-required', 'message': str(exc)})
            return result
    selected = choices.get('target')
    result['unresolved'] = unresolved(selected, task)
    if selected is None and task.get('execution') == 'authored':
        owned_task = (choices.get('authoring') or {}).get('task') or {}
        for declaration in (task.get('authored'), owned_task.get('authored')):
            if isinstance(declaration, dict):
                declaration.pop('target', None)
    if result['unresolved'] or selected is None:
        return result
    try:
        acquisition = selected
        if selected['kind'] == 'external':
            evidence = selected['model'].get('evidence')
            pins = (external or {}).get('source_files') or {}
            if isinstance(evidence, dict) and evidence.get('sha256') is None and evidence.get('path') in pins:
                acquisition = copy.deepcopy(selected)
                acquisition['model']['evidence']['sha256'] = pins[evidence['path']]
        resolved, source = _resolve(acquisition, task, root, reader, source)
        with source.using() if source is not None else nullcontext():
            result['knowledge'] = _knowledge(resolved, selected, source)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result['unresolved'].append({'field': 'target', 'code': 'target-evidence-required', 'message': str(exc)})
        return result
    result['resolved_target'] = resolved
    authored = choices.get('authoring')
    if authored is not None and not isinstance(authored, dict):
        raise ValueError('editable authoring content must be an object')
    has_authoring = authored is not None
    authored = authored if has_authoring else {}
    execution, route = task['execution'], task['route']
    owned_task = authored.setdefault('task', {})
    if execution == 'authored':
        field = 'model_file' if selected['kind'] == 'acquired' else 'model'
        target = {field: selected[field] if field == 'model_file' else resolved.model_id,
                  **{key: copy.deepcopy(selected[key]) for key in AUTHORED_FIELDS if key in selected}}
        if selected.get('service') is not None:
            target['service'] = selected['service']
        task.setdefault('authored', {})['target'] = copy.deepcopy(target)
        owned_task.setdefault('authored', {})['target'] = target
    elif execution == 'dispatcher':
        if resolved.offering is None:
            result['unresolved'].append({'field': 'target.service', 'code': 'target-selection-required',
                'message': 'Select one available offering for this dispatcher request.'})
            return result
        if route == 'upscale':
            if has_authoring and not isinstance(authored.get('upscale'), dict):
                result['unresolved'].append({'field': 'authoring.upscale', 'code': 'authored-choice-required',
                    'message': 'Select the source image, scale and controls for this upscale.'})
                return result
            if has_authoring:
                authored['upscale']['model'] = resolved.model_id
            task.setdefault('upscale', {})['service'] = resolved.offering['service']
            owned_task.setdefault('upscale', {})['service'] = resolved.offering['service']
        else:
            for generation in (authored.setdefault('generation', {}), task.setdefault('generation', {})):
                generation.update(model=resolved.model_id, service=resolved.offering['service'])
    for specification in _specifications(authored):
        specification['target_model'] = resolved.model_id
    external = choices.get('external')
    needs_binding = execution == 'external' or any(isinstance(value.get('image_input'), dict)
        for value in _reference_choices(authored, external))
    if needs_binding:
        try:
            model = _external_model(selected, resolved, out_dir, result['files'])
        except (ValueError, KeyError) as exc:
            result['unresolved'].append({'field': 'target', 'code': 'target-evidence-required', 'message': str(exc)})
            return result
        for references in _reference_choices(authored, external):
            if isinstance(references.get('image_input'), dict):
                references['image_input']['model'] = copy.deepcopy(model)
        if execution == 'external':
            plan = (external or {}).get('image_input')
            if isinstance(plan, dict):
                plan['model'] = model
            else:
                result['unresolved'].append({'field': 'external.image_input', 'code': 'selection-required',
                    'message': 'Select the editable native request and reference inputs for this external target.'})
            delivery = (external or {}).get('reference_delivery')
            if isinstance(delivery, dict):
                delivery['target_model'] = (resolved.model_id if selected['kind'] == 'catalog'
                                            else selected.get('reference_model'))
                if delivery['target_model'] is None:
                    from production_reference_inputs import _authored_rows
                    if _authored_rows(delivery['choices']):
                        result['unresolved'].append({'field': 'target.reference_model',
                            'code': 'target-selection-required',
                            'message': 'Select the catalog model that prepares canonical references for this external interface.'})
    return result
