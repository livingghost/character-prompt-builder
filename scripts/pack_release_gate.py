#!/usr/bin/env python3
"""Run one content pack's declared release evaluations in an exact runtime.

The gate never consults the bundled default state or the process' platform
state.  Its state file must enable exactly the positional pack, its discovery
roots must contain exactly that pack directory, and every named resource
binding must select that pack as provider.  A pack without declared evaluation
resources receives the structural lock and cache checks only.  A pack that
declares evaluations owns their counts and preservation expectations through
the ``release-evaluation-contract`` named resource.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True

from catalog_cli import configure_pack_runtime, load_pack_catalog
from pack_cache import cache_status, refresh_cache
from pack_manager import (
    PackSettings,
    canonical_json,
    build_lock_data,
    is_project_pack,
    load_state,
    sha256_bytes,
    validate_pack,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_RESOURCE = "release-evaluation-contract"
TIER_BASELINE_RESOURCE = "tier-strategy-retrieval-baseline"
SUITE_RESOURCE_NAMES = {
    "search_regression": "catalog-search-regression",
    "sparse_discovery": "sparse-discovery-evaluation",
    "tier_strategy": "tier-strategy-evaluation-cases",
    "style_family": "style-family-taxonomy",
    "reference_corpus": "reference-corpus-manifest",
}
DECLARED_EVALUATION_RESOURCES = frozenset(
    {
        *SUITE_RESOURCE_NAMES.values(),
        TIER_BASELINE_RESOURCE,
    }
)
SUITE_NAMES = frozenset(
    {
        "search_regression",
        "sparse_discovery",
        "tier_strategy",
        "style_family",
        "quality",
        "reference_corpus",
        "preservation",
    }
)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
RESOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
ID_SHAPED_ALIAS_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value


def _positive_integer(value: Any, field: str, errors: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(f"{field} must be a positive integer")
        return None
    return value


def _nonnegative_integer(value: Any, field: str, errors: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{field} must be a non-negative integer")
        return None
    return value


def _exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    field: str,
    errors: list[str],
) -> None:
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    if missing:
        errors.append(f"{field} is missing fields: {missing}")
    if extra:
        errors.append(f"{field} contains unsupported fields: {extra}")


def validate_release_contract(value: Any) -> list[str]:
    """Validate the strict pack-owned evaluation contract shape."""
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["release-evaluation-contract must contain one JSON object"]
    unknown = sorted(set(value) - SUITE_NAMES)
    if unknown:
        errors.append(f"release-evaluation-contract declares unknown suites: {unknown}")
    if not value:
        errors.append("release-evaluation-contract must declare at least one suite")

    simple_resources = {
        "search_regression": ("resource", "expected_case_count"),
        "sparse_discovery": ("resource", "expected_case_count"),
        "style_family": ("taxonomy_resource", "expected_family_count"),
    }
    for suite, fields in simple_resources.items():
        if suite not in value:
            continue
        row = value[suite]
        if not isinstance(row, Mapping):
            errors.append(f"{suite} must be an object")
            continue
        _exact_keys(row, required=set(fields), field=suite, errors=errors)
        resource = row.get(fields[0])
        expected_resource = SUITE_RESOURCE_NAMES[suite]
        if resource != expected_resource:
            errors.append(
                f"{suite}.{fields[0]} must be the logical resource {expected_resource!r}"
            )
        _positive_integer(row.get(fields[1]), f"{suite}.{fields[1]}", errors)

    if "tier_strategy" in value:
        row = value["tier_strategy"]
        required = {"cases_resource", "baseline_resource", "expected_case_count"}
        if not isinstance(row, Mapping):
            errors.append("tier_strategy must be an object")
        else:
            _exact_keys(row, required=required, field="tier_strategy", errors=errors)
            if row.get("cases_resource") != SUITE_RESOURCE_NAMES["tier_strategy"]:
                errors.append(
                    "tier_strategy.cases_resource must be the logical resource "
                    f"{SUITE_RESOURCE_NAMES['tier_strategy']!r}"
                )
            if row.get("baseline_resource") != TIER_BASELINE_RESOURCE:
                errors.append(
                    "tier_strategy.baseline_resource must be the logical resource "
                    f"{TIER_BASELINE_RESOURCE!r}"
                )
            _positive_integer(
                row.get("expected_case_count"),
                "tier_strategy.expected_case_count",
                errors,
            )

    if "quality" in value:
        row = value["quality"]
        required = {"derive_expected_record_count_from_lock"}
        if not isinstance(row, Mapping):
            errors.append("quality must be an object")
        else:
            _exact_keys(row, required=required, field="quality", errors=errors)
            if row.get("derive_expected_record_count_from_lock") is not True:
                errors.append(
                    "quality.derive_expected_record_count_from_lock must be true"
                )

    if "reference_corpus" in value:
        row = value["reference_corpus"]
        required = {
            "manifest_resource",
            "expected_searchable_asset_count",
            "expected_source_file_count",
            "expected_evidence_bundle_count",
        }
        if not isinstance(row, Mapping):
            errors.append("reference_corpus must be an object")
        else:
            _exact_keys(row, required=required, field="reference_corpus", errors=errors)
            if row.get("manifest_resource") != SUITE_RESOURCE_NAMES["reference_corpus"]:
                errors.append(
                    "reference_corpus.manifest_resource must be the logical resource "
                    f"{SUITE_RESOURCE_NAMES['reference_corpus']!r}"
                )
            for name in sorted(required - {"manifest_resource"}):
                _positive_integer(row.get(name), f"reference_corpus.{name}", errors)

    if "preservation" in value:
        row = value["preservation"]
        required = {
            "expected_record_count",
            "expected_record_content_sha256",
            "expected_explicit_lexical_tuple_count",
            "expected_explicit_lexical_tuples_sha256",
            "expected_search_profile_alias_tuple_count",
            "expected_search_profile_alias_tuples_sha256",
            "expected_noncanonical_id_alias_count",
        }
        if not isinstance(row, Mapping):
            errors.append("preservation must be an object")
        else:
            _exact_keys(row, required=required, field="preservation", errors=errors)
            _positive_integer(
                row.get("expected_record_count"),
                "preservation.expected_record_count",
                errors,
            )
            _positive_integer(
                row.get("expected_explicit_lexical_tuple_count"),
                "preservation.expected_explicit_lexical_tuple_count",
                errors,
            )
            _nonnegative_integer(
                row.get("expected_search_profile_alias_tuple_count"),
                "preservation.expected_search_profile_alias_tuple_count",
                errors,
            )
            _nonnegative_integer(
                row.get("expected_noncanonical_id_alias_count"),
                "preservation.expected_noncanonical_id_alias_count",
                errors,
            )
            for name in (
                "expected_record_content_sha256",
                "expected_explicit_lexical_tuples_sha256",
                "expected_search_profile_alias_tuples_sha256",
            ):
                if not isinstance(row.get(name), str) or not SHA256_RE.fullmatch(row[name]):
                    errors.append(f"preservation.{name} must be a lowercase SHA-256")
    return errors


def authored_metrics(validation: Any) -> dict[str, Any]:
    """Return deterministic pack-owned record and explicit lexical invariants."""
    record_rows = [
        {
            "source_file": row.source_file,
            "kind": row.kind,
            "category": row.category,
            "record": row.record,
        }
        for row in validation.records
    ]
    lexical_rows: list[tuple[str, str, str, float, str]] = []
    search_profile_alias_rows: list[tuple[str, str]] = []
    noncanonical_id_alias_count = 0
    for row in validation.records:
        record_id = str(row.record.get("id") or "").strip().lower()
        for term in row.record.get("search_terms") or []:
            lexical_rows.append(
                (
                    str(term.get("phrase") or "").strip().lower(),
                    record_id,
                    str(term.get("facet") or ""),
                    float(term.get("weight")),
                    str(term.get("source") or ""),
                )
            )
        search_profile = row.record.get("search_profile")
        aliases = (
            search_profile.get("aliases")
            if isinstance(search_profile, Mapping)
            else None
        )
        if not isinstance(aliases, list):
            continue
        namespace_prefixes: set[str] = set()
        for raw_label in (row.kind, row.category, row.record.get("type")):
            if not isinstance(raw_label, str):
                continue
            label = raw_label.strip().lower()
            prefix = f"{label}-"
            if label and record_id.startswith(prefix):
                namespace_prefixes.add(prefix)
        for raw_alias in aliases:
            alias = str(raw_alias).strip().lower()
            search_profile_alias_rows.append((alias, record_id))
            if (
                alias != record_id
                and ID_SHAPED_ALIAS_RE.fullmatch(alias)
                and any(alias.startswith(prefix) for prefix in namespace_prefixes)
            ):
                noncanonical_id_alias_count += 1
    unique_lexical_rows = sorted(set(lexical_rows))
    unique_search_profile_alias_rows = sorted(set(search_profile_alias_rows))
    return {
        "record_count": len(record_rows),
        "record_content_sha256": sha256_bytes(
            canonical_json(record_rows).encode("utf-8")
        ),
        "explicit_lexical_term_count": len(lexical_rows),
        "explicit_lexical_tuple_count": len(unique_lexical_rows),
        "explicit_lexical_tuples_sha256": sha256_bytes(
            canonical_json(unique_lexical_rows).encode("utf-8")
        ),
        "search_profile_alias_term_count": len(search_profile_alias_rows),
        "search_profile_alias_tuple_count": len(unique_search_profile_alias_rows),
        "search_profile_alias_tuples_sha256": sha256_bytes(
            canonical_json(unique_search_profile_alias_rows).encode("utf-8")
        ),
        "noncanonical_id_alias_count": noncanonical_id_alias_count,
        "quality_record_count_from_lock": sum(
            1 for row in validation.records if row.kind not in {"asset", "model"}
        ),
        "style_family_record_count": sum(
            1 for row in validation.records if row.kind == "style-family"
        ),
    }


def _skip_count(value: Any) -> int:
    """Count explicit skip-report fields recursively; ordinary prose is ignored."""
    if isinstance(value, Mapping):
        total = 0
        for key, child in value.items():
            if key in {
                "skip_count",
                "skipped",
                "skipped_case_count",
                "skipped_cases",
            }:
                if isinstance(child, bool):
                    total += int(child)
                elif isinstance(child, int):
                    total += max(0, child)
                elif isinstance(child, (list, tuple, set, dict)):
                    total += len(child)
                elif child not in (None, "", "0"):
                    total += 1
            else:
                total += _skip_count(child)
        return total
    if isinstance(value, (list, tuple)):
        return sum(_skip_count(item) for item in value)
    return 0


def _resource_path(catalog: Any, name: str, pack_id: str) -> Path:
    if not RESOURCE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid logical resource name: {name!r}")
    resource = catalog.resources.get(name)
    if resource is None:
        raise ValueError(f"declared logical resource is unavailable: {name!r}")
    if resource.source_pack != pack_id:
        raise ValueError(
            f"logical resource {name!r} resolved from {resource.source_pack}, not {pack_id}"
        )
    if not resource.path.is_file():
        raise ValueError(f"logical resource {name!r} does not resolve to a file")
    return resource.path


def _case_document(path: Path, label: str) -> tuple[dict[str, Any], list[Any]]:
    document = _load_json_object(path, label)
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{label}.cases must be a non-empty array")
    declared = document.get("case_count")
    if declared != len(cases):
        raise ValueError(
            f"{label}.case_count is stale: declared {declared!r}, found {len(cases)}"
        )
    return document, cases


def _search_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    del metrics
    import search_regression

    resource = str(row["resource"])
    path = _resource_path(catalog, resource, pack_id)
    _, cases = _case_document(path, resource)
    expected = int(row["expected_case_count"])
    errors: list[str] = []
    if len(cases) != expected:
        errors.append(f"expected {expected} cases, resource contains {len(cases)}")
    report = search_regression.run_chunked_in_process()
    skip_count = _skip_count(report)
    failures = [str(value) for value in report.get("failures") or []]
    case_names = [str(case.get("name") or "") for case in cases]
    failed_names = {
        name for name in case_names if any(failure.startswith(f"{name}:") for failure in failures)
    }
    unattributed = [
        failure
        for failure in failures
        if not any(failure.startswith(f"{name}:") for name in case_names)
    ]
    if report.get("cases") != expected or report.get("total_cases") != expected:
        errors.append("search report case totals do not match the contract")
    if report.get("coverage_complete") is not True:
        errors.append("search report coverage is incomplete")
    if report.get("missing_expected_ids"):
        errors.append("search report contains missing expected record IDs")
    if failures:
        errors.append(f"search regression produced {len(failures)} assertion failures")
    if skip_count:
        errors.append(f"search regression reported {skip_count} skipped cases")
    if report.get("ok") is not True:
        errors.append("search regression reported ok=false")
    return {
        "ok": not errors,
        "expected_count": expected,
        "actual_count": int(report.get("cases") or 0),
        "passed_count": expected - len(failed_names) if not unattributed else None,
        "failed_count": len(failed_names),
        "expected_case_count": expected,
        "actual_case_count": int(report.get("cases") or 0),
        "passed_case_count": expected - len(failed_names) if not unattributed else None,
        "failed_case_count": len(failed_names),
        "assertion_failure_count": len(failures),
        "unattributed_failure_count": len(unattributed),
        "coverage_complete": report.get("coverage_complete") is True,
        "skipped": skip_count,
        "errors": errors,
    }


def _sparse_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    del metrics
    import sparse_discovery_eval

    resource = str(row["resource"])
    path = _resource_path(catalog, resource, pack_id)
    _, cases = _case_document(path, resource)
    expected = int(row["expected_case_count"])
    errors: list[str] = []
    if len(cases) != expected:
        errors.append(f"expected {expected} cases, resource contains {len(cases)}")
    report = sparse_discovery_eval.evaluate()
    skip_count = _skip_count(report)
    actual = int(report.get("case_count") or 0)
    total = int(report.get("total_case_count") or 0)
    passed = int(report.get("passed") or 0)
    failed = int(report.get("failed") or 0)
    failures = [str(value) for value in report.get("failures") or []]
    if actual != expected or total != expected:
        errors.append("sparse-discovery report case totals do not match the contract")
    if passed + failed != expected:
        errors.append("sparse-discovery pass/fail totals are incomplete")
    if report.get("coverage_complete") is not True:
        errors.append("sparse-discovery coverage is incomplete")
    if report.get("missing_expected_ids"):
        errors.append("sparse-discovery contains missing expected record IDs")
    if failed or failures:
        errors.append(
            f"sparse-discovery produced {failed} failed cases and {len(failures)} failures"
        )
    if skip_count:
        errors.append(f"sparse-discovery reported {skip_count} skipped cases")
    if report.get("ok") is not True:
        errors.append("sparse-discovery reported ok=false")
    return {
        "ok": not errors,
        "expected_count": expected,
        "actual_count": actual,
        "passed_count": passed,
        "failed_count": failed,
        "expected_case_count": expected,
        "actual_case_count": actual,
        "passed_case_count": passed,
        "failed_case_count": failed,
        "assertion_failure_count": len(failures),
        "coverage_complete": report.get("coverage_complete") is True,
        "skipped": skip_count,
        "errors": errors,
    }


def _tier_retrieval_projection(retrieval: Any) -> dict[str, Any] | None:
    """Project retrieval identity/order without release or filesystem metadata."""
    if retrieval is None:
        return None
    if not isinstance(retrieval, Mapping):
        raise ValueError("tier retrieval must be an object or null")

    def rows(values: Any) -> list[dict[str, Any]]:
        return [
            {
                "id": str(item.get("id") or ""),
                "relevance": item.get("relevance"),
                "tier": item.get("tier"),
            }
            for item in values or []
            if isinstance(item, Mapping)
        ]

    categories = retrieval.get("categories")
    return {
        "categories": {
            str(name): rows(values)
            for name, values in sorted((categories or {}).items())
        },
        "aesthetic_cores": rows(retrieval.get("aesthetic_cores")),
        "style_families": rows(retrieval.get("style_families")),
        "domain_realizations": rows(retrieval.get("domain_realizations")),
        "render_profiles": rows(retrieval.get("render_profiles")),
    }


def tier_baseline_from_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return a frozen ID/order/relevance baseline for a tier packet."""
    rows: list[dict[str, Any]] = []
    for case in packet.get("cases") or []:
        conditions = case.get("conditions") or {}
        rows.append(
            {
                "id": str(case.get("id") or ""),
                "conditions": {
                    name: {
                        "retrieval_sha256": hashlib.sha256(
                            canonical_json(
                                _tier_retrieval_projection(
                                    (conditions.get(name) or {}).get("retrieval")
                                )
                            ).encode("utf-8")
                        ).hexdigest()
                    }
                    for name in ("any", "curated")
                },
            }
        )
    return {"cases": rows}


def _validate_tier_baseline(value: Any, expected: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping) or set(value) != {"cases"}:
        return ["tier baseline must be an object containing only cases"]
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != expected:
        return [f"tier baseline must contain exactly {expected} cases"]
    ids: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping) or set(case) != {"id", "conditions"}:
            errors.append(f"tier baseline cases[{index}] has an invalid shape")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"tier baseline cases[{index}].id must be a non-empty string")
        else:
            ids.append(case_id)
        conditions = case.get("conditions")
        if not isinstance(conditions, Mapping) or set(conditions) != {"any", "curated"}:
            errors.append(
                f"tier baseline cases[{index}].conditions must contain any and curated"
            )
            continue
        for condition in ("any", "curated"):
            item = conditions.get(condition)
            if not isinstance(item, Mapping) or set(item) != {"retrieval_sha256"}:
                errors.append(
                    f"tier baseline cases[{index}].conditions.{condition} has an invalid shape"
                )
                continue
            digest = item.get("retrieval_sha256")
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                errors.append(
                    f"tier baseline cases[{index}].conditions.{condition}.retrieval_sha256 "
                    "must be a lowercase SHA-256"
                )
    if len(ids) != len(set(ids)):
        errors.append("tier baseline case IDs must be unique")
    return errors


def _tier_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    del metrics
    import tier_strategy_eval

    cases_path = _resource_path(catalog, str(row["cases_resource"]), pack_id)
    baseline_path = _resource_path(catalog, str(row["baseline_resource"]), pack_id)
    cases = tier_strategy_eval.load_cases(cases_path)
    expected = int(row["expected_case_count"])
    errors: list[str] = []
    if len(cases) != expected:
        errors.append(f"expected {expected} tier cases, resource contains {len(cases)}")
    baseline = _load_json_object(baseline_path, str(row["baseline_resource"]))
    baseline_errors = _validate_tier_baseline(baseline, expected)
    errors.extend(baseline_errors)
    packet = tier_strategy_eval.build_packet(cases)
    observed = tier_baseline_from_packet(packet)
    expected_by_id = {
        str(case.get("id")): case for case in baseline.get("cases") or []
        if isinstance(case, Mapping)
    }
    observed_by_id = {
        str(case.get("id")): case for case in observed.get("cases") or []
        if isinstance(case, Mapping)
    }
    case_ids = [str(case.get("id") or "") for case in cases]
    baseline_ids_complete = set(expected_by_id) == set(case_ids)
    if not baseline_ids_complete:
        errors.append("tier baseline case IDs do not exactly match the cases resource")
    mismatched_ids = sorted(
        case_id
        for case_id in set(expected_by_id) & set(observed_by_id)
        if expected_by_id[case_id] != observed_by_id[case_id]
    )
    if mismatched_ids:
        errors.append(f"tier retrieval baseline changed for case IDs: {mismatched_ids}")
    zero_candidate_conditions: list[str] = []
    for case in packet.get("cases") or []:
        for condition in ("any", "curated"):
            diagnostics = ((case.get("conditions") or {}).get(condition) or {}).get(
                "diagnostics"
            ) or {}
            candidate_total = sum(
                int(value)
                for key, value in diagnostics.items()
                if key.endswith("_candidates") and isinstance(value, int)
            )
            if candidate_total <= 0:
                zero_candidate_conditions.append(f"{case.get('id')}:{condition}")
    if zero_candidate_conditions:
        errors.append(
            "tier retrieval returned zero candidates for: "
            + ", ".join(zero_candidate_conditions)
        )
    actual = int(packet.get("case_count") or 0)
    if actual != expected or len(packet.get("cases") or []) != expected:
        errors.append("tier packet case totals do not match the contract")
    zero_candidate_case_ids = {
        value.rsplit(":", 1)[0] for value in zero_candidate_conditions
    }
    failed_case_ids = set(mismatched_ids) | zero_candidate_case_ids
    baseline_complete = not baseline_errors and baseline_ids_complete
    coverage_complete = (
        actual == expected
        and len(observed_by_id) == expected
        and baseline_complete
    )
    return {
        "ok": not errors,
        "expected_count": expected,
        "actual_count": actual,
        "passed_count": expected - len(failed_case_ids)
        if baseline_complete
        else None,
        "failed_count": len(failed_case_ids) if baseline_complete else None,
        "expected_case_count": expected,
        "actual_case_count": actual,
        "passed_case_count": expected - len(failed_case_ids)
        if baseline_complete
        else None,
        "failed_case_count": len(failed_case_ids) if baseline_complete else None,
        "coverage_complete": coverage_complete,
        "zero_candidate_condition_count": len(zero_candidate_conditions),
        "skipped": 0,
        "observed_baseline": observed,
        "errors": errors,
    }


def _style_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    import style_family_audit

    _resource_path(catalog, str(row["taxonomy_resource"]), pack_id)
    expected = int(row["expected_family_count"])
    errors: list[str] = []
    if metrics["style_family_record_count"] != expected:
        errors.append(
            "locked style-family record count does not match the contract: "
            f"{metrics['style_family_record_count']} != {expected}"
        )
    report = style_family_audit.audit(PROJECT_ROOT)
    actual = int(report.get("family_count") or 0)
    if actual != expected:
        errors.append(f"style audit returned {actual} families; expected {expected}")
    if report.get("errors"):
        errors.append(f"style audit produced {len(report['errors'])} errors")
    if report.get("ok") is not True:
        errors.append("style audit reported ok=false")
    suite_ok = not errors
    return {
        "ok": suite_ok,
        "expected_count": expected,
        "actual_count": actual,
        "passed_count": expected if suite_ok else None,
        "failed_count": 0 if suite_ok else None,
        "expected_family_count": expected,
        "actual_family_count": actual,
        "revised_or_new_family_count": int(
            report.get("revised_or_new_family_count") or 0
        ),
        "retained_family_count": int(report.get("retained_family_count") or 0),
        "deferred_candidate_count": int(report.get("deferred_candidate_count") or 0),
        "coverage_complete": actual == expected,
        "skipped": _skip_count(report),
        "errors": errors,
        "warnings": [str(value) for value in report.get("warnings") or []],
    }


def _quality_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    del row, catalog, pack_id
    import audit_preset_quality

    expected = int(metrics["quality_record_count_from_lock"])
    errors: list[str] = []
    if expected <= 0:
        errors.append("quality suite has zero locked non-asset/model records")
    report = audit_preset_quality.audit(PROJECT_ROOT, write_report=False)
    actual = int(report.get("records_total") or 0)
    if actual != expected:
        errors.append(f"quality audit returned {actual} records; expected {expected}")
    if report.get("errors"):
        errors.append(f"quality audit produced {len(report['errors'])} errors")
    skip_count = _skip_count(report)
    if skip_count:
        errors.append(f"quality audit reported {skip_count} skipped items")
    if report.get("ok") is not True:
        errors.append("quality audit reported ok=false")
    suite_ok = not errors
    return {
        "ok": suite_ok,
        "expected_count": expected,
        "actual_count": actual,
        "passed_count": expected if suite_ok else None,
        "failed_count": 0 if suite_ok else None,
        "expected_record_count_from_lock": expected,
        "actual_record_count": actual,
        "curated_record_count": int(report.get("curated_records") or 0),
        "vocabulary_record_count": int(
            (report.get("tier_counts") or {}).get("vocabulary") or 0
        ),
        "near_duplicate_finding_count": len(report.get("near_duplicate_findings") or []),
        "coverage_complete": actual == expected,
        "skipped": skip_count,
        "errors": errors,
        "warnings": [str(value) for value in report.get("warnings") or []],
    }


def _corpus_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    del metrics
    import validate_reference_corpus

    _resource_path(catalog, str(row["manifest_resource"]), pack_id)
    report = validate_reference_corpus.validate(
        None,
        require_bundles=True,
        workers=1,
    )
    stats = report.get("stats") or {}
    expected = {
        "searchable_asset_count": int(row["expected_searchable_asset_count"]),
        "source_file_count": int(row["expected_source_file_count"]),
        "evidence_bundle_count": int(row["expected_evidence_bundle_count"]),
    }
    errors: list[str] = []
    for name, count in expected.items():
        if stats.get(name) != count:
            errors.append(
                f"reference corpus {name} is {stats.get(name)!r}; expected {count}"
            )
    if stats.get("validated_bundle_count") != expected["evidence_bundle_count"]:
        errors.append("reference corpus did not validate every expected bundle")
    if stats.get("validation_mode") != "full":
        errors.append("reference corpus validation did not run in full mode")
    skip_count = _skip_count(report)
    if skip_count:
        errors.append(f"reference corpus reported {skip_count} skipped items")
    if report.get("errors"):
        errors.append(f"reference corpus produced {len(report['errors'])} errors")
    if report.get("ok") is not True:
        errors.append("reference corpus validation reported ok=false")
    suite_ok = not errors
    return {
        "ok": suite_ok,
        "expected_count": expected["evidence_bundle_count"],
        "actual_count": int(stats.get("validated_bundle_count") or 0),
        "passed_count": expected["evidence_bundle_count"] if suite_ok else None,
        "failed_count": 0 if suite_ok else None,
        "expected_searchable_asset_count": expected["searchable_asset_count"],
        "actual_searchable_asset_count": int(stats.get("searchable_asset_count") or 0),
        "expected_source_file_count": expected["source_file_count"],
        "actual_source_file_count": int(stats.get("source_file_count") or 0),
        "expected_evidence_bundle_count": expected["evidence_bundle_count"],
        "actual_evidence_bundle_count": int(stats.get("evidence_bundle_count") or 0),
        "validated_bundle_count": int(stats.get("validated_bundle_count") or 0),
        "coverage_complete": (
            stats.get("validated_bundle_count") == expected["evidence_bundle_count"]
        ),
        "skipped": skip_count,
        "errors": errors,
        "warnings": [str(value) for value in report.get("warnings") or []],
    }


def _preservation_suite(
    row: Mapping[str, Any], catalog: Any, pack_id: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    del catalog, pack_id
    comparisons = {
        "record_count": (
            int(row["expected_record_count"]),
            int(metrics["record_count"]),
        ),
        "record_content_sha256": (
            str(row["expected_record_content_sha256"]),
            str(metrics["record_content_sha256"]),
        ),
        "explicit_lexical_tuple_count": (
            int(row["expected_explicit_lexical_tuple_count"]),
            int(metrics["explicit_lexical_tuple_count"]),
        ),
        "explicit_lexical_tuples_sha256": (
            str(row["expected_explicit_lexical_tuples_sha256"]),
            str(metrics["explicit_lexical_tuples_sha256"]),
        ),
        "search_profile_alias_tuple_count": (
            int(row["expected_search_profile_alias_tuple_count"]),
            int(metrics["search_profile_alias_tuple_count"]),
        ),
        "search_profile_alias_tuples_sha256": (
            str(row["expected_search_profile_alias_tuples_sha256"]),
            str(metrics["search_profile_alias_tuples_sha256"]),
        ),
        "noncanonical_id_alias_count": (
            int(row["expected_noncanonical_id_alias_count"]),
            int(metrics["noncanonical_id_alias_count"]),
        ),
    }
    comparison_errors = [
        f"preservation {name} changed: expected {expected!r}, found {actual!r}"
        for name, (expected, actual) in comparisons.items()
        if expected != actual
    ]
    duplicate_free = (
        metrics["explicit_lexical_term_count"]
        == metrics["explicit_lexical_tuple_count"]
    )
    errors = list(comparison_errors)
    if not duplicate_free:
        errors.append("authored search_terms contain duplicate explicit lexical tuples")
    noncanonical_id_aliases_absent = metrics["noncanonical_id_alias_count"] == 0
    if not noncanonical_id_aliases_absent:
        errors.append("search_profile.aliases contain noncanonical same-namespace record IDs")
    expected_checks = len(comparisons) + 2
    failed_checks = (
        len(comparison_errors)
        + int(not duplicate_free)
        + int(not noncanonical_id_aliases_absent)
    )
    return {
        "ok": not errors,
        "expected_count": expected_checks,
        "actual_count": expected_checks,
        "passed_count": expected_checks - failed_checks,
        "failed_count": failed_checks,
        "expected_record_count": comparisons["record_count"][0],
        "actual_record_count": comparisons["record_count"][1],
        "expected_record_content_sha256": comparisons["record_content_sha256"][0],
        "actual_record_content_sha256": comparisons["record_content_sha256"][1],
        "expected_explicit_lexical_tuple_count": comparisons[
            "explicit_lexical_tuple_count"
        ][0],
        "actual_explicit_lexical_tuple_count": comparisons[
            "explicit_lexical_tuple_count"
        ][1],
        "actual_explicit_lexical_term_count": int(
            metrics["explicit_lexical_term_count"]
        ),
        "expected_explicit_lexical_tuples_sha256": comparisons[
            "explicit_lexical_tuples_sha256"
        ][0],
        "actual_explicit_lexical_tuples_sha256": comparisons[
            "explicit_lexical_tuples_sha256"
        ][1],
        "expected_search_profile_alias_tuple_count": comparisons[
            "search_profile_alias_tuple_count"
        ][0],
        "actual_search_profile_alias_tuple_count": comparisons[
            "search_profile_alias_tuple_count"
        ][1],
        "actual_search_profile_alias_term_count": int(
            metrics["search_profile_alias_term_count"]
        ),
        "expected_search_profile_alias_tuples_sha256": comparisons[
            "search_profile_alias_tuples_sha256"
        ][0],
        "actual_search_profile_alias_tuples_sha256": comparisons[
            "search_profile_alias_tuples_sha256"
        ][1],
        "expected_noncanonical_id_alias_count": comparisons[
            "noncanonical_id_alias_count"
        ][0],
        "actual_noncanonical_id_alias_count": comparisons[
            "noncanonical_id_alias_count"
        ][1],
        "coverage_complete": True,
        "skipped": 0,
        "errors": errors,
    }


SUITE_RUNNERS: dict[
    str,
    Callable[[Mapping[str, Any], Any, str, Mapping[str, Any]], dict[str, Any]],
] = {
    "search_regression": _search_suite,
    "sparse_discovery": _sparse_suite,
    "tier_strategy": _tier_suite,
    "style_family": _style_suite,
    "quality": _quality_suite,
    "reference_corpus": _corpus_suite,
    "preservation": _preservation_suite,
}


def _base_report(
    pack_root: Path, state_file: Path, cache_dir: Path, managed_root: Path
) -> dict[str, Any]:
    return {
        "ok": False,
        "pack": {"root": str(pack_root)},
        "runtime": {
            "state_file": str(state_file),
            "cache_dir": str(cache_dir),
            "managed_root": str(managed_root),
            "ambient_roots_allowed": False,
        },
        "checks": {},
        "contract": {"resource": CONTRACT_RESOURCE, "declared": False},
        "suites": {},
        "declared_suite_count": 0,
        "executed_suite_count": 0,
        "skipped": 0,
        "errors": [],
        "warnings": [],
    }


def run_release_gate(
    pack_root: Path,
    *,
    state_file: Path,
    cache_dir: Path,
    managed_root: Path,
) -> dict[str, Any]:
    """Execute the complete gate for one explicit pack runtime."""
    pack_root = pack_root.resolve()
    state_file = state_file.resolve()
    cache_dir = cache_dir.resolve()
    managed_root = managed_root.resolve()
    output = _base_report(pack_root, state_file, cache_dir, managed_root)
    errors: list[str] = output["errors"]

    if not pack_root.is_dir():
        errors.append(f"pack directory does not exist: {pack_root}")
    if not state_file.is_file():
        errors.append(f"explicit state file does not exist: {state_file}")
    if not managed_root.is_dir():
        errors.append(f"explicit managed root does not exist: {managed_root}")
    if _is_within(state_file, pack_root):
        errors.append("state file must be outside the released pack directory")
    if _is_within(cache_dir, pack_root):
        errors.append("cache directory must be outside the released pack directory")
    if _is_within(managed_root, pack_root):
        errors.append("managed root must be outside the released pack directory")
    if errors:
        return output

    validation = validate_pack(pack_root, require_lock=True, verify_lock=True)
    validation_data = validation.to_dict()
    output["checks"]["released_pack"] = validation_data
    output["pack"].update(
        {
            "pack_id": validation.pack_id,
            "release": validation.release,
            "record_count": len(validation.records),
            "resource_file_count": len(validation.resource_files),
            "resource_binding_count": len(validation.resource_bindings),
        }
    )
    project_owned = is_project_pack(pack_root, validation.manifest)
    if not validation.valid or (not validation.lock_present and not project_owned) or not validation.pack_id:
        errors.extend(
            f"released pack: {item['code']}: {item['message']}"
            for item in validation_data.get("errors") or []
        )
        if not validation.lock_present and not project_owned:
            errors.append("released pack is missing pack.lock.json")
        if not errors:
            errors.append("released pack validation failed")
        return output

    try:
        lock = build_lock_data(pack_root) if project_owned else _load_json_object(pack_root / "pack.lock.json", "pack.lock.json")
        output["pack"]["integrity_policy"] = "core-managed-live-inventory" if project_owned else "released-pack-lock"
    except ValueError as exc:
        errors.append(str(exc))
        return output
    output["pack"].update(
        {
            "inventory_file_count": len(lock.get("files") or []),
            "locked_file_count": None if project_owned else len(lock.get("files") or []),
            "inventory_content_sha256": lock.get("content_sha256"),
            "locked_content_sha256": None if project_owned else lock.get("content_sha256"),
        }
    )

    metrics = authored_metrics(validation)
    output["pack"]["authored_metrics"] = metrics
    pack_id = str(validation.pack_id)
    try:
        state = load_state(state_file)
    except Exception as exc:  # PackError plus malformed external inputs
        errors.append(f"explicit state is invalid: {exc}")
        return output
    expected_root = os.path.normcase(str(pack_root))
    actual_roots = [os.path.normcase(str(Path(value).resolve())) for value in state["pack_roots"]]
    if actual_roots != [expected_root]:
        errors.append(
            "explicit state pack_roots must contain exactly the positional pack directory"
        )
    if state["enabled_packs"] != [pack_id]:
        errors.append("explicit state enabled_packs must contain exactly the positional pack ID")
    expected_providers = {
        name: pack_id for name in sorted(validation.resource_bindings)
    }
    if state["resource_providers"] != expected_providers:
        missing = sorted(set(expected_providers) - set(state["resource_providers"]))
        extra = sorted(set(state["resource_providers"]) - set(expected_providers))
        wrong = sorted(
            name
            for name in set(expected_providers) & set(state["resource_providers"])
            if state["resource_providers"][name] != pack_id
        )
        errors.append(
            "explicit state must select the positional pack for every and only its named "
            f"resources; missing={missing}, extra={extra}, wrong_provider={wrong}"
        )
    if errors:
        return output

    settings = PackSettings(
        roots=(pack_root,),
        state_file=state_file,
        cache_dir=cache_dir,
        managed_root=managed_root,
        quarantine_root=(managed_root / ".quarantine").resolve(),
        default_enabled_packs=(),
        default_resource_providers=(),
    )
    configure_pack_runtime(settings)
    try:
        try:
            refresh = refresh_cache(settings, force=True)
            status = cache_status(settings)
            catalog = load_pack_catalog()
        except Exception as exc:
            errors.append(f"exact runtime cache failed: {exc}")
            return output

        error_diagnostics = [
            item
            for item in catalog.diagnostics
            if str(item.get("severity") or "error") == "error"
        ]
        source_pack_ids = sorted({entry.source_pack for entry in catalog.entries})
        resource_pack_ids = sorted({item.source_pack for item in catalog.resources.values()})
        cache_check = {
            "ok": False,
            "fresh": status.get("fresh") is True,
            "active_pack_count": catalog.active_pack_count,
            "enabled_pack_ids": status.get("enabled_packs") or [],
            "available_enabled_pack_ids": status.get("available_enabled_packs") or [],
            "record_count": len(catalog.entries),
            "named_resource_count": len(catalog.resources),
            "record_source_pack_ids": source_pack_ids,
            "resource_source_pack_ids": resource_pack_ids,
            "diagnostic_count": len(catalog.diagnostics),
            "error_diagnostic_count": len(error_diagnostics),
            "discovery_issue_count": len(status.get("discovery_issues") or []),
            "cache_path": status.get("cache_path"),
            "rebuilt": refresh.get("rebuilt") is True,
        }
        cache_errors: list[str] = []
        if catalog.active_pack_count != 1:
            cache_errors.append("runtime cache does not contain exactly one active pack")
        if status.get("enabled_packs") != [pack_id]:
            cache_errors.append("runtime cache enabled-pack state is not exact")
        if status.get("available_enabled_packs") != [pack_id]:
            cache_errors.append("runtime cache available-pack state is not exact")
        if source_pack_ids not in ([], [pack_id]):
            cache_errors.append("runtime cache contains records from another pack")
        if len(catalog.entries) != len(validation.records):
            cache_errors.append(
                "runtime cache record count differs from the locked pack: "
                f"{len(catalog.entries)} != {len(validation.records)}"
            )
        if resource_pack_ids not in ([], [pack_id]):
            cache_errors.append("runtime cache contains resources from another pack")
        if len(catalog.resources) != len(validation.resource_bindings):
            cache_errors.append(
                "runtime cache named-resource count differs from the locked pack bindings"
            )
        if error_diagnostics:
            cache_errors.append(
                f"runtime cache contains {len(error_diagnostics)} error diagnostics"
            )
        if status.get("discovery_issues"):
            cache_errors.append("runtime cache reported pack discovery issues")
        if status.get("fresh") is not True:
            cache_errors.append("runtime cache is not fresh")
        cache_check["errors"] = cache_errors
        cache_check["ok"] = not cache_errors
        output["checks"]["runtime_cache"] = cache_check
        errors.extend(f"runtime cache: {message}" for message in cache_errors)
        if cache_errors:
            return output

        contract_resource = catalog.resources.get(CONTRACT_RESOURCE)
        declared_eval_resources = sorted(
            DECLARED_EVALUATION_RESOURCES & set(validation.resource_bindings)
        )
        if contract_resource is None:
            if project_owned:
                # Commons is released with the project, not as a separately
                # licensed/locked pack. Its taxonomy is runtime policy; the
                # core gate owns its quality and regression evaluation.
                output["scope"] = "core-managed-pack-structure"
                output["release_authorized"] = False
                output["contract"].update({
                    "declared": False, "owner": "core-release-gate",
                    "check_command": "python scripts/validate.py",
                    "declared_evaluation_resources": declared_eval_resources,
                    "note": "Structural and live-inventory checks only; core release validation is still required.",
                })
                output["ok"] = not errors
                return output
            if declared_eval_resources:
                errors.append(
                    "pack declares evaluation resources but has no pack-owned "
                    f"{CONTRACT_RESOURCE!r} binding: {declared_eval_resources}"
                )
            output["contract"].update(
                {
                    "declared": False,
                    "declared_evaluation_resources": declared_eval_resources,
                }
            )
            output["ok"] = not errors
            return output

        try:
            contract_path = _resource_path(catalog, CONTRACT_RESOURCE, pack_id)
            contract = _load_json_object(contract_path, CONTRACT_RESOURCE)
        except ValueError as exc:
            errors.append(str(exc))
            return output
        contract_errors = validate_release_contract(contract)
        output["contract"].update(
            {
                "declared": True,
                "path": str(contract_path),
                "suite_names": sorted(contract),
                "errors": contract_errors,
            }
        )
        errors.extend(f"release evaluation contract: {message}" for message in contract_errors)

        expected_declared_suites = {
            suite
            for suite, resource_name in SUITE_RESOURCE_NAMES.items()
            if resource_name in validation.resource_bindings
        }
        missing_contract_suites = sorted(expected_declared_suites - set(contract))
        if missing_contract_suites:
            errors.append(
                "release evaluation contract omits suites declared by named resources: "
                f"{missing_contract_suites}"
            )
        if "tier_strategy" in contract and TIER_BASELINE_RESOURCE not in validation.resource_bindings:
            errors.append(
                f"tier_strategy requires the pack-owned {TIER_BASELINE_RESOURCE!r} binding"
            )
        required_quality_resources = {"archetype-policy", "negative-policy", "project-defaults"}
        if "quality" in contract:
            missing_quality = sorted(
                required_quality_resources - set(validation.resource_bindings)
            )
            if missing_quality:
                errors.append(
                    "quality suite requires named resources missing from the pack: "
                    f"{missing_quality}"
                )
        output["declared_suite_count"] = len(contract)
        if errors:
            return output

        for suite_name in sorted(contract):
            runner = SUITE_RUNNERS[suite_name]
            try:
                suite_report = runner(contract[suite_name], catalog, pack_id, metrics)
            except (Exception, SystemExit) as exc:
                suite_report = {
                    "ok": False,
                    "coverage_complete": False,
                    "skipped": 0,
                    "errors": [f"suite raised {type(exc).__name__}: {exc}"],
                }
            suite_report["executed"] = True
            output["suites"][suite_name] = suite_report
            if suite_report.get("ok") is not True:
                errors.append(f"declared suite failed: {suite_name}")
            if suite_report.get("coverage_complete") is not True:
                errors.append(f"declared suite has incomplete coverage: {suite_name}")
            if int(suite_report.get("skipped") or 0) != 0:
                errors.append(f"declared suite skipped work: {suite_name}")
        output["executed_suite_count"] = len(output["suites"])
        if output["executed_suite_count"] != output["declared_suite_count"]:
            errors.append("not every declared evaluation suite executed")
        output["skipped"] = sum(
            int(row.get("skipped") or 0) for row in output["suites"].values()
        )
        output["ok"] = not errors and output["skipped"] == 0
        return output
    finally:
        configure_pack_runtime(None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one released pack's complete pack-owned evaluation contract"
    )
    parser.add_argument("pack", type=Path, help="Exact released pack directory")
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--managed-root", type=Path, required=True)
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args(argv)
    if args.report_out and _is_within(args.report_out.resolve(), args.pack.resolve()):
        parser.error("--report-out must be outside the released pack directory")
    report = run_release_gate(
        args.pack,
        state_file=args.state_file,
        cache_dir=args.cache_dir,
        managed_root=args.managed_root,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report_out:
        args.report_out.resolve().write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
