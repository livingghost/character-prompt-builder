"""Read the inputs or evidence needed for one production decision.

Views use the run's saved bytes. They do not mark instructions as read, fill
judgments, authorize an operation or change a production record.
"""
from __future__ import annotations

from pathlib import Path

import execution_contract as c
import production_evidence as media
import production_operations as workflow


def _candidate(loaded, candidate: str) -> dict:
    row = workflow.find(loaded.rows, 'candidate', candidate)
    files = []
    for item in row['data']['files']:
        raw = loaded.evidence.read(item['sha256'])
        files.append({'path': str(loaded.directory / 'objects' / item['sha256']),
                      'sha256': item['sha256'], 'size': len(raw)})
    return {'id': candidate, 'evidence_id': workflow.REVIEW_CANDIDATE_EVIDENCE,
            'files': files, 'media': row['data']['media']}


def _reading(prepared: dict, phase: str) -> dict:
    import execution_routes
    task = prepared['task']
    operation = 'execute' if phase in {'input', 'decision'} else 'review'
    selected = execution_routes.resolve(task['route'], task.get('features', []),
        execution=task['execution'], operation=operation)
    return {'entry': str(workflow.ROOT / 'SKILL.md'),
            'operation': operation,
            'documents': [{'path': str(workflow.ROOT / item['path']), 'sha256': item['sha256'],
                           'ranges': item['ranges'],
                           'sections': [row['anchor'] for row in selected['section_owners'][item['path']]]}
                          for item in selected['reads']],
            'instruction': 'Use these paths to recover any applicable Skill instructions missing from the '
                           'active context at the required source ranges, then apply them to this phase. '
                           'Earlier authoring-stage reading is not the current operation scope.'}


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
            # A workspace locates the exact captured original. Repeating every
            # document body here makes the act of reopening a decision depend
            # on the size of all authoring sources, including unchanged ones.
            # Sources remain accessible at saved_path, with their authored
            # role, locator and scope, and the review evidence owns their IDs.
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


def _saved_knowledge(root: Path, loaded) -> dict:
    """Locate model interpretation evidence from the prepared edition itself."""
    prepared, directory = loaded.prepared, loaded.directory
    reading = prepared.get('route_reading') or {}
    result = {'model': reading.get('model'),
        'instruction': 'Use these retained originals to interpret the saved request. '
            'They preserve its selected model edition; current catalog changes do not redefine it.'}
    if reading:
        result['reading_record'] = {'path': str(directory / 'prepared.json'), 'pointer': '/route_reading'}
    if prepared['task'].get('authored_basis'):
        result['authored_basis'] = {'path': str(directory / 'prepared.json'), 'pointer': '/task/authored_basis'}
    if 'execution-target.json' in loaded.artifacts:
        path = directory / 'execution-target.json'
        result['target'] = {'path': str(path), 'sha256': c.digest(c.read(path)),
                            'model_pointer': '/model', 'offering_pointer': '/offering'}
    descriptor = prepared.get('runtime_snapshot')
    binding = (descriptor or {}).get('binding', {})
    if descriptor is not None:
        import runtime_snapshot
        snapshot = runtime_snapshot.path(root, descriptor)
        result['runtime_snapshot'] = {'path': str(snapshot / 'snapshot.json'), 'sha256': descriptor['sha256']}
    result['resources'] = [{**row,
        'saved_path': str(snapshot / 'packs' / row['pack'] / row['path'])}
        for row in binding.get('resources', []) if row.get('role') == 'guide']
    return result


def summary(root: Path, report: dict) -> dict:
    """Keep this phase's judgment and name the other complete evidence owners.

    The input and observation phases are the material being interpreted, so
    their exact content stays visible. A decision or review presents every
    criterion and its source relationship once. Its other prepared views have
    executable read actions; original files have exact captured paths.
    """
    from production_report_view import action, fields, authority, authorization_requirements
    result = fields(report, ('phase', 'run', 'execution', 'input_sha256', 'candidate', 'saved_knowledge',
                             'artifact', 'state', 'input_verified', 'instruction', 'next_action'))
    phase = report['phase']
    if 'reading' in report:
        result['reading'] = fields(report['reading'], ('entry', 'operation', 'instruction'))
        result['reading']['documents'] = [fields(document, ('path', 'sections'))
                                          for document in report['reading']['documents']]
    if phase in {'input', 'observe'}:
        if 'prepared_input' in report:
            result['prepared_input'] = fields(report, ('prepared_input',))['prepared_input']
        return result
    if 'basis' in report:
        result['basis'] = fields(report['basis'], (key for key in report['basis']
                                                if key not in {'evidence', 'identity_coverage'}))
    else:
        # Authored revisions expose their basis at the top level.
        result.update(fields(report, ('purpose', 'intended_effect', 'direction', 'criteria', 'source_task_direction',
                                      'source_task_criteria', 'requirements', 'identity_instruction', 'unresolved')))
    result['sources'] = [fields(source, (key for key in source if key != 'text'))
                         for source in report.get('sources', [])]
    result['source_access'] = ('Read applicable originals at sources[].saved_path and evidence[].path, '
        'using each source role, locator and declared scope. These references preserve complete saved bytes; '
        'a path or this view does not establish that the source has been read.')
    basis = report.get('basis', report)
    guide = report.get('review_guide')
    if guide is not None:
        result['review_guide'] = fields(guide, (key for key in guide if key not in {'automatic_evidence', 'next_action'}))
        result['evidence'] = fields(guide, ('automatic_evidence',))['automatic_evidence']
    else:
        result['evidence'] = fields(basis, ('evidence',)).get('evidence', [])
        for entry in result['evidence']:
            if entry.get('path') and not Path(entry['path']).is_absolute():
                entry['path'] = str(root / entry['path'])
    coverage = basis.get('identity_coverage', report.get('identity_coverage'))
    if coverage is not None:
        # The source terminal inventories repeat complete identity values.
        # Keep the authored binding choices, whole-subject obligations and all
        # unresolved findings; put the complete structural map at one owner.
        result['identity_coverage'] = fields(coverage, (key for key in coverage if key != 'sources'))
        result['identity_coverage']['sources'] = [
            {**fields(source, (key for key in source if key != 'terminals')),
             'terminal_count': len(source.get('terminals', [])),
             'full_report': 'full_report#' + ('/basis' if 'basis' in report else '')
                            + '/identity_coverage/sources/' + str(index)}
            for index, source in enumerate(coverage.get('sources', []))]
        result['identity_instruction'] = basis.get('identity_instruction', report.get('identity_instruction'))
    if 'prepared_input' in report:
        result['prepared_input'] = fields(report['prepared_input'], ('execution', 'target', 'request_sha256', 'outputs'))
        result['prepared_input']['read_action'] = action(root, 'workspace',
            ['--run', report['run'], '--phase', 'input'],
            'Read the exact saved model request and inspect its media before comparing it with this basis.')
    if report.get('source_context'):
        result['source_context'] = {name: {'full_report': 'full_report#/source_context/' + name,
            'meaning': 'Retained prepared context for this selected source kind.'}
            for name in report['source_context']}
    result.update(fields(report, ('review_requirements', 'prompt_check')))
    if 'authority' in report:
        held = report['authority']
        result['authority'] = authority(held)
        document = held.get('document') if held else None
        if document is not None:
            relevant = {candidate['grant']
                for requirement in (report.get('authorization_requirements') or {}).get('requirements', [])
                for candidate in requirement.get('candidates', [])
                if candidate.get('eligible') or candidate.get('grant') == requirement.get('selected_grant')}
            result['authority']['document'] = fields(document, ('task_id', 'issuer', 'evidence', 'stop_conditions'))
            result['authority']['document']['grants'] = [fields(grant, grant) for grant in document.get('grants', [])
                                                        if grant['id'] in relevant]
            result['authority']['other_grant_count'] = len(document.get('grants', [])) - len(
                result['authority']['document']['grants'])
            result['authority']['full_report'] = 'full_report#/authority'
    if 'authorization_requirements' in report:
        result['authorization_requirements'] = authorization_requirements(report['authorization_requirements'])
    if 'operations' in report:
        result['operations'] = [fields(operation, ('operation', 'targets')) for operation in report['operations']]
    if report.get('request_scope_template') is not None:
        result['request_scope_template'] = {'full_report': 'full_report#/request_scope_template',
            'meaning': 'Unanswered authority template for a new request delegation; current grants remain authoritative.'}
    result['details_action'] = action(root, 'workspace', ['--run', report['run'], '--phase', phase,
        *(['--candidate', report['candidate']['id']] if 'candidate' in report else []), '--view', 'full'],
        'Read every retained relationship for this phase. Captured originals remain at their displayed file paths.')
    return result


def _authored(root: Path, loaded, phase: str) -> dict:
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
        result['saved_knowledge'] = _saved_knowledge(root, loaded)
        result['review_guide'] = workflow.review_authoring_guide(
            root, prepared['run'], loaded=loaded, basis=result)
        result['next_action'] = result['review_guide']['next_action']
    return result


def workspace(root: Path, run: str, *, phase: str, candidate: str | None = None) -> dict:
    """Return an input, candidate-only observation, or prepared assessment view."""
    if phase not in {'input', 'decision', 'observe', 'review'}:
        raise ValueError('workspace phase must be input, decision, observe or review')
    if phase in {'input', 'decision'} and candidate is not None:
        from production_diagnostics import ProductionError
        from production_report_view import action
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            'The input and decision views describe the prepared request; a candidate belongs to observation or review.',
            phase='workspace', run=run, candidate=candidate,
            required_action='Use next_action to observe this exact candidate before assessment. '
                            'For the prepared input or execution decision, omit --candidate.',
            next_action=action(root, 'workspace', ['--run', run, '--phase', 'observe', '--candidate', candidate],
                               'Observe the exact saved candidate before interpreting it against the commission.'))
    root = c._root(root)
    loaded = workflow.read_run(root, run)
    directory, prepared, consumer, rows = loaded
    if prepared['task']['execution'] == 'authored':
        if candidate is not None:
            raise ValueError('an authored workspace reads its saved revision')
        return _authored(root, loaded, phase)
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
    result.update(input_sha256=prepared['input_sha256'], reading=_reading(prepared, phase),
                  saved_knowledge=_saved_knowledge(root, loaded),
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
        import production_request
        plan = loaded.artifacts['execution-plan.json']
        held = production_store.read_authority(root, prepared['task']['task_id'], required=False)
        authority = held.document if held is not None else None
        result['authority'] = production_store.authority_snapshot(root, prepared['task']['task_id'], held,
                                                                 source_path=prepared['task'].get('authority'), run=run)
        result['authorization_requirements'] = workflow.authorization_requirements(root, prepared, held, plan['operations'])
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
    result['review_guide'] = workflow.review_authoring_guide(root, run, candidate,
                                                           loaded=loaded, basis=result['basis'])
    result['next_action'] = result['review_guide']['next_action']
    return result
