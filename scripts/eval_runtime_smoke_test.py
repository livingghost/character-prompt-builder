#!/usr/bin/env python3
"""Exercise pack-owned evaluation mechanics with a temporary locked pack.

This is a core-mechanism smoke test. It deliberately does not use any authored
content pack. Full catalog-quality
evaluation suites remain the responsibility of each pack's release gate.
"""
from __future__ import annotations

import argparse
import io
import json
import tempfile
from contextlib import redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import catalog_retrieval.runtime
import search_regression
import sparse_discovery_eval
from catalog_cli import (
    begin_catalog_request,
    configure_pack_runtime,
    load_entries,
    named_resource_path,
)
from pack_manager import (
    atomic_write_json,
    initialize_pack,
    save_state,
    validate_pack,
    write_lock,
)
from pack_runtime_cli import (
    PackRuntimeContext,
    add_pack_runtime_arguments,
    resolve_pack_runtime,
)


FIXTURE_RECORD_ID = "runtime-eval-smoke-amber-edge-light"
MISSING_RECORD_ID = "runtime-eval-smoke-missing-record"
SEARCH_RESOURCE = "catalog-search-regression"
SPARSE_RESOURCE = "sparse-discovery-evaluation"
MISSING_SEARCH_RESOURCE = "catalog-search-missing-id-probe"
MISSING_SPARSE_RESOURCE = "sparse-discovery-missing-id-probe"


@dataclass(frozen=True)
class RuntimeFixture:
    """Paths and identity for one temporary, released evaluation pack."""

    pack_parent: Path
    pack_root: Path
    pack_id: str
    state_file: Path
    cache_dir: Path
    managed_root: Path
    resource_paths: Mapping[str, Path]

    @property
    def resource_providers(self) -> dict[str, str]:
        return {name: self.pack_id for name in self.resource_paths}


def _record_file() -> dict[str, Any]:
    return {
        "kind": "module",
        "category": "lighting",
        "records": [
            {
                "id": FIXTURE_RECORD_ID,
                "label": "Runtime smoke amber edge light",
                "category": "lighting",
                "curation_status": "curated",
                "prompt": "Use a controlled amber edge light for the runtime smoke fixture.",
                "domains": ["shared"],
                "tags": ["runtime smoke", "amber edge light"],
                "search_terms": [
                    {
                        "phrase": "runtime smoke amber edge light",
                        "facet": "lighting",
                        "weight": 1.2,
                        "source": "author",
                    }
                ],
            }
        ],
    }


def _search_case(expected_id: str, *, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "mode": "search",
        "query": "runtime smoke amber edge light",
        "kinds": ["module"],
        "categories": ["lighting"],
        "domain": "human",
        "limit": 3,
        "assert": {
            "top": expected_id,
            "must_include": [expected_id],
        },
    }


def _sparse_case(expected_id: str, *, case_id: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "mode": "search",
        "query": "runtime smoke amber edge light",
        "domain": "human",
        "kinds": ["module"],
        "categories": ["lighting"],
        "limit": 3,
        "expected_top_ids": [expected_id],
    }


def _case_document(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "purpose": "Temporary core-mechanism evaluation fixture.",
        "case_count": 1,
        "cases": [dict(case)],
    }


def _save_fixture_state(
    fixture: RuntimeFixture,
    *,
    resource_providers: Mapping[str, str] | None = None,
) -> None:
    save_state(
        fixture.state_file,
        {
            "pack_roots": [],
            "enabled_packs": [fixture.pack_id],
            "resource_providers": dict(
                fixture.resource_providers
                if resource_providers is None
                else resource_providers
            ),
        },
    )


def _build_fixture(root: Path) -> tuple[RuntimeFixture, dict[str, Any]]:
    pack_parent = root / "pack-root"
    pack_root = pack_parent / "runtime-eval-fixture"
    manifest = initialize_pack(
        pack_root,
        name="Runtime Evaluation Mechanism Fixture",
    )
    manifest["content"] = {
        "record_globs": ["records/**/*.json"],
        "resource_globs": ["resources/**/*.json"],
        "resource_bindings": {
            SEARCH_RESOURCE: "resources/evals/search.json",
            SPARSE_RESOURCE: "resources/evals/sparse.json",
            MISSING_SEARCH_RESOURCE: "resources/evals/search-missing.json",
            MISSING_SPARSE_RESOURCE: "resources/evals/sparse-missing.json",
        },
    }
    manifest["capabilities"] = ["atomic-modules", "evaluation-fixtures"]
    atomic_write_json(pack_root / "pack.json", manifest)
    atomic_write_json(pack_root / "records" / "lighting.json", _record_file())

    resource_paths = {
        SEARCH_RESOURCE: pack_root / "resources" / "evals" / "search.json",
        SPARSE_RESOURCE: pack_root / "resources" / "evals" / "sparse.json",
        MISSING_SEARCH_RESOURCE: pack_root / "resources" / "evals" / "search-missing.json",
        MISSING_SPARSE_RESOURCE: pack_root / "resources" / "evals" / "sparse-missing.json",
    }
    atomic_write_json(
        resource_paths[SEARCH_RESOURCE],
        _case_document(
            _search_case(FIXTURE_RECORD_ID, name="pack-owned runtime search")
        ),
    )
    atomic_write_json(
        resource_paths[SPARSE_RESOURCE],
        _case_document(
            _sparse_case(FIXTURE_RECORD_ID, case_id="pack-owned-runtime-search")
        ),
    )
    atomic_write_json(
        resource_paths[MISSING_SEARCH_RESOURCE],
        _case_document(
            _search_case(MISSING_RECORD_ID, name="missing search record must fail")
        ),
    )
    atomic_write_json(
        resource_paths[MISSING_SPARSE_RESOURCE],
        _case_document(
            _sparse_case(MISSING_RECORD_ID, case_id="missing-sparse-record-must-fail")
        ),
    )
    write_lock(pack_root)
    validation = validate_pack(pack_root, require_lock=True)

    fixture = RuntimeFixture(
        pack_parent=pack_parent,
        pack_root=pack_root,
        pack_id=str(manifest["pack_id"]),
        state_file=root / "runtime" / "state.json",
        cache_dir=root / "runtime" / "cache",
        managed_root=root / "runtime" / "managed",
        resource_paths=resource_paths,
    )
    _save_fixture_state(fixture)
    return fixture, validation.to_dict()


def _runtime_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval-runtime-boundary", add_help=False)
    add_pack_runtime_arguments(parser)
    return parser


def _resolve_complete_runtime(fixture: RuntimeFixture) -> PackRuntimeContext:
    parser = _runtime_parser()
    args = parser.parse_args(
        [
            "--state-file",
            str(fixture.state_file),
            "--cache-dir",
            str(fixture.cache_dir),
            "--managed-root",
            str(fixture.managed_root),
            "--pack-root",
            str(fixture.pack_parent),
        ]
    )
    return resolve_pack_runtime(parser, args)


def _partial_runtime_results() -> list[dict[str, Any]]:
    rows = (
        ["--state-file", "state.json"],
        ["--cache-dir", "cache"],
        ["--managed-root", "managed"],
        ["--pack-root", "packs/fixture"],
    )
    results: list[dict[str, Any]] = []
    for argv in rows:
        parser = _runtime_parser()
        args = parser.parse_args(argv)
        try:
            with redirect_stderr(io.StringIO()):
                resolve_pack_runtime(parser, args)
        except SystemExit as exc:
            results.append({"arguments": argv, "rejected": exc.code == 2})
        else:
            results.append({"arguments": argv, "rejected": False})
    return results


def _run_search_resource(name: str) -> dict[str, Any]:
    original = search_regression.SEARCH_REGRESSION_RESOURCE
    search_regression.SEARCH_REGRESSION_RESOURCE = name
    try:
        return search_regression.run_chunked_in_process(chunk_size=1)
    finally:
        search_regression.SEARCH_REGRESSION_RESOURCE = original


def _run_sparse_resource(name: str) -> dict[str, Any]:
    original = sparse_discovery_eval.CASES_RESOURCE
    sparse_discovery_eval.CASES_RESOURCE = name
    try:
        return sparse_discovery_eval.evaluate()
    finally:
        sparse_discovery_eval.CASES_RESOURCE = original


def _record_check(
    details: list[dict[str, Any]],
    errors: list[str],
    check_id: str,
    condition: bool,
    observed: Any,
) -> None:
    details.append({"id": check_id, "ok": bool(condition), "observed": observed})
    if not condition:
        errors.append(f"{check_id} failed: {observed}")


def _no_root_fallback_probe(
    fixture: RuntimeFixture,
    runtime_context: PackRuntimeContext,
) -> dict[str, Any]:
    providers = fixture.resource_providers
    providers.pop(SEARCH_RESOURCE)
    _save_fixture_state(fixture, resource_providers=providers)
    configure_pack_runtime(runtime_context.settings)
    try:
        try:
            search_regression.load_spec()
        except SystemExit as exc:
            return {
                "rejected": True,
                "diagnostic": str(exc),
                "resource": SEARCH_RESOURCE,
            }
        return {
            "rejected": False,
            "diagnostic": "unselected resource unexpectedly resolved",
            "resource": SEARCH_RESOURCE,
        }
    finally:
        _save_fixture_state(fixture)
        configure_pack_runtime(runtime_context.settings)
        begin_catalog_request()


def run() -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    errors: list[str] = []
    search_report: dict[str, Any] = {}
    sparse_report: dict[str, Any] = {}
    missing_search_report: dict[str, Any] = {}
    missing_sparse_report: dict[str, Any] = {}
    isolated_worker_report: dict[str, Any] | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="cpb-eval-runtime-smoke-") as temporary:
            fixture, validation = _build_fixture(Path(temporary))
            _record_check(
                details,
                errors,
                "temporary-pack-is-valid-and-locked",
                bool(validation.get("ok"))
                and validation.get("lock_present") is True
                and validation.get("record_count") == 1
                and len(validation.get("resource_bindings") or {}) == 4,
                {
                    "valid": validation.get("ok"),
                    "locked": validation.get("lock_present"),
                    "records": validation.get("record_count"),
                    "named_resources": len(validation.get("resource_bindings") or {}),
                    "errors": validation.get("errors"),
                },
            )

            runtime_context = _resolve_complete_runtime(fixture)
            _record_check(
                details,
                errors,
                "complete-explicit-runtime-is-accepted",
                runtime_context.settings.state_file == fixture.state_file.resolve()
                and runtime_context.settings.cache_dir == fixture.cache_dir.resolve()
                and runtime_context.settings.managed_root == fixture.managed_root.resolve()
                and runtime_context.pack_roots == (fixture.pack_parent.resolve(),),
                {
                    "state": runtime_context.settings.state_file == fixture.state_file.resolve(),
                    "cache": runtime_context.settings.cache_dir == fixture.cache_dir.resolve(),
                    "managed": runtime_context.settings.managed_root == fixture.managed_root.resolve(),
                    "pack_roots": len(runtime_context.pack_roots),
                },
            )
            round_trip_parser = _runtime_parser()
            round_trip_args = round_trip_parser.parse_args(runtime_context.command_arguments())
            round_trip = resolve_pack_runtime(round_trip_parser, round_trip_args)
            _record_check(
                details,
                errors,
                "explicit-runtime-round-trips-to-workers",
                round_trip == runtime_context,
                {"argument_count": len(runtime_context.command_arguments())},
            )

            configure_pack_runtime(runtime_context.settings)
            catalog = begin_catalog_request()
            entries = load_entries()
            _record_check(
                details,
                errors,
                "only-temporary-pack-is-active",
                catalog.active_pack_count == 1
                and len(entries) == 1
                and entries[0].source_pack == fixture.pack_id
                and str(entries[0].record.get("id")) == FIXTURE_RECORD_ID,
                {
                    "active_pack_count": catalog.active_pack_count,
                    "entry_count": len(entries),
                    "fixture_entry_active": bool(entries)
                    and entries[0].source_pack == fixture.pack_id,
                },
            )

            resolved_search = named_resource_path(SEARCH_RESOURCE)
            resolved_sparse = named_resource_path(SPARSE_RESOURCE)
            _record_check(
                details,
                errors,
                "search-suite-uses-named-pack-resource",
                resolved_search == fixture.resource_paths[SEARCH_RESOURCE].resolve(),
                {
                    "resolved_to_fixture": resolved_search
                    == fixture.resource_paths[SEARCH_RESOURCE].resolve()
                },
            )
            _record_check(
                details,
                errors,
                "sparse-suite-uses-named-pack-resource",
                resolved_sparse == fixture.resource_paths[SPARSE_RESOURCE].resolve(),
                {
                    "resolved_to_fixture": resolved_sparse
                    == fixture.resource_paths[SPARSE_RESOURCE].resolve()
                },
            )

            search_report = _run_search_resource(SEARCH_RESOURCE)
            _record_check(
                details,
                errors,
                "complete-search-suite-succeeds",
                search_report.get("ok") is True
                and search_report.get("cases") == 1
                and search_report.get("total_cases") == 1
                and search_report.get("coverage_complete") is True
                and not search_report.get("missing_expected_ids")
                and not search_report.get("failures"),
                {
                    key: search_report.get(key)
                    for key in (
                        "ok",
                        "cases",
                        "total_cases",
                        "coverage_complete",
                        "missing_expected_ids",
                        "failures",
                    )
                },
            )

            sparse_report = _run_sparse_resource(SPARSE_RESOURCE)
            _record_check(
                details,
                errors,
                "complete-sparse-suite-succeeds",
                sparse_report.get("ok") is True
                and sparse_report.get("case_count") == 1
                and sparse_report.get("total_case_count") == 1
                and sparse_report.get("coverage_complete") is True
                and sparse_report.get("passed") == 1
                and sparse_report.get("failed") == 0
                and not sparse_report.get("missing_expected_ids")
                and not sparse_report.get("failures"),
                {
                    key: sparse_report.get(key)
                    for key in (
                        "ok",
                        "case_count",
                        "total_case_count",
                        "coverage_complete",
                        "passed",
                        "failed",
                        "missing_expected_ids",
                        "failures",
                    )
                },
            )

            start, end, exit_code, _stdout, stderr, isolated_worker_report = (
                search_regression._run_isolated_worker(0, 1, runtime_context)
            )
            _record_check(
                details,
                errors,
                "isolated-worker-uses-complete-explicit-runtime",
                (start, end) == (0, 1)
                and exit_code == 0
                and bool(isolated_worker_report)
                and isolated_worker_report.get("ok") is True
                and isolated_worker_report.get("cases") == 1,
                {
                    "range": [start, end],
                    "exit_code": exit_code,
                    "cases": (
                        isolated_worker_report.get("cases")
                        if isolated_worker_report
                        else None
                    ),
                    "stderr_tail": stderr[-300:] if exit_code else "",
                },
            )

            missing_search_report = _run_search_resource(MISSING_SEARCH_RESOURCE)
            _record_check(
                details,
                errors,
                "missing-search-expected-id-fails",
                missing_search_report.get("ok") is False
                and missing_search_report.get("coverage_complete") is True
                and MISSING_RECORD_ID
                in {
                    value
                    for values in (missing_search_report.get("missing_expected_ids") or {}).values()
                    for value in values
                }
                and bool(missing_search_report.get("failures")),
                {
                    "ok": missing_search_report.get("ok"),
                    "coverage_complete": missing_search_report.get("coverage_complete"),
                    "missing_expected_ids": missing_search_report.get("missing_expected_ids"),
                    "failure_count": len(missing_search_report.get("failures") or []),
                },
            )

            missing_sparse_report = _run_sparse_resource(MISSING_SPARSE_RESOURCE)
            _record_check(
                details,
                errors,
                "missing-sparse-expected-id-fails",
                missing_sparse_report.get("ok") is False
                and missing_sparse_report.get("coverage_complete") is True
                and missing_sparse_report.get("failed") == 1
                and MISSING_RECORD_ID
                in {
                    value
                    for values in (missing_sparse_report.get("missing_expected_ids") or {}).values()
                    for value in values
                }
                and bool(missing_sparse_report.get("failures")),
                {
                    "ok": missing_sparse_report.get("ok"),
                    "coverage_complete": missing_sparse_report.get("coverage_complete"),
                    "failed": missing_sparse_report.get("failed"),
                    "missing_expected_ids": missing_sparse_report.get("missing_expected_ids"),
                    "failure_count": len(missing_sparse_report.get("failures") or []),
                },
            )

            reports_with_no_skip_contract = (
                search_report,
                sparse_report,
                missing_search_report,
                missing_sparse_report,
                isolated_worker_report or {},
            )
            _record_check(
                details,
                errors,
                "evaluation-reports-have-no-skip-path",
                all("skipped" not in report for report in reports_with_no_skip_contract),
                {
                    "report_count": len(reports_with_no_skip_contract),
                    "reports_with_skipped_field": sum(
                        1 for report in reports_with_no_skip_contract if "skipped" in report
                    ),
                },
            )

            fallback_probe = _no_root_fallback_probe(fixture, runtime_context)
            _record_check(
                details,
                errors,
                "unselected-named-resource-has-no-root-fallback",
                fallback_probe.get("rejected") is True
                and fallback_probe.get("diagnostic")
                == f"Required named pack resource is unavailable: {SEARCH_RESOURCE}",
                fallback_probe,
            )

            partial_results = _partial_runtime_results()
            _record_check(
                details,
                errors,
                "every-partial-runtime-is-rejected",
                len(partial_results) == 4
                and all(row.get("rejected") is True for row in partial_results),
                partial_results,
            )
    except Exception as exc:  # pragma: no cover - report unexpected smoke failures
        errors.append(f"unexpected smoke-test failure: {type(exc).__name__}: {exc}")
    finally:
        configure_pack_runtime(None)

    _record_check(
        details,
        errors,
        "catalog-runtime-is-reset",
        catalog_retrieval.runtime._PACK_SETTINGS is None,
        {"pack_settings_is_none": catalog_retrieval.runtime._PACK_SETTINGS is None},
    )
    passed = sum(1 for row in details if row["ok"])
    return {
        "ok": not errors,
        "scope": "self-contained-core-evaluation-mechanism",
        "fixture": {
            "temporary": True,
            "active_pack_count": 1,
            "record_count": 1,
            "named_resource_count": 4,
            "successful_search_cases": int(search_report.get("cases", 0)),
            "successful_sparse_cases": int(sparse_report.get("case_count", 0)),
            "isolated_worker_cases": int(
                isolated_worker_report.get("cases", 0)
                if isolated_worker_report
                else 0
            ),
        },
        "checks": len(details),
        "passed": passed,
        "failed": len(details) - passed,
        "details": details,
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
