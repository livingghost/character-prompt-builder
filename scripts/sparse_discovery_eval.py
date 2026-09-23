#!/usr/bin/env python3
"""Evaluate sparse-brief discovery without relying on preset names or IDs in queries."""
from __future__ import annotations

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
        for key in ("expected_top_ids", "expected_identity_top_ids")
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
                int(case.get("directions", 4)), analysis=analysis_object,
            )
            analysis = result.get("query_analysis") or {}
            anchors = analysis.get("normalized_anchors") or {}
            identities = [str(row.get("id")) for row in result.get("identity_candidates") or []]
            cards = result.get("direction_cards") or []
            lane_ids = [str(card.get("id")) for card in cards]
            style_ids = {
                str((card.get("preset_ids") or {}).get("style_family"))
                for card in cards
                if (card.get("preset_ids") or {}).get("style_family")
            }
            observed = {
                "canonical_query": analysis.get("canonical_query"),
                "source_brief": analysis.get("source_brief"),
                "source_language": analysis.get("source_language"),
                "anchors": anchors,
                "identity_ids": identities,
                "lane_ids": lane_ids,
                "style_family_ids": sorted(style_ids),
            }
            failures.extend(_contains_expected(anchors, case.get("expected_anchors") or {}))
            expected_identity = [str(value) for value in case.get("expected_identity_top_ids") or []]
            if expected_identity and identities[:len(expected_identity)] != expected_identity:
                failures.append(f"top identity IDs {identities[:len(expected_identity)]} != expected {expected_identity}")
            forbidden = {str(value) for value in case.get("forbidden_identity_ids") or []}
            overlap = forbidden & set(identities)
            if overlap:
                failures.append(f"forbidden identity IDs returned: {sorted(overlap)}")
            expected_lanes = [str(value) for value in case.get("expected_lane_ids") or []]
            if expected_lanes and lane_ids != expected_lanes:
                failures.append(f"lane IDs {lane_ids} != expected {expected_lanes}")
            required_lanes = {str(value) for value in case.get("required_lane_ids") or []}
            missing_lanes = sorted(required_lanes - set(lane_ids))
            if missing_lanes:
                failures.append(f"required lane IDs are missing: {missing_lanes}; got {lane_ids}")
            minimum_styles = int(case.get("minimum_distinct_style_families", 0))
            if len(style_ids) < minimum_styles:
                failures.append(f"only {len(style_ids)} distinct style families; expected {minimum_styles}")
            required_keys = [str(value) for value in case.get("required_preset_ids_per_card") or []]
            required_fields = [str(value) for value in case.get("required_fields_per_card") or []]
            forbidden_card_ids = {str(value) for value in case.get("forbidden_card_preset_ids") or []}
            for card in cards:
                missing = [key for key in required_keys if key not in (card.get("preset_ids") or {})]
                if missing:
                    failures.append(f"card {card.get('id')} lacks preset IDs: {missing}")
                missing_fields = [field for field in required_fields if not card.get(field)]
                if missing_fields:
                    failures.append(f"card {card.get('id')} lacks fields: {missing_fields}")
                selected_ids = {str(value) for value in (card.get("preset_ids") or {}).values()}
                forbidden_overlap = forbidden_card_ids & selected_ids
                if forbidden_overlap:
                    failures.append(
                        f"card {card.get('id')} contains forbidden preset IDs: {sorted(forbidden_overlap)}"
                    )

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
    parser = argparse.ArgumentParser(description="Evaluate sparse-brief preset discovery")
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
    raise SystemExit(main())
