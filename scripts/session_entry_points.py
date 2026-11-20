#!/usr/bin/env python3
"""Report the runtime this session starts from, before anything asks for it.

SKILL.md makes resolving the pack runtime a session-entry precondition, and then
has to instruct the agent to go and look. Two of the three questions it asks are
answered by reading one file, so they are answered here as fact instead: whether
the persistent state exists, and what it enables.

The third question, which discovered packs are disabled, needs discovery, and
discovery reads every record in every root. It is the runtime's work and not a
hook's, so this says it is unsettled rather than spending twenty seconds of every
session on it.

The studio the working directory belongs to, and the task it left open, are
reported first, whether or not a pack runtime exists: text authoring resumes
from its trail without an image pack. This reads the saved task trail, not the
Production database or generated displays; deeper inspection is an explicit
next command. An unreadable trail is named with its problem, and the report
goes on.

This reads existing state and writes only to standard output. It creates no
operation log, refreshes no Studio projection, and installs no dependency.
The host selects an already provisioned interpreter; missing package metadata
is reported with an explicit setup command. Functional checks run separately.
It does not read standard input: a host that sends JSON on the pipe and one that leaves the pipe open look
the same from here, and reading would hang on the second. Every command it
prints runs as printed, with the runtime paths it was given.

Usage:
  python scripts/session_entry_points.py [--state-file FILE] [--cache-dir DIR] [--managed-root DIR] [--pack-root DIR]
"""
from __future__ import annotations

import sys

# Keep direct invocations read-only as well as the host hook's `python -B`.
sys.dont_write_bytecode = True

import argparse
import importlib.metadata
import json
from pathlib import Path

from cli_invocation import python_argv, shown

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def read_state(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split()) or type(exc).__name__


def environment_errors() -> list[str]:
    """Read the selected interpreter's declared package versions without importing them."""
    from check_dependencies import load_dependencies

    minimum, declarations = load_dependencies(ROOT / "pyproject.toml")
    errors = []
    if sys.version_info[:2] < minimum:
        errors.append("Python " + ".".join(map(str, minimum)) + " or newer is required")
    for declaration in declarations:
        name, expected = declaration["distribution"], declaration["version"]
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(name + " is missing")
        else:
            if actual != expected:
                errors.append(f"{name} requires {expected}; installed {actual}")
    return errors


def setup_lines() -> list[str]:
    return ["Set up the selected project environment explicitly: " + shown(
                ["uv", "sync", "--locked", "--project", str(ROOT)]),
            "Retain UV_PROJECT_ENVIRONMENT if it selects an environment outside the project. "
            "Then check that environment as described in " + str(ROOT / "DEPENDENCIES.md") + "."]


def authoring_lines(cwd: Path) -> list[str]:
    """Read the saved work trail without opening databases or refreshing displays."""

    from studio_workspace import init_command, manifest, studio_root
    from work_ledger import read_current, read_ledger, session_summary, suspended_tasks

    found = studio_root(cwd)
    root = found or next(
        (parent for parent in (cwd, *cwd.parents) if (parent / "work" / "ledger.jsonl").is_file()),
        None,
    )
    if root is None:
        return [f"The working directory is not in a studio. Create one with: {init_command()}"]
    try:
        lines = []
        if found is not None:
            document = manifest(root)
            lines.append(f"studio {document.get('studio_id')}: {document.get('title')} ({root})")
        else:
            lines.append(f"work trail at {root}")
        active = read_current(root)
        entries = read_ledger(root)
        lines.extend(session_summary(root, active, entries, suspended_tasks(root)))
        run = (active or {}).get("production_run")
        if not run and not active:
            run = next(
                (entry["production_run"] for entry in reversed(entries)
                 if entry.get("event") == "finished" and entry.get("production_run")),
                None,
            )
    except Exception as exc:  # noqa: BLE001 - one damaged studio is reported, never raised
        check = shown(python_argv(ROOT / "scripts" / "validate_studio.py", str(root)))
        return [f"The studio at {root} cannot be read: {one_line(exc)}. Check it with: {check}"]
    workflow = ROOT / "scripts/production_workflow.py"
    lines.append("Inspect current work: " + shown(python_argv(workflow, "status", "--root", str(root))))
    if active:
        lines.append("Inspect saved inputs: " + shown(python_argv(workflow, "inspect-inputs", "--root", str(root))))
    if run:
        lines.append("Saved production revision: " + shown(python_argv(workflow, "status", "--root", str(root), "--run", run)))
    if found is not None:
        lines.append("Saved task trail only; generated displays were not refreshed. Refresh with: " +
                     shown(python_argv(ROOT / "scripts/studio.py", "sync", "--studio", str(root))))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read the current Studio and pack state without changing them or installing dependencies.")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--managed-root", type=Path)
    parser.add_argument("--pack-root", type=Path, action="append", default=[])
    arguments = parser.parse_args(argv)

    # Every path printed here is absolute. The reader's working directory belongs
    # to their own work, not to this skill, so a bare `scripts/...` names nothing
    # they can open.
    lines = [f"Character Prompt Builder is installed at {ROOT}."]
    try:
        problems = environment_errors()
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        problems = ["the selected environment cannot be checked: " + one_line(exc)]
    if problems:
        lines.append("Session report unavailable in " + sys.executable + ": " + "; ".join(problems))
        print("\n".join([*lines, *setup_lines()]))
        return 0
    try:
        lines.extend(authoring_lines(Path.cwd().resolve()))
    except Exception as exc:  # noqa: BLE001 - the hook blocks nothing
        lines.append(f"The studio of the working directory cannot be looked up: {one_line(exc)}")

    from pack_manager import default_settings, pack_runtime_arguments

    settings = default_settings(state_file=arguments.state_file, cache_dir=arguments.cache_dir,
                                managed_root=arguments.managed_root, extra_roots=arguments.pack_root)
    state_file = settings.state_file
    pack_cli = python_argv(ROOT / "scripts" / "pack_cli.py", *pack_runtime_arguments(settings))
    state = read_state(state_file)
    counts = None
    if state is not None:
        enabled, disabled, roots = (
            state.get(name) for name in ("enabled_packs", "disabled_packs", "pack_roots"))
        if all(isinstance(value, (list, type(None))) for value in (enabled, disabled, roots)):
            counts = (len(enabled or []), len(disabled or []), len(roots or []))
    if state is None:
        lines.append(
            f"No pack runtime at {state_file}. Files under the skill directory are not "
            f"activation. Run: {shown([*pack_cli, 'ready'])}"
        )
    elif counts is None:
        lines.append(f"The pack runtime at {state_file} is not in the form the runtime writes. "
                     f"Check it with: {shown([*pack_cli, 'list'])}")
    else:
        lines.append(
            f"Pack runtime: {state_file}, {counts[0]} pack(s) enabled, {counts[1]} disabled by the author, "
            f"{counts[2]} root(s) registered."
        )
        lines.append(
            "Packs that appeared since the author last decided are not checked here. "
            f"Run: {shown([*pack_cli, 'ready'])}"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
