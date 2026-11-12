"""Read the inputs or evidence needed for one production decision.

Views use the run's saved bytes. They do not mark instructions as read, fill
judgments, authorize an operation or change a production record.
"""
from __future__ import annotations

from pathlib import Path

import execution_contract as c
import production_evidence as media
import production_workflow as workflow


def _candidate(loaded, candidate: str) -> dict:
    row = workflow.find(loaded.rows, 'candidate', candidate)
    files = []
    for item in row['data']['files']:
        raw = loaded.evidence.read(item['sha256'])
        files.append({'path': str(loaded.directory / 'objects' / item['sha256']),
                      'sha256': item['sha256'], 'size': len(raw)})
    return {'id': candidate, 'files': files, 'media': row['data']['media']}


def _reading(prepared: dict) -> dict:
    return {'entry': str(workflow.ROOT / 'SKILL.md'),
            'documents': [{'path': str(workflow.ROOT / item['path']), 'prepared_sha256': item['sha256']}
                          for item in prepared['route']['reads']],
            'instruction': 'Use these paths to recover any applicable Skill instructions missing from the '
                           'active context, then apply them to this phase.'}


def _input(loaded) -> dict:
    """Expose provider-facing text, parameters and media without assessment context."""
    directory, prepared, consumer, _ = loaded
    execution = prepared['task']['execution']
    plan = loaded.artifacts['execution-plan.json']
    if execution == 'dispatcher':
        rendered = loaded.artifacts['request-contract.json']
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
        from image_input import external_delivery
        delivery = external_delivery(binding, run_directory=directory, read_object=loaded.evidence.read)
        return {'execution': execution, **delivery, 'outputs': external['count']}
    return {'execution': execution, 'delivery': consumer['instructions'],
            'media': [], 'request': plan.get('request')}


def _sources(loaded) -> list[dict]:
    from production_compiler import dependency_space
    directory, prepared = loaded.directory, loaded.prepared
    sources = []
    originals = {}

    def append(source: dict, digest: str) -> None:
        entry = {**source, 'saved_path': str(directory / 'objects' / digest), 'sha256': digest}
        if digest in originals:
            original = originals[digest]
            entry.update(size=original['size'], content_ref=original['id'])
        else:
            raw = loaded.evidence.read(digest)
            entry['size'] = len(raw)
            try:
                entry['text'] = raw.decode('utf-8')
            except UnicodeDecodeError:
                pass
            originals[digest] = entry
        sources.append(entry)

    dependencies = {(item['space'], item['path']): item for item in prepared['dependencies']}
    for source in prepared['task']['sources']:
        item = dependencies.get((dependency_space(source['path']), source['path']))
        if item is None:
            raise ValueError('review source lacks a prepared dependency')
        append(source, item['sha256'])
    selected = {source['id'] for source in sources}
    for source in prepared.get('identity_coverage', {}).get('sources', []):
        if source['id'] in selected:
            continue
        append(source, source['sha256'])
    return sources


def _authored(loaded, phase: str) -> dict:
    """Read the exact authored artifact before its independent assessment basis."""
    prepared, consumer = loaded.prepared, loaded.consumer
    revision = prepared['authored_revision']
    result = {'phase': phase, 'run': prepared['run'], 'execution': 'authored',
              'artifact': {'path': str(loaded.directory / revision['artifact']['path']),
                           'sha256': revision['artifact']['sha256'], 'text': consumer['instructions']},
              'state': revision['state'], 'input_verified': revision['input_verified']}
    if phase in {'input', 'observe'}:
        result['instruction'] = ('Read the saved text and describe what it says or calls for, including '
            'its specific relationships and limits. Preserve that reading before assessing it against '
            'the task requirements or prior findings.')
    else:
        from production_authored import review_basis
        result.update(review_basis(loaded))
    return result


def workspace(root: Path, run: str, *, phase: str, candidate: str | None = None) -> dict:
    """Return an input, candidate-only observation, or prepared assessment view."""
    if phase not in {'input', 'decision', 'observe', 'review'}:
        raise ValueError('workspace phase must be input, decision, observe or review')
    if phase in {'input', 'decision'} and candidate is not None:
        raise ValueError('the input view is scoped to its prepared request')
    root = c._root(root)
    loaded = workflow.read_run(root, run)
    directory, prepared, consumer, rows = loaded
    if prepared['task']['execution'] == 'authored':
        if candidate is not None:
            raise ValueError('an authored workspace reads its saved revision')
        return _authored(loaded, phase)
    if phase in {'observe', 'review'} and candidate is None:
        raise ValueError('observation and review views require one actual candidate')
    result = {'phase': phase, 'run': run}
    if candidate is not None:
        result['candidate'] = _candidate(loaded, candidate)
    if phase == 'observe':
        result['instruction'] = ('Inspect the supplied candidate files. Describe what is visible or measurable, '
                                 'with locators and limits. Preserve this first observation before receiving '
                                 'the commission, expected interpretation or prior findings.')
        return result
    result.update(input_sha256=prepared['input_sha256'], reading=_reading(prepared),
                  prepared_input=_input(loaded))
    if phase == 'input':
        result['instruction'] = ('Read the complete prepared request and inspect its supplied media. '
                                 'Describe the concrete result their combination calls for and how the '
                                 'supplied media contribute. Preserve this reconstruction before comparing '
                                 'it with the commission.')
        return result
    result.update(basis=workflow.review_basis(root, run, candidate), sources=_sources(loaded),
                  source_context={key: consumer[key] for key in
                                  ('world_views', 'moment_views', 'authoring_materials', 'semantic_edit')
                                  if key in consumer})
    if 'identity_coverage' in prepared:
        result['identity_coverage'] = prepared['identity_coverage']
        result['identity_instruction'] = result['basis']['identity_instruction']
    if phase == 'decision':
        import production_store
        import production_permissions
        import production_request
        plan = loaded.artifacts['execution-plan.json']
        held = production_store.read_authority(root, prepared['task']['task_id'], required=False)
        authority = held.document if held is not None else None
        result['authority'] = production_store.authority_snapshot(root, prepared['task']['task_id'], held,
                                                                 source_path=prepared['task'].get('authority'))
        result['authorization_requirements'] = production_permissions.grant_requirements(authority, plan['operations'])
        result['request_scope_template'] = production_request.delegation_template(prepared, plan['operations'], authority)
        result['operations'] = plan['operations']
        result['review_requirements'] = plan.get('review_requirements', [])
        result['prompt_check'] = plan.get('prompt_check')
        result['instruction'] = ('Establish the intended result from the commission and applicable original '
                                 'sources, including adopted definitions and current state, necessary '
                                 'conditions of use, and authorized change and preservation scopes. Assess '
                                 'their authored meaning, scope and importance. Compare the prepared hard '
                                 'and advisory criteria with those requirements, including necessary '
                                 'identity obligations, and compare the complete prepared input with the '
                                 'intended result. Judge agent-selected staging, format and incidental '
                                 'detail as means within the available freedom; coherent alternatives can '
                                 'meet the same requirements. Complete each operation decision within the '
                                 'recorded authority. Resolve a material mismatch through its owning '
                                 'authoring choice. Keep provenance and payload details in their existing '
                                 'records.')
        return result
    result['instruction'] = ('After recording the candidate observation, assess the result against the '
                             'commission and applicable original sources, including adopted definitions '
                             'and current state, necessary conditions of use, and preservation required '
                             'by authorized local changes. Judge differences at their authored meaning, '
                             'scope and importance. Check the prepared criteria against those requirements. '
                             'Correct a criterion that incorrectly makes a chosen means mandatory through '
                             'the existing authorized task revision path, then prepare and review the '
                             'revised task before formal selection. Apply hard criteria for required '
                             'outcomes and necessary source-based identity obligations at that scope; '
                             'assess advisory criteria '
                             'according to their authored purpose. Use selected '
                             'realizations and craft questions to judge how the means contribute to the '
                             'result; coherent alternatives can satisfy the same requirements. Record a '
                             'pass when a criterion is met, describe shortfalls and evidence limits at '
                             'their specific scope, and complete the conclusion. Place nonblocking '
                             'uncertainty in observations, limitations or advisory checks, and offer '
                             'useful optional repairs as proposals. Reserve review.unresolved for '
                             'questions that need resolution or explicit acceptance to select the '
                             'candidate against the required outcome. Use the evidence IDs in this view '
                             'for source comparisons. Record author self-review in the review fields '
                             'when the observing context already knew the intended result.')
    return result
