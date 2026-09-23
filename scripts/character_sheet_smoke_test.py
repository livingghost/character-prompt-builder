#!/usr/bin/env python3
"""Exercise Character Sheet readiness, safe sidecars, rendering, and harvesting."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping
from unittest import mock

from PIL import Image, ImageDraw, ImageFont

from character_sheet import bind_sidecar, initialize_sidecar, sheet_status, validate_sidecar
from character_sheet_render import textmetrics
from character_sheet_render.textmetrics import font_has_glyph, segment_text_by_font
from compose_sheet_panel_fills import compose_panel_fills
from harvest_sheet_render import harvest_sheet
from render_character_sheet import (
    ANTHRO_PROFILE_PATH,
    DEFAULT_PROFILE_PATH,
    GENERAL_PROFILE_PATH,
    KIND_DRAW_GUIDE,
    apply_sheet_context,
    build_panel_plan,
    build_fill_prompt,
    fit_title_size,
    fit_wrapped_text,
    resolve_state_panels,
    load_sheet,
    load_profile,
    PANEL_GAP,
    RESOLVED_ROW_HEIGHT,
    panel_generation_size,
    SECTION_HEADER_HEIGHT,
    desired_panel_width,
    SIDE_MARGIN,
    render_sheet,
    resolve_cjk_fonts,
    select_profile_path,
    sheet_coverage,
    slot_image,
    validate_profile_semantics,
    PROFILE_SCHEMA_PATH,
)
from state_protocol import validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CHECKS = 152


def expect_error(fn: Callable[[], Any], text: str) -> bool:
    try:
        fn()
    except (ValueError, OSError, RuntimeError, TypeError) as exc:
        return text in str(exc)
    return False


def first_panel_prompt(render_result: Mapping[str, Any]) -> str:
    return panel_prompts(render_result)[0][1]


def panel_prompts(render_result: Mapping[str, Any]) -> list[tuple[dict[str, Any], str]]:
    manifest_path = Path(render_result["panel_requests"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        (
            request,
            (manifest_path.parent / request["prompt"]["path"]).read_text(encoding="utf-8"),
        )
        for request in manifest["requests"]
    ]


def cjk_font_lookup_order() -> tuple[bool, dict[str, Any]]:
    """Known font paths come first, fontconfig answers when none loads, and text without a font fails."""

    regular = textmetrics.usable_cjk_font_files("regular")
    bold = textmetrics.usable_cjk_font_files("bold")
    if not regular or not bold:
        return False, {"regular": [str(path) for path in regular], "bold": [str(path) for path in bold]}
    pair = list(dict.fromkeys([*regular, *bold]))[:2]
    early, late = min(pair), max(pair)
    absent = [Path(tempfile.gettempdir()) / "cpb-absent-known-font.ttc"]
    listings = {"ja": f"{absent[0]}\n{late}\n{late}\n", "ko": f"{early}\n{late}\n"}
    queries: list[str] = []

    def fake_fc_list(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        queries.append(command[-1])
        language = command[-1].split(":")[1].removeprefix("lang=")
        return subprocess.CompletedProcess(command, 0, stdout=listings.get(language, ""), stderr="")

    which = mock.Mock(return_value="fc-list")
    try:
        textmetrics.fontconfig_cjk_font_files.cache_clear()
        with mock.patch.object(textmetrics.shutil, "which", which), \
                mock.patch.object(textmetrics.subprocess, "run", side_effect=fake_fc_list):
            known = textmetrics.usable_cjk_font_files("regular")
            known_asked_fontconfig = which.called
            with mock.patch.object(textmetrics, "cjk_font_candidates", return_value=absent):
                listed = textmetrics.usable_cjk_font_files("regular")
                runs = segment_text_by_font("regular", "見本")
        textmetrics.fontconfig_cjk_font_files.cache_clear()
        with mock.patch.object(textmetrics.shutil, "which", return_value=None), \
                mock.patch.object(textmetrics, "cjk_font_candidates", return_value=absent):
            fails_closed = expect_error(lambda: segment_text_by_font("regular", "見本"), "no usable CJK font file")
    finally:
        textmetrics.fontconfig_cjk_font_files.cache_clear()
    detail = {
        "known": [str(path) for path in known],
        "listed": [str(path) for path in listed],
        "queries": queries,
        "runs": [[str(path), text] for path, text in runs],
        "fails_closed": fails_closed,
    }
    passed = (
        known == regular
        and not known_asked_fontconfig
        and listed == list(dict.fromkeys([late, early]))
        and queries == [f":lang={language}:weight=regular" for language in ("ja", "ko", "zh-cn", "zh-tw")]
        and runs == [(late, "見本")]
        and fails_closed
    )
    return passed, detail


def generation_package() -> dict[str, Any]:
    return {
        "status": "ready",
        "model": "smoke-generation-model",
        "generation_payload": {},
        "generation_contract": {},
        "generation_input_sha256": "a" * 64,
    }


def base_sidecar() -> dict[str, Any]:
    return {
        "sheet_status": "draft",
        "fields": {},
        "tables": {
            "items": [
                {
                    "row_id": "items.01",
                    "values": {"item": "-", "role_rule": "-"},
                }
            ]
        },
        "slots": {
            "canon.primary": {"image_path": "", "generation_package": ""},
            "identity.icon": {"image_path": "", "generation_package": ""},
        },
    }


def render_sidecar() -> dict[str, Any]:
    slot_ids = (
        "canon.primary",
        "canon.back",
        "canon.side",
        "canon.right",
        "eye.left.detail",
        "eye.right.detail",
        "hand.detail",
        "foot.detail",
        "slot.mark.01",
        "slot.mark.02",
        "identity.icon",
        "pose.state.01",
        "pose.state.02",
        "pose.state.03",
        "pose.state.04",
        "outfit.turn.front",
        "outfit.turn.side",
        "outfit.turn.back",
        "outfit.turn.right",
        "outfit.details",
        "items.primary",
        "expressions.ex.01",
        "expressions.ex.02",
        "expressions.ex.03",
        "expressions.ex.04",
        "expressions.ex.05",
        "expressions.ex.06",
    )
    return {
        "sheet_status": "identity-ready",
        "fields": {
            "identity.name": "Aster",
            "identity.species_domain": "anthropomorphic wolf",
            "field.pronouns": "they / them",
            "field.kind_baseline_sheet_or_self": "self-authored wolf kind",
            "field.form_of_spine_sheet_or_self": "single baseline form",
            "field.form_id_display_name": "baseline / Aster",
            "field.height_against_a_stated_measure": "172 cm",
            "field.build_register": "lean runner build",
            "field.notes": "left and right evidence remains literal in every panel",
            "field.personality_and_motivational_structure": "quietly alert and observant; protects routes and travelers",
            "field.counter_element_or_weakness": "overchecks safe routes before resting",
            "field.role_world_and_standing": "trusted winter pathfinder",
            "field.design_themes_and_organizing_principles": "moonlit wayfinding, repaired field instruments, restrained practical shapes",
            "field.motifs_derived_from_the_theme_and_where_they_appear": "crescent marks stay on the declared cheek only",
            "field.signature_poses_and_mannerisms_described": "weight back, one ear tracking",
            "field.relationships_and_stance_toward_others": "gives companions room while monitoring their route",
            "field.character_specific_expression_described": "a restrained one-corner smile",
            "field.base_form_visual_description": "uncovered wolf form with the same fixed anatomy in all four directions",
            "field.dressed_equipped_form_visual_description": "the same form wearing a short field coat and narrow scarf in all four directions",
            "field.free_01": "broken charcoal stripes follow the outer forearms",
        },
        "tables": {
            "axes": [
                {
                    "row_id": "axes.01",
                    "values": {
                        "axis": "habitual silhouette and deployment",
                        "choices_expression": "quiet vigilance expressed by compact carried gear and economical movement",
                        "binding": "character-fixed",
                    },
                }
            ],
            "bodylang": [
                {
                    "row_id": "bodylang.01",
                    "values": {
                        "state": "baseline",
                        "posture": "upright but economical",
                        "gesture": "hands near useful objects",
                        "kind_channels": "ears independently attentive",
                        "distance_orientation": "three-quarter toward others",
                    },
                },
                {
                    "row_id": "bodylang.02",
                    "values": {
                        "state": "alert",
                        "posture": "weight shifts to rear foot",
                        "gesture": "left hand near compass",
                        "kind_channels": "ears forward; tail still",
                        "distance_orientation": "squares toward source",
                    },
                },
                {
                    "row_id": "bodylang.03",
                    "values": {
                        "state": "embarrassed",
                        "posture": "shoulders narrow",
                        "gesture": "thumb rubs compass rim",
                        "kind_channels": "one ear folds outward",
                        "distance_orientation": "angles away",
                    },
                },
                {
                    "row_id": "bodylang.04",
                    "values": {
                        "state": "relaxed",
                        "posture": "weight balanced and shoulders loose",
                        "gesture": "hands resting open",
                        "kind_channels": "ears neutral; tail resting low",
                        "distance_orientation": "faces the viewer",
                    },
                },
            ],
            "marks": [
                {
                    "row_id": "marks.01",
                    "values": {
                        "mark_id": "split crescent",
                        "landmark_anchor": "under right eye",
                        "shape_path": "two pale arcs",
                        "laterality": "right",
                        "counterpart_rule": "the left under-eye has no pale arcs",
                        "continuity_rule": "never crosses lower eyelid",
                        "visibility_rule": "must appear whenever the right under-eye is exposed",
                        "binding": "individual-fixed",
                    },
                },
                {
                    "row_id": "marks.02",
                    "values": {
                        "mark_id": "map notch",
                        "landmark_anchor": "outer left ear",
                        "shape_path": "small triangular notch",
                        "laterality": "left",
                        "counterpart_rule": "the right ear rim is intact with no notch",
                        "continuity_rule": "visible front and rear",
                        "visibility_rule": "must appear whenever the left ear rim is exposed",
                        "binding": "individual-fixed",
                    },
                },
            ],
            "colors": [
                {
                    "row_id": "colors.01",
                    "values": {
                        "zone": "base fur",
                        "base": "#66717C",
                        "shadow": "#414952",
                        "highlight": "#A9B2BA",
                        "visibility_rule": "must appear wherever the base fur is exposed",
                        "binding": "individual-fixed",
                    },
                },
                {
                    "row_id": "colors.02",
                    "values": {
                        "zone": "amber eyes",
                        "base": "#D18A2C",
                        "shadow": "#8A541C",
                        "highlight": "#FFD47A",
                        "visibility_rule": "must appear whenever either iris is exposed",
                        "binding": "individual-fixed",
                    },
                },
            ],
            "parts": [
                {
                    "row_id": "parts.01",
                    "values": {
                        "part": "Hands and claws",
                        "attribute": "five fingers with short graphite claws",
                        "laterality": "bilateral symmetric",
                        "counterpart_rule": "left and right hands have the same digit and claw structure",
                        "continuity_rule": "preserve the same digit and claw structure",
                        "visibility_rule": "must appear in every panel where either hand is exposed",
                        "binding": "individual-fixed",
                    },
                },
                {
                    "row_id": "parts.02",
                    "values": {
                        "part": "Left eye",
                        "attribute": "warm amber iris and one crisp catchlight",
                        "laterality": "left",
                        "counterpart_rule": "right eye has the same iris and catchlight",
                        "continuity_rule": "preserve the same iris and catchlight",
                        "visibility_rule": "must appear whenever the left eye is exposed",
                        "binding": "individual-fixed",
                    },
                },
                {
                    "row_id": "parts.03",
                    "values": {
                        "part": "Right eye",
                        "attribute": "warm amber iris and one crisp catchlight",
                        "laterality": "right",
                        "counterpart_rule": "left eye has the same iris and catchlight",
                        "continuity_rule": "preserve the same iris and catchlight",
                        "visibility_rule": "must appear whenever the right eye is exposed",
                        "binding": "individual-fixed",
                    },
                },
                {
                    "row_id": "parts.04",
                    "values": {
                        "part": "Feet and toes",
                        "attribute": "five toes with short graphite nails",
                        "laterality": "bilateral symmetric",
                        "counterpart_rule": "left and right feet have the same toe and nail structure",
                        "continuity_rule": "preserve the same toe and nail structure",
                        "visibility_rule": "must appear in every panel where either foot is exposed",
                        "binding": "individual-fixed",
                    },
                },
            ],
            "expressions": [
                {
                    "row_id": f"expressions.{index:02d}",
                    "values": {
                        "state": state,
                        "overall_read": overall_read,
                        "binding": "variable",
                    },
                }
                for index, (state, overall_read) in enumerate(
                    (
                        ("calm", "quiet baseline"),
                        ("alert", "attention toward a sound"),
                        ("amused", "restrained one-corner smile"),
                        ("joy", "open relaxed smile"),
                        ("angry", "controlled warning"),
                        ("worried", "quiet uncertainty"),
                    ),
                    start=1,
                )
            ],
            "items": [
                {
                    "row_id": "items.01",
                    "values": {
                        "item": "brass compass",
                        "visual_identity": "round brass case with one repaired hinge",
                        "role_rule": "left belt with repaired hinge",
                        "continuity_rule": "preserve the same case and hinge across all applicable views",
                        "visibility_rule": "must appear on the left belt in applicable dressed panels",
                        "binding": "individual-fixed",
                    },
                }
            ],
        },
        "slots": {slot_id: {"image_path": "", "generation_package": ""} for slot_id in slot_ids},
    }


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    html = (ROOT / "templates/character-sheet.template.html").read_text(encoding="utf-8")
    check(
        "template does not execute a JavaScript data sidecar",
        not re.search(r'<script\s+[^>]*src=["\']sheet-data\.js["\']', html, re.I)
        and "window.SHEET" not in html,
    )
    check("template has no external script source", not re.search(r"<script\s+[^>]*src=", html, re.I))
    check("template imports JSON only", 'accept="application/json"' in html)
    check("template exports sheet-data.json", "sheet-data.json" in html)
    identity_selectors = re.findall(r'<[^>]+\sdata-identity-required(?:="")?[^>]*>', html, re.I)
    check("template has exactly two identity selectors", len(identity_selectors) == 2)
    check("template has no design-complete state", "DESIGN COMPLETE" not in html)
    check(
        "items table has matching data columns plus a non-data action column",
        bool(
            re.search(
                r"<tr><th[^>]*>Item / assembly</th><th>Visual identity</th><th[^>]*>Scale, placement, and attachment</th><th[^>]*>Role / use rule</th><th[^>]*>Continuity rule</th><th[^>]*>Applicability / visibility rule</th><th[^>]*>Binding</th><th[^>]*>Actions</th></tr>",
                html,
                re.I | re.S,
            )
        ),
    )
    check(
        "added rows use a hidden row template without injecting character data defaults",
        'template data-row-template="bodylang"' in html
        and "template.content.firstElementChild.cloneNode(true)" in html
        and "data-default=" not in html
        and 'data-default="individual-fixed"' not in html,
    )
    field_ids = re.findall(r'data-field-id="([^"]+)"', html)
    slot_ids = re.findall(r'<div class="slot"[^>]*\sdata-slot-id="([^"]+)"', html, re.I)
    check("field IDs are stable and unique", len(field_ids) == len(set(field_ids)) and len(field_ids) > 10)
    check(
        "panel artifact slots are generated from declared rows or imports rather than fixed HTML cards",
        not slot_ids
        and "syncDeclaredPanelSlotEditors" in html
        and "view.base." in html
        and "view.outfit." in html
        and "'row.'+spec.tableId+'.'+row.dataset.rowId" in html,
    )

    check(
        "template exposes raster-readable model-fill brief fields",
        'data-field-id="field.model_fill_visual_design_brief"' in html
        and 'data-field-id="field.reference_sheet_visual_finish"' in html,
    )
    check(
        "template round-trips an explicit per-slot fill policy",
        "Model-fill policy" in html
        and "fill_policy:state.fillPolicy" in html
        and "setFillPolicy(slot" in html
        and "raw.fill_policy" in html,
    )
    check(
        "template makes the HTML-to-raster boundary visible",
        "REUSABLE JSON EDITOR - NOT A PER-CHARACTER HTML DOCUMENT" in html
        and "does not screenshot or rasterize this HTML page" in html
        and "selected layout profile" in html,
    )

    with tempfile.TemporaryDirectory() as init_temp:
        initialized_path = initialize_sidecar(Path(init_temp) / "new-sheet", profile="general")
        initialized = json.loads(initialized_path.read_text(encoding="utf-8"))
        check(
            "sidecar initialization creates and validates the current blank authoring contract",
            initialized_path.name == "sheet-data.json"
            and initialized["sheet_status"] == "draft"
            and initialized["fields"]["field.sheet_layout_profile"] == "general"
            and set(initialized["tables"])
            == {
                "axes",
                "views",
                "evidence",
                "formreg",
                "invariants",
                "bodylang",
                "partstates",
                "motion",
                "actions",
                "gestures",
                "marks",
                "overrides",
                "colors",
                "parts",
                "items",
                "expressions",
                "outfits",
            }
            and validate_sidecar(initialized)["sheet_status"] == "draft",
        )

    draft = base_sidecar()
    draft["fields"] = {"identity.name": "-", "identity.species_domain": "wolf", "field.notes": "-"}
    check("dash does not satisfy the minimum name selector", sheet_status(draft) == "draft")
    validated_draft = validate_sidecar(draft)
    check(
        "optional dash values remain valid in a draft",
        validated_draft["sheet_status"] == "draft"
        and validated_draft["fields"]["identity.name"] == "-"
        and validated_draft["fields"]["field.notes"] == "-",
    )

    identity = base_sidecar()
    identity["fields"] = {
        "identity.name": "Aster",
        "identity.species_domain": "wolf",
        "field.notes": "-",
        "field.build_register": "-",
    }
    identity["sheet_status"] = "identity-ready"
    check("name and species alone produce identity readiness", sheet_status(identity) == "identity-ready")
    validated_identity = validate_sidecar(identity)
    anatomy_row = next(
        (
            f"tables.{table_id}.{row.get('row_id')}"
            for table_id in ("parts", "marks", "colors", "outfits", "bodylang")
            for row in validated_identity.get("tables", {}).get(table_id, [])
            for value in (row.get("values") or {}).values()
            if str(value or "").strip().lower() not in
            {"", "-", "unknown", "tbd", "n/a", "not applicable", "unspecified"}
        ),
        None,
    )
    check(
        "identity readiness does not require anatomy palette outfit or pose",
        validated_identity["sheet_status"] == "identity-ready" and anatomy_row is None,
    )

    mismatch = copy.deepcopy(identity)
    mismatch["sheet_status"] = "reference-ready"
    check(
        "sidecar cannot overstate readiness",
        expect_error(lambda: validate_sidecar(mismatch), "sheet_status must be"),
    )

    duplicate = copy.deepcopy(identity)
    duplicate["tables"]["items"].append(copy.deepcopy(duplicate["tables"]["items"][0]))
    check(
        "duplicate stable row IDs are rejected",
        expect_error(lambda: validate_sidecar(duplicate), "duplicate row_id"),
    )

    wrong_prefix = copy.deepcopy(identity)
    wrong_prefix["tables"] = {"marks": [{"row_id": "colors.01", "values": {}}]}
    check(
        "row IDs remain scoped to their owning table",
        expect_error(lambda: validate_sidecar(wrong_prefix), "must start with"),
    )

    with tempfile.TemporaryDirectory(prefix="cpb-character-sheet-smoke-") as raw:
        root = Path(raw).resolve()
        image_path = root / "front.png"
        Image.new("RGB", (4, 6), (30, 60, 90)).save(image_path, format="PNG")
        package_path = root / "front.package.json"
        package_path.write_text(
            json.dumps(generation_package(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        reference = copy.deepcopy(identity)
        reference["sheet_status"] = "reference-ready"
        reference["slots"]["canon.primary"] = {
            "image_path": "front.png",
            "generation_package": "front.package.json",
        }
        check(
            "primary image and package paths produce reference readiness",
            sheet_status(reference) == "reference-ready",
        )
        bound = bind_sidecar(reference, sheet_root=root)
        check(
            "binding commits both image and package hashes",
            len(bound["slots"]["canon.primary"]["image_sha256"]) == 64
            and len(bound["slots"]["canon.primary"]["generation_package_sha256"]) == 64,
        )
        validated_bound = validate_sidecar(bound, sheet_root=root, verify_files=True)
        check(
            "bound reference sidecar verifies",
            validated_bound["slots"]["canon.primary"]["image_sha256"]
            == bound["slots"]["canon.primary"]["image_sha256"]
            and validated_bound["slots"]["canon.primary"]["generation_package_sha256"]
            == bound["slots"]["canon.primary"]["generation_package_sha256"],
        )

        original_image = image_path.read_bytes()
        Image.new("RGB", (4, 6), (90, 60, 30)).save(image_path, format="PNG")
        check(
            "image mutation breaks the committed binding",
            expect_error(
                lambda: validate_sidecar(bound, sheet_root=root, verify_files=True),
                "image_sha256 mismatch",
            ),
        )
        image_path.write_bytes(original_image)

        package_path.write_text(json.dumps({"status": "ready"}) + "\n", encoding="utf-8", newline="\n")
        unbound = copy.deepcopy(reference)
        check(
            "uncommitted ready-looking JSON is not accepted as a generation package",
            expect_error(lambda: bind_sidecar(unbound, sheet_root=root), "structurally committed"),
        )
        package_path.write_text(
            json.dumps(generation_package(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        traversal = copy.deepcopy(reference)
        traversal["slots"]["canon.primary"]["image_path"] = "../outside.png"
        check(
            "carrier path traversal is rejected",
            expect_error(lambda: bind_sidecar(traversal, sheet_root=root), "safe path relative"),
        )

        incomplete_optional = copy.deepcopy(identity)
        incomplete_optional["slots"]["identity.icon"] = {
            "image_path": "front.png",
            "generation_package": "",
        }
        check(
            "a populated optional slot must still identify its matching package",
            expect_error(lambda: bind_sidecar(incomplete_optional, sheet_root=root), "declare both"),
        )

        render_root = root / "render-sheet"
        render_root.mkdir()
        sidecar_path = render_root / "sheet-data.json"
        sidecar_value = render_sidecar()
        validate_sidecar(sidecar_value)
        sidecar_path.write_text(
            json.dumps(sidecar_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        loaded_sheet, loaded_sidecar_path = load_sheet(render_root)
        check(
            "renderer loads the current sidecar through structural validation",
            loaded_sheet == sidecar_value and loaded_sidecar_path == sidecar_path,
        )
        profile = load_profile(DEFAULT_PROFILE_PATH)
        profile_schema_errors = validate_against_schema(
            profile,
            json.loads(PROFILE_SCHEMA_PATH.read_text(encoding="utf-8")),
        )
        try:
            validate_profile_semantics(copy.deepcopy(profile))
            profile_semantics_ok = True
        except (ValueError, KeyError):
            profile_semantics_ok = False
        check(
            "default render profile is schema-valid and passes load-time semantics",
            not profile_schema_errors
            and profile_semantics_ok
            and profile["canvas"][0] > 0
            and profile["canvas"][1] > 0
            and bool(profile["rows"]),
        )
        profile_boxes = [box for row in profile["rows"] for box in row["boxes"]]
        check(
            "render profile gives every panel a unique raster-readable code and authority role",
            len({box["panel_code"] for box in profile_boxes}) == len(profile_boxes)
            and all(box.get("reference_role") in {"identity", "performance", "support"} for box in profile_boxes),
        )
        strip_mix = copy.deepcopy(profile)
        palette_box = next(
            box for box in profile_boxes if box.get("kind") == "palette"
        )
        strip_mix["rows"][0]["boxes"].append(copy.deepcopy(palette_box))
        check(
            "palette strips refuse row sharing with drawing panels at load time",
            expect_error(
                lambda: validate_profile_semantics(copy.deepcopy(strip_mix)),
                "palette/profile strips with",
            ),
        )
        low_height = copy.deepcopy(profile)
        low_height["rows"][0]["height"] = 130
        check(
            "section-label height rules fail at load time, not mid-render",
            expect_error(
                lambda: validate_profile_semantics(copy.deepcopy(low_height)),
                "120px below its section label",
            ),
        )
        anchored_pattern_schema = {
            "type": "object",
            "properties": {
                "panel_code": {"type": "string", "pattern": "^[A-Z][0-9]+$"},
            },
        }
        check(
            "anchored schema patterns reject trailing newlines",
            validate_against_schema({"panel_code": "A1\n"}, anchored_pattern_schema)
            and "pattern" in validate_against_schema({"panel_code": "A1\n"}, anchored_pattern_schema)[0]
            and not validate_against_schema({"panel_code": "A1"}, anchored_pattern_schema),
        )
        declared_views = copy.deepcopy(sidecar_value)
        declared_views["tables"]["views"] = [
            {
                "row_id": f"views.{index:02d}",
                "values": {
                    "view_id": view_id,
                    "label": label,
                    "specification": specification,
                    "must_prove": must_prove,
                },
            }
            for index, (view_id, label, specification, must_prove) in enumerate(
                (
                    ("front", "front", "orthographic primary surface", "overall proportions"),
                    ("left", "left surface", "orthographic left surface", "left-only marks"),
                    ("rear", "rear", "orthographic opposite surface", "rear topology"),
                    ("right", "right surface", "orthographic right surface", "right counterpart evidence"),
                    ("dorsal", "dorsal", "orthographic top surface", "topology hidden from lateral views"),
                ),
                start=1,
            )
        ]
        declared_views["tables"]["outfits"] = [
            {
                "row_id": "outfits.01",
                "values": {
                    "outfit": "field gear",
                    "description": "short coat and scarf",
                },
            }
        ]
        declared_view_render = render_sheet(
            profile,
            declared_views,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=render_root / "declared-view-grid",
            profile_path=DEFAULT_PROFILE_PATH,
        )
        declared_view_layout = json.loads(
            declared_view_render["layout"].read_text(encoding="utf-8")
        )
        base_view_boxes = [
            box for box in declared_view_layout["boxes"] if box["kind"] == "canonical_view"
        ]
        outfit_view_boxes = [
            box
            for box in declared_view_layout["boxes"]
            if box["kind"] == "outfit_turnaround"
        ]
        check(
            "declared view rows dynamically create matching base and outfit image frames",
            len(base_view_boxes) == 5
            and len(outfit_view_boxes) == 5
            and {box["slot_id"] for box in base_view_boxes}
            == {f"view.base.views.{index:02d}" for index in range(1, 6)}
            and {box["slot_id"] for box in outfit_view_boxes}
            == {
                f"view.outfit.outfits.01.views.{index:02d}"
                for index in range(1, 6)
            }
            and not declared_view_render["coverage"]["gaps"],
        )
        check(
            "declared view layout boxes record their source view row",
            {box["source_view_row_id"] for box in base_view_boxes}
            == {f"views.{index:02d}" for index in range(1, 6)}
            and {box["source_view_row_id"] for box in outfit_view_boxes}
            == {f"views.{index:02d}" for index in range(1, 6)},
        )
        single_view = copy.deepcopy(sidecar_value)
        single_view["tables"]["views"] = [declared_views["tables"]["views"][0]]
        check(
            "a single declared view row names the sheet views table, not the profile",
            expect_error(
                lambda: render_sheet(
                    profile,
                    single_view,
                    sheet_dir=render_root,
                    mode="scaffold",
                    out_dir=render_root / "single-view-grid",
                    profile_path=DEFAULT_PROFILE_PATH,
                ),
                "views table must declare at least two view rows",
            ),
        )
        scaffold_dir = render_root / "scaffold"
        scaffold = render_sheet(
            profile,
            sidecar_value,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=scaffold_dir,
            profile_path=DEFAULT_PROFILE_PATH,
            sidecar_path=sidecar_path,
        )
        target_geometries = [(2048, 2048), (1776, 2368), (2368, 1776), (1456, 2912), (2912, 1456)]
        check(
            "a fixed geometry set answers each panel with the size nearest its aspect",
            panel_generation_size({}, {}, (700, 900), target_geometries) == (1776, 2368)
            and panel_generation_size({}, {}, (900, 700), target_geometries) == (2368, 1776)
            and panel_generation_size({}, {}, (500, 500), target_geometries) == (2048, 2048)
            and panel_generation_size({}, {}, (300, 170), target_geometries) == (2912, 1456)
            and panel_generation_size({}, {}, (700, 900)) == (1593, 2048),
        )
        geometry_scaffold = render_sheet(
            profile,
            sidecar_value,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=render_root / "scaffold-geometries",
            profile_path=DEFAULT_PROFILE_PATH,
            sidecar_path=sidecar_path,
            panel_geometries=target_geometries,
        )
        geometry_requests = json.loads(
            geometry_scaffold["panel_requests"].read_text(encoding="utf-8")
        )
        geometry_package = json.loads(geometry_scaffold["package"].read_text(encoding="utf-8"))
        check(
            "every request under a geometry set asks for one of its sizes and says so in its prompt",
            all(
                (request["target"]["generation_w"], request["target"]["generation_h"]) in target_geometries
                and f"Produce a {request['target']['generation_w']} by {request['target']['generation_h']} pixel image"
                in (render_root / "scaffold-geometries" / request["prompt"]["path"]).read_text(encoding="utf-8")
                for request in geometry_requests["requests"]
            )
            and geometry_requests["transport"]["panel_geometries"]
            == [{"w": width, "h": height} for width, height in target_geometries]
            and geometry_package["fill_transport"]["panel_geometries"]
            == geometry_requests["transport"]["panel_geometries"],
        )
        with Image.open(scaffold["png"]) as scaffold_image:
            raster_size = scaffold_image.size
        layout = json.loads(scaffold["layout"].read_text(encoding="utf-8"))
        canvas = layout["canvas"]
        check(
            "scaffold raster matches the declared profile dimensions",
            raster_size == (canvas["w"], canvas["h"]),
        )
        drawing_rows: dict[int, list[dict[str, Any]]] = {}
        for box in layout["boxes"]:
            if box["kind"] in {"palette", "profile"}:
                continue
            drawing_rows.setdefault(box["y"], []).append(box)
        # A row of one or two panels stops at the fill cap rather than becoming
        # a page; every fuller row reaches the margins.
        row_spans = [
            (max(box["x"] + box["w"] for box in boxes) - min(box["x"] for box in boxes))
            / (canvas["w"] - 2 * SIDE_MARGIN)
            for boxes in drawing_rows.values()
            if len(boxes) >= 3
        ]
        check(
            "every drawing row of three or more panels spans the canvas width",
            bool(row_spans) and all(span >= 0.9 for span in row_spans),
            f"row spans: {[round(span, 3) for span in row_spans]}",
        )
        check(
            "every rendered panel fits inside the canvas",
            all(
                box["x"] >= 0
                and box["y"] >= 0
                and box["x"] + box["w"] <= canvas["w"]
                and box["y"] + box["h"] <= canvas["h"]
                for box in layout["boxes"]
            ),
        )
        check(
            "every harvest crop excludes printed headers and footers",
            all(
                box["content_y"] >= box["y"] + box["header_height"]
                and box["content_y"] + box["content_h"] <= box["y"] + box["h"] - box["footer_height"]
                for box in layout["boxes"]
            ),
        )
        pose_alert = next(box for box in layout["boxes"] if box["slot_id"] == "pose.state.02")
        check(
            "renderer reads canonical values rows for body-language labels and hints",
            pose_alert["label"] == "POSE: ALERT" and "rear foot" in pose_alert["hint"],
        )
        svg = scaffold["svg"].read_text(encoding="utf-8")
        check(
            "renderer reads canonical values rows for palette swatches",
            "#66717C" in svg and "base fur" in svg,
        )
        eye_box = next(
            box
            for box in layout["boxes"]
            if box["slot_id"] == "eye.left.detail"
        )
        mark_box = next(
            box for box in layout["boxes"] if box["slot_id"] == "slot.mark.01"
        )
        check(
            "part detail binds to its explicit source part rather than first-row order",
            eye_box["label"] == "LEFT EYE"
            and "warm amber iris" in eye_box["hint"]
            and "graphite claws" not in eye_box["hint"],
        )
        right_eye_box = next(
            box for box in layout["boxes"] if box["slot_id"] == "eye.right.detail"
        )
        check(
            "each named part detail binds its own matching row without stealing another's",
            eye_box["source_row_id"] == "parts.02"
            and right_eye_box["source_row_id"] == "parts.03",
        )
        unpaired_parts_sheet = {
            "fields": {},
            "tables": {
                "parts": [
                    {
                        "row_id": "parts.01",
                        "values": {
                            "part": "Right hand",
                            "attribute": "one right hand with the shared five-finger claw build",
                            "laterality": "single",
                            "counterpart_rule": "",
                            "continuity_rule": "same digit and claw structure",
                            "visibility_rule": "appears whenever the right hand is exposed",
                            "binding": "individual-fixed",
                        },
                    }
                ]
            },
            "slots": {},
        }
        unpaired_resolved, _ = resolve_state_panels(profile, copy.deepcopy(unpaired_parts_sheet))
        unpaired_coverage = sheet_coverage(unpaired_resolved, unpaired_parts_sheet)
        sided_parts_sheet = copy.deepcopy(unpaired_parts_sheet)
        sided_parts_sheet["tables"]["parts"][0]["values"]["laterality"] = "right"
        sided_resolved, _ = resolve_state_panels(profile, sided_parts_sheet)
        sided_coverage = sheet_coverage(sided_resolved, sided_parts_sheet)
        check(
            "unpaired laterality values never demand a counterpart rule",
            not unpaired_coverage["structural_errors"],
        )
        check(
            "side-taking laterality still demands a counterpart rule",
            any("counterpart_rule" in error for error in sided_coverage["structural_errors"]),
        )
        flag_sheet = copy.deepcopy(unpaired_parts_sheet)
        flag_sheet["tables"]["parts"][0]["values"]["laterality"] = "right"
        flag_sheet["tables"]["parts"][0]["values"]["counterpart_rule"] = (
            "no left-side counterpart exists"
        )
        bare_profile = copy.deepcopy(profile)
        bare_profile["rows"] = [
            {**row, "boxes": [box for box in row["boxes"] if box.get("kind") != "part_detail"]}
            for row in bare_profile["rows"]
        ]
        comparison_box = {
            "slot_id": "counterpart.side",
            "kind": "icon",
            "output_name": "counterpart-side.png",
            "label": "OPPOSITE SIDE CHECK",
            "hint": "Show the declared hand beside its absent left-side counterpart for comparison.",
            "reference_role": "identity",
            "source_part": "Right hand",
        }
        unflagged_profile = copy.deepcopy(bare_profile)
        unflagged_profile["rows"][0]["boxes"].append(copy.deepcopy(comparison_box))
        unflagged_resolved, _ = resolve_state_panels(unflagged_profile, copy.deepcopy(flag_sheet))
        flagged_profile = copy.deepcopy(bare_profile)
        flagged_box = copy.deepcopy(comparison_box)
        flagged_box["counterpart_comparison"] = True
        flagged_profile["rows"][0]["boxes"].append(flagged_box)
        flagged_resolved, _ = resolve_state_panels(flagged_profile, copy.deepcopy(flag_sheet))
        flagged_coverage = sheet_coverage(flagged_resolved, flag_sheet)
        check(
            "a flagged non-part_detail panel can carry the asymmetric comparison",
            not flagged_coverage["structural_errors"]
            and any(
                box.get("slot_id") == "counterpart.side"
                and box.get("source_row_id") == "parts.01"
                for row in flagged_resolved["rows"]
                for box in row["boxes"]
            )
            and not any(
                str(box.get("slot_id", "")).startswith("slot.part")
                for row in flagged_resolved["rows"]
                for box in row["boxes"]
            )
            and any(
                str(box.get("slot_id", "")).startswith("slot.part")
                for row in unflagged_resolved["rows"]
                for box in row["boxes"]
            ),
        )
        check(
            "part and mark ledgers preserve profile instructions while adding declared context",
            "left eye at readable scale" in eye_box["hint"]
            and "SPLIT CRESCENT" in mark_box["label"],
        )
        outfit_box = next(box for box in layout["boxes"] if box["slot_id"] == "outfit.turn.front")
        items_box = next(box for box in layout["boxes"] if box["slot_id"] == "items.primary")
        expression_box = next(box for box in layout["boxes"] if box["slot_id"] == "expressions.ex.03")
        check(
            "outfit and item panels keep generic drawing instructions plus declared content",
            "primary outfit" in outfit_box["hint"]
            and "short field coat" in outfit_box["hint"]
            and "brass compass" in items_box["hint"]
            and "repaired hinge" in items_box["hint"],
        )
        check(
            "expression panel keeps generic set instructions plus character-specific expression",
            "third declared expression" in expression_box["hint"]
            and "restrained one-corner smile" in expression_box["hint"],
        )
        panel_requests = json.loads(scaffold["panel_requests"].read_text(encoding="utf-8"))
        prompt = first_panel_prompt(scaffold)
        check(
            "scaffold writes exact panel-only model prompts with no renderer-owned content",
            "single Character Sheet panel" in prompt
            and "same identity consistently" in prompt
            and "Return artwork only" in prompt
            and "profile block" in prompt
            and "strict coordinate template" not in prompt,
        )
        check(
            "default scaffold transport never sends the full sheet to a maskless model",
            panel_requests["transport"]["id"] == "panel-images"
            and panel_requests["transport"]["full_sheet_model_input"] is False
            and panel_requests["transport"]["pixel_edit_mask_required"] is False
            and scaffold["fill_prompt"] is None
            and len(panel_requests["requests"])
            == sum(1 for box in layout["boxes"] if box["harvest"])
            and panel_requests["requests"][0]["generation_stage"] == 1
            and panel_requests["requests"][0]["required_accepted_reference_results"] == []
            and all(
                request["required_accepted_reference_results"]
                for request in panel_requests["requests"]
                if request["generation_stage"] > 1
            ),
        )
        check(
            "arbitrary visual identity axes reach the complete fill prompt",
            "Visual identity axis axes.01" in prompt
            and "habitual silhouette and deployment" in prompt
            and "character-fixed" in prompt,
        )
        check(
            "fixed visual continuity is global across parts marks colors and items",
            "Fixed parts.01" in prompt
            and "Fixed marks.01" in prompt
            and "Fixed colors.01" in prompt
            and "Fixed items.01" in prompt
            and "Fixed visual continuity is global, not limited to marks or anatomy" in prompt
            and "A panel-specific line that does not repeat the feature never permits removing it" in prompt,
        )
        combined_panel_prompts = "\n".join(text for _request, text in panel_prompts(scaffold))
        missing_prompt_values = [
            f"fields/{key}"
            for key, value in sidecar_value["fields"].items()
            if isinstance(value, str)
            and value.strip()
            and value.casefold() not in combined_panel_prompts.casefold()
        ]
        rule_columns = {
            "counterpart_rule", "continuity_rule", "visibility_rule", "role_rule", "must_prove", "limit"
        }
        missing_prompt_values.extend(
            f"tables/{table_id}/{row['row_id']}/{column}"
            for table_id, rows in sidecar_value["tables"].items()
            for row in rows
            for column, value in row["values"].items()
            if isinstance(value, str)
            and value.strip()
            and column not in rule_columns
            and value.casefold() not in combined_panel_prompts.casefold()
        )
        check(
            "every nonempty authored drawing value reaches the complete fill prompt",
            not missing_prompt_values,
            missing_prompt_values,
        )
        combined_reviews = "\n".join(
            str(request.get("review") or "") for request in panel_requests["requests"]
        )
        rule_values = [
            f"tables/{table_id}/{row['row_id']}/{column}"
            for table_id, rows in sidecar_value["tables"].items()
            for row in rows
            for column, value in row["values"].items()
            if isinstance(value, str) and value.strip() and column in rule_columns
        ]
        leaked_rules = [
            key for key in rule_values
            if sidecar_value["tables"][key.split("/")[1]][int(key.split("/")[2].split(".")[1]) - 1]["values"][key.split("/")[3]].casefold()
            in combined_panel_prompts.casefold()
        ]
        check(
            "rule columns reach the request review and never a prompt",
            bool(rule_values) and not leaked_rules and combined_reviews.strip() != "",
            f"leaked {leaked_rules}",
        )
        palette_box = next(box for box in layout["boxes"] if box["slot_id"] == "palette.strip")
        check("renderer-owned color key is not harvestable", palette_box["harvest"] is False)

        many_colors = copy.deepcopy(sidecar_value)
        many_colors["tables"]["colors"] = [
            {
                "row_id": f"colors.{index:02d}",
                "values": {
                    "zone": f"declared target {index}",
                    "base": f"#{index:02X}{(index * 7) % 256:02X}{(index * 13) % 256:02X}",
                },
            }
            for index in range(1, 14)
        ]
        many_colors_render = render_sheet(
            profile,
            many_colors,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=render_root / "many-color-targets",
            profile_path=DEFAULT_PROFILE_PATH,
        )
        many_colors_layout = json.loads(
            many_colors_render["layout"].read_text(encoding="utf-8")
        )
        many_colors_palette = next(
            box
            for box in many_colors_layout["boxes"]
            if box["slot_id"] == "palette.strip"
        )
        check(
            "color targets are arbitrary declared rows rather than a ten-zone category cap",
            many_colors_palette["content_h"] >= 228
            and "declared target 13"
                in first_panel_prompt(many_colors_render),
            )

        cjk_value = copy.deepcopy(sidecar_value)
        cjk_name = "견본 見本 みほん / Sample"
        cjk_zone = "코 鼻 はな / nose"
        cjk_value["fields"]["identity.name"] = cjk_name
        cjk_value["tables"]["colors"].append(
            {
                "row_id": "colors.03",
                "values": {"zone": cjk_zone, "base": "#27231F"},
            }
        )
        cjk_render = render_sheet(
            profile,
            cjk_value,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=render_root / "cjk-scaffold",
            profile_path=DEFAULT_PROFILE_PATH,
        )
        cjk_layout = json.loads(cjk_render["layout"].read_text(encoding="utf-8"))
        raster_text = cjk_layout.get("raster_text") or {}
        overlays = raster_text.get("overlays") or []
        resolved_fonts = resolve_cjk_fonts(overlays)
        name_runs = segment_text_by_font("regular", cjk_name)
        glyphs_are_real = all(
            font_has_glyph(path, character)
            for path, segment in name_runs
            for character in segment
            if not character.isspace()
        ) and not any(
            font_has_glyph(path, "͸") for path in resolved_fonts.values()
        )
        with Image.open(cjk_render["png"]).convert("RGB") as cjk_image:
            name_crop = cjk_image.crop((35, 94, cjk_image.width // 3, 123))
            name_has_ink = any(
                max(pixel) < 180 for pixel in name_crop.getdata()
            )
        check(
            "design text outside the Latin script prints with hash-recorded real fonts and survives into the PNG",
            any(overlay.get("text") == cjk_name for overlay in overlays)
            and any(str(overlay.get("text", "")).startswith(cjk_zone) for overlay in overlays)
            and all(
                len(font.get("sha256", "")) == 64
                for font in raster_text.get("fonts", {}).values()
            )
            and all(
                overlay.get("fonts")
                and set(overlay["fonts"]) <= set(raster_text.get("fonts", {}))
                for overlay in overlays
            )
            and glyphs_are_real
            and name_has_ink,
            raster_text,
        )
        check(
            "CJK fonts resolve from the known paths first, then from fontconfig, and fail closed without either",
            *cjk_font_lookup_order(),
        )
        render_package = json.loads(scaffold["package"].read_text(encoding="utf-8"))
        check(
            "render package commits profile sidecar layout PNG mask and panel request manifest",
            render_package["renderer"].get("id") == "render_character_sheet"
            and all(
                isinstance(render_package.get(key), str) and len(render_package[key]) == 64
                for key in (
                    "profile_sha256",
                    "sheet_data_sha256",
                    "layout_sha256",
                    "png_sha256",
                    "edit_mask_sha256",
                )
            )
            and render_package["fill_transport"]["id"] == "panel-images"
            and len(render_package["fill_transport"]["panel_requests_sha256"]) == 64
            and render_package["fill_transport"]["panel_request_count"]
            == len(panel_requests["requests"]),
        )
        check(
            "masked full-sheet transport is refused without actual pixel-mask capability confirmation",
            expect_error(
                lambda: render_sheet(
                    profile,
                    sidecar_value,
                    sheet_dir=render_root,
                    mode="scaffold",
                    out_dir=render_root / "unconfirmed-masked-sheet",
                    profile_path=DEFAULT_PROFILE_PATH,
                    fill_transport="masked-sheet",
                ),
                "requires explicit confirmation",
            ),
        )
        confirmed_masked = render_sheet(
            profile,
            sidecar_value,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=render_root / "confirmed-masked-sheet",
            profile_path=DEFAULT_PROFILE_PATH,
            fill_transport="masked-sheet",
            pixel_edit_mask_confirmed=True,
        )
        confirmed_masked_package = json.loads(
            confirmed_masked["package"].read_text(encoding="utf-8")
        )
        masked_canvas = json.loads(
            confirmed_masked["layout"].read_text(encoding="utf-8")
        )["canvas"]
        check(
            "masked-sheet board keeps the model's 2:3 output ratio",
            masked_canvas["w"] * 3 == masked_canvas["h"] * 2,
        )
        check(
            "confirmed masked transport records the capability and emits only its mask-bound full-sheet prompt",
            confirmed_masked["fill_prompt"].is_file()
            and confirmed_masked["panel_requests"] is None
            and confirmed_masked_package["fill_transport"]["id"] == "masked-sheet"
            and confirmed_masked_package["fill_transport"]["pixel_edit_mask_confirmed"] is True
            and "valid only in an interface that applies the attached pixel edit mask"
            in confirmed_masked["fill_prompt"].read_text(encoding="utf-8"),
        )
        with Image.open(scaffold["edit_mask"]) as mask_image:
            active_box = next(box for box in layout["boxes"] if box["harvest"])
            palette_center = (
                round(palette_box["content_x"] + palette_box["content_w"] / 2),
                round(palette_box["content_y"] + palette_box["content_h"] / 2),
            )
            active_center = (
                round(active_box["content_x"] + active_box["content_w"] / 2),
                round(active_box["content_y"] + active_box["content_h"] / 2),
            )
            check(
                "edit mask exposes only harvestable white interiors",
                mask_image.size == (canvas["w"], canvas["h"])
                and mask_image.getpixel(active_center) == 255
                and mask_image.getpixel(palette_center) == 0,
            )

        sparse_value = base_sidecar()
        sparse_value["sheet_status"] = "identity-ready"
        sparse_value["fields"] = {
            "identity.name": "Aster",
            "identity.species_domain": "anthropomorphic wolf",
        }
        sparse_dir = render_root / "sparse-scaffold"
        sparse = render_sheet(
            profile,
            sparse_value,
            sheet_dir=render_root,
            mode="scaffold",
            out_dir=sparse_dir,
            profile_path=DEFAULT_PROFILE_PATH,
        )
        sparse_layout = json.loads(sparse["layout"].read_text(encoding="utf-8"))
        sparse_ids = {box["slot_id"] for box in sparse_layout["boxes"]}
        check(
            "auto policy omits undeclared optional panels from the model-facing sheet",
            "slot.mark.01" not in sparse_ids
            and "pose.state.01" not in sparse_ids
            and "eye.left.detail" not in sparse_ids
            and "expressions.ex.01" not in sparse_ids,
        )
        with Image.open(sparse["edit_mask"]) as sparse_mask:
            sparse_active = [
                box
                for box in sparse_layout["boxes"]
                if box["fill_state"] == "fill"
            ]
            sparse_skipped = [
                box
                for box in sparse_layout["boxes"]
                if box["fill_state"] == "skip"
                and box.get("kind") not in {"palette", "profile"}
            ]
            def mask_center(box: Mapping[str, Any]) -> tuple[int, int]:
                return (
                    round(box["content_x"] + box["content_w"] / 2),
                    round(box["content_y"] + box["content_h"] / 2),
                )
            check(
                "omitted panels allocate no editable mask region",
                sparse_mask.getbbox() is not None
                and all(
                    box["slot_id"] not in sparse_ids
                    for box in profile_boxes
                    if box.get("source_row_id")
                )
                and sparse_active
                and all(sparse_mask.getpixel(mask_center(box)) == 255 for box in sparse_active)
                and all(sparse_mask.getpixel(mask_center(box)) == 0 for box in sparse_skipped),
            )
        sparse_warnings = sparse["coverage"]["warnings"]
        check(
            "unmatched authored bindings surface as coverage warnings, not silent fallbacks",
            any("declares source_part" in warning for warning in sparse_warnings)
            and any(
                "source_row_id 'marks.01' but the marks table has no such row" in warning
                for warning in sparse_warnings
            ),
        )

        forced_value = copy.deepcopy(sparse_value)
        forced_value["slots"]["slot.mark.01"] = {
            "image_path": "",
            "generation_package": "",
            "fill_policy": "fill",
        }
        check(
            "fill policy cannot force a panel whose persistent source row was deleted",
            expect_error(
                lambda: render_sheet(
                    profile,
                    forced_value,
                    sheet_dir=render_root,
                    mode="scaffold",
                    out_dir=render_root / "forced-scaffold",
                    profile_path=DEFAULT_PROFILE_PATH,
                ),
                "does not exist in the source table",
            ),
        )

        invalid_keep = copy.deepcopy(sparse_value)
        invalid_keep["slots"]["canon.primary"]["fill_policy"] = "keep"
        check(
            "keep policy refuses to protect a panel without an accepted image",
            expect_error(
                lambda: render_sheet(
                    profile,
                    invalid_keep,
                    sheet_dir=render_root,
                    mode="scaffold",
                    out_dir=render_root / "invalid-keep",
                ),
                "has no accepted image_path",
            ),
        )

        panel_results_dir = render_root / "panel-results"
        panel_results_dir.mkdir()
        fill_colors: dict[str, tuple[int, int, int]] = {}
        check(
            "every panel request asks for an image at least 1024 pixels on its long side",
            all(
                max(request["target"]["generation_w"], request["target"]["generation_h"]) >= 1024
                for request in panel_requests["requests"]
            ),
        )
        check(
            "every panel prompt states the generation size it asks for",
            all(
                f"Produce a {request['target']['generation_w']} by {request['target']['generation_h']} pixel image"
                in (render_root / "scaffold" / request["prompt"]["path"]).read_text(encoding="utf-8")
                for request in panel_requests["requests"]
            ),
        )
        for index, request in enumerate(panel_requests["requests"]):
            color = ((index * 37 + 40) % 220, (index * 67 + 50) % 220, (index * 97 + 60) % 220)
            fill_colors[request["slot_id"]] = color
            target = request["target"]
            Image.new(
                "RGB",
                (target["generation_w"], target["generation_h"]),
                color,
            ).save(panel_results_dir / request["result_file"], format="PNG")
        filled_path = render_root / "filled.png"
        composition = compose_panel_fills(
            scaffold["panel_requests"],
            panel_results_dir,
            out_path=filled_path,
        )
        check(
            "panel compositor writes every requested result only into scaffold content rectangles",
            composition["output"] == filled_path.resolve()
            and composition["manifest"].is_file()
            and len(composition["results"]) == len(panel_requests["requests"]),
        )
        check(
            "the board takes a reduced copy and the result keeps its size",
            all(
                record["fitted_size"]["w"] <= record["target"]["w"]
                and record["fitted_size"]["h"] <= record["target"]["h"]
                and max(record["source_size"]["w"], record["source_size"]["h"]) >= 1024
                for record in composition["results"]
            ),
        )
        bound_sidecar_path = render_root / "sheet-data.json"
        bound_before = bound_sidecar_path.read_bytes()
        bound = compose_panel_fills(
            scaffold["panel_requests"],
            panel_results_dir,
            out_path=render_root / "filled-bound.png",
            update_sidecar_path=bound_sidecar_path,
        )
        bound_sidecar = json.loads(bound_sidecar_path.read_text(encoding="utf-8"))
        first_request = panel_requests["requests"][0]
        bound_slot = bound_sidecar["slots"].get(first_request["slot_id"]) or bound_sidecar["slots"].get(
            first_request["resolved_slot_id"]
        )
        with Image.open(render_root / bound_slot["image_path"]) as bound_image:
            bound_size = bound_image.size
        check(
            "compose binds each slot to the full-size result, not to a board crop",
            bound["sidecar_update"] is not None
            and bound_slot["image_path"] == f"panel-results/{first_request['result_file']}"
            and bound_size == (first_request["target"]["generation_w"], first_request["target"]["generation_h"]),
            f"bound {bound_slot} size {bound_size}",
        )
        bound_sidecar_path.write_bytes(bound_before)
        staged_dir = render_root / "panel-results-staged"
        staged_dir.mkdir(exist_ok=True)
        staged_first = panel_requests["requests"][0]
        shutil.copyfile(panel_results_dir / staged_first["result_file"], staged_dir / staged_first["result_file"])
        staged = compose_panel_fills(
            scaffold["panel_requests"],
            staged_dir,
            out_path=render_root / "filled-staged.png",
            update_sidecar_path=bound_sidecar_path,
            only=[staged_first["slot_id"]],
            allow_missing=True,
        )
        staged_sidecar = json.loads(bound_sidecar_path.read_text(encoding="utf-8"))
        staged_bound = staged_sidecar["slots"].get(staged_first["slot_id"]) or staged_sidecar["slots"].get(
            staged_first["resolved_slot_id"]
        )
        check(
            "a staged fill binds the accepted anchor while the other panels have no result yet",
            len(staged["results"]) == 1
            and len(staged["missing_results"]) == len(panel_requests["requests"]) - 1
            and staged_bound["image_path"] == f"panel-results-staged/{staged_first['result_file']}"
            and expect_error(
                lambda: compose_panel_fills(
                    scaffold["panel_requests"], staged_dir, out_path=render_root / "filled-staged.png"
                ),
                "panel result is missing",
            ),
            f"results {len(staged['results'])} missing {len(staged['missing_results'])} bound {staged_bound}",
        )
        bound_sidecar_path.write_bytes(bound_before)
        second_request = panel_requests["requests"][1]
        second_slot_id = second_request.get("resolved_slot_id", second_request["slot_id"])
        compose_panel_fills(
            scaffold["panel_requests"],
            panel_results_dir,
            out_path=render_root / "filled-bound.png",
            update_sidecar_path=bound_sidecar_path,
            only=[first_request["slot_id"]],
        )
        only_sidecar = json.loads(bound_sidecar_path.read_text(encoding="utf-8"))
        only_first = only_sidecar["slots"].get(first_request["slot_id"]) or only_sidecar["slots"].get(
            first_request["resolved_slot_id"]
        )
        check(
            "compose --only binds the accepted slot and leaves the others unbound",
            only_first["image_path"] == f"panel-results/{first_request['result_file']}"
            and not only_sidecar["slots"].get(second_slot_id, {}).get("image_path"),
            f"second slot {second_slot_id}: {only_sidecar['slots'].get(second_slot_id)}",
        )
        try:
            compose_panel_fills(
                scaffold["panel_requests"],
                panel_results_dir,
                out_path=render_root / "filled-bound.png",
                update_sidecar_path=bound_sidecar_path,
                only=["no.such.slot"],
            )
            only_unknown = None
        except ValueError as exc:
            only_unknown = str(exc)
        check(
            "compose --only refuses a slot that has no panel request",
            only_unknown is not None and "no.such.slot" in only_unknown,
            str(only_unknown),
        )
        bound_sidecar_path.write_bytes(bound_before)
        sheet_package_path = render_root / "sheet.package.json"
        sheet_package_path.write_text(
            json.dumps(generation_package(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        candidate_sidecar_before = sidecar_path.read_bytes()
        candidate = harvest_sheet(
            filled_path,
            layout_path=scaffold["layout"],
            out_dir=render_root / "candidates",
        )
        check(
            "candidate harvest leaves the sidecar unchanged until explicit acceptance",
            candidate["sidecar_update"] is None
            and sidecar_path.read_bytes() == candidate_sidecar_before
            and len(candidate["crops"]) == sum(1 for box in layout["boxes"] if box["harvest"]),
        )

        crops_dir = render_root / "crops"
        harvested = harvest_sheet(
            filled_path,
            layout_path=scaffold["layout"],
            out_dir=crops_dir,
            update_sidecar_path=sidecar_path,
            generation_package=sheet_package_path,
        )
        check(
            "harvester produces every drawing panel and skips the color key",
            len(harvested["crops"]) == sum(1 for box in layout["boxes"] if box["harvest"])
            and all(crop["slot_id"] != "palette.strip" for crop in harvested["crops"]),
        )
        harvested_names = {crop["file"] for crop in harvested["crops"]}
        check(
            "profile-owned output names keep HTML slot filenames stable",
            {
                "base-front.png",
                "left-eye-detail.png",
                "mark-01.png",
                "mark-02.png",
                "pose-state-02.png",
                "outfit-front.png",
            }
            <= harvested_names,
        )
        solid = True
        for crop in harvested["crops"]:
            with Image.open(crops_dir / crop["file"]) as crop_image:
                extrema = crop_image.convert("RGB").getextrema()
                expected = fill_colors[crop["slot_id"]]
                if any(low != high or low != expected[channel] for channel, (low, high) in enumerate(extrema)):
                    solid = False
                    break
        check("harvested slot images contain only the white drawing regions", solid)
        manifest = json.loads(harvested["manifest"].read_text(encoding="utf-8"))
        check(
            "harvest manifest commits source layout and every crop",
            manifest["harvester"].get("id") == "harvest_sheet_render"
            and len(manifest["source_sha256"]) == 64
            and len(manifest["layout_sha256"]) == 64
            and all(len(crop["sha256"]) == 64 for crop in manifest["crops"]),
        )
        updated = json.loads(sidecar_path.read_text(encoding="utf-8"))
        check(
            "sidecar update uses current persistent eye and mark slot IDs",
            updated["slots"]["eye.left.detail"]["image_path"]
            == "crops/left-eye-detail.png"
            and updated["slots"]["slot.mark.01"]["image_path"]
            == "crops/mark-01.png",
        )
        check(
            "accepted harvest updates provenance and reference readiness",
            updated["sheet_status"] == "reference-ready"
            and all(
                slot["generation_package"] == "sheet.package.json"
                for slot in updated["slots"].values()
                if slot["image_path"]
            ),
        )
        composite_dir = render_root / "composite"
        composite = render_sheet(
            profile,
            updated,
            sheet_dir=render_root,
            mode="reference",
            out_dir=composite_dir,
            profile_path=DEFAULT_PROFILE_PATH,
            sidecar_path=sidecar_path,
        )
        composite_package = json.loads(composite["package"].read_text(encoding="utf-8"))
        composite_svg = composite["svg"].read_text(encoding="utf-8")
        check(
            "clean composite resolves all harvested slots under pristine labels",
            len(composite_package["inputs"]) == len(harvested["crops"])
            and composite_svg.count("<image ") == len(harvested["crops"]),
        )
        check(
            "clean composite replaces fill instructions with downstream authority",
            "IDENTITY REFERENCE" in composite_svg
            and "SCENE PROMPTS OWN" in composite_svg
            and "DRAW THE SAME CHARACTER ONLY INSIDE" not in composite_svg,
        )

        identity_reference_dir = render_root / "identity-reference"
        identity_reference = render_sheet(
            profile,
            updated,
            sheet_dir=render_root,
            mode="reference",
            reference_scope="identity",
            out_dir=identity_reference_dir,
            profile_path=DEFAULT_PROFILE_PATH,
            sidecar_path=sidecar_path,
        )
        identity_reference_layout = json.loads(
            identity_reference["layout"].read_text(encoding="utf-8")
        )
        check(
            "identity scope narrows the reference board to fixed identity panels",
            all(
                box["reference_role"] == "identity" and box.get("binding") != "variable"
                for box in identity_reference_layout["boxes"]
                if box["kind"] != "palette"
            )
            and len(json.loads(identity_reference["package"].read_text(encoding="utf-8"))["inputs"])
            == sum(
                1
                for box in layout["boxes"]
                if box["harvest"]
                and box["reference_role"] == "identity"
                and box.get("binding") != "variable"
            ),
        )
        identity_bundle_path = identity_reference_dir / "reference-bundle.json"
        identity_bundle = json.loads(identity_bundle_path.read_text(encoding="utf-8"))
        bundle_panels = identity_bundle["panels"]
        check(
            "the reference bundle lists every accepted panel with its role whatever the board shows",
            identity_reference["reference_bundle"] == identity_bundle_path
            and identity_bundle["artifact_type"] == "character-sheet-reference-bundle"
            and identity_bundle["board"]["scope"] == "identity"
            and len(bundle_panels) == sum(1 for box in layout["boxes"] if box["harvest"])
            and identity_bundle["roles"].get("performance", 0) >= 1
            and len({panel["slot_id"] for panel in bundle_panels}) == len(bundle_panels)
            and json.loads(identity_reference["package"].read_text(encoding="utf-8"))["reference_bundle_sha256"]
            == hashlib.sha256(identity_bundle_path.read_bytes()).hexdigest(),
            f"roles {identity_bundle['roles']} panels {len(bundle_panels)}",
        )
        bundle_sizes_match = True
        for panel in bundle_panels:
            with Image.open(render_root / panel["image_path"]) as panel_image:
                if panel_image.size != (panel["width"], panel["height"]):
                    bundle_sizes_match = False
            if len(panel["image_sha256"]) != 64 or not panel["kind"] or not panel["label"]:
                bundle_sizes_match = False
        check(
            "the reference bundle records each panel's size and hash from its file",
            bundle_sizes_match,
        )

        square_path = render_root / "square.png"
        Image.new("RGB", (512, 512), (255, 255, 255)).save(square_path, format="PNG")
        check(
            "harvester rejects aspect-ratio drift before cropping",
            expect_error(
                lambda: harvest_sheet(
                    square_path,
                    layout_path=scaffold["layout"],
                    out_dir=render_root / "bad-aspect",
                ),
                "aspect ratio differs",
            ),
        )
        protected_drift_path = render_root / "protected-drift.png"
        with Image.open(filled_path) as filled_source:
            protected_drift = filled_source.convert("RGB")
        ImageDraw.Draw(protected_drift).rectangle((0, 0, protected_drift.width - 1, 160), fill=(255, 0, 255))
        protected_drift.save(protected_drift_path, format="PNG")
        check(
            "harvester rejects a model output that moved or repainted protected scaffold regions",
            expect_error(
                lambda: harvest_sheet(
                    protected_drift_path,
                    layout_path=scaffold["layout"],
                    out_dir=render_root / "protected-drift-crops",
                ),
                "protected regions differ from the scaffold",
            ),
        )
        check(
            "harvester rejects unknown or renderer-owned --only panels",
            expect_error(
                lambda: harvest_sheet(
                    filled_path,
                    layout_path=scaffold["layout"],
                    out_dir=render_root / "bad-only",
                    only=["palette.strip"],
                ),
                "unknown or non-harvestable",
            ),
        )
        outside_dir = root / "outside-crops"
        check(
            "sidecar update refuses crop output outside the sheet folder",
            expect_error(
                lambda: harvest_sheet(
                    filled_path,
                    layout_path=scaffold["layout"],
                    out_dir=outside_dir,
                    update_sidecar_path=sidecar_path,
                    generation_package=sheet_package_path,
                ),
                "inside the Character Sheet folder",
            ),
        )
        short_profile = copy.deepcopy(profile)
        short_profile["canvas"][1] = 2200
        check(
            "renderer rejects profiles whose last row would be clipped",
            expect_error(lambda: validate_profile_semantics(short_profile), "do not fit"),
        )
    with tempfile.TemporaryDirectory() as profile_tmp:
        profile_root = Path(profile_tmp)
        anthro = load_profile(ANTHRO_PROFILE_PATH)
        anthro_slots = {box["slot_id"] for row in anthro["rows"] for box in row["boxes"]}
        check(
            "anthro render profile is schema-valid and carries anthro-specific panels",
            anthro["canvas"][0] > 0
            and anthro["canvas"][1] > 0
            and {"head.study", "hand.detail", "hindpaw.detail", "tail.detail", "identity.icon"}
            <= anthro_slots,
        )
        declared_sheet = {
            "sheet_status": "draft",
            "fields": {"field.sheet_layout_profile": "anthro"},
            "tables": {},
            "slots": {},
        }
        resolved_path, selection = select_profile_path(declared_sheet, None)
        check(
            "profile selection resolves the declared bundled profile id",
            resolved_path == ANTHRO_PROFILE_PATH and selection["method"] == "sheet-field",
        )
        authored_profile = {
            "id": "custom-smoke",
            "title": "CUSTOM SMOKE SHEET",
            "canvas": [1600, 2400],
            "header_fields": [{"field_id": "identity.name", "label": "NAME"}],
            "rows": [
                {
                    "height": 700,
                    "boxes": [
                        {
                            "slot_id": "canon.primary",
                            "output_name": "front.png",
                            "panel_code": "A1",
                            "kind": "canonical_view",
                            "label": "FRONT",
                            "hint": "full body front view of this individual, neutral stance, plain background",
                        },
                        {
                            "slot_id": "canon.back",
                            "output_name": "back.png",
                            "panel_code": "A2",
                            "kind": "canonical_view",
                            "label": "BACK",
                            "hint": "full body back view of this individual, neutral stance, plain background",
                        },
                        {
                            "slot_id": "canon.side",
                            "output_name": "left.png",
                            "panel_code": "A3",
                            "kind": "canonical_view",
                            "label": "LEFT SIDE",
                            "hint": "complete left-side view of this individual, neutral stance, plain background",
                        },
                        {
                            "slot_id": "canon.right",
                            "output_name": "right.png",
                            "panel_code": "A4",
                            "kind": "canonical_view",
                            "label": "RIGHT SIDE",
                            "hint": "complete right-side view of this individual, neutral stance, plain background",
                        },
                        {
                            "slot_id": "canon.top",
                            "output_name": "top.png",
                            "panel_code": "A5",
                            "kind": "canonical_view",
                            "label": "TOP",
                            "hint": "complete top view exposing the declared upper topology on a plain background",
                        },
                        {
                            "slot_id": "canon.underside",
                            "output_name": "underside.png",
                            "panel_code": "A6",
                            "kind": "canonical_view",
                            "label": "UNDERSIDE",
                            "hint": "complete underside view exposing the declared lower topology on a plain background",
                        },
                        {
                            "slot_id": "identity.icon",
                            "output_name": "icon.png",
                            "panel_code": "C1",
                            "kind": "icon",
                            "label": "ICON",
                            "hint": "primary recognition structure at readable scale on a plain background",
                        },
                    ],
                }
            ],
        }
        authored_path = profile_root / "layout-profile.json"
        authored_path.write_text(
            json.dumps(authored_profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        declared_authored = copy.deepcopy(declared_sheet)
        declared_authored["fields"]["field.sheet_layout_profile"] = "layout-profile.json"
        authored_resolved, _ = select_profile_path(
            declared_authored, None, sheet_dir=profile_root
        )
        check(
            "profile selection resolves an authored profile relative to the sheet folder",
            authored_resolved == authored_path
            and load_profile(authored_resolved)["id"] == "custom-smoke",
        )
        check(
            "authored profiles may declare topology views beyond a four-direction starter",
            [
                box["slot_id"]
                for row in load_profile(authored_resolved)["rows"]
                for box in row["boxes"]
                if box["kind"] == "canonical_view"
            ]
            == [
                "canon.primary",
                "canon.back",
                "canon.side",
                "canon.right",
                "canon.top",
                "canon.underside",
            ],
        )
        unknown_sheet = copy.deepcopy(declared_sheet)
        unknown_sheet["fields"]["field.sheet_layout_profile"] = "starship"
        check(
            "unknown profile id fails with the bundled profile list",
            expect_error(lambda: select_profile_path(unknown_sheet, None), "bundled profiles"),
        )
        explicit_id_path, explicit_id_selection = select_profile_path(
            {"fields": {}, "tables": {}, "slots": {}}, Path("anthro")
        )
        check(
            "--profile accepts a bundled profile id like the sheet field does",
            explicit_id_path == ANTHRO_PROFILE_PATH
            and explicit_id_selection["method"] == "explicit-argument"
            and "anthro" in explicit_id_selection["reason"],
        )
        check(
            "--profile rejects an unknown profile id with the bundled profile list",
            expect_error(
                lambda: select_profile_path(
                    {"fields": {}, "tables": {}, "slots": {}}, Path("starship")
                ),
                "bundled profiles",
            ),
        )
        fallback_path, fallback_selection = select_profile_path(
            {"fields": {}, "tables": {}, "slots": {}}, None
        )
        check(
            "undeclared profile falls back to the domain-neutral profile",
            fallback_path == GENERAL_PROFILE_PATH and fallback_selection["method"] == "default",
        )

        general_profile = load_profile(GENERAL_PROFILE_PATH)
        spine_dir = profile_root / "form-spine"
        base_form_dir = spine_dir / "forms" / "base"
        changed_form_dir = spine_dir / "forms" / "changed"
        base_form_dir.mkdir(parents=True)
        changed_form_dir.mkdir(parents=True)

        def linked_form_sheet(form_id: str, display_name: str, profile_id: str) -> dict[str, Any]:
            return {
                "sheet_status": "identity-ready",
                "fields": {
                    "identity.name": display_name,
                    "identity.species_domain": "profile-declared form domain",
                    "field.form_id": form_id,
                    "field.form_spine_path": "../../sheet-data.json",
                    "field.sheet_layout_profile": profile_id,
                },
                "tables": {},
                "slots": {},
            }

        base_form_path = base_form_dir / "sheet-data.json"
        changed_form_path = changed_form_dir / "sheet-data.json"
        base_form_value = linked_form_sheet("base", "Mica", "general")
        changed_form_value = linked_form_sheet("changed", "Mica / Changed", "anthro")
        base_form_path.write_text(
            json.dumps(base_form_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        changed_form_path.write_text(
            json.dumps(changed_form_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        spine_sheet = {
            "sheet_status": "identity-ready",
            "fields": {
                "identity.name": "Mica",
                "identity.species_domain": "multi-form character spine",
                "field.sheet_layout_profile": "general",
            },
            "tables": {
                "formreg": [
                    {
                        "row_id": "formreg.01",
                        "values": {
                            "form_id": "base",
                            "display_name": "Mica",
                            "kind_ref": "base-domain",
                            "trigger_transition": "default stable form",
                            "persists": "recognition core and left-side signal mark",
                            "sheet_path": "forms/base",
                        },
                    },
                    {
                        "row_id": "formreg.02",
                        "values": {
                            "form_id": "changed",
                            "display_name": "Mica / Changed",
                            "kind_ref": "changed-domain",
                            "trigger_transition": "declared activation transition",
                            "persists": "recognition core and left-side signal mark",
                            "sheet_path": "forms/changed/sheet-data.json",
                        },
                    },
                ],
                "invariants": [
                    {
                        "row_id": "invariants.01",
                        "values": {
                            "invariant": "recognition core and signal-side relation",
                            "value": "same cyan core; signal mark remains left only",
                            "binding": "character-fixed",
                            "visible_expression": "core shape and left/right comparison in every form",
                        },
                    }
                ],
            },
            "slots": {},
        }
        spine_path = spine_dir / "sheet-data.json"
        spine_path.write_text(
            json.dumps(spine_sheet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        spine_render = render_sheet(
            general_profile,
            spine_sheet,
            sheet_dir=spine_dir,
            mode="scaffold",
            out_dir=spine_dir / "rendered",
            profile_path=GENERAL_PROFILE_PATH,
            sidecar_path=spine_path,
        )
        form_lineage = json.loads(
            spine_render["package"].read_text(encoding="utf-8")
        )["form_lineage"]
        check(
            "form registry hash-binds separate complete form sheets and their own profiles",
            [form["form_id"] for form in form_lineage["forms"]]
            == ["base", "changed"]
            and all(len(form["sheet_data_sha256"]) == 64 for form in form_lineage["forms"])
            and all(len(form["profile_sha256"]) == 64 for form in form_lineage["forms"])
            and all(form["canonical_view_count"] >= 2 for form in form_lineage["forms"])
            and len(form_lineage["cross_form_invariants_sha256"]) == 64,
        )

        broken_reverse = copy.deepcopy(base_form_value)
        broken_reverse["fields"]["field.form_spine_path"] = "../sheet-data.json"
        base_form_path.write_text(
            json.dumps(broken_reverse, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        check(
            "a linked form must point back to the exact spine sidecar",
            expect_error(
                lambda: render_sheet(
                    general_profile,
                    spine_sheet,
                    sheet_dir=spine_dir,
                    mode="scaffold",
                    out_dir=spine_dir / "broken-reverse",
                    profile_path=GENERAL_PROFILE_PATH,
                    sidecar_path=spine_path,
                ),
                "does not resolve to this spine",
            ),
        )
        base_form_path.write_text(
            json.dumps(base_form_value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        escaping_spine = copy.deepcopy(spine_sheet)
        escaping_spine["tables"]["formreg"][0]["values"]["sheet_path"] = "../outside"
        check(
            "form registry paths cannot escape the character spine folder",
            expect_error(
                lambda: render_sheet(
                    general_profile,
                    escaping_spine,
                    sheet_dir=spine_dir,
                    mode="scaffold",
                    out_dir=spine_dir / "escaping-form",
                    profile_path=GENERAL_PROFILE_PATH,
                    sidecar_path=spine_path,
                ),
                "escapes the character spine folder",
            ),
        )

        nonhuman_sheet = {
            "sheet_status": "identity-ready",
            "fields": {
                "identity.name": "Hex",
                "identity.species_domain": "six-unit photonic swarm",
                "field.model_fill_visual_design_brief": (
                    "Exactly six cobalt luminous orbs in a fixed hexagonal formation; "
                    "no face, limbs, torso, feet, clothing, or biological anatomy."
                ),
            },
            "tables": {
                "invariants": [
                    {
                        "row_id": "invariants.01",
                        "values": {
                            "invariant": "component count and topology",
                            "value": "exactly six separate cores in a hexagonal formation",
                            "binding": "character-fixed",
                            "visible_expression": "six distinct lights",
                        },
                    }
                ],
                "overrides": [
                    {
                        "row_id": "overrides.01",
                        "values": {
                            "attribute": "anatomy",
                            "baseline": "may have limbs",
                            "override": "no biological anatomy",
                            "reason": "photonic collective",
                            "binding": "individual-fixed",
                        },
                    }
                ],
            },
            "slots": {},
        }
        general_profile = load_profile(GENERAL_PROFILE_PATH)
        nonhuman_render = render_sheet(
            general_profile,
            nonhuman_sheet,
            sheet_dir=profile_root,
            mode="scaffold",
            out_dir=profile_root / "nonhuman-out",
            profile_path=GENERAL_PROFILE_PATH,
        )
        nonhuman_layout = json.loads(nonhuman_render["layout"].read_text(encoding="utf-8"))
        nonhuman_prompt = first_panel_prompt(nonhuman_render)
        check(
            "domain-neutral fallback emits no undeclared humanoid anatomy panels",
            not {
                "head_study",
                "part_detail",
                "hand_detail",
                "foot_detail",
                "tail_detail",
            }.intersection({box["kind"] for box in nonhuman_layout["boxes"]})
            and sum(
                box["kind"] == "canonical_view" for box in nonhuman_layout["boxes"]
            )
            >= 2,
        )
        check(
            "complete invariant and override contracts reach the model-fill prompt",
            "exactly six separate cores" in nonhuman_prompt
            and "no biological anatomy" in nonhuman_prompt
            and "Never add humanoid anatomy" in nonhuman_prompt,
        )

        stable_mark_sheet = {
            "sheet_status": "identity-ready",
            "fields": {
                "identity.name": "Row Stable",
                "identity.species_domain": "humanoid",
            },
            "tables": {
                "marks": [
                    {
                        "row_id": "marks.02",
                        "values": {
                            "mark_id": "ear notch",
                            "landmark_anchor": "left ear",
                            "shape_path": "triangular notch",
                            "laterality": "left only",
                            "counterpart_rule": "the right ear rim is intact",
                            "continuity_rule": "preserve the same notch shape and placement",
                            "visibility_rule": "must appear whenever the left ear rim is visible",
                            "binding": "individual-fixed",
                        },
                    }
                ],
            },
            "slots": {
                "slot.mark.01": {
                    "image_path": "crops/mark-01.png",
                    "generation_package": "",
                    "fill_policy": "auto",
                }
            },
        }
        stable_resolved, _ = resolve_state_panels(profile, stable_mark_sheet)
        stable_plan = build_panel_plan(
            apply_sheet_context(stable_resolved, stable_mark_sheet),
            stable_mark_sheet,
            sheet_dir=render_root,
            mode="scaffold",
            reference_scope="identity",
        )
        stable_marks = [
            box for row in stable_plan for box in row["boxes"] if box["kind"] == "mark_detail"
        ]
        check(
            "stable row ids prevent a deleted mark's accepted image from rebinding",
            len(stable_marks) == 1
            and stable_marks[0]["source_row_id"] == "marks.02"
            and stable_marks[0]["slot_id"] == "slot.mark.02"
            and stable_marks[0]["fill_state"] == "fill"
            and not stable_marks[0]["image_relative"],
        )

        variable_sheet = copy.deepcopy(nonhuman_sheet)
        variable_sheet["tables"]["marks"] = [
            {
                "row_id": "marks.01",
                "values": {
                    "mark_id": "moving halo",
                    "landmark_anchor": "around formation",
                    "shape_path": "position changes with mood",
                    "laterality": "radial symmetric around the complete formation",
                    "counterpart_rule": "the halo surrounds the full formation rather than one lateral unit",
                    "binding": "variable",
                },
            }
        ]
        Image.new("RGB", (32, 32), (20, 40, 80)).save(
            profile_root / "variable-front.png", format="PNG"
        )
        Image.new("RGB", (32, 32), (80, 40, 20)).save(
            profile_root / "variable-mark.png", format="PNG"
        )
        variable_sheet["slots"] = {
            "canon.primary": {
                "image_path": "variable-front.png",
                "generation_package": "",
            },
            "slot.mark.01": {
                "image_path": "variable-mark.png",
                "generation_package": "",
            },
        }
        variable_reference = render_sheet(
            general_profile,
            variable_sheet,
            sheet_dir=profile_root,
            mode="reference",
            reference_scope="identity",
            out_dir=profile_root / "variable-reference",
            profile_path=GENERAL_PROFILE_PATH,
        )
        variable_package = json.loads(variable_reference["package"].read_text(encoding="utf-8"))
        check(
            "variable evidence is excluded from the identity-only reference board",
            [item["slot_id"] for item in variable_package["inputs"]] == ["canon.primary"],
        )
        expression_sheet = {
            "fields": {},
            "tables": {
                "expressions": [
                    {
                        "row_id": "expressions.01",
                        "values": {
                            "state": "wary delight",
                            "overall_read": "restrained delight with continued vigilance",
                            "channel_states": "one-corner smile; narrowed eyes; slow tail movement",
                            "fixed_identity_cues": "same muzzle, eye spacing, and split-crescent mark",
                        },
                    },
                    {"row_id": "expressions.02", "values": {"state": "startled", "channel_states": "attention darts toward the disturbance"}},
                ],
            },
        }
        contexted = apply_sheet_context(anthro, expression_sheet)
        expression_boxes = [
            box
            for row in contexted["rows"]
            for box in row["boxes"]
            if box.get("kind") == "expression_variant"
        ]
        check(
            "expression variants merge declared rows into labels and hints",
            len(expression_boxes) >= 2
            and expression_boxes[0]["label"] == "STATE: WARY DELIGHT"
            and "one-corner smile" in expression_boxes[0]["hint"]
            and expression_boxes[1]["label"] == "STATE: STARTLED",
        )
        blank_plan = [
            {
                "height": 700,
                "boxes": [
                    {**authored_profile["rows"][0]["boxes"][0], "hint": " ", "fill_state": "fill"},
                    {**authored_profile["rows"][0]["boxes"][1], "fill_state": "fill"},
                ],
            }
        ]
        check(
            "fill prompt refuses panels without drawing instructions",
            expect_error(
                lambda: build_fill_prompt(authored_profile, {}, blank_plan),
                "no drawing instructions",
            ),
        )
        authored_loaded = load_profile(authored_path)
        gap_sheet = {
            "sheet_status": "draft",
            "fields": {},
            "tables": {
                "marks": [
                    {
                        "row_id": "marks.01",
                        "values": {
                            "mark_id": "horn chip",
                            "landmark_anchor": "left horn",
                            "shape_path": "small chip",
                            "laterality": "left only",
                            "counterpart_rule": "the corresponding right horn is intact with no chip",
                        },
                    }
                ],
                "items": [
                    {
                        "row_id": "items.01",
                        "values": {
                            "item": "signal key",
                            "visual_identity": "flat brass hexagon with one cyan enamel diagonal and a repaired black hinge",
                            "scale_attachment": "palm-sized; single offset loop attaches at the upper-left corner",
                            "role_rule": "always carried and identity-bearing",
                        },
                    }
                ],
                "evidence": [
                    {
                        "row_id": "evidence.01",
                        "values": {
                            "subject_table": "items",
                            "subject_row_id": "items.01",
                            "view_id": "reverse",
                            "orientation_configuration": "orthographic reverse face",
                            "specification": "show the repaired hinge plate and no enamel diagonal on this face",
                            "must_prove": "front-only enamel and reverse-only hinge construction are not mirrored",
                        },
                    },
                    {
                        "row_id": "evidence.02",
                        "values": {
                            "subject_table": "items",
                            "subject_row_id": "items.01",
                            "view_id": "edge",
                            "orientation_configuration": "orthographic edge view",
                            "specification": "show plate thickness and the offset attachment loop",
                            "must_prove": "loop placement, thickness, and hinge projection remain fixed",
                        },
                    },
                ],
            },
            "slots": {},
        }
        resolved_content_render = render_sheet(
            authored_loaded,
            gap_sheet,
            sheet_dir=profile_root,
            mode="scaffold",
            out_dir=profile_root / "resolved-content-out",
            profile_path=authored_path,
        )
        resolved_content_package = json.loads(
            resolved_content_render["package"].read_text(encoding="utf-8")
        )
        resolved_content_layout = json.loads(
            resolved_content_render["layout"].read_text(encoding="utf-8")
        )
        check(
            "declared visual rows receive resolved evidence panels instead of becoming coverage gaps",
            not resolved_content_package["coverage_gaps"]
            and resolved_content_package["state_panels"].get("mark_detail") == 1
            and resolved_content_package["state_panels"].get("items") == 1
            and resolved_content_package["state_panels"].get("evidence_view") == 2
            and {
                box["source_row_id"]
                for box in resolved_content_layout["boxes"]
                if box.get("kind") == "evidence_view"
            }
            == {"evidence.01", "evidence.02"}
            and any(
                "front-only enamel" in (box.get("review") or "")
                and "front-only enamel" not in box.get("hint", "")
                for box in resolved_content_layout["boxes"]
                if box.get("kind") == "evidence_view"
            ),
        )

        headless_profile = copy.deepcopy(authored_loaded)
        for profile_row in headless_profile["rows"]:
            profile_row["boxes"] = [
                box for box in profile_row["boxes"] if box.get("kind") != "icon"
            ]
        exception_sheet = copy.deepcopy(gap_sheet)
        exception_text = "The complete primary view is the intentional recognition panel."
        exception_sheet["fields"] = {"field.sheet_coverage_exceptions": exception_text}
        exception_render = render_sheet(
            headless_profile,
            exception_sheet,
            sheet_dir=profile_root,
            mode="scaffold",
            out_dir=profile_root / "exception-out",
            profile_path=authored_path,
        )
        exception_package = json.loads(exception_render["package"].read_text(encoding="utf-8"))
        check(
            "declared coverage exceptions allow the render and are recorded",
            bool(exception_package["coverage_gaps"])
            and exception_package["coverage_exceptions"]
            == exception_text
            and len(exception_package["coverage_exception_records"]) == 1,
        )
        one_line_exception = copy.deepcopy(exception_sheet)
        one_line_exception["tables"]["colors"] = [
            {
                "row_id": "colors.01",
                "values": {"zone": "signal key", "base": "#335577"},
            }
        ]
        one_line_exception["fields"]["field.sheet_coverage_exceptions"] = (
            "One generic sentence must not waive every unrelated gap."
        )
        check(
            "coverage exceptions require one justification per concrete gap",
            expect_error(
                lambda: render_sheet(
                    headless_profile,
                    one_line_exception,
                    sheet_dir=profile_root,
                    mode="scaffold",
                    out_dir=profile_root / "bad-exception-out",
                    profile_path=authored_path,
                ),
                "exactly one nonempty justification line per coverage gap",
            ),
        )

        source_part_profile = copy.deepcopy(authored_profile)
        source_part_profile["rows"][0]["boxes"][0]["kind"] = "items"
        source_part_profile["rows"][0]["boxes"][0]["source_part"] = "wings"
        source_part_context = apply_sheet_context(
            source_part_profile,
            {
                "fields": {},
                "tables": {
                    "parts": [
                        {
                            "row_id": "parts.01",
                            "values": {
                                "part": "wings",
                                "attribute": "three translucent vanes",
                                "laterality": "radial symmetric set",
                                "counterpart_rule": "all three vanes repeat the same structure around the core",
                                "continuity_rule": "preserve the same vane count and shape",
                                "visibility_rule": "must appear whenever the vane set is exposed",
                                "binding": "character-fixed",
                            },
                        }
                    ]
                },
            },
        )
        source_part_box = source_part_context["rows"][0]["boxes"][0]
        check(
            "source_part attributes reach panels even when their kind has its own handler",
            "three translucent vanes" in source_part_box["hint"]
            and source_part_box["binding"] == "character-fixed",
        )
        exact_bound_part_coverage = sheet_coverage(
            {
                "rows": [
                    {
                        "boxes": [
                            {
                                "kind": "part_detail",
                                "source_row_id": "parts.01",
                            }
                        ]
                    }
                ]
            },
            {
                "fields": {},
                "tables": {
                    "parts": [
                        {
                            "row_id": "parts.01",
                            "values": {
                                "part": "shoulders and arms",
                                "attribute": "trained muscular construction",
                            },
                        }
                    ]
                },
            },
        )
        check(
            "a dynamically resolved part panel covers its exact source row",
            not any(
                "declared part" in message
                for message in (
                    exact_bound_part_coverage["gaps"]
                    + exact_bound_part_coverage["warnings"]
                )
            ),
        )
        asymmetric_without_counterpart = {
            "sheet_status": "draft",
            "fields": {
                "field.sheet_coverage_exceptions": (
                    "Coverage prose cannot waive an identity-structure declaration."
                )
            },
            "tables": {
                "parts": [
                    {
                        "row_id": "parts.01",
                        "values": {
                            "part": "left sensor",
                            "attribute": "single cyan aperture",
                            "laterality": "left only",
                            "binding": "individual-fixed",
                        },
                    }
                ]
            },
            "slots": {},
        }
        check(
            "asymmetric parts cannot omit the opposite-side rule or waive it with prose",
            expect_error(
                lambda: render_sheet(
                    general_profile,
                    asymmetric_without_counterpart,
                    sheet_dir=profile_root,
                    mode="scaffold",
                    out_dir=profile_root / "missing-counterpart",
                    profile_path=GENERAL_PROFILE_PATH,
                ),
                "must declare counterpart_rule",
            ),
        )
        fixed_mark_without_visibility = {
            "sheet_status": "draft",
            "fields": {},
            "tables": {
                "marks": [
                    {
                        "row_id": "marks.01",
                        "values": {
                            "mark_id": "left shoulder scar",
                            "landmark_anchor": "left shoulder cap",
                            "shape_path": "short pale diagonal scar",
                            "laterality": "left only",
                            "counterpart_rule": "right shoulder is intact with no scar",
                            "continuity_rule": "same length and angle in every appearance",
                            "binding": "individual-fixed",
                        },
                    }
                ]
            },
            "slots": {},
        }
        check(
            "fixed marks cannot omit the cross-panel visibility and occlusion rule",
            expect_error(
                lambda: render_sheet(
                    general_profile,
                    fixed_mark_without_visibility,
                    sheet_dir=profile_root,
                    mode="scaffold",
                    out_dir=profile_root / "missing-mark-visibility",
                    profile_path=GENERAL_PROFILE_PATH,
                ),
                "must declare visibility_rule",
            ),
        )
        fixed_visual_missing_rules = {
            "parts": {
                "part": "single dorsal sensor",
                "attribute": "one cyan aperture",
                "laterality": "single unpaired",
                "counterpart_rule": "no paired or opposite sensor exists",
                "visibility_rule": "must appear whenever the dorsal surface is exposed",
                "binding": "individual-fixed",
            },
            "items": {
                "item": "left docking key",
                "visual_identity": "one triangular cobalt key",
                "scale_attachment": "fixed to the left docking port",
                "role_rule": "never duplicated",
                "visibility_rule": "must appear whenever the left port is exposed",
                "binding": "individual-fixed",
            },
            "outfits": {
                "outfit": "deployed shell",
                "description": "three overlapping cobalt plates",
                "notes": "covers the dorsal core",
                "visibility_rule": "applies in every deployed-shell panel",
                "binding": "individual-fixed",
            },
            "colors": {
                "zone": "dorsal core",
                "base": "#123456",
                "binding": "individual-fixed",
            },
        }
        check(
            "fixed visual continuity rules apply beyond scars and marks",
            all(
                expect_error(
                    lambda table_id=table_id, values=values: render_sheet(
                        general_profile,
                        {
                            "sheet_status": "draft",
                            "fields": {},
                            "tables": {
                                table_id: [
                                    {"row_id": f"{table_id}.01", "values": values}
                                ]
                            },
                            "slots": {},
                        },
                        sheet_dir=profile_root,
                        mode="scaffold",
                        out_dir=profile_root / f"missing-fixed-{table_id}-rule",
                        profile_path=GENERAL_PROFILE_PATH,
                    ),
                    "must declare continuity_rule"
                    if table_id != "colors"
                    else "must declare visibility_rule",
                )
                for table_id, values in fixed_visual_missing_rules.items()
            ),
        )
        isolated_asymmetry_profile = copy.deepcopy(source_part_profile)
        isolated_asymmetry_sheet = {
            "sheet_status": "draft",
            "fields": {},
            "tables": {
                "parts": [
                    {
                        "row_id": "parts.01",
                        "values": {
                            "part": "wings",
                            "attribute": "one chipped left vane",
                            "laterality": "left only",
                            "counterpart_rule": "the right vane is intact with no chip",
                            "continuity_rule": "preserve the same chipped left vane in every applicable panel",
                            "visibility_rule": "must appear whenever the left vane is exposed",
                            "binding": "individual-fixed",
                        },
                    }
                ]
            },
            "slots": {},
        }
        isolated_asymmetry_render = render_sheet(
            isolated_asymmetry_profile,
            isolated_asymmetry_sheet,
            sheet_dir=profile_root,
            mode="scaffold",
            out_dir=profile_root / "isolated-asymmetry",
            profile_path=authored_path,
        )
        isolated_asymmetry_layout = json.loads(
            isolated_asymmetry_render["layout"].read_text(encoding="utf-8")
        )
        check(
            "asymmetry resolves a feature-versus-counterpart frame instead of relying on an isolated crop",
            any(
                box.get("kind") == "part_detail"
                and box.get("source_row_id") == "parts.01"
                and "paired or opposite-side counterpart" in box.get("hint", "")
                for box in isolated_asymmetry_layout["boxes"]
            ),
        )

        # Declared state rows grow the frame instead of blocking: the renderer
        # clones same-kind panels until every declared table row has a frame,
        # so declarations never have to be trimmed to fit a shipped profile.
        # The humanoid profile satisfies the structural floor (icon, expression
        # panel, palette), so only the state deficits are expanded here.
        state_sheet = {
            "sheet_status": "draft",
            "fields": {},
            "tables": {
                "marks": [
                    gap_sheet["tables"]["marks"][0],
                    {
                        "row_id": "marks.02",
                        "values": {
                            "mark_id": "ear notch",
                            "landmark_anchor": "left ear rim",
                            "shape_path": "v notch",
                            "laterality": "left only",
                            "counterpart_rule": "right ear rim has no notch",
                        },
                    },
                    {
                        "row_id": "marks.03",
                        "values": {
                            "mark_id": "tail tip",
                            "landmark_anchor": "tail tip",
                            "shape_path": "white band",
                            "laterality": "single midline appendage",
                            "counterpart_rule": "there is one tail and no paired counterpart",
                        },
                    },
                    {
                        "row_id": "marks.04",
                        "values": {
                            "mark_id": "collar line",
                            "landmark_anchor": "neck base",
                            "shape_path": "thin ring",
                            "laterality": "centered bilateral ring",
                            "counterpart_rule": "the ring continues evenly around both sides",
                        },
                    },
                ],
                "bodylang": [
                    {
                        "row_id": f"bodylang.{index:02d}",
                        "values": {
                            "state": state,
                            "posture": posture,
                            "gesture": "tail signals the state",
                        },
                    }
                    for index, (state, posture) in enumerate(
                        (
                            ("alert stand", "weight forward, ears raised"),
                            ("crouched prowl", "low carriage, shoulders rolled in"),
                            ("play bow", "forequarters lowered, hindquarters raised"),
                            ("flat warning", "flattened silhouette, ears pinned"),
                            ("open celebration", "upright lift with broad readable gesture"),
                            ("guarded retreat", "weight withdrawn while keeping the subject visible"),
                        ),
                        start=1,
                    )
                ],
                "outfits": [
                    {"row_id": "outfits.01", "values": {"outfit": "travel gear", "description": "cloak and satchel"}},
                    {"row_id": "outfits.02", "values": {"outfit": "formal dress", "description": "long coat"}},
                ],
            },
            "slots": {},
        }
        humanoid_loaded = load_profile(DEFAULT_PROFILE_PATH)
        state_render = render_sheet(
            humanoid_loaded,
            state_sheet,
            sheet_dir=profile_root,
            mode="scaffold",
            out_dir=profile_root / "state-out",
            profile_path=DEFAULT_PROFILE_PATH,
        )
        state_package = json.loads(state_render["package"].read_text(encoding="utf-8"))
        expanded_boxes = [
            box
            for profile_row in state_render["profile"]["rows"]
            for box in profile_row["boxes"]
        ]
        check(
            "declared state rows resolve into panel frames instead of blocking",
            state_package["state_panels"]
            == {"mark_detail": 2, "pose_state": 2, "outfit_turnaround": 4}
            and not state_package["coverage_gaps"]
            and sum(1 for box in expanded_boxes if box["kind"] == "mark_detail") == 4
            and sum(1 for box in expanded_boxes if box["kind"] == "pose_state") == 6
            and sum(1 for box in expanded_boxes if box["kind"] == "outfit_turnaround") == 8,
        )
        check(
            "resolved panels bind to their declared rows and inherit drawing details",
            any(
                box.get("label") == "MARK: TAIL TIP" and "white band" in box["hint"]
                for box in expanded_boxes
            )
            and any(
                box.get("label") == "POSE: FLAT WARNING" and "ears pinned" in box["hint"]
                for box in expanded_boxes
            )
            and len(
                [
                    box
                    for box in expanded_boxes
                    if box.get("source_row_id") == "outfits.02"
                    and box.get("kind") == "outfit_turnaround"
                    and "FORMAL DRESS" in box.get("label", "")
                    and "long coat" in box.get("hint", "")
                ]
            )
            == sum(
                box.get("kind") == "outfit_turnaround"
                and box.get("source_row_id") == "outfits.01"
                for box in expanded_boxes
            ),
        )
        check(
            "resolved panels keep slot ids, output names, and panel codes unique",
            len({box["slot_id"] for box in expanded_boxes}) == len(expanded_boxes)
            and len(
                {
                    box.get("output_name") or box["slot_id"].replace(".", "-") + ".png"
                    for box in expanded_boxes
                }
            )
            == len(expanded_boxes)
            and len({box.get("panel_code") for box in expanded_boxes}) == len(expanded_boxes),
        )
        series_kinds = {"part_state", "range_of_motion", "action_pose", "idle_gesture"}
        series_sheet = {
            "fields": {"identity.name": "Aster", "identity.species_domain": "wolf"},
            "tables": {
                "partstates": [
                    {
                        "row_id": "partstates.01",
                        "values": {
                            "part": "tail",
                            "state": "alert",
                            "configuration": "raised in a high arc, tip curled forward",
                            "read": "attention",
                        },
                    }
                ],
                "motion": [
                    {
                        "row_id": "motion.01",
                        "values": {
                            "region": "ears",
                            "range": "fully forward to fully flattened back",
                            "limit": "no rotation past the skull line",
                            "must_prove": "both ears at each extreme",
                        },
                    }
                ],
                "actions": [
                    {
                        "row_id": "actions.01",
                        "values": {
                            "action": "leap",
                            "phase": "mid-air",
                            "mechanics": "spine extended, forelimbs reaching, tail streaming behind",
                            "kind_channels": "claws out",
                        },
                    }
                ],
                "gestures": [
                    {
                        "row_id": "gestures.01",
                        "values": {
                            "gesture": "grooming a forepaw",
                            "context": "resting after a run",
                            "body": "seated, head lowered to the paw",
                            "props": "",
                        },
                    }
                ],
            },
            "slots": {},
        }
        series_resolved, series_counts = resolve_state_panels(humanoid_loaded, series_sheet)
        series_context = apply_sheet_context(series_resolved, series_sheet)
        series_boxes = [
            box
            for row in series_context["rows"]
            for box in row["boxes"]
            if box["kind"] in series_kinds
        ]
        series_rows = [
            row
            for row in series_context["rows"]
            if any(box["kind"] in series_kinds for box in row["boxes"])
        ]
        check(
            "declared part-state, motion, action, and gesture rows each resolve into a performance panel",
            series_counts
            == {"part_state": 1, "range_of_motion": 1, "action_pose": 1, "idle_gesture": 1}
            and all(box.get("reference_role") == "performance" for box in series_boxes),
            str(series_counts),
        )
        check(
            "resolved performance panels carry the declared row's title and details",
            any(box.get("label") == "TAIL: ALERT" and "tip curled forward" in box["hint"] for box in series_boxes)
            and any(box.get("label") == "RANGE: EARS" and "flattened" in box["hint"] for box in series_boxes)
            and any(box.get("label") == "ACTION: LEAP" and "spine extended" in box["hint"] for box in series_boxes)
            and any(
                box.get("label") == "GESTURE: GROOMING A FOREPAW" and "head lowered" in box["hint"]
                for box in series_boxes
            ),
            str([(box.get("label"), box.get("hint", "")[:60]) for box in series_boxes]),
        )
        check(
            "resolved panels take one labeled section per kind at the resolved row height",
            [row.get("section_label") for row in series_rows]
            == ["PART STATES", "RANGE OF MOTION", "ACTION POSES", "EVERYDAY GESTURES"]
            and all(
                int(row["height"]) - SECTION_HEADER_HEIGHT == RESOLVED_ROW_HEIGHT for row in series_rows
            ),
            str([(row.get("section_label"), row["height"]) for row in series_rows]),
        )
        series_tables = ("partstates", "motion", "actions", "gestures")
        series_coverage = sheet_coverage(series_resolved, series_sheet)
        unresolved_series_coverage = sheet_coverage(humanoid_loaded, series_sheet)
        check(
            "performance rows are coverage gaps until they resolve into panels",
            not [gap for gap in series_coverage["gaps"] if gap.split(" ", 1)[0] in series_tables]
            and sum(
                1 for gap in unresolved_series_coverage["gaps"] if gap.split(" ", 1)[0] in series_tables
            )
            == 4,
            str(unresolved_series_coverage["gaps"]),
        )
        no_change, no_change_counts = resolve_state_panels(
            humanoid_loaded, {"fields": {}, "tables": {"expressions": expression_sheet["tables"]["expressions"][:2]}, "slots": {}}
        )
        check(
            "declared rows already covered by the profile resolve nothing",
            no_change_counts == {},
        )
        humanoid_resolved, humanoid_counts = resolve_state_panels(
            humanoid_loaded,
            {
                "fields": {},
                "tables": {
                    "expressions": expression_sheet["tables"]["expressions"]
                    + [
                        {"row_id": "expressions.03", "values": {"state": "flat stare"}},
                        {"row_id": "expressions.04", "values": {"state": "wide grin"}},
                        {"row_id": "expressions.05", "values": {"state": "sleepy blink"}},
                        {"row_id": "expressions.06", "values": {"state": "cold focus"}},
                        {"row_id": "expressions.07", "values": {"state": "open delight"}},
                        {"row_id": "expressions.08", "values": {"state": "contained grief"}},
                    ]
                },
                "slots": {},
            },
        )
        humanoid_expression_boxes = [
            box
            for profile_row in humanoid_resolved["rows"]
            for box in profile_row["boxes"]
            if box["kind"] == "expression_variant"
        ]
        check(
            "expression rows beyond the starter band resolve without a fixed total",
            humanoid_counts == {"expression_variant": 2}
            and len(humanoid_expression_boxes) == 8
            and [box["slot_id"] for box in humanoid_expression_boxes[6:]]
            == ["expressions.ex.07", "expressions.ex.08"]
            and [box["panel_code"] for box in humanoid_expression_boxes[6:]] == ["F7", "F8"]
            # Dedicated last row, never squeezed into the authored F row, and
            # the resolved panels keep a drawing-friendly width (columns, not
            # wider panels).
            and len(humanoid_resolved["rows"][-1]["boxes"]) == 2
            and humanoid_resolved["rows"][-1]["height"] - SECTION_HEADER_HEIGHT == RESOLVED_ROW_HEIGHT
            and humanoid_resolved["rows"][-1].get("section_label") == "DECLARED EXPRESSIONS"
            and humanoid_resolved["canvas"][1] >= humanoid_loaded["canvas"][1],
        )
        # Resolved expression panels are square head-and-shoulders frames:
        # their width follows their kind's shape, not the row's even split.
        resolved_panel_w = desired_panel_width(
            humanoid_resolved["rows"][-1]["boxes"][0], 560
        )
        check(
            "resolved panels keep a drawing-friendly panel width",
            400 <= resolved_panel_w <= 900 and len(humanoid_resolved["rows"][-1]["boxes"]) == 2,
        )
        # Every rendered panel must show its complete header and its complete
        # model-facing instruction; a clipped word in one footer is a word the
        # image model never receives.
        rendered_layout = json.loads(state_render["layout"].read_text(encoding="utf-8"))
        pose_layouts = {"humanoid": (rendered_layout, state_render)}
        for pose_profile_path in (ANTHRO_PROFILE_PATH, GENERAL_PROFILE_PATH):
            pose_profile = load_profile(pose_profile_path)
            pose_render = render_sheet(
                pose_profile,
                state_sheet,
                sheet_dir=profile_root,
                mode="scaffold",
                out_dir=profile_root / f"pose-geometry-{pose_profile['id']}",
                profile_path=pose_profile_path,
            )
            pose_layouts[pose_profile["id"]] = (
                json.loads(pose_render["layout"].read_text(encoding="utf-8")),
                pose_render,
            )
        pose_geometry_details = [
            {
                "profile": profile_id,
                "panel_code": box["panel_code"],
                "content_w": box["content_w"],
                "content_h": box["content_h"],
            }
            for profile_id, (layout, _render) in pose_layouts.items()
            for box in layout["boxes"]
            if box["kind"] == "pose_state"
        ]
        check(
            "every bundled profile gives authored and resolved pose panels a full-figure portrait area and prompt guard",
            bool(pose_geometry_details)
            and all(
                row["content_h"] / row["content_w"] >= 1.45
                for row in pose_geometry_details
            )
            and all(
                all(
                    "Do not bend, crouch, compress, crop" in prompt_text
                    for request, prompt_text in panel_prompts(render)
                    if request["kind"] == "pose_state"
                )
                for _layout, render in pose_layouts.values()
            ),
            pose_geometry_details,
        )
        truncated: list[str] = []
        for layout_box in rendered_layout["boxes"]:
            width_px = layout_box["w"] - 24
            title = " ".join(
                value
                for value in (layout_box.get("panel_code"), layout_box["label"])
                if value
            )
            title_size = fit_title_size(title, width_px, 23 if layout_box["w"] >= 360 else 19)
            if len(title) * title_size * 0.62 > width_px:
                truncated.append(f"{layout_box['panel_code']} title")
            if layout_box["fill_state"] == "skip":
                continue
            hint_size = 15 if layout_box["w"] >= 360 else 14
            _, hint_lines, _ = fit_wrapped_text(
                layout_box["hint"],
                width_px=width_px,
                base_size=hint_size,
                available_height=layout_box["footer_height"] - 6,
            )
            if " ".join(hint_lines) != " ".join(layout_box["hint"].split()):
                truncated.append(f"{layout_box['panel_code']} hint")
        check(
            "every rendered panel shows its full header and instruction",
            not truncated,
            truncated,
        )

    check(
        "empty placeholder images are not exported as committed paths",
        "image_path:state.imagePath" in html and "naturalWidth" not in html,
    )
    check(
        "mark rows expose stable columns matching their headers",
        all(
            f'data-column-id="{column}"' in html
            for column in (
                "mark_id",
                "landmark_anchor",
                "shape_path",
                "laterality",
                "counterpart_rule",
                "continuity_rule",
                "visibility_rule",
                "binding",
            )
        ),
    )
    check("marks are optional rather than a completion requirement", "At least one mark anchors" not in html)
    check(
        "palette zones are optional rather than a completion requirement",
        "at least one complete zone anchors" not in html,
    )
    check(
        "view rows have round-trip image artifact slots without a fixed card total",
        'id="viewPanelEditors"' in html
        and 'id="outfitPanelEditors"' in html
        and "ensureSlotEditor(baseSlot" in html
        and "ensureSlotEditor(outfitSlot" in html,
    )
    check(
        "kind override headers and semantic columns agree",
        all(
            f'data-column-id="{column}"' in html
            for column in ("attribute", "baseline", "override", "reason", "binding")
        )
        and "Why it matters</th><th" in html,
    )
    check(
        "template explains the render harvest and reference-board loop",
        "Export sheet-data.json" in html
        and "exact panel-only requests" in html
        and "Never send the full sheet" in html
        and "Harvest the returned sheet as candidates" in html
        and "reference board" in html,
    )

    kind_rule_profile = {"id": "kind-rule-probe", "title": "Kind rule probe"}

    def kind_rule_box(
        kind: str, slot_id: str, source_row_id: str, binding: str = "individual-fixed"
    ) -> dict[str, Any]:
        return {
            "slot_id": slot_id,
            "resolved_slot_id": slot_id,
            "panel_code": slot_id.upper(),
            "label": kind.upper(),
            "kind": kind,
            "fill_state": "fill",
            "hint": KIND_DRAW_GUIDE[kind],
            "source_row_id": source_row_id,
            "binding": binding,
        }

    mark_rows = [
        {"row_id": "marks.01", "values": {"mark_id": "marks.01", "binding": "individual-fixed"}}
    ]
    single_mark_sheet = {
        "sheet_status": "draft",
        "fields": {},
        "tables": {"marks": mark_rows},
        "slots": {},
    }
    single_mark_prompt = build_fill_prompt(
        kind_rule_profile,
        single_mark_sheet,
        [{"boxes": [kind_rule_box("mark_detail", "d1", "marks.01")]}],
    )
    check(
        "a single named panel kind still states the rule it names",
        KIND_DRAW_GUIDE["mark_detail"] in single_mark_prompt,
        single_mark_prompt.splitlines()[-4:],
    )
    check(
        "a named panel kind keeps the short plan-line reference",
        "Use mark_detail rule" in single_mark_prompt,
        [line for line in single_mark_prompt.splitlines() if line.startswith("- D1")],
    )

    evidence_sheet = {
        "sheet_status": "draft",
        "fields": {},
        "tables": {
            "marks": mark_rows,
            "evidence": [
                {
                    "row_id": "evidence.01",
                    "values": {
                        "subject_table": "marks",
                        "subject_row_id": "marks.01",
                        "view_id": "v1",
                        "orientation_configuration": "front",
                        "specification": "close-up",
                    },
                }
            ],
        },
        "slots": {},
    }
    evidence_prompt = build_fill_prompt(
        kind_rule_profile,
        evidence_sheet,
        [{"boxes": [kind_rule_box("evidence_view", "e1", "evidence.01")]}],
    )
    check(
        "a single evidence_view panel states the rule it names",
        KIND_DRAW_GUIDE["evidence_view"] in evidence_prompt
        and "Use evidence_view rule" in evidence_prompt,
        evidence_prompt.splitlines()[-4:],
    )

    repeated_mark_sheet = {
        "sheet_status": "draft",
        "fields": {},
        "tables": {
            "marks": mark_rows
            + [
                {
                    "row_id": "marks.02",
                    "values": {"mark_id": "marks.02", "binding": "individual-fixed"},
                }
            ]
        },
        "slots": {},
    }
    repeated_mark_prompt = build_fill_prompt(
        kind_rule_profile,
        repeated_mark_sheet,
        [
            {
                "boxes": [
                    kind_rule_box("mark_detail", "d1", "marks.01"),
                    kind_rule_box("mark_detail", "d2", "marks.02"),
                ]
            }
        ],
    )
    check(
        "a repeated panel kind states its rule exactly once",
        repeated_mark_prompt.count("- mark_detail: ") == 1
        and KIND_DRAW_GUIDE["mark_detail"] in repeated_mark_prompt,
        repeated_mark_prompt.count("- mark_detail: "),
    )

    with tempfile.TemporaryDirectory(prefix="cpb-sheet-containment-") as containment_raw:
        containment_root = Path(containment_raw)
        (containment_root / "outside.png").write_bytes(b"outside")
        containment_sheet = containment_root / "sheet"
        containment_sheet.mkdir()
        (containment_sheet / "inside.png").write_bytes(b"inside")
        containment_box = {"slot_id": "canon.primary", "aliases": []}

        def containment_slot_image(stored: str) -> Any:
            (containment_sheet / "sheet-data.json").write_text(
                json.dumps(
                    {
                        "sheet_status": "draft",
                        "fields": {},
                        "tables": {},
                        "slots": {
                            "canon.primary": {
                                "image_path": stored,
                                "generation_package": "",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            sheet_value, _ = load_sheet(containment_sheet)
            return slot_image(sheet_value, containment_box, containment_sheet)

        escapes = {
            "parent segment": "../outside.png",
            "absolute path": (containment_root / "outside.png").resolve().as_posix(),
            "backslash separator": "sheet\\inside.png",
        }
        escape_details: dict[str, str] = {}
        for label, stored in escapes.items():
            try:
                containment_slot_image(stored)
            except ValueError as exc:
                escape_details[label] = str(exc)
            except Exception as exc:  # noqa: BLE001 - reported as a failure below
                escape_details[label] = f"{type(exc).__name__}: {exc}"
        check(
            "slot_image refuses image paths that leave the sheet folder",
            sorted(escape_details) == sorted(escapes)
            and all("image_path" in text for text in escape_details.values()),
            escape_details,
        )

        inside_result = containment_slot_image("inside.png")
        check(
            "slot_image still resolves an image inside the sheet folder",
            inside_result[2] == "inside.png"
            and inside_result[3] == (containment_sheet / "inside.png").resolve(),
            [inside_result[2], str(inside_result[3])],
        )
        empty_result = containment_slot_image("")
        check(
            "slot_image leaves an undeclared image unresolved",
            empty_result[2] == "" and empty_result[3] is None,
            [empty_result[2], empty_result[3]],
        )
        missing_detail = ""
        try:
            containment_slot_image("missing.png")
        except ValueError as exc:
            missing_detail = str(exc)
        check(
            "slot_image keeps the missing-image diagnostic",
            missing_detail == "slot canon.primary image does not exist: missing.png",
            missing_detail,
        )

        symlink_detail: Any = "symbolic links are not creatable here"
        symlink_refused = True
        link = containment_sheet / "link.png"
        try:
            link.symlink_to(containment_root / "outside.png")
        except (OSError, NotImplementedError) as exc:
            symlink_detail = f"skipped: {type(exc).__name__}: {exc}"
        else:
            symlink_refused = False
            try:
                containment_slot_image("link.png")
            except ValueError as exc:
                symlink_detail = str(exc)
                symlink_refused = "image_path" in symlink_detail
        check(
            "slot_image refuses a symbolic link that leaves the sheet folder",
            symlink_refused,
            symlink_detail,
        )

    report = {
        "ok": len(results) == EXPECTED_CHECKS and all(row["passed"] for row in results),
        "checks": len(results),
        "expected_checks": EXPECTED_CHECKS,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
