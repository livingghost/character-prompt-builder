#!/usr/bin/env python3
"""Exercise how validate and build-lock select one pack by ID, unique name or absolute directory."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from unittest import mock

from pack_cli import main as pack_cli_main
import pack_manager
from pack_manager import generate_uuid7, write_lock


ROOT = Path(__file__).resolve().parents[1]


class PackSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        self.pack = self.managed / "alpha"
        shutil.copytree(ROOT / "examples" / "pack-authoring" / "minimal-pack", self.pack)
        self.manifest = json.loads((self.pack / "pack.json").read_text(encoding="utf-8"))
        write_lock(self.pack)
        self.common = [
            "--state-file", str(self.root / "state.json"),
            "--cache-dir", str(self.root / "cache"),
            "--managed-root", str(self.managed),
        ]

    def call(self, *args: str) -> tuple[int, dict]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = pack_cli_main([*self.common, *args])
        text = output.getvalue()
        return code, json.loads(text) if text.strip() else {}

    def test_explicit_extra_roots_reach_validate_without_persisting_selection(self) -> None:
        outside = self.root / "extra roots"
        outside.mkdir(); external = outside / "external"
        shutil.move(str(self.pack), external)
        code, payload = self.call("--pack-root", str(outside), "validate", "--pack", self.manifest["pack_id"], "--released")
        self.assertEqual(code, 0, payload)
        self.assertEqual(Path(payload["resolved_root"]), external.resolve())
        self.assertFalse((self.root / "state.json").exists())

    def test_root_add_help_leads_to_a_complete_runtime_registration(self) -> None:
        outside = self.root / "registered root's $literal"
        outside.mkdir()
        external = outside / "alpha"
        shutil.move(str(self.pack), external)
        caller = self.root / "caller with spaces"
        caller.mkdir()
        environment = {**os.environ, "CPB_HOME": str(self.root / "other home"),
                       "PATH": "", "PYTHON_COLORS": "0", "NO_COLOR": "1"}
        base = [sys.executable, str(ROOT / "scripts/pack_cli.py")]

        def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run([*base, *arguments], cwd=caller, env=environment,
                                  capture_output=True, text=True, encoding="utf-8")

        for arguments in (["--help"], ["root-add", "--help"]):
            with self.subTest(help=arguments):
                run = execute(arguments)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                help_text = " ".join(run.stdout.split())
                for option in ("--state-file", "--cache-dir", "--managed-root", "--pack-root"):
                    self.assertIn(option, help_text)
                self.assertIn("together", help_text)
                self.assertIn("before the subcommand", help_text)

        # Following the complete prefix succeeds; partial selectors and moving
        # the global options after root-add both fail before any state is written.
        for arguments in (["--state-file", str(self.root / "state.json"), "root-add", str(outside)],
                          ["root-add", str(outside), *self.common]):
            with self.subTest(incomplete_or_misplaced=arguments):
                run = execute(arguments)
                self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
                self.assertFalse((self.root / "state.json").exists())
        run = execute([*self.common, "root-add", str(outside)])
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        payload = json.loads(run.stdout)
        self.assertEqual((payload["ok"], payload["operation"]), (True, "root-add"))
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertIn(str(outside.resolve()), state["pack_roots"])
        found = execute([*self.common, "validate", "--pack", self.manifest["pack_id"], "--released"])
        self.assertEqual(found.returncode, 0, found.stdout + found.stderr)
        self.assertEqual(Path(json.loads(found.stdout)["resolved_root"]), external.resolve())
        self.assertFalse((self.root / "other home/pack-state.json").exists())

    def test_ready_repairs_run_as_printed_with_multiple_discovery_roots(self) -> None:
        first_root = self.root / "first root's $literal"
        second_root = self.root / "second root & extra"
        first_root.mkdir(); second_root.mkdir()
        shutil.move(str(self.pack), first_root / "alpha")
        second = pack_manager.initialize_pack(second_root / "beta", name="Second fixture pack")
        outside = self.root / "caller"
        outside.mkdir()
        environment = {**os.environ, "CPB_HOME": str(self.root / "home"), "PATH": ""}
        base = [sys.executable, str(ROOT / "scripts" / "pack_cli.py"), *self.common]

        # The state predates both extra discovery roots. Only commons is enabled.
        initial = subprocess.run(
            [*base, "ready", "--only", pack_manager.COMMONS_PACK_ID],
            cwd=outside, env=environment, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        selected = [*base, "--pack-root", str(first_root), "--pack-root", str(second_root), "ready"]
        ready = subprocess.run(selected, cwd=outside, env=environment,
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(ready.returncode, 1, ready.stdout + ready.stderr)
        decisions = [line for line in ready.stdout.splitlines() if "is new and not enabled" in line]
        self.assertEqual(len(decisions), 2, ready.stdout)

        for line in decisions:
            # Execute the offered fix unchanged, outside the product directory and
            # without any Python alias on PATH. Shell metacharacters stay in paths.
            command = line.split("then run ", 1)[1].split(" or ", 1)[0]
            fixed = subprocess.run(command, shell=True, cwd=outside, env=environment,
                                   capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(fixed.returncode, 0, fixed.stdout + fixed.stderr)
            self.assertTrue(json.loads(fixed.stdout)["ok"])

        settled = subprocess.run(selected, cwd=outside, env=environment,
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(settled.returncode, 0, settled.stdout + settled.stderr)
        state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(set(state["enabled_packs"]), {
            pack_manager.COMMONS_PACK_ID, self.manifest["pack_id"], second["pack_id"],
        })
        self.assertEqual(state["pack_roots"], [])

    def test_all_suboperations_use_one_resolved_runtime(self) -> None:
        from unittest.mock import patch
        import pack_cli
        original = pack_cli.resolve_pack_runtime
        with patch.object(pack_cli, "resolve_pack_runtime", wraps=original) as resolve:
            code, payload = self.call("validate", "--pack", self.manifest["pack_id"], "--released")
        self.assertEqual(code, 0, payload)
        self.assertEqual(resolve.call_count, 1)

    def test_validate_resolves_exact_id_and_unique_authored_name(self) -> None:
        for selector in (self.manifest["pack_id"], self.manifest["name"]):
            code, payload = self.call("validate", "--pack", selector, "--released")
            self.assertEqual(code, 0, payload)
            self.assertEqual(Path(payload["resolved_root"]), self.pack.resolve())

    def test_build_lock_resolves_discovered_pack_id(self) -> None:
        before = (self.pack / "pack.lock.json").read_bytes()
        code, payload = self.call("build-lock", "--pack", self.manifest["pack_id"])
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["pack_id"], self.manifest["pack_id"])
        self.assertEqual((self.pack / "pack.lock.json").read_bytes(), before)

    def test_directory_is_explicit_and_need_not_be_discovered(self) -> None:
        outside = self.root / "outside"
        shutil.copytree(self.pack, outside)
        code, payload = self.call("validate", "--directory", str(outside), "--released")
        self.assertEqual(code, 0, payload)
        self.assertEqual(Path(payload["resolved_root"]), outside.resolve())

    def test_validate_returns_the_manifest_and_discovery_issues(self) -> None:
        code, payload = self.call("validate", "--pack", self.manifest["pack_id"])
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["manifest"], self.manifest)
        self.assertIsInstance(payload["discovery_issues"], list)

    def test_duplicate_authored_name_lists_candidates_instead_of_choosing(self) -> None:
        other = self.managed / "beta"
        shutil.copytree(self.pack, other)
        manifest = json.loads((other / "pack.json").read_text(encoding="utf-8"))
        manifest["pack_id"] = generate_uuid7()
        (other / "pack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        code, payload = self.call("validate", "--pack", self.manifest["name"])
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        diagnostic = payload["diagnostics"][0]
        self.assertEqual(diagnostic["code"], "PACK_NAME_AMBIGUOUS")
        for key in ("severity", "phase", "file", "pointer", "message", "required_action", "blocked_checks"):
            self.assertIn(key, diagnostic)
        self.assertEqual(
            sorted(diagnostic["candidates"], key=lambda row: row["pack_id"]),
            sorted([
                {"pack_id": self.manifest["pack_id"], "name": self.manifest["name"], "root": str(self.pack.resolve())},
                {"pack_id": manifest["pack_id"], "name": self.manifest["name"], "root": str(other.resolve())},
            ], key=lambda row: row["pack_id"]),
        )

    def test_relative_directory_is_refused_before_any_lookup(self) -> None:
        import os
        current = Path.cwd()
        try:
            os.chdir(self.managed)
            code, payload = self.call("validate", "--directory", "alpha")
        finally:
            os.chdir(current)
        self.assertEqual(code, 2)
        self.assertEqual(payload["diagnostics"][0]["code"], "PACK_DIRECTORY_NOT_ABSOLUTE")
        self.assertEqual(payload["diagnostics"][0]["actual"], "alpha")

    def test_a_file_no_declared_glob_matches_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "pack"
            manifest = pack_manager.initialize_pack(pack, name="Declared pack", release="2026.08.24.1")
            (pack / "notice.txt").write_text("fixture\n", encoding="utf-8", newline="\n")
            manifest["content"]["resource_globs"] = ["*.txt"]
            (pack / "pack.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
            for name in ("README.md", "NOTICE.md", "LICENSE"):
                (pack / name).write_text("top-level document\n", encoding="utf-8", newline="\n")
            self.assertEqual([issue.code for issue in pack_manager.validate_pack(pack).issues if issue.severity == "error"], [])
            # The process lock file coordinates commands and is neither content nor an error.
            (pack / ".cpb.lock").write_bytes(b"")
            self.assertEqual([issue.code for issue in pack_manager.validate_pack(pack).issues if issue.severity == "error"], [])
            self.assertNotIn(".cpb.lock", {row["path"] for row in write_lock(pack)["files"]})
            (pack / "records").mkdir(exist_ok=True)
            (pack / "records" / "scratch.txt").write_text("not a record\n", encoding="utf-8", newline="\n")
            issues = [issue for issue in pack_manager.validate_pack(pack).issues if issue.code == "undeclared-file"]
            self.assertEqual([issue.path for issue in issues], ["records/scratch.txt"])
            with self.assertRaises(pack_manager.PackError):
                write_lock(pack)

    def test_lock_media_type_does_not_depend_on_the_interpreter_table(self) -> None:
        # A lock built on one Python release verifies on another: the media type
        # of a common image file comes from the pack manager, not from the
        # interpreter's mimetypes table.
        with mock.patch.object(pack_manager.mimetypes, "guess_type", return_value=(None, None)):
            self.assertEqual(pack_manager._media_type(Path("thumbnail.webp")), "image/webp")
            self.assertEqual(pack_manager._media_type(Path("rows.jsonl")), "application/jsonl")
            self.assertEqual(pack_manager._media_type(Path("unknown.bin")), "application/octet-stream")
        manifest = json.loads((self.pack / "pack.json").read_text(encoding="utf-8"))
        manifest["content"]["resource_globs"] = ["resources/**/*"]
        (self.pack / "pack.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        (self.pack / "resources").mkdir(exist_ok=True)
        (self.pack / "resources" / "thumbnail.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        rows = {row["path"]: row for row in write_lock(self.pack)["files"]}
        self.assertEqual(rows["resources/thumbnail.webp"]["media_type"], "image/webp")

    def test_name_is_not_interpreted_as_a_cwd_relative_path(self) -> None:
        cwd_named = self.root / "Unique Local Name"
        shutil.copytree(self.pack, cwd_named)
        current = Path.cwd()
        try:
            # The selector is resolved only against discovery, even if a same-named
            # directory exists in the caller's CWD.
            import os
            os.chdir(self.root)
            code, payload = self.call("validate", "--pack", "Unique Local Name")
        finally:
            os.chdir(current)
        self.assertEqual(code, 2)
        diagnostic = payload["diagnostics"][0]
        self.assertEqual(diagnostic["code"], "PACK_NOT_FOUND")
        self.assertIn(self.manifest["pack_id"], diagnostic["discovered"])


class BrowserCatalogTests(unittest.TestCase):
    """The selected pack runtime maintains a complete, disposable browser view."""

    def setUp(self) -> None:
        import browser_catalog
        from pack_manager import PackSettings, atomic_write_json
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.managed = self.root / "managed"
        self.pack = self.managed / "first"
        shutil.copytree(ROOT / "examples" / "pack-authoring" / "minimal-pack", self.pack)
        self.pack_id = json.loads((self.pack / "pack.json").read_text(encoding="utf-8"))["pack_id"]
        self.settings = PackSettings(
            roots=(self.managed,), state_file=self.root / "state.json",
            cache_dir=self.root / "cache", managed_root=self.managed,
            quarantine_root=self.root / "quarantine",
        )
        atomic_write_json(self.settings.state_file, {
            "pack_roots": [], "enabled_packs": [self.pack_id], "disabled_packs": [],
        })
        self.output = browser_catalog.output_directory(self.settings)

    def call(self, *arguments: str, settings=None) -> tuple[int, str]:
        from pack_runtime_cli import PackRuntimeContext
        output = io.StringIO()
        context = PackRuntimeContext(settings or self.settings, ())
        with mock.patch("pack_cli.resolve_pack_runtime", return_value=context), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            code = pack_cli_main(list(arguments))
        return code, output.getvalue()

    def manifest(self, output: Path | None = None) -> dict:
        return json.loads(((output or self.output) / "catalog-manifest.json").read_text(encoding="utf-8"))

    def second_pack(self) -> str:
        from pack_manager import atomic_write_json
        second = self.managed / "second"
        shutil.copytree(self.pack, second)
        manifest = json.loads((second / "pack.json").read_text(encoding="utf-8"))
        manifest["pack_id"] = generate_uuid7()
        manifest["name"] = "Second browser fixture"
        atomic_write_json(second / "pack.json", manifest)
        record_path = second / "records" / "lighting.json"
        records = json.loads(record_path.read_text(encoding="utf-8"))
        records["records"][0]["id"] = "fixture-broad-bounce"
        records["records"][0]["label"] = "broad bounce"
        atomic_write_json(record_path, records)
        return manifest["pack_id"]

    def test_ready_creates_reuses_updates_and_repairs_complete_view(self) -> None:
        import pack_cache
        from pack_manager import atomic_write_json
        from validate_catalog_site import run as validate_site
        with mock.patch.object(pack_cache, "acquire_runtime_inputs", wraps=pack_cache.acquire_runtime_inputs) as snapshots:
            code, text = self.call("ready")
        self.assertEqual(code, 0, text)
        self.assertIn(f"catalog: {self.output / 'index.html'}", text)
        self.assertEqual(snapshots.call_count, 1)
        manifest = self.manifest()
        self.assertEqual((manifest["pack_count"], manifest["record_count"]), (1, 1))
        self.assertTrue(validate_site(self.output)["ok"])
        mtimes = {name: (self.output / name).stat().st_mtime_ns for name in manifest["generated_files"]}
        with mock.patch("catalog_html.write_catalog_directory", side_effect=AssertionError("unchanged view was rebuilt")):
            code, text = self.call("ready")
        self.assertEqual(code, 0, text)
        self.assertEqual(mtimes, {name: (self.output / name).stat().st_mtime_ns for name in mtimes})
        record_file = self.pack / "records" / "lighting.json"
        records = json.loads(record_file.read_text(encoding="utf-8"))
        records["records"][0]["prompt"] = "a broad diffused wall reflection"
        atomic_write_json(record_file, records)
        code, text = self.call("ready")
        self.assertEqual(code, 0, text)
        updated = self.manifest()
        self.assertNotEqual(manifest["runtime_projection"], updated["runtime_projection"])
        detail = next((self.output / "records").rglob("*.html"))
        self.assertIn("a broad diffused wall reflection", detail.read_text(encoding="utf-8"))
        detail.unlink()
        code, text = self.call("ready")
        self.assertEqual(code, 0, text)
        self.assertTrue(detail.is_file())
        self.assertEqual(updated["runtime_projection"], self.manifest()["runtime_projection"])
        self.assertTrue(validate_site(self.output)["ok"])

    def test_current_browser_view_is_reused_without_a_writer_lock(self) -> None:
        import browser_catalog
        from pack_cache import load_runtime_catalog
        runtime = load_runtime_catalog(self.settings, quiet=True)
        first = browser_catalog.maintain_catalog(self.settings, runtime)
        self.assertTrue(first["ok"], first)
        self.assertTrue(first["rebuilt"])
        files = self.manifest()["generated_files"]
        before = {name: ((self.output / name).read_bytes(), (self.output / name).stat().st_mtime_ns)
                  for name in files}
        with mock.patch.object(browser_catalog, "lock", side_effect=AssertionError("current view acquired a writer lock")):
            current = browser_catalog.maintain_catalog(self.settings, runtime)
        self.assertTrue(current["ok"], current)
        self.assertTrue(current["fresh"])
        self.assertFalse(current["rebuilt"])
        self.assertEqual(before, {name: ((self.output / name).read_bytes(), (self.output / name).stat().st_mtime_ns)
                                  for name in files})

    def test_activation_and_invalid_source_replace_previous_active_records(self) -> None:
        import pack_cache
        second_id = self.second_pack()
        self.call("ready")
        with mock.patch.object(pack_cache, "acquire_runtime_inputs", wraps=pack_cache.acquire_runtime_inputs) as snapshots:
            code, text = self.call("enable", second_id)
        self.assertEqual(code, 0, text)
        self.assertEqual(snapshots.call_count, 1)
        self.assertEqual(self.manifest()["record_count"], 2)
        code, text = self.call("disable", self.pack_id)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.manifest()["record_count"], 1)
        self.assertFalse((self.output / "records" / self.pack_id).exists())
        (self.managed / "second" / "records" / "lighting.json").write_text("{ invalid record", encoding="utf-8")
        code, text = self.call("ready")
        self.assertEqual(code, 1, text)
        self.assertEqual(self.manifest()["record_count"], 0)
        self.assertEqual(self.manifest()["pack_count"], 0)
        self.assertEqual(list((self.output / "records").rglob("*.html")), [])
        self.assertIn("No active pack is available", (self.output / "index.html").read_text(encoding="utf-8"))
        self.assertIn("catalog:", text)

    def test_shared_cache_keeps_state_and_root_contexts_separate(self) -> None:
        import browser_catalog
        from dataclasses import replace
        from pack_manager import atomic_write_json
        self.call("ready")
        first_mtime = (self.output / "index.html").stat().st_mtime_ns
        second_settings = replace(self.settings, state_file=self.root / "another-state.json")
        atomic_write_json(second_settings.state_file, json.loads(self.settings.state_file.read_text(encoding="utf-8")))
        code, text = self.call("ready", settings=second_settings)
        self.assertEqual(code, 0, text)
        second_output = browser_catalog.output_directory(second_settings)
        self.assertNotEqual(self.output, second_output)
        self.assertEqual(self.manifest()["runtime_projection"]["source_fingerprint"],
                         self.manifest(second_output)["runtime_projection"]["source_fingerprint"])
        alternate_roots = replace(self.settings, roots=(*self.settings.roots, self.root / "additional-root"))
        code, text = self.call("ready", settings=alternate_roots)
        self.assertEqual(code, 0, text)
        third_output = browser_catalog.output_directory(alternate_roots)
        self.assertEqual(len({self.output, second_output, third_output}), 3)
        self.assertTrue((third_output / "index.html").is_file())
        self.assertEqual(first_mtime, (self.output / "index.html").stat().st_mtime_ns)

    def test_failed_view_keeps_activation_and_does_not_become_a_ready_gate(self) -> None:
        second_id = self.second_pack()
        self.call("ready")
        with mock.patch("catalog_html.write_catalog_directory", side_effect=OSError("fixture display storage failure")):
            code, text = self.call("enable", second_id)
            payload = json.loads(text)
            self.assertEqual(code, 0, text)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["visual_catalog"]["ok"])
            self.assertIn(second_id, json.loads(self.settings.state_file.read_text(encoding="utf-8"))["enabled_packs"])
            self.assertIn("Pack catalog unavailable", (self.output / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(self.manifest()["runtime_projection"]["status"], "unavailable")
            code, text = self.call("ready")
            self.assertEqual(code, 0, text)
            self.assertIn("warning: browser catalog unavailable:", text)
            self.assertNotIn("decide:", text)
        code, text = self.call("ready")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.manifest()["record_count"], 2)
        self.assertEqual(self.manifest()["runtime_projection"]["status"], "ready")

    def test_lock_publication_preserves_unselected_runtime_and_updates_selected_view(self) -> None:
        from pack_manager import atomic_write_json
        self.settings.state_file.unlink()
        with mock.patch("pack_cli.refresh_runtime_catalog", side_effect=AssertionError("lock publication selected a runtime")):
            code, text = self.call("build-lock", "--directory", str(self.pack))
        self.assertEqual(code, 0, text)
        self.assertEqual(json.loads(text)["visual_catalog"]["status"], "unselected")
        self.assertFalse(self.settings.state_file.exists())
        self.assertFalse(self.settings.cache_dir.exists())
        self.assertTrue((self.pack / "pack.lock.json").is_file())

        code, text = self.call("ready", "--only", self.pack_id)
        self.assertEqual(code, 0, text)
        selected_state = self.settings.state_file.read_bytes()
        previous = self.manifest()["runtime_projection"]["source_fingerprint"]
        manifest = json.loads((self.pack / "pack.json").read_text(encoding="utf-8"))
        manifest["release"] = "2026.08.15.2"
        atomic_write_json(self.pack / "pack.json", manifest)
        record_file = self.pack / "records" / "lighting.json"
        records = json.loads(record_file.read_text(encoding="utf-8"))
        records["records"][0]["prompt"] = "a broad overcast fill"
        atomic_write_json(record_file, records)
        code, text = self.call("build-lock", "--directory", str(self.pack))
        self.assertEqual(code, 0, text)
        self.assertTrue(json.loads(text)["visual_catalog"]["fresh"])
        self.assertEqual(selected_state, self.settings.state_file.read_bytes())
        self.assertNotEqual(previous, self.manifest()["runtime_projection"]["source_fingerprint"])
        detail = next((self.output / "records").rglob("*.html"))
        self.assertIn("a broad overcast fill", detail.read_text(encoding="utf-8"))

    def test_empty_enabled_set_publishes_current_empty_view(self) -> None:
        self.call("ready")
        code, text = self.call("disable", self.pack_id)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.manifest()["record_count"], 0)
        self.assertEqual(self.manifest()["pack_count"], 0)
        self.assertEqual(list((self.output / "records").rglob("*.html")), [])
        self.assertIn("No active pack is available", (self.output / "index.html").read_text(encoding="utf-8"))
        code, text = self.call("cache-status")
        self.assertEqual(code, 0, text)
        self.assertTrue(json.loads(text)["visual_catalog"]["fresh"])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
