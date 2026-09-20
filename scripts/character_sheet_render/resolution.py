"""Panel resolution and binding from the layout profile and sheet state rows."""
from __future__ import annotations

import copy
import hashlib
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from character_sheet import resolve_sheet_relative
from character_sheet_render.profiles import (
    ASPECT_LIMIT,
    BORDER,
    BOTTOM_MARGIN,
    DEFAULT_FOOTER_HEIGHT,
    FILL_POLICIES,
    HEADER_HEIGHT,
    PALETTE_CELL_MIN_HEIGHT,
    PANEL_GAP,
    RESOLVED_ROW_HEIGHT,
    ROW_GAP,
    SCAFFOLD_TOP_OF_ROWS,
    SECTION_HEADER_HEIGHT,
    SIDE_MARGIN,
    desired_panel_width,
    row_natural_width,
    validate_profile_semantics,
)
from character_sheet_render.sheetdata import (
    COVERAGE_EVIDENCE_COLUMNS,
    COVERAGE_EXPRESSION_COLUMNS,
    COVERAGE_ITEM_COLUMNS,
    COVERAGE_MARK_COLUMNS,
    COVERAGE_PART_COLUMNS,
    COVERAGE_VIEW_COLUMNS,
    PERFORMANCE_SERIES_KINDS,
    STATE_PANEL_SOURCES,
    _part_match_score,
    _part_source_keys,
    asymmetric_laterality,
    box_source_row_id,
    color_rows,
    compact_join,
    meaningful,
    review_text,
    row_has_visual_data,
    source_entry,
    table_entries,
    table_values,
)


def resolve_slot(
    sheet: Mapping[str, Any], box: Mapping[str, Any]
) -> tuple[str | None, Mapping[str, Any] | None]:
    slots = sheet.get("slots")
    if not isinstance(slots, Mapping):
        return None, None
    for slot_id in (box["slot_id"], *box.get("aliases", [])):
        candidate = slots.get(slot_id)
        if isinstance(candidate, Mapping):
            return slot_id, candidate
    return None, None


def slot_image(
    sheet: Mapping[str, Any], box: Mapping[str, Any], sheet_dir: Path
) -> tuple[str | None, Mapping[str, Any] | None, str, Path | None]:
    resolved_id, slot = resolve_slot(sheet, box)
    relative = meaningful(slot.get("image_path", "")) if slot else ""
    if not relative:
        return resolved_id, slot, "", None
    slot_label = resolved_id or box["slot_id"]
    try:
        image_path = resolve_sheet_relative(
            relative,
            root=sheet_dir,
            field=f"slot {slot_label} image_path",
        )
    except OSError as exc:
        raise ValueError(f"slot {slot_label} image does not exist: {relative}") from exc
    return resolved_id, slot, relative, image_path


def requested_fill_policy(slot: Mapping[str, Any] | None, box: Mapping[str, Any]) -> str:
    policy = slot.get("fill_policy") if slot else None
    if not isinstance(policy, str) or not policy:
        policy = str(box.get("default_fill_policy", "auto"))
    if policy not in FILL_POLICIES:
        raise ValueError(f"slot {box['slot_id']} has unsupported fill_policy {policy!r}")
    return policy


def source_declared(box: Mapping[str, Any], sheet: Mapping[str, Any]) -> bool:
    kind = str(box.get("kind", "drawing"))
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    if box.get("source_missing"):
        return False
    if kind in {"canonical_view", "icon", "profile"}:
        return True
    source_part_keys = _part_source_keys(box)
    if source_part_keys:
        return any(
            _part_match_score(source_part_keys, str(row.get("part", ""))) > 0
            for row in table_values(sheet, "parts")
        )
    if kind == "size_reference":
        return bool(meaningful(fields.get("field.height_against_a_stated_measure", "")))
    if kind == "part_detail":
        entry = source_entry(box, sheet, "parts")
        return bool(
            entry
            and row_has_visual_data(entry["values"], COVERAGE_PART_COLUMNS)
        )
    if kind == "mark_detail":
        entry = source_entry(box, sheet, "marks")
        return bool(entry) and row_has_visual_data(
            entry["values"],
            COVERAGE_MARK_COLUMNS,
        )
    if kind == "pose_state":
        entry = source_entry(box, sheet, "bodylang")
        return bool(entry) and row_has_visual_data(
            entry["values"], ("posture", "gesture", "kind_channels", "distance_orientation")
        )
    if kind == "outfit":
        return bool(
            meaningful(fields.get("field.dressed_equipped_form_visual_description", ""))
            or any(
                row_has_visual_data(row, ("outfit", "description", "notes"))
                for row in table_values(sheet, "outfits")
            )
        )
    if kind == "outfit_detail":
        return bool(
            meaningful(fields.get("field.dressed_equipped_form_visual_description", ""))
            or any(
                row_has_visual_data(row, ("outfit", "description", "notes"))
                for row in table_values(sheet, "outfits")
            )
        )
    if kind == "outfit_turnaround":
        return bool(
            meaningful(fields.get("field.dressed_equipped_form_visual_description", ""))
            or any(
                row_has_visual_data(row, ("outfit", "description", "notes"))
                for row in table_values(sheet, "outfits")
            )
        )
    if kind == "signature_pose":
        return bool(
            meaningful(fields.get("field.signature_poses_and_mannerisms_described", ""))
        )
    if kind == "items":
        entry = source_entry(box, sheet, "items")
        if meaningful(box.get("source_row_id", "")):
            return bool(entry) and row_has_visual_data(
                entry["values"], COVERAGE_ITEM_COLUMNS
            )
        return any(
            row_has_visual_data(row, COVERAGE_ITEM_COLUMNS)
            for row in table_values(sheet, "items")
        )
    if kind == "evidence_view":
        entry = source_entry(box, sheet, "evidence")
        return bool(entry) and row_has_visual_data(
            entry["values"], COVERAGE_EVIDENCE_COLUMNS
        )
    if kind == "expressions":
        return bool(
            meaningful(fields.get("field.character_specific_expression_described", ""))
        )
    if kind == "outfit_variant":
        entry = source_entry(box, sheet, "outfits")
        return bool(entry) and row_has_visual_data(
            entry["values"], ("outfit", "description", "notes")
        )
    if kind == "expression_variant":
        entry = source_entry(box, sheet, "expressions")
        return bool(entry) and row_has_visual_data(
            entry["values"], COVERAGE_EXPRESSION_COLUMNS
        )
    if kind in PERFORMANCE_SERIES_KINDS:
        table_id, columns = STATE_PANEL_SOURCES[kind]
        entry = source_entry(box, sheet, table_id)
        return bool(entry) and row_has_visual_data(entry["values"], columns)
    return True


def series_panel_text(kind: str, row: Mapping[str, str]) -> tuple[str, str]:
    """Label and drawing details a performance-series row gives its panel."""

    if kind == "part_state":
        part = meaningful(row.get("part", ""))
        state = meaningful(row.get("state", ""))
        title = ": ".join(value.upper() for value in (part, state) if value)
        return title, compact_join((row.get("configuration", ""), row.get("read", "")))
    if kind == "range_of_motion":
        region = meaningful(row.get("region", ""))
        return (
            f"RANGE: {region.upper()}" if region else "",
            compact_join((row.get("region", ""), row.get("range", ""))),
        )
    if kind == "action_pose":
        action = meaningful(row.get("action", ""))
        return (
            f"ACTION: {action.upper()}" if action else "",
            compact_join((row.get("phase", ""), row.get("mechanics", ""), row.get("kind_channels", ""))),
        )
    if kind == "idle_gesture":
        gesture = meaningful(row.get("gesture", ""))
        return (
            f"GESTURE: {gesture.upper()}" if gesture else "",
            compact_join((row.get("context", ""), row.get("body", ""), row.get("props", ""))),
        )
    return "", ""


def effective_fill_state(
    *,
    policy: str,
    box: Mapping[str, Any],
    sheet: Mapping[str, Any],
    image_path: Path | None,
) -> str:
    if box.get("kind") in {"palette", "profile"}:
        return "renderer"
    if box.get("source_missing"):
        return "skip"
    if policy == "skip":
        return "skip"
    if policy == "fill":
        return "fill"
    if policy == "keep":
        if image_path is None:
            raise ValueError(
                f"slot {box['slot_id']} requests fill_policy=keep but has no accepted image_path"
            )
        return "keep"
    if image_path is not None:
        return "keep"
    return "fill" if source_declared(box, sheet) else "skip"


def merge_panel_hint(base: Any, detail: Any, label: str) -> str:
    """Preserve profile instructions while adding sheet-specific panel context."""

    base_text = meaningful(base)
    detail_text = meaningful(detail)
    if not detail_text:
        return base_text
    qualified = f"{label}: {detail_text}" if label else detail_text
    if not base_text:
        return qualified
    if detail_text.casefold() in base_text.casefold():
        return base_text
    return f"{base_text}; {qualified}"


def apply_sheet_context(profile: Mapping[str, Any], sheet: Mapping[str, Any]) -> dict[str, Any]:
    """Turn generic profile panels into concise sheet-specific visual instructions."""

    resolved = copy.deepcopy(profile)
    part_entries = table_entries(sheet, "parts")
    item_rows = table_values(sheet, "items")
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    bound_tables = {
        "pose_state": "bodylang",
        "mark_detail": "marks",
        "expression_variant": "expressions",
        "items": "items",
        "evidence_view": "evidence",
        "outfit_variant": "outfits",
        "outfit_turnaround": "outfits",
        "outfit_detail": "outfits",
        **{kind: STATE_PANEL_SOURCES[kind][0] for kind in PERFORMANCE_SERIES_KINDS},
    }

    for profile_row in resolved["rows"]:
        for box in profile_row["boxes"]:
            kind = box.get("kind", "")
            bound_entry = (
                source_entry(box, sheet, bound_tables[kind])
                if kind in bound_tables
                else None
            )
            if bound_entry:
                box["source_row_id"] = bound_entry["row_id"]
                box["source_index"] = bound_entry["index"]
                binding = meaningful(bound_entry["values"].get("binding", ""))
                if binding:
                    box["binding"] = binding

            if kind == "canonical_view":
                value = meaningful(
                    fields.get("field.base_form_visual_description", "")
                )
                if value:
                    box["hint"] = merge_panel_hint(
                        box.get("hint", ""), value, "declared base form"
                    )
            elif kind == "pose_state" and bound_entry:
                row = bound_entry["values"]
                state = meaningful(row.get("state", ""))
                if state:
                    box["label"] = "POSE: " + state.upper()
                details = compact_join(
                    (
                        row.get("posture", ""),
                        row.get("gesture", ""),
                        row.get("kind_channels", ""),
                        row.get("distance_orientation", ""),
                    )
                )
                if details:
                    box["hint"] = details
            elif kind == "mark_detail" and bound_entry:
                row = bound_entry["values"]
                mark_id = meaningful(row.get("mark_id", ""))
                if mark_id:
                    box["label"] = "MARK: " + mark_id.upper()
                details = compact_join(
                    (
                        row.get("landmark_anchor", ""),
                        row.get("shape_path", ""),
                        row.get("laterality", ""),
                    )
                )
                if details:
                    box["hint"] = details
                box["review"] = review_text("marks", row) or None
            elif kind == "part_detail":
                source_part = meaningful(box.get("source_part", ""))
                # resolve_state_panels is the binding authority: it assigns
                # declared source_part panels by strongest unused name match
                # and leaves unmatchable panels unbound. This pass only
                # reads the bound row (conventional first-row binding for
                # generic detail panels) and enriches label and hint. A
                # declared source_part whose binding is empty must never
                # fall back to the conventionally-numbered row: rendering
                # another part's data would corrupt label, hint, and every
                # downstream fill-policy error message.
                part_entry = source_entry(box, sheet, "parts")
                if source_part and part_entry is None:
                    box.setdefault("source_missing", True)
                if part_entry:
                    row = part_entry["values"]
                    box["source_row_id"] = part_entry["row_id"]
                    box["source_index"] = part_entry["index"]
                    part = meaningful(row.get("part", ""))
                    attribute = meaningful(row.get("attribute", ""))
                    laterality = meaningful(row.get("laterality", ""))
                    counterpart_rule = meaningful(row.get("counterpart_rule", ""))
                    continuity_rule = meaningful(row.get("continuity_rule", ""))
                    visibility_rule = meaningful(row.get("visibility_rule", ""))
                    binding = meaningful(row.get("binding", ""))
                    if binding:
                        box["binding"] = binding
                    if part and not source_part:
                        box["label"] = part.upper()
                    details = compact_join((attribute, laterality))
                    if details:
                        box["hint"] = merge_panel_hint(box.get("hint", ""), details, "declared")
                    box["review"] = compact_join((counterpart_rule, continuity_rule, visibility_rule)) or None
            elif kind == "items":
                rows = [bound_entry["values"]] if bound_entry else item_rows
                items = []
                for row in rows:
                    item = meaningful(row.get("item", ""))
                    visual_identity = meaningful(row.get("visual_identity", ""))
                    scale_attachment = meaningful(row.get("scale_attachment", ""))
                    rule = meaningful(row.get("role_rule", ""))
                    continuity_rule = meaningful(row.get("continuity_rule", ""))
                    visibility_rule = meaningful(row.get("visibility_rule", ""))
                    details = compact_join((item, visual_identity, scale_attachment))
                    if details:
                        items.append(details)
                if bound_entry:
                    item = meaningful(bound_entry["values"].get("item", ""))
                    if item:
                        box["label"] = "ITEM: " + item.upper()
                if items:
                    box["hint"] = merge_panel_hint(
                        box.get("hint", ""), "; ".join(items), "declared"
                    )
                reviews = [review_text("items", row) for row in rows]
                box["review"] = "; ".join(text for text in reviews if text) or None
            elif kind == "evidence_view" and bound_entry:
                row = bound_entry["values"]
                subject_table = meaningful(row.get("subject_table", ""))
                subject_row_id = meaningful(row.get("subject_row_id", ""))
                view_id = meaningful(row.get("view_id", ""))
                subject = next(
                    (
                        entry
                        for entry in table_entries(sheet, subject_table)
                        if entry["row_id"] == subject_row_id
                    ),
                    None,
                )
                if view_id:
                    box["label"] = "EVIDENCE: " + view_id.upper()
                subject_details = ""
                if subject:
                    subject_details = compact_join(
                        (
                            f"{key}: {value}"
                            for key, value in subject["values"].items()
                            if key != "binding"
                        )
                    )
                details = compact_join(
                    (
                        f"subject: {subject_table}/{subject_row_id}",
                        subject_details,
                        row.get("orientation_configuration", ""),
                        row.get("specification", ""),
                    )
                )
                box["review"] = review_text("evidence", row) or None
                if details:
                    box["hint"] = merge_panel_hint(
                        box.get("hint", ""), details, "declared evidence"
                    )
            elif kind == "signature_pose":
                value = meaningful(
                    fields.get("field.signature_poses_and_mannerisms_described", "")
                )
                if value:
                    box["hint"] = merge_panel_hint(box.get("hint", ""), value, "declared")
            elif kind == "expressions":
                value = meaningful(
                    fields.get("field.character_specific_expression_described", "")
                )
                if value:
                    box["hint"] = merge_panel_hint(
                        box.get("hint", ""), value, "character-specific"
                    )
            elif kind == "expression_variant":
                if bound_entry:
                    row = bound_entry["values"]
                    state = meaningful(row.get("state", ""))
                    if state:
                        box["label"] = "STATE: " + state.upper()
                    details = compact_join(
                        (
                            row.get("overall_read", ""),
                            row.get("channel_states", ""),
                            row.get("fixed_identity_cues", ""),
                            row.get("notes", ""),
                        )
                    )
                    if details:
                        box["hint"] = merge_panel_hint(
                            box.get("hint", ""), details, "declared"
                        )
            elif kind == "outfit":
                value = meaningful(
                    fields.get("field.dressed_equipped_form_visual_description", "")
                )
                if value:
                    box["hint"] = merge_panel_hint(box.get("hint", ""), value, "declared")
            elif kind in {"outfit_turnaround", "outfit_detail"}:
                value = meaningful(
                    fields.get("field.dressed_equipped_form_visual_description", "")
                )
                if bound_entry:
                    row = bound_entry["values"]
                    details = compact_join(
                        (row.get("outfit", ""), row.get("description", ""), row.get("notes", ""))
                    )
                    if details:
                        value = compact_join((value, details))
                    box["review"] = review_text("outfits", row) or None
                if value:
                    box["hint"] = merge_panel_hint(
                        box.get("hint", ""), value, "declared dressed/equipped form"
                    )
            elif kind == "outfit_variant":
                if bound_entry:
                    row = bound_entry["values"]
                    name = meaningful(row.get("outfit", ""))
                    if name:
                        box["label"] = "OUTFIT: " + name.upper()
                    details = compact_join((row.get("description", ""), row.get("notes", "")))
                    if details:
                        box["hint"] = merge_panel_hint(
                            box.get("hint", ""), details, "declared"
                        )
                    box["review"] = review_text("outfits", row) or None
            elif kind in PERFORMANCE_SERIES_KINDS and bound_entry:
                title, details = series_panel_text(kind, bound_entry["values"])
                if title:
                    box["label"] = title
                if details:
                    box["hint"] = merge_panel_hint(box.get("hint", ""), details, "declared")
                if kind == "range_of_motion":
                    box["review"] = review_text("motion", bound_entry["values"]) or None
            if kind != "part_detail" and meaningful(box.get("source_part", "")):
                # A panel of any other kind may bind itself to a declared parts
                # row by naming it. The coverage audit credits that binding, so
                # the declared attribute has to reach the panel hint here.
                source_keys = _part_source_keys(box)
                part_entry = source_entry(box, sheet, "parts")
                if part_entry is None:
                    ranked = sorted(
                        part_entries,
                        key=lambda candidate: _part_match_score(
                            source_keys,
                            meaningful(candidate["values"].get("part", "")),
                        ),
                        reverse=True,
                    )
                    part_entry = next(
                        (
                            candidate
                            for candidate in ranked
                            if _part_match_score(
                                source_keys,
                                meaningful(candidate["values"].get("part", "")),
                            )
                            > 0
                        ),
                        None,
                    )
                if part_entry:
                    row = part_entry["values"]
                    box["source_row_id"] = part_entry["row_id"]
                    attribute = meaningful(row.get("attribute", ""))
                    laterality = meaningful(row.get("laterality", ""))
                    binding = meaningful(row.get("binding", ""))
                    if binding:
                        box["binding"] = binding
                    details = compact_join((attribute, laterality))
                    if details:
                        box["hint"] = merge_panel_hint(
                            box.get("hint", ""), details, "declared"
                        )
                    box["review"] = compact_join(
                        (box.get("review") or "", review_text("parts", row))
                    ) or None
    return resolved


def build_panel_plan(
    profile: Mapping[str, Any],
    sheet: Mapping[str, Any],
    *,
    sheet_dir: Path,
    mode: str,
    reference_scope: str,
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    colors = color_rows(sheet)
    if mode == "reference" and reference_scope == "identity":
        colors = [row for row in colors if row.get("binding") != "variable"]
    for profile_row in profile["rows"]:
        boxes_out = []
        for raw_box in profile_row["boxes"]:
            box = copy.deepcopy(raw_box)
            if box.get("source_missing"):
                resolved_id, slot = resolve_slot(sheet, box)
                image_relative, image_path = "", None
            else:
                resolved_id, slot, image_relative, image_path = slot_image(
                    sheet, box, sheet_dir
                )
            policy = requested_fill_policy(slot, box)
            if box.get("source_missing") and policy in {"fill", "keep"}:
                declared_part = meaningful(str(box.get("source_part", "")))
                if declared_part:
                    origin = f"no parts row matches its source_part {declared_part!r}"
                else:
                    origin = (
                        f"its bound row {box.get('source_row_id') or '<unbound>'} "
                        "does not exist in the source table"
                    )
                raise ValueError(
                    f"slot {resolved_id or box['slot_id']} requests fill_policy={policy} but {origin}"
                )
            state = effective_fill_state(
                policy=policy, box=box, sheet=sheet, image_path=image_path
            )
            role = str(box.get("reference_role", "identity"))
            if mode == "scaffold":
                # Undeclared optional anatomy is not a useful gray rectangle:
                # omitting it keeps the model-facing sheet legible and prevents
                # accidental invention. An explicit skip remains visible.
                if box.get("kind") == "palette" and not colors:
                    continue
                if state == "skip" and policy == "auto":
                    continue
            if mode == "reference":
                if box.get("kind") in {"palette", "profile"}:
                    if box.get("kind") == "palette" and not colors:
                        continue
                    state = "renderer"
                else:
                    if image_path is None:
                        continue
                    if reference_scope == "identity" and (
                        role != "identity" or box.get("binding") == "variable"
                    ):
                        continue
                    state = "keep"
            box["resolved_slot_id"] = resolved_id or box["slot_id"]
            box["slot"] = slot
            box["image_relative"] = image_relative
            box["image_path"] = image_path
            box["requested_fill_policy"] = policy
            box["fill_state"] = state
            boxes_out.append(box)
        if boxes_out:
            planned_row = {"height": int(profile_row["height"]), "boxes": boxes_out}
            section_label = meaningful(str(profile_row.get("section_label", "")))
            if section_label:
                planned_row["section_label"] = section_label
            rows_out.append(planned_row)
    return rows_out


# Image models read attached text only marginally, so the fill prompt text,
# not the wording printed inside the scaffold image, is the authoritative
# instruction channel. Each panel kind carries a fixed drawing rule that
# states what occupies the panel and how it is drawn, so even a terse
# profile hint still yields a self-sufficient panel instruction.
KIND_DRAW_GUIDE = {
    "canonical_view": (
        "Draw one complete unobstructed base-form view of this same individual or collective configuration only, with removable clothing, equipment, coverings, and carried items absent; use a plain white panel background, no props, and no scene; do not assume a humanoid body plan or exposed biological anatomy unless declared."
    ),
    "outfit_turnaround": (
        "Draw one complete dressed, covered, shelled, or equipped view of this same identity in the exact orientation requested; preserve the base form underneath and show the declared outfit or assembly consistently across every declared comparison view."
    ),
    "outfit_detail": (
        "Draw the declared clothing, covering, shell, or equipment as separated readable components, including front/back construction, fastenings, openings, layers, and identity-bearing motifs; no extra outfit design."
    ),
    "icon": (
        "Draw one tight recognition crop of the declared identity focal feature: face, sensor, emblem, core, or other recognition landmark as applicable; do not invent a face."
    ),
    "mark_detail": (
        "Draw a matched side-by-side close-up of this declared marking at its exact landmark and the corresponding opposite-side or paired landmark at the same scale and orientation; prove both presence and declared absence or difference; do not mirror the feature unless bilateral symmetry is explicitly declared."
    ),
    "part_detail": (
        "Draw only this declared part, component, or structural feature at close-up scale. When it has a paired or opposite-side counterpart, show both at matched scale and orientation and preserve the declared symmetry, absence, or difference."
    ),
    "pose_state": (
        "Draw this same individual in the declared pose state, full figure from the highest to the lowest extent, on a plain white background. Scale the complete figure down to fit the frame. Do not bend, crouch, compress, crop, or alter the declared posture merely to fit the panel; identity and proportions remain unchanged."
    ),
    "signature_pose": (
        "Draw this same individual in the declared habitual stance or gesture; identity and anatomy unchanged."
    ),
    "outfit": (
        "Draw this same individual wearing the declared outfit, full body, with anatomy and proportions still readable."
    ),
    "outfit_variant": (
        "Draw this same individual wearing the declared outfit variant; identity and anatomy unchanged."
    ),
    "items": (
        "Draw one isolated identity study of this declared item or assembly at a readable scale. Preserve its exact silhouette, proportions, materials, colors, fixed marks, attachment geometry, and declared orientation; include a small in-context scale or attachment inset when the row requires it; no unrelated objects."
    ),
    "evidence_view": (
        "Draw one additional identity-evidence view of the referenced declaration in exactly the declared orientation or configuration. Preserve the same identity and all already declared geometry, materials, colors, marks, counterparts, scale relations, and attachments; reveal only the requested surface, state, or comparison and do not invent missing structure."
    ),
    "expressions": (
        "Draw the declared state-expression channels of this same individual; use face, posture, light, topology, appendages, or other channels only when declared, and do not invent facial anatomy."
    ),
    "expression_variant": (
        "Draw one declared expression or communicated-state variant using this character's actual channels; do not invent a face, head, limbs, or tail."
    ),
    "head_study": (
        "Draw the declared primary recognition structure from the requested angle; it may be a head, sensor cluster, core, prow, emblem, or other focal structure."
    ),
    "tail_detail": (
        "Draw only the declared tail feature at close-up scale on a plain white background."
    ),
    "size_reference": (
        "Draw the complete extent of this same individual or collective beside a plain scale indicator, "
        "configuration and proportions identical to the canonical view; show only the declared "
        "height, length, span, diameter, or other measure."
    ),
    "part_state": (
        "Draw only the declared part of this same individual in the declared state, at close-up scale on a plain white background; keep the construction, length, markings, and colors of its identity panel and change only the declared configuration."
    ),
    "range_of_motion": (
        "Draw the declared body region of this same individual at both extremes of its declared range, side by side at matched scale and orientation on a plain white background; show the reach the body actually has and nothing past its declared limit; identity, proportions, and joint construction unchanged."
    ),
    "action_pose": (
        "Draw this same individual mid-action in the declared phase, full figure from the highest to the lowest extent on a plain white background, with weight, balance, spine, limbs, and the declared kind channels committed to the motion; scale the complete figure down to fit the frame; identity, proportions, and outfit unchanged."
    ),
    "idle_gesture": (
        "Draw this same individual in the declared everyday gesture or habit, full figure on a plain white background, with any declared prop at its declared scale; the posture is relaxed and particular to this character; identity, proportions, and outfit unchanged."
    ),
}

# PNG captions are deliberately short and complete. The full ``hint`` remains
# in the selected model request prompt and sheet-layout.json; it must never be
# squeezed into tiny raster text or shortened with an ellipsis.
KIND_PANEL_CAPTION = {
    "canonical_view": "Uncovered base form; match this exact direction and neutral stance.",
    "outfit_turnaround": "Same base form and direction; apply the bound outfit or equipment state.",
    "profile": "Renderer-owned identity facts; keep unchanged.",
    "palette": "Renderer-owned color and material key; keep unchanged.",
    "size_reference": "Complete base form beside the declared scale reference.",
    "head_study": "Large identity study; preserve structure, proportions, and fixed cues.",
    "icon": "Tight recognition crop showing the strongest fixed identity cues.",
    "part_detail": "Matched close-up of the named part and any paired counterpart.",
    "tail_detail": "Entire tail from base to tip; preserve length, flow, and markings.",
    "mark_detail": "Compare feature side and opposite side; preserve presence and absence.",
    "expression_variant": "Same head and markings; change only the declared expression channels.",
    "expressions": "Same identity across the declared communicated-state range.",
    "outfit_detail": "Separate construction details of the primary outfit or equipment.",
    "outfit": "Complete primary outfit over the unchanged base form.",
    "outfit_variant": "Complete declared outfit variant over the unchanged base form.",
    "items": "One declared item or assembly; preserve its construction and attachment cues.",
    "evidence_view": "Additional declared evidence view; prove the requested surface or state.",
    "pose_state": "Complete figure in the declared pose or state; identity unchanged.",
    "signature_pose": "Complete figure in the habitual pose; identity unchanged.",
    "part_state": "Same part as its identity panel; only the declared state changes.",
    "range_of_motion": "Declared region at both extremes of its range; nothing past its limit.",
    "action_pose": "Complete figure mid-action in the declared phase; identity unchanged.",
    "idle_gesture": "Complete figure in the declared everyday gesture; identity unchanged.",
}


# Resolved state panels never squeeze into an authored row - that shrinks
# already-designed panels and produces frames too small to draw detail into.
# They take dedicated rows after the authored rows, packed several panels per
# row at a drawing-friendly width, with a kind-appropriate panel design each.
STATE_PANEL_FALLBACKS = {
    "mark_detail": {
        "box": {
            "kind": "mark_detail",
            "reference_role": "identity",
            "label": "MARK",
            "hint": KIND_DRAW_GUIDE["mark_detail"],
            "footer_height": 96,
        },
    },
    "part_detail": {
        "box": {
            "kind": "part_detail",
            "reference_role": "identity",
            "label": "PART / COMPONENT",
            "hint": KIND_DRAW_GUIDE["part_detail"],
            "footer_height": 96,
        },
    },
    "expression_variant": {
        "box": {
            "kind": "expression_variant",
            "reference_role": "performance",
            "label": "EXPRESSION",
            "hint": KIND_DRAW_GUIDE["expression_variant"],
            "footer_height": 96,
        },
    },
    "pose_state": {
        "box": {
            "kind": "pose_state",
            "reference_role": "performance",
            "label": "POSE STATE",
            "hint": KIND_DRAW_GUIDE["pose_state"],
            "footer_height": 96,
        },
    },
    "items": {
        "box": {
            "kind": "items",
            "reference_role": "identity",
            "label": "ITEM",
            "hint": KIND_DRAW_GUIDE["items"],
            "footer_height": 96,
        },
    },
    "evidence_view": {
        "box": {
            "kind": "evidence_view",
            "reference_role": "identity",
            "label": "IDENTITY EVIDENCE",
            "hint": KIND_DRAW_GUIDE["evidence_view"],
            "footer_height": 96,
        },
    },
    "outfit_variant": {
        "box": {
            "kind": "outfit_variant",
            "reference_role": "identity",
            "label": "OUTFIT VARIANT",
            "hint": KIND_DRAW_GUIDE["outfit_variant"],
            "footer_height": 96,
        },
    },
    "part_state": {
        "box": {
            "kind": "part_state",
            "reference_role": "performance",
            "label": "PART STATE",
            "hint": KIND_DRAW_GUIDE["part_state"],
            "footer_height": 96,
        },
    },
    "range_of_motion": {
        "box": {
            "kind": "range_of_motion",
            "reference_role": "performance",
            "label": "RANGE OF MOTION",
            "hint": KIND_DRAW_GUIDE["range_of_motion"],
            "footer_height": 96,
        },
    },
    "action_pose": {
        "box": {
            "kind": "action_pose",
            "reference_role": "performance",
            "label": "ACTION POSE",
            "hint": KIND_DRAW_GUIDE["action_pose"],
            "footer_height": 96,
        },
    },
    "idle_gesture": {
        "box": {
            "kind": "idle_gesture",
            "reference_role": "performance",
            "label": "GESTURE",
            "hint": KIND_DRAW_GUIDE["idle_gesture"],
            "footer_height": 96,
        },
    },
}

STATE_SLOT_PREFIX = {
    "mark_detail": "slot.mark",
    "part_detail": "slot.part",
    "expression_variant": "expressions.ex",
    "pose_state": "pose.state",
    "items": "items.item",
    "evidence_view": "evidence.view",
    "outfit_variant": "slot.outfit.variant",
    "part_state": "part.state",
    "range_of_motion": "motion.range",
    "action_pose": "action.pose",
    "idle_gesture": "gesture.idle",
}

STATE_PANEL_LABELS = {
    "mark_detail": "MARK {number:02d}",
    "part_detail": "PART / COMPONENT {number:02d}",
    "expression_variant": "EXPRESSION {number:02d}",
    "pose_state": "POSE STATE {number:02d}",
    "items": "ITEM {number:02d}",
    "evidence_view": "IDENTITY EVIDENCE {number:02d}",
    "outfit_variant": "OUTFIT VARIANT {number:02d}",
    "part_state": "PART STATE {number:02d}",
    "range_of_motion": "RANGE OF MOTION {number:02d}",
    "action_pose": "ACTION POSE {number:02d}",
    "idle_gesture": "GESTURE {number:02d}",
}

# Resolved panels of one kind form one section of the board, under the same
# kind of heading an authored row carries.
KIND_SECTION_LABELS = {
    "mark_detail": "DECLARED MARKS",
    "part_detail": "DECLARED PARTS / COMPONENTS",
    "expression_variant": "DECLARED EXPRESSIONS",
    "pose_state": "DECLARED POSES AND BODY LANGUAGE",
    "items": "DECLARED ITEMS",
    "evidence_view": "DECLARED IDENTITY EVIDENCE",
    "outfit_variant": "DECLARED OUTFIT VARIANTS",
    "part_state": "PART STATES",
    "range_of_motion": "RANGE OF MOTION",
    "action_pose": "ACTION POSES",
    "idle_gesture": "EVERYDAY GESTURES",
}


def resolve_state_panels(
    profile: Mapping[str, Any], sheet: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, int]]:
    """Resolve the sheet's declared state rows into same-kind panel frames.

    The layout profile is the design baseline; the declared state tables in
    sheet-data (marks, expressions, bodylang, outfits) complete the panel set.
    Every declared visual row gets a same-kind panel frame as part of the
    sheet's initial state, using a kind-appropriate generous panel design.
    Resolved panels never squeeze into an authored row: they take dedicated
    rows after the authored rows, packed several panels per row at a
    drawing-friendly width. When the stack would grow too tall, the canvas
    widens to add columns per row - extra horizontal room buys more columns,
    never wider panels.

    Returns the resolved profile and a mapping of kind to the number of panels
    resolved from declared rows.
    """

    resolved = copy.deepcopy(profile)
    counts: dict[str, int] = {}
    if not isinstance(resolved.get("rows"), list) or not resolved["rows"]:
        return resolved, counts

    claimed_row_aliases: set[str] = set()

    def attach_editor_row_alias(
        box: dict[str, Any], table_id: str, row_id: str
    ) -> None:
        """Let the profile-neutral HTML bind evidence before profile resolution."""

        alias = f"row.{table_id}.{row_id}"
        if alias == box.get("slot_id"):
            return
        if alias in claimed_row_aliases:
            # A second panel resolving to the same row (a counterpart
            # comparison, for example) must not duplicate an editor alias
            # already claimed by another slot; the resolved-profile
            # re-validation would otherwise reject the render with a
            # generated alias name. The row stays bound through
            # source_row_id either way.
            return
        aliases = [str(value) for value in box.get("aliases", [])]
        if alias not in aliases:
            box["aliases"] = [*aliases, alias]
            claimed_row_aliases.add(alias)

    palette_count = len(color_rows(sheet))
    if palette_count:
        palette_grid_rows = math.ceil(palette_count / 10)
        for profile_row in resolved["rows"]:
            palette_boxes = [
                box for box in profile_row["boxes"] if box.get("kind") == "palette"
            ]
            if not palette_boxes:
                continue
            footer_height = max(
                int(box.get("footer_height", DEFAULT_FOOTER_HEIGHT))
                for box in palette_boxes
            )
            section_height = (
                SECTION_HEADER_HEIGHT
                if meaningful(str(profile_row.get("section_label", "")))
                else 0
            )
            required_height = (
                section_height
                + HEADER_HEIGHT
                + footer_height
                + BORDER * 2
                + palette_grid_rows * PALETTE_CELL_MIN_HEIGHT
                + max(0, palette_grid_rows - 1) * 8
            )
            profile_row["height"] = max(int(profile_row["height"]), required_height)

    view_entries = [
        entry
        for entry in table_entries(sheet, "views")
        if row_has_visual_data(entry["values"], COVERAGE_VIEW_COLUMNS)
    ]
    if view_entries:
        incomplete_views = [
            entry["row_id"]
            for entry in view_entries
            if any(not meaningful(entry["values"].get(column, "")) for column in COVERAGE_VIEW_COLUMNS)
        ]
        if incomplete_views:
            raise ValueError(
                "every declared view row must provide view_id, label, specification, "
                "and must_prove: " + ", ".join(incomplete_views)
            )
        semantic_view_ids = [meaningful(entry["values"]["view_id"]) for entry in view_entries]
        if len(semantic_view_ids) != len(set(semantic_view_ids)):
            raise ValueError("declared view_id values must be unique within a form sheet")
        if len(view_entries) < 2:
            raise ValueError(
                "the sheet's views table must declare at least two view rows: "
                "declared views replace the profile's authored canonical view grid "
                f"with one base panel per declared row, and {len(view_entries)} row "
                "cannot form the minimum topology comparison grid"
            )

        canonical_templates = [
            copy.deepcopy(box)
            for profile_row in resolved["rows"]
            for box in profile_row["boxes"]
            if box.get("kind") == "canonical_view"
        ]
        outfit_templates = [
            copy.deepcopy(box)
            for profile_row in resolved["rows"]
            for box in profile_row["boxes"]
            if box.get("kind") == "outfit_turnaround"
        ]
        if not canonical_templates:
            raise ValueError("the selected profile has no canonical_view frame to resolve declared views")

        remaining_rows: list[dict[str, Any]] = []
        for profile_row in resolved["rows"]:
            remaining_boxes = [
                box
                for box in profile_row["boxes"]
                if box.get("kind") not in {"canonical_view", "outfit_turnaround"}
            ]
            if remaining_boxes:
                retained = copy.deepcopy(profile_row)
                retained["boxes"] = remaining_boxes
                remaining_rows.append(retained)

        used_codes = {
            meaningful(str(box.get("panel_code", "")))
            for profile_row in remaining_rows
            for box in profile_row["boxes"]
            if meaningful(str(box.get("panel_code", "")))
        }

        def next_view_code(prefix: str, index: int) -> str:
            candidate_index = index
            while f"{prefix}{candidate_index}" in used_codes:
                candidate_index += 1
            code = f"{prefix}{candidate_index}"
            used_codes.add(code)
            return code

        def view_details(entry: Mapping[str, Any]) -> str:
            return meaningful(entry["values"].get("specification", ""))

        canonical_boxes: list[dict[str, Any]] = []
        for index, entry in enumerate(view_entries, start=1):
            values = entry["values"]
            clone = copy.deepcopy(canonical_templates[0])
            clone.pop("aliases", None)
            clone["slot_id"] = f"view.base.{entry['row_id']}"
            clone["output_name"] = f"view-base-{entry['row_id'].replace('.', '-')}.png"
            clone["panel_code"] = next_view_code("A", index)
            clone["source_view_row_id"] = entry["row_id"]
            clone["label"] = meaningful(values["label"]).upper()
            clone["hint"] = merge_panel_hint(
                KIND_DRAW_GUIDE["canonical_view"], view_details(entry), "declared view"
            )
            clone["caption"] = "Base configuration in this declared comparison view."
            clone["review"] = review_text("views", values) or None
            canonical_boxes.append(clone)

        outfit_entries = [
            entry
            for entry in table_entries(sheet, "outfits")
            if row_has_visual_data(entry["values"], ("outfit", "description", "notes"))
        ]
        if outfit_entries and not outfit_templates:
            raise ValueError(
                "outfit states and declared views exist, but the selected profile has no "
                "outfit_turnaround frame to resolve their comparison grid"
            )
        outfit_boxes_by_row: list[tuple[str, list[dict[str, Any]]]] = []
        outfit_code_index = 1
        for outfit_entry in outfit_entries:
            outfit_name = meaningful(outfit_entry["values"].get("outfit", "")) or outfit_entry["row_id"]
            group: list[dict[str, Any]] = []
            for view_entry in view_entries:
                view_values = view_entry["values"]
                clone = copy.deepcopy(outfit_templates[0])
                clone.pop("aliases", None)
                clone["slot_id"] = (
                    f"view.outfit.{outfit_entry['row_id']}.{view_entry['row_id']}"
                )
                clone["output_name"] = (
                    "view-outfit-"
                    + outfit_entry["row_id"].replace(".", "-")
                    + "-"
                    + view_entry["row_id"].replace(".", "-")
                    + ".png"
                )
                clone["panel_code"] = next_view_code("B", outfit_code_index)
                outfit_code_index += 1
                clone["source_row_id"] = outfit_entry["row_id"]
                clone["source_index"] = outfit_entry["index"]
                clone["source_view_row_id"] = view_entry["row_id"]
                clone["label"] = f"{outfit_name.upper()} / {meaningful(view_values['label']).upper()}"
                clone["hint"] = merge_panel_hint(
                    KIND_DRAW_GUIDE["outfit_turnaround"],
                    view_details(view_entry),
                    "declared view",
                )
                clone["caption"] = "Same declared view with this covering or equipment state."
                clone["review"] = compact_join(
                    (review_text("views", view_values), review_text("outfits", outfit_entry["values"]))
                ) or None
                group.append(clone)
            outfit_boxes_by_row.append((outfit_name, group))

        def pack_view_boxes(
            boxes: Sequence[Mapping[str, Any]], section_label: str
        ) -> list[dict[str, Any]]:
            if not boxes:
                return []
            panel_width = desired_panel_width(boxes[0], RESOLVED_ROW_HEIGHT)
            capacity = max(
                1,
                (int(resolved["canvas"][0]) - SIDE_MARGIN * 2 + PANEL_GAP)
                // (panel_width + PANEL_GAP),
            )
            packed: list[dict[str, Any]] = []
            for start in range(0, len(boxes), capacity):
                row = {
                    "height": RESOLVED_ROW_HEIGHT,
                    "boxes": [copy.deepcopy(box) for box in boxes[start : start + capacity]],
                }
                if start == 0:
                    row["section_label"] = section_label
                packed.append(row)
            return packed

        resolved_view_rows = pack_view_boxes(canonical_boxes, "DECLARED BASE VIEWS")
        for outfit_name, group in outfit_boxes_by_row:
            resolved_view_rows.extend(
                pack_view_boxes(group, f"DECLARED VIEWS / {outfit_name.upper()}")
            )
        resolved["rows"] = resolved_view_rows + remaining_rows
        counts["canonical_view"] = len(canonical_boxes)
        if outfit_boxes_by_row:
            counts["outfit_turnaround"] = sum(
                len(group) for _outfit_name, group in outfit_boxes_by_row
            )

    evidence_entries = [
        entry
        for entry in table_entries(sheet, "evidence")
        if row_has_visual_data(entry["values"], COVERAGE_EVIDENCE_COLUMNS)
    ]
    evidence_keys: set[tuple[str, str, str]] = set()
    for entry in evidence_entries:
        values = entry["values"]
        missing = [
            column
            for column in COVERAGE_EVIDENCE_COLUMNS
            if not meaningful(values.get(column, ""))
        ]
        if missing:
            raise ValueError(
                f"evidence row {entry['row_id']} must provide every evidence column; "
                "missing: " + ", ".join(missing)
            )
        subject_table = meaningful(values["subject_table"])
        subject_row_id = meaningful(values["subject_row_id"])
        view_id = meaningful(values["view_id"])
        if subject_table == "evidence":
            raise ValueError(
                f"evidence row {entry['row_id']} cannot use another evidence row as its subject"
            )
        subject = next(
            (
                candidate
                for candidate in table_entries(sheet, subject_table)
                if candidate["row_id"] == subject_row_id
            ),
            None,
        )
        if subject is None:
            raise ValueError(
                f"evidence row {entry['row_id']} references missing declaration "
                f"{subject_table}/{subject_row_id}"
            )
        key = (subject_table, subject_row_id, view_id)
        if key in evidence_keys:
            raise ValueError(
                f"duplicate evidence view_id {view_id!r} for "
                f"{subject_table}/{subject_row_id}"
            )
        evidence_keys.add(key)

    # Bind authored component panels first, across all visual kinds. A tail may
    # use ``tail_detail`` rather than ``part_detail`` and still represents its
    # parts row. Pick the strongest unused match so similar declarations such
    # as forepaws and hindpaws do not both bind to the first row and create a
    # duplicate catch-all panel later.
    part_entries = table_entries(sheet, "parts")
    used_part_rows: set[str] = set()
    for profile_row in resolved["rows"]:
        for box in profile_row["boxes"]:
            source_keys = _part_source_keys(box)
            if not source_keys:
                continue
            ranked = sorted(
                part_entries,
                key=lambda candidate: (
                    candidate["row_id"] in used_part_rows,
                    -_part_match_score(
                        source_keys,
                        meaningful(candidate["values"].get("part", "")),
                    ),
                    candidate["index"],
                ),
            )
            entry = next(
                (
                    candidate
                    for candidate in ranked
                    if _part_match_score(
                        source_keys,
                        meaningful(candidate["values"].get("part", "")),
                    )
                    > 0
                ),
                None,
            )
            if entry is None:
                box["source_missing"] = True
                continue
            box["source_row_id"] = entry["row_id"]
            box["source_index"] = entry["index"]
            entry_laterality = meaningful(entry["values"].get("laterality", ""))
            proves_counterpart = (
                box.get("kind") == "part_detail"
                or box.get("counterpart_comparison") is True
            )
            if not asymmetric_laterality(entry_laterality) or proves_counterpart:
                attach_editor_row_alias(box, "parts", entry["row_id"])
            box.pop("source_missing", None)
            used_part_rows.add(entry["row_id"])

    # The first declared outfit/equipment row is shown through every
    # outfit_turnaround view authored by the selected profile. Additional
    # outfit rows clone that complete profile-defined view set below; no
    # humanoid direction names or fixed view count are assumed here.
    for profile_row in resolved["rows"]:
        for box in profile_row["boxes"]:
            if box.get("kind") != "outfit_turnaround":
                continue
            entry = source_entry(box, sheet, "outfits")
            if entry is not None:
                box["source_row_id"] = entry["row_id"]
                box["source_index"] = entry["index"]

    # Bind every authored state panel to a persistent row before resolving
    # missing rows. Bundled profiles use source_row_id explicitly; conventional
    # table.NN ids keep positional source_index profiles stable across reordering.
    for kind, (table_id, _columns) in STATE_PANEL_SOURCES.items():
        if kind == "part_detail":
            continue
        entries = table_entries(sheet, table_id)
        for profile_row in resolved["rows"]:
            for box in profile_row["boxes"]:
                if box.get("kind") != kind:
                    continue
                entry = None
                entry = source_entry(box, sheet, table_id)
                if entry is None:
                    authored_row_id = meaningful(str(box.get("source_row_id", "")))
                    if authored_row_id:
                        box["_authored_source_row_id"] = authored_row_id
                    box["source_missing"] = True
                    box.setdefault("source_row_id", box_source_row_id(box, table_id))
                    continue
                box["source_row_id"] = entry["row_id"]
                box["source_index"] = entry["index"]
                attach_editor_row_alias(box, table_id, entry["row_id"])
                box.pop("source_missing", None)

    known_ids: set[str] = set()
    known_outputs: set[str] = set()
    known_codes: set[str] = set()
    for profile_row in resolved["rows"]:
        for box in profile_row["boxes"]:
            known_ids.add(str(box.get("slot_id", "")))
            known_ids.update(str(alias) for alias in box.get("aliases", []))
            known_outputs.add(
                str(box.get("output_name") or box["slot_id"].replace(".", "-") + ".png")
            )
            code = meaningful(str(box.get("panel_code", "")))
            if code:
                known_codes.add(code)

    def unique(base: str, taken: set[str]) -> str:
        candidate = base
        suffix = 2
        while candidate in taken:
            candidate = f"{base}-{suffix}"
            suffix += 1
        taken.add(candidate)
        return candidate

    def stable_row_suffix(table_id: str, row_id: str) -> str:
        conventional = re.fullmatch(re.escape(table_id) + r"\.(\d+)", row_id)
        if conventional:
            return conventional.group(1).zfill(2)
        slug = re.sub(r"[^a-z0-9]+", "-", row_id.casefold()).strip("-")[:36]
        digest = hashlib.sha256(row_id.encode("utf-8")).hexdigest()[:8]
        return f"row-{slug or 'entry'}-{digest}"

    outfit_group_rows: list[dict[str, Any]] = []
    outfit_templates = [
        box
        for profile_row in resolved["rows"]
        for box in profile_row["boxes"]
        if box.get("kind") == "outfit_turnaround"
        and not box.get("source_missing")
    ]
    if outfit_templates:
        outfit_entries = [
            entry
            for entry in table_entries(sheet, "outfits")
            if row_has_visual_data(entry["values"], ("outfit", "description", "notes"))
        ]
        covered_outfit_ids = {
            meaningful(box.get("source_row_id", "")) for box in outfit_templates
        }
        additional_outfits = [
            entry for entry in outfit_entries if entry["row_id"] not in covered_outfit_ids
        ]
        authored_outfit_codes = [
            meaningful(str(box.get("panel_code", ""))) for box in outfit_templates
        ]
        outfit_code_prefix = next(
            (code[:1].upper() for code in reversed(authored_outfit_codes) if code),
            "",
        )
        if not outfit_code_prefix or outfit_code_prefix not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            outfit_code_prefix = next(
                letter
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if not any(code.startswith(letter) for code in known_codes)
            )
        next_outfit_code_number = 1 + max(
            (
                int(code[1:])
                for code in known_codes
                if code.startswith(outfit_code_prefix) and code[1:].isdigit()
            ),
            default=0,
        )
        for entry in additional_outfits:
            suffix = stable_row_suffix("outfits", entry["row_id"])
            name = meaningful(entry["values"].get("outfit", ""))
            group: list[dict[str, Any]] = []
            for template in outfit_templates:
                clone = copy.deepcopy(template)
                clone.pop("aliases", None)
                clone["source_index"] = entry["index"]
                clone["source_row_id"] = entry["row_id"]
                clone["slot_id"] = unique(
                    f"{template['slot_id']}.{suffix}", known_ids
                )
                output_path = Path(
                    str(
                        template.get("output_name")
                        or template["slot_id"].replace(".", "-") + ".png"
                    )
                )
                clone["output_name"] = unique(
                    f"{output_path.stem}-{suffix}{output_path.suffix}", known_outputs
                )
                clone["panel_code"] = f"{outfit_code_prefix}{next_outfit_code_number}"
                next_outfit_code_number += 1
                known_codes.add(clone["panel_code"])
                direction_label = meaningful(str(template.get("label", "")))
                clone["label"] = (
                    f"{name.upper()} / {direction_label}" if name else direction_label
                )
                clone["caption"] = (
                    "Same base form and declared view; apply this bound outfit or "
                    "equipment state."
                )
                group.append(clone)
            outfit_group_rows.append({"height": RESOLVED_ROW_HEIGHT, "boxes": group})

    kind_clones: dict[str, list[dict[str, Any]]] = {}
    for kind, (table_id, columns) in STATE_PANEL_SOURCES.items():
        entries = table_entries(sheet, table_id)

        def box_covers_kind(box: Mapping[str, Any]) -> bool:
            if box.get("kind") == kind:
                return True
            if kind == "part_detail" and bool(_part_source_keys(box)):
                entry = source_entry(box, sheet, "parts")
                if entry is None:
                    return False
                laterality = meaningful(entry["values"].get("laterality", ""))
                if asymmetric_laterality(laterality):
                    return (
                        box.get("kind") == "part_detail"
                        or box.get("counterpart_comparison") is True
                    )
                return True
            return (
                kind == "outfit_variant"
                and box.get("kind") == "outfit_turnaround"
            )

        covered = {
            meaningful(box.get("source_row_id", ""))
            for profile_row in resolved["rows"]
            for box in profile_row["boxes"]
            if not box.get("source_missing")
            and box_covers_kind(box)
        }
        needed = [
            entry
            for entry in entries
            if entry["row_id"] not in covered
            and row_has_visual_data(entry["values"], columns)
        ]
        if kind == "outfit_variant" and outfit_templates:
            # Every remaining outfit row already received the complete authored
            # outfit_turnaround view group above.
            needed = []
        if not needed:
            continue
        # Continue the authored band's panel-code letter when the profile
        # already carries panels of this kind; otherwise take an unused letter.
        authored_codes = [
            meaningful(str(box.get("panel_code", "")))
            for profile_row in resolved["rows"]
            for box in profile_row["boxes"]
            if box.get("kind") == kind
        ]
        code_prefix = next(
            (code[:1].upper() for code in reversed(authored_codes) if code),
            "",
        )
        if not code_prefix or code_prefix not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            code_prefix = next(
                letter
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                if not any(code.startswith(letter) for code in known_codes)
            )
        next_code_number = 1 + max(
            (
                int(code[1:])
                for code in known_codes
                if code.startswith(code_prefix) and code[1:].isdigit()
            ),
            default=0,
        )
        fallback = STATE_PANEL_FALLBACKS[kind]
        clones = []
        for entry in needed:
            clone = copy.deepcopy(fallback["box"])
            suffix = stable_row_suffix(table_id, entry["row_id"])
            clone["slot_id"] = unique(
                f"{STATE_SLOT_PREFIX[kind]}.{suffix}", known_ids
            )
            clone["output_name"] = unique(
                clone["slot_id"].replace(".", "-") + ".png", known_outputs
            )
            clone["panel_code"] = f"{code_prefix}{next_code_number}"
            next_code_number += 1
            known_codes.add(clone["panel_code"])
            clone["source_index"] = entry["index"]
            clone["source_row_id"] = entry["row_id"]
            attach_editor_row_alias(clone, table_id, entry["row_id"])
            clone["label"] = STATE_PANEL_LABELS[kind].format(number=entry["index"] + 1)
            # The generic kind rule guarantees a self-sufficient instruction
            # even when the table row is sparse; apply_sheet_context then merges
            # the declared details on top like it does for authored panels.
            clone["hint"] = KIND_DRAW_GUIDE[kind]
            clones.append(clone)
        kind_clones[kind] = clones
        counts[kind] = len(clones)
    if not kind_clones and not outfit_group_rows:
        required_height = (
            SCAFFOLD_TOP_OF_ROWS
            + sum(int(row["height"]) for row in resolved["rows"])
            + ROW_GAP * max(0, len(resolved["rows"]) - 1)
            + BOTTOM_MARGIN
        )
        resolved["canvas"][1] = max(int(resolved["canvas"][1]), required_height)
        return resolved, counts
    if outfit_group_rows:
        counts["outfit_turnaround"] = sum(
            len(row["boxes"]) for row in outfit_group_rows
        )

    def pack_kind_rows(
        flat: Sequence[dict[str, Any]], content_width: int
    ) -> list[dict[str, Any]]:
        """Flow one kind's resolved panels into rows.

        The row count is the fewest that lets every row hold its panels at
        their kind-appropriate widths, and the panels are spread evenly across
        those rows instead of filling each row to the brim and stranding one
        or two panels in a short last row.
        """

        total = len(flat)
        for row_count in range(1, total + 1):
            base, extra = divmod(total, row_count)
            capacities = [
                base + (1 if index < extra else 0) for index in range(row_count)
            ]
            rows: list[dict[str, Any]] = []
            index = 0
            fits = True
            for capacity in capacities:
                group = list(flat[index : index + capacity])
                index += capacity
                group_width = (
                    sum(desired_panel_width(box, RESOLVED_ROW_HEIGHT) for box in group)
                    + PANEL_GAP * (capacity - 1)
                )
                if group_width > content_width:
                    fits = False
                    break
                rows.append({"height": RESOLVED_ROW_HEIGHT, "boxes": group})
            if fits:
                return rows
        return [{"height": RESOLVED_ROW_HEIGHT, "boxes": [clone]} for clone in flat]

    def pack_state_rows(content_width: int) -> list[dict[str, Any]]:
        """Flow the resolved panels into rows, one section per kind."""

        rows = copy.deepcopy(outfit_group_rows)
        for kind, clones in kind_clones.items():
            if not clones:
                continue
            packed = pack_kind_rows(copy.deepcopy(clones), content_width)
            packed[0]["section_label"] = KIND_SECTION_LABELS[kind]
            packed[0]["height"] += SECTION_HEADER_HEIGHT
            rows.extend(packed)
        return rows

    authored_width = max(
        (
            row_natural_width(row)
            for row in [*resolved["rows"], *outfit_group_rows]
        ),
        default=0,
    )
    width = max(int(resolved["canvas"][0]), authored_width + SIDE_MARGIN * 2)
    step = 460 + PANEL_GAP  # one panel column of widening per step
    last_rows: list[dict[str, Any]] | None = None
    last_height = 0
    last_width = width
    while True:
        state_rows = pack_state_rows(width - SIDE_MARGIN * 2)
        required_height = SCAFFOLD_TOP_OF_ROWS + sum(
            int(row["height"]) for row in resolved["rows"]
        )
        required_height += sum(int(row["height"]) for row in state_rows)
        required_height += ROW_GAP * (len(resolved["rows"]) + len(state_rows) - 1)
        required_height += BOTTOM_MARGIN
        # Widening adds columns per row and can shorten the stack, so grow
        # while the sheet is taller than wide. Once widening stops reducing
        # the resolved row count it only adds dead margin, so keep the natural
        # width instead.
        if required_height <= ASPECT_LIMIT * width:
            break
        if last_rows is not None and len(state_rows) >= len(last_rows):
            state_rows = last_rows
            required_height = last_height
            width = last_width
            break
        last_rows = state_rows
        last_height = required_height
        last_width = width
        width += step
    height = max(int(resolved["canvas"][1]), required_height)
    resolved["rows"].extend(state_rows)
    resolved["canvas"] = [width, height]
    validate_profile_semantics(resolved)
    return resolved, counts
