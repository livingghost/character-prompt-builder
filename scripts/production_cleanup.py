"""Release this execution's uploaded inputs after its outputs are durable.

Upload responses establish ownership. Deletion has its own saved request and
receipt, independent of the generation result. An uncertain deletion is looked
up by that same request; recovery never uploads or generates another image.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import execution_contract as c
import execution_lifecycle as accounting
from operation_context import stage
from production_diagnostics import ProductionError, from_exception


def supported(transport: Any) -> bool:
    return all(callable(getattr(transport, name, None))
               for name in ('prepare_delete', 'send_delete', 'lookup_delete'))


def _owned(directory: Path, rendered: dict, state: dict | None) -> list[dict]:
    """Only actual upload responses already recorded by this execution name targets."""
    if state is None:
        return []
    output = []
    seen = set()
    for index, item in enumerate(rendered['media']):
        result = state['effect_results'].get(f'upload:{index}')
        if result is None or 'outcome' in result:
            continue
        if len(result['evidence']) != 1:
            raise ProductionError('CLEANUP_OWNERSHIP_REQUIRED', 'An uploaded input needs its exact response receipt.',
                                  phase='input-cleanup')
        witness = result['evidence'][0]
        receipt = c.decode(c.object_read(directory, witness['sha256']))
        c.exact(receipt, {'index', 'source', 'source_sha256', 'provider_id', 'response', 'usage'}, 'owned upload receipt')
        if (receipt['index'] != index or receipt['source'] != item['path']
                or receipt['source_sha256'] != item['sha256']):
            # The receipt comes from the run's object store by its digest, so the journal's request copy changed.
            raise ProductionError('CLEANUP_OWNERSHIP_REQUIRED',
                f"The upload receipt of media input {index + 1} names another input than the request-contract.json "
                "of this execution's journal.", phase='input-cleanup', pointer=f'$.media[{index}]',
                expected={'path': receipt['source'], 'sha256': receipt['source_sha256']},
                actual={'path': item['path'], 'sha256': item['sha256']},
                required_action="Restore request-contract.json in this execution's journal, the directory status --run "
                                'reports as journal, to the copy execute wrote: '
                                + str(directory / 'request-contract.json') + ' with each media path moved from the run '
                                'directory into the journal. Its media entry then names the path and SHA-256 given as '
                                'expected, which the upload receipt recorded. Nothing is deleted or sent meanwhile.')
        identifier = c.text(receipt['provider_id'], 'uploaded provider identifier')
        if identifier in seen:
            continue
        seen.add(identifier)
        output.append({'upload_index': index, 'provider_id': identifier,
                       'upload_receipt_sha256': witness['sha256']})
    return output


def inspect(directory: Path, rendered: dict, state: dict | None, transport: Any) -> dict:
    """Read cleanup separately from output capture and artistic review."""
    items = []
    owned = _owned(directory, rendered, state)
    eligible = bool(state and accounting.cleanup_ready(state))
    available = supported(transport)
    for upload in owned:
        boundary = next((item for item in state['steps']
                         if item['operation'] == 'delete' and item['upload_index'] == upload['upload_index']), None)
        result = state['effect_results'].get(boundary['step']) if boundary else None
        item_state = ('deleted' if result is not None and 'outcome' not in result
                      else 'failed' if result is not None
                      else 'outcome_unknown' if boundary else 'pending')
        items.append({**upload, 'state': item_state})
    deleted = sum(item['state'] == 'deleted' for item in items)
    cleanup_state = ('not-needed' if not owned else 'complete' if deleted == len(owned)
                     else 'waiting' if not eligible else 'unsupported' if not available
                     else 'outcome_unknown' if any(item['state'] == 'outcome_unknown' for item in items)
                     else 'pending' if any(item['state'] == 'pending' for item in items) else 'failed')
    return {'state': cleanup_state, 'eligible': eligible, 'uploaded': len(owned), 'deleted': deleted,
            'retained': len(owned) - deleted, 'items': items}


def _name(index: int) -> str:
    return f'delete-{index + 1:03d}'


def _warnings(cleanup: dict) -> list[dict]:
    warnings = []
    failed = sum(item['state'] == 'failed' for item in cleanup['items'])
    if failed:
        warnings.append({'code': 'INPUT_CLEANUP_FAILED', 'phase': 'input-cleanup', 'count': failed,
            'message': 'Deletion failed for recorded uploaded inputs and will not be repeated. Saved images remain available for review.'})
    if cleanup['state'] in {'pending', 'outcome_unknown'}:
        warnings.append({'code': 'INPUT_CLEANUP_PENDING', 'phase': 'input-cleanup',
            'message': 'Cleanup remains for untouched or unresolved inputs. Resume never uploads or generates another image.'})
    return warnings


def _observation(root: Path, run: str, journal, claim: dict, step: str, kind: str,
                 detail: dict) -> None:
    """Keep each lookup/failure as new evidence; never rewrite a provider result."""
    import production_execution as execution
    prefix = step.replace(':', '-')
    number = 1
    while (journal.path / f'{prefix}-observation-{number:03d}.json').exists():
        number += 1
    name = f'{prefix}-observation-{number:03d}.json'
    journal.write(name, {'kind': kind, **detail})
    execution._append(root, run, 'cleanup-observation', {'claim': claim['sha256'], 'step': step, 'kind': kind,
        'evidence': execution._evidence(root, run, journal, [name])})


def _read_request(directory: Path, journal, boundary: dict) -> dict:
    witness = boundary['evidence'][0]
    request = c.decode(c.object_read(directory, witness['sha256']))
    path = journal.path / (_name(boundary['upload_index']) + '-request.json')
    if c.sha256_file(path) != boundary['delete_request_sha256']:
        raise ProductionError('ARTIFACT_CORRUPT', 'The saved deletion request differs from its committed boundary.',
                              phase='input-cleanup', file=str(path),
                              required_action='Copy ' + str(directory / 'objects' / boundary['delete_request_sha256'])
                                              + ' to this journal file, then run resume for this run; the deletion is not sent again.')
    return request


def _receipt(root: Path, run: str, journal, claim: dict, authorization: str,
             boundary: dict, name: str, value: dict) -> None:
    import production_execution as execution
    c.exact(value, {'response', 'usage'}, 'transport deletion result')
    if not isinstance(value['response'], dict):
        raise ValueError('the deletion result must preserve the actual provider response object')
    accounting.validate_usage(value['usage'])
    journal.write(name, value)
    accounting.record_effect(root, run, authorization, claim=claim['sha256'], step=boundary['step'],
                             usage=value['usage'], evidence=execution._evidence(root, run, journal, [name]))


def _refusal(root: Path, run: str, journal, claim: dict, authorization: str,
             boundary: dict, name: str, value: dict) -> None:
    import production_execution as execution
    if value.get('outcome') != 'rejected':
        raise ValueError('a deletion refusal needs an actual rejected provider response')
    journal.write(name, value)
    execution._record_no_effect(root, run, authorization, claim, boundary['step'], 'rejected',
                                 execution._evidence(root, run, journal, [name]))


def perform(root: Path, run: str, journal, claim: dict, target: dict, transport: Any) -> dict:
    """Run only pending cleanup, leaving source files and captured image results intact."""
    import production_execution as execution
    import production_workflow as workflow
    import transport_contract
    directory, prepared, _, rows = workflow.read_run(root, run)
    authorization = claim['data']['authorizations'][0]
    state = accounting.require_active(rows, prepared, run, authorization)
    rendered = c.load(journal.path / 'request-contract.json')
    before = inspect(directory, rendered, state, transport)
    result = {'cleanup': before, 'external_effect': False, 'warnings': _warnings(before)}
    if before['state'] in {'not-needed', 'complete', 'failed', 'waiting'}:
        return result
    if before['state'] == 'unsupported':
        result['warnings'].append({'code': 'INPUT_CLEANUP_UNSUPPORTED', 'phase': 'input-cleanup',
            'message': 'This transport cannot delete the uploaded inputs. Their IDs remain recorded as retained.'})
        return result
    # Reading the original authentication selection does not reactivate a
    # submission. The recorded submit scope already includes these deletions.
    try:
        selected = execution.claim_authentication(claim, transport, target['offering']['service'])
        credential = execution._credential(root, transport, target['offering']['service'], expected=selected)
        key = credential.value if credential is not None else ''
    except (ValueError, OSError) as exc:
        result['warnings'].append(from_exception(exc, phase='input-cleanup'))
        return result
    for upload in before['items']:
        if upload['state'] in {'deleted', 'failed'}:
            continue
        directory, prepared, _, rows = workflow.read_run(root, run)
        state = accounting.require_active(rows, prepared, run, authorization)
        boundary = next((item for item in state['steps']
                         if item['operation'] == 'delete' and item['upload_index'] == upload['upload_index']), None)
        outcome = state['effect_results'].get(boundary['step']) if boundary else None
        if boundary is not None and outcome is None:
            base = _name(upload['upload_index'])
            request = _read_request(directory, journal, boundary)
            receipt_name, refused_name = base + '-result.json', base + '-refused.json'
            # A crash after durable response capture needs no network call.
            if (journal.path / receipt_name).is_file():
                _receipt(root, run, journal, claim, authorization, boundary, receipt_name, c.load(journal.path / receipt_name))
                continue
            if (journal.path / refused_name).is_file():
                _refusal(root, run, journal, claim, authorization, boundary, refused_name, c.load(journal.path / refused_name))
                continue
            try:
                with stage('input-cleanup-lookup'):
                    found = transport.lookup_delete(request, target['service'], key, provider_id=upload['provider_id'])
                    result['external_effect'] = True
                if found is None:
                    _observation(root, run, journal, claim, boundary['step'], 'no-answer',
                                 {'reason': 'The provider did not return the original deletion result.'})
                else:
                    _receipt(root, run, journal, claim, authorization, boundary, receipt_name, found)
            except (ValueError, OSError) as exc:
                # A lookup failure says nothing about the original delete.
                detail = exc.evidence() if hasattr(exc, 'evidence') else {'reason': str(exc)}
                _observation(root, run, journal, claim, boundary['step'], 'lookup-unavailable', detail)
            continue
        if outcome is not None:
            continue
        base = _name(upload['upload_index'])
        request_name, receipt_name, refused_name = (base + suffix for suffix in ('-request.json', '-result.json', '-refused.json'))
        # Reuse a prepared but not yet transmitted delete request after a local
        # interruption, without assigning it a second provider identity.
        if (journal.path / request_name).is_file():
            request = c.load(journal.path / request_name)
        else:
            request = transport.prepare_delete(upload['provider_id'], target['service'])
            if not isinstance(request, dict):
                raise ValueError('prepare_delete must return the exact provider request object')
            journal.write(request_name, request)
        evidence = execution._evidence(root, run, journal, [request_name])[0]
        boundary = accounting.begin_cleanup_step(root, run, authorization, claim=claim['sha256'],
            upload_index=upload['upload_index'], provider_id=upload['provider_id'], request=evidence)['data']
        try:
            with stage('input-cleanup'):
                result['external_effect'] = True
                answer = transport.send_delete(request, target['service'], key, provider_id=upload['provider_id'])
            _receipt(root, run, journal, claim, authorization, boundary, receipt_name, answer)
        except transport_contract.Refused as exc:
            _refusal(root, run, journal, claim, authorization, boundary, refused_name, exc.evidence())
        except (ValueError, OSError) as exc:
            detail = exc.evidence() if hasattr(exc, 'evidence') else {'reason': str(exc)}
            _observation(root, run, journal, claim, boundary['step'], 'outcome-unknown', detail)
    directory, prepared, _, rows = workflow.read_run(root, run)
    result['cleanup'] = inspect(directory, rendered, accounting.require_active(rows, prepared, run, authorization), transport)
    result['warnings'] = _warnings(result['cleanup'])
    return result
