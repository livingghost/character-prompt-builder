"""Whole installed implementation acquisition without retained analysis state."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import builder_inputs as inputs


class BuilderInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="builder-inputs-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def capture(self):
        return inputs.capture(self.root)

    def link(self, relative, target, *, directory=False):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symbolic links are unavailable: {exc}")
        return path

    def test_all_modules_are_owned_without_parsing_or_executing_imports(self):
        self.write("scripts/entry.py", "raise RuntimeError('Must not execute source.')\n")
        self.write("scripts/__init__.py", "ROOT = True\n")
        self.write("scripts/plugins/__init__.py", "PLUGIN = True\n")
        self.write("scripts/plugins/extension.py", "VALUE = 1\n")
        self.write("scripts/unimported.py", "Source acquisition does not need valid Python syntax.\n")
        source = self.capture()
        self.assertEqual(source.paths, frozenset({
            "scripts/entry.py", "scripts/__init__.py", "scripts/plugins/__init__.py",
            "scripts/plugins/extension.py", "scripts/unimported.py"}))

    def test_same_size_and_mtime_module_edit_changes_identity_at_next_capture(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        dependency = self.write("scripts/not_statically_imported.py", "LIMIT = 1\n")
        before = self.capture()
        metadata = dependency.stat()
        dependency.write_bytes(b"LIMIT = 2\n")
        os.utime(dependency, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        after = self.capture()
        self.assertEqual(dependency.stat().st_size, metadata.st_size)
        self.assertNotEqual(before.fingerprint, after.fingerprint)
        self.assertEqual(before.read_bytes(dependency), b"LIMIT = 1\n")
        self.assertEqual(after.read_bytes(dependency), b"LIMIT = 2\n")

    def test_added_and_deleted_module_are_observed_without_an_inventory_cache(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        before = self.capture()
        extension = self.write("scripts/new_package/extension.py", "VALUE = 2\n")
        added = self.capture()
        self.assertIn("scripts/new_package/extension.py", added.paths)
        self.assertNotEqual(added.fingerprint, before.fingerprint)
        extension.unlink()
        removed = self.capture()
        self.assertNotIn("scripts/new_package/extension.py", removed.paths)
        self.assertEqual(removed.fingerprint, before.fingerprint)

    def test_all_source_data_families_are_acquired_with_add_edit_and_delete_freshness(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        paths = ["scripts/computed-name.json", "schemas/private/value.json",
                 "protocols/rules.md", "config/selection.json",
                 "references/authored.md", "templates/nested/template.json"]
        for relative in paths:
            with self.subTest(relative=relative):
                before = self.capture()
                path = self.write(relative, "synthetic A\n")
                added = self.capture()
                self.assertIn(relative, added.paths)
                self.assertNotEqual(added.fingerprint, before.fingerprint)
                metadata = path.stat()
                path.write_bytes(b"synthetic B\n")
                os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
                edited = self.capture()
                self.assertNotEqual(edited.fingerprint, added.fingerprint)
                self.assertEqual(added.read_bytes(relative), b"synthetic A\n")
                path.unlink()
                self.assertEqual(self.capture().fingerprint, before.fingerprint)

    def test_capture_reads_each_input_once_and_excludes_unowned_files(self):
        included = {"scripts/entry.py", "scripts/shared.json", "schemas/value.json"}
        excluded = {"scripts/test_entry.py", "scripts/entry_test.py", "scripts/stale.pyc",
                    "scripts/__pycache__/entry.pyc", "config/implementation-files.json",
                    "packs/user-library/private.py", "package-manifest.toml",
                    "pyproject.toml", "MANIFEST.json", "README.md"}
        for relative in included | excluded:
            self.write(relative, "Synthetic bytes for " + relative)
        read = Path.read_bytes
        visited = []

        def observe(path):
            visited.append(path.relative_to(self.root).as_posix())
            return read(path)

        with mock.patch.object(Path, "read_bytes", observe):
            source = self.capture()
        self.assertEqual(source.paths, frozenset(included))
        self.assertCountEqual(visited, included)

    def test_captured_bytes_and_inventory_survive_live_edits_and_mutable_exports(self):
        entry = self.write("scripts/entry.py", "VALUE = 1\n")
        source = self.capture()
        before = source.fingerprint
        exposed = source.rows
        exposed[0]["sha256"] = "changed"
        entry.unlink()
        self.assertEqual(source.read_bytes("scripts/entry.py"), b"VALUE = 1\n")
        self.assertEqual(source.read_bytes(entry), b"VALUE = 1\n")
        self.assertEqual(source.fingerprint, before)
        self.assertNotEqual(source.rows[0]["sha256"], "changed")
        for path in ("../entry.py", self.root.parent / "entry.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                source.read_bytes(path)
        with self.assertRaises(FileNotFoundError):
            source.read_bytes("scripts/never-acquired.py")

    def test_release_only_metadata_does_not_change_builder_identity(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        manifest = self.write("package-manifest.toml", '[package]\nversion="2026.11.07.4"\n')
        project = self.write("pyproject.toml", '[project]\nversion="2026.11.07.4"\n')
        before = self.capture()
        for path in (manifest, project):
            path.write_bytes(path.read_text(encoding='utf-8').replace(".4", ".5").encode("utf-8"))
        self.assertEqual(self.capture().fingerprint, before.fingerprint)

    def test_directory_links_are_rejected_for_source_packages_and_data_families(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        target = self.write("not-owned/plugin.py", "VALUE = 2\n").parent
        for relative in ("scripts/linked_package", "schemas/linked", "protocols", "templates/linked"):
            with self.subTest(relative=relative):
                link = self.link(relative, target, directory=True)
                try:
                    with self.assertRaisesRegex(ValueError, "link or reparse point"):
                        self.capture()
                finally:
                    link.unlink()

    def test_file_links_and_broken_links_are_rejected(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        target = self.write("not-owned/schema.json", "{}")
        for relative, destination in (("schemas/alias.json", target),
                                      ("scripts/missing.py", target.parent / "missing.py")):
            with self.subTest(relative=relative):
                link = self.link(relative, destination)
                try:
                    with self.assertRaisesRegex(ValueError, "link or reparse point"):
                        self.capture()
                finally:
                    link.unlink()

    def test_windows_directory_reparse_point_is_rejected_before_descent(self):
        self.write("scripts/entry.py", "VALUE = 1\n")
        directory = self.write("schemas/junction/value.json", "{}").parent
        lstat = Path.lstat

        def observe(path):
            value = lstat(path)
            if path == directory:
                return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=1024)
            return value

        with mock.patch.object(inputs.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024, create=True), \
                mock.patch.object(Path, "lstat", observe):
            with self.assertRaisesRegex(ValueError, "link or reparse point"):
                self.capture()


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
