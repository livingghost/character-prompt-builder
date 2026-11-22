"""Compare retained authoring owners to select current amendment knowledge.

The author declares the intended change. Exact structured values can enlarge
that scope and detect a conflicting retention; prompt prose is never classified.
The declaration supplies neither source authority nor permission to publish.
"""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c

RETAIN_SCOPES = ('identity', 'source-authority', 'depiction', 'rendition', 'finish',
                 'target', 'controls', 'references', 'recording')
CHANGE_SCOPES = ('definition', 'source-authority', 'depiction', 'depiction.view',
                 'references', 'rendition', 'controls', 'controls.parameters',
                 'controls.render-intent', 'target', 'recording', 'recording.slot')
PROFILE_BY_SCOPE = {
    'definition': 'amend-definition', 'source-authority': 'amend-definition',
    'depiction': 'amend-depiction', 'references': 'amend-references',
    'rendition': 'amend-rendition', 'controls': 'amend-controls',
    'target': 'retarget', 'recording': 'amend-recording',
}
PROFILES = frozenset(PROFILE_BY_SCOPE.values())
RETAIN_OWNER = {'identity': 'definition', 'finish': 'controls.render-intent'}
TEXT_DOCUMENTS = {'negative', 'integrated_prompt', 'native_negative'}
DEFINITION_FIELDS = {'id', 'domain', 'identity', 'identity_contract_ref',
    'species_morphology_profile_ref', 'individual_morphology_contract_ref',
    'resolved_morphology', 'frame_character', 'load_bearing_part_measurements'}
TASK_META = {'task_id', 'production_id', 'authority', 'route_reading', 'work_basis',
             'authored_basis', 'execution_decisions', 'delivery', 'generation', 'image_input', 'authored', 'upscale'}
TASK_DEPICTION = {'direction', 'criteria', 'world_views', 'moment_views', 'scene_materials'}
TASK_KNOWN = TASK_META | TASK_DEPICTION | {'sources', 'recording', 'route', 'features',
    'artifact', 'execution', 'semantic_edit', 'upload_sources'}


def validate_change_scope(value: dict | None) -> None:
    if value is None:
        return
    c.exact(value, {'retain', 'change'}, 'amendment change scope')
    for key, allowed in (('retain', RETAIN_SCOPES), ('change', CHANGE_SCOPES)):
        rows = value[key]
        if (not isinstance(rows, list) or any(not isinstance(item, str) for item in rows)
                or len(set(rows)) != len(rows) or set(rows) - set(allowed)):
            raise ValueError('change_scope.' + key + ' must contain distinct names from: ' + ', '.join(allowed))
    if not value['change']:
        raise ValueError('change_scope.change must name the intended amendment')
    changed = {item.split('.')[0] for item in value['change']}
    for retained in value['retain']:
        owner = RETAIN_OWNER.get(retained, retained)
        # Finishing is independent of seed, count and numeric parameters.
        conflict = (owner in value['change'] or 'controls' in value['change']) if retained == 'finish' else owner in changed
        if conflict:
            raise ValueError('change_scope cannot both retain and change ' + retained)


def _read(root: Path, path: str, read_source=None) -> bytes:
    selected = Path(path)
    if selected.is_absolute():
        try:
            path = selected.relative_to(root.resolve()).as_posix()
        except ValueError:
            # Reference and pack owners declare absolute original sources.
            # They retain their own provenance and byte validation; the task
            # reader's Studio-relative namespace cannot identify these files.
            return c.read(selected)
    return read_source(path) if read_source is not None else c.read(c.local(root, path))


def _selected(root: Path, value, *, text=False, read_source=None):
    if not isinstance(value, dict) or 'file' not in value:
        return copy.deepcopy(value)
    raw = _read(root, value['file'], read_source)
    result = raw.decode('utf-8') if text and 'field' not in value else c.decode(raw)
    for part in value.get('field', []):
        result = result[part]
    return result


def _document_witnesses(documents: dict) -> None:
    """Drop only generated fields at their documented owning locations."""
    plot = documents.get('plot')
    if isinstance(plot, dict) and isinstance(plot.get('approved'), dict):
        plot['approved'].pop('content_sha256', None)
    retrieval = documents.get('retrieval_record')
    if isinstance(retrieval, dict):
        retrieval.pop('context', None)
        retrieval.pop('settled', None)
    visual = documents.get('visual_continuity')
    if isinstance(visual, dict):
        if isinstance(visual.get('basis'), dict):
            visual['basis'].pop('sha256', None)
        for subject in (visual.get('subjects') or {}).values():
            for selected in subject.get('identity_refs', []):
                selected.pop('source_sha256', None)
                selected.pop('reference_number', None)


def _measured(root: Path, path: str, witnesses: dict, *, read_source=None, retained=False) -> str:
    witness = witnesses.get(path)
    digest = witness.get('sha256') if isinstance(witness, dict) else witness
    if retained and digest is not None:
        return digest
    raw = c.read(Path(path)) if read_source is None and Path(path).is_absolute() else _read(root, path, read_source)
    return c.digest(raw)


def _evidence(root: Path, evidence, witnesses: dict, *, read_source=None, retained=False):
    result = copy.deepcopy(evidence)
    if isinstance(result, dict) and isinstance(result.get('path'), str):
        path = result.pop('path')
        result['sha256'] = _measured(root, path, witnesses, read_source=read_source, retained=retained)
    return result


def _external_owners(root: Path, external: dict, *, read_source=None, retained=False) -> dict:
    """Use declared request paths, without interpreting provider field names."""
    import request_contract as rc
    plan = external.get('image_input')
    if isinstance(plan, str):
        plan = c.decode(_read(root, plan, read_source))
    if not isinstance(plan, dict):
        return {'controls': None, 'negative': None, 'wording_fields': None, 'target': None, 'transport': None}
    binding = plan.get('external_request') or {}
    request = copy.deepcopy(external.get('request'))
    if request is None:
        request = copy.deepcopy(binding.get('request'))
    if request is None and binding.get('file') is not None:
        request = c.decode(_read(root, binding['file'], read_source))
    negative = None
    if request is not None:
        for field in ('prompt_field', 'model_field', 'operation_field', 'count_field', 'negative_field'):
            path = binding.get(field)
            if path is not None and rc.present(request, path):
                if field == 'negative_field':
                    negative = rc.get(request, path)
                rc.put(request, path, None)
        slots = external.get('media_slots') or [row['field'] for row in binding.get('reference_fields', [])]
        for path in slots:
            if rc.present(request, path):
                rc.put(request, path, None)
    reference_text = binding.get('reference_text')
    if reference_text is not None and binding.get('negative_field') is not None:
        negative = reference_text['channels']['negative_prompt']['source_text']
    target = {key: copy.deepcopy(binding[key]) for key in
        ('model_field', 'model_identity', 'operation_field', 'schema', 'syntax', 'vocabulary_record') if key in binding}
    for key in ('schema', 'vocabulary_record'):
        if key in target:
            target[key] = _evidence(root, target[key], external.get('source_files') or {},
                                    read_source=read_source, retained=retained)
    if isinstance(target.get('model_identity'), dict) and 'evidence' in target['model_identity']:
        target['model_identity']['evidence'] = _evidence(root, target['model_identity']['evidence'],
            external.get('source_files') or {}, read_source=read_source, retained=retained)
    controls = {'request': request, **{key: binding[key] for key in ('count', 'count_field') if key in binding}}
    transport = {'slots': external.get('media_slots') or [row['field'] for row in binding.get('reference_fields', [])]}
    wording_fields = {key: copy.deepcopy(binding[key]) for key in ('prompt_field', 'negative_field') if key in binding}
    return {'controls': controls, 'negative': negative, 'wording_fields': wording_fields,
            'target': target, 'transport': transport}


def _transport(root: Path, value: dict | None, external: dict, *, read_source=None, retained=False):
    if value is None or not set(value).intersection({'field', 'local_file', 'value', 'evidence'}):
        return None
    evidence = copy.deepcopy(value.get('evidence'))
    if isinstance(evidence, dict) and isinstance(evidence.get('path'), str):
        path = evidence.pop('path')
        witness = (external.get('source_files') or {}).get(path)
        digest = evidence.get('sha256') or (witness.get('sha256') if isinstance(witness, dict) else witness)
        if not retained or digest is None:
            digest = c.digest(_read(root, path, read_source))
        evidence['sha256'] = digest
    return {'field': value.get('field'), 'local_file': value.get('local_file') is True,
            'value': copy.deepcopy(value.get('value')), 'evidence': evidence}


def _source_rows(root: Path, authored: dict, task: dict, *, basis: dict | None,
                 read_source=None) -> tuple[list, list]:
    identity, references = [], []
    for row in task.get('sources', []):
        if row.get('role') == 'brief' or row.get('disposition') != 'applied':
            continue
        # Local subject identity is compared at its editable specification.
        if row.get('definition_owner') is not None:
            continue
        source = (basis or {}).get('sources', {}).get(row.get('id'))
        digest = (authored.get('source_files') or {}).get(row.get('path'))
        if source is not None:
            from authoring_work import source_bytes
            digest = c.digest(source_bytes(source))
        if digest is None:
            digest = c.digest(_read(root, (row.get('origin') or {}).get('path') or row['path'], read_source))
        selected = {key: copy.deepcopy(row[key]) for key in
                    ('id', 'role', 'disposition', 'locator', 'reason', 'identity', 'applications') if key in row}
        selected['content'] = digest
        (identity if row.get('identity') or row.get('role') == 'definition' else references).append(selected)
    return identity, references


def _identity_sources(root: Path, choices: dict, task: dict, *, basis: dict | None,
                      read_source=None, retained=False) -> list[dict]:
    """Use the identity owner's common form for direct and derived sources."""
    import authoring_work
    import production_identity
    import production_identity_boundary as boundary
    authored = choices.get('authoring') or {}
    witnesses = dict(authored.get('source_files') or {})
    references = authored.get('references') or {}
    witnesses.update(references.get('source_files') or {})
    external = choices.get('external') or {}
    witnesses.update(external.get('source_files') or {})
    delivery = (external.get('reference_delivery') or {}).get('choices') or {}
    witnesses.update(delivery.get('source_files') or {})
    captured = {}
    if retained:
        raw_by_hash = {source['sha256']: authoring_work.source_bytes(source)
                       for source in (basis or {}).get('sources', {}).values()}
        for path, witness in witnesses.items():
            digest = witness.get('sha256') if isinstance(witness, dict) else witness
            if digest in raw_by_hash:
                captured[path] = raw_by_hash[digest]
    def acquire(path):
        return captured[path] if path in captured else _read(root, path, read_source)
    selected = production_identity.source_snapshot(task, acquire, choices=choices,
                                                   basis=None if retained else basis)
    if selected['unresolved']:
        raise ValueError('; '.join(row['message'] for row in selected['unresolved']))
    result = {}
    for source in selected['sources']:
        source = copy.deepcopy(source)
        if retained:
            witness = witnesses.get(source.get('path'))
            digest = witness.get('sha256') if isinstance(witness, dict) else witness
            if digest is not None:
                source['sha256'] = digest
                proof = (source.get('authority') or {}).get('source')
                if isinstance(proof, dict) and proof.get('kind') == 'supplied-file':
                    proof['sha256'] = digest
                    if isinstance(witness, dict) and witness.get('media_type'):
                        proof['media_type'] = witness['media_type']
        value = boundary.normalize_source(source)
        if value.get('unresolved'):
            raise ValueError(value['unresolved'])
        # State identity nodes own their selected values independently of the
        # scene fields that share a graph container.
        value = boundary._comparison_key(value)
        result[c.content_id(value)] = value
    return sorted(result.values(), key=lambda row: (row['id'], c.content_id(row)))


def _references(root: Path, references, external: dict, *, read_source=None, retained=False):
    """Compare selected source uses, preserving attachment order and carrier bytes."""
    from production_reference_inputs import _authored_rows
    choices = references
    if external.get('reference_delivery') is not None:
        choices = external['reference_delivery']['choices']
    rows = list(_authored_rows(choices)) if isinstance(choices, dict) else []
    if not rows and external.get('image_input') is not None:
        plan = external['image_input']
        if isinstance(plan, str):
            plan = c.decode(_read(root, plan, read_source))
        rows = plan.get('references', [])
    external_plan = external.get('image_input')
    if isinstance(external_plan, str):
        external_plan = c.decode(_read(root, external_plan, read_source))
    bound_transports = {row['reference']: row for row in
        ((external_plan or {}).get('external_request') or {}).get('reference_fields', [])}
    result = []
    for row in rows:
        source = copy.deepcopy(row.get('source') or row.get('file') or {})
        if isinstance(source, str):
            source = {'path': source}
        path = source.get('resolved_path') or source.get('path')
        if path:
            witnesses = (choices or {}).get('source_files') or external.get('source_files') or {}
            witness = witnesses.get(path)
            digest = source.get('sha256') or row.get('sha256') or (witness.get('sha256') if isinstance(witness, dict) else witness)
            if not retained or digest is None:
                raw = (c.read(Path(path)) if read_source is None and Path(path).is_absolute()
                       else _read(root, path, read_source))
                digest = c.digest(raw)
            source = {key: value for key, value in source.items()
                      if key not in {'path', 'resolved_path', 'media_type'}}
            source['sha256'] = digest
        identifier = row.get('id') or row.get('reference_id') or source.get('reference_id')
        result.append({'id': identifier,
            'role': row.get('role'), 'source': source,
            'transport': _transport(root, row.get('transport') or bound_transports.get(identifier), external,
                                    read_source=read_source, retained=retained),
            **{key: copy.deepcopy(row[key]) for key in ('subject_uses', 'use_for', 'do_not_transfer',
                'intended_influence', 'selected_controls', 'control_expressions') if key in row}})
    selected_controls = ('transport_mode', 'max_side') if result else ()
    plan_choices = copy.deepcopy((choices or {}).get('reference_use_plan'))
    if isinstance(plan_choices, dict):
        plan_choices.pop('items', None)
    state_choices = copy.deepcopy((choices or {}).get('reference_selection'))
    if isinstance(state_choices, dict):
        state_choices.pop('selected_references', None)
        state_choices.pop('selection_sha256', None)
    return {'rows': result, 'zero_reference_reason': (choices or {}).get('zero_reference_reason'),
        'plan': plan_choices, 'state': state_choices,
        **{key: copy.deepcopy(choices[key]) for key in selected_controls if isinstance(choices, dict) and key in choices}}


def _uploads(root: Path, rows: list, authored: dict, *, read_source=None, retained=False) -> list:
    result = []
    for row in rows:
        digest = (authored.get('source_files') or {}).get(row['file']) if retained else None
        if digest is None:
            digest = c.digest(_read(root, row['file'], read_source))
        result.append({'sha256': digest, 'url': row['url']})
    return result


def _snapshot(root: Path, choices: dict, task: dict, *, basis: dict | None = None,
              read_source=None, retained=False) -> dict:
    authored = choices.get('authoring') or {}
    docs = {key: _selected(root, value, text=key in TEXT_DOCUMENTS, read_source=read_source)
            for key, value in (authored.get('documents') or {}).items()}
    _document_witnesses(docs)
    delivery = authored.get('delivery') or {}
    text = (_selected(root, {key: delivery[key] for key in ('file', 'field') if key in delivery},
                      text=True, read_source=read_source) if 'file' in delivery else delivery.get('content'))
    generation = authored.get('generation') or {}
    specification = copy.deepcopy(docs.pop('production_spec', None))
    definitions = []
    if isinstance(specification, dict):
        specification.pop('target_model', None)
        render = specification.pop('render_intent', None)
        for subject in specification.get('subjects', []):
            if not isinstance(subject, dict):
                raise ValueError('production specification subject is not an object')
            definitions.append({key: subject.pop(key) for key in tuple(subject) if key in DEFINITION_FIELDS})
            subject['id'] = definitions[-1].get('id')
    else:
        render = None
    if generation.get('render_intent') is not None:
        render = copy.deepcopy(generation['render_intent'])
    if isinstance(render, dict) and render.get('prompt_expression') == {'document': 'delivery'}:
        render['prompt_expression'] = text or ''
    # A text change can alter the expression binding without changing finish.
    if isinstance(render, dict):
        render.pop('prompt_expression', None)
    task_value = {key: copy.deepcopy(task[key]) for key in TASK_DEPICTION if key in task}
    if isinstance(task_value.get('direction'), dict):
        task_value['direction'].pop('basis', None)
    source_rows, source_references = _source_rows(root, authored, task,
        basis=None if retained else basis, read_source=read_source)
    identity = _identity_sources(root, choices, task, basis=basis, read_source=read_source, retained=retained)
    definitions_from_sources = [row for row in source_rows if not row.get('identity')]
    external = choices.get('external') or {}
    external_owners = _external_owners(root, external, read_source=read_source, retained=retained)
    references = _references(root, authored.get('references'), external, read_source=read_source, retained=retained)
    references['sources'] = source_references
    references['external_transport'] = external_owners['transport']
    references['uploads'] = _uploads(root, task.get('upload_sources') or [], authored,
                                     read_source=read_source, retained=retained)
    semantic = task.get('semantic_edit')
    if isinstance(semantic, str):
        semantic = c.decode(_read(root, semantic, read_source))
    target = copy.deepcopy(choices.get('target'))
    if isinstance(target, dict):
        # Assessment is an inspection request, not a model input or target
        # selection. Native controls and vocabulary retain their own owners.
        for key in ('assessment', 'parameters', 'vocabulary_record'):
            target.pop(key, None)
        if target.get('kind') == 'acquired' and target.get('model_file'):
            target['model_content'] = _measured(root, target.pop('model_file'), authored.get('source_files') or {},
                                                 read_source=read_source, retained=retained)
        if target.get('kind') == 'external' and isinstance(target.get('model'), dict) and 'evidence' in target['model']:
            target['model']['evidence'] = _evidence(root, target['model']['evidence'], external.get('source_files') or {},
                                                   read_source=read_source, retained=retained)
    parameters = docs.pop('parameters', None)
    rendition = {key: docs.pop(key) for key in tuple(docs) if key in
                 {'negative', 'integrated_prompt', 'native_negative', 'negative_provenance', 'retrieval_record'}}
    rendition['delivery'] = text
    rendition['translation_notes'] = delivery.get('translation_notes')
    rendition['external_negative'] = external_owners['negative']
    rendition['external_wording_fields'] = external_owners['wording_fields']
    vocabulary = (choices.get('target') or {}).get('vocabulary_record')
    rendition['vocabulary_record'] = (_measured(root, vocabulary, authored.get('source_files') or {},
        read_source=read_source, retained=retained) if vocabulary is not None else None)
    authored_contract = task.get('authored') or {}
    rendition['authored_prompt_field'] = authored_contract.get('prompt_field')
    negative = authored_contract.get('negative')
    rendition['authored_negative'] = ({'field': negative.get('field'), 'content': _measured(root, negative['path'],
        authored.get('source_files') or {}, read_source=read_source, retained=retained)} if negative is not None else None)
    for key in ('negative_transport', 'critical_avoidance_integrated'):
        if key in generation:
            rendition[key] = generation[key]
    generation_fields = {'model', 'service', 'count', 'seed', 'continuity', 'render_intent',
                         'negative_transport', 'critical_avoidance_integrated', 'brief'}
    return {
        'definition': {'subjects': definitions, 'sources': identity, 'definitions': definitions_from_sources,
                       'continuity': generation.get('continuity'), 'visual': choices.get('visual')},
        'source-authority': {row['id']: {key: row[key] for key in ('subject_ids', 'selectors', 'authority') if key in row}
                             for row in identity},
        'depiction': {'task': task_value, 'specification': specification, 'documents': docs,
                     'semantic_edit': semantic, 'brief': generation.get('brief')},
        'rendition': rendition,
        'controls.parameters': {'parameters': parameters,
            'target_parameters': (choices.get('target') or {}).get('parameters'),
            **{key: generation[key] for key in ('seed', 'count') if key in generation},
            'upscale': authored.get('upscale'), 'external': external_owners['controls']},
        'controls.render-intent': render,
        'target': {'selection': target, 'external': external_owners['target']},
        'references': references, 'recording': {'destination': task.get('recording'),
            'authored_result': {key: authored_contract[key] for key in ('completion_state', 'requirements') if key in authored_contract}},
        'unknown': {'task': {key: task[key] for key in task if key not in TASK_KNOWN},
            'generation': {key: generation[key] for key in generation if key not in generation_fields},
            'external': {key: external[key] for key in external if key not in
                {'image_input', 'request', 'media_slots', 'source_files', 'source_uploads', 'reference_delivery'}}},
        'route': {key: task.get(key) for key in ('route', 'features', 'artifact', 'execution')},
    }


def evaluate(root: Path, choices: dict, task: dict, basis: dict, *, read_source=None) -> dict:
    declaration = basis.get('change_scope')
    if declaration is None:
        return {}
    validate_change_scope(declaration)
    if basis.get('operation') != 'amend' or not isinstance(basis.get('baseline'), dict):
        raise ValueError('change_scope requires amend with an actual acquired baseline')
    baseline = basis['baseline']
    observed, notices = set(), []
    try:
        if not isinstance(baseline.get('authoring'), dict):
            # A direct task amendment has a different delivery adapter. It
            # retains complete knowledge until its actual owners are comparable.
            observed.add('unknown')
            notices.append({'cause': 'baseline-owner-unavailable',
                'message': 'This baseline has no comparable editable owner projection; complete amendment knowledge is selected.',
                'required_action': 'Use draft-inputs from the retained run for a directly comparable editable amendment.'})
        else:
            previous_task = {**baseline['authoring']['task'], **(baseline.get('task_changes') or {})}
            previous = _snapshot(root, baseline, previous_task, basis=basis, read_source=read_source, retained=True)
            current = _snapshot(root, choices, task, basis=basis, read_source=read_source)
            observed.update(key for key in current if current[key] != previous[key])
    except (ValueError, OSError, TypeError, KeyError, AttributeError, IndexError) as exc:
        # Unknown sources cannot be treated as proof of unchanged content.
        observed.add('unknown')
        notices.append({'cause': 'selected-owner-unreadable', 'message': str(exc),
            'required_action': 'Repair the selected source or editable file named by the input diagnostics, then inspect the same draft again. '
                'Complete amendment knowledge remains selected while comparison is unavailable.'})
    if 'unknown' in observed and not notices:
        notices.append({'cause': 'unclassified-structured-owner',
            'message': 'An additional structured owner changed; complete amendment knowledge is selected.',
            'required_action': 'Read the complete returned scope and retain the ordinary input validation for the changed owner.'})
    profiles = {PROFILE_BY_SCOPE[item.split('.')[0]] for item in declaration['change']}
    for item in observed:
        if item in {'unknown', 'route'}:
            profiles.update(PROFILES)
        else:
            profiles.add(PROFILE_BY_SCOPE[item.split('.')[0]])
    conflicts = sorted(name for name in declaration['retain']
        if any(item == RETAIN_OWNER.get(name, name) or item.startswith(RETAIN_OWNER.get(name, name) + '.')
               for item in observed))
    return {'change_scope': copy.deepcopy(declaration), 'profiles': sorted(profiles),
            'observed_changes': sorted(observed), 'change_conflicts': conflicts, 'comparison_notices': notices}


def diagnostics(scope: dict, *, basis_path: str | None = None) -> list[dict]:
    conflicts = scope.get('change_conflicts') or []
    if not conflicts:
        return []
    return [{'field': 'authoring_work/basis/change_scope/retain', 'code': 'AUTHORING_WORK_INCOMPLETE',
        'phase': 'authoring', 'file': basis_path, 'pointer': '/change_scope/retain',
        'message': 'The declared retained owners have changed: ' + ', '.join(conflicts) + '.',
        'required_action': 'Restore the retained authored values, or revise change_scope.retain and '
            'change_scope.change in work-basis.json to state the intended amendment, then inspect the draft again.',
        'guidance': {'document_path': 'references/runtime/production-authoring.md#declare-a-retained-amendment'},
        'retained_conflicts': conflicts}]
