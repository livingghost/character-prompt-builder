"""Selected sheet views survive prompt construction and panel geometry.

The fixtures are synthetic. These checks cover the emitted drawing request,
retained identity source and layout, not the quality of a generated picture.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import character_sheet_render.board as board
from character_sheet_render.board import build_sheet_plan, publish_sheet
import compose_sheet_panel_fills as compose
from harvest_sheet_render import protected_region_mask
from character_sheet_render.profiles import (
    BORDER, DEFAULT_FOOTER_HEIGHT, HEADER_HEIGHT, PROFILE_SCHEMA_PATH,
    SIDE_MARGIN, desired_panel_width, fill_rows_to_width, row_natural_width,
)
from character_sheet_render.prompts import build_fill_prompt
from character_sheet_render.resolution import apply_sheet_context, resolve_state_panels
from character_sheet_render.textmetrics import build_raster_text_layer, segment_text_by_font
from state_protocol import validate_against_schema


PARTIAL_VIEW = (
    "Three-quarter view of the head and upper coils. The continuous trunk turns "
    "through the lower edge of the frame, with its near coil overlapping the far coil."
)
WHOLE_VIEW = "Complete extended figure in lateral view, with the head and tail tip inside the frame."
IDENTITY = (
    "A blue glass serpent with three small ridges above its single eye, one continuous "
    "trunk, and two short fins near the tail. A pale spiral line runs from the neck "
    "to the tail tip, passing behind each overlapping coil."
)


def panel(slot: str, kind: str, hint: str, **extra):
    return {"slot_id": slot, "label": slot.upper(), "output_name": slot + ".png",
            "kind": kind, "hint": hint, **extra}


def view_sheet():
    return {
        "fields": {"identity.name": "Glass Serpent",
                   "field.model_fill_visual_design_brief": IDENTITY,
                   "field.base_form_visual_description": "The adopted continuous blue glass construction.",
                   "field.reference_sheet_visual_finish": "Clear line and transparent color."},
        "tables": {"views": [
            {"row_id": "views.01", "values": {
                "view_id": "upper-turn", "label": "Upper turn", "specification": PARTIAL_VIEW,
                "must_prove": "The ridges, eye, neck and overlapping continuous coils."}},
            {"row_id": "views.02", "values": {
                "view_id": "extended", "label": "Extended side", "specification": WHOLE_VIEW,
                "must_prove": "The full length and fin placement."}},
        ]},
        "slots": {},
    }


def view_profile():
    return {
        "id": "synthetic-views", "title": "Synthetic view study", "canvas": [3000, 4800],
        "header_fields": [{"field_id": "identity.name", "label": "Name"}],
        "rows": [
            {"height": 500, "boxes": [
                panel("base.default", "canonical_view", "Complete default view.",
                      aspect_ratio=0.5, source_view_row_id="views.02"),
                panel("base.wide", "canonical_view", "An older profile drawing instruction.",
                      aspect_ratio=2, source_view_row_id="views.01"),
            ]},
            {"height": 500, "boxes": [
                panel("outfit.default", "outfit_turnaround", "Complete default outfit view.",
                      aspect_ratio=0.75),
                panel("outfit.wide", "outfit_turnaround", "An older outfit drawing instruction.",
                      aspect_ratio=1.5, source_view_row_id="views.01"),
            ]},
            {"height": 400, "boxes": [
                panel("identity.icon", "icon", "Study of the eye and its three ridges.")
            ]},
        ],
    }


class SheetDrawingScopeTests(unittest.TestCase):
    def test_partial_depiction_leads_and_complete_identity_remains_context(self):
        box = panel("view.partial", "canonical_view", PARTIAL_VIEW, fill_state="fill")
        prompt = build_fill_prompt({}, view_sheet(), [{"boxes": [box]}],
                                   target_slot_id=box["slot_id"], target_content_size=(2048, 1024))
        self.assertIn("2048 by 1024", prompt)
        self.assertIn(PARTIAL_VIEW, prompt)
        self.assertIn("Character design: " + IDENTITY, prompt)
        self.assertLess(prompt.index(PARTIAL_VIEW), prompt.index("Identity and rendering sources:"))
        self.assertIn("connected construction coherent through overlap and the frame edges", prompt)
        self.assertNotIn("complete described subject filling the frame", prompt)
        self.assertNotIn("complete unobstructed base form", prompt)

    def test_complete_extent_is_preserved_when_the_view_selects_it(self):
        box = panel("view.whole", "canonical_view", WHOLE_VIEW, fill_state="fill")
        prompt = build_fill_prompt({}, view_sheet(), [{"boxes": [box]}],
                                   target_slot_id=box["slot_id"], target_content_size=(1024, 2048))
        self.assertIn(WHOLE_VIEW, prompt)
        self.assertLess(prompt.index(WHOLE_VIEW), prompt.index("Character design:"))

    def test_masked_sheet_retains_independent_view_scopes(self):
        boxes = [panel("upper", "canonical_view", PARTIAL_VIEW, fill_state="fill", panel_code="A1"),
                 panel("side", "canonical_view", WHOLE_VIEW, fill_state="fill", panel_code="A2")]
        prompt = build_fill_prompt({}, view_sheet(), [{"boxes": boxes}])
        self.assertIn("- A1 UPPER: " + PARTIAL_VIEW, prompt)
        self.assertIn("- A2 SIDE: " + WHOLE_VIEW, prompt)
        self.assertLess(prompt.index(WHOLE_VIEW), prompt.index("Character design:"))
        self.assertNotIn("complete described subject filling the frame", prompt)

    def test_pose_context_retains_the_authored_view_and_adds_the_declared_state(self):
        hint = "Wide view of the upper coils and their contact with a stone ledge."
        profile = {"rows": [{"boxes": [panel("pose.01", "pose_state", hint,
                                              source_row_id="bodylang.01")]}]}
        sheet = view_sheet()
        sheet["tables"]["bodylang"] = [{"row_id": "bodylang.01", "values": {
            "state": "watching", "posture": "The near coil rests on the ledge.",
            "gesture": "The head turns toward the opening.",
            "kind_channels": "The eye narrows slightly.", "distance_orientation": "Viewed from above."}}]
        box = apply_sheet_context(profile, sheet)["rows"][0]["boxes"][0]
        self.assertTrue(box["hint"].startswith(hint))
        self.assertIn("The near coil rests on the ledge.", box["hint"])
        box["fill_state"] = "fill"
        prompt = build_fill_prompt(profile, sheet, [{"boxes": [box]}], target_slot_id="pose.01")
        self.assertIn(box["hint"], prompt)
        self.assertNotIn("Do not bend, crouch, compress, crop", prompt)

    def test_declared_views_replace_drawing_defaults_and_select_matching_geometry(self):
        sheet = view_sheet()
        sheet["tables"]["outfits"] = [{"row_id": "outfits.01", "values": {
            "outfit": "Copper harness", "description": "Two copper bands connected along the upper trunk."}}]
        resolved, counts = resolve_state_panels(view_profile(), sheet)
        boxes = [box for row in resolved["rows"] for box in row["boxes"]]
        by_view = {(box["kind"], box.get("source_view_row_id")): box for box in boxes
                   if box["kind"] in {"canonical_view", "outfit_turnaround"}}
        self.assertEqual(counts["canonical_view"], 2)
        self.assertEqual(counts["outfit_turnaround"], 2)
        for kind, partial_aspect, whole_aspect in (
            ("canonical_view", 2, 0.5), ("outfit_turnaround", 1.5, 0.75)
        ):
            with self.subTest(kind=kind):
                partial, whole = by_view[(kind, "views.01")], by_view[(kind, "views.02")]
                self.assertEqual(partial["hint"], PARTIAL_VIEW)
                self.assertEqual(whole["hint"], WHOLE_VIEW)
                self.assertEqual(partial["aspect_ratio"], partial_aspect)
                self.assertEqual(whole["aspect_ratio"], whole_aspect)

    def test_optional_aspect_uses_interior_geometry_without_overflow_when_rows_grow(self):
        profile = view_profile()
        schema = json.loads(PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(validate_against_schema(profile, schema), [])
        for invalid in (0, -1, True, "wide"):
            candidate = copy.deepcopy(profile)
            candidate["rows"][0]["boxes"][0]["aspect_ratio"] = invalid
            self.assertTrue(validate_against_schema(candidate, schema), repr(invalid))
        rows = copy.deepcopy(profile["rows"][:1])
        fill_rows_to_width(rows, 2200)
        self.assertLessEqual(row_natural_width(rows[0]), 2200 - SIDE_MARGIN * 2)
        height = rows[0]["height"]
        interior_height = height - HEADER_HEIGHT - DEFAULT_FOOTER_HEIGHT - BORDER * 2
        for box in rows[0]["boxes"]:
            self.assertAlmostEqual((desired_panel_width(box, height) - BORDER * 2) / interior_height,
                                   box["aspect_ratio"], delta=1 / interior_height)
        default = panel("default", "canonical_view", "The selected view.")
        self.assertEqual(desired_panel_width(default, 500), 350)

    def test_rendered_requests_consume_the_selected_view_geometry(self):
        profile, sheet = view_profile(), view_sheet()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = build_sheet_plan(profile, sheet, sheet_dir=root, mode="scaffold",
                                    panel_geometries=[(1024, 2048), (2048, 1024), (1024, 1024)])
            metadata = copy.deepcopy(plan.package_metadata)
            planned_requests = copy.deepcopy(plan.panel_requests)
            profile["title"] = "A later input edit"
            sheet["fields"]["identity.name"] = "A later character edit"
            with mock.patch.object(board, 'build_sheet_plan', side_effect=AssertionError('Plan rebuilt during publication')):
                result = publish_sheet(plan, out_dir=root / "render")
            layout = json.loads(Path(result["layout"]).read_text(encoding="utf-8"))
            request_path = Path(result["panel_requests"])
            manifest = json.loads(request_path.read_text(encoding="utf-8"))
            requests = manifest["requests"]
            self.assertEqual(layout, {**plan.layout, "raster_text": None})
            package = json.loads(Path(result["package"]).read_text(encoding="utf-8"))
            published_metadata = {key: copy.deepcopy(package[key]) for key in metadata}
            published_metadata["fill_transport"].pop("panel_requests_sha256")
            self.assertEqual(published_metadata, metadata)
            for key in ('scaffold', 'layout'):
                companion = request_path.parent / manifest[key]["path"]
                self.assertEqual(manifest[key]["sha256"], hashlib.sha256(companion.read_bytes()).hexdigest())
            self.assertEqual(package["png_sha256"], manifest["scaffold"]["sha256"])
            self.assertEqual(package["fill_transport"]["panel_requests_sha256"],
                             hashlib.sha256(request_path.read_bytes()).hexdigest())
            for request, planned in zip(requests, planned_requests["requests"], strict=True):
                prompt_path = request_path.parent / request["prompt"]["path"]
                self.assertEqual(prompt_path.read_text(encoding="utf-8"), planned["prompt"])
                self.assertEqual(request["prompt"]["sha256"], hashlib.sha256(prompt_path.read_bytes()).hexdigest())
                self.assertEqual({key:value for key,value in request.items() if key != 'prompt'},
                                 {key:value for key,value in planned.items() if key != 'prompt'})
            self.assertEqual(plan.package_metadata, metadata)
            self.assertEqual(plan.panel_requests, planned_requests)
            for view_id, aspect, selected_text, geometry in (
                ("views.01", 2, PARTIAL_VIEW, (2048, 1024)),
                ("views.02", 0.5, WHOLE_VIEW, (1024, 2048)),
            ):
                box = next(box for box in layout["boxes"]
                           if box["kind"] == "canonical_view" and box["source_view_row_id"] == view_id)
                self.assertAlmostEqual(box["content_w"] / box["content_h"], aspect,
                                       delta=1 / box["content_h"])
                self.assertLessEqual(box["x"] + box["w"], layout["canvas"]["w"] - SIDE_MARGIN)
                request = next(row for row in requests if row["slot_id"] == box["slot_id"])
                self.assertEqual((request["target"]["generation_w"], request["target"]["generation_h"]), geometry)
                prompt = (request_path.parent / request["prompt"]["path"]).read_text(encoding="utf-8")
                self.assertIn(selected_text, prompt)
                self.assertIn(IDENTITY, prompt)
                self.assertNotIn("An older profile drawing instruction.", prompt)

            from PIL import Image
            results = root / 'results'
            results.mkdir()
            Image.new('RGB', (8, 8), '#345678').save(results / requests[0]['result_file'])
            with mock.patch.object(compose.Image, 'open', side_effect=AssertionError('Rejected composition decoded an image')):
                with self.assertRaisesRegex(ValueError, 'panel result is missing'):
                    compose.compose_panel_fills(request_path, results, out_path=root/'missing.png')
            for request in requests[1:]:
                Image.new('RGB', (8, 8), '#345678').save(results / request['result_file'])
            sidecar = root / 'sheet-data.json'
            sidecar.write_text(json.dumps({'sheet_status':'draft', **view_sheet()}), encoding='utf-8')
            before_sidecar = sidecar.read_bytes()
            with mock.patch.object(compose.Image, 'open', side_effect=AssertionError('Rejected scope decoded an image')):
                with self.assertRaisesRegex(ValueError, 'slots without a panel request'):
                    compose.compose_panel_fills(request_path, results, out_path=root/'unknown.png',
                                                register_sidecar_path=sidecar, only=['unknown-slot'])
            self.assertEqual(sidecar.read_bytes(), before_sidecar)
            self.assertFalse((root/'missing.png').exists())
            self.assertFalse((root/'unknown.png').exists())

    def test_planning_owns_its_text_and_geometry_without_publishing(self):
        profile, sheet = view_profile(), view_sheet()
        sheet["fields"]["identity.name"] = "見本"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(board, 'rasterize_board', side_effect=AssertionError('Unexpected rasterization')), \
                    mock.patch.object(board, 'build_raster_text_layer', side_effect=AssertionError('Unexpected text rasterization')), \
                    mock.patch.object(board, 'create_edit_mask', side_effect=AssertionError('Unexpected mask publication')):
                first = build_sheet_plan(profile, sheet, sheet_dir=root, mode="scaffold")
                layout, drawing = copy.deepcopy(first.layout), list(first.drawing)
                overlays = copy.deepcopy(first.drawing.text_overlays)
                sheet["fields"]["identity.name"] = "Second character"
                profile["title"] = "Second sheet"
                second = build_sheet_plan(profile, sheet, sheet_dir=root, mode="scaffold")
            self.assertEqual(list(root.iterdir()), [])
            self.assertTrue(any(row['text'] == '見本' for row in overlays))
            self.assertEqual(first.drawing.text_overlays, overlays)
            self.assertEqual(first.drawing, drawing)
            self.assertEqual(first.layout, layout)
            self.assertEqual(second.drawing.text_overlays, [])
            self.assertNotEqual(first.drawing, second.drawing)

    def test_bounded_text_preserves_fractional_positions_overlap_and_board_clipping(self):
        from PIL import Image, ImageDraw, ImageFont
        text = "見本"
        width, height = 240, 160
        overlays = [
            {"text": text, "x": x, "y": y, "size": 22, "anchor": anchor,
             "font_role": "regular", "weight": "400", "fill": fill}
            for x, y, anchor, fill in [
                (5.25, 20.5, "start", "#26221c"),
                (17.5, 21.5, "start", "#cc3300"),
                (-7.75, 80.25, "start", "#26221c"),
                (231.5, 160.5, "end", "#26221c"),
                (100.25, 120.5, "middle", "#26221c"),
            ]
        ]
        expected = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(expected)
        for overlay in overlays:
            runs = [(ImageFont.truetype(str(path), overlay['size']), segment)
                    for path, segment in segment_text_by_font(overlay['font_role'], overlay['text'])]
            advances = [font.getlength(segment) for font, segment in runs]
            x = overlay['x']
            if overlay['anchor'] == 'end':
                x -= sum(advances)
            elif overlay['anchor'] == 'middle':
                x -= sum(advances) / 2
            for (font, segment), advance in zip(runs, advances):
                draw.text((x, overlay['y']), segment, font=font, fill=overlay['fill'], anchor='ls')
                x += advance
        layers, manifest = build_raster_text_layer(width=width, height=height, overlays=overlays)
        actual = Image.new("RGBA", (width, height))
        for index, layer in enumerate(layers):
            self.assertGreaterEqual(layer['x'], 0)
            self.assertGreaterEqual(layer['y'], 0)
            self.assertLessEqual(layer['x'] + layer['width'], width)
            self.assertLessEqual(layer['y'] + layer['height'], height)
            for other in layers[:index]:
                self.assertFalse(layer['x'] < other['x'] + other['width']
                                 and other['x'] < layer['x'] + layer['width']
                                 and layer['y'] < other['y'] + other['height']
                                 and other['y'] < layer['y'] + layer['height'])
            with Image.open(io.BytesIO(base64.b64decode(layer['uri'].split(',', 1)[1]))) as region:
                actual.paste(region, (layer['x'], layer['y']))
        self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertIsNotNone(actual.getbbox())
        self.assertEqual(len(manifest['overlays']), len(overlays))
        self.assertLess(sum(layer['width'] * layer['height'] for layer in layers), width * height // 2)
        self.assertEqual(build_raster_text_layer(width=width, height=height, overlays=overlays), (layers, manifest))

    def test_protected_region_guard_uses_threshold_and_clips_each_board_edge(self):
        from PIL import Image
        width, height = 13, 9
        values = bytes(128 if (x, y) in {(0, 0), (12, 8), (0, 6), (6, 4)} else 127
                       for y in range(height) for x in range(width))
        for width, height, pixels in [(1, 1, b'\x00'), (1, 1, b'\x80'),
                                     (2, 3, bytes([0, 127, 0, 0, 128, 0])), (width, height, values)]:
            with self.subTest(width=width, height=height, pixels=pixels):
                mask = Image.frombytes('L', (width, height), pixels)
                actual = protected_region_mask(mask)
                expected = bytes(
                    0 if any(pixels[neighbor_y * width + neighbor_x] >= 128
                             for neighbor_y in range(max(0, y - 2), min(height, y + 3))
                             for neighbor_x in range(max(0, x - 2), min(width, x + 3))) else 255
                    for y in range(height) for x in range(width)
                )
                self.assertEqual(actual.mode, 'L')
                self.assertEqual(actual.size, (width, height))
                self.assertEqual(actual.tobytes(), expected)
                self.assertEqual(mask.tobytes(), pixels)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
