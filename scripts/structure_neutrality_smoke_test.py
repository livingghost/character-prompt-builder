#!/usr/bin/env python3
"""Offline regressions for declaration-based structure authoring and handoff.

Run: python scripts/structure_neutrality_smoke_test.py
No network, rendering, credentials, generation or real consent is used.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from state_protocol import (artifact_hash, finalize_artifact, load_json, parse_json,
                            plan_reference_bundle, resolve_growth_geometry,
                            validate_against_schema, validate_artifact,
                            validate_state_artifact_graph)
from structure_contract import KINDS, inspect_contract, structure_view
from validate_prompt_semantics import validate_plan
from search_discovery import SearchIndex, analyze_query
from growth_resolution_smoke_test import graph_fixture, relink
import production_spec


def fixture(name):
    return load_json(ROOT / "examples/declared-structures" / name)


def schema_errors(value, kind):
    return validate_against_schema(value, load_json(ROOT / "schemas" / (kind + ".schema.json")))


class StructureNeutralityTests(unittest.TestCase):
    def declaration(self):
        return fixture("lattice-growth.json")

    def test_empty_structure_maps_validate(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                value = load_json(ROOT / "templates" / (kind + "-template.json"))
                self.assertEqual([], schema_errors(value, kind))
                self.assertEqual({}, value["structures"])

    def test_generic_examples_are_valid(self):
        for name, kind in (("lattice-growth.json", "growth-geometry"), ("fluid-frame.json", "frame-character"),
                           ("rim-terminal.json", "terminal-growth-contract"), ("ring-garment.json", "garment-geometry")):
            with self.subTest(name=name):
                self.assertEqual([], schema_errors(fixture(name), kind))




    def test_authored_geometry_in_templates_examples_and_pack_records(self):
        paths = list((ROOT / "templates").rglob("*.json")) + list((ROOT / "examples").rglob("*.json"))
        for records in (ROOT / "packs").glob("*/records"):
            paths.extend(records.rglob("*.json"))
        checked = 0

        def walk(value, path, pointer=""):
            nonlocal checked
            if isinstance(value, dict):
                if value.get("representation") == "declared-structures":
                    kind = ("growth-geometry" if "grooming_state" in value else
                            "frame-character" if "frame_character_id" in value else
                            "garment-geometry" if "garment_id" in value else "terminal-growth-contract")
                    with self.subTest(file=str(path.relative_to(ROOT)), pointer=pointer):
                        self.assertEqual([], schema_errors(value, kind))
                    checked += 1
                for name, child in value.items():
                    walk(child, path, pointer + "/" + name)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, path, pointer + "/" + str(index))

        for path in paths:
            walk(parse_json(path.read_text(encoding="utf-8")), path)
        self.assertGreaterEqual(checked, len(KINDS))

    def test_present_requires_actual_geometry(self):
        value = self.declaration(); value["structures"]["edge-filaments"]["geometry"] = {}
        self.assertTrue(schema_errors(value, "growth-geometry"))

    def test_absent_unknown_and_omitted_are_distinct(self):
        for presence in ("absent", "unknown"):
            with self.subTest(presence=presence):
                value = self.declaration()
                value["structures"] = {"declared-part": {"kind": "arbitrary", "location": "authored region", "presence": presence, "geometry": {}}}
                self.assertEqual([], schema_errors(value, "growth-geometry"))
                view = structure_view(value, "growth-geometry")
                self.assertEqual(presence, view["structures"]["declared-part"]["presence"])
                value["structures"]["declared-part"]["geometry"]["shape"] = "invented geometry"
                self.assertTrue(schema_errors(value, "growth-geometry"))

    def test_invalid_reference_is_rejected_in_every_contract(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                value = load_json(ROOT / "templates" / (kind + "-template.json"))
                value["structures"] = self.declaration()["structures"]
                value["structures"]["edge-filaments"]["parent_id"] = "missing"
                self.assertTrue(schema_errors(value, kind))

    def test_containment_cycles_are_rejected(self):
        value = self.declaration(); value["structures"]["carrier-mesh"]["parent_id"] = "edge-filaments"
        self.assertTrue(schema_errors(value, "growth-geometry"))

    def test_override_cycles_are_rejected(self):
        value = self.declaration(); value["structures"]["carrier-mesh"]["overrides"] = [{"structure_id": "edge-filaments", "properties": ["color"]}]
        self.assertTrue(schema_errors(value, "growth-geometry"))

    def test_attachment_rings_are_permitted(self):
        value = self.declaration()
        value["structures"]["carrier-mesh"]["attachment_ids"] = ["edge-filaments"]
        value["structures"]["edge-filaments"]["attachment_ids"] = ["carrier-mesh"]
        self.assertEqual([], schema_errors(value, "growth-geometry"))

    def test_present_cannot_attach_to_explicitly_absent_carrier(self):
        value = self.declaration(); value["structures"]["carrier-mesh"].update(presence="absent", geometry={})
        self.assertTrue(schema_errors(value, "growth-geometry"))

    def test_unknown_override_property_is_rejected(self):
        value = self.declaration(); value["structures"]["edge-filaments"]["overrides"][0]["properties"] = ["not-declared"]
        self.assertTrue(schema_errors(value, "growth-geometry"))

    def test_local_exception_preserves_global_geometry(self):
        value = self.declaration(); before = copy.deepcopy(value)
        view = inspect_contract(value, "growth-geometry")
        self.assertTrue(view["ok"], view["errors"])
        self.assertEqual(before, value)
        self.assertEqual("matte graphite", view["view"]["structures"]["carrier-mesh"]["definition"]["geometry"]["color"])
        self.assertEqual("pale amber", view["view"]["structures"]["edge-filaments"]["definition"]["geometry"]["color"])

    def test_duplicate_ids_in_json_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            parse_json('{"structures":{"same":{},"same":{}}}')



    def test_two_same_side_structures_are_permitted(self):
        plan = fixture("asymmetric-topology.json")
        self.assertTrue(validate_plan(plan)["ok"], validate_plan(plan))
        for row in plan["structure_plan"]["assigned_structures"]:
            row["side"] = "ventral-inner"
        self.assertTrue(validate_plan(plan)["ok"])

    def test_declared_side_limit_is_enforced(self):
        plan = fixture("asymmetric-topology.json")
        plan["structure_plan"]["side_limits"] = [{"kind": "manipulator", "side": "left", "max_count": 1}]
        self.assertFalse(validate_plan(plan)["ok"])

    def test_duplicate_excess_and_unknown_action_still_fail(self):
        for mutation in ("duplicate", "count", "reference", "action"):
            with self.subTest(mutation=mutation):
                plan = fixture("asymmetric-topology.json"); body = plan["structure_plan"]
                if mutation == "duplicate": body["assigned_structures"][1]["structure_id"] = "left-upper"
                if mutation == "count": body["expected_counts"]["manipulator"] = 1
                if mutation == "reference": body["primary_actions"][0]["structure_id"] = "missing"
                if mutation == "action": body["primary_actions"].append({"structure_id": "left-upper", "action": "unrelated motion"})
                self.assertFalse(validate_plan(plan)["ok"])

    def test_owner_specific_limit_is_enforced(self):
        plan = fixture("asymmetric-topology.json")
        plan["structure_plan"]["expected_by_owner"] = {"C01": {"manipulator": 1}}
        self.assertFalse(validate_plan(plan)["ok"])

    def test_plan_errors_say_what_to_write(self):
        errors = validate_plan({"structure_plan": {"expected_counts": {}, "assigned_structures": []}})["errors"]
        self.assertEqual(["$: missing required property 'camera'; write an object with angle, shot_scale, distance,"
                          " pitch and subject_frame_occupancy; --template prints a plan to start from"], errors)
        plan = fixture("asymmetric-topology.json")
        plan["camera"]["subject_frame_occupancy"] = "0.45"
        del plan["structure_plan"]["assigned_structures"][0]["structure_id"]
        errors = validate_plan(plan)["errors"]
        self.assertIn("$.camera.subject_frame_occupancy: expected type ['number'], got str; write a number from"
                      " 0 to 1, the share of the frame the subject fills, such as 0.5", errors)
        self.assertIn("$.structure_plan.assigned_structures[0]: missing required property 'structure_id'; write a"
                      " name you choose for the structure, unique in the plan; primary_actions refer to it", errors)

    def test_unknown_plan_fields_are_refused_one_line_each(self):
        plan = fixture("asymmetric-topology.json")
        plan["structure_plan"]["assigned_structures"][0]["action"] = "holds the tool"
        plan["camera"]["lens"] = "35mm"
        report = validate_plan(plan)
        self.assertFalse(report["ok"])
        self.assertEqual([
            "$.camera.lens: unknown field; this object takes angle, shot_scale, distance, camera_height, pitch,"
            " subject_frame_occupancy, establishing_context",
            "$.structure_plan.assigned_structures[0].action: unknown field; an action goes in"
            ' structure_plan.primary_actions as {"structure_id": "...", "action": "..."}',
        ], report["errors"])

    def test_plan_help_names_every_field_and_template_passes(self):
        def run(*args):
            return subprocess.run([sys.executable, "scripts/validate_prompt_semantics.py", *args], cwd=ROOT,
                                  capture_output=True, text=True, encoding="utf-8", timeout=30)
        schema = load_json(ROOT / "schemas/prompt-semantic-preflight.schema.json")
        names = set()
        stack = [schema]
        while stack:
            node = stack.pop()
            names.update((node.get("properties") or {}).keys())
            stack.extend((node.get("properties") or {}).values())
            stack.extend(child for child in (node.get("items"), node.get("additionalProperties")) if isinstance(child, dict))
        shown = run("--help").stdout
        self.assertEqual(set(), {name for name in names if f"  {name}  " not in shown})
        template = run("--template").stdout
        self.assertIn(template, shown)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(template, encoding="utf-8")
            self.assertEqual(0, run(str(path)).returncode)
        missing = run()
        self.assertEqual(2, missing.returncode)
        self.assertIn("--template prints one to start from", missing.stderr)


    def test_camera_does_not_require_human_distance_or_eyes(self):
        value = fixture("reference-camera.json")
        self.assertNotIn("human_scale_distance_equivalent_m", value)
        self.assertNotIn("eye_line_position", value)
        self.assertEqual([], schema_errors(value, "camera-framing-contract"))

    def test_production_template_omits_anatomical_summary_slots(self):
        value = load_json(ROOT / "templates/production-spec-template.json")
        for row in value["subjects"]:
            self.assertFalse({"head_and_face", "hands", "legs_and_feet", "gaze_and_head"} & row.keys())
        report = production_spec.validate(value)
        self.assertTrue(report["ok"], report["errors"])

    def test_morphology_starters_do_not_invent_paired_eyes_or_human_scale(self):
        for kind in ("species-morphology-profile", "individual-morphology-contract", "visual-state-projection"):
            with self.subTest(kind=kind):
                value = load_json(ROOT / "templates/state" / (kind + ".template.json"))
                self.assertEqual([], schema_errors(value, kind))
                text = json.dumps(value)
                for assumption in ("head.eye.pair", "region-head", "eye count remains two", "human-scale unless"):
                    self.assertNotIn(assumption, text)
        individual = load_json(ROOT / "templates/state/individual-morphology-contract.template.json")
        self.assertNotIn("head_to_body_ratio", individual["individual_measurements"])
        self.assertNotIn("limb_ratios", individual["individual_measurements"])
        species = load_json(ROOT / "templates/state/species-morphology-profile.template.json")
        self.assertEqual("declared-structures", species["frame_character_model"]["default"]["representation"])
        self.assertNotIn("face_body_coherence_rule", species["frame_character_model"])

    def test_neutral_camera_example_does_not_smuggle_in_anatomy(self):
        for file in ("templates/camera-framing-contract-template.json", "examples/declared-structures/reference-camera.json"):
            value = load_json(ROOT / file)
            self.assertEqual([], schema_errors(value, "camera-framing-contract"))
            text = json.dumps(value).lower()
            for assumption in ("muzzle", "forearm", "ear tip", "sternum", "belt line"):
                self.assertNotIn(assumption, text)

    def test_kind_spelling_cannot_bypass_declared_limits(self):
        plan = fixture("asymmetric-topology.json")
        kind = plan["structure_plan"]["assigned_structures"][0]["kind"]
        plan["structure_plan"]["expected_counts"] = {kind.upper(): 0}
        self.assertFalse(validate_plan(plan)["ok"])
        plan["structure_plan"]["expected_counts"] = {kind: 10, kind.upper(): 10}
        self.assertFalse(validate_plan(plan)["ok"])

    def test_search_does_not_promote_unspecified_locations(self):
        index = SearchIndex({"phrases": {}, "records": {}})
        for query in ("hair", "tail hair", "back hair", "dorsal horns", "robot with a speaker horn", "ventral strands"):
            with self.subTest(query=query):
                anchors = analyze_query(query, index).anchors
                self.assertNotIn("head_hair", anchors)
                self.assertNotIn("head_feature", anchors)
                self.assertIn("identity_detail", anchors)

    def test_explicit_head_location_is_still_searchable(self):
        index = SearchIndex({"phrases": {}, "records": {}})
        self.assertIn("head_hair", analyze_query("blue head hair", index).anchors)
        self.assertIn("head_feature", analyze_query("cranial horns", index).anchors)

    def test_coat_context_does_not_assume_covering(self):
        index = SearchIndex({"phrases": {}, "records": {}})
        worn = analyze_query("wearing a blue coat", index).anchors
        self.assertEqual(["blue"], worn.get("wardrobe"))
        self.assertNotIn("coat_palette", worn)
        self.assertEqual(["blue"], analyze_query("blue coat of fur", index).anchors.get("coat_palette"))
        bare = analyze_query("blue coat", index).anchors
        self.assertNotIn("coat_palette", bare)
        self.assertNotIn("wardrobe", bare)

    def test_populated_index_cannot_restore_a_head_assumption(self):
        index = SearchIndex({"records": {}, "phrases": {
            "hair": [{"id": "fixture-head", "facet": "head_hair", "source": "label", "weight": 1}],
            "horn": [{"id": "fixture-horn", "facet": "head_feature", "source": "label", "weight": 1}],
        }})
        self.assertNotIn("head_hair", analyze_query("tail hair", index).anchors)
        self.assertNotIn("head_feature", analyze_query("speaker horn", index).anchors)

    def graph(self):
        graph = graph_fixture()
        graph["identity_contract"]["stable_identity"]["growth_geometry"] = self.declaration()
        relink(graph)
        resolved = resolve_growth_geometry(graph["identity_contract"], state_snapshot=graph["state_snapshot"])
        graph["production_spec"]["subjects"][0]["growth_geometry"] = copy.deepcopy(resolved)
        graph["asset_render_spec"]["subject_resolution"]["growth_geometry"] = copy.deepcopy(resolved)
        relink(graph)
        return graph

    def test_declared_geometry_passes_full_state_graph(self):
        graph = self.graph()
        report = validate_state_artifact_graph(**graph)
        self.assertTrue(report["ok"], report["errors"])

    def test_declared_approved_change_and_temporary_state_are_preserved(self):
        graph = self.graph(); identity = graph["identity_contract"]
        variant = load_json(ROOT / "templates/state/appearance-variant-contract.template.json")
        variant.update(variant_class="grooming", canon_status="approved", parent_identity_contract_sha256=artifact_hash(identity), growth_geometry=self.declaration())
        variant["growth_geometry"]["structures"]["edge-filaments"]["geometry"]["color"] = "approved cyan"
        graph["appearance_variant"] = variant; relink(graph)
        resolved = resolve_growth_geometry(identity, appearance_variant=variant, state_snapshot=graph["state_snapshot"])
        self.assertEqual("approved cyan", resolved["structures"]["edge-filaments"]["geometry"]["color"])
        self.assertEqual("matte graphite", resolved["structures"]["carrier-mesh"]["geometry"]["color"])
        self.assertTrue(resolved["grooming_state"])
        variant["growth_geometry"]["structures"]["carrier-mesh"]["geometry"]["color"] = "unauthorized"
        with self.assertRaisesRegex(ValueError, "authorized variant_fields"):
            resolve_growth_geometry(identity, appearance_variant=variant)

    def test_declared_geometry_drift_is_rejected(self):
        graph = self.graph()
        graph["production_spec"]["subjects"][0]["growth_geometry"]["structures"]["edge-filaments"]["geometry"]["color"] = "unapproved"
        report = validate_state_artifact_graph(**graph)
        self.assertFalse(report["ok"])

    def test_reference_planner_requires_authored_views(self):
        graph = self.graph()
        graph["identity_contract"].pop("reference_views", None)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "reference_views"):
                plan_reference_bundle(graph["identity_contract"], species_profile=graph["species_profile"], individual_morphology=graph["individual_morphology"], style_family_id="style-family-clear-portrait", target_model=graph["production_spec"]["target_model"], policy="core-coverage", out_dir=Path(directory))
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_authored_reference_view_has_no_injected_anatomical_views(self):
        graph = self.graph(); identity = graph["identity_contract"]
        identity["coverage_requirements"] = [{"requirement_id": "rim-coverage", "feature_refs": ["edge-filaments"], "acceptable_views": ["mesh-overview"], "priority": "signature"}]
        identity["anchor_fragments"] = []
        identity["reference_views"] = {"mesh-overview": {"view": "authored outer-axis", "framing": "whole carrier", "coverage_tokens": ["mesh-overview"], "camera": fixture("reference-camera.json")}}
        with tempfile.TemporaryDirectory() as directory:
            plan = plan_reference_bundle(identity, species_profile=graph["species_profile"], individual_morphology=graph["individual_morphology"], style_family_id="style-family-clear-portrait", target_model=graph["production_spec"]["target_model"], policy="core-coverage", out_dir=Path(directory))
            self.assertEqual(1, len(plan["assets"]))
            render = load_json(Path(directory) / plan["assets"][0]["render_spec_file"])
            self.assertEqual(fixture("reference-camera.json"), render["camera"])
            self.assertEqual(self.declaration(), render["subject_resolution"]["growth_geometry"])
            self.assertEqual([], plan["unresolved_requirements"])
            self.assertNotIn("unobstructed anatomy", render["prompt_scaffold"])
            self.assertNotIn("hands or feet", render["art_direction"]["detail_hierarchy"])

    def test_documented_commands_execute(self):
        commands = [
            ["scripts/structure_contract.py", "--help"],
            ["scripts/structure_contract.py", "validate", "templates/growth-geometry-template.json", "--kind", "growth-geometry"],
            ["scripts/structure_contract.py", "inspect", "examples/declared-structures/lattice-growth.json", "--kind", "growth-geometry"],
            ["scripts/validate_prompt_semantics.py", "examples/declared-structures/asymmetric-topology.json"],
        ]
        for args in commands:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)


def main() -> int:
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(StructureNeutralityTests))
    errors = [text for _, text in result.failures + result.errors]
    print(json.dumps({"ok": result.wasSuccessful(), "checks": result.testsRun,
                      "errors": errors, "detail": stream.getvalue()}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
