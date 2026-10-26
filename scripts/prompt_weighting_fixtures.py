"""Synthetic weighting interfaces for contract tests; never provider capability evidence."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch

import execution_contract as c
import pack_manager as packs
import production_case_fixtures as base
from catalog_retrieval import runtime

MODEL = base.MODEL_ID
PROMPT = '("solo, (blue eyes)1.2, long hair+", "forest, soft lighting").and(1, 0.8)'
NEGATIVE = '("lettering+, watermark", "signature").blend(1, 0.5)'


def refresh(case: dict) -> None:
    """Rebuild only authored synthetic evidence after changing this fixture's interface."""
    from prompt_retrieval import settle_retrieval_record
    from prepare_generation_references import resolve_model_record
    from request_validation_fixtures import fixture_validation
    from reading_fixtures import fixture_reading
    root = case['root']
    packs.write_lock(case['pack'])
    runtime.configure_pack_runtime(case['settings'])
    retrieval = c.load(root / 'retrieval.json')
    retrieval['pack_state'] = runtime.load_pack_catalog().fingerprint
    text = (root / 'prompt.txt').read_text(encoding='utf-8')
    base.write(root / 'retrieval.json', settle_retrieval_record(retrieval, prompt=text, plot=c.load(root / 'plot.json')))
    base.write(root / 'validation.json', fixture_validation(root, MODEL, reference_mode='authored-rendition', service='synthetic'))
    dialect = resolve_model_record(MODEL)[1].get('prompt_dialect')
    base.write(root / 'reading.json', fixture_reading(route='generation', studio=root,
               ledger=root / 'work/reads.jsonl', dialect=dialect))


def create(root: Path, runtime_root: Path, *, prompt: str = PROMPT, negative: str = NEGATIVE,
           syntax: str | None = 'compel', supported: tuple[str, ...] = ('compel', 'sdEmbeds'),
           family: bool = True, recommended_negative: str | None = None,
           default: str | None = None) -> dict:
    from render_contract_fixtures import control
    with patch.object(base, 'PROMPT', prompt):
        case = base.create(root, runtime_root)
    pack = case['pack']
    models = c.load(pack / 'records/models.json')
    record = models['records'][0]
    if default is not None:
        record['recommended_parameters'] = {'weighting': default}
    if family:
        record['prompt_dialect'] = 'synthetic-tags'
    if recommended_negative is not None:
        record.update(recommended_negative_prompt=recommended_negative, recommendation_merge_mode='tag-list')
    for profile in (record['execution_profile'], record['offerings'][0]['execution_profile']):
        for mode in profile['modes'].values():
            mode['controls']['promptWeighting'] = control('required' if default else 'optional', schema={'type': 'string', 'enum': list(supported)}, recommendation='weighting' if default else None)
    base.write(pack / 'records/models.json', models)
    manifest = c.load(pack / 'pack.json')
    manifest['content']['resource_bindings'].update({'prompt-vocabulary': 'resources/dictionary.json', 'prompt-dialects': 'resources/dialects.json'})
    base.write(pack / 'pack.json', manifest)
    base.write(pack / 'resources/dictionary.json', {
        'format': 'character-prompt-builder-prompt-vocabulary', 'name': 'Synthetic weighting vocabulary',
        'description': 'Small authored terms for mechanics, not a provider dictionary.',
        'categories': [{'id': 'fixture', 'name': 'Synthetic terms', 'description': 'Fixture words.',
            'entries': [{'term': term, 'description': 'Synthetic test meaning.'} for term in
                        ['solo', 'blue eyes', 'green eyes', 'long hair', 'forest', 'soft lighting', 'lettering', 'watermark', 'signature', 'blurry']]}]})
    base.write(pack / 'resources/dialects.json', {
        'format': 'character-prompt-builder-prompt-dialects', 'name': 'Synthetic learned families',
        'description': 'Learned terms and the weighting parser are different declarations.',
        'dialects': [{'id': 'synthetic-tags', 'name': 'Fixture family', 'description': 'No real model claim.',
                      'tag_separator': 'comma', 'block_order': ['subject', 'environment']}]})
    task = c.load(root / 'task.json')
    if negative:
        base.write(root / 'negative.txt', negative)
        task['generation']['negative'] = 'negative.txt'
        task['generation']['critical_avoidance_integrated'] = True
    base.write(root / 'task.json', task)
    parameters = c.load(root / 'parameters.json')
    if syntax is not None:
        parameters['promptWeighting'] = syntax
    base.write(root / 'parameters.json', parameters)
    refresh(case)
    return case
