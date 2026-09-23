#!/usr/bin/env python3
"""Build and verify Character Prompt Builder batch generation plans.

A batch is several model-facing generation inputs dispatched at once:
several variants of one model concurrently, or several models through
their endpoints at the same time. Dispatch is grouped per transport, the
configured endpoint a job's variants are sent through, because separate
endpoint configurations cannot share one concurrent block. The batch
layer only organizes dispatch and review. Every job still forwards its
own verified Generation Package through the selected adapter exactly as
the Image Generation Runtime requires.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from execution_contract import sha256_file

RESULT_STATUSES = ("accepted", "rejected", "pending", "failed")


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _load_json_file(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be an existing regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{label} is not readable UTF-8 JSON: {exc}") from exc


def _validate_job(index: int, raw: Any, root: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"job {index} must be a JSON object")
    job_id = _require_string(raw.get("job_id"), f"job {index} job_id")
    target_model = _require_string(raw.get("target_model"), f"job {job_id} target_model")
    package_relative = _require_string(
        raw.get("generation_package"), f"job {job_id} generation_package"
    )
    package_path = Path(package_relative)
    if package_path.is_absolute():
        raise ValueError(
            f"job {job_id} generation_package must be a relative path: {package_relative}"
        )
    # Reject parent references outright, then walk every component on the
    # unresolved path: resolve() follows symlinks, so only the raw path can
    # reveal a symlinked directory, not just a symlinked final entry. The
    # containment check stays as defense in depth behind those two rejections.
    if any(part == ".." for part in package_path.parts):
        raise ValueError(
            f"job {job_id} generation_package must not contain parent references: {package_relative}"
        )
    current = root
    for part in package_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(
                f"job {job_id} generation_package must not be a symbolic link: {package_relative}"
            )
    resolved = (root / package_path).resolve()
    if not resolved.is_file():
        raise ValueError(
            f"job {job_id} generation_package must be an existing regular file: {package_relative}"
        )
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(
            f"job {job_id} generation_package must stay inside the jobs directory: {package_relative}"
        )
    count = raw.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError(f"job {job_id} count must be a positive integer")
    seeds = raw.get("seeds")
    if seeds is not None:
        if not isinstance(seeds, list) or len(seeds) != count:
            raise ValueError(f"job {job_id} seeds must be a list with one seed per variant ({count})")
        for seed in seeds:
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                raise ValueError(f"job {job_id} seeds must be nonnegative integers")
    parameters = raw.get("parameters")
    if parameters is not None and not isinstance(parameters, dict):
        raise ValueError(f"job {job_id} parameters must be a JSON object")
    note = raw.get("note")
    if note is not None:
        note = _require_string(note, f"job {job_id} note")
    transport = raw.get("transport")
    if transport is not None:
        transport = _require_string(transport, f"job {job_id} transport")
    return {
        "job_id": job_id,
        "target_model": target_model,
        "transport": transport if transport is not None else "default",
        "generation_package": package_relative,
        "generation_package_sha256": sha256_file(resolved),
        "count": count,
        "parameters": parameters if parameters is not None else {},
        "seeds": seeds,
        "note": note,
    }


def build_batch_plan(jobs_document: Any, root: Path) -> dict[str, Any]:
    """Validate the authored job list and expand it into dispatchable variants."""
    if not isinstance(jobs_document, dict):
        raise ValueError("batch jobs must be a JSON object")
    raw_jobs = jobs_document.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise ValueError("batch jobs must be a nonempty list")
    label = jobs_document.get("label")
    if label is not None:
        label = _require_string(label, "batch label")
    seen: set[str] = set()
    jobs = []
    for index, raw in enumerate(raw_jobs):
        job = _validate_job(index, raw, root)
        if job["job_id"] in seen:
            raise ValueError(f"duplicate job_id: {job['job_id']}")
        seen.add(job["job_id"])
        jobs.append(job)
    variants = []
    for job in jobs:
        for position in range(1, job["count"] + 1):
            seed = None
            if job["seeds"] is not None:
                seed = job["seeds"][position - 1]
            variants.append(
                {
                    "variant_id": f"{job['job_id']}#v{position:02d}",
                    "job_id": job["job_id"],
                    "target_model": job["target_model"],
                    "transport": job["transport"],
                    "generation_package": job["generation_package"],
                    "generation_package_sha256": job["generation_package_sha256"],
                    "parameters": copy.deepcopy(job["parameters"]),
                    "seed": seed,
                    "note": job["note"],
                }
            )
    endpoint_models: dict[str, dict[str, list[str]]] = {}
    for variant in variants:
        endpoint_models.setdefault(variant["transport"], {}).setdefault(
            variant["target_model"], []
        ).append(variant["variant_id"])
    return {
        "label": label,
        "jobs": jobs,
        "variants": variants,
        "dispatch": {
            "variant_count": len(variants),
            "endpoint_groups": [
                {
                    "transport": transport,
                    "models": {
                        model: endpoint_models[transport][model]
                        for model in sorted(endpoint_models[transport])
                    },
                }
                for transport in sorted(endpoint_models)
            ],
        },
    }


def _validate_result_entry(variant_id: str, raw: Any, root: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"result {variant_id} must be a JSON object")
    status = raw.get("status")
    if status not in RESULT_STATUSES:
        raise ValueError(
            f"result {variant_id} status must be one of: {', '.join(RESULT_STATUSES)}"
        )
    note = raw.get("note")
    if note is not None:
        note = _require_string(note, f"result {variant_id} note")
    entry: dict[str, Any] = {"status": status, "note": note}
    if status == "failed":
        entry["error"] = _require_string(raw.get("error"), f"result {variant_id} error")
        return entry
    image_relative = _require_string(raw.get("image_path"), f"result {variant_id} image_path")
    image_path = Path(image_relative)
    if image_path.is_absolute():
        raise ValueError(f"result {variant_id} image_path must be a relative path: {image_relative}")
    if any(part == ".." for part in image_path.parts):
        raise ValueError(
            f"result {variant_id} image_path must not contain parent references: {image_relative}"
        )
    current = root
    for part in image_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(
                f"result {variant_id} image_path must not be a symbolic link: {image_relative}"
            )
    resolved = (root / image_path).resolve()
    if not resolved.is_file():
        raise ValueError(
            f"result {variant_id} image_path must be an existing regular file: {image_relative}"
        )
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(
            f"result {variant_id} image_path must stay inside the results directory: {image_relative}"
        )
    if resolved.stat().st_size == 0:
        raise ValueError(f"result {variant_id} image file is empty: {image_relative}")
    entry["image_path"] = image_relative
    entry["image_sha256"] = sha256_file(resolved)
    return entry


def build_batch_ledger(
    plan: Any, results_document: Any, plan_path: Path, results_root: Path
) -> dict[str, Any]:
    """Validate dispatched results against the batch plan and emit a review ledger."""
    planned = plan.get("variants") if isinstance(plan, dict) else None
    if not isinstance(planned, list) or not planned:
        raise ValueError("batch plan has no variants")
    planned_jobs = plan.get("jobs") if isinstance(plan, dict) else None
    if not isinstance(planned_jobs, list) or not planned_jobs:
        raise ValueError("batch plan has no jobs")
    job_ids: set[str] = set()
    jobs_by_id: dict[str, dict[str, Any]] = {}
    for index, job in enumerate(planned_jobs):
        if not isinstance(job, dict):
            raise ValueError(f"batch plan job {index} must be a JSON object")
        job_id = job.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError(f"batch plan job {index} has no job_id")
        if job_id in job_ids:
            raise ValueError(f"batch plan contains a duplicate job_id: {job_id}")
        if not isinstance(job.get("target_model"), str) or not job["target_model"].strip():
            raise ValueError(f"batch plan job {job_id} has no target_model")
        count = job.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"batch plan job {job_id} has no positive variant count")
        parameters = job.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError(f"batch plan job {job_id} parameters must be a JSON object")
        seeds = job.get("seeds")
        if seeds is not None:
            if not isinstance(seeds, list) or len(seeds) != count:
                raise ValueError(
                    f"batch plan job {job_id} seeds must contain one seed per variant"
                )
            if any(
                not isinstance(seed, int) or isinstance(seed, bool) or seed < 0
                for seed in seeds
            ):
                raise ValueError(
                    f"batch plan job {job_id} seeds must be nonnegative integers"
                )
        note = job.get("note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            raise ValueError(f"batch plan job {job_id} note must be a nonempty string or null")
        for field in ("transport", "generation_package"):
            value = job.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"batch plan job {job_id} has no {field}")
        package_sha = job.get("generation_package_sha256")
        if not isinstance(package_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", package_sha):
            raise ValueError(
                f"batch plan job {job_id} generation_package_sha256 must be 64 hexadecimal characters"
            )
        # The plan side hashed this package at build time. Recording results
        # against a package that was swapped, moved, or deleted would attach
        # those results to a provenance hash matching nothing on disk, which
        # is exactly the tamper class the hash exists to prevent. Re-derive
        # the hash from the file itself, under the same path-safety rule the
        # builder used.
        package_relative = job.get("generation_package")
        package_path = Path(package_relative)
        if package_path.is_absolute() or any(part == ".." for part in package_path.parts):
            raise ValueError(
                f"batch plan job {job_id} generation_package must be a safe relative path: "
                f"{package_relative}"
            )
        package_current = plan_path.resolve().parent
        for part in package_path.parts:
            package_current = package_current / part
            if package_current.is_symlink():
                raise ValueError(
                    f"batch plan job {job_id} generation_package must not be a symbolic link: "
                    f"{package_relative}"
                )
        package_resolved = (plan_path.resolve().parent / package_path).resolve()
        if not package_resolved.is_file() or not package_resolved.is_relative_to(
            plan_path.resolve().parent.resolve()
        ):
            raise ValueError(
                f"batch plan job {job_id} generation_package is missing or outside the "
                f"plan directory: {package_relative}; replan the batch before recording"
            )
        package_actual_sha = sha256_file(package_resolved)
        if package_actual_sha != package_sha:
            raise ValueError(
                f"batch plan job {job_id} generation_package content no longer matches its "
                f"recorded generation_package_sha256 (expected {package_sha}, found "
                f"{package_actual_sha}); replan the batch before recording results"
            )
        job_ids.add(job_id)
        jobs_by_id[job_id] = job
    planned_ids: list[str] = []
    variants_by_job: dict[str, list[dict[str, Any]]] = {}
    for index, variant in enumerate(planned):
        if not isinstance(variant, dict):
            raise ValueError(f"batch plan variant {index} must be a JSON object")
        variant_id = variant.get("variant_id")
        if not isinstance(variant_id, str) or not variant_id.strip():
            raise ValueError(f"batch plan variant {index} has no variant_id")
        if variant_id in planned_ids:
            raise ValueError(f"batch plan contains a duplicate variant_id: {variant_id}")
        # Every planned variant must belong to a listed job. The ledger groups
        # by job, so a variant whose job_id has no matching job would otherwise
        # be silently dropped from both the ledger body and the summary counts.
        # The builder also copies the fields below from the owning job, so a
        # mismatch means the plan was hand-edited and would misattribute
        # results to another model's dispatch block.
        variant_job_id = variant.get("job_id")
        if not isinstance(variant_job_id, str) or variant_job_id not in job_ids:
            raise ValueError(
                f"batch plan variant {variant_id} references an unknown job_id: {variant_job_id!r}"
            )
        job = jobs_by_id[variant_job_id]
        for field in (
            "target_model",
            "transport",
            "generation_package",
            "generation_package_sha256",
            "parameters",
            "note",
        ):
            if variant.get(field) != job.get(field):
                raise ValueError(
                    f"batch plan variant {variant_id} {field} does not match job {variant_job_id}"
                )
        position_match = re.fullmatch(re.escape(variant_job_id) + r"#v(\d+)", variant_id)
        position = int(position_match.group(1)) - 1 if position_match else -1
        expected_seed = (
            job["seeds"][position]
            if job.get("seeds") is not None and 0 <= position < job["count"]
            else None
        )
        if variant.get("seed") != expected_seed:
            raise ValueError(
                f"batch plan variant {variant_id} seed does not match job {variant_job_id}"
            )
        planned_ids.append(variant_id)
        variants_by_job.setdefault(variant_job_id, []).append(variant)
    # A variant's id embeds its owning job, so each job must own exactly the
    # ids the builder would have expanded for it. This closes the last hole a
    # hand edit can open: moving a variant to another job along with that
    # job's copied metadata reconciles field by field, but leaves the source
    # job short and the target job over-full, which the count check catches.
    for job_id, job in jobs_by_id.items():
        count = job["count"]
        expected = {f"{job_id}#v{position:02d}" for position in range(1, count + 1)}
        owned = {variant["variant_id"] for variant in variants_by_job.get(job_id, [])}
        if owned != expected:
            raise ValueError(
                f"batch plan job {job_id} must own exactly its expanded variants "
                f"(expected {count}, found {len(owned)})"
            )
    # The dispatch block summarises how the plan was handed to the endpoints.
    # It is generated alongside the variants, so a hand edit that changed the
    # variants without regenerating it leaves results recorded against
    # dispatch metadata that no longer describes them.
    dispatch = plan.get("dispatch") if isinstance(plan, dict) else None
    if not isinstance(dispatch, dict):
        raise ValueError("batch plan has no dispatch block")
    dispatch_count = dispatch.get("variant_count")
    if not isinstance(dispatch_count, int) or isinstance(dispatch_count, bool):
        raise ValueError("batch plan dispatch.variant_count must be an integer")
    if dispatch_count != len(planned_ids):
        raise ValueError(
            f"batch plan dispatch.variant_count ({dispatch_count}) does not match the "
            f"plan variants ({len(planned_ids)}); replan the batch before recording results"
        )
    groups = dispatch.get("endpoint_groups")
    if not isinstance(groups, list):
        raise ValueError("batch plan dispatch.endpoint_groups must be a list")
    planned_transport_variants: dict[str, set[str]] = {}
    for variant in planned:
        transport = jobs_by_id[variant["job_id"]]["transport"]
        planned_transport_variants.setdefault(transport, set()).add(variant["variant_id"])
    group_transports: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError(
                "batch plan dispatch.endpoint_groups entries must be JSON objects"
            )
        transport = group.get("transport")
        if not isinstance(transport, str) or not transport:
            raise ValueError("batch plan dispatch endpoint group has no transport")
        if transport in group_transports:
            raise ValueError(
                f"batch plan dispatch has duplicate endpoint groups for transport {transport}"
            )
        group_transports.add(transport)
        if transport not in planned_transport_variants:
            raise ValueError(
                f"batch plan dispatch declares a transport no job uses: {transport}"
            )
        models = group.get("models")
        if not isinstance(models, dict) or not models:
            raise ValueError(f"batch plan dispatch group {transport} has no models")
        group_variants: set[str] = set()
        for model, variant_ids in models.items():
            if not isinstance(variant_ids, list) or not variant_ids:
                raise ValueError(
                    f"batch plan dispatch group {transport} model {model} has no variant list"
                )
            group_variants.update(variant_ids)
        if group_variants != planned_transport_variants[transport]:
            raise ValueError(
                f"batch plan dispatch group {transport} does not list exactly the plan "
                "variants for that transport"
            )
    if group_transports != set(planned_transport_variants):
        raise ValueError(
            "batch plan dispatch.endpoint_groups must cover exactly the transports its jobs use"
        )
    if not isinstance(results_document, dict) or not isinstance(
        results_document.get("variants"), dict
    ):
        raise ValueError("batch results must be a JSON object with a variants object")
    reported = results_document["variants"]
    missing = [variant_id for variant_id in planned_ids if variant_id not in reported]
    if missing:
        raise ValueError("batch results are incomplete; missing variants: " + ", ".join(missing))
    unknown = sorted(set(reported) - set(planned_ids))
    if unknown:
        raise ValueError("batch results contain unknown variants: " + ", ".join(unknown))
    results_by_id = {
        variant_id: _validate_result_entry(variant_id, reported[variant_id], results_root)
        for variant_id in planned_ids
    }
    summary = {"variant_count": len(planned_ids), "accepted": 0, "rejected": 0, "pending": 0, "failed": 0}
    jobs_ledger = []
    for job in plan["jobs"]:
        job_variants = []
        for variant in planned:
            if variant["job_id"] != job["job_id"]:
                continue
            variant_id = variant["variant_id"]
            summary[results_by_id[variant_id]["status"]] += 1
            job_variants.append(
                {
                    "variant_id": variant_id,
                    "seed": variant.get("seed"),
                    "result": results_by_id[variant_id],
                }
            )
        jobs_ledger.append(
            {
                "job_id": job.get("job_id"),
                "target_model": job.get("target_model"),
                "variants": job_variants,
            }
        )
    return {
        "label": plan.get("label"),
        "batch_plan_sha256": sha256_file(plan_path),
        "summary": summary,
        "jobs": jobs_ledger,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan_parser = commands.add_parser(
        "plan", help="validate an authored batch job list and expand dispatch variants"
    )
    plan_parser.add_argument("--jobs", type=Path, required=True, help="authored batch jobs JSON")
    plan_parser.add_argument("--out", type=Path, required=True, help="output batch plan JSON")

    record_parser = commands.add_parser(
        "record", help="validate dispatched results against a batch plan and emit a ledger"
    )
    record_parser.add_argument("--plan", type=Path, required=True, help="batch plan JSON")
    record_parser.add_argument("--results", type=Path, required=True, help="dispatched results JSON")
    record_parser.add_argument("--out", type=Path, required=True, help="output batch ledger JSON")

    args = parser.parse_args(argv)
    if args.command == "plan":
        document = _load_json_file(args.jobs, "--jobs")
        plan = build_batch_plan(document, args.jobs.resolve().parent)
        args.out.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "job_count": len(plan["jobs"]),
                    "variant_count": plan["dispatch"]["variant_count"],
                    "endpoints": [
                        group["transport"] for group in plan["dispatch"]["endpoint_groups"]
                    ],
                    "out": str(args.out),
                }
            )
        )
        return 0
    plan_document = _load_json_file(args.plan, "--plan")
    results_document = _load_json_file(args.results, "--results")
    ledger = build_batch_ledger(
        plan_document, results_document, args.plan, args.results.resolve().parent
    )
    args.out.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"ok": True, "summary": ledger["summary"], "out": str(args.out)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
