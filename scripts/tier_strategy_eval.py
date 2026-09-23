#!/usr/bin/env python3
"""Prepare retrieval packets for tier-strategy prompt/image evaluation.

This script does not write prompts, generate images, or score artistic quality.
It freezes retrieval evidence for no-preset, broad-role (`any`), and
curated-only atomic conditions while keeping the same universal-core,
domain-realization, and rendering-profile candidate limits.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from catalog_cli import configure_pack_runtime, inspire, load_entries, named_resource_path
from pack_runtime_cli import (
    add_pack_runtime_arguments,
    has_pack_runtime_arguments,
    resolve_pack_runtime,
)

REQUIRED_FIELDS = {
    "id", "brief", "domain", "query", "categories", "per_category",
    "profile_limit", "core_limit", "realization_limit", "evaluation_focus",
}
TIER_STRATEGY_CASES_RESOURCE = "tier-strategy-evaluation-cases"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"line {line_number}: case must be an object")
        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            raise ValueError(f"line {line_number}: missing fields {missing}")
        if not isinstance(item["categories"], list) or not item["categories"]:
            raise ValueError(f"line {line_number}: categories must be a non-empty list")
        if not isinstance(item["evaluation_focus"], list) or not item["evaluation_focus"]:
            raise ValueError(f"line {line_number}: evaluation_focus must be a non-empty list")
        for field in ("per_category", "profile_limit", "core_limit", "realization_limit"):
            if not isinstance(item[field], int) or item[field] < 0:
                raise ValueError(f"line {line_number}: {field} must be a non-negative integer")
        cases.append(item)
    ids = [str(item["id"]) for item in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("tier-strategy case IDs must be unique")
    if not cases:
        raise ValueError("tier-strategy case set is empty")
    return cases


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    categories = result.get("categories", {})
    records = [item for values in categories.values() for item in values]
    return {
        "populated_categories": sum(1 for values in categories.values() if values),
        "atomic_candidates": len(records),
        "strong_atomic_candidates": sum(1 for item in records if item.get("relevance") == "strong"),
        "curated_atomic_candidates": sum(1 for item in records if item.get("tier") == "curated"),
        "vocabulary_atomic_candidates": sum(1 for item in records if item.get("tier") == "vocabulary"),
        "aesthetic_core_candidates": len(result.get("aesthetic_cores", [])),
        "style_family_candidates": len(result.get("style_families", [])),
        "domain_realization_candidates": len(result.get("domain_realizations", [])),
        "render_profile_candidates": len(result.get("render_profiles", [])),
    }


def build_packet(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    entries = load_entries()
    output_cases: list[dict[str, Any]] = []
    for case in cases:
        kwargs = {
            "entries": entries,
            "query": str(case["query"]),
            "categories": list(case["categories"]),
            "domain": str(case["domain"]),
            "per_category": int(case["per_category"]),
            "profile_limit": int(case["profile_limit"]),
            "core_limit": int(case["core_limit"]),
            "style_family_limit": int(case.get("style_family_limit", 3)),
            "realization_limit": int(case["realization_limit"]),
        }
        broad = inspire(tier="any", **kwargs)
        curated = inspire(tier="curated", **kwargs)
        output_cases.append({
            "id": case["id"],
            "brief": case["brief"],
            "domain": case["domain"],
            "art_direction_query": case["query"],
            "evaluation_focus": case["evaluation_focus"],
            "conditions": {
                "no-preset": {
                    "instruction": (
                        "Do not query or use the preset catalog. Keep the same image promise, "
                        "art direction, subject-domain interpretation, and medium choice."
                    ),
                    "retrieval": None,
                },
                "any": {
                    "instruction": (
                        "Use broad atomic retrieval and apply each result according to its curated "
                        "or vocabulary role. The art direction remains authoritative. Use at most "
                        "one relevant universal aesthetic core, the matching domain realization, "
                        "and at most one compatible curated rendering profile."
                    ),
                    "retrieval": broad,
                    "diagnostics": summarize(broad),
                },
                "curated": {
                    "instruction": (
                        "Use curated-only atomic retrieval. The art direction remains authoritative. "
                        "Use at most one relevant universal aesthetic core, the matching domain "
                        "realization, and at most one compatible curated rendering profile."
                    ),
                    "retrieval": curated,
                    "diagnostics": summarize(curated),
                },
            },
            "result_slots": {
                "no-preset": {"prompt": None, "negative_prompt": None, "image_files": [], "scores": None},
                "any": {"prompt": None, "negative_prompt": None, "image_files": [], "scores": None},
                "curated": {"prompt": None, "negative_prompt": None, "image_files": [], "scores": None},
            },
        })
    return {
        "purpose": "Preparation packet for blind final-prompt and image comparison across atomic retrieval strategies.",
        "quality_claim": "none; retrieval coverage is diagnostic only",
        "conditions": ["no-preset", "any", "curated"],
        "case_count": len(output_cases),
        "cases": output_cases,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare tier-strategy retrieval packets; does not score art.")
    add_pack_runtime_arguments(parser)
    parser.add_argument(
        "--cases",
        type=Path,
        help="Explicit cases file for catalog-independent --validate-only mode",
    )
    parser.add_argument("--out")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    if args.validate_only:
        if has_pack_runtime_arguments(args):
            parser.error("pack runtime arguments are not accepted with catalog-independent --validate-only")
        if args.cases is None:
            parser.error("--validate-only requires an explicit --cases path")
        cases = load_cases(args.cases.resolve())
        report = {"ok": True, "case_count": len(cases)}
    else:
        if args.cases is not None:
            parser.error(
                "--cases is only valid with --validate-only; packet mode uses the active "
                f"pack resource {TIER_STRATEGY_CASES_RESOURCE!r}"
            )
        runtime_context = resolve_pack_runtime(parser, args)
        configure_pack_runtime(runtime_context.settings)
        try:
            cases_path = named_resource_path(TIER_STRATEGY_CASES_RESOURCE)
            assert cases_path is not None
            report = build_packet(load_cases(cases_path))
        finally:
            configure_pack_runtime(None)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
