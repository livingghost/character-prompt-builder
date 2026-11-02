"""Read the inputs or evidence needed for one production decision.

Views use the run's saved bytes. They do not mark instructions as read, fill
judgments, authorize an operation or change a production record.
"""
from __future__ import annotations

from pathlib import Path

import execution_contract as c
import production_evidence as media
import production_workflow as workflow


def _candidate(directory: Path, rows: list[dict], candidate: str) -> dict:
    row = workflow.find(rows, 'candidate', candidate)
    files = []
    for item in row['data']['files']:
        raw = c.object_read(directory, item['sha256'])
        files.append({'path': str(directory / 'objects' / item['sha256']),
                      'sha256': item['sha256'], 'size': len(raw)})
    return {'id': candidate, 'files': files, 'media': row['data']['media']}


def _reading(prepared: dict) -> dict:
    return {'entry': str(workflow.ROOT / 'SKILL.md'),
            'documents': [{'path': str(workflow.ROOT / item['path']), 'prepared_sha256': item['sha256']}
                          for item in prepared['route']['reads']],
            'instruction': 'Read the applicable Skill instructions when they are absent from the active context. '
                           'Use these paths to recover that context. A saved reading record records earlier '
                           'delivery and application; it does not establish what this reader understands. '
                           'This view does not issue or complete a reading record.'}


def _external_media(directory: Path, binding: dict) -> list[dict]:
    external = binding['external_request']
    prepared = binding.get('prepared_reference_set')
    found = set()
    result = []
    for index, (reference, field) in enumerate(zip(binding['references'], external['reference_fields'], strict=True)):
        if prepared is None:
            key = reference['sha256']
        elif prepared['transport_mode'] == 'single-board':
            key = prepared['single_board']['sha256']
        else:
            key = prepared['selected_references'][index]['transport']['sha256']
        identity = (key, tuple(field['field']))
        if identity in found:
            continue
        found.add(identity)
        raw = c.object_read(directory, key)
        result.append({'path': str(directory / 'objects' / key), 'sha256': key,
                       'request_fields': [field['field']], 'media': media.inspect(raw, 'image')})
    return result


def _input(directory: Path, prepared: dict, consumer: dict) -> dict:
    """Expose provider-facing text, parameters and media without assessment context."""
    execution = prepared['task']['execution']
    plan = c.load(directory / 'execution-plan.json')
    if execution == 'dispatcher':
        import request_contract
        rendered = c.load(directory / 'request-contract.json')
        request_contract.validate_seal(rendered)
        attachments = []
        for index, item in enumerate(rendered['media']):
            path = Path(item['path'])
            relative = path.relative_to(directory)
            raw = c.read(c.local(directory, relative.as_posix()))
            if c.digest(raw) != item['sha256'] or len(raw) != item['size']:
                raise ValueError('prepared workspace media differs from the sealed request')
            kind = item['media_type'].split('/', 1)[0]
            if kind not in media.KINDS:
                kind = 'binary'
            attachments.append({'path': str(path), 'sha256': item['sha256'],
                'request_fields': [entry['field'] for entry in rendered['layout']['media'] if entry['index'] == index],
                'media': media.inspect(raw, kind)})
        return {'execution': execution, 'target': rendered['sealed']['target'],
                'request': rendered['request'], 'request_sha256': rendered['request_sha256'],
                'media': attachments, 'outputs': rendered['output_count'],
                'transport': 'Declared media fields receive upload identifiers for these exact saved bytes before sending.'}
    binding = consumer.get('image_input')
    external = binding.get('external_request') if binding else None
    if external is not None:
        result = {'execution': execution, 'target': binding['model']['target'],
                  'request': external['request'], 'request_sha256': external['sha256'],
                  'media': _external_media(directory, binding), 'outputs': external['count']}
        if external.get('model_identity') is not None:
            result['model_identity'] = external['model_identity']
        return result
    return {'execution': execution, 'delivery': consumer['instructions'],
            'media': [], 'request': plan.get('request')}


def _sources(directory: Path, prepared: dict) -> list[dict]:
    from production_compiler import dependency_space
    sources = []
    dependencies = {(item['space'], item['path']): item for item in prepared['dependencies']}
    for source in prepared['task']['sources']:
        item = dependencies.get((dependency_space(source['path']), source['path']))
        if item is None:
            raise ValueError('review source lacks a prepared dependency')
        raw = c.object_read(directory, item['sha256'])
        entry = {**source, 'saved_path': str(directory / 'objects' / item['sha256']),
                 'sha256': item['sha256'], 'size': len(raw)}
        try:
            entry['text'] = raw.decode('utf-8')
        except UnicodeDecodeError:
            pass
        sources.append(entry)
    return sources


def workspace(root: Path, run: str, *, phase: str, candidate: str | None = None) -> dict:
    """Return an input, candidate-only observation, or prepared assessment view."""
    if phase not in {'input', 'decision', 'observe', 'review'}:
        raise ValueError('workspace phase must be input, decision, observe or review')
    if phase in {'observe', 'review'} and candidate is None:
        raise ValueError('observation and review views require one actual candidate')
    if phase in {'input', 'decision'} and candidate is not None:
        raise ValueError('the input view is scoped to its prepared request')
    root = c._root(root)
    directory, prepared, consumer, rows = workflow.load_run(root, run)
    result = {'phase': phase, 'run': run}
    if candidate is not None:
        result['candidate'] = _candidate(directory, rows, candidate)
    if phase == 'observe':
        result['instruction'] = ('Inspect the supplied candidate files. Describe what is visible or measurable, '
                                 'with locators and limits. Preserve this first observation before receiving '
                                 'the commission, expected interpretation or prior findings.')
        return result
    result.update(input_sha256=prepared['input_sha256'], reading=_reading(prepared),
                  prepared_input=_input(directory, prepared, consumer))
    if phase == 'input':
        result['instruction'] = ('Read the complete prepared request and inspect its supplied media. '
                                 'Reconstruct what their combined input asks the model to depict before '
                                 'comparing it with the commission. These are prepared bytes; this view '
                                 'does not establish that they were sent or that a result was accepted.')
        return result
    result.update(basis=workflow.review_basis(root, run, candidate), sources=_sources(directory, prepared),
                  source_context={key: consumer[key] for key in
                                  ('world_views', 'moment_views', 'authoring_materials', 'semantic_edit')
                                  if key in consumer})
    if phase == 'decision':
        import production_store
        plan = c.load(directory / 'execution-plan.json')
        result['authority'] = production_store.authority(root, prepared['task']['task_id'], required=False)
        result['operations'] = plan['operations']
        result['review_requirements'] = plan.get('review_requirements', [])
        result['prompt_check'] = plan.get('prompt_check')
        result['instruction'] = ('After reconstructing the input, compare it with this commission and source scope. '
                                 'Read the actual authority evidence and complete each separate operation decision. '
                                 'The execution draft contains judgments; exact payloads, actor identities, counts '
                                 'and hashes are derived from this prepared run when those judgments are recorded.')
        return result
    result['instruction'] = ('After recording the candidate observation, assess it against the commission and '
                             'applicable sources. The prepared criteria, selected realizations and craft questions '
                             'supply the assessment basis. Judge the chosen means against the commission as well. '
                             'Write the supported verdicts, reasons and limits in the compact review draft; '
                             'reference evidence in this view is resolved automatically when that draft is recorded. '
                             'Declare author self-review when the observing context already knew the intent.')
    return result
