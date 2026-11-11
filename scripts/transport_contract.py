#!/usr/bin/env python3
"""What every transport module defines, and the network rules every transport shares.

A transport is the one module that knows a service's field names, hosts and
answer shapes. The service record names it in `transport`: the value "synthetic"
selects scripts/transport_synthetic.py. load() refuses a name that is not
lowercase letters, digits and underscores before it imports anything.

A transport defines these names, and check() refuses a module that lacks one or
gives one the wrong type, naming each such name in one error:

    OPERATIONS
        A dict: the service's operation name for each model record
        `operation_kind` it sends. `compile_upscale` is needed only where it
        names "upscale".

    RESULT_HOSTS
        A set of the hosts a returned image URL may name; the image is fetched
        over https.

    UPLOAD_SOURCE
        "bytes" when the upload endpoint receives the verified file content, or
        "url" when it imports an authored, remotely readable source URL.

    endpoint(service) -> str
        The service record's endpoint, refused unless the credential may go there.

    compile_request(verified, offering, service, media_ids, seed, count) -> dict
        {"request", "layout", "request_trace"}: the request as it would be
        sent, the source of each field, and a layout naming where each part
        sits, as request_contract.validate_layout reads it: the model and the
        operation (null where the address carries them), the prompt, the
        negative, the output count, the seed, each media item, and the
        identifiers of this one run. `media_ids` is empty for the preview.

    compile_upscale(model_identifier, source_path, scale, settings, offering,
                    service, media_ids, guidance) -> dict
        The same for an upscale of one image.

    added_parameters(offering, seed, count) -> dict
        The seed and the count the dispatch adds, on this service's keys.

    upload_media(data, media_type, service, key, *, source_url) -> dict
        Register the verified image through the service's HTTP interface,
        applying the network rules below, and return exactly provider_id,
        response (the actual provider JSON), and usage (null or a currency,
        decimal-string amount and final boolean). Missing billing evidence is
        unknown, never zero; a quoted ceiling is not an actual charge. A
        service that answers and refuses the upload raises Refused with that
        answer. source_url is the sealed URL for a URL-import interface and
        None for a byte-upload interface. The URL is an existing host/storage
        locator; an adapter does not publish a local file to obtain one. A URL
        importer verifies the stored content against data before accepting the
        issued identifier. The original provider response remains unmodified.

    usage(answer) -> dict | None
        The independently reported send charge, not an upload-plus-send total.
        The same usage shape is used for each external effect.

    send(request, service, key) -> dict
        Perform the request through post() and return the answer as a JSON object.

    lookup(request, service, key) -> dict | None
        Ask the service again, by the request's original identifiers, for the
        answer to a request that was sent: one that was lost, or one whose
        outputs were unfinished. Return that answer in the shape send()
        returns, or None when the service gives no answer for it. A service
        that never leaves an output unfinished and offers no way to ask again
        returns None.

    rejections(answer) -> list[dict]
        The service's refusals, empty when it accepted the request.

    results(answer) -> list[dict]
        One entry per returned image with its "seed" and "id", and either its
        "url" or its bytes as base64 text in "data". An unfinished output has
        "pending": true. Acceptance does not imply that all outputs finished.

    observation_outcome(answer) -> str
        The outcome of an answer the service gave.

A transport may also define these names; check() refuses one with the wrong type:

    prepare_delete(provider_id, service) -> dict
        Build the exact request to delete an input registered by this execution.
        Its operation identifier is stable once the request is journaled.

    send_delete(request, service, key, *, provider_id) -> dict
        Send the recorded deletion once. Return exactly response (the actual
        provider JSON) and usage. Outputs are captured before cleanup begins;
        a cleanup failure cannot start a new upload or generation. Verify the
        request's target against provider_id from the owned upload receipt.
        A definitive deletion error is recorded without sending it again.

    lookup_delete(request, service, key, *, provider_id) -> dict | None
        Ask for the outcome of that recorded deletion. Return the same result
        as send_delete, or None when the provider has no definitive answer.
        An unknown deletion is reconciled without sending it again. These
        three methods form one complete optional cleanup capability.

    CREDENTIAL_FREE
        True for a transport that reaches no network and reads no credential.
        execute and resume then read no key; every other transport gets the
        value selected by the service's Studio authentication entry. Stored
        values and explicit environment sources share this transport contract.

Every send has one of three outcomes:

- accepted: the service answered and took the request.
- rejected: the service answered and refused the request, so nothing was made.
- indeterminate: the service may or may not have carried out the request.

post() applies these network rules to each adapter's HTTP request:

- the address is https, or http on a loopback address for a local test service;
- a redirect is never followed, because it would carry the credential elsewhere;
- the exchange waits as long as PRODUCTION_HTTP_TIMEOUT_SECONDS allows, and with no deadline when it is unset;
- a 5xx answer, a redirect, a timeout or a dropped connection raises Indeterminate.

The dispatcher puts every endpoint to address() and sends through send_once(),
which turns any failed exchange into Indeterminate. The dispatcher records it and
stops, and nothing is sent again.
"""
from __future__ import annotations

import http.client
import importlib
import ipaddress
import re
import urllib.error
import urllib.request
from types import ModuleType
from typing import Any, Callable
from urllib.parse import urlparse

from io_budget import environment_seconds

NAME = re.compile(r"^[a-z0-9_]+$")
TIMEOUT = "PRODUCTION_HTTP_TIMEOUT_SECONDS"

ACCEPTED, REJECTED, INDETERMINATE = "accepted", "rejected", "indeterminate"
OUTCOMES = (ACCEPTED, REJECTED, INDETERMINATE)


def _operations(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(key, str) and isinstance(item, str) for key, item in value.items())


def _hosts(value: Any) -> bool:
    return isinstance(value, (set, frozenset)) and all(isinstance(host, str) for host in value)


# Each name a transport defines, with the test its value passes and the words a refusal uses.
NAMES: dict[str, tuple[Callable[[Any], bool], str]] = {
    "OPERATIONS": (_operations, "a dict of operation names"),
    "RESULT_HOSTS": (_hosts, "a set of host names"),
    "UPLOAD_SOURCE": (lambda value: value in ("bytes", "url"), "bytes or url"),
    "endpoint": (callable, "a function"),
    "compile_request": (callable, "a function"),
    "compile_upscale": (callable, "a function"),
    "added_parameters": (callable, "a function"),
    "upload_media": (callable, "a function"),
    "usage": (callable, "a function"),
    "send": (callable, "a function"),
    "lookup": (callable, "a function"),
    "rejections": (callable, "a function"),
    "results": (callable, "a function"),
    "observation_outcome": (callable, "a function"),
}

# Names a transport may define, with the same test and words.
OPTIONAL: dict[str, tuple[Callable[[Any], bool], str]] = {
    "prepare_delete": (callable, "a function"),
    "send_delete": (callable, "a function"),
    "lookup_delete": (callable, "a function"),
    "CREDENTIAL_FREE": (lambda value: type(value) is bool, "a boolean"),
}


def check(module: Any) -> Any:
    """The module, refused in one error that names every missing or wrongly typed name."""
    operations = getattr(module, "OPERATIONS", None)
    upscales = isinstance(operations, dict) and "upscale" in operations
    problems = []
    for name, (passes, kind) in NAMES.items():
        if name == "compile_upscale" and not upscales:
            continue
        if not hasattr(module, name):
            problems.append(f"{name} is missing")
        elif not passes(getattr(module, name)):
            problems.append(f"{name} is not {kind}")
    for name, (passes, kind) in OPTIONAL.items():
        if hasattr(module, name) and not passes(getattr(module, name)):
            problems.append(f"{name} is not {kind}")
    cleanup = ('prepare_delete', 'send_delete', 'lookup_delete')
    if any(hasattr(module, name) for name in cleanup):
        problems.extend(name + ' is missing from the cleanup capability'
                        for name in cleanup if not hasattr(module, name))
    if problems:
        label = getattr(module, "__name__", "the transport")
        raise ValueError(f"{label} does not meet the transport contract in scripts/transport_contract.py: "
                         + "; ".join(problems))
    return module


def load(name: Any) -> ModuleType:
    """The transport module the service record names, checked against the contract."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError(f"{name!r} is not a transport name; the service record's transport is lowercase "
                         "letters, digits and underscores")
    module_name = "transport_" + name
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise ValueError(
            f"the service record names the transport {name!r}, and there is no scripts/{module_name}.py. Write it "
            "against scripts/transport_contract.py, or send by hand and record the result with scripts/studio.py iterate."
        ) from None
    return check(module)


def _loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def address(url: Any) -> str:
    """The URL, where it is https or http on a loopback address and names no user or password."""
    parsed = urlparse(str(url or ""))
    host = parsed.hostname or ""
    secure = parsed.scheme == "https" or (parsed.scheme == "http" and _loopback(host))
    if not host or not secure or parsed.username or parsed.password:
        raise ValueError(f"refused to send to {url!r}: a service is reached over https, or over http on a "
                         "loopback address for a local test service")
    return str(url)


class Indeterminate(OSError):
    """The exchange ended without an answer, so the service may or may not have carried out the request."""

    def __init__(self, reason: str, *, status: int | None = None, body: bytes | None = None) -> None:
        super().__init__(reason)
        self.reason, self.status, self.body = reason, status, body

    def evidence(self) -> dict[str, Any]:
        """What the run journal keeps: the reason, and the status and body of an answer that came."""
        return {"outcome": INDETERMINATE, "reason": self.reason, "http_status": self.status,
                "body": None if self.body is None else self.body.decode("utf-8", "replace")}


class Refused(ValueError):
    """The service answered and refused the exchange, so nothing was made; the answer is kept."""

    def __init__(self, reason: str, answer: Any) -> None:
        super().__init__(reason)
        self.reason, self.answer = reason, answer

    def evidence(self) -> dict[str, Any]:
        """What the run journal keeps: the outcome, the reason and the service's own answer."""
        return {"outcome": REJECTED, "reason": self.reason, "answer": self.answer}


def credential_free(transport: Any) -> bool:
    """Whether the transport declares that it reaches no network and reads no credential."""
    return getattr(transport, "CREDENTIAL_FREE", False) is True


def lookup_once(transport: Any, request: dict[str, Any], service: dict[str, Any], key: str) -> dict[str, Any]:
    """Ask the service once for the answer to a sent request, and say what the asking found.

    The result is {"outcome", "answer", "reason"}. The outcome is "found" with the
    service's answer, "no-answer" when the service gave none, and "unavailable"
    when the exchange ended without an answer. Only "found" carries an answer.
    """
    try:
        answer = transport.lookup(request, service, key)
    except Indeterminate as unknown:
        return {"outcome": "unavailable", "answer": None, "reason": unknown.reason, "evidence": unknown.evidence()}
    except (OSError, http.client.HTTPException) as exc:
        return {"outcome": "unavailable", "answer": None,
                "reason": _failure(exc, environment_seconds(TIMEOUT)).reason}
    if answer is None:
        return {"outcome": "no-answer", "answer": None, "reason": "The service gave no answer for this request."}
    if not isinstance(answer, dict):
        raise ValueError("the transport's lookup returned something other than a JSON object or None")
    return {"outcome": "found", "answer": answer, "reason": None}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Leave a redirect unfollowed, so it reaches post() as an answer with its 3xx status."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _failure(exc: BaseException, seconds: float | None) -> Indeterminate:
    """The reason an exchange ended without an answer, from the error's type and never from its text."""
    cause = getattr(exc, "reason", exc) if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(cause, TimeoutError):
        return Indeterminate(f"no complete answer within {TIMEOUT} ({seconds:g} seconds)" if seconds
                             else "the exchange timed out before a complete answer")
    return Indeterminate(f"the connection ended before a complete answer ({type(cause).__name__})")


def post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    """POST body to url and return the answer's status and body; a 2xx or 4xx answer is returned as it came."""
    request = urllib.request.Request(address(url), data=body, headers=headers, method="POST")
    seconds = environment_seconds(TIMEOUT)
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=seconds) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        try:
            answer = error.read() if error.fp is not None else b""
        except (OSError, http.client.HTTPException):
            answer = b""
        if 300 <= error.code < 400:
            raise Indeterminate(f"the service answered {error.code} with a redirect, which is not followed",
                                status=error.code, body=answer) from None
        if error.code >= 500:
            raise Indeterminate(f"the service answered {error.code}", status=error.code, body=answer) from None
        return error.code, answer
    except (OSError, http.client.HTTPException) as exc:
        raise _failure(exc, seconds) from None


def send_once(transport: Any, request: dict[str, Any], service: dict[str, Any], key: str) -> dict[str, Any]:
    """The transport's answer to one send; an exchange that ends without one raises Indeterminate."""
    try:
        return transport.send(request, service, key)
    except Indeterminate:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise _failure(exc, environment_seconds(TIMEOUT)) from None


def outcome(transport: Any, answer: dict[str, Any]) -> str:
    """The transport's outcome for an answer, refused unless it is one of OUTCOMES."""
    value = transport.observation_outcome(answer)
    if value not in OUTCOMES:
        raise ValueError(f"the transport gave the outcome {value!r}; an answer's outcome is one of {', '.join(OUTCOMES)}")
    return value


def reading(transport: Any, answer: dict[str, Any]) -> dict[str, Any]:
    """What the dispatcher reads from an answer: its outcome, its outputs, its refusals and its charge.

    Two answers with the same reading settle, capture and charge a request alike.
    """
    return {"outcome": outcome(transport, answer), "results": transport.results(answer),
            "rejections": transport.rejections(answer), "usage": transport.usage(answer)}


def complete(transport: Any, answer: dict[str, Any]) -> bool:
    """Whether this observation settles the request, independently of acceptance."""
    observed = outcome(transport, answer)
    entries = transport.results(answer)
    if observed == INDETERMINATE or any(entry.get('pending') for entry in entries):
        return False
    return observed == REJECTED or bool(transport.rejections(answer)) or any(
        entry.get('url') or entry.get('data') for entry in entries)
