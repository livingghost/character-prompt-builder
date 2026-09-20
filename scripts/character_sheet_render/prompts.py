"""Model-facing fill, reference, guide, and anchor text generation."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from character_sheet_render.resolution import KIND_DRAW_GUIDE
from character_sheet_render.sheetdata import (
    FIXED_BINDINGS,
    DRAW_COLUMNS,
    FIXED_VISUAL_TABLES,
    compact_join,
    meaningful,
    table_entries,
)


PANEL_FILL_TRANSPORT = "panel-images"
MASKED_SHEET_TRANSPORT = "masked-sheet"
FILL_TRANSPORTS = frozenset({PANEL_FILL_TRANSPORT, MASKED_SHEET_TRANSPORT})


def character_anchor_lines(sheet: Mapping[str, Any]) -> list[str]:
    """Serialize global identity facts not repeated by a bound panel plan.

    Every fixed visual declaration is global because every applicable panel
    exposing its subject must preserve it. This includes parts, marks, colors,
    clothing or other state coverings, equipment, carried or docked items, and
    non-biological components. Variable declarations and scenario rows remain
    in their owning panel lines. This keeps each authored value present without
    repeating long declarations per panel.
    """

    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    anchors: list[tuple[str, str]] = [
        ("Name", meaningful(fields.get("identity.name", ""))),
        ("Species or domain", meaningful(fields.get("identity.species_domain", ""))),
        ("First-fill visual design brief", meaningful(fields.get("field.model_fill_visual_design_brief", ""))),
        ("Reference-sheet finish", meaningful(fields.get("field.reference_sheet_visual_finish", ""))),
        ("Pronouns", meaningful(fields.get("field.pronouns", ""))),
        ("Kind baseline", meaningful(fields.get("field.kind_baseline_sheet_or_self", ""))),
        ("Form or spine", meaningful(fields.get("field.form_of_spine_sheet_or_self", ""))),
        ("Form display", meaningful(fields.get("field.form_id_display_name", ""))),
        ("Height", meaningful(fields.get("field.height_against_a_stated_measure", ""))),
        ("Build", meaningful(fields.get("field.build_register", ""))),
        ("Key ratios", meaningful(fields.get("field.key_ratios_load_bearing", ""))),
        ("Base form / uncovered configuration", meaningful(fields.get("field.base_form_visual_description", ""))),
        ("Dressed / equipped form", meaningful(fields.get("field.dressed_equipped_form_visual_description", ""))),
        ("Author notes", meaningful(fields.get("field.notes", ""))),
        (
            "Personality and motivations",
            meaningful(fields.get("field.personality_and_motivational_structure", "")),
        ),
        (
            "Counter-element or weakness",
            meaningful(fields.get("field.counter_element_or_weakness", "")),
        ),
        ("Role, world, and standing", meaningful(fields.get("field.role_world_and_standing", ""))),
        (
            "Design themes and organizing principles",
            meaningful(fields.get("field.design_themes_and_organizing_principles", "")),
        ),
        (
            "Theme-derived motifs",
            meaningful(fields.get("field.motifs_derived_from_the_theme_and_where_they_appear", "")),
        ),
        ("Unseen but binding settings", meaningful(fields.get("field.unseen_settings_never_drawn_still_binding", ""))),
        (
            "Signature poses and mannerisms",
            meaningful(fields.get("field.signature_poses_and_mannerisms_described", "")),
        ),
        (
            "Relationships and stance",
            meaningful(fields.get("field.relationships_and_stance_toward_others", "")),
        ),
        (
            "Per-form character deltas",
            meaningful(
                fields.get(
                    "field.per_form_character_deltas_personality_or_stance_shifts_that_are_canon_in_a_given",
                    "",
                )
            ),
        ),
        (
            "Character-specific expression",
            meaningful(fields.get("field.character_specific_expression_described", "")),
        ),
    ]

    def scope(row: Mapping[str, str]) -> str:
        binding = meaningful(row.get("binding", ""))
        if not binding:
            return ""
        if binding == "variable":
            return " [variable: may change only under its written rule; do not freeze as identity]"
        return f" [{binding}: preserve exactly at that scope]"

    for entry in table_entries(sheet, "axes"):
        row = entry["values"]
        axis = meaningful(row.get("axis", ""))
        choices_expression = meaningful(row.get("choices_expression", ""))
        summary = compact_join((axis, choices_expression), separator=": ")
        if summary:
            anchors.append((f"Visual identity axis {entry['row_id']}", summary + scope(row)))

    for entry in table_entries(sheet, "formreg"):
        row = entry["values"]
        summary = compact_join(
            (
                row.get("form_id", ""),
                row.get("display_name", ""),
                row.get("kind_ref", ""),
                row.get("trigger_transition", ""),
                row.get("persists", ""),
            )
        )
        if summary:
            anchors.append((f"Form registry {entry['row_id']}", summary))

    for entry in table_entries(sheet, "invariants"):
        row = entry["values"]
        summary = compact_join(
            (
                row.get("invariant", ""),
                row.get("value", ""),
                row.get("visible_expression", ""),
            ),
            separator=" = ",
        )
        if summary:
            anchors.append((f"Cross-form invariant {entry['row_id']}", summary + scope(row)))

    for table_id in FIXED_VISUAL_TABLES:
        columns = DRAW_COLUMNS[table_id]
        for entry in table_entries(sheet, table_id):
            row = entry["values"]
            if meaningful(row.get("binding", "")) not in FIXED_BINDINGS:
                continue
            summary = compact_join(row.get(column, "") for column in columns)
            if summary:
                anchors.append(
                    (f"Fixed {entry['row_id']}", summary + scope(row))
                )

    for entry in table_entries(sheet, "overrides"):
        row = entry["values"]
        summary = compact_join(
            (
                row.get("attribute", ""),
                "baseline " + meaningful(row.get("baseline", "")) if meaningful(row.get("baseline", "")) else "",
                "this individual instead " + meaningful(row.get("override", "")) if meaningful(row.get("override", "")) else "",
                row.get("reason", ""),
            )
        )
        if summary:
            anchors.append((f"Kind override {entry['row_id']}", summary + scope(row)))

    for entry in table_entries(sheet, "colors"):
        row = entry["values"]
        if meaningful(row.get("binding", "")) in FIXED_BINDINGS:
            continue
        summary = compact_join(
            (row.get("zone", ""), row.get("base", ""), row.get("shadow", ""), row.get("highlight", ""))
        )
        if summary:
            anchors.append((f"Color zone {entry['row_id']}", summary + scope(row)))

    texture = meaningful(fields.get("field.free_01", ""))
    if texture:
        anchors.append(("Rule-governed texture", texture))
    return [f"- {label}: {value}" for label, value in anchors if value]


def guide_lines_for_mode(
    profile: Mapping[str, Any], mode: str, fill_transport: str = PANEL_FILL_TRANSPORT
) -> list[str]:
    if mode == "scaffold" and fill_transport == PANEL_FILL_TRANSPORT:
        return [
            "RENDERER-OWNED COMPOSITION BASE. DO NOT SEND THIS FULL SHEET TO A MASKLESS IMAGE MODEL.",
            "GENERATE ONLY THE DECLARED PANEL RESULT FILES, THEN COMPOSE THEM INTO WHITE INTERIORS.",
        ]
    raw = (
        profile.get("scaffold_guide_lines", profile.get("guide_lines", []))
        if mode == "scaffold"
        else profile.get("reference_guide_lines", [])
    )
    if not isinstance(raw, list):
        return []
    lines = [str(value) for value in raw if isinstance(value, str) and value.strip()]
    if len(lines) > 2:
        raise ValueError("render profile provides more than two guide lines")
    return lines


def build_fill_prompt(
    profile: Mapping[str, Any],
    sheet: Mapping[str, Any],
    plan_rows: Sequence[Mapping[str, Any]],
    *,
    target_slot_id: str | None = None,
    target_content_size: tuple[int, int] | None = None,
) -> str:
    unspecified: list[str] = []
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    base_form = meaningful(fields.get("field.base_form_visual_description", ""))
    dressed_form = meaningful(fields.get("field.dressed_equipped_form_visual_description", ""))
    target_boxes = [
        box
        for row in plan_rows
        for box in row["boxes"]
        if box.get("fill_state") == "fill"
        and (
            target_slot_id is None
            or str(box.get("resolved_slot_id", box.get("slot_id", ""))) == target_slot_id
        )
    ]
    if target_slot_id is not None and len(target_boxes) != 1:
        raise ValueError(
            f"panel-only fill target {target_slot_id!r} must resolve to exactly one fill-state panel"
        )
    selected_slot_ids = {
        str(box.get("resolved_slot_id", box.get("slot_id", ""))) for box in target_boxes
    }

    fill_kind_counts: dict[str, int] = {}
    for row in plan_rows:
        for box in row["boxes"]:
            if box.get("fill_state") != "fill":
                continue
            if target_slot_id is not None and str(
                box.get("resolved_slot_id", box.get("slot_id", ""))
            ) not in selected_slot_ids:
                continue
            kind = str(box.get("kind", ""))
            if kind in KIND_DRAW_GUIDE:
                fill_kind_counts[kind] = fill_kind_counts.get(kind, 0) + 1
    factored_kind_rules = {
        kind: KIND_DRAW_GUIDE[kind]
        for kind, count in fill_kind_counts.items()
        if count > 1 or target_slot_id is not None
    }
    fixed_panel_tables = {
        "mark_detail": "marks",
        "part_detail": "parts",
        "items": "items",
        "outfit_turnaround": "outfits",
        "outfit_detail": "outfits",
        "outfit_variant": "outfits",
    }

    def fixed_visual_entry(table_id: str, row_id: str) -> Mapping[str, Any] | None:
        entry = next(
            (
                candidate
                for candidate in table_entries(sheet, table_id)
                if candidate["row_id"] == row_id
            ),
            None,
        )
        if entry is None:
            return None
        if meaningful(entry["values"].get("binding", "")) not in FIXED_BINDINGS:
            return None
        return entry

    referenced_kinds: list[str] = []

    def name_kind_rule(kind: str) -> str:
        """Name a kind rule in a plan line and guarantee the rule block carries it.

        A plan line that says "Use <kind> rule" must never point at a rule the
        prompt does not state. Recording the reference here, rather than
        deciding the block from how many panels share a kind, keeps the two
        in step however many branches name a rule.
        """

        if kind in KIND_DRAW_GUIDE and kind not in referenced_kinds:
            referenced_kinds.append(kind)
        return f"Use {kind} rule"

    def prompt_panel_hint(box: Mapping[str, Any]) -> str:
        """Factor repeated complete configurations through the anchor block."""

        hint = str(box["hint"])
        if base_form:
            hint = hint.replace(
                f"declared base form: {base_form}",
                "apply the complete Base form / uncovered configuration declared above",
            )
        if dressed_form:
            hint = hint.replace(
                f"declared dressed/equipped form: {dressed_form}",
                "apply the complete Dressed / equipped form declared above",
            )
        kind = str(box.get("kind", ""))
        row_id = meaningful(str(box.get("source_row_id", "")))
        table_id = fixed_panel_tables.get(kind, "")
        if table_id and fixed_visual_entry(table_id, row_id) is not None:
            state_rule = (
                " and the complete Dressed / equipped form declared above"
                if table_id == "outfits"
                else ""
            )
            return f"{name_kind_rule(kind)}{state_rule} and Fixed {row_id} exactly."
        if kind == "evidence_view":
            evidence = next(
                (
                    candidate
                    for candidate in table_entries(sheet, "evidence")
                    if candidate["row_id"] == row_id
                ),
                None,
            )
            if evidence is not None:
                values = evidence["values"]
                subject_table = meaningful(values.get("subject_table", ""))
                subject_row_id = meaningful(values.get("subject_row_id", ""))
                if (
                    subject_table in FIXED_VISUAL_TABLES
                    and fixed_visual_entry(subject_table, subject_row_id) is not None
                ):
                    evidence_details = compact_join(
                        (
                            f"subject {subject_table}/{subject_row_id}",
                            values.get("view_id", ""),
                            values.get("orientation_configuration", ""),
                            values.get("specification", ""),
                        )
                    )
                    return (
                        f"{name_kind_rule('evidence_view')} and Fixed "
                        f"{subject_row_id} exactly; {evidence_details}"
                    )
        guide = factored_kind_rules.get(kind)
        if guide:
            if hint.startswith(guide):
                hint = hint[len(guide) :].lstrip(" ;")
            return name_kind_rule(kind) + (f"; {hint}" if hint else ".")
        return hint

    for row in plan_rows:
        for box in row["boxes"]:
            resolved_slot_id = str(box.get("resolved_slot_id", box.get("slot_id", "")))
            if target_slot_id is not None and resolved_slot_id not in selected_slot_ids:
                continue
            if box.get("fill_state") == "fill" and not meaningful(str(box.get("hint", ""))):
                code = meaningful(str(box.get("panel_code", ""))) or str(
                    box.get("slot_id", "?")
                )
                unspecified.append(str(code))
    if unspecified:
        raise ValueError(
            "fill-state panels have no drawing instructions and image models cannot "
            "be trusted to improvise them; add a hint to the render profile or the "
            "matching sheet-data table for: " + ", ".join(unspecified)
        )
    # Build the plan lines first. They are what names a kind rule, so the rule
    # block cannot be settled until every line has been produced.
    plan_lines: list[str] = []
    for row in plan_rows:
        for box in row["boxes"]:
            resolved_slot_id = str(box.get("resolved_slot_id", box.get("slot_id", "")))
            if target_slot_id is not None and resolved_slot_id not in selected_slot_ids:
                continue
            code = meaningful(str(box.get("panel_code", "")))
            title = " ".join(value for value in (code, box["label"]) if value)
            source_row_id = meaningful(str(box.get("source_row_id", "")))
            source_view_row_id = meaningful(str(box.get("source_view_row_id", "")))
            binding = meaningful(str(box.get("binding", "")))
            source_parts = [value for value in (source_row_id, source_view_row_id) if value]
            if source_row_id.startswith("parts."):
                part_entry = next(
                    (
                        entry
                        for entry in table_entries(sheet, "parts")
                        if entry["row_id"] == source_row_id
                    ),
                    None,
                )
                part_name = (
                    meaningful(part_entry["values"].get("part", ""))
                    if part_entry is not None
                    else ""
                )
                if part_name and part_name.casefold() not in title.casefold():
                    source_parts.append(part_name)
            if binding:
                source_parts.append(binding)
            if source_parts:
                title += " [" + "; ".join(source_parts) + "]"
            state = box["fill_state"]
            if state == "renderer":
                plan_lines.append(f"- {title}: renderer-owned; leave unchanged.")
            elif state == "keep":
                plan_lines.append(
                    f"- {title}: preserve the accepted image already present; do not redraw it."
                )
            elif state == "skip":
                plan_lines.append(f"- {title}: leave blank; do not invent this undeclared panel.")
            else:
                # Profile hints and resolved fallback hints already include the
                # complete kind instruction. Appending KIND_DRAW_GUIDE again
                # duplicates the same sentence for every panel and can push an
                # otherwise complete handoff beyond a target prompt limit.
                plan_lines.append(f"- {title}: {prompt_panel_hint(box)}")

    if target_slot_id is None:
        lines = [
            "Use the attached labeled Character Sheet scaffold as a strict coordinate template.",
            "This full-sheet request is valid only in an interface that applies the attached pixel edit mask.",
            "Apply sheet-edit-mask.png as an edit mask: edit white only and keep black unchanged.",
            "Do not submit this full sheet through a reference-only or maskless image interface.",
            "This text is authoritative; follow it if small printed text differs.",
            "Keep exact canvas aspect and panel positions for coordinate harvesting.",
        ]
    else:
        target_width, target_height = target_content_size or (1, 1)
        lines = [
            "Generate only the artwork for the single Character Sheet panel named below.",
            "Return artwork only. Do not draw a sheet frame, title, label, panel code, caption, profile block, color key, border, or any other text.",
            f"Produce a {target_width} by {target_height} pixel image with the complete declared subject filling the frame.",
            "Do not invent any additional panel or contact-sheet layout.",
        ]
    lines.extend(
        [
        "Draw the same identity consistently in every panel marked for generation. Keep topology, proportions, parts, surfaces, colors, materials, coverings, equipment, and accompanying items coherent across panels.",
        "Binding is authoritative: preserve every fixed fact at its declared scope. Variable facts change only under their written rule and never become permanent identity.",
        "Topology is authoritative: preserve declared component count, connection pattern, symmetry, formation, appendage count, and absence statements. Never add humanoid anatomy unless it is declared.",
        "Fixed visual continuity is global, not limited to marks or anatomy. Every fixed part, mark, wound, damage state, color region, material boundary, covering, outfit feature, item, module, repair, fastener, sensor, and other declared visual remains identical in every applicable panel where its subject is exposed. It may be absent only under its written view, state, or physical-occlusion condition. A panel-specific line that does not repeat the feature never permits removing it. Never copy a unilateral feature onto a counterpart declared plain, intact, absent, or different.",
        "One panel shows only what its plan line describes; never add extra subjects, items, or panels.",
        "Do not add text. Do not paint over headers, footers, borders, the color key, kept accepted panels, or panels marked LEAVE BLANK.",
        "Use a clean reference-sheet presentation with plain panel interiors and even, low-drama lighting unless the visual-finish brief says otherwise.",
        ]
    )
    if referenced_kinds:
        lines.extend(
            (
                "",
                "Panel-kind rules:",
                *(
                    f"- {kind}: {KIND_DRAW_GUIDE[kind]}"
                    for kind in referenced_kinds
                ),
            )
        )
    anchors = character_anchor_lines(sheet)
    if anchors:
        lines.extend(("", "Character anchors:", *anchors))
    lines.extend(("", "Panel plan:", *plan_lines))
    lines.extend(("",))
    if target_slot_id is None:
        lines.append(
            "Return one complete masked edit of the scaffold only. Do not return separate images, annotations, explanations, or extra panels."
        )
    else:
        lines.append(
            "Return one image containing only this panel's artwork. Do not include annotations, explanations, typography, borders, or extra panels."
        )
    return "\n".join(lines).strip() + "\n"


def build_reference_prompt(reference_scope: str) -> str:
    scope_note = (
        "Performance examples on the board are secondary evidence only."
        if reference_scope == "all"
        else "The board intentionally excludes performance-only panels."
    )
    return (
        "Use the attached Character Sheet board only as identity evidence for this exact individual.\n"
        "Preserve stable topology, component count, connection pattern, proportions, silhouette, parts, surface boundaries, colors, marks, damage, materials, coverings, and declared fixed items. Do not assume a humanoid or biological body plan.\n"
        "Only kind-fixed, character-fixed, and individual-fixed evidence is authoritative identity. Variable facts remain variable under their written rules.\n"
        "Do not copy the board layout, labels, panel borders, neutral turnaround poses, white panel backgrounds, or reference-sheet lighting into the new image.\n"
        "The current scene prompt owns pose, expression, action, camera, crop, environment, lighting, wardrobe state, injury, dirt, wetness, and every other transient condition.\n"
        f"{scope_note}\n"
    )
