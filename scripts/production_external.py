"""Receive actual external results and derive their durable production records.

The executor supplies the returned files and its conclusion about completion.
The runtime owns decoding, hashes, candidate counts and settlement records.
Nothing in this module invokes a provider or judges the depicted result.
"""
from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Any

import execution_contract as c
import execution_lifecycle as lifecycle
import production_store as store
from production_diagnostics import ProductionError
import request_contract as request


def _pointer(value: Any, label: str) -> list[str | int]:
    if not isinstance(value, list) or any(
            not ((isinstance(part, str) and part) or (type(part) is int and part >= 0))
            for part in value):
        raise ValueError(label + ' must be an array of nonempty keys and nonnegative indices')
    return value


def _selected(document: Any, pointer: list[str | int], label: str) -> Any:
    _pointer(pointer, label)
    return request.get(document, pointer) if pointer else document


def _saved(root: Path, directory: Path, raw: bytes) -> dict:
    key = c.object_store(directory, raw)
    return {'path': (directory / 'objects' / key).relative_to(root).as_posix(),
            'sha256': key, 'size': len(raw)}


def _image_bytes(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError('selected response image must be a base64 string or an image data URL')
    encoded = value
    if value.startswith('data:'):
        header, separator, encoded = value.partition(',')
        if not separator or not header.startswith('data:image/') or not header.endswith(';base64'):
            raise ValueError('selected response image must use an image base64 data URL')
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('selected response image is not valid base64; supply downloaded files for remote URLs') from exc


def _settle(root: Path, run: str, receipt: dict) -> dict:
    """Commit a generated receipt after receiving candidates, without live-input gates."""
    import image_input
    import production_workflow as workflow
    from state_protocol import validate_against_schema

    schema = c.load(Path(__file__).resolve().parents[1] / 'schemas/production-external-receipt.schema.json')
    errors = validate_against_schema(receipt, schema)
    if errors:
        raise ValueError('external result receipt: ' + '; '.join(errors))
    with store.transaction(root):
        directory, prepared, consumer, rows = workflow.load_run(root, run)
        claim = workflow.find(rows, 'external-claim', receipt['claim'])
        authorization = claim['data']['authorizations'][0]
        approved = workflow.find(rows, 'authorization', authorization)['data']['request']
        if receipt['actor'] != approved['actor']:
            raise ProductionError('AUTHORIZATION_MISMATCH', 'External receipt actor differs from the delegated executor.',
                                  phase='settlement', run=run)
        acquired = [row for row in rows if row['event'] == 'candidate']
        if receipt['outputs'] != len(acquired):
            raise ProductionError('INPUT_CONSISTENCY_ERROR', 'External receipt output count differs from saved candidates.',
                                  phase='settlement', run=run, expected=len(acquired), actual=receipt['outputs'])
        response = workflow.file_record(root, directory, receipt['response']['path'])
        if response['sha256'] != receipt['response']['sha256']:
            raise ProductionError('EVIDENCE_SNAPSHOT_CORRUPT', 'External response differs from the saved receipt.',
                                  phase='settlement', run=run)
        receipt_record = _saved(root, directory, c.encoded(receipt))
        evidence = [receipt_record, response]
        submission = receipt.get('submission')
        submission_record = None
        if submission is not None:
            submission_record = workflow.file_record(root, directory, submission['path'])
            evidence.append(submission_record)
        request_evidence = image_input.submission_evidence(consumer.get('image_input'), submission,
            lambda path: c.object_read(directory, submission_record['sha256']))
        if receipt['final']:
            lifecycle.record_effect(root, run, authorization, claim=claim['sha256'], step='external-send',
                usage={**receipt['cost'], 'final': True} if receipt['cost'] is not None else None, evidence=evidence)
        row = lifecycle.record_result(root, run, authorization, outputs=receipt['outputs'], cost=receipt['cost'],
                                      final=receipt['final'], evidence=evidence)
        return {'recorded': receipt['final'],
                'execution_completed': receipt['final'] and receipt['outputs'] == claim['data']['count'],
                'request_evidence': request_evidence, 'receipt_file': receipt_record['path'],
                'response_file': response['path'], 'receipt': row, 'external_effect': False,
                'execution_records': lifecycle.summary(root, run=run)}


def receive_external(root: Path, run: str, *, response_file: str,
                     artifacts: list[str] | None = None,
                     image_pointers: list[list[str | int]] | None = None,
                     final: bool, reason: str, submission_file: str | None = None,
                     request_pointer: list[str | int] | None = None,
                     model_identity_pointer: list[str | int] | None = None,
                     cost_pointer: list[str | int] | None = None) -> dict:
    """Capture returned files and selected inline images, then record the actual response.

    Pointers use arrays of keys and indices into the actual saved response or call.
    A cost pointer selects the provider's exact ``{currency, amount}`` object;
    without that evidence billing remains unknown. Finality and its reason are
    the executor's explicit conclusion. Each capture commits before settlement,
    so a later read or comparison failure cannot discard an acquired image.
    Repeating this operation recovers the same result without another host call.
    """
    import production_workflow as workflow

    c.text(reason, 'external result reason')
    if type(final) is not bool:
        raise ValueError('external result final must be a boolean')
    artifacts = [] if artifacts is None else artifacts
    image_pointers = [] if image_pointers is None else image_pointers
    if not isinstance(artifacts, list) or any(not isinstance(path, str) or not path for path in artifacts):
        raise ValueError('external artifacts must be an array of received file paths')
    if not isinstance(image_pointers, list):
        raise ValueError('image pointers must be an array of response field paths')
    for pointer in image_pointers:
        _pointer(pointer, 'response image pointer')
    if submission_file is None and (request_pointer is not None or model_identity_pointer is not None):
        raise ValueError('recorded call pointers require an actual submission file')
    if submission_file is not None:
        _pointer(request_pointer, 'recorded call request pointer')
        if model_identity_pointer is not None:
            _pointer(model_identity_pointer, 'recorded model identity pointer')
    if cost_pointer is not None:
        _pointer(cost_pointer, 'response cost pointer')

    directory, prepared, _, rows = workflow.load_run(root, run)
    if prepared['task']['execution'] != 'external':
        raise ProductionError('INPUT_CONSISTENCY_ERROR', 'This run does not delegate execution to an external host.',
                              phase='result-capture', run=run)
    claim = workflow.find(rows, 'external-claim')
    authorization = claim['data']['authorizations'][0]
    actor = workflow.find(rows, 'authorization', authorization)['data']['request']['actor']
    response_raw = store.stable_bytes(root, response_file)
    if not response_raw:
        raise ValueError('external response must contain the actual returned evidence')
    response = _saved(root, directory, response_raw)
    document = c.decode(response_raw) if image_pointers or cost_pointer is not None else None
    submission = None
    if submission_file is not None:
        call = _saved(root, directory, store.stable_bytes(root, submission_file))
        submission = {'path': call['path'], 'sha256': call['sha256'], 'locator': 'recorded host call',
                      'request_pointer': request_pointer, 'model_identity_pointer': model_identity_pointer}

    note = 'External host result received by ' + actor + '. ' + reason
    captured = []
    for artifact in artifacts:
        captured.append(workflow.capture(root, run, artifact, note))
    for pointer in image_pointers:
        if prepared['task']['artifact'] != 'image':
            raise ValueError('inline image selectors require an image task')
        raw = _image_bytes(_selected(document, pointer, 'response image pointer'))
        item = _saved(root, directory, raw)
        captured.append(workflow.capture(root, run, item['path'], note))

    cost = None if cost_pointer is None else _selected(document, cost_pointer, 'response cost pointer')
    if cost is not None:
        lifecycle.validate_cost(cost)
    _, _, _, rows = workflow.load_run(root, run)
    acquired = [row for row in rows if row['event'] == 'candidate']
    receipt = {'claim': claim['sha256'], 'actor': actor, 'outputs': len(acquired),
               'cost': cost, 'final': final, 'reason': reason,
               'response': {'path': response['path'], 'sha256': response['sha256'], 'locator': 'whole'}}
    if submission is not None:
        receipt['submission'] = submission
    result = _settle(root, run, receipt)
    result['candidates'] = [row['sha256'] for row in acquired]
    result['received'] = list(dict.fromkeys(row['sha256'] for row in captured))
    return result
