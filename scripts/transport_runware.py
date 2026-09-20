#!/usr/bin/env python3
"""Runware transport: the service-specific half of a dispatch.

A transport module turns a verified Generation Package into the exact bytes one
service accepts and reads the service's answer back. `dispatch.py` owns
everything that is not service-specific: the studio, the record, the files.

A module named `transport_<service>.py` is found by that service id and provides,
with these exact signatures:

    media_paths(verified)                                -> list[str]
        The local files that must be registered with the service before the
        request can name them: the selected reference transports.

    build(verified, offering, service, media_ids, seed, count) -> dict
        The request as it would be sent, with local paths replaced by the ids in
        `media_ids`. Called once for the dry run with `media_ids` empty and once
        with the real ids, so the request is shown before anything is uploaded.

    added_parameters(offering, seed, count)              -> dict
        What the dispatch adds to the package's own parameters, by this service's
        request keys. `build` places exactly this, and `dispatch.py` puts exactly
        this to the model record and the service's observed schema, so that what
        is checked is what is sent.

    upload(path, service, key) -> str
        Register one local file and return the id the request will carry.

    send(request, service, key) -> dict
        Perform the request and return the parsed answer.

    rejections(answer) -> list[dict]
        The service's refusals, empty when it accepted the request.

    results(answer) -> list[dict]
        One entry per returned image: {"url", "seed", "id"}.
"""
from __future__ import annotations
from io_budget import environment_seconds

import base64
import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from model_contract import generation_media_counts

SERVICE = "runware"


def _endpoint(service: dict[str, Any]) -> str:
    url = ((service.get("endpoint") or {}).get("base_url") or "").strip()
    if not url:
        raise SystemExit("the service record carries no endpoint.base_url")
    return url


def _post(payload: list[dict[str, Any]], service: dict[str, Any], key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        _endpoint(service),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=environment_seconds("PRODUCTION_HTTP_TIMEOUT_SECONDS")) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"errors": [{"code": f"http{error.code}", "message": body}]}


def media_paths(verified: dict[str, Any]) -> list[str]:
    forwarding = verified.get("host_forwarding") or {}
    return [str(item.get("resolved_path")) for item in forwarding.get("selected_references") or [] if item.get("resolved_path")]


def _place(task: dict[str, Any], key_path: str, value: Any) -> None:
    """Write a value at a request key, which may name a nested envelope."""
    parts = key_path.split(".")
    target = task
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _merge_absent(target: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Write each default at its key path where the target has nothing there."""
    for key, value in defaults.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_absent(target[key], value)
        elif isinstance(value, dict) and key not in target:
            target[key] = json.loads(json.dumps(value))
        elif key not in target:
            target[key] = value


def build(verified: dict[str, Any], offering: dict[str, Any], service: dict[str, Any],
          media_ids: dict[str, str], seed: int | None = None, count: int = 1) -> dict[str, Any]:
    if "imageInference" not in (service.get("operations") or {}):
        raise SystemExit("the service record does not describe the operation 'imageInference'")
    forwarding = verified["host_forwarding"]
    transport = forwarding["selected_transport"]
    task: dict[str, Any] = {
        "taskType": "imageInference",
        "taskUUID": str(uuid.uuid4()),
        "model": offering["model_identifier"],
        "positivePrompt": forwarding["effective_prompt"],
    }
    # The negative travels only on a channel the verifier selected for it.
    negative = (transport.get("rendition") or {}).get("negative") or ""
    if transport.get("mode") in ("separate-field", "native-subset") and negative:
        task["negativePrompt"] = negative
    for name, value in (forwarding.get("parameters") or {}).items():
        _place(task, str(name), value)
    keys = offering.get("request_keys") or {}
    paths = media_paths(verified)
    if paths:
        ids = [media_ids.get(path, f"<{path}>") for path in paths]
        # The role, and how many go on it, are settled where the package was
        # checked, so what is sent is what was judged.
        try:
            role = next(iter(generation_media_counts(offering, len(ids))))
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        _place(task, str(keys[role][0]), ids if role.endswith("images") else ids[0])
    for name, value in added_parameters(offering, seed, count).items():
        _place(task, name, value)
    _merge_absent(task, ((offering.get("constraints") or {}).get("as_written") or {}))
    return task


def added_parameters(offering: dict[str, Any], seed: int | None = None, count: int = 1) -> dict[str, Any]:
    """What a dispatch adds to the parameters the package carries, by this service's request keys.

    The seed and the result count come from the command line rather than from the
    package, so they were never put to the model record or to the service's
    observed schema when the package was built. Naming them here lets the
    dispatcher check them before it sends them.
    """
    added: dict[str, Any] = {}
    if seed is not None:
        added["seed"] = seed
    if count and count != 1:
        added["numberResults"] = count
    return added


def build_upscale(model_identifier: str, source_path: str, scale: float, settings: dict[str, Any],
                  offering: dict[str, Any], service: dict[str, Any], media_ids: dict[str, str],
                  guidance: str | None = None) -> dict[str, Any]:
    """The upscale request as sent: the source by the offering's input key, the factor, the settings by their request keys, and a guidance prompt where the offering takes one."""
    if "imageUpscale" not in (service.get("operations") or {}):
        raise SystemExit("the service record does not describe the operation 'imageUpscale'")
    keys = offering.get("request_keys") or {}
    if not keys.get("input image"):
        raise SystemExit(f"the offering on {offering.get('service')!r} records no request key for the input image")
    task: dict[str, Any] = {
        "taskType": "imageUpscale",
        "taskUUID": str(uuid.uuid4()),
        "model": model_identifier,
        "upscaleFactor": int(scale) if float(scale).is_integer() else scale,
    }
    _place(task, str(keys["input image"][0]), media_ids.get(source_path, f"<{source_path}>"))
    for key_path, value in settings.items():
        _place(task, key_path, value)
    # A guidance prompt travels only where the offering records a key for it;
    # dispatch.py refuses one that has nowhere to go before anything is uploaded.
    if guidance and keys.get("guidance prompt"):
        _place(task, str(keys["guidance prompt"][0]), guidance)
    # An enlargement is kept lossless; a compressed result would spend what the pass produced.
    task.setdefault("outputFormat", "PNG")
    _merge_absent(task, ((offering.get("constraints") or {}).get("as_written") or {}))
    return task


def upload(path: str, service: dict[str, Any], key: str) -> str:
    data = Path(path).read_bytes()
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
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
    return [item for item in errors if isinstance(item, dict)] if isinstance(errors, list) else []


def results(answer: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for entry in (answer.get("data") or []) if isinstance(answer, dict) else []:
        if not isinstance(entry, dict):
            continue
        found.append({"url": entry.get("imageURL"), "seed": entry.get("seed"), "id": entry.get("imageUUID") or entry.get("taskUUID")})
    return found
