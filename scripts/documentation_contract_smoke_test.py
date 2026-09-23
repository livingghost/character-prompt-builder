#!/usr/bin/env python3
"""Regression tests for the lean SKILL router and routed documentation contract."""
from __future__ import annotations

import concurrent.futures
import functools
import html
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import runtime_read_footprint
import scene_plot
from validate import (
    AUTHORITATIVE_DOCUMENT_MARKERS,
    FRESH_SESSION_RUNTIME_DOCUMENTS,
    SKILL_CHARACTERS_PER_TOKEN,
    SKILL_DIRECT_LINKS,
    SKILL_MAX_ESTIMATED_TOKENS,
    SKILL_MAX_LINES,
    SKILL_REQUIRED_ROUTER_PHRASES,
    SKILL_ROUTED_DOCUMENTS,
    _adapter_documents,
    _skill_target_adapters,
    _skill_word_count,
    check_english_content,
    check_skill_documentation_contract,
    newest_changelog_release,
)
from package_metadata import load_package_metadata
from search_discovery import ANCHOR_FACETS


ROOT = Path(__file__).resolve().parents[1]

# Help text is read for what an option is called, not for how it is painted.
# argparse colours its output when the environment asks for colour, and an agent
# or CI harness that sets FORCE_COLOR turns every assertion about help text into
# an assertion about escape sequences.
UNPAINTED = {**os.environ, "PYTHON_COLORS": "0", "NO_COLOR": "1"}


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one catalog command and return its unpainted output."""

    return subprocess.run(
        [sys.executable, "scripts/catalog_cli.py", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=UNPAINTED,
    )


class DocumentationContractSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="cpb-doc-contract-")
        self.root = Path(self._temporary.name)
        self._write_valid_fixture()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")

    def _write_valid_fixture(self) -> None:
        skill_lines = [
            "---",
            "name: character-prompt-builder",
            "description: Build prompts through a lean routed runtime contract.",
            "---",
            "",
            *SKILL_REQUIRED_ROUTER_PHRASES,
            "",
        ]
        skill_lines.extend(
            f"[Route {index}]({relative})"
            for index, relative in enumerate(SKILL_ROUTED_DOCUMENTS, start=1)
        )
        skill_lines.extend(
            f"[Prompt {index}]({relative})"
            for index, relative in enumerate(SKILL_DIRECT_LINKS, start=1)
        )
        direct_routes = [
            relative
            for relative in AUTHORITATIVE_DOCUMENT_MARKERS
            if relative not in SKILL_ROUTED_DOCUMENTS
        ]
        skill_lines.extend(
            f"[Nested authority {index}]({relative})"
            for index, relative in enumerate(direct_routes, start=1)
        )
        self._write("SKILL.md", "\n".join(skill_lines))

        for relative, markers in AUTHORITATIVE_DOCUMENT_MARKERS.items():
            body = list(markers)
            if relative == "references/runtime/image-generation.md":
                body.extend(
                    f"[Adapter {index}](../adapters/{Path(adapter).name})"
                    for index, adapter in enumerate(
                        (
                            candidate
                            for candidate in SKILL_ROUTED_DOCUMENTS
                            if candidate.startswith("references/adapters/")
                        ),
                        start=1,
                    )
                )
            self._write(relative, "\n\n".join(body))

    def _errors(self) -> list[str]:
        errors: list[str] = []
        check_skill_documentation_contract(self.root, errors)
        return errors

    def test_valid_contract_passes(self) -> None:
        self.assertEqual([], self._errors())

    def test_frontmatter_rejects_release_metadata(self) -> None:
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8").replace(
            "description: Build prompts through a lean routed runtime contract.\n",
            "description: Build prompts through a lean routed runtime contract.\n"
            'unsupported_field: arbitrary\n',
        )
        self._write("SKILL.md", text)
        self.assertTrue(
            any("front matter must contain exactly name and description" in error for error in self._errors())
        )

    def test_preparation_and_material_reuse_have_distinct_reads(self) -> None:
        from execution_routes import resolve
        preparing = {x['path'] for x in resolve('performance')['reads']}
        reusing = {x['path'] for x in resolve('performance', ['scene-persona'])['reads']}
        self.assertIn('templates/narrative/personas/persona-template.md', preparing)
        self.assertIn('references/runtime/scene-persona.md', reusing)
        self.assertNotIn('templates/narrative/personas/persona-template.md', reusing)

    def test_line_limit_is_enforced(self) -> None:
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8") + ("filler\n" * (SKILL_MAX_LINES + 1))
        self._write("SKILL.md", text)
        self.assertTrue(
            any(f"{SKILL_MAX_LINES}-line limit" in error for error in self._errors())
        )

    def test_estimated_token_limit_is_enforced(self) -> None:
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        limit = SKILL_MAX_ESTIMATED_TOKENS * SKILL_CHARACTERS_PER_TOKEN
        at_limit = text + "x" * (limit - len(text) - 1) + "\n"
        path.write_text(at_limit, encoding="utf-8", newline="\n")
        self.assertEqual([], self._errors())
        path.write_text(at_limit + "x", encoding="utf-8", newline="\n")
        self.assertTrue(
            any(f"{SKILL_MAX_ESTIMATED_TOKENS}-token limit" in error for error in self._errors())
        )

    def test_required_route_link_is_enforced(self) -> None:
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8").replace(
            f"]({SKILL_ROUTED_DOCUMENTS[0]})",
            "](references/not-the-authority.md)",
        )
        self._write("SKILL.md", text)
        self.assertTrue(
            any("does not route the required document" in error for error in self._errors())
        )

    def test_named_route_feature_routes_and_reaches_its_documents(self) -> None:
        required = SKILL_ROUTED_DOCUMENTS[0]
        specialist = "references/specialist.md"
        adapter = "references/adapters/stray-surface.md"
        self._write(specialist, "# Specialist\n\nA route read delivers this document.")
        self._write(adapter, "# Stray Surface Adapter")
        manifest = {
            "always_read": [],
            "routes": {},
            "features": {"specialist": {"reads": [required, specialist, adapter], "source_roles": []}},
        }
        self._write("config/execution-routes.json", json.dumps(manifest))
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8").replace(f"]({required})", "](references/not-the-authority.md)")
        self._write("SKILL.md", text)
        unnamed = self._errors()
        for relative in (required, specialist, adapter):
            self.assertTrue(any(error.endswith(relative) for error in unnamed), relative)
        self._write("SKILL.md", text + "\nAdd feature `specialist` for a specialist subject.")
        self.assertEqual([], self._errors())

    def test_conversational_prompt_document_needs_its_own_link(self) -> None:
        relative = SKILL_DIRECT_LINKS[-1]
        manifest = {"always_read": [], "routes": {},
                    "features": {"prompt-help": {"reads": [relative], "source_roles": []}}}
        self._write("config/execution-routes.json", json.dumps(manifest))
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8").replace(f"]({relative})", "](references/not-the-authority.md)")
        self._write("SKILL.md", text + "\nAdd feature `prompt-help` for prompt help.")
        self.assertTrue(
            any(
                error == f"SKILL.md does not link the conversational prompt document: {relative}"
                for error in self._errors()
            )
        )

    def test_judgment_automation_boundary_is_enforced(self) -> None:
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8").replace(
            "Keep judgment and automation separate.\n",
            "",
        )
        self._write("SKILL.md", text)
        self.assertTrue(
            any("Keep judgment and automation separate." in error for error in self._errors())
        )

    def test_authoritative_marker_is_enforced(self) -> None:
        relative = "references/runtime/prompt-composition.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8").replace(
            "Search is discovery, not authority.",
            "Search can be used as authority.",
        )
        self._write(relative, text)
        self.assertTrue(
            any("missing contract marker" in error for error in self._errors())
        )

    def test_model_adapter_cannot_own_another_adapter_heading(self) -> None:
        relative = "references/adapters/gpt-image.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8") + "\n# FLUX Adapter\n"
        self._write(relative, text)
        self.assertTrue(
            any("contains another adapter heading" in error for error in self._errors())
        )

    def test_authority_heading_has_one_owner(self) -> None:
        relative = "references/runtime/sparse-discovery.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8") + "\n# Prompt Composition Runtime\n"
        self._write(relative, text)
        self.assertTrue(
            any("contains authority heading owned by" in error for error in self._errors())
        )

    def test_unreachable_reference_document_is_rejected(self) -> None:
        relative = "references/dead-feature.md"
        self._write(relative, "# Dead Feature\n\nNo routed authority links here.")
        self.assertTrue(
            any(
                f"reached by no SKILL.md link or named route or feature: {relative}" in error
                for error in self._errors()
            )
        )

    def test_undocumented_script_entrypoint_is_rejected(self) -> None:
        script_name = "dead_cli.py"
        self._write(
            f"scripts/{script_name}",
            "if __name__ == '__main__':\n    raise SystemExit(0)",
        )
        self.assertTrue(
            any(
                f"unreachable from routed Skill documentation: {script_name}" in error
                for error in self._errors()
            )
        )

    def test_prompt_runtime_rejects_state_builder_command(self) -> None:
        relative = "references/runtime/prompt-composition.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8") + "\nscripts/build_state_generation_package.py\n"
        self._write(relative, text)
        self.assertTrue(
            any("prompt-composition runtime must not embed" in error for error in self._errors())
        )

    def test_live_repository_contract(self) -> None:
        errors: list[str] = []
        check_skill_documentation_contract(ROOT, errors)
        self.assertEqual([], errors)

    def test_live_context_measurement_counts_consumed_cli_outputs(self) -> None:
        errors: list[str] = []
        observed = check_skill_documentation_contract(ROOT, errors)
        self.assertEqual([], errors)
        cli_words = observed["fresh-session consumed CLI words"]
        self.assertEqual(
            {"catalog batch --help", "reference_runtime example plan"},
            set(cli_words),
        )
        self.assertTrue(all(value > 0 for value in cli_words.values()))
        document_words = _skill_word_count(
            (ROOT / "SKILL.md").read_text(encoding="utf-8")
        ) + sum(
            _skill_word_count((ROOT / relative).read_text(encoding="utf-8"))
            for relative in FRESH_SESSION_RUNTIME_DOCUMENTS
        )
        total = observed["fresh-session sparse prompt-artifacts words"]
        self.assertEqual(document_words + sum(cli_words.values()), total)
        self.assertGreater(total, 0)

    def test_footprint_tool_reports_static_words_without_quality_claim(self) -> None:
        self.assertIs(runtime_read_footprint.count_words, _skill_word_count)
        result = subprocess.run(
            [sys.executable, "scripts/runtime_read_footprint.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=UNPAINTED,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("static-lexical-words-not-host-tokens", report["measurement"])
        for route in report["routes"].values():
            # The host loads SKILL.md itself; a route read never repeats it.
            self.assertNotIn("SKILL.md", [entry["path"] for entry in route["files"]])
            for entry in route["files"]:
                self.assertFalse(entry["missing"], entry["path"])
                self.assertEqual(
                    _skill_word_count(
                        (ROOT / entry["path"]).read_text(encoding="utf-8")
                    ),
                    entry["words"],
                    entry["path"],
                )

    def test_routed_detail_has_no_fixed_aggregate_limit(self) -> None:
        relative = "references/runtime/prompt-composition.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8") + ("preserved detail " * 5000)
        self._write(relative, text)
        self.assertEqual([], self._errors())

    def test_catalog_batch_is_routed_and_self_describing(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        sparse = (ROOT / "references/runtime/sparse-discovery.md").read_text(
            encoding="utf-8"
        )
        result = run_cli("batch", "--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("`batch`", skill)
        self.assertIn("batch --input", sparse)
        self.assertIn('"request_id":"identity"', sparse)
        self.assertIn("Supported commands: search, recommend, and inspire", result.stdout)
        example_line = result.stdout.strip().splitlines()[-1]
        example = json.loads(example_line)
        self.assertIsInstance(example, list)
        self.assertEqual("identity", example[0]["request_id"])

    def test_retrieval_recording_is_routed_and_accepted(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--record lookups.json --element NAME", skill)
        self.assertIn("prompt_retrieval.py lookups.json --element NAME --adopted ID", skill)
        for command in ("search", "inspect", "inspect-many", "batch"):
            result = run_cli(command, "--help")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("--record PATH", result.stdout, command)
        marking = subprocess.run(
            [sys.executable, "scripts/prompt_retrieval.py", "--help"],
            cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", env=UNPAINTED,
        )
        for option in ("--element", "--adopted ID", "--composed TEXT", "--reason"):
            self.assertIn(option, marking.stdout)

    def test_inspect_output_file_is_routed_and_discoverable(self) -> None:
        sparse = (ROOT / "references/runtime/sparse-discovery.md").read_text(
            encoding="utf-8"
        )
        result = run_cli("inspect", "--help")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("inspect <record-id> --out <path>", sparse)
        self.assertIn("--out PATH", result.stdout)

    def test_reference_plan_schema_and_example_are_routed(self) -> None:
        reference = (
            ROOT / "references/runtime/reference-prompt-artifacts.md"
        ).read_text(encoding="utf-8")
        for arguments, routed_command in (
            (("example", "plan"), "reference_runtime.py example plan"),
            (
                ("schema", "surface-lighting-plan"),
                "reference_runtime.py schema surface-lighting-plan",
            ),
        ):
            result = subprocess.run(
                [sys.executable, "scripts/reference_runtime.py", *arguments],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(routed_command, reference)
            self.assertIsInstance(json.loads(result.stdout), dict)

    def test_visual_preflight_is_conditionally_routed(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        generation = (ROOT / "references/runtime/image-generation.md").read_text(
            encoding="utf-8"
        )
        prompt_artifacts = (
            ROOT / "references/runtime/reference-prompt-artifacts.md"
        ).read_text(encoding="utf-8")
        self.assertIn("dependency preflight", skill.lower())
        self.assertIn(
            "python scripts/check_dependencies.py --profile visual", generation
        )
        self.assertIn("prompt-artifacts", prompt_artifacts)
        self.assertIn("Core", prompt_artifacts)
        self.assertIn("Do not install Visual dependencies", prompt_artifacts)

    def test_svg_reference_prompt_synthesis_is_routed(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = (
            ROOT / "references/visual-reference-activation-and-transport.md"
        ).read_text(encoding="utf-8")
        generation = (ROOT / "references/runtime/image-generation.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Treat every selected SVG as bounded evidence, not as the whole requested image.",
            skill,
        )
        for marker in (
            "## Semantic reading",
            "## Role map",
            "## Reference-to-prompt synthesis",
            "## Review",
            "preserve authorized evidence",
            "replace conflicting source content",
            "add target content",
            "omit contamination",
        ):
            self.assertIn(marker, reference)
        self.assertIn(
            "complete the semantic reading and reference-to-prompt synthesis",
            generation,
        )

    def test_prompt_writing_guide_is_an_executed_rendition_stage(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        runtime = (ROOT / "references/runtime/prompt-writing-guide.md").read_text(encoding="utf-8")
        generation = (ROOT / "references/runtime/image-generation.md").read_text(encoding="utf-8")
        prompt_only = (ROOT / "references/runtime/prompt-only-core.md").read_text(encoding="utf-8")
        composition = (ROOT / "references/runtime/prompt-composition.md").read_text(encoding="utf-8")
        output_template = (ROOT / "templates/output-template.md").read_text(encoding="utf-8")

        self.assertIn("resolve the optional `prompt-writing-guide`", skill)
        self.assertIn("read the complete selected guide before final rendition", skill)
        self.assertIn("## Prompt rendition gate", generation)
        self.assertIn("resolve and read the complete guide before final rendition", generation)
        self.assertIn("Generation builders commit the supplied final rendition", generation)
        self.assertIn("Treat this as the master prompt", prompt_only)
        self.assertIn("This reviewed wording is the master prompt", composition)
        self.assertIn("already rendered for the named target", output_template)
        self.assertIn("The Skill-using agent decides which rules are relevant.", runtime)

        targets = _skill_target_adapters(skill, ROOT)
        self.assertNotEqual((), targets)
        for adapter in targets:
            body = (ROOT / adapter).read_text(encoding="utf-8")
            self.assertIn("Prompt Writing Guide Runtime", body, adapter)

    def test_specification_example_manifests_satisfy_the_pack_schema(self) -> None:
        """The manifest the specification shows is one the schema accepts."""

        from state_protocol import validate_against_schema

        specification = (
            ROOT / "references/pack-format-specification.md"
        ).read_text(encoding="utf-8")
        schema = json.loads(
            (ROOT / "schemas/pack.schema.json").read_text(encoding="utf-8")
        )
        examples: list[dict[str, object]] = []
        for block in specification.split("```json")[1:]:
            body = block.split("```")[0]
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and {
                "pack_id",
                "content",
                "license",
            } <= set(value):
                examples.append(value)
        self.assertNotEqual(
            [],
            examples,
            "the specification shows no example pack manifest to check",
        )
        for example in examples:
            self.assertEqual([], validate_against_schema(example, schema))

    def test_unrouted_adapter_document_is_rejected(self) -> None:
        self._write(
            "references/adapters/stray-surface.md",
            "# Stray Surface Adapter",
        )
        self.assertTrue(
            any(
                "does not route the adapter document" in error
                for error in self._errors()
            )
        )
        self.assertIn(
            "references/adapters/stray-surface.md",
            _adapter_documents(self.root),
        )

    def test_changelog_current_release_matches_product_calver(self) -> None:
        from release_contract import validate_changelog
        from package_metadata import pep440_version_for_calver
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        metadata = load_package_metadata(ROOT)
        self.assertEqual(metadata.version, newest_changelog_release(text))
        self.assertEqual([], validate_changelog(text, metadata.version, style="plain"))
        self.assertEqual(pep440_version_for_calver(metadata.version), metadata.pyproject_version)
        self.assertEqual("YYYY.MM.DD.N", metadata.version_scheme)
        self.assertEqual("UTC", metadata.release_timezone)

    def test_release_validation_step_three_names_existing_reports(self) -> None:
        document = (ROOT / "references/release/validation.md").read_text(encoding="utf-8")
        steps = [line for line in document.splitlines() if line.startswith("3. ")]
        self.assertEqual(1, len(steps), steps)
        names = [
            re.sub(r"^<[^>]+>", "", value)
            for value in re.findall(r"`([^`]+)`", steps[0])
        ]
        self.assertTrue(names, steps[0])
        packager = (ROOT / "scripts/package.py").read_text(encoding="utf-8")
        self.assertEqual([], [name for name in names if name not in packager])

    def test_language_gate_covers_routed_runtime_documents(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-language-gate-") as temporary:
            root = Path(temporary)
            runtime = root / "references" / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "ok.md").write_text(
                "# Routed\n\nThis document is written in English.\n",
                encoding="utf-8",
                newline="\n",
            )
            samples = {
                "bad-ko.md": "# Routed\n\n\uc774 \ubb38\uc11c\ub294 \ud55c\uad6d\uc5b4\ub85c \uc4f0\uc600\ub2e4.\n",
                "bad-zh.md": "# Routed\n\n\u8fd9\u4efd\u6587\u4ef6\u662f\u4e2d\u6587\u7684\u3002\n",
                "bad-ja.md": "# Routed\n\n\u3053\u308c\u306f\u65e5\u672c\u8a9e\u3067\u3042\u308b\u3002\n",
                "bad-ru.md": "# Routed\n\n\u042d\u0442\u043e\u0442 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c.\n",
            }
            for name, text in samples.items():
                (runtime / name).write_text(text, encoding="utf-8", newline="\n")
            errors = check_english_content(root)
            self.assertEqual(len(samples), len(errors), errors)
            for name in samples:
                with self.subTest(document=name):
                    self.assertTrue(
                        any(f"references/runtime/{name}:3" in error for error in errors),
                        errors,
                    )

    def test_language_gate_reads_code_spans_and_fences_and_passes_accented_latin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cpb-language-span-") as temporary:
            root = Path(temporary)
            runtime = root / "references" / "runtime"
            runtime.mkdir(parents=True)
            document = runtime / "sample.md"
            document.write_text(
                "Zo\u00eb's caf\u00e9 r\u00e9sum\u00e9, \u00c6r\u00f8 and na\u00efve pass; "
                "so do \u00a7 12, 3 \u00d7 4 and \u201cquotes\u201d.\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertEqual([], check_english_content(root))

            document.write_text(
                "A form such as `\ud55c\uae00` is data.\n", encoding="utf-8", newline="\n"
            )
            spanned = check_english_content(root)
            self.assertEqual(1, len(spanned), spanned)
            self.assertIn("references/runtime/sample.md:1 (\ud55c\uae00)", spanned[0])

            document.write_text(
                "```python\n# \uc8fc\uc11d\n```\n", encoding="utf-8", newline="\n"
            )
            fenced = check_english_content(root)
            self.assertEqual(1, len(fenced), fenced)
            self.assertIn("references/runtime/sample.md:2", fenced[0])

            document.write_text(
                "Only \u3002 and \uff01 remain.\n", encoding="utf-8", newline="\n"
            )
            self.assertEqual(1, len(check_english_content(root)))

    def test_character_sheet_uses_existing_reference_authority_runtime(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        sheet = (ROOT / "references/runtime/character-sheet-discipline.md").read_text(encoding="utf-8")
        visual = (ROOT / "references/visual-reference-activation-and-transport.md").read_text(encoding="utf-8")
        self.assertIn("one ordinary Reference Use Plan", skill)
        self.assertIn("Build one Reference Use Plan and one Prepared Reference Set", sheet)
        self.assertIn("Registered Character Sheet identity with other evidence", visual)
        self.assertIn("supplied-file-only preparation", visual)
        self.assertFalse((ROOT / "references/adapters/role-scoped-evidence-transport.md").exists())

    def test_focalization_field_names_every_kind_that_may_carry_through(self) -> None:
        """The focalization field reads for every kind the reader takes `through` from.

        This compares strings only. That the field describes the kinds correctly
        in general is not automated here.
        """

        document = (ROOT / "references/narrative-protocol.md").read_text(encoding="utf-8")
        field: list[str] = []
        for line in document.splitlines():
            if field:
                if line.startswith(" "):
                    field.append(line)
                    continue
                break
            if line.startswith("focalization"):
                field.append(line)
        self.assertTrue(field, "the contract carries no focalization field")
        entry = "\n".join(field)
        for kind in ("internal", "external"):
            self.assertIn(kind, scene_plot.FOCALIZATIONS)
            self.assertIn(kind, entry, f"the focalization field does not name {kind}")

    def test_bundled_query_examples_name_real_anchor_facets(self) -> None:
        """A shipped example must not spell an anchor facet the runtime refuses."""

        template = json.loads(
            (ROOT / "templates/catalog-query-template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(template.get("anchors"))
        self.assertLessEqual(set(template["anchors"]), ANCHOR_FACETS)

        document = (ROOT / "references/runtime/sparse-discovery.md").read_text(
            encoding="utf-8"
        )
        blocks = re.findall(r"```json\n(.*?)```", document, re.DOTALL)
        self.assertTrue(blocks, "the sparse discovery document carries no example")
        checked = 0
        for block in blocks:
            example = json.loads(block)
            if not isinstance(example, dict):
                continue
            for key in ("anchors", "normalized_anchors"):
                facets = example.get(key)
                if not isinstance(facets, dict):
                    continue
                checked += 1
                self.assertLessEqual(
                    set(facets),
                    ANCHOR_FACETS,
                    f"{key} names a facet the analyzer does not define",
                )
        self.assertTrue(checked, "no documented anchor example was checked")


class RegressionExecutionTests(unittest.TestCase):
    def invoke(self, stdout, stderr, returncode, output_format):
        from unittest.mock import patch
        from validate import run_standalone_regression
        result = subprocess.CompletedProcess(["fixture"], returncode, stdout, stderr)
        with patch("validate.subprocess.run", return_value=result):
            return run_standalone_regression(ROOT, "fixture.py", output_format=output_format)

    def test_json_report_cannot_hide_failed_exit(self):
        self.assertFalse(self.invoke('{"ok": true}', '', 1, 'json')['ok'])
        self.assertFalse(self.invoke('not-json', '', 0, 'json')['ok'])
        self.assertFalse(self.invoke('[]', '', 0, 'json')['ok'])
        self.assertTrue(self.invoke('{"ok": true}', '', 0, 'json')['ok'])

    def test_unittest_must_execute_cases(self):
        self.assertFalse(self.invoke('', 'No tests ran', 0, 'unittest')['ok'])
        self.assertFalse(self.invoke('', 'Ran 0 tests in 0s\nOK', 0, 'unittest')['ok'])
        self.assertFalse(self.invoke('', 'Ran 2 tests in 0s\nFAILED', 1, 'unittest')['ok'])
        self.assertTrue(self.invoke('', 'Ran 2 tests in 0s\nOK', 0, 'unittest')['ok'])



class ReadmeReleaseExplanationTests(unittest.TestCase):
    def test_readme_can_explain_product_release_management(self):
        from validate import check_documentation
        errors = []
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("YYYY.MM.DD.N", readme)
        self.assertIn("CalVer", readme)
        self.assertIn("UTC", readme)
        check_documentation(ROOT, errors)
        self.assertEqual([], errors)

    def test_readme_release_explanation_keeps_authority_link(self):
        from unittest.mock import patch
        from validate import check_documentation
        read = Path.read_text
        def without_manifest_link(path, *args, **kwargs):
            text = read(path, *args, **kwargs)
            if path == ROOT / "README.md":
                return text.replace("](package-manifest.toml)", "]")
            return text
        errors = []
        with patch.object(Path, "read_text", without_manifest_link):
            check_documentation(ROOT, errors)
        self.assertIn("README must link to package-manifest.toml", errors)


DOCUMENTED_COMMAND = re.compile(r"\bpython3? scripts/(\w+)\.py\b")
FENCE = re.compile(r"^(```|~~~)[^\n]*\n(.*?)^\1[ \t]*$", re.M | re.S)
SHELL_BREAKS = {"|", "||", "&&", ";", ">", ">>", "<", "&"}


def documented_commands() -> list[tuple[str, str]]:
    """Every `python scripts/<name>.py ...` command in the routed documents, with the document that shows it."""

    documents = [ROOT / "README.md", ROOT / "SKILL.md", *sorted((ROOT / "references").rglob("*.md"))]
    documents += sorted(path for path in (ROOT / "templates").rglob("*") if path.suffix in {".md", ".html"})
    commands: list[tuple[str, str]] = []
    for document in documents:
        text = document.read_text(encoding="utf-8")
        if document.suffix == ".html":
            text = html.unescape(text)
        # A fenced line that ends in a continuation character goes on to the next line.
        lines = [line for fence in FENCE.finditer(text)
                 for line in re.sub(r"[ \t]*[\\`^]\n[ \t]*", " ", fence.group(2)).splitlines()]
        lines += re.findall(r"`([^`\n]+)`", FENCE.sub("", text))
        for line in lines:
            for match in DOCUMENTED_COMMAND.finditer(line):
                command = re.split(r"\s#", line[match.start():], maxsplit=1)[0].strip()
                commands.append((document.relative_to(ROOT).as_posix(), command))
    return commands


def is_value(word: str) -> bool:
    """A placeholder in angle brackets or capitals, a shell variable, or an ellipsis stands for a value."""

    return "<" in word or "$" in word or word == "..." or bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", word))


def parses_arguments(script: Path) -> bool:
    """Whether the script, or the module whose main it runs, reads its command line with argparse."""

    text = script.read_text(encoding="utf-8")
    if "argparse" in text:
        return True
    for module, names in re.findall(r"^from (\w+) import (\([^)]*\)|[^\n]*)", text, re.M):
        source = script.with_name(module + ".py")
        if re.search(r"\bmain\b", names) and source.is_file() and "argparse" in source.read_text(encoding="utf-8"):
            return True
    return False


@functools.lru_cache(maxsize=None)
def script_help(words: tuple[str, ...]) -> str:
    """The --help of a script, or of one of its subcommands; empty when --help fails."""

    result = subprocess.run(
        [sys.executable, f"scripts/{words[0]}.py", *words[1:], "--help"],
        cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**UNPAINTED, "COLUMNS": "200", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return result.stdout if result.returncode == 0 else ""


def subcommand_choices(help_text: str) -> set[str]:
    positional = help_text.partition("positional arguments:")[2].partition("options:")[0]
    match = re.search(r"^\s+\{([^}]+)\}", positional, re.M)
    return set(match.group(1).split(",")) if match else set()


def option_arity(help_text: str, option: str) -> str:
    """'' for a switch, 'one' for an option that takes a value, 'many' for one that takes a list."""

    match = re.search(re.escape(option) + r"(?:[ =]([A-Z_{<\[][^\s,]*)( \[[^\]]*\.\.\.\])?)?(?=[\s,\]])", help_text)
    if not match or not match.group(1):
        return ""
    return "many" if match.group(2) else "one"


def command_problems(command: str) -> list[str]:
    """Check one documented command against the --help of its script and of each subcommand it names."""

    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    for index, word in enumerate(words):
        if word in SHELL_BREAKS or word.startswith((">", "2>")):
            words = words[:index]
            break
    name = re.fullmatch(r"scripts/(\w+)\.py", words[1]).group(1)
    script = ROOT / "scripts" / f"{name}.py"
    if not script.is_file():
        return [f"scripts/{name}.py does not exist"]
    arguments = words[2:]
    if not arguments:
        return []
    if not parses_arguments(script):
        return [f"{name}.py reads no options"] if any(word.startswith("-") for word in arguments) else []
    level: tuple[str, ...] = (name,)
    text = script_help(level)
    if not text:
        return [f"{name}.py --help failed"]
    problems: list[str] = []
    choosing = True
    index = 0
    while index < len(arguments):
        word = arguments[index].strip("[]")
        index += 1
        if re.fullmatch(r"--?[A-Za-z][\w-]*(=.*)?", word):
            option = word.split("=", 1)[0]
            if not re.search(r"(?<![\w-])" + re.escape(option) + r"(?![\w-])", text):
                problems.append(f"{' '.join(level)} --help names no option {option}")
                continue
            arity = "" if "=" in word else option_arity(text, option)
            if arity == "one":
                index += 1
            elif arity == "many":
                while index < len(arguments) and not arguments[index].startswith("-"):
                    index += 1
            continue
        choices = subcommand_choices(text) if choosing else set()
        if not choices:
            continue
        if is_value(word):
            break
        if word not in choices:
            problems.append(f"{' '.join(level)} --help names no subcommand {word}")
            break
        child = script_help((*level, word))
        if re.search(r"^usage: \S+ " + re.escape(" ".join((*level[1:], word))) + r"\b", child, re.M):
            level, text = (*level, word), child
        else:
            # The choice was the value of a positional argument, not a subcommand.
            choosing = False
    return problems


class DocumentedCommandTests(unittest.TestCase):
    maxDiff = None

    def test_documented_commands_match_each_script_help(self) -> None:
        commands = documented_commands()
        self.assertTrue(commands, "no documented command was found")
        unique = sorted({command for _, command in commands})
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            problems = dict(zip(unique, pool.map(command_problems, unique)))
        self.assertEqual(
            [],
            [f"{document}: {command}: {problem}" for document, command in commands for problem in problems[command]],
        )


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
