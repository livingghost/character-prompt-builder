#!/usr/bin/env python3
"""Retrieval-quality regression suite.

Asserts not merely that searches return results, but that known-irrelevant
records stay out of the strong band and known-correct records remain reachable.
Cases come from the active pack's ``catalog-search-regression`` named resource,
so review findings remain owned by and evaluated with the catalog they target.

The catalog is intentionally large. The default execution path loads it once
and evaluates small bounded case ranges while clearing query-corpus state after
each case. An explicit isolated diagnostic mode runs the same ranges in fresh
worker processes when process-lifetime behavior itself needs examination.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from catalog_cli import (  # noqa: E402
    clear_corpus_cache,
    configure_pack_runtime,
    inspire,
    load_entries,
    named_resource_path,
    search_entries,
)
from pack_runtime_cli import (  # noqa: E402
    PackRuntimeContext,
    add_pack_runtime_arguments,
    resolve_pack_runtime,
)

DEFAULT_KINDS = {
    "module", "profile", "aesthetic-core", "style-family", "domain-realization",
    "scene", "archetype", "correction",
}
# Cases per isolated worker. Chunking bounds process startup and per-chunk
# retention; the assertions are per case, so no result depends on where the
# boundaries fall and any positive value is correct. --chunk-size overrides it.
DEFAULT_CHUNK_SIZE = 20
# One worker, because SKILL.md forbids running several catalog processes at
# once: they contend for the one cache lock. --max-workers overrides it for a
# caller that has isolated the state and cache.
DEFAULT_MAX_WORKERS = 1
DEFAULT_EXECUTION_MODE = "in-process"
SEARCH_REGRESSION_RESOURCE = "catalog-search-regression"


def load_spec() -> dict[str, Any]:
    path = named_resource_path(SEARCH_REGRESSION_RESOURCE)
    assert path is not None
    return json.loads(path.read_text(encoding="utf-8"))


def _positive_expected_ids(case: dict[str, Any]) -> set[str]:
    """Return the canonical IDs a case requires the active catalog to supply."""
    checks = case.get("assert") or {}
    required: set[str] = set()
    for key in (
        "must_strong",
        "must_include",
        "core_includes",
        "style_family_includes",
        "realization_includes",
        "profile_includes",
    ):
        required.update(str(item) for item in checks.get(key, []))
    for key in (
        "top",
        "core_top",
        "style_family_top",
        "realization_top",
        "profile_top",
    ):
        if checks.get(key):
            required.add(str(checks[key]))
    for values in checks.get("category_includes", {}).values():
        required.update(str(item) for item in values)
    alternatives = {str(item) for item in checks.get("top_includes_any", [])}
    if len(alternatives) == 1:
        required.update(alternatives)
    return required


def _missing_expected_ids(
    entries: Sequence[Any],
    cases: Sequence[dict[str, Any]],
) -> dict[str, list[str]]:
    available = {str(entry.record["id"]) for entry in entries}
    missing: dict[str, list[str]] = {}
    for case in cases:
        absent = sorted(_positive_expected_ids(case) - available)
        alternatives = {
            str(item) for item in (case.get("assert") or {}).get("top_includes_any", [])
        }
        if alternatives and not (alternatives & available):
            absent.extend(sorted(alternatives - set(absent)))
        if absent:
            missing[str(case.get("name") or "unnamed")] = absent
    return missing


def run_cases(entries: Sequence[Any], cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate one bounded case range in the current process.

    Reuse immutable indexed-entry views, while clearing query-corpus state
    after every case. Some adjacent cases share a large eligible subset but
    exercise very different phrase and facet routes; retaining that corpus
    across the whole range can accumulate enough query state to make release
    validation stall. Per-case clearing preserves deterministic assertions and
    keeps the reusable content-derived entry index warm.
    """
    missing_expected_ids = _missing_expected_ids(entries, cases)
    failures: list[str] = [
        f"{name}: active catalog is missing expected IDs {record_ids}"
        for name, record_ids in missing_expected_ids.items()
    ]
    clear_corpus_cache()
    for case in cases:
        name = case["name"]
        checks = case["assert"]
        if case["mode"] == "search":
            hits = search_entries(
                entries,
                case["query"],
                kinds=set(case.get("kinds") or DEFAULT_KINDS),
                categories=set(case.get("categories") or []),
                domain=case.get("domain"),
                limit=int(case.get("limit", 10)),
                diverse=False,
                tier=case.get("tier"),
            )
            strong = {hit["id"] for hit in hits if hit.get("relevance") == "strong"}
            ids = [hit["id"] for hit in hits]
            if checks.get("no_strong") and strong:
                failures.append(f"{name}: expected no strong results, got {sorted(strong)}")
            for record_id in checks.get("must_strong", []):
                if record_id not in strong:
                    failures.append(f"{name}: {record_id} should be strong")
            for record_id in checks.get("must_not_strong", []):
                if record_id in strong:
                    failures.append(f"{name}: {record_id} must not be strong")
            for record_id in checks.get("must_include", []):
                if record_id not in ids:
                    failures.append(f"{name}: {record_id} should be returned, got {ids}")
            for record_id in checks.get("must_not_include", []):
                if record_id in ids:
                    failures.append(f"{name}: {record_id} must not be returned")
            if "top" in checks and (not ids or ids[0] != checks["top"]):
                failures.append(f"{name}: top should be {checks['top']}, got {ids[:1]}")
            if "top_includes_any" in checks and not set(checks["top_includes_any"]) & set(ids[:3]):
                failures.append(
                    f"{name}: top-3 should include one of {checks['top_includes_any']}, got {ids[:3]}"
                )
            clear_corpus_cache()
            continue

        result = inspire(
            entries,
            case["query"],
            case.get("categories", []),
            case.get("domain"),
            int(case.get("per_category", 4)),
            case.get("tier"),
            int(case.get("profiles", 3)),
            int(case.get("cores", 3)),
            int(case.get("style_families", 3)),
            int(case.get("realizations", 2)),
        )
        categories = result["categories"]
        profile_ids = [item["id"] for item in result.get("render_profiles", [])]
        core_ids = [item["id"] for item in result.get("aesthetic_cores", [])]
        style_family_ids = [item["id"] for item in result.get("style_families", [])]
        realization_ids = [item["id"] for item in result.get("domain_realizations", [])]

        for record_id in checks.get("core_includes", []):
            if record_id not in core_ids:
                failures.append(f"{name}: aesthetic_cores should include {record_id}, got {core_ids}")
        if "core_top" in checks and (not core_ids or core_ids[0] != checks["core_top"]):
            failures.append(f"{name}: aesthetic core top should be {checks['core_top']}, got {core_ids[:1]}")

        for record_id in checks.get("style_family_includes", []):
            if record_id not in style_family_ids:
                failures.append(f"{name}: style_families should include {record_id}, got {style_family_ids}")
        if "style_family_top" in checks and (
            not style_family_ids or style_family_ids[0] != checks["style_family_top"]
        ):
            failures.append(
                f"{name}: style family top should be {checks['style_family_top']}, got {style_family_ids[:1]}"
            )

        for record_id in checks.get("realization_includes", []):
            if record_id not in realization_ids:
                failures.append(
                    f"{name}: domain_realizations should include {record_id}, got {realization_ids}"
                )
        if "realization_top" in checks and (
            not realization_ids or realization_ids[0] != checks["realization_top"]
        ):
            failures.append(
                f"{name}: domain realization top should be {checks['realization_top']}, got {realization_ids[:1]}"
            )
        if checks.get("realization_exact_domain"):
            expected = case.get("domain")
            wrong = [
                item for item in result.get("domain_realizations", [])
                if item.get("subject_domain") != expected
            ]
            if wrong:
                failures.append(
                    f"{name}: domain realizations must match {expected}, got "
                    f"{[(item.get('id'), item.get('subject_domain')) for item in wrong]}"
                )

        for record_id in checks.get("profile_includes", []):
            if record_id not in profile_ids:
                failures.append(f"{name}: render_profiles should include {record_id}, got {profile_ids}")
        if "profile_top" in checks and (not profile_ids or profile_ids[0] != checks["profile_top"]):
            failures.append(
                f"{name}: render profile top should be {checks['profile_top']}, got {profile_ids[:1]}"
            )

        for category, required in checks.get("category_includes", {}).items():
            got = {item["id"] for item in categories.get(category, [])}
            for record_id in required:
                if record_id not in got:
                    failures.append(f"{name}: {category} should include {record_id}, got {sorted(got)}")
        for category in checks.get("category_has_strong", []):
            if not any(item.get("relevance") == "strong" for item in categories.get(category, [])):
                failures.append(f"{name}: {category} should contain a strong result")
        for category in checks.get("category_no_strong", []):
            bad = [
                item["id"] for item in categories.get(category, [])
                if item.get("relevance") == "strong"
            ]
            if bad:
                failures.append(f"{name}: {category} must contain no strong result, got {bad}")
        clear_corpus_cache()


    # Retain the last bounded corpus until the caller either clears it or the
    # process exits. In-process callers already use the catalog LRUs to cap
    # retained subsets, while isolated workers end immediately after reporting.
    return {
        "ok": not failures,
        "cases": len(cases),
        "missing_expected_ids": missing_expected_ids,
        "failures": failures,
    }


def _parse_worker_output(stdout: str) -> dict[str, Any]:
    """Parse a worker report while tolerating accidental leading whitespace."""
    text = stdout.strip()
    if not text:
        raise ValueError("worker produced no JSON output")
    return json.loads(text)


def _run_isolated_worker(
    start: int,
    end: int,
    runtime_context: PackRuntimeContext,
) -> tuple[int, int, int, str, str, dict[str, Any] | None]:
    """Execute one bounded worker process and return its parsed report data."""
    command = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        *runtime_context.command_arguments(),
        "--worker-start",
        str(start),
        "--worker-end",
        str(end),
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=360,
        )
    except subprocess.TimeoutExpired as exc:
        return start, end, -1, exc.stdout or "", exc.stderr or "", None
    try:
        report = _parse_worker_output(proc.stdout)
    except (ValueError, json.JSONDecodeError):
        report = None
    return start, end, proc.returncode, proc.stdout, proc.stderr, report


def run_chunked_in_process(
    entries=None,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Run the complete suite with one catalog load and bounded case chunks.

    This mode keeps one immutable entry list and evaluates deterministic bounded
    ranges while retaining only the catalog's bounded corpus and indexed-entry
    LRUs. It exercises the complete assertions and search implementation with
    one catalog load.
    """
    loaded = load_entries() if entries is None else entries
    cases = load_spec()["cases"]
    chunk_size = max(1, int(chunk_size))
    failures: list[str] = []
    missing_expected_ids: dict[str, list[str]] = {}
    chunk_reports: list[dict[str, Any]] = []
    for start in range(0, len(cases), chunk_size):
        end = min(len(cases), start + chunk_size)
        report = run_cases(loaded, cases[start:end])
        chunk_reports.append({
            "start": start,
            "end": end,
            "ok": bool(report.get("ok")),
            "cases": int(report.get("cases", 0)),
        })
        missing_expected_ids.update(report.get("missing_expected_ids") or {})
        failures.extend(str(item) for item in report.get("failures", []))
        print(f"[search-regression] evaluated {end}/{len(cases)} cases", file=sys.stderr, flush=True)
    return {
        "ok": not failures,
        "cases": len(cases),
        "total_cases": len(cases),
        "coverage_complete": sum(row["cases"] for row in chunk_reports) == len(cases),
        "missing_expected_ids": missing_expected_ids,
        "failures": failures,
        "execution": {
            "mode": "single-process-bounded-chunks",
            "chunk_size": chunk_size,
            "worker_count": 1,
            "chunks": chunk_reports,
        },
    }


def run_isolated(
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    runtime_context: PackRuntimeContext,
) -> dict[str, Any]:
    """Run the complete suite in fresh bounded worker processes.

    Workers execute in a small bounded pool. Each worker loads its own
    immutable catalog and evaluates one deterministic case range. Ranges stay
    large across changing filters, but long runs sharing the same full-catalog
    subset are split after a small number of cases so per-query state cannot
    accumulate without bound. Result aggregation is sorted by range so report
    ordering remains stable.
    """
    cases = load_spec()["cases"]
    failures: list[str] = []
    missing_expected_ids: dict[str, list[str]] = {}
    worker_reports: list[dict[str, Any]] = []
    chunk_size = max(1, int(chunk_size))
    # Query scoring uses the exact candidate index in catalog_cli, so per-query
    # state does not grow with the full catalog and the ranges are plain chunks.
    ranges: list[tuple[int, int]] = []
    start = 0
    for index in range(len(cases)):
        if index > start and index - start >= chunk_size:
            ranges.append((start, index))
            start = index
    if start < len(cases):
        ranges.append((start, len(cases)))
    requested_workers = int(max_workers)
    if requested_workers < 1:
        raise ValueError("max_workers must be at least 1")
    worker_limit = min(requested_workers, len(ranges) or 1)

    completed: list[tuple[int, int, int, str, str, dict[str, Any] | None]] = []
    if worker_limit == 1:
        # Run directly rather than through a thread. This avoids retaining a
        # queue of child-process futures while the large catalog is rebuilt in
        # each bounded worker, and makes release validation stable on modest
        # memory hosts.
        for start, end in ranges:
            completed.append(_run_isolated_worker(start, end, runtime_context))
    else:
        with ThreadPoolExecutor(max_workers=worker_limit) as pool:
            futures = {
                pool.submit(_run_isolated_worker, start, end, runtime_context): (start, end)
                for start, end in ranges
            }
            for future in as_completed(futures):
                completed.append(future.result())

    for start, end, returncode, stdout, stderr, report in sorted(completed, key=lambda row: row[0]):
        if report is None:
            if returncode == -1:
                failures.append(f"worker cases {start}:{end} exceeded 360 seconds")
            else:
                failures.append(
                    f"worker cases {start}:{end} returned invalid JSON; "
                    f"exit={returncode}; stderr={stderr[-1000:]!r}; stdout={stdout[-1000:]!r}"
                )
            continue
        worker_reports.append({
            "start": start,
            "end": end,
            "ok": bool(report.get("ok")),
            "cases": int(report.get("cases", 0)),
        })
        missing_expected_ids.update(report.get("missing_expected_ids") or {})
        failures.extend(str(item) for item in report.get("failures", []))
        if returncode not in (0, 1):
            failures.append(
                f"worker cases {start}:{end} exited {returncode}; stderr={stderr[-1000:]!r}"
            )
        elif returncode == 1 and report.get("ok"):
            failures.append(f"worker cases {start}:{end} exited 1 despite an ok report")

    return {
        "ok": not failures,
        "cases": len(cases),
        "total_cases": len(cases),
        "coverage_complete": sum(row["cases"] for row in worker_reports) == len(cases),
        "missing_expected_ids": missing_expected_ids,
        "failures": failures,
        "execution": {
            "mode": "parallel-isolated-workers",
            "chunk_size": chunk_size,
            "max_workers": worker_limit,
            "worker_count": len(worker_reports),
            "workers": worker_reports,
        },
    }


def run(
    entries=None,
    *,
    mode: str = DEFAULT_EXECUTION_MODE,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    runtime_context: PackRuntimeContext | None = None,
) -> dict[str, Any]:
    """Run all regression cases.

    Select the execution strategy explicitly with ``mode``. Isolated mode runs
    fresh worker processes; in-process mode uses one catalog load with bounded
    case chunks. A worker range always runs directly in its current process.
    """
    if mode not in {"in-process", "isolated"}:
        raise ValueError("mode must be 'in-process' or 'isolated'")
    if mode == "isolated" and entries is not None:
        raise ValueError("isolated mode cannot use preloaded entries")
    if mode == "isolated":
        if runtime_context is None:
            raise ValueError("isolated mode requires an exact runtime_context")
        return run_isolated(
            chunk_size=chunk_size,
            max_workers=max_workers,
            runtime_context=runtime_context,
        )
    return run_chunked_in_process(
        entries,
        chunk_size=chunk_size,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    add_pack_runtime_arguments(parser)
    parser.add_argument("--worker-start", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--worker-end", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument(
        "--mode",
        choices=("in-process", "isolated"),
        default=DEFAULT_EXECUTION_MODE,
        help=f"execution strategy (default: {DEFAULT_EXECUTION_MODE})",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="maximum isolated worker processes (default: 1)",
    )
    args = parser.parse_args()
    runtime_context = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime_context.settings)
    try:
        if args.worker_start is not None or args.worker_end is not None:
            if args.worker_start is None or args.worker_end is None:
                parser.error("--worker-start and --worker-end must be supplied together")
            cases = load_spec()["cases"]
            start = max(0, args.worker_start)
            end = min(len(cases), args.worker_end)
            if end < start:
                parser.error("worker end must be greater than or equal to worker start")
            report = run_cases(load_entries(), cases[start:end])
            report["range"] = {"start": start, "end": end}
        else:
            mode = args.mode
            if mode == "isolated":
                if args.jobs < 1:
                    parser.error("--jobs must be at least 1")
                report = run_isolated(
                    chunk_size=args.chunk_size,
                    max_workers=args.jobs,
                    runtime_context=runtime_context,
                )
            else:
                report = run_chunked_in_process(chunk_size=args.chunk_size)
    finally:
        configure_pack_runtime(None)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
