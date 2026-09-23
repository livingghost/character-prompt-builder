#!/usr/bin/env python3
"""Render a Character Sheet folder as a model-fill scaffold or reference board.

The editable HTML is the human authoring surface. This renderer consumes the
exported sheet-data.json and a kind-specific layout profile, then emits raster
artifacts that can actually be attached to an image model.

Modes:
  scaffold  Create a labeled PNG, white-area edit mask, coordinate manifest,
            and either panel-only requests or an explicitly authorized masked
            full-sheet request.
  reference Create a clean reference board for people from accepted slot images,
            and reference-bundle.json listing every accepted image with its role.
            Performance panels leave the board only with --reference-scope identity.

Outputs in --out (the sheet folder by default):
  sheet-render.svg
  sheet-render.png
  sheet-layout.json
  render-package.json
  sheet-edit-mask.png       (scaffold only; white means editable)
  panel-fill-requests.json  (panel-images scaffold transport)
  panel-fill-prompts/       (panel-images scaffold transport)
  sheet-fill-prompt.txt     (masked-sheet scaffold transport only)
  sheet-reference-prompt.txt (reference only)
  reference-bundle.json     (reference only)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from character_sheet_render.board import (
    RENDERER_ID,
    create_edit_mask,
    draw_guide,
    draw_header,
    draw_model_brief,
    image_data_uri,
    render_palette,
    render_profile_summary,
    render_sheet,
    write_panel_fill_requests,
)
from character_sheet_render.coverage import coverage_exception_records, sheet_coverage
from character_sheet_render.lineage import (
    FORM_ID_RE,
    FORM_REGISTRY_COLUMNS,
    INVARIANT_COLUMNS,
    _safe_linked_path,
    resolve_form_lineage,
)
from character_sheet_render.profiles import (
    panel_generation_size,
    parse_panel_geometries,
    ANTHRO_PROFILE_PATH,
    ASPECT_LIMIT,
    BORDER,
    BOTTOM_MARGIN,
    DEFAULT_FOOTER_HEIGHT,
    DEFAULT_PROFILE_PATH,
    FILL_POLICIES,
    GENERAL_PROFILE_PATH,
    HEADER_HEIGHT,
    KIND_PANEL_ASPECT,
    MIN_PANEL_WIDTH,
    PALETTE_CELL_MIN_HEIGHT,
    PANEL_GAP,
    PROFILE_LIBRARY_DIR,
    PROFILE_SCHEMA_PATH,
    REFERENCE_ROLES,
    REFERENCE_TOP_OF_ROWS,
    RESOLVED_ROW_HEIGHT,
    ROW_GAP,
    SCAFFOLD_TOP_OF_ROWS,
    SECTION_HEADER_HEIGHT,
    SIDE_MARGIN,
    available_profiles,
    desired_panel_width,
    load_profile,
    resolve_profile_reference,
    row_natural_width,
    row_panel_height,
    select_profile_path,
    validate_profile_semantics,
)
from character_sheet_render.prompts import (
    FILL_TRANSPORTS,
    MASKED_SHEET_TRANSPORT,
    PANEL_FILL_TRANSPORT,
    build_fill_prompt,
    build_reference_prompt,
    character_anchor_lines,
    guide_lines_for_mode,
)
from character_sheet_render.resolution import (
    KIND_DRAW_GUIDE,
    KIND_PANEL_CAPTION,
    STATE_PANEL_FALLBACKS,
    STATE_PANEL_LABELS,
    STATE_SLOT_PREFIX,
    apply_sheet_context,
    build_panel_plan,
    effective_fill_state,
    merge_panel_hint,
    requested_fill_policy,
    resolve_slot,
    resolve_state_panels,
    slot_image,
    source_declared,
)
from character_sheet_render.sheetdata import (
    COVERAGE_COLOR_COLUMNS,
    COVERAGE_EVIDENCE_COLUMNS,
    COVERAGE_EXPRESSION_COLUMNS,
    COVERAGE_ITEM_COLUMNS,
    COVERAGE_MARK_COLUMNS,
    COVERAGE_OUTFIT_COLUMNS,
    COVERAGE_PART_COLUMNS,
    COVERAGE_POSE_COLUMNS,
    COVERAGE_VIEW_COLUMNS,
    FIXED_BINDINGS,
    FIXED_VISUAL_TABLES,
    HEX_RE,
    PAIRED_PART_TOKENS,
    PLACEHOLDERS,
    ROOT,
    STATE_PANEL_SOURCES,
    SYMMETRIC_LATERALITY_TERMS,
    UNPAIRED_LATERALITY_TERMS,
    _part_match_score,
    _part_names_overlap,
    _part_source_keys,
    _part_tokens,
    asymmetric_laterality,
    box_source_row_id,
    color_rows,
    compact_join,
    first_matching_part,
    json_bytes,
    load_json_object,
    load_sheet,
    meaningful,
    paired_part_declared,
    row_has_visual_data,
    row_values,
    sha256_bytes,
    sha256_file,
    source_entry,
    table_entries,
    table_values,
)
from character_sheet_render.textmetrics import (
    DISABLED,
    FONT_FAMILY,
    FULLWIDTH_TEXT_UNIT,
    INK,
    LATIN_TEXT_UNIT,
    MUTED,
    PANEL,
    PAPER,
    REFERENCE_GUIDE,
    SCAFFOLD_GUIDE,
    SOFT,
    build_raster_text_layer,
    cjk_font_candidates,
    contains_cjk,
    contains_fullwidth_glyphs,
    estimated_text_units,
    fit_title_size,
    fit_wrapped_text,
    make_svg_text,
    make_wrapped_svg_text,
    raster_font_role,
    resolve_cjk_fonts,
    wrap_lines,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sheet_dir", type=Path, help="Character Sheet folder containing sheet-data.json and slot images"
    )
    parser.add_argument(
        "--mode", choices=("scaffold", "reference"), default="scaffold"
    )
    parser.add_argument(
        "--reference-scope",
        choices=("identity", "all"),
        default="all",
        help="reference mode: all shows every accepted panel on the board; identity narrows it to fixed identity panels (the bundle lists all either way)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="layout profile: a bundled profile id (anthro, humanoid, general) or a "
        "profile JSON path; overrides field.sheet_layout_profile in sheet-data.json "
        "(default: that field, else the bundled domain-neutral general profile)",
    )
    parser.add_argument(
        "--out", type=Path, help="output directory (default: the Character Sheet folder)"
    )
    parser.add_argument(
        "--fill-transport",
        choices=(PANEL_FILL_TRANSPORT, MASKED_SHEET_TRANSPORT),
        default=PANEL_FILL_TRANSPORT,
        help="scaffold mode: panel-images is safe for maskless interfaces; masked-sheet requires a real pixel edit mask",
    )
    parser.add_argument(
        "--panel-geometries",
        type=parse_panel_geometries,
        default=None,
        metavar="WxH,WxH,...",
        help="scaffold mode, panel-images: the target's fixed output sizes; each panel request asks for the one nearest its aspect",
    )
    parser.add_argument(
        "--confirm-pixel-edit-mask",
        action="store_true",
        help="confirm that the active interface applies the supplied pixel edit mask; required by --fill-transport masked-sheet",
    )
    args = parser.parse_args(argv)

    sheet_dir = args.sheet_dir.resolve()
    if not sheet_dir.is_dir():
        raise ValueError(f"sheet_dir must be an existing directory: {sheet_dir}")
    out_dir = (args.out or sheet_dir).resolve()
    sheet, sidecar_path = load_sheet(sheet_dir)
    profile_path, profile_selection = select_profile_path(
        sheet, args.profile if args.profile else None, sheet_dir=sheet_dir
    )
    if not profile_path.is_file():
        raise ValueError(f"render profile does not exist: {profile_path}")
    profile = load_profile(profile_path)
    result = render_sheet(
        profile,
        sheet,
        sheet_dir=sheet_dir,
        mode=args.mode,
        out_dir=out_dir,
        reference_scope=args.reference_scope,
        profile_path=profile_path,
        sidecar_path=sidecar_path,
        profile_selection=profile_selection,
        fill_transport=args.fill_transport,
        pixel_edit_mask_confirmed=args.confirm_pixel_edit_mask,
        panel_geometries=args.panel_geometries,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "mode": result["mode"],
                "profile": result["profile"]["id"],
                "profile_selection": profile_selection,
                "coverage_gaps": result["coverage"]["gaps"],
                "coverage_warnings": result["coverage"]["warnings"],
                "state_panels": result["state_panels"],
                "png": str(result["png"]),
                "layout": str(result["layout"]),
                "edit_mask": str(result["edit_mask"]) if result["edit_mask"] else None,
                "fill_prompt": str(result["fill_prompt"]) if result["fill_prompt"] else None,
                "panel_requests": str(result["panel_requests"])
                if result["panel_requests"]
                else None,
                "reference_prompt": str(result["reference_prompt"])
                if result["reference_prompt"]
                else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
