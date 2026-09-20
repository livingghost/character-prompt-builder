#!/usr/bin/env python3
"""Offline regressions for world-coherent authoring, not a fiction-quality test.

    python scripts/world_coherence_smoke_test.py

Temporary files and synthetic test approvals only. No network, model, image,
pack mutation, actual user approval or semantic coherence score is involved.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import narrative  # noqa: E402
import narrative_coverage  # noqa: E402
import narrative_entity  # noqa: E402
import narrative_index  # noqa: E402
import narrative_init  # noqa: E402
import scene_plot  # noqa: E402


def minimal_narrative(cast_size: int = 0, *, chapter: bool = True) -> dict:
    """A fixture with no implicitly declared concern, arc or interpersonal plot."""
    return {
        "artifact_type": "narrative", "series_id": "coherence-fixture", "timeline_id": "main",
        "medium": "prose", "themes": [], "arcs": [], "acts": [],
        "characters": [{"id": f"C{i:02d}", "name": f"Agent {i}",
                        "persona": f"narrative/personas/c{i:02d}.md"}
                       for i in range(1, cast_size + 1)],
        "chapters": ([{"id": "ch01", "number": 1, "title": "Observation", "status": "complete",
                       "arcs": [], "depicts": ["A held condition at one interval."],
                       "story_order_start": 0, "story_order_end": 0}] if chapter else []),
        "relationships": [], "promises": [], "questions": [], "knowledge": [],
    }


def observational_scene(document: dict | None = None) -> dict:
    """One unpeopled, non-dramatic prose scene with actual visible support."""
    document = minimal_narrative() if document is None else document
    return {
        "artifact_type": "scene-plot", "scene_id": "sc01",
        "narrative_sha256": narrative.content_sha256(document), "chapter": "ch01", "order": 1,
        "arcs": [], "themes": [], "characters": [], "focalization": {"kind": "external"},
        "setting": {"interior_exterior": "exterior", "location": "basin",
                    "where": "along the rim", "time_of_day": "dawn"},
        "scene_function": "settle", "delivery_role": "standalone_short",
        "proposition": "Sustain attention to the unchanged pattern of light on still water.",
        "beats": [{"id": "b1", "beat": "The light holds a narrow line along the still water.",
                   "visibility": "visible"}],
        "exchanges": [], "relationship_delta": [], "state_changes": [],
        "placement": [{"statement": "The light lies along the rim.", "from": ["b1"]}],
        "must_preserve": [{"statement": "The water remains still.", "from": ["b1"]}],
        "free": [{"statement": "The length of the description within the intended rhythm."}],
        "realization": {"kind": "passages", "units": [{"id": "p1", "focal_beat": "b1",
            "mode": "scene", "covers": [{"statement": "Light sustained on still water.", "from": ["b1"]}]}]},
    }


def invoke(function, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = function(list(args))
    return code, json.loads(out.getvalue())


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprints(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


class ReaderTests(unittest.TestCase):
    def accepted(self, value, reader=narrative.validate_narrative):
        report = reader(value)
        self.assertTrue(report["ok"], report["errors"])
        return report

    def refused(self, value, fragment, reader=narrative.validate_narrative):
        report = reader(value)
        self.assertFalse(report["ok"])
        self.assertIn(fragment, "; ".join(report["errors"]))

    def test_neutral_tables_are_not_invalid_or_approved(self):
        report = self.accepted(minimal_narrative(chapter=False))
        self.assertFalse(report["approved"])
        self.assertEqual([report[k] for k in ("themes", "characters", "arcs", "chapters")], [0]*4)

    def test_required_arrays_cannot_be_missing(self):
        for key in ("themes", "characters", "arcs", "chapters"):
            with self.subTest(key=key):
                value = minimal_narrative(); value.pop(key)
                self.refused(value, f"{key} must be an array")

    def test_required_arrays_cannot_be_scalars(self):
        for key in ("themes", "characters", "arcs", "chapters"):
            with self.subTest(key=key):
                value = minimal_narrative(); value[key] = "none"
                self.refused(value, f"{key} must be an array")

    def test_empty_narrative_does_not_accept_invented_json_fields(self):
        value = minimal_narrative(); value["genre"] = "some invented genre"
        self.refused(value, "unknown keys")

    def test_non_character_arc_needs_no_persona_or_climax(self):
        value = minimal_narrative()
        value["arcs"] = [{"id": "a1", "name": "The cycle", "type": "main", "status": "resolved",
                          "themes": [], "characters": []}]
        value["chapters"][0]["arcs"] = ["a1"]
        self.accepted(value)

    def test_explicit_character_arc_still_needs_an_agent(self):
        value = minimal_narrative()
        value["arcs"] = [{"id": "a1", "name": "Choice", "type": "character", "status": "planned",
                          "themes": [], "characters": [], "want": "Observe", "need": "Reconsider"}]
        self.refused(value, "characters must be a non-empty array")

    def test_explicit_thematic_arc_still_needs_a_theme(self):
        value = minimal_narrative()
        value["arcs"] = [{"id": "a1", "name": "Inquiry", "type": "thematic", "status": "planned",
                          "themes": [], "characters": []}]
        self.refused(value, "themes must be a non-empty array")

    def test_plural_themes_can_exist_without_cast_or_dramatic_shape(self):
        value = minimal_narrative()
        value["themes"] = [{"id": f"t{i}", "statement": text} for i, text in enumerate(
            ("Continuity", "Local difference", "Unanswered origin", "Observer dependence"), 1)]
        value["arcs"] = [{"id": "a1", "name": "Contrasts", "type": "thematic", "status": "planned",
                          "themes": [t["id"] for t in value["themes"]], "characters": []}]
        self.accepted(value)

    def test_declared_unknown_arc_is_still_invalid(self):
        value = minimal_narrative(); value["chapters"][0]["arcs"] = ["absent"]
        self.refused(value, "names something that does not exist")

    def test_rising_content_is_checked_when_present(self):
        for bad in ("not an array", [""], [17]):
            with self.subTest(bad=bad):
                value = minimal_narrative()
                value["arcs"] = [{"id": "a1", "name": "Cycle", "type": "main", "status": "planned",
                                  "themes": [], "characters": [], "rising": bad}]
                self.refused(value, "rising")

    def test_observation_needs_no_turn_speech_or_state_change(self):
        report = self.accepted(observational_scene(), scene_plot.validate_scene_plot)
        self.assertEqual(report["characters"], [])
        self.assertEqual(report["turn"], {})
        self.assertEqual(report["state_changes"], 0)

    def test_unchanged_turn_is_explicit_persistence(self):
        value = observational_scene(); value["turn"] = {"value": "water", "from": "still", "to": "still"}
        self.accepted(value, scene_plot.validate_scene_plot)

    def test_present_null_or_scalar_turn_is_not_an_omitted_turn(self):
        for bad in (None, [], "none", 17):
            with self.subTest(bad=bad):
                value = observational_scene(); value["turn"] = bad
                self.refused(value, "turn must be an object", scene_plot.validate_scene_plot)

    def test_malformed_turn_is_still_refused(self):
        value = observational_scene(); value["turn"] = {"from": "still", "to": "still"}
        self.refused(value, "turn.value", scene_plot.validate_scene_plot)

    def test_scene_reference_arrays_are_still_required(self):
        for key in ("arcs", "themes", "characters", "state_changes"):
            with self.subTest(key=key):
                value = observational_scene(); value.pop(key)
                self.refused(value, f"{key} must be an array", scene_plot.validate_scene_plot)

    def test_unpeopled_scene_cannot_have_internal_viewpoint(self):
        value = observational_scene(); value["focalization"] = {"kind": "internal", "through": "C01"}
        self.refused(value, "who the scene does not say is in it", scene_plot.validate_scene_plot)

    def test_fake_relationship_in_empty_cast_is_refused(self):
        value = observational_scene()
        value["relationship_delta"] = [{"channel": "eye-contact", "between": ["C01", "C02"],
                                        "change": "Meets a gaze", "from": ["b1"]}]
        self.refused(value, "who the scene does not say is in it", scene_plot.validate_scene_plot)

    def test_unseen_context_cannot_support_visible_observation(self):
        value = observational_scene(); value["beats"][0]["visibility"] = "context"
        self.refused(value, "context", scene_plot.validate_scene_plot)

    def test_named_structure_still_checks_its_parts(self):
        value = observational_scene(); value["structure"] = {"profile": "kishotenketsu", "parts": {}}
        self.refused(value, "structure.parts", scene_plot.validate_scene_plot)


def cast_test(size: int):
    def test(self):
        self.accepted(minimal_narrative(size))
        # Having a cast does not require using it in every scene or creating relationships.
        self.accepted(observational_scene(minimal_narrative(size)), scene_plot.validate_scene_plot)
    return test


for size in (0, 1, 2, 5, 17):
    setattr(ReaderTests, f"test_cast_size_{size}_imposes_no_story_mode", cast_test(size))


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cpb-world-coherence-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.series = self.base / "series"
        code, self.started = invoke(narrative_init.main, "--out", str(self.series), "--series-id",
                                    "coherence-test", "--title", "Design fixture", "--medium", "prose")
        self.assertEqual(code, 0, self.started)
        self.path = self.series / "narrative/narrative.json"
        self.design = self.series / "narrative/design/project.md"

    def add(self, kind, identifier, *extra):
        return invoke(narrative_entity.main, "--series", str(self.series), "add", kind, identifier, *extra)

    def root_references(self, *ids):
        self.design.write_text(self.design.read_text().replace("references: []",
                               "references: [" + ", ".join(ids) + "]"), encoding="utf-8")

    def install_scene(self, document=None):
        document = minimal_narrative() if document is None else document
        document["approved"] = {"by": "synthetic-regression-fixture", "at": "2026-09-16T00:00:00Z",
                                "content_sha256": narrative.content_sha256(document)}
        save(self.path, document)
        self.add("location", "basin")
        plot = observational_scene(document)
        if document["arcs"]:
            plot["arcs"] = [item["id"] for item in document["arcs"]]
        save(self.series / "narrative/scenes/sc01.json", plot)
        return document, plot

    def coverage(self):
        return narrative_coverage.cover(self.path, self.series / "narrative/scenes", self.series)

    def test_default_init_creates_no_story_or_persona(self):
        value = json.loads(self.path.read_text())
        self.assertEqual(self.started["seed"], "neutral")
        self.assertTrue(all(value[field] == [] for field in ("characters", "themes", "arcs", "chapters")))
        self.assertFalse((self.series / "narrative/personas/c01.md").exists())
        self.assertNotIn("approved", value)

    def test_full_design_root_is_created_and_blanks_are_visible(self):
        report = narrative_index.scan(self.series)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["counts"]["design"], 1)
        self.assertEqual(report["orphans"], [])
        fields = {item["label"] for item in report["unfilled"]["narrative/design/project.md"]}
        self.assertTrue({"world_authorities", "theme_status_and_scope", "change_impact_and_retained_decisions"} <= fields)
        self.assertNotIn("narrative/design/design-template.md", report["unfilled"])
        self.assertTrue(self.design.read_text().startswith("---\nkind: design"))

    def test_world_records_join_through_design_without_personas_or_scenes(self):
        for kind, identifier in (("location", "basin"), ("system", "cycle"), ("faction", "guild"),
                                 ("artifact", "dial"), ("term", "interval")):
            self.assertEqual(self.add(kind, identifier)[0], 0)
        self.root_references("basin", "cycle", "guild", "dial", "interval")
        report = narrative_index.scan(self.series)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["orphans"], [])
        self.assertEqual(report["counts"]["persona"], 0)

    def test_missing_world_dependency_is_reported(self):
        self.root_references("missing-world-rule")
        report = narrative_index.scan(self.series)
        self.assertFalse(report["ok"])
        self.assertIn("missing-world-rule", report["dangling"])

    def test_rename_updates_design_dependency_without_interpreting_prose(self):
        self.add("system", "cycle")
        self.root_references("cycle")
        self.design.write_text(self.design.read_text() + "\nProse mention: cycle.\n", encoding="utf-8")
        code, report = invoke(narrative_entity.main, "--series", str(self.series), "rename", "cycle", "period")
        self.assertEqual(code, 0, report)
        self.assertIn("references: [period]", self.design.read_text())
        self.assertIn("Prose mention: cycle.", self.design.read_text())
        self.assertTrue(narrative_index.scan(self.series)["ok"])

    def test_design_root_can_be_removed_when_nobody_else_names_it(self):
        code, report = invoke(narrative_entity.main, "--series", str(self.series), "remove", "project")
        self.assertEqual(code, 0, report)
        self.assertFalse(self.design.exists())

    def test_real_reference_still_prevents_design_removal(self):
        self.add("design", "branch")
        branch = self.series / "narrative/design/branch.md"
        branch.write_text(branch.read_text().replace("references: []", "references: [project]"), encoding="utf-8")
        code, report = invoke(narrative_entity.main, "--series", str(self.series), "remove", "project")
        self.assertEqual(code, 1, report)
        self.assertTrue(self.design.exists())

    def test_design_add_contains_current_intent_register(self):
        code, report = self.add("design", "branch", "--name", "Branch")
        self.assertEqual(code, 0, report)
        text = (self.series / "narrative/design/branch.md").read_text()
        self.assertIn("## Authorial intent register", text)
        self.assertIn("## Portrayal review", text)

    def test_created_design_carries_intent_scope_and_departure_fields(self):
        text = narrative_entity.design_document("branch", "Branch")
        for field in ("subject_scope", "variation_envelope", "departure_policy", "information_boundary"):
            self.assertIn("**"+field+"**:", text)

    def test_missing_design_form_refuses_without_writing(self):
        (self.series / "narrative/design/design-template.md").unlink()
        before = fingerprints(self.series)
        with patch.object(narrative_entity, "ROOT", self.base / "missing-installation"):
            code, report = self.add("design", "branch")
        self.assertEqual(code, 1, report)
        self.assertEqual(before, fingerprints(self.series))

    def test_persona_is_added_only_when_requested_and_retains_twenty_sections(self):
        code, report = self.add("persona", "c01", "--character", "C01", "--phase", "opening")
        self.assertEqual(code, 0, report)
        text = (self.series / "narrative/personas/c01.md").read_text()
        self.assertEqual(re.findall(r"^## (\d+)\.", text, re.M), [str(i) for i in range(20)])
        self.assertEqual(json.loads(self.path.read_text())["characters"], [])

    def test_explicit_example_seed_preserves_teaching_fixture(self):
        target = self.base / "example"
        code, report = invoke(narrative_init.main, "--out", str(target), "--series-id", "sample",
                              "--title", "Example", "--seed", "example")
        self.assertEqual(code, 0, report)
        self.assertEqual(len(json.loads((target / "narrative/narrative.json").read_text())["characters"]), 1)
        self.assertTrue((target / "narrative/personas/c01.md").is_file())

    def test_default_initialization_does_not_overwrite_existing_work(self):
        before = fingerprints(self.series)
        with self.assertRaises(SystemExit):
            invoke(narrative_init.main, "--out", str(self.series), "--series-id", "new-id", "--title", "New")
        self.assertEqual(before, fingerprints(self.series))

    def test_multiline_title_is_refused_before_writing(self):
        target = self.base / "bad"
        with self.assertRaises(SystemExit):
            invoke(narrative_init.main, "--out", str(target), "--series-id", "bad-title", "--title", "X\nid: fake")
        self.assertFalse(target.exists())

    def test_multiline_entity_name_is_refused_before_writing(self):
        before = fingerprints(self.series)
        self.assertEqual(self.add("design", "branch", "--name", "X\nreferences: [fake]")[0], 1)
        self.assertEqual(before, fingerprints(self.series))

    def test_new_world_record_and_design_keep_distinct_responsibilities(self):
        self.assertEqual(self.add("design", "branch")[0], 0)
        self.assertEqual(self.add("system", "cycle")[0], 0)
        self.assertIn("## Authorial intent register", (self.series / "narrative/design/branch.md").read_text())
        self.assertIn("Conditions, operation, effects", (self.series / "narrative/world/systems/cycle.md").read_text())

    def test_unpeopled_scene_joins_narrative_index_and_coverage(self):
        self.install_scene()
        self.assertTrue(narrative_index.scan(self.series)["ok"])
        report = self.coverage()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["scenes"], 1)
        self.assertEqual(report["chapters"][0]["personas"], {})
        self.assertFalse(any("complete and no scene" in g or "opens or closes" in g for g in report["gaps"]))

    def test_one_scene_can_resolve_a_declared_non_dramatic_arc(self):
        value = minimal_narrative()
        value["arcs"] = [{"id": "a1", "name": "Observation", "type": "main", "status": "resolved",
                          "themes": [], "characters": []}]
        value["chapters"][0]["arcs"] = ["a1"]
        self.install_scene(value)
        report = self.coverage()
        self.assertTrue(report["ok"], report["errors"])
        self.assertFalse(any("arc a1" in gap for gap in report["gaps"]))

    def test_empty_cast_does_not_hide_undefined_scene_agents(self):
        _, plot = self.install_scene()
        plot["characters"] = ["C99"]
        save(self.series / "narrative/scenes/sc01.json", plot)
        report = self.coverage()
        self.assertFalse(report["ok"])
        self.assertTrue(any("C99" in error for error in report["errors"]))

    def test_changed_narrative_hash_still_breaks_scene_join(self):
        value, _ = self.install_scene()
        value["themes"] = [{"id": "t1", "statement": "A newly proposed concern"}]
        save(self.path, value)
        report = self.coverage()
        self.assertFalse(report["ok"])
        self.assertTrue(any("hash" in error or "written against" in error for error in report["errors"]))

    def test_design_edit_does_not_claim_automatic_json_approval_invalidation(self):
        value, _ = self.install_scene()
        self.design.write_text(self.design.read_text() + "\nA proposed revision requiring author review.\n")
        self.assertTrue(narrative.validate_narrative(json.loads(self.path.read_text()))["approved"])
        self.assertEqual(narrative.content_sha256(value), narrative.content_sha256(json.loads(self.path.read_text())))

    def test_reports_do_not_write_or_promote(self):
        self.install_scene()
        before = fingerprints(self.series)
        narrative_index.scan(self.series); self.coverage()
        self.assertEqual(before, fingerprints(self.series))

    def test_strict_index_keeps_design_gaps_visible(self):
        code, report = invoke(narrative_index.main, str(self.series), "--json", "--strict")
        self.assertEqual(code, 1)
        self.assertIn("narrative/design/project.md", report["unfilled"])


class RoutingTests(unittest.TestCase):
    def test_skill_routes_world_design_and_full_persona_directly(self):
        text = (ROOT / "SKILL.md").read_text()
        for link in ("references/runtime/narrative-development.md", "templates/narrative/design/design-template.md",
                     "templates/narrative/personas/persona-template.md"):
            self.assertIn(f"]({link})", text)

    def test_method_preserves_local_variation_axis(self):
        text = (ROOT / "references/runtime/narrative-development.md").read_text()
        self.assertIn("A situation variation does not silently redesign its", text)
        self.assertIn("Keep incompatible branches separate", text)
        self.assertIn("affected outputs", text)

    def test_method_preserves_plurality_and_does_not_mandate_ensemble(self):
        text = (ROOT / "references/runtime/narrative-development.md").read_text()
        for term in ("make the work an ensemble drama", "Theme is not a compulsory message",
                     "A scene need not change a relationship", "does not require realism"):
            self.assertIn(term, text)
        self.assertIn("deliberate indeterminacy", text)
        self.assertIn("Retain the creator", text)

    def test_world_and_persona_authorities_are_not_fused(self):
        form = (ROOT / "templates/narrative/personas/persona-template.md").read_text()
        self.assertIn("World-Coherence Boundary", form)
        self.assertIn("Shared world facts, adopted visual identity", form)
        self.assertEqual(re.findall(r"^## (\d+)\.", form, re.M), [str(i) for i in range(20)])

    def test_semantic_and_serializer_limits_are_explicit(self):
        text = (ROOT / "references/runtime/narrative-development.md").read_text()
        for term in ("not a native interactive branch graph", "not the bytes of linked Markdown",
                     "do not infer semantic dependencies", "Neither can establish"):
            self.assertIn(term, text)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    transcript = io.StringIO()
    result = unittest.TextTestRunner(stream=transcript, verbosity=2).run(suite)
    errors = [f"{case}: {detail}" for case, detail in result.failures + result.errors]
    print(json.dumps({"ok": result.wasSuccessful(), "checks": result.testsRun,
                      "skipped": [str(item) for item in result.skipped], "errors": errors}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
