#!/usr/bin/env python3
"""Exercise how validate and build-lock select one pack by ID, unique name or absolute directory."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
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
