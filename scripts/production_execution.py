"""Execute and recover the prepared request, with authored judgments kept separately.

The production transaction owns permission and execution claims. Network I/O
starts only after that transaction commits. Recovery reads durable answers; it
never interprets a timeout as evidence that a request was not sent. A lost
answer is asked for again only through the transport's lookup, and an author's
evidenced statement that the provider holds no such task is recorded as one.
"""
from __future__ import annotations

import copy
import functools
import os
import sqlite3
from pathlib import Path
from typing import Any

import execution_contract as c
import production_store as store
import execution_lifecycle as accounting
from operation_context import current, current_operation_id, stage
from production_diagnostics import ProductionError, compare_exact, from_exception

# Every failure a read-only status inspection reports instead of raising.
INSPECTION_ERRORS = (ValueError, OSError, KeyError, TypeError, sqlite3.DatabaseError)
# Step outcomes the provider evidenced as making nothing.
NO_EFFECT_OUTCOMES = frozenset({'rejected', 'not_executed'})
SCRIPT = str(Path(__file__).with_name('production_workflow.py'))


def _public_call(function):
    """Run one public entry on the checked studio root, in one verification scope.

    The root is checked and resolved once here (`execution_contract._root`), so a
    root given through a directory junction names the same files as the paths
    the run and the Studio record. The stages of the call reuse what the call
    already verified. Each production transaction still starts its own scope.
    `accounting.begin_step` checks the run and its live sources again even
    inside a caller's transaction.
    """
    @functools.wraps(function)
    def call(*args, **kwargs):
        import runtime_snapshot
        if 'root' in kwargs:
            kwargs['root'] = c._root(kwargs['root'])
        else:
            args = (c._root(args[0]), *args[1:])
        with runtime_snapshot.public_call():
            return function(*args, **kwargs)
    return call


def compiled(root: Path, run: str, *, fresh: bool = False) -> tuple:
    import production_workflow as workflow
    import request_contract as rc
    import transport_contract
    loaded = workflow.assert_current(root, run) if fresh else workflow.load_run(root, run)
    directory, prepared, consumer, rows = loaded
    if prepared['task']['execution'] != 'dispatcher' or not (directory / 'package.json').is_file():
        raise ProductionError('EXECUTION_NOT_APPLICABLE', 'This operation needs a prepared model request.', phase='execution', run=run)
    package = c.load(directory / 'package.json')
    rendered = c.load(directory / 'request-contract.json')
    plan = c.load(directory / 'execution-plan.json')
    target = c.load(directory / 'execution-target.json')
    compare_exact(prepared['compiled'], {'package_sha256': c.content_id(package),
        'request_sha256': rendered['request_sha256'], 'plan_sha256': c.content_id(plan)}, phase='integrity')
    rc.validate_seal(rendered)
    compare_exact(plan['request_sha256'], rendered['request_sha256'], phase='integrity')
    transport = transport_contract.load(target['service']['transport'])
    current_transport = c.sha256_file(Path(transport.__file__))
    if target['transport_sha256'] != current_transport:
        raise ProductionError('TRANSPORT_IMPLEMENTATION_CHANGED', 'The installed transport differs from the one sealed for this run.',
                              phase='integrity', run=run, expected=target['transport_sha256'], actual=current_transport,
                              required_action='Use the installation that prepared this run to recover its existing provider task. Do not resend it.')
    transport.endpoint(target['service'])
    return directory, prepared, consumer, rows, package, rendered, plan, target, transport


@_public_call
def draft_execution(root: Path, run: str, grant: str) -> dict:
    """Draft the independent judgments of the prepared operations in one editing document."""
    import production_decisions
    return production_decisions.draft(root, run, grant)


def authorize_decisions(root: Path, run: str, path: str, prepared: dict, plan: dict) -> None:
    import production_decisions
    production_decisions.authorize(root, run, path, prepared, plan)


def receipts(root: Path, prepared: dict, rows: list[dict], plan: dict, *,
             required_action: str = 'Fill the execution decision file from the actual approval or delegation, then execute with --decisions-file.') -> dict[str, str]:
    """Select only receipts covering each entire operation under current grants."""
    import production_workflow as workflow
    selected = {}
    for intent in plan['operations']:
        matches = [row for row in reversed(rows) if row['event'] == 'authorization' and
                   all(row['data']['request'].get(key) == intent[key] for key in ('operation', 'targets', 'payload'))]
        if not matches:
            raise ProductionError('AUTHORIZATION_REQUIRED', 'No exact authorization covers this prepared operation.',
                phase='authorization', run=prepared['run'], pointer='$.operations.' + intent['operation'],
                expected=intent['targets'], actual=[],
                required_action=required_action)
        last_error = None
        for row in matches:
            try:
                request = workflow._permission(root, prepared, rows, row['sha256'], **intent)
                selected[intent['operation']] = row['sha256']
                break
            except (ValueError, OSError) as exc:
                last_error = exc
        else:
            raise last_error
    return selected


def require_recording(root: Path, prepared: dict) -> None:
    """The recording destination still has the slot and the conditions preparation checked.

    A send stops here when the Studio character, the slot, its sheet-panel
    condition or the subject mapping changed after preparation. A destination
    that cannot be written keeps its own operating-system error.
    """
    import studio
    from production_compiler import validate_recording
    recording = prepared['task']['recording']
    try:
        studio.validate_recording_target(root, recording['character'], recording['slot'], writable=True)
    except ValueError as exc:
        raise ProductionError('RECORDING_CONTRACT_INVALID', str(exc), phase='recording-validation', run=prepared['run'],
                              pointer='$.recording',
                              required_action='Restore the Studio character and slot this run records to, or prepare a variant '
                                              'with a recording contract for an existing slot.') from exc
    validate_recording(root, prepared['task'], {})


def _append(root: Path, run: str, event: str, data: dict) -> dict:
    import production_workflow as workflow
    directory, prepared, _, rows = workflow.load_run(root, run)
    return workflow.append_record(directory, prepared, rows, event, data)


def _evidence(root: Path, run: str, journal, names: list[str]) -> list[dict]:
    """Snapshot the named journal files into the run, as formal event evidence."""
    import production_workflow as workflow
    directory = workflow.run_dir(root, run)
    base = journal.path.absolute().relative_to(Path(root).absolute()).as_posix()
    return [workflow.file_record(root, directory, base + '/' + name) for name in names if (journal.path / name).is_file()]


def _credential(root: Path, transport: Any, service_id: str, *, expected: dict | None = None):
    """Resolve the selected Studio's authentication only when the transport needs it."""
    import service_auth
    import transport_contract
    return None if transport_contract.credential_free(transport) else service_auth.resolve(root, service_id, expected=expected)


def authentication_readiness(root: Path, transport: Any, service_id: str, *,
                             required: bool = True, expected: dict | None = None) -> dict:
    """Local availability of the next network step's authentication, without a provider request."""
    import service_auth
    import transport_contract
    required = required and not transport_contract.credential_free(transport)
    observed = service_auth.inspect(root, service_id, expected=expected) if required else {
        'available': None, 'selection': expected, 'diagnostics': []}
    return {'required': required, **observed, 'remote_validation': 'not-performed'}


def claim_authentication(claim: dict, transport: Any, service_id: str) -> dict | None:
    """The claim's non-secret source identity; an absent declaration is an invalid claim."""
    import production_workflow as workflow
    if 'authentication' not in claim['data']:
        raise ProductionError('ARTIFACT_CORRUPT', 'The dispatch claim has no authentication selection.',
                              phase='integrity', required_action='Restore the complete recorded dispatch claim.')
    try:
        return workflow.validate_dispatch_authentication(claim['data']['authentication'], transport, service_id)
    except ValueError as exc:
        raise ProductionError('ARTIFACT_CORRUPT', 'The dispatch claim has an invalid authentication selection.',
                              phase='integrity', required_action='Restore the complete recorded dispatch claim.') from exc


def _journal(root: Path, run: str, data: tuple):
    import dispatch
    from production_compiler import read_manifest
    from publication_artifacts import ArtifactSet
    directory, prepared, _, _, package, rendered, plan, target, _ = data
    manifest=read_manifest(directory,expected=store.registered_run(root,run)['manifest_sha256'])
    artifacts=ArtifactSet(directory,manifest['files'])
    recording = prepared['task']['recording']
    operation = 'upscale' if package.get('artifact_type')=='upscale-request' else 'generation'
    if operation == 'upscale':
        companion = 'upscale.references'
    else:
        from build_generation_payload import validate_generation_package_carrier_paths
        companion = validate_generation_package_carrier_paths(package['prepared_reference_set'], package_root=directory)
    journal = dispatch.RunJournal.create(root, operation=operation, character=recording['character'],
        slot=recording['slot'], service=plan['service'], transport=plan['transport'], model=plan['model'],
        production_run=run, expected=plan['quantities']['outputs'], note='Executed from the sealed production input.',
        offering=dispatch.offering_summary(target['offering'], target['model_id'], target['model']), companion=companion)
    for name in ('package.json', 'consumer.json'):
        artifacts.copy_file(name, journal.path / name)
    if companion:
        artifacts.subtree(companion).copy_to(journal.path / companion)
    if operation=='upscale':
        journal.update(upscale={'source':Path(rendered['media'][0]['path']).relative_to(directory).as_posix(),
            'audit_status':'pending' if target['model'].get('upscaler_class') in {'generative','creative'} else 'not-required'})
    saved = copy.deepcopy(rendered)
    for item in saved['media']:
        item['path'] = str(journal.path / Path(item['path']).relative_to(directory))
    import request_contract as rc
    rc.validate_seal(saved)
    journal.write('request-contract.json', saved)
    journal.write('preview.json', saved['request'])
    return journal, saved


def _execute_external(root: Path, run: str, *, decisions_file: str | None) -> dict:
    """Hand the exact input to the host once after both independent decisions pass."""
    import production_decisions
    import production_workflow as workflow
    with store.transaction(root):
        _, prepared, consumer, rows, plan = production_decisions.context(root, run)
        if any(row['event'] == 'external-claim' for row in rows):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already handed its request to the host.',
                phase='execution', run=run,
                required_action='Recover that host call and receive its actual result. A new call needs a newly prepared run.')
        if decisions_file is not None:
            authorize_decisions(root, run, decisions_file, prepared, plan)
        _, prepared, consumer, rows = workflow.assert_current(root, run)
        tokens = receipts(root, prepared, rows, plan)
        hand = plan['handoff']
        workflow.handoff(root, run, hand['recipient'], hand['method'], tokens['direction'])
        claim = workflow.claim_external(root, run, plan['quantities']['outputs'], tokens['submit'])
    binding = consumer['image_input']
    return {'artifact_type': 'external-execution-instruction',
            'run': run, 'state': 'host-call-required', 'external_effect': False,
            'host_request': {'claim': claim['sha256'], 'target': binding['model']['target'],
                          'request': copy.deepcopy(binding['external_request']['request']),
                          'references': copy.deepcopy(binding['references']),
                          'prepared_reference_set': copy.deepcopy(binding.get('prepared_reference_set')),
                          'model_identity': copy.deepcopy(binding['external_request'].get('model_identity'))},
            'instruction': 'Invoke this exact host request once. Save the actual response and returned media, '
                           'then use receive-external. After interruption, recover the same call; do not invoke it again.'}


@_public_call
def execute(root: Path, run: str, *, decisions_file: str | None = None) -> dict:
    import production_workflow as workflow
    import studio
    from verify_generation_payload import verify
    import runtime_snapshot

    if workflow.load_run(root, run)[1]['task']['execution'] == 'external':
        return _execute_external(root, run, decisions_file=decisions_file)

    with stage('execution-preflight'):
        data = compiled(root, run, fresh=True)
        directory, prepared, _, rows, package, rendered, plan, target, transport = data
        if any(row['event'] == 'dispatch-claim' for row in rows):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already owns an execution.', phase='execution', run=run,
                required_action='Use resume for this execution, variant for changed input, or repeat for an intentional new run.')
        require_recording(root, prepared)
        credential = _credential(root, transport, target['offering']['service'])
        descriptor = prepared['runtime_snapshot']
        with runtime_snapshot.using(runtime_snapshot.path(root, descriptor), descriptor):
            if package.get('artifact_type')=='upscale-request':
                from production_binding import validate_upscale_input
                validate_upscale_input(root,package)
                verified={}
            else:
                verified = verify(package, package_root=directory, studio=root, reading_ledgers=[directory / 'reads.jsonl'])
        if current():
            current().link(run=run, task=prepared['task']['task_id'])
            current().durable()
        # Every external step performs its own fresh integrity check inside
        # accounting.begin_step, after authorization and immediately before I/O.
        # That check is independent of the presence of a diagnostic operation.

    with stage('authorization-and-claim'), store.transaction(root):
        if decisions_file is not None:
            authorize_decisions(root, run, decisions_file, prepared, plan)
        _, live_prepared, _, rows = workflow.assert_current(root, run)
        tokens = receipts(root, live_prepared, rows, plan)
        # The journal is the dispatcher's own copy of the consumer, so writing it
        # is the handoff. It is written only after every check above passed, right
        # before the claim. A transaction that fails after this point leaves a
        # journal no claim names; unclaimed_journals() lists it.
        journal, saved = _journal(root, run, data)
        hand = plan['handoff']
        workflow.handoff(root, run, hand['recipient'], hand['method'], tokens['direction'], journal=journal.path)
        submission = next(item for item in plan['operations'] if item['operation'] == 'submit')
        claim = workflow.claim_dispatch(root, run, package, verified, journal.path, submission,
                                        tokens['submit'], rendered=saved,
                                        authentication=credential.selection if credential is not None else None)
    return _transmit(root, run, journal, saved, claim, tokens['submit'], target, transport,
                     credential.value if credential is not None else '')


def _upload_receipt(root: Path, run: str, journal, rendered: dict, claim: dict,
                    authorization: str, index: int) -> dict:
    """Validate one actual upload response and persist its independently billed effect."""
    import production_workflow as workflow
    item=rendered['media'][index]
    path=journal.path/f'upload-{index+1:03d}.json'
    receipt=c.load(path)
    c.exact(receipt,{'index','source','source_sha256','provider_id','response','usage'},'upload receipt')
    if receipt['index']!=index or receipt['source']!=item['path'] or receipt['source_sha256']!=item['sha256']:
        raise ProductionError('ARTIFACT_CORRUPT','The upload receipt belongs to another sealed media input.',phase='result-capture',run=run)
    c.text(receipt['provider_id'],'uploaded provider identifier')
    if not isinstance(receipt['response'],dict):
        raise ProductionError('TRANSPORT_RESULT_INVALID','The actual upload response must be a JSON object.',phase='result-capture')
    accounting.validate_usage(receipt['usage'])
    directory=workflow.run_dir(root,run)
    witness=workflow.file_record(root,directory,path.relative_to(root).as_posix())
    accounting.record_effect(root,run,authorization,claim=claim['sha256'],step=f'upload:{index}',
                             usage=receipt['usage'],evidence=[witness])
    return receipt


def _record_no_effect(root: Path, run: str, authorization: str, claim: dict, step: str, outcome: str,
                      evidence: list[dict]) -> dict:
    """Record that one started external step made nothing, as the provider or the author evidenced."""
    import production_workflow as workflow
    if outcome not in NO_EFFECT_OUTCOMES:
        raise ValueError('a step without effect is rejected or not_executed')
    with store.transaction(root):
        directory, prepared, _, rows = workflow.load_run(root, run)
        state = accounting.require_active(rows, prepared, run, authorization)
        if not any(item['step'] == step and item['claim'] == claim['sha256'] for item in state['steps']):
            raise ProductionError('SETTLEMENT_EVIDENCE_REQUIRED', 'No exact external boundary supports this outcome.',
                                  phase='result-capture', run=run)
        data = {'execution_id': state['execution_id'], 'claim': claim['sha256'], 'step': step,
                'usage': None, 'evidence': evidence, 'outcome': outcome}
        previous = state['effect_results'].get(step)
        if previous is not None:
            if previous != data:
                raise ProductionError('SETTLEMENT_CONFLICT', 'This external step already has a different recorded result.',
                                      phase='result-capture', run=run,
                                      required_action='Inspect the recorded result; a step keeps the first evidenced outcome.')
            return next(row for row in rows if row['event'] == 'external-effect-result' and row['data'] == data)
        return workflow.append_record(directory, prepared, rows, 'external-effect-result', data)



def _owner() -> dict:
    return {'operation_id': current_operation_id(), 'pid': os.getpid()}


def _transmit(root: Path, run: str, journal, rendered: dict, claim: dict, authorization: str,
              target: dict, transport: Any, key: str) -> dict:
    import dispatch
    import request_contract as rc
    import transport_contract
    import production_workflow as workflow
    try:
        media_ids = {}
        with stage('reference-upload'):
            for index, item in enumerate(rendered['media']):
                raw = c.read(Path(item['path']))
                if c.digest(raw) != item['sha256'] or len(raw) != item['size']:
                    raise ProductionError('ARTIFACT_CORRUPT', 'Saved reference bytes changed.', phase='before-send', file=item['path'])
                _,prepared,_,rows=workflow.load_run(root,run)
                state=accounting.require_active(rows,prepared,run,authorization)
                step=f'upload:{index}'
                started=any(entry['step']==step for entry in state['steps'])
                if not started:
                    accounting.begin_step(root, run, authorization, claim=claim['sha256'], step=step, operation='upload')
                    try:
                        source=item['upload_source']
                        uploaded=transport.upload_media(raw,item['media_type'],target['service'],key,
                            source_url=source['url'] if source['kind']=='url' else None)
                    except transport_contract.Refused as refusal:
                        return _refused_upload(root, run, journal, claim, authorization, index, refusal.evidence())
                    c.exact(uploaded,{'provider_id','response','usage'},'transport upload result')
                    journal.write(f'upload-{index + 1:03d}.json', {'index': index, 'source': item['path'],
                        'source_sha256': item['sha256'], **uploaded})
                elif not (journal.path/f'upload-{index+1:03d}.json').is_file():
                    raise ProductionError('REMOTE_OUTCOME_UNKNOWN','An upload started without its saved response; it cannot be sent again.',
                                          phase='reference-upload',run=run)
                media_ids[index]=_upload_receipt(root,run,journal,rendered,claim,authorization,index)['provider_id']
        request = rc.materialize(rendered, media_ids)
        rc.validate_wire(rendered, request, media_ids)
        journal.write('request.json', request)
        # The identifiers the service knows this request by, as sent, so a lost
        # answer can be looked up without reading the journal.
        identifiers = [{'field': list(path), 'value': rc.get(request, path)} for path in rendered['layout']['management']]
        with stage('provider-wait'):
            journal.update(sender=_owner())
            accounting.begin_step(root, run, authorization, claim=claim['sha256'], step='send', operation='send',
                                  identifiers=identifiers)
            journal.update(status='sending')
            answer = dispatch.send_and_keep(journal, transport, request, target['service'], key)
        if answer is None:
            _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': 'outcome_unknown',
                'reason': 'The send started without a saved provider answer.',
                'evidence': _evidence(root, run, journal, ['request-contract.json', 'request.json', 'indeterminate.json'])})
            result = status(root, run)
            result.update(ok=False, execution_completed=False, external_effect=True)
            return result
        if not transport_contract.complete(transport, answer):
            return _unfinished(root, run, journal, claim, transport, answer, 'send-observation.json')
        _acknowledge(root, run, journal, claim)
        result = _finish(root, run, journal, transport)
        result.update(external_effect=True)
        return result
    except BaseException as exc:
        _record_execution_failure(root, run, journal, claim, exc)
        raise


def _acknowledge(root: Path, run: str, journal, claim: dict, *, witnesses: tuple[str, ...] = (), **facts: Any) -> dict:
    """Commit the receipt of the saved answer, with the journal files that witness it."""
    names = ['request-contract.json', 'request.json', *witnesses, 'answer.json', 'transport-outcome.json']
    return _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': 'acknowledged',
        'response_sha256': c.sha256_file(journal.path / 'answer.json'), **facts,
        'evidence': _evidence(root, run, journal, names)})


def _unfinished(root: Path, run: str, journal, claim: dict, transport: Any, answer: dict,
                answer_name: str, *, witnesses: tuple[str, ...] = (), **facts: Any) -> dict:
    """Keep an unfinished observation and capture outputs without finalizing the send."""
    import transport_contract
    observed = transport_contract.outcome(transport, answer)
    known_accepted = any(row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
                         and row['data'].get('submission') == 'pending' for row in store.event_rows(root, run))
    submission = 'pending' if observed == transport_contract.ACCEPTED or known_accepted else 'outcome_unknown'
    reason = ('The provider accepted the request and has unfinished outputs.' if submission == 'pending'
              else 'The saved provider observation does not settle whether the request was carried out.')
    _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': submission,
        'provider_outcome': observed, 'reason': reason, **facts,
        'evidence': _evidence(root, run, journal, ['request-contract.json', 'request.json', answer_name, *witnesses])})
    if any(entry.get('url') or entry.get('data') for entry in transport.results(answer)):
        result = _finish(root, run, journal, transport, answer_name=answer_name, provider_complete=False)
    else:
        result = status(root, run)
    journal.update(status=submission)
    result.update(ok=False, execution_completed=False, external_effect=True)
    return result


def _refused_upload(root: Path, run: str, journal, claim: dict, authorization: str, index: int, refusal: dict) -> dict:
    """Keep the service's refusal of an upload; nothing was made, so the request is never sent."""
    c.exact(refusal, {'outcome', 'reason', 'answer'}, 'upload refusal')
    if refusal['outcome'] != 'rejected':
        raise ValueError('an upload refusal needs the actual rejected provider response')
    name = f'upload-{index + 1:03d}-refused.json'
    if (journal.path / f'upload-{index + 1:03d}.json').is_file():
        raise ProductionError('ARTIFACT_CORRUPT', 'An upload has conflicting saved outcomes.',
                              phase='result-capture', run=run)
    journal.write(name, refusal)
    journal.update(status='upload-refused')
    evidence = _evidence(root, run, journal, [name])
    _record_no_effect(root, run, authorization, claim, f'upload:{index}', 'rejected', evidence)
    _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': 'claimed',
        'code': 'PROVIDER_REJECTION', 'step': f'upload:{index}', 'evidence': evidence})
    _, _, _, _, _, _, _, target, transport = compiled(root, run)
    result = _cleanup_report(root, run, journal, claim, target, transport)
    result.update(ok=False, execution_completed=False)
    return result


def _claim_execution(rows: list[dict], prepared: dict, run: str, claim: dict) -> dict | None:
    states = accounting.derive(rows, prepared, run)
    return next((item for item in states.values() if item['authorization_sha256'] in claim['data']['authorizations']), None)


def submission_state(rows: list[dict], prepared: dict, run: str, *, sender_alive: bool = False) -> tuple[str, list[dict]]:
    """The submission axis and the started external effects, from formal events only.

    A dispatcher run with no send step is claimed, whatever its uploads did. A
    send step is send_started while its owner operation still runs and
    outcome_unknown once it does not, until a receipt acknowledges an answer or
    evidence shows the provider never executed it.
    """
    claims = [row for row in rows if row['event'] == 'dispatch-claim']
    external = [row for row in rows if row['event'] == 'external-claim']
    if not claims and not external:
        return 'unclaimed', []
    claim = (claims or external)[-1]
    state = _claim_execution(rows, prepared, run, claim)
    steps = state['steps'] if state else []
    results = state['effect_results'] if state else {}
    effects = [{'step': item['step'], 'operation': item['operation'],
                'result': (results[item['step']].get('outcome', 'executed') if item['step'] in results else 'unanswered')}
               for item in steps]
    if external:
        if any(row['event'] == 'candidate' for row in rows) or any(row['event'] == 'execution-result' for row in rows):
            return 'acknowledged', effects
        return 'outcome_unknown', effects
    send = next((item for item in steps if item['operation'] == 'send'), None)
    if send is None:
        return 'claimed', effects
    if (results.get(send['step']) or {}).get('outcome') == 'not_executed':
        return 'not_executed', effects
    outcomes = [row['data']['submission'] for row in rows
                if row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']]
    if 'acknowledged' in outcomes:
        return 'acknowledged', effects
    if 'pending' in outcomes:
        return 'pending', effects
    if outcomes and outcomes[-1] == 'outcome_unknown':
        return 'outcome_unknown', effects
    return ('send_started' if sender_alive else 'outcome_unknown'), effects


def _record_execution_failure(root: Path, run: str, journal, claim: dict, error: BaseException) -> None:
    """Record a stopped attempt without changing facts about prior external effects."""
    try:
        import production_workflow as workflow
        _, prepared, _, rows = workflow.load_run(root, run)
        # The failing process owns the attempt and is stopping now.
        outcome, effects = submission_state(rows, prepared, run, sender_alive=False)
        diagnostic = getattr(error, 'diagnostic', None)
        _append(root, run, 'execution-outcome', {'claim': claim['sha256'],
            'submission': outcome, 'effects': effects, 'error_type': type(error).__name__,
            'code': diagnostic.code if diagnostic is not None else 'EXECUTION_STOPPED',
            'recovery': 'Inspect saved evidence; resume does not blindly resend.'})
    except (ValueError, OSError):
        # The original failure must survive a simultaneous record-storage failure.
        # A diagnostic log never substitutes for the missing formal event.
        if current():
            current().event('formal_record_unavailable', run=run, phase='execution-recovery')


def _finish(root: Path, run: str, journal, transport: Any, *, answer_name: str = 'answer.json',
            provider_complete: bool = True) -> dict:
    """Recover against the saved runtime, without overriding current selection for a new send."""
    import runtime_snapshot
    import production_workflow as workflow
    prepared=workflow.load_run(root,run)[1]
    descriptor=prepared['runtime_snapshot']
    with runtime_snapshot.using(runtime_snapshot.path(root,descriptor),descriptor):
        return _finish_captured(root,run,journal,transport,answer_name=answer_name,provider_complete=provider_complete)


def _finish_captured(root: Path, run: str, journal, transport: Any, *, answer_name: str = 'answer.json',
                     provider_complete: bool = True) -> dict:
    """Commit every acquired candidate and accounting before updating Studio."""
    import dispatch
    import production_workflow as workflow
    import studio
    rows = store.event_rows(root, run)
    answer_path = journal.path / answer_name
    relative_answer = answer_path.relative_to(root).as_posix()
    expected = {item['sha256'] for row in rows for item in row['data'].get('evidence', [])
                if item['path'] == relative_answer}
    if expected and expected != {c.sha256_file(answer_path)}:
        raise ProductionError('RESPONSE_CORRUPT', 'Saved provider response differs from its durable receipt.',
                              phase='result-capture', run=run, file=str(answer_path),
                              required_action='Restore the recorded response bytes; do not resend the request.')
    captured = {index: item['sha256'] for row in rows if row['event'] == 'dispatch-results'
                for index, item in zip(row['data']['output_indices'], row['data']['files'])}
    with stage('result-capture'):
        acquisition = dispatch.acquire(journal, transport, answer_name=answer_name, captured=captured)
    package = c.load(journal.path / 'package.json')
    capture_diagnostics=[]
    if acquisition['refused']:
        capture_diagnostics.append({'code':'PROVIDER_REJECTION','severity':'warning','phase':'result-capture',
            'message':'The saved provider answer includes refusal information. Inspect its exact reason with the generation failure assessment; a provider rejection alone does not identify moderation.',
            'required_action':'Use render_contract.py diagnose with the saved response before changing models or retrying.',
            'count':len(acquisition['refused'])})
    if provider_complete and acquisition['entries']!=journal.document['expected']:
        capture_diagnostics.append({'code':'OUTPUT_COUNT_MISMATCH','severity':'warning','phase':'result-capture',
            'message':'Returned output count differs from the authorized request.','expected':journal.document['expected'],'actual':acquisition['entries']})
    result_packages={}
    invalid_upscale=set()
    if journal.document['operation']=='upscale':
        for index,path,_ in acquisition['acquired']:
            try:
                result_packages[index]=dispatch.upscale_result_package(journal,index,path)
            except (ValueError,OSError,KeyError,TypeError) as exc:
                invalid_upscale.add(index)
                capture_diagnostics.append(from_exception(exc,phase='result-capture',code='UPSCALE_OUTPUT_CONTRACT_MISMATCH'))
    with stage('candidate-registration'), store.transaction(root):
        result = workflow.record_dispatch_results(root, run, package, journal.path,
            [path for _, path, _ in acquisition['acquired']], journal.document['expected'],
            indices=[index for index, _, _ in acquisition['acquired']], returned_count=acquisition['entries'],
            upscale_packages=result_packages if journal.document['operation']=='upscale' else None,
            invalid_output_indices=invalid_upscale, answer_name=answer_name, provider_complete=provider_complete)
        directory, prepared, _, rows = workflow.load_run(root, run)
        claim = workflow.find(rows, 'dispatch-claim')
        handoff = workflow.find(rows, 'handoff')
        for index, item in zip(result['data']['output_indices'], result['data']['files']):
            response = c.load(journal.path / f'response-{index}.json')
            workflow.append_record(directory, prepared, store.event_rows(root, run), 'candidate',
                {'handoff': handoff['sha256'], 'files': [item],
                 'media': workflow.media.inspect(c.object_read(directory, item['sha256']), prepared['task']['artifact']),
                 'note': 'Captured provider output; not a review or selection.',
                 'output_index': index, 'provider_output_id': response.get('id')})
        answer = c.load(answer_path)
        usage = transport.usage(answer)
        if usage is not None and len(acquisition['observed_indices']) != acquisition['entries']:
            # This charge covers only the latest observation. Earlier outputs
            # remain captured, but their costs cannot be inferred or counted twice.
            usage = {**usage, 'final': False}
        response_ref = workflow.file_record(root, directory, relative_answer)
        authorization=claim['data']['authorizations'][0]
        rendered=c.load(journal.path/'request-contract.json')
        for index in range(len(rendered['media'])):
            _upload_receipt(root,run,journal,rendered,claim,authorization,index)
        if provider_complete:
            accounting.record_effect(root,run,authorization,claim=claim['sha256'],step='send',usage=usage,evidence=[response_ref])
        state=accounting.require_active(store.event_rows(root,run),prepared,run,authorization)
        # The generation result is immutable. Later input deletion keeps its
        # own billed receipts in aggregate accounting, not a rewritten result.
        actual_cost,_=accounting.effect_total(state, operations={'upload', 'send'})
        accounting.record_result(root, run, authorization, outputs=len(acquisition['acquired']),
            cost=actual_cost if provider_complete else None, final=provider_complete and not acquisition['failed'], evidence=[response_ref])
        _append(root, run, 'capture-status', {'claim': claim['sha256'], 'capture': 'complete' if result['data']['complete'] else 'partial',
            'received': acquisition['entries'], 'registered': len(acquisition['acquired']), 'expected': journal.document['expected'], 'diagnostics':capture_diagnostics})
    # These files are projections. A slot removed during generation cannot
    # discard captured bytes or roll back the authoritative candidate records.
    warnings = list(capture_diagnostics)
    with stage('studio-projection'):
        try:
            recorded = list(journal.document.get('iterations', []))
            for index, path, response in acquisition['acquired']:
                if index in invalid_upscale:
                    continue
                found = dispatch.recorded_iteration(root, journal.document['character'], journal.document['slot'],
                                                     (path, journal.path / 'request.json', response))
                if found is None:
                    row = studio.iterate(root, journal.document['character'], journal.document['slot'], path,
                        package=result_packages.get(index,journal.path / 'package.json'), request=journal.path / 'request.json', response=response,
                        answer=c.local(journal.path, c.load(response)['answer']), note='Projection of the captured Production candidate.',
                        service=journal.document['offering'],
                        package_companion=(journal.path / journal.document['companion']) if journal.document.get('companion') else None,
                        layout=c.load(journal.path / 'request-contract.json')['layout'])
                    found = row['iteration_id']
                if prepared['task']['recording']['sheet_panel']:
                    import sheet_artifacts
                    row = studio._find(studio.read_iterations(studio.character_home(root, journal.document['character'])), found)
                    sheet_artifacts.from_iteration(root, journal.document['character'], row)
                if found not in recorded:
                    recorded.append(found)
            journal.update(status='capture-invalid' if invalid_upscale else ('complete' if result['data']['complete'] else 'capture-incomplete'), iterations=recorded)
        except (ValueError, OSError, KeyError) as exc:
            warnings.append(from_exception(exc, phase='studio-projection', code='STUDIO_PROJECTION_FAILED'))
            # The candidates are registered; only their Studio projection is missing.
            journal.update(status='projection-missing')
    images_complete = provider_complete and result['data']['complete'] and not warnings
    if provider_complete and not acquisition['failed']:
        _, _, _, _, _, _, _, target, _ = compiled(root, run)
        report = _cleanup_report(root, run, journal, claim, target, transport)
        warnings.extend(report.get('warnings', []))
    else:
        report = status(root, run)
    report['warnings'] = warnings
    cleanup = report['runs'][0]['cleanup']['state']
    report['execution_completed'] = images_complete and cleanup in {'not-needed', 'complete', 'failed', 'unsupported'}
    report['ok'] = report['ok'] and report['execution_completed']
    return report


def _cleanup_report(root: Path, run: str, journal, claim: dict, target: dict, transport: Any) -> dict:
    """Complete only owned-input cleanup, keeping captured images immediately usable."""
    import production_cleanup
    cleanup = production_cleanup.perform(root, run, journal, claim, target, transport)
    report = status(root, run)
    item = report['runs'][0]
    report['warnings'] = cleanup['warnings']
    report['external_effect'] = cleanup['external_effect']
    report['execution_completed'] = (item['capture'] == 'complete' and item['registration'] == 'registered'
        and item['cleanup']['state'] in {'not-needed', 'complete', 'failed', 'unsupported'} and not item['capture_diagnostics'])
    report['ok'] = report['ok'] and report['execution_completed']
    return report


def _lookup_receipt_name(journal) -> str:
    number = 1
    while any((journal.path / name).exists() for name in
              (f'lookup-{number:03d}.json', f'lookup-{number:03d}-answer.json')):
        number += 1
    return f'lookup-{number:03d}.json'


def _reconcile(root: Path, run: str, journal, claim: dict, target: dict, transport: Any) -> dict:
    """Ask the provider once for the lost answer of the started send, and record what it said."""
    import transport_contract
    import dispatch
    request = c.load(journal.path / 'request.json')
    # A transport without lookup is asked nothing, so it needs no credential.
    selected = claim_authentication(claim, transport, target['offering']['service'])
    credential = _credential(root, transport, target['offering']['service'], expected=selected) \
        if callable(getattr(transport, 'lookup', None)) else None
    key = credential.value if credential is not None else ''
    with stage('provider-lookup'):
        found = transport_contract.lookup_once(transport, request, target['service'], key)
    if found['outcome'] == 'unsupported':
        # Nothing was asked, so there is no new fact to record.
        result = status(root, run)
        result.update(ok=False, execution_completed=False, external_effect=False,
                      warnings=[{'code': 'PROVIDER_LOOKUP_UNSUPPORTED', 'severity': 'warning', 'phase': 'resume',
                                 'message': found['reason'],
                                 'required_action': "Check the provider's own records; record an evidenced statement with "
                                                    'draft-outcome and resume --outcome-file when it holds no such task.'}])
        return result
    receipt = {'outcome': found['outcome'], 'reason': found['reason'], 'transport': target['service']['transport'],
               'request_sha256': c.sha256_file(journal.path / 'request.json'), 'looked_up_at': c.now()}
    if found.get('evidence') is not None:
        receipt['evidence'] = found['evidence']
    name = _lookup_receipt_name(journal)
    if found['outcome'] == 'found':
        answer_name = name.removesuffix('.json') + '-answer.json'
        answer_path = journal.write(answer_name, found['answer'])
        response_sha256 = c.sha256_file(answer_path)
        journal.write(name, {**receipt, 'response_sha256': response_sha256})
        if not dispatch.keep_answer(journal, transport, found['answer']):
            return _unfinished(root, run, journal, claim, transport, found['answer'], answer_name,
                               witnesses=(name,), lookup='found')
        _acknowledge(root, run, journal, claim, witnesses=(name,), reconciled='provider-lookup', lookup='found')
        result = _finish(root, run, journal, transport)
        result.update(external_effect=True)
        return result
    journal.write(name, receipt)
    known_accepted = any(row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
                         and row['data'].get('submission') == 'pending' for row in store.event_rows(root, run))
    _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': 'pending' if known_accepted else 'outcome_unknown',
        'lookup': found['outcome'], 'reason': found['reason'], 'evidence': _evidence(root, run, journal, [name])})
    result = status(root, run)
    result.update(ok=False, execution_completed=False, external_effect=False)
    return result


OUTCOME_STATEMENT_FIELDS = {'run', 'claim', 'outcome', 'actor', 'reason', 'evidence'}


def _response_observations(directory: Path) -> list[Path]:
    """Saved provider observations in send and lookup order."""
    observations = [directory / 'send-observation.json'] if (directory / 'send-observation.json').is_file() else []
    return observations + sorted(directory.glob('lookup-*-answer.json'), key=lambda path: int(path.name.split('-')[1]))


@_public_call
def draft_outcome(root: Path, run: str) -> dict:
    """The statement to fill when the provider's own records hold no task for the started send."""
    import production_workflow as workflow
    _, prepared, _, rows = workflow.load_run(root, run)
    claim = workflow.find(rows, 'dispatch-claim')
    return {'run': run, 'claim': claim['sha256'], 'outcome': 'not_executed', 'actor': '', 'reason': '',
            'evidence': {'path': '', 'sha256': '', 'locator': ''}}


def _record_not_executed(root: Path, run: str, journal, claim: dict, execution_state: dict, outcome_file: str) -> dict:
    """Record the author's evidenced statement that the provider never executed the started send."""
    import production_workflow as workflow
    raw = store.stable_bytes(root, outcome_file)
    statement = c.decode(raw)
    c.exact(statement, OUTCOME_STATEMENT_FIELDS, 'outcome statement')
    c.text(statement['actor'], 'statement actor'); c.text(statement['reason'], 'statement reason')
    c.exact(statement['evidence'], {'path', 'sha256', 'locator'}, 'statement evidence')
    c.sha(statement['evidence']['sha256']); c.text(statement['evidence']['path'], 'evidence path')
    c.text(statement['evidence']['locator'], 'evidence locator')
    compare_exact({'run': run, 'claim': claim['sha256'], 'outcome': 'not_executed'},
                  {key: statement[key] for key in ('run', 'claim', 'outcome')}, pointer='$', phase='resume')
    send = next((item for item in execution_state['steps'] if item['operation'] == 'send'), None)
    if send is None:
        raise ProductionError('OUTCOME_STATEMENT_NOT_APPLICABLE', 'No send started for this execution.', phase='resume', run=run,
                              required_action='Resume this unsent execution, or abandon the task without changing its history.')
    if (journal.path / 'answer.json').is_file() or any(
            row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
            and row['data'].get('submission') == 'pending' for row in store.event_rows(root, run)):
        raise ProductionError('OUTCOME_STATEMENT_CONFLICT', 'The provider answer for this send is saved.', phase='resume', run=run,
                              required_action='Run resume without --outcome-file to register the saved answer.')
    if statement['actor'] not in execution_state['outcome_actors']:
        raise ProductionError('AUTHORIZATION_MISMATCH', 'This actor cannot state the outcome of this execution_state.', phase='resume',
                              run=run, expected=execution_state['outcome_actors'], actual=statement['actor'])
    if c.digest(store.stable_bytes(root, statement['evidence']['path'])) != statement['evidence']['sha256']:
        raise ProductionError('SOURCE_CHANGED', 'The statement evidence differs from its declared digest.', phase='resume',
                              file=statement['evidence']['path'], expected=statement['evidence']['sha256'])
    directory = workflow.run_dir(root, run)
    files = [workflow.file_record(root, directory, outcome_file),
             workflow.file_record(root, directory, statement['evidence']['path'])]
    if files[0]['sha256'] != c.digest(raw) or files[1]['sha256'] != statement['evidence']['sha256']:
        raise ProductionError('SOURCE_CHANGED', 'The statement or its evidence changed while it was read.', phase='resume')
    with store.transaction(root):
        _record_no_effect(root, run, claim['data']['authorizations'][0], claim, send['step'], 'not_executed', files)
        _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': 'not_executed',
                                                 'actor': statement['actor'], 'evidence': files})
    journal.update(status='not-executed')
    _, _, _, _, _, _, _, target, transport = compiled(root, run)
    import production_cleanup
    cleanup = production_cleanup.perform(root, run, journal, claim, target, transport)
    result = status(root, run)
    # Recording a proven non-execution is successful settlement. It does not
    # claim an image was generated, even when owned inputs also need cleanup.
    result.update(execution_completed=False, external_effect=cleanup['external_effect'], warnings=cleanup['warnings'])
    return result


@_public_call
def resume(root: Path, run: str, *, outcome_file: str | None = None) -> dict:
    """Recover the same claim, without freshness gates on already received bytes."""
    import dispatch
    import production_workflow as workflow
    import transport_contract
    initial = workflow.load_run(root, run)
    if initial[1]['task']['execution'] != 'dispatcher':
        if outcome_file is not None:
            raise ProductionError('OUTCOME_STATEMENT_NOT_APPLICABLE', 'Only a dispatcher execution has a send to state.', phase='resume', run=run)
        return status(root, run)
    data = compiled(root, run)
    _, prepared, _, rows, _, _, plan, target, transport = data
    claims = [row for row in rows if row['event'] == 'dispatch-claim']
    if not claims:
        if outcome_file is not None:
            raise ProductionError('OUTCOME_STATEMENT_NOT_APPLICABLE', 'This run has no claimed execution.', phase='resume', run=run)
        return status(root, run)
    claim = claims[-1]
    selected = claim_authentication(claim, transport, target['offering']['service'])
    journal = dispatch.RunJournal.open(c.local(root, claim['data']['journal']))
    execution_state = _claim_execution(rows, prepared, run, claim)
    if outcome_file is not None:
        return _record_not_executed(root, run, journal, claim, execution_state, outcome_file)
    send = next((step for step in execution_state['steps'] if step['operation'] == 'send'), None)
    if send is None:
        for step in execution_state['steps']:
            if step['operation'] != 'upload':
                continue
            index = int(step['step'].split(':', 1)[1])
            refusal = journal.path / f'upload-{index + 1:03d}-refused.json'
            if refusal.is_file():
                # The response may be durable before its event is committed.
                # Recover it before deciding whether earlier uploads can be deleted.
                return _refused_upload(root, run, journal, claim, execution_state['authorization_sha256'],
                                       index, c.load(refusal))
    import production_cleanup
    cleanup = production_cleanup.inspect(data[0], c.load(journal.path / 'request-contract.json'), execution_state, transport)
    if cleanup['eligible'] and (cleanup['state'] in {'pending', 'outcome_unknown'}
            or (cleanup['state'] in {'failed', 'unsupported'} and _registration(root, prepared, rows) == 'registered')):
        # Provider completion and captured output facts are already durable.
        # Cleanup recovery never uploads, generates, or reacquires the image.
        return _cleanup_report(root, run, journal, claim, target, transport)
    observations = _response_observations(journal.path)
    if observations and send is not None:
        observation = observations[-1]
        relative = observation.relative_to(root).as_posix()
        recorded = {item['sha256'] for row in rows for item in row['data'].get('evidence', []) if item['path'] == relative}
        if recorded and recorded != {c.sha256_file(observation)}:
            raise ProductionError('RESPONSE_CORRUPT', 'The saved provider observation differs from its durable receipt.',
                                  phase='resume', run=run, file=str(observation))
        saved = c.load(observation)
        if transport_contract.complete(transport, saved):
            # Recover a crash after saving the observation but before publishing the final answer.
            dispatch.keep_answer(journal, transport, saved)
        elif not (journal.path / 'answer.json').is_file():
            witnessed = bool(recorded)
            if not witnessed:
                return _unfinished(root, run, journal, claim, transport, saved, observation.name)
            if (any(entry.get('url') or entry.get('data') for entry in transport.results(saved))
                    or list(journal.path.glob('response-*.json'))):
                _finish(root, run, journal, transport, answer_name=observation.name, provider_complete=False)
    if (journal.path / 'answer.json').is_file():
        if not transport_contract.complete(transport, c.load(journal.path / 'answer.json')):
            raise ProductionError('RESPONSE_CORRUPT', 'The sealed final answer no longer settles this request.',
                                  phase='resume', run=run, required_action='Restore the recorded answer bytes; do not resend.')
        acknowledged = any(row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
                           and row['data'].get('submission') == 'acknowledged' for row in rows)
        if send is not None and not acknowledged:
            # The answer was saved, and the process stopped before committing its receipt.
            _acknowledge(root, run, journal, claim, reconciled='saved-answer')
        return _finish(root, run, journal, transport)

    if send is not None:
        if (execution_state['effect_results'].get(send['step']) or {}).get('outcome') == 'not_executed':
            result = status(root, run)
            result.update(execution_completed=False)
            return result
        return _reconcile(root, run, journal, claim, target, transport)
    # Only completed, durably saved uploads may be reused before the first send.
    # A step without a response remains unknown and is never reissued.
    for step in execution_state['steps']:
        if step['operation']!='upload' or not step['step'].startswith('upload:'):
            raise ProductionError('REMOTE_OUTCOME_UNKNOWN','Unresolved external step prevents further effects.',phase='resume',run=run)
        index=int(step['step'].split(':',1)[1])
        if not (journal.path/f'upload-{index+1:03d}.json').is_file():
            result=status(root,run);result.update(ok=False,execution_completed=False)
            return result
    # No send has begun: revalidate current conditions before any new effect.
    # Failures here are still attempts to resume this exact claim, so retain the
    # same formal outcome record as failures during transmission.
    try:
        data = compiled(root, run, fresh=True)
        receipts(root, data[1], data[3], plan)
        require_recording(root, prepared)
        credential = _credential(root, transport, target['offering']['service'], expected=selected)
    except BaseException as exc:
        _record_execution_failure(root, run, journal, claim, exc)
        raise
    return _transmit(root, run, journal, c.load(journal.path / 'request-contract.json'), claim,
                     claim['data']['authorizations'][0], target, transport,
                     credential.value if credential is not None else '')


def unclaimed_journals(root: Path) -> list[dict]:
    """Dispatch journals under the Studio's runs/ that no dispatch claim names.

    A journal is written right before its claim, so one without a claim belongs
    to an execute whose claim transaction failed or is still running. A journal
    a claim names is never listed. `eligible` marks one whose owner process has
    ended; cleanup decides whether to remove it.
    """
    from production_compiler import _pid_active
    parent = Path(root) / 'runs'
    if not parent.is_dir():
        return []
    named, unreadable = set(), []
    for item in store.runs(root):
        try:
            for row in store.event_rows(root, item['run_id']):
                if row['event'] == 'dispatch-claim':
                    named.add(row['data']['journal'])
        except INSPECTION_ERRORS:
            unreadable.append(item['run_id'])
    output = []
    for directory in sorted(parent.iterdir()):
        if not directory.is_dir() or directory.is_symlink() or not (directory / 'run.json').is_file():
            continue
        relative = directory.absolute().relative_to(Path(root).absolute()).as_posix()
        if relative in named:
            continue
        row = {'path': str(directory), 'name': directory.name, 'eligible': False, 'reasons': []}
        try:
            document = c.load(directory / 'run.json')
            owner = document.get('owner') or {}
            row.update(production_run=document.get('production_run'), operation_id=owner.get('operation_id'),
                       pid=owner.get('pid'), created_at=document.get('at'))
        except INSPECTION_ERRORS:
            row['reasons'].append('journal metadata is unreadable')
            output.append(row)
            continue
        if row['production_run'] in unreadable:
            row['reasons'].append('the run it names cannot be read, so a claim may still name it')
        elif type(row['pid']) is not int or row['pid'] < 0:
            row['reasons'].append('owner process is not declared')
        elif _pid_active(row['pid']):
            row['reasons'].append('owner process may still be active')
        else:
            row['eligible'] = True
            row['reasons'].append('no dispatch claim names this journal and its owner process has ended')
        output.append(row)
    return output


def _current_task(root: Path) -> dict | None:
    """The open work task from the Studio's work ledger, reported rather than raised when unreadable."""
    import work_ledger
    try:
        task = work_ledger.read_current(root)
    except INSPECTION_ERRORS as exc:
        return {'task_id': None, 'goal': None, 'next': None, 'production_run': None,
                'diagnostics': [from_exception(exc, phase='status', file='work/current.json')]}
    if task is None:
        return None
    import production_authoring_state
    authoring = production_authoring_state.inspect(root, task)
    return {'task_id': task.get('task_id'), 'goal': task.get('goal'), 'next': task.get('next'),
            'production_run': task.get('production_run'),
            'focus': 'authoring' if authoring['pending'] or not task.get('production_run') else 'execution',
            'next_actions': authoring['next_actions'], 'authoring': authoring}


def _logs_by_run(root: Path) -> dict[str, list[str]]:
    from operation_context import list_operations
    buckets: dict[str, list[str]] = {}
    for row in list_operations(root):
        context = (row.get('metadata') or {}).get('context') or {}
        if isinstance(context.get('run'), str):
            buckets.setdefault(context['run'], []).append(row['operation_id'])
    return buckets


def _argv(command: str, root: Path, *arguments: str) -> list[str]:
    from cli_invocation import python_argv
    return python_argv(SCRIPT, command, '--root', str(root), *arguments)


def _action(command: str, root: Path, arguments: list[str], reason: str) -> dict:
    return {'command': command, 'argv': _argv(command, root, *arguments), 'reason': reason}


def _draft_action(root: Path, run: str, kind: str, *, candidate: str | None = None,
                  basis: object = None, grant: str | None = None) -> dict:
    """Name drafts by run, candidate and decision basis, never by a shared filename."""
    identity = c.content_id({'run': run, 'candidate': candidate, 'basis': basis, 'grant': grant})[:24]
    relative = f'production/decisions/{run}/{kind}/{identity}.json'
    path = c.local(root, relative, exists=False)
    apply_name, option = {'review':('review','--file'), 'selection':('select','--file'),
                          'acceptance':('accept','--file'),
                          'execution':('execute','--decisions-file'), 'outcome':('resume','--outcome-file')}[kind]
    apply_args = ['--run', run, option, relative]
    if path.exists():
        return {**_action(apply_name, root, apply_args,
            f'Existing {kind} draft: {relative}. Inspect and complete it from actual evidence, then apply it. '
            'The draft is not itself approval; do not recreate or overwrite it.'),
            'draft': relative, 'requires_author_input': True}
    arguments = ['--run', run]
    if candidate is not None: arguments += ['--candidate', candidate]
    if grant is not None: arguments += ['--grant', grant]
    arguments += ['--out', relative]
    return {**_action('draft-' + kind, root, arguments,
        f'Create the {kind} draft for this exact run and candidate in {relative}. '
        'Fill it from actual review or authority evidence; then use the next status action.'), 'draft': relative}


def _sender_alive(root: Path, claims: list[dict]) -> bool:
    from production_compiler import _pid_active
    if not claims:
        return False
    try:
        document = c.load(c.local(root, claims[-1]['data']['journal']) / 'run.json')
    except INSPECTION_ERRORS:
        return False
    pid = (document.get('sender') or document.get('owner') or {}).get('pid')
    return type(pid) is int and (pid == os.getpid() or _pid_active(pid))


def _registration(root: Path, prepared: dict, rows: list[dict]) -> str:
    """Whether captured candidates are formally registered, and whether Studio still shows each of them."""
    import studio
    candidates = [row for row in rows if row['event'] == 'candidate']
    if not candidates:
        return 'unregistered'
    if prepared['task']['execution'] != 'dispatcher':
        return 'registered'
    invalid = {index for row in rows if row['event'] == 'dispatch-results' for index in row['data'].get('invalid_output_indices', [])}
    recording = prepared['task']['recording']
    try:
        studio.validate_recording_target(root, recording['character'], recording['slot'])
    except INSPECTION_ERRORS:
        # The destination is gone. The run keeps the captured bytes as candidates; nothing shows them.
        return 'unregistered'
    try:
        shown = {(row.get('result') or {}).get('sha256') for row in studio.read_iterations(studio.character_dir(root, recording['character']))
                 if row.get('slot') == recording['slot']}
    except INSPECTION_ERRORS:
        return 'projection-missing'
    wanted = {row['data']['files'][0]['sha256'] for row in candidates if row['data'].get('output_index') not in invalid}
    return 'registered' if wanted <= shown else 'projection-missing'


def _unknown_outcome_action(root: Path, run: str, rows: list[dict]) -> dict:
    """Ask the provider first; after it gave no answer, the author's evidenced statement is next."""
    lookups = [row['data'].get('lookup') for row in rows if row['event'] == 'execution-outcome' and row['data'].get('lookup')]
    if lookups and lookups[-1] == 'no-answer':
        return _draft_action(root, run, 'outcome', basis='provider-no-answer')
    return _action('resume', root, ['--run', run],
        "resume asks the provider for the lost answer where the transport can; it never sends again. When the provider's "
        'records hold no such task, record that with draft-outcome and resume --outcome-file.')


def _next_action(root: Path, report: dict, prepared: dict, rows: list[dict], *, execution_state: dict | None,
                 authority: dict | None) -> dict | None:
    """The one concrete command that moves this run forward, with why."""
    import production_workflow as workflow
    run = report['run']
    mode = prepared['task']['execution']
    events = {row['event'] for row in rows}
    if mode == 'dispatcher' and report['submission'] == 'pending':
        return _action('resume', root, ['--run', run],
            'The provider accepted this task and is still processing. Resume retrieves the same task without sending again.')
    if mode == 'dispatcher' and report['submission'] == 'outcome_unknown':
        return _unknown_outcome_action(root, run, rows)
    cleanup = report['cleanup']
    if mode == 'dispatcher' and cleanup['eligible'] and cleanup['state'] in {'pending', 'outcome_unknown'}:
        reason = ('Recover the original deletion requests by their recorded identifiers; their unknown outcomes never cause a new generation.'
                  if cleanup['state'] == 'outcome_unknown' else
                  'Delete only this run\'s retained uploaded inputs. Captured images stay saved; resume never uploads or generates them again.')
        return _action('resume', root, ['--run', run], reason)
    if report['task_disposition'] == 'completed':
        return None
    if report['task_disposition'] == 'abandoned':
        if report['submission'] == 'outcome_unknown':
            return _unknown_outcome_action(root, run, rows)
        return None
    if mode == 'external' and 'external-claim' in events and report['settlement_open']:
        return {**_action('receive-external', root,
            ['--run', run, '--response', '<actual-response-file>', '--artifact', '<received-file>',
             '--reason', '<observed-outcome>'],
            'Recover the existing host call and receive its actual response and files. Use --image-pointer for inline images, '
            '--pending while the response is incomplete, and --call with --request-pointer for recorded host-call evidence. '
            'This operation never sends another request.'), 'requires_author_input': True}
    if report['selection_ready']:
        return _action('complete', root, ['--run', run],
            'The current selection has a verified review and decision basis; complete the task.')
    if 'selection' in events:
        try:
            _, selected, _ = workflow.current_selection(prepared, rows)
        except (ValueError, KeyError):
            pass
        else:
            if selected['scope'] == 'studio-slot':
                conflicts = [item for item in report['selection_diagnostics'] if item['code'] == 'SLOT_ACCEPTANCE_CONFLICT']
                blocked = [item for item in report['selection_diagnostics']
                           if item['code'] not in {'SLOT_ACCEPTANCE_REQUIRED', 'SLOT_ACCEPTANCE_CONFLICT'}]
                if blocked:
                    return _action('status', root, ['--run', run], blocked[0]['required_action'])
                if not conflicts:
                    return _action('accept', root, ['--run', run],
                        'Resume the recorded slot acceptance and completion using the same selected candidate and saved owner decision.')
    captured = [row['data'] for row in rows if row['event'] == 'capture-status']
    if mode == 'dispatcher' and report['candidates'] and report['registration'] == 'unregistered':
        recording = prepared['task']['recording']
        return _action('resume', root, ['--run', run],
            f"The recording destination {recording['character']}/{recording['slot']} is missing, and the run keeps the "
            'captured candidates. Restore that Studio character and slot, then resume registers them without sending again.')
    if mode == 'dispatcher' and report['submission'] == 'acknowledged' and (
            not captured or captured[-1]['registered'] < captured[-1]['received']
            or report['registration'] == 'projection-missing'):
        return _action('resume', root, ['--run', run],
            'The saved provider answer is not fully registered or shown; resume registers it without sending again.')
    if report['candidates']:
        for candidate in report['candidate_states']:
            if candidate['review'] is None or candidate['selection_requirements']['unassessed_hard_criteria']:
                continue
            if candidate.get('disposition') != 'not_selected':
                if prepared['task']['artifact'] == 'image' and prepared['task'].get('recording'):
                    import production_permissions
                    import production_acceptance
                    try:
                        target, _ = production_acceptance._target(root, run, candidate['candidate'],
                                                                 loaded=(None, prepared, None, rows))
                        expected_slot = production_acceptance.slot_state(root, target['character'], target['slot'])
                    except INSPECTION_ERRORS as exc:
                        diagnostic = from_exception(exc, phase='acceptance')
                        command = 'resume' if diagnostic['code'] == 'STUDIO_CANDIDATE_REQUIRED' else 'status'
                        return _action(command, root, ['--run', run], diagnostic['required_action'])
                    grants = [item['grant'] for item in production_permissions.target_coverage(authority or {'grants': []},
                                                                                              'select', ['delivery'])
                              if not item['missing']]
                    grant = grants[0] if len(grants) == 1 else '<grant-id>'
                    return _draft_action(root, run, 'acceptance', candidate=candidate['candidate'], grant=grant,
                                         basis={'review': candidate['review'], 'authority': c.content_id(authority or {}),
                                                'expected_slot': expected_slot})
                return _draft_action(root, run, 'selection', candidate=candidate['candidate'], basis=candidate.get('review'))
        unreviewed = [row['candidate'] for row in report['candidate_states'] if row['review'] is None] or report['candidates']
        previous = next((row.get('review') for row in report['candidate_states'] if row['candidate'] == unreviewed[0]), None)
        return _draft_action(root, run, 'review', candidate=unreviewed[0], basis=previous)
    if report['submission'] == 'unclaimed' and 'handoff' not in events and report['readiness'] == 'blocked':
        diagnostic = report['readiness_diagnostics'][0]
        if not report['freshness_diagnostics']:
            # Only the committed authority is unreadable; the run's own inputs are current.
            return _action('status', root, ['--run', run], diagnostic['required_action'])
        # Nothing was handed over yet, so a changed source is prepared again instead of passed on.
        return _action('prepare', root, ['--task', prepared['task_path']], diagnostic['required_action'])
    if mode == 'external' and prepared['task'].get('image_input') and 'external-claim' not in events:
        if report['readiness'] == 'authorization_required':
            grants = [item['id'] for item in (authority or {}).get('grants', []) if not item.get('revoked_at')]
            grant = grants[0] if len(grants) == 1 else '<grant-id>'
            return _draft_action(root, run, 'execution', grant=grant, basis=c.content_id(authority or {}))
        return _action('execute', root, ['--run', run],
            'Hand the exact request to the host once under the current separate direction and submission authorizations.')
    if mode == 'dispatcher':
        submission = report['submission']
        if submission == 'unclaimed':
            if report['readiness'] == 'authorization_required':
                grants = [item['id'] for item in (authority or {}).get('grants', []) if not item.get('revoked_at')]
                grant = grants[0] if len(grants) == 1 else '<grant-id>'
                return _draft_action(root, run, 'execution', grant=grant, basis=c.content_id(authority or {}))
            return _action('execute', root, ['--run', run], 'Every prepared operation has a current exact authorization.')
        if submission == 'claimed':
            if any(item['result'] == 'rejected' for item in report['effects']):
                return _action('repeat', root, ['--from', run, '--prepare'],
                    'The provider refused an upload. Prepare a new request and obtain its exact approval.')
            return _action('resume', root, ['--run', run],
                'No send has started; resume rechecks current conditions and continues the same execution.')
        if submission == 'send_started':
            return _action('status', root, ['--run', run], 'The owner operation is still sending; check again after it ends.')
        if submission == 'outcome_unknown':
            return _unknown_outcome_action(root, run, rows)
        if submission == 'not_executed':
            return _action('repeat', root, ['--from', run, '--prepare'],
                'The provider never executed the send; prepare an intentional new run.')
        return _action('repeat', root, ['--from', run, '--prepare'],
            'The provider answered without an image to register; prepare an intentional new run or a variant.')
    if 'handoff' not in events:
        return _action('handoff', root, ['--run', run, '--recipient', '<recipient>', '--method', mode if mode in {'conversation', 'manual'} else 'manual',
                                         '--authorization', '<direction-authorization>'],
            'Hand the consumer to its recipient under an exact direction authorization from handoff-intent and authorize.')
    if mode == 'external' and 'external-claim' not in events:
        return _action('claim-external', root, ['--run', run, '--count', '<count>', '--authorization', '<submit-authorization>'],
            'Claim the host tool call under an exact submission authorization from external-intent and authorize.')
    return _action('capture', root, ['--run', run, '--artifact', '<received-file>', '--note', '<provenance>'],
        'Record the actually received result as a candidate.')


def _run_authentication(root: Path, directory: Path, prepared: dict, claims: list[dict],
                         report: dict, execution_state: dict | None) -> dict | None:
    """Inspect authentication for this run's next provider step, using its recorded source."""
    import transport_contract
    if prepared['task']['execution'] != 'dispatcher':
        return None
    target = c.load(directory / 'execution-target.json')
    transport = transport_contract.load(target['service']['transport'])
    selected = claim_authentication(claims[-1], transport, target['offering']['service']) if claims else None
    required = False
    if not transport_contract.credential_free(transport):
        if not claims:
            required = report['task_disposition'] == 'open' and report['readiness'] != 'blocked'
        elif (report['next_action'] or {}).get('command') == 'resume':
            journal = c.local(root, claims[-1]['data']['journal'])
            observations = _response_observations(journal)
            saved_answer = ((journal / 'answer.json').is_file() or bool(observations and
                transport_contract.complete(transport, c.load(observations[-1]))))
            if report['cleanup']['eligible'] and report['cleanup']['state'] in {'pending', 'outcome_unknown'}:
                required = True
            elif not saved_answer and report['submission'] in {'pending', 'outcome_unknown'}:
                required = callable(getattr(transport, 'lookup', None))
            elif not saved_answer and report['submission'] == 'claimed' and report['readiness'] != 'blocked':
                steps = execution_state['steps'] if execution_state else []
                required = (not any(item['result'] == 'rejected' for item in report['effects'])
                    and all(step['operation'] == 'upload' and step['step'].startswith('upload:')
                            and (journal / f"upload-{int(step['step'].split(':', 1)[1]) + 1:03d}.json").is_file()
                            for step in steps))
    return authentication_readiness(root, transport, target['offering']['service'], required=required, expected=selected)


def _run_status(root: Path, item: dict, logs: dict[str, list[str]], authorities: dict) -> dict:
    import production_workflow as workflow
    identifier = item['run_id']
    directory, prepared, consumer, rows = workflow.load_run(root, identifier)
    claims = [row for row in rows if row['event'] == 'dispatch-claim']
    external_claims = [row for row in rows if row['event'] == 'external-claim']
    captures = [row for row in rows if row['event'] == 'capture-status']
    submission, effects = submission_state(rows, prepared, identifier, sender_alive=_sender_alive(root, claims))
    capture = captures[-1]['data']['capture'] if captures else 'none'
    candidates = [row['sha256'] for row in rows if row['event'] == 'candidate']
    states = accounting.derive(rows, prepared, identifier)
    settlement_open = False
    if external_claims:
        capture = 'complete' if len(candidates) == external_claims[-1]['data']['count'] else 'partial' if candidates else 'none'
        settlement_open = any(entry['status'] != 'complete' for entry in states.values())
    claim = (claims or external_claims or [None])[-1]
    execution_state = _claim_execution(rows, prepared, identifier, claim) if claim else None
    candidate_states = [workflow.candidate_state(root, identifier, key, loaded=(directory, prepared, None, rows)) for key in candidates]
    freshness = workflow.freshness_diagnostics(root, identifier, loaded=(directory, prepared, None, rows))
    events = {row['event'] for row in rows}
    mode = prepared['task']['execution']
    task_disposition = 'completed' if 'completion' in events else 'abandoned' if 'abandoned' in events else 'open'
    selection_ready = False
    selection_diagnostics = []
    if 'selection' in events:
        try:
            selection, chosen, _ = workflow.current_selection(prepared, rows)
            if chosen['scope'] == 'studio-slot':
                from production_acceptance import verify_slot
                verify_slot(root, identifier, selection, rows=rows, require_current='completion' not in events)
            selection_ready = True
        except ValueError as exc:
            selection_diagnostics.append(from_exception(exc, phase='selection'))
    readiness = 'blocked' if freshness else 'ready'
    readiness_diagnostics = list(freshness)
    task_id = prepared['task']['task_id']
    if task_id not in authorities:
        try:
            authorities[task_id] = (store.authority(root, task_id, required=False), None)
        except INSPECTION_ERRORS as exc:
            authorities[task_id] = (None, from_exception(exc, phase='authority'))
    authority, authority_error = authorities[task_id]
    if authority_error is not None:
        readiness = 'blocked'
        readiness_diagnostics.append(authority_error)
    if not claims and mode == 'dispatcher' and readiness != 'blocked' and task_disposition == 'open':
        plan = c.load(directory / 'execution-plan.json')
        try:
            receipts(root, prepared, rows, plan)
        except INSPECTION_ERRORS as exc:
            readiness = 'authorization_required'
            readiness_diagnostics.append(from_exception(exc, phase='readiness'))
    if not external_claims and mode == 'external' and consumer.get('image_input') and readiness != 'blocked' and task_disposition == 'open':
        try:
            plan = c.load(directory / 'execution-plan.json')
            receipts(root, prepared, rows, plan,
                required_action='Complete the separate decisions in draft-execution, then execute hands the exact input to the host once.')
        except INSPECTION_ERRORS as exc:
            readiness = 'authorization_required'
            readiness_diagnostics.append(from_exception(exc, phase='readiness'))
    reviewed = [row for row in candidate_states if row['review'] is not None]
    review_state = ('unreviewed' if not reviewed else
        'complete' if len(reviewed) == len(candidate_states) and all(not row['unassessed_criteria'] for row in reviewed)
        else 'partial')
    report = {'run': identifier, 'task_id': task_id, 'integrity': 'intact',
        'preparation': 'prepared', 'readiness': readiness, 'readiness_diagnostics': readiness_diagnostics,
        'submission': submission, 'send_started': submission not in {'unclaimed', 'claimed'},
        'effects': effects, 'capture': capture, 'capture_diagnostics': captures[-1]['data'].get('diagnostics', []) if captures else [],
        'registration': _registration(root, prepared, rows), 'review': review_state, 'task_disposition': task_disposition,
        'candidates': candidates, 'candidate_states': candidate_states, 'freshness_diagnostics': freshness,
        'selection_diagnostics': selection_diagnostics, 'selection_ready': selection_ready, 'settlement_open': settlement_open,
        'execution': None if execution_state is None else {'execution_id': execution_state['execution_id'], 'status': execution_state['status']},
        'journal': claims[-1]['data']['journal'] if claims else None,
        'logs': logs.get(identifier, [])}
    import production_cleanup
    report['cleanup'] = {'state': 'not-needed', 'eligible': False, 'uploaded': 0, 'deleted': 0, 'retained': 0, 'items': []}
    if mode == 'dispatcher':
        import transport_contract
        target = c.load(directory / 'execution-target.json')
        transport = transport_contract.load(target['service']['transport'])
        media_directory = c.local(root, claims[-1]['data']['journal']) if claims else directory
        rendered = c.load(media_directory / 'request-contract.json')
        report['cleanup'] = production_cleanup.inspect(directory, rendered, execution_state, transport)
    report['next_action'] = _next_action(root, report, prepared, rows, execution_state=execution_state, authority=authority)
    action = report['next_action']
    if action and action['command'] in {'draft-execution', 'execute', 'draft-review', 'review', 'draft-acceptance', 'accept'}:
        candidate = None
        if action['command'] in {'draft-review', 'review', 'draft-acceptance', 'accept'}:
            if '--candidate' in action['argv']:
                candidate = action['argv'][action['argv'].index('--candidate') + 1]
            elif action.get('draft'):
                candidate = c.load(c.local(root, action['draft'])).get('candidate')
            if candidate is None and action['command'] == 'accept':
                try:
                    candidate = workflow.current_selection(prepared, rows)[1]['candidate']
                except (ValueError, KeyError):
                    pass
            phases = ['review'] if action['command'] in {'draft-acceptance', 'accept'} else ['observe', 'review']
        else:
            phases = ['input', 'decision']
        action['read_context'] = [_action('workspace', root,
            ['--run', identifier, '--phase', phase] + (['--candidate', candidate] if candidate else []),
            'Read this context when needed, in the listed order; existing knowledge does not require another read record.')
            for phase in phases]
    authentication = _run_authentication(root, directory, prepared, claims, report, execution_state)
    report['authentication'] = authentication
    if authentication and authentication['required'] and not authentication['available']:
        report['readiness'] = 'configuration_required'
        report['readiness_diagnostics'] += authentication['diagnostics']
        report['next_action'] = authentication['diagnostics'][0]['next_action']
    return report


def _blocked_run(root: Path, identifier: str, exc: BaseException, logs: dict[str, list[str]]) -> dict:
    diagnostic = from_exception(exc, phase='integrity')
    return {'run': identifier, 'integrity': 'blocked', 'diagnostics': [diagnostic], 'logs': logs.get(identifier, []),
            'next_action': _action('status', root, ['--run', identifier], diagnostic['required_action'])}


@_public_call
def status(root: Path, run: str | None = None) -> dict:
    """Every run's state on its separate axes, isolating each failure to the part it affects."""
    import production_workflow as workflow
    from production_compiler import staging_cleanup, unregistered_publications
    root = Path(root)
    result = {'ok': True, 'current_task': _current_task(root), 'runs': [], 'diagnostics': [],
              'external_effect': False}
    if run is not None:
        workflow.run_identifier(run)
    try:
        items = store.runs(root)
    except INSPECTION_ERRORS as exc:
        items = []
        result['diagnostics'].append(from_exception(exc, phase='status'))
    else:
        if run is not None:
            items = [row for row in items if row['run_id'] == run]
            if not items:
                raise ProductionError('RUN_NOT_REGISTERED', 'No formal run has this ID.', phase='status', run=run)
    try:
        logs = _logs_by_run(root)
    except INSPECTION_ERRORS as exc:
        logs = {}
        result['diagnostics'].append(from_exception(exc, phase='logs'))
    authorities: dict = {}
    for item in items:
        try:
            result['runs'].append(_run_status(root, item, logs, authorities))
        except INSPECTION_ERRORS as exc:
            result['runs'].append(_blocked_run(root, item['run_id'], exc, logs))
    current = result['current_task']
    if current is not None and current.get('focus') == 'execution':
        selected = next((item for item in result['runs'] if item['run'] == current['production_run']), None)
        if selected is None:
            current['next_actions'] = [_action('status', root, ['--run', current['production_run']],
                'Inspect the existing run for the current work task and follow its saved execution state.')]
        else:
            current['next_actions'] = [selected['next_action']] if selected['next_action'] else []
    authority_errors = [error for _, error in authorities.values() if error is not None]
    result['ok'] = (not result['diagnostics'] and not authority_errors
                    and all(row['integrity'] == 'intact' for row in result['runs']))
    result['execution_records'] = accounting.summary(root, run=run, isolate=True)
    try:
        staging = staging_cleanup(root)
        result['staging'] = [row['name'] for row in staging['items']]
        result['staging_details'] = staging['items']
    except INSPECTION_ERRORS as exc:
        result['staging'] = []
        result['staging_details'] = [{'diagnostics': [from_exception(exc, phase='cleanup')]}]
    try:
        result['unclaimed_journals'] = unclaimed_journals(root)
    except INSPECTION_ERRORS as exc:
        result['unclaimed_journals'] = [{'diagnostics': [from_exception(exc, phase='cleanup')]}]
    try:
        result['unregistered_publications'] = unregistered_publications(root, store.runs(root))
    except INSPECTION_ERRORS as exc:
        result['unregistered_publications'] = [{'diagnostics': [from_exception(exc, phase='publication')]}]
    return result
