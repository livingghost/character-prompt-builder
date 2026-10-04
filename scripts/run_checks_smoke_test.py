#!/usr/bin/env python3
"""The check runner runs commands in parallel with one scratch configuration directory, and reports every failure."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_checks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Each copy writes its name into a shared folder and waits until three names are
# there, so three copies pass together only when they run at the same time.
BARRIER = """
import pathlib, sys, time
folder = pathlib.Path(sys.argv[1])
(folder / sys.argv[2]).write_bytes(b"")
deadline = time.monotonic() + 30
while len(list(folder.iterdir())) < 3 and time.monotonic() < deadline:
    time.sleep(0.05)
sys.exit(0 if len(list(folder.iterdir())) >= 3 else 1)
"""

# Prints what the runner gave the command: its configuration directory, the pack state there and its folder.
ENVIRONMENT = """
import json, os, pathlib
home = pathlib.Path(os.environ["CPB_HOME"])
print(json.dumps({"home": str(home), "cwd": os.getcwd(),
                  "bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
                  "state": json.loads((home / "pack-state.json").read_text(encoding="utf-8"))}))
"""

FAILING = """
print("first line of the failing command")
print("last line of the failing command")
raise SystemExit(3)
"""


class Runner(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="run-checks-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.out = self.work / "out"

    def program(self, name: str, text: str) -> str:
        path = self.work / f"{name}.py"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_quietly(self, selected, jobs):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = run_checks.run(selected, jobs=jobs, out=self.out)
        return code, printed.getvalue()

    def test_commands_run_at_the_same_time(self):
        folder = self.work / "barrier"
        folder.mkdir()
        barrier = self.program("barrier", BARRIER)
        selected = [(f"copy {name}", [sys.executable, barrier, str(folder), name]) for name in "abc"]
        code, printed = self.run_quietly(selected, jobs=3)
        self.assertEqual(0, code, printed)
        self.assertEqual(["a", "b", "c"], sorted(path.name for path in folder.iterdir()))

    def test_every_command_reads_one_scratch_home_holding_the_default_pack_state(self):
        program = self.program("environment", ENVIRONMENT)
        selected = [("first", [sys.executable, program]), ("second", [sys.executable, program])]
        code, printed = self.run_quietly(selected, jobs=2)
        self.assertEqual(0, code, printed)
        default = json.loads((ROOT / "config/default-pack-state.json").read_text(encoding="utf-8"))
        for index in (1, 2):
            observed = json.loads((self.out / f"{index:03d}.log").read_text(encoding="utf-8"))
            self.assertEqual(self.out / "home", Path(observed["home"]))
            self.assertEqual(default, observed["state"])
            self.assertEqual("1", observed["bytecode"])
            self.assertEqual(ROOT, Path(observed["cwd"]).resolve())

    def test_a_failure_is_summarized_with_its_log_tail_and_exits_1(self):
        failing = self.program("failing", FAILING)
        selected = [("passing", [sys.executable, "-c", "print('ok')"]), ("failing", [sys.executable, failing])]
        code, printed = self.run_quietly(selected, jobs=2)
        self.assertEqual(1, code)
        self.assertIn("exit 3", printed)
        self.assertIn("  | last line of the failing command", printed)
        self.assertIn("2 commands: 1 passed, 1 failed", printed)
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual((1, 1), (summary["passed"], summary["failed"]))
        self.assertEqual({"passing": 0, "failing": 3}, {item["label"]: item["exit"] for item in summary["commands"]})

    def test_a_failed_pack_runtime_preparation_stops_the_commands_that_read_it(self):
        selected = [
            ("preparation", [sys.executable, "-c", "raise SystemExit(2)", run_checks.PACK_RUNTIME]),
            ("reader", [sys.executable, "-c", "print('read')", run_checks.PACK_RUNTIME]),
            ("independent", [sys.executable, "-c", "print('ok')"]),
        ]
        code, printed = self.run_quietly(selected, jobs=2)
        self.assertEqual(1, code)
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual({"preparation": 2, "reader": None, "independent": 0},
                         {item["label"]: item["exit"] for item in summary["commands"]})
        self.assertIn("not run", printed)


class Inventory(unittest.TestCase):
    def setUp(self):
        self.commands = run_checks.commands()
        self.labels = [label for label, _ in self.commands]

    def list_output(self, *arguments: str) -> list[str]:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(0, run_checks.main(["--list", *arguments]))
        return printed.getvalue().splitlines()

    def test_every_suite_unittest_module_and_example_check_is_listed_once(self):
        self.assertEqual(len(self.labels), len(set(self.labels)))
        for path in sorted(ROOT.glob("scripts/test_*.py")):
            self.assertIn(f"scripts/{path.name}", self.labels)
        for path in sorted(ROOT.glob("scripts/*_test.py")):
            self.assertIn(f"scripts/{path.name}", self.labels)
        self.assertIn("scripts/run_checks_smoke_test.py", self.labels)
        commands = [run_checks.display(argv) for _, argv in self.commands]
        self.assertIn("cd scripts && python -m unittest test_production_cli", commands)
        self.assertIn("python examples/render-contract/build_example.py --check", commands)

    def test_the_pack_runtime_is_prepared_before_the_commands_that_read_it(self):
        readers = [label for label, argv in self.commands if run_checks.needs_runtime(argv)]
        self.assertEqual("commons-only pack runtime", readers[0])
        self.assertEqual({"preset quality audit", "scripts/default_release_smoke_test.py"}, set(readers[1:]))
        self.assertEqual("commons-only pack runtime", self.labels[0])

    def test_list_prints_every_command_without_running_one(self):
        lines = self.list_output()
        self.assertEqual([run_checks.display(argv) for _, argv in self.commands], lines)
        self.assertIn("python scripts/pack_smoke_test.py", lines)

    def test_only_keeps_the_matching_commands_and_the_runtime_they_read(self):
        self.assertEqual(["python scripts/pack_selector_smoke_test.py"], self.list_output("--only", "pack_selector"))
        lines = self.list_output("--only", "default_release")
        self.assertEqual(2, len(lines))
        self.assertTrue(lines[0].startswith("python scripts/pack_cli.py"))
        self.assertTrue(lines[1].startswith("python scripts/default_release_smoke_test.py ."))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_checks.main(["--list", "--only", "no command has this text"])


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
