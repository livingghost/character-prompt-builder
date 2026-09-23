"""Board drawing, artifact emission, and the render_sheet orchestration."""
from __future__ import annotations

import base64
import io
import json
import math
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from character_sheet_render.coverage import coverage_exception_records, sheet_coverage
from character_sheet_render.lineage import resolve_form_lineage
from character_sheet_render.profiles import (
    BORDER,
    BOTTOM_MARGIN,
    DEFAULT_FOOTER_HEIGHT,
    HEADER_HEIGHT,
    PANEL_GAP,
    REFERENCE_TOP_OF_ROWS,
    ROW_GAP,
    SCAFFOLD_TOP_OF_ROWS,
    SECTION_HEADER_HEIGHT,
    SIDE_MARGIN,
    desired_panel_width,
    fill_rows_to_width,
    panel_generation_size,
    row_natural_width,
    row_panel_height,
    validate_profile_semantics,
)
from character_sheet_render.prompts import (
    FILL_TRANSPORTS,
    MASKED_SHEET_TRANSPORT,
    PANEL_FILL_TRANSPORT,
    build_fill_prompt,
    build_reference_prompt,
    guide_lines_for_mode,
)
from character_sheet_render.resolution import (
    KIND_PANEL_CAPTION,
    apply_sheet_context,
    build_panel_plan,
    resolve_state_panels,
)
from character_sheet_render.sheetdata import (
    HEX_RE,
    color_rows,
    compact_join,
    json_bytes,
    meaningful,
    sha256_bytes,
    sha256_file,
)
from character_sheet_render.textmetrics import (
    DISABLED,
    FONT_FAMILY,
    INK,
    MUTED,
    PANEL,
    PAPER,
    REFERENCE_GUIDE,
    SCAFFOLD_GUIDE,
    SOFT,
    begin_raster_text_collection,
    build_raster_text_layer,
    estimated_text_units,
    fit_title_size,
    fit_wrapped_text,
    make_svg_text,
    make_wrapped_svg_text,
    take_raster_text_overlays,
)


RENDERER_ID = "render_character_sheet"


def rasterize_board(svg_markup: str, png_path: Path) -> None:
    """Draw the board SVG to PNG with resvg and the installed fonts.

    The board's own text uses the first installed family in FONT_FAMILY. When no
    installed font draws that text, the render stops rather than leaving the text out.
    """

    try:
        import resvg_py
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "resvg-py and Pillow are required. Run scripts/check_dependencies.py --profile visual."
        ) from exc
    probe = resvg_py.svg_to_bytes(
        svg_string=(
            '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32">'
            f'<text x="0" y="24" font-size="20" font-family="{FONT_FAMILY}">Hg</text></svg>'
        )
    )
    with Image.open(io.BytesIO(probe)) as probe_image:
        if probe_image.getchannel("A").getbbox() is None:
            raise RuntimeError(f"no installed font matches the sheet font families: {FONT_FAMILY}")
    png_path.write_bytes(resvg_py.svg_to_bytes(svg_string=svg_markup))


def image_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_palette(
    svg: list[str],
    rows: Sequence[Mapping[str, str]],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{REFERENCE_GUIDE}"/>')
    valid_rows = list(rows)
    if not valid_rows:
        make_svg_text(
            svg,
            x + width / 2,
            y + height / 2 + 7,
            "NO FIXED COLOR ZONES DECLARED",
            20,
            anchor="middle",
            weight="700",
            fill=MUTED,
        )
        return
    gap = 8
    columns = min(10, len(valid_rows))
    grid_rows = math.ceil(len(valid_rows) / columns)
    cell_height = int((height - gap * (grid_rows - 1)) / grid_rows)
    if cell_height < 92:
        raise ValueError(
            "palette panel is too short for all declared color targets without omission"
        )
    for index, row in enumerate(valid_rows):
        grid_row = index // columns
        grid_column = index % columns
        entries_in_row = min(columns, len(valid_rows) - grid_row * columns)
        segment = int((width - gap * (entries_in_row - 1)) / entries_in_row)
        cursor = x + grid_column * (segment + gap)
        cell_y = y + grid_row * (cell_height + gap)
        if grid_column == entries_in_row - 1:
            segment = x + width - cursor
        base = row.get("base", "") if HEX_RE.fullmatch(row.get("base", "")) else "#ffffff"
        shadow = (
            row.get("shadow", "") if HEX_RE.fullmatch(row.get("shadow", "")) else base
        )
        highlight = (
            row.get("highlight", "")
            if HEX_RE.fullmatch(row.get("highlight", ""))
            else base
        )
        label_height = max(30, min(58, cell_height // 2))
        swatch_h = cell_height - label_height - 4
        if swatch_h < 20:
            raise ValueError("palette panel is too short to show complete labels")
        main_w = max(20, int(segment * 0.68))
        side_w = max(8, (segment - main_w) // 2)
        svg.append(
            f'<rect x="{cursor}" y="{cell_y}" width="{main_w}" height="{swatch_h}" fill="{base}" stroke="{INK}" stroke-width="1"/>'
        )
        svg.append(
            f'<rect x="{cursor + main_w}" y="{cell_y}" width="{side_w}" height="{swatch_h}" fill="{shadow}" stroke="{INK}" stroke-width="1"/>'
        )
        svg.append(
            f'<rect x="{cursor + main_w + side_w}" y="{cell_y}" width="{segment - main_w - side_w}" height="{swatch_h}" fill="{highlight}" stroke="{INK}" stroke-width="1"/>'
        )
        zone_label = row.get("zone", "")
        if row.get("binding") == "variable" and zone_label:
            zone_label += " [VARIABLE]"
        label = compact_join((zone_label, base), separator=" ") or base
        label_size, label_lines, label_line_height = fit_wrapped_text(
            label,
            width_px=segment - 8,
            base_size=12,
            available_height=label_height,
            minimum_size=8,
        )
        make_wrapped_svg_text(
            svg,
            cursor + segment / 2,
            cell_y + swatch_h + label_size + 5,
            label,
            label_size,
            width_px=segment - 8,
            max_lines=len(label_lines),
            line_height=label_line_height,
            anchor="middle",
            weight="400",
            fill=INK,
        )


def render_profile_summary(
    svg: list[str],
    sheet: Mapping[str, Any],
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """Draw a protected, scan-friendly identity summary into the board."""

    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    entries = [
        ("NAME", meaningful(fields.get("identity.name", ""))),
        ("KIND / DOMAIN", meaningful(fields.get("identity.species_domain", ""))),
        ("EXTENT", meaningful(fields.get("field.height_against_a_stated_measure", ""))),
        ("BUILD / CONFIGURATION", meaningful(fields.get("field.build_register", ""))),
        ("KEY RATIOS", meaningful(fields.get("field.key_ratios_load_bearing", ""))),
        (
            "DESIGN PRINCIPLES",
            meaningful(fields.get("field.design_themes_and_organizing_principles", "")),
        ),
    ]
    columns = 3
    rows = 2
    gap = 12
    cell_width = int((width - gap * (columns - 1)) / columns)
    cell_height = int((height - gap * (rows - 1)) / rows)
    for index, (label, value) in enumerate(entries):
        column = index % columns
        row = index // columns
        cell_x = x + column * (cell_width + gap)
        cell_y = y + row * (cell_height + gap)
        svg.append(
            f'<rect x="{cell_x}" y="{cell_y}" width="{cell_width}" height="{cell_height}" '
            f'fill="{REFERENCE_GUIDE}" stroke="{MUTED}" stroke-width="1"/>'
        )
        make_svg_text(svg, cell_x + 10, cell_y + 18, label, 12, weight="800", fill=MUTED)
        display = value or "NOT DECLARED"
        size, lines, line_height = fit_wrapped_text(
            display,
            width_px=cell_width - 20,
            base_size=15,
            available_height=max(18, cell_height - 25),
            minimum_size=10,
        )
        if " ".join(lines) != " ".join(display.split()):
            raise ValueError(f"profile field {label!r} was not rendered completely")
        make_wrapped_svg_text(
            svg,
            cell_x + 10,
            cell_y + 38,
            display,
            size,
            width_px=cell_width - 20,
            max_lines=max(1, len(lines)),
            line_height=line_height,
            anchor="start",
            weight="600",
            fill=INK,
        )


def draw_header(
    svg: list[str],
    *,
    profile: Mapping[str, Any],
    sheet: Mapping[str, Any],
    width: int,
    mode: str,
) -> None:
    fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
    status = "MODEL-FILL SCAFFOLD" if mode == "scaffold" else "REFERENCE BOARD"
    status_fill = SCAFFOLD_GUIDE if mode == "scaffold" else INK
    status_size = 22
    status_width = estimated_text_units(status) * status_size
    title = str(profile["title"])
    title_width = int(width - SIDE_MARGIN * 2 - status_width - 32)
    title_size = fit_title_size(title, title_width, 42, minimum_size=12)
    if estimated_text_units(title) * title_size > title_width:
        raise ValueError(f"profile title does not fit without omission: {title!r}")
    make_svg_text(svg, SIDE_MARGIN, 58, title, title_size)
    make_svg_text(
        svg,
        width - SIDE_MARGIN,
        58,
        status,
        status_size,
        anchor="end",
        weight="800",
        fill=status_fill,
    )
    header_fields = profile["header_fields"]
    gap = 20
    field_width = (width - SIDE_MARGIN * 2 - gap * (len(header_fields) - 1)) / len(header_fields)
    x = SIDE_MARGIN
    for header_field in header_fields:
        value = meaningful(fields.get(header_field["field_id"], "")) or "________________"
        label = str(header_field["label"])
        label_size = fit_title_size(label, int(field_width), 13, minimum_size=8)
        if estimated_text_units(label) * label_size > field_width:
            raise ValueError(
                f"header label {header_field['field_id']} does not fit without omission"
            )
        make_svg_text(svg, x, 90, label, label_size, weight="700", fill=MUTED)
        value_size = fit_title_size(value, int(field_width), 21, minimum_size=8)
        if estimated_text_units(value) * value_size > field_width:
            raise ValueError(
                f"header field {header_field['field_id']} does not fit without omission"
            )
        make_svg_text(svg, x, 116, value, value_size, weight="400", fill=INK)
        x += field_width + gap
    svg.append(
        f'<line x1="{SIDE_MARGIN}" y1="130" x2="{width - SIDE_MARGIN}" y2="130" stroke="{INK}" stroke-width="4"/>'
    )


def draw_guide(
    svg: list[str],
    *,
    profile: Mapping[str, Any],
    width: int,
    mode: str,
    fill_transport: str,
) -> None:
    guide_lines = guide_lines_for_mode(profile, mode, fill_transport)
    if not guide_lines:
        return
    if mode == "scaffold":
        svg.append(
            f'<rect x="{SIDE_MARGIN}" y="144" width="{width - SIDE_MARGIN * 2}" height="68" fill="#fff8f7" stroke="{SCAFFOLD_GUIDE}" stroke-width="3"/>'
        )
        fill = SCAFFOLD_GUIDE
    else:
        svg.append(
            f'<rect x="{SIDE_MARGIN}" y="144" width="{width - SIDE_MARGIN * 2}" height="68" fill="{REFERENCE_GUIDE}" stroke="{INK}" stroke-width="3"/>'
        )
        fill = INK
    if len(guide_lines) == 1:
        guide_size = fit_title_size(
            guide_lines[0], width - SIDE_MARGIN * 2 - 28, 20, minimum_size=8
        )
        if estimated_text_units(guide_lines[0]) * guide_size > width - SIDE_MARGIN * 2 - 28:
            raise ValueError("guide line does not fit without omission")
        make_svg_text(
            svg,
            width / 2,
            185,
            guide_lines[0],
            guide_size,
            anchor="middle",
            weight="800",
            fill=fill,
        )
    else:
        first_size = fit_title_size(
            guide_lines[0], width - SIDE_MARGIN * 2 - 28, 19, minimum_size=8
        )
        second_size = fit_title_size(
            guide_lines[1], width - SIDE_MARGIN * 2 - 28, 18, minimum_size=8
        )
        if any(
            estimated_text_units(line) * size > width - SIDE_MARGIN * 2 - 28
            for line, size in zip(guide_lines, (first_size, second_size))
        ):
            raise ValueError("guide line does not fit without omission")
        make_svg_text(
            svg,
            width / 2,
            171,
            guide_lines[0],
            first_size,
            anchor="middle",
            weight="800",
            fill=fill,
        )
        make_svg_text(
            svg,
            width / 2,
            197,
            guide_lines[1],
            second_size,
            anchor="middle",
            weight="700",
            fill=fill,
        )


def draw_model_brief(
    svg: list[str], *, sheet: Mapping[str, Any], width: int, fill_transport: str
) -> None:
    x = SIDE_MARGIN
    y = 224
    h = 88
    total_width = width - SIDE_MARGIN * 2
    left_width = int(total_width * 0.68)
    right_width = total_width - left_width - 16
    svg.append(
        f'<rect x="{x}" y="{y}" width="{total_width}" height="{h}" fill="{SOFT}" stroke="{INK}" stroke-width="2"/>'
    )
    make_svg_text(svg, x + 14, y + 22, "VISUAL IDENTITY BRIEF", 13, weight="800", fill=MUTED)
    identity_contract_text = (
        "Each panel-fill-prompts file contains the complete identity contract for that one panel. The full sheet is not a model input."
        if fill_transport == PANEL_FILL_TRANSPORT
        else "The complete identity contract is in the attached sheet-fill-prompt.txt. Section and panel labels define each editable region."
    )
    make_wrapped_svg_text(
        svg,
        x + 14,
        y + 46,
        identity_contract_text,
        16,
        width_px=left_width - 28,
        max_lines=2,
        line_height=19,
        anchor="start",
        weight="400",
        fill=INK,
    )
    divider_x = x + left_width
    svg.append(
        f'<line x1="{divider_x}" y1="{y + 10}" x2="{divider_x}" y2="{y + h - 10}" stroke="{INK}" stroke-width="1"/>'
    )
    make_svg_text(svg, divider_x + 14, y + 22, "REFERENCE-SHEET FINISH", 13, weight="800", fill=MUTED)
    finish_contract_text = (
        "Keep this renderer-owned base unchanged. Compose panel result PNGs only into their declared white interiors."
        if fill_transport == PANEL_FILL_TRANSPORT
        else "The complete visual-finish contract is in sheet-fill-prompt.txt. Preserve the scaffold and edit only masked interiors."
    )
    make_wrapped_svg_text(
        svg,
        divider_x + 14,
        y + 46,
        finish_contract_text,
        15,
        width_px=right_width - 28,
        max_lines=2,
        line_height=18,
        anchor="start",
        weight="400",
        fill=INK,
    )


def create_edit_mask(path: Path, *, width: int, height: int, boxes: Sequence[Mapping[str, Any]]) -> None:
    from PIL import Image, ImageDraw

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        if not box.get("harvest"):
            continue
        left = round(float(box["content_x"]))
        top = round(float(box["content_y"]))
        right = round(float(box["content_x"]) + float(box["content_w"])) - 1
        bottom = round(float(box["content_y"]) + float(box["content_h"])) - 1
        draw.rectangle((left, top, right, bottom), fill=255)
    mask.save(path, format="PNG")


def write_panel_fill_requests(
    *,
    out_dir: Path,
    profile: Mapping[str, Any],
    sheet: Mapping[str, Any],
    plan_rows: Sequence[Mapping[str, Any]],
    layout_boxes: Sequence[Mapping[str, Any]],
    scaffold_path: Path,
    layout_path: Path,
    panel_geometries: Sequence[tuple[int, int]] | None = None,
) -> tuple[Path, str, int]:
    """Write one maskless model request per editable panel.

    None of these requests includes the full sheet. A later deterministic
    compositor pastes result pixels into the declared content rectangles of the
    pristine renderer-owned scaffold.
    """

    prompts_dir = out_dir / "panel-fill-prompts"
    if prompts_dir.resolve().parent != out_dir.resolve():
        raise ValueError("panel fill prompt directory must be a direct child of the render output")
    if prompts_dir.exists():
        shutil.rmtree(prompts_dir)
    prompts_dir.mkdir(parents=True, exist_ok=False)

    plan_boxes = {
        str(box.get("resolved_slot_id", box.get("slot_id", ""))): box
        for row in plan_rows
        for box in row["boxes"]
        if box.get("fill_state") == "fill"
    }
    requests: list[dict[str, Any]] = []
    for layout_box in layout_boxes:
        if not layout_box.get("harvest"):
            continue
        slot_id = str(layout_box["resolved_slot_id"])
        plan_box = plan_boxes.get(slot_id)
        if plan_box is None:
            raise ValueError(f"editable layout panel has no source plan: {slot_id}")
        output_name = str(layout_box["output_name"])
        prompt_name = Path(output_name).with_suffix(".txt").name
        prompt_path = prompts_dir / prompt_name
        content_width = int(round(float(layout_box["content_w"])))
        content_height = int(round(float(layout_box["content_h"])))
        generation_width, generation_height = panel_generation_size(
            profile, layout_box, (content_width, content_height), panel_geometries
        )
        prompt = build_fill_prompt(
            profile,
            sheet,
            plan_rows,
            target_slot_id=slot_id,
            target_content_size=(generation_width, generation_height),
        )
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        requests.append(
            {
                "request_id": slot_id,
                "panel_code": layout_box.get("panel_code", ""),
                "slot_id": layout_box["slot_id"],
                "resolved_slot_id": slot_id,
                "kind": layout_box.get("kind", "drawing"),
                "reference_role": layout_box.get("reference_role", "identity"),
                "prompt": {
                    "path": prompt_path.relative_to(out_dir).as_posix(),
                    "sha256": sha256_file(prompt_path),
                },
                "result_file": output_name,
                # What the returned image is judged against. It is not in the
                # prompt: a rule about what may not change is not a thing to draw.
                "review": layout_box.get("review"),
                "target": {
                    "content_x": int(round(float(layout_box["content_x"]))),
                    "content_y": int(round(float(layout_box["content_y"]))),
                    "content_w": content_width,
                    "content_h": content_height,
                    # The box is where a reduced copy is shown. This is the
                    # size of the image the model is asked to return.
                    "generation_w": generation_width,
                    "generation_h": generation_height,
                },
            }
        )
    if not requests:
        raise ValueError("panel-images transport requires at least one fill-state panel")

    canonical_request_ids = [
        str(request["request_id"])
        for request in requests
        if request["kind"] == "canonical_view" and request["reference_role"] == "identity"
    ]
    identity_anchor_request_id = (
        canonical_request_ids[0]
        if canonical_request_ids
        else str(
            next(
                (
                    request["request_id"]
                    for request in requests
                    if request["reference_role"] == "identity"
                ),
                requests[0]["request_id"],
            )
        )
    )
    for request in requests:
        request_id = str(request["request_id"])
        if request_id == identity_anchor_request_id:
            request["generation_stage"] = 1
            request["required_accepted_reference_results"] = []
        elif request_id in canonical_request_ids:
            request["generation_stage"] = 2
            request["required_accepted_reference_results"] = [identity_anchor_request_id]
        else:
            request["generation_stage"] = 3
            request["required_accepted_reference_results"] = (
                canonical_request_ids or [identity_anchor_request_id]
            )

    manifest = {
        "producer": {"id": RENDERER_ID},
        "transport": {
            "id": PANEL_FILL_TRANSPORT,
            "full_sheet_model_input": False,
            "pixel_edit_mask_required": False,
            "result_contract": "one artwork-only PNG per request",
            "panel_geometries": (
                [{"w": width, "h": height} for width, height in panel_geometries]
                if panel_geometries
                else None
            ),
            "generation_order": "accept the identity anchor, derive and accept canonical views, then generate remaining panels with accepted canonical results attached as identity references",
        },
        "identity_anchor_request_id": identity_anchor_request_id,
        "scaffold": {
            "path": scaffold_path.relative_to(out_dir).as_posix(),
            "sha256": sha256_file(scaffold_path),
        },
        "layout": {
            "path": layout_path.relative_to(out_dir).as_posix(),
            "sha256": sha256_file(layout_path),
        },
        "requests": requests,
    }
    manifest_path = out_dir / "panel-fill-requests.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path, sha256_file(manifest_path), len(requests)


def write_reference_bundle(
    path: Path,
    *,
    rows: Sequence[Mapping[str, Any]],
    board_png: Path,
    board_scope: str,
    profile_id: str,
    sidecar_path: Path | None,
) -> Path:
    """List every accepted slot image with its role, for downstream selection.

    The board shows what its scope allows; the bundle lists all of it, so a
    consumer choosing references for a shot sees the performance panels as
    well as the identity panels and picks within its own attachment limit.
    """

    from PIL import Image

    panels: list[dict[str, Any]] = []
    for row in rows:
        section = meaningful(str(row.get("section_label", "")))
        for box in row["boxes"]:
            if box.get("kind") in {"palette", "profile"} or box.get("image_path") is None:
                continue
            image_path = Path(box["image_path"])
            with Image.open(image_path) as image:
                width, height = image.size
            slot = box.get("slot") or {}
            panels.append(
                {
                    "slot_id": str(box["resolved_slot_id"]),
                    "kind": str(box.get("kind", "")),
                    "reference_role": str(box.get("reference_role", "identity")),
                    "binding": box.get("binding"),
                    "label": str(box.get("label", "")),
                    "section_label": section or None,
                    "source_row_id": box.get("source_row_id"),
                    "image_path": str(box["image_relative"]),
                    "image_sha256": sha256_file(image_path),
                    "width": width,
                    "height": height,
                    "generation_package": meaningful(str(slot.get("generation_package", ""))) or None,
                }
            )
    roles: dict[str, int] = {}
    for panel in panels:
        roles[panel["reference_role"]] = roles.get(panel["reference_role"], 0) + 1
    bundle = {
        "artifact_type": "character-sheet-reference-bundle",
        "producer": {"id": RENDERER_ID},
        "profile": profile_id,
        "sheet_data_sha256": sha256_file(sidecar_path) if sidecar_path else None,
        "board": {
            "path": board_png.name,
            "sha256": sha256_file(board_png),
            "scope": board_scope,
            "audience": "people",
        },
        "roles": roles,
        "panels": panels,
    }
    path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def render_sheet(
    profile: Mapping[str, Any],
    sheet: Mapping[str, Any],
    *,
    sheet_dir: Path,
    mode: str,
    out_dir: Path,
    reference_scope: str = "all",
    profile_path: Path | None = None,
    sidecar_path: Path | None = None,
    profile_selection: Mapping[str, Any] | None = None,
    fill_transport: str = PANEL_FILL_TRANSPORT,
    pixel_edit_mask_confirmed: bool = False,
    panel_geometries: Sequence[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    if mode not in {"scaffold", "reference"}:
        raise ValueError("mode must be scaffold or reference")
    if reference_scope not in {"identity", "all"}:
        raise ValueError("reference_scope must be identity or all")
    if fill_transport not in FILL_TRANSPORTS:
        raise ValueError("fill_transport must be panel-images or masked-sheet")
    if mode == "scaffold" and fill_transport == MASKED_SHEET_TRANSPORT and not pixel_edit_mask_confirmed:
        raise ValueError(
            "masked-sheet transport requires explicit confirmation that the active image interface applies a pixel edit mask; use panel-images for a maskless or reference-only interface"
        )

    resolved_profile, resolved_state_panels = resolve_state_panels(profile, sheet)
    resolved_profile = apply_sheet_context(resolved_profile, sheet)
    validate_profile_semantics(resolved_profile)
    coverage = sheet_coverage(resolved_profile, sheet)
    if coverage["structural_errors"]:
        raise ValueError(
            "the character sheet violates non-exemptible identity structure: "
            + "; ".join(coverage["structural_errors"])
            + ". The minimum topology evidence and explicit laterality/counterpart "
            "contracts cannot be waived by field.sheet_coverage_exceptions."
        )
    form_lineage = resolve_form_lineage(
        sheet,
        sheet_dir=sheet_dir,
        sidecar_path=sidecar_path,
    )
    coverage_exceptions = ""
    exception_records: list[dict[str, str]] = []
    if mode == "scaffold" and coverage["gaps"]:
        fields = sheet.get("fields") if isinstance(sheet.get("fields"), Mapping) else {}
        coverage_exceptions = meaningful(
            fields.get("field.sheet_coverage_exceptions", "")
        )
        if not coverage_exceptions:
            raise ValueError(
                "the layout profile leaves declared character content or the minimum "
                "sheet floor without a frame: " + "; ".join(coverage["gaps"])
                + ". Add the missing panels to the layout profile, or declare the "
                "deliberate omission in field.sheet_coverage_exceptions."
            )
        exception_records = coverage_exception_records(
            coverage["gaps"], coverage_exceptions
        )
    plan_rows = build_panel_plan(
        resolved_profile,
        sheet,
        sheet_dir=sheet_dir,
        mode=mode,
        reference_scope=reference_scope,
    )
    if mode == "reference" and not any(
        box.get("kind") == "palette" or box.get("image_path") is not None
        for row in plan_rows
        for box in row["boxes"]
    ):
        raise ValueError("reference mode requires at least one accepted slot image or fixed color row")
    # Validate the fill plan before any artifact is written so a refused render
    # never leaves a stale prompt or mask beside a freshly drawn scaffold.
    fill_prompt = None
    if mode == "scaffold" and fill_transport == MASKED_SHEET_TRANSPORT:
        fill_prompt = build_fill_prompt(resolved_profile, sheet, plan_rows)

    # Normalize every model-facing board to the bundled model's supported 2:3
    # output ratio. Work in exact 2-by-3 integer units so harvesting never
    # depends on an aspect-tolerance exception.
    minimum_width = max(
        800,
        max((row_natural_width(row) for row in plan_rows), default=0)
        + SIDE_MARGIN * 2,
    )
    top_of_rows = SCAFFOLD_TOP_OF_ROWS if mode == "scaffold" else REFERENCE_TOP_OF_ROWS

    def stack_height() -> int:
        return (
            top_of_rows
            + sum(row["height"] for row in plan_rows)
            + ROW_GAP * max(0, len(plan_rows) - 1)
            + BOTTOM_MARGIN
        )

    if mode == "scaffold" and fill_transport == MASKED_SHEET_TRANSPORT:
        # The whole board is the model input here, so it takes the bundled
        # model's 2:3 output ratio in exact 2-by-3 integer units. Rows are not
        # scaled to that width: a taller stack would widen the canvas and a
        # wider canvas would scale the rows taller again, without end.
        aspect_unit = max(math.ceil(minimum_width / 2), math.ceil(stack_height() / 3))
        width = aspect_unit * 2
        height = aspect_unit * 3
    else:
        # The board is never a model input in the other transports, so it has
        # no ratio to keep. It is as wide as its widest row and every other row
        # is scaled up to that width, so the panels are as large as the board
        # allows and the margins are the gutters and nothing else.
        # The profile's declared width is the board's reading width; the rows
        # are scaled up to it, and a row that is wider than it widens the board.
        width = max(minimum_width, int(resolved_profile["canvas"][0]))
        fill_rows_to_width(plan_rows, width)
        height = stack_height()

    begin_raster_text_collection()
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{PAPER}"/>',
    ]
    draw_header(svg, profile=resolved_profile, sheet=sheet, width=width, mode=mode)
    draw_guide(
        svg,
        profile=resolved_profile,
        width=width,
        mode=mode,
        fill_transport=fill_transport,
    )
    if mode == "scaffold":
        draw_model_brief(
            svg,
            sheet=sheet,
            width=width,
            fill_transport=fill_transport,
        )

    colors = color_rows(sheet)
    if mode == "reference" and reference_scope == "identity":
        colors = [row for row in colors if row.get("binding") != "variable"]
    layout_boxes: list[dict[str, Any]] = []
    inputs: list[dict[str, str]] = []
    y = top_of_rows
    for row_index, plan_row in enumerate(plan_rows):
        row_y = y
        boxes = plan_row["boxes"]
        gap = PANEL_GAP
        row_height = int(plan_row["height"])
        section_label = meaningful(str(plan_row.get("section_label", "")))
        if section_label:
            svg.append(
                f'<rect x="{SIDE_MARGIN}" y="{y}" width="{width - SIDE_MARGIN * 2}" '
                f'height="{SECTION_HEADER_HEIGHT - 6}" fill="{REFERENCE_GUIDE}"/>'
            )
            section_size = fit_title_size(
                section_label, width - SIDE_MARGIN * 2 - 28, 21, minimum_size=8
            )
            if (
                estimated_text_units(section_label) * section_size
                > width - SIDE_MARGIN * 2 - 28
            ):
                raise ValueError(
                    f"section label does not fit without omission: {section_label!r}"
                )
            make_svg_text(
                svg,
                SIDE_MARGIN + 14,
                y + 27,
                section_label,
                section_size,
                weight="800",
                fill=INK,
            )
            y += SECTION_HEADER_HEIGHT
        box_height = row_panel_height(plan_row)
        if any(box.get("kind") in {"palette", "profile"} for box in boxes):
            # The color key is a renderer-owned strip, not a drawing frame.
            x = SIDE_MARGIN
        else:
            # Panels keep their kind-appropriate shape; the row's group is
            # centered in whatever width the canvas offers.
            row_width = row_natural_width(plan_row)
            x = SIDE_MARGIN + max(0, (width - SIDE_MARGIN * 2 - row_width) // 2)
        for box_index, box in enumerate(boxes):
            actual_width = (
                width - SIDE_MARGIN * 2
                if box.get("kind") in {"palette", "profile"}
                else desired_panel_width(box, box_height)
            )
            footer_height = int(box.get("footer_height", DEFAULT_FOOTER_HEIGHT))
            content_x = x + BORDER
            content_y = y + HEADER_HEIGHT + BORDER
            content_width = actual_width - BORDER * 2
            content_height = box_height - HEADER_HEIGHT - footer_height - BORDER * 2
            if content_height <= 0:
                raise ValueError(f"panel {box['slot_id']} has no drawable content area")

            state = str(box["fill_state"])
            harvest = mode == "scaffold" and state == "fill"
            layout_box = {
                "panel_code": box.get("panel_code", ""),
                "slot_id": box["slot_id"],
                "resolved_slot_id": box["resolved_slot_id"],
                "aliases": list(box.get("aliases", [])),
                "output_name": box.get(
                    "output_name", box["slot_id"].replace(".", "-") + ".png"
                ),
                "label": box["label"],
                "hint": box["hint"],
                "caption": meaningful(str(box.get("caption", "")))
                or KIND_PANEL_CAPTION.get(str(box.get("kind", "")), "See attached panel plan."),
                "kind": box.get("kind", "drawing"),
                "source_row_id": box.get("source_row_id"),
                "source_view_row_id": box.get("source_view_row_id"),
                "binding": box.get("binding"),
                "reference_role": box.get("reference_role", "identity"),
                "long_side": box.get("long_side"),
                "review": box.get("review"),
                "section_label": section_label,
                "requested_fill_policy": box["requested_fill_policy"],
                "fill_state": state,
                "active": state == "fill",
                "harvest": harvest,
                "x": x,
                "y": y,
                "w": actual_width,
                "h": box_height,
                "header_height": HEADER_HEIGHT,
                "footer_height": footer_height,
                "content_x": content_x,
                "content_y": content_y,
                "content_w": content_width,
                "content_h": content_height,
            }
            layout_boxes.append(layout_box)

            panel_fill = REFERENCE_GUIDE if box.get("kind") == "palette" else PANEL
            if state == "skip":
                panel_fill = DISABLED
            svg.append(
                f'<rect x="{x}" y="{y}" width="{actual_width}" height="{box_height}" fill="{panel_fill}" stroke="{INK}" stroke-width="{BORDER}"/>'
            )

            filled = False
            if box.get("kind") == "palette":
                render_palette(
                    svg,
                    colors,
                    x=content_x,
                    y=content_y,
                    width=content_width,
                    height=content_height,
                )
                filled = True
            elif box.get("kind") == "profile":
                render_profile_summary(
                    svg,
                    sheet,
                    x=content_x,
                    y=content_y,
                    width=content_width,
                    height=content_height,
                )
                filled = True
            elif state == "keep" and box.get("image_path") is not None:
                image_path = Path(box["image_path"])
                inputs.append(
                    {
                        "slot_id": str(box["resolved_slot_id"]),
                        "path": str(box["image_relative"]),
                        "sha256": sha256_file(image_path),
                    }
                )
                svg.append(
                    f'<image x="{content_x}" y="{content_y}" width="{content_width}" height="{content_height}" '
                    f'preserveAspectRatio="xMidYMid meet" href="{image_data_uri(image_path)}"/>'
                )
                filled = True
            elif state == "skip":
                svg.append(
                    f'<rect x="{content_x}" y="{content_y}" width="{content_width}" height="{content_height}" fill="{DISABLED}" stroke="{MUTED}" stroke-width="2" stroke-dasharray="10 8"/>'
                )
                make_svg_text(
                    svg,
                    content_x + content_width / 2,
                    content_y + content_height / 2 + 8,
                    "LEAVE BLANK",
                    24 if actual_width >= 340 else 20,
                    anchor="middle",
                    weight="800",
                    fill=MUTED,
                )
                filled = True

            svg.append(
                f'<rect x="{x}" y="{y}" width="{actual_width}" height="{HEADER_HEIGHT}" fill="{INK}"/>'
            )
            code = meaningful(str(box.get("panel_code", "")))
            title = " ".join(value for value in (code, box["label"]) if value)
            if state == "skip" and "UNUSED" not in title:
                title = " ".join(value for value in (code, "UNUSED", box["label"]) if value)
            title_size = fit_title_size(
                title,
                actual_width - 24,
                23 if actual_width >= 360 else 19,
                minimum_size=8,
            )
            if estimated_text_units(title) * title_size > actual_width - 24:
                raise ValueError(
                    f"panel {box['slot_id']} title does not fit without omission: {title!r}"
                )
            make_svg_text(
                svg,
                x + actual_width / 2,
                y + 33,
                title,
                title_size,
                anchor="middle",
                weight="800",
                fill="#ffffff",
            )
            footer_y = y + box_height - footer_height
            svg.append(
                f'<rect x="{x + BORDER / 2}" y="{footer_y}" width="{actual_width - BORDER}" height="{footer_height - BORDER / 2}" fill="{SOFT}"/>'
            )
            hint = meaningful(str(box.get("caption", ""))) or KIND_PANEL_CAPTION.get(
                str(box.get("kind", "")), "See attached panel plan."
            )
            if state == "skip":
                hint = "Leave blank; this feature or state is not declared."
            elif state == "keep" and mode == "scaffold":
                hint = "Accepted image; preserve this panel unchanged."
            hint_size = 15 if actual_width >= 360 else 14
            hint_size, lines, line_height = fit_wrapped_text(
                hint,
                width_px=actual_width - 24,
                base_size=hint_size,
                available_height=footer_height - 6,
            )
            if " ".join(lines) != " ".join(hint.split()):
                raise ValueError(
                    f"panel {box['slot_id']} raster caption does not fit without omission"
                )
            total_text_height = line_height * len(lines)
            hint_y = footer_y + max(
                hint_size + 2,
                (footer_height - total_text_height) / 2 + hint_size - 2,
            )
            make_wrapped_svg_text(
                svg,
                x + actual_width / 2,
                hint_y,
                hint,
                hint_size,
                width_px=actual_width - 24,
                max_lines=max(1, len(lines)),
                line_height=line_height,
                anchor="middle",
                weight="400",
                fill=MUTED,
            )
            if mode == "reference" and not filled:
                raise ValueError(f"reference panel {box['slot_id']} has no accepted image")
            x += actual_width + gap
        y = row_y + row_height
        if row_index != len(plan_rows) - 1:
            y += ROW_GAP
    raster_text_manifest: dict[str, Any] | None = None
    raster_text_overlays = take_raster_text_overlays()
    if raster_text_overlays:
        raster_layer_uri, raster_text_manifest = build_raster_text_layer(
            width=width,
            height=height,
            overlays=raster_text_overlays,
        )
        svg.append(
            f'<image x="0" y="0" width="{width}" height="{height}" '
            f'href="{raster_layer_uri}"/>'
        )
    svg.append("</svg>")

    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / "sheet-render.svg"
    png_path = out_dir / "sheet-render.png"
    layout_path = out_dir / "sheet-layout.json"
    package_path = out_dir / "render-package.json"
    fill_prompt_path = out_dir / "sheet-fill-prompt.txt"
    reference_prompt_path = out_dir / "sheet-reference-prompt.txt"
    edit_mask_path = out_dir / "sheet-edit-mask.png"
    panel_requests_path = out_dir / "panel-fill-requests.json"
    panel_prompts_dir = out_dir / "panel-fill-prompts"

    svg_markup = "\n".join(svg) + "\n"
    svg_path.write_text(svg_markup, encoding="utf-8", newline="\n")
    layout = {
        "renderer": {"id": RENDERER_ID},
        "profile": resolved_profile["id"],
        "mode": mode,
        "reference_scope": reference_scope if mode == "reference" else None,
        "canvas": {"w": width, "h": height},
        "coordinate_space": "renderer-pixels",
        "font_family": FONT_FAMILY,
        "raster_text": raster_text_manifest,
        "mask_semantics": "white-editable-black-protected" if mode == "scaffold" else None,
        "boxes": layout_boxes,
    }
    layout_path.write_text(
        json.dumps(layout, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    rasterize_board(svg_markup, png_path)

    fill_prompt_sha256 = None
    panel_requests_sha256 = None
    panel_request_count = 0
    reference_prompt_sha256 = None
    edit_mask_sha256 = None
    if mode == "scaffold":
        create_edit_mask(edit_mask_path, width=width, height=height, boxes=layout_boxes)
        edit_mask_sha256 = sha256_file(edit_mask_path)
        if fill_transport == MASKED_SHEET_TRANSPORT:
            prompt = fill_prompt
            fill_prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
            fill_prompt_sha256 = sha256_file(fill_prompt_path)
            panel_requests_path.unlink(missing_ok=True)
            if panel_prompts_dir.exists():
                if panel_prompts_dir.resolve().parent != out_dir.resolve():
                    raise ValueError("refusing to remove a panel prompt directory outside the render output")
                shutil.rmtree(panel_prompts_dir)
        else:
            fill_prompt_path.unlink(missing_ok=True)
            panel_requests_path, panel_requests_sha256, panel_request_count = write_panel_fill_requests(
                out_dir=out_dir,
                profile=resolved_profile,
                sheet=sheet,
                plan_rows=plan_rows,
                layout_boxes=layout_boxes,
                scaffold_path=png_path,
                layout_path=layout_path,
                panel_geometries=panel_geometries,
            )
        reference_prompt_path.unlink(missing_ok=True)
    else:
        prompt = build_reference_prompt(reference_scope)
        reference_prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        reference_prompt_sha256 = sha256_file(reference_prompt_path)
        fill_prompt_path.unlink(missing_ok=True)
        edit_mask_path.unlink(missing_ok=True)
        panel_requests_path.unlink(missing_ok=True)
        if panel_prompts_dir.exists():
            if panel_prompts_dir.resolve().parent != out_dir.resolve():
                raise ValueError("refusing to remove a panel prompt directory outside the render output")
            shutil.rmtree(panel_prompts_dir)

    reference_bundle_path = out_dir / "reference-bundle.json"
    reference_bundle_sha256 = None
    if mode == "reference":
        bundle_rows = build_panel_plan(
            resolved_profile,
            sheet,
            sheet_dir=sheet_dir,
            mode="reference",
            reference_scope="all",
        )
        write_reference_bundle(
            reference_bundle_path,
            rows=bundle_rows,
            board_png=png_path,
            board_scope=reference_scope,
            profile_id=resolved_profile["id"],
            sidecar_path=sidecar_path,
        )
        reference_bundle_sha256 = sha256_file(reference_bundle_path)
    else:
        reference_bundle_path.unlink(missing_ok=True)

    profile_sha256 = sha256_bytes(json_bytes(profile))
    package: dict[str, Any] = {
        "renderer": {"id": RENDERER_ID},
        "mode": mode,
        "reference_scope": reference_scope if mode == "reference" else None,
        "profile": resolved_profile["id"],
        "profile_source": str(profile_path) if profile_path else None,
        "profile_selection": dict(profile_selection)
        if profile_selection is not None
        else None,
        "coverage_gaps": coverage["gaps"],
        "coverage_warnings": coverage["warnings"],
        "coverage_exceptions": coverage_exceptions if mode == "scaffold" else None,
        "coverage_exception_records": exception_records if mode == "scaffold" else None,
        "state_panels": resolved_state_panels,
        "form_lineage": form_lineage,
        "profile_sha256": profile_sha256,
        "sheet_data_source": str(sidecar_path) if sidecar_path else None,
        "sheet_data_sha256": sha256_file(sidecar_path) if sidecar_path else None,
        "inputs": inputs,
        "layout_sha256": sha256_file(layout_path),
        "svg_sha256": sha256_file(svg_path),
        "png_sha256": sha256_file(png_path),
        "edit_mask_sha256": edit_mask_sha256,
        "fill_prompt_sha256": fill_prompt_sha256,
        "fill_transport": (
            {
                "id": fill_transport,
                "pixel_edit_mask_confirmed": (
                    pixel_edit_mask_confirmed if fill_transport == MASKED_SHEET_TRANSPORT else False
                ),
                "full_sheet_model_input": fill_transport == MASKED_SHEET_TRANSPORT,
                "panel_requests_sha256": panel_requests_sha256,
                "panel_request_count": panel_request_count,
                "panel_geometries": (
                    [{"w": width, "h": height} for width, height in panel_geometries]
                    if panel_geometries and fill_transport == PANEL_FILL_TRANSPORT
                    else None
                ),
            }
            if mode == "scaffold"
            else None
        ),
        "reference_prompt_sha256": reference_prompt_sha256,
        "reference_bundle_sha256": reference_bundle_sha256,
    }
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "mode": mode,
        "coverage": coverage,
        "state_panels": resolved_state_panels,
        "form_lineage": form_lineage,
        "png": png_path,
        "svg": svg_path,
        "layout": layout_path,
        "package": package_path,
        "edit_mask": edit_mask_path if mode == "scaffold" else None,
        "fill_prompt": (
            fill_prompt_path
            if mode == "scaffold" and fill_transport == MASKED_SHEET_TRANSPORT
            else None
        ),
        "panel_requests": (
            panel_requests_path
            if mode == "scaffold" and fill_transport == PANEL_FILL_TRANSPORT
            else None
        ),
        "reference_prompt": reference_prompt_path if mode == "reference" else None,
        "reference_bundle": reference_bundle_path if mode == "reference" else None,
        "profile": resolved_profile,
    }
