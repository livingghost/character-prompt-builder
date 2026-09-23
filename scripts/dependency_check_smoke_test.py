#!/usr/bin/env python3
"""The dependency check reads each version from one file, prints the commands that install a
profile, and runs them with --install once the user confirms."""
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

VISUAL = str(deps.PROFILE_PATHS["visual"])


def plan(*, modules=("pip", "venv", "ensurepip"), tools=("uv",), managed=False, profile="visual", venv=None):
    """The install plan with the running Python's modules and the executables on the search path mocked."""
    with mock.patch.object(deps, "externally_managed", return_value=managed), \
            mock.patch.object(deps.importlib.util, "find_spec",
                              side_effect=lambda name, *rest: object() if name in modules else None), \
            mock.patch.object(deps.shutil, "which", side_effect=lambda name: name if name in tools else None):
        return deps.install_plan(profile, venv)


def check_with_versions(path: Path, versions: dict[str, str]) -> dict:
    """Check a definition with each distribution in versions installed at that version and importable."""
    def version(name):
        if name not in versions:
            raise deps.importlib.metadata.PackageNotFoundError(name)
        return versions[name]
    with mock.patch.object(deps.importlib.metadata, "version", side_effect=version), \
            mock.patch.object(deps.importlib, "import_module", return_value=object()), \
            mock.patch.object(deps, "functional_checks", return_value=[]):
        return deps.check(path)


def rows(path: Path) -> list[dict]:
    return deps.load_requirements(path)


def declared_versions(path: Path) -> dict[str, str]:
    """Each distribution at the lowest version its definition accepts."""
    return {str(row["distribution"]): str(row["lower"]) for row in rows(path)}


class InstallPlanTests(unittest.TestCase):
    def test_pip_installs_into_the_running_python(self):
        commands, note = plan()
        self.assertIsNone(note)
        self.assertEqual(commands, [[sys.executable, "-m", "pip", "install", "-r", VISUAL]])

    def test_uv_installs_where_the_python_has_no_pip(self):
        commands, note = plan(modules=())
        self.assertIsNone(note)
        self.assertEqual(commands, [["uv", "pip", "install", "--python", sys.executable, "-r", VISUAL]])

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
            [python, "-m", "pip", "install", "-r", VISUAL],
        ])

    def test_uv_creates_the_environment_where_the_python_has_no_venv_or_pip(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch) / "env"
            python = str(deps.environment_python(venv))
            commands, note = plan(modules=("pip", "venv"), venv=venv)
        self.assertIsNone(note)
        self.assertEqual(commands, [
            ["uv", "venv", "--python", sys.executable, str(venv)],
            ["uv", "pip", "install", "--python", python, "-r", VISUAL],
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
        self.assertEqual(with_pip, [[python, "-m", "pip", "install", "-r", VISUAL]])
        self.assertEqual(without_pip, [["uv", "pip", "install", "--python", python, "-r", VISUAL]])

    def test_a_directory_with_other_files_is_not_made_an_environment(self):
        with tempfile.TemporaryDirectory() as scratch:
            (Path(scratch) / "notes.txt").write_text("x", encoding="utf-8")
            commands, note = plan(venv=Path(scratch))
        self.assertEqual(commands, [])
        self.assertIn("not an empty directory", note)

    def test_the_core_profile_installs_nothing(self):
        self.assertEqual(plan(profile="core"), ([], None))

    def test_the_report_carries_each_command_and_a_note_only_when_there_is_one(self):
        with mock.patch.object(deps, "install_plan", return_value=([["pip", "install"]], None)):
            report = deps.check_profile("visual")
        self.assertEqual(report["install_command"], "pip install")
        self.assertNotIn("venv_command", report)
        self.assertNotIn("install_note", report)
        with mock.patch.object(deps, "install_plan", return_value=([["make", "env"], ["pip", "install"]], None)):
            report = deps.check_profile("visual")
        self.assertEqual((report["venv_command"], report["install_command"]), ("make env", "pip install"))
        with mock.patch.object(deps, "install_plan", return_value=([], "why not")):
            report = deps.check_profile("visual")
        self.assertIsNone(report["install_command"])
        self.assertEqual(report["install_note"], "why not")


class EnvironmentReportTests(unittest.TestCase):
    def test_an_absent_environment_is_reported_with_the_commands_that_create_it(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch) / "env"
            report = deps.check_profile("visual", venv, plan=([["make", "env"], ["pip", "install"]], None))
        self.assertFalse(report["ok"])
        self.assertIn("holds no virtual environment", report["errors"][0])
        self.assertEqual(report["executable"], str(deps.environment_python(venv)))
        self.assertTrue(report["check_command"].endswith(f"--venv {deps.shown([str(venv)])}"))
        self.assertEqual(report["venv_command"], "make env")

    def test_an_existing_environment_is_checked_with_its_own_python(self):
        with tempfile.TemporaryDirectory() as scratch:
            venv = Path(scratch)
            (venv / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
            child = {"ok": True, "python": "3.12.0", "profile": "visual", "definition": "requirements-visual.txt",
                     "dependencies": [], "errors": [], "ffprobe": {"required": False, "runs": True}}
            with mock.patch.object(deps, "check_in", return_value=child) as check_in, \
                    mock.patch.object(deps, "ffprobe_report") as ffprobe_report:
                report = deps.check_profile("visual", venv, plan=([], None))
        check_in.assert_called_once_with(str(deps.environment_python(venv)), "visual")
        ffprobe_report.assert_not_called()
        self.assertEqual((report["python"], report["ffprobe"]), ("3.12.0", child["ffprobe"]))

    def test_a_new_process_reports_through_its_printed_json(self):
        printed = {"ok": True, "python": "3.12.0", "profile": "visual", "definition": "requirements-visual.txt",
                   "dependencies": [], "errors": [], "install_command": "theirs", "ffprobe": {"runs": True}}
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(printed), stderr="")
        with mock.patch.object(deps.subprocess, "run", return_value=completed) as run:
            report = deps.check_in("python-in-env", "tested")
        self.assertEqual(run.call_args.args[0][0], "python-in-env")
        self.assertEqual(run.call_args.args[0][-1], "--tested")
        self.assertEqual(report, {field: printed[field] for field in (*deps.REPORT_FIELDS, "ffprobe")})

    def test_a_new_process_without_a_report_names_its_last_error_line(self):
        completed = subprocess.CompletedProcess([], 1, stdout="", stderr="Traceback\nModuleNotFoundError: tomllib\n")
        with mock.patch.object(deps.subprocess, "run", return_value=completed):
            report = deps.check_in("old-python", "visual")
        self.assertFalse(report["ok"])
        self.assertIn("status 1", report["errors"][0])
        self.assertIn("ModuleNotFoundError: tomllib", report["errors"][0])


class FfprobeTests(unittest.TestCase):
    def test_a_running_ffprobe_reports_its_version(self):
        completed = subprocess.CompletedProcess([], 0, stdout="ffprobe version 7.1\nbuilt with gcc\n", stderr="")
        with mock.patch.object(deps.shutil, "which", return_value="/bin/ffprobe"), \
                mock.patch.object(deps.subprocess, "run", return_value=completed):
            report = deps.ffprobe_report(required=True)
        self.assertEqual((report["runs"], report["version"]), (True, "ffprobe version 7.1"))
        self.assertNotIn("install_command", report)
        self.assertEqual(report["enables"], deps.FFPROBE_ENABLES)

    def test_a_missing_ffprobe_carries_the_package_manager_command(self):
        with mock.patch.object(deps.shutil, "which", side_effect=lambda name: name if name == "brew" else None), \
                mock.patch.object(deps.sys, "platform", "darwin"):
            report = deps.ffprobe_report(required=False)
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

    def test_only_the_tested_profile_requires_ffprobe(self):
        absent = {"required": None, "enables": deps.FFPROBE_ENABLES, "path": None, "runs": False, "version": None}
        passing = {"ok": True, "python": "3", "profile": "x", "definition": "x", "dependencies": [], "errors": []}

        def report(profile):
            with mock.patch.object(deps, "check", return_value=dict(passing)), \
                    mock.patch.object(deps, "ffprobe_report", side_effect=lambda required: {**absent, "required": required}):
                return deps.check_profile(profile, plan=([], None))

        visual, tested, core = report("visual"), report("tested"), report("core")
        self.assertTrue(visual["ok"])
        self.assertFalse(visual["ffprobe"]["required"])
        self.assertFalse(tested["ok"])
        self.assertIn("ffprobe", tested["errors"][-1])
        self.assertNotIn("ffprobe", core)


class DefinitionTests(unittest.TestCase):
    def test_the_combined_file_and_the_extras_read_the_visual_ranges(self):
        self.assertEqual(rows(deps.SUPPORTED), rows(deps.VISUAL))
        with deps.PYPROJECT.open("rb") as stream:
            data = tomllib.load(stream)
        self.assertIn("optional-dependencies", data["project"]["dynamic"])
        extras = data["tool"]["setuptools"]["dynamic"]["optional-dependencies"]
        self.assertEqual(extras, {"visual": {"file": [deps.VISUAL.name]}})

    def test_each_profile_passes_at_the_versions_it_declares(self):
        for profile in ("visual", "full", "tested"):
            path = deps.PROFILE_PATHS[profile]
            with self.subTest(profile=profile):
                report = check_with_versions(path, declared_versions(path))
                self.assertTrue(report["ok"], report["errors"])

    def test_a_version_outside_the_declared_range_fails(self):
        bounded = next(row for row in rows(deps.VISUAL) if row["upper"])
        name, outside = str(bounded["distribution"]), str(bounded["upper"])
        report = check_with_versions(deps.VISUAL, {**declared_versions(deps.VISUAL), name: outside})
        self.assertFalse(report["ok"])
        self.assertIn(f"{name} {outside} does not satisfy", " ".join(report["errors"]))

    def check_tested_pins(self, lines: list[str], versions: dict[str, str]) -> str:
        with tempfile.TemporaryDirectory() as scratch:
            pins = Path(scratch) / deps.TESTED.name
            pins.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with mock.patch.dict(deps.PROFILE_PATHS, {"tested": pins}):
                return " ".join(check_with_versions(pins, versions)["errors"])

    def test_a_tested_pin_outside_the_visual_range_fails(self):
        ranges = {str(row["distribution"]): row for row in rows(deps.VISUAL)}
        pins = declared_versions(deps.TESTED)
        name = next(name for name in pins if ranges[name]["upper"])
        pins[name] = str(ranges[name]["upper"])
        errors = self.check_tested_pins([f"{key}=={value}" for key, value in pins.items()], pins)
        self.assertIn(f"{name}=={pins[name]} is outside the range", errors)

    def test_a_tested_entry_must_be_an_exact_pin(self):
        pins = declared_versions(deps.TESTED)
        first = next(iter(pins))
        lines = [f"{key}{'>=' if key == first else '=='}{value}" for key, value in pins.items()]
        errors = self.check_tested_pins(lines, pins)
        self.assertIn(f"must pin {first} to one version with ==", errors)


def run_main(arguments, *, reports, run=None, terminal=None):
    """Run main with the reports check_profile returns in order, the commands' exit statuses and a
    mocked terminal answer; return the exit code, the printed report, what stderr showed and the calls."""
    stdout, stderr = io.StringIO(), io.StringIO()
    stdin = mock.Mock()
    stdin.isatty.return_value = terminal is not None
    stdin.readline.return_value = terminal or ""
    completed = [subprocess.CompletedProcess([], status) for status in (run or [])]
    with mock.patch.object(deps, "install_plan", return_value=([["make", "env"], ["pip", "install"]], None)), \
            mock.patch.object(deps, "check_profile", side_effect=[copy.deepcopy(report) for report in reports]) \
            as check_profile, \
            mock.patch.object(deps.subprocess, "run", side_effect=completed) as subprocess_run, \
            mock.patch.object(deps.sys, "stdin", stdin), mock.patch.object(deps.sys, "stderr", stderr), \
            contextlib.redirect_stdout(stdout):
        code = deps.main(arguments)
    return code, json.loads(stdout.getvalue()), stderr.getvalue(), check_profile, subprocess_run


MISSING = {"ok": False, "errors": ["numpy is not installed"],
           "dependencies": [{"distribution": "numpy", "import_ok": False, "constraint_ok": False}]}
PASSING = {"ok": True, "errors": [], "dependencies": [{"distribution": "numpy", "import_ok": True, "constraint_ok": True}]}


class InstallTests(unittest.TestCase):
    def test_a_terminal_confirmation_runs_the_commands_and_checks_again(self):
        code, report, shown, check_profile, run = run_main(
            ["--profile", "visual", "--install"], reports=[MISSING, PASSING], run=[0, 0], terminal="y\n")
        self.assertEqual(code, 0)
        self.assertIn("make env\n", shown)
        self.assertIn("Run these commands? [y/N]", shown)
        self.assertEqual([call.args[0] for call in run.call_args_list], [["make", "env"], ["pip", "install"]])
        self.assertTrue(check_profile.call_args_list[1].kwargs["fresh"])
        self.assertEqual(report["install_ran"], ["make env", "pip install"])
        self.assertTrue(report["ok"])

    def test_a_declined_confirmation_runs_nothing(self):
        code, report, _, _, run = run_main(
            ["--profile", "visual", "--install"], reports=[MISSING], terminal="n\n")
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertIn("did not confirm", report["errors"][-1])

    def test_without_a_terminal_install_needs_yes(self):
        code, report, shown, _, run = run_main(["--profile", "visual", "--install"], reports=[MISSING])
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertEqual(shown, "")
        self.assertIn("pass --yes", report["errors"][-1])

    def test_yes_records_a_confirmation_given_elsewhere(self):
        code, report, shown, _, run = run_main(
            ["--profile", "visual", "--install", "--yes"], reports=[MISSING, PASSING], run=[0, 0])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("Run these commands?", shown)
        self.assertEqual(report["install_ran"], ["make env", "pip install"])

    def test_a_failed_command_stops_the_rest_and_the_check_runs_again(self):
        code, report, _, check_profile, run = run_main(
            ["--profile", "visual", "--install", "--yes"], reports=[MISSING, MISSING], run=[3])
        self.assertEqual(code, 1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(check_profile.call_count, 2)
        self.assertEqual(report["install_ran"], ["make env"])
        self.assertIn("make env exited with status 3", report["errors"][-1])

    def test_a_passing_check_installs_nothing(self):
        code, report, _, check_profile, run = run_main(
            ["--profile", "visual", "--install", "--yes"], reports=[PASSING])
        self.assertEqual(code, 0)
        run.assert_not_called()
        self.assertEqual(check_profile.call_count, 1)
        self.assertNotIn("install_ran", report)

    def test_without_install_nothing_runs(self):
        code, _, _, _, run = run_main(["--profile", "visual"], reports=[MISSING])
        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_yes_needs_install_and_the_core_profile_installs_nothing(self):
        for arguments in (["--profile", "visual", "--yes"], ["--profile", "core", "--install"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as raised:
                deps.main(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_install_adds_ffmpeg_only_where_the_profile_requires_ffprobe(self):
        packages = ([["pip", "install"]], None)
        absent = {"required": True, "runs": False}
        with mock.patch.object(deps, "ffmpeg_install_command", return_value=(["brew", "install", "ffmpeg"], None)):
            self.assertEqual(deps.pending_commands({**PASSING, "ffprobe": absent}, packages),
                             [["brew", "install", "ffmpeg"]])
            self.assertEqual(deps.pending_commands({**MISSING, "ffprobe": {**absent, "required": False}}, packages),
                             [["pip", "install"]])
            self.assertEqual(deps.pending_commands({**PASSING, "ffprobe": {**absent, "runs": True}}, packages), [])


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
