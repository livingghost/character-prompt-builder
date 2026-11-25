#!/usr/bin/env python3
"""Product checks use isolated core sources and state, run in parallel, and report every failure."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
import json, os, pathlib, tempfile
home = pathlib.Path(os.environ["CPB_HOME"])
print(json.dumps({"home": str(home), "cwd": os.getcwd(),
                  "bytecode": os.environ.get("PYTHONDONTWRITEBYTECODE"),
                  "child_workers": os.environ.get("CPB_CHECK_CHILD_WORKERS"),
                  "temporary_directory": tempfile.gettempdir(),
                  "state": json.loads((home / "pack-state.json").read_text(encoding="utf-8"))}))
"""

FAILING = """
print("first line of the failing command")
print("last line of the failing command")
raise SystemExit(3)
"""

CATALOG = """
import json, pathlib, sys
root = pathlib.Path.cwd()
sys.path.insert(0, str(root / "scripts"))
from pack_cache import load_runtime_catalog
catalog = load_runtime_catalog(quiet=True)
print(json.dumps({"packs": sorted(path.name for path in (root / "packs").iterdir()),
                  "source_packs": sorted(catalog.pack_roots), "diagnostics": catalog.diagnostics}))
raise SystemExit(1 if catalog.diagnostics else 0)
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

    def runner_source(self):
        """Small declared source tree for scheduling and reporting contracts."""
        # Windows may expose TEMP through an 8.3 alias; copied paths are resolved.
        source = (self.work / "runner-source").resolve()
        source.mkdir()
        metadata = run_checks.load_package_metadata(ROOT)
        for relative in metadata.release_include:
            original, target = ROOT / relative, source / relative
            if original.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                (target / "synthetic-runner-fixture.txt").write_text(
                    "Synthetic source member for runner contract tests.\n", encoding="utf-8")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
        for relative in ("scripts/run_checks.py", "config/default-pack-state.json", "packs/commons/pack.json"):
            shutil.copyfile(ROOT / relative, source / relative)
        (source / "MANIFEST.json").write_text(
            json.dumps({"fixture": "synthetic runner source inventory"}) + "\n", encoding="utf-8")
        return source

    def run_quietly(self, selected, jobs, *, source=None):
        source = self.runner_source() if source is None else source
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), \
                mock.patch.object(run_checks, "ROOT", source), \
                mock.patch.object(run_checks, "DEFAULT_PACK_STATE", source / "config/default-pack-state.json"):
            code = run_checks.run(selected, jobs=jobs, out=self.out)
        return code, printed.getvalue()

    def source_with_nonrelease_pack(self):
        source = run_checks.copy_check_tree(ROOT, self.work / "source")
        pack = source / "packs" / "nonrelease-fixture"
        (pack / "records").mkdir(parents=True)
        (pack / "pack.json").write_text("{broken synthetic manifest", encoding="utf-8")
        (pack / "records" / "record.json").write_text("{broken synthetic record", encoding="utf-8")
        return source, pack

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
        with mock.patch.dict(os.environ, {"CPB_CHECK_CHILD_WORKERS": "99"}), \
                mock.patch.object(run_checks, "cpu_context", return_value={
                    "available_cpus": 4, "logical_cpus": 64, "cpu_source": "synthetic process allowance"}):
            code, printed = self.run_quietly(selected, jobs=2)
        self.assertEqual(0, code, printed)
        default = json.loads((ROOT / "config/default-pack-state.json").read_text(encoding="utf-8"))
        roots = set()
        temporary_directories = set()
        for index in (1, 2):
            observed = json.loads((self.out / f"{index:03d}.log").read_text(encoding="utf-8"))
            self.assertEqual(self.out / "home", Path(observed["home"]))
            self.assertEqual(default, observed["state"])
            self.assertEqual("1", observed["bytecode"])
            self.assertEqual("2", observed["child_workers"])
            temporary_directories.add(observed["temporary_directory"])
            roots.add(Path(observed["cwd"]).resolve())
        self.assertEqual(len(roots), 1)
        copied_root = roots.pop()
        self.assertNotEqual(ROOT, copied_root)
        self.assertTrue(copied_root.is_relative_to(self.out.resolve()))
        self.assertFalse(copied_root.exists())
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        context = summary["context"]
        self.assertEqual((summary["jobs"], context["jobs"], context["jobs_source"]), (2, 2, "explicit"))
        self.assertEqual(context["child_command_workers"], 2)
        self.assertEqual(temporary_directories, {context["temporary_directory"]})
        self.assertIn("CLI-help workers per suite: 2", printed)
        self.assertIn(f"temporary files: {context['temporary_directory']}", printed)
        self.assertIn(f"workers: 2 (explicit); available CPUs: {context['available_cpus']} ({context['cpu_source']})", printed)
        self.assertIn(f"runtime: {context['python_implementation']} {context['python']}; {context['platform']}", printed)
        self.assertIn(f"python: {context['python_executable']}", printed)
        self.assertLess(printed.index("workers:"), printed.index("[  1/"))

    def test_elapsed_time_includes_source_copy_bytecode_and_cleanup(self):
        program = self.program("timed-environment", ENVIRONMENT)
        selected = [("environment", [sys.executable, program])]
        clock = [0.0]
        context = run_checks.execution_context(1)
        original_home, original_copy = run_checks.scratch_home, run_checks.copy_check_tree
        original_bytecode = run_checks.prepare_bytecode
        original_run = run_checks.subprocess.run
        original_directory = tempfile.TemporaryDirectory
        summary_seen_during_cleanup = []

        def home(out):
            result = original_home(out)
            clock[0] += 1
            return result

        def copy(source, destination):
            result = original_copy(source, destination)
            clock[0] += 2
            return result

        def execute(*args, **kwargs):
            result = original_run(*args, **kwargs)
            clock[0] += 3
            return result

        def bytecode(root):
            result = original_bytecode(root)
            clock[0] += 5
            return result

        out = self.out

        class TimedDirectory(original_directory):
            def cleanup(self):
                summary_seen_during_cleanup.append((out / "summary.json").exists())
                super().cleanup()
                clock[0] += 4

        with mock.patch.object(run_checks, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                mock.patch.object(run_checks, "execution_context", return_value=context), \
                mock.patch.object(run_checks, "scratch_home", side_effect=home), \
                mock.patch.object(run_checks, "copy_check_tree", side_effect=copy), \
                mock.patch.object(run_checks, "prepare_bytecode", side_effect=bytecode), \
                mock.patch.object(run_checks.subprocess, "run", side_effect=execute), \
                mock.patch.object(run_checks.tempfile, "TemporaryDirectory", TimedDirectory):
            code, printed = self.run_quietly(selected, jobs=1)
        self.assertEqual(code, 0, printed)
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["seconds"], 15)
        self.assertEqual(summary["timings_seconds"], {"setup": 1, "copy": 2, "bytecode": 5, "commands": 3, "cleanup": 4})
        self.assertGreater(summary["bytecode_files"], 0)
        self.assertEqual(summary["commands"][0]["seconds"], 3)
        self.assertEqual(summary_seen_during_cleanup, [False])
        observed = json.loads((self.out / "001.log").read_text(encoding="utf-8"))
        self.assertFalse(Path(observed["cwd"]).exists())
        self.assertIn("in 15.0s with 1 workers", printed)
        self.assertIn("elapsed phases: setup 1.000s; copy 2.000s; bytecode 5.000s; commands 3.000s; cleanup 4.000s", printed)

    def test_nonrelease_pack_inputs_and_owner_home_do_not_reach_commands(self):
        source, pack = self.source_with_nonrelease_pack()
        owner_home = self.work / "owner-home"
        owner_home.mkdir()
        owner_state = owner_home / "pack-state.json"
        owner_state.write_text("{unreadable synthetic owner state", encoding="utf-8")
        original = {path: path.read_bytes() for path in (owner_state, pack / "pack.json", pack / "records/record.json")}
        probe = self.program("catalog", CATALOG)
        with mock.patch.dict(os.environ, {"CPB_HOME": str(owner_home)}):
            code, printed = self.run_quietly([("catalog", [sys.executable, probe])], jobs=1, source=source)
        self.assertEqual(code, 0, printed)
        observed = json.loads((self.out / "001.log").read_text(encoding="utf-8"))
        metadata = run_checks.load_package_metadata(source)
        self.assertEqual(observed["packs"], [Path(relative).name for relative in metadata.release_pack_dirs])
        self.assertEqual(observed["source_packs"], sorted(metadata.default_pack_ids))
        self.assertEqual(observed["diagnostics"], [])
        self.assertEqual(original, {path: path.read_bytes() for path in original})

    def test_source_checks_and_existing_manifest_keep_their_exact_bytes(self):
        copied = run_checks.copy_check_tree(ROOT, self.work / "core")
        for name in (*run_checks.SOURCE_CHECK_INPUTS, "MANIFEST.json"):
            source = ROOT / name
            paths = source.rglob("*") if source.is_dir() else [source]
            for path in paths:
                if path.is_file():
                    with self.subTest(path=str(path.relative_to(ROOT))):
                        self.assertEqual(path.read_bytes(), (copied / path.relative_to(ROOT)).read_bytes())
        identity = run_checks.source_identity(copied)
        self.assertEqual(identity['release'], run_checks.load_package_metadata(copied).version)
        for key, name in (('runner_sha256', 'scripts/run_checks.py'), ('inventory_sha256', 'MANIFEST.json')):
            self.assertEqual(identity[key], hashlib.sha256((copied / name).read_bytes()).hexdigest())
        # The copied code identifies itself even if its original checkout changes.
        (copied / 'scripts/run_checks.py').write_bytes(b'# A separate acquired runner.\n')
        self.assertNotEqual(run_checks.source_identity(copied)['runner_sha256'], identity['runner_sha256'])

    def test_core_content_checks_keep_the_selected_release_runtime(self):
        from catalog_retrieval.runtime import using_pack_runtime
        from runtime_paths import PackSettings
        import structure_neutrality_smoke_test as structures
        from validate import run_preset_quality_audit

        source, _ = self.source_with_nonrelease_pack()
        metadata = run_checks.load_package_metadata(source)
        runtime = self.work / "runtime"
        settings = PackSettings(
            roots=tuple(source / relative for relative in metadata.release_pack_dirs),
            state_file=runtime / "state.json", cache_dir=runtime / "cache",
            managed_root=runtime / "managed", quarantine_root=runtime / "quarantine",
            default_enabled_packs=metadata.default_pack_ids,
        )
        errors = []
        with using_pack_runtime(settings):
            run_preset_quality_audit(source, errors)
        self.assertEqual(errors, [])
        with mock.patch.object(structures, "ROOT", source):
            structures.StructureNeutralityTests().test_authored_geometry_in_templates_examples_and_pack_records()

    def test_core_audit_reports_a_missing_required_resource_without_exiting(self):
        from catalog_retrieval.runtime import using_pack_runtime
        from pack_manager import initialize_pack
        from runtime_paths import PackSettings
        from validate import run_preset_quality_audit

        pack = self.work / "missing-policy-fixture"
        manifest = initialize_pack(pack, name="Synthetic pack without policy bindings")
        runtime = self.work / "runtime"
        settings = PackSettings(
            roots=(pack,), state_file=runtime / "state.json", cache_dir=runtime / "cache",
            managed_root=runtime / "managed", quarantine_root=runtime / "quarantine",
            default_enabled_packs=(manifest["pack_id"],),
        )
        errors = []
        with using_pack_runtime(settings):
            run_preset_quality_audit(ROOT, errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("audit_preset_quality.py refused the shipped catalog", errors[0])
        self.assertIn("archetype-policy", errors[0])

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
        self.assertEqual((summary["passed"], summary["failed"]), (1, 2))


class BytecodePreparation(unittest.TestCase):
    def test_read_only_children_reuse_bytecode_and_detect_same_size_same_mtime_edits(self):
        with tempfile.TemporaryDirectory(prefix="check-bytecode-") as temporary:
            work = Path(temporary)
            source = work / "original"
            (source / "scripts").mkdir(parents=True)
            original = source / "scripts" / "bytecode_fixture.py"
            original.write_text("VALUE = 'first'\n", encoding="utf-8")
            root = work / "copy"
            run_checks.copy_runtime_tree(source, root, ("scripts",))
            module = root / "scripts" / original.name
            outside = work / "outside-cache"
            with mock.patch.object(sys, "pycache_prefix", str(outside)):
                self.assertEqual(run_checks.prepare_bytecode(root), 1)
            cache, = (root / "scripts" / "__pycache__").glob("*.pyc")
            cached = cache.read_bytes()
            self.assertFalse(outside.exists())
            self.assertFalse((source / "scripts" / "__pycache__").exists())

            probe = (
                "import json, pathlib, sys\n"
                "sys.path.insert(0, str(pathlib.Path.cwd() / 'scripts'))\n"
                "compiled = []\n"
                "def observe(event, arguments):\n"
                "    if event == 'compile' and str(arguments[1]).endswith('bytecode_fixture.py'):\n"
                "        compiled.append(arguments[1])\n"
                "sys.addaudithook(observe)\n"
                "import bytecode_fixture\n"
                "print(json.dumps({'value': bytecode_fixture.VALUE, 'compiled': compiled}))\n"
            )
            argv = [sys.executable, "-B", "-c", probe]
            with mock.patch.dict(os.environ, {"PYTHONPYCACHEPREFIX": str(outside)}):
                first = run_checks.run_one(1, "cached import", argv, work, root, child_workers=1)
                before = module.stat()
                module.write_text("VALUE = 'later'\n", encoding="utf-8")
                os.utime(module, ns=(before.st_atime_ns, before.st_mtime_ns))
                second = run_checks.run_one(2, "changed import", argv, work, root, child_workers=1)
            self.assertEqual((first["exit"], second["exit"]), (0, 0))
            self.assertEqual(json.loads((work / "001.log").read_text(encoding="utf-8")),
                             {"value": "first", "compiled": []})
            self.assertEqual(json.loads((work / "002.log").read_text(encoding="utf-8")),
                             {"value": "later", "compiled": [str(module)]})
            self.assertEqual((module.stat().st_size, module.stat().st_mtime_ns),
                             (before.st_size, before.st_mtime_ns))
            self.assertEqual(cache.read_bytes(), cached)
            self.assertFalse(outside.exists())

            # The release inventory does not carry the disposable import cache.
            released = work / "release"
            run_checks.copy_runtime_tree(root, released, ("scripts",))
            self.assertEqual(sorted(path.relative_to(released).as_posix()
                                    for path in released.rglob("*") if path.is_file()),
                             ["scripts/bytecode_fixture.py"])
            self.assertEqual(original.read_text(encoding="utf-8"), "VALUE = 'first'\n")


class WorkerPolicy(unittest.TestCase):
    def test_automatic_workers_follow_process_availability_up_to_eight(self):
        with mock.patch.object(run_checks.os, "cpu_count", return_value=64), \
                mock.patch.object(run_checks.os, "sched_getaffinity", return_value=set(range(32)), create=True):
            for available, expected, children in ((1, 1, 1), (2, 2, 1), (4, 4, 1),
                                                  (7, 7, 1), (8, 8, 1), (9, 8, 1),
                                                  (12, 8, 1), (16, 8, 2), (24, 8, 3), (64, 8, 4)):
                with self.subTest(available=available), \
                        mock.patch.object(run_checks.os, "process_cpu_count", return_value=available, create=True):
                    context = run_checks.execution_context(None)
                    self.assertEqual((context["jobs"], context["jobs_source"]), (expected, "automatic"))
                    self.assertEqual((context["available_cpus"], context["logical_cpus"]), (available, 64))
                    self.assertEqual(context["cpu_source"], "os.process_cpu_count")
                    self.assertEqual(context["child_command_workers"], children)

    def test_cpu_discovery_uses_affinity_then_reported_cpu_count(self):
        cases = (
            ({1, 3}, 32, 2, 2, "os.sched_getaffinity"),
            (set(range(16)), 32, 16, 8, "os.sched_getaffinity"),
            (OSError("affinity unavailable"), 64, 64, 8, "os.cpu_count"),
            (NotImplementedError(), None, 1, 1, "fallback"),
        )
        for affinity, logical, available, expected, source in cases:
            with self.subTest(source=source), \
                    mock.patch.object(run_checks.os, "process_cpu_count", None, create=True), \
                    mock.patch.object(run_checks.os, "sched_getaffinity", create=True) as probe, \
                    mock.patch.object(run_checks.os, "cpu_count", return_value=logical):
                if isinstance(affinity, Exception):
                    probe.side_effect = affinity
                else:
                    probe.return_value = affinity
                context = run_checks.execution_context(None)
                self.assertEqual((context["available_cpus"], context["jobs"], context["cpu_source"]),
                                 (available, expected, source))

    def test_explicit_workers_override_the_automatic_limit_and_cpu_count(self):
        with mock.patch.object(run_checks.os, "process_cpu_count", return_value=1, create=True):
            context = run_checks.execution_context(12)
        self.assertEqual((context["jobs"], context["jobs_source"], context["available_cpus"]), (12, "explicit", 1))
        self.assertEqual(context["child_command_workers"], 1)
        with mock.patch.object(run_checks.os, "process_cpu_count", return_value=9, create=True):
            self.assertEqual(run_checks.execution_context(1)["child_command_workers"], 4)
            self.assertEqual(run_checks.execution_context(3)["child_command_workers"], 3)
            import documentation_contract_smoke_test as documentation_contract
            with mock.patch.dict(os.environ):
                os.environ.pop("CPB_CHECK_CHILD_WORKERS", None)
                self.assertEqual(documentation_contract.help_workers(), 4)


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
        # An example script with another name runs the same way when it offers --check.
        self.assertIn("python examples/production-execution/repair_example.py --check", commands)

    def test_the_pack_runtime_is_prepared_before_the_commands_that_read_it(self):
        readers = [label for label, argv in self.commands if run_checks.needs_runtime(argv)]
        self.assertEqual("commons-only pack runtime", readers[0])
        self.assertEqual({"preset quality audit", "scripts/default_release_smoke_test.py",
                          "catalog retrieval", "knowledge discovery"}, set(readers[1:]))
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

    def test_jobs_option_preserves_explicit_values_and_automatic_selection(self):
        for options, expected in (([], None), (["--jobs", "12"], 12)):
            with self.subTest(options=options), mock.patch.object(run_checks, "run", return_value=0) as execute:
                self.assertEqual(run_checks.main(["--only", "pack_selector", "--out", "runner-fixture", *options]), 0)
                self.assertEqual(execute.call_args.kwargs["jobs"], expected)
                self.assertEqual(execute.call_args.args[0],
                                 [item for item in self.commands if item[0] == "scripts/pack_selector_smoke_test.py"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_checks.main(["--jobs", "0", "--list"])
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), self.assertRaises(SystemExit) as help_exit:
            run_checks.main(["--help"])
        self.assertEqual(help_exit.exception.code, 0)
        self.assertIn("capped at 8", " ".join(printed.getvalue().split()))


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
