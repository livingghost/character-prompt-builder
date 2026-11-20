#!/usr/bin/env python3
"""Session entry reports the studio and its open task before the pack runtime, with or without one.

Text authoring resumes from the work trail without an image pack, so the studio
lookup must not wait on the pack state. The work ledger also accepts the studio
after the command, as Studio Runtime writes the commands.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import session_entry_points  # noqa: E402
import studio_workspace as studio  # noqa: E402
import work_ledger  # noqa: E402
from cli_invocation import shown  # noqa: E402
from pack_manager import COMMONS_PACK_ID  # noqa: E402
from package_metadata import session_hook  # noqa: E402


def entry(cwd: Path, state_file: Path, *extra: str) -> str:
    previous = Path.cwd()
    os.chdir(cwd)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = session_entry_points.main(["--state-file", str(state_file), *extra])
    finally:
        os.chdir(previous)
    if code != 0:
        raise AssertionError(f"session entry exited {code}")
    return buffer.getvalue()


def snapshot(root: Path) -> dict:
    """Retain file contents, modification times and directory membership."""
    return {path.relative_to(root).as_posix():
            ("directory", path.stat().st_mtime_ns) if path.is_dir() else
            ("file", path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*")}


class SessionEntry(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cpb-entry-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.missing_state = self.root / "no-state.json"
        self.studio = self.root / "studio"
        studio.init(self.studio, "entry-test", "Entry test")
        (self.studio / "story").mkdir()
        work_ledger.begin(self.studio, "draft the first design note", ["record the brief", "propose two directions"])

    def settle_commons(self, state: Path, cache: Path, managed: Path, cwd: Path, environment: dict) -> None:
        ready = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "pack_cli.py"),
             "--state-file", str(state), "--cache-dir", str(cache), "--managed-root", str(managed),
             "ready", "--only", COMMONS_PACK_ID],
            cwd=cwd, env=environment, capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)

    def test_open_task_prints_before_a_missing_pack_runtime(self) -> None:
        text = entry(self.studio / "story", self.missing_state)
        self.assertIn("draft the first design note", text)
        self.assertIn("No pack runtime", text)
        self.assertLess(text.index("draft the first design note"), text.index("No pack runtime"))

    def test_open_task_prints_before_an_existing_pack_runtime(self) -> None:
        state = self.root / "pack-state.json"
        state.write_text(
            json.dumps({"enabled_packs": [], "pack_roots": []}),
            encoding="utf-8",
        )
        text = entry(self.studio, state)
        self.assertIn("draft the first design note", text)
        self.assertIn("Pack runtime:", text)
        self.assertLess(text.index("draft the first design note"), text.index("Pack runtime:"))

    def test_saved_trail_does_not_open_databases_or_external_connections(self) -> None:
        before = snapshot(self.root)
        with mock.patch.object(sqlite3, "connect", side_effect=AssertionError("startup opened SQLite")), \
                mock.patch.object(socket, "socket", side_effect=AssertionError("startup opened a socket")), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("startup started a process")):
            text = entry(self.studio, self.missing_state)
        self.assertIn("draft the first design note", text)
        self.assertIn("Inspect saved inputs:", text)
        self.assertEqual(snapshot(self.root), before)

    def test_suspended_and_finished_trails_keep_their_exact_continuation_commands(self) -> None:
        task = work_ledger.read_current(self.studio)
        work_ledger.suspend(self.studio, reason="Synthetic pause.")
        text = entry(self.studio, self.missing_state)
        self.assertIn("1 suspended task(s):", text)
        resume = next(line.partition(": ")[2] for line in text.splitlines() if line.startswith("Resume suspended task "))
        self.assertEqual(resume, shown([sys.executable, str(ROOT / "scripts/work_ledger.py"),
            "resume-task", "--studio", str(self.studio), "--task-id", task["task_id"]]))
        # A completed trail receipt is sufficient for startup; the explicit
        # Production command owns validation of its referenced run.
        with (self.studio / "work/ledger.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "finished", "task_id": "finished-fixture", "at": "2026-01-01",
                "text": "Prior synthetic work completed.", "production_run": "saved-run"}) + "\n")
        text = entry(self.studio, self.missing_state)
        self.assertIn("Prior synthetic work completed.", text)
        saved = next(line.partition(": ")[2] for line in text.splitlines() if line.startswith("Saved production revision: "))
        self.assertEqual(saved, shown([sys.executable, str(ROOT / "scripts/production_workflow.py"),
            "status", "--root", str(self.studio), "--run", "saved-run"]))

    def test_outside_any_studio_says_so_and_still_reports_the_pack_runtime(self) -> None:
        outside = self.root / "elsewhere"
        outside.mkdir()
        text = entry(outside, self.missing_state)
        self.assertIn("not in a studio", text)
        self.assertIn("No pack runtime", text)

    def test_a_damaged_studio_is_one_line_and_the_report_goes_on(self) -> None:
        # What an interrupted plain write used to leave behind: half a record.
        (self.studio / "work" / "current.json").write_text('{"task_id": "unfinished', encoding="utf-8")
        text = entry(self.studio, self.missing_state)
        problem = [line for line in text.splitlines() if "cannot be read" in line]
        self.assertEqual(len(problem), 1, text)
        self.assertIn(str(self.studio), problem[0])
        self.assertIn("validate_studio.py", problem[0])
        self.assertNotIn("Traceback", text)
        self.assertIn("No pack runtime", text)

    def test_hints_run_as_printed_with_the_runtime_paths_given(self) -> None:
        cache, managed = self.root / "cache's $literal", self.root / "managed & packs"
        text = entry(self.studio, self.missing_state, "--cache-dir", str(cache), "--managed-root", str(managed))
        hint = next(line for line in text.splitlines() if line.startswith("No pack runtime"))
        command = hint.split("Run: ", 1)[1]
        outside = self.root / "elsewhere's $literal"
        outside.mkdir()
        environment = {**os.environ, "PATH": "", "CPB_HOME": str(self.root / "home")}
        # Keep a developer's personal packs outside this command-execution fixture.
        self.settle_commons(self.missing_state, cache, managed, outside, environment)
        ready = subprocess.run(command, shell=True, cwd=outside, env=environment,
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
        self.assertTrue(self.missing_state.is_file())
        self.assertTrue(cache.is_dir())
        self.assertIn(str(managed.resolve()), ready.stderr)

        create = next(line for line in entry(outside, self.missing_state).splitlines() if "not in a studio" in line)
        command = create.split("Create one with: ", 1)[1]
        command = command.replace("<dir>", "opened").replace("<id>", "opened").replace("<title>", "Opened")
        created = subprocess.run(command, shell=True, cwd=outside, env=environment,
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        opened = outside / "opened"
        self.assertEqual(studio.manifest(opened)["studio_id"], "opened")
        begin = next(line for line in created.stdout.splitlines() if "work_ledger.py" in line)
        command = begin.partition(": ")[2].replace("<goal>", "Synthetic-goal").replace("<step>", "Synthetic-step")
        begun = subprocess.run(command, shell=True, cwd=outside, env=environment,
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(begun.returncode, 0, begun.stdout + begun.stderr)
        self.assertEqual(work_ledger.read_current(opened)["goal"], "Synthetic-goal")

    def test_state_only_hint_completes_the_runtime_selector(self) -> None:
        outside = self.root / "caller"
        outside.mkdir()
        text = entry(outside, self.missing_state)
        hint = next(line for line in text.splitlines() if line.startswith("No pack runtime"))
        environment = {**os.environ, "PATH": "", "CPB_HOME": str(self.root / "home")}
        self.settle_commons(self.missing_state, self.missing_state.parent / "cache",
                            self.missing_state.parent / "packs", outside, environment)
        ready = subprocess.run(hint.split("Run: ", 1)[1], shell=True, cwd=outside, env=environment,
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
        self.assertTrue(self.missing_state.is_file())
        self.assertTrue((self.missing_state.parent / "cache").is_dir())

    def test_work_ledger_accepts_the_studio_after_the_command(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = work_ledger.main(["step", "--studio", str(self.studio), "1", "--note", "brief recorded"])
        self.assertEqual(code, 0)
        current = work_ledger.read_current(self.studio)
        self.assertIsNotNone(current["steps"][0]["done_at"])

    def test_work_ledger_still_accepts_the_studio_before_the_command(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = work_ledger.main(["--studio", str(self.studio), "note", "two directions drafted"])
        self.assertEqual(code, 0)
        self.assertEqual(work_ledger.read_current(self.studio)["notes"][-1], "two directions drafted")


    def test_missing_package_reports_setup_without_running_a_command(self) -> None:
        for metadata, expected in (({"side_effect": session_entry_points.importlib.metadata.PackageNotFoundError}, "numpy is missing"),
                                   ({"return_value": "0.0.0"}, "installed 0.0.0")):
            with self.subTest(expected=expected), \
                    mock.patch.object(session_entry_points.importlib.metadata, "version", **metadata), \
                    mock.patch.object(subprocess, "run", side_effect=AssertionError("startup ran a command")):
                text = entry(self.studio, self.missing_state)
            self.assertIn("Session report unavailable in " + sys.executable, text)
            self.assertIn(expected, text)
            self.assertIn(shown(["uv", "sync", "--locked", "--project", str(ROOT)]), text)

    def invoke_hook(self, command: str, **kwargs):
        if os.name == "posix":
            return subprocess.run(command, shell=True, **kwargs)
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("the host hook needs a POSIX shell")
        return subprocess.run([bash, "-c", command], **kwargs)

    def test_missing_uv_reports_setup_without_changing_files(self) -> None:
        project = self.root / "project without uv"
        project.mkdir()
        environment = {**os.environ, "PATH": "", "CPB_HOME": str(self.root / "home")}
        before = snapshot(self.root)
        for variable in ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT"):
            command = session_hook(variable)["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            result = self.invoke_hook(command, cwd=self.studio,
                                      env={**environment, variable: str(project)}, capture_output=True,
                                      text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("requires uv to locate its existing environment", result.stdout)
            self.assertIn("uv sync --locked", result.stdout)
        self.assertEqual(snapshot(self.root), before)

    def test_missing_environment_does_not_invoke_a_package_manager(self) -> None:
        uv = shutil.which("uv")
        if uv is None:
            self.skipTest("the project environment requires uv")
        project = self.root / "new project's $literal"
        project.mkdir()
        executables = self.root / "commands"
        executables.mkdir()
        called = self.root / "unexpected-package-command"
        for name in ("pip", "python", "python3"):
            stub = executables / name
            stub.write_text("#!/bin/sh\nprintf invoked > " + shlex.quote(str(called)) + "\nexit 97\n", encoding="utf-8")
            stub.chmod(0o755)
        environment = {**os.environ, "PATH": str(Path(uv).parent) + os.pathsep + str(executables),
                       "CPB_HOME": str(self.root / "home")}
        before = snapshot(self.root)
        for configured in (None, str(self.root / "missing external env")):
            environment.pop("UV_PROJECT_ENVIRONMENT", None)
            if configured is not None:
                environment["UV_PROJECT_ENVIRONMENT"] = configured
            for variable in ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT"):
                command = session_hook(variable)["hooks"]["SessionStart"][0]["hooks"][0]["command"]
                result = self.invoke_hook(command, cwd=self.studio,
                                          env={**environment, variable: str(project)}, capture_output=True,
                                          text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("environment is not provisioned", result.stdout)
                self.assertIn("From " + str(project) + ", run: uv sync --locked", result.stdout)
        self.assertFalse(called.exists())
        self.assertEqual(snapshot(self.root), before)

    def test_hook_uses_uv_only_to_find_the_selected_environment(self) -> None:
        project = self.root / "project's $literal"
        project.mkdir()
        executables = self.root / "resolver commands"
        executables.mkdir()
        arguments = self.root / "uv-arguments"
        selections = ((None, project / ".venv", "bin/python"),
                      ("custom env", project / "custom env", "bin/python"),
                      (str(self.root / "external env"), self.root / "external env", "Scripts/python.exe"))
        for configured, selected, relative in selections:
            interpreter = selected / relative
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("#!/bin/sh\nprintf '%s\\n' \"$0\" \"$@\"\n", encoding="utf-8")
            interpreter.chmod(0o755)
            resolver = executables / "uv"
            resolver.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > " + shlex.quote(str(arguments)) +
                                "\ncase \"$1 $2\" in 'python find') ;; *) exit 97;; esac\n" +
                                "printf '%s\\n' " + shlex.quote(str(interpreter)) + "\n", encoding="utf-8")
            resolver.chmod(0o755)
            environment = {**os.environ, "PATH": str(executables), "PLUGIN_ROOT": str(project)}
            environment.pop("UV_PROJECT_ENVIRONMENT", None)
            if configured is not None:
                environment["UV_PROJECT_ENVIRONMENT"] = configured
            command = session_hook("PLUGIN_ROOT")["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            result = self.invoke_hook(command, cwd=self.studio, env=environment,
                                      capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(),
                             [str(interpreter), "-B", str(project) + "/scripts/session_entry_points.py"])
            observed = arguments.read_text(encoding="utf-8").splitlines()
            self.assertEqual(observed[:2], ["python", "find"])
            self.assertEqual(observed[observed.index("--directory") + 1], str(project))
            self.assertIn("--offline", observed)
            self.assertIn("--no-python-downloads", observed)
            self.assertEqual(observed[-1], configured or ".venv")

    def test_startup_preserves_pending_studio_state_and_creates_no_logs(self) -> None:
        import production_store
        import read_context

        uv = shutil.which("uv")
        if uv is None:
            self.skipTest("the project environment requires uv")
        studio.add_character(self.studio, "C01", "")
        with read_context.public_call(), production_store.transaction(self.studio):
            pass
        pending = self.studio / "work/activity/pending-events/fixture.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(json.dumps({"kind": "synthetic-event", "subject": "fixture",
            "revision": "fixture", "details": {}, "at": "2026-01-01T00:00:00Z"}), encoding="utf-8")
        dirty = self.studio / "work/activity/dirty/gallery/fixture"
        dirty.parent.mkdir(parents=True, exist_ok=True)
        dirty.write_bytes(b"")
        environment = {**os.environ, "PATH": str(Path(uv).parent), "PLUGIN_ROOT": str(ROOT),
                       "UV_PROJECT_ENVIRONMENT": str(Path(sys.executable).parent.parent),
                       "CPB_HOME": str(self.root / "home")}
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        before = snapshot(self.root)
        bytecode = {str(path): (path.stat().st_mtime_ns, path.stat().st_size)
                    for path in (ROOT / "scripts").rglob("*.pyc")}
        command = session_hook("PLUGIN_ROOT")["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        result = self.invoke_hook(command, cwd=self.studio / "story", env=environment,
                                  capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("draft the first design note", result.stdout)
        self.assertIn("generated displays were not refreshed", result.stdout)
        self.assertIn("No pack runtime", result.stdout)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual({str(path): (path.stat().st_mtime_ns, path.stat().st_size)
                          for path in (ROOT / "scripts").rglob("*.pyc")}, bytecode)
        sync = next(line for line in result.stdout.splitlines() if "Refresh with: " in line)
        self.assertEqual(sync.partition("Refresh with: ")[2], shown(
            [sys.executable, str(ROOT / "scripts/studio.py"), "sync", "--studio", str(self.studio)]))


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SessionEntry)
    )
    sys.stderr.write(stream.getvalue())
    print(json.dumps({
        "ok": result.wasSuccessful(),
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }))
    raise SystemExit(not result.wasSuccessful())
