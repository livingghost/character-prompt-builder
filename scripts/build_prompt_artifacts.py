#!/usr/bin/env python3
"""Publish the actual selected authoring work as prompt artifacts.

The work owns its text, target and selected documents. Publication resolves
that one input, checks the selected contracts and preserves its exact text.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Sequence

import execution_contract as c
import operation_context
from prompt_plot import validate_prompt_plot
from prompt_retrieval import validate_prompt_retrieval_record
from validate_prompt_semantics import validate_plan


DOCUMENTS = {
    'reference_use_plan': 'reference-use-plan.json',
    'surface_lighting_plan': 'surface-lighting-plan.json',
    'prepared_reference_set': 'prepared-reference-set.json',
    'semantic_plan': 'semantic-plan.json',
    'retrieval_record': 'prompt-retrieval-record.json',
    'plot': 'prompt-plot.json',
}
CONTENT_FIELDS = frozenset({'prompt', 'negative', 'model', 'model_record', 'weighting',
                            'documents', 'retrieval_unavailable'})


def selected_reference_count(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, dict) or value.get('artifact_type') != 'reference-use-plan':
        raise ValueError("reference use plan artifact_type must be 'reference-use-plan'")
    if not isinstance(value.get('reference_items'), list):
        raise ValueError('reference use plan reference_items must be a list')
    return len(value['reference_items'])


def check_content(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) - CONTENT_FIELDS:
        raise ValueError('prompt work content requires prompt, optional negative, model or model_record, '
                         'weighting, documents and retrieval_unavailable')
    c.text(value.get('prompt'), 'work content prompt')
    if 'negative' in value and not isinstance(value['negative'], str):
        raise ValueError('work content negative must be text')
    if value.get('model') is not None and value.get('model_record') is not None:
        raise ValueError('select content.model or content.model_record')
    if value.get('weighting', 'literal') not in {'literal', 'sdEmbeds', 'compel'}:
        raise ValueError('content.weighting must be literal, sdEmbeds or compel')
    documents = value.get('documents', {})
    if not isinstance(documents, dict) or set(documents) - set(DOCUMENTS):
        raise ValueError('content.documents contains an unknown document')
    if 'retrieval_unavailable' in value:
        c.text(value['retrieval_unavailable'], 'retrieval unavailable reason')
    return value


def _checked(report: dict, label: str) -> dict:
    if not report['ok']:
        raise ValueError(label + ': ' + '; '.join(str(item) for item in report['errors']))
    return report


def inspect_content(content: dict, *, generation: bool, require_semantics: bool) -> dict:
    """Use existing target, vocabulary, plot and geometry contract owners."""
    from model_prompt_input import resolve_prompt_input
    from prompt_retrieval import resolve_selected_model, require_generation_retrieval
    prompt, negative = content['prompt'], content.get('negative', '')
    documents = content.get('documents', {})
    model_record = content.get('model_record')
    if model_record is not None:
        resolve_prompt_input(model_record)
        c.text(model_record.get('id'), 'acquired model id')
    else:
        model_record = resolve_selected_model(content.get('model'), None)
    if generation and model_record is None:
        raise ValueError('generation-ready packaging requires content.model or content.model_record')
    syntax = content.get('weighting', 'literal')
    target_contract = None
    if model_record is not None:
        from check_tag_prompt import inspect
        from production_diagnostics import ProductionError
        inspection = inspect(prompt, negative, None, model_record, syntax=syntax)
        if any(row['severity'] == 'problem' for row in inspection['findings']):
            raise ProductionError('TAG_PROMPT_PROBLEM',
                'The selected work violates its text grammar or declared model constraints.',
                phase='prompt-artifact', prompt_check=inspection,
                guidance={'document_path': 'references/runtime/prompt-only-core.md#specialized-prompt-artifact-export'},
                required_action='Edit the actual work content or select its intended weighting grammar, then publish it again.')
        target_contract = {'id': model_record['id'], 'prompt_input': resolve_prompt_input(model_record),
                           'weighting': syntax}
        if model_record.get('prompt_dialect'):
            target_contract['prompt_dialect'] = model_record['prompt_dialect']
        target_contract['source'] = ({'kind': 'acquired-external-record', 'path': 'model-input.json',
            'sha256': c.content_id(model_record)} if content.get('model_record') is not None else
            {'kind': 'catalog-record', 'requested': content['model']})

    plot_value = documents.get('plot')
    plot_report = _checked(validate_prompt_plot(plot_value), 'prompt plot is invalid') if plot_value is not None else None
    plot = {'settled': plot_report is not None, 'approved': bool(plot_report and plot_report['approved'])}
    if plot_report:
        plot.update({key: plot_report[key] for key in ('beats', 'visible_beats', 'derived', 'source')})
        if plot_report['approval_errors']:
            raise ValueError('invalid supplied approval: ' + '; '.join(plot_report['approval_errors']))
    if generation and plot_value is not None and not plot['approved']:
        raise ValueError('generation-ready packaging requires an approved selected plot')

    record = documents.get('retrieval_record')
    unavailable = content.get('retrieval_unavailable')
    if record is not None and unavailable is not None:
        raise ValueError('select a retrieval_record or retrieval_unavailable')
    validation = {'state': 'unverified-draft', 'vocabulary_searched': False}
    if record is not None:
        report = _checked(validate_prompt_retrieval_record(record), 'prompt retrieval record is invalid')
        retrieval = {'settled': record.get('settled') is True,
                     **{key: report[key] for key in ('elements', 'adopted', 'composed', 'unused')}}
    elif unavailable is not None:
        retrieval = {'settled': False, 'reason': unavailable.strip()}
        if generation:
            raise ValueError('generation-ready packaging requires a retrieval record; retrieval was unavailable: ' + unavailable)
    else:
        retrieval = {'settled': True, 'elements': 0, 'adopted': 0, 'composed': 0, 'unused': 0}
    if generation:
        checked = require_generation_retrieval(record, prompt=prompt, plot=plot_value,
            model_record=model_record, negative=negative, syntax=syntax)
        validation.update(state='model-input-checked', vocabulary_searched=checked['vocabulary_searched'])
    elif model_record is not None:
        from prompt_vocabulary_selection import require_for_model
        selected = require_for_model(record or {}, prompt=prompt, negative=negative,
                                     model_record=model_record, syntax=syntax)
        validation.update(state='model-input-checked', vocabulary_searched=selected is not None)

    semantic = documents.get('semantic_plan')
    if require_semantics and semantic is None:
        raise ValueError('--require-semantic-plan requires content.documents.semantic_plan')
    semantic_report = _checked(validate_plan(semantic), 'prompt semantic preflight failed') if semantic is not None else None
    ref_count = selected_reference_count(documents.get('reference_use_plan'))
    if generation and ref_count and documents.get('prepared_reference_set') is None:
        raise ValueError('generation-ready reference transport requires content.documents.prepared_reference_set')
    return {'target': target_contract, 'input_validation': validation, 'plot': plot,
            'retrieval': retrieval, 'selected_reference_count': ref_count, 'semantic_report': semantic_report}


def publish(work_path: Path, out: Path, *, generation: bool = False,
            require_semantics: bool = False, overwrite: bool = False) -> dict:
    from authoring_work import resolve_work
    work_path, out = work_path.resolve(), out.resolve()
    if work_path == out or out in work_path.parents:
        raise ValueError('the authoring work is inside the output directory and would be destroyed')
    raw = work_path.read_bytes()
    work = c.decode(raw)
    resolved = resolve_work(work, complete=True, require_subject=True)
    content = check_content(resolved['content'])
    inspected = inspect_content(content, generation=generation, require_semantics=require_semantics)
    if out.exists():
        if not out.is_dir():
            raise ValueError('output path exists and is not a directory: ' + str(out))
        if any(out.iterdir()) and not overwrite:
            raise ValueError('output directory is not empty; pass --overwrite to replace it: ' + str(out))
    staging = out.parent / f'.{out.name}.partial-{os.getpid()}'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        included, omitted = [], []
        def put(name: str, value: Any, *, text: bool = False, acquired: bool = False) -> None:
            data = value if acquired else value.encode('utf-8') if text else c.encoded(value)
            (staging / name).write_bytes(data)
            included.append({'path': name, 'bytes': len(data), 'sha256': c.digest(data)})
        put('authoring-work.json', raw, acquired=True)
        report = {key: value for key, value in resolved.items() if key != 'content'}
        put('authoring-report.json', report)
        put('final-prompt.txt', content['prompt'], text=True)
        if 'negative' in content:
            put('final-negative.txt', content['negative'], text=True)
        if content.get('model_record') is not None:
            put('model-input.json', content['model_record'])
        if inspected['semantic_report'] is not None:
            put('semantic-preflight.json', inspected['semantic_report'])
        for key, name in DOCUMENTS.items():
            value = content.get('documents', {}).get(key)
            if value is not None and (key != 'reference_use_plan' or inspected['selected_reference_count'] > 0):
                put(name, value)
            else:
                reason = ('no selected references' if key == 'reference_use_plan' else
                          inspected['retrieval'].get('reason', 'no retrieval work selected') if key == 'retrieval_record' else
                          'document not selected for this work')
                omitted.append({'artifact': name, 'reason': reason})
        manifest = {'artifact_type': 'prompt-artifact-package',
            'mode': 'generation-ready' if generation else 'prompt-only',
            'approval_scope': 'preparation-only' if generation else 'draft-unapproved',
            'execution_authorized': False, 'canonical_update_authorized': False,
            **{key: value for key, value in inspected.items() if key != 'semantic_report'},
            'authoring': {'work_sha256': c.digest(raw), 'content_sha256': c.content_id(content)},
            'included': included, 'omitted': omitted}
        (staging / 'prompt-artifact-manifest.json').write_bytes(c.encoded(manifest))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = operation_context.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--work', required=True, type=Path, help='The selected actual authoring work')
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--prepare-for-generation', action='store_true')
    parser.add_argument('--require-semantic-plan', action='store_true')
    parser.add_argument('--overwrite', action='store_true')
    from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    from catalog_api import configure_pack_runtime
    configure_pack_runtime(resolve_pack_runtime(parser, args).settings)
    manifest = publish(args.work, args.out_dir, generation=args.prepare_for_generation,
                       require_semantics=args.require_semantic_plan, overwrite=args.overwrite)
    print(json.dumps({'ok': True, 'manifest': manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(operation_context.run_cli(main))
