#!/usr/bin/env python3
"""Session entry reports the studio and its open task before the pack runtime, with or without one.

Text authoring resumes from the work trail without an image pack, so the studio
lookup must not wait on the pack state. The work ledger also accepts the studio
after the command, as Studio Runtime writes the commands.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import session_entry_points  # noqa: E402
import studio  # noqa: E402
import work_ledger  # noqa: E402


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

    def test_open_task_prints_before_a_missing_pack_runtime(self) -> None:
        text = entry(self.studio / "story", self.missing_state)
        self.assertIn("draft the first design note", text)
        self.assertIn("No pack runtime", text)
        self.assertLess(text.index("draft the first design note"), text.index("No pack runtime"))

    def test_open_task_prints_before_an_existing_pack_runtime(self) -> None:
        state = self.root / "pack-state.json"
        state.write_text(
            json.dumps({"enabled_packs": [], "pack_roots": [], "resource_providers": {}}),
            encoding="utf-8",
        )
        text = entry(self.studio, state)
        self.assertIn("draft the first design note", text)
        self.assertIn("Pack runtime:", text)
        self.assertLess(text.index("draft the first design note"), text.index("Pack runtime:"))

    def test_outside_any_studio_says_so_and_still_reports_the_pack_runtime(self) -> None:
        outside = self.root / "elsewhere"
        outside.mkdir()
        text = entry(outside, self.missing_state)
        self.assertIn("not in a studio", text)
        self.assertIn("No pack runtime", text)

    def test_a_damaged_studio_is_one_line_and_the_report_goes_on(self) -> None:
        studio.add_character(self.studio, "C01", "")
        # What an interrupted plain write used to leave behind: half a record.
        (self.studio / "characters" / "C01" / "iterations.jsonl").write_text('{"iteration_id": "it-00', encoding="utf-8")
        text = entry(self.studio, self.missing_state)
        problem = [line for line in text.splitlines() if "cannot be read" in line]
        self.assertEqual(len(problem), 1, text)
        self.assertIn(str(self.studio), problem[0])
        self.assertIn("validate_studio.py", problem[0])
        self.assertNotIn("Traceback", text)
        self.assertIn("No pack runtime", text)

    def test_hints_run_as_printed_with_the_runtime_paths_given(self) -> None:
        cache, managed = self.root / "cache", self.root / "managed"
        text = entry(self.studio, self.missing_state, "--cache-dir", str(cache), "--managed-root", str(managed))
        hint = next(line for line in text.splitlines() if line.startswith("No pack runtime"))
        command = shlex.split(hint.split("Run: ", 1)[1], posix=True)
        self.assertEqual(command[-1], "ready")
        self.assertEqual(command[command.index("--state-file") + 1], str(self.missing_state.resolve()))
        self.assertEqual(command[command.index("--cache-dir") + 1], str(cache.resolve()))
        self.assertEqual(command[command.index("--managed-root") + 1], str(managed.resolve()))
        outside = self.root / "elsewhere"
        outside.mkdir()
        create = next(line for line in entry(outside, self.missing_state).splitlines() if "not in a studio" in line)
        arguments = shlex.split(create.split("Create one with: ", 1)[1], posix=True)
        self.assertEqual(arguments[2:], ["init", "--out", "<dir>", "--studio-id", "<id>", "--title", "<title>"])

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


if __name__ == "__main__":
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
