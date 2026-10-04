#!/usr/bin/env python3
"""Audit the boundary evidence that every enabled style-family record carries.

Each style-family record states its review status, evidence, recurring finish
axes, excluded scene attributes, nearest family and boundary. The audit reads
the families of every enabled pack together, so a nearest family may live in
another pack. It checks evidence structure; the author judges artistic quality.
"""
from __future__ import annotations
import operation_context as _operation_context

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from catalog_cli import configure_pack_runtime, load_entries
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
STATUSES = {"retained", "revised-and-generalized", "new"}
REVISED_STATUSES = {"revised-and-generalized", "new"}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def audit(root: Path = ROOT) -> dict[str, Any]:
    """Audit the style-family records of the configured pack runtime.

    ``root`` names the product tree that ``--write`` writes the report into;
    the records come from the active catalog.
    """
    del root
    errors: list[str] = []
    warnings: list[str] = []
    families = [entry.record for entry in load_entries() if entry.kind == "style-family"]
    family_ids = [str(record.get("id") or "") for record in families]
    family_id_set = set(family_ids)
    if len(family_ids) != len(family_id_set):
        errors.append("enabled style-family records contain duplicate IDs")

    deferred_count = 0
    for record in families:
        family_id = str(record.get("id") or "")
        status = str(record.get("status") or "")
        if status not in STATUSES:
            errors.append(f"{family_id}: unknown status `{status}`")
        axes = set(_strings(record.get("recurring_axes"))) & RECURRING_AXES
        if len(axes) < 6:
            errors.append(f"{family_id}: needs at least six recurring visual axes")
        if len(_strings(record.get("excluded_scene_attributes"))) < 2:
            errors.append(f"{family_id}: needs at least two excluded scene attributes")
        nearest = str(record.get("nearest_family") or "")
        if nearest == family_id or nearest not in family_id_set:
            errors.append(
                f"{family_id}: nearest_family `{nearest}` is not another enabled style family"
            )
        if not str(record.get("boundary") or "").strip():
            errors.append(f"{family_id}: lacks a nearest-family boundary")
        if status in REVISED_STATUSES:
            if len(_strings(record.get("evidence_basis"))) < 3:
                errors.append(f"{family_id}: a revised or new family needs at least three evidence items")
            if len(str(record.get("review_notes") or "").split()) < 8:
                errors.append(f"{family_id}: review_notes need at least eight words")
        for candidate in record.get("deferred_candidates") or []:
            deferred_count += 1
            candidate_id = str(candidate.get("candidate_id") or "") if isinstance(candidate, Mapping) else ""
            if candidate_id in family_id_set:
                errors.append(f"{family_id}: deferred candidate `{candidate_id}` is also a style family")

    return {
        "audit": "style-family-taxonomy",
        "ok": not errors,
        "family_count": len(families),
        "revised_or_new_family_count": sum(
            1 for record in families if record.get("status") in REVISED_STATUSES
        ),
        "retained_family_count": sum(1 for record in families if record.get("status") == "retained"),
        "deferred_candidate_count": deferred_count,
        "errors": errors,
        "warnings": warnings,
        "quality_claim": "none; this audit checks family evidence structure, not artistic merit",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description="Audit style-family boundary evidence")
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
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
