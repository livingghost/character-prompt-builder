"""Carry one authored use through the existing selection and adoption owners.

The public work plan owns the editable choices. This module captures their
observed basis, derives the mechanical records and resumes their exact effects.
The author supplies the actual choice, approval and stop judgments once.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import execution_contract as c
import production_curation_assessments as assessments
import production_permissions as permissions
import production_store as store
from production_diagnostics import ProductionError

SCOPES = {'delivery-only', 'studio-slot', 'sheet', 'catalog', 'withdraw'}


def _changed(message: str, **details) -> None:
    raise ProductionError('ADOPTION_DECISION_CHANGED', message, phase='curation', **details,
        required_action='Inspect the changed source or destination through the work plan and decide its current use. '
                        'The retained operation remains available for recovery and historical inspection.')


def _write(path: Path, value: dict) -> None:
    c.atomic(path, c.encoded(value), replace=path.exists())


def _authority_anchor(authority) -> dict:
    return {'task_id': authority.task_id, 'issuer': authority.document['issuer'],
            'declaration': [{key: item[key] for key in ('path', 'locator', 'sha256')}
                for item in authority.evidence if item['purpose'] == 'authority-declaration']}


def _directory(state_dir: Path, binding: dict) -> Path:
    return state_dir / 'revisions' / c.content_id(binding) if 'resume' in binding else state_dir


def _identity(operation: str, binding: dict, decision: dict) -> str:
    """A saved work item owns its retry identity, even when a later choice has the same meaning."""
    return c.content_id({'operation': operation, 'binding': binding, 'decision': decision})


def _production(root: Path, source: dict, *, scope: str) -> tuple[dict, object]:
    """Bind the captured result and the destination required by this use."""
    import production_operations as workflow
    import production_acceptance as acceptance
    import studio_workspace as studio
    loaded = workflow.read_run(root, source['run'])
    candidate = source['candidate']
    captured = workflow.find(loaded.rows, 'candidate', candidate)
    review = workflow.latest_review(loaded.rows, candidate)
    result = {'input_sha256': loaded.prepared['input_sha256'], 'candidate': candidate,
              'review': review['sha256'], 'files': copy.deepcopy(captured['data']['files']),
              'selection': workflow.replaced_selection(loaded.rows)}
    if (scope != 'delivery-only' and loaded.prepared['task'].get('recording')
            and loaded.prepared['task']['artifact'] == 'image'):
        target, row = acceptance._target(root, source['run'], candidate, loaded=loaded)
        read = studio.StudioRead(root)
        current = (read.sheet(target['character'])['slots'].get(target['slot']) or {}).get('current')
        result.update(target=target, placement=row['placement']['sha256'],
            slot_acceptance=acceptance.slot_state(root, target['character'], target['slot']),
            canonical=None if current is None else c.content_id(current))
    return result, loaded


def _imported(root: Path, source: dict) -> tuple[dict, dict]:
    import studio_workspace as studio
    read = studio.StudioRead(root)
    row = read.iteration(source['character'], source['iteration'])
    if row.get('production') is not None:
        raise ValueError('Use the exact Production run and candidate recorded by this iteration.')
    target = {'character': source['character'], 'iteration_id': source['iteration'],
              'slot': studio.placement_slot(row)}
    current = (read.sheet(target['character'])['slots'].get(target['slot']) or {}).get('current')
    image = c.local(root, row['result']['path'])
    if c.sha256_file(image) != row['result']['sha256']:
        _changed('The imported image differs from its retained source.')
    return {'target': target, 'image': copy.deepcopy(row['result']),
            'package': copy.deepcopy(row.get('package')), 'package_attachment': copy.deepcopy(row.get('package_attachment')),
            'placement': row['placement']['sha256'],
            'slot_acceptance': studio.acceptance_state(root, target['character'], target['slot'], read=read),
            'canonical': None if current is None else c.content_id(current)}, row


def _sheet(root: Path, source: dict, *, withdrawal: bool = False) -> tuple[dict, dict]:
    import sheet_artifacts as fills
    path = c.local(root, source['sheet'])
    if withdrawal:
        value = fills.draft_withdrawal(path, source['slot'])
        if value['artifact_id'] != source['artifact']:
            _changed('The current sheet adoption belongs to another exact artifact.')
        artifact = fills._read(path)['slots'][source['slot']]['current']['artifact']
    else:
        value = fills.draft_adoption(path, source['slot'], source['artifact'], include_history=True)
        slot = fills._read(path)['slots'][source['slot']]
        artifacts = [*slot['candidates'], *[item['artifact'] for item in slot['history']]]
        if slot.get('current') is not None:
            artifacts.append(slot['current']['artifact'])
        artifact = next(item for item in artifacts if item['artifact_id'] == source['artifact'])
        provenance = fills.verify_artifact(artifact, path.parent)
        if (provenance.get('origin') or {}).get('kind') == 'production':
            raise ValueError('Use the exact Production run and candidate recorded by this sheet artifact.')
    current = fills._read(path)['slots'][source['slot']].get('current')
    return {'sheet_decision': value, 'artifact': artifact,
            'current_acceptance': None if current is None else c.content_id(current)}, value


def resolve_source(root: Path, source: dict) -> dict:
    """Resolve a sheet projection's exact origin to its existing curation owner."""
    if source.get('kind') != 'sheet':
        return source
    if not source.get('artifact'):
        return source
    import sheet_artifacts as fills
    path = c.local(root, source['sheet'])
    slot = fills._read(path)['slots'][source['slot']]
    artifacts = [*slot['candidates'], *[item['artifact'] for item in slot['history']]]
    if slot.get('current') is not None:
        artifacts.append(slot['current']['artifact'])
    artifact = next((item for item in artifacts if item['artifact_id'] == source['artifact']), None)
    if artifact is None:
        raise ValueError('Choose an exact candidate, current or historical sheet artifact.')
    origin = fills.verify_artifact(artifact, path.parent).get('origin') or {}
    if origin.get('kind') == 'production':
        import production_operations as workflow
        import production_acceptance as acceptance
        resolved = {'kind': 'production', 'run': origin['run'], 'candidate': origin['candidate']}
        loaded = workflow.read_run(root, resolved['run'])
        current = {'target': acceptance._target(root, resolved['run'], resolved['candidate'], loaded=loaded)[0]}
        image_sha = workflow.find(loaded.rows, 'candidate', resolved['candidate'])['data']['files'][0]['sha256']
    elif origin.get('kind') == 'external-import' and origin.get('iteration_id') is not None:
        c.text(origin.get('character'), 'the imported iteration origin character')
        resolved = {'kind': 'imported', 'character': origin['character'], 'iteration': origin['iteration_id']}
        current, _ = _imported(root, resolved)
        image_sha = current['image']['sha256']
    else:
        return source
    target = current['target']
    if (target['slot'] != source['slot'] or image_sha != artifact['image']['sha256'] or
            c.local(root, f'characters/{target["character"]}/sheet/sheet-data.json') != path):
        _changed('The selected sheet projection differs from its original image or current destination. '
                 'Inspect its exact origin and choose the intended current placement.')
    return resolved


def _continuity(root: Path, target: dict) -> dict | None:
    import studio_workspace as studio
    read = studio.StudioRead(root)
    row = read.iteration(target['character'], target['iteration_id'])
    if not row.get('package'):
        import adoption_workflow as adoption
        adoption.require_adoption_source(root, target['character'], row, read=read)
    _, package = read._package(row['package'])
    if package.get('artifact_type') == 'upscale-package':
        _, package = read._package(package['source_generation_package'], verify=True)
    subjects = package['visual_continuity']['subjects']
    if len(subjects) != 1:
        raise ValueError('Identity adoption needs a single-subject candidate.')
    subject = next(iter(subjects.values()))
    if subject['continuity'] == 'undecided' or subject['character_id'] is None:
        return {'character_id': subject['character_id'], 'continuity': None}
    return None


def _instruction_context(root: Path, path: str, locator: str, raw: bytes) -> dict:
    """Locate an instruction without selecting it for the current use."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = None
    return {'path': str(c.local(root, path)), 'locator': locator,
        'sha256': c.digest(raw), 'bytes': len(raw),
        'text_preview': None if text is None else text[:512],
        'preview_complete': text is not None and len(text) <= 512}


def _answer_contract(root: Path, choices: dict) -> dict:
    """Explain the current editable form without a lower-level generated schema."""
    fields = {
        'reason': 'String: why the exact result is being selected for this destination, including material limitations.',
        'approval': 'Choose the actual instruction for this use once as evidence {path, locator}, with the '
                    'actual actor and direct or delegated mode. Prior authority instruction is read-only context, not '
                    'the chosen source. When both selection and adoption are required, this instruction must explicitly '
                    'authorize both operations shown in authority_requirements. The requested destination alone grants no permission.',
        'stop_assessments': 'Keep each displayed id and condition. Set clear to true only from actual evidence '
                            'and write that evidence. An empty array means no current stop conditions.',
        'continuity_decision': 'character_id is the actual identity string (or null for one-off); continuity is '
                               'recurring or one-off. The selected approval instruction also supplies continuity '
                               'when basis is omitted. If another instruction establishes identity or continuity, '
                               'add basis {path, locator} for that distinct source. Hashes are derived.',
        'owner_acceptance': 'Owner-approved allowance: criteria lists the displayed criterion IDs and unresolved '
                            'lists the exact findings the actual owner explicitly accepts.',
        'review': 'Actual observation and conclusion strings, with limitations as an array of strings.',
        'license': 'The actual license string for the intended catalog use, when required.',
        'grant_choices': 'For each displayed operation, choose the number of its applicable grant option.',
    }
    return {'paths_relative_to': str(root),
            'fields': {name: fields[name] for name in choices},
            'document': str(Path(__file__).resolve().parents[1] / 'references/runtime/production-work-plan.md'),
            'section': 'Select and adopt'}


def draft(root: Path, source: dict, destination: dict) -> dict:
    """Expose only current semantic choices; return observed bindings separately."""
    import production_operations as workflow
    from route_reading import curation_action
    requested_source = copy.deepcopy(source)
    source, destination = resolve_source(root, copy.deepcopy(source)), copy.deepcopy(destination)
    scope = destination['scope']
    if scope not in SCOPES:
        raise ValueError('Unknown curation destination scope.')
    if source.get('kind') == 'sheet' and not source.get('artifact'):
        if scope != 'withdraw':
            raise ValueError('Choose the exact sheet artifact for its intended use.')
        import sheet_artifacts as fills
        held = fills.draft_withdrawal(c.local(root, source['sheet']), source['slot'])
        source = resolve_source(root, {**source, 'artifact': held['artifact_id']})
    kind = source['kind']
    if kind not in {'production', 'imported', 'sheet'}:
        raise ValueError('Curation source must be production, imported or sheet.')
    choices = {'reason': '', 'approval': {'evidence': {'path': '', 'locator': ''},
               'actor': None, 'mode': None}, 'stop_assessments': []}
    binding = {'source': source, 'destination': destination}
    evidence = {}
    authority = None
    authority_requirements = None
    if kind == 'production':
        snapshot, loaded = _production(root, source, scope=scope)
        reviewed = workflow.find(loaded.rows, 'review', snapshot['review'])
        evidence = {'artifacts': [{'path': str(loaded.directory / 'objects' / item['sha256']),
                                   'sha256': item['sha256']} for item in snapshot['files']],
                    'review': {'event': snapshot['review'], 'conclusion': reviewed['data']['review']['conclusion'],
                               'findings': workflow.selection_requirements(loaded.prepared, reviewed)}}
        binding['snapshot'] = snapshot
        authority = workflow.current_authority(root, loaded.prepared)
        binding['authority_anchor'] = _authority_anchor(authority)
        evidence['prior_authority_instruction'] = [
            _instruction_context(root, item['path'], item['locator'], item['raw'])
            for item in authority.evidence if item['purpose'] == 'authority-declaration']
        try:
            _, retained, _ = workflow.current_selection(loaded.prepared, loaded.rows)
            already_selected = retained['candidate'] == source['candidate']
        except ValueError:
            already_selected = False
        needs_selection = scope != 'withdraw' and not (already_selected and scope in {'sheet', 'catalog', 'delivery-only'})
        operations = [{'operation': 'select', 'targets': ['delivery']}] if needs_selection else []
        if scope in {'sheet', 'catalog'}:
            operations.append({'operation': 'adopt', 'targets': ['canon:' + scope]})
        requirement = permissions.grant_requirements(authority.document, operations)
        authority_requirements = []
        for row in requirement['requirements']:
            eligible = [item['grant'] for item in row['candidates'] if item['eligible']]
            required_action = (
                'Use this current grant only within the actual approval and assessed stop conditions.'
                if row['selected_grant'] is not None else
                'Choose one displayed grant number in grant_choices.' + row['operation'] + '.'
                if eligible else
                'Choose approval.evidence only from an actual instruction authorizing ' + row['operation'] +
                ' for ' + ', '.join(row['targets']) + '; record its actual actor and mode in the same answer.')
            authority_requirements.append({key: copy.deepcopy(row[key])
                for key in ('operation', 'targets', 'selected_grant')})
            authority_requirements[-1]['required_action'] = required_action
        grants = {row['operation']: row['selected_grant'] for row in requirement['requirements']}
        options = {}
        for row in requirement['requirements']:
            eligible = [item['grant'] for item in row['candidates'] if item['eligible']]
            if len(eligible) > 1:
                operation = row['operation']
                options[operation] = []
                for number, identifier in enumerate(eligible, 1):
                    grant = next(item for item in authority.document['grants'] if item['id'] == identifier)
                    options[operation].append({'number': number, 'grant': identifier,
                        **{key: copy.deepcopy(grant.get(key)) for key in
                           ('actor', 'mode', 'targets', 'effective_at', 'expires_at', 'reason')},
                        'terms': assessments.authority_terms(authority, identifier, operation,
                            scope if operation == 'adopt' else None)})
        if options:
            choices['grant_choices'] = {operation: None for operation in options}
            binding['grant_options'] = options
        binding['grants'] = grants
        binding['authority_terms'] = {op: assessments.authority_terms(authority, grant, op,
            scope if op == 'adopt' else None) for op, grant in grants.items() if grant is not None}
        binding['stop_conditions'] = copy.deepcopy(authority.document['stop_conditions'])
        choices['stop_assessments'] = assessments.unanswered(authority, describe=True)
        actors = {item['actor'] for item in authority.document['grants'] if item['id'] in grants.values()}
        modes = {item['mode'] for item in authority.document['grants'] if item['id'] in grants.values()}
        choices['approval'].update(actor=next(iter(actors)) if len(actors) == 1 else None,
                                   mode=next(iter(modes)) if len(modes) == 1 else None)
        if grants and all(grant is not None for grant in grants.values()) and (len(actors) > 1 or len(modes) > 1):
            choices['approval'].pop('actor')
            choices['approval'].pop('mode')
        needed = workflow.selection_requirements(loaded.prepared,
            workflow.find(loaded.rows, 'review', snapshot['review']))
        if scope != 'withdraw' and needed['unassessed_hard_criteria']:
            raise ProductionError('REVIEW_INCOMPLETE', 'Required criteria need actual observation and review.',
                phase='curation', run=source['run'], candidate=source['candidate'],
                required_action='Complete the listed hard criteria through the work plan review step.',
                selection_requirements=needed)
        if scope != 'withdraw' and (needed['nonpassing_hard_criteria'] or needed['unresolved_indices']):
            choices['owner_acceptance'] = None
            binding['review_findings'] = {'criteria': needed['nonpassing_hard_criteria'],
                'unresolved': copy.deepcopy(workflow.find(loaded.rows, 'review', snapshot['review'])['data']['review']['unresolved'])}
        execution = loaded.prepared['task']['execution']
    elif kind == 'imported':
        snapshot, _ = _imported(root, source)
        evidence = {'artifacts': [{'path': str(c.local(root, snapshot['image']['path'])),
                                   'sha256': snapshot['image']['sha256']}], 'origin': source}
        binding['snapshot'] = snapshot
        execution = 'external'
        if scope != 'withdraw':
            choices['review'] = {'observation': '', 'conclusion': '', 'limitations': []}
    else:
        if scope not in {'sheet', 'withdraw'}:
            raise ValueError('A sheet artifact supports sheet adoption or withdrawal.')
        snapshot, _ = _sheet(root, source, withdrawal=scope == 'withdraw')
        binding['snapshot'] = snapshot
        image = snapshot['artifact']['image']
        evidence = {'artifacts': [{'path': str(c.local(root, source['sheet']).parent / image['path']),
                                   'sha256': image['sha256']}], 'origin': source}
        execution = 'external'
        if scope != 'withdraw':
            choices['review'] = {'observation': '', 'conclusion': '', 'limitations': []}
    if scope in {'studio-slot', 'sheet', 'catalog', 'withdraw'} and kind != 'sheet' and 'target' not in snapshot:
        raise ValueError('This destination requires the candidate\'s existing Studio recording.')
    if scope in {'sheet', 'catalog'} and kind != 'sheet':
        import adoption_workflow as adoption
        influence = destination.get('influence')
        if influence not in adoption.INFLUENCES:
            raise ValueError('Choose the intended influence in the destination: ' + ', '.join(adoption.INFLUENCES) + '.')
        if snapshot['target']['slot'].startswith(('base.', 'canon.')) and influence != 'identity':
            raise ValueError('Base and canon slots require identity influence.')
        if influence == 'identity':
            continuity = _continuity(root, snapshot['target'])
            if continuity is not None:
                choices['continuity_decision'] = continuity
        if scope == 'catalog':
            choices['license'] = None
            raw = store.stable_bytes(root, destination['registration_file'])
            adoption.validate_registration_record(c.decode(raw))
            binding['registration_sha256'] = c.digest(raw)
            c.text(destination['pack_dir'], 'catalog destination')
    if scope == 'withdraw' and kind != 'sheet':
        import sheet_artifacts as fills
        target = snapshot['target']
        path = c.local(root, f'characters/{target["character"]}/sheet/sheet-data.json')
        binding['withdrawal'] = fills.draft_withdrawal(path, target['slot'])
        current = fills._read(path)['slots'][target['slot']]['current']
        origin = fills.verify_artifact(current['artifact'], path.parent).get('origin') or {}
        expected = ({'kind': 'production', 'run': source['run'], 'candidate': source['candidate']} if kind == 'production'
                    else {'kind': 'external-import', 'character': source['character'], 'iteration_id': source['iteration']})
        if any(origin.get(key) != value for key, value in expected.items()):
            _changed('The current canonical image belongs to another exact source; choose that source to withdraw it.')
    return {'choices': choices, 'binding': binding,
        'source': source, 'destination': destination, 'evidence': evidence,
        'answer_contract': _answer_contract(root, choices),
        **({'requested_source': requested_source} if requested_source != source else {}),
        **({'review_findings': binding['review_findings'], 'owner_acceptance_fields':
            {'criteria': 'IDs of assessed findings explicitly accepted by the owner.',
             'unresolved': 'Exact unresolved finding text explicitly accepted by the owner.'}}
           if binding.get('review_findings') else {}),
        **({'grant_options': {operation: [{key: value for key, value in item.items() if key != 'terms'}
                            for item in options] for operation, options in binding['grant_options'].items()}}
           if binding.get('grant_options') else {}),
        **({'acting_authority': {operation: {key: terms['grant'][key] for key in ('id', 'actor', 'mode')}
                                for operation, terms in binding['authority_terms'].items()}}
           if binding.get('authority_terms') else {}),
        **({'authority_requirements': authority_requirements} if authority_requirements is not None else {}),
        'reading_action': curation_action(root, execution=execution,
            scope='sheet' if scope == 'withdraw' else scope,
            source_kind='production-candidate' if kind == 'production' else 'imported-iteration',
            operation='withdraw' if scope == 'withdraw' else 'adopt'),
        'required_action': 'Observe the actual selected artifact and complete the displayed choices from the actual '
            'instruction. One decision covers exactly the named destination; advance derives its formal records.'}


def _resolved(binding: dict, decision: dict) -> tuple[dict, dict]:
    """Bind an explicit numbered grant choice; fill only identities owned by that grant."""
    effective, value = copy.deepcopy(binding), copy.deepcopy(decision)
    options = binding.get('grant_options', {})
    choices = value.get('grant_choices', {})
    if set(choices) != set(options):
        raise ValueError('Choose one displayed grant number for each operation that has several eligible grants.')
    for operation, entries in options.items():
        number = choices[operation]
        chosen = next((entry for entry in entries if type(number) is int and entry['number'] == number), None)
        if chosen is None:
            raise ValueError('Choose a displayed grant number for ' + operation + '.')
        effective['grants'][operation] = chosen['grant']
        effective['authority_terms'][operation] = copy.deepcopy(chosen['terms'])
    terms = list(effective.get('authority_terms', {}).values())
    covered = effective.get('grants') and all(value is not None for value in effective['grants'].values())
    for key in ('actor', 'mode'):
        supplied = value.get('approval', {}).get(key)
        values = {term['grant'][key] for term in terms}
        if supplied is None and len(values) == 1:
            value['approval'][key] = next(iter(values))
        elif covered and len(values) > 1:
            if supplied is not None:
                raise ValueError('Each selected operation has its own ' + key + '; use the displayed grants\' '
                                 'derived identities and keep this common field empty.')
            value['approval'].pop(key, None)
    return effective, value


def _continuity_basis(decision: dict) -> dict:
    """One instruction can own both judgments; a separate source stays explicit."""
    return decision['continuity_decision'].get('basis',
        {name: decision['approval']['evidence'][name] for name in ('path', 'locator')})


def _validate_choices(root: Path, decision: dict, binding: dict) -> dict[str, bytes]:
    allowed = {'reason', 'approval', 'stop_assessments', 'owner_acceptance', 'continuity_decision', 'review', 'license',
               'grant_choices'}
    if set(decision) - allowed:
        raise ValueError('Unknown curation choice fields: ' + ', '.join(sorted(set(decision) - allowed)))
    c.text(decision.get('reason'), 'curation reason')
    approval = decision['approval']
    covered = binding.get('grants') and all(value is not None for value in binding['grants'].values())
    if not covered:
        c.text(approval.get('actor'), 'actual authorized actor for the additional grant or local decision')
        if approval.get('mode') not in {'direct', 'delegated'}:
            raise ValueError('Record the actual direct or delegated authority mode for that additional grant or local decision.')
    else:
        for key in ('actor', 'mode'):
            values = {terms['grant'][key] for terms in binding['authority_terms'].values()}
            if approval.get(key) is not None and values != {approval[key]}:
                raise ValueError('The selected grants supply each operation\'s ' + key + '; use those displayed identities.')
    evidence = approval['evidence']
    c.text(evidence.get('locator'), 'actual instruction locator')
    raw = store.stable_bytes(root, evidence['path'])
    if not raw.strip():
        raise ValueError('Actual instruction evidence must be nonempty.')
    acquired = {'instruction': raw}
    if decision.get('continuity_decision') is not None:
        continuity = decision['continuity_decision']
        c.exact(continuity, {'character_id', 'continuity'} | ({'basis'} if 'basis' in continuity else set()),
                'curation continuity decision')
        if continuity['continuity'] not in {'recurring', 'one-off'}:
            raise ValueError('Choose recurring or one-off for the actual continuity decision.')
        if continuity['continuity'] == 'recurring' or continuity['character_id'] is not None:
            c.text(continuity['character_id'], 'the actual continuity character identity')
        basis = _continuity_basis(decision)
        c.exact(basis, {'path', 'locator'}, 'curation continuity basis')
        c.text(basis['locator'], 'the instruction locator establishing this continuity')
        if basis != {name: evidence[name] for name in ('path', 'locator')}:
            acquired['continuity'] = raw if basis['path'] == evidence['path'] else store.stable_bytes(root, basis['path'])
            if not acquired['continuity'].strip():
                raise ValueError('The selected continuity instruction must be nonempty.')
    expected = binding.get('stop_conditions', [])
    actual = decision.get('stop_assessments', [])
    if len(actual) != len(expected) or {item['id'] for item in actual} != {item['id'] for item in expected}:
        raise ValueError('Assess each current stop condition once for the complete intended use.')
    definitions = {item['id']: item['text'] for item in expected}
    for item in actual:
        if item.get('condition') != definitions[item['id']] or item.get('clear') is not True:
            raise ValueError('A stop condition is changed, active or unanswered.')
        c.text(item.get('evidence'), 'stop assessment evidence')
    if binding['source']['kind'] == 'production' and binding['destination']['scope'] != 'withdraw':
        import production_operations as workflow
        loaded = workflow.read_run(root, binding['source']['run'])
        allowance = _owner_acceptance({'binding': binding, 'decision': decision,
                                      'instruction_path': approval['evidence']['path']})
        if allowance is not None:
            allowance.update(principal=binding['authority_anchor']['issuer'],
                             evidence={**allowance['evidence'], 'sha256': c.digest(raw)})
        workflow.eligible(loaded.prepared,
            workflow.find(loaded.rows, 'review', binding['snapshot']['review']), allowance)
    if binding['source']['kind'] != 'production' and binding['destination']['scope'] != 'withdraw':
        review = decision['review']
        c.text(review['observation'], 'actual artifact observation')
        c.text(review['conclusion'], 'artifact review conclusion')
        if not isinstance(review['limitations'], list):
            raise ValueError('Review limitations must be a list.')
    return acquired


def _retained_continuity(root: Path, state: dict, intent: dict) -> dict | None:
    """Check the captured source chosen by the author, independently of approval."""
    choice = state['decision'].get('continuity_decision')
    evidence = state.get('continuity_evidence')
    if choice is None:
        if evidence is not None or intent.get('continuity_evidence') is not None:
            _changed('Continuity evidence is present without an authored continuity decision.')
        return None
    basis = _continuity_basis(state['decision'])
    shared = basis == {name: state['decision']['approval']['evidence'][name] for name in ('path', 'locator')}
    retained = intent.get('continuity_evidence')
    if shared and 'continuity_evidence' not in state and 'continuity_evidence' not in intent:
        # This is the same declared instruction, not a version exception or a
        # reread of the mutable source. Its formal capture already owns the bytes.
        retained = {**intent['instruction'], 'locator': basis['locator']}
        evidence = {**retained, 'path': state['instruction_path']}
    if (not isinstance(evidence, dict) or evidence != retained
            or evidence.get('locator') != basis.get('locator')
            or (shared and evidence.get('sha256') != intent['instruction']['sha256'])
            or c.sha256_file(c.local(root, evidence['path'])) != evidence.get('sha256')):
        _changed('The retained continuity instruction differs from its authored decision and formal intent.')
    return evidence


def reassess(root: Path, state_dir: Path, *, binding: dict) -> dict:
    """Reopen only current judgments while retaining an already committed selection or claim."""
    import production_adoption as adoption
    import production_operations as workflow
    directory = _directory(state_dir.resolve(), binding)
    state = c.load(directory / 'progress.json')
    operation = directory.relative_to(root.resolve()).as_posix()
    if state['binding'] != binding or state.get('operation') != operation or state['identity'] != _identity(
            operation, binding, state['decision']):
        _changed('The retained operation differs from the requested reassessment.')
    if 'result' in state:
        raise ValueError('This use already completed. Inspect its verified receipt or create a new intended use.')
    result = draft(root, binding['source'], binding['destination'])
    current = result['binding']
    previous_resume = binding.get('resume', {})
    claim = previous_resume.get('claim')
    if binding['source']['kind'] == 'production':
        loaded = workflow.read_run(root, binding['source']['run'])
        file = directory / 'adoption.json'
        if file.exists():
            retained = adoption._claim_for_decision(loaded, file.read_bytes())
            if retained is not None:
                claim = retained['sha256']
        if claim is not None:
            # A retained claim owns its original canonical approval. Current
            # permission may change; its exact image and destination do not.
            payload = workflow.find(loaded.rows, 'adoption-claim', claim)['data']['intent']['payload']
            if payload['candidate'] != binding['source']['candidate']:
                _changed('A retained claim belongs to another exact candidate.')
    current['resume'] = {'identity': state['identity'],
        'selection': copy.deepcopy(state.get('selection') or previous_resume.get('selection')), 'claim': claim}
    previous = state['decision']
    retained_path = (directory / 'instruction.txt').relative_to(root.resolve()).as_posix()
    result['evidence']['prior_use_instruction'] = [_instruction_context(root, retained_path,
        previous['approval']['evidence']['locator'], store.stable_bytes(root, retained_path))]
    result['choices']['reason'] = previous['reason']
    old_stops = {item['id']: item for item in previous['stop_assessments']}
    for item in result['choices']['stop_assessments']:
        old = old_stops.get(item['id'])
        if old is not None and item['condition'] == old['condition']:
            item.update(clear=old['clear'], evidence=old['evidence'])
    changed = [key for key in ('snapshot', 'grants', 'stop_conditions', 'authority_terms', 'authority_anchor')
               if binding.get(key) != current.get(key)]
    result['changes'] = changed
    source_fields = (set(binding['snapshot']) | set(current['snapshot'])) - {'selection', 'slot_acceptance'}
    judgment_source_changed = any(binding['snapshot'].get(key) != current['snapshot'].get(key) for key in source_fields)
    for key in ('review', 'continuity_decision', 'owner_acceptance', 'license'):
        if key in result['choices'] and key in previous and not judgment_source_changed:
            result['choices'][key] = copy.deepcopy(previous[key])
    if claim is not None:
        result['choices'].pop('continuity_decision', None)
        result['choices'].pop('license', None)
    if current.get('grants') and any(value is None for value in current['grants'].values()):
        result['choices']['approval']['evidence'] = {'path': '', 'locator': ''}
    result['required_action'] = ('Assess the displayed changed conditions and current actual permission. '
        'The recorded selection and retained adoption claim remain the same; advance records only the current reassessment.')
    return result


def _owner_acceptance(state: dict) -> dict | None:
    """Bind explicitly accepted findings to the same actual approval once."""
    choice = state['decision'].get('owner_acceptance')
    if choice is None:
        return None
    c.exact(choice, {'criteria', 'unresolved'}, 'explicit accepted review findings')
    findings = state['binding'].get('review_findings') or {'criteria': [], 'unresolved': []}
    if not isinstance(choice['criteria'], list) or not isinstance(choice['unresolved'], list):
        raise ValueError('Accepted criteria and unresolved findings must be lists.')
    if set(choice['unresolved']) - set(findings['unresolved']):
        raise ValueError('An accepted finding must name the exact retained review text.')
    # The caller supplies the Studio-relative instruction path with the state;
    # no review evidence digest or finding-array index is authored by the agent.
    return {'criteria': choice['criteria'],
            'unresolved_indices': [index for index, text in enumerate(findings['unresolved']) if text in choice['unresolved']],
            'evidence': {'path': state['instruction_path'], 'locator': state['decision']['approval']['evidence']['locator']},
            'reason': state['decision']['reason']}


def _check_authority(root: Path, binding: dict) -> None:
    if binding['source']['kind'] != 'production':
        return
    import production_operations as workflow
    loaded = workflow.read_run(root, binding['source']['run'])
    authority = workflow.current_authority(root, loaded.prepared)
    anchor = binding.get('authority_anchor')
    if anchor is not None:
        current = _authority_anchor(authority)
        declarations = {c.content_id(item) for item in current['declaration']}
        if (anchor['task_id'], anchor['issuer']) != (current['task_id'], current['issuer']) \
                or not all(c.content_id(item) in declarations for item in anchor['declaration']):
            _changed('The authority issuer or actual instruction changed after this use was decided.')
    if list(authority.document['stop_conditions']) != binding['stop_conditions']:
        _changed('Current stop conditions changed after this use was decided.')
    for operation, old in binding['authority_terms'].items():
        if not any(item['id'] == binding['grants'][operation] for item in authority.document['grants']):
            raise ProductionError('GRANT_REVOKED', 'The selected grant was removed after this use was decided.',
                phase='curation', grant=binding['grants'][operation],
                required_action='Reassess this saved use from current actual authority through the work plan.')
        current = assessments.authority_terms(authority, binding['grants'][operation], operation,
            binding['destination']['scope'] if operation == 'adopt' else None)
        declarations = {c.content_id(item) for item in current['declaration']}
        if current['grant'] != old['grant'] or not all(c.content_id(item) in declarations for item in old['declaration']):
            _changed('The relevant grant or its actual instruction changed after this use was decided.')


def _check_source(root: Path, binding: dict, *, selected: bool = False) -> None:
    source, scope, expected = binding['source'], binding['destination']['scope'], binding['snapshot']
    if source['kind'] == 'production':
        actual, _ = _production(root, source, scope=scope)
        keys = ['input_sha256', 'candidate', 'review', 'files']
        if not selected:
            keys.append('selection')
    elif source['kind'] == 'imported':
        actual, _ = _imported(root, source)
        keys = ['image', 'package', 'package_attachment']
    else:
        actual, _ = _sheet(root, source, withdrawal=scope == 'withdraw')
        keys = ['sheet_decision', 'current_acceptance']
    if scope != 'delivery-only' and 'target' in expected:
        keys += ['target', 'placement', 'canonical']
        if not selected:
            keys.append('slot_acceptance')
    if any(actual.get(key) != expected.get(key) for key in keys):
        _changed('The reviewed source or intended destination changed after this use was decided.',
                 expected={key: expected.get(key) for key in keys}, actual={key: actual.get(key) for key in keys})


def _grant(root: Path, directory: Path, state: dict, operation: str) -> str:
    import production_authority_drafts as drafts
    import production_operations as workflow
    binding, decision = state.get('effective_binding', state['binding']), state['decision']
    source, destination = binding['source'], binding['destination']
    loaded = workflow.read_run(root, source['run'])
    authority = workflow.current_authority(root, loaded.prepared)
    selected = binding['grants'].get(operation)
    target = 'delivery' if operation == 'select' else 'canon:' + destination['scope']
    identifier = selected or 'curation-' + state['identity'][:24] + '-' + operation
    if any(item['id'] == identifier for item in authority.document['grants']):
        required = permissions.grant_requirements(authority.document,
            [{'operation': operation, 'targets': [target]}], grant=identifier)
        permissions.require_grants(required)
        return identifier
    if selected is not None:
        raise ProductionError('GRANT_REVOKED', 'The selected current grant was removed after this decision.',
            phase='curation', grant=selected,
            required_action='Reassess this saved use from current actual authority through the work plan.')
    history = store.read_history(root, 'authority:' + authority.task_id)
    if any(identifier == item['id'] for row in history.rows if row['event'] == 'authority-updated'
           for item in row['data']['authority']['grants']):
        raise ProductionError('GRANT_REVOKED', 'The grant derived for this saved use was removed afterwards.',
            phase='curation', grant=identifier,
            required_action='Reassess this saved use from current actual authority; record any renewed actual instruction once.')
    kwargs = {'phase': 'selection' if operation == 'select' else 'adoption', 'candidate': source['candidate']}
    if operation == 'adopt':
        kwargs.update(scope=destination['scope'], influence=destination['influence'],
            registration_file=state.get('registration_path'),
            pack_dir=Path(destination['pack_dir']) if destination.get('pack_dir') else None)
    evidence = (directory / 'instruction.txt').relative_to(root).as_posix()
    update = drafts.draft_authority_update(root, source['run'], evidence, **kwargs)['choices']
    update['evidence']['locator'] = decision['approval']['evidence']['locator']
    for grant in update['grants']:
        grant.update(id=identifier, actor=decision['approval']['actor'], mode=decision['approval']['mode'],
                     reason=decision['reason'], expires_at=decision['approval'].get('expires_at'))
    file = directory / ('authority-' + operation + '.json')
    _write(file, update)
    store.import_authority(root, file.relative_to(root).as_posix(), expected=authority.event['sha256'])
    return identifier


def _production_apply(root: Path, directory: Path, state: dict, *, settings=None,
                      continuity_evidence: dict | None = None) -> dict:
    import production_acceptance as acceptance
    import production_adoption as adoption
    import production_operations as workflow
    binding = state.get('effective_binding', state['binding'])
    source, destination, decision = binding['source'], binding['destination'], state['decision']
    run, candidate, scope = source['run'], source['candidate'], destination['scope']
    progress = directory / 'progress.json'
    # Recover already committed effects before testing permission for another
    # effect. Revocation ends future authority; it does not erase a completed
    # selection or canonical result whose receipt was not yet checkpointed.
    loaded = workflow.read_run(root, run)
    completed = [row for row in loaded.rows if row['event'] == 'completion']
    selection_file = directory / 'selection.json'
    if 'selection' not in state and completed and selection_file.exists():
        retained = acceptance._resumed(loaded.rows, c.digest(selection_file.read_bytes()))
        if retained is not None:
            state['selection'] = acceptance.accept(root, run, decision_file=selection_file.relative_to(root).as_posix())
            _write(progress, state)
    adoption_file = directory / 'adoption.json'
    if 'adoption' not in state and adoption_file.exists():
        held_claim = adoption._claim_for_decision(loaded, adoption_file.read_bytes())
        if held_claim is not None:
            results = [row for row in loaded.rows if row['event'] == 'adoption-result'
                       and row['data']['claim'] == held_claim['sha256']]
            if len(results) == 1:
                state['adoption'] = {**results[0], 'adoption_claim': held_claim['sha256']}
                _write(progress, state)
    if 'selection' in state and 'adoption' in state:
        return {'ok': True, 'scope': scope, 'selection': state['selection'], 'adoption': state['adoption']}
    if scope in {'delivery-only', 'studio-slot'} and 'selection' in state and completed:
        if scope == 'delivery-only' or not state['selection'].get('retained'):
            return {'ok': True, 'scope': scope, 'selection': state['selection']}
        saved = _saved_slot_use(root, state)
        if saved is not None:
            state['slot_use'] = saved
            _write(progress, state)
            return {'ok': True, 'scope': scope, 'selection': state['selection'], 'slot_use': saved}
    _check_authority(root, binding)
    resumed = state['binding'].get('resume')
    if resumed is not None and 'selection' not in state and resumed.get('selection') is not None:
        state['selection'] = copy.deepcopy(resumed['selection'])
        _write(progress, state)
    if 'selection' not in state:
        file = directory / 'selection.json'
        if not file.exists():
            _check_source(root, binding)
            loaded = workflow.read_run(root, run)
            try:
                selected, choice, _ = workflow.current_selection(loaded.prepared, loaded.rows)
            except ValueError:
                selected = choice = None
            if selected is not None and choice['candidate'] == candidate:
                state['selection'] = {'selection': selected['sha256'], 'retained': True}
                _write(progress, state)
            else:
                grant = _grant(root, directory, state, 'select')
                value = acceptance.draft(root, run, candidate, grant,
                    scope='delivery-only' if scope == 'delivery-only' else 'studio-slot')
                value.update(reason=decision['reason'], stop_assessments=[
                    {key: item[key] for key in ('id', 'clear', 'evidence')} for item in decision['stop_assessments']],
                             owner_acceptance=_owner_acceptance(state))
                _write(file, value)
        if 'selection' not in state:
            state['selection'] = acceptance.accept(root, run, decision_file=file.relative_to(root).as_posix())
            _write(progress, state)
    if scope in {'delivery-only', 'studio-slot'}:
        loaded = workflow.read_run(root, run)
        if not any(item['event'] == 'completion' for item in loaded.rows):
            state['selection'] = acceptance.accept(root, run)
            _write(progress, state)
        if scope == 'studio-slot' and state['selection'].get('retained'):
            state['slot_use'] = _slot_use(root, directory, state)
            _write(progress, state)
        return {'ok': True, 'scope': scope, 'selection': state['selection'],
                **({'slot_use': state['slot_use']} if 'slot_use' in state else {})}
    if 'adoption' not in state:
        file = directory / 'adoption.json'
        if not file.exists():
            _check_source(root, binding, selected=True)
            grant = _grant(root, directory, state, 'adopt')
            if resumed is not None and resumed.get('claim') is not None:
                value = adoption.draft_reassessment(root, run, resumed['claim'], grant=grant)
                value.update(reason=decision['reason'], additional_stop_assessments=decision['stop_assessments'])
            else:
                value = adoption.draft(root, run, candidate, scope=scope, influence=destination['influence'], grant=grant,
                    registration_file=state.get('registration_path'),
                    pack_dir=Path(destination['pack_dir']) if destination.get('pack_dir') else None)
                value.update(reason=decision['reason'], at=state['recorded_at'], shared_stop_assessments=None,
                             additional_stop_assessments=decision['stop_assessments'])
                if decision.get('license') is not None:
                    value['license'] = decision['license']
                if value['continuity_decision'] is not None:
                    value['continuity_decision'] = {**decision['continuity_decision'],
                        'basis': {key: continuity_evidence[key] for key in ('path', 'locator')}}
            _write(file, value)
        state['adoption'] = adoption.apply(root, run, decision_file=file.relative_to(root).as_posix(), settings=settings)
        _write(progress, state)
    return {'ok': True, 'scope': scope, 'selection': state['selection'], 'adoption': state['adoption']}


def _slot_use(root: Path, directory: Path, state: dict) -> dict:
    """Record a later slot use without reopening a completed production run."""
    import production_acceptance as acceptance
    import production_operations as workflow
    import studio_workspace as studio
    binding, decision = state.get('effective_binding', state['binding']), state['decision']
    source, target = binding['source'], binding['snapshot']['target']
    scope = 'curation:' + state['identity']
    rows = store.event_rows(root, scope)
    authorization = next((row for row in rows if row['event'] == 'slot-use-authorized'), None)
    if authorization is None:
        _check_source(root, binding)
        terms = request = None
        if source['kind'] == 'production':
            grant = _grant(root, directory, state, 'select')
            loaded = workflow.read_run(root, source['run'])
            authority = workflow.current_authority(root, loaded.prepared)
            compact = {'run': source['run'], 'input_sha256': loaded.prepared['input_sha256'],
                'candidate': source['candidate'], 'review': binding['snapshot']['review'], 'scope': 'studio-slot',
                'expected_selection': workflow.replaced_selection(loaded.rows),
                'authority_sha256': acceptance.authority_basis(authority, grant), 'grant': grant,
                'reason': decision['reason'], 'stop_assessments': [
                    {key: item[key] for key in ('id', 'clear', 'evidence')} for item in decision['stop_assessments']],
                'owner_acceptance': _owner_acceptance(state),
                'expected_placement': binding['snapshot']['placement'],
                'expected_slot': binding['snapshot']['slot_acceptance']}
            selection, request = acceptance._expand(root, source['run'], compact, loaded)
            review = workflow.find(loaded.rows, 'review', binding['snapshot']['review'])
            workflow.eligible(loaded.prepared, review, selection['owner_acceptance'])
            permissions.check(authority.document, request)
            terms = assessments.authority_terms(authority, grant, 'select')
        authorization = store.append(root, scope, None, 'slot-use-authorized',
            {'intent': state['intent'], 'target': target, 'request': request, 'authority_terms': terms})
    token = {'scope': scope, 'authorization': authorization['sha256']}
    read = studio.StudioRead(root)
    row = read.iteration(target['character'], target['iteration_id'])
    saved = [item for item in row.get('acceptances', []) if item.get('curation_authorization') == token]
    if saved:
        return {'ok': True, 'retained': True, 'target': target, 'acceptance': c.content_id(saved[-1]),
                'authorization': token}
    result = studio.accept(root, target['character'], target['iteration_id'], curation_authorization=token)
    receipt = next(item for item in result['acceptances'] if item.get('curation_authorization') == token)
    return {'ok': True, 'target': target, 'acceptance': c.content_id(receipt), 'authorization': token}


def _saved_slot_use(root: Path, state: dict) -> dict | None:
    """Read this operation's exact historical slot receipt without another acceptance."""
    import studio_workspace as studio
    target = state['binding']['snapshot']['target']
    scope = 'curation:' + state['identity']
    authorized = [row for row in store.event_rows(root, scope) if row['event'] == 'slot-use-authorized']
    if not authorized:
        return None
    token = {'scope': scope, 'authorization': authorized[0]['sha256']}
    row = studio.StudioRead(root).iteration(target['character'], target['iteration_id'])
    saved = [item for item in row.get('acceptances', []) if item.get('curation_authorization') == token]
    if not saved:
        return None
    if len(saved) != 1:
        _changed('The saved slot-use authorization has more than one receipt.')
    verify_slot_receipt(root, target['character'], row, saved[0])
    return {'ok': True, 'retained': True, 'target': target, 'acceptance': c.content_id(saved[0]), 'authorization': token}


def validate_slot_authorization(root: Path, character: str, iteration: str, token: dict) -> None:
    """Check the exact later-use decision again inside the Studio effect owner."""
    import production_operations as workflow
    c.exact(token, {'scope', 'authorization'}, 'curation slot authorization')
    if not token['scope'].startswith('curation:'):
        raise ValueError('Slot use requires its recorded curation scope.')
    rows = store.event_rows(root, token['scope'])
    authorized = workflow.find(rows, 'slot-use-authorized', token['authorization'])
    intent = workflow.find(rows, 'curation-intent', authorized['data']['intent'])
    binding, _ = _resolved(intent['data']['binding'], intent['data']['decision'])
    expected = binding['snapshot']['target']
    if expected['character'] != character or expected['iteration_id'] != iteration or authorized['data']['target'] != expected:
        _changed('The retained slot-use permission names another exact iteration.')
    evidence = intent['data']['instruction']
    if c.sha256_file(c.local(root, evidence['path'])) != evidence['sha256']:
        _changed('The retained slot-use instruction bytes changed.')
    _check_source(root, binding)
    _check_authority(root, binding)
    request = authorized['data']['request']
    if request is not None:
        source = binding['source']
        loaded = workflow.read_run(root, source['run'])
        authority = workflow.current_authority(root, loaded.prepared)
        current = assessments.authority_terms(authority, request['grant'], 'select')
        if current != authorized['data']['authority_terms']:
            _changed('The current slot-use authority differs from its exact authorization.')
        permissions.check(authority.document, request)


def verify_slot_receipt(root: Path, character: str, row: dict, receipt: dict) -> None:
    """Verify historical slot-use proof without renewing its old permission."""
    import production_operations as workflow
    import studio_workspace as studio
    token = receipt['curation_authorization']
    c.exact(token, {'scope', 'authorization'}, 'curation slot authorization')
    if not token['scope'].startswith('curation:'):
        raise ValueError('A slot receipt needs its recorded curation scope.')
    records = store.event_rows(root, token['scope'])
    authorization = workflow.find(records, 'slot-use-authorized', token['authorization'])
    intent = workflow.find(records, 'curation-intent', authorization['data']['intent'])
    binding = intent['data']['binding']
    target = binding['snapshot']['target']
    if target != {'character': character, 'iteration_id': row['iteration_id'],
                  'slot': studio.acceptance_receipt_slot(row, receipt)} or authorization['data']['target'] != target:
        raise ValueError('The slot receipt differs from its recorded curation destination.')
    source = binding['source']
    if source['kind'] == 'production' and row.get('production') != {
            'run': source['run'], 'candidate': source['candidate']}:
        raise ValueError('The slot receipt differs from its exact Production origin.')
    evidence = intent['data']['instruction']
    if c.sha256_file(c.local(root, evidence['path'])) != evidence['sha256']:
        raise ValueError('The retained curation instruction bytes changed.')


def verify(root: Path, state_dir: Path, *, binding: dict) -> dict:
    """Read formal completion and current use separately, including later replacement."""
    import production_operations as workflow
    import sheet_artifacts as fills
    import studio_workspace as studio
    root, directory = root.resolve(), _directory(state_dir.resolve(), binding)
    directory.relative_to(root)
    state = c.load(directory / 'progress.json')
    operation = directory.relative_to(root).as_posix()
    if binding != state['binding'] or state.get('operation') != operation or state['identity'] != _identity(
            operation, state['binding'], state['decision']):
        _changed('The retained curation basis differs from this work plan.')
    effective, _ = _resolved(binding, state['decision'])
    if state.get('effective_binding', state['binding']) != effective:
        _changed('The retained grant differs from the authored grant choice.')
    records = store.event_rows(root, 'curation:' + state['identity'])
    intent = workflow.find(records, 'curation-intent', state['intent'])
    if intent['data']['binding'] != binding or intent['data']['decision'] != state['decision']:
        _changed('The saved decision differs from its formal curation intent.')
    evidence = intent['data']['instruction']
    if c.sha256_file(c.local(root, evidence['path'])) != evidence['sha256']:
        _changed('The retained instruction evidence changed.')
    continuity_evidence = _retained_continuity(root, state, intent['data'])
    saved = state['result']
    result = workflow.find(records, 'curation-result', saved['receipt'])
    if result['data'] != {'intent': state['intent'], 'result': {key: value for key, value in saved.items() if key != 'receipt'}}:
        _changed('The saved result differs from its formal curation receipt.')
    source, scope = binding['source'], binding['destination']['scope']
    outcome, current_use = saved['result'], 'delivery'
    journal = None
    if source['kind'] == 'production':
        loaded = workflow.read_run(root, source['run'])
        if scope != 'withdraw':
            selected = workflow.find(loaded.rows, 'selection', outcome['selection']['selection'])
            if selected['data']['selection']['candidate'] != source['candidate']:
                _changed('The result selection names another captured candidate.')
            if outcome['selection'].get('completion'):
                completion = workflow.verify_completion(root, source['run'], loaded.prepared['task']['task_id'])
                if completion['sha256'] != outcome['selection']['completion']:
                    _changed('The result names another production completion.')
            if scope in {'sheet', 'catalog'}:
                claim = outcome['adoption']['adoption_claim']
                matches = [row for row in loaded.rows if row['event'] == 'adoption-result' and row['data']['claim'] == claim]
                if len(matches) != 1:
                    _changed('The canonical use has no unique formal adoption result.')
                journal = matches[0]['data']['result']
    elif source['kind'] == 'imported':
        image = binding['snapshot']['image']
        if c.sha256_file(c.local(root, image['path'])) != image['sha256']:
            _changed('The retained imported image changed.')
        if scope in {'sheet', 'catalog'}:
            journal = outcome
    if continuity_evidence is not None and journal is not None:
        actual = journal.get('approval', {}).get('continuity_decision') or {}
        expected = state['decision']['continuity_decision']
        if (any(actual.get(name) != expected[name] for name in ('character_id', 'continuity'))
                or any((actual.get('basis') or {}).get(name) != continuity_evidence[name]
                       for name in ('sha256', 'locator'))):
            _changed('The formal adoption does not retain the authored continuity and its exact instruction evidence.')
    target = binding['snapshot'].get('target')
    if scope == 'studio-slot':
        read = studio.StudioRead(root)
        row = read.iteration(target['character'], target['iteration_id'])
        slot_use = outcome.get('slot_use') if source['kind'] == 'production' else outcome
        if slot_use is not None:
            matching = [item for item in row.get('acceptances', []) if c.content_id(item) == slot_use['acceptance']]
            if len(matching) != 1:
                _changed('The exact curation slot receipt is missing.')
            verify_slot_receipt(root, target['character'], row, matching[0])
            digest = slot_use['acceptance']
        else:
            import production_acceptance
            selected = workflow.find(loaded.rows, 'selection', outcome['selection']['selection'])
            held = production_acceptance._receipt(root, source['run'], selected, require_current=False)
            digest = c.content_id(held['acceptance'])
        current = studio.acceptance_state(root, target['character'], target['slot'], read=read)
        current_use = 'current' if current and current['acceptance_sha256'] == digest else 'superseded'
    elif scope in {'sheet', 'catalog', 'withdraw'}:
        sheet = (c.local(root, source['sheet']) if source['kind'] == 'sheet' else
                 c.local(root, f'characters/{target["character"]}/sheet/sheet-data.json'))
        slot_id = source['slot'] if source['kind'] == 'sheet' else target['slot']
        slot = fills._read(sheet)['slots'][slot_id]
        if scope == 'withdraw':
            receipt = outcome['withdrawal']
            if receipt not in slot.get('withdrawals', []):
                _changed('The exact withdrawal receipt is missing.')
            accepted = next((item for item in slot['history'] if c.content_id(item) == receipt['acceptance_sha256']), None)
            if accepted is None:
                _changed('The withdrawal has lost its historical accepted image.')
            fills.verify_withdrawal(receipt, sheet.parent, slot_id, accepted)
            current_use = 'withdrawn' if slot.get('current') is None else 'superseded'
        else:
            expected = outcome['current'] if source['kind'] == 'sheet' else journal['sheet_binding']['current']
            held = [item for item in [slot.get('current'), *slot['history']] if item == expected]
            if not held:
                _changed('The completed adoption has lost its current or historical sheet receipt.')
            fills.verify_acceptance(expected, sheet.parent, slot_id)
            current_use = ('current' if slot.get('current') == expected else
                           'withdrawn' if fills.withdrawn_acceptance(slot, expected) else 'superseded')
    return {**saved, 'verified': True, 'historical_completion': True, 'current_use': current_use}


def _local_decision(root: Path, directory: Path, state: dict, *, continuity_evidence: dict | None) -> dict:
    """Reconstruct the derived local decision from the retained curation answer."""
    import adoption_workflow as adoption
    binding, decision = state['binding'], state['decision']
    source, destination = binding['source'], binding['destination']
    scope = destination['scope']
    approval = {**decision['approval'], 'at': state['recorded_at']}
    if scope == 'withdraw':
        value = copy.deepcopy(binding.get('withdrawal') or binding['snapshot']['sheet_decision'])
    elif source['kind'] == 'sheet':
        value = copy.deepcopy(binding['snapshot']['sheet_decision'])
    elif scope in {'sheet', 'catalog'}:
        target = binding['snapshot']['target']
        registration = c.load(c.local(root, state['registration_path'])) if scope == 'catalog' else None
        value = adoption.draft_approval(root, target['character'], target['iteration_id'],
            scope=scope, influence=destination['influence'], registration_record=registration)
        if decision.get('continuity_decision') is not None:
            value['continuity_decision'] = {**decision['continuity_decision'], 'by': approval['actor'],
                'at': approval['at'], 'basis': copy.deepcopy(continuity_evidence)}
    else:
        value = {'scope': scope, 'source': source}
    value.update(by=approval['actor'], at=approval['at'])
    if scope == 'withdraw' or source['kind'] == 'sheet':
        value.update(reason=decision['reason'], evidence={'path': state['instruction_path'],
            'sha256': c.sha256_file(directory / 'instruction.txt'), 'locator': approval['evidence']['locator']})
    elif scope in {'sheet', 'catalog'}:
        value['note'] = decision['reason']
        if decision.get('license') is not None:
            value['license'] = decision['license']
    return value


def _local_apply(root: Path, directory: Path, state: dict, *, settings=None,
                 continuity_evidence: dict | None = None) -> dict:
    import adoption_workflow as adoption
    import sheet_artifacts as fills
    import studio_workspace as studio
    binding = state['binding']
    source, destination = binding['source'], binding['destination']
    scope = destination['scope']
    file = directory / 'local-decision.json'
    value = _local_decision(root, directory, state, continuity_evidence=continuity_evidence)
    if file.exists():
        actual = c.load(file)
        if actual != value:
            _changed('The retained local decision differs from the saved curation choice.',
                file=file.relative_to(root).as_posix(), expected=value, actual=actual)
    else:
        _check_source(root, binding)
        _write(file, value)
    if scope == 'withdraw':
        return fills.withdraw(Path(value['sheet']), value, evidence_root=root)
    if source['kind'] == 'sheet':
        slot = fills._read(Path(value['sheet']))['slots'][value['slot']]
        retained = [item for item in [slot.get('current'), *slot['history']] if item is not None
                    and item['approval']['decision_sha256'] == c.content_id(value)]
        if retained:
            fills.verify_acceptance(retained[0], Path(value['sheet']).parent, value['slot'])
            return {'adopted': True, 'already_adopted': True, 'historical_completion': True, 'current': retained[0]}
        if slot.get('current') is not None and slot['current']['artifact']['artifact_id'] == value['artifact_id']:
            fills.verify_acceptance(slot['current'], Path(value['sheet']).parent, value['slot'])
            return {'adopted': True, 'already_adopted': True, 'retained': True, 'current': slot['current']}
        if not any(item['artifact_id'] == value['artifact_id'] for item in slot['candidates']):
            _check_source(root, binding)
            fills.reoffer(Path(value['sheet']), value['slot'], value['artifact_id'])
        return fills.adopt(Path(value['sheet']), value, evidence_root=root)
    target = binding['snapshot']['target']
    if scope == 'delivery-only':
        return {'ok': True, 'scope': scope, 'image': binding['snapshot']['image']}
    if scope == 'studio-slot':
        return _slot_use(root, directory, state)
    journal_path = adoption._journal_path(studio.character_home(root, target['character']), target['iteration_id'])
    if journal_path.exists():
        journal = c.load(journal_path)
        seen = set()
        while journal is not None:
            if journal.get('approval') == value and journal.get('next_action') is None:
                return {'ok': True, 'retained': True, **journal}
            previous = journal.get('previous_adoption')
            if previous is None:
                break
            if previous['sha256'] in seen:
                _changed('The retained adoption history repeats a prior journal.')
            seen.add(previous['sha256'])
            path = c.local(root, previous['path'])
            if c.sha256_file(path) != previous['sha256']:
                _changed('The retained earlier adoption journal changed.')
            journal = c.load(path)
    return adoption.adopt(root, target['character'], target['iteration_id'], value,
        registration_record=c.load(c.local(root, state['registration_path'])) if scope == 'catalog' else None,
        pack_dir=Path(destination['pack_dir']) if scope == 'catalog' else None, settings=settings)


def apply(root: Path, state_dir: Path, decision: dict, *, binding: dict, settings=None) -> dict:
    """Apply one decision or resume its retained records, with no repeated author fields."""
    import studio_activity as activity
    root, directory = root.resolve(), _directory(state_dir.resolve(), binding)
    directory.relative_to(root)
    effective, decision = _resolved(binding, decision)
    operation = directory.relative_to(root).as_posix()
    identity = _identity(operation, binding, decision)
    progress = directory / 'progress.json'
    if not progress.exists():
        acquired = _validate_choices(root, decision, effective)
        _check_source(root, effective)
        _check_authority(root, effective)
        state = {'identity': identity, 'operation': operation, 'binding': copy.deepcopy(binding), 'decision': copy.deepcopy(decision),
                 'effective_binding': effective,
                 'recorded_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                 'instruction_path': (directory / 'instruction.txt').relative_to(root).as_posix()}
        directory.mkdir(parents=True, exist_ok=True)
        if binding['destination']['scope'] == 'catalog':
            registration = store.stable_bytes(root, binding['destination']['registration_file'])
            if c.digest(registration) != binding['registration_sha256']:
                _changed('The selected catalog record changed after this use was decided.')
            target = directory / 'registration.json'
            try:
                c.atomic(target, registration)
            except FileExistsError:
                if target.read_bytes() != registration:
                    _changed('The operation already captured a different catalog record.')
            state['registration_path'] = target.relative_to(root).as_posix()
        for name, raw in acquired.items():
            target = directory / (name + '.txt')
            try:
                c.atomic(target, raw)
            except FileExistsError:
                if target.read_bytes() != raw:
                    _changed('The operation already captured different ' + name + ' evidence.')
            if name == 'continuity':
                state['continuity_evidence'] = {'path': target.relative_to(root).as_posix(),
                    'sha256': c.digest(raw), 'locator': _continuity_basis(decision)['locator']}
        try:
            c.atomic(progress, c.encoded(state))
        except FileExistsError:
            pass
    with c.file_lock(progress):
        state = c.load(progress)
        if (state['identity'] != identity or state.get('operation') != operation or
                _identity(operation, state['binding'], state['decision']) != identity):
            _changed('This retained operation belongs to another decision; preserve it and open the new intended use.')
        if state.get('effective_binding', state['binding']) != effective:
            _changed('The selected grant differs from the generated binding of this exact saved decision.')
        if 'result' in state:
            return {**verify(root, state_dir, binding=binding), 'recovered': True}
        with activity.operation(root) as projection:
            import production_operations as workflow
            records = store.event_rows(root, 'curation:' + identity)
            if 'intent' not in state:
                data = {'operation': operation, 'binding': state['binding'], 'decision': state['decision'], 'recorded_at': state['recorded_at'],
                        'instruction': {'path': (directory / 'instruction.txt').relative_to(root).as_posix(),
                                        'sha256': c.sha256_file(directory / 'instruction.txt')},
                        **({'continuity_evidence': state['continuity_evidence']} if 'continuity_evidence' in state else {})}
                held = [item for item in records if item['event'] == 'curation-intent']
                if len(held) > 1 or (held and held[0]['data'] != data):
                    _changed('The retained curation intent differs from this exact saved decision.')
                intent = held[0] if held else store.append(root, 'curation:' + identity, None, 'curation-intent', data)
                state['intent'] = intent['sha256']
                _write(progress, state)
            else:
                intent = workflow.find(records, 'curation-intent', state['intent'])
                if intent['data']['binding'] != binding or intent['data']['decision'] != decision \
                        or intent['data']['recorded_at'] != state['recorded_at'] \
                        or intent['data']['instruction']['path'] != state['instruction_path'] \
                        or intent['data']['instruction']['sha256'] != c.sha256_file(directory / 'instruction.txt'):
                    _changed('The saved operation differs from its formal intent or retained instruction.')
            continuity_evidence = _retained_continuity(root, state, intent['data'])
            held_results = [item for item in records if item['event'] == 'curation-result']
            if held_results:
                if len(held_results) != 1 or held_results[0]['data']['intent'] != state['intent']:
                    _changed('The saved use has conflicting completion receipts.')
                state['result'] = {**held_results[0]['data']['result'], 'receipt': held_results[0]['sha256']}
                _write(progress, state)
                return {**verify(root, state_dir, binding=binding), 'recovered': True}
            if binding['source']['kind'] == 'production' and binding['destination']['scope'] != 'withdraw':
                result = _production_apply(root, directory, state, settings=settings,
                    continuity_evidence=continuity_evidence)
            else:
                result = _local_apply(root, directory, state, settings=settings,
                    continuity_evidence=continuity_evidence)
            state['result'] = {'ok': True, 'scope': binding['destination']['scope'],
                               'source': binding['source'], 'result': result}
            receipt = store.append(root, 'curation:' + identity, None, 'curation-result',
                {'intent': state['intent'], 'result': state['result']})
            state['result']['receipt'] = receipt['sha256']
            _write(progress, state)
        return activity.project_result(state['result'], projection)
