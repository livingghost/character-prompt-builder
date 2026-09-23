#!/usr/bin/env python3
"""Send a verified Generation Package, or an upscale of one image, to the service its model record names, and record what came back in the studio.

Usage:
  python scripts/dispatch.py <generation-package.json> --studio DIR --character ID --slot SLOT
      [--service ID] [--seed N] [--count N] [--note "..."]
      [--preview-out FILE] [--intent-out FILE]                     show the request, send nothing
  python scripts/dispatch.py ... --production-authorization RECEIPT --send
                                                                   send it and record every result

  python scripts/dispatch.py --upscale --model ID --source <image> --scale N [--settings '{...}']
      [--guidance "..."] --request-validation-file FILE --studio DIR --character ID --slot SLOT
      [--service ID] [--production-authorization RECEIPT --send]

The studio is the production root. A Generation Package bound to a production
run names that run; an upscale goes under the run prepared for the studio's
open task.

A Generation Package is verified first, so what is sent is exactly the host
forwarding the verifier settled: the effective prompt, the negative on the
channel the record declares, the parameters, and the selected reference
transports. An upscale is checked against the upscaler record (the factor and
the settings it declares) and against the service's observed parameter schema,
with each setting placed on the request key the offering's `setting_keys` gives
it; the Upscale Package is built from the source and the returned image and
recorded with them.

The service record (endpoint, auth, operations) is the `service-profiles`
resource, and the model's identifier and request keys on that service are the
model record's offering. The record's `transport` names the module that knows the
rest of the service; scripts/transport_contract.py states what that module defines.

Every returned image is saved and recorded as its own iteration of the
character, with the request as sent, the answer, the package, and the file, and
the studio's gallery is rewritten with it. An image the answer carries inline is
decoded from it; one it names by URL is downloaded. That holds when the service
refuses part of the request, when it returns a different number of images than
the authorization allows, and when another image fails to arrive. Every sent run
is journaled under the studio's runs/ before upload, with the expected and
received counts, any refusal, and any failed download. `production_workflow.py
recover-recording` saves the missing images from the saved answer; nothing is
sent again. A send that ends without an answer is journaled as indeterminate,
and the dispatcher stops.

The dry run prints the model, the service and its endpoint, the output count,
whether the negative prompt is sent, the cost, and then the exact request, so
the user approves the thing that would be sent rather than a description of it.
No byte leaves the machine without `--send`.
"""
from __future__ import annotations
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
import service_profile  # noqa: E402
import studio  # noqa: E402
import transport_contract  # noqa: E402
from catalog_cli import configure_pack_runtime  # noqa: E402
from build_generation_payload import validate_generation_package_carrier_paths  # noqa: E402
from model_contract import (  # noqa: E402
    NEGATIVE_ROLE, generation_media_counts, request_key, select_offering, validate_generation_parameters,
    validate_request_instance,
)
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime  # noqa: E402
from prepare_generation_references import model_pack_root, resolve_model_record  # noqa: E402
from upscale_package import build_upscale_package, validate_settings  # noqa: E402
from verify_generation_payload import verify  # noqa: E402


def api_key(service: dict[str, Any]) -> str:
    """The credential, from the environment or from an MCP server's env block in the host's configuration."""
    variable = ((service.get("auth") or {}).get("env_var") or "").strip()
    if not variable:
        raise SystemExit("the service record names no auth.env_var")
    key = os.environ.get(variable, "").strip() or mcp_server_credential(Path.home() / ".claude.json", variable)
    if key:
        return key
    raise SystemExit(f"the credential is not in the environment. Set {variable} and run again.")


def mcp_server_credential(path: Path, variable: str) -> str | None:
    """The value MCP server env blocks give the variable, top-level or per project, and nothing else in the file."""
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(config, dict):
        return None
    blocks = [config.get("mcpServers")]
    projects = config.get("projects")
    if isinstance(projects, dict):
        blocks.extend(project.get("mcpServers") for project in projects.values() if isinstance(project, dict))
    values = set()
    for servers in blocks:
        for server in servers.values() if isinstance(servers, dict) else ():
            env = server.get("env") if isinstance(server, dict) else None
            value = env.get(variable) if isinstance(env, dict) else None
            if isinstance(value, str) and value.strip():
                values.add(value.strip())
    if len(values) > 1:
        raise SystemExit(f"MCP servers in {path} give {variable} different values. Set {variable} in the environment and run again.")
    return values.pop() if values else None


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
    checked = validate_settings(record, settings)
    keys = offering.get("setting_keys") or {}
    placed: dict[str, Any] = {}
    for name, value in checked.items():
        key = keys.get(name)
        if not key:
            raise SystemExit(
                f"the offering on {offering.get('service')!r} records no request key for the setting {name!r}; "
                "omit it, or add it to the offering's setting_keys"
            )
        placed[str(key)] = value
    return placed


def guidance_key(offering: dict[str, Any]) -> str | None:
    """The request key this offering takes a guidance prompt on, or None where it takes none."""
    keys = (offering.get("request_keys") or {}).get("guidance prompt") or []
    return str(keys[0]) if keys else None


def require_guidance_key(offering: dict[str, Any], guidance: str | None) -> str | None:
    """The key a guidance prompt would travel on; a guidance prompt with nowhere to go is refused here."""
    key = guidance_key(offering)
    if guidance and key is None:
        raise SystemExit(
            f"the offering on {offering.get('service')!r} records no request key for a guidance prompt, so one "
            "cannot be sent there; upscale by hand and build the package with scripts/build_upscale_package.py, "
            "or add 'guidance prompt' to the offering's request_keys"
        )
    return key


def service_for(offering: dict[str, Any], profiles_arg: str | None, settings: Any = None):
    """The service record and the transport it names; an endpoint the network rules refuse stops here."""
    service_id = str(offering["service"])
    # The same runtime the model record came from: a record and the service it
    # names must not be read from two different sets of packs.
    try:
        profiles = service_profile.resolve_path(profiles_arg, state_file=None, cache_dir=None, managed_root=None,
                                                settings=settings)
        service = service_profile.load_service(service_id, profiles)
    except service_profile.PackError as exc:
        raise ValueError(str(exc)) from None
    transport = transport_contract.load(service["transport"])
    transport_contract.address(transport.endpoint(service))
    return service_id, service, transport


def check_request(verified: dict[str, Any], record: dict[str, Any], offering: dict[str, Any], model_id: str,
                  transport: Any, seed: int | None, count: int) -> None:
    """Put what would be sent to the model record and the service's observed schema.

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
    validate_generation_parameters(
        record,
        parameters,
        service=offering["service"],
        pack_root=model_pack_root(model_id),
        prompt=forwarding["effective_prompt"],
        negative_prompt=negative if selected.get("mode") in ("separate-field", "native-subset") else None,
        media_counts=generation_media_counts(offering, len(forwarding.get("selected_references") or [])),
        output_count=count,
    )


def check_upscale(rendered: dict[str, Any], offering: dict[str, Any], model_id: str) -> None:
    """Put the built upscale request to the service's observed schema before anything is uploaded.

    The fields that only address the operation or name this one run are left
    out, because the schema describes the model's own parameters.
    """
    import request_contract as rc
    import request_renderer
    instance = copy.deepcopy(rendered["request"])
    for path in request_renderer.envelope_fields(rendered):
        rc.remove(instance, path)
    validate_request_instance(offering, instance, model_pack_root(model_id))


def negative_line(verified: dict[str, Any], rendered: dict[str, Any], offering: dict[str, Any]) -> str:
    """Whether the authored negative prompt travels, in words a person approving the request reads."""
    field = rendered["layout"].get("negative_text")
    if field:
        return "sent on " + ".".join(str(part) for part in field)
    if not str(verified.get("negative_prompt") or "").strip():
        return "none authored"
    if request_key(offering, NEGATIVE_ROLE) is None:
        return "not sent; this target has no negative field, so the authored negative stays in the package"
    mode = ((verified.get("host_forwarding") or {}).get("selected_transport") or {}).get("mode")
    return f"not sent under the record's {mode} negative transport; the authored negative stays in the package"


def show_preview(*, model_id: str, offering: dict[str, Any], service_id: str, service: dict[str, Any],
                 rendered: dict[str, Any], negative: str, production_run: str | None,
                 review: list[dict[str, Any]], args: argparse.Namespace) -> None:
    """A few plain lines a person can check, then the exact request; the long trace goes to --preview-out."""
    pricing = offering.get("pricing") or service.get("pricing")
    saved = [f"{label} in {path}" for label, path in (("trace and validation", getattr(args, "preview_out", None)),
                                                      ("submission intent", getattr(args, "intent_out", None))) if path]
    lines = [
        f"model: {model_id} as {offering['model_identifier']} (offering observed {offering.get('observed_at')})",
        f"service: {service_id} at {(service.get('endpoint') or {}).get('base_url')} (record observed {service.get('observed_at')})",
        f"outputs: {rendered['output_count']}",
        f"negative prompt: {negative}",
        "cost: " + (json.dumps(pricing, ensure_ascii=False) if pricing
                    else "unknown; the author states the upper bound in the authorization"),
        f"production run: {production_run}" if production_run else "production run: none, so --send is refused",
        *[f"review: {item.get('statement')}" for item in review],
        *([] if args.send else ["saved: " + "; ".join(saved) if saved else
           "more: --preview-out FILE saves the trace and validation; --intent-out FILE saves the submission intent to authorize",
           "shown, not sent"]),
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
    """Durable local evidence, created before the first upload or paid request."""

    def __init__(self, path: Path, document: dict[str, Any]) -> None:
        self.path = path
        self.document = document

    @classmethod
    def create(cls, root: Path, **facts: Any) -> "RunJournal":
        from pack_manager import generate_uuid7
        path = root / "runs" / generate_uuid7()
        path.mkdir(parents=False, exist_ok=False)
        journal = cls(path, {"at": execution_contract.now(), **facts, "status": "preparing", "iterations": []})
        journal.update()
        return journal

    @classmethod
    def open(cls, path: Path) -> "RunJournal":
        return cls(path, json.loads((path / "run.json").read_text(encoding="utf-8")))

    def write(self, name: str, value: Any) -> Path:
        target = self.path / name
        descriptor, temporary = tempfile.mkstemp(prefix=".journal-", dir=self.path)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target

    def update(self, **facts: Any) -> None:
        self.document.update(facts, updated_at=execution_contract.now())
        self.write("run.json", self.document)

    def keep(self, source: Path, name: str) -> Path:
        target = self.path / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
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
    """Send once and keep the answer with its outcome; None for a send whose outcome is unknown.

    A send that ends without an answer keeps its reason in indeterminate.json and
    no answer.json, so recovery and resume treat it as unconfirmed. The caller stops.
    """
    try:
        answer = transport_contract.send_once(transport, request, service, key)
    except transport_contract.Indeterminate as unknown:
        run.write("indeterminate.json", unknown.evidence())
        run.update(status="indeterminate")
        print(f"error: {unknown.reason}; whether the service carried out the request is unknown. Nothing is sent "
              f"again. Check the service's own records before preparing a new run; the request is kept in {run.path}",
              file=sys.stderr)
        return None
    answer_path = run.write("answer.json", answer)
    run.write("transport-outcome.json", {"outcome": transport_contract.outcome(transport, answer),
              "response_sha256": hashlib.sha256(answer_path.read_bytes()).hexdigest()})
    run.update(status="answered")
    return answer


def acquire(run: RunJournal, transport: Any) -> dict[str, Any]:
    """Save every image the saved answer returns that the journal does not hold yet.

    An image the answer carries inline is decoded from it, and one it names by
    URL is downloaded. A result already in the journal is complete, because its
    file is replaced only when whole. One failed image leaves the others.

    The answer stays once, in answer.json. Each image's response-N.json names
    its place among the returned images and the answer's SHA-256, with the seed,
    the id and the URL the transport read there.
    """
    upscale = run.document["operation"] == "upscale"
    body = (run.path / "answer.json").read_bytes()
    answer, answer_sha256 = json.loads(body.decode("utf-8")), hashlib.sha256(body).hexdigest()
    entries = [entry for entry in transport.results(answer) if entry.get("url") or entry.get("data")]
    refused = transport.rejections(answer)
    run.update(status="downloading", received=len(entries), refused=refused)
    folder, stem = (run.path / "upscale.references", "output") if upscale else (run.path, "result")
    acquired, failed, downloaded = [], [], 0
    for index, entry in enumerate(entries, 1):
        response = run.path / f"response-{index}.json"
        if not response.is_file():
            run.write(response.name, {"at": execution_contract.now(), "answer_sha256": answer_sha256, "index": index,
                                      "seed": entry.get("seed"), "id": entry.get("id"), "url": entry.get("url")})
        else:
            named = json.loads(response.read_text(encoding="utf-8"))
            if (named.get("answer_sha256"), named.get("index")) != (answer_sha256, index):
                raise ValueError(f"{response} names another answer or image than answer.json holds; "
                                 "the saved evidence changed, so nothing is recorded from it")
        try:
            if entry.get("data"):
                raw = inline_image(entry["data"])
                result = folder / f"{stem}-{index}{image_suffix(raw)}"
                if not result.is_file():
                    execution_contract.atomic(result, raw, replace=True)
            else:
                result = folder / f"{stem}-{index}{suffix_of(entry['url'])}"
                if not result.is_file():
                    save(entry["url"], result, transport.RESULT_HOSTS)
                    downloaded += 1
        except (OSError, ValueError, http.client.HTTPException) as exc:
            # No credential goes to a result host, so the reason is kept.
            failed.append({"index": index, "error": f"{type(exc).__name__}: {exc}"})
            continue
        acquired.append((index, result, response))
    run.update(failed_downloads=failed)
    return {"entries": len(entries), "refused": refused, "acquired": acquired, "failed": failed, "downloaded": downloaded}


def upscale_result_package(run: RunJournal, index: int, output: Path) -> Path:
    """The Upscale Package of one returned image, built once from the source and the declared operation."""
    path = run.path / f"upscale-package-{index}.json"
    if path.is_file():
        return path
    declared = json.loads((run.path / "package.json").read_text(encoding="utf-8"))
    source = run.document["upscale"]["source"]
    package = build_upscale_package(
        model=declared["model"], source_image=run.path / source, output_image=output, package_root=run.path,
        source_stored_path=source, output_stored_path=output.relative_to(run.path).as_posix(),
        scale_factor=float(declared["scale_factor"]), settings=declared["settings"],
        guidance_prompt=declared["guidance_prompt"], audit_status=run.document["upscale"]["audit_status"],
        audit_notes=[],
    )
    return run.write(path.name, package)


def recorded_iteration(root: Path, character: str, slot: str, paths: tuple[Path, Path, Path]) -> str | None:
    """The iteration already holding this result, request and response, if a recording finished before."""
    wanted = [studio.sha256_file(path) for path in paths]
    for row in studio.read_iterations(studio.character_dir(root, character)):
        if row.get("slot") == slot and [(row.get(key) or {}).get("sha256") for key in ("result", "request", "response")] == wanted:
            return row["iteration_id"]
    return None


def settle(root: Path, run: RunJournal, acquisition: dict[str, Any], *, recovering: bool) -> str:
    """Write the production result and the studio iterations for what was acquired; return the run's status.

    The production run receives its dispatch result only when every returned
    image arrived and their number is the authorized one. Every image that
    arrived becomes a studio iteration either way.
    """
    facts = run.document
    acquired = acquisition["acquired"]
    packages: dict[int, Path] = {}
    if facts["operation"] == "upscale":
        run.update(status="building-package")
        packages = {index: upscale_result_package(run, index, result) for index, result, _ in acquired}
    expected = facts["expected"]
    if acquisition["entries"] and not acquisition["failed"] and acquisition["entries"] == expected:
        from production_workflow import record_dispatch_results
        package = json.loads((run.path / "package.json").read_text(encoding="utf-8"))
        record_dispatch_results(root, facts["production_run"], package, run.path,
                                [result for _, result, _ in acquired], expected)
    run.update(status="recording")
    recorded = list(facts.get("iterations") or [])
    request = run.path / "request.json"
    layout = json.loads((run.path / "request-contract.json").read_text(encoding="utf-8"))["layout"]
    companion = run.path / facts["companion"] if facts.get("companion") else None
    audit = (facts.get("upscale") or {}).get("audit_status")
    for index, result, response in acquired:
        found = recorded_iteration(root, facts["character"], facts["slot"], (result, request, response)) if recovering else None
        if found is None:
            row = studio.iterate(root, facts["character"], facts["slot"], result,
                                 package=packages.get(index, run.path / "package.json"), request=request,
                                 response=response, answer=run.path / "answer.json", note=facts.get("note"),
                                 service=facts.get("offering"), package_companion=companion, layout=layout)
            found = row["iteration_id"]
            detail = f"({'identity audit pending' if audit == 'pending' else 'ready'})" if audit else f"seed {row.get('seed')}"
            print(f"  recorded {found} {detail} -> {row['result']['path']}")
        if found not in recorded:
            recorded.append(found)
            run.update(iterations=list(recorded))
    if acquisition["failed"]:
        status = "download-incomplete"
    elif not acquisition["entries"]:
        status = "refused" if acquisition["refused"] else "no-results"
    elif acquisition["entries"] != expected:
        status = "count-mismatch"
    else:
        status = "complete"
    run.update(status=status)
    return status


def report_outcome(root: Path, run: RunJournal, status: str) -> int:
    """Say what the service's answer left in the studio; 0 only for every authorized image with no refusal."""
    facts = run.document
    if status == "download-incomplete":
        print(f"error: {len(facts['failed_downloads'])} of {facts['received']} returned images were not saved; "
              f"the answer and every image that was are kept in {run.path}. Save the rest without sending "
              f"again: python scripts/production_workflow.py recover-recording --root {root} --run {facts['production_run']}",
              file=sys.stderr)
    elif status == "count-mismatch":
        print(f"error: the service returned {facts['received']} images where the authorization allows "
              f"{facts['expected']}. Every returned image is recorded in the studio; none is a result of "
              f"production run {facts['production_run']}.", file=sys.stderr)
    elif status == "no-results":
        print(f"error: the service answered with no result file; answer retained in {run.path}", file=sys.stderr)
    return 0 if status == "complete" and not facts.get("refused") else 1


def recover(root: Path, production_run: str, journal: Path) -> int:
    """Save what the saved answer returns and the journal lacks, then record it; nothing is sent again.

    `production_workflow.py recover-recording` calls this for a claimed run that
    has no dispatch result yet. Returns the number of images downloaded now; an
    image the answer carries inline is decoded without a connection.
    """
    import execution_contract as c
    if not (journal / "run.json").is_file():
        raise ValueError(f"{journal} holds no dispatch journal, so nothing can be recovered from it")
    run = RunJournal.open(journal)
    if run.document.get("production_run") != production_run:
        raise ValueError("the dispatch journal belongs to another production run")
    if not (journal / "answer.json").is_file():
        raise ValueError("the send has no saved answer, so its outcome is unknown; recovery sends nothing, "
                         "so no image can be recovered from this run")
    acquisition = acquire(run, transport_contract.load(run.document.get("transport")))
    with c.lock(root):
        status = settle(root, run, acquisition, recovering=True)
    if status == "download-incomplete":
        raise ValueError(f"{len(acquisition['failed'])} returned images are still not saved; "
                         f"see {journal / 'run.json'} and run recover-recording again")
    if status == "count-mismatch":
        raise ValueError(f"the service returned {acquisition['entries']} images where the authorization allows "
                         f"{run.document['expected']}; every returned image is recorded in the studio, and none is a production result")
    if status in {"refused", "no-results"}:
        raise ValueError(f"the saved answer holds no image; it is kept in {journal}")
    return acquisition["downloaded"]


def write_preview_outputs(args: argparse.Namespace, rendered: dict, validation: dict, submission: dict | None) -> None:
    """Save an explicitly requested preview without reserving or executing work."""
    import execution_contract as c
    preview_out = getattr(args, 'preview_out', None)
    intent_out = getattr(args, 'intent_out', None)
    if intent_out is not None and submission is None:
        raise ValueError('--intent-out requires a prepared production run')
    if args.send and (preview_out is not None or intent_out is not None):
        raise ValueError('save preview files before selecting --send')
    destinations = [Path(value).absolute() for value in (preview_out, intent_out) if value is not None]
    if len(set(destinations)) != len(destinations):
        raise ValueError('preview and intent need distinct new files')
    for path in destinations:
        if path.exists():
            raise FileExistsError('preview destination already exists: ' + str(path))
    if preview_out is not None:
        c.atomic(Path(preview_out), c.encoded({'request_contract': rendered, 'validation': validation,
            'execution_ready': False, 'external_effect': False, 'budget_effect': 'none'}))
    if intent_out is not None:
        c.atomic(Path(intent_out), c.encoded(submission))


def require_submission(args: argparse.Namespace, production_run: str | None) -> None:
    """A send needs a prepared production run and the receipt of its exact authorization."""
    if args.send and (production_run is None or not getattr(args, "production_authorization", None)):
        raise ValueError("--send needs a prepared production run and --production-authorization with the receipt "
                         "of its exact authorization")


def open_run(root: Path) -> str | None:
    """The production run prepared for the studio's open task, which an upscale goes under."""
    import work_ledger
    return (work_ledger.read_current(root) or {}).get("production_run")


def read_package(path: Path) -> tuple[Path, dict[str, Any]]:
    package_path = path.resolve()
    if not package_path.is_file():
        raise ValueError(f"there is no Generation Package at {path}; check the path")
    return package_path, json.loads(package_path.read_text(encoding="utf-8"))


def dispatch_generation(args: argparse.Namespace, root: Path) -> int:
    package_path, package = read_package(args.package)
    studio.validate_recording_target(root, args.character, args.slot, writable=args.send)
    verified = verify(package, package_root=package_path.parent, project=root)
    from production_binding import validate_live
    binding = package.get("production_binding")
    production_run = binding["run"] if binding is not None else None
    validate_live(root if binding is not None else None, production_run, package)
    require_submission(args, production_run)
    from visual_continuity import require as require_visual
    require_visual(package["visual_continuity"], production_spec=package["production_spec"],
                   prepared=package["prepared_reference_set"], root=root,
                   recording_character=args.character, recording_slot=args.slot)
    # The companion holding the carriers the package names, so that every
    # iteration keeps a package that can still be read beside its references.
    companion_name = validate_generation_package_carrier_paths(
        package.get("prepared_reference_set") or {}, package_root=package_path.parent
    )
    companion = package_path.parent / companion_name if companion_name else None
    model_id, record = resolve_model_record(verified["model"])
    offering = select_offering(record, args.service)
    if offering is None:
        raise SystemExit(
            f"model record {model_id!r} is exposed on no service here; send the package by hand and record "
            "the result with scripts/studio.py iterate"
        )
    service_id, service, transport = service_for(offering, args.profiles, getattr(args, "pack_settings", None))
    check_request(verified, record, offering, model_id, transport, args.seed, args.count)
    import request_contract as rc
    import request_renderer
    import runtime_evidence
    rendered = request_renderer.generation(package, verified, record, offering, service, transport,
                                           seed=args.seed, count=args.count)
    reader = runtime_evidence.reader(root, snapshots=copy.deepcopy(package['input_snapshots']))
    validation = request_renderer.check_final(package['request_validation'], reader, rendered)
    preview = rendered['request']
    submission = None
    if production_run is not None:
        from production_workflow import submission_intent
        submission = submission_intent(package, rendered=rendered, seed=args.seed, count=args.count, offering=offering, service=service)
    write_preview_outputs(args, rendered, validation, submission)
    show_preview(model_id=model_id, offering=offering, service_id=service_id, service=service, rendered=rendered,
                 negative=negative_line(verified, rendered, offering), production_run=production_run,
                 review=verified.get("review_requirements") or [], args=args)
    if not args.send:
        return 0

    authorization = args.production_authorization
    key = api_key(service)
    with recorded_run(root, operation="generation", character=args.character, slot=args.slot,
                      service=service_id, transport=service.get("transport"), model=model_id,
                      production_run=production_run, expected=args.count,
                      note=args.note, offering=offering_summary(offering, model_id, record),
                      companion=companion.name if companion is not None else None) as run:
        stored_package = run.keep(package_path, "package.json")
        if companion is not None:
            run.keep(companion, companion.name)
        saved_package = json.loads(stored_package.read_text(encoding="utf-8"))
        if saved_package != package:
            raise ValueError("generation package changed while the dispatch snapshot was being saved")
        # Revalidate beside the saved carriers and upload those copies, not files
        # an author could change after the preflight. The durable package must
        # describe the same carrier bytes that actually leave this machine.
        saved_verified = verify(saved_package, package_root=run.path, project=root)
        saved_rendered = request_renderer.generation(saved_package, saved_verified, record, offering, service, transport,
                                                     seed=args.seed, count=args.count)
        if rc.receipt_projection(saved_rendered) != rc.receipt_projection(rendered):
            raise ValueError('request changed while saving its input snapshots')
        # Retain the preview's declared management identifiers as well as its semantic request.
        for field in saved_rendered['layout']['management']:
            rc.put(saved_rendered['request'], field, rc.get(rendered['request'], field))
        rc.validate_seal(saved_rendered)
        request_renderer.check_final(saved_package['request_validation'],
            runtime_evidence.reader(root, snapshots=copy.deepcopy(saved_package['input_snapshots'])), saved_rendered)
        run.write('request-contract.json', saved_rendered)
        from production_workflow import claim_dispatch
        claim = claim_dispatch(root, production_run, saved_package, saved_verified, run.path, submission, authorization, rendered=saved_rendered)
        run.write("preview.json", preview)
        run.update(status="uploading")
        import reservation_lifecycle
        media_ids = {}
        for index, item in enumerate(saved_rendered['media']):
            raw = Path(item['path']).read_bytes()
            if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('saved upload bytes differ from the sealed request')
            reservation_lifecycle.begin_step(root, production_run, authorization, claim=claim['sha256'],
                                             step=f'upload:{index}', operation='upload')
            media_ids[index] = transport.upload_bytes(raw, item['media_type'], service, key)
            run.write(f'upload-{index + 1:03d}.json', {'index': index, 'source': item['path'],
                      'source_sha256': item['sha256'], 'provider_id': media_ids[index]})
        request = rc.materialize(saved_rendered, media_ids)
        rc.validate_wire(saved_rendered, request, media_ids)
        run.write("request.json", request)
        run.update(status="sending")
        reservation_lifecycle.begin_step(root, production_run, authorization, claim=claim['sha256'], step='send', operation='send')
        answer = send_and_keep(run, transport, request, service, key)
        if answer is None:
            return 1
        refused = transport.rejections(answer)
        if refused:
            record_refusal(root, package_path.stem, request, refused, package=str(stored_package),
                           character=args.character, slot=args.slot, service=service_id)
        status = settle(root, run, acquire(run, transport), recovering=False)
        return report_outcome(root, run, status)


def suffix_of(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in (".png", ".jpg", ".jpeg", ".webp") else ".jpg"


def dispatch_upscale(args: argparse.Namespace, root: Path) -> int:
    studio.validate_recording_target(root, args.character, args.slot, writable=args.send)
    production_run = open_run(root)
    require_submission(args, production_run)
    source = args.source.resolve()
    if not source.is_file():
        raise SystemExit(f"{source} is not a file")
    model_id, record = resolve_model_record(args.model)
    if record.get("operation_kind") != "upscale":
        raise SystemExit(f"model record {model_id!r} is not an upscaler; a Generation Package goes without --upscale")
    supported = [float(value) for value in record.get("supported_scale_factors") or []]
    if float(args.scale) not in supported:
        raise SystemExit(f"scale {args.scale!r} is not one the record {model_id!r} declares: {supported}")
    settings = json.loads(args.settings)
    if not isinstance(settings, dict):
        raise SystemExit("--settings must be a JSON object")
    if args.guidance and record.get("supports_guidance_prompt") is not True:
        raise SystemExit(f"model {model_id!r} does not accept a guidance prompt")
    offering = select_offering(record, args.service)
    if offering is None:
        raise SystemExit(
            f"model record {model_id!r} is exposed on no service here; upscale by hand, build the package with "
            "scripts/build_upscale_package.py, and record the result with scripts/studio.py iterate"
        )
    require_guidance_key(offering, args.guidance)
    placed = mapped_settings(record, offering, settings)
    service_id, service, transport = service_for(offering, args.profiles, getattr(args, "pack_settings", None))
    from production_binding import upscale_request, validate_upscale_live
    from production_workflow import submission_intent, claim_dispatch
    import execution_contract as c
    import request_contract as rc
    import request_renderer
    import runtime_evidence
    validation_file = getattr(args, 'request_validation_file', None)
    if validation_file is None:
        raise ValueError('upscale requires an explicit --request-validation-file')
    declared = upscale_request(root, source, model_id, args.scale, settings, args.guidance,
                               request_validation=c.load(validation_file))
    if production_run is not None:
        validate_upscale_live(root, production_run, declared)
    rendered = request_renderer.upscale(declared, record, offering, service, transport, source, placed, root=root)
    check_upscale(rendered, offering, model_id)
    validation = request_renderer.check_final(declared['request_validation'],
        runtime_evidence.reader(root, snapshots=copy.deepcopy(declared['input_snapshots'])), rendered)
    preview = rendered['request']
    submission = None
    if production_run is not None:
        submission = submission_intent(declared, rendered=rendered, seed=None, count=1, offering=offering, service=service)
    write_preview_outputs(args, rendered, validation, submission)
    show_preview(model_id=model_id, offering=offering, service_id=service_id, service=service, rendered=rendered,
                 negative="none; an upscale takes no negative prompt", production_run=production_run,
                 review=[], args=args)
    if not args.send:
        return 0

    key = api_key(service)
    audit = "pending" if record.get("upscaler_class") in {"generative", "creative"} else "not-required"
    with recorded_run(root, operation="upscale", character=args.character, slot=args.slot,
                      service=service_id, transport=service.get("transport"), model=model_id,
                      production_run=production_run, expected=1,
                      note=args.note, offering=offering_summary(offering, model_id, record),
                      companion="upscale.references") as run:
        # Keep both images beside the package and copy them into the iteration
        # under the same relative companion path, so either copy is recoverable.
        companion = run.path / "upscale.references"
        companion.mkdir()
        staged_source = companion / f"source{source.suffix.lower()}"
        shutil.copyfile(source, staged_source)
        run.update(upscale={"source": staged_source.relative_to(run.path).as_posix(), "audit_status": audit})
        if c.digest(c.read(staged_source)) != declared['source']['sha256']:
            raise ValueError('upscale source changed while saving the dispatch snapshot')
        run.write('package.json', declared)
        saved_rendered = request_renderer.upscale(declared, record, offering, service, transport, staged_source, placed, root=root)
        if rc.receipt_projection(saved_rendered) != rc.receipt_projection(rendered):
            raise ValueError('upscale request changed while saving its input snapshot')
        for field in saved_rendered['layout']['management']:
            rc.put(saved_rendered['request'], field, rc.get(rendered['request'], field))
        rc.validate_seal(saved_rendered)
        request_renderer.check_final(declared['request_validation'],
            runtime_evidence.reader(root, snapshots=copy.deepcopy(declared['input_snapshots'])), saved_rendered)
        run.write('request-contract.json', saved_rendered)
        claim = claim_dispatch(root, production_run, declared, {}, run.path, submission, args.production_authorization,
                               rendered=saved_rendered)
        run.write("preview.json", preview)
        run.update(status="uploading")
        import reservation_lifecycle
        raw = staged_source.read_bytes()
        item = saved_rendered['media'][0]
        if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('upscale upload bytes differ from the sealed input')
        reservation_lifecycle.begin_step(root, production_run, args.production_authorization, claim=claim['sha256'], step='upload:0', operation='upload')
        media_ids = {0: transport.upload_bytes(raw, item['media_type'], service, key)}
        run.write('upload-001.json', {'index': 0, 'source': str(staged_source),
                  'source_sha256': item['sha256'], 'provider_id': media_ids[0]})
        request = rc.materialize(saved_rendered, media_ids)
        rc.validate_wire(saved_rendered, request, media_ids)
        run.write("request.json", request)
        run.update(status="sending")
        reservation_lifecycle.begin_step(root, production_run, args.production_authorization, claim=claim['sha256'], step='send', operation='send')
        answer = send_and_keep(run, transport, request, service, key)
        if answer is None:
            return 1
        refused = transport.rejections(answer)
        if refused:
            record_refusal(root, f"upscale-{source.stem}", request, refused, source=str(staged_source),
                           model=model_id, character=args.character, slot=args.slot, service=service_id)
        status = settle(root, run, acquire(run, transport), recovering=False)
        return report_outcome(root, run, status)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("package", type=Path, nargs="?", help="A verified Generation Package; absent with --upscale")
    parser.add_argument("--studio", type=Path, required=True, help="A directory in the studio the result belongs to")
    parser.add_argument("--character", required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--service", help="The service, when the model record is exposed on more than one")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--count", type=int, default=1, help="Results to ask for in one request")
    parser.add_argument("--note")
    parser.add_argument("--send", action="store_true", help="Send; without it, only show the request")
    parser.add_argument("--profiles", help="A service-profiles JSON file, instead of the active pack's")
    parser.add_argument("--upscale", action="store_true", help="Upscale one image with an upscaler record instead of sending a package")
    parser.add_argument("--model", help="With --upscale: the upscaler record")
    parser.add_argument("--source", type=Path, help="With --upscale: the image to enlarge")
    parser.add_argument("--scale", type=float, help="With --upscale: the factor, one the record declares")
    parser.add_argument("--settings", default="{}", help="With --upscale: JSON object of the settings the record declares")
    parser.add_argument("--guidance", help="With --upscale: a guidance prompt, where the record accepts one")
    parser.add_argument("--request-validation-file", type=Path, help="With --upscale: explicit validation record and evidence.")
    parser.add_argument('--preview-out', type=Path, help='New local file for the sealed request, its trace and the validation report; preview only.')
    parser.add_argument('--intent-out', type=Path, help='New local file for the exact submission intent to authorize; preview only.')
    add_pack_runtime_arguments(parser)
    parser.add_argument("--production-authorization", help="With --send: the receipt of the exact authorization of this request.")
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    args.pack_settings = runtime.settings
    try:
        root = studio.require_studio(args.studio)
        if args.upscale:
            if not (args.model and args.source and args.scale):
                parser.error("--upscale needs --model, --source, and --scale")
            return dispatch_upscale(args, root)
        if args.package is None:
            parser.error("a Generation Package, or --upscale")
        return dispatch_generation(args, root)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        # What the studio, the verifier and the record contract refuse is a
        # statement to the person running this, not a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
