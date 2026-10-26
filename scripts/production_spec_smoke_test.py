#!/usr/bin/env python3
"""Exercise shared identity, local depiction and sealed artifact layout handoff."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import production_spec
from build_asset_render_spec import build_render_spec
from growth_resolution_smoke_test import graph_fixture, relink
from render_contract_fixtures import intent
from state_protocol import artifact_hash, load_json, validate_state_artifact_graph


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "composed-artifact"


def layout(name: str) -> dict:
    return load_json(EXAMPLES / (name + "-layout.json"))


def drafted(subject: str = "mechanic", selected_layout: dict | None = None) -> dict:
    return production_spec.draft(
        model="synthetic-image-model", brief="A blue robot inspects a brass latch.",
        subject=subject, kind="robot", render_intent=intent("Clean blue forms in warm workshop light."),
        layout=selected_layout,
    )


class ProductionSpecificationTests(unittest.TestCase):
    def assert_valid(self, spec):
        report = production_spec.validate(spec, require_content=True)
        self.assertTrue(report["ok"], report["errors"])

    def test_simple_depiction_uses_the_small_draft(self):
        spec = drafted()
        self.assert_valid(spec)
        self.assertNotIn("layout", spec)
        self.assertNotIn("camera", spec)
        self.assertEqual(1, len(spec["subjects"]))

    def test_repeated_subject_keeps_independent_local_visibility(self):
        selected = layout("inspection")
        original = copy.deepcopy(selected)
        spec = drafted(selected_layout=selected)
        self.assert_valid(spec)
        self.assertEqual(original, spec["layout"])
        self.assertEqual(["mechanic"], [subject["id"] for subject in spec["subjects"]])
        first, _, last = spec["layout"]["regions"]
        self.assertEqual(["front display"], first["subjects"][0]["occluded_elements"])
        self.assertEqual(["front display", "blue display bezel"], last["subjects"][0]["visible_elements"])
        selected["regions"][0]["depiction"] = "A different authored view."
        self.assertEqual(original, spec["layout"])

    def test_authored_sequence_keeps_local_states_and_time_relationship(self):
        selected = layout("sequence")
        spec = drafted("courier", selected)
        self.assert_valid(spec)
        self.assertEqual({}, spec["subjects"][0]["current_state"])
        self.assertEqual(["reach", "carry"], spec["layout"]["reading_order"])
        self.assertEqual(selected["relationships"], spec["layout"]["relationships"])
        self.assertEqual(
            [{"parcel": "resting on the shelf"}, {"parcel": "held in both grippers"}],
            [region["subjects"][0]["current_state"] for region in spec["layout"]["regions"]],
        )

    def test_flat_poster_requires_neither_camera_nor_character(self):
        spec = drafted()
        spec["subjects"] = []
        spec["source_brief"] = spec["image_promise"] = "A geometric poster about movement."
        spec["layout"] = layout("poster")
        self.assert_valid(spec)
        self.assertEqual([], spec["subjects"])
        self.assertTrue(all("camera" not in region and "subjects" not in region
                            for region in spec["layout"]["regions"]))

    def test_region_camera_is_a_complete_local_contract(self):
        spec = drafted(selected_layout=layout("inspection"))
        camera = load_json(ROOT / "examples/declared-structures/reference-camera.json")
        spec["layout"]["regions"][1]["camera"] = camera
        self.assert_valid(spec)
        spec["layout"]["regions"][1]["camera"]["pitch_degrees"] = 100
        report = production_spec.validate(spec)
        self.assertFalse(report["ok"])
        self.assertTrue(any("$.layout.regions[1].camera.pitch_degrees" in error for error in report["errors"]))

    def test_layout_identifiers_resolve_within_the_artifact(self):
        cases = [
            (lambda value: value["regions"][1].update(id="workshop"), "duplicate region id"),
            (lambda value: value["regions"][0]["subjects"][0].update(subject_id="unknown"), "unknown subject id"),
            (lambda value: value.update(reading_order=["missing"]), "unknown region id"),
            (lambda value: value.update(reading_order=["workshop", "latch", "workshop"]), "array items are not unique"),
            (lambda value: value["relationships"][0].update(to="missing"), "unknown region id"),
        ]
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                spec = drafted(selected_layout=layout("inspection"))
                mutate(spec["layout"])
                report = production_spec.validate(spec)
                self.assertFalse(report["ok"])
                self.assertTrue(any(expected in error for error in report["errors"]), report["errors"])

    def test_draft_cli_preserves_the_selected_layout_and_seals_its_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = layout("inspection")
            (root / "layout.json").write_text(json.dumps(selected), encoding="utf-8")
            (root / "intent.json").write_text(json.dumps(intent("Clean blue forms.")), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = production_spec.main([
                    "draft", "spec.json", "--root", str(root), "--model", "synthetic-image-model",
                    "--brief", "A blue robot inspects a latch.", "--kind", "robot",
                    "--subject", "mechanic", "--continuity", "one-off",
                    "--render-intent", "intent.json", "--layout", "layout.json",
                ])
            self.assertEqual(0, code, output.getvalue())
            spec = load_json(root / "spec.json")
            self.assertEqual(selected, spec["layout"])
            self.assertEqual(production_spec.digest(spec), json.loads(output.getvalue())["sha256"])
            committed = production_spec.digest(spec)
            spec["layout"]["reading_order"] = ["workshop", "display", "latch"]
            self.assertNotEqual(committed, production_spec.digest(spec))

    def test_layout_survives_asset_render_and_state_graph_handoff(self):
        graph = graph_fixture()
        selected = {
            "arrangement": "A wide view above a small detail view.",
            "regions": [
                {"id": "wide", "placement": "Upper region", "depiction": "The subject in the approved scene.",
                 "subjects": [{"subject_id": graph["identity_contract"]["character_id"],
                               "depiction": "The approved subject in a wide view."}],
                 "camera": copy.deepcopy(graph["asset_render_spec"]["camera"])},
                {"id": "detail", "placement": "Lower region", "depiction": "A closer view of the same subject."},
            ],
            "reading_order": ["wide", "detail"],
            "relationships": [{"from": "wide", "to": "detail", "relation": "The same instant from a closer view."}],
        }
        request = copy.deepcopy(graph["asset_render_spec"])
        request.pop("camera")
        request["layout"] = selected
        before = artifact_hash(graph["asset_render_spec"])
        graph["asset_render_spec"] = built = build_render_spec(
            request=request, identity_contract=graph["identity_contract"],
            species_profile=graph["species_profile"], individual_morphology=graph["individual_morphology"],
            state_snapshot=graph["state_snapshot"], visual_projection=graph["visual_projection"],
        )
        self.assertEqual(selected, built["layout"])
        self.assertNotIn("camera", built)
        self.assertNotEqual(before, artifact_hash(built))
        graph["production_spec"].pop("camera")
        graph["production_spec"]["layout"] = copy.deepcopy(selected)
        relink(graph)
        report = validate_state_artifact_graph(**graph)
        self.assertTrue(report["ok"], report["errors"])
        graph["production_spec"]["layout"]["regions"][1]["placement"] = "Upper right inset"
        report = validate_state_artifact_graph(**graph)
        self.assertFalse(report["ok"])
        self.assertIn("production specification layout differs from the asset render specification", report["errors"])


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
