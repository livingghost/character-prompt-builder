#!/usr/bin/env python3
"""Build a clean, reproducible Character Prompt Builder release archive.

The working tree may contain generated validation reports. This packager never
zips the working tree directly. It copies an explicit runtime allowlist into a
fresh stage, rebuilds metadata there, runs the complete core release-gate set,
creates a deterministic ZIP, extracts it into a second fresh directory, and
repeats the identical gates. Reports, an optional retained stage, and the
checksum are verified before the archive becomes visible as the final write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from execution_contract import sha256_file
from package_metadata import (
    CORE_RELEASE_REGRESSION_CONTRACT,
    DEVELOPMENT_ARTIFACT_SUFFIXES,
    GENERATED_RELEASE_ARTIFACT_NAMES,
    VCS_DIR_NAMES,
    iter_release_files,
    load_package_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DEFAULT_RELEASE_CASE_IDS = (
    ("required-resource-providers", "resource-providers"),
    ("search-wolf", "search"),
    ("search-muscular", "search"),
    ("search-blue-coat", "search"),
    ("search-close-portrait", "search"),
    ("search-window-light", "search"),
    ("search-cat", "search"),
    ("search-dragon", "search"),
    ("search-androgynous", "search"),
    ("search-quiet-authority", "search"),
    ("inspire-portrait-state", "inspire"),
)
EXPECTED_DEFAULT_RELEASE_CASES = len(EXPECTED_DEFAULT_RELEASE_CASE_IDS)
EXPECTED_TESTED_DEPENDENCIES = {
    "CairoSVG": ("==2.9.0", "cairosvg"),
    "numpy": ("==2.5.2", "numpy"),
    "Pillow": ("==12.3.0", "PIL"),
    "rasterio": ("==1.5.1", "rasterio"),
    "opencv-python-headless": ("==5.0.0.93", "cv2"),
    "scikit-image": ("==0.26.0", "skimage"),
}
EXPECTED_VISUAL_EVIDENCE_CHECKS = 28
EXPECTED_REFERENCE_RUNTIME_CHECK_NAMES = (
    "non-object-validator-inputs-return-structured-errors",
    "empty-record-use-list-is-rejected",
    "record-scoped-plan-validates-against-active-pack",
    "environment-use-activates-structure-and-subject-mask",
    "outfit-use-cannot-control-source-identity",
    "identity-use-keeps-stable-grooming-and-excludes-transient-presentation",
    "pose-camera-use-cannot-control-identity-color-or-lighting",
    "combined-identity-and-outfit-retain-distinct-record-authority",
    "subject-mask-selection-is-reachable",
    "nested-surface-plan-hash-mutation-is-rejected",
    "prompt-package-delivers-exact-svg-bytes-with-relative-paths",
    "prompt-package-includes-complete-contract-and-prompt-files",
    "moved-prompt-package-resolves-relative-artifact-paths",
    "prompt-only-package-preserves-unresolved-lighting-for-review",
    "state-ineligible-reference-cannot-enter-prepared-package",
    "unresolved-lighting-blocks-model-facing-execution",
    "direct-raster-multi-image-is-copied-under-package-without-visual",
    "direct-raster-post-copy-failure-restores-empty-output",
    "direct-raster-post-commit-failure-restores-empty-output",
    "multi-image-uses-two-independent-role-scoped-transports",
    "multi-image-host-forwarding-resolves-only-verified-transports",
    "single-board-keeps-source-transport-and-board-hashes-distinct",
    "single-board-host-forwarding-exposes-only-composite-board",
    "failed-materialization-restores-preexisting-empty-output",
    "zero-reference-package-requires-structured-reason",
    "unexplained-zero-activation-is-rejected",
    "impossible-transport-shape-is-rejected",
    "unnamed-reference-averaging-is-rejected",
    "fabricated-pack-artifact-is-rejected",
    "stale-pack-source-hash-is-rejected",
    "inactive-pack-is-rejected-in-every-transport-mode",
    "unsupported-record-influence-is-rejected-before-artifact-selection",
    "stale-active-record-semantic-scope-is-rejected",
    "legitimate-multi-scope-scene-supports-identity-and-outfit",
    "non-lighting-reference-cannot-authorize-source-lighting-preservation",
    "partial-lighting-evidence-cannot-authorize-full-source-lighting-preservation",
)
EXPECTED_REFERENCE_RUNTIME_CHECKS = len(EXPECTED_REFERENCE_RUNTIME_CHECK_NAMES)
EXPECTED_REFERENCE_RUNTIME_CLI_CONTRACT_CHECKS = 7
EXPECTED_FRESH_SESSION_RUNTIME_CHECK_NAMES = (
    "public-pack-activation-enables-default-and-capable-content",
    "unselected-provider-is-warning-and-direct-request-fails",
    "sparse-recommend-preserves-literal-brief-anchors",
    "sparse-recommend-returns-four-whole-image-directions",
    "one-batch-evaluates-four-ordered-probes",
    "retrieval-selects-records-without-id-inputs",
    "inspect-archetype-is-complete-and-asset-compact",
    "inspect-scene-is-complete-and-asset-compact",
    "full-asset-lookup-runs-for-every-selected-record",
    "agent-facing-asset-summary-omits-complete-resources",
    "identity-authority-excludes-all-scene-conditioned-axes",
    "archetype-transient-defaults-remain-outside-character-lock",
    "pose-camera-plan-selects-exact-complementary-svg-roles",
    "composed-prompt-rebuilds-every-load-bearing-state-axis",
    "prompt-artifacts-materialize-two-byte-identical-svgs",
    "fresh-session-runtime-context-is-fully-measured",
    "four-probe-batch-uses-one-public-catalog-process",
)
EXPECTED_FRESH_SESSION_RUNTIME_CHECKS = len(
    EXPECTED_FRESH_SESSION_RUNTIME_CHECK_NAMES
)
# Every EXPECTED_ count below records how many checks one suite reports today.
# They are not tuning: the correct value is whatever the suite currently runs, and
# it is read off the suite. They exist because a suite that silently stops running
# cases still exits zero, and nothing else would notice. A count that falls behind
# fails the release loudly, which is the only direction it can be wrong in.
EXPECTED_DOCUMENTATION_CONTRACT_TESTS = 37
EXPECTED_RELEASE_FILE_OPERATION_CHECKS = 84
EXPECTED_PACKAGE_SECURITY_CHECKS = 16
EXPECTED_PACK_MANAGEMENT_CHECKS = 117
EXPECTED_CATALOG_HTML_CHECKS = 29
EXPECTED_CATALOG_CLI_RUNTIME_TESTS = 44
EXPECTED_SEARCH_DISCOVERY_TESTS = 18
EXPECTED_EVAL_RUNTIME_CHECK_IDS = (
    "temporary-pack-is-valid-and-locked",
    "complete-explicit-runtime-is-accepted",
    "explicit-runtime-round-trips-to-workers",
    "only-temporary-pack-is-active",
    "search-suite-uses-named-pack-resource",
    "sparse-suite-uses-named-pack-resource",
    "complete-search-suite-succeeds",
    "complete-sparse-suite-succeeds",
    "isolated-worker-uses-complete-explicit-runtime",
    "missing-search-expected-id-fails",
    "missing-sparse-expected-id-fails",
    "evaluation-reports-have-no-skip-path",
    "unselected-named-resource-has-no-root-fallback",
    "every-partial-runtime-is-rejected",
    "catalog-runtime-is-reset",
)
EXPECTED_EVAL_RUNTIME_FIXTURE = {
    "temporary": True,
    "active_pack_count": 1,
    "record_count": 1,
    "named_resource_count": 4,
    "successful_search_cases": 1,
    "successful_sparse_cases": 1,
    "isolated_worker_cases": 1,
}
EXPECTED_PACK_RELEASE_GATE_CHECKS = 53
EXPECTED_GENERATION_PAYLOAD_CHECKS = 180
EXPECTED_MODEL_CONTRACT_CHECKS = 62
EXPECTED_UPSCALE_PACKAGE_CHECKS = 18
EXPECTED_CHARACTER_SHEET_CHECKS = 152
EXPECTED_PACK_RELEASE_IDENTITY_CHECKS = 9
EXPECTED_BUNDLED_PACK_GATE_CHECKS = 8
EXPECTED_GENERATION_MUTATIONS_REJECTED = 27
EXPECTED_STATE_GENERATION_CHECK_NAMES = (
    "default-only runnable state record references resolve against packs/commons",
    "state-aware pilot public build and out-dir preserve existing custom output",
    "artifact schema registry is explicit and populated",
    "unsupported schema keywords report the exact nested property path",
    "schema title and description annotations are not unsupported constraints",
    "supported allOf and local $defs references are reported cleanly and enforced",
    "unknown artifact type cannot select a schema path",
    "stateless lineage uses null graph nodes and a concrete self hash",
    "state-aware lineage template preserves the complete required graph",
    "temporary-state template preserves precondition clear and expiry relationships",
    "runtime lineage rejects an all-zero self hash",
    "stateless lineage rejects non-null state nodes",
    "state-aware lineage rejects zero required node hashes",
    "runtime artifact rejects a stale self hash",
    "an off-type container is reported rather than raised",
    "every off-type top-level field is reported rather than raised",
    "growth template validates its declared structures",
    "identity growth structures retain their authored geometry",
    "pilot grooming variants retain exact appearance-state and approved polish ownership",
    "growth structures require explicit geometry",
    "growth schema rejects undeclared covering fields",
    "growth contracts close value sets only for representation, presence and source confidence",
    "growth contracts validate authored coverings and terminal structures",
    "event supersession is future-filtered for historical snapshots",
    "scene-local state applies only to the exact requested scene and snapshots record it",
    "decay uses only exact authored integer milestones and persists the latest milestone",
    "restartable process interrupts explicitly, never auto-resumes, and restarts a fresh epoch",
    "restartable process rejects restart without an inactive epoch",
    "same-order precedence is deterministic with state events after milestones",
    "an event may guard its own introduction of an entity with not-exists",
    "a precondition on an absent entity fails the event, not the resolve",
    "an absent entity reads as an absent path and evaluating it leaves the world alone",
    "supersedable process cancels future milestones at the first later same-path event",
    "per-change effective_until_order is exclusive and restores prior state",
    "per-change clear_event_id resolves a later matching event",
    "temporal validation rejects fixed lifecycle actions, duplicate IDs, and invalid references",
    "canonical state artifact graph validates",
    "artifact graph rejects individually valid cross-character artifacts",
    "pilot event timing resolves offscreen injury, masked emotion, long process, and atomic prop transfer",
    "visual projection exposes state only when requested and at the resolved story instant",
    "scene prompt regeneration ignores artifact IDs but reacts to visible semantics and scene lineage",
    "environment adaptation remains a human-approval proposal and never mutates source state",
    "missing JSON pointers and type-incompatible comparisons fail closed",
    "state-reference fixture is a valid locked released pack",
    "reference selection binds identity, state hash, current range, and flashback range",
    "pack-backed state selection requires an explicit record-use plan",
    "schema-valid unresolved state selection cannot create prepared transports",
    "state binding rejects untyped state features, duplicates, empties, and reversed ranges",
    "state selection and preparation reject changed supplied source bytes without output",
    "state selection and preparation reject missing supplied source bytes without output",
    "state selection rejects stale and spoofed active-pack provenance",
    "state reference preparation intersects explicit record-use plans with state eligibility and commits portable PNG transports",
    "unsupported state and assumptions survive selection, preparation, and ordering",
    "open-ended superseded bindings are excluded while closed historical bindings remain usable",
    "state-aware wrapper preserves the portable canonical prepared set for zero, one, and multiple references",
    "state-aware package and verifier preserve unsupported state and assumptions end to end",
    "state-aware packaging rejects omitted prepared sets and omitted embedded selections",
    "state-aware packaging rejects a non-object prepared-reference input",
    "generic generation CLI rejects state-aware graph bypass",
    "state-aware CLI preserves a read-only source and prior output after a post-materialization failure",
    "state-aware CLI reports both the primary error and cleanup failure without false success",
    "state-aware CLI preserves and reports the prior package when publication rollback is incomplete",
    "prepared state scope rejects omission, mutation, and invalid influence",
    "prepared references reject reordered selection projections and source substitution",
    "state-aware packaging rejects stale outer and embedded selection hashes",
    "reference selection binds identity, era, appearance, state, and story order to the supplied graph",
    "state-aware wrapper rejects a cross-wired graph before packaging",
    "state-aware wrapper binds the package model to the Production Specification",
    "state-aware wrapper binds the package model to the Asset Render Specification",
    "standalone reference selector uses the core hash contract",
    "state reference selector rejects every partial shared pack runtime without output",
    "the standalone selector reports a bindings file whose rows are not objects",
    "reference bundle validates complete child cameras, links, and one identity hash",
    "reference bundle requires unique render hashes and zero unresolved coverage",
    "reference bundle rejects scalar, missing, extra, unknown, duplicate, and stale coverage matrices",
    "candidate manifest is self-hashed and leaves its source plan and inspection immutable",
    "candidate manifest rejects resigned links, invalid decisions, and scalar evidence arrays",
    "consumer adoption validates the immutable candidate and manifest hash",
    "adoption receipts reject invalid time, range, and unrecognized registry properties",
    "invalid reference plan writes no child artifacts",
)
EXPECTED_STATE_GENERATION_CHECKS = len(EXPECTED_STATE_GENERATION_CHECK_NAMES)


def progress(message: str) -> None:
    print(f"[package] {message}", file=sys.stderr, flush=True)

GENERATED_REPORT_NAMES = set(GENERATED_RELEASE_ARTIFACT_NAMES) - {"MANIFEST.json"}
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
} | set(VCS_DIR_NAMES)
EXCLUDED_SUFFIXES = set(DEVELOPMENT_ARTIFACT_SUFFIXES)


_WRITABLE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
_WRITABLE_DIRECTORY_MODE = (
    stat.S_IRUSR
    | stat.S_IWUSR
    | stat.S_IXUSR
    | stat.S_IRGRP
    | stat.S_IXGRP
    | stat.S_IROTH
    | stat.S_IXOTH
)


def _copy_file_writable(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    follow_symlinks: bool = True,
) -> str:
    """Copy exact bytes without inheriting source permissions."""

    target = Path(destination)
    shutil.copyfile(source, target, follow_symlinks=follow_symlinks)
    target.chmod(_WRITABLE_FILE_MODE)
    return str(target)


def _copy_tree_writable(source: Path, destination: Path) -> None:
    """Copy a tree exactly while making every copied path transaction-writable."""

    shutil.copytree(source, destination, copy_function=_copy_file_writable)
    destination.chmod(_WRITABLE_DIRECTORY_MODE)
    for path in destination.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            path.chmod(_WRITABLE_DIRECTORY_MODE)
        elif path.is_file() and not path.is_symlink():
            path.chmod(_WRITABLE_FILE_MODE)


def copy_runtime_tree(
    source: Path,
    destination: Path,
    include: Sequence[str],
    *,
    excluded_subtrees: Sequence[str] = (),
    exclude_names: Sequence[str] = (),
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for child in iter_release_files(
        source,
        include,
        exclude_names=exclude_names,
        excluded_subtrees=excluded_subtrees,
    ):
        relative = child.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_file_writable(child, target, follow_symlinks=False)


def clean_artifacts(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix(), reverse=True):
        rel = path.relative_to(root)
        if path.is_dir() and path.name in EXCLUDED_DIR_NAMES:
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and (
            path.name in GENERATED_REPORT_NAMES
            or path.suffix.lower() in EXCLUDED_SUFFIXES
            or path.name.endswith("~")
        ):
            path.unlink(missing_ok=True)


def run_command(command: Sequence[str], cwd: Path, *, expect_json: bool = True) -> Any:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(command)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    if not expect_json:
        return proc.stdout
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"command did not return JSON: {' '.join(command)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        ) from exc


def run_json_gate(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    """Run a JSON gate while preserving a machine-readable failure report."""

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    errors: list[str] = []
    try:
        parsed = json.loads(process.stdout)
        if not isinstance(parsed, dict):
            raise ValueError("gate output must be a JSON object")
        report: dict[str, Any] = parsed
    except (json.JSONDecodeError, ValueError) as exc:
        report = {"ok": False}
        errors.append(f"gate returned invalid JSON: {exc}")
    if process.returncode != 0:
        errors.append(f"gate exited with status {process.returncode}")
    if process.stderr.strip():
        report["stderr"] = process.stderr.strip()
    if errors:
        report["ok"] = False
        existing_errors = report.get("errors", [])
        if not isinstance(existing_errors, list):
            existing_errors = ["gate errors field must be an array"]
        report["errors"] = [*existing_errors, *errors]
    else:
        report.setdefault("errors", [])
    report["command_returncode"] = process.returncode
    return report


def run_unittest_gate(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    """Run one unittest-style script and return a strict JSON gate report."""

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    combined = "\n".join(value for value in (process.stdout, process.stderr) if value)
    matches = re.findall(r"\bRan\s+(\d+)\s+tests?\b", combined)
    skipped_matches = re.findall(r"\bskipped=(\d+)\b", combined)
    errors: list[str] = []
    checks = int(matches[-1]) if matches else 0
    skipped = sum(int(value) for value in skipped_matches)
    if process.returncode != 0:
        errors.append(f"unittest gate exited with status {process.returncode}")
    if len(matches) != 1:
        errors.append(
            f"unittest gate must report exactly one executed test count, found {len(matches)}"
        )
    if checks <= 0:
        errors.append("unittest gate ran no tests")
    if skipped:
        errors.append(f"unittest gate skipped {skipped} tests")
    if not re.search(r"(?m)^OK(?:\s|$)", combined):
        errors.append("unittest gate did not report OK")
    return {
        "ok": not errors,
        "checks": checks,
        "tests": checks,
        "skipped": skipped,
        "errors": errors,
        "command_returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }


def run_catalog_stats_gate(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    """Run catalog stats and turn its data response into a strict gate report."""

    raw = run_json_gate(command, cwd)
    raw_errors = raw.get("errors", [])
    errors = (
        [str(value) for value in raw_errors]
        if isinstance(raw_errors, list)
        else ["catalog stats errors field must be an array"]
    )
    total = raw.get("total_records")
    families = raw.get("record_families")
    diagnostics = raw.get("diagnostics")
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        errors.append("catalog stats total_records must be a positive integer")
    if not isinstance(families, Mapping) or not families:
        errors.append("catalog stats record_families must be a non-empty object")
    else:
        values = list(families.values())
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            errors.append("catalog stats record_families counts must be non-negative integers")
        elif isinstance(total, int) and sum(values) != total:
            errors.append("catalog stats record_families do not sum to total_records")
    if not isinstance(diagnostics, list):
        errors.append("catalog stats diagnostics must be an array")
    elif diagnostics:
        errors.append("default catalog stats reported pack diagnostics")
    return {
        "ok": not errors,
        "checks": total if isinstance(total, int) and not isinstance(total, bool) else 0,
        "stats": raw,
        "errors": errors,
        "command_returncode": raw.get("command_returncode"),
    }


def _positive_integer(
    report: Mapping[str, Any],
    field: str,
    label: str,
    errors: list[str],
) -> int:
    value = report.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(f"{label}.{field} must be a positive integer")
        return 0
    return value


def _non_negative_integer(
    report: Mapping[str, Any],
    field: str,
    label: str,
    errors: list[str],
) -> int:
    value = report.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{label}.{field} must be a non-negative integer")
        return -1
    return value


def _require_zero_skips(name: str, report: Mapping[str, Any], errors: list[str]) -> None:
    if "skipped" not in report:
        errors.append(f"{name}.skipped must be explicit")
        return
    value = report.get("skipped")
    if isinstance(value, list):
        if value:
            errors.append(f"{name} skipped {len(value)} checks")
    elif isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{name}.skipped must be zero or an empty array")
    elif value != 0:
        errors.append(f"{name} skipped {value} checks")


def _require_report_ok(name: str, report: Mapping[str, Any], errors: list[str]) -> None:
    if report.get("ok") is not True:
        errors.append(f"{name}.ok must be the boolean true")
    if report.get("command_returncode", 0) != 0:
        errors.append(f"{name} command did not exit with status zero")
    report_errors = report.get("errors", [])
    if not isinstance(report_errors, list):
        errors.append(f"{name}.errors must be an array")
    elif report_errors:
        errors.append(f"{name} reported errors: {report_errors}")


def _require_nested_report_ok(
    parent: str,
    field: str,
    value: object,
    errors: list[str],
) -> Mapping[str, Any]:
    label = f"{parent}.{field}"
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be an object")
        return {}
    if value.get("ok") is not True:
        errors.append(f"{label}.ok must be the boolean true")
    nested_errors = value.get("errors", [])
    if not isinstance(nested_errors, list):
        errors.append(f"{label}.errors must be an array")
    elif nested_errors:
        errors.append(f"{label} reported errors: {nested_errors}")
    return value


def evaluate_core_gate_contract(
    reports: Mapping[str, Mapping[str, Any]],
    *,
    default_pack_ids: Sequence[str],
    expected_contract: Mapping[str, int] | None = None,
    strict_release_tree: bool = True,
) -> dict[str, Any]:
    """Validate every core report and normalize its executed coverage counts."""

    errors: list[str] = []
    for name, report in reports.items():
        _require_report_ok(name, report, errors)
    for name in (
        "default_release",
        "release_file_operations",
        "package_security",
        "catalog_cli_runtime",
        "search_discovery",
        "documentation_contract",
        "fresh_session_runtime",
    ):
        _require_zero_skips(name, reports[name], errors)

    contract: dict[str, int] = {}

    dependencies = reports["dependencies"]
    if dependencies.get("profile") != "tested":
        errors.append("dependencies.profile must be 'tested'")
    if dependencies.get("definition") != "requirements-tested.txt":
        errors.append("dependencies.definition must be requirements-tested.txt")
    dependency_rows = dependencies.get("dependencies")
    if not isinstance(dependency_rows, list) or not dependency_rows:
        errors.append("dependencies.dependencies must be a non-empty array")
        dependency_rows = []
    observed_dependencies: dict[str, tuple[str, str]] = {}
    for index, row in enumerate(dependency_rows):
        if not isinstance(row, Mapping):
            errors.append(f"dependencies.dependencies[{index}] must be an object")
            continue
        expected_row_fields = {
            "distribution",
            "constraint",
            "installed",
            "import_name",
            "import_ok",
            "constraint_ok",
        }
        if set(row) != expected_row_fields:
            errors.append(
                f"dependencies.dependencies[{index}] fields are invalid: {sorted(row)}"
            )
        if row.get("import_ok") is not True or row.get("constraint_ok") is not True:
            errors.append(f"dependencies.dependencies[{index}] is not exact and importable")
        distribution = str(row.get("distribution") or "")
        constraint = str(row.get("constraint") or "")
        import_name = str(row.get("import_name") or "")
        if distribution in observed_dependencies:
            errors.append(f"dependencies contains duplicate distribution {distribution!r}")
        observed_dependencies[distribution] = (constraint, import_name)
        if not isinstance(row.get("installed"), str) or not row.get("installed"):
            errors.append(f"dependencies.dependencies[{index}].installed must be explicit")
    if observed_dependencies != EXPECTED_TESTED_DEPENDENCIES:
        errors.append(
            "tested dependency inventory differs from the release contract: "
            f"expected {EXPECTED_TESTED_DEPENDENCIES}, got {observed_dependencies}"
        )
    contract["tested_dependencies"] = len(dependency_rows)

    visual = reports["visual_evidence"]
    contract["visual_evidence_checks"] = _positive_integer(
        visual, "checks", "visual_evidence", errors
    )
    if contract["visual_evidence_checks"] != EXPECTED_VISUAL_EVIDENCE_CHECKS:
        errors.append(
            "visual-evidence regression inventory differs from the release contract: "
            f"expected {EXPECTED_VISUAL_EVIDENCE_CHECKS}, "
            f"got {contract['visual_evidence_checks']}"
        )
    for field in (
        "three_layer_bundle",
        "single_source_cli",
        "full_file_security_scan",
        "production_cairosvg_render",
        "compact_batch_source_hash_gate",
    ):
        if visual.get(field) is not True:
            errors.append(f"visual_evidence.{field} must be the boolean true")
    if visual.get("source_dimensions") != {"width": 240, "height": 180}:
        errors.append("visual_evidence.source_dimensions differs from the test fixture")

    reference_runtime = reports["reference_runtime"]
    runtime_contract = reference_runtime.get("contract_checks")
    if not isinstance(runtime_contract, Mapping):
        errors.append("reference_runtime.contract_checks must be an object")
        runtime_contract = {}
    elif set(runtime_contract) != {"ok", "passed", "failed", "total"}:
        errors.append(
            "reference_runtime.contract_checks fields are invalid: "
            f"{sorted(runtime_contract)}"
        )
    if runtime_contract.get("ok") is not True:
        errors.append("reference_runtime.contract_checks.ok must be the boolean true")
    runtime_total = _positive_integer(
        runtime_contract, "total", "reference_runtime.contract_checks", errors
    )
    runtime_passed = _non_negative_integer(
        runtime_contract, "passed", "reference_runtime.contract_checks", errors
    )
    runtime_failed = _non_negative_integer(
        runtime_contract, "failed", "reference_runtime.contract_checks", errors
    )
    contract["reference_runtime_checks"] = runtime_total
    if runtime_total != EXPECTED_REFERENCE_RUNTIME_CHECKS:
        errors.append(
            "reference-runtime regression inventory differs from the release contract: "
            f"expected {EXPECTED_REFERENCE_RUNTIME_CHECKS}, got {runtime_total}"
        )
    if runtime_passed != runtime_total:
        errors.append("reference-runtime regression did not pass every case")
    if runtime_failed != 0:
        errors.append("reference-runtime regression reported failed contract checks")
    if reference_runtime.get("complete") is not True:
        errors.append("reference_runtime.complete must be true for a release gate")
    if reference_runtime.get("status") != "passed":
        errors.append("reference_runtime.status must be 'passed' for a release gate")
    environment = reference_runtime.get("environment_prerequisites")
    if not isinstance(environment, Mapping):
        errors.append("reference_runtime.environment_prerequisites must be an object")
    else:
        if environment.get("ok") is not True:
            errors.append("reference_runtime environment prerequisites did not pass")
        profiles = environment.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            errors.append(
                "reference_runtime.environment_prerequisites.profiles must be a non-empty array"
            )
        elif any(
            not isinstance(profile, Mapping) or profile.get("ok") is not True
            for profile in profiles
        ):
            errors.append("reference_runtime contains an unmet environment profile")
    if reference_runtime.get("skipped_checks") != []:
        errors.append("reference_runtime.skipped_checks must be an empty array")
    runtime_errors = reference_runtime.get("errors")
    if runtime_errors != []:
        errors.append("reference_runtime.errors must be an empty array")
    runtime_checks = reference_runtime.get("checks")
    if not isinstance(runtime_checks, list) or len(runtime_checks) != runtime_total:
        errors.append("reference_runtime.checks must contain one row per executed check")
    else:
        observed_names: list[str] = []
        for index, row in enumerate(runtime_checks):
            if not isinstance(row, Mapping):
                errors.append(f"reference_runtime.checks[{index}] must be an object")
                continue
            if set(row) != {"name", "passed", "detail"}:
                errors.append(
                    f"reference_runtime.checks[{index}] fields are invalid: {sorted(row)}"
                )
            if row.get("passed") is not True:
                errors.append(f"reference_runtime.checks[{index}] did not pass")
            name = str(row.get("name") or "")
            if not name:
                errors.append(f"reference_runtime.checks[{index}].name is empty")
            observed_names.append(name)
        if len(observed_names) != len(set(observed_names)):
            errors.append("reference_runtime.check names must be unique")
        if tuple(observed_names) != EXPECTED_REFERENCE_RUNTIME_CHECK_NAMES:
            errors.append(
                "reference_runtime check names or order differ from the release contract"
            )

    reference_cli = reports["reference_runtime_cli_contract"]
    reference_cli_summary = reference_cli.get("summary")
    if not isinstance(reference_cli_summary, Mapping):
        errors.append("reference_runtime_cli_contract.summary must be an object")
        reference_cli_summary = {}
    elif set(reference_cli_summary) != {"passed", "failed", "total"}:
        errors.append(
            "reference_runtime_cli_contract.summary fields are invalid: "
            f"{sorted(reference_cli_summary)}"
        )
    reference_cli_total = _positive_integer(
        reference_cli_summary,
        "total",
        "reference_runtime_cli_contract.summary",
        errors,
    )
    reference_cli_passed = _non_negative_integer(
        reference_cli_summary,
        "passed",
        "reference_runtime_cli_contract.summary",
        errors,
    )
    reference_cli_failed = _non_negative_integer(
        reference_cli_summary,
        "failed",
        "reference_runtime_cli_contract.summary",
        errors,
    )
    contract["reference_runtime_cli_contract_checks"] = reference_cli_total
    if reference_cli_total != EXPECTED_REFERENCE_RUNTIME_CLI_CONTRACT_CHECKS:
        errors.append(
            "reference-runtime CLI contract inventory differs from the release contract: "
            f"expected {EXPECTED_REFERENCE_RUNTIME_CLI_CONTRACT_CHECKS}, "
            f"got {reference_cli_total}"
        )
    if reference_cli_passed != reference_cli_total or reference_cli_failed != 0:
        errors.append("reference-runtime CLI contract did not pass every check")
    reference_cli_checks = reference_cli.get("checks")
    if (
        not isinstance(reference_cli_checks, list)
        or len(reference_cli_checks) != reference_cli_total
    ):
        errors.append(
            "reference_runtime_cli_contract.checks must contain one row per executed check"
        )
    else:
        reference_cli_names: list[str] = []
        for index, row in enumerate(reference_cli_checks):
            if not isinstance(row, Mapping):
                errors.append(
                    f"reference_runtime_cli_contract.checks[{index}] must be an object"
                )
                continue
            if set(row) != {"name", "passed", "detail"}:
                errors.append(
                    "reference_runtime_cli_contract.checks"
                    f"[{index}] fields are invalid: {sorted(row)}"
                )
            if row.get("passed") is not True:
                errors.append(
                    f"reference_runtime_cli_contract.checks[{index}] did not pass"
                )
            name = row.get("name")
            if not isinstance(name, str) or not name:
                errors.append(
                    f"reference_runtime_cli_contract.checks[{index}].name is invalid"
                )
            else:
                reference_cli_names.append(name)
            if not isinstance(row.get("detail"), str):
                errors.append(
                    f"reference_runtime_cli_contract.checks[{index}].detail must be a string"
                )
        if len(reference_cli_names) != len(set(reference_cli_names)):
            errors.append("reference-runtime CLI contract check names must be unique")

    fresh_session = reports["fresh_session_runtime"]
    fresh_total = _positive_integer(
        fresh_session, "total", "fresh_session_runtime", errors
    )
    fresh_passed = _non_negative_integer(
        fresh_session, "passed", "fresh_session_runtime", errors
    )
    fresh_failed = _non_negative_integer(
        fresh_session, "failed", "fresh_session_runtime", errors
    )
    contract["fresh_session_runtime_checks"] = fresh_total
    if fresh_total != EXPECTED_FRESH_SESSION_RUNTIME_CHECKS:
        errors.append(
            "fresh-session runtime inventory differs from the release contract: "
            f"expected {EXPECTED_FRESH_SESSION_RUNTIME_CHECKS}, got {fresh_total}"
        )
    if fresh_passed != fresh_total or fresh_failed != 0:
        errors.append("fresh-session runtime did not pass every check")
    fresh_checks = fresh_session.get("checks")
    if not isinstance(fresh_checks, list) or len(fresh_checks) != fresh_total:
        errors.append(
            "fresh_session_runtime.checks must contain one row per executed check"
        )
    else:
        observed_fresh_names: list[str] = []
        for index, row in enumerate(fresh_checks):
            if not isinstance(row, Mapping):
                errors.append(f"fresh_session_runtime.checks[{index}] must be an object")
                continue
            if set(row) != {"name", "passed", "detail"}:
                errors.append(
                    "fresh_session_runtime.checks"
                    f"[{index}] fields are invalid: {sorted(row)}"
                )
            if row.get("passed") is not True:
                errors.append(f"fresh_session_runtime.checks[{index}] did not pass")
            name = row.get("name")
            if not isinstance(name, str) or not name:
                errors.append(
                    f"fresh_session_runtime.checks[{index}].name is invalid"
                )
            else:
                observed_fresh_names.append(name)
        if tuple(observed_fresh_names) != EXPECTED_FRESH_SESSION_RUNTIME_CHECK_NAMES:
            errors.append(
                "fresh-session runtime check names or order differ from the "
                "release contract"
            )

    validation = reports["validation"]
    if validation.get("package_structural_only") is not True:
        errors.append("validation must run in package-delegated structural mode")
    for field in ("dependencies", "visual_evidence_smoke", "reference_runtime_smoke", "default_release_regression"):
        delegated = validation.get(field)
        if not isinstance(delegated, Mapping) or delegated.get("not_run") is not True:
            errors.append(f"validation.{field} must explicitly delegate to a package gate")
        elif delegated.get("ok") is not None:
            errors.append(f"validation.{field}.ok must be null when delegated")
    contract["release_tree_files"] = _positive_integer(
        validation, "files", "validation", errors
    )
    release_manifest = validation.get("release_manifest")
    release_manifest = _require_nested_report_ok(
        "validation", "release_manifest", release_manifest, errors
    )
    if release_manifest.get("strict_release_tree") is not strict_release_tree:
        errors.append(
            "validation.release_manifest strict-tree mode differs from the package gate"
        )
    contract["release_manifest_files"] = _positive_integer(
        release_manifest, "manifest_files", "validation.release_manifest", errors
    )
    expected_manifest_files = _positive_integer(
        release_manifest, "expected_files", "validation.release_manifest", errors
    )
    if contract["release_manifest_files"] != expected_manifest_files:
        errors.append("release MANIFEST inventory count differs from the declared release inventory")
    if strict_release_tree:
        if contract["release_tree_files"] != expected_manifest_files + 1:
            errors.append(
                "strict release tree count must equal the inventory plus MANIFEST.json"
            )
    elif contract["release_tree_files"] < expected_manifest_files + 1:
        errors.append("release tree is missing files declared by MANIFEST.json")
    _positive_integer(
        release_manifest,
        "total_bytes_excluding_manifest",
        "validation.release_manifest",
        errors,
    )

    state_protocol = validation.get("state_protocol")
    state_protocol = _require_nested_report_ok(
        "validation", "state_protocol", state_protocol, errors
    )
    contract["state_artifact_schemas"] = _positive_integer(
        state_protocol, "artifact_schema_count", "validation.state_protocol", errors
    )
    contract["state_templates"] = _positive_integer(
        state_protocol, "state_template_count", "validation.state_protocol", errors
    )
    binding = validation.get("shot_binding_regression")
    binding = _require_nested_report_ok(
        "validation",
        "shot_binding_regression",
        binding,
        errors,
    )
    contract["shot_binding_checks"] = _positive_integer(
        binding, "checks", "validation.shot_binding_regression", errors
    )
    _require_nested_report_ok(
        "validation",
        "shot_handoff",
        validation.get("shot_handoff"),
        errors,
    )
    _require_nested_report_ok(
        "validation",
        "reference_corpus",
        validation.get("reference_corpus"),
        errors,
    )

    default_packs = validation.get("default_packs")
    if not isinstance(default_packs, list) or not default_packs:
        errors.append("validation.default_packs must be a non-empty array")
        default_packs = []
    observed_pack_ids: list[str] = []
    pack_records = 0
    pack_resources = 0
    for index, row in enumerate(default_packs):
        if not isinstance(row, Mapping):
            errors.append(f"validation.default_packs[{index}] must be an object")
            continue
        if row.get("ok") is not True:
            errors.append(f"validation.default_packs[{index}] is not valid")
        pack_errors = row.get("errors", [])
        if not isinstance(pack_errors, list):
            errors.append(f"validation.default_packs[{index}].errors must be an array")
        elif pack_errors:
            errors.append(
                f"validation.default_packs[{index}] reported errors: {pack_errors}"
            )
        if row.get("warnings") != []:
            errors.append(f"validation.default_packs[{index}].warnings must be empty")
        observed_pack_ids.append(str(row.get("pack_id") or ""))
        pack_records += _positive_integer(
            row, "records", f"validation.default_packs[{index}]", errors
        )
        pack_resources += _positive_integer(
            row, "resources", f"validation.default_packs[{index}]", errors
        )
    if tuple(observed_pack_ids) != tuple(default_pack_ids):
        errors.append(
            "validated default pack IDs differ from the release activation contract: "
            f"expected {list(default_pack_ids)}, got {observed_pack_ids}"
        )
    contract["default_pack_records"] = pack_records
    contract["default_pack_resources"] = pack_resources

    catalog_stats_gate = reports["default_catalog_stats"]
    stats = catalog_stats_gate.get("stats")
    if not isinstance(stats, Mapping):
        errors.append("default_catalog_stats.stats must be an object")
        stats = {}
    catalog_records = _positive_integer(
        stats, "total_records", "default_catalog_stats.stats", errors
    )
    contract["default_catalog_records"] = catalog_records
    active_pack_count = _positive_integer(
        stats, "active_pack_count", "default_catalog_stats.stats", errors
    )
    contract["default_active_packs"] = active_pack_count
    if active_pack_count != len(default_pack_ids):
        errors.append("default catalog active pack count differs from the release contract")
    if catalog_records != pack_records:
        errors.append("default catalog record count differs from validated default pack records")

    quality = reports["default_authoring_quality"]
    quality_records = _positive_integer(
        quality, "records_total", "default_authoring_quality", errors
    )
    contract["default_quality_records"] = quality_records
    tier_counts = quality.get("tier_counts")
    if not isinstance(tier_counts, Mapping) or set(tier_counts) != {
        "curated",
        "vocabulary",
    }:
        errors.append(
            "default_authoring_quality.tier_counts must contain curated and vocabulary"
        )
        tier_counts = {}
    normalized_tiers: list[int] = []
    for key, value in tier_counts.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"default_authoring_quality.tier_counts.{key} is invalid")
        else:
            normalized_tiers.append(value)
    if sum(normalized_tiers) != quality_records:
        errors.append("default authoring tier counts do not sum to records_total")
    curated_records = _non_negative_integer(
        quality, "curated_records", "default_authoring_quality", errors
    )
    if curated_records != tier_counts.get("curated"):
        errors.append("default authoring curated_records differs from tier_counts.curated")
    curated_by_kind = quality.get("curated_by_kind")
    if not isinstance(curated_by_kind, Mapping) or not curated_by_kind:
        errors.append("default_authoring_quality.curated_by_kind must be a non-empty object")
    else:
        curated_kind_counts = list(curated_by_kind.values())
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in curated_kind_counts
        ):
            errors.append(
                "default_authoring_quality.curated_by_kind counts must be positive integers"
            )
        elif sum(curated_kind_counts) != curated_records:
            errors.append(
                "default_authoring_quality.curated_by_kind does not sum to curated_records"
            )
    for field in (
        "near_duplicate_findings",
        "positive_language_findings",
        "positive_text_quality_findings",
        "warnings",
    ):
        if quality.get(field) != []:
            errors.append(f"default_authoring_quality.{field} must be an empty array")
    archetype_counts = quality.get("archetype_counts")
    if not isinstance(archetype_counts, Mapping):
        errors.append("default_authoring_quality.archetype_counts must be an object")
    else:
        archetype_total = _non_negative_integer(
            archetype_counts,
            "total",
            "default_authoring_quality.archetype_counts",
            errors,
        )
        archetype_curated = _non_negative_integer(
            archetype_counts,
            "curated",
            "default_authoring_quality.archetype_counts",
            errors,
        )
        archetype_vocabulary = _non_negative_integer(
            archetype_counts,
            "vocabulary",
            "default_authoring_quality.archetype_counts",
            errors,
        )
        if archetype_curated + archetype_vocabulary != archetype_total:
            errors.append("default authoring archetype tier counts are incomplete")
        by_domain = archetype_counts.get("by_domain")
        if not isinstance(by_domain, Mapping) or set(by_domain) != {
            "human",
            "anthropomorphic-animal",
            "animal",
            "creature",
            "hybrid",
            "robot",
        }:
            errors.append("default authoring archetype domain inventory is incomplete")
        else:
            domain_counts = list(by_domain.values())
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in domain_counts
            ):
                errors.append("default authoring archetype domain counts are invalid")
            elif sum(domain_counts) != archetype_total:
                errors.append("default authoring archetype domain counts are incomplete")
    families = stats.get("record_families") if isinstance(stats, Mapping) else None
    excluded_quality_records = 0
    if isinstance(families, Mapping):
        for kind in ("asset", "model"):
            value = families.get(kind, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(f"default catalog {kind} count is invalid")
            else:
                excluded_quality_records += value
    else:
        errors.append("default catalog record_families is unavailable")
    if quality_records != catalog_records - excluded_quality_records:
        errors.append(
            "default authoring audit did not cover every non-asset, non-model catalog record"
        )

    default_release = reports["default_release"]
    if default_release.get("fixture") != CORE_RELEASE_REGRESSION_CONTRACT:
        errors.append(
            f"default_release.fixture must be {CORE_RELEASE_REGRESSION_CONTRACT}"
        )
    if default_release.get("default_pack_ids") != list(default_pack_ids):
        errors.append("default_release.default_pack_ids differs from the release contract")
    total_cases = _positive_integer(
        default_release, "total_cases", "default_release", errors
    )
    contract["default_release_cases"] = total_cases
    if total_cases != EXPECTED_DEFAULT_RELEASE_CASES:
        errors.append(
            "default release regression case inventory differs from the core contract: "
            f"expected {EXPECTED_DEFAULT_RELEASE_CASES}, got {total_cases}"
        )
    passed = _non_negative_integer(default_release, "passed", "default_release", errors)
    failed = _non_negative_integer(default_release, "failed", "default_release", errors)
    details = default_release.get("details")
    if passed != total_cases or failed != 0:
        errors.append("default release regression did not pass every case")
    if not isinstance(details, list) or len(details) != total_cases:
        errors.append("default release regression detail count differs from total_cases")
    elif any(not isinstance(row, Mapping) or row.get("ok") is not True for row in details):
        errors.append("default release regression contains a non-passing case detail")
    else:
        observed_cases = tuple(
            (str(row.get("id") or ""), str(row.get("operation") or ""))
            for row in details
        )
        if observed_cases != EXPECTED_DEFAULT_RELEASE_CASE_IDS:
            errors.append("default release case IDs or operations differ from the core contract")
        for index, row in enumerate(details):
            case_errors = row.get("errors", [])
            if not isinstance(case_errors, list):
                errors.append(f"default_release.details[{index}].errors must be an array")
            elif case_errors:
                errors.append(
                    f"default_release.details[{index}] reported errors: {case_errors}"
                )

    for name in (
        "release_file_operations",
        "pack_management",
        "catalog_html",
        "package_security",
        "catalog_cli_runtime",
        "search_discovery",
        "documentation_contract",
        "generation_payload",
        "model_contract",
        "upscale_package",
        "character_sheet",
        "pack_release_identity",
        "bundled_pack_gate",
        "eval_runtime_mechanism",
        "pack_release_gate_mechanism",
    ):
        contract[f"{name}_checks"] = _positive_integer(
            reports[name], "checks", name, errors
        )
    if (
        contract["release_file_operations_checks"]
        != EXPECTED_RELEASE_FILE_OPERATION_CHECKS
    ):
        errors.append(
            "release file-operation check inventory differs from the release contract: "
            f"expected {EXPECTED_RELEASE_FILE_OPERATION_CHECKS}, "
            f"got {contract['release_file_operations_checks']}"
        )
    if contract["package_security_checks"] != EXPECTED_PACKAGE_SECURITY_CHECKS:
        errors.append(
            "package safety check inventory differs from the release contract: "
            f"expected {EXPECTED_PACKAGE_SECURITY_CHECKS}, "
            f"got {contract['package_security_checks']}"
        )
    if contract["generation_payload_checks"] != EXPECTED_GENERATION_PAYLOAD_CHECKS:
        errors.append(
            "generation payload check inventory differs from the release contract: "
            f"expected {EXPECTED_GENERATION_PAYLOAD_CHECKS}, "
            f"got {contract['generation_payload_checks']}"
        )
    for name, expected in (
        ("pack_management", EXPECTED_PACK_MANAGEMENT_CHECKS),
        ("catalog_html", EXPECTED_CATALOG_HTML_CHECKS),
        ("catalog_cli_runtime", EXPECTED_CATALOG_CLI_RUNTIME_TESTS),
        ("search_discovery", EXPECTED_SEARCH_DISCOVERY_TESTS),
        ("documentation_contract", EXPECTED_DOCUMENTATION_CONTRACT_TESTS),
        ("eval_runtime_mechanism", len(EXPECTED_EVAL_RUNTIME_CHECK_IDS)),
        ("pack_release_gate_mechanism", EXPECTED_PACK_RELEASE_GATE_CHECKS),
        ("model_contract", EXPECTED_MODEL_CONTRACT_CHECKS),
        ("upscale_package", EXPECTED_UPSCALE_PACKAGE_CHECKS),
        ("character_sheet", EXPECTED_CHARACTER_SHEET_CHECKS),
        ("pack_release_identity", EXPECTED_PACK_RELEASE_IDENTITY_CHECKS),
        ("bundled_pack_gate", EXPECTED_BUNDLED_PACK_GATE_CHECKS),
    ):
        observed = contract[f"{name}_checks"]
        if observed != expected:
            errors.append(
                f"{name} check inventory differs from the release contract: "
                f"expected {expected}, got {observed}"
            )

    eval_runtime = reports["eval_runtime_mechanism"]
    if eval_runtime.get("scope") != "self-contained-core-evaluation-mechanism":
        errors.append("eval_runtime_mechanism.scope differs from the core-only boundary")
    if eval_runtime.get("fixture") != EXPECTED_EVAL_RUNTIME_FIXTURE:
        errors.append("eval_runtime_mechanism.fixture differs from the exact temporary inventory")
    if "skipped" in eval_runtime:
        errors.append("eval_runtime_mechanism must not expose a skip path")
    eval_passed = _non_negative_integer(
        eval_runtime, "passed", "eval_runtime_mechanism", errors
    )
    eval_failed = _non_negative_integer(
        eval_runtime, "failed", "eval_runtime_mechanism", errors
    )
    eval_details = eval_runtime.get("details")
    if eval_passed != contract["eval_runtime_mechanism_checks"]:
        errors.append("eval_runtime_mechanism did not pass its complete check inventory")
    if eval_failed != 0:
        errors.append("eval_runtime_mechanism reported failed checks")
    if not isinstance(eval_details, list) or len(eval_details) != len(
        EXPECTED_EVAL_RUNTIME_CHECK_IDS
    ):
        errors.append("eval_runtime_mechanism detail count differs from its inventory")
    elif any(
        not isinstance(row, Mapping)
        or set(row) != {"id", "ok", "observed"}
        or row.get("ok") is not True
        for row in eval_details
    ):
        errors.append("eval_runtime_mechanism contains an invalid or non-passing detail")
    elif tuple(str(row["id"]) for row in eval_details) != EXPECTED_EVAL_RUNTIME_CHECK_IDS:
        errors.append("eval_runtime_mechanism check IDs or order differ from the core contract")

    pack_release_gate = reports["pack_release_gate_mechanism"]
    pack_release_passed = _non_negative_integer(
        pack_release_gate, "passed", "pack_release_gate_mechanism", errors
    )
    pack_release_failed = _non_negative_integer(
        pack_release_gate, "failed", "pack_release_gate_mechanism", errors
    )
    if pack_release_passed != contract["pack_release_gate_mechanism_checks"]:
        errors.append("pack_release_gate_mechanism did not pass its complete check inventory")
    if pack_release_failed != 0:
        errors.append("pack_release_gate_mechanism reported failed checks")
    if pack_release_gate.get("failures") != []:
        errors.append("pack_release_gate_mechanism.failures must be an empty array")

    generation = reports["generation_payload"]
    if generation.get("round_trip_reference_counts") != [0, 1, 2]:
        errors.append("generation payload did not exercise ordered zero, one, and two references")
    if generation.get("supplied_reference_order_preserved") is not True:
        errors.append("generation payload did not preserve supplied-reference order")
    if generation.get("svg_rasterization_exercised") is not True:
        errors.append("generation payload did not exercise SVG rasterization")
    if generation.get("prepared_reference_set_contract_exercised") is not True:
        errors.append("generation payload did not exercise the prepared reference-set contract")
    if generation.get("stateless_reference_origin_is_null") is not True:
        errors.append("generation payload did not enforce the stateless null reference origin")
    for field, message in (
        (
            "runtime_plan_round_trip_exercised",
            "generation payload did not exercise the canonical runtime-plan round trip",
        ),
        (
            "portable_companion_exercised",
            "generation payload did not exercise portable companion carriers",
        ),
        (
            "authority_preamble_forwarded",
            "generation payload did not exercise authority-preamble forwarding",
        ),
        (
            "transactional_publication_exercised",
            "generation payload did not exercise transactional publication",
        ),
        (
            "manual_pack_bypass_rejected",
            "generation payload did not reject manual pack-artifact bypasses",
        ),
        (
            "certified_primary_transport_exercised",
            "generation payload did not exercise certified-primary negative transport",
        ),
    ):
        if generation.get(field) is not True:
            errors.append(message)
    contract["generation_mutations_rejected"] = _positive_integer(
        generation,
        "committed_mutations_rejected",
        "generation_payload",
        errors,
    )
    if (
        contract["generation_mutations_rejected"]
        != EXPECTED_GENERATION_MUTATIONS_REJECTED
    ):
        errors.append(
            "generation mutation rejection inventory differs from the release "
            "contract: expected "
            f"{EXPECTED_GENERATION_MUTATIONS_REJECTED}, got "
            f"{contract['generation_mutations_rejected']}"
        )
    expected_host_fields = ["role", "resolved_path", "media_type", "sha256"]
    if generation.get("host_reference_fields") != expected_host_fields:
        errors.append("generation payload host reference field contract is incomplete")

    state_generation = reports["state_generation"]
    state_total = _positive_integer(
        state_generation, "total", "state_generation", errors
    )
    state_passed = _non_negative_integer(
        state_generation, "passed", "state_generation", errors
    )
    state_checks = state_generation.get("checks")
    if state_total != EXPECTED_STATE_GENERATION_CHECKS:
        errors.append(
            "state generation check inventory differs from the release contract: "
            f"expected {EXPECTED_STATE_GENERATION_CHECKS}, got {state_total}"
        )
    if state_passed != state_total:
        errors.append("state generation did not pass every check")
    if not isinstance(state_checks, list) or len(state_checks) != state_total:
        errors.append("state generation check detail count differs from total")
    elif any(
        not isinstance(row, Mapping)
        or set(row) != {"name", "passed", "detail"}
        or row.get("passed") is not True
        or not isinstance(row.get("name"), str)
        or not row.get("name")
        for row in state_checks
    ):
        errors.append("state generation contains an invalid or non-passing check detail")
    elif (
        tuple(str(row["name"]) for row in state_checks)
        != EXPECTED_STATE_GENERATION_CHECK_NAMES
    ):
        errors.append("state generation check names or order differ from the release contract")
    else:
        state_check_names = {str(row["name"]) for row in state_checks}
        required_reference_selection_checks = {
            "state-aware package and verifier preserve unsupported state and assumptions end to end",
            "state-aware packaging rejects omitted prepared sets and omitted embedded selections",
            "state-aware packaging rejects a non-object prepared-reference input",
            "generic generation CLI rejects state-aware graph bypass",
            "prepared state scope rejects omission, mutation, and invalid influence",
            "prepared references reject reordered selection projections and source substitution",
            "state-aware packaging rejects stale outer and embedded selection hashes",
            "reference selection binds identity, era, appearance, state, and story order to the supplied graph",
        }
        missing_reference_selection_checks = sorted(
            required_reference_selection_checks - state_check_names
        )
        if missing_reference_selection_checks:
            errors.append(
                "state generation omitted required reference-selection contract checks: "
                f"{missing_reference_selection_checks}"
            )
    contract["state_generation_checks"] = state_total

    expected_match = True
    if expected_contract is not None and dict(expected_contract) != contract:
        expected_match = False
        missing = sorted(set(expected_contract) - set(contract))
        unexpected = sorted(set(contract) - set(expected_contract))
        mismatched = {
            key: {"expected": expected_contract[key], "observed": contract[key]}
            for key in sorted(set(expected_contract) & set(contract))
            if expected_contract[key] != contract[key]
        }
        errors.append(
            "extracted gate coverage differs from staged coverage: "
            f"missing={missing}, unexpected={unexpected}, mismatched={mismatched}"
        )

    return {
        "ok": not errors,
        "checks": len(contract),
        "skipped": 0,
        "coverage": contract,
        "expected_contract_match": expected_match,
        "errors": errors,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def collect_forbidden(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            findings.append(path.relative_to(root).as_posix())
        elif path.is_dir() and path.name in EXCLUDED_DIR_NAMES:
            findings.append(path.relative_to(root).as_posix())
        elif path.is_file() and (
            path.name in GENERATED_REPORT_NAMES
            or path.suffix.lower() in EXCLUDED_SUFFIXES
            or path.name.endswith("~")
        ):
            findings.append(path.relative_to(root).as_posix())
    return sorted(findings)


def zip_timestamp() -> tuple[int, int, int, int, int, int]:
    # ZIP cannot represent dates before 1980. A fixed timestamp makes archives
    # reproducible when canonical file content is unchanged.
    return (1980, 1, 1, 0, 0, 0)


def _zip_info(name: str, *, is_directory: bool) -> zipfile.ZipInfo:
    """Return one host-independent ZIP member descriptor.

    Python exposes the source filesystem mode through ``Path.stat()``. Those
    bits differ across operating systems even when the file content is
    identical, so copying them into ``external_attr`` makes the archive hash
    platform-dependent. Release archives use one canonical Unix metadata
    representation instead: directories are 0755 and regular files are 0644.
    """

    info = zipfile.ZipInfo(name, date_time=zip_timestamp())
    info.create_system = 3  # Unix metadata, independent of the build host.
    if is_directory:
        info.external_attr = ((stat.S_IFDIR | 0o755) & 0xFFFF) << 16
        info.external_attr |= 0x10
        info.compress_type = zipfile.ZIP_STORED
    else:
        info.external_attr = ((stat.S_IFREG | 0o644) & 0xFFFF) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
    return info


def write_deterministic_zip(source_root: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = archive_path.with_suffix(archive_path.suffix + ".tmp")
    temp_path.unlink(missing_ok=True)
    prefix = source_root.name
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        directories = {Path(prefix)}
        for path in source_root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"symbolic links are forbidden in staged release trees: {path}")
            rel = Path(prefix) / path.relative_to(source_root)
            if path.is_dir():
                directories.add(rel)
            else:
                directories.update(parent for parent in rel.parents if parent != Path("."))
        for directory in sorted(directories, key=lambda value: (len(value.parts), value.as_posix())):
            info = _zip_info(directory.as_posix().rstrip("/") + "/", is_directory=True)
            zf.writestr(info, b"")
        for path in sorted(
            (p for p in source_root.rglob("*") if p.is_file()),
            key=lambda value: value.relative_to(source_root).as_posix(),
        ):
            rel = Path(prefix) / path.relative_to(source_root)
            info = _zip_info(rel.as_posix(), is_directory=False)
            zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temp_path.replace(archive_path)


def _path_is_within(candidate: Path, parent: Path) -> bool:
    candidate = candidate.resolve()
    parent = parent.resolve()
    return candidate == parent or parent in candidate.parents


def ensure_output_is_not_release_input(
    candidate: Path,
    source: Path,
    include: Sequence[str],
    *,
    label: str,
) -> None:
    """Reject output locations that are themselves copied into the release.

    The manifest intentionally declares ``dist/...`` under the repository
    root. That path is safe because ``dist`` is not in the release allowlist.
    Paths under included entries such as ``scripts/`` are unsafe on repeated
    builds because an earlier archive or report could be copied into the next
    stage.
    """

    if candidate.resolve() == source.resolve():
        raise ValueError(f"{label} must not replace the skill source directory")

    for entry_name in include:
        entry = (source / entry_name).resolve()
        if _path_is_within(candidate, entry):
            raise ValueError(
                f"{label} must not be inside a release input entry: {entry_name}"
            )


def resolve_archive_path(source: Path, release_output: str, out: str | None) -> Path:
    canonical_name = Path(release_output).name
    candidate = Path(out).resolve() if out else (source / release_output).resolve()
    if candidate.name != canonical_name:
        raise ValueError(
            "release archive filename must preserve package identity: "
            f"expected {canonical_name!r}, got {candidate.name!r}"
        )
    return candidate


def validate_keep_stage_destination(
    candidate: Path,
    source: Path,
    include: Sequence[str],
) -> Path:
    """Resolve a new, non-input destination for a retained staged tree.

    A retained stage is a publication output, not a workspace to refresh in
    place. Requiring an absent destination keeps the operation additive and
    prevents a command-line typo from recursively deleting user data.
    """

    requested = Path(candidate)
    destination = requested.resolve()
    ensure_output_is_not_release_input(
        destination,
        source,
        include,
        label="retained stage directory",
    )
    if requested.exists() or requested.is_symlink():
        raise FileExistsError(
            f"retained stage directory must not already exist: {destination}"
        )
    return destination


def validate_stage(
    stage_root: Path,
    reports_dir: Path,
    prefix: str,
    runtime_root: Path,
    *,
    expected_contract: Mapping[str, int] | None = None,
    strict_release_tree: bool = True,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Run the complete production gate set against one clean candidate."""

    python = sys.executable
    metadata = load_package_metadata(stage_root)
    run_json_gate([python, "scripts/release_contract.py"], stage_root)
    run_json_gate([python, "scripts/release_management_smoke_test.py"], stage_root)
    runtime_root.mkdir(parents=True, exist_ok=False)
    state_file = runtime_root / "pack-state.json"
    cache_dir = runtime_root / "cache"
    managed_root = runtime_root / "managed"
    runtime_args = [
        "--state-file",
        str(state_file),
        "--cache-dir",
        str(cache_dir),
        "--managed-root",
        str(managed_root),
    ]
    # Every gate below reads one runtime that enables the default packs alone,
    # whatever other packs sit beside them.
    progress(f"{prefix}: default-pack runtime")
    created = subprocess.run(
        [python, "scripts/pack_cli.py", *runtime_args, "ready",
         *(item for pack_id in metadata.default_pack_ids for item in ("--only", pack_id))],
        cwd=str(stage_root), text=True, capture_output=True, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if created.returncode != 0:
        raise RuntimeError(f"{prefix}: the default-pack runtime is not ready: {created.stdout}{created.stderr}")
    progress(f"{prefix}: exact tested dependency validation")
    dependencies = run_json_gate(
        [python, "scripts/check_dependencies.py", "--tested"], stage_root
    )
    progress(f"{prefix}: production visual-evidence validation")
    visual_evidence = run_json_gate(
        [python, "scripts/visual_evidence_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: visual-reference activation and transport validation")
    reference_runtime = run_json_gate(
        [python, "scripts/reference_runtime_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: reference-runtime CLI contract regression")
    reference_runtime_cli_contract = run_json_gate(
        [python, "scripts/reference_runtime_cli_contract_test.py"], stage_root
    )
    progress(f"{prefix}: self-contained fresh-session prompt-artifact regression")
    fresh_session_runtime = run_json_gate(
        [python, "scripts/fresh_session_runtime_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: strict structural and MANIFEST validation")
    validation_command = [
        python,
        "scripts/validate.py",
        ".",
        "--package-structural-only",
    ]
    if strict_release_tree:
        validation_command.append("--strict-release-tree")
    validation_command.extend(runtime_args)
    validation = run_json_gate(validation_command, stage_root)
    progress(f"{prefix}: default-pack positive retrieval regression")
    default_release = run_json_gate(
        [python, "scripts/default_release_smoke_test.py", ".", *runtime_args],
        stage_root,
    )
    progress(f"{prefix}: default-pack runtime catalog inventory")
    default_catalog_stats = run_catalog_stats_gate(
        [python, "scripts/catalog_cli.py", *runtime_args, "stats"], stage_root
    )
    progress(f"{prefix}: default-pack authoring conformance")
    default_authoring_quality = run_json_gate(
        [python, "scripts/audit_preset_quality.py", ".", *runtime_args], stage_root
    )
    progress(f"{prefix}: release file-operation regression")
    release_file_operations = run_json_gate(
        [python, "scripts/release_file_operations_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: pack lifecycle regression")
    pack_management = run_json_gate(
        [python, "scripts/pack_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: independent one-pack release-gate mechanism regression")
    pack_release_gate_mechanism = run_json_gate(
        [python, "scripts/pack_release_gate_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: catalog HTML regression")
    catalog_html = run_json_gate(
        [python, "scripts/catalog_html_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: package file-safety regression")
    package_security = run_json_gate(
        [python, "scripts/package_security_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: catalog CLI runtime regression")
    catalog_cli_runtime = run_unittest_gate(
        [python, "scripts/catalog_cli_runtime_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: search discovery regression")
    search_discovery = run_unittest_gate(
        [python, "scripts/search_discovery_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: routed documentation contract regression")
    documentation_contract = run_unittest_gate(
        [python, "scripts/documentation_contract_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: self-contained evaluation-runtime mechanism regression")
    eval_runtime_mechanism = run_json_gate(
        [python, "scripts/eval_runtime_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: generation payload regression")
    generation_payload = run_json_gate(
        [python, "scripts/generation_payload_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: model capability and prompt recommendation contract")
    model_contract = run_json_gate(
        [python, "scripts/model_contract_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: committed Upscale Package regression")
    upscale_package = run_json_gate(
        [python, "scripts/upscale_package_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: Character Sheet readiness and safe-sidecar regression")
    character_sheet = run_json_gate(
        [python, "scripts/character_sheet_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: immutable Pack release identity regression")
    pack_release_identity = run_json_gate(
        [python, "scripts/pack_release_identity_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: bundled Pack gate enforcement regression")
    bundled_pack_gate = run_json_gate(
        [python, "scripts/bundled_pack_gate_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: state generation regression")
    state_generation = run_json_gate(
        [python, "scripts/state_generation_smoke_test.py"], stage_root
    )
    progress(f"{prefix}: resolved growth authority and dispatch recovery")
    structure_neutrality = run_json_gate([python, "scripts/structure_neutrality_smoke_test.py"], stage_root)
    growth_resolution = run_json_gate([python, "scripts/growth_resolution_smoke_test.py"], stage_root)
    dispatch_recovery = run_json_gate([python, "scripts/dispatch_recovery_smoke_test.py"], stage_root)
    feature_workflow = run_json_gate([python, "scripts/feature_workflow_smoke_test.py"], stage_root)
    reports: dict[str, Any] = {
        "evidence_review": run_json_gate([python, "scripts/evidence_tools_smoke_test.py"], stage_root),
        "reference_delivery": run_json_gate([python, "scripts/reference_delivery_smoke_test.py"], stage_root),
        "feature_workflow": feature_workflow,
        "growth_resolution": growth_resolution,
        "structure_neutrality": structure_neutrality,
        "dispatch_recovery": dispatch_recovery,
        "dependencies": dependencies,
        "visual_evidence": visual_evidence,
        "reference_runtime": reference_runtime,
        "reference_runtime_cli_contract": reference_runtime_cli_contract,
        "fresh_session_runtime": fresh_session_runtime,
        "validation": validation,
        "default_release": default_release,
        "default_catalog_stats": default_catalog_stats,
        "default_authoring_quality": default_authoring_quality,
        "release_file_operations": release_file_operations,
        "pack_management": pack_management,
        "pack_release_gate_mechanism": pack_release_gate_mechanism,
        "catalog_html": catalog_html,
        "package_security": package_security,
        "catalog_cli_runtime": catalog_cli_runtime,
        "search_discovery": search_discovery,
        "documentation_contract": documentation_contract,
        "eval_runtime_mechanism": eval_runtime_mechanism,
        "generation_payload": generation_payload,
        "model_contract": model_contract,
        "upscale_package": upscale_package,
        "character_sheet": character_sheet,
        "pack_release_identity": pack_release_identity,
        "bundled_pack_gate": bundled_pack_gate,
        "state_generation": state_generation,
    }
    gate_contract = evaluate_core_gate_contract(
        reports,
        default_pack_ids=metadata.default_pack_ids,
        expected_contract=expected_contract,
        strict_release_tree=strict_release_tree,
    )
    reports["gate_contract"] = gate_contract
    for name, report in reports.items():
        write_json(reports_dir / f"{prefix}-{name.replace('_', '-')}.json", report)
    if gate_contract.get("ok") is not True:
        # The error output of each failed gate travels with the failure, so a CI
        # log alone says why a gate stopped.
        stderr = [
            f"{name} stderr: ...{str(report['stderr'])[-1500:]}"
            for name, report in reports.items()
            if isinstance(report, dict) and report.get("ok") is not True and report.get("stderr")
        ]
        raise RuntimeError(
            f"{prefix} core release gate contract failed: "
            + "; ".join(str(value) for value in gate_contract.get("errors", [])[:12])
            + "".join("\n" + line for line in stderr)
        )
    return reports, dict(gate_contract["coverage"])


def tree_file_hashes(root: Path) -> dict[str, str]:
    links = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_symlink()]
    if links:
        raise ValueError(f"symbolic links are forbidden in release trees: {links}")
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    }


def archive_members(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def verify_archive_reproducibility(stage: Path, archive: Path, work: Path) -> dict[str, Any]:
    """Prove the candidate archive is intact and that rebuilding it is byte-identical.

    The core archive is built for reproducibility - a fixed 1980 timestamp,
    canonical 0644/0755 modes, `info.create_system = 3`, and a compression
    independent content digest - but nothing in the core publication path ever
    built it a second time and compared, nor asked the archive to verify its own
    member CRCs. A claim no gate checks is a claim that can quietly stop being
    true, so both checks run before anything is published.
    """

    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        failed_member = zf.testzip()
    repeat = work / "repeat.zip"
    write_deterministic_zip(stage, repeat)
    return {
        "zip_crc_ok": failed_member is None,
        "deterministic_rebuild": archive.read_bytes() == repeat.read_bytes(),
        "failed_member": failed_member,
    }


def archive_content_sha256(path: Path) -> str:
    """Digest member names and their decompressed bytes.

    The raw archive digest also covers the deflate stream, which differs
    between zlib builds: CPython 3.14 links zlib-ng while 3.12 links stock
    zlib, so the same content yields a different `.sha256` on each. This digest
    ignores compression entirely, so it stays comparable across interpreters as
    well as across operating systems.
    """
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            digest.update(name.encode("utf-8"))
            if not name.endswith("/"):
                digest.update(hashlib.sha256(zf.read(name)).digest())
    return digest.hexdigest()


def _path_exists(path: Path) -> bool:
    """Return true for ordinary paths and dangling symbolic links."""

    return path.exists() or path.is_symlink()


def _validate_publication_targets(
    archive: Path,
    sha_path: Path,
    reports_dir: Path,
    keep_stage: Path | None,
) -> None:
    """Require a fresh, non-overlapping destination set for one attempt.

    A failed build must not leave a current-looking archive beside reports from
    a different invocation. Requiring absent destinations also means rollback
    may remove only paths that the current invocation created; it never has to
    replace, merge, or delete an earlier release.
    """

    targets = [archive, sha_path, reports_dir]
    if keep_stage is not None:
        targets.append(keep_stage)
    resolved = [path.resolve() for path in targets]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError(
                    "publication destinations must be distinct and non-overlapping: "
                    f"{left} and {right}"
                )
    occupied = [str(path) for path in targets if _path_exists(path)]
    if occupied:
        raise FileExistsError(
            "publication destinations must not already exist: " + ", ".join(occupied)
        )


def _remove_owned_output(path: Path) -> None:
    """Remove one exact output known to have been absent before this attempt."""

    if not _path_exists(path):
        return
    if path.is_dir() and not path.is_symlink():
        path.chmod(_WRITABLE_DIRECTORY_MODE)
        for current, directory_names, file_names in os.walk(
            path, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            current_path.chmod(_WRITABLE_DIRECTORY_MODE)
            for name in directory_names:
                child = current_path / name
                if not child.is_symlink():
                    child.chmod(_WRITABLE_DIRECTORY_MODE)
            for name in file_names:
                child = current_path / name
                if not child.is_symlink():
                    child.chmod(_WRITABLE_FILE_MODE)
        shutil.rmtree(path)
    else:
        if not path.is_symlink():
            path.chmod(_WRITABLE_FILE_MODE)
        path.unlink()


def _cleanup_attempt_directory(root: Path, parent: Path, prefix: str) -> None:
    """Best-effort cleanup restricted to the directory created by mkdtemp."""

    try:
        resolved_root = root.resolve()
        resolved_parent = parent.resolve()
        if resolved_root.parent != resolved_parent or not resolved_root.name.startswith(prefix):
            return
        _remove_owned_output(resolved_root)
    except OSError:
        # The release is already either unpublished or fully published. A
        # temporary-directory cleanup failure must not create a false build
        # failure after the archive has become visible.
        return


def publish_validated_outputs(
    *,
    candidate_archive: Path,
    candidate_sha_path: Path,
    candidate_reports_dir: Path,
    archive: Path,
    sha_path: Path,
    reports_dir: Path,
    candidate_keep_stage: Path | None = None,
    keep_stage: Path | None = None,
) -> None:
    """Publish one already-validated attempt, with the archive appearing last.

    Reports (including the summary and success marker), an optional retained
    stage, and the checksum are copied and verified before the candidate ZIP is
    atomically moved into place. Any earlier failure removes every output made
    by this invocation, so no newly published archive can survive a failed
    pre-publication step.
    """

    _validate_publication_targets(archive, sha_path, reports_dir, keep_stage)
    if not candidate_archive.is_file():
        raise FileNotFoundError(f"candidate archive is missing: {candidate_archive}")
    if not candidate_sha_path.is_file():
        raise FileNotFoundError(f"candidate checksum is missing: {candidate_sha_path}")
    if not candidate_reports_dir.is_dir():
        raise FileNotFoundError(
            f"candidate reports directory is missing: {candidate_reports_dir}"
        )
    if (candidate_keep_stage is None) != (keep_stage is None):
        raise ValueError("candidate and destination retained-stage paths must be paired")
    if candidate_keep_stage is not None and not candidate_keep_stage.is_dir():
        raise FileNotFoundError(
            f"candidate retained stage is missing: {candidate_keep_stage}"
        )

    for parent in {archive.parent, sha_path.parent, reports_dir.parent}:
        parent.mkdir(parents=True, exist_ok=True)
    if keep_stage is not None:
        keep_stage.parent.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    try:
        created.append(reports_dir)
        shutil.copytree(candidate_reports_dir, reports_dir)
        if tree_file_hashes(candidate_reports_dir) != tree_file_hashes(reports_dir):
            raise RuntimeError("published reports differ from the validated candidate reports")

        if candidate_keep_stage is not None and keep_stage is not None:
            created.append(keep_stage)
            _copy_tree_writable(candidate_keep_stage, keep_stage)
            if tree_file_hashes(candidate_keep_stage) != tree_file_hashes(keep_stage):
                raise RuntimeError("retained stage differs from the validated candidate stage")

        created.append(sha_path)
        _copy_file_writable(candidate_sha_path, sha_path)
        if sha256_file(candidate_sha_path) != sha256_file(sha_path):
            raise RuntimeError("published checksum file differs from the candidate checksum")

        # This is the publication commit point. There are no fallible release
        # writes after it; candidate_archive shares archive.parent's volume.
        created.append(archive)
        candidate_archive.replace(archive)
    except BaseException as original_error:
        rollback_errors: list[str] = []
        for path in reversed(created):
            try:
                _remove_owned_output(path)
            except OSError as exc:
                rollback_errors.append(f"{path}: {exc}")
        if rollback_errors:
            raise RuntimeError(
                "publication failed with "
                f"{type(original_error).__name__}: {original_error}; "
                "rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from original_error
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build one clean, unified Character Prompt Builder release ZIP.")
    parser.add_argument("--source", default=str(ROOT), help="Skill source directory")
    parser.add_argument(
        "--out",
        help=(
            "Output ZIP path. A different directory is allowed, but the filename "
            "must match the canonical release.output filename from "
            "package-manifest.toml. Default: release.output resolved relative to "
            "--source."
        ),
    )
    parser.add_argument("--reports-dir", help="Directory for validation and evaluation reports")
    parser.add_argument(
        "--keep-stage",
        help=(
            "Optional new directory in which to retain the clean staged tree; "
            "the destination must not already exist"
        ),
    )
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    metadata = load_package_metadata(source)
    from release_contract import check as check_release_contract
    identity = check_release_contract(source)
    if not identity["ok"]:
        raise ValueError("invalid product release identity: " + "; ".join(identity["errors"]))
    package_name = metadata.name
    package_version = metadata.version
    release_output = metadata.release_output
    release_variant = "unified"
    archive = resolve_archive_path(source, release_output, args.out)
    reports_dir = (
        Path(args.reports_dir).resolve()
        if args.reports_dir
        else archive.with_suffix("").with_name(archive.stem + "-reports")
    )
    keep_stage = (
        validate_keep_stage_destination(
            Path(args.keep_stage),
            source,
            metadata.release_include,
        )
        if args.keep_stage
        else None
    )
    ensure_output_is_not_release_input(
        archive, source, metadata.release_include, label="output archive"
    )
    ensure_output_is_not_release_input(
        reports_dir, source, metadata.release_include, label="reports directory"
    )
    sha_path = archive.with_suffix(archive.suffix + ".sha256")
    ensure_output_is_not_release_input(
        sha_path, source, metadata.release_include, label="checksum file"
    )
    _validate_publication_targets(archive, sha_path, reports_dir, keep_stage)
    # The generated artifacts are release members, and a stale one describes a
    # tree that is not there. This regenerates without writing and compares, so
    # the answer is the same one CI reaches by regenerating and diffing.
    progress("source: generated artifacts match the tree")
    generated_artifacts = run_json_gate(
        [sys.executable, "scripts/rebuild_metadata.py", "--check"], source
    )
    if not generated_artifacts.get("ok"):
        raise RuntimeError(
            "generated artifacts are stale; run scripts/rebuild_metadata.py: "
            + ", ".join(generated_artifacts.get("stale", []))
        )
    archive.parent.mkdir(parents=True, exist_ok=True)
    attempt_prefix = f".{archive.stem}-candidate-"
    publish_root = Path(
        tempfile.mkdtemp(prefix=attempt_prefix, dir=str(archive.parent))
    )
    attempt_id = publish_root.name
    candidate_archive = publish_root / archive.name
    candidate_sha_path = publish_root / (archive.name + ".sha256")
    candidate_reports_dir = publish_root / "reports"
    candidate_reports_dir.mkdir()
    candidate_keep_stage = (
        publish_root / "retained-stage" if keep_stage is not None else None
    )
    summary: dict[str, Any] | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="cpb-package-") as temp:
            temp_root = Path(temp)
            stage = temp_root / package_name
            progress("copy runtime tree")
            copy_runtime_tree(
                source,
                stage,
                metadata.release_include,
                excluded_subtrees=(),
                exclude_names=metadata.release_exclude_names,
            )
            clean_artifacts(stage)

            # Metadata must describe the exact staged runtime tree, not the
            # working tree.
            progress("rebuild staged metadata")
            run_command([sys.executable, "scripts/rebuild_metadata.py"], stage)
            clean_artifacts(stage)
            forbidden = collect_forbidden(stage)
            if forbidden:
                raise RuntimeError(
                    f"forbidden generated artifacts in stage: {forbidden}"
                )
            pre_validation_hashes = tree_file_hashes(stage)

            progress("validate staged package with the complete core gate set")
            stage_reports, staged_contract = validate_stage(
                stage,
                candidate_reports_dir,
                "staged",
                temp_root / "staged-runtime",
            )
            forbidden = collect_forbidden(stage)
            if forbidden:
                raise RuntimeError(
                    f"validation wrote forbidden artifacts into stage: {forbidden}"
                )
            progress("record validated staged package snapshot")
            stage_hashes = tree_file_hashes(stage)
            staged_validation_read_only = pre_validation_hashes == stage_hashes
            if not staged_validation_read_only:
                raise RuntimeError("staged release gates modified the candidate tree")

            progress("write candidate deterministic zip")
            write_deterministic_zip(stage, candidate_archive)
            digest = sha256_file(candidate_archive)
            content_digest = archive_content_sha256(candidate_archive)
            candidate_sha_path.write_text(
                f"{digest}  {archive.name}\n", encoding="utf-8", newline="\n"
            )

            progress("verify candidate archive CRC and deterministic rebuild")
            reproducibility = verify_archive_reproducibility(
                stage, candidate_archive, temp_root / "archive-reproducibility"
            )
            if not reproducibility["zip_crc_ok"]:
                raise RuntimeError(
                    f"candidate ZIP CRC failed at {reproducibility['failed_member']}"
                )
            if not reproducibility["deterministic_rebuild"]:
                raise RuntimeError("candidate archive rebuild is not byte-identical")

            members = archive_members(candidate_archive)
            forbidden_members = [
                name
                for name in members
                if Path(name).name in GENERATED_REPORT_NAMES
                or "__pycache__" in Path(name).parts
                or Path(name).suffix.lower() in EXCLUDED_SUFFIXES
            ]
            top_levels = sorted(
                {Path(name).parts[0] for name in members if Path(name).parts}
            )
            if forbidden_members:
                raise RuntimeError(
                    f"forbidden files entered archive: {forbidden_members}"
                )
            if top_levels != [package_name]:
                raise RuntimeError(
                    f"archive must have one top-level folder: {top_levels}"
                )

            extract_dir = temp_root / "extracted"
            extract_dir.mkdir()
            with zipfile.ZipFile(candidate_archive) as zf:
                zf.extractall(extract_dir)
            extracted_root = extract_dir / package_name
            extracted_hashes = tree_file_hashes(extracted_root)
            missing_from_extracted = sorted(
                set(stage_hashes) - set(extracted_hashes)
            )
            unexpected_in_extracted = sorted(
                set(extracted_hashes) - set(stage_hashes)
            )
            content_mismatches = sorted(
                path
                for path in set(stage_hashes) & set(extracted_hashes)
                if stage_hashes[path] != extracted_hashes[path]
            )
            tree_match = not (
                missing_from_extracted
                or unexpected_in_extracted
                or content_mismatches
            )
            tree_report = {
                "ok": tree_match,
                "checks": len(stage_hashes),
                "skipped": 0,
                "errors": [] if tree_match else ["extracted tree differs from stage"],
                "stage_file_count": len(stage_hashes),
                "extracted_file_count": len(extracted_hashes),
                "missing_from_extracted": missing_from_extracted,
                "unexpected_in_extracted": unexpected_in_extracted,
                "content_mismatches": content_mismatches,
            }
            write_json(
                candidate_reports_dir / "stage-extracted-tree-check.json",
                tree_report,
            )
            if not tree_match:
                raise RuntimeError(
                    "candidate extraction does not match the staged package"
                )

            progress("validate extracted package with the complete core gate set")
            extracted_reports, extracted_contract = validate_stage(
                extracted_root,
                candidate_reports_dir,
                "extracted",
                temp_root / "extracted-runtime",
                expected_contract=staged_contract,
            )
            if extracted_contract != staged_contract:
                raise RuntimeError(
                    "extracted core gate coverage differs from staged coverage"
                )
            extracted_metadata = load_package_metadata(extracted_root)
            extracted_manifest = json.loads(
                (extracted_root / "MANIFEST.json").read_text(encoding="utf-8")
            )
            # The capability manifest is not asked for a release. It states what
            # this product exchanges, identified by manifest_sha256, and carries
            # no version to agree or disagree with the one here.
            artifact_release_identity = {
                "product_release": extracted_metadata.version,
                "pyproject_project_version": extracted_metadata.pyproject_version,
                "generated_manifest_release": extracted_manifest.get("version"),
                "archive_filename": candidate_archive.name,
                "top_level_folder": top_levels[0],
            }
            expected_artifact_release_identity = {
                "product_release": package_version,
                "pyproject_project_version": metadata.pyproject_version,
                "generated_manifest_release": package_version,
                "archive_filename": metadata.release_artifact_name,
                "top_level_folder": package_name,
            }
            if artifact_release_identity != expected_artifact_release_identity:
                raise RuntimeError(
                    "packaged artifact release identity differs from the product release: "
                    f"expected {expected_artifact_release_identity}, "
                    f"got {artifact_release_identity}"
                )
            extracted_post_validation_hashes = tree_file_hashes(extracted_root)
            extracted_validation_read_only = (
                extracted_post_validation_hashes == extracted_hashes
            )
            read_only_report = {
                "ok": staged_validation_read_only and extracted_validation_read_only,
                "checks": len(stage_hashes) + len(extracted_hashes),
                "skipped": 0,
                "errors": [],
                "staged_validation_read_only": staged_validation_read_only,
                "extracted_validation_read_only": extracted_validation_read_only,
            }
            if not extracted_validation_read_only:
                read_only_report["errors"].append(
                    "extracted release gates modified the candidate tree"
                )
            write_json(
                candidate_reports_dir / "validation-read-only-check.json",
                read_only_report,
            )
            if read_only_report["ok"] is not True:
                raise RuntimeError("release gates modified a candidate tree")

            archive_check = {
                "ok": True,
                "checks": len(staged_contract) * 2 + len(stage_hashes) * 3,
                "skipped": 0,
                "errors": [],
                "package": package_name,
                "version": package_version,
                "version_scheme": metadata.version_scheme,
                "release_timezone": metadata.release_timezone,
                "license": metadata.license_id,
                "archive": str(archive),
                "release_variant": release_variant,
                "attempt_id": attempt_id,
                "sha256": digest,
                "content_sha256": content_digest,
                "zip_crc_ok": reproducibility["zip_crc_ok"],
                "deterministic_rebuild": reproducibility["deterministic_rebuild"],
                "failed_member": reproducibility["failed_member"],
                "member_count": len(members),
                "top_level_folders": top_levels,
                "forbidden_members": forbidden_members,
                "generated_reports_in_archive": False,
                "publication_mode": "fresh-attempt-archive-last",
                "artifact_release_identity": artifact_release_identity,
                "artifact_release_identity_consistent": True,
                "stage_extracted_tree_match": True,
                "staged_validation_read_only": True,
                "extracted_validation_read_only": True,
                "staged_core_gate_contract": staged_contract,
                "extracted_core_gate_contract": extracted_contract,
                "core_gate_contracts_match": True,
                "staged_gate_reports": sorted(stage_reports),
                "extracted_gate_reports": sorted(extracted_reports),
            }
            write_json(candidate_reports_dir / "archive-check.json", archive_check)

            if candidate_keep_stage is not None:
                progress("prepare retained clean stage before publication")
                _copy_tree_writable(stage, candidate_keep_stage)
                if tree_file_hashes(candidate_keep_stage) != stage_hashes:
                    raise RuntimeError(
                        "candidate retained stage differs from the validated stage"
                    )

            summary = {
                "ok": True,
                "package": package_name,
                "version": package_version,
                "version_scheme": metadata.version_scheme,
                "release_timezone": metadata.release_timezone,
                "license": metadata.license_id,
                "archive": str(archive),
                "release_variant": release_variant,
                "attempt_id": attempt_id,
                "sha256": digest,
                "sha256_file": str(sha_path),
                "content_sha256": content_digest,
                "reports_dir": str(reports_dir),
                "retained_stage": str(keep_stage) if keep_stage is not None else None,
                "publication_mode": "fresh-attempt-archive-last",
                "artifact_release_identity": artifact_release_identity,
                "artifact_release_identity_consistent": True,
                "staged_core_gate_contract": staged_contract,
                "extracted_core_gate_contract": extracted_contract,
                "core_gate_contracts_match": True,
                "stage_extracted_tree_match": True,
                "staged_validation_read_only": True,
                "extracted_validation_read_only": True,
            }
            write_json(candidate_reports_dir / "package-summary.json", summary)
            success_marker = {
                "ok": True,
                "attempt_id": attempt_id,
                "archive": str(archive),
                "sha256": digest,
                "content_sha256": content_digest,
                "summary_sha256": sha256_file(
                    candidate_reports_dir / "package-summary.json"
                ),
                "core_gate_contract": staged_contract,
                "core_gate_contracts_match": True,
                "stage_extracted_tree_match": True,
                "staged_validation_read_only": True,
                "extracted_validation_read_only": True,
            }
            write_json(
                candidate_reports_dir / "release-success.json", success_marker
            )

        progress("publish reports, retained stage, checksum, then archive")
        publish_validated_outputs(
            candidate_archive=candidate_archive,
            candidate_sha_path=candidate_sha_path,
            candidate_reports_dir=candidate_reports_dir,
            archive=archive,
            sha_path=sha_path,
            reports_dir=reports_dir,
            candidate_keep_stage=candidate_keep_stage,
            keep_stage=keep_stage,
        )
    except BaseException:
        _cleanup_attempt_directory(publish_root, archive.parent, attempt_prefix)
        raise

    # The archive is now visible and is the final release write. Cleanup and
    # console output are deliberately best effort so they cannot turn a fully
    # published attempt into a reported failure.
    _cleanup_attempt_directory(publish_root, archive.parent, attempt_prefix)
    if summary is not None:
        try:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        except (BrokenPipeError, OSError):
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
