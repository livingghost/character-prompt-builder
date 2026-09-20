#!/usr/bin/env python3
"""Send a verified Generation Package, or an upscale of one image, to the service its model record names, and record what came back in the studio.

Usage:
  python scripts/dispatch.py <generation-package.json> --studio DIR --character ID --slot SLOT
      [--service ID] [--seed N] [--count N] [--note "..."]        show the request, send nothing
  python scripts/dispatch.py ... --send                            send it and record every result

  python scripts/dispatch.py --upscale --model ID --source <image> --scale N [--settings '{...}']
      [--guidance "..."] --studio DIR --character ID --slot SLOT [--service ID] [--send]

A Generation Package is verified first, so what is sent is exactly the host
forwarding the verifier settled: the effective prompt, the negative on the
channel the record declares, the parameters, and the selected reference
transports. An upscale is checked against the upscaler record (the factor and
the settings it declares) and against the service's observed parameter schema,
with each setting placed on the request key the offering's `setting_keys` gives
it; the Upscale Package is built from the source and the returned image and
recorded with them.

The service-specific half is `transport_<service>.py` beside this file; the
service record (endpoint, auth, operations) is the `service-profiles` resource;
the per-model identifier and request keys are the model record's offering.

Every result is recorded as an iteration of the character by this script, with
the request as sent, the answer, the package, and the file, and the studio's
gallery is rewritten with it. Nothing is recorded by hand. Every sent run is
journaled under the studio's runs/ before upload. The exact
request, answer, package and downloaded images survive a later recording failure;
a refusal or an empty answer is retained too.

The dry run prints the exact request, so the user approves the thing that would
be sent rather than a description of it. No byte leaves the machine without
`--send`.
"""
from __future__ import annotations
from io_budget import environment_seconds

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import service_profile  # noqa: E402
import studio  # noqa: E402
from catalog_cli import configure_pack_runtime  # noqa: E402
from build_generation_payload import validate_generation_package_carrier_paths  # noqa: E402
from model_contract import generation_media_counts, select_offering, validate_generation_parameters  # noqa: E402
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime  # noqa: E402
from prepare_generation_references import model_pack_root, resolve_model_record  # noqa: E402
from upscale_package import build_upscale_package, validate_settings  # noqa: E402
from verify_generation_payload import verify  # noqa: E402


def stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_transport(service_id: str):
    try:
        return importlib.import_module(f"transport_{service_id.replace('-', '_')}")
    except ModuleNotFoundError:
        raise SystemExit(
            f"no transport for the service {service_id!r}. Write scripts/transport_{service_id}.py "
            "against the contract in transport_runware.py, or send by hand and record "
            "the result with scripts/studio.py iterate."
        )


def api_key(service: dict[str, Any]) -> str:
    """The credential, from the environment or the host's own configuration; never from a file of this suite."""
    variable = ((service.get("auth") or {}).get("env_var") or "").strip()
    if not variable:
        raise SystemExit("the service record names no auth.env_var")
    key = os.environ.get(variable, "").strip()
    if key:
        return key
    host = Path.home() / ".claude.json"
    if host.is_file():
        try:
            found = _find_env(json.loads(host.read_text(encoding="utf-8")), variable)
        except (OSError, json.JSONDecodeError):
            found = None
        if found:
            return found
    raise SystemExit(f"the credential is not in the environment. Set {variable} and run again.")


def _find_env(node: Any, variable: str) -> str | None:
    if isinstance(node, dict):
        value = node.get(variable)
        if isinstance(value, str) and value.strip():
            return value.strip()
        for child in node.values():
            found = _find_env(child, variable)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_env(child, variable)
            if found:
                return found
    return None


def save(url: str, destination: Path) -> str:
    with urllib.request.urlopen(url, timeout=environment_seconds("PRODUCTION_HTTP_TIMEOUT_SECONDS")) as response:
        data = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


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
    service_id = str(offering["service"])
    # The same runtime the model record came from: a record and the service it
    # names must not be read from two different sets of packs.
    profiles = service_profile.resolve_path(profiles_arg, state_file=None, cache_dir=None, managed_root=None,
                                            settings=settings)
    service = service_profile.load_service(service_id, profiles)
    print(f"service {service_id} at {(service.get('endpoint') or {}).get('base_url')} (record observed {service.get('observed_at')}, read from {profiles})")
    return service_id, service, load_transport(service_id)


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
    )


def record_refusal(root: Path, name: str, request: dict[str, Any], refused: list[dict[str, Any]], **facts: Any) -> Path:
    runs = root / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{name}-{request['taskUUID'][:8]}-refused.json"
    path.write_text(json.dumps({"at": stamp(), **facts, "submitted": request, "refused": refused}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    print(f"refused by the service: {json.dumps(refused, ensure_ascii=False)}")
    print(f"recorded {path}")
    return path


class RunJournal:
    """Durable local evidence, created before the first upload or paid request."""

    def __init__(self, root: Path, **facts: Any) -> None:
        from pack_manager import generate_uuid7
        self.path = root / "runs" / generate_uuid7()
        self.path.mkdir(parents=False, exist_ok=False)
        self.document: dict[str, Any] = {"at": stamp(), **facts, "status": "preparing", "iterations": []}
        self.update()

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
        self.document.update(facts, updated_at=stamp())
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
    journal = RunJournal(root, **facts)
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


def require_submission_context(args: argparse.Namespace, root: Path) -> None:
    if not args.send:
        return
    production_root = getattr(args, 'production_root', None)
    if production_root is None or not getattr(args, 'production_run', None) or not getattr(args, 'production_authorization', None):
        raise ValueError('submission requires production root, prepared run and exact authorization receipt')
    if production_root.resolve() != root.resolve():
        raise ValueError('production root must be the receiving Studio root')


def dispatch_generation(args: argparse.Namespace, root: Path) -> int:
    studio.validate_recording_target(root, args.character, args.slot, writable=args.send)
    require_submission_context(args, root)
    package_path = args.package.resolve()
    package = json.loads(package_path.read_text(encoding="utf-8"))
    verified = verify(package, package_root=package_path.parent)
    from production_binding import validate_live
    production_root = getattr(args, "production_root", None)
    production_run = getattr(args, "production_run", None)
    validate_live(production_root, production_run, package)
    if production_root is not None and production_root.resolve() != root.resolve():
        raise ValueError("production root must be the receiving Studio root")
    from adoption_workflow import validate_for_generation
    validate_for_generation(root, args.character, package)
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
    preview = transport.build(verified, offering, service, {}, args.seed, args.count)
    print(f"model {model_id} as {offering['model_identifier']} (offering observed {offering.get('observed_at')})")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    submission = None
    if production_run is not None:
        from production_workflow import submission_intent
        submission = submission_intent(package, seed=args.seed, count=args.count, offering=offering, service=service)
        print("production submission intent (not permission):")
        print(json.dumps(submission, ensure_ascii=False, indent=2))
    if not args.send:
        print("shown, not sent. Add --send once the user has approved this request.")
        return 0

    authorization = getattr(args, "production_authorization", None)
    if production_run is None or not authorization:
        raise ValueError("submission requires a prepared production run and exact authorization receipt")
    key = api_key(service)
    with recorded_run(root, operation="generation", character=args.character, slot=args.slot,
                      service=service_id, model=model_id) as run:
        stored_package = run.keep(package_path, "package.json")
        stored_companion = run.keep(companion, companion.name) if companion is not None else None
        saved_package = json.loads(stored_package.read_text(encoding="utf-8"))
        if saved_package != package:
            raise ValueError("generation package changed while the dispatch snapshot was being saved")
        # Revalidate beside the saved carriers and upload those copies, not files
        # an author could change after the preflight. The durable package must
        # describe the same carrier bytes that actually leave this machine.
        saved_verified = verify(saved_package, package_root=run.path)
        if production_run is not None:
            from production_workflow import claim_dispatch
            claim_dispatch(root, production_run, saved_package, saved_verified, run.path, submission, authorization)
        run.write("preview.json", preview)
        run.update(status="uploading")
        media_ids = {path: transport.upload(path, service, key) for path in transport.media_paths(saved_verified)}
        request = transport.build(saved_verified, offering, service, media_ids, args.seed, args.count)
        request_path = run.write("request.json", request)
        run.update(status="sending")
        answer = transport.send(request, service, key)
        run.write("answer.json", answer)
        run.update(status="answered")
        refused = transport.rejections(answer)
        if refused:
            run.update(status="refused", refused=refused)
            record_refusal(root, package_path.stem, request, refused, package=str(stored_package),
                           character=args.character, slot=args.slot, service=service_id)
            return 1
        recorded = []
        acquired = []
        entries = [entry for entry in transport.results(answer) if entry.get("url")]
        if production_run is not None and len(entries) != args.count:
            run.update(status="response-count-mismatch", expected=args.count, received=len(entries))
            raise ValueError("returned output count differs from the authorized count")
        for index, entry in enumerate(entries):
            response_path = run.write(f"response-{index + 1}.json", {
                "at": stamp(), "seed": entry.get("seed"), "id": entry.get("id"),
                "url": entry["url"], "answer": answer,
            })
            result_path = run.path / f"result-{index + 1}{suffix_of(entry['url'])}"
            run.update(status="downloading")
            save(entry["url"], result_path)
            acquired.append((result_path, response_path))
        if production_run is not None:
            from production_workflow import record_dispatch_results
            record_dispatch_results(root, production_run, saved_package, run.path,
                                    [p for p, _ in acquired], args.count)
        for result_path, response_path in acquired:
            run.update(status="recording")
            row = studio.iterate(root, args.character, args.slot, result_path, package=stored_package,
                                 request=request_path, response=response_path, note=args.note,
                                 service=offering_summary(offering, model_id, record),
                                 package_companion=stored_companion)
            recorded.append(row["iteration_id"])
            run.update(iterations=list(recorded))
            print(f"  recorded {row['iteration_id']} seed {row.get('seed')} -> {row['result']['path']}")
        run.update(status="complete" if recorded else "no-results")
        if not recorded:
            print(f"the service answered with no result file; answer retained in {run.path}")
            return 1
    return 0


def suffix_of(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in (".png", ".jpg", ".jpeg", ".webp") else ".jpg"


def dispatch_upscale(args: argparse.Namespace, root: Path) -> int:
    studio.validate_recording_target(root, args.character, args.slot, writable=args.send)
    require_submission_context(args, root)
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
    guidance = require_guidance_key(offering, args.guidance)
    placed = mapped_settings(record, offering, settings)
    # The request the service will see, against its observed schema, before anything is uploaded.
    validate_generation_parameters(record, {"upscaleFactor": int(args.scale) if float(args.scale).is_integer() else args.scale, "outputFormat": "PNG", **placed,
                                            **({guidance: args.guidance} if guidance and args.guidance else {})},
                                   service=offering["service"], pack_root=model_pack_root(model_id),
                                   media_counts={"input image": 1})
    service_id, service, transport = service_for(offering, args.profiles, getattr(args, "pack_settings", None))
    preview = transport.build_upscale(offering["model_identifier"], str(source), args.scale, placed, offering, service, {}, args.guidance)
    print(f"model {model_id} as {offering['model_identifier']} (offering observed {offering.get('observed_at')})")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if getattr(args, 'production_run', None):
        from production_binding import upscale_request, validate_upscale_live
        from production_workflow import submission_intent
        declared = upscale_request(root, source, model_id, args.scale, settings, args.guidance)
        validate_upscale_live(root, args.production_run, declared)
        print('production submission intent (not permission):')
        print(json.dumps(submission_intent(declared, seed=None, count=1, offering=offering, service=service), indent=2))
    if not args.send:
        print("shown, not sent. Add --send once the user has approved this request.")
        return 0

    from production_binding import upscale_request, validate_upscale_live
    from production_workflow import submission_intent, claim_dispatch, record_dispatch_results
    production_run = args.production_run
    declared = upscale_request(root, source, model_id, args.scale, settings, args.guidance)
    validate_upscale_live(root, production_run, declared)
    submission = submission_intent(declared, seed=None, count=1, offering=offering, service=service)
    key = api_key(service)
    with recorded_run(root, operation="upscale", character=args.character, slot=args.slot,
                      service=service_id, model=model_id) as run:
        # Keep both images beside the package and copy them into the iteration
        # under the same relative companion path, so either copy is recoverable.
        companion = run.path / "upscale.references"
        companion.mkdir()
        staged_source = companion / f"source{source.suffix.lower()}"
        shutil.copyfile(source, staged_source)
        from execution_contract import digest, read
        if digest(read(staged_source)) != declared['source']['sha256']:
            raise ValueError('upscale source changed while saving the dispatch snapshot')
        run.write('package.json', declared)
        claim_dispatch(root, production_run, declared, {}, run.path, submission, args.production_authorization)
        run.write("preview.json", preview)
        run.update(status="uploading")
        media_ids = {str(source): transport.upload(str(staged_source), service, key)}
        request = transport.build_upscale(offering["model_identifier"], str(source), args.scale,
                                          placed, offering, service, media_ids, args.guidance)
        request_path = run.write("request.json", request)
        run.update(status="sending")
        answer = transport.send(request, service, key)
        run.write("answer.json", answer)
        run.update(status="answered")
        refused = transport.rejections(answer)
        if refused:
            run.update(status="refused", refused=refused)
            record_refusal(root, f"upscale-{source.stem}", request, refused, source=str(staged_source),
                           model=model_id, character=args.character, slot=args.slot, service=service_id)
            return 1
        entries = [entry for entry in transport.results(answer) if entry.get("url")]
        if len(entries) != 1:
            run.update(status="response-count-mismatch", expected=1, received=len(entries))
            raise ValueError('upscale returned output count differs from the authorized count')
        recorded = []
        required = record.get("upscaler_class") in {"generative", "creative"}
        for index, entry in enumerate(entries, 1):
            response_path = run.write(f"response-{index}.json", {
                "at": stamp(), "seed": entry.get("seed"), "id": entry.get("id"),
                "url": entry["url"], "answer": answer,
            })
            output = companion / f"output-{index}{suffix_of(entry['url'])}"
            run.update(status="downloading")
            save(entry["url"], output)
            run.update(status="building-package")
            package = build_upscale_package(
                model=model_id, source_image=staged_source, output_image=output, package_root=run.path,
                source_stored_path=staged_source.relative_to(run.path).as_posix(),
                output_stored_path=output.relative_to(run.path).as_posix(), scale_factor=float(args.scale),
                settings=settings, guidance_prompt=args.guidance, audit_status="pending" if required else "not-required",
                audit_notes=[],
            )
            package_path = run.write(f"upscale-package-{index}.json", package)
            record_dispatch_results(root, production_run, declared, run.path, [output], 1)
            run.update(status="recording")
            row = studio.iterate(root, args.character, args.slot, output, package=package_path,
                                 request=request_path, response=response_path, note=args.note,
                                 service=offering_summary(offering, model_id, record), package_companion=companion)
            recorded.append(row["iteration_id"])
            run.update(iterations=list(recorded))
            print(f"  recorded {row['iteration_id']} -> {row['result']['path']} ({'identity audit pending' if required else 'ready'})")
        run.update(status="complete")
    return 0


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
    add_pack_runtime_arguments(parser)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--production-run")
    parser.add_argument("--production-authorization", help="Exact submit authorization receipt for a bound production run.")
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
    raise SystemExit(main())
