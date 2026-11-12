#!/usr/bin/env python3
"""Show the exact request a prepared run sends, and hold the transfer, journal and recovery steps execute uses.

Usage:
  python scripts/dispatch.py <generation-package.json> --studio DIR --character ID --slot SLOT
      [--preview-out FILE]
  python scripts/dispatch.py --upscale --model ID --source IMAGE --scale N --render-intent FILE
      --request-validation-file FILE [--settings-file FILE] [--guidance "..."]
      --studio DIR --character ID --slot SLOT [--preview-out FILE]

The studio is the production root, and every relative path is a /-separated
path below it. A Generation Package names the run it is bound to; an upscale
goes under the run prepared for the studio's open task. The preview refuses
what `production_workflow.py execute` refuses for that run: a changed source,
a package, upscale input or recording target that differs from the sealed one,
and a run that already owns an execution. Authorization, cost and credentials
are what execute settles; the preview shows the cost the authorization covers.

The preview prints the render contract, then the model, the service and its
endpoint, the output count, whether the negative prompt is sent and the cost,
and then the exact request, so the author approves the thing that would be sent
rather than a description of it. `--preview-out FILE` saves the request with
its trace and the validation report. Nothing is claimed, uploaded or sent;
`production_workflow.py execute` is the one send path.

The service record (endpoint, auth, operations) is the `service-profiles`
resource, and the model's identifier and request keys on that service are the
model record's offering. The record's `transport` names the module that knows the
rest of the service; scripts/transport_contract.py states what that module defines.

When execute sends, the functions here keep the request and the answer in a run
journal under the studio's runs/, save every returned image (decoded when the
answer carries it inline, downloaded over https from a declared host when it
names a URL), and build the Upscale Package of an enlarged image. A send that
ends without an answer is journaled as indeterminate, and nothing is sent again.
"""
from __future__ import annotations
import operation_context as _operation_context
from io_budget import environment_seconds

import argparse
import base64
import contextlib
import copy
import hashlib
import http.client
import itertools
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execution_contract  # noqa: E402
import studio  # noqa: E402
import transport_contract  # noqa: E402
from catalog_cli import configure_pack_runtime  # noqa: E402
from model_contract import (  # noqa: E402
    NEGATIVE_ROLE, generation_media_counts, request_key, select_offering, validate_generation_parameters,
    validate_request_instance,
)
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime  # noqa: E402
from prepare_generation_references import model_pack_root, resolve_model_record  # noqa: E402
from upscale_package import build_upscale_package, validate_settings  # noqa: E402


def result_url(url: str, hosts: Iterable[str]) -> str:
    """The URL of a returned image, only where it is https on a host the transport declares."""
    hosts = frozenset(hosts)
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in hosts or parsed.username or parsed.password:
        raise ValueError(f"refused to download {url!r}: returned images are fetched over https from "
                         f"{', '.join(sorted(hosts)) or 'no declared host'} only")
    return url


class _ResultRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to https on a declared result host."""

    def __init__(self, hosts: Iterable[str]) -> None:
        super().__init__()
        self.hosts = frozenset(hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        result_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(hosts: Iterable[str]):
    return urllib.request.build_opener(_ResultRedirect(hosts))


def _is_image(head: bytes) -> bool:
    return (head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def save(url: str, destination: Path, hosts: Iterable[str]) -> str:
    """Download one returned image to destination and return its SHA-256.

    The body streams to a temporary file beside the destination. It replaces the
    destination only when it begins like a PNG, JPEG or WebP image and its length
    matches a declared Content-Length.
    """
    result_url(url, hosts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with os.fdopen(descriptor, "wb") as stream:
            request = urllib.request.Request(url, method="GET")
            with _opener(hosts).open(request, timeout=environment_seconds("PRODUCTION_HTTP_TIMEOUT_SECONDS")) as response:
                declared = response.headers.get("Content-Length")
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    head = (head + chunk)[:12] if len(head) < 12 else head
                    digest.update(chunk)
                    size += len(chunk)
                    stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if declared is not None and (not declared.strip().isdigit() or int(declared) != size):
            raise ValueError(f"{url} declared a Content-Length of {declared!r} and sent {size} bytes")
        if not _is_image(head):
            raise ValueError(f"{url} did not return a PNG, JPEG or WebP image")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return digest.hexdigest()


def inline_image(data: Any) -> bytes:
    """The bytes of an image the answer carries as base64 text, only where they begin like a PNG, JPEG or WebP image."""
    if not isinstance(data, str):
        raise ValueError("inline image data is not base64 text")
    raw = base64.b64decode(data, validate=True)
    if not _is_image(raw[:12]):
        raise ValueError("the inline image data is not a PNG, JPEG or WebP image")
    return raw


def image_suffix(raw: bytes) -> str:
    return ".png" if raw.startswith(b"\x89PNG") else ".webp" if raw.startswith(b"RIFF") else ".jpg"


def offering_summary(offering: dict[str, Any], model_id: str | None = None,
                     record: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the studio records about where a result came from: the record, its family, and the service."""

    return {
        "model": model_id,
        "dialect": (record or {}).get("prompt_dialect"),
        "id": offering["service"],
        "model_identifier": offering["model_identifier"],
        "observed_at": offering["observed_at"],
        "schema_snapshot": offering.get("schema_snapshot"),
    }


def mapped_settings(record: dict[str, Any], offering: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Each declared setting on the request key the offering gives it; a setting with no key is refused."""
    from production_diagnostics import ProductionError
    checked = validate_settings(record, settings)
    keys = offering.get("setting_keys") or {}
    placed: dict[str, Any] = {}
    for name, value in checked.items():
        key = keys.get(name)
        if not key:
            raise ProductionError(
                "CONTROL_NOT_AVAILABLE",
                f"the offering on {offering.get('service')!r} records no request key for the setting {name!r}",
                phase="request-compilation", pointer="$.settings." + name,
                required_action="Omit the setting, or add it to the offering's setting_keys.",
            )
        from render_contract_lib import _get, _put
        if _get(placed, str(key))[0]:
            raise ValueError('two settings map to one request control')
        _put(placed, str(key), value)
    return placed


def guidance_key(offering: dict[str, Any]) -> str | None:
    """The request key this offering takes a guidance prompt on, or None where it takes none."""
    keys = (offering.get("request_keys") or {}).get("guidance prompt") or []
    return str(keys[0]) if keys else None


def require_guidance_key(offering: dict[str, Any], guidance: str | None) -> str | None:
    """The key a guidance prompt would travel on; a guidance prompt with nowhere to go is refused here."""
    key = guidance_key(offering)
    if guidance and key is None:
        from production_diagnostics import ProductionError
        raise ProductionError(
            "CONTROL_NOT_AVAILABLE",
            f"the offering on {offering.get('service')!r} records no request key for a guidance prompt, so one "
            "cannot be sent there",
            phase="request-compilation", pointer="$.guidance_prompt",
            required_action="Upscale by hand and build the package with scripts/build_upscale_package.py, "
            "or add 'guidance prompt' to the offering's request_keys.",
        )
    return key


def endpoint(service: dict[str, Any], transport: Any) -> str:
    """The endpoint the transport accepts from the service record; one the network rules refuse stops here."""
    return transport_contract.address(transport.endpoint(service))


def check_request(verified: dict[str, Any], record: dict[str, Any], offering: dict[str, Any], model_id: str,
                  transport: Any, seed: int | None, count: int) -> None:
    """Put what would be sent to the model record and the offering's parameter contract.

    The package was checked when it was built, but a dispatch adds a seed and a
    result count that were never in it. The transport names them, so they are
    checked the same way here, on a dry run as well as on a send: the tool's
    promise is that a request the service would refuse is refused before it is
    shown, not after it is sent.
    """

    forwarding = verified["host_forwarding"]
    parameters = {**(forwarding.get("parameters") or {}), **transport.added_parameters(offering, seed, count)}
    selected = forwarding.get("selected_transport") or {}
    negative = (selected.get("rendition") or {}).get("negative") or ""
    media_counts = generation_media_counts(offering, len(forwarding.get("selected_references") or []),
                                           media_role=forwarding["reference_media_role"])
    for item in forwarding.get('technical_media', []):
        media_counts[item['role']] = media_counts.get(item['role'], 0) + 1
    validate_generation_parameters(
        record,
        parameters,
        service=offering["service"],
        pack_root=model_pack_root(model_id),
        prompt=forwarding["effective_prompt"],
        negative_prompt=negative if selected.get("mode") in ("separate-field", "native-subset") else None,
        media_counts=media_counts,
        output_count=count,
    )


def check_upscale(rendered: dict[str, Any], offering: dict[str, Any], model_id: str) -> None:
    """Put the built upscale request to the offering's parameter contract before anything is uploaded.

    The fields that only address the operation or name this one run are left
    out, because the schema describes the model's own parameters.
    """
    import request_contract as rc
    import request_renderer
    instance = copy.deepcopy(rendered["request"])
    for path in request_renderer.envelope_fields(rendered):
        rc.remove(instance, path)
    validate_request_instance(offering, instance, model_pack_root(model_id), model_id)


def negative_line(package: dict[str, Any], rendered: dict[str, Any], offering: dict[str, Any]) -> str:
    """Whether the authored negative prompt travels, in words a person approving the request reads."""
    field = rendered["layout"].get("negative_text")
    if field:
        return "sent on " + ".".join(str(part) for part in field)
    payload = package["generation_payload"]
    if not payload["negative_prompt"].strip():
        return "none authored"
    if request_key(offering, NEGATIVE_ROLE) is None:
        return "not sent; this target has no negative field, so the authored negative stays in the package"
    mode = payload["negative_transport"]["mode"]
    return f"not sent under the record's {mode} negative transport; the authored negative stays in the package"




def show_preview(*, sealed: tuple, rendered: dict[str, Any], negative: str, review: list[dict[str, Any]],
                 preview_out: str | None) -> None:
    """A few plain lines a person can check, then the exact request; the long trace goes to --preview-out."""
    _, prepared, _, _, _, _, plan, target, _ = sealed
    offering, service = target["offering"], target["service"]
    lines = [
        f"model: {target['model_id']} as {offering['model_identifier']} (offering observed {offering.get('observed_at')})",
        f"service: {offering['service']} at {(service.get('endpoint') or {}).get('base_url')} (record observed {service.get('observed_at')})",
        f"outputs: {rendered['output_count']}",
        f"negative prompt: {negative}",
        f"production run: {prepared['run']}",
        *[f"review: {item.get('statement')}" for item in review],
        f"saved: trace and validation in {preview_out}" if preview_out
        else "more: --preview-out FILE saves the trace and validation",
        "shown, not sent; production_workflow.py execute sends it under the run's authorization",
        f"request (sha256 {rendered['request_sha256']}):",
    ]
    print("\n".join(lines))
    print(json.dumps(rendered["request"], ensure_ascii=False, indent=2))


def record_refusal(root: Path, name: str, request: dict[str, Any], refused: list[dict[str, Any]], **facts: Any) -> Path:
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    body = (json.dumps({"at": execution_contract.now(), **facts, "submitted": request, "refused": refused}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    base = f"{name}-{execution_contract.content_id(request)[:8]}-refused"
    # A resent request can be refused again; each refusal keeps its own file.
    for number in itertools.count(1):
        path = runs / (f"{base}.json" if number == 1 else f"{base}-{number}.json")
        try:
            with path.open("xb") as stream:
                stream.write(body)
            break
        except FileExistsError:
            continue
    print(f"refused by the service: {json.dumps(refused, ensure_ascii=False)}")
    print(f"recorded {path}")
    return path


class RunJournal:
    """Durable local evidence, created right before the claim and the first upload or paid request.

    `owner` names the operation and process that created it, so a journal that
    no claim names can be told apart from one still being written.
    """

    def __init__(self, path: Path, document: dict[str, Any]) -> None:
        self.path = path
        self.document = document

    @classmethod
    def create(cls, root: Path, **facts: Any) -> "RunJournal":
        from pack_manager import generate_uuid7
        path = root / "runs" / generate_uuid7()
        path.mkdir(parents=False, exist_ok=False)
        owner = {"operation_id": _operation_context.current_operation_id(), "pid": os.getpid()}
        journal = cls(path, {"at": execution_contract.now(), **facts, "owner": owner, "status": "preparing", "iterations": []})
        journal.update()
        return journal

    @classmethod
    def open(cls, path: Path) -> "RunJournal":
        return cls(path, json.loads((path / "run.json").read_text(encoding="utf-8")))

    def write(self, name: str, value: Any) -> Path:
        target = execution_contract.local(self.path, name, exists=False)
        raw = execution_contract.encoded(value)
        if name != 'run.json' and target.exists():
            if execution_contract.read(target) == raw:
                return target
            raise ValueError('saved journal evidence already exists with different contents: ' + name)
        execution_contract.atomic(target, raw, replace=name == 'run.json')
        execution_contract.fsync_dir(self.path)
        return target

    def update(self, **facts: Any) -> None:
        self.document.update(facts, updated_at=execution_contract.now())
        self.write("run.json", self.document)

    def keep(self, source: Path, name: str) -> Path:
        target = self.path / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            execution_contract.atomic(target, execution_contract.read(source))
        return target


@contextlib.contextmanager
def recorded_run(root: Path, **facts: Any):
    journal = RunJournal.create(root, **facts)
    print(f"run evidence: {journal.path}")
    try:
        yield journal
    except BaseException as exc:
        # Exception text can contain a remote endpoint or a credential. Keep
        # only its type and stage; exact requests and answers have their own files.
        try:
            journal.update(status="failed", failed_at=journal.document["status"], error_type=type(exc).__name__)
        except OSError:
            pass  # Never mask the original failure with a second disk failure.
        print(f"run failed; recover saved evidence from {journal.path}; do not blindly resend", file=sys.stderr)
        raise


def send_and_keep(run: RunJournal, transport: Any, request: dict[str, Any], service: dict[str, Any],
                  key: str) -> dict[str, Any] | None:
    """Keep the first observation; only a terminal response becomes answer.json."""
    try:
        answer = transport_contract.send_once(transport, request, service, key)
    except transport_contract.Indeterminate as unknown:
        run.write("indeterminate.json", unknown.evidence())
        run.update(status="indeterminate")
        print(f"error: {unknown.reason}; whether the service carried out the request is unknown. Nothing is sent "
              f"again. Check the service's own records before preparing a new run; the request is kept in {run.path}",
              file=sys.stderr)
        return None
    run.write('send-observation.json', answer)
    keep_answer(run, transport, answer)
    return answer


def _store_observation(run: RunJournal, name: str, value: Any) -> Path:
    """Keep provider evidence immutable and diagnose differing saved bytes."""
    from production_diagnostics import ProductionError
    path = execution_contract.local(run.path, name, exists=False)
    expected = execution_contract.encoded(value)
    if path.exists():
        actual = execution_contract.read(path)
        if actual != expected:
            raise ProductionError('RESPONSE_CORRUPT', 'Saved provider evidence differs from the response being recovered.',
                                  phase='result-capture', file=str(path),
                                  expected=hashlib.sha256(expected).hexdigest(), actual=hashlib.sha256(actual).hexdigest(),
                                  required_action='Restore this journal file to its recorded bytes. The run that owns this journal '
                                                  'keeps them in its objects directory, production/runs/RUN/objects/, under the SHA-256 '
                                                  'its event evidence lists for this path. Do not resend the request.')
    return run.write(name, value)


def keep_answer(run: RunJournal, transport: Any, answer: dict[str, Any]) -> bool:
    """Seal a completed provider response, leaving earlier observations unchanged."""
    observed = transport_contract.outcome(transport, answer)
    if not transport_contract.complete(transport, answer):
        run.update(status='pending' if observed == transport_contract.ACCEPTED else 'indeterminate')
        return False
    answer_path = _store_observation(run, 'answer.json', answer)
    _store_observation(run, "transport-outcome.json", {"outcome": transport_contract.outcome(transport, answer),
              "response_sha256": hashlib.sha256(answer_path.read_bytes()).hexdigest()})
    run.update(status="answered")
    return True


def _restore_journal_files(run: RunJournal, names: list[str], kept: dict[str, Path]) -> str:
    """The repair of journal files that no longer agree: copy back each recorded copy that differs.

    `kept` maps a journal file name to the run's object file that holds the bytes
    an event of the run recorded for it. A file no event recorded has no copy in
    the run, so it is restored from a copy of the Studio.
    """
    copies = []
    for name in names:
        path = run.path / name
        current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if name in kept and kept[name].name != current:
            copies.append(f'Copy {kept[name]} to {path}')
    if copies:
        return '; '.join(copies) + '. Then run resume for this run; do not resend the request.'
    return ('The events of this run hold no copy of ' + ' or '.join(str(run.path / name) for name in names)
            + ' with other bytes; restore the changed file from a copy of this Studio, then run resume for this run. '
              'Do not resend the request.')


def _receipt_entry(run: RunJournal, transport: Any, index: int, kept: dict[str, Path],
                   media_key) -> tuple[dict[str, Any], dict[str, Any]]:
    """The receipt `response-N.json` and the output it describes in the provider answer it names.

    A receipt that disagrees reports RESPONSE_CORRUPT with `file` (the receipt)
    and `answer`. The answer is the file to restore when the run recorded it with
    the digest the receipt names; the receipt is when the answer still has the
    bytes the run recorded for it.
    """
    from production_diagnostics import ProductionError
    name = f'response-{index}.json'

    def corrupt(message: str, restore: list[str], answer: str | None = None, **details: Any) -> ProductionError:
        if answer is not None:
            details['answer'] = str(run.path / answer)
        return ProductionError('RESPONSE_CORRUPT', message, phase='result-capture', file=str(run.path / name),
                               required_action=_restore_journal_files(run, restore, kept), **details)
    try:
        receipt = json.loads((run.path / name).read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        receipt = None
    if not isinstance(receipt, dict) or not isinstance(receipt.get('answer'), str) or receipt.get('index') != index:
        raise corrupt('The output response file is not the receipt this journal wrote for its output.', [name])
    try:
        source = execution_contract.local(run.path, receipt['answer'])
        source_body = execution_contract.read(source)
    except (OSError, ValueError):
        raise corrupt('The output response file names a provider answer this journal does not hold.', [name],
                      receipt['answer']) from None
    observed, current = receipt.get('answer_sha256'), hashlib.sha256(source_body).hexdigest()
    if observed != current:
        recorded = kept.get(receipt['answer'])
        restore = ([receipt['answer']] if recorded is not None and recorded.name == observed else
                   [name] if recorded is not None and recorded.name == current else [name, receipt['answer']])
        raise corrupt('The output response file and the provider answer it names no longer agree.', restore,
                      receipt['answer'], expected=observed, actual=current)
    source_entries = [entry for entry in transport.results(json.loads(source_body.decode('utf-8')))
                      if entry.get('url') or entry.get('data')]
    position = receipt.get('source_index')
    if type(position) is not int or not 1 <= position <= len(source_entries):
        raise corrupt('The output response file names a position its provider answer does not have.', [name],
                      receipt['answer'])
    entry = source_entries[position - 1]
    if (any(receipt.get(key) != entry.get(key) for key in ('id', 'url', 'seed'))
            or receipt.get('media_key') != media_key(entry)):
        raise corrupt('The output response file names another output than its provider answer holds there.', [name],
                      receipt['answer'])
    return receipt, entry


def acquire(run: RunJournal, transport: Any, *, answer_name: str = 'answer.json',
            captured: dict[int, str] | None = None, kept: dict[str, Path] | None = None) -> dict[str, Any]:
    """Acquire cumulative outputs against their first response and recorded bytes.

    Each output keeps its first observation, stable index and acquisition digest.
    Later observations may change order; an existing provider id reuses its index.
    An interrupted download is retried, while changed acquired bytes are refused.
    `kept` maps a journal file name to the run's object file that holds the
    bytes an event recorded for it, which a refusal names as its repair. Every
    saved receipt is checked against its answer before a new output is indexed.
    """
    from production_diagnostics import ProductionError
    captured = dict(captured or {})
    kept = dict(kept or {})
    upscale = run.document["operation"] == "upscale"
    body = execution_contract.read(execution_contract.local(run.path, answer_name))
    answer, answer_sha256 = json.loads(body.decode("utf-8")), hashlib.sha256(body).hexdigest()
    entries = [entry for entry in transport.results(answer) if entry.get("url") or entry.get("data")]
    refused = transport.rejections(answer)
    def media_key(entry: dict) -> str:
        return execution_contract.content_id({'data': entry['data']} if entry.get('data') else {'url': entry.get('url')})
    checked = {index: _receipt_entry(run, transport, index, kept, media_key)
               for index in sorted(int(path.stem.split('-')[1]) for path in run.path.glob('response-*.json')
                                   if path.stem.split('-')[1].isdigit())}
    receipts = {index: receipt for index, (receipt, _) in checked.items()}
    sources = {index: entry for index, (_, entry) in checked.items()}
    observed, assigned = {}, set()
    for source_index, entry in enumerate(entries, 1):
        shared_id = not entry.get('id') or sum(item.get('id') == entry.get('id') for item in entries) > 1 \
            or sum(item.get('id') == entry.get('id') for item in receipts.values()) > 1
        matches = [index for index, receipt in sorted(receipts.items()) if index not in assigned
                   and receipt.get('id') == entry.get('id')
                   and (not shared_id or receipt['media_key'] == media_key(entry))]
        index = matches[0] if matches else max(receipts, default=0) + 1
        assigned.add(index)
        observed[index] = entry
        if index not in receipts:
            receipt = {'at': execution_contract.now(), 'answer': answer_name, 'answer_sha256': answer_sha256,
                       'source_index': source_index, 'index': index, 'seed': entry.get('seed'),
                       'id': entry.get('id'), 'url': entry.get('url'), 'media_key': media_key(entry)}
            run.write(f'response-{index}.json', receipt)
            receipts[index] = receipt
            sources[index] = entry
    run.update(status="downloading", received=len(receipts), refused=refused)
    folder, stem = (run.path / "upscale.references", "output") if upscale else (run.path, "result")
    acquired, failed, downloaded = [], [], 0
    for index in sorted(receipts):
        response = run.path / f"response-{index}.json"
        entry = sources[index]
        acquired_path = run.path / f'acquisition-{index}.json'

        def receipt_changed() -> ProductionError:
            # The receipt, or the output response whose digest it keeps, differs from the bytes first written.
            return ProductionError('PROVIDER_OUTPUT_CHANGED', 'The acquisition receipt differs from the recorded output.',
                                   phase='result-capture', file=str(acquired_path), output_response=str(response),
                                   required_action=_restore_journal_files(run, [acquired_path.name, response.name], kept))
        try:
            previous = json.loads(acquired_path.read_text(encoding='utf-8')) if acquired_path.is_file() else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise receipt_changed() from None
        if previous is not None and not isinstance(previous, dict):
            raise receipt_changed()
        expected = captured.get(index) or (previous or {}).get('sha256')
        try:
            if entry.get("data"):
                raw = inline_image(entry["data"])
                result = folder / f"{stem}-{index}{image_suffix(raw)}"
                if not result.is_file():
                    execution_contract.atomic(result, raw, replace=True)
                original = hashlib.sha256(raw).hexdigest()
            else:
                result = folder / f"{stem}-{index}{suffix_of(entry['url'])}"
                if not result.is_file() or not expected:
                    save(entry["url"], result, transport.RESULT_HOSTS)
                    downloaded += 1
                original = expected
            digest = execution_contract.sha256_file(result)
            latest_data = observed.get(index, {}).get('data')
            latest_digest = hashlib.sha256(inline_image(latest_data)).hexdigest() if latest_data else digest
        except (OSError, ValueError, http.client.HTTPException) as exc:
            # No credential goes to a result host, so the reason is kept.
            failed.append({"index": index, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if ((original and digest != original) or (expected and digest != expected) or latest_digest != digest):
            raise ProductionError('PROVIDER_OUTPUT_CHANGED', 'Acquired provider output differs from its first recorded bytes.',
                                  phase='result-capture', file=str(result), expected=expected or original, actual=digest,
                                  required_action='Restore this result file to its first recorded bytes, whose SHA-256 is given as '
                                                  'expected. The run that owns this journal keeps them in production/runs/RUN/objects/ '
                                                  'under that SHA-256. Do not resend the request.')
        acquisition = {'path': result.relative_to(run.path).as_posix(), 'sha256': digest, 'size': result.stat().st_size,
                       'response_sha256': execution_contract.sha256_file(response)}
        if previous is not None and previous != acquisition:
            # The result file still has its first bytes, so the receipt or the output response it digests changed.
            raise receipt_changed()
        run.write(acquired_path.name, acquisition)
        acquired.append((index, result, response))
    run.update(failed_downloads=failed)
    return {"entries": len(receipts), "observed_indices": sorted(observed), "refused": refused,
            "acquired": acquired, "failed": failed, "downloaded": downloaded}


def upscale_result_package(run: RunJournal, index: int, output: Path, *, loaded=None) -> Path:
    """The Upscale Package of one returned image, built once from the source and the declared operation."""
    path = run.path / f"upscale-package-{index}.json"
    if path.is_file():
        return path
    declared = json.loads((run.path / "package.json").read_text(encoding="utf-8"))
    source = run.document["upscale"]["source"]
    binding = None
    target=None
    if run.document.get("production_run"):
        import production_workflow as workflow
        loaded=loaded or workflow.read_run(run.path.parent.parent, run.document["production_run"])
        _, prepared, _, _ = loaded
        if prepared['run']!=run.document['production_run']:
            raise ValueError('upscale result input belongs to another registered run')
        target=loaded.artifacts['execution-target.json']
        binding = {"run": run.document["production_run"], "input_sha256": prepared["input_sha256"]}
    output_carrier = run.path / "upscale.references" / (f"output-{index}" + output.suffix.lower())
    if not output_carrier.exists():
        execution_contract.atomic(output_carrier, execution_contract.read(output))
    elif execution_contract.sha256_file(output_carrier) != execution_contract.sha256_file(output):
        raise ValueError("upscale output companion differs from captured pixels")
    package = build_upscale_package(
        model=declared["model"], source_image=run.path / source, output_image=output_carrier, package_root=run.path,
        source_stored_path=source, output_stored_path=output_carrier.relative_to(run.path).as_posix(),
        scale_factor=float(declared["scale_factor"]), settings=declared["settings"],
        guidance_prompt=declared["guidance_prompt"], audit_status=run.document["upscale"]["audit_status"],
        audit_notes=[], production_binding=binding,model_record=target['model'] if target is not None else None,
    )
    return run.write(path.name, package)


def recorded_iteration(root: Path, character: str, origin: dict, paths: tuple[Path, Path, Path]) -> str | None:
    """Recover this exact captured output independently of its current placement."""
    wanted = [studio.sha256_file(path) for path in paths]
    rows = [row for row in studio.read_iterations(studio.character_dir(root, character), project=False)
            if row.get('production') == origin]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError('the captured Production candidate has more than one Studio iteration')
    row = rows[0]
    if [(row.get(key) or {}).get('sha256') for key in ('result', 'request', 'response')] != wanted:
        raise ValueError('the captured Production iteration differs from its retained result, request or response')
    return row['iteration_id']


def write_preview_outputs(args: argparse.Namespace, root: Path, rendered: dict, validation: dict) -> None:
    """Save an explicitly requested preview as a new file; nothing is claimed or executed."""
    value = getattr(args, "preview_out", None)
    if value is None:
        return
    from production_binding import new_output, write_new
    from model_rendition import review_requirements
    path = new_output(root, value, option="--preview-out", root_option="--studio")
    write_new(path, execution_contract.encoded({"request_contract": rendered, "validation": validation,
                                                "review_requirements": review_requirements(),
                                                "execution_ready": False, "external_effect": False}),
              option="--preview-out", value=str(value))


def open_run(root: Path) -> str | None:
    """The production run prepared for the studio's open task, which an upscale goes under."""
    import work_ledger
    return (work_ledger.read_current(root) or {}).get("production_run")


def read_package(root: Path, value: str | Path) -> tuple[Path, dict[str, Any]]:
    """The Generation Package a path below the studio, or an absolute path, names."""
    from production_binding import studio_file
    path = studio_file(root, value, option="package", root_option="--studio")
    package = execution_contract.decode(execution_contract.read(path))
    if not isinstance(package, dict):
        raise ValueError(f"{value} is not a Generation Package")
    return path.resolve(), package


def _differs(what: str, pointer: str) -> Exception:
    from production_diagnostics import ProductionError
    return ProductionError("INPUT_CONSISTENCY_ERROR", f"{what} differs from what the prepared run sealed",
                           phase="preview", pointer=pointer,
                           required_action="Preview the run as prepared, or prepare a variant for the changed input.")


def sealed_run(root: Path, run: str, character: str | None = None, slot: str | None = None) -> tuple:
    """The sealed run execute would send, refused where execute refuses it before authorization.

    `production_execution.compiled` checks the saved publication, evidence and
    fixed runtime. A run that already owns an execution, another recording target, or
    an endpoint the network rules refuse stops here as well.
    """
    from production_diagnostics import ProductionError, same_json
    from production_execution import compiled
    sealed = compiled(root, run, fresh=True)
    _, prepared, _, rows, _, _, _, target, transport = sealed
    if any(row["event"] == "dispatch-claim" for row in rows):
        raise ProductionError("DISPATCH_ALREADY_CLAIMED", "This run already owns an execution.", phase="preview", run=run,
                              required_action="Use resume for this execution, variant for changed input, "
                              "or repeat for an intentional new run.")
    recording = prepared["task"].get("recording")
    if character is not None or slot is not None:
        expected = {"character": recording["character"], "slot": recording["slot"]} if recording else None
        if not same_json(expected, {"character": character, "slot": slot}):
            raise _differs("the recording target", "$.recording")
    if recording is not None:
        studio.validate_recording_target(root, recording['character'], recording['slot'], writable=True)
    endpoint(target["service"], transport)
    return sealed


def dispatch_generation(args: argparse.Namespace, root: Path) -> int:
    """Show the sealed request of the run a Generation Package is bound to."""
    import request_renderer
    import runtime_evidence
    import runtime_snapshot
    from production_diagnostics import ProductionError, same_json
    from render_contract_lib import summary as render_summary
    _, package = read_package(root, args.package)
    binding = package.get("production_binding")
    if not isinstance(binding, dict) or not isinstance(binding.get("run"), str):
        raise ProductionError("EXECUTION_NOT_APPLICABLE", "the package is bound to no prepared run, so execute never sends it",
                              phase="preview", file=str(args.package),
                              required_action="Prepare the task with production_workflow.py prepare, "
                              "and preview the package its run holds.")
    sealed = sealed_run(root, binding["run"], args.character, args.slot)
    _, prepared, _, _, stored, rendered, _, target, _ = sealed
    if not same_json(stored, package):
        raise _differs("the package", "$")
    # Preparation verified the package and rendered this request. The preview
    # shows them as sealed and checks the request against the fixed evidence.
    descriptor = prepared["runtime_snapshot"]
    source=runtime_snapshot.CompileRuntime.from_fixed(
        runtime_snapshot.acquire_runtime(runtime_snapshot.path(root,descriptor),descriptor),descriptor)
    validation = request_renderer.check_final(
        stored["request_validation"],
        runtime_evidence.reader(root, snapshots=copy.deepcopy(stored["input_snapshots"]),source=source), rendered)
    write_preview_outputs(args, root, rendered, validation)
    print(render_summary(stored["render_contract"]))
    show_preview(sealed=sealed, rendered=rendered, negative=negative_line(stored, rendered, target["offering"]),
                 review=sealed[6]['review_requirements'], preview_out=args.preview_out)
    return 0


def suffix_of(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in (".png", ".jpg", ".jpeg", ".webp") else ".jpg"


def dispatch_upscale(args: argparse.Namespace, root: Path) -> int:
    """Show the sealed request of the upscale prepared for the studio's open task, given its exact inputs."""
    import request_renderer
    import runtime_evidence
    import runtime_snapshot
    from production_binding import json_object, studio_file, single_stdin, upscale_request, validate_upscale_input
    from production_diagnostics import ProductionError, same_json
    from render_contract_lib import summary as render_summary
    single_stdin({"--settings-file": args.settings_file, "--render-intent": args.render_intent,
                  "--request-validation-file": args.request_validation_file})
    run = open_run(root)
    if run is None:
        raise ProductionError("EXECUTION_NOT_APPLICABLE", "the studio's open work task has no prepared run for an upscale",
                              phase="preview", required_action="Prepare the upscale task with production_workflow.py prepare.")
    sealed = sealed_run(root, run, args.character, args.slot)
    _, prepared, _, _, stored, rendered, _, target, _ = sealed
    if stored.get("artifact_type") != "upscale-request":
        raise ProductionError("INPUT_CONSISTENCY_ERROR", "the open task's run prepared a generation, not an upscale",
                              phase="preview", run=run, required_action="Preview the run's Generation Package instead.")
    descriptor = prepared["runtime_snapshot"]
    source=runtime_snapshot.CompileRuntime.from_fixed(
        runtime_snapshot.acquire_runtime(runtime_snapshot.path(root,descriptor),descriptor),descriptor)
    declared = upscale_request(
        root, studio_file(root, args.source, option="--source", root_option="--studio"), args.model, args.scale,
        json_object(root, args.settings_file, option="--settings-file", root_option="--studio"), args.guidance,
        request_validation=json_object(root, args.request_validation_file, option="--request-validation-file",
                                       root_option="--studio"),
        render_intent=json_object(root, args.render_intent, option="--render-intent", root_option="--studio"),
        input_source=source)
    if not same_json(stored, declared):
        raise _differs("the upscale input", "$")
    from build_generation_payload import resolve_execution_target
    resolved=resolve_execution_target(target,source=source)
    if stored['model']!=resolved.model_id:
        raise _differs('the upscale target','$.model')
    validate_upscale_input(root, stored,input_source=source)
    validation = request_renderer.check_final(
        stored["request_validation"],
        runtime_evidence.reader(root, snapshots=copy.deepcopy(stored["input_snapshots"]),source=source), rendered)
    write_preview_outputs(args, root, rendered, validation)
    print(render_summary(rendered["sealed"]["context"]["render_contract"]))
    show_preview(sealed=sealed, rendered=rendered, negative="none; an upscale takes no negative prompt", review=sealed[6]['review_requirements'],
                 preview_out=args.preview_out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog="A relative path is a /-separated path below the studio root; an absolute path is taken as given. "
        "production_workflow.py execute sends the request.",
    )
    parser.add_argument("package", nargs="?", help="A Generation Package bound to a prepared run; absent with --upscale")
    parser.add_argument("--studio", type=Path, required=True, help="A directory in the studio the run belongs to")
    parser.add_argument("--character", help="Check the optional Studio character already selected by the run")
    parser.add_argument("--slot", help="Check the optional Studio slot already selected by the run")
    parser.add_argument("--upscale", action="store_true", help="Preview the upscale prepared for the studio's open task")
    parser.add_argument("--model", help="With --upscale: the upscaler record")
    parser.add_argument("--source", help="With --upscale: the image to enlarge")
    parser.add_argument("--scale", type=float, help="With --upscale: the factor, one the record declares")
    parser.add_argument("--settings-file", help="With --upscale: UTF-8 JSON settings file, or - for stdin")
    parser.add_argument("--render-intent", help="With --upscale: explicit rendering intent JSON file, or - for stdin")
    parser.add_argument("--guidance", help="With --upscale: a guidance prompt, where the record accepts one")
    parser.add_argument("--request-validation-file",
                        help="With --upscale: explicit validation record and evidence, or - for stdin")
    parser.add_argument("--preview-out", help="New file for the sealed request, its trace and the validation report")
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    if args.upscale:
        if not (args.model and args.source and args.scale and args.render_intent and args.request_validation_file):
            parser.error("--upscale needs --model, --source, --scale, --render-intent and --request-validation-file")
    elif args.package is None:
        parser.error("a Generation Package, or --upscale")
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    from production_binding import new_output, report_failure
    try:
        root = studio.require_studio(args.studio)
        if args.preview_out is not None:
            new_output(root, args.preview_out, option="--preview-out", root_option="--studio")
        return dispatch_upscale(args, root) if args.upscale else dispatch_generation(args, root)
    except (ValueError, OSError) as exc:
        return report_failure(exc, phase="preview")
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
