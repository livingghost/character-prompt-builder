#!/usr/bin/env python3
"""The dependency check prints the command that installs a profile into the Python running it."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_dependencies as deps  # noqa: E402

VISUAL = str(deps.PROFILE_PATHS["visual"])


def command(*, pip: bool, uv: bool, managed: bool = False, profile: str = "visual"):
    with mock.patch.object(deps, "externally_managed", return_value=managed), \
            mock.patch.object(deps.importlib.util, "find_spec", return_value=object() if pip else None), \
            mock.patch.object(deps.shutil, "which", return_value="uv" if uv else None):
        return deps.install_command(profile)


class InstallCommandTests(unittest.TestCase):
    def test_pip_installs_into_the_running_python(self):
        text, note = command(pip=True, uv=True)
        self.assertIsNone(note)
        self.assertIn("-m pip install -r", text)
        self.assertIn(VISUAL, text)
        self.assertTrue(text.startswith(sys.executable) or text.startswith(f'"{sys.executable}"'), text)

    def test_uv_installs_where_the_python_has_no_pip(self):
        text, note = command(pip=False, uv=True)
        self.assertIsNone(note)
        self.assertTrue(text.startswith("uv pip install --python "), text)
        self.assertIn(VISUAL, text)

    def test_no_installer_gives_a_reason(self):
        text, note = command(pip=False, uv=False)
        self.assertIsNone(text)
        self.assertIn("no pip", note)

    def test_a_system_managed_python_is_sent_to_a_virtual_environment(self):
        text, note = command(pip=True, uv=True, managed=True)
        self.assertIsNone(text)
        self.assertIn("PEP 668", note)
        self.assertIn("uv venv", note)

    def test_the_core_profile_installs_nothing(self):
        self.assertEqual(command(pip=True, uv=True, profile="core"), (None, None))

    def test_the_report_carries_the_command_and_a_note_only_when_there_is_one(self):
        with mock.patch.object(deps, "install_command", return_value=("pip command", None)):
            report = deps.check_profile("visual")
        self.assertEqual(report["install_command"], "pip command")
        self.assertNotIn("install_note", report)
        with mock.patch.object(deps, "install_command", return_value=(None, "why not")):
            report = deps.check_profile("visual")
        self.assertIsNone(report["install_command"])
        self.assertEqual(report["install_note"], "why not")


if __name__ == "__main__":
    unittest.main(verbosity=2)
