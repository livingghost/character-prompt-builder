#!/usr/bin/env python3
"""Runware transport, written against the transport contract in the dispatch.py docstring.

Runware takes a JSON array of tasks at https://api.runware.ai with the key as a
bearer token, and refuses per task inside a successful answer. Each task names
its operation in `taskType` and carries a fresh `taskUUID`, which is the run's
own identifier; the model sits in `model`, the count in `numberResults`, and the
seed in `seed`. The prompt, the negative and the media go on the keys the
offering gives them. An upscale asks for `upscaleFactor` and a PNG
`outputFormat`. An image is registered with `imageUpload` as a data URI and
travels by the id it returns. A finished image comes back as `imageURL` on
im.runware.ai. An answer body that is not a JSON object is kept as an error
answer.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
import uuid
from typing import Any
from urllib.parse import urlparse

from io_budget import environment_seconds
from model_contract import NEGATIVE_ROLE, PROMPT_ROLE, generation_media_counts, required_request_key

SERVICE = "runware"
API_HOST = "api.runware.ai"
OPERATIONS = {"generation": "imageInference", "upscale": "imageUpscale"}
RESULT_HOSTS = frozenset({"im.runware.ai"})


def endpoint(service: dict[str, Any]) -> str:
    """The record's endpoint, only where it is https on the Runware API host."""
    url = str((service.get("endpoint") or {}).get("base_url") or "").strip()
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != API_HOST or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise ValueError(f"the service record's endpoint {url!r} is not https://{API_HOST}; "
                         "the Runware transport sends the credential to no other place")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the credential to a place the record did not name."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl} refused", headers, fp)


def _answer(status: int, body: bytes) -> dict[str, Any]:
    """The parsed answer, or an error answer that keeps a body that is not a JSON object."""
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = None
    if isinstance(value, dict):
        return value
    return {"errors": [{"code": f"http{status}-not-json-object", "message": body.decode("utf-8", "replace")}]}


def _post(payload: list[dict[str, Any]], service: dict[str, Any], key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint(service),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=environment_seconds("PRODUCTION_HTTP_TIMEOUT_SECONDS")) as response:
            return _answer(response.status, response.read())
    except urllib.error.HTTPError as error:
        return _answer(error.code, error.read() if error.fp is not None else b"")


def _media_paths(verified: dict[str, Any]) -> list[str]:
    forwarding = verified.get("host_forwarding") or {}
    references = forwarding.get("selected_references") or []
    return [str(item.get("resolved_path")) for item in references if item.get("resolved_path")]


def compile_request(verified: dict, offering: dict, service: dict, media_ids: dict | None = None,
                    seed: int | None = None, count: int = 1) -> dict:
    from request_contract import MANAGEMENT_VALUE, RequestWriter, path_parts

    operation = OPERATIONS['generation']
    if operation not in service.get('operations', {}):
        raise ValueError('service does not declare ' + operation)
    if type(count) is not int or count < 1:
        raise ValueError('output count must be a positive integer')
    if seed is not None and type(seed) is not int:
        raise ValueError('seed must be an integer or omitted')
    forwarding = verified['host_forwarding']
    writer = RequestWriter()
    media_ids = media_ids or {}
    source = [{'kind': 'offering', 'service': offering['service'], 'model_identifier': offering['model_identifier']}]

    def write(path, value, kind, transform, bindings=None):
        writer.write(path, value, source_kind=kind, source_refs=source, transform_id=transform, binding_ids=bindings)

    write(['taskType'], operation, 'transport-envelope', 'operation')
    write(['taskUUID'], str(uuid.uuid4()), 'transport-envelope', 'task-identifier')
    write(['model'], offering['model_identifier'], 'model-setting', 'model-identifier')
    prompt = path_parts(required_request_key(offering, PROMPT_ROLE))
    write(prompt, forwarding['effective_prompt'], 'authored', 'selected-rendition')
    prompt_trace = forwarding.get('prompt_trace')
    if prompt_trace:
        # The rendition's own trace replaces the single row written for the whole prompt.
        kept = [row for row in writer.trace if row['target_field'] != prompt]
        writer.trace = kept + [{**row, 'target_field': prompt} for row in prompt_trace]
    layout = {
        'model': ['model'],
        'operation': ['taskType'],
        'primary_text': prompt,
        'negative_text': None,
        'output_count': ['numberResults'],
        'fixed_output_count': None,
        'seed': None,
        'media': [],
        'management': [['taskUUID']],
        'content': [{'id': 'prompt', 'field': prompt}],
        'fields': [
            {'id': 'prompt', 'field': prompt, 'kind': 'content'},
            {'id': 'model', 'field': ['model'], 'kind': 'fixed'},
            {'id': 'operation', 'field': ['taskType'], 'kind': 'fixed'},
            {'id': 'count', 'field': ['numberResults'], 'kind': 'parameter'},
        ],
    }

    selected = forwarding['selected_transport']
    negative = selected['rendition'].get('negative') or ''
    if selected['mode'] in {'separate-field', 'native-subset'} and negative:
        field = path_parts(required_request_key(offering, NEGATIVE_ROLE))
        write(field, negative, 'authored', 'selected-negative-channel')
        layout['negative_text'] = field
        layout['content'].append({'id': 'negative', 'field': field})
        layout['fields'].append({'id': 'negative', 'field': field, 'kind': 'content'})

    parameters = dict(forwarding.get('parameters') or {})
    if 'numberResults' in parameters and parameters['numberResults'] != count:
        raise ValueError('package output count differs from the explicit dispatch count')
    if 'seed' in parameters:
        if seed is not None and parameters['seed'] != seed:
            raise ValueError('package seed differs from the explicit dispatch seed')
        seed = parameters['seed']
    for name, value in sorted(parameters.items()):
        if name in {'seed', 'numberResults'}:
            continue
        path = path_parts(name)
        write(path, value, 'model-setting', 'selected-parameter')
        layout['fields'].append({'id': 'parameter:' + name, 'field': path, 'kind': 'parameter'})

    paths = _media_paths(verified)
    if paths:
        role = next(iter(generation_media_counts(offering, len(paths))))
        field = path_parts(offering['request_keys'][role][0])
        values = [media_ids.get(path, MANAGEMENT_VALUE) for path in paths]
        many = role == 'reference images'
        attachments = [f'attachment:{index + 1}' for index in range(len(paths))]
        write(field, values if many else values[0], 'reference-binding', 'ordered-media', attachments)
        for index in range(len(paths)):
            location = field + [index] if many else field
            layout['media'].append({'index': index, 'field': location})
            layout['fields'].append({'id': f'media:{index + 1}', 'field': location, 'kind': 'media'})
    for control in forwarding.get('native_reference_controls', []):
        write(control['field'], control['value'], 'reference-binding', 'native-reference-controls',
              control['binding_ids'])
        layout['fields'].append({'id': control['id'], 'field': control['field'], 'kind': 'fixed'})

    write(['numberResults'], count, 'model-setting', 'explicit-output-count')
    if seed is not None:
        write(['seed'], seed, 'model-setting', 'explicit-seed')
        layout['seed'] = ['seed']
        layout['fields'].append({'id': 'seed', 'field': ['seed'], 'kind': 'parameter'})
    writer.defaults((offering.get('constraints') or {}).get('as_written') or {}, source)
    return {'request': writer.request, 'layout': layout, 'request_trace': writer.trace}


def added_parameters(offering: dict, seed: int | None = None, count: int = 1) -> dict:
    if type(count) is not int or count < 1:
        raise ValueError('positive explicit output count required')
    added = {'numberResults': count}
    if seed is not None:
        added['seed'] = seed
    return added


def compile_upscale(model_identifier: str, source_path: str, scale: float, settings: dict,
                    offering: dict, service: dict, media_ids: dict, guidance: str | None = None) -> dict:
    from request_contract import MANAGEMENT_VALUE, RequestWriter, path_parts

    operation = OPERATIONS['upscale']
    if operation not in service.get('operations', {}):
        raise ValueError('service does not declare ' + operation)
    keys = offering.get('request_keys', {})
    mapped = keys.get('input image')
    if not mapped:
        raise ValueError('upscale offering has no declared input image field')
    writer = RequestWriter()
    source = [{'kind': 'offering', 'service': offering['service'], 'model_identifier': model_identifier}]

    def write(path, value, kind, transform):
        writer.write(path, value, source_kind=kind, source_refs=source, transform_id=transform)

    write(['taskType'], operation, 'transport-envelope', 'operation')
    write(['taskUUID'], str(uuid.uuid4()), 'transport-envelope', 'task-identifier')
    write(['model'], model_identifier, 'model-setting', 'model-identifier')
    write(['upscaleFactor'], int(scale) if float(scale).is_integer() else scale, 'model-setting', 'selected-scale')
    image_field = path_parts(mapped[0])
    write(image_field, media_ids.get(source_path, MANAGEMENT_VALUE), 'reference-binding', 'upscale-source')
    layout = {
        'model': ['model'],
        'operation': ['taskType'],
        'primary_text': ['guidanceText'],
        'negative_text': None,
        'output_count': None,
        'fixed_output_count': 1,
        'seed': None,
        'media': [{'index': 0, 'field': image_field}],
        'management': [['taskUUID']],
        'content': [],
        'fields': [
            {'id': 'model', 'field': ['model'], 'kind': 'fixed'},
            {'id': 'operation', 'field': ['taskType'], 'kind': 'fixed'},
            {'id': 'scale', 'field': ['upscaleFactor'], 'kind': 'parameter'},
            {'id': 'media:1', 'field': image_field, 'kind': 'media'},
        ],
    }
    if guidance:
        prompt = keys.get('guidance prompt')
        if not prompt:
            raise ValueError('this offering has no guidance prompt field')
        field = path_parts(prompt[0])
        write(field, guidance, 'authored', 'upscale-guidance')
        layout['primary_text'] = field
        layout['content'].append({'id': 'prompt', 'field': field})
        layout['fields'].append({'id': 'prompt', 'field': field, 'kind': 'content'})
    else:
        # An absent text channel is represented in the layout, not injected into the wire request.
        layout['primary_text'] = None
    for name, value in sorted(settings.items()):
        field = path_parts(name)
        write(field, value, 'model-setting', 'selected-upscale-setting')
        layout['fields'].append({'id': 'parameter:' + name, 'field': field, 'kind': 'parameter'})
    writer.defaults({'outputFormat': 'PNG'}, source)
    writer.defaults((offering.get('constraints') or {}).get('as_written') or {}, source)
    return {'request': writer.request, 'layout': layout, 'request_trace': writer.trace}


def upload_bytes(data: bytes, media_type: str, service: dict[str, Any], key: str) -> str:
    """Upload the exact bytes already verified and reserved by the dispatcher."""
    if not isinstance(data, bytes) or not isinstance(media_type, str) or not media_type:
        raise ValueError('upload requires verified bytes and their declared media type')
    payload = f"data:{media_type};base64," + base64.b64encode(data).decode("ascii")
    answer = _post([{"taskType": "imageUpload", "taskUUID": str(uuid.uuid4()), "image": payload}], service, key)
    refused = rejections(answer)
    if refused:
        raise SystemExit(f"the service refused an upload: {json.dumps(refused)}")
    entry = (answer.get("data") or [{}])[0]
    identifier = entry.get("imageUUID") or entry.get("mediaUUID") or entry.get("mediaId")
    if not identifier:
        raise SystemExit(f"the service returned no id for the upload: {json.dumps(answer)}")
    return str(identifier)


def send(request: dict[str, Any], service: dict[str, Any], key: str) -> dict[str, Any]:
    return _post([request], service, key)


def rejections(answer: dict[str, Any]) -> list[dict[str, Any]]:
    errors = answer.get("errors") if isinstance(answer, dict) else None
    if not isinstance(errors, list):
        return []
    return [item for item in errors if isinstance(item, dict)]


def results(answer: dict[str, Any]) -> list[dict[str, Any]]:
    entries = (answer.get("data") or []) if isinstance(answer, dict) else []
    found = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("imageUUID") or entry.get("taskUUID")
        found.append({"url": entry.get("imageURL"), "seed": entry.get("seed"), "id": identifier})
    return found


def observation_outcome(answer: dict) -> str:
    if rejections(answer):
        return 'rejected'
    entries = results(answer)
    if any(entry.get('id') or entry.get('url') or entry.get('pending') for entry in entries):
        return 'accepted'
    return 'indeterminate'
