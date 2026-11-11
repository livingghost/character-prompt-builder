"""Author one canonical-use decision and derive its exact recoverable operation."""
from __future__ import annotations

import copy
from pathlib import Path

import execution_contract as c
import production_permissions as permissions
import production_store as store
import runtime_snapshot
from production_diagnostics import ProductionError, compare_exact


def _grant(authority, scope: str, selected: str | None) -> str:
    requirements = permissions.grant_requirements(authority.document,
        [{'operation': 'adopt', 'targets': ['canon:' + scope]}], grant=selected)
    permissions.require_grants(requirements)
    return requirements['requirements'][0]['selected_grant']


def authority_basis(authority, grant: str, scope: str) -> str:
    """Only the selected adoption terms and their actual source bind this decision."""
    document = authority.document
    selected = next(item for item in document['grants'] if item['id'] == grant)
    terms = {key: selected.get(key) for key in
             ('id', 'actor', 'mode', 'effective_at', 'expires_at', 'revoked_at')}
    terms.update(operation='adopt', operation_granted='adopt' in selected['operations'],
                 target='canon:' + scope, target_granted='canon:' + scope in selected['targets'])
    declaration = [{key: item[key] for key in ('path', 'locator', 'sha256')}
                   for item in authority.evidence if item['purpose'] == 'authority-declaration']
    return c.content_id({'task_id': authority.task_id, 'issuer': document['issuer'], 'grant': terms,
                         'declaration': declaration,
                         'stop_conditions': sorted(document['stop_conditions'], key=lambda item: item['id'])})


def require_approval_authority(root: Path, prepared: dict, approval: dict, request: dict,
                               *, reassessed: str | None = None, claim: str | None = None) -> None:
    """Keep an authored assessment tied to its exact applicable terms at the effect."""
    expected = reassessed or approval.get('authority_sha256')
    if expected is None:
        return
    import production_workflow as workflow
    authority = workflow.current_authority(root, prepared)
    actual = authority_basis(authority, request['grant'], approval['scope'])
    if expected != actual:
        raise ProductionError('ADOPTION_DECISION_CHANGED',
            'The current adoption terms differ from the recorded author assessments.', phase='adoption',
            expected=expected, actual=actual,
            required_action=('Inspect the changed terms, then use production_workflow.py draft-adoption '
                f'--run {prepared["run"]} --claim {claim} --out NEW-ASSESSMENT.json. Author the actual current '
                'assessments and apply with adopt --file NEW-ASSESSMENT.json to continue this same claim.' if claim else
                'Inspect the current authority and draft-adoption again; earlier assessments do not clear a changed stop condition.'))


def _source(root: Path, loaded, candidate: str) -> tuple[dict, dict, object]:
    import adoption_workflow as adoption
    import production_acceptance as acceptance
    import production_workflow as workflow
    import studio
    selected, choice, _ = workflow.current_selection(loaded.prepared, loaded.rows)
    workflow.require_selected(loaded.prepared, loaded.rows, candidate, run=loaded.prepared['run'])
    target, raw = acceptance._target(root, loaded.prepared['run'], candidate, loaded=loaded)
    read = studio.StudioRead(root)
    row = {**raw, 'status': raw.get('adoption_status', raw.get('status', 'candidate'))}
    adoption.require_adoption_source(root, target['character'], row, read=read)
    journal = adoption._journal_path(read.home(target['character']), target['iteration_id'])
    if journal.exists() or adoption.recorded_adoptions(loaded.rows, target['character'], target['iteration_id'])[1]:
        adoption.require_journal_agreement(read.journal(target['character'], target['iteration_id']),
            target['character'], target['iteration_id'], row['production'], loaded.rows)
    current = (read.sheet(target['character'])['slots'].get(target['slot']) or {}).get('current')
    state = {'placement': raw['placement']['sha256'],
             'slot_acceptance': studio.acceptance_state(root, target['character'], target['slot'], read=read),
             'adoption': None if current is None else c.content_id(current)}
    return {'character': target['character'], 'iteration': target['iteration_id'], 'slot': target['slot'],
            'image_sha256': raw['result']['sha256'], 'selection': selected['sha256'],
            'review': choice['review'], 'source_state': state}, row, read


@runtime_snapshot.operation
def draft(root: Path, run: str, candidate: str, *, scope: str, influence: str,
          grant: str | None = None, registration_file: str | None = None,
          pack_dir: Path | None = None) -> dict:
    """Pin the selected image and destination, leaving actual judgments unanswered."""
    import adoption_workflow as adoption
    import production_workflow as workflow
    if scope not in adoption.SCOPES or influence not in adoption.INFLUENCES:
        raise ValueError('select the intended adoption scope and influence')
    loaded = workflow.read_run(root, run)
    source, row, read = _source(root, loaded, candidate)
    if influence != 'identity' and source['slot'].startswith(('base.', 'canon.')):
        raise ValueError('base/canon identity slots require identity influence')
    authority = workflow.current_authority(root, loaded.prepared)
    grant = _grant(authority, scope, grant)
    registration = None
    if scope == 'catalog':
        if registration_file is None or pack_dir is None:
            raise ValueError('catalog adoption needs --registration-record and --pack-dir')
        raw = store.stable_bytes(root, registration_file)
        record = adoption.validate_registration_record(c.decode(raw))
        registration = {'path': registration_file, 'sha256': c.digest(raw),
                        'record_sha256': adoption.digest(record), 'pack_dir': str(pack_dir.resolve())}
    elif registration_file is not None or pack_dir is not None:
        raise ValueError('registration arguments require catalog scope')
    continuity = None
    if influence == 'identity':
        _, package = read._package(row['package'])
        if package.get('artifact_type') == 'upscale-package':
            _, package = read._package(package['source_generation_package'], verify=True)
        subjects = package['visual_continuity']['subjects']
        if len(subjects) != 1:
            raise ValueError('identity adoption requires a single-subject candidate')
        subject = next(iter(subjects.values()))
        if subject['continuity'] == 'undecided' or subject['character_id'] is None:
            continuity = {'character_id': subject['character_id'], 'continuity': None,
                          'basis': {'path': '', 'locator': ''}}
    return {'run': run, 'input_sha256': loaded.prepared['input_sha256'], 'candidate': candidate,
            **source, 'scope': scope, 'influence': influence, 'grant': grant,
            'authority_sha256': authority_basis(authority, grant, scope),
            'at': None, 'reason': '', 'license': None, 'continuity_decision': continuity,
            'registration': registration,
            'stop_assessments': [{'id': item['id'], 'condition': item['text'], 'clear': False, 'evidence': ''}
                                 for item in authority.document['stop_conditions']]}


def decision_basis(value: dict) -> dict:
    if 'claim' in value:
        return {'claim': value['claim'], 'approval': c.content_id(value['approval']),
                'authority_sha256': value['authority_sha256']}
    return {key: value[key] for key in ('review', 'selection', 'character', 'iteration', 'slot',
            'image_sha256', 'source_state', 'authority_sha256', 'influence', 'registration')}


def _expand(root: Path, loaded, value: dict) -> tuple[dict, dict, dict | None, Path | None]:
    import adoption_workflow as adoption
    import production_workflow as workflow
    workflow.schema_check(value, 'adoption')
    source, row, read = _source(root, loaded, value['candidate'])
    expected = {'run': loaded.prepared['run'], 'input_sha256': loaded.prepared['input_sha256'], **source}
    if any(value[key] != item for key, item in expected.items()):
        raise ProductionError('ADOPTION_DECISION_CHANGED',
            'The selected image, review, placement or destination changed after this adoption was drafted.',
            phase='adoption', expected=expected, actual={key: value[key] for key in expected},
            required_action='Inspect the current candidate and destination, then use draft-adoption to make a new '
                            'decision if still intended. Retain judgments only where their evidence still applies.')
    authority = workflow.current_authority(root, loaded.prepared)
    grant = _grant(authority, value['scope'], value['grant'])
    actual = authority_basis(authority, grant, value['scope'])
    if value['authority_sha256'] != actual:
        raise ProductionError('ADOPTION_DECISION_CHANGED',
            'The adoption grant, source authority or stop conditions changed after drafting.', phase='adoption',
            expected=value['authority_sha256'], actual=actual,
            required_action='Read the changed authority and draft-adoption again; keep assessments only where the '
                            'current evidence supports them.')
    compare_exact({item['id']: item['text'] for item in authority.document['stop_conditions']},
                  {item['id']: item['condition'] for item in value['stop_assessments']}, phase='adoption')
    actor = next(item['actor'] for item in authority.document['grants'] if item['id'] == grant)
    approval = {key: value[key] for key in ('scope', 'influence', 'character', 'slot', 'image_sha256', 'at')}
    approval.update(iteration_id=value['iteration'], by=actor, note=value['reason'],
                    authority_sha256=value['authority_sha256'],
                    source_state=copy.deepcopy(value['source_state']))
    if value['license'] is not None:
        approval['license'] = value['license']
    if value['continuity_decision'] is not None:
        choice = value['continuity_decision']
        basis = choice['basis']
        # The authored file retains the source citation. The formal approval
        # cites its immutable bytes, so a saved decision never depends on a
        # mutable authoring path after its claim has committed.
        digest = c.object_store(loaded.directory, store.stable_bytes(root, basis['path']))
        held = (loaded.directory / 'objects' / digest).relative_to(root).as_posix()
        approval['continuity_decision'] = {**copy.deepcopy(choice), 'by': actor, 'at': value['at'],
            'basis': {'path': held, 'locator': basis['locator'], 'sha256': digest}}
    registration, target = None, None
    if value['scope'] == 'catalog':
        chosen = value['registration']
        raw = store.stable_bytes(root, chosen['path'])
        if c.digest(raw) != chosen['sha256']:
            raise ProductionError('SOURCE_CHANGED', 'The selected catalog record changed after drafting.',
                phase='adoption', file=chosen['path'], expected=chosen['sha256'], actual=c.digest(raw),
                required_action='Inspect the changed catalog record and draft-adoption again for its exact content.')
        registration = adoption.validate_registration_record(c.decode(raw))
        compare_exact(chosen['record_sha256'], adoption.digest(registration), phase='adoption')
        approval['registration_record_sha256'] = adoption.digest(registration)
        target = Path(chosen['pack_dir'])
    adoption.preflight(root, value['character'], value['iteration'], approval,
        expected_production={'run': loaded.prepared['run'], 'candidate': value['candidate']},
        expected_image=value['image_sha256'], registration_record=registration, pack_dir=target, read=read)
    intent = workflow._adoption_operation(value['review'], value['candidate'], value['character'],
        value['iteration'], approval, registration_record=registration, pack_dir=target)
    request = workflow.draft_authorization_from(loaded, authority, grant, intent)
    request.update(reason=value['reason'], stop_assessments=[
        {key: item[key] for key in ('id', 'clear', 'evidence')} for item in value['stop_assessments']])
    permissions.check(authority.document, request)
    return approval, request, registration, target


def _retained_claim(loaded, identifier: str) -> tuple[dict, dict]:
    import execution_lifecycle as lifecycle
    import production_workflow as workflow
    claim = workflow.find(loaded.rows, 'adoption-claim', identifier)
    lifecycle.require_operation(loaded.rows, loaded.prepared, loaded.prepared['run'], **claim['data']['intent'])
    approval = c.decode(loaded.evidence.read(claim['data']['files'][0]['sha256']))
    return claim, approval


@runtime_snapshot.operation
def draft_reassessment(root: Path, run: str, claim_id: str, *, grant: str | None = None) -> dict:
    """Ask for current authority judgments while retaining the exact canonical use."""
    import production_workflow as workflow
    loaded = workflow.read_run(root, run)
    claim, approval = _retained_claim(loaded, claim_id)
    authority = workflow.current_authority(root, loaded.prepared)
    grant = _grant(authority, approval['scope'], grant)
    return {'run': run, 'input_sha256': loaded.prepared['input_sha256'], 'claim': claim_id,
            'candidate': claim['data']['intent']['payload']['candidate'], 'scope': approval['scope'],
            'approval': approval, 'grant': grant, 'authority_sha256': authority_basis(authority, grant, approval['scope']),
            'reason': '', 'stop_assessments': [{'id': item['id'], 'condition': item['text'], 'clear': False, 'evidence': ''}
                                               for item in authority.document['stop_conditions']]}


def _reassessment(root: Path, loaded, value: dict) -> tuple[dict, dict]:
    import adoption_workflow as adoption
    import production_workflow as workflow
    workflow.schema_check(value, 'adoption')
    claim, approval = _retained_claim(loaded, value['claim'])
    expected = {'run': loaded.prepared['run'], 'input_sha256': loaded.prepared['input_sha256'],
                'candidate': claim['data']['intent']['payload']['candidate'],
                'scope': approval['scope'], 'approval': approval}
    compare_exact(expected, {key: value[key] for key in expected}, phase='adoption')
    authority = workflow.current_authority(root, loaded.prepared)
    grant = _grant(authority, value['scope'], value['grant'])
    actual = authority_basis(authority, grant, value['scope'])
    if value['authority_sha256'] != actual:
        raise ProductionError('ADOPTION_DECISION_CHANGED', 'The reassessment authority changed after drafting.',
            phase='adoption', expected=value['authority_sha256'], actual=actual,
            required_action='Read the changed authority and draft-adoption --claim for this exact claim again.')
    compare_exact({item['id']: item['text'] for item in authority.document['stop_conditions']},
                  {item['id']: item['condition'] for item in value['stop_assessments']}, phase='adoption')
    request = workflow.draft_authorization_from(loaded, authority, grant, claim['data']['intent'])
    request.update(reason=value['reason'], stop_assessments=[
        {key: item[key] for key in ('id', 'clear', 'evidence')} for item in value['stop_assessments']])
    permissions.check(authority.document, request)
    if not any(row['event'] == 'adoption-result' and row['data']['claim'] == claim['sha256'] for row in loaded.rows):
        payload = claim['data']['intent']['payload']
        registration = (c.decode(loaded.evidence.read(payload['registration_sha256']))
                        if payload['registration_sha256'] is not None else None)
        adoption.preflight(root, payload['character'], payload['iteration'], approval,
            expected_production={'run': loaded.prepared['run'], 'candidate': payload['candidate']},
            expected_image=approval['image_sha256'], registration_record=registration,
            pack_dir=Path(payload['pack_dir']) if payload['pack_dir'] is not None else None,
            production_claim=claim['sha256'])
    return claim, request


def _claim_for_decision(loaded, raw: bytes) -> dict | None:
    """Match one validated decision by its content, not its newline or formatting bytes."""
    import production_workflow as workflow
    value = c.decode(raw)
    workflow.schema_check(value, 'adoption')
    identity = c.content_id(value)

    def matches(item: dict) -> bool:
        try:
            other = c.decode(loaded.evidence.read(item['sha256']))
            workflow.schema_check(other, 'adoption')
        except (ValueError, TypeError):
            return False
        return c.content_id(other) == identity

    requests = {row['sha256'] for row in loaded.rows if row['event'] == 'authorization'
                and row['data']['request']['operation'] == 'adopt'
                and any(matches(item) for item in row['data']['files'])}
    reassessed = {row['data']['claim'] for row in loaded.rows if row['event'] == 'adoption-authority'
                  and row['data']['authorization'] in requests}
    claims = [row for row in loaded.rows if row['event'] == 'adoption-claim'
              and (row['sha256'] in reassessed or any(token in requests for token in row['data']['authorizations']))]
    if len(claims) > 1:
        raise ValueError('one authored adoption decision has conflicting claims')
    return claims[0] if claims else None


def _resume(root: Path, loaded, claim: dict, *, settings=None) -> dict:
    import adoption_workflow as adoption
    import production_workflow as workflow
    run, rows = loaded.prepared['run'], loaded.rows
    intent = claim['data']['intent']
    payload = intent['payload']
    from execution_lifecycle import current_adoption_authorization
    token, reassessed = current_adoption_authorization(rows, claim)
    workflow.require_selected(loaded.prepared, rows, payload['candidate'], run=run)
    request = workflow._permission(root, loaded.prepared, rows, token, **intent, loaded=loaded)
    approval = c.decode(loaded.evidence.read(claim['data']['files'][0]['sha256']))
    require_approval_authority(root, loaded.prepared, approval, request,
                               reassessed=reassessed, claim=claim['sha256'])
    completed = [row for row in rows if row['event'] == 'adoption-result' and row['data']['claim'] == claim['sha256']]
    if completed:
        adoption.restore_journal(root, payload['character'], payload['iteration'], production_claim=claim['sha256'])
        result = workflow._refresh_studio_projection(root, completed[-1])
    else:
        registration = (c.decode(loaded.evidence.read(payload['registration_sha256']))
                        if payload['registration_sha256'] is not None else None)
        result = workflow.adopt(root, run, payload['candidate'], payload['character'], payload['iteration'],
            claim['data']['files'][0]['path'], token, registration_record=registration,
            pack_dir=Path(payload['pack_dir']) if payload['pack_dir'] is not None else None, settings=settings)
    return {**result, 'adoption_claim': claim['sha256'],
            'resume': {'command': 'adopt', 'arguments': ['--run', run, '--claim', claim['sha256']]}}


@runtime_snapshot.operation
def apply(root: Path, run: str, *, decision_file: str | None = None,
          claim_id: str | None = None, settings=None) -> dict:
    """Authorize authored choices once, then use the existing adoption effect owner."""
    import production_workflow as workflow
    import studio_activity as activity
    if (decision_file is None) == (claim_id is None):
        raise ValueError('adopt needs one --file decision or --claim to recover')
    raw = store.stable_bytes(root, decision_file) if decision_file is not None else None
    with activity.operation(root) as projection:
        with store.transaction(root):
            loaded = workflow.read_run(root, run)
            claim = (workflow.find(loaded.rows, 'adoption-claim', claim_id) if claim_id is not None else
                     _claim_for_decision(loaded, raw))
            if claim is None:
                value = c.decode(raw)
                if 'claim' in value:
                    claim, request = _reassessment(root, loaded, value)
                    authorization = workflow.authorize_value(root, run, request, evidence_files=[decision_file],
                        expected_source=(decision_file, c.digest(raw)))
                    current = workflow.read_run(root, run)
                    workflow.append_record(current.directory, current.prepared, current.rows, 'adoption-authority',
                        {'claim': claim['sha256'], 'authorization': authorization['sha256'],
                         'authority_sha256': value['authority_sha256']})
            if claim is None:
                approval, request, registration, target = _expand(root, loaded, value)
                # These are immutable products of the one authored decision. The
                # author never transcribes either their content or their digests.
                approval_sha = c.object_store(loaded.directory, c.encoded(approval))
                approval_path = (loaded.directory / 'objects' / approval_sha).relative_to(root).as_posix()
                evidence = [decision_file]
                if approval.get('continuity_decision') is not None:
                    evidence.append(approval['continuity_decision']['basis']['path'])
                if registration is not None:
                    digest = c.object_store(loaded.directory, c.encoded(registration))
                    evidence.append((loaded.directory / 'objects' / digest).relative_to(root).as_posix())
                authorization = workflow.authorize_value(root, run, request, evidence_files=evidence,
                    expected_source=(decision_file, c.digest(raw)))
                current = workflow.read_run(root, run)
                item = workflow.file_record(root, current.directory, approval_path)
                claim = workflow.append_record(current.directory, current.prepared, current.rows, 'adoption-claim',
                    {'intent': {key: request[key] for key in ('operation', 'targets', 'payload')},
                     'files': [item], 'authorizations': [authorization['sha256']]})
        result = _resume(root, workflow.read_run(root, run), claim, settings=settings)
    return activity.project_result(result, projection)


def scope(root: Path, run: str, *, decision_file: str | None, claim_id: str | None) -> str:
    """Locate the selected catalog runtime without inventing a new decision."""
    import production_workflow as workflow
    if decision_file is not None:
        value = c.load(c.local(root, decision_file))
        workflow.schema_check(value, 'adoption')
        return value['scope']
    claim = workflow.find(workflow.read_run(root, run).rows, 'adoption-claim', claim_id)
    return claim['data']['intent']['targets'][0].removeprefix('canon:')


def saved_actions(root: Path, loaded) -> list[dict]:
    """Inspect only this explicitly selected run's registered adoption branches."""
    import production_authoring_state as authored
    import production_workflow as workflow
    from cli_invocation import python_argv
    from production_diagnostics import from_exception
    run = loaded.prepared['run']
    result = []
    covered_claims = set()
    for item in authored.decision_drafts(root, loaded.prepared['task']['task_id'], kind='adoption', run=run):
        if not item['available']:
            continue
        action = {'command': 'adopt', 'argv': python_argv(workflow.ROOT / 'scripts/production_workflow.py',
            'adopt', '--root', str(root), '--run', run, '--file', item['path']),
            'draft': item['path'], 'requires_author_input': True,
            'reason': 'Read and complete this saved canonical-use decision from the actual approval and evidence; '
                      'its existence is not permission.', 'diagnostics': []}
        try:
            raw = store.stable_bytes(root, item['path'])
            value = c.decode(raw)
            workflow.schema_check(value, 'adoption')
            context = item['context']
            if (value['run'] != run or value['input_sha256'] != loaded.prepared['input_sha256']
                    or decision_basis(value) != context['basis'] or value['candidate'] != context['candidate']
                    or value['scope'] != context['scope'] or value['grant'] != context['grant']):
                raise ValueError('saved adoption draft ownership fields differ from its producer registration')
            recorded = _claim_for_decision(loaded, raw)
            if recorded is not None:
                covered_claims.add(recorded['sha256'])
                action.update(argv=python_argv(workflow.ROOT / 'scripts/production_workflow.py', 'adopt',
                    '--root', str(root), '--run', run, '--claim', recorded['sha256']), requires_author_input=False,
                    claim=recorded['sha256'],
                    reason='Recover or inspect this exact recorded adoption; the claim retains its decision and evidence.')
            else:
                if 'claim' in value:
                    _, approval = _retained_claim(loaded, value['claim'])
                    source = {'approval': approval}
                else:
                    source, _, _ = _source(root, loaded, value['candidate'])
                authority = workflow.current_authority(root, loaded.prepared)
                grant = _grant(authority, value['scope'], value['grant'])
                if (any(value[key] != actual for key, actual in source.items())
                        or value['authority_sha256'] != authority_basis(authority, grant, value['scope'])):
                    raise ProductionError('ADOPTION_DECISION_CHANGED', 'The saved adoption basis is no longer current.',
                        phase='adoption', file=item['path'], required_action='Keep this draft as history and run '
                        'draft-adoption against the current selection, placement and authority; do not overwrite it.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            action['diagnostics'] = [from_exception(exc, phase='adoption')]
            action.update(command='status', argv=python_argv(workflow.ROOT / 'scripts/production_workflow.py',
                'status', '--root', str(root), '--run', run),
                reason='Inspect this saved adoption decision and follow its diagnostic before applying it.')
        result.append(action)
    completed = {row['data']['claim'] for row in loaded.rows if row['event'] == 'adoption-result'}
    for claim in (row for row in loaded.rows if row['event'] == 'adoption-claim'):
        if claim['sha256'] in covered_claims:
            continue
        result.append({'command': 'adopt', 'argv': python_argv(workflow.ROOT / 'scripts/production_workflow.py',
            'adopt', '--root', str(root), '--run', run, '--claim', claim['sha256']),
            'draft': None, 'claim': claim['sha256'], 'completed': claim['sha256'] in completed,
            'requires_author_input': False, 'diagnostics': [],
            'reason': ('Inspect or restore this completed adoption evidence; it never reinstates a withdrawn '
                       'or replaced canonical use.' if claim['sha256'] in completed else
                       'Recover this committed adoption from its retained decision and evidence. The current '
                       'selection, authority and destination are checked again before an effect.')})
    return result
