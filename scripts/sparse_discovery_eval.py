#!/usr/bin/env python3
"""Evaluate sparse-brief discovery without relying on record names or IDs in queries."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from catalog_cli import (  # noqa: E402
    clear_runtime_caches,
    configure_pack_runtime,
    load_entries,
    load_search_index,
    named_resource_path,
    recommend,
    search_entries,
)
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime  # noqa: E402
from search_discovery import CatalogQueryInput, analyze_query, catalog_query_from_mapping  # noqa: E402

CASES_RESOURCE = "sparse-discovery-evaluation"
REPORT_PATH = ROOT / "sparse-discovery-report.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_expected(actual: Mapping[str, Sequence[str]], expected: Mapping[str, Sequence[str]]) -> list[str]:
    failures: list[str] = []
    for facet, values in expected.items():
        actual_values = set(actual.get(facet) or [])
        for value in values:
            if value not in actual_values:
                failures.append(f"missing anchor {facet}={value}; got {sorted(actual_values)}")
    return failures


def _request_for_case(case: Mapping[str, Any]) -> CatalogQueryInput:
    payload = case.get("query_request")
    if isinstance(payload, Mapping):
        return catalog_query_from_mapping(payload)
    return CatalogQueryInput(
        canonical_query=str(case.get("query") or ""),
        domain=str(case.get("domain") or "").strip() or None,
    )


def _analysis_for_request(request: CatalogQueryInput, index: Any):
    return analyze_query(
        request.canonical_query,
        index,
        request.domain,
        explicit_anchors=request.anchors,
        source_brief=request.source_brief,
        source_language=request.source_language,
        unresolved_terms=request.unresolved_terms,
    )


def _missing_expected_ids(
    case: Mapping[str, Any],
    available_ids: set[str],
) -> list[str]:
    required = {
        str(value)
        for key in ("expected_top_ids", "expected_candidate_ids")
        for value in case.get(key) or []
    }
    alternatives = {str(value) for value in case.get("expected_any_top_ids") or []}
    missing = required - available_ids
    if alternatives and not (alternatives & available_ids):
        missing.update(alternatives)
    return sorted(missing)


def evaluate() -> dict[str, Any]:
    # Do not inherit another suite's indexed-entry graph when several checks
    # execute in one Python process.
    clear_runtime_caches()
    cases_path = named_resource_path(CASES_RESOURCE)
    assert cases_path is not None
    data = load_json(cases_path)
    entries = load_entries()
    index = load_search_index()
    details: list[dict[str, Any]] = []
    all_failures: list[str] = []
    all_cases = data.get("cases", [])
    available_ids = {str(entry.record["id"]) for entry in entries}
    missing_expected_ids: dict[str, list[str]] = {}

    for case in all_cases:
        cid = str(case.get("id") or "unnamed")
        mode = str(case.get("mode") or "")
        request = _request_for_case(case)
        query = request.canonical_query
        domain = request.domain
        failures: list[str] = []
        observed: dict[str, Any] = {}
        absent = _missing_expected_ids(case, available_ids)
        if absent:
            missing_expected_ids[cid] = absent
            failures.append(f"active catalog is missing expected IDs {absent}")

        if mode == "analyze":
            analysis = _analysis_for_request(request, index)
            observed = analysis.to_dict()
            failures.extend(_contains_expected(analysis.anchors, case.get("expected_anchors") or {}))
            for facet in case.get("forbidden_anchor_facets") or []:
                if analysis.anchors.get(str(facet)):
                    failures.append(f"unexpected anchor facet {facet}: {analysis.anchors.get(str(facet))}")
            expected_unmatched = [str(value) for value in case.get("expected_terms_without_alias") or []]
            if expected_unmatched != analysis.terms_without_alias:
                failures.append(
                    f"unmatched terms {analysis.terms_without_alias} != expected {expected_unmatched}"
                )

        elif mode == "search":
            analysis = _analysis_for_request(request, index)
            results = search_entries(
                entries,
                query,
                kinds={str(value) for value in case.get("kinds") or []},
                categories={str(value) for value in case.get("categories") or []},
                domain=str(domain) if domain else None,
                limit=int(case.get("limit", 5)),
                diverse=bool(case.get("diverse", False)),
                tier=str(case.get("tier") or "any"),
                group_variants=bool(case.get("group_variants", True)),
                search_index=index,
                analysis=analysis,
            )
            result_ids = [str(row.get("id")) for row in results]
            observed = {
                "query_analysis": analysis.to_dict(),
                "result_ids": result_ids,
                "first_related_variants": (results[0].get("related_variants") or []) if results else [],
            }
            failures.extend(_contains_expected(analysis.anchors, case.get("expected_anchors") or {}))
            expected_top = [str(value) for value in case.get("expected_top_ids") or []]
            if expected_top and result_ids[:len(expected_top)] != expected_top:
                failures.append(f"top IDs {result_ids[:len(expected_top)]} != expected {expected_top}")
            expected_any = {str(value) for value in case.get("expected_any_top_ids") or []}
            if expected_any and (not result_ids or result_ids[0] not in expected_any):
                failures.append(f"first result {result_ids[:1]} is not one of {sorted(expected_any)}")
            minimum_related = int(case.get("minimum_related_variants_on_first", 0))
            if minimum_related and (not results or len(results[0].get("related_variants") or []) < minimum_related):
                failures.append(f"first result has fewer than {minimum_related} related variants")

        elif mode == "recommend":
            analysis_object = _analysis_for_request(request, index)
            result = recommend(
                entries, query, str(domain) if domain else None,
                int(case.get("limit", 8)), analysis=analysis_object, search_index=index,
            )
            analysis = result.get("query_analysis") or {}
            anchors = analysis.get("normalized_anchors") or {}
            candidates = result.get("candidates") or []
            candidate_ids = [str(row.get("id")) for row in candidates]
            inventory = result.get("catalog_inventory") or {}
            observed = {
                "query_analysis": analysis,
                "candidate_ids": candidate_ids,
                "inventory_categories": sorted(inventory.get("categories") or {}),
                "inspection_queue": result.get("inspection_queue"),
                "terms_without_alias": result.get("terms_without_alias"),
            }
            failures.extend(_contains_expected(anchors, case.get("expected_anchors") or {}))
            expected = {str(value) for value in case.get("expected_candidate_ids") or []}
            missing = sorted(expected - set(candidate_ids))
            if missing:
                failures.append(f"missing candidate IDs {missing}; got {candidate_ids}")
            expected_top = [str(value) for value in case.get("expected_top_ids") or []]
            if expected_top and candidate_ids[:len(expected_top)] != expected_top:
                failures.append(f"top IDs {candidate_ids[:len(expected_top)]} != expected {expected_top}")
            forbidden = {str(value) for value in case.get("forbidden_candidate_ids") or []}
            overlap = sorted(forbidden & set(candidate_ids))
            if overlap:
                failures.append(f"forbidden candidate IDs returned: {overlap}")
            minimum = int(case.get("minimum_candidates", 0))
            if len(candidates) < minimum:
                failures.append(f"only {len(candidates)} candidates; expected at least {minimum}")
            expected_count = case.get("expected_candidate_count")
            if expected_count is not None and len(candidates) != int(expected_count):
                failures.append(f"candidate count {len(candidates)} != expected {expected_count}")
            required_categories = {str(value) for value in case.get("expected_inventory_categories") or []}
            missing_categories = sorted(required_categories - set(inventory.get("categories") or {}))
            if missing_categories:
                failures.append(f"inventory lacks categories {missing_categories}")
            required_facets = {str(value) for value in case.get("expected_inventory_facets") or []}
            missing_facets = sorted(required_facets - set(inventory.get("facets") or {}))
            if missing_facets:
                failures.append(f"inventory lacks authored facets {missing_facets}")
            required_fields = [str(value) for value in case.get("required_candidate_fields") or []]
            for candidate in candidates:
                missing_fields = [field for field in required_fields if not candidate.get(field)]
                if missing_fields:
                    failures.append(f"candidate {candidate.get('id')} lacks fields {missing_fields}")
            if result.get("inspection_queue") != candidate_ids:
                failures.append("inspection queue differs from returned candidate IDs")

        else:
            failures.append(f"unknown mode: {mode}")

        observed_analysis = observed.get("query_analysis") if isinstance(observed, dict) else None
        if mode == "recommend":
            observed_analysis = result.get("query_analysis") if isinstance(result, dict) else None
        elif mode == "analyze":
            observed_analysis = observed
        if isinstance(observed_analysis, Mapping):
            expected_source = case.get("expected_source_brief")
            if expected_source is not None and observed_analysis.get("source_brief") != expected_source:
                failures.append("source_brief was not preserved verbatim")
            expected_language = case.get("expected_source_language")
            if expected_language is not None and observed_analysis.get("source_language") != expected_language:
                failures.append("source_language metadata was not preserved")

        ok = not failures
        details.append({"id": cid, "mode": mode, "ok": ok, "failures": failures, "observed": observed})
        all_failures.extend(f"{cid}: {failure}" for failure in failures)

    return {
        "ok": not all_failures,
        "case_count": len(details),
        "total_case_count": len(all_cases),
        "coverage_complete": len(details) == len(all_cases),
        "missing_expected_ids": missing_expected_ids,
        "passed": sum(1 for row in details if row["ok"]),
        "failed": sum(1 for row in details if not row["ok"]),
        "failures": all_failures,
        "cases": details,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description="Evaluate sparse-brief record discovery")
    add_pack_runtime_arguments(parser)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    runtime_context = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime_context.settings)
    try:
        report = evaluate()
        if not args.no_write:
            REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    finally:
        configure_pack_runtime(None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
