"""Pytest bridge that runs every scripts/ smoke suite as a subprocess.

Each parametrized case executes ``python scripts/<name>.py [args...]``
with cwd = repository root and PYTHONDONTWRITEBYTECODE=1,
mirroring how validate.py, package.py, and CI invoke the suites, and
asserts a zero exit code.  On failure the suite's full stdout and stderr
are echoed in the assertion message.

The known-heavy suites carry the "slow" marker (registered in
conftest.py); deselect them with -m "not slow" for a quick lane.  The
default run includes everything.

validate.py and package.py themselves are deliberately excluded: they
are the integrator's release gates and too heavy for this bridge.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

# Per-suite subprocess timeout in seconds (generous: the heaviest suites
# run multi-thousand-check batteries).
SUITE_TIMEOUT = 600

# Sentinel expanded at run time into --state-file/--cache-dir/
# --managed-root arguments under the test's tmp_path, matching how
# package.py builds a fresh pack runtime root for suites that need one.
RUNTIME_DIRS = object()

# A pack the home of the person running the tests enables and no suite may find.
MISSING_PACK_ID = "0199aaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee"

SLOW = pytest.mark.slow

# Discover the entire inventory; a new suite must never be silently omitted.
# Only invocation differences and known-heavy suites require explicit entries.
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SLOW_SUITES = {
    "catalog_cli_runtime_smoke_test.py", "character_sheet_smoke_test.py",
    "fresh_session_runtime_smoke_test.py", "generation_payload_smoke_test.py",
    "pack_release_gate_smoke_test.py", "pack_smoke_test.py",
    "release_file_operations_smoke_test.py", "state_generation_smoke_test.py",
}
SUITE_ARGUMENTS = {"default_release_smoke_test.py": (".", RUNTIME_DIRS)}
SUITE_FILES = sorted({path.name for path in SCRIPT_DIR.glob("*smoke_test.py")}
                     | {"reference_runtime_cli_contract_test.py"})
SUITES = [
    pytest.param(name, SUITE_ARGUMENTS.get(name, ()), id=Path(name).stem,
                 marks=SLOW if name in SLOW_SUITES else ())
    for name in SUITE_FILES
]


def test_suite_inventory():
    discovered = {path.name for path in SCRIPT_DIR.glob("*smoke_test.py")}
    discovered.add("reference_runtime_cli_contract_test.py")
    registered = [case.values[0] for case in SUITES]
    assert len(registered) == len(set(registered)), "duplicate suite registration"
    assert set(registered) == discovered, "smoke suite inventory and registration differ"
    assert SLOW_SUITES <= discovered, "stale slow-suite annotation"
    assert set(SUITE_ARGUMENTS) <= discovered, "stale suite argument override"
    assert all((SCRIPT_DIR / name).is_file() for name in registered)


def _default_packs_only(selectors, env):
    """Create a pack state that enables the shipped default packs alone, whatever other packs the working tree holds."""
    defaults = json.loads(
        (SCRIPT_DIR.parent / "config" / "default-pack-state.json").read_text(encoding="utf-8")
    )["enabled_packs"]
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "pack_cli.py"), *selectors, "ready",
         *(item for pack_id in defaults for item in ("--only", pack_id))],
        check=True, capture_output=True, text=True, encoding="utf-8", env=env,
    )


def _resolve_args(args, tmp_path):
    resolved = []
    for arg in args:
        if arg is RUNTIME_DIRS:
            runtime_root = tmp_path / "pack-runtime"
            runtime_root.mkdir(parents=True, exist_ok=False)
            selectors = [
                "--state-file",
                str(runtime_root / "pack-state.json"),
                "--cache-dir",
                str(runtime_root / "cache"),
                "--managed-root",
                str(runtime_root / "managed"),
            ]
            _default_packs_only(selectors, {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            resolved.extend(selectors)
        else:
            resolved.append(arg)
    return resolved


@pytest.mark.parametrize(("script", "args"), SUITES)
def test_smoke_suite(repo_root, tmp_path, script, args):
    command = [sys.executable, "scripts/" + script, *_resolve_args(args, tmp_path)]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    # Each suite gets its own home, so the pack state and host configuration of
    # the person running the tests never reach it. That home's pack state enables
    # a pack and registers a root that do not exist; a suite that reads it
    # instead of its own names the missing pack in a warning.
    home = tmp_path / "home"
    (home / ".character-prompt-builder").mkdir(parents=True)
    defaults = json.loads(
        (SCRIPT_DIR.parent / "config" / "default-pack-state.json").read_text(encoding="utf-8")
    )
    (home / ".character-prompt-builder" / "pack-state.json").write_text(json.dumps({
        **defaults,
        "pack_roots": [str(tmp_path / "missing-pack-root")],
        "enabled_packs": [*defaults["enabled_packs"], MISSING_PACK_ID],
    }), encoding="utf-8")
    env["HOME"] = env["USERPROFILE"] = str(home)
    try:
        result = subprocess.run(
            command,
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUITE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            "{0} timed out after {1}s\n--- stdout ---\n{2}\n--- stderr ---\n{3}".format(
                script, SUITE_TIMEOUT, exc.stdout or "", exc.stderr or ""
            ),
            pytrace=False,
        )
    if result.returncode != 0:
        pytest.fail(
            "{0} exited {1}\n--- stdout ---\n{2}\n--- stderr ---\n{3}".format(
                script, result.returncode, result.stdout, result.stderr
            ),
            pytrace=False,
        )
    assert MISSING_PACK_ID not in result.stdout + result.stderr, (
        f"{script} read the pack state of the person running it; call smoke_fixtures.isolate_home()"
    )

    if script in {"growth_resolution_smoke_test.py", "dispatch_recovery_smoke_test.py", "feature_workflow_smoke_test.py", "structure_neutrality_smoke_test.py"}:
        # These suites feed the release gate as JSON, not only as exit codes.
        report = json.loads(result.stdout)
        assert report.get("ok") is True
        assert isinstance(report.get("errors"), list), "release report errors must be an array"
        assert not report["errors"], "successful release report must contain no errors"
