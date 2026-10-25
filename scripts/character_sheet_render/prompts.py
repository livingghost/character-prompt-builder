"""Model-facing drawing text from authored visual descriptions."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from character_sheet_render.resolution import KIND_DRAW_GUIDE
from character_sheet_render.sheetdata import meaningful


PANEL_FILL_TRANSPORT = "panel-images"
MASKED_SHEET_TRANSPORT = "masked-sheet"
FILL_TRANSPORTS = frozenset({PANEL_FILL_TRANSPORT, MASKED_SHEET_TRANSPORT})


def character_anchor_lines(sheet: Mapping[str, Any]) -> list[str]:
    """Return the author's complete visual descriptions for the image maker."""
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    descriptions = (
        ("Character design", "field.model_fill_visual_design_brief"),
        ("Rendering", "field.reference_sheet_visual_finish"),
        ("Base configuration", "field.base_form_visual_description"),
        ("Dressed or equipped configuration", "field.dressed_equipped_form_visual_description"),
    )
    return [f"{label}: {value}" for label, key in descriptions
            if (value := meaningful(fields.get(key, "")))]


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
    """Render authored depiction text; layout identifiers select work internally."""
    boxes = [box for row in plan_rows for box in row["boxes"]
             if target_slot_id is None
             or str(box.get("resolved_slot_id", box.get("slot_id", ""))) == target_slot_id]
    fill_boxes = [box for box in boxes if box.get("fill_state") == "fill"]
    if target_slot_id is not None and len(fill_boxes) != 1:
        raise ValueError(f"panel-only fill target {target_slot_id!r} must resolve to exactly one fill-state panel")
    unspecified = [str(box.get("resolved_slot_id", box.get("slot_id", "?")))
                   for box in fill_boxes if not meaningful(str(box.get("hint", "")))]
    if unspecified:
        raise ValueError("fill-state panels have no drawing instructions; author their visual description: "
                         + ", ".join(unspecified))
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    if fill_boxes and not meaningful(fields.get("field.model_fill_visual_design_brief", "")):
        raise ValueError("model fill requires field.model_fill_visual_design_brief with the complete visible design and fixed conditions")

    def drawing_text(box: Mapping[str, Any]) -> str:
        text = meaningful(str(box["hint"]))
        guide = KIND_DRAW_GUIDE.get(str(box.get("kind", "")), "")
        return text if not guide or text.startswith(guide) else guide + " " + text

    if target_slot_id is None:
        lines = [
            "Edit the attached labeled Character Sheet scaffold using the attached pixel edit mask.",
            "Fill white mask regions only and keep black mask regions unchanged.",
            "Keep the canvas aspect, panel positions, printed labels, borders, and color key unchanged.",
        ]
    else:
        width, height = target_content_size or (1, 1)
        lines = [
            "Generate only the artwork for one Character Sheet panel.",
            "Return artwork only. Do not draw a sheet frame, title, label, panel code, caption, profile block, color key, border, or any other text.",
            f"Produce a {width} by {height} pixel image with the complete described subject filling the frame.",
            "Return a single image with no additional panels or contact-sheet layout.",
        ]
    lines.extend([
        "Preserve the described identity, topology, proportions, materials, colors, and fixed details wherever visible.",
        "Use the described body plan and component count. Never add humanoid anatomy unless it is described.",
        "Show only the requested view, configuration, or action.",
        "Use plain panel interiors and even lighting unless the rendering description specifies otherwise.",
    ])
    anchors = character_anchor_lines(sheet)
    if anchors:
        lines.extend(["", *anchors])
    lines.append("")
    for box in boxes:
        state = box["fill_state"]
        if target_slot_id is not None:
            lines.append(drawing_text(box))
            continue
        # These labels are printed on the attached scaffold and locate its regions.
        title = " ".join(value for value in (meaningful(str(box.get("panel_code", ""))),
                                              meaningful(str(box.get("label", "")))) if value)
        if not title:
            raise ValueError("a masked-sheet panel requires its visible scaffold label")
        if state in {"renderer", "keep"}:
            instruction = "Keep the existing content unchanged."
        elif state == "skip":
            instruction = "Leave this panel blank."
        else:
            instruction = drawing_text(box)
        lines.append(f"- {title}: {instruction}")
    lines.extend(["", "Return only the requested image, with no explanations or annotations."])
    return "\n".join(lines) + "\n"


def build_reference_prompt(reference_scope: str) -> str:
    scope_note = (
        "Expression, pose, and condition examples show possible states; use the state requested by the current scene."
        if reference_scope == "all"
        else "Use the individual shown in these reference views."
    )
    return (
        "Use the attached Character Sheet board as visual evidence of this individual's stable design.\n"
        "Preserve stable identity features: topology, component count, proportions, silhouette, surface boundaries, underlying colors, permanent markings, and material construction.\n"
        "Do not copy the board layout, labels, borders, turnaround poses, panel backgrounds, or sheet lighting into the new image.\n"
        "Follow the current scene description for action, expression, pose, clothing and equipment, camera, environment, lighting, and temporary appearance or condition.\n"
        "The current scene takes precedence over reference examples for temporary color changes, temporary marks, injuries and healing, wetness, dirt, wear, and other changing states. Do not carry a temporary state into the new image solely because it appears on the board.\n"
        f"{scope_note}\n"
    )
