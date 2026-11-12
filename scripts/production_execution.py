"""Execute and recover the prepared request, with authored judgments kept separately.

The production transaction owns permission and execution claims. Network I/O
starts only after that transaction commits. Recovery reads durable answers; it
never interprets a timeout as evidence that a request was not sent. A lost or
unfinished answer is asked for again only through the transport's lookup, and
an author's evidenced statement that the provider holds no such task is
recorded as one.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import datetime
import functools
import math
import os
import sqlite3
import time
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
# The seconds resume --watch waits between lookups of a pending provider task, and in all. The included
# service record polls an asynchronous task about every ten seconds. The limit keeps one watch within
# about two minutes, a common time limit of an agent's command; a pending run is watched again from
# its next action.
WATCH_LIMIT_SECONDS = 120


def _public_call(function):
    """Run one public entry on the checked studio root, in one verification scope.

    The root is checked and resolved once here (`execution_contract._root`), so a
    root given through a directory junction names the same files as the paths
    the run and the Studio record. The stages of the call reuse what the call
    already verified. Each production transaction still starts its own scope.
    `accounting.begin_step` checks the saved run, fixed runtime and current
    imported authority again even inside a caller's transaction.
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


def compiled(root: Path, run: str, *, fresh: bool = False, loaded=None) -> tuple:
    import production_workflow as workflow
    import transport_contract
    loaded = workflow.assert_current(root, run) if fresh else loaded or workflow.read_run(root, run)
    directory, prepared, consumer, rows = loaded
    if prepared['task']['execution'] != 'dispatcher' or 'package.json' not in loaded.artifacts:
        raise ProductionError('EXECUTION_NOT_APPLICABLE', 'This operation needs a prepared model request.', phase='execution', run=run,
                              required_action='Follow the next action of status --run; this run holds no sealed dispatcher '
                                              'request to send or resume.')
    package = loaded.artifacts['package.json']
    rendered = loaded.artifacts['request-contract.json']
    plan = loaded.artifacts['execution-plan.json']
    target = loaded.artifacts['execution-target.json']
    transport = transport_contract.load(target['service']['transport'])
    current_transport = c.sha256_file(Path(transport.__file__))
    if target['transport_sha256'] != current_transport:
        raise ProductionError('TRANSPORT_IMPLEMENTATION_CHANGED', 'The installed transport differs from the one sealed for this run.',
                              phase='integrity', run=run, expected=target['transport_sha256'], actual=current_transport,
                              required_action='Use the installation that prepared this run to recover its existing provider task. Do not resend it.')
    transport.endpoint(target['service'])
    return directory, prepared, consumer, rows, package, rendered, plan, target, transport


@_public_call
def draft_execution(root: Path, run: str, grant: str | None = None) -> dict:
    """Draft the independent judgments of the prepared operations in one editing document."""
    import production_decisions
    return production_decisions.draft(root, run, grant)


def authorize_decisions(root: Path, run: str, path: str, prepared: dict, plan: dict) -> None:
    import production_decisions
    production_decisions.authorize(root, run, path, prepared, plan)


@contextlib.contextmanager
def _imported_authority_note(root: Path, authority: store.CurrentAuthority | None):
    """Name an unimported edit of the authority file in a refused authorization, ahead of its own repair.

    Decisions are checked against the imported authority, so a grant or stop
    condition added only in the file shows here as a mismatch.
    """
    try:
        yield
    except ProductionError as exc:
        edited = store.edited_authority_source(root, authority)
        if edited is not None:
            exc.diagnostic.required_action = (
                f'{edited["path"]} changed after its import and this check read the imported authority; when the '
                'edit records an actual authority change, import it with authority-import (status --run gives the '
                'exact command in authority.update_action) and draft the decisions again. '
                + exc.diagnostic.required_action)
            exc.diagnostic.details['authority_source_edited'] = edited
        raise


def receipts(root: Path, prepared: dict, rows: list[dict], plan: dict, *,
             authority: store.CurrentAuthority | None = None,
             loaded=None,
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
                authority = authority or workflow.current_authority(root, prepared)
                request = workflow._permission(root, prepared, rows, row['sha256'], **intent,
                                               authority=authority, loaded=loaded)
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
    recording = prepared['task'].get('recording')
    if recording is None:
        validate_recording(root, prepared['task'], {})
        return
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
    directory, prepared, _, rows = workflow.read_run(root, run)
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


def _journal(root: Path, run: str, data: tuple, *, loaded=None):
    import dispatch
    import production_workflow as workflow
    from publication_artifacts import ArtifactSet
    directory, prepared, _, _, package, rendered, plan, target, _ = data
    loaded = loaded if loaded is not None else workflow.read_run(root, run)
    artifacts = ArtifactSet(directory, loaded.manifest['files'])
    recording = prepared['task'].get('recording')
    operation = 'upscale' if package.get('artifact_type')=='upscale-request' else 'generation'
    if operation == 'upscale':
        companion = 'upscale.references'
    else:
        from build_generation_payload import validate_generation_package_carrier_paths
        companion = validate_generation_package_carrier_paths(package['prepared_reference_set'], package_root=directory)
    journal = dispatch.RunJournal.create(root, operation=operation, character=recording['character'] if recording else None,
        slot=recording['slot'] if recording else None, service=plan['service'], transport=plan['transport'], model=plan['model'],
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
        boundary = workflow.read_current(root, run)
        loaded = boundary.view
        _, prepared, consumer, rows = loaded
        plan = loaded.artifacts['execution-plan.json']
        if prepared['task']['execution'] not in {'dispatcher', 'external'} or not plan['operations']:
            raise ProductionError('EXECUTION_NOT_APPLICABLE', 'This operation needs a prepared model request.',
                                  phase='execution', run=run,
                                  required_action='Follow the next action of status --run; an external run without an image '
                                                  'request is handed over with handoff and claimed with claim-external.')
        if any(row['event'] == 'external-claim' for row in rows):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already handed its request to the host.',
                phase='execution', run=run,
                required_action='Recover that host call and receive its actual result. A new call needs a newly prepared run.')
        from image_input import external_delivery
        delivery = external_delivery(consumer['image_input'], run_directory=loaded.directory,
                                     read_object=loaded.evidence.read)
        authority = workflow.current_authority(root, prepared)
        with _imported_authority_note(root, authority):
            if decisions_file is not None:
                production_decisions._authorize_from(root, loaded, authority, decisions_file, plan)
                loaded = workflow.read_run(root, run)
            tokens = receipts(root, loaded.prepared, loaded.rows, plan, authority=authority, loaded=loaded)
        hand = plan['handoff']
        workflow._handoff_from(root, loaded, authority, hand['recipient'], hand['method'], tokens['direction'])
        loaded = workflow.read_run(root, run)
        claim = workflow._claim_external_from(root, loaded, authority, plan['quantities']['outputs'], tokens['submit'])
    return _external_instruction(run, claim, delivery)


def _external_instruction(run: str, claim: dict, delivery: dict) -> dict:
    return {'artifact_type': 'external-execution-instruction',
            'run': run, 'state': 'host-call-required', 'external_effect': False,
            'host_request': {'claim': claim['sha256'], **delivery},
            'instruction': 'Invoke this exact host request once. Save the actual response and returned media, '
                           'then use receive-external. After interruption, recover the same call; do not invoke it again.'}


def external_instruction(root: Path, run: str, *, claim: dict) -> dict:
    """Expose the same saved host call for the explicit handoff/claim commands."""
    import image_input
    import production_workflow as workflow
    loaded = workflow.read_run(root, run)
    binding = loaded.consumer.get('image_input')
    if binding is None:
        return claim
    delivery = image_input.external_delivery(binding, run_directory=loaded.directory,
                                             read_object=loaded.evidence.read)
    return _external_instruction(run, claim, delivery)


@_public_call
def execute(root: Path, run: str, *, decisions_file: str | None = None) -> dict:
    import production_workflow as workflow
    import studio

    loaded = workflow.read_run(root, run)
    if loaded.prepared['task']['execution'] == 'external':
        return _execute_external(root, run, decisions_file=decisions_file)

    with stage('execution-preflight'):
        # The publication read above verified the sealed package, request and
        # target by content. They are sent as prepared, not built again. The
        # claim transaction checks the saved run before any journal or handoff
        # is written; each later external step checks them again.
        data = compiled(root, run, loaded=loaded)
        directory, prepared, _, rows, package, rendered, plan, target, transport = data
        if any(row['event'] == 'dispatch-claim' for row in rows):
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'This run already owns an execution.', phase='execution', run=run,
                required_action='Use resume for this execution, variant for changed input, or repeat for an intentional new run.')
        require_recording(root, prepared)
        credential = _credential(root, transport, target['offering']['service'])
        if current():
            current().link(run=run, task=prepared['task']['task_id'])
            current().durable()
        # Every external step performs its own fresh integrity check inside
        # accounting.begin_step, after authorization and immediately before I/O.
        # That check is independent of the presence of a diagnostic operation.

    with stage('authorization-and-claim'), store.transaction(root):
        boundary = workflow.read_current(root, run)
        loaded = boundary.view
        authority = workflow.current_authority(root, loaded.prepared)
        with _imported_authority_note(root, authority):
            if decisions_file is not None:
                import production_decisions
                production_decisions._authorize_from(root, loaded, authority, decisions_file, plan)
                loaded = workflow.read_run(root, run)
            tokens = receipts(root, loaded.prepared, loaded.rows, plan, authority=authority, loaded=loaded)
        # The journal is the dispatcher's own copy of the consumer, so writing it
        # is the handoff. It is written only after every check above passed, right
        # before the claim. A transaction that fails after this point leaves a
        # journal no claim names; unclaimed_journals() lists it.
        journal, saved = _journal(root, run, data, loaded=loaded)
        hand = plan['handoff']
        workflow._handoff_from(root, loaded, authority, hand['recipient'], hand['method'],
                               tokens['direction'], journal=journal.path)
        loaded = workflow.read_run(root, run)
        submission = next(item for item in plan['operations'] if item['operation'] == 'submit')
        claim = workflow._claim_dispatch_from(root, loaded, authority, package, journal.path, submission,
                                              tokens['submit'], rendered=saved,
                                              authentication=credential.selection if credential is not None else None)
    return _transmit(root, run, journal, saved, claim, tokens['submit'], target, transport,
                     credential.value if credential is not None else '', previous_runtime=boundary.runtime)


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
        directory, prepared, _, rows = workflow.read_run(root, run)
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


def _unsaved_uploads(journal: Path, state: dict | None) -> list[int]:
    """Media positions whose upload started and left no provider answer in the journal.

    An upload's response or refusal is saved before its result is recorded, so
    recovery continues from either file. A started upload with neither is never
    sent again: the provider may or may not hold it. Neither is one whose stopped
    attempt recorded its outcome as unknown, whatever the journal holds later.
    """
    positions = []
    for step in state['steps'] if state else []:
        if step['operation'] != 'upload':
            continue
        index = int(step['step'].split(':', 1)[1])
        name = f'upload-{index + 1:03d}'
        if (step['step'] in state['unknown_uploads']
                or not any((journal / (name + suffix)).is_file() for suffix in ('.json', '-refused.json'))):
            positions.append(index)
    return positions


def _unanswered_upload_name(index: int) -> str:
    """The journal file that keeps what an upload exchange without an answer returned."""
    return f'upload-{index + 1:03d}-indeterminate.json'


def _keep_unanswered_upload(journal, index: int, cause: BaseException) -> None:
    """Save the reason an upload exchange ended without an answer, with the HTTP status and body of one that came.

    A service can answer and still leave the outcome unknown, for example with an
    issued media identifier whose stored content could not be verified. That
    answer is the author's evidence for the provider's records. A failure to save
    it leaves the unknown outcome reported as before.
    """
    import transport_contract
    evidence = (cause.evidence() if isinstance(cause, transport_contract.Indeterminate) else
                {'outcome': transport_contract.INDETERMINATE,
                 'reason': f'the upload ended without a provider answer ({type(cause).__name__})',
                 'http_status': None, 'body': None})
    try:
        journal.write(_unanswered_upload_name(index), evidence)
    except (ValueError, OSError):
        if current():
            current().event('upload_evidence_unavailable', phase='reference-upload')


def _upload_blocker(root: Path, claims: list[dict], rows: list[dict], state: dict | None) -> tuple[str, list[int]] | None:
    """Why a claimed execution cannot continue from the uploads it started before its send.

    The result is ('running', positions) while the operation that started them
    still runs, ('unknown', positions) once it ended without their provider
    answers, and None when every started upload left its answer in the journal.
    Status and resume both decide from this one reading.
    """
    claim = claims[-1]
    positions = _unsaved_uploads(c.local(root, claim['data']['journal']), state)
    if not positions:
        return None
    if {f'upload:{index}' for index in positions} <= set(state['unknown_uploads']):
        return 'unknown', positions
    started = max((index for index, row in enumerate(rows)
                   if row['event'] == 'external-step' and row['data'].get('claim') == claim['sha256']
                   and row['data'].get('operation') in {'upload', 'send'}), default=-1)
    # A stopped attempt records an execution outcome after its last upload or send.
    # Without one, the process the journal names decides.
    stopped = any(row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
                  for row in rows[started + 1:])
    return ('unknown' if stopped or not _sender_alive(root, claims) else 'running'), positions


def _unknown_upload_action(root: Path, run: str) -> dict:
    """The continuation of an execution whose started upload has no saved provider answer."""
    return _action('repeat', root, ['--from', run, '--prepare'],
        'An upload started and no provider response was saved, so its outcome is unknown and it is never sent again. '
        'This execution cannot reach its send: prepare an intentional new run and obtain its exact approval. '
        "Check the provider's own records when the stored input or its charge matters.")


def _upload_outcome_unknown(root: Path, run: str, journal, positions: list[int], *, phase: str,
                            cause: BaseException | None = None, cleanup: dict | None = None,
                            cleanup_failure: dict | None = None) -> ProductionError:
    """The diagnostic of uploads that started without a saved provider answer, with the continuation.

    `evidence` lists the journal files that keep what each exchange returned.
    `cleanup` is the deletion of the inputs this execution uploaded before, as
    production_cleanup.perform reported it, and `cleanup_failure` the diagnostic
    of a deletion that stopped.
    """
    inputs = ', '.join(str(index + 1) for index in positions)
    base = journal.path.absolute().relative_to(Path(root).absolute()).as_posix()
    evidence = [base + '/' + _unanswered_upload_name(index) for index in positions
                if (journal.path / _unanswered_upload_name(index)).is_file()]
    details = {} if cause is None else {'cause': type(cause).__name__ + ': ' + str(cause)}
    if evidence:
        details['evidence'] = evidence
    action = _unknown_upload_action(root, run)
    release = ''
    if cleanup is not None:
        details['cleanup'] = cleanup['cleanup']
        if cleanup['warnings']:
            details['cleanup_warnings'] = cleanup['warnings']
        if cleanup['cleanup']['eligible'] and cleanup['cleanup']['state'] in {'pending', 'outcome_unknown'}:
            action = _cleanup_action(root, run, cleanup['cleanup'])
            release = ('First run resume for this run: it deletes the inputs this execution uploaded before and never '
                       'uploads or sends again. ')
    elif cleanup_failure is not None:
        details['cleanup_warnings'] = [cleanup_failure]
        action = _action('status', root, ['--run', run],
            'Deleting the inputs this execution uploaded before stopped: ' + cleanup_failure['message'] + ' '
            + cleanup_failure['required_action'])
        release = 'Deleting the inputs this execution uploaded before stopped; follow the next action of status --run. '
    kept = (' What the exchange returned is saved in ' + ', '.join(evidence) + '.') if evidence else ''
    return ProductionError('REMOTE_OUTCOME_UNKNOWN',
        f'An upload started without a saved provider response (media input {inputs}); its outcome is unknown '
        'and it is not sent again.', phase=phase, run=run,
        steps=[f'upload:{index}' for index in positions], next_action=action,
        required_action='This execution cannot reach its send. ' + release + 'Prepare an intentional new run with '
                        'repeat --from ' + run + " --prepare and obtain its exact approval. Check the provider's own "
                        'records when the stored input or its charge matters.' + kept, **details)


class _UploadUnanswered(Exception):
    """An upload exchange that ended without a saved provider answer, which `_transmit` settles on its own."""

    def __init__(self, index: int, cause: BaseException | None) -> None:
        super().__init__(f'upload:{index}')
        self.index, self.cause = index, cause


def _stop_on_unknown_upload(root: Path, run: str, journal, claim: dict, target: dict, transport: Any,
                            positions: list[int], *, phase: str, cause: BaseException | None = None) -> ProductionError:
    """Settle what uploads without a saved provider answer settle, and return their diagnostic.

    Such an upload is never sent again, so this execution can never reach its
    send. What the exchange returned is kept in the journal, the stopped attempt
    is recorded once with the uploads whose outcome is unknown, and the inputs
    this execution uploaded before are deleted, as after a refused upload. An
    upload of unknown outcome has no recorded identifier and is never deleted.
    """
    import production_workflow as workflow
    if cause is not None:
        _keep_unanswered_upload(journal, positions[0], cause)
    error = _upload_outcome_unknown(root, run, journal, positions, phase=phase, cause=cause)
    try:
        _, prepared, _, rows = workflow.read_run(root, run)
        recorded = set(_claim_execution(rows, prepared, run, claim)['unknown_uploads'])
    except (ValueError, OSError):
        recorded = set()
    if not {f'upload:{index}' for index in positions} <= recorded:
        _record_execution_failure(root, run, journal, claim, error, unknown_uploads=positions)
    try:
        import production_cleanup
        cleanup = production_cleanup.perform(root, run, journal, claim, target, transport)
    except (ValueError, OSError) as exc:
        # A stopped deletion is reported beside the unknown upload; it never hides it.
        return _upload_outcome_unknown(root, run, journal, positions, phase=phase, cause=cause,
                                       cleanup_failure=from_exception(exc, phase='input-cleanup'))
    return _upload_outcome_unknown(root, run, journal, positions, phase=phase, cause=cause, cleanup=cleanup)


def _transmit(root: Path, run: str, journal, rendered: dict, claim: dict, authorization: str,
              target: dict, transport: Any, key: str, *, previous_runtime=None) -> dict:
    """Carry fixed metadata while each external step reacquires its actual inputs."""
    import dispatch
    import request_contract as rc
    import transport_contract
    import production_workflow as workflow
    try:
        media_ids = {}
        # The journal names the operation that transmits now, for its uploads and its send.
        journal.update(sender=_owner())
        with stage('reference-upload'):
            for index, item in enumerate(rendered['media']):
                raw = c.read(Path(item['path']))
                if c.digest(raw) != item['sha256'] or len(raw) != item['size']:
                    raise ProductionError('ARTIFACT_CORRUPT', 'Saved reference bytes changed.', phase='before-send', file=item['path'],
                        expected=item['sha256'],
                        required_action='Copy the file at the same relative path under ' + str(workflow.run_dir(root, run))
                                        + ' to this journal file, then run resume for this run.')
                _,prepared,_,rows=workflow.read_run(root,run)
                state=accounting.require_active(rows,prepared,run,authorization)
                step=f'upload:{index}'
                started=any(entry['step']==step for entry in state['steps'])
                if not started:
                    accounting.begin_step(root, run, authorization, claim=claim['sha256'], step=step, operation='upload',
                                          previous_runtime=previous_runtime)
                    try:
                        source=item['upload_source']
                        uploaded=transport.upload_media(raw,item['media_type'],target['service'],key,
                            source_url=source['url'] if source['kind']=='url' else None)
                    except transport_contract.Refused as refusal:
                        return _refused_upload(root, run, journal, claim, authorization, index, refusal.evidence(),
                                               previous_runtime=previous_runtime)
                    except (ValueError, OSError) as exc:
                        # The step is committed and no answer was saved, whatever ended the exchange.
                        raise _UploadUnanswered(index, exc) from exc
                    c.exact(uploaded,{'provider_id','response','usage'},'transport upload result')
                    journal.write(f'upload-{index + 1:03d}.json', {'index': index, 'source': item['path'],
                        'source_sha256': item['sha256'], **uploaded})
                elif not (journal.path/f'upload-{index+1:03d}.json').is_file():
                    raise _UploadUnanswered(index, None)
                media_ids[index]=_upload_receipt(root,run,journal,rendered,claim,authorization,index)['provider_id']
        request = rc.materialize(rendered, media_ids)
        rc.validate_wire(rendered, request, media_ids)
        journal.write('request.json', request)
        # The identifiers the service knows this request by, as sent, so a lost
        # answer can be looked up without reading the journal.
        identifiers = [{'field': list(path), 'value': rc.get(request, path)} for path in rendered['layout']['management']]
        with stage('provider-wait'):
            accounting.begin_step(root, run, authorization, claim=claim['sha256'], step='send', operation='send',
                                  identifiers=identifiers, previous_runtime=previous_runtime)
            journal.update(status='sending')
            answer = dispatch.send_and_keep(journal, transport, request, target['service'], key)
        if answer is None:
            _append(root, run, 'execution-outcome', {'claim': claim['sha256'], 'submission': 'outcome_unknown',
                'reason': 'The send started without a saved provider answer.',
                'evidence': _evidence(root, run, journal, ['request-contract.json', 'request.json', 'indeterminate.json'])})
            result = _status(root, run, previous_runtime=previous_runtime)
            result.update(ok=False, execution_completed=False, external_effect=True)
            return result
        if not transport_contract.complete(transport, answer):
            return _unfinished(root, run, journal, claim, transport, answer, 'send-observation.json',
                               previous_runtime=previous_runtime)
        _acknowledge(root, run, journal, claim)
        result = _finish(root, run, journal, transport, previous_runtime=previous_runtime)
        result.update(external_effect=True)
        return result
    except _UploadUnanswered as unanswered:
        raise _stop_on_unknown_upload(root, run, journal, claim, target, transport, [unanswered.index],
                                      phase='reference-upload', cause=unanswered.cause) from unanswered.cause
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
                answer_name: str, *, witnesses: tuple[str, ...] = (), previous_runtime=None, **facts: Any) -> dict:
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
        result = _finish(root, run, journal, transport, answer_name=answer_name, provider_complete=False,
                         previous_runtime=previous_runtime)
    else:
        result = _status(root, run, previous_runtime=previous_runtime)
    journal.update(status=submission)
    result.update(ok=False, execution_completed=False, external_effect=True)
    return result


def _refused_upload(root: Path, run: str, journal, claim: dict, authorization: str, index: int, refusal: dict, *,
                    previous_runtime=None) -> dict:
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
    result = _cleanup_report(root, run, journal, claim, target, transport, previous_runtime=previous_runtime)
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


def _record_execution_failure(root: Path, run: str, journal, claim: dict, error: BaseException, *,
                              unknown_uploads: tuple[int, ...] | list[int] = ()) -> None:
    """Record a stopped attempt without changing facts about prior external effects.

    `unknown_uploads` names the media positions whose started upload left no
    provider answer. The record states their outcome as unknown, with the journal
    evidence of each exchange, so the execution never starts another upload or
    its send and the inputs it uploaded before may be deleted.
    """
    try:
        import production_workflow as workflow
        _, prepared, _, rows = workflow.read_run(root, run)
        # The failing process owns the attempt and is stopping now.
        outcome, effects = submission_state(rows, prepared, run, sender_alive=False)
        diagnostic = getattr(error, 'diagnostic', None)
        data = {'claim': claim['sha256'],
            'submission': outcome, 'effects': effects, 'error_type': type(error).__name__,
            'code': diagnostic.code if diagnostic is not None else 'EXECUTION_STOPPED',
            'recovery': 'Inspect saved evidence; resume does not blindly resend.'}
        if unknown_uploads:
            data['unknown_uploads'] = [f'upload:{index}' for index in unknown_uploads]
            evidence = _evidence(root, run, journal, [_unanswered_upload_name(index) for index in unknown_uploads])
            if evidence:
                data['evidence'] = evidence
        _append(root, run, 'execution-outcome', data)
    except (ValueError, OSError):
        # The original failure must survive a simultaneous record-storage failure.
        # A diagnostic log never substitutes for the missing formal event.
        if current():
            current().event('formal_record_unavailable', run=run, phase='execution-recovery')


def _finish(root: Path, run: str, journal, transport: Any, *, answer_name: str = 'answer.json',
            provider_complete: bool = True, previous_runtime=None) -> dict:
    """Acquire the recorded run once for result capture and its sealed target."""
    import production_workflow as workflow
    import runtime_snapshot
    loaded = workflow.read_run(root, run)
    descriptor = loaded.prepared['runtime_snapshot']
    fixed = runtime_snapshot.acquire_runtime(runtime_snapshot.path(root, descriptor), descriptor,
                                             previous=previous_runtime)
    return _finish_captured(root, run, journal, transport, loaded=loaded,
                            answer_name=answer_name, provider_complete=provider_complete, previous_runtime=fixed)


def _finish_captured(root: Path, run: str, journal, transport: Any, *, loaded,
                     answer_name: str = 'answer.json', provider_complete: bool = True, previous_runtime=None) -> dict:
    """Commit every acquired candidate and accounting before updating Studio."""
    import dispatch
    import production_workflow as workflow
    import studio
    rows = loaded.rows
    target = loaded.artifacts['execution-target.json']
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
    # The run's copy of each journal file an event recorded, which a refused receipt names as its repair.
    base = journal.path.absolute().relative_to(Path(root).absolute()).as_posix() + '/'
    kept = {item['path'][len(base):]: loaded.directory / 'objects' / item['sha256']
            for row in rows for item in row['data'].get('evidence', []) if item['path'].startswith(base)}
    with stage('result-capture'):
        acquisition = dispatch.acquire(journal, transport, answer_name=answer_name, captured=captured, kept=kept)
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
                result_packages[index]=dispatch.upscale_result_package(journal,index,path,loaded=loaded)
            except (ValueError,OSError,KeyError,TypeError) as exc:
                invalid_upscale.add(index)
                capture_diagnostics.append(from_exception(exc,phase='result-capture',code='UPSCALE_OUTPUT_CONTRACT_MISMATCH'))
    with stage('candidate-registration'), store.transaction(root):
        result = workflow.record_dispatch_results(root, run, package, journal.path,
            [path for _, path, _ in acquisition['acquired']], journal.document['expected'],
            indices=[index for index, _, _ in acquisition['acquired']], returned_count=acquisition['entries'],
            upscale_packages=result_packages if journal.document['operation']=='upscale' else None,
            invalid_output_indices=invalid_upscale, answer_name=answer_name, provider_complete=provider_complete)
        directory, prepared, _, rows = workflow.read_run(root, run)
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
            projected = acquisition['acquired'] if prepared['task'].get('recording') is not None else []
            captured_rows = workflow.read_run(root, run).rows
            for index, path, response in projected:
                if index in invalid_upscale:
                    continue
                exact = [item for item in captured_rows if item['event'] == 'candidate' and item['data'].get('output_index') == index]
                if len(exact) != 1:
                    raise ValueError('the captured output index has no unique Production candidate')
                found = dispatch.recorded_iteration(root, journal.document['character'], {'run': run, 'candidate': exact[0]['sha256']},
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
                    sheet_artifacts.from_iteration(root, journal.document['character'], row, run_view=loaded)
                if found not in recorded:
                    recorded.append(found)
            journal.update(status='capture-invalid' if invalid_upscale else ('complete' if result['data']['complete'] else 'capture-incomplete'), iterations=recorded)
        except (ValueError, OSError, KeyError) as exc:
            warnings.append(from_exception(exc, phase='studio-projection', code='STUDIO_PROJECTION_FAILED'))
            # The candidates are registered; only their Studio projection is missing.
            journal.update(status='projection-missing')
    images_complete = provider_complete and result['data']['complete'] and not warnings
    if provider_complete and not acquisition['failed']:
        compiled(root, run, loaded=loaded)
        report = _cleanup_report(root, run, journal, claim, target, transport, previous_runtime=previous_runtime)
        warnings.extend(report.get('warnings', []))
    else:
        report = _status(root, run, previous_runtime=previous_runtime)
    report['warnings'] = warnings
    item = report['runs'][0]
    cleanup = item.get('cleanup', {}).get('state')
    report['execution_completed'] = (item['integrity'] == 'intact' and images_complete
        and cleanup in {'not-needed', 'complete', 'failed', 'unsupported'})
    report['ok'] = report['ok'] and report['execution_completed']
    return report


def _cleanup_report(root: Path, run: str, journal, claim: dict, target: dict, transport: Any, *,
                    previous_runtime=None) -> dict:
    """Complete only owned-input cleanup, keeping captured images immediately usable."""
    import production_cleanup
    cleanup = production_cleanup.perform(root, run, journal, claim, target, transport)
    report = _status(root, run, previous_runtime=previous_runtime)
    item = report['runs'][0]
    report['warnings'] = cleanup['warnings']
    report['external_effect'] = cleanup['external_effect']
    report['execution_completed'] = (item['integrity'] == 'intact'
        and item['capture'] == 'complete' and item['registration'] == 'registered'
        and item['cleanup']['state'] in {'not-needed', 'complete', 'failed', 'unsupported'} and not item['capture_diagnostics'])
    report['ok'] = report['ok'] and report['execution_completed']
    return report


def _lookup_receipt_name(journal) -> str:
    number = 1
    while any((journal.path / name).exists() for name in
              (f'lookup-{number:03d}.json', f'lookup-{number:03d}-answer.json')):
        number += 1
    return f'lookup-{number:03d}.json'


def _lookup_observation(transport: Any, found: dict) -> dict:
    """What one lookup observed: the reading of the answer it found, or the outcome and reason of none."""
    import transport_contract
    if found['outcome'] == 'found':
        return {'outcome': 'found', 'answer': transport_contract.reading(transport, found['answer'])}
    return {'outcome': found['outcome'], 'reason': found['reason']}


def _recorded_observation(root: Path, run: str, journal, claim: dict, transport: Any) -> dict | None:
    """The latest observation of the started send that an event of the run records, as _lookup_observation gives it.

    That is the reading of the provider answer the send or a lookup saved, as the
    run keeps its bytes, or the outcome and reason of a lookup that received no
    answer. It is None while the latest record is a send that ended without an
    answer, and while nothing is recorded.
    """
    import transport_contract
    import production_workflow as workflow
    base = journal.path.absolute().relative_to(Path(root).absolute()).as_posix() + '/'
    for row in reversed(store.event_rows(root, run)):
        data = row['data']
        if row['event'] != 'execution-outcome' or data.get('claim') != claim['sha256']:
            continue
        if data.get('lookup') in {'no-answer', 'unavailable'}:
            return {'outcome': data['lookup'], 'reason': data['reason']}
        kept = {item['path'][len(base):]: item['sha256'] for item in data.get('evidence', [])
                if item['path'].startswith(base)}
        answer = next((sha for name, sha in kept.items() if name == 'send-observation.json'
                       or (name.startswith('lookup-') and name.endswith('-answer.json'))), None)
        if answer is not None:
            saved = c.decode(c.object_read(workflow.run_dir(root, run), answer))
            return {'outcome': 'found', 'answer': transport_contract.reading(transport, saved)}
        if 'indeterminate.json' in kept:
            return None
    return None


def _reconcile(root: Path, run: str, journal, claim: dict, target: dict, transport: Any, *,
               found: dict | None = None) -> dict:
    """Ask the provider once for the answer of the started send, and record what it said when that is new.

    A lookup that observes what the run already records for the send, the same
    reading of an answer or no answer again for the same reason, records nothing.
    `found` is what a lookup of resume --watch already received, as
    transport_contract.lookup_once gives it; it is recorded instead of asking again.
    """
    import transport_contract
    import dispatch
    request = c.load(journal.path / 'request.json')
    if found is None:
        selected = claim_authentication(claim, transport, target['offering']['service'])
        credential = _credential(root, transport, target['offering']['service'], expected=selected)
        key = credential.value if credential is not None else ''
        with stage('provider-lookup'):
            found = transport_contract.lookup_once(transport, request, target['service'], key)
    if _lookup_observation(transport, found) == _recorded_observation(root, run, journal, claim, transport):
        result = status(root, run)
        result.update(ok=False, execution_completed=False, external_effect=False)
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
    _, prepared, _, rows = workflow.read_run(root, run)
    claim = workflow.find(rows, 'dispatch-claim')
    return {'run': run, 'claim': claim['sha256'], 'outcome': 'not_executed', 'actor': '', 'reason': '',
            'evidence': {'path': '', 'sha256': '', 'locator': ''}}


def _statement_not_applicable(root: Path, run: str, message: str, why: str) -> ProductionError:
    """Refuse an outcome statement for a run without a started send, naming the run's own continuation.

    A statement records that the provider holds no task for a started send, so
    a run without one has nothing to state. Its repair is the next action that
    status gives the run in its current state.
    """
    from cli_invocation import shown
    action = _status(root, run)['runs'][0]['next_action']
    following = (' Nothing is left to do for this run.' if action is None else
                 ' Its next action, as status --run gives it: ' + action['reason'] + ' Run: ' + shown(action['argv']))
    return ProductionError('OUTCOME_STATEMENT_NOT_APPLICABLE', message, phase='resume', run=run, next_action=action,
                           required_action=why + ' It continues without an outcome statement.' + following)


def _record_not_executed(root: Path, run: str, journal, claim: dict, execution_state: dict, outcome_file: str) -> dict:
    """Record the author's evidenced statement that the provider never executed the started send."""
    import production_workflow as workflow
    send = next((item for item in execution_state['steps'] if item['operation'] == 'send'), None)
    if send is None:
        raise _statement_not_applicable(root, run, 'No send started for this execution.',
                                        'No send started, so the provider holds no task of this execution to state.')
    if (journal.path / 'answer.json').is_file() or any(
            row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
            and row['data'].get('submission') == 'pending' for row in store.event_rows(root, run)):
        raise ProductionError('OUTCOME_STATEMENT_CONFLICT', 'The provider answer for this send is saved.', phase='resume', run=run,
                              required_action='Run resume without --outcome-file to register the saved answer.')
    raw = store.stable_bytes(root, outcome_file)
    statement = c.decode(raw)
    c.exact(statement, OUTCOME_STATEMENT_FIELDS, 'outcome statement')
    c.text(statement['actor'], 'statement actor'); c.text(statement['reason'], 'statement reason')
    c.exact(statement['evidence'], {'path', 'sha256', 'locator'}, 'statement evidence')
    c.sha(statement['evidence']['sha256']); c.text(statement['evidence']['path'], 'evidence path')
    c.text(statement['evidence']['locator'], 'evidence locator')
    compare_exact({'run': run, 'claim': claim['sha256'], 'outcome': 'not_executed'},
                  {key: statement[key] for key in ('run', 'claim', 'outcome')}, pointer='$', phase='resume')
    if statement['actor'] not in execution_state['outcome_actors']:
        raise ProductionError('AUTHORIZATION_MISMATCH', 'This actor cannot state the outcome of this execution.', phase='resume',
                              run=run, expected=execution_state['outcome_actors'], actual=statement['actor'],
                              required_action='Have one of the outcome actors listed in expected make the statement and '
                                              'name that actor in the outcome file.')
    if c.digest(store.stable_bytes(root, statement['evidence']['path'])) != statement['evidence']['sha256']:
        raise ProductionError('SOURCE_CHANGED', 'The statement evidence differs from its declared digest.', phase='resume',
                              file=statement['evidence']['path'], expected=statement['evidence']['sha256'],
                              required_action='Set evidence.sha256 in the outcome file to the SHA-256 of the evidence '
                                              'file it names, or restore that file, then resume with --outcome-file.')
    directory = workflow.run_dir(root, run)
    files = [workflow.file_record(root, directory, outcome_file),
             workflow.file_record(root, directory, statement['evidence']['path'])]
    if files[0]['sha256'] != c.digest(raw) or files[1]['sha256'] != statement['evidence']['sha256']:
        raise ProductionError('SOURCE_CHANGED', 'The statement or its evidence changed while it was read.', phase='resume',
                              required_action='Leave the outcome file and its evidence file unchanged while resume reads '
                                              'them, then run resume --outcome-file again.')
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
    return _resume(root, run, outcome_file=outcome_file)


def _resume(root: Path, run: str, *, outcome_file: str | None = None, found: dict | None = None) -> dict:
    """resume, where `found` is a lookup answer resume --watch received for the started send."""
    import dispatch
    import production_workflow as workflow
    import transport_contract
    initial = workflow.read_run(root, run)
    mode = initial[1]['task']['execution']
    if mode != 'dispatcher':
        if outcome_file is not None:
            raise _statement_not_applicable(root, run, 'Only a dispatcher execution has a send to state.',
                                            f'This {mode} run has no dispatcher send whose absence a statement records.')
        return _status(root, run, loaded=initial)
    data = compiled(root, run, loaded=initial)
    _, prepared, _, rows, _, _, plan, target, transport = data
    claims = [row for row in rows if row['event'] == 'dispatch-claim']
    if not claims:
        if outcome_file is not None:
            raise _statement_not_applicable(root, run, 'This run has no claimed execution.',
                                            'Nothing was sent for this run, so there is no provider task to state.')
        return _status(root, run, loaded=initial)
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
                                  phase='resume', run=run, file=str(observation), expected=sorted(recorded),
                                  required_action='Copy ' + str(workflow.run_dir(root, run) / 'objects' / sorted(recorded)[0])
                                                  + ' to this file; do not resend the request.')
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
        return _reconcile(root, run, journal, claim, target, transport, found=found)
    # Only completed, durably saved uploads may be reused before the first send.
    # A started upload without a saved answer stays unknown and is never reissued.
    blocker = _upload_blocker(root, claims, rows, execution_state)
    if blocker is not None:
        if blocker[0] == 'running':
            raise ProductionError('DISPATCH_ALREADY_CLAIMED', 'The operation that started this upload is still running.',
                                  phase='resume', run=run, steps=[f'upload:{index}' for index in blocker[1]],
                                  required_action='Wait for that operation to end, then follow the next action of '
                                                  'status --run; the upload is not started again.')
        # The operation that started the upload has ended. Record its unknown outcome
        # where that operation could not, and delete the inputs uploaded before it.
        raise _stop_on_unknown_upload(root, run, journal, claim, target, transport, blocker[1], phase='resume')
    # No send has begun: revalidate current conditions before any new effect.
    # Failures here are still attempts to resume this exact claim, so retain the
    # same formal outcome record as failures during transmission.
    try:
        boundary = workflow.read_current(root, run)
        loaded = boundary.view
        data = compiled(root, run, loaded=loaded)
        authority = workflow.current_authority(root, loaded.prepared)
        receipts(root, loaded.prepared, loaded.rows, plan, authority=authority, loaded=loaded)
        require_recording(root, prepared)
        credential = _credential(root, transport, target['offering']['service'], expected=selected)
    except BaseException as exc:
        _record_execution_failure(root, run, journal, claim, exc)
        raise
    return _transmit(root, run, journal, c.load(journal.path / 'request-contract.json'), claim,
                     claim['data']['authorizations'][0], target, transport,
                     credential.value if credential is not None else '', previous_runtime=boundary.runtime)


def _pending(report: dict, run: str) -> bool:
    """Whether the report shows the run's provider task accepted with outputs still unfinished."""
    return any(item.get('run') == run and item.get('submission') == 'pending' for item in report['runs'])


@dataclasses.dataclass(frozen=True)
class PollSchedule:
    """When resume --watch asks the provider again for a pending task.

    The first lookup comes no sooner than `first_delay` seconds after the
    provider accepted the task. The wait after it is `interval` seconds, and
    each later wait is the one before times `factor`, never longer than
    `maximum`. A factor of 1 waits the same interval every time.
    """
    first_delay: float
    interval: float
    factor: float
    maximum: float

    def waits(self):
        """The waits between lookups, in order."""
        wait = self.interval
        while True:
            yield wait
            wait = min(wait * self.factor, self.maximum)

    def describe(self) -> str:
        first = (f'first {self.first_delay:g} seconds after the provider accepted it, then ' if self.first_delay
                 else '')
        if self.factor == 1:
            return first + f'every {self.interval:g} seconds'
        return (first + f'after {self.interval:g} seconds, each later wait {self.factor:g} times the one before, '
                f'up to {self.maximum:g} seconds')


POLL_FIELDS = ('poll_first_delay_seconds', 'poll_interval_seconds', 'poll_backoff_factor', 'poll_max_interval_seconds')


def poll_schedule(target: dict, artifact: str) -> PollSchedule | None:
    """The lookup schedule that the sealed service record declares for this kind of output, or None.

    The service record's `delivery` holds one entry per kind of output, the
    task's `artifact`, and its poll fields come from the service's own polling
    guidance. An entry without `poll_interval_seconds` declares no schedule.
    """
    service = target['offering']['service']
    entry = (target['service'].get('delivery') or {}).get(artifact) or {}
    values = {name: entry.get(name) for name in POLL_FIELDS}
    if values['poll_interval_seconds'] is None:
        return None

    def number(name: str, default: float, *, least: float, inclusive: bool) -> float:
        value = values[name]
        if value is None:
            return default
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or value < least or (not inclusive and value == least)):
            raise ProductionError('INPUT_CONSISTENCY_ERROR',
                f'delivery.{artifact}.{name} of the service record {service!r} sealed in this run is not a valid '
                'number of seconds or factor.', phase='resume', pointer=f'$.delivery.{artifact}.{name}',
                actual=value, required_action=f'Run resume --watch with --interval SECONDS for this run. Correct '
                f'delivery.{artifact}.{name} in the service record {service!r} for runs prepared later, as '
                'schemas/service-profile.schema.json describes.')
        return float(value)
    interval = number('poll_interval_seconds', 0, least=0, inclusive=False)
    factor = number('poll_backoff_factor', 1, least=1, inclusive=True)
    maximum = number('poll_max_interval_seconds', interval, least=interval, inclusive=True)
    if factor > 1 and values['poll_max_interval_seconds'] is None:
        raise ProductionError('INPUT_CONSISTENCY_ERROR',
            f'delivery.{artifact}.poll_backoff_factor of the service record {service!r} sealed in this run grows the '
            'wait without poll_max_interval_seconds.', phase='resume', pointer=f'$.delivery.{artifact}',
            required_action=f'Run resume --watch with --interval SECONDS for this run. Add '
                            f'delivery.{artifact}.poll_max_interval_seconds to the service record {service!r} for '
                            'runs prepared later.')
    return PollSchedule(number('poll_first_delay_seconds', 0, least=0, inclusive=True), interval, factor, maximum)


def _accepted_at(rows: list[dict], claim: dict) -> datetime.datetime | None:
    """When the run first recorded the provider's acceptance of the claim's send as pending."""
    for row in rows:
        if (row['event'] == 'execution-outcome' and row['data'].get('claim') == claim['sha256']
                and row['data'].get('submission') == 'pending'):
            return datetime.datetime.fromisoformat(row['created_at'])
    return None


def _seconds_since(moment: datetime.datetime) -> float:
    return (datetime.datetime.now(datetime.timezone.utc) - moment).total_seconds()


class _WatchLookup:
    """One lookup of the started send per call, without reading or checking the run again.

    It is built from a run that resume has just read and checked. A lookup has
    no effect at the provider; whatever it finds is recorded only by a resume,
    which reads and checks the run again.
    """

    def __init__(self, root: Path, run: str) -> None:
        import dispatch
        import production_workflow as workflow
        loaded = workflow.read_run(root, run)
        _, prepared, _, rows, _, _, _, target, transport = compiled(root, run, loaded=loaded)
        self.claim = [row for row in rows if row['event'] == 'dispatch-claim'][-1]
        self.journal = dispatch.RunJournal.open(c.local(root, self.claim['data']['journal']))
        self.request = c.load(self.journal.path / 'request.json')
        self.root, self.run, self.target, self.transport = root, run, target, transport
        self.artifact = prepared['task']['artifact']
        selected = claim_authentication(self.claim, transport, target['offering']['service'])
        credential = _credential(root, transport, target['offering']['service'], expected=selected)
        self.key = credential.value if credential is not None else ''

    def ask(self) -> dict:
        import transport_contract
        with stage('provider-lookup'):
            return transport_contract.lookup_once(self.transport, self.request, self.target['service'], self.key)

    def is_new(self, found: dict) -> bool:
        """Whether resume would record this lookup: it differs from the latest observation the run records."""
        return (_lookup_observation(self.transport, found)
                != _recorded_observation(self.root, self.run, self.journal, self.claim, self.transport))


def watch(root: Path, run: str, *, interval: float | None = None,
          limit: float = WATCH_LIMIT_SECONDS) -> dict:
    """Resume the run, then ask for its provider task again while that task is pending.

    The first pass is one resume. While the task stays pending, each later pass
    is one lookup through the transport, with no reading of the run: a lookup
    that reports what the run already records is dropped, and a lookup that
    reports something new goes to a resume in a read boundary of its own, which
    records that answer and registers the outputs that finished. The watch never
    sends or uploads again. `interval` fixes every wait; without it the run's
    sealed service record declares the schedule for its kind of output, its
    first delay after the provider's acceptance and its growing waits, as
    PollSchedule describes.

    The watch returns once the run is no longer pending, or when the next lookup
    would start more than `limit` seconds after the watch began. The run is then
    exactly as a plain resume leaves it, and the result is what that resume
    returns. A KeyboardInterrupt ends the watch where it arrives, and what the
    passes before it registered stays registered.
    """
    import runtime_snapshot
    for option, value in (('--interval', interval), ('--limit', limit)):
        if value is None and option == '--interval':
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            default = ('the interval the service record declares' if option == '--interval'
                       else f'{WATCH_LIMIT_SECONDS}')
            raise ProductionError('INPUT_ARGUMENT_INVALID', f'{option} of resume --watch is not a positive number of seconds.',
                                  phase='resume', run=run,
                                  required_action=f'Give {option} a positive number of seconds, or leave it out for {default}.')
    import production_workflow as workflow
    root = c._root(root)
    deadline = time.monotonic() + limit

    def as_resume_leaves_it() -> dict:
        # Nothing new was recorded since the last pass, as a plain resume would find the run.
        with runtime_snapshot.public_call(fresh=True):
            report = _status(root, run)
        report.update(ok=False, execution_completed=False, external_effect=False)
        return report

    with runtime_snapshot.public_call(fresh=True):
        schedule, delay = _watch_start(workflow.read_run(root, run), run, interval)
    if delay > 0:
        # The service record asks for this time between the provider's acceptance and the first lookup.
        wait = min(delay, max(deadline - time.monotonic(), 0.0))
        with stage('provider-watch', seconds=wait):
            time.sleep(wait)
        if wait < delay:
            return as_resume_leaves_it()
    with runtime_snapshot.public_call(fresh=True):
        result = _resume(root, run)
        if not _pending(result, run):
            return result
        asking = _WatchLookup(root, run)
    if schedule is None:
        service = asking.target['offering']['service']
        raise ProductionError('INPUT_ARGUMENT_INVALID',
            f'The service record {service!r} sealed in this run declares no poll interval for {asking.artifact} '
            'output, so resume --watch has no time to wait between lookups.', phase='resume', run=run,
            required_action=f'Run resume --watch again with --interval SECONDS for this run. The first pass already '
                            f'registered what had finished. Runs prepared after delivery.{asking.artifact}.'
                            f'poll_interval_seconds is added to the service record {service!r}, from the service\'s own '
                            f'polling guidance, wait that schedule; python scripts/service_profile.py {service} prints the record.')
    waits = schedule.waits()
    wait = next(waits)
    unchanged = False
    while time.monotonic() + wait <= deadline:
        with stage('provider-watch', seconds=wait):
            time.sleep(wait)
        found = asking.ask()
        if asking.is_new(found):
            with runtime_snapshot.public_call(fresh=True):
                result = _resume(root, run, found=found)
            unchanged = False
            if not _pending(result, run):
                return result
        else:
            unchanged = True
        wait = next(waits)
    return as_resume_leaves_it() if unchanged else result


def _watch_start(loaded, run: str, interval: float | None) -> tuple[PollSchedule | None, float]:
    """The schedule of a watch and the seconds it waits before its first pass.

    `--interval` fixes every wait and asks at once. Otherwise the run's sealed
    service record declares the schedule, and a pending task that the provider
    accepted less than its first delay ago is asked only when that delay ends.
    """
    if interval is not None:
        return PollSchedule(0.0, float(interval), 1.0, float(interval)), 0.0
    prepared, rows = loaded.prepared, loaded.rows
    if prepared['task']['execution'] != 'dispatcher' or 'execution-target.json' not in loaded.artifacts:
        return None, 0.0
    schedule = poll_schedule(loaded.artifacts['execution-target.json'], prepared['task']['artifact'])
    claims = [row for row in rows if row['event'] == 'dispatch-claim']
    if schedule is None or not schedule.first_delay or not claims:
        return schedule, 0.0
    if submission_state(rows, prepared, run)[0] != 'pending':
        return schedule, 0.0
    accepted = _accepted_at(rows, claims[-1])
    if accepted is None:
        return schedule, 0.0
    return schedule, max(0.0, schedule.first_delay - _seconds_since(accepted))


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


def _logs_by_run(root: Path) -> dict[str, list[str]]:
    from operation_context import operations_by_run
    return operations_by_run(root)


def _argv(command: str, root: Path, *arguments: str) -> list[str]:
    from cli_invocation import python_argv
    return python_argv(SCRIPT, command, '--root', str(root), *arguments)


def _action(command: str, root: Path, arguments: list[str], reason: str) -> dict:
    return {'command': command, 'argv': _argv(command, root, *arguments), 'reason': reason}


def decision_context(prepared: dict, *, candidate: str | None = None, basis: object = None,
                     grant: str | None = None, scope: str | None = None) -> dict:
    """The producer's immutable decision basis, separate from editable answers."""
    return {'input_sha256': prepared['input_sha256'], 'candidate': candidate, 'basis': basis,
            'grant': grant, 'scope': scope}


def _choose_drafts(root: Path, run: str, kind: str, actions: list[dict]) -> dict:
    if len(actions) == 1:
        return actions[0]
    return {**_action('status', root, ['--run', run],
        f'Several saved {kind} drafts are available. Inspect them and explicitly choose the intended file; '
        'no draft was selected or overwritten.'), 'requires_author_input': True, 'alternatives': actions}


def _draft_action(root: Path, run: str, kind: str, *, candidate: str | None = None,
                  basis: object = None, grant: str | None = None, scope: str | None = None,
                  prepared: dict | None = None, existing_only: bool = False, guidance: str = '') -> dict | None:
    """Continue producer-owned files for this exact target and decision basis.

    `guidance` follows the reason of each returned action: what the file states
    and the evidence that settles it.
    """
    import production_authoring_state
    if prepared is None:
        import production_workflow
        prepared = production_workflow.read_run(root, run).prepared
    context = decision_context(prepared, candidate=candidate, basis=basis, grant=grant, scope=scope)
    filename_basis = 'provider-no-answer' if kind == 'outcome' else basis
    identity = c.content_id({'run': run, 'candidate': candidate, 'basis': filename_basis,
                             'grant': grant, 'scope': scope})[:24]
    relative = f'production/decisions/{run}/{kind}/{identity}.json'
    path = c.local(root, relative, exists=False)
    drafts = {item['path']: item for item in production_authoring_state.decision_drafts(
        root, prepared['task']['task_id'], kind=kind, run=run, context=context)}
    if path.exists():
        drafts.setdefault(relative, {'path': relative, 'available': True})
    apply_name, option = {'review':('review','--file'), 'selection':('select','--file'),
                          'acceptance':('accept','--file'),
                          'execution':('execute','--decisions-file'), 'outcome':('resume','--outcome-file')}[kind]
    if kind == 'review' and prepared['task']['execution'] == 'authored':
        apply_name = 'review-authored'
    expected = {'run': run}
    if kind in {'review', 'selection', 'acceptance'}:
        expected = {'input_sha256': prepared['input_sha256'], 'candidate': candidate}
        if kind == 'review' and candidate is None:
            expected['candidate'] = prepared['authored_revision']['artifact']['sha256']
        if kind == 'selection':
            expected.update(review=basis['review'], replaces=basis['replaces'])
        elif kind == 'acceptance':
            expected.update(run=run, review=basis['review'], scope=scope, grant=grant,
                            authority_sha256=basis.get('authority'))
            if scope == 'studio-slot':
                expected['expected_slot'] = basis['expected_slot']
                expected['expected_placement'] = basis['expected_placement']
    elif kind == 'outcome':
        expected['claim'] = basis['claim']
    review_guidance = (' Review only the commissioned criteria; measured output can establish technical requirements. '
        'The evidence medium adds no artistic-quality requirement. Record supported findings and limits, then continue '
        'to the next status action.') if kind == 'review' else ''
    review_guidance += (' ' + guidance) if guidance else ''
    required = {'review': {'reviewer', 'checks'}, 'selection': {'selector', 'authorization'},
                'acceptance': {'stop_assessments'}, 'outcome': {'outcome'}, 'execution': {'decisions'}}[kind]
    for item in drafts.values():
        if item['available']:
            item['ownership'] = production_authoring_state.decision_file_state(root, item['path'], expected,
                                                                               required=required)
    other_targets = [name for name, item in drafts.items() if item.get('ownership') == 'other-target']
    drafts = {name: item for name, item in drafts.items() if item.get('ownership') != 'other-target'}
    present = [item for item in drafts.values() if item['available']]
    if present:
        actions = []
        for item in present:
            if item['ownership'] == 'unfinished':
                action = _action('status', root, ['--run', run],
                    f"The saved {kind} draft at {item['path']} is incomplete or unreadable. "
                    'Inspect and finish that file, including its original ownership fields, then check status again. '
                    'Its contents do not change the saved candidate or the workspace to inspect.' + review_guidance)
            else:
                action = _action(apply_name, root, ['--run', run, option, item['path']],
                    f"Existing {kind} draft: {item['path']}. Inspect and complete it from actual evidence, then apply it. "
                    'The draft is not itself approval; do not recreate or overwrite it.' + review_guidance)
            actions.append({**action, 'draft': item['path'], 'requires_author_input': True})
        return _choose_drafts(root, run, kind, actions)
    if existing_only and not drafts:
        return None
    arguments = ['--run', run]
    if candidate is not None: arguments += ['--candidate', candidate]
    if grant is not None: arguments += ['--grant', grant]
    if scope is not None: arguments += ['--scope', scope]
    if not drafts and path.exists():
        number = 2
        while c.local(root, relative, exists=False).exists():
            relative = f'production/decisions/{run}/{kind}/{identity}-{number}.json'
            number += 1
    destinations = list(drafts) or [relative]
    ownership_guidance = (' Existing files belong to another decision target and are retained: '
                          + ', '.join(other_targets) + '. Continue this run in the new path shown here.') if other_targets else ''
    def created(destination: str) -> str:
        if kind == 'outcome':
            return f'Write the outcome statement of this run to {destination}.'
        return (f'Create the {kind} draft for this exact run and candidate in {destination}. '
                'Fill it from actual review or authority evidence; then use the next status action.')
    actions = [{**_action('draft-' + kind, root, arguments + ['--out', destination],
        created(destination) + ownership_guidance + review_guidance),
        'draft': destination} for destination in destinations]
    return _choose_drafts(root, run, kind, actions)


def _acceptance_action(root: Path, run: str, candidate: dict, prepared: dict,
                       rows: list[dict], authority: store.CurrentAuthority | None, scope: str) -> dict:
    """Keep destination-specific checks within the explicitly named use."""
    import production_permissions
    import production_acceptance
    expected_slot = None
    expected_placement = None
    if scope == 'studio-slot':
        try:
            target, iteration = production_acceptance._target(root, run, candidate['candidate'],
                                                     loaded=(None, prepared, None, rows))
            expected_placement = iteration['placement']['sha256']
            expected_slot = production_acceptance.slot_state(root, target['character'], target['slot'])
        except INSPECTION_ERRORS as exc:
            diagnostic = from_exception(exc, phase='acceptance')
            command = 'resume' if diagnostic['code'] == 'STUDIO_CANDIDATE_REQUIRED' else 'status'
            return _action(command, root, ['--run', run],
                'For Studio slot acceptance: ' + diagnostic['message'] + ' ' + diagnostic['required_action'])
    document = authority.document if authority is not None else {'grants': []}
    grants = [item['grant'] for item in production_permissions.target_coverage(document, 'select', ['delivery'])
              if not item['missing']]
    saved = []
    for grant in grants:
        basis = {'review': candidate['review'], 'expected_slot': expected_slot, 'expected_placement': expected_placement,
                 'authority': production_acceptance.authority_basis(authority, grant)}
        action = _draft_action(root, run, 'acceptance', candidate=candidate['candidate'], grant=grant,
            scope=scope, basis=basis, prepared=prepared, existing_only=True)
        if action is not None:
            saved.extend(action['alternatives'] if action['command'] == 'status' and action.get('alternatives')
                         else [action])
    if saved:
        action = _choose_drafts(root, run, 'acceptance', saved)
    else:
        grant = grants[0] if len(grants) == 1 else None
        basis = {'review': candidate['review'], 'expected_slot': expected_slot, 'expected_placement': expected_placement}
        if grant is not None:
            basis['authority'] = production_acceptance.authority_basis(authority, grant)
        action = _draft_action(root, run, 'acceptance', candidate=candidate['candidate'], grant=grant,
                               scope=scope, basis=basis, prepared=prepared)
    action['reason'] = ('Use this action for ' + ('delivery only' if scope == 'delivery-only' else 'explicit Studio slot acceptance')
                        + '. ' + action['reason'])
    return action


def _candidate_action(root: Path, run: str, candidate: dict, prepared: dict,
                      rows: list[dict], authority: store.CurrentAuthority | None) -> dict:
    """Expose the current judgment for one candidate without ranking alternatives."""
    if candidate['review'] is None or candidate['selection_requirements']['unassessed_hard_criteria']:
        actions = [_draft_action(root, run, 'review', candidate=candidate['candidate'],
                                 basis=candidate['review'], prepared=prepared)]
        phases = ['observe', 'review']
    else:
        scopes = ['delivery-only', 'studio-slot'] if prepared['task'].get('recording') else ['delivery-only']
        previous = [row['data']['selection']['scope'] for row in rows if row['event'] == 'selection'
                    and row['data']['selection']['candidate'] == candidate['candidate']]
        if previous and previous[-1] in scopes:
            scopes.remove(previous[-1])
            scopes.insert(0, previous[-1])
        actions = [_acceptance_action(root, run, candidate, prepared, rows, authority, scope) for scope in scopes]
        import production_workflow
        selection = _draft_action(root, run, 'selection', candidate=candidate['candidate'],
            basis={'review': candidate['review'], 'replaces': production_workflow.replaced_selection(rows)},
            prepared=prepared, existing_only=True)
        if selection is not None:
            actions.insert(0, selection)
        phases = ['review']
    contexts = [_action('workspace', root,
        ['--run', run, '--phase', phase, '--candidate', candidate['candidate']],
        'Read the candidate and its commissioned criteria when needed; retain knowledge already in this context.')
        for phase in phases]
    def attach_context(action):
        action['read_context'] = contexts
        for alternative in action.get('alternatives', []):
            attach_context(alternative)
    for action in actions:
        attach_context(action)
    saved = []
    for action in actions:
        if action['command'] in {'review', 'select', 'accept'}:
            saved.append(action)
        elif action['command'] == 'status':
            if action.get('alternatives'):
                saved.extend(action['alternatives'])
            elif action.get('draft'):
                saved.append(action)
    if len(saved) > 1:
        action = _choose_drafts(root, run, 'decision', saved)
        action['read_context'] = contexts
    else:
        action = saved[0] if saved else actions[0]
        others = [item for item in actions if item is not action]
        if others:
            action['alternatives'] = action.get('alternatives', []) + others
    return action


def _execution_draft_paths(root: Path, prepared: dict) -> list[dict]:
    """Discover registered custom files and the ordinary run-owned draft folder."""
    import production_authoring_state
    result = {item['path']: item for item in production_authoring_state.decision_drafts(
        root, prepared['task']['task_id'], kind='execution', run=prepared['run'])}
    folder = c.local(root, 'production/decisions/' + prepared['run'] + '/execution', exists=False)
    for path in sorted(folder.glob('*.json')):
        relative = path.relative_to(root).as_posix()
        result.setdefault(relative, {'run': prepared['run'], 'path': relative, 'available': True})
    for item in result.values():
        if item['available']:
            item['ownership'] = production_authoring_state.decision_file_state(
                root, item['path'], {'run': prepared['run']}, required={'decisions'})
    return [item for item in result.values() if item.get('ownership') != 'other-target']


def _execution_draft_action(root: Path, prepared: dict) -> dict:
    run = prepared['run']
    drafts = _execution_draft_paths(root, prepared)
    present = [item for item in drafts if item['available']]
    if present:
        actions = []
        for item in present:
            if item['ownership'] == 'unfinished':
                action = _action('status', root, ['--run', run],
                    'The saved execution draft is incomplete or unreadable. Inspect and finish ' + item['path'] +
                    ' with its original run ownership, then check status again. Do not recreate its applicable choices.')
            else:
                action = _action('execute', root, ['--run', run, '--decisions-file', item['path']],
                    'Continue this saved execution draft. Inspect its operation requirements and update unanswered judgments '
                    'from current authority; retain applicable decisions and do not recreate the file.')
            actions.append({**action, 'draft': item['path'], 'requires_author_input': True})
        if len(actions) == 1:
            return actions[0]
        return {**_action('status', root, ['--run', run],
            'Several saved execution drafts belong to this run. Inspect them and explicitly choose the intended file; '
            'no draft was selected or overwritten.'), 'requires_author_input': True, 'alternatives': actions}
    if len(drafts) == 1:
        relative = drafts[0]['path']
        return {**_action('draft-execution', root, ['--run', run, '--out', relative],
            'The registered execution draft has not been published. Create it at this unused location and retain its task/run association.'),
            'draft': relative}
    return _draft_action(root, run, 'execution', basis=prepared['input_sha256'], prepared=prepared)


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
    if prepared['task']['execution'] != 'dispatcher' or prepared['task'].get('recording') is None:
        return 'registered'
    invalid = {index for row in rows if row['event'] == 'dispatch-results' for index in row['data'].get('invalid_output_indices', [])}
    recording = prepared['task']['recording']
    try:
        studio.validate_recording_target(root, recording['character'], recording['slot'])
    except INSPECTION_ERRORS:
        # The destination is gone. The run keeps the captured bytes as candidates; nothing shows them.
        return 'unregistered'
    try:
        shown = {(row.get('production') or {}).get('candidate'): (row.get('result') or {}).get('sha256')
                 for row in studio.read_iterations(studio.character_dir(root, recording['character']), project=False)
                 if (row.get('production') or {}).get('run') == prepared['run']}
    except INSPECTION_ERRORS:
        return 'projection-missing'
    wanted = {row['sha256']: row['data']['files'][0]['sha256'] for row in candidates if row['data'].get('output_index') not in invalid}
    return 'registered' if all(shown.get(key) == value for key, value in wanted.items()) else 'projection-missing'


def _unknown_outcome_action(root: Path, run: str, rows: list[dict]) -> dict:
    """The continuation of a started send whose outcome is unknown.

    resume records an answer the journal saved and asks the provider through the
    transport's lookup; it never sends again. Once that lookup found no answer,
    only the author's evidenced statement settles the send.
    """
    claim = next((row for row in reversed(rows) if row['event'] == 'dispatch-claim'), None)
    lookups = [row['data'].get('lookup') for row in rows if row['event'] == 'execution-outcome' and row['data'].get('lookup')]
    if claim is None or not lookups or lookups[-1] != 'no-answer':
        return _action('resume', root, ['--run', run],
            "resume asks the provider for the lost answer through the transport's lookup; it never sends again. When the "
            "provider's records hold no such task, record that with draft-outcome and resume --outcome-file.")
    return _draft_action(root, run, 'outcome', basis={'claim': claim['sha256']}, guidance=
        "resume asked the provider through the transport's lookup, and the provider gave no answer for this send. Check "
        "the provider's own records for the request in request.json of this run's journal. When they hold no such task, "
        'fill the statement with its actor, its reason and the evidence file that shows it (path, SHA-256 and locator), '
        'then run resume --outcome-file with the statement: it records the send as not_executed. When they hold the '
        'task, run resume again: it asks the provider once more and never sends again.')


def _cleanup_action(root: Path, run: str, cleanup: dict) -> dict:
    """Continue deleting this run's uploaded inputs, from their recorded upload receipts and deletion requests."""
    reason = ('Recover the original deletion requests by their recorded identifiers; their unknown outcomes never cause a new generation.'
              if cleanup['state'] == 'outcome_unknown' else
              'Delete only this run\'s retained uploaded inputs. Captured images stay saved; resume never uploads or generates them again.')
    return _action('resume', root, ['--run', run], reason)


def _next_action(root: Path, report: dict, prepared: dict, rows: list[dict], *, execution_state: dict | None,
                 authority: store.CurrentAuthority | None, transport: Any = None,
                 schedule: PollSchedule | None = None) -> dict | None:
    """The one concrete command that moves this run forward, with why.

    `transport` is the module a dispatcher run sends through; an external or
    authored run has none. `schedule` is the lookup schedule its sealed service
    record declares for its kind of output, or None.
    """
    import production_workflow as workflow
    run = report['run']
    mode = prepared['task']['execution']
    events = {row['event'] for row in rows}
    if mode == 'dispatcher' and report['submission'] == 'pending':
        if schedule is None:
            return _action('resume', root, ['--run', run],
                'The provider accepted this task and is still processing it. resume asks for it once and registers '
                'each output that finished. The service record sealed in this run declares no usable poll schedule '
                f'for its output, so resume --watch needs --interval SECONDS to keep asking, for at most '
                f'{WATCH_LIMIT_SECONDS} seconds unless --limit changes that. Neither sends again.')
        return _action('resume', root, ['--run', run, '--watch'],
            f'The provider accepted this task and is still processing it. resume --watch asks for the same task '
            f'{schedule.describe()}, as its service record declares, registers each output as it finishes and '
            f'returns when none is pending, or after {WATCH_LIMIT_SECONDS} seconds; --interval fixes every wait and '
            '--limit changes that time. It never sends again.')
    if mode == 'dispatcher' and report['submission'] == 'outcome_unknown':
        return _unknown_outcome_action(root, run, rows)
    cleanup = report['cleanup']
    if mode == 'dispatcher' and cleanup['eligible'] and cleanup['state'] in {'pending', 'outcome_unknown'}:
        return _cleanup_action(root, run, cleanup)
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
        candidates = [candidate for candidate in report['candidate_states']
                      if candidate.get('disposition') != 'not_selected']
        actions = [_candidate_action(root, run, candidate, prepared, rows, authority) for candidate in candidates]
        if len(actions) == 1:
            return actions[0]
        if actions:
            return {**_action('status', root, ['--run', run],
                'Several candidates remain available. Inspect the intended candidates and choose the next review or '
                'acceptance action; listing order is not a recommendation or selection.'),
                'requires_author_input': True, 'alternatives': actions}
        return _action('repeat', root, ['--from', run, '--prepare'],
            'Every candidate was marked not selected. Continue with an intentional new trial or author a revised '
            'draft from this run; existing candidates and decisions remain saved.')
    if report['submission'] == 'unclaimed' and 'handoff' not in events and report['readiness'] == 'blocked':
        diagnostic = report['readiness_diagnostics'][0]
        return _action('status', root, ['--run', run], diagnostic['required_action'])
    if mode == 'external' and prepared['task'].get('image_input') and 'external-claim' not in events:
        if report['readiness'] == 'authorization_required':
            return _execution_draft_action(root, prepared)
        return _action('execute', root, ['--run', run],
            'Hand the exact request to the host once under the current separate direction and submission authorizations.')
    if mode == 'dispatcher':
        submission = report['submission']
        if submission == 'unclaimed':
            if report['readiness'] == 'authorization_required':
                return _execution_draft_action(root, prepared)
            return _action('execute', root, ['--run', run], 'Every prepared operation has a current exact authorization.')
        if submission == 'claimed':
            if any(item['result'] == 'rejected' for item in report['effects']):
                return _action('repeat', root, ['--from', run, '--prepare'],
                    'The provider refused an upload. Prepare a new request and obtain its exact approval.')
            blocker = _upload_blocker(root, [row for row in rows if row['event'] == 'dispatch-claim'], rows, execution_state)
            if blocker is not None:
                if blocker[0] == 'running':
                    return _action('status', root, ['--run', run],
                        'The owner operation is still uploading; check again after it ends.')
                import production_cleanup
                unrecorded = [index for index in blocker[1]
                              if f'upload:{index}' not in execution_state['unknown_uploads']]
                if unrecorded and report['cleanup']['retained'] and production_cleanup.supported(transport):
                    inputs = ', '.join(str(index + 1) for index in unrecorded)
                    return _action('resume', root, ['--run', run],
                        f'The operation that started the upload of media input {inputs} ended without recording that '
                        'its outcome is unknown. resume records it and deletes the inputs this execution uploaded before; '
                        'it never uploads or sends again.')
                return _unknown_upload_action(root, run)
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


def _run_authentication(root: Path, prepared: dict, claims: list[dict], report: dict,
                         execution_state: dict | None, target: dict | None) -> dict | None:
    """Inspect authentication for this run's next provider step, using its recorded source."""
    import transport_contract
    if prepared['task']['execution'] != 'dispatcher':
        return None
    transport = transport_contract.load(target['service']['transport'])
    selected = claim_authentication(claims[-1], transport, target['offering']['service']) if claims else None
    required = False
    if not transport_contract.credential_free(transport):
        if not claims:
            required = report['task_disposition'] == 'open' and report['readiness'] not in {'blocked', 'unchecked'}
        elif (report['next_action'] or {}).get('command') == 'resume':
            journal = c.local(root, claims[-1]['data']['journal'])
            observations = _response_observations(journal)
            saved_answer = ((journal / 'answer.json').is_file() or bool(observations and
                transport_contract.complete(transport, c.load(observations[-1]))))
            if report['cleanup']['eligible'] and report['cleanup']['state'] in {'pending', 'outcome_unknown'}:
                required = True
            elif not saved_answer and report['submission'] in {'pending', 'outcome_unknown'}:
                required = True
            elif not saved_answer and report['submission'] == 'claimed' and report['readiness'] not in {'blocked', 'unchecked'}:
                steps = execution_state['steps'] if execution_state else []
                required = (not any(item['result'] == 'rejected' for item in report['effects'])
                    and all(step['operation'] == 'upload' and step['step'].startswith('upload:')
                            and (journal / f"upload-{int(step['step'].split(':', 1)[1]) + 1:03d}.json").is_file()
                            for step in steps))
    return authentication_readiness(root, transport, target['offering']['service'], required=required, expected=selected)


def _work_open(root: Path, task_id: str, states: dict) -> bool:
    """Whether the run's work task can still continue: active or suspended.

    An unreadable work record leaves the run comparable; its own diagnostics
    belong to the work ledger.
    """
    if task_id not in states:
        import work_ledger
        try:
            states[task_id] = c.load(work_ledger.task_path(root, task_id)).get('work_state')
        except INSPECTION_ERRORS:
            states[task_id] = None
    return states[task_id] in {None, 'active', 'suspended'}


def _run_status(root: Path, item: dict, logs: dict[str, list[str]], authorities: dict, *, loaded=None,
                previous_runtime=None, work_states: dict | None = None, selected_by_id: bool = True) -> dict:
    import production_workflow as workflow
    identifier = item['run_id']
    loaded = loaded if loaded is not None else workflow.read_run(root, identifier)
    directory, prepared, consumer, rows = loaded
    if prepared['task']['execution'] == 'authored':
        from production_authored import status as authored_status
        return authored_status(root, loaded, logs=logs.get(identifier, []))
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
    candidate_states = [workflow.candidate_state(root, identifier, key, loaded=loaded) for key in candidates]
    events = {row['event'] for row in rows}
    mode = prepared['task']['execution']
    task_disposition = 'completed' if 'completion' in events else 'abandoned' if 'abandoned' in events else 'open'
    # Current sources are compared with the prepared ones while the run can
    # still change its outcome. A completed or abandoned run is shown from its
    # retained records. An open run left by closed work is compared when it is
    # selected by its ID, not on every view of the whole Studio.
    unchecked = (task_disposition == 'open' and not selected_by_id
                 and not _work_open(root, prepared['task']['task_id'], {} if work_states is None else work_states))
    compared = task_disposition == 'open' and not unchecked
    # A freshness problem stops the next effect. A notice reports a changed
    # installation or pack, which the sealed request does not depend on.
    freshness, notices = (workflow.freshness(root, identifier, loaded=loaded, previous_runtime=previous_runtime)
                          if compared else ([], []))
    selection_ready = False
    selection_diagnostics = []
    if 'selection' in events:
        try:
            selection, chosen, _ = workflow.current_selection(prepared, rows)
            if chosen['scope'] == 'studio-slot':
                from production_acceptance import verify_slot
                verify_slot(root, identifier, selection, rows=rows, require_current='completion' not in events)
            elif chosen['scope'] == 'studio-adoption':
                if 'completion' in events:
                    workflow.verify_studio_adoption_receipt(root, identifier, selection, rows=rows)
                else:
                    selected = workflow.find(rows, 'candidate', chosen['candidate'])
                    workflow.confirm_studio_adoption(root, chosen['adoption'], selected['data']['files'][0]['sha256'], rows)
            selection_ready = True
        except ValueError as exc:
            selection_diagnostics.append(from_exception(exc, phase='selection'))
    readiness = ('unchecked' if unchecked else 'blocked' if freshness else
                 'ready' if compared else 'not-applicable')
    readiness_diagnostics = list(freshness)
    task_id = prepared['task']['task_id']
    if task_id not in authorities:
        try:
            authorities[task_id] = (store.read_authority(root, task_id, required=False), None)
        except INSPECTION_ERRORS as exc:
            authorities[task_id] = (None, from_exception(exc, phase='authority'))
    authority, authority_error = authorities[task_id]
    if authority_error is not None:
        readiness = 'blocked'
        readiness_diagnostics.append(authority_error)
    # Without a registered authority no decision file can be completed, so the repair names its import first.
    unregistered = ('' if authority is not None else 'The work task has no registered authority: import it first with '
                    'the authority-import command in authority.update_action. ')
    if not claims and mode == 'dispatcher' and readiness not in {'blocked', 'unchecked'} and task_disposition == 'open':
        plan = loaded.artifacts['execution-plan.json']
        try:
            receipts(root, prepared, rows, plan, authority=authority, loaded=loaded,
                required_action=unregistered + 'Fill the execution decision file from the actual approval or delegation, '
                                'then execute with --decisions-file.')
        except INSPECTION_ERRORS as exc:
            readiness = 'authorization_required'
            readiness_diagnostics.append(from_exception(exc, phase='readiness'))
    if (not external_claims and mode == 'external' and consumer.get('image_input')
            and readiness not in {'blocked', 'unchecked'} and task_disposition == 'open'):
        try:
            plan = loaded.artifacts['execution-plan.json']
            receipts(root, prepared, rows, plan,
                authority=authority, loaded=loaded,
                required_action=unregistered + 'Complete the separate decisions in draft-execution, then execute hands '
                                'the exact input to the host once.')
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
        'freshness_notices': notices,
        'selection_diagnostics': selection_diagnostics, 'selection_ready': selection_ready, 'settlement_open': settlement_open,
        'execution': None if execution_state is None else {'execution_id': execution_state['execution_id'], 'status': execution_state['status']},
        'journal': claims[-1]['data']['journal'] if claims else None,
        'logs': logs.get(identifier, [])}
    if selected_by_id:
        from production_adoption import saved_actions
        report['adoption_actions'] = saved_actions(root, loaded)
    import production_permissions
    plan = loaded.artifacts['execution-plan.json']
    selections = None
    # Prepared operations are authorized before their send; afterwards the
    # recorded authorizations are the evidence and no grant is still chosen.
    unsent = (compared and submission in {'unclaimed', 'claimed'} and not external_claims
              and ('handoff' not in events or (mode == 'external' and bool(consumer.get('image_input')))))
    draft_paths = [item for item in _execution_draft_paths(root, prepared) if item['available']] if unsent else []
    if len(draft_paths) == 1:
        try:
            decisions = c.load(c.local(root, draft_paths[0]['path']))
            workflow.schema_check(decisions, 'execution-decisions')
            if decisions.get('run') == identifier:
                selections = decisions.get('decisions')
        except INSPECTION_ERRORS as exc:
            report['readiness_diagnostics'].append(from_exception(exc, phase='authorization', file=draft_paths[0]['path']))
    report['authority'] = store.authority_snapshot(root, task_id, authority,
                                                  source_path=prepared['task'].get('authority'))
    edited = report['authority']['source_edited']
    if edited is not None and unsent:
        from cli_invocation import shown
        from production_diagnostics import Diagnostic
        report['readiness_diagnostics'].append(Diagnostic('AUTHORITY_SOURCE_NOT_IMPORTED',
            f'The authority file {edited["path"]} changed after its import. Execution decisions are checked '
            'against the imported authority, so the edit has no effect yet.', severity='warning',
            phase='authority', file=edited['path'],
            required_action='Import the edit with ' + shown(report['authority']['update_action']['argv'])
                            + ' when it records an actual authority change, then draft the execution decisions '
                            'again; otherwise restore the imported content of the file.').as_dict())
    report['authorization_requirements'] = (production_permissions.grant_requirements(
        authority.document if authority is not None else None, plan['operations'], selections=selections)
        if unsent else None)
    import production_cleanup
    report['cleanup'] = {'state': 'not-needed', 'eligible': False, 'uploaded': 0, 'deleted': 0, 'retained': 0, 'items': []}
    transport = None
    schedule = None
    if mode == 'dispatcher':
        import transport_contract
        target = loaded.artifacts['execution-target.json']
        transport = transport_contract.load(target['service']['transport'])
        try:
            schedule = poll_schedule(target, prepared['task']['artifact'])
        except ProductionError:
            # An unusable sealed schedule leaves the choice to the caller, as a missing one does.
            schedule = None
        media_directory = c.local(root, claims[-1]['data']['journal']) if claims else directory
        rendered = c.load(media_directory / 'request-contract.json') if claims else loaded.artifacts['request-contract.json']
        report['cleanup'] = production_cleanup.inspect(directory, rendered, execution_state, transport)
    # Authoring-source observations explain later edits without changing the
    # saved request. Recovery and a new claim use their own effect boundaries.
    report['next_action'] = (_action('status', root, ['--run', identifier],
        'This unsent run belongs to closed work, so this view did not compare its current sources. '
        'Select the run to compare them and receive its next action; reopen its inputs in new work with '
        'draft-inputs --from-run when the commission continues.')
        if unchecked and submission in {'unclaimed', 'claimed'} and not external_claims else
        _next_action(root, report, prepared, rows, execution_state=execution_state, authority=authority,
                     transport=transport, schedule=schedule))
    action = report['next_action']
    if (action and 'read_context' not in action
            and action['command'] in {'draft-execution', 'execute', 'draft-review', 'review', 'draft-acceptance', 'accept'}):
        candidate = None
        if action['command'] in {'draft-review', 'review', 'draft-acceptance', 'accept'}:
            if '--candidate' in action['argv']:
                candidate = action['argv'][action['argv'].index('--candidate') + 1]
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
    authentication = _run_authentication(root, prepared, claims, report, execution_state,
                                         loaded.artifacts.get('execution-target.json'))
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
    return _status(root, run)


def _status(root: Path, run: str | None = None, *, loaded=None, previous_runtime=None) -> dict:
    """Inspect the complete status, receiving an already acquired selected run."""
    import production_workflow as workflow
    import production_authoring_state
    from production_compiler import inspect_staging, unregistered_publications
    root = c._root(root)
    def read_task_run(identifier):
        return loaded if loaded is not None and loaded.prepared['run'] == identifier else workflow.read_run(root, identifier)
    result = {'ok': True, 'current_task': production_authoring_state.current_task(root, read_run=read_task_run, run=run),
              'runs': [], 'diagnostics': [],
              'external_effect': False}
    if run is not None:
        workflow.run_identifier(run)
    try:
        items = store.runs(root)
    except INSPECTION_ERRORS as exc:
        items = None
        result['diagnostics'].append(from_exception(exc, phase='status'))
    else:
        if run is not None:
            items = [row for row in items if row['run_id'] == run]
            if not items:
                raise ProductionError('RUN_NOT_REGISTERED', 'No formal run has this ID.', phase='status', run=run,
                    required_action='Run status without --run to list the runs of this Studio, and check that --root '
                                    'names the Studio that holds the run.')
    try:
        logs = _logs_by_run(root)
    except INSPECTION_ERRORS as exc:
        logs = {}
        result['diagnostics'].append(from_exception(exc, phase='logs'))
    authorities: dict = {}
    work_states: dict = {}
    execution_states = []
    execution_diagnostics = []
    for item in items or []:
        identifier = item['run_id']
        try:
            observed = loaded if loaded is not None and loaded.prepared['run'] == identifier else workflow.read_run(root, identifier)
            execution_states.extend(accounting.derive(observed.rows, observed.prepared, identifier).values())
        except INSPECTION_ERRORS as exc:
            result['runs'].append(_blocked_run(root, identifier, exc, logs))
            execution_diagnostics.append({**from_exception(exc, phase='execution-records'),
                                          'run': identifier, 'task_id': item['task_id']})
            continue
        try:
            result['runs'].append(_run_status(root, item, logs, authorities, loaded=observed,
                previous_runtime=previous_runtime if identifier == run else None, work_states=work_states,
                selected_by_id=identifier == run))
        except INSPECTION_ERRORS as exc:
            result['runs'].append(_blocked_run(root, identifier, exc, logs))
    current = result['current_task']
    if current is not None and current.get('focus') == 'execution':
        selected = next((item for item in result['runs'] if item['run'] == current['production_run']), None)
        if selected is None:
            current['next_actions'] = [_action('status', root, ['--run', current['production_run']],
                'Inspect the existing run for the current work task and follow its saved execution state.')]
        else:
            current['next_actions'] = [selected['next_action']] if selected['next_action'] else []
            if selected.get('task_disposition') == 'completed' and not current['next_actions']:
                import work_ledger
                from cli_invocation import python_argv
                try:
                    current['work_completion'] = work_ledger.finish_state(root, selected['run'])
                except INSPECTION_ERRORS as exc:
                    diagnostic = from_exception(exc, phase='work-finish',
                        file='work/tasks/' + current['task_id'] + '/task.json')
                    current.setdefault('diagnostics', []).append(diagnostic)
                    result['diagnostics'].append(diagnostic)
                    current['next_actions'] = [{'command': 'show',
                        'argv': python_argv(Path(work_ledger.__file__), 'show', '--studio', str(root)),
                        'reason': 'Inspect and repair the owning work record. Its unreadable finish state does not erase the saved result.'}]
                else:
                    work = current['work_completion']
                if current.get('work_completion') and not work['finished']:
                    command = 'finish' if work['ready_to_finish'] else 'show'
                    arguments = ['--run', selected['run']] if work['ready_to_finish'] else []
                    current['next_actions'] = [{'command': command,
                        'argv': python_argv(Path(work_ledger.__file__), command, '--studio', str(root), *arguments),
                        'reason': ('The selected result and all work steps are complete; finish this exact task.'
                            if work['ready_to_finish'] else
                            'The result is complete. Continue the listed unfinished work or resolve its questions before finishing; '
                            'record only steps actually completed.')}]
    authority_errors = [error for _, error in authorities.values() if error is not None]
    result['ok'] = (not result['diagnostics'] and not authority_errors
                    and all(row['integrity'] == 'intact' for row in result['runs']))
    result['execution_records'] = (accounting.summary(root, run=run, isolate=True) if items is None else
        accounting.summarize_states(execution_states, diagnostics=execution_diagnostics))
    try:
        staging = inspect_staging(root)
    except INSPECTION_ERRORS as exc:
        staging = exc
    try:
        journals = unclaimed_journals(root)
    except INSPECTION_ERRORS as exc:
        journals = exc
    try:
        publications = unregistered_publications(root, store.runs(root))
    except INSPECTION_ERRORS as exc:
        publications = exc
    # The combined cleanup inspection reports its first failing collector in
    # staging, while each audit retains its own outcome. Acquire them once and
    # preserve that existing diagnostic order in all three projections.
    cleanup_error = next((value for value in (staging, journals, publications)
                          if isinstance(value, BaseException)), None)
    if cleanup_error is None:
        result['staging'] = [row['name'] for row in staging]
        result['staging_details'] = staging
    else:
        result['staging'] = []
        result['staging_details'] = [{'diagnostics': [from_exception(cleanup_error, phase='cleanup')]}]
    result['unclaimed_journals'] = ([{'diagnostics': [from_exception(journals, phase='cleanup')]}]
        if isinstance(journals, BaseException) else journals)
    result['unregistered_publications'] = ([{'diagnostics': [from_exception(publications, phase='publication')]}]
        if isinstance(publications, BaseException) else publications)
    return result
