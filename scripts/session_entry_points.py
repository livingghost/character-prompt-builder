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

This writes to standard output and blocks nothing. It does not read standard
input: a host that sends JSON on the pipe and one that leaves the pipe open look
the same from here, and reading would hang on the second.

Usage:
  python scripts/session_entry_points.py [--state-file FILE]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_HOME = Path.home() / ".character-prompt-builder"
STATE_FILE = STATE_HOME / "pack-state.json"


def read_state(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Announce the pack runtime this session starts from.")
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    arguments = parser.parse_args(argv)

    # Every path printed here is absolute. The reader's working directory belongs
    # to their own work, not to this skill, so a bare `scripts/...` names nothing
    # they can open.
    lines = [f"Character Prompt Builder is installed at {ROOT}."]

    from work_ledger import show, read_current, read_ledger
    import shlex
    for parent in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (parent / "work" / "ledger.jsonl").is_file():
            lines.append(show(parent))
            active=read_current(parent)
            records=read_ledger(parent)
            run=(active or {}).get("production_run")
            if not run and not active:
                run=next((entry["production_run"] for entry in reversed(records) if entry.get("event")=="finished" and entry.get("production_run")),None)
            if run:
                command=["python",str(ROOT / "scripts/production_workflow.py"),"resume","--root",str(parent),"--run",run]
                lines.append("Production status: " + shlex.join(command))
            elif active:
                lines.append("No prepared run for the open task. Follow Production Execution to prepare exact inputs before delivery.")
            break

    state = read_state(arguments.state_file)
    if state is None:
        lines.append(
            f"No pack runtime at {arguments.state_file}. Files under the skill directory are not "
            f"activation. Run: python {ROOT / 'scripts' / 'pack_cli.py'} state-init"
        )
        print(" ".join(lines))
        return 0

    enabled = state.get("enabled_packs") or []
    roots = state.get("pack_roots") or []
    providers = state.get("resource_providers") or {}
    lines.append(
        f"Pack runtime: {arguments.state_file}, {len(enabled)} pack(s) enabled, "
        f"{len(roots)} root(s) registered, {len(providers)} resource provider(s) selected."
    )
    lines.append(
        "Discovered packs that are present but disabled are not settled here; discovery reads "
        f"every record in every root. Run: python {ROOT / 'scripts' / 'pack_cli.py'} list"
    )
    # The studio the working directory belongs to, and where its work stands.
    # A session that lost its context reads this before anything else.
    from studio import status, studio_root

    found = studio_root(Path.cwd().resolve())
    if found is None:
        lines.append(
            "The working directory is not in a studio; "
            f"python {ROOT / 'scripts' / 'studio.py'} init creates one."
        )
    else:
        lines.append(status(found))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
