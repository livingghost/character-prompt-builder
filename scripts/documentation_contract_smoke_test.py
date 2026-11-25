#!/usr/bin/env python3
"""Regression tests for the lean SKILL router and routed documentation contract."""
from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Callable
import concurrent.futures
import html
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
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
    _route_deliveries,
    _skill_target_adapters,
    _skill_word_count,
    check_english_content,
    check_skill_documentation_contract,
    markdown_anchor_slugs,
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
        required = next(path for path in SKILL_ROUTED_DOCUMENTS if path not in SKILL_DIRECT_LINKS)
        specialist = "references/specialist.md"
        adapter = "references/adapters/stray-surface.md"
        self._write(specialist, "# Specialist\n\nA route read delivers this document.")
        self._write(adapter, "# Stray Surface Adapter")
        manifest = {
            "operation_contexts": {},
            "routes": {},
            "features": {"specialist": {"reads": [path.removesuffix('.md') for path in (required, specialist, adapter)],
                                          "source_roles": []}},
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

    def test_core_authoring_document_is_directly_reachable(self) -> None:
        relative = SKILL_DIRECT_LINKS[-1]
        manifest = {"operation_contexts": {}, "routes": {},
                    "features": {"prompt-help": {"reads": [relative.removesuffix('.md')], "source_roles": []}}}
        self._write("config/execution-routes.json", json.dumps(manifest))
        path = self.root / "SKILL.md"
        text = path.read_text(encoding="utf-8").replace(f"]({relative})", "](references/not-the-authority.md)")
        self._write("SKILL.md", text + "\nAdd feature `prompt-help` for prompt help.")
        self.assertTrue(
            any(
                error == f"SKILL.md does not link the core authoring document: {relative}"
                for error in self._errors()
            )
        )

    def test_route_reachability_resolves_operation_and_transitive_feature_document_ids(self) -> None:
        manifest = {
            'features': {
                'specialist': {'reads': ['references/specialist'],
                               'execution_features': {'dispatcher': ['transport']}},
                'transport': {'reads': ['references/transport']},
            },
            'operation_contexts': {'prepare': {'reads': ['references/preparation'],
                                              'executions': {'dispatcher': ['references/dispatch']}}},
            'routes': {'production': {'reads': ['references/production'], 'features': ['specialist']}},
        }
        self._write('config/execution-routes.json', json.dumps(manifest))
        deliveries = _route_deliveries(self.root)
        self.assertEqual(deliveries['specialist'], ('references/specialist.md', 'references/transport.md'))
        self.assertEqual(deliveries['production'], tuple('references/' + name + '.md'
                         for name in ('dispatch', 'preparation', 'production', 'specialist', 'transport')))

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

    def test_authoritative_section_is_required(self) -> None:
        relative = "references/runtime/prompt-composition.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8").replace(
            "## Catalog retrieval and inspection",
            "",
        )
        self._write(relative, text)
        self.assertTrue(
            any("missing contract marker" in error for error in self._errors())
        )

    def test_model_adapter_cannot_own_another_adapter_heading(self) -> None:
        relative = "references/adapters/gpt-image.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8") + "\n# NovelAI Adapter\n"
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


    def test_routed_detail_has_no_fixed_aggregate_limit(self) -> None:
        relative = "references/runtime/prompt-composition.md"
        path = self.root / relative
        text = path.read_text(encoding="utf-8") + ("preserved detail " * 5000)
        self._write(relative, text)
        self.assertEqual([], self._errors())


    def test_prompt_work_routes_to_the_actual_candidate_owner(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        owner = "references/runtime/authoring-work.md"
        self.assertIn(f"]({owner})", skill.partition("## Core contract")[2].partition("\n## ")[0])
        paths = skill.partition("## Choose a runtime path")[2].partition("\n- ")[0]
        core = "references/runtime/prompt-only-core.md"
        self.assertIn(f"]({core})", paths)
        routes = json.loads((ROOT / "config/execution-routes.json").read_text(encoding="utf-8"))
        self.assertIn(core.removesuffix('.md'), routes["routes"]["prompt-only"]["reads"])
        for operation in ("author", "save", "prepare", "review"):
            self.assertIn(owner.removesuffix('.md'), routes["operation_contexts"][operation]["reads"])

        authoring = (ROOT / owner).read_text(encoding="utf-8")
        self.assertIn("../../schemas/authoring/authoring-work.schema.json", authoring)
        for command in ("begin", "context", "edit", "replace-text", "inspect", "check", "extract", "export"):
            self.assertIn(f"scripts/authoring_work.py {command}", authoring)
        run = subprocess.run(
            [sys.executable, str(ROOT / "scripts/authoring_work.py"), "--help"],
            cwd=self.root, env=UNPAINTED, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        for command in ("begin", "context", "edit", "replace-text", "inspect", "check", "extract", "export"):
            self.assertIn(command, run.stdout)

        gate = skill.partition("## Artifact-bearing production gate")[2].partition("\n## ")[0]
        route_command = "`python scripts/execution_routes.py read --root STUDIO --choices FILE --all --view text`"
        self.assertIn(route_command, gate)
        self.assertEqual(1, skill.count(route_command))
        for marker in ("--choices", "actions.continue", "reading.record", "--fresh-context",
                       "--reading-context", "reread after compaction"):
            self.assertIn(marker, gate)

        sequence = skill.partition("## Start the current work")[2].partition("\n## ")[0]
        workflow_path = "references/runtime/production-workflow.md"
        self.assertIn(f"]({workflow_path}#read-the-current-stage)", sequence)
        for marker in ("production-work-plan.md", "plan --root STUDIO", "advance", "answer file", "compaction"):
            self.assertIn(marker, sequence)
        workflow = (ROOT / workflow_path).read_text(encoding="utf-8")
        self.assertIn("](authoring-work.md)", workflow)
        self.assertIn("complete contract for the current operation", workflow)
        self.assertIn("execution_routes.py read ROUTE --operation OPERATION --execution EXECUTION --root STUDIO", workflow)
        production_authoring = (ROOT / "references/runtime/production-authoring.md").read_text(encoding="utf-8")
        self.assertIn("--model-file FILE", production_authoring)

    def test_indexed_reading_guidance_matches_the_delivery_cli(self) -> None:
        document = (ROOT / "references/runtime/production-authoring.md").read_text(encoding="utf-8")
        reading = document.partition("### Select and read the current knowledge")[2].partition("\n## ")[0]
        for marker in ("actions.continue", "`argv`", "`command: read`", "`reason`", "`body`", "`null`",
                       "--reading-ledger", "CPB_READS_LEDGER", "reading.record", "--known-reading",
                       "actions.next", "actions.all", "--snapshot", "--section", "--all", "non-null",
                       "--fresh-context", "--reading-context", "--host-page-bytes"):
            self.assertIn(marker, reading)
        run = subprocess.run([sys.executable, str(ROOT / "scripts/execution_routes.py"), "read", "--help"],
                             cwd=self.root, env=UNPAINTED, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        for option in ("--page-bytes", "--continue", "--replay", "--reading-ledger", "--known-reading",
                       "--snapshot", "--section", "--all", "--fresh-context",
                       "--reading-context", "--bind-choices", "--host-page-bytes"):
            self.assertIn(option, run.stdout)
        from route_reading import INDEX_SOURCE_STATES
        for state in INDEX_SOURCE_STATES:
            self.assertIn('`' + state + '`', reading)
            self.assertIn(state + ':', run.stdout)

    def test_pack_quickstart_registration_example_runs_in_its_selected_runtime(self) -> None:
        from shutil import copytree
        from pack_manager import write_lock

        document = (ROOT / "references/runtime/pack-state-quickstart.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```bash\n(.*?)\n```", document, flags=re.S)
        commands = [block for block in blocks if "root-add PACK_OR_CONTAINER" in block]
        self.assertEqual(len(commands), 1)
        argv = shlex.split(commands[0].replace("\\\n", " "))
        self.assertEqual(argv[:2], ["python", "scripts/pack_cli.py"])
        container = self.root / "documented pack container"
        pack = container / "example pack"
        copytree(ROOT / "examples/pack-authoring/minimal-pack", pack)
        write_lock(pack)
        selected = self.root / "documented runtime"
        caller = self.root / "different caller"
        caller.mkdir()
        substitutions = {
            "python": sys.executable,
            "scripts/pack_cli.py": str(ROOT / "scripts/pack_cli.py"),
            "TASK_PACK_STATE_JSON": str(selected / "state.json"),
            "TASK_CATALOG_CACHE": str(selected / "cache"),
            "TASK_MANAGED_PACKS": str(selected / "managed"),
            "PACK_OR_CONTAINER": str(container),
        }
        argv = [substitutions.get(word, word) for word in argv]
        environment = {**UNPAINTED, "CPB_HOME": str(self.root / "unselected home"), "PATH": ""}
        run = subprocess.run(argv, cwd=caller, env=environment, capture_output=True,
                             text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["operation"], "root-add")
        state = json.loads((selected / "state.json").read_text(encoding="utf-8"))
        self.assertIn(str(container.resolve()), state["pack_roots"])
        self.assertFalse((self.root / "unselected home/pack-state.json").exists())


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


class RepositoryDocumentationTests(unittest.TestCase):
    """Check installed source documents and CLI help without a synthetic tree."""

    def test_preparation_and_material_reuse_have_distinct_reads(self) -> None:
        from execution_routes import resolve
        preparing = {x['document_id'] for x in resolve('performance', execution='authored')['reads']}
        reusing = {x['document_id'] for x in resolve('performance', ['scene-persona'], execution='authored')['reads']}
        self.assertIn('templates/narrative/personas/persona-template', preparing)
        self.assertIn('references/runtime/scene-persona', reusing)
        self.assertNotIn('templates/narrative/personas/persona-template', reusing)

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
            self.assertNotIn("SKILL", [entry["document_id"] for entry in route["files"]])
            for entry in route["files"]:
                self.assertFalse(entry["missing"], entry["document_id"])
                record = json.loads((ROOT / 'knowledge' / (entry['document_id'] + '.json')).read_text(encoding='utf-8'))
                bodies = {section['id']: section['body'].encode('utf-8') for section in record['sections']}
                selected = b''.join(bodies[section['section_id']] for section in entry['sections'])
                self.assertEqual(
                    _skill_word_count(selected.decode('utf-8')),
                    entry["words"],
                    entry["document_id"],
                )
                self.assertEqual(len(selected), entry['selected_bytes'])
                self.assertEqual(sum(map(len, bodies.values())), entry['source_bytes'])
            self.assertEqual(sum(entry['selected_bytes'] for entry in route['files']), route['selected_bytes'])

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
        example_line = result.stdout.split("Minimal example JSON:\n", 1)[1].splitlines()[0]
        example = json.loads(example_line)
        self.assertIsInstance(example, list)
        self.assertEqual("identity", example[0]["request_id"])

    def test_retrieval_recording_is_routed_and_accepted(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        owner = "references/runtime/prompt-only-core.md"
        self.assertIn(f"]({owner}#saved-prompt-artifacts)", skill)
        core = (ROOT / owner).read_text(encoding="utf-8")
        saved = core.partition("## Saved prompt artifacts")[2].partition("\n## ")[0]
        self.assertIn("--record lookups.json --element NAME", saved)
        self.assertIn("prompt_retrieval.py lookups.json --element NAME --adopted ID", saved)
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

    def test_skill_uses_one_locked_environment_for_all_routes(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        generation = (ROOT / "references/runtime/image-generation.md").read_text(
            encoding="utf-8"
        )
        prompt_artifacts = (
            ROOT / "references/runtime/reference-prompt-artifacts.md"
        ).read_text(encoding="utf-8")
        self.assertIn("dependency checks", skill.lower())
        check = "uv run --project <skill-root> --locked python <skill-root>/scripts/check_dependencies.py"
        self.assertIn(check, skill)
        self.assertIn(check, generation)
        self.assertIn(check, prompt_artifacts)
        self.assertIn("uv run --project <skill-root> --locked python <skill-root>/scripts/<name>.py ...", skill)
        self.assertIn(
            "Run documented `python scripts/<name>.py ...` as "
            "`uv run --project <skill-root> --locked python <skill-root>/scripts/<name>.py ...`.",
            skill,
        )
        self.assertIn("Start in an existing directory", skill)
        self.assertIn("after Studio initialization, use its directory", skill)
        self.assertLess(skill.index("## Mandatory execution environment"), skill.index("## Core contract"))
        self.assertIn("prompt-artifacts", prompt_artifacts)
        self.assertIn("same locked environment", prompt_artifacts)

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
            "Assign the delivered references to their subjects and permitted uses",
            "Describe target changes as the chosen result",
            "Add required target properties absent from the references",
            "Apply record knowledge according to its role in the selected depiction.",
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
        workflow = (ROOT / "references/runtime/production-authoring.md").read_text(encoding="utf-8")

        self.assertIn("resolve the optional `prompt-writing-guide`", workflow)
        self.assertIn("read the complete selected guide before final rendition", workflow)
        self.assertIn("## Prompt rendition gate", generation)
        self.assertIn("resolve and read the complete guide before final rendition", generation)
        self.assertIn("Generation builders commit the supplied final rendition", generation)
        rendition = prompt_only.partition("## Rendition and delivery")[2].partition("\n## ")[0]
        self.assertIn("Authoring work", rendition)
        self.assertIn("](prompt-writing-guide.md)", rendition)
        self.assertIn("Use [Prompt Writing Guide](prompt-writing-guide.md) for the final interface", composition)
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

    def test_changelog_current_release_matches_product_calver(self) -> None:
        from release_contract import validate_changelog
        from package_identity import pep440_version_for_calver
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


class ReleaseDocumentationOwnershipTests(unittest.TestCase):
    def test_contributor_guide_owns_release_explanation_and_readme_links_authorities(self):
        from validate import check_documentation
        errors = []
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("YYYY.MM.DD.N", contributing)
        self.assertIn("UTC CalVer", contributing)
        for authority in ("CONTRIBUTING.md", "package-manifest.toml"):
            self.assertIn(f"]({authority})", readme)
            self.assertTrue((ROOT / authority).is_file())
        check_documentation(ROOT, errors)
        self.assertEqual([], errors)

    def test_readme_cannot_drop_manifest_authority_link(self):
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

    def test_readme_local_links_accept_real_anchors_and_report_missing_anchors(self):
        from unittest.mock import patch
        from validate import check_documentation
        read = Path.read_text
        for fragment, accepted in (('open-the-current-work', True), ('unavailable-synthetic-heading', False)):
            with self.subTest(fragment=fragment):
                target = 'references/runtime/production-workflow.md#' + fragment
                def with_anchor(path, *args, **kwargs):
                    text = read(path, *args, **kwargs)
                    if path == ROOT / 'README.md':
                        return text + '\nRead [the workflow](' + target + ').\n'
                    return text
                errors = []
                with patch.object(Path, 'read_text', with_anchor):
                    check_documentation(ROOT, errors)
                expected = [] if accepted else ['broken local anchor link in README.md: ' + target]
                self.assertEqual(errors, expected)


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
    """Whether the script, or the module whose main it runs, reads its command line with an argparse parser."""

    text = script.read_text(encoding="utf-8")
    if "argparse" in text or "ArgumentParser" in text:
        return True
    for module, names in re.findall(r"^from (\w+) import (\([^)]*\)|[^\n]*)", text, re.M):
        source = script.with_name(module + ".py")
        if re.search(r"\bmain\b", names) and source.is_file() and "argparse" in source.read_text(encoding="utf-8"):
            return True
    return False


def script_help(words: tuple[str, ...]) -> str:
    """The --help of a script, or of one of its subcommands; empty when --help fails."""

    result = subprocess.run(
        [sys.executable, f"scripts/{words[0]}.py", *words[1:], "--help"],
        cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**UNPAINTED, "COLUMNS": "200", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return result.stdout if result.returncode == 0 else ""


class HelpResults:
    """Own each help outcome once while one batch checks its commands."""

    def __init__(self, fetch: Callable[[tuple[str, ...]], str]):
        self.fetch = fetch
        self._lock = threading.Lock()
        self._results: dict[tuple[str, ...], concurrent.futures.Future[str]] = {}

    def read(self, words: tuple[str, ...]) -> str:
        with self._lock:
            future = self._results.get(words)
            owner = future is None
            if owner:
                future = concurrent.futures.Future()
                self._results[words] = future
        if owner:
            try:
                future.set_result(self.fetch(words))
            except BaseException as exc:
                future.set_exception(exc)
        return future.result()


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


def command_problems(command: str, *, read_help: Callable[[tuple[str, ...]], str]) -> list[str]:
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
    text = read_help(level)
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
        child = read_help((*level, word))
        if re.search(r"^usage: \S+ " + re.escape(" ".join((*level[1:], word))) + r"\b", child, re.M):
            level, text = (*level, word), child
        else:
            # The choice was the value of a positional argument, not a subcommand.
            choosing = False
    return problems


def help_workers() -> int:
    """Use the runner's child budget or its normal standalone worker policy."""
    budget = os.environ.get("CPB_CHECK_CHILD_WORKERS")
    if budget is None:
        from run_checks import execution_context
        return execution_context(1)["child_command_workers"]
    count = int(budget)
    if count < 1:
        raise ValueError("CPB_CHECK_CHILD_WORKERS must be a positive integer")
    return count


def documented_command_problems(commands: list[str]) -> dict[str, list[str]]:
    """Check every command, sharing each help key's completion within this batch."""
    commands = sorted(set(commands))
    help_results = HelpResults(script_help)

    def check(command: str) -> list[str]:
        return command_problems(command, read_help=help_results.read)

    with concurrent.futures.ThreadPoolExecutor(help_workers()) as pool:
        return dict(zip(commands, pool.map(check, commands)))


class DocumentedCommandTests(unittest.TestCase):
    maxDiff = None

    def test_documented_commands_match_each_script_help(self) -> None:
        commands = documented_commands()
        self.assertTrue(commands, "no documented command was found")
        problems = documented_command_problems([command for _, command in commands])
        self.assertEqual(
            [],
            [f"{document}: {command}: {problem}" for document, command in commands for problem in problems[command]],
        )

    def test_distinct_subcommands_run_together_and_each_batch_reads_each_key_once(self) -> None:
        from collections import Counter
        from unittest import mock

        calls = Counter()
        subcommands_started = threading.Barrier(2)
        def help_result(argv, **kwargs):
            key = tuple(argv[1:-1])
            calls[key] += 1
            name = Path(argv[1]).stem
            if len(key) == 1:
                text = f"usage: {name}.py\npositional arguments:\n  {{inspect,show}}\noptions:\n  --version\n"
            else:
                subcommands_started.wait(timeout=5)
                text = f"usage: {name}.py {argv[2]}\noptions:\n  --value VALUE\n"
            return subprocess.CompletedProcess(argv, 0, stdout=text)

        with tempfile.TemporaryDirectory(prefix="cpb-help-keys-") as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "scripts/fixture.py").write_text("import argparse\n", encoding="utf-8")
            commands = ["python scripts/fixture.py inspect --value first",
                        "python scripts/fixture.py show --value first",
                        "python scripts/fixture.py show --value second",
                        "python scripts/fixture.py show --absent"]
            with mock.patch.dict(os.environ, {"CPB_CHECK_CHILD_WORKERS": "2"}), \
                    mock.patch.object(sys.modules[__name__], "ROOT", root), \
                    mock.patch.object(subprocess, "run", side_effect=help_result):
                for batch in (1, 2):
                    problems = documented_command_problems(commands)
                    self.assertEqual(set(problems), set(commands))
                    self.assertEqual(len(calls), 3)
                    self.assertEqual(set(calls.values()), {batch})
                    for command, found in problems.items():
                        self.assertEqual(bool(found), command.endswith("--absent"))

    def test_same_key_shares_empty_help_and_propagates_fetch_failure(self) -> None:
        key = ("fixture", "show")
        for failure in (None, RuntimeError("synthetic help failure")):
            with self.subTest(failure=failure):
                entered, release = threading.Event(), threading.Event()
                calls = []
                def fetch(words):
                    calls.append(words)
                    entered.set()
                    if not release.wait(timeout=5):
                        raise TimeoutError("test did not release the help fetch")
                    if failure is not None:
                        raise failure
                    return ""
                owner = HelpResults(fetch)
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    first = pool.submit(owner.read, key)
                    self.assertTrue(entered.wait(timeout=5))
                    second = pool.submit(owner.read, key)
                    release.set()
                    for result in (first, second):
                        if failure is None:
                            self.assertEqual(result.result(timeout=5), "")
                        else:
                            self.assertIs(result.exception(timeout=5), failure)
                self.assertEqual(calls, [key])


DIAGNOSTICS_DOCUMENT = ROOT / "references/runtime/production-diagnostics.md"
DIAGNOSTIC_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")
# A row of the code table, and a row of the exit status table with its example codes.
CODE_ROW = re.compile(r"^\| `([A-Z][A-Z0-9_]*)` \| (.+) \|$", re.M)
EXIT_ROW = re.compile(r"^\| (\d+) \| [^|]+ \| (.+) \|$", re.M)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def script_module(path: Path) -> str:
    """The name a script below scripts/ is imported by."""
    parts = path.relative_to(ROOT / "scripts").with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class DiagnosticCodeFlow:
    """The diagnostic codes that string literals of the scripts become, and where.

    A literal becomes a code when it reaches the code of a diagnostic: the first
    argument or `code` keyword of `ProductionError` or `Diagnostic` (kind
    "raise"), or the `code` key, keyword, attribute or item of another record
    (kind "record"). It reaches it directly, as a branch of a conditional
    expression or of `or`, as the default of `.get`, through an assignment or a
    parameter default, or as the argument of a function or class that passes
    that parameter on to such a position, followed until no further one appears.
    A call is bound the way Python binds its name: a function or class of an
    enclosing scope or of the module, an imported one, or `module.name`.
    """

    def __init__(self, paths: list[Path]) -> None:
        self.sources = {path: ast.parse(path.read_text(encoding="utf-8")) for path in paths}
        self.modules = {script_module(path): tree for path, tree in self.sources.items()}
        self.imports = {}
        self.sites = {}
        self.guidance = {}
        for name, tree in self.modules.items():
            self.imports[name], self.sites[name], self.guidance[name] = self._scan(tree)
        self._values: dict[tuple[str, ast.AST | None], dict[str, list[ast.expr]]] = {}
        self._definitions: dict[ast.AST, dict[str, ast.AST]] = {}
        self._resolutions: dict[ast.expr, ast.AST | None] = {}
        diagnostic = self._defined(self.modules["production_diagnostics"], "Diagnostic")
        self.forwards: dict[ast.AST, dict[str, str]] = {diagnostic: {"code": "raise"}}
        self.codes: dict[str, set[tuple[str, str]]] = {}
        while self._propagate():
            pass

    @staticmethod
    def _scan(tree: ast.Module):
        """Acquire import bindings, scoped sites and guidance in one tree traversal."""
        table: dict[str, tuple[str, ...]] = {}
        sites = []
        guidance = []
        pending: deque[tuple[ast.AST, tuple[ast.AST, ...]]] = deque([(tree, ())])
        while pending:
            node, scopes = pending.popleft()
            if isinstance(node, ast.Import):
                for alias in node.names:
                    table[alias.asname or alias.name.split(".")[0]] = (
                        "module", alias.name if alias.asname else alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    table[alias.asname or alias.name] = ("name", node.module, alias.name)
            if isinstance(node, (ast.Call, ast.Dict, ast.Assign)):
                sites.append((node, scopes))
            if isinstance(node, ast.Dict):
                guidance.extend((value.lineno, value.value) for key, value in zip(node.keys, node.values)
                                if isinstance(key, ast.Constant) and key.value == "document_path"
                                and isinstance(value, ast.Constant) and isinstance(value.value, str))
            inner = scopes + (node,) if isinstance(node, SCOPES) else scopes
            pending.extend((child, inner) for child in ast.iter_child_nodes(node))
        return table, sites, guidance

    def _defined(self, owner: ast.AST, name: str) -> ast.AST | None:
        if owner not in self._definitions:
            definitions: dict[str, ast.AST] = {}
            for child in ast.iter_child_nodes(owner):
                if isinstance(child, SCOPES):
                    definitions.setdefault(child.name, child)
            self._definitions[owner] = definitions
        return self._definitions[owner].get(name)

    def _resolve(self, module: str, scopes: tuple[ast.AST, ...], function: ast.expr) -> ast.AST | None:
        """Bind each call once; propagation changes forwarded parameters, not its AST scope."""
        if function not in self._resolutions:
            self._resolutions[function] = self._resolve_binding(module, scopes, function)
        return self._resolutions[function]

    def _resolve_binding(self, module: str, scopes: tuple[ast.AST, ...], function: ast.expr) -> ast.AST | None:
        if isinstance(function, ast.Name):
            for scope in reversed(scopes):
                found = None if isinstance(scope, ast.ClassDef) else self._defined(scope, function.id)
                if found is not None:
                    return found
            found = self._defined(self.modules[module], function.id)
            if found is not None:
                return found
            imported = self.imports[module].get(function.id)
            if imported and imported[0] == "name" and imported[1] in self.modules:
                return self._defined(self.modules[imported[1]], imported[2])
        elif isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
            imported = self.imports[module].get(function.value.id)
            if imported and imported[0] == "module" and imported[1] in self.modules:
                return self._defined(self.modules[imported[1]], function.attr)
        return None

    @staticmethod
    def _positional(callee: ast.AST) -> list[str]:
        """The parameters a call binds by position, in order."""
        if isinstance(callee, ast.ClassDef):
            init = next((child for child in callee.body
                         if isinstance(child, ast.FunctionDef) and child.name == "__init__"), None)
            if init is None:
                # A dataclass binds its annotated fields in order.
                return [child.target.id for child in callee.body
                        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)]
            return [argument.arg for argument in init.args.posonlyargs + init.args.args][1:]
        return [argument.arg for argument in callee.args.posonlyargs + callee.args.args]

    @staticmethod
    def _argument(call: ast.Call, positional: list[str], name: str) -> ast.expr | None:
        if name in positional:
            index = positional.index(name)
            if index < len(call.args) and not any(isinstance(item, ast.Starred) for item in call.args[:index + 1]):
                return call.args[index]
        return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)

    def _assigned(self, module: str, function: ast.AST | None) -> dict[str, list[ast.expr]]:
        """What each name of a function, or of the module itself, is assigned, with parameter defaults."""
        key = (module, function)
        if key not in self._values:
            values: dict[str, list[ast.expr]] = defaultdict(list)
            owner = self.modules[module] if function is None else function
            nodes = ast.iter_child_nodes(owner) if function is None else ast.walk(owner)
            for node in nodes:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            values[target.id].append(node.value)
            if function is not None:
                arguments = function.args
                positional = arguments.posonlyargs + arguments.args
                for argument, default in zip(reversed(positional), reversed(arguments.defaults)):
                    values[argument.arg].append(default)
                for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
                    if default is not None:
                        values[argument.arg].append(default)
            self._values[key] = values
        return self._values[key]

    @classmethod
    def _branches(cls, expression: ast.expr) -> list[ast.expr]:
        """The expressions a code expression takes its value from."""
        if isinstance(expression, ast.IfExp):
            return cls._branches(expression.body) + cls._branches(expression.orelse)
        if isinstance(expression, ast.BoolOp):
            return [branch for value in expression.values for branch in cls._branches(value)]
        if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                and expression.func.attr == "get" and len(expression.args) == 2):
            return cls._branches(expression.args[1])
        return [expression]

    def _literals(self, module: str, function: ast.AST | None, expression: ast.expr,
                  seen: frozenset[str] = frozenset()) -> set[str]:
        found: set[str] = set()
        for branch in self._branches(expression):
            if isinstance(branch, ast.Constant) and isinstance(branch.value, str):
                found.add(branch.value)
            elif isinstance(branch, ast.Name) and branch.id not in seen:
                values = self._assigned(module, function).get(branch.id) or self._assigned(module, None).get(branch.id, [])
                for value in values:
                    found |= self._literals(module, function, value, seen | {branch.id})
        return found

    def _code_expressions(self, module: str, scopes: tuple[ast.AST, ...], node: ast.AST):
        """The expressions this node places in a diagnostic code, with the kind of that code."""
        if isinstance(node, ast.Call):
            callee = self._resolve(module, scopes, node.func)
            for name, kind in list(self.forwards.get(callee, {}).items()):
                expression = self._argument(node, self._positional(callee), name)
                if expression is not None:
                    yield expression, kind
            if isinstance(node.func, ast.Name) and node.func.id == "dict":
                yield from ((keyword.value, "record") for keyword in node.keywords if keyword.arg == "code")
        elif isinstance(node, ast.Dict):
            yield from ((value, "record") for key, value in zip(node.keys, node.values)
                        if isinstance(key, ast.Constant) and key.value == "code")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Attribute) and target.attr == "code") or (
                        isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
                        and target.slice.value == "code"):
                    yield node.value, "record"

    def _propagate(self) -> bool:
        """Collect the codes once with the known forwarding parameters; report whether new ones appeared."""
        changed = False
        self.codes = defaultdict(set)
        for module, sites in self.sites.items():
            for node, scopes in sites:
                functions = [scope for scope in scopes if not isinstance(scope, ast.ClassDef)]
                function = functions[-1] if functions else None
                for expression, kind in self._code_expressions(module, scopes, node):
                    for value in self._literals(module, function, expression):
                        if DIAGNOSTIC_CODE.fullmatch(value):
                            self.codes[value].add((module, kind))
                    if function is None:
                        continue
                    # A constructor's parameters belong to the class that a call names.
                    position = scopes.index(function)
                    owner = (scopes[position - 1] if function.name == "__init__" and position
                             and isinstance(scopes[position - 1], ast.ClassDef) else function)
                    arguments = function.args
                    parameters = {argument.arg for argument in
                                  arguments.posonlyargs + arguments.args + arguments.kwonlyargs}
                    for branch in self._branches(expression):
                        if isinstance(branch, ast.Name) and branch.id in parameters:
                            known = self.forwards.setdefault(owner, {})
                            before = known.get(branch.id)
                            after = "raise" if "raise" in (before, kind) else "record"
                            if before != after:
                                known[branch.id] = after
                                changed = True
        return changed


class DiagnosticCodeFlowBindingTests(unittest.TestCase):
    def test_bindings_keep_imports_cycles_constructors_and_local_scopes_distinct(self) -> None:
        from unittest import mock

        sources = {
            "production_diagnostics.py": (
                "class Diagnostic:\n"
                "    def __init__(self, code):\n"
                "        self.code = code\n"
            ),
            "forwarding.py": (
                "from production_diagnostics import Diagnostic\n"
                "def first(code):\n"
                "    return second(code)\n"
                "def second(code):\n"
                "    first(code)\n"
                "    return Diagnostic(code)\n"
                "class Wrapper:\n"
                "    def __init__(self, code):\n"
                "        second(code)\n"
                "def local_scope():\n"
                "    def first(code):\n"
                "        return {'code': code}\n"
                "    return first('LOCAL_RECORD')\n"
            ),
            "consumer.py": (
                "from forwarding import first as renamed, Wrapper\n"
                "import forwarding as forwarding_module\n"
                "renamed('ALIAS_CHAIN')\n"
                "forwarding_module.second('MODULE_CYCLE')\n"
                "Wrapper('WRAPPED_CODE')\n"
                "def defaulted(code='DEFAULT_CODE'):\n"
                "    renamed(code)\n"
                "guidance = {'document_path': 'references/runtime/production-diagnostics.md#codes'}\n"
            ),
        }
        with tempfile.TemporaryDirectory(prefix="cpb-diagnostic-bindings-") as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            paths = []
            for name, text in sources.items():
                path = root / "scripts" / name
                path.write_text(text, encoding="utf-8")
                paths.append(path)
            with mock.patch.object(sys.modules[__name__], "ROOT", root):
                flow = DiagnosticCodeFlow(paths)
            self.assertEqual(dict(flow.codes), {
                "ALIAS_CHAIN": {("consumer", "raise")},
                "MODULE_CYCLE": {("consumer", "raise")},
                "WRAPPED_CODE": {("consumer", "raise")},
                "DEFAULT_CODE": {("consumer", "raise")},
                "LOCAL_RECORD": {("forwarding", "record")},
            })
            self.assertEqual(flow.guidance["consumer"],
                             [(8, "references/runtime/production-diagnostics.md#codes")])

    def test_implementation_closure_reuses_parsed_sources_and_rereads_new_observations(self) -> None:
        from unittest import mock
        import production_operations as workflow

        sources = {
            "entry.py": "import alpha\nfrom branch import leaf\n",
            "alpha.py": "VALUE = 1\n",
            "bravo.py": "VALUE = 2\n",
            "branch/__init__.py": "from . import leaf\n",
            "branch/leaf.py": "import importlib\nimportlib.import_module('dynamic')\n'helper.json'\n",
            "dynamic.py": "VALUE = 3\n",
        }
        with tempfile.TemporaryDirectory(prefix="cpb-implementation-sources-") as temporary:
            root = Path(temporary)
            parsed = {}
            for relative, source in sources.items():
                path = root / "scripts" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
                parsed[path] = ast.parse(source)
            (root / "scripts/helper.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(workflow, "ROOT", root), mock.patch.object(workflow, "ENTRY_MODULES", ("entry",)):
                original = workflow.implementation_closure()
                self.assertEqual(set(original), {
                    "scripts/entry.py", "scripts/alpha.py", "scripts/branch/__init__.py",
                    "scripts/branch/leaf.py", "scripts/dynamic.py", "scripts/helper.json",
                    workflow.execution_routes.MANIFEST, workflow.IMPLEMENTATION_INDEX,
                })
                with mock.patch.object(ast, "parse", side_effect=AssertionError("source parsed again")), \
                        mock.patch.object(workflow.c, "read", side_effect=AssertionError("source read again")):
                    self.assertEqual(workflow.implementation_closure(parsed=parsed), original)

                entry = root / "scripts/entry.py"
                before = entry.stat()
                entry.write_text(sources["entry.py"].replace("alpha", "bravo"), encoding="utf-8")
                os.utime(entry, ns=(before.st_atime_ns, before.st_mtime_ns))
                current = workflow.implementation_closure()
                self.assertEqual((entry.stat().st_size, entry.stat().st_mtime_ns),
                                 (before.st_size, before.st_mtime_ns))
                self.assertNotIn("scripts/alpha.py", current)
                self.assertIn("scripts/bravo.py", current)


class DiagnosticDocumentationTests(unittest.TestCase):
    """Each diagnostic leads to an existing section, and the code table matches the codes the scripts raise.

    Production scripts are the modules a prepared run pins: the import closure
    of the production commands that `production_workflow.implementation_closure`
    computes and `config/implementation-files.json` records. Every code they
    raise through `ProductionError` or `Diagnostic` has a row, and every row
    names a code that some script produces, as a raised diagnostic or as the
    `code` of another record.
    """

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        import production_operations as production_workflow
        scripts = sorted(path for path in (ROOT / "scripts").rglob("*.py")
                         if not path.name.startswith("test_") and not path.name.endswith("_test.py"))
        flow = DiagnosticCodeFlow(scripts)
        cls.production = {script_module(ROOT / path)
                          for path in production_workflow.implementation_closure(parsed=flow.sources)
                          if path.endswith(".py")}
        # Retain the small test observations, not every source AST until shutdown.
        cls.codes = flow.codes
        cls.guidance = flow.guidance
        cls.rows = CODE_ROW.findall(DIAGNOSTICS_DOCUMENT.read_text(encoding="utf-8"))

    def test_diagnostic_guidance_names_existing_documents_and_sections(self) -> None:
        from production_diagnostics import PHASE_DOCUMENTS, PHASE_SCHEMAS
        declared = [(f"phase {phase}", target) for phase, target in PHASE_DOCUMENTS.items()]
        for module in sorted(self.production):
            declared.extend((f"{module}.py line {line}", target) for line, target in self.guidance[module])
        problems = []
        for owner, target in declared:
            path, _, anchor = target.partition("#")
            document = ROOT / path
            if not document.is_file():
                problems.append(f"{owner}: no document {path}")
            elif anchor and anchor not in markdown_anchor_slugs(document):
                problems.append(f"{owner}: no section #{anchor} in {path}")
        problems += [f"phase {phase}: no schema {schema}" for phase, schema in PHASE_SCHEMAS.items()
                     if not (ROOT / schema).is_file()]
        problems += [f"phase {phase}: guidance names a schema only beside a document" for phase in PHASE_SCHEMAS
                     if phase not in PHASE_DOCUMENTS]
        self.assertEqual([], problems)

    def test_code_table_lists_each_code_production_raises_and_only_produced_codes(self) -> None:
        documented = [code for code, _ in self.rows]
        self.assertEqual([], sorted({code for code in documented if documented.count(code) > 1}), "repeated rows")
        raised = {code for code, sources in self.codes.items()
                  if any(module in self.production and kind == "raise" for module, kind in sources)}
        self.assertEqual([], sorted(raised - set(documented)), "codes a production script raises without a row")
        self.assertEqual([], sorted(set(documented) - set(self.codes)), "rows that name a code no script produces")

    def test_authored_choice_reasons_match_their_schema_and_code_table_row(self) -> None:
        import production_diagnostics
        reasons = set(getattr(production_diagnostics, "CHOICE_REASONS", ()))
        self.assertTrue(reasons, "production_diagnostics.CHOICE_REASONS names no reason")
        schema = json.loads((ROOT / "schemas/authoring/production-compilation-report.schema.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(set(schema["$defs"].get("choice_reason", {}).get("enum", [])), reasons)
        row = dict(self.rows).get("AUTHORED_CHOICE_REQUIRED", "")
        named = {term for term in re.findall(r"`([a-z]+(?:-[a-z]+)+)`", row) if term.endswith("-required")}
        self.assertEqual(named, reasons, "reasons the AUTHORED_CHOICE_REQUIRED row names")

    def test_code_table_states_the_exit_status_each_code_selects(self) -> None:
        from production_diagnostics import EXIT_INPUT, exit_code
        problems = []
        for code, text in self.rows:
            stated = re.match(r"Exit (\d+)\b", text)
            expected = exit_code(code)
            if expected != EXIT_INPUT and (stated is None or int(stated.group(1)) != expected):
                problems.append(f"{code}: its row begins with Exit {expected}")
            elif expected == EXIT_INPUT and stated is not None:
                problems.append(f"{code}: exits {EXIT_INPUT}, not {stated.group(1)}")
        for status, examples in EXIT_ROW.findall(DIAGNOSTICS_DOCUMENT.read_text(encoding="utf-8")):
            problems += [f"exit {status}: the example {code} exits {exit_code(code)}"
                         for code in re.findall(r"`([A-Z][A-Z0-9_]*)`", examples) if exit_code(code) != int(status)]
        self.assertEqual([], problems)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
