"""Compile and recheck a saved prompt against its selected text-input contract.

An authored artifact can be portable text or name a catalog/evidenced target.
The existing syntax and vocabulary owners inspect exact primary and negative
surfaces. Saving a draft does not claim that these final checks succeeded.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import execution_contract as c
from model_prompt_input import resolve_prompt_input
from production_diagnostics import ProductionError

ROOT = Path(__file__).resolve().parents[1]


def paths(task: dict) -> list[str]:
    """Files the selected authored contract consumes in addition to delivery."""
    authored = task.get('authored') or {}
    target = authored.get('target') or {}
    negative = authored.get('negative') or {}
    return list(dict.fromkeys(value for value in (
        target.get('model_file'), target.get('vocabulary_record'), negative.get('path'))
        if isinstance(value, str) and value))


def _surface(raw: bytes, field: list | None, label: str) -> str:
    if field is None:
        value = raw.decode('utf-8')
    else:
        from request_contract import get
        value = get(c.decode(raw), field)
    if not isinstance(value, str):
        raise ValueError(label + ' must select a text string')
    return value


def surfaces(task: dict, read) -> tuple[str, str]:
    """Read the chosen text fields without rewriting whitespace or punctuation."""
    authored = task.get('authored') or {}
    raw = read(task['delivery']['path'])
    prompt = _surface(raw, authored.get('prompt_field'), 'authored primary text')
    negative = authored.get('negative')
    other = (_surface(read(negative['path']), negative.get('field'), 'authored negative text')
             if negative is not None else '')
    return prompt, other


def _selected_model(target: dict, read) -> dict:
    if target.get('model_file') is not None:
        record = c.decode(read(target['model_file']))
    else:
        from prepare_generation_references import resolve_model_record
        _, record = resolve_model_record(target['model'])
    c.text(record.get('id'), 'authored model identity')
    resolve_prompt_input(record)
    return record


def _syntax(target: dict, model: dict) -> str:
    """Resolve the selected interface grammar; an authored syntax asserts it."""
    from model_contract import select_offering
    from render_contract_lib import resolve_prompt_syntax, selected_profile

    offerings = ([select_offering(model, target['service'])] if target.get('service') is not None
                 else list(model.get('offerings') or [None]))
    parameters = target.get('parameters', {})
    if not isinstance(parameters, dict):
        raise ValueError('authored target parameters must be an object')
    syntaxes = set()
    for offering in offerings:
        owner = offering if offering is not None else model
        if owner.get('execution_profile') is None:
            if target.get('execution_mode') is not None or parameters:
                raise ValueError('authored execution mode and controls require the selected interface execution profile')
            syntaxes.add('literal')
            continue
        profile = selected_profile(model, offering)
        modes = ([target['execution_mode']] if target.get('execution_mode') is not None
                 else profile['modes'])
        syntaxes.update(resolve_prompt_syntax(model, profile, mode, parameters) for mode in modes)
    if len(syntaxes) != 1:
        raise ProductionError('PROMPT_SYNTAX_SELECTION_REQUIRED',
            'The applicable interfaces use different prompt grammars; select the service and execution_mode that own this text.',
            phase='authored-prompt', pointer='$.authored.target',
            required_action='Select the intended offering or mode, then check the authored text again.')
    syntax = next(iter(syntaxes))
    if 'syntax' in target and target['syntax'] != syntax:
        raise ProductionError('PROMPT_SYNTAX_MISMATCH',
            f"Authored syntax {target['syntax']!r} differs from the selected interface grammar {syntax!r}.",
            phase='authored-prompt', pointer='$.authored.target.syntax',
            required_action='Select the intended interface controls or correct the syntax assertion.')
    return syntax


def _inspect(prompt: str, negative: str, model: dict, syntax: str,
             selection: dict | None) -> dict:
    from check_tag_prompt import inspect
    report = inspect(prompt, negative, None, model,
                     selection['dialect_guidance'] if selection is not None else None,
                     syntax=syntax)
    problems = [row['message'] for row in report['findings'] if row['severity'] == 'problem']
    if problems:
        raise ProductionError('TAG_PROMPT_PROBLEM', '; '.join(problems), phase='authored-prompt',
            prompt_check=report, required_action='Correct the current authored text or its selected syntax.')
    return report


def _validate_artifact(task: dict, read) -> None:
    if task.get('artifact') == 'json':
        c.decode(read(task['delivery']['path']))


def check(task: dict, read) -> dict | None:
    """Check completed authored text with actual searches for every tag target."""
    _validate_artifact(task, read)
    target = (task.get('authored') or {}).get('target')
    if target is None:
        return None
    selected = _selected_model(target, read)
    import route_reading
    route_reading.require_model_reading(c.decode(read(task['route_reading'])),
        model_record=selected, service=target.get('service'),
        resource_reader=route_reading._live_resource_reader())
    model = copy.deepcopy(selected)
    contract = resolve_prompt_input(model)
    if contract['mode'] in {'unresolved', 'none'}:
        raise ValueError('a finished targeted prompt requires a resolved model text-input contract')
    prompt, negative = surfaces(task, read)
    c.text(prompt, 'authored primary text')
    syntax = _syntax(target, model)
    # Grammar uses the same owner before search and when rereading the saved
    # revision. Vocabulary decisions remain model-bound author decisions.
    _inspect(prompt, negative, model, syntax, None)
    selection = None
    if contract['mode'] == 'tag-based':
        from prompt_vocabulary_selection import require_for_model
        path = target.get('vocabulary_record')
        receipt = c.decode(read(path)) if path is not None else {}
        try:
            selection = require_for_model(receipt, prompt=prompt, negative=negative,
                                          model_record=model, syntax=syntax)
        except ValueError as exc:
            raise ProductionError('PROMPT_VOCABULARY_REQUIRED', str(exc), phase='authored-prompt',
                file=path, pointer='$.authored.target.vocabulary_record',
                required_action='Search this exact prompt and negative for the selected model; settle any authored wording.') from exc
    return {'model': model, 'target': copy.deepcopy(target),
            'prompt_sha256': c.digest(prompt.encode('utf-8')),
            'negative_sha256': c.digest(negative.encode('utf-8')),
            'vocabulary': selection, 'inspection': _inspect(prompt, negative, model, syntax, selection)}


def validate_bound(task: dict, bound: Any, read) -> None:
    """Validate recorded final checks against pinned text and model knowledge.

    Historical validation does not replace the active dictionary or model with
    newer definitions. The final authoring operation already performed search;
    this check verifies its saved binding and reuses the common grammar owner.
    """
    _validate_artifact(task, read)
    target = (task.get('authored') or {}).get('target')
    if target is None:
        if bound is not None:
            raise ValueError('a portable authored artifact has no targeted prompt check')
        return
    c.exact(bound, {'model', 'target', 'prompt_sha256', 'negative_sha256', 'vocabulary', 'inspection'},
            'saved authored prompt check')
    if bound['target'] != target:
        raise ValueError('saved authored prompt check differs from its target selection')
    model = bound['model']
    contract = resolve_prompt_input(model)
    if contract['mode'] in {'unresolved', 'none'}:
        raise ValueError('saved targeted prompt has no resolved text-input contract')
    if target.get('model_file') is not None and _selected_model(target, read) != model:
        raise ValueError('saved authored prompt model differs from its captured model file')
    prompt, negative = surfaces(task, read)
    syntax = _syntax(target, model)
    if (bound['prompt_sha256'] != c.digest(prompt.encode('utf-8'))
            or bound['negative_sha256'] != c.digest(negative.encode('utf-8'))):
        raise ValueError('saved authored prompt check differs from its exact text')
    recorded = bound['inspection']
    if (not isinstance(recorded, dict) or not isinstance(recorded.get('findings'), list)
            or any(not isinstance(row, dict) or row.get('severity') == 'problem'
                   for row in recorded['findings'])):
        raise ValueError('saved authored prompt check is missing or records a problem')
    selection = bound['vocabulary']
    if contract['mode'] == 'tag-based':
        from state_protocol import validate_against_schema
        errors = validate_against_schema(selection, c.load(ROOT / 'schemas/prompt-vocabulary-selection.schema.json'))
        if errors:
            raise ValueError('saved authored vocabulary: ' + '; '.join(errors))
        expected = {'model': model['id'], 'prompt_input_sha256': c.digest(c.encoded(contract).rstrip(b'\n')),
                    'dialect': model['prompt_dialect'], 'prompt_sha256': bound['prompt_sha256'],
                    'negative_sha256': bound['negative_sha256'], 'syntax': syntax}
        if (any(selection['context'][key] != value for key, value in expected.items())
                or selection['vocabularies'] != contract['vocabularies'] or selection['unresolved']
                or any(row['choice'] is None for row in selection['entries'])):
            raise ValueError('saved authored vocabulary differs from its text, model, syntax or settled choices')
    elif selection is not None:
        raise ValueError('a descriptive model has no required tag vocabulary binding')
    if recorded != _inspect(prompt, negative, model, syntax, selection):
        raise ValueError('saved authored prompt check differs from inspection of its exact input')
