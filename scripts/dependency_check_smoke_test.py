#!/usr/bin/env python3
"""The dependency check reads project pins and verifies one complete environment.

Installation targets the selected interpreter and requires the user's confirmation.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))


import check_dependencies as deps  # noqa: E402

REQUIREMENTS = str(deps.REQUIREMENTS)


def plan(*, modules=("pip", "venv", "ensurepip"), tools=("uv",), managed=False, venv=None):
    """The install plan with the running Python's modules and the executables on the search path mocked."""
    with mock.patch.object(deps, "externally_managed", return_value=managed), \
            mock.patch.object(deps.importlib.util, "find_spec",
                              side_effect=lambda name, *rest: object() if name in modules else None), \
            mock.patch.object(deps.shutil, "which", side_effect=lambda name: name if name in tools else None):
        return deps.install_plan(venv)


def check_with_versions(path: Path, versions: dict[str, str]) -> dict:
    """Check a definition with each distribution in versions installed at that version and importable."""
    def version(name):
        if name not in versions:
            raise deps.importlib.metadata.PackageNotFoundError(name)
        return versions[name]
    with mock.patch.object(deps.importlib.metadata, "version", side_effect=version), \
            mock.patch.object(deps.importlib, "import_module", return_value=object()), \
            mock.patch.object(deps, "functional_checks", return_value=[]), \
            mock.patch.object(deps, "with_sheet_fonts", side_effect=lambda report, texts: report), \
            mock.patch.object(deps, "with_ffprobe", side_effect=lambda report: report):
        return deps.check(path)


def rows(path: Path) -> list[dict]:
    return deps.load_dependencies(path)[1]


def declared_versions(path: Path) -> dict[str, str]:
    """Each distribution at the exact version its definition declares."""
    return {str(row["distribution"]): str(row["version"]) for row in rows(path)}


class InstallPlanTests(unittest.TestCase):
    def test_pip_installs_into_the_running_python(self):
        commands, note = plan()
        self.assertIsNone(note)
        self.assertEqual(commands, [[sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS]])

    def test_uv_installs_where_the_python_has_no_pip(self):
        commands, note = plan(modules=())
        self.assertIsNone(note)
        self.assertEqual(commands, [["uv", "pip", "install", "--python", sys.executable, "-r", REQUIREMENTS]])

    def test_no_installer_gives_a_reason(self):
        commands, note = plan(modules=(), tools=())
        self.assertEqual(commands, [])
        self.assertIn("no pip", note)

    def test_a_system_managed_python_gets_nothing_without_a_virtual_environment(self):
        commands, note = plan(managed=True)
        self.assertEqual(commands, [])
        self.assertIn("PEP 668", note)
        self.assertIn("--venv DIR", note)

    def test_a_virtual_environment_is_created_with_venv_and_pip_installs_into_it(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch) / "env"
            python = str(deps.environment_python(venv))
            commands, note = plan(managed=True, venv=venv)
        self.assertIsNone(note)
        self.assertEqual(commands, [
            [sys.executable, "-m", "venv", str(venv)],
            [python, "-m", "pip", "install", "-r", REQUIREMENTS],
        ])

    def test_uv_creates_the_environment_where_the_python_has_no_venv_or_pip(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch) / "env"
            python = str(deps.environment_python(venv))
            commands, note = plan(modules=("pip", "venv"), venv=venv)
        self.assertIsNone(note)
        self.assertEqual(commands, [
            ["uv", "venv", "--python", sys.executable, str(venv)],
            ["uv", "pip", "install", "--python", python, "-r", REQUIREMENTS],
        ])

    def test_an_existing_environment_is_installed_into_by_the_installer_it_has(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch)
            (venv / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
            python = str(deps.environment_python(venv))
            with mock.patch.object(deps, "runs_pip", return_value=True):
                with_pip, _ = plan(venv=venv)
            with mock.patch.object(deps, "runs_pip", return_value=False):
                without_pip, _ = plan(venv=venv)
        self.assertEqual(with_pip, [[python, "-m", "pip", "install", "-r", REQUIREMENTS]])
        self.assertEqual(without_pip, [["uv", "pip", "install", "--python", python, "-r", REQUIREMENTS]])

    def test_a_directory_with_other_files_is_not_made_an_environment(self):
        with tempfile.TemporaryDirectory() as scratch:
            (Path(scratch) / "notes.txt").write_text("x", encoding="utf-8")
            commands, note = plan(venv=Path(scratch))
        self.assertEqual(commands, [])
        self.assertIn("not an empty directory", note)

    def test_the_report_carries_each_command_and_a_note_only_when_there_is_one(self):
        with mock.patch.object(deps, "install_plan", return_value=([["pip", "install"]], None)):
            report = deps.check_environment()
        self.assertEqual(report["install_command"], "pip install")
        self.assertNotIn("venv_command", report)
        self.assertNotIn("install_note", report)
        with mock.patch.object(deps, "install_plan", return_value=([["make", "env"], ["pip", "install"]], None)):
            report = deps.check_environment()
        self.assertEqual((report["venv_command"], report["install_command"]), ("make env", "pip install"))
        with mock.patch.object(deps, "install_plan", return_value=([], "why not")):
            report = deps.check_environment()
        self.assertIsNone(report["install_command"])
        self.assertEqual(report["install_note"], "why not")


class EnvironmentReportTests(unittest.TestCase):
    def test_an_absent_environment_is_reported_with_the_commands_that_create_it(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch) / "env"
            report = deps.check_environment(venv, plan=([["make", "env"], ["pip", "install"]], None))
        self.assertFalse(report["ok"])
        self.assertIn("holds no virtual environment", report["errors"][0])
        self.assertEqual(report["executable"], str(deps.environment_python(venv)))
        self.assertTrue(report["check_command"].endswith(f"--venv {deps.shown([str(venv)])}"))
        self.assertEqual(report["venv_command"], "make env")

    def test_an_existing_environment_is_checked_with_its_own_python(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch)
            (venv / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
            child = {"ok": True, "python": "3.12.0", "definition": "pyproject.toml",
                     "dependencies": [], "errors": [], "ffprobe": {"required": True, "runs": True}}
            with mock.patch.object(deps, "check_in", return_value=child) as check_in, \
                    mock.patch.object(deps, "ffprobe_report") as ffprobe_report:
                report = deps.check_environment(venv, plan=([], None))
        check_in.assert_called_once_with(str(deps.environment_python(venv)))
        ffprobe_report.assert_not_called()
        self.assertEqual((report["python"], report["ffprobe"]), ("3.12.0", child["ffprobe"]))

    def test_a_new_process_reports_through_its_printed_json(self):
        printed = {"ok": True, "python": "3.12.0", "definition": "pyproject.toml",
                   "dependencies": [], "errors": [], "install_command": "theirs", "ffprobe": {"runs": True}}
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(printed), stderr="")
        with mock.patch.object(deps.subprocess, "run", return_value=completed) as run:
            report = deps.check_in("python-in-env")
        self.assertEqual(run.call_args.args[0][0], "python-in-env")
        self.assertEqual(run.call_args.args[0][1], str(Path(deps.__file__).resolve()))
        self.assertEqual(report, {field: printed[field] for field in (*deps.REPORT_FIELDS, "ffprobe")})

    def test_a_new_process_without_a_report_names_its_last_error_line(self):
        completed = subprocess.CompletedProcess([], 1, stdout="", stderr="Traceback\nModuleNotFoundError: tomllib\n")
        with mock.patch.object(deps.subprocess, "run", return_value=completed):
            report = deps.check_in("old-python")
        self.assertFalse(report["ok"])
        self.assertIn("status 1", report["errors"][0])
        self.assertIn("ModuleNotFoundError: tomllib", report["errors"][0])


class FfprobeTests(unittest.TestCase):
    def test_a_running_ffprobe_reports_its_version(self):
        completed = subprocess.CompletedProcess([], 0, stdout="ffprobe version 7.1\nbuilt with gcc\n", stderr="")
        with mock.patch.object(deps.shutil, "which", return_value="/bin/ffprobe"), \
                mock.patch.object(deps.subprocess, "run", return_value=completed):
            report = deps.ffprobe_report()
        self.assertEqual((report["runs"], report["version"]), (True, "ffprobe version 7.1"))
        self.assertNotIn("install_command", report)
        self.assertEqual(report["enables"], deps.FFPROBE_ENABLES)

    def test_a_missing_ffprobe_carries_the_package_manager_command(self):
        with mock.patch.object(deps.shutil, "which", side_effect=lambda name: name if name == "brew" else None), \
                mock.patch.object(deps.sys, "platform", "darwin"):
            report = deps.ffprobe_report()
        self.assertEqual((report["path"], report["runs"]), (None, False))
        self.assertEqual(report["install_command"], "brew install ffmpeg")

    def test_each_platform_uses_the_first_package_manager_on_the_search_path(self):
        def command(platform, tools, uid=1000):
            with mock.patch.object(deps.shutil, "which", side_effect=lambda name: name if name in tools else None), \
                    mock.patch.object(deps.os, "geteuid", return_value=uid, create=True):
                return deps.ffmpeg_install_command(platform)

        self.assertEqual(command("win32", {"winget", "choco"})[0], ["winget", "install", "--exact", "--id", "Gyan.FFmpeg"])
        self.assertEqual(command("win32", {"choco"})[0], ["choco", "install", "ffmpeg", "-y"])
        self.assertEqual(command("darwin", {"brew"})[0], ["brew", "install", "ffmpeg"])
        self.assertEqual(command("linux", {"apt-get", "dnf", "sudo"})[0], ["sudo", "apt-get", "install", "-y", "ffmpeg"])
        self.assertEqual(command("linux", {"dnf", "sudo"}, uid=0)[0], ["dnf", "install", "-y", "ffmpeg-free"])
        self.assertEqual(command("linux", {"pacman"})[0], ["pacman", "-S", "--noconfirm", "ffmpeg"])
        self.assertEqual(command("linux", {"apk"}, uid=0)[0], ["apk", "add", "ffmpeg"])
        missing, note = command("linux", set())
        self.assertIsNone(missing)
        self.assertIn("install FFmpeg", note)

    def test_the_complete_environment_requires_a_running_ffprobe(self):
        absent = {"required": True, "enables": deps.FFPROBE_ENABLES, "path": None, "runs": False, "version": None}
        passing = {"ok": True, "python": "3", "definition": "pyproject.toml", "dependencies": [], "errors": []}
        with mock.patch.object(deps, "_packages", return_value=passing), \
                mock.patch.object(deps, "with_sheet_fonts", side_effect=lambda report, texts: report), \
                mock.patch.object(deps, "ffprobe_report", return_value=absent):
            report = deps.check(deps.PYPROJECT)
        self.assertFalse(report["ok"])
        self.assertTrue(report["ffprobe"]["required"])
        self.assertIn("ffprobe", report["errors"][-1])


class DefinitionTests(unittest.TestCase):
    def test_the_project_owns_one_complete_dependency_set(self):
        with deps.PYPROJECT.open("rb") as stream:
            data = tomllib.load(stream)
        self.assertEqual(data["project"]["requires-python"], ">=3.12")
        self.assertEqual(set(declared_versions(deps.PYPROJECT)), set(deps.IMPORT_NAMES))
        self.assertFalse(data["project"].get("optional-dependencies"))
        self.assertFalse(data.get("dependency-groups"))
        self.assertEqual((deps.ROOT / ".python-version").read_text(encoding="utf-8").strip(), "3.12")

    def test_the_environment_passes_at_the_declared_versions(self):
        report = check_with_versions(deps.PYPROJECT, declared_versions(deps.PYPROJECT))
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["definition"], "pyproject.toml")

    def test_a_version_that_differs_from_the_pin_fails(self):
        name, outside = "numpy", "0.0.1"
        report = check_with_versions(deps.PYPROJECT, {**declared_versions(deps.PYPROJECT), name: outside})
        self.assertFalse(report["ok"])
        self.assertIn(f"{name} {outside} does not satisfy", " ".join(report["errors"]))

    def check_declarations(self, lines: list[str], versions: dict[str, str], *, python=">=3.12") -> dict:
        with tempfile.TemporaryDirectory() as scratch:
            project = Path(scratch) / "pyproject.toml"
            project.write_text('[project]\nrequires-python = ' + json.dumps(python)
                               + '\ndependencies = ' + json.dumps(lines) + '\n', encoding="utf-8")
            return check_with_versions(project, versions)

    def test_a_staged_project_is_read_from_its_requested_path(self):
        pins = {**declared_versions(deps.PYPROJECT), "numpy": "9.0.0"}
        report = self.check_declarations([f"{key}=={value}" for key, value in pins.items()], pins)
        self.assertTrue(report["ok"], report["errors"])

    def test_each_direct_dependency_has_one_exact_pin(self):
        pins = declared_versions(deps.PYPROJECT)
        first = next(iter(pins))
        lines = [f"{key}{'>=' if key == first else '=='}{value}" for key, value in pins.items()]
        report = self.check_declarations(lines, pins)
        self.assertFalse(report["ok"])
        self.assertIn("requires an exact package pin", " ".join(report["errors"]))

    def test_a_missing_direct_package_is_a_definition_error(self):
        pins = declared_versions(deps.PYPROJECT)
        report = self.check_declarations([f"{key}=={value}" for key, value in pins.items() if key != "numpy"], pins)
        self.assertFalse(report["ok"])
        self.assertIn("directly imported packages", " ".join(report["errors"]))

    def test_a_repeated_direct_package_is_a_definition_error(self):
        pins = declared_versions(deps.PYPROJECT)
        lines = [f"{key}=={value}" for key, value in pins.items()]
        report = self.check_declarations([*lines, lines[0]], pins)
        self.assertFalse(report["ok"])
        self.assertIn("duplicate dependency", " ".join(report["errors"]))

    def test_the_python_minimum_is_checked_before_reporting_success(self):
        with mock.patch.object(deps.sys, "version_info", (3, 11, 14)):
            report = check_with_versions(deps.PYPROJECT, declared_versions(deps.PYPROJECT))
        self.assertFalse(report["ok"])
        self.assertIn("Python 3.12 or newer", " ".join(report["errors"]))

    def test_a_prerelease_is_distinct_from_the_exact_final_pin(self):
        pins = declared_versions(deps.PYPROJECT)
        report = check_with_versions(deps.PYPROJECT, {**pins, "numpy": pins["numpy"] + "rc1"})
        self.assertFalse(report["ok"])
        self.assertIn("does not satisfy", " ".join(report["errors"]))


class SheetFontTests(unittest.TestCase):
    TEXT = "\u65e5\u672c\u8a9e"

    @staticmethod
    def passing_environment():
        return {"ok": True, "python": "3", "definition": "pyproject.toml",
                "dependencies": [], "errors": []}

    def test_missing_fonts_fail_before_rendering_and_name_both_weights(self):
        from character_sheet_render import textmetrics
        with mock.patch.object(textmetrics, "usable_cjk_font_files", return_value=[]):
            report = deps.sheet_font_report([self.TEXT])
        self.assertFalse(report["ok"])
        self.assertFalse(report["roles"]["regular"]["ok"])
        self.assertFalse(report["roles"]["bold"]["ok"])
        self.assertIn("no usable CJK font", " ".join(report["errors"]))

    def test_a_regular_font_does_not_satisfy_bold_text(self):
        from character_sheet_render import textmetrics
        font = Path("synthetic-regular.ttf")
        with mock.patch.object(textmetrics, "usable_cjk_font_files",
                               side_effect=lambda role: [font] if role == "regular" else []), \
                mock.patch.object(textmetrics, "font_has_glyph", return_value=True):
            report = deps.sheet_font_report([self.TEXT])
        self.assertTrue(report["roles"]["regular"]["ok"])
        self.assertFalse(report["roles"]["bold"]["ok"])
        self.assertFalse(report["ok"])

    def test_available_files_do_not_hide_missing_requested_glyphs(self):
        from character_sheet_render import textmetrics
        with mock.patch.object(textmetrics, "usable_cjk_font_files", return_value=[Path("synthetic.ttf")]), \
                mock.patch.object(textmetrics, "font_has_glyph", return_value=False):
            report = deps.sheet_font_report([self.TEXT])
        self.assertFalse(report["ok"])
        self.assertIn("U+65E5", " ".join(report["errors"]))

    def test_every_environment_checks_representative_and_requested_text(self):
        from character_sheet_render import textmetrics
        with mock.patch.object(deps, "_packages", side_effect=lambda path: self.passing_environment()), \
                mock.patch.object(deps, "ffprobe_report", return_value={"required": True, "runs": True}), \
                mock.patch.object(textmetrics, "usable_cjk_font_files", return_value=[]):
            ordinary = deps.check(deps.PYPROJECT)
            requested = deps.check_environment(plan=([], None), sheet_text=[self.TEXT])
        self.assertFalse(ordinary["ok"])
        self.assertEqual(ordinary["sheet_fonts"]["checked_texts"], [deps.SHEET_TEXT])
        self.assertFalse(requested["ok"])
        self.assertEqual(requested["sheet_fonts"]["checked_texts"], [deps.SHEET_TEXT, self.TEXT])

    def test_virtual_environment_keeps_its_own_font_result_and_requested_text(self):
        child = {**self.passing_environment(), "sheet_fonts": {"ok": False, "roles": {"bold": {"ok": False}}}}
        child.update(ok=False, errors=["child environment has no bold font"])
        completed = subprocess.CompletedProcess([], 1, stdout=json.dumps(child), stderr="")
        with mock.patch.object(deps.subprocess, "run", return_value=completed) as run:
            report = deps.check_in("python-in-env", sheet_text=[self.TEXT])
        self.assertEqual(run.call_args.args[0][-1], "--sheet-text=" + self.TEXT)
        self.assertEqual(report["sheet_fonts"], child["sheet_fonts"])
        self.assertFalse(report["ok"])

    def test_a_label_starting_with_a_hyphen_survives_the_real_child_cli(self):
        text = "-" + self.TEXT
        report = deps.check_in(sys.executable, sheet_text=[text])
        self.assertEqual(report["definition"], "pyproject.toml")
        self.assertEqual(report["sheet_fonts"]["checked_texts"], [deps.SHEET_TEXT, text])


def run_main(arguments, *, reports, run=None, terminal=None):
    """Run main with the reports check_environment returns in order, the commands' exit statuses and a
    mocked terminal answer; return the exit code, the printed report, what stderr showed and the calls."""
    stdout, stderr = io.StringIO(), io.StringIO()
    stdin = mock.Mock()
    stdin.isatty.return_value = terminal is not None
    stdin.readline.return_value = terminal or ""
    completed = [subprocess.CompletedProcess([], status) for status in (run or [])]
    with mock.patch.object(deps, "install_plan", return_value=([["make", "env"], ["pip", "install"]], None)), \
            mock.patch.object(deps, "check_environment", side_effect=[copy.deepcopy(report) for report in reports]) \
            as check_environment, \
            mock.patch.object(deps.subprocess, "run", side_effect=completed) as subprocess_run, \
            mock.patch.object(deps.sys, "stdin", stdin), mock.patch.object(deps.sys, "stderr", stderr), \
            contextlib.redirect_stdout(stdout):
        code = deps.main(arguments)
    return code, json.loads(stdout.getvalue()), stderr.getvalue(), check_environment, subprocess_run


MISSING = {"ok": False, "errors": ["numpy is not installed"],
           "dependencies": [{"distribution": "numpy", "import_ok": False, "constraint_ok": False}]}
PASSING = {"ok": True, "errors": [], "dependencies": [{"distribution": "numpy", "import_ok": True, "constraint_ok": True}]}


class InstallTests(unittest.TestCase):
    def test_a_terminal_confirmation_runs_the_commands_and_checks_again(self):
        code, report, shown, check_environment, run = run_main(
            ["--install"], reports=[MISSING, PASSING], run=[0, 0], terminal="y\n")
        self.assertEqual(code, 0)
        self.assertIn("make env\n", shown)
        self.assertIn("Run these commands? [y/N]", shown)
        self.assertEqual([call.args[0] for call in run.call_args_list], [["make", "env"], ["pip", "install"]])
        self.assertTrue(check_environment.call_args_list[1].kwargs["fresh"])
        self.assertEqual(report["install_ran"], ["make env", "pip install"])
        self.assertTrue(report["ok"])

    def test_a_declined_confirmation_runs_nothing(self):
        code, report, _, _, run = run_main(
            ["--install"], reports=[MISSING], terminal="n\n")
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertIn("did not confirm", report["errors"][-1])

    def test_without_a_terminal_install_needs_yes(self):
        code, report, shown, _, run = run_main(["--install"], reports=[MISSING])
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertEqual(shown, "")
        self.assertIn("pass --yes", report["errors"][-1])

    def test_yes_records_a_confirmation_given_elsewhere(self):
        code, report, shown, _, run = run_main(
            ["--install", "--yes"], reports=[MISSING, PASSING], run=[0, 0])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("Run these commands?", shown)
        self.assertEqual(report["install_ran"], ["make env", "pip install"])

    def test_a_failed_command_stops_the_rest_and_the_check_runs_again(self):
        code, report, _, check_environment, run = run_main(
            ["--install", "--yes"], reports=[MISSING, MISSING], run=[3])
        self.assertEqual(code, 1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(check_environment.call_count, 2)
        self.assertEqual(report["install_ran"], ["make env"])
        self.assertIn("make env exited with status 3", report["errors"][-1])

    def test_a_passing_check_installs_nothing(self):
        code, report, _, check_environment, run = run_main(
            ["--install", "--yes"], reports=[PASSING])
        self.assertEqual(code, 0)
        run.assert_not_called()
        self.assertEqual(check_environment.call_count, 1)
        self.assertNotIn("install_ran", report)

    def test_without_install_nothing_runs(self):
        code, _, _, _, run = run_main([], reports=[MISSING])
        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_yes_needs_install(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            deps.main(["--yes"])
        self.assertEqual(raised.exception.code, 2)

    def test_install_adds_missing_ffmpeg_and_preserves_a_working_installation(self):
        packages = ([["pip", "install"]], None)
        absent = {"required": True, "runs": False}
        with mock.patch.object(deps, "ffmpeg_install_command", return_value=(["brew", "install", "ffmpeg"], None)):
            self.assertEqual(deps.pending_commands({**PASSING, "ffprobe": absent}, packages),
                             [["brew", "install", "ffmpeg"]])
            self.assertEqual(deps.pending_commands({**MISSING, "ffprobe": absent}, packages),
                             [["pip", "install"], ["brew", "install", "ffmpeg"]])
            self.assertEqual(deps.pending_commands({**PASSING, "ffprobe": {**absent, "runs": True}}, packages), [])


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
