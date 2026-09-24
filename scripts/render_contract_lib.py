"""Resolve explicit rendering choices and model controls before request assembly.

Profiles describe a particular interface, not every member of a model family.
This module performs no inference, catalog search, network call or prompt writing.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
AXES = ('medium', 'dimensionality', 'linework', 'shading', 'surface', 'detail')
STATUSES = {'required', 'optional', 'not-applicable', 'backend-managed'}
BINDINGS = {'package', 'dispatch-seed', 'dispatch-count'}
MODES = {'text-to-image', 'image-to-image', 'reference-guided', 'instruction-edit', 'upscale'}
MEDIA = {'none', 'seed-image', 'references', 'input-image'}
KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$')


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip().lower() == 'unspecified':
        raise ValueError(where + ': choose a non-empty explicit value')
    return value


def exact(value: Any, keys: set[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(where + ': expected exactly ' + ', '.join(sorted(keys)))


def presets() -> dict[str, dict]:
    rows = json.loads((ROOT / 'config/render-presets.json').read_text(encoding='utf-8'))['presets']
    found = {row['id']: row for row in rows}
    if len(found) != len(rows):
        raise ValueError('render preset identifiers must be unique')
    for row in rows:
        exact(row, {'id', 'label', 'axes', 'guidance'}, 'render preset')
        exact(row['axes'], set(AXES), 'preset axes')
        for key, value in row['axes'].items():
            text(value, key)
    return found


def make_intent(preset: str, *, mode: str, chosen_by: str, reason: str,
                presentation: str, prompt_expression: str) -> dict:
    if preset not in presets():
        raise ValueError('unknown render preset: ' + preset)
    value = {'artifact_type': 'render-intent', 'preset': preset,
             'axes': copy.deepcopy(presets()[preset]['axes']),
             'presentation': presentation, 'selection': {'chosen_by': chosen_by, 'reason': reason},
             'execution_mode': mode, 'prompt_expression': prompt_expression, 'regional_overrides': []}
    validate_intent(value, for_generation=False)
    return value


def validate_intent(value: Any, *, for_generation: bool = True, prompt: str | None = None) -> None:
    exact(value, {'artifact_type', 'preset', 'axes', 'presentation', 'selection',
                  'execution_mode', 'prompt_expression', 'regional_overrides'}, 'render intent')
    if value['artifact_type'] != 'render-intent' or value['execution_mode'] not in MODES:
        raise ValueError('render intent: invalid artifact type or execution mode')
    if value['preset'] is not None:
        if value['preset'] not in presets():
            raise ValueError('unknown render preset: ' + str(value['preset']))
        if value['axes'] != presets()[value['preset']]['axes']:
            raise ValueError('preset axes differ; use a custom intent with preset=null for a distinct whole-image finish')
    exact(value['axes'], set(AXES), 'render axes')
    for key, item in value['axes'].items():
        text(item, 'render axis ' + key)
    text(value['presentation'], 'presentation')
    exact(value['selection'], {'chosen_by', 'reason'}, 'render selection')
    if value['selection']['chosen_by'] not in {'user', 'agent'}:
        raise ValueError('render selection must identify user or agent')
    text(value['selection']['reason'], 'render selection reason')
    if not isinstance(value['prompt_expression'], str):
        raise ValueError('render prompt expression must be text')
    if for_generation:
        expression = text(value['prompt_expression'], 'render prompt expression')
        if prompt is not None and expression not in prompt:
            raise ValueError('render prompt expression is absent from the authored prompt')
    if not isinstance(value['regional_overrides'], list):
        raise ValueError('regional overrides must be an array')
    regions = set()
    for row in value['regional_overrides']:
        exact(row, {'region', 'axes', 'reason', 'prompt_expression'}, 'regional render override')
        region = text(row['region'], 'render region')
        if region in regions:
            raise ValueError('render region repeats: ' + region)
        regions.add(region)
        text(row['reason'], 'regional rendering reason')
        if not isinstance(row['axes'], dict) or not row['axes'] or set(row['axes']) - set(AXES):
            raise ValueError('regional override must name known render axes')
        for key, item in row['axes'].items():
            text(item, key)
        expression = text(row['prompt_expression'], 'regional render prompt expression')
        if for_generation and prompt is not None and expression not in prompt:
            raise ValueError('regional render expression is absent from the authored prompt')


def _schema(value: Any, schema: dict, where: str) -> None:
    from state_protocol import validate_against_schema, find_non_finite_numbers
    if find_non_finite_numbers(value):
        raise ValueError(where + ': non-finite value')
    issues = validate_against_schema(value, schema)
    if issues:
        raise ValueError(where + ': ' + '; '.join(issues))


def _has_default(schema: Any) -> bool:
    """Inspect schema nodes, not example or const values that happen to name default."""
    if not isinstance(schema, dict):
        return False
    if 'default' in schema:
        return True
    for key in ('properties', 'patternProperties', '$defs', 'dependentSchemas'):
        if isinstance(schema.get(key), dict) and any(_has_default(v) for v in schema[key].values()):
            return True
    for key in ('items', 'additionalProperties', 'propertyNames', 'not', 'if', 'then', 'else', 'contains'):
        if _has_default(schema.get(key)):
            return True
    return any(_has_default(v) for key in ('allOf', 'anyOf', 'oneOf', 'prefixItems') for v in schema.get(key, []))


def _supported_schema(schema: dict, where: str) -> None:
    from state_protocol import unsupported_schema_keywords
    unsupported = unsupported_schema_keywords(schema)
    if unsupported:
        raise ValueError(where + ': unsupported schema constraints: ' + ', '.join(unsupported))
    if _has_default(schema):
        raise ValueError(where + ': schema defaults are not parameter decisions')


def validate_profile(profile: Any) -> None:
    exact(profile, {'id', 'basis', 'prompt_recipe', 'modes'}, 'execution profile')
    text(profile['id'], 'profile id')
    exact(profile['basis'], {'kind', 'source', 'limitations'}, 'profile basis')
    if profile['basis']['kind'] not in {'provider-documentation', 'curated-starting-point', 'measured', 'synthetic'}:
        raise ValueError('unknown profile evidence kind')
    text(profile['basis']['source'], 'profile evidence source')
    if not isinstance(profile['basis']['limitations'], list):
        raise ValueError('profile limitations must be an array')
    for item in profile['basis']['limitations']:
        text(item, 'profile limitation')
    recipe = profile['prompt_recipe']
    exact(recipe, {'order', 'guidance'}, 'prompt recipe')
    if not isinstance(recipe['order'], list) or not recipe['order'] or len(set(recipe['order'])) != len(recipe['order']):
        raise ValueError('prompt recipe needs a non-empty unique slot order')
    if 'rendering' not in recipe['order']:
        raise ValueError('prompt recipe must have a rendering slot')
    for item in recipe['order']:
        text(item, 'recipe slot')
    if not isinstance(recipe['guidance'], list) or not recipe['guidance']:
        raise ValueError('prompt recipe needs authored guidance')
    for item in recipe['guidance']:
        text(item, 'prompt guidance')
    if not isinstance(profile['modes'], dict) or not profile['modes']:
        raise ValueError('execution profile needs modes')
    for name, mode in profile['modes'].items():
        if name not in MODES:
            raise ValueError('unsupported execution mode: ' + name)
        exact(mode, {'media', 'controls', 'parameter_schema'}, 'execution mode ' + name)
        if not isinstance(mode['parameter_schema'], dict):
            raise ValueError('mode parameter_schema must be an object')
        _supported_schema(mode['parameter_schema'], 'mode ' + name)
        if mode['media'] not in MEDIA:
            raise ValueError('invalid media semantics for ' + name)
        if name == 'text-to-image' and mode['media'] != 'none':
            raise ValueError('text-to-image must not consume reference media')
        if name in {'image-to-image', 'instruction-edit', 'upscale'} and mode['media'] == 'none':
            raise ValueError(name + ' needs source media')
        if name == 'image-to-image' and mode['media'] not in {'seed-image', 'input-image'}:
            raise ValueError('image-to-image requires one source-image transport, not style references')
        if name == 'upscale' and mode['media'] != 'input-image':
            raise ValueError('upscale requires an input-image transport')
        if name == 'reference-guided' and mode['media'] != 'references':
            raise ValueError('reference-guided mode needs references, not an img2img seed')
        controls = mode['controls']
        if not isinstance(controls, dict):
            raise ValueError('mode controls must be an object')
        special = set()
        for key, rule in controls.items():
            if not KEY.fullmatch(key):
                raise ValueError('invalid request control path: ' + key)
            exact(rule, {'status', 'binding', 'schema', 'recommendation', 'reason'}, 'control ' + key)
            if rule['status'] not in STATUSES or rule['binding'] not in BINDINGS:
                raise ValueError('invalid control status or binding: ' + key)
            text(rule['reason'], key + ' reason')
            if rule['status'] in {'required', 'optional'}:
                if not isinstance(rule['schema'], dict) or not rule['schema']:
                    raise ValueError(key + ': exposed controls need a value schema')
                _supported_schema(rule['schema'], key)
            elif rule['schema'] is not None or rule['recommendation'] is not None:
                raise ValueError(key + ': unavailable controls have no schema or recommendation')
            if rule['recommendation'] is not None:
                text(rule['recommendation'], key + ' recommendation name')
                if rule['binding'] != 'package':
                    raise ValueError(key + ': dispatch values are explicit, not model recommendations')
            if rule['binding'] != 'package':
                if rule['binding'] in special:
                    raise ValueError('dispatch binding repeats: ' + rule['binding'])
                special.add(rule['binding'])
        if special != {'dispatch-seed', 'dispatch-count'}:
            raise ValueError('each mode must declare a seed and count disposition')
        for key in controls:
            if any(other.startswith(key + '.') for other in controls):
                raise ValueError('control paths overlap: ' + key)


def selected_profile(record: Mapping, offering: Mapping | None) -> dict:
    """The offering owns its interface; a host-only record owns its host profile."""
    owner = offering if offering is not None else record
    profile = owner.get('execution_profile')
    if profile is None:
        raise ValueError('execution profile is missing for this exact interface; author it before generation')
    validate_profile(profile)
    return copy.deepcopy(profile)


def model_card(record: Mapping, offering: Mapping | None = None) -> dict:
    owner = offering if offering is not None else record
    profile = owner.get('execution_profile')
    if profile is not None:
        validate_profile(profile)
    return {'model': record.get('id'), 'service': (offering or {}).get('service'),
            'model_identifier': (offering or {}).get('model_identifier', record.get('id')),
            'ready_for_parameter_resolution': profile is not None,
            'execution_profile': copy.deepcopy(profile),
            'recommended_parameters': copy.deepcopy(record.get('recommended_parameters') or {}),
            'recommended_positive_prompt': record.get('recommended_positive_prompt', ''),
            'recommended_negative_prompt': record.get('recommended_negative_prompt', ''),
            'recommendation_merge_mode': record.get('recommendation_merge_mode', 'advisory-only'),
            'size_choices': copy.deepcopy(record.get('size_hints') or {}),
            'note': 'Recommendations are starting points. Interface validity and observed image quality are separate evidence.'}


def _get(tree: dict, path: str) -> tuple[bool, Any]:
    node = tree
    for part in path.split('.'):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _put(tree: dict, path: str, value: Any) -> None:
    node = tree
    parts = path.split('.')
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ValueError('parameter envelope conflict: ' + path)
    node[parts[-1]] = copy.deepcopy(value)


def _paths(tree: dict, controls: dict, prefix: str = '') -> set[str]:
    found = set()
    for key, value in tree.items():
        if not isinstance(key, str) or '.' in key:
            raise ValueError('use nested JSON objects, not dotted parameter keys')
        path = prefix + key
        if path in controls:
            found.add(path)
        elif isinstance(value, dict) and value:
            found.update(_paths(value, controls, path + '.'))
        else:
            found.add(path)
    return found


def resolve_parameters(record: Mapping, profile: dict, mode: str, parameters: dict) -> tuple[dict, list[dict]]:
    validate_profile(profile)
    if mode not in profile['modes']:
        raise ValueError('mode not exposed by this execution profile: ' + mode)
    if not isinstance(parameters, dict):
        raise ValueError('parameters must be an object')
    encoded(parameters)
    controls = profile['modes'][mode]['controls']
    unknown = _paths(parameters, controls) - set(controls)
    if unknown:
        raise ValueError('undeclared parameters for ' + mode + ': ' + ', '.join(sorted(unknown)))
    result, decisions = {}, []
    recommendations = record.get('recommended_parameters') or {}
    for key, rule in sorted(controls.items()):
        present, value = _get(parameters, key)
        status = rule['status']
        if rule['binding'] != 'package':
            if present:
                raise ValueError(key + ': supply this through the explicit dispatcher option')
            source = 'dispatch-required' if status in {'required', 'optional'} else status
            decisions.append({'key': key, 'status': source, 'value': None, 'reason': rule['reason']})
            continue
        if status in {'not-applicable', 'backend-managed'}:
            if present:
                raise ValueError(key + ': ' + status + ' in mode ' + mode)
            decisions.append({'key': key, 'status': status, 'value': None, 'reason': rule['reason']})
            continue
        source = 'explicit'
        if not present:
            if status == 'optional':
                decisions.append({'key': key, 'status': 'not-selected', 'value': None, 'reason': rule['reason']})
                continue
            name = rule['recommendation']
            if name is None or name not in recommendations:
                raise ValueError(key + ': required explicit value has no recommendation')
            value = recommendations[name]
            if isinstance(value, list):
                raise ValueError(key + ': recommendation is a range; choose one explicit value')
            source = 'model-recommendation'
        _schema(value, rule['schema'], key)
        _put(result, key, value)
        decisions.append({'key': key, 'status': source, 'value': copy.deepcopy(value), 'reason': rule['reason']})
    _schema(result, profile['modes'][mode]['parameter_schema'], 'combined mode parameters')
    return result, decisions


def media_check(profile: dict, mode: str, *, reference_count: int, offering: Mapping | None) -> None:
    if type(reference_count) is not int or reference_count < 0:
        raise ValueError('reference count must be a nonnegative integer')
    media = profile['modes'][mode]['media']
    if media == 'none' and reference_count:
        raise ValueError('text-only mode cannot carry reference media; select its actual transport mode')
    if media != 'none' and reference_count < 1:
        raise ValueError(mode + ' requires source/reference media')
    if media in {'seed-image', 'input-image'} and reference_count != 1:
        raise ValueError(mode + ' takes one image, not a reference collection')
    if offering is not None:
        role = {'seed-image': 'seed image', 'references': 'reference images', 'input-image': 'input image'}.get(media)
        if role and role not in offering.get('request_keys', {}):
            raise ValueError('offering has no transport for declared media role: ' + role)


def compile_contract(record: Mapping, offering: Mapping | None, intent: dict,
                     parameters: dict, *, prompt: str, reference_count: int) -> dict:
    preserve_without_text = intent.get('execution_mode') == 'upscale' and not prompt
    validate_intent(intent, for_generation=not preserve_without_text, prompt=prompt)
    if preserve_without_text and intent['prompt_expression']:
        raise ValueError('an upscaler without a text channel cannot receive a rendering prompt expression')
    profile = selected_profile(record, offering)
    mode = intent['execution_mode']
    effective, decisions = resolve_parameters(record, profile, mode, parameters)
    media_check(profile, mode, reference_count=reference_count, offering=offering)
    card = model_card(record, offering)
    return {'artifact_type': 'render-contract', 'intent': copy.deepcopy(intent), 'model_card': card,
            'profile_sha256': digest(card), 'authored_parameters': copy.deepcopy(parameters),
            'parameters': effective, 'parameter_decisions': decisions, 'reference_count': reference_count,
            'prompt_expression': intent['prompt_expression']}


def verify_contract(value: Any, *, intent: dict, parameters: dict, prompt: str,
                    record: Mapping | None = None, offering: Mapping | None = None,
                    reference_count: int) -> None:
    exact(value, {'artifact_type', 'intent', 'model_card', 'profile_sha256', 'authored_parameters',
                  'parameters', 'parameter_decisions', 'reference_count', 'prompt_expression'}, 'render contract')
    if value['artifact_type'] != 'render-contract' or encoded(value['intent']) != encoded(intent) or encoded(value['parameters']) != encoded(parameters):
        raise ValueError('render contract differs from the generation specification')
    card = value['model_card']
    if digest(card) != value['profile_sha256']:
        raise ValueError('render profile hash mismatch')
    snapshot = {'id': card['model'], 'execution_profile': card['execution_profile'],
                'recommended_parameters': card['recommended_parameters'],
                'recommended_positive_prompt': card['recommended_positive_prompt'],
                'recommended_negative_prompt': card['recommended_negative_prompt'],
                'recommendation_merge_mode': card['recommendation_merge_mode'], 'size_hints': card['size_choices']}
    expected = compile_contract(snapshot, None, intent, value['authored_parameters'],
                                prompt=prompt, reference_count=reference_count)
    for key in ('parameter_decisions', 'parameters', 'reference_count', 'prompt_expression'):
        if encoded(expected[key]) != encoded(value[key]):
            raise ValueError('render contract has inconsistent ' + key)
    if record is not None and encoded(model_card(record, offering)) != encoded(card):
        raise ValueError('active model/interface guidance differs from the selected render contract')


def dispatch_values(contract: dict, *, seed: int | None, count: int) -> tuple[int | None, int]:
    """Resolve transport controls without silently using a provider's seed policy."""
    profile = contract['model_card']['execution_profile']
    rules = profile['modes'][contract['intent']['execution_mode']]['controls']
    for key, rule in rules.items():
        binding = rule['binding']
        if binding == 'package':
            continue
        value = seed if binding == 'dispatch-seed' else count
        if rule['status'] in {'backend-managed', 'not-applicable'}:
            if binding == 'dispatch-seed' and value is not None:
                raise ValueError(key + ': seed is ' + rule['status'])
            if binding == 'dispatch-count' and (type(value) is not int or value != 1):
                raise ValueError(key + ': unavailable count accepts only one operation, not an invented batch')
            continue
        if value is None:
            raise ValueError(key + ': choose an explicit seed with --seed before preview or submission')
        _schema(value, rule['schema'], key)
    return seed, count


def check_wire(contract: dict, request: dict, layout: dict | None = None, *,
               seed: int | None, count: int) -> list[dict]:
    """Check exact package and dispatch decisions against the final wire values."""
    dispatch_values(contract, seed=seed, count=count)
    profile = contract['model_card']['execution_profile']
    rules = profile['modes'][contract['intent']['execution_mode']]['controls']
    decisions = []
    if layout is not None:
        for field in layout['fields']:
            if field['kind'] != 'parameter':
                continue
            path = '.'.join(str(part) for part in field['field'])
            exists, value = _get(request, path)
            leaves = {path} if path in rules else (_paths(value, rules, path + '.') if isinstance(value, dict) else {path})
            if not exists or leaves - set(rules):
                raise ValueError('wire request added an undeclared control: ' + path)
    for key, rule in rules.items():
        present, value = _get(request, key)
        if rule['status'] in {'not-applicable', 'backend-managed'}:
            if present:
                raise ValueError('wire request supplied unavailable control: ' + key)
        elif rule['status'] == 'required' and not present:
            raise ValueError('wire request omitted required control: ' + key)
        if present:
            _schema(value, rule['schema'], key)
        if present and rule['binding'] != 'package':
            chosen_dispatch = seed if rule['binding'] == 'dispatch-seed' else count
            if encoded(value) != encoded(chosen_dispatch):
                raise ValueError('wire dispatch value differs from the explicit choice: ' + key)
        if rule['binding'] == 'package':
            expected, chosen = _get(contract['parameters'], key)
            if present != expected or (present and encoded(value) != encoded(chosen)):
                raise ValueError('wire parameter differs from explicit render decision: ' + key)
        decisions.append({'key': key, 'status': rule['status'], 'value': value if present else None,
                          'sent': present, 'reason': rule['reason']})
    return decisions


def summary(contract: dict) -> str:
    axes = contract['intent']['axes']
    lines = ['Render contract', '  model: ' + str(contract['model_card']['model']),
             '  service: ' + str(contract['model_card']['service']),
             '  mode: ' + contract['intent']['execution_mode']]
    lines += ['  ' + key + ': ' + axes[key] for key in AXES]
    lines.append('  choice: ' + contract['intent']['selection']['chosen_by'] + ' - ' + contract['intent']['selection']['reason'])
    for row in contract['parameter_decisions']:
        lines.append('  ' + row['key'] + ': ' + (json.dumps(row['value']) if row['status'] in {'explicit', 'model-recommendation'} else row['status']) + ' [' + row['status'] + ']')
    return '\n'.join(lines)
