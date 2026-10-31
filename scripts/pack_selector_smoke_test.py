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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
