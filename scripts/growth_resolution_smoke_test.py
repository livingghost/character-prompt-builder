#!/usr/bin/env python3
"""Regression coverage for resolved growth authority and state handoff."""
from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_asset_render_spec import build_render_spec
from state_protocol import (
    artifact_hash, finalize_artifact, load_json, plan_reference_bundle,
    resolve_growth_geometry, validate_state_artifact_graph,
)

PILOT = ROOT / "examples" / "state-aware-pilot"
GENERATED = PILOT / "generated"


def graph_fixture():
    files = {
        "lineage": GENERATED / "state-lineage.json",
        "species_profile": PILOT / "species-morphology-profile.json",
        "individual_morphology": PILOT / "individual-morphology-contract.json",
        "identity_contract": PILOT / "character-identity-contract.json",
        "state_snapshot": GENERATED / "state-snapshot-C01.json",
        "scene_context": GENERATED / "scene-context-snapshot.json",
        "visual_projection": GENERATED / "visual-state-projection.json",
        "asset_render_spec": GENERATED / "asset-render-specification.json",
        "production_spec": GENERATED / "production-specification.json",
    }
    return {name: load_json(path) for name, path in files.items()}


def relink(graph):
    """Reseal legitimate changed inputs, never repairing a deliberately bad output."""
    identity = graph["identity_contract"]
    optional = {name + "_sha256": artifact_hash(graph[name]) if graph.get(name) else None
                for name in ("era_contract", "form_contract", "appearance_variant")}
    state = graph["state_snapshot"]
    state.update(optional, identity_contract_sha256=artifact_hash(identity))
    graph["state_snapshot"] = state = finalize_artifact(state)
    context = graph["scene_context"]
    for row in context["active_character_snapshots"]:
        if row["character_id"] == identity["character_id"]:
            row["state_snapshot_sha256"] = artifact_hash(state)
    graph["scene_context"] = context = finalize_artifact(context)
    projection = graph["visual_projection"]
    projection.update(state_snapshot_sha256=artifact_hash(state), scene_context_sha256=artifact_hash(context))
    graph["visual_projection"] = projection = finalize_artifact(projection)
    render = graph["asset_render_spec"]
    render.update(identity_contract_sha256=artifact_hash(identity), state_snapshot_sha256=artifact_hash(state),
                  visual_state_projection_sha256=artifact_hash(projection),
                  **{k: v for k, v in optional.items() if k != "form_contract_sha256"})
    graph["asset_render_spec"] = render = finalize_artifact(render)
    lineage = graph["lineage"]
    lineage.update(identity_contract_sha256=artifact_hash(identity), state_snapshot_sha256=artifact_hash(state),
                   scene_context_sha256=artifact_hash(context), visual_projection_sha256=artifact_hash(projection),
                   asset_render_spec_sha256=artifact_hash(render), **optional)
    graph["lineage"] = lineage = finalize_artifact(lineage)
    spec = graph["production_spec"]
    spec["state_context"].update(state_lineage_sha256=artifact_hash(lineage),
                                 scene_context_ref={"id": context["scene_context_id"], "sha256": artifact_hash(context)})
    subject = spec["subjects"][0]
    subject["identity_contract_ref"]["sha256"] = artifact_hash(identity)
    subject["state_snapshot_ref"]["sha256"] = artifact_hash(state)
    subject["visual_projection_ref"]["sha256"] = artifact_hash(projection)


class GrowthResolutionTests(unittest.TestCase):
    def setUp(self):
        self.graph = graph_fixture()
        self.identity = self.graph["identity_contract"]
        self.base = self.identity["stable_identity"]["growth_geometry"]

    def variant(self):
        value = load_json(ROOT / "templates/state/appearance-variant-contract.template.json")
        value.update(variant_class="grooming", canon_status="approved",
                     parent_identity_contract_sha256=artifact_hash(self.identity),
                     growth_geometry=copy.deepcopy(self.base))
        value["growth_geometry"]["structures"]["terminal-tips"]["geometry"]["color_and_value"] = "bright red approved polish"
        return value

    def plan(self, output, variant):
        return plan_reference_bundle(
            self.identity, species_profile=self.graph["species_profile"],
            individual_morphology=self.graph["individual_morphology"],
            style_family_id="style-family-clear-portrait", target_model=self.graph["production_spec"]["target_model"],
            policy="core-coverage", out_dir=output, appearance_variant=variant,
        )

    def test_baseline_graph_and_resolution_are_valid(self):
        report = validate_state_artifact_graph(**self.graph)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(resolve_growth_geometry(self.identity), self.base)

    def test_resolution_never_mutates_its_inputs(self):
        variant = self.variant()
        before = copy.deepcopy((self.identity, variant))
        geometry = resolve_growth_geometry(self.identity, appearance_variant=variant)
        geometry["structures"]["terminal-tips"]["geometry"]["color_and_value"] = "changed by caller"
        self.assertEqual((self.identity, variant), before)

    def test_unapproved_structure_changes_are_rejected_by_graph(self):
        for key, field, value in (("fur-tail", "length", "twice the approved length"),
                                  ("terminal-tips", "length_relative_to_terminal_digit", "three times the digit")):
            with self.subTest(key=key):
                graph = copy.deepcopy(self.graph)
                graph["production_spec"]["subjects"][0]["growth_geometry"]["structures"][key]["geometry"][field] = value
                report = validate_state_artifact_graph(**graph)
                self.assertFalse(report["ok"])
                self.assertTrue(any("growth_geometry differs" in error for error in report["errors"]))

    def test_agreeing_but_forged_render_and_production_are_rejected(self):
        for geometry in (self.graph["asset_render_spec"]["subject_resolution"]["growth_geometry"],
                         self.graph["production_spec"]["subjects"][0]["growth_geometry"]):
            geometry["structures"]["fur-tail"]["geometry"]["length"] = "twice the approved length"
        relink(self.graph)
        report = validate_state_artifact_graph(**self.graph)
        self.assertFalse(report["ok"])
        self.assertEqual(sum("growth_geometry differs" in error for error in report["errors"]), 2)

    def test_missing_render_geometry_is_rejected(self):
        del self.graph["asset_render_spec"]["subject_resolution"]["growth_geometry"]
        relink(self.graph)
        self.assertFalse(validate_state_artifact_graph(**self.graph)["ok"])

    def test_approved_polish_reaches_every_reference_render(self):
        variant = self.variant()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            plan = self.plan(output, variant)
            for row in plan["assets"]:
                render = load_json(output / row["render_spec_file"])
                geometry = render["subject_resolution"]["growth_geometry"]
                self.assertEqual(geometry, variant["growth_geometry"])
                self.assertEqual(geometry["structures"]["fur-tail"], self.base["structures"]["fur-tail"])
                self.assertEqual(render["appearance_variant_sha256"], artifact_hash(variant))

    def test_bad_approval_parent_and_character_leave_no_output(self):
        for field, value in (("canon_status", "proposed"), ("canon_status", "superseded"),
                             ("parent_identity_contract_sha256", "1" * 64), ("character_id", "OTHER")):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as temporary:
                variant = self.variant()
                variant[field] = value
                output = Path(temporary) / "bundle"
                with self.assertRaises(ValueError):
                    self.plan(output, variant)
                self.assertFalse(output.exists())

    def test_approval_does_not_grant_permission_for_locked_structure(self):
        variant = self.variant()
        variant["growth_geometry"]["structures"]["fur-tail"]["geometry"]["length"] = "twice the approved length"
        with self.assertRaisesRegex(ValueError, "outside authorized variant_fields"):
            resolve_growth_geometry(self.identity, appearance_variant=variant)

    def test_variant_cannot_grant_itself_new_permissions(self):
        variant = self.variant()
        variant["growth_geometry"]["variant_fields"].append("/stable_identity/growth_geometry/structures/fur-tail/geometry/length")
        with self.assertRaisesRegex(ValueError, "outside authorized variant_fields"):
            resolve_growth_geometry(self.identity, appearance_variant=variant)

    def test_shadow_geometry_in_free_form_description_is_rejected(self):
        variant = self.variant()
        variant["appearance_definition"]["growth_geometry"] = copy.deepcopy(self.base)
        with self.assertRaisesRegex(ValueError, "must not shadow"):
            resolve_growth_geometry(self.identity, appearance_variant=variant)

    def test_approved_polish_and_current_wetness_coexist_without_changing_shape(self):
        variant = self.variant()
        self.graph["appearance_variant"] = variant
        self.graph["state_snapshot"]["appearance_state"]["grooming"]["fur_wetness"]["brow"] = "wet"
        relink(self.graph)
        geometry = resolve_growth_geometry(self.identity, appearance_variant=variant,
                                           state_snapshot=self.graph["state_snapshot"])
        self.assertIn('"brow":"wet"', geometry["grooming_state"][-1])
        self.assertEqual(geometry["structures"]["fur-tail"], self.base["structures"]["fur-tail"])
        self.assertEqual(geometry["structures"]["terminal-tips"]["geometry"]["color_and_value"], "bright red approved polish")
        self.graph["production_spec"]["subjects"][0]["growth_geometry"] = copy.deepcopy(geometry)
        self.graph["asset_render_spec"]["subject_resolution"]["growth_geometry"] = copy.deepcopy(geometry)
        relink(self.graph)
        report = validate_state_artifact_graph(**self.graph)
        self.assertTrue(report["ok"], report["errors"])

    def test_forged_current_condition_is_rejected(self):
        self.graph["production_spec"]["subjects"][0]["growth_geometry"]["grooming_state"].append("invented wetness")
        self.assertFalse(validate_state_artifact_graph(**self.graph)["ok"])

    def test_state_must_reference_the_same_approved_variant(self):
        with self.assertRaisesRegex(ValueError, "appearance_variant_sha256"):
            resolve_growth_geometry(self.identity, appearance_variant=self.variant(), state_snapshot=self.graph["state_snapshot"])

    def test_approved_era_and_form_can_explicitly_replace_geometry(self):
        for kind, field, argument in (("era", "approved_changes", "era_contract"),
                                      ("form", "surface_system", "form_contract")):
            with self.subTest(kind=kind):
                contract = load_json(ROOT / f"templates/state/{kind}-contract.template.json")
                contract.update(canon_status="approved", parent_identity_contract_sha256=artifact_hash(self.identity))
                geometry = copy.deepcopy(self.base)
                geometry["structures"]["fur-tail"]["geometry"]["length"] = "twice the approved length"
                contract[field]["growth_geometry"] = geometry
                self.assertEqual(resolve_growth_geometry(self.identity, **{argument: contract}), geometry)
                contract["canon_status"] = "proposed"
                with self.assertRaisesRegex(ValueError, "must be approved"):
                    resolve_growth_geometry(self.identity, **{argument: contract})

    def test_form_render_requires_the_snapshot_that_binds_its_hash(self):
        form = load_json(ROOT / "templates/state/form-contract.template.json")
        form.update(canon_status="approved", parent_identity_contract_sha256=artifact_hash(self.identity))
        form["surface_system"]["growth_geometry"] = copy.deepcopy(self.base)
        kwargs = dict(request=load_json(PILOT / "render-spec-request.json"), identity_contract=self.identity,
                      species_profile=self.graph["species_profile"],
                      individual_morphology=self.graph["individual_morphology"], form_contract=form)
        with self.assertRaisesRegex(ValueError, "requires a state snapshot"):
            build_render_spec(**kwargs)
        snapshot = copy.deepcopy(self.graph["state_snapshot"])
        snapshot["form_contract_sha256"] = artifact_hash(form)
        snapshot = finalize_artifact(snapshot)
        rendered = build_render_spec(**kwargs, state_snapshot=snapshot)
        self.assertEqual(rendered["state_snapshot_sha256"], artifact_hash(snapshot))
        self.assertEqual(rendered["subject_resolution"]["growth_geometry"],
                         resolve_growth_geometry(self.identity, form_contract=form, state_snapshot=snapshot))

    def test_nonhuman_authored_material_is_preserved_without_inference(self):
        self.base["structures"]["ruff-cheeks-neck"]["kind"] = "segmented ceramic vanes"
        self.assertEqual(resolve_growth_geometry(self.identity)["structures"]["ruff-cheeks-neck"]["kind"], "segmented ceramic vanes")

    def test_render_builder_fills_resolved_geometry_and_refuses_conflicting_input(self):
        request = load_json(PILOT / "render-spec-request.json")
        kwargs = dict(request=request, identity_contract=self.identity, species_profile=self.graph["species_profile"],
                      individual_morphology=self.graph["individual_morphology"], appearance_variant=self.variant())
        rendered = build_render_spec(**kwargs)
        self.assertEqual(rendered["subject_resolution"]["growth_geometry"]["structures"]["terminal-tips"]["geometry"]["color_and_value"],
                         "bright red approved polish")
        self.assertNotIn("growth_geometry", request["subject_resolution"])
        request["subject_resolution"]["growth_geometry"] = copy.deepcopy(self.base)
        with self.assertRaisesRegex(ValueError, "render request growth_geometry differs"):
            build_render_spec(**kwargs)


def main():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream).run(unittest.defaultTestLoader.loadTestsFromTestCase(GrowthResolutionTests))
    print(json.dumps({"ok": result.wasSuccessful(), "checks": result.testsRun,
                      "failures": len(result.failures), "error_count": len(result.errors),
                      "errors": [f"{case.id()}: {detail}" for case, detail in result.failures + result.errors],
                      "detail": stream.getvalue()}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
