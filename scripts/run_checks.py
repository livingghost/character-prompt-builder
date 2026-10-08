#!/usr/bin/env python3
"""Run every test suite and check command of the repository once, in parallel.

CI runs it once per operating system, and a contributor runs it the same way:

    python scripts/run_checks.py               every command, one worker per processor
    python scripts/run_checks.py --only pack   the commands whose label or command contains "pack"
    python scripts/run_checks.py --list        print the commands without running them

The commands are:

- every ``scripts/*_test.py`` suite, found by name;
- every ``scripts/test_*.py`` unittest module, run from ``scripts/`` as ``python -m unittest <module>``;
- every ``examples/*/build_example.py`` that offers ``--check``;
- the validators in ``VALIDATORS`` and the audit of the shipped packs.

Each command runs from the repository root with ``CPB_HOME`` at ``<out>/home``,
one scratch configuration directory whose pack state is
``config/default-pack-state.json``. The pack state of the person running the
checks therefore never reaches a command. Each command writes its output to
``<out>/<index>.log``. The runner prints one line per finished
command, then the slowest ten and the log tail of every failure:

    [ 63/109]    58.5s  exit 0  python scripts/production_resume_smoke_test.py
    ...
    slowest:
        199.8s  python scripts/production_workflow_smoke_test.py
        157.1s  cd scripts && python -m unittest test_production_execution
    ...
    109 commands: 105 passed, 4 failed in 379.7s with 8 workers

It writes ``<out>/summary.json`` and exits 1 when any command failed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_PACK_STATE = ROOT / "config" / "default-pack-state.json"
COMMONS_PACK = ROOT / "packs" / "commons" / "pack.json"

# An argument holding this token names the commons-only pack runtime of the run.
# The first command naming it prepares that runtime before the other commands
# start, and a command naming it runs only after that preparation succeeds.
PACK_RUNTIME = "{pack-runtime}"
RUNTIME_ARGUMENTS = (
    "--state-file", PACK_RUNTIME + "/pack-state.json",
    "--cache-dir", PACK_RUNTIME + "/cache",
    "--managed-root", PACK_RUNTIME + "/managed",
)

# Every other suite runs without arguments.
SUITE_ARGUMENTS = {"default_release_smoke_test.py": (".", *RUNTIME_ARGUMENTS)}

VALIDATORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("release contract", ("scripts/release_contract.py",)),
    ("state protocol", ("scripts/validate_state_protocol.py", ".")),
    ("integration contracts", ("scripts/validate_integration.py",)),
    ("execution routes", ("scripts/execution_routes.py", "validate")),
)

# The longest commands of a full run start first, so none of them starts last
# and holds the run open alone.
LONGEST_FIRST = (
    "scripts/production_workflow_smoke_test.py",
    "scripts/test_production_execution.py",
    "scripts/test_production_foundation.py",
    "scripts/test_production_review.py",
    "scripts/state_generation_smoke_test.py",
    "scripts/execution_lifecycle_smoke_test.py",
    "scripts/dispatch_recovery_smoke_test.py",
    "scripts/test_production_variation.py",
    "scripts/test_production_boundaries.py",
    "scripts/test_runtime_snapshot.py",
    "scripts/test_model_observation.py",
    "scripts/reimplementation_smoke_test.py",
    "scripts/test_production_adoption.py",
    "scripts/test_production_retarget.py",
    "scripts/production_direction_smoke_test.py",
    "scripts/image_edit_smoke_test.py",
    "scripts/production_resume_smoke_test.py",
    "scripts/craft_consultation_smoke_test.py",
    "scripts/character_sheet_smoke_test.py",
    "scripts/generation_payload_smoke_test.py",
)

TAIL_LINES = 40


def _python(*arguments: str) -> list[str]:
    return [sys.executable, *arguments]


def suite_files() -> list[Path]:
    """Every suite run as its own script: each scripts/*_test.py file."""
    return sorted(path for path in SCRIPTS.glob("*_test.py") if not path.name.startswith("test_"))


def unittest_modules() -> list[Path]:
    """Every unittest module: each scripts/test_*.py file."""
    return sorted(SCRIPTS.glob("test_*.py"))


def example_checks() -> list[Path]:
    """Every example builder that offers --check."""
    return sorted(
        path for path in (ROOT / "examples").glob("*/build_example.py")
        if "--check" in path.read_text(encoding="utf-8")
    )


def commands() -> list[tuple[str, list[str]]]:
    """Return every (label, argv) pair the runner runs, in start order.

    A suite and a unittest module are labelled by their repository path. A
    unittest module's argv runs from scripts/, see working_directory(). Reading
    this list writes nothing.
    """
    commons = json.loads(COMMONS_PACK.read_text(encoding="utf-8"))["pack_id"]
    suites = [
        (f"scripts/{path.name}", _python(f"scripts/{path.name}", *SUITE_ARGUMENTS.get(path.name, ())))
        for path in suite_files()
    ]
    modules = [(f"scripts/{path.name}", _python("-m", "unittest", path.stem)) for path in unittest_modules()]
    examples = [
        (f"example {path.parent.name}", _python(path.relative_to(ROOT).as_posix(), "--check"))
        for path in example_checks()
    ]
    validators = [(label, _python(*arguments)) for label, arguments in VALIDATORS]
    validators.append(("preset quality audit", _python("scripts/audit_preset_quality.py", ".", *RUNTIME_ARGUMENTS)))
    preparation = ("commons-only pack runtime",
                   _python("scripts/pack_cli.py", *RUNTIME_ARGUMENTS, "ready", "--only", commons))
    rank = {label: index for index, label in enumerate(LONGEST_FIRST)}
    listed = sorted(suites + modules + examples + validators, key=lambda item: rank.get(item[0], len(rank)))
    return [preparation, *listed]


def working_directory(argv: Sequence[str]) -> Path:
    """A unittest module runs from scripts/; every other command runs from the repository root."""
    return SCRIPTS if list(argv[1:3]) == ["-m", "unittest"] else ROOT


def display(argv: Sequence[str]) -> str:
    """The command as a person types it from the repository root."""
    text = shlex.join(["python", *argv[1:]])
    return "cd scripts && " + text if working_directory(argv) == SCRIPTS else text


def needs_runtime(argv: Sequence[str]) -> bool:
    return any(PACK_RUNTIME in argument for argument in argv)


def select(listed: Sequence[tuple[str, list[str]]], only: str | None) -> list[tuple[str, list[str]]]:
    """Keep the commands whose label or command contains ``only``, and the pack runtime preparation they read."""
    if not only:
        return list(listed)
    chosen = [item for item in listed if only in item[0] or only in display(item[1])]
    preparation = next((item for item in listed if needs_runtime(item[1])), None)
    if preparation is not None and preparation not in chosen and any(needs_runtime(argv) for _, argv in chosen):
        chosen.insert(0, preparation)
    return chosen


def scratch_home(out: Path) -> Path:
    """Create the configuration directory every command reads, whose pack state enables the shipped packs alone."""
    home = out / "home"
    home.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DEFAULT_PACK_STATE, home / "pack-state.json")
    return home


def run_one(index: int, label: str, argv: Sequence[str], out: Path) -> dict[str, Any]:
    """Run one command with CPB_HOME at the scratch home and record its exit status, time and log."""
    runtime = str(out / "pack-runtime")
    resolved = [argument.replace(PACK_RUNTIME, runtime) for argument in argv]
    environment = {**os.environ, "CPB_HOME": str(out / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
    log = out / f"{index:03d}.log"
    started = time.monotonic()
    with log.open("wb") as handle:
        try:
            code = subprocess.run(resolved, cwd=working_directory(argv), env=environment, stdin=subprocess.DEVNULL,
                                  stdout=handle, stderr=subprocess.STDOUT, check=False).returncode
        except OSError as exc:
            handle.write(f"the command did not start: {exc}\n".encode("utf-8"))
            code = 127
    seconds = time.monotonic() - started
    return {"index": index, "label": label, "command": display(argv), "exit": code,
            "seconds": round(seconds, 2), "log": str(log)}


def refused(index: int, label: str, argv: Sequence[str], out: Path, reason: str) -> dict[str, Any]:
    log = out / f"{index:03d}.log"
    log.write_bytes((reason + "\n").encode("utf-8"))
    return {"index": index, "label": label, "command": display(argv), "exit": None, "seconds": 0.0, "log": str(log)}


def tail(path: str, count: int = TAIL_LINES) -> list[str]:
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    return text.splitlines()[-count:]


def run(selected: Sequence[tuple[str, list[str]]], *, jobs: int, out: Path) -> int:
    """Run the commands with ``jobs`` workers, print each result and the summary, and return the exit status."""
    out.mkdir(parents=True, exist_ok=True)
    scratch_home(out)
    total = len(selected)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    started = time.monotonic()

    def report(result: dict[str, Any]) -> None:
        with lock:
            results.append(result)
            status = "not run" if result["exit"] is None else f"exit {result['exit']}"
            print(f"[{len(results):3d}/{total}] {result['seconds']:7.1f}s  {status}  {result['command']}", flush=True)

    numbered = list(enumerate(selected, start=1))
    preparation = next(((index, item) for index, item in numbered if needs_runtime(item[1])), None)
    pending = numbered
    if preparation is not None:
        index, (label, argv) = preparation
        first = run_one(index, label, argv, out)
        report(first)
        pending = [entry for entry in numbered if entry[0] != index]
        if first["exit"] != 0:
            reason = f"not run: the pack runtime preparation failed, see {first['log']}"
            for index, (label, argv) in [entry for entry in pending if needs_runtime(entry[1][1])]:
                report(refused(index, label, argv, out, reason))
            pending = [entry for entry in pending if not needs_runtime(entry[1][1])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, index, label, argv, out) for index, (label, argv) in pending]
        try:
            for future in concurrent.futures.as_completed(futures):
                report(future.result())
        except KeyboardInterrupt:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    wall = time.monotonic() - started

    results.sort(key=lambda item: item["index"])
    failed = [item for item in results if item["exit"] != 0]
    summary = {"jobs": jobs, "seconds": round(wall, 2), "passed": len(results) - len(failed),
               "failed": len(failed), "commands": results}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print()
    print("slowest:")
    for item in sorted(results, key=lambda entry: entry["seconds"], reverse=True)[:10]:
        print(f"  {item['seconds']:7.1f}s  {item['command']}")
    for item in failed:
        status = "not run" if item["exit"] is None else f"exit {item['exit']}"
        print()
        print(f"FAILED ({status}): {item['command']}  log {item['log']}")
        for line in tail(item["log"]):
            print("  | " + line)
    print()
    print(f"{total} commands: {summary['passed']} passed, {summary['failed']} failed "
          f"in {wall:.1f}s with {jobs} workers")
    print(f"summary: {out / 'summary.json'}")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run every test suite and check command once, in parallel.")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                        help="commands run at once (default: the processor count)")
    parser.add_argument("--out", type=Path, help="folder for the logs and summary.json (default: a new temporary folder)")
    parser.add_argument("--only", metavar="SUBSTRING",
                        help="run the commands whose label or command contains SUBSTRING")
    parser.add_argument("--list", action="store_true", help="print the commands without running them")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    selected = select(commands(), args.only)
    if not selected:
        parser.error(f"no command contains {args.only!r}")
    if args.list:
        for _, command in selected:
            print(display(command))
        return 0
    out = args.out.resolve() if args.out else Path(tempfile.mkdtemp(prefix="cpb-checks-"))
    return run(selected, jobs=args.jobs, out=out)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
