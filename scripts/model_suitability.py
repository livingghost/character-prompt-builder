"""Combine exact model evidence with the author's scoped selection preferences.

The catalog owns model and offering facts. The author owns preferences in
their configuration home or active content pack. These helpers inspect both
without generating images, inferring content categories from prompts, or
changing provider controls.
"""
from __future__ import annotations

import copy
import fnmatch
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import execution_contract as c

OPERATIONS = {'generation', 'instruction-edit', 'upscale'}
GUIDANCE = {'discourage', 'consider', 'unknown'}
BASIS_KINDS = {'provider-statement', 'user-report', 'observed-outcome', 'author-preference', 'synthetic'}
FAILURES = {'provider-moderation', 'provider-refusal', 'authentication', 'quota', 'rate-limit',
            'timeout', 'transport', 'request-schema', 'reference-input', 'output-artifact', 'unknown'}
PREFERENCES_FILE = 'model-selection-preferences.json'
PREFERENCES_RESOURCE = 'model-selection-preferences'


def _strings(value: Any, where: str, *, empty: bool = False) -> None:
    if not isinstance(value, list) or (not empty and not value):
        raise ValueError(where + ': a non-empty array is required')
    for item in value:
        c.text(item, where)
    if len(set(value)) != len(value):
        raise ValueError(where + ': duplicate values')


def validate_basis(value: Any) -> None:
    c.exact(value, {'kind', 'source', 'observed_at', 'limitations'}, 'use-case evidence basis')
    if value['kind'] not in BASIS_KINDS:
        raise ValueError('unknown use-case evidence kind')
    c.text(value['source'], 'use-case evidence source')
    if not isinstance(value['observed_at'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['observed_at']):
        raise ValueError('use-case evidence date must be YYYY-MM-DD')
    try:
        date.fromisoformat(value['observed_at'])
    except (TypeError, ValueError):
        raise ValueError('use-case evidence date must be YYYY-MM-DD') from None
    _strings(value['limitations'], 'use-case evidence limitations')


def validate_guidance(value: Any) -> None:
    """Validate scoped guidance stored on an exact catalog offering."""
    if not isinstance(value, list):
        raise ValueError('use_case_guidance must be an array')
    seen = set()
    for item in value:
        c.exact(item, {'id', 'operation', 'use_case', 'recommendation', 'reason', 'basis'}, 'use-case guidance')
        c.text(item['id'], 'use-case guidance id')
        if item['id'] in seen:
            raise ValueError('use-case guidance id repeats: ' + item['id'])
        seen.add(item['id'])
        if item['operation'] not in OPERATIONS or item['recommendation'] not in GUIDANCE:
            raise ValueError('unknown use-case operation or recommendation')
        c.text(item['use_case'], 'use case')
        c.text(item['reason'], 'use-case guidance reason')
        validate_basis(item['basis'])


def validate_preferences(value: Any) -> None:
    c.exact(value, {'artifact_type', 'entries'}, 'model selection preferences')
    if value['artifact_type'] != 'model-selection-preferences' or not isinstance(value['entries'], list):
        raise ValueError('invalid model selection preferences')
    seen = set()
    for item in value['entries']:
        c.exact(item, {'id', 'selector', 'preference', 'reported_failure', 'reason', 'basis'}, 'model selection preference')
        c.text(item['id'], 'preference id')
        if item['id'] in seen:
            raise ValueError('preference id repeats: ' + item['id'])
        seen.add(item['id'])
        if item['preference'] not in {'discourage', 'no-discouragement'}:
            raise ValueError('unknown model selection preference')
        c.text(item['reason'], 'preference reason')
        validate_basis(item['basis'])
        if item['basis']['kind'] not in {'user-report', 'author-preference', 'synthetic'}:
            raise ValueError('user preferences retain user-report or author-preference provenance')
        if item['reported_failure'] not in (None, 'provider-moderation', 'provider-refusal'):
            raise ValueError('unknown reported provider failure')
        if item['reported_failure'] is not None and item['basis']['kind'] != 'user-report':
            raise ValueError('a reported provider failure requires user-report provenance')
        selector = item['selector']
        c.exact(selector, {'family', 'model_patterns', 'service', 'operations', 'use_cases'}, 'preference selector')
        c.text(selector['family'], 'descriptive model family')
        if selector['service'] is not None:
            c.text(selector['service'], 'preference service')
        _strings(selector['operations'], 'preference operations')
        if set(selector['operations']) - OPERATIONS:
            raise ValueError('unknown preference operation')
        _strings(selector['use_cases'], 'preference use cases')
        patterns = selector['model_patterns']
        if not isinstance(patterns, list) or not patterns:
            raise ValueError('preference needs explicit model patterns')
        unique = set()
        for pattern in patterns:
            c.exact(pattern, {'field', 'pattern'}, 'model pattern')
            if pattern['field'] not in {'model-id', 'model-identifier'}:
                raise ValueError('model pattern must select a model id or exact-interface identifier')
            text = c.text(pattern['pattern'], 'model pattern')
            if not any(char.isalnum() for char in text):
                raise ValueError('model pattern must name a model or family')
            key = (pattern['field'], text)
            if key in unique:
                raise ValueError('model pattern repeats')
            unique.add(key)


def preferences_path() -> Path:
    from pack_manager import user_data_home
    return user_data_home() / PREFERENCES_FILE


def load_preferences() -> tuple[dict, dict | None]:
    """Read the complete home override, then one active pack's named resource."""
    path = preferences_path()
    resource = None
    if not path.exists():
        from catalog_retrieval.runtime import load_pack_catalog, selected_pack_settings
        from pack_cache import resource_warning
        # Explicit pack state owns activation. A preference read cannot turn
        # discovered directories into an initial selection.
        if not selected_pack_settings().state_file.is_file():
            return {'artifact_type': PREFERENCES_RESOURCE, 'entries': []}, None
        catalog = load_pack_catalog()
        problem = resource_warning(catalog, PREFERENCES_RESOURCE)
        if problem:
            raise ValueError(problem)
        resource = catalog.resources.get(PREFERENCES_RESOURCE)
        if resource is None:
            return {'artifact_type': PREFERENCES_RESOURCE, 'entries': []}, None
        if resource.source_pack not in catalog.pack_roots:
            raise ValueError('model selection preferences come from a pack without an active root: '
                             + resource.source_pack)
        path = c.local(Path(catalog.pack_roots[resource.source_pack]), resource.relative_path)
    raw = path.read_bytes()
    value = c.decode(raw)
    validate_preferences(value)
    witness = {'path': str(path), 'sha256': c.digest(raw)}
    if resource is not None:
        witness.update(source_pack=resource.source_pack, relative_path=resource.relative_path)
    return value, witness


def install_preferences(value: Any) -> dict:
    """Replace the author's complete preferences atomically after validation."""
    validate_preferences(value)
    path = preferences_path()
    raw = c.encoded(value)
    with c.lock(path.parent):
        c.atomic(path, raw, replace=True)
    return {'path': str(path), 'sha256': c.digest(raw), 'entries': len(value['entries'])}


def _matches(selector: dict, record: Mapping, offering: Mapping | None, operation: str) -> bool:
    target = offering or {}
    if selector['service'] is not None and selector['service'] != target.get('service'):
        return False
    if operation not in selector['operations']:
        return False
    fields = {'model-id': record.get('id'), 'model-identifier': target.get('model_identifier')}
    return any(isinstance(fields[item['field']], str)
               and fnmatch.fnmatchcase(fields[item['field']], item['pattern'])
               for item in selector['model_patterns'])


def guidance_card(record: Mapping, offering: Mapping | None, *, operation: str | None = None,
                  preferences: dict | None = None, witness: dict | None = None) -> dict:
    operation = operation or record.get('operation_kind', 'generation')
    if operation not in OPERATIONS:
        raise ValueError('unknown use-case assessment operation')
    guidance = copy.deepcopy((offering or {}).get('use_case_guidance', []))
    validate_guidance(guidance)
    guidance = [item for item in guidance if item['operation'] == operation]
    if preferences is None:
        preferences, witness = load_preferences()
    else:
        validate_preferences(preferences)
    matched = [copy.deepcopy(item) for item in preferences['entries']
               if _matches(item['selector'], record, offering, operation)]
    return {'operation': operation, 'offering_guidance': guidance,
            'author_preferences': matched, 'preferences_source': witness}


def assess(record: Mapping, offering: Mapping | None, *, use_cases: list[str], mode: str,
           reference_count: int, operation: str | None = None,
           preferences: dict | None = None, witness: dict | None = None) -> dict:
    """Compare declared use cases and input conditions; the agent evaluates meaning."""
    from model_contract import model_reference_limit
    from render_contract_lib import MODES, media_check, validate_profile
    _strings(use_cases, 'assessment use cases')
    if mode not in MODES or type(reference_count) is not int or reference_count < 0:
        raise ValueError('assessment needs a known mode and nonnegative reference count')
    operation = operation or record.get('operation_kind', 'generation')
    if (mode == 'upscale') != (operation == 'upscale'):
        raise ValueError('upscale operation and mode must agree')
    card = guidance_card(record, offering, operation=operation, preferences=preferences, witness=witness)
    rows = []
    for use_case in use_cases:
        facts = [item for item in card['offering_guidance'] if item['use_case'] == use_case]
        choices = [item for item in card['author_preferences'] if use_case in item['selector']['use_cases']]
        preference = ('discourage' if any(item['preference'] == 'discourage' for item in choices)
                      else 'no-discouragement' if choices else 'none')
        recommendation = ('discourage' if preference == 'discourage'
                          or any(item['recommendation'] == 'discourage' for item in facts)
                          else 'consider' if any(item['recommendation'] == 'consider' for item in facts)
                          else 'unknown')
        rows.append({'use_case': use_case, 'recommendation': recommendation,
                     'author_preference': preference, 'offering_guidance': facts, 'author_preferences': choices})
    profile = (offering or record).get('execution_profile')
    inputs = {'status': 'unknown', 'mode': mode, 'reference_count': reference_count,
              'reference_limit': None, 'issues': []}
    if profile is not None:
        validate_profile(profile)
        selected = profile['modes'].get(mode)
        if selected is None:
            inputs['status'] = 'unsupported'
            inputs['issues'].append('The selected interface does not expose this execution mode.')
        else:
            media = selected['media']
            limits = (offering or {}).get('constraints', {}).get('reference_images')
            maximum = (model_reference_limit(record) if offering is None
                       else limits.get('max') if isinstance(limits, Mapping) else None)
            if media in {'seed-image', 'input-image'}:
                maximum = 1
            if media == 'none':
                maximum = 0
            if type(maximum) is not int or maximum < 0:
                maximum = None
            inputs['reference_limit'] = maximum
            try:
                media_check(profile, mode, reference_count=reference_count, offering=offering)
            except ValueError as exc:
                inputs['issues'].append(str(exc))
            if maximum is not None and reference_count > maximum:
                inputs['issues'].append('The reference count exceeds the recorded interface limit.')
            inputs['status'] = ('unsupported' if inputs['issues'] else
                                'unknown' if media == 'references' and maximum is None else 'compatible')
    discouraged = any(item['recommendation'] == 'discourage' for item in rows)
    status = ('discouraged' if discouraged else 'incompatible-inputs' if inputs['status'] == 'unsupported'
              else 'candidate' if inputs['status'] == 'compatible' else 'needs-interface-evidence')
    return {'model': record.get('id'), 'service': (offering or {}).get('service'),
            'model_identifier': (offering or {}).get('model_identifier', record.get('id')),
            'operation': operation, 'use_cases': rows, 'input_compatibility': inputs,
            'selection_status': status, 'preferences_source': card['preferences_source'],
            'content_permission_assessed': False, 'visual_quality_assessed': False}


def validate_failure(value: Any) -> None:
    c.exact(value, {'artifact_type', 'target', 'use_cases', 'category', 'basis', 'evidence',
                    'signal', 'reason', 'unmeasured'}, 'generation failure assessment')
    if value['artifact_type'] != 'generation-failure-assessment' or value['category'] not in FAILURES:
        raise ValueError('unknown failure assessment type or category')
    c.exact(value['target'], {'service', 'model_identifier', 'operation'}, 'failure target')
    for name, item in value['target'].items():
        c.text(item, 'failure target ' + name)
    if value['target']['operation'] not in OPERATIONS:
        raise ValueError('unknown failure operation')
    _strings(value['use_cases'], 'failure use cases', empty=True)
    basis = value['basis']
    if basis not in {'provider-response', 'runtime-error', 'visual-review', 'operator-hypothesis'}:
        raise ValueError('unknown failure evidence basis')
    if value['category'] in {'provider-moderation', 'provider-refusal'} and basis != 'provider-response':
        raise ValueError('provider moderation or refusal requires provider-response evidence')
    if basis == 'operator-hypothesis' and value['category'] != 'unknown':
        raise ValueError('an operator hypothesis keeps the failure category unknown')
    if value['category'] == 'output-artifact' and basis != 'visual-review':
        raise ValueError('an output artifact diagnosis requires visual-review evidence')
    c.exact(value['evidence'], {'path', 'sha256'}, 'failure evidence')
    c.text(value['evidence']['path'], 'failure evidence path')
    c.sha(value['evidence']['sha256'])
    signal = value['signal']
    if signal is None:
        if basis == 'provider-response':
            raise ValueError('provider-response evidence needs an exact response signal')
    else:
        c.exact(signal, {'pointer', 'value'}, 'failure signal')
        if not isinstance(signal['pointer'], str) or (signal['pointer'] and not signal['pointer'].startswith('/')):
            raise ValueError('failure signal pointer must be a JSON Pointer')
    c.text(value['reason'], 'failure assessment reason')
    _strings(value['unmeasured'], 'failure unmeasured scopes')


def _pointer(value: Any, pointer: str) -> Any:
    for part in pointer.split('/')[1:] if pointer else []:
        if re.search(r'~(?![01])', part):
            raise ValueError('invalid JSON Pointer escape')
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ValueError('invalid JSON Pointer array index')
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError('failure signal pointer does not resolve')
    return value


def diagnose(value: Any, root: Path, *, record: Mapping | None = None) -> dict:
    """Verify the recorded signal, preserving operational and policy distinctions."""
    from input_evidence import InputEvidence
    validate_failure(value)
    reader = InputEvidence(root)
    selected = reader.select(value['evidence']['path'])
    if selected['sha256'] != value['evidence']['sha256']:
        raise ValueError('failure evidence changed')
    if value['signal'] is not None:
        try:
            observed = _pointer(reader.json(selected), value['signal']['pointer'])
        except (KeyError, IndexError):
            raise ValueError('failure signal pointer does not resolve') from None
        if c.encoded(observed) != c.encoded(value['signal']['value']):
            raise ValueError('failure signal differs from the saved evidence')
    target, category = value['target'], value['category']
    offered = target
    if record is not None:
        from model_contract import select_offering
        offered = select_offering(record, target['service'])
        if offered is None or offered.get('model_identifier') != target['model_identifier']:
            raise ValueError('failure catalog model does not match the saved service and model identifier')
    card = guidance_card(record or {}, offered, operation=target['operation'])
    matches = [item for item in card['author_preferences']
               if set(item['selector']['use_cases']) & set(value['use_cases'])
               and item['preference'] == 'discourage'
               and item['reported_failure'] is not None
               and item['basis']['kind'] == 'user-report']
    if category == 'provider-moderation':
        relevance, action = 'explicit-provider-moderation', 'Review the recorded reason and applicable policy. '
        action += 'For a permitted request, assess suitable alternatives against the same scene and reference requirements.'
    elif category == 'provider-refusal':
        relevance, action = 'refusal-reason-needs-review', 'Inspect the provider reason before assigning a policy cause; '
        action += 'then assess permitted alternatives when model suitability caused the refusal.'
    elif category == 'unknown':
        relevance = 'possible-from-author-report' if matches else 'unestablished'
        action = 'Inspect the saved response and execution evidence before assigning a cause.'
        if matches:
            action += ' Matching author reports make provider restrictions one possible explanation, not a confirmed diagnosis.'
            action += ' For a permitted request, assess alternatives against the same scene and reference requirements.'
    elif category == 'output-artifact':
        relevance, action = 'unestablished', 'Review the visible identity, anatomy, wardrobe, composition or output defect and its source.'
    else:
        relevance, action = 'unestablished', 'Resolve the recorded ' + category + ' failure through the existing execution recovery path.'
    return {'target': copy.deepcopy(target), 'category': category, 'basis': value['basis'],
            'catalog_model': record.get('id') if record is not None else None,
            'evidence': selected, 'signal': copy.deepcopy(value['signal']), 'reason': value['reason'],
            'policy_relevance': relevance, 'matching_author_reports': matches if category == 'unknown' else [],
            'preferences_source': card['preferences_source'],
            'next_action': action, 'unmeasured': copy.deepcopy(value['unmeasured']),
            'automatic_retry': False}
