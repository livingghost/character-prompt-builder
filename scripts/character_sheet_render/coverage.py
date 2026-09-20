"""Coverage audit cross-checking the panel set against the declared character."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from character_sheet_render.sheetdata import (
    COVERAGE_EXPRESSION_COLUMNS,
    COVERAGE_ITEM_COLUMNS,
    COVERAGE_MARK_COLUMNS,
    COVERAGE_OUTFIT_COLUMNS,
    COVERAGE_PART_COLUMNS,
    COVERAGE_POSE_COLUMNS,
    FIXED_BINDINGS,
    FIXED_VISUAL_TABLES,
    PERFORMANCE_SERIES_KINDS,
    STATE_PANEL_SOURCES,
    _part_names_overlap,
    _part_source_keys,
    asymmetric_laterality,
    box_source_row_id,
    color_rows,
    meaningful,
    row_has_visual_data,
    table_entries,
    table_values,
)


def sheet_coverage(profile: Mapping[str, Any], sheet: Mapping[str, Any]) -> dict[str, list[str]]:
    """Cross-check the designed panel set against the character definition.

    Gaps are either character content the profile gives no frame to (each
    signature mark, each declared expression variant, declared items, declared
    outfit variants, declared body-language states) or a missing piece of the
    minimum sheet floor (the canonical view set, a face panel, the color key
    when colors are declared, an expression panel). Gaps block the scaffold
    unless the omission is explicitly justified in
    ``field.sheet_coverage_exceptions``. A declared part whose panel names it in
    ``source_part`` or binds its exact ``source_row_id`` is covered outright and
    reported neither way. Warnings are the remaining case: a per-part attribute
    that can only be riding on an unbound detail panel, which is worth confirming
    and never blocks.
    """

    boxes = [box for row in profile["rows"] for box in row["boxes"]]
    structural_errors: list[str] = []
    gaps: list[str] = []
    warnings: list[str] = []
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}

    canonical_boxes = [box for box in boxes if box.get("kind") == "canonical_view"]
    if len(canonical_boxes) < 2:
        structural_errors.append(
            "the selected profile must declare at least two distinct canonical_view "
            "panels that expose this kind's topology; the view names and total count "
            "are profile-defined and are not limited to humanoid directions"
        )
    outfit_declared = bool(
        meaningful(fields.get("field.dressed_equipped_form_visual_description", ""))
        or any(
            row_has_visual_data(row, COVERAGE_OUTFIT_COLUMNS)
            for row in table_values(sheet, "outfits")
        )
    )
    outfit_turnaround_boxes = [
        box for box in boxes if box.get("kind") == "outfit_turnaround"
    ]
    if outfit_declared and not outfit_turnaround_boxes and not any(
        box.get("kind") in {"outfit", "outfit_detail", "outfit_variant"}
        for box in boxes
    ):
        gaps.append(
            "a covered, dressed, shelled, or equipped state is declared but the "
            "selected profile provides no panel for it"
        )

    for table_id in ("marks", "parts"):
        for entry in table_entries(sheet, table_id):
            row = entry["values"]
            laterality = meaningful(row.get("laterality", ""))
            counterpart = meaningful(row.get("counterpart_rule", ""))
            visual = row_has_visual_data(
                row,
                COVERAGE_MARK_COLUMNS if table_id == "marks" else COVERAGE_PART_COLUMNS,
            )
            if not visual:
                continue
            if table_id == "marks" and not laterality:
                structural_errors.append(
                    f"mark {entry['row_id']} must declare laterality, including an "
                    "explicit bilateral or center value when it is not asymmetric"
                )
            if table_id == "parts" and not laterality:
                structural_errors.append(
                    f"part {entry['row_id']} must declare laterality/topology, including "
                    "an explicit bilateral, midline, single, radial, distributed, or "
                    "otherwise unpaired value"
                )
            if asymmetric_laterality(laterality):
                if not counterpart:
                    structural_errors.append(
                        f"asymmetric row {entry['row_id']} must declare counterpart_rule "
                        "for the corresponding opposite side or paired component"
                    )
                comparison_panel = any(
                    meaningful(box.get("source_row_id", "")) == entry["row_id"]
                    and (
                        box.get("kind")
                        == ("mark_detail" if table_id == "marks" else "part_detail")
                        or box.get("counterpart_comparison") is True
                    )
                    for box in boxes
                )
                if not comparison_panel:
                    structural_errors.append(
                        f"asymmetric row {entry['row_id']} must bind to a feature-versus-"
                        "counterpart comparison panel; an isolated close-up cannot prove "
                        "the opposite side's absence, intactness, or different feature"
                    )
    for table_id, (columns, continuity_required) in FIXED_VISUAL_TABLES.items():
        for entry in table_entries(sheet, table_id):
            row = entry["values"]
            if not row_has_visual_data(row, columns):
                continue
            if meaningful(row.get("binding", "")) not in FIXED_BINDINGS:
                continue
            if continuity_required and not meaningful(row.get("continuity_rule", "")):
                structural_errors.append(
                    f"fixed visual {entry['row_id']} must declare continuity_rule so its "
                    "identity does not change between applicable panels or orientations"
                )
            if not meaningful(row.get("visibility_rule", "")):
                structural_errors.append(
                    f"fixed visual {entry['row_id']} must declare visibility_rule so it "
                    "appears in every applicable panel where its subject is exposed and "
                    "may be absent only under a declared view, state, or occlusion condition"
                )
    if not any(box.get("kind") in {"head_study", "icon"} for box in boxes):
        gaps.append("the profile provides no head study or icon panel")
    expression_declared = bool(
        meaningful(fields.get("field.character_specific_expression_described", ""))
        or any(
            row_has_visual_data(row, COVERAGE_EXPRESSION_COLUMNS)
            for row in table_values(sheet, "expressions")
        )
    )
    if expression_declared and not any(
        box.get("kind") in {"expressions", "expression_variant"} for box in boxes
    ):
        gaps.append("declared expression behavior has no expression panel")
    colors = color_rows(sheet)
    if colors and not any(box.get("kind") == "palette" for box in boxes):
        gaps.append("declared color zones have no palette panel")

    mark_row_ids = {
        box_source_row_id(box, "marks")
        for box in boxes
        if box.get("kind") == "mark_detail"
    }
    for entry in table_entries(sheet, "marks"):
        row = entry["values"]
        if entry["row_id"] not in mark_row_ids and row_has_visual_data(row, COVERAGE_MARK_COLUMNS):
            label = meaningful(row.get("mark_id", "")) or entry["row_id"]
            gaps.append(f"mark {label!r} has no mark_detail panel")

    expression_row_ids = {
        box_source_row_id(box, "expressions")
        for box in boxes
        if box.get("kind") == "expression_variant"
    }
    for entry in table_entries(sheet, "expressions"):
        row = entry["values"]
        if entry["row_id"] not in expression_row_ids and row_has_visual_data(
            row, COVERAGE_EXPRESSION_COLUMNS
        ):
            label = meaningful(row.get("state", "")) or entry["row_id"]
            gaps.append(f"expression {label!r} has no expression_variant panel")

    item_row_ids = {
        box_source_row_id(box, "items")
        for box in boxes
        if box.get("kind") == "items"
    }
    for entry in table_entries(sheet, "items"):
        row = entry["values"]
        if entry["row_id"] not in item_row_ids and row_has_visual_data(
            row, COVERAGE_ITEM_COLUMNS
        ):
            label = meaningful(row.get("item", "")) or entry["row_id"]
            gaps.append(f"item {label!r} has no dedicated items panel")

    pose_row_ids = {
        box_source_row_id(box, "bodylang")
        for box in boxes
        if box.get("kind") == "pose_state"
    }
    for entry in table_entries(sheet, "bodylang"):
        row = entry["values"]
        if entry["row_id"] not in pose_row_ids and row_has_visual_data(row, COVERAGE_POSE_COLUMNS):
            gaps.append(f"body-language row {entry['row_id']} has no pose_state panel")

    for kind in PERFORMANCE_SERIES_KINDS:
        table_id, columns = STATE_PANEL_SOURCES[kind]
        covered_row_ids = {
            box_source_row_id(box, table_id)
            for box in boxes
            if box.get("kind") == kind
        }
        for entry in table_entries(sheet, table_id):
            if entry["row_id"] not in covered_row_ids and row_has_visual_data(
                entry["values"], columns
            ):
                gaps.append(f"{table_id} row {entry['row_id']} has no {kind} panel")

    outfit_row_ids = {
        box_source_row_id(box, "outfits")
        for box in boxes
        if box.get("kind") in {"outfit_variant", "outfit_turnaround"}
    }
    for entry in table_entries(sheet, "outfits"):
        row = entry["values"]
        if entry["row_id"] not in outfit_row_ids and row_has_visual_data(
            row, ("outfit", "description", "notes")
        ):
            label = meaningful(row.get("outfit", "")) or entry["row_id"]
            gaps.append(f"declared outfit {label!r} has no outfit_variant panel")

    # A panel of any kind binds itself to one declared parts row by naming it in
    # `source_part`, so a dedicated panel such as the anthro profile's
    # tail_detail counts as coverage exactly like a named part_detail does.
    # A source_part may also list synonyms ("skin / pads / plating") so one
    # panel can own a part however a species names it - scales, plating, hide.
    dedicated_parts: set[str] = set()
    bound_part_row_ids: set[str] = set()
    generic_part_detail = False
    for box in boxes:
        keys = _part_source_keys(box)
        if keys:
            dedicated_parts.update(keys)
        if box.get("kind") == "part_detail":
            row_id = box_source_row_id(box, "parts")
            if row_id:
                bound_part_row_ids.add(row_id)
            elif not keys:
                generic_part_detail = True
    for entry in table_entries(sheet, "parts"):
        row = entry["values"]
        part = meaningful(row.get("part", ""))
        attribute = meaningful(row.get("attribute", ""))
        if not part or not attribute:
            continue
        if entry["row_id"] in bound_part_row_ids:
            # A dynamically resolved panel that binds the exact editor row is
            # just as dedicated as a profile-authored source_part panel.
            continue
        if any(_part_names_overlap(name, part) for name in dedicated_parts):
            # The part owns a panel that names it. Fully covered, so stay silent.
            continue
        if generic_part_detail:
            warnings.append(
                f"declared part {part!r} attribute rides on an unbound detail panel; "
                "confirm the owning panel shows it"
            )
            continue
        gaps.append(f"declared part {part!r} has no part_detail panel")

    # A profile panel whose authored binding names a row that does not exist
    # in its table (or a row of a different table) resolves to source_missing
    # and the scaffold substitutes a generic fallback panel. That substitution
    # discards the author's deliberate binding, so it must surface as a
    # warning instead of disappearing without a trace.
    for box in boxes:
        if not box.get("source_missing"):
            continue
        slot_id = box.get("slot_id", "?")
        authored_row_id = meaningful(str(box.get("_authored_source_row_id", "")))
        declared_part = meaningful(str(box.get("source_part", "")))
        table_id = STATE_PANEL_SOURCES.get(str(box.get("kind", "")), ("?",))[0]
        if declared_part:
            if not table_id or table_id == "?":
                table_id = "parts"
            warnings.append(
                f"panel {slot_id} declares source_part {declared_part!r} but no rows in "
                f"the {table_id} table match it; the panel fell back to an unbound default"
            )
        elif authored_row_id:
            if authored_row_id.split(".", 1)[0] != table_id:
                warnings.append(
                    f"panel {slot_id} declares source_row_id {authored_row_id!r} which "
                    f"belongs to a different table; {table_id} panels bind {table_id}.NN "
                    "rows, so the panel fell back to an unbound default"
                )
            else:
                warnings.append(
                    f"panel {slot_id} declares source_row_id {authored_row_id!r} but the "
                    f"{table_id} table has no such row; the panel fell back to an "
                    "unbound default"
                )

    return {
        "structural_errors": structural_errors,
        "gaps": gaps,
        "warnings": warnings,
    }


def coverage_exception_records(gaps: Sequence[str], raw: str) -> list[dict[str, str]]:
    """Bind one substantive justification line to each coverage gap."""

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) != len(gaps):
        raise ValueError(
            "field.sheet_coverage_exceptions must contain exactly one nonempty "
            f"justification line per coverage gap (expected {len(gaps)}, found {len(lines)})"
        )
    too_short = [index + 1 for index, line in enumerate(lines) if len(line) < 12]
    if too_short:
        raise ValueError(
            "coverage-exception justifications must be substantive (at least 12 "
            "characters); short lines: " + ", ".join(map(str, too_short))
        )
    return [
        {"gap": gap, "justification": justification}
        for gap, justification in zip(gaps, lines, strict=True)
    ]
