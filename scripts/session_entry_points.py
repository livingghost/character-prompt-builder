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
from its trail without an image pack. A studio that cannot be read is named in
one line with its problem, and the report goes on.

This writes to standard output and blocks nothing. It does not read standard
input: a host that sends JSON on the pipe and one that leaves the pipe open look
the same from here, and reading would hang on the second. Every command it
prints runs as printed, with the runtime paths it was given.

Usage:
  python scripts/session_entry_points.py [--state-file FILE] [--cache-dir DIR] [--managed-root DIR]
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path


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


def authoring_lines(cwd: Path) -> list[str]:
    """The studio or work trail the working directory belongs to, and where its work stands."""

    from studio import init_command, status, studio_root
    from work_ledger import read_current, read_ledger, show

    found = studio_root(cwd)
    root = found or next(
        (parent for parent in (cwd, *cwd.parents) if (parent / "work" / "ledger.jsonl").is_file()),
        None,
    )
    if root is None:
        return [f"The working directory is not in a studio. Create one with: {init_command()}"]
    try:
        lines = [status(root) if found is not None else show(root)]
        active = read_current(root)
        records = read_ledger(root)
        run = (active or {}).get("production_run")
        if not run and not active:
            run = next(
                (entry["production_run"] for entry in reversed(records)
                 if entry.get("event") == "finished" and entry.get("production_run")),
                None,
            )
    except Exception as exc:  # noqa: BLE001 - one damaged studio is reported, never raised
        check = shlex.join(["python", str(ROOT / "scripts" / "validate_studio.py"), str(root)])
        return [f"The studio at {root} cannot be read: {one_line(exc)}. Check it with: {check}"]
    if run:
        command = ["python", str(ROOT / "scripts/production_workflow.py"), "resume", "--root", str(root), "--run", run]
        lines.append("Production status: " + shlex.join(command))
    elif active:
        lines.append("No prepared run for the open task. Follow Production Execution to prepare exact inputs before delivery.")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Announce the pack runtime this session starts from.")
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--managed-root", type=Path)
    arguments = parser.parse_args(argv)

    # Every path printed here is absolute. The reader's working directory belongs
    # to their own work, not to this skill, so a bare `scripts/...` names nothing
    # they can open.
    lines = [f"Character Prompt Builder is installed at {ROOT}."]
    try:
        lines.extend(authoring_lines(Path.cwd().resolve()))
    except Exception as exc:  # noqa: BLE001 - the hook blocks nothing
        lines.append(f"The studio of the working directory cannot be looked up: {one_line(exc)}")

    from pack_manager import default_settings

    explicit = {"--state-file": arguments.state_file, "--cache-dir": arguments.cache_dir,
                "--managed-root": arguments.managed_root}
    state_file = default_settings(state_file=arguments.state_file, cache_dir=arguments.cache_dir,
                                  managed_root=arguments.managed_root).state_file
    pack_cli = ["python", str(ROOT / "scripts" / "pack_cli.py")]
    for flag, value in explicit.items():
        if value is not None:
            pack_cli.extend((flag, str(value.resolve())))
    state = read_state(state_file)
    counts = None
    if state is not None:
        enabled, disabled, roots, providers = (
            state.get(name) for name in ("enabled_packs", "disabled_packs", "pack_roots", "resource_providers"))
        if all(isinstance(value, (list, dict, type(None))) for value in (enabled, disabled, roots, providers)):
            counts = (len(enabled or []), len(disabled or []), len(roots or []), len(providers or {}))
    if state is None:
        lines.append(
            f"No pack runtime at {state_file}. Files under the skill directory are not "
            f"activation. Run: {shlex.join([*pack_cli, 'ready'])}"
        )
    elif counts is None:
        lines.append(f"The pack runtime at {state_file} is not in the form the runtime writes. "
                     f"Check it with: {shlex.join([*pack_cli, 'list'])}")
    else:
        lines.append(
            f"Pack runtime: {state_file}, {counts[0]} pack(s) enabled, {counts[1]} disabled by the author, "
            f"{counts[2]} root(s) registered, {counts[3]} resource provider(s) selected."
        )
        lines.append(
            "Packs that appeared since the author last decided are not checked here. "
            f"Run: {shlex.join([*pack_cli, 'ready'])}"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
