#!/usr/bin/env python3
"""Regression tests for persona-led authoring, not a rating of fiction.

    python scripts/persona_workflow_smoke_test.py

Uses temporary series, synthetic approvals and in-process CLI entrypoints. No
network, image generation, pack mutation, or creator approval is performed.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import re
import subprocess
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
from narrative_authoring_smoke_test import scene_plot as make_scene  # noqa: E402


def invoke(function, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = function(list(args))
    return code, json.loads(output.getvalue())


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tree_hashes(path: Path) -> dict[str, str]:
    return {file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in path.rglob("*") if file.is_file()}


class PlaceholderTests(unittest.TestCase):
    def details(self, text):
        return narrative_index.placeholder_details(text)

    def test_empty_field_has_actual_line(self):
        self.assertEqual(self.details("# Name\n\n- **goal**:\n  <!-- example -->\n"),
                         [{"line": 3, "kind": "empty-field", "label": "goal"}])

    def test_multiline_answer_counts_as_content(self):
        self.assertEqual(self.details("- **goal**:\n  <!-- guidance -->\n  A chosen aim.\n"), [])

    def test_nested_group_is_not_an_additional_blank(self):
        found = self.details("- **refusal**:\n  - **if**:\n  - **then**: ask once\n")
        self.assertEqual([x["label"] for x in found], ["if"])

    def test_commented_list_item_is_a_gap(self):
        self.assertEqual(self.details("- <!-- value -->\n")[0]["kind"], "empty-item")

    def test_multiline_list_item_is_not_a_gap(self):
        self.assertEqual(self.details("- <!-- value -->\n  A specific value.\n"), [])

    def test_table_cells_are_reported(self):
        text = "| Rule | Basis |\n|---|---|\n| Acts | <!-- source --> |\n"
        self.assertEqual(self.details(text),
                         [{"line": 3, "kind": "empty-table-cells", "label": "empty table cell(s): 2"}])

    def test_inline_code_and_escaped_pipe_do_not_make_table_cells(self):
        text = "| Rule | Basis |\n|---|---|\n| `a||b` | evidence \\| boundary |\n"
        self.assertEqual(self.details(text), [])

    def test_examined_unknown_and_inapplicable_are_not_blanks(self):
        self.assertEqual(self.details("- **fact**: unknown\n- **trait**: n/a\n"), [])

    def test_undecided_design_is_still_a_gap(self):
        self.assertEqual(len(self.details("- **name**: undecided: choose later\nundecided\n")), 2)

    def test_audit_items_only_unchecked_are_gaps(self):
        self.assertEqual(len(self.details("- [ ] <!-- review -->\n- [x] reviewed\n")), 1)

    def test_quoted_examples_are_ignored(self):
        for fence in ("```", "~~~", "````"):
            with self.subTest(fence=fence):
                text = f"{fence}text\n[name]\n- **goal**:\nundecided\n{fence}\n"
                self.assertEqual(self.details(text), [])
        self.assertEqual(self.details("`{name}` <!-- [name]\nundecided -->\n"), [])

    def test_code_answer_fills_field(self):
        self.assertEqual(self.details("- **form**: `thank you`\n- **flow**:\n```text\nIF x THEN y\n```\n"), [])

    def test_unclosed_fence_does_not_expose_examples(self):
        self.assertEqual(self.details("```text\n- **goal**:\nundecided\n"), [])

    def test_link_and_footnote_labels_are_not_name_blanks(self):
        self.assertEqual(self.details("[name](local.md)\n[name]: local.md\n[name][source]\n"), [])

    def test_all_shipped_narrative_placeholders_are_seen(self):
        text = "# {name} ({phase_name})\n> {One sentence description of this character in this phase}\n"
        self.assertEqual(len(self.details(text)), 3)

    def test_custom_prose_is_not_forced_into_twenty_sections(self):
        self.assertEqual(self.details("# A person\nA stated aim, with a condition and a limit.\n"), [])

    def test_comments_do_not_shift_line_numbers(self):
        found = self.details("<!-- first\nsecond -->\n- **fact**:\n")
        self.assertEqual(found[0]["line"], 3)


class PersonaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cpb-persona-workflow-")
        self.addCleanup(self.temp.cleanup)
        self.series = Path(self.temp.name) / "series"
        code, self.started = invoke(narrative_init.main, "--out", str(self.series),
                                    "--series-id", "demo", "--title", "Test series", "--medium", "prose", "--seed", "example")
        self.assertEqual(code, 0, self.started)
        self.path = self.series / "narrative/narrative.json"
        self.persona = self.series / "narrative/personas/c01.md"

    def document(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def cover(self):
        return narrative_coverage.cover(self.path, self.series / "narrative/scenes", self.series)

    def fill_persona(self, name="c01", character="C01", phase=""):
        path = self.series / f"narrative/personas/{name}.md"
        path.write_text(narrative_entity.front_matter("persona", name, name, character, phase)
                        + "\n# Synthetic persona\nA chosen action with a condition and a limit.\n",
                        encoding="utf-8")
        return path

    def phases(self):
        value = self.document()
        second = copy.deepcopy(value["chapters"][0])
        second.update(id="ch02", number=2, story_order_start=100, story_order_end=200)
        value["chapters"].append(second)
        value["characters"][0].update(
            persona="narrative/personas/c01-later.md",
            phases=[{"id": "opening", "persona": "narrative/personas/c01.md", "from_chapter": "ch01"},
                    {"id": "later", "persona": "narrative/personas/c01-later.md", "from_chapter": "ch02",
                     "changed": "Shares one specific concern.", "held": "Keeps the same practical aim."}])
        self.fill_persona(phase="opening")
        self.fill_persona("c01-later", phase="later")
        save(self.path, value)
        return value

    def test_initial_persona_uses_the_full_form(self):
        body = self.persona.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## (\d+)\.", body, re.M), [str(i) for i in range(20)])
        self.assertIn("### Action Patterns", body)
        self.assertIn("### Vocabulary Registry", body)
        self.assertIn("### Design Ledger", body)
        self.assertIn("narrative/personas/c01.md", self.started["written"])
        self.assertEqual(self.document()["medium"], "prose")

    def test_full_initial_and_added_persona_share_creation(self):
        code, report = invoke(narrative_entity.main, "--series", str(self.series), "add", "persona",
                              "c02", "--character", "C02", "--name", "Second", "--phase", "opening")
        self.assertEqual(code, 0, report)
        second = (self.series / "narrative/personas/c02.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## \d+\..*$", second, re.M),
                         re.findall(r"^## \d+\..*$", self.persona.read_text(encoding="utf-8"), re.M))
        self.assertNotIn("# Persona Template", second)
        self.assertIn("# Second (opening)", second)

    def test_unselected_phase_is_not_silently_chosen(self):
        self.assertIn("{phase_name}", self.persona.read_text(encoding="utf-8"))
        self.assertNotIn("phases", self.document()["characters"][0])
        self.assertNotIn("approved", self.document())

    def test_index_finds_full_form_gaps_and_excludes_template(self):
        report = narrative_index.scan(self.series)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["counts"]["persona"], 1)
        details = report["unfilled"]["narrative/personas/c01.md"]
        self.assertTrue(any(x["label"] == "decision_style" for x in details))
        self.assertTrue(any(x["label"] == "reputation" for x in details))
        self.assertNotIn("narrative/personas/persona-template.md", report["unfilled"])

    def test_missing_form_is_not_a_silent_short_fallback(self):
        before = tree_hashes(self.series)
        with patch.object(narrative_entity, "persona_form", return_value=None):
            code, report = invoke(narrative_entity.main, "--series", str(self.series), "add", "persona",
                                  "c02", "--character", "C02")
        self.assertEqual(code, 1)
        self.assertIn("full persona form", report["errors"][0])
        self.assertEqual(tree_hashes(self.series), before)

    def test_empty_form_is_reported(self):
        with patch.object(narrative_entity, "persona_form", return_value="  \n"):
            with self.assertRaises(ValueError):
                narrative_entity.persona_document("c02", "Second", "C02")

    def test_added_persona_exposes_identity_intent_bindings(self):
        code, report = invoke(narrative_entity.main, "--series", str(self.series), "add", "persona",
                              "c02", "--character", "C02", "--phase", "opening")
        self.assertEqual(code, 0, report)
        text = (self.series / "narrative/personas/c02.md").read_text(encoding="utf-8")
        for field in ("authorial_intent_refs", "inner_core", "signature_dynamics", "identity_realization"):
            self.assertIn("**" + field + "**:", text)

    def test_current_profile_has_scoped_continuity_review(self):
        text = narrative_entity.persona_document("c02", "Second", "C02", "opening")
        self.assertIn("## 2. PORTRAYAL IDENTITY", text)
        self.assertIn("### Core-to-Performance Bindings", text)
        self.assertIn("### Portrayal Continuity Review", text)

    def test_coverage_reports_blank_persona_and_fingerprint(self):
        report = self.cover()
        self.assertTrue(report["ok"], report["errors"])
        meta = report["chapters"][0]["personas"]["C01"]
        self.assertGreater(meta["unfilled_count"], 0)
        self.assertEqual(meta["file_sha256"], hashlib.sha256(self.persona.read_bytes()).hexdigest())

    def test_coverage_reports_missing_persona(self):
        self.persona.unlink()
        report = self.cover()
        self.assertTrue(any("selected persona file is missing" in x for x in report["gaps"]))

    def test_index_reports_unreadable_utf8_without_crashing(self):
        self.persona.write_bytes(b"\xff")
        report = narrative_index.scan(self.series)
        self.assertFalse(report["ok"])
        self.assertTrue(any("could not read the entity" in x for x in report["errors"]))

    def test_unreadable_utf8_persona_is_an_error(self):
        self.persona.write_bytes(b"\xff")
        report = self.cover()
        self.assertFalse(report["ok"])
        self.assertTrue(any("could not read the selected persona" in x for x in report["errors"]))

    def test_chapters_select_opening_and_later_not_final_for_both(self):
        self.phases()
        report = self.cover()
        self.assertTrue(report["ok"], report["errors"])
        selected = [x["personas"]["C01"] for x in report["chapters"]]
        self.assertEqual([x["phase"] for x in selected], ["opening", "later"])
        self.assertEqual([x["persona"] for x in selected],
                         ["narrative/personas/c01.md", "narrative/personas/c01-later.md"])
        self.assertEqual([x["unfilled_count"] for x in selected], [0, 0])

    def test_chapter_before_first_phase_does_not_get_later_persona(self):
        value = self.phases()
        value["characters"][0]["phases"] = [value["characters"][0]["phases"][1]]
        value["characters"][0]["phases"][0].pop("changed")
        value["characters"][0]["phases"][0].pop("held")
        save(self.path, value)
        report = self.cover()
        self.assertIsNone(report["chapters"][0]["personas"]["C01"]["persona"])
        self.assertTrue(any("every declared phase begins later" in x for x in report["gaps"]))

    def test_persona_edit_changes_fingerprint_not_json_approval(self):
        value = self.document()
        value["approved"] = {"by": "synthetic test", "at": "2026-09-16T00:00:00Z",
                             "content_sha256": narrative.content_sha256(value)}
        save(self.path, value)
        old = self.cover()["chapters"][0]["personas"]["C01"]["file_sha256"]
        self.fill_persona()
        new = self.cover()["chapters"][0]["personas"]["C01"]["file_sha256"]
        self.assertNotEqual(old, new)
        self.assertTrue(narrative.validate_narrative(self.document())["approved"])

    def test_index_and_coverage_do_not_write_or_adopt(self):
        before = tree_hashes(self.series)
        narrative_index.scan(self.series)
        self.cover()
        self.assertEqual(before, tree_hashes(self.series))
        self.assertNotIn("approved", self.document())

    def test_strict_index_succeeds_after_syntactic_gaps_are_resolved(self):
        self.fill_persona()
        def fill(value):
            if isinstance(value, dict):
                return {key: fill(item) for key, item in value.items()}
            if isinstance(value, list):
                return [fill(item) for item in value]
            return "Synthetic authored value" if value in ("undecided", "[name]", "[title]") else value
        save(self.path, fill(self.document()))
        (self.series / "narrative/design/project.md").write_text(
            narrative_entity.front_matter("design", "project", "Test", "", "")
            + "\n# Synthetic design\nScope: syntactic-completion fixture only.\n", encoding="utf-8")
        code, report = invoke(narrative_index.main, str(self.series), "--json", "--strict")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["gaps"], [])

    def test_real_cli_strict_fails_for_draft(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/narrative_index.py"),
                   str(self.series), "--json", "--strict"]
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("unfilled", json.loads(done.stdout))

    def test_two_persona_relationship_turn_joins_existing_scene_contract(self):
        self.fill_persona()
        self.fill_persona("c02", "C02")
        value = self.document()
        value["characters"].append({"id": "C02", "name": "Second", "persona": "narrative/personas/c02.md",
                                    "prohibitions": [{"kind": "judgement", "statement": "Keeps the declared boundary."}]})
        value["arcs"][0]["characters"].append("C02")
        value["relationships"] = [{"id": "r01", "from": "C01", "to": "C02", "bond_type": "stranger",
                                    "at_start": "Has not sought contact.", "arcs": ["a01"]}]
        value["approved"] = {"by": "synthetic test", "at": "2026-09-16T00:00:00Z",
                             "content_sha256": narrative.content_sha256(value)}
        save(self.path, value)
        code, _ = invoke(narrative_entity.main, "--series", str(self.series), "add", "location", "room")
        self.assertEqual(code, 0)
        plot = make_scene(self.series, "room")
        plot["characters"].append("C02")
        plot["relationship_delta"] = [{"channel": "shares-information", "between": ["C01", "C02"],
                                       "change": "Shares the practical reason for refusing.", "from": ["b2"]}]
        plot["realization"] = {"kind": "passages", "units": [{"id": "p01", "focal_beat": "b2",
            "covers": [{"statement": "The refusal gains a specific explanation.", "from": ["b1", "b2"]}],
            "mode": "scene"}]}
        self.assertTrue(scene_plot.validate_scene_plot(plot)["ok"], scene_plot.validate_scene_plot(plot)["errors"])
        save(self.series / "narrative/scenes/sc01.json", plot)
        report = self.cover()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["scenes"], 1)
        self.assertEqual(set(report["chapters"][0]["personas"]), {"C01", "C02"})
        self.assertTrue(narrative_index.scan(self.series)["ok"])
        # Negative control: a relationship change cannot cite an unseen context beat.
        plot["beats"][1]["visibility"] = "context"
        self.assertFalse(scene_plot.validate_scene_plot(plot)["ok"])


class RoutingTests(unittest.TestCase):
    def test_persona_route_and_full_form_are_direct_skill_links(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("](references/runtime/narrative-development.md)", text)
        self.assertIn("](templates/narrative/personas/persona-template.md)", text)
        self.assertIn("For world, persona or narrative work", text)

    def test_original_design_and_temporal_boundaries_are_explicit(self):
        form = (ROOT / "templates/narrative/personas/persona-template.md").read_text(encoding="utf-8")
        for text in ("Original-Character Design Mode", "hypothetical design sample", "Design Ledger",
                     "provisional", "Temporal firewall", "twenty-section workspace"):
            self.assertIn(text, form)

    def test_workflow_connects_personas_without_new_shared_artifact_keys(self):
        text = (ROOT / "references/runtime/narrative-development.md").read_text(encoding="utf-8")
        for marker in ("## 2. Develop the relevant dependencies, in either direction", "relationship_delta",
                       "from_chapter", "current state", "not the bytes of linked Markdown",
                       "Neither can establish", "not a questionnaire"):
            self.assertIn(marker, text)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    transcript = io.StringIO()
    result = unittest.TextTestRunner(stream=transcript, verbosity=2).run(suite)
    errors = [f"{case}: {detail}" for case, detail in result.failures + result.errors]
    print(json.dumps({"ok": result.wasSuccessful(), "checks": result.testsRun,
                      "skipped": [str(item) for item in result.skipped], "errors": errors}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
