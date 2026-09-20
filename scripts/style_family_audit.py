#!/usr/bin/env python3
"""Audit concrete style-family taxonomy boundaries.

This validator checks structural evidence and separation of responsibilities. It
cannot prove artistic quality, but it can prevent scene nouns from silently
becoming canonical family IDs and prevent undocumented family boundary changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from catalog_cli import configure_pack_runtime, load_entries, named_resource_path
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "style-family-audit.json"

RECURRING_AXES = {
    "line",
    "form",
    "shadow_and_value",
    "highlight",
    "color",
    "surface",
    "background",
    "detail_hierarchy",
}
REVISED_STATUSES = {"revised-and-generalized", "new"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    taxonomy_path = named_resource_path("style-family-taxonomy")
    assert taxonomy_path is not None
    families = [
        entry.record
        for entry in load_entries()
        if entry.kind == "style-family"
    ]
    taxonomy = load_json(taxonomy_path)
    family_ids = [str(row.get("id") or "") for row in families]
    family_id_set = set(family_ids)

    if len(family_ids) != len(family_id_set):
        errors.append("enabled style-family records contain duplicate IDs")

    taxonomy_rows = [row for row in taxonomy.get("families", []) if isinstance(row, Mapping)]
    taxonomy_ids = [str(row.get("family_id") or "") for row in taxonomy_rows]
    if taxonomy.get("count") != len(taxonomy_rows):
        errors.append("style-family-taxonomy.json count is stale")
    if len(taxonomy_ids) != len(set(taxonomy_ids)):
        errors.append("style-family-taxonomy.json contains duplicate family_id values")
    missing_rows = sorted(family_id_set - set(taxonomy_ids))
    extra_rows = sorted(set(taxonomy_ids) - family_id_set)
    if missing_rows:
        errors.append(f"canonical style families missing taxonomy rows: {missing_rows}")
    if extra_rows:
        errors.append(f"taxonomy rows target noncanonical families: {extra_rows}")

    by_id = {str(row.get("family_id") or ""): row for row in taxonomy_rows}
    for family_id in sorted(family_id_set & set(by_id)):
        row = by_id[family_id]
        status = str(row.get("status") or "")
        if status not in {"retained", "revised-and-generalized", "new"}:
            errors.append(f"{family_id}: unknown taxonomy status `{status}`")
        axes = {str(value) for value in row.get("recurring_axes") or []}
        if len(axes & RECURRING_AXES) < 6:
            errors.append(f"{family_id}: taxonomy needs at least six recurring visual axes")
        excluded = [str(value).strip() for value in row.get("excluded_scene_attributes") or [] if str(value).strip()]
        if len(excluded) < 2:
            errors.append(f"{family_id}: taxonomy needs at least two excluded scene attributes")
        if not str(row.get("boundary") or "").strip():
            errors.append(f"{family_id}: taxonomy lacks nearest-family boundary")
        evidence = [str(value).strip() for value in row.get("evidence_basis") or [] if str(value).strip()]
        if status in REVISED_STATUSES and len(evidence) < 3:
            errors.append(f"{family_id}: revised/new family needs at least three evidence items")
        if status in REVISED_STATUSES and len(str(row.get("review_notes") or "").split()) < 8:
            errors.append(f"{family_id}: review_notes are too short")

    deferred = taxonomy.get("deferred_candidates") or []
    if not isinstance(deferred, list):
        errors.append("style-family-taxonomy.json deferred_candidates must be an array")
        deferred = []
    for row in deferred:
        if not isinstance(row, Mapping):
            errors.append("deferred style-family candidate must be an object")
            continue
        if str(row.get("decision") or "") != "deferred-not-canonical":
            errors.append("deferred candidate must state decision deferred-not-canonical")
        if not str(row.get("evidence_gap") or "").strip():
            errors.append("deferred candidate must document the evidence gap")
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id and candidate_id in family_id_set:
            errors.append(f"deferred candidate is also canonical: {candidate_id}")

    return {
        "audit": "style-family-taxonomy",
        "ok": not errors,
        "family_count": len(families),
        "revised_family_count": sum(1 for row in taxonomy_rows if row.get("status") in REVISED_STATUSES),
        "revised_or_new_family_count": sum(1 for row in taxonomy_rows if row.get("status") in REVISED_STATUSES),
        "retained_family_count": sum(1 for row in taxonomy_rows if row.get("status") == "retained"),
        "deferred_candidate_count": len(deferred),
        "errors": errors,
        "warnings": warnings,
        "quality_claim": "none; this audit checks taxonomy evidence structure, not artistic merit",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit style-family taxonomy boundaries")
    add_pack_runtime_arguments(parser)
    parser.add_argument("root", nargs="?", default=str(ROOT))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    runtime_context = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime_context.settings)
    try:
        report = audit(root)
        if args.write:
            (root / REPORT_PATH.name).write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
    finally:
        configure_pack_runtime(None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
