#!/usr/bin/env python3
"""Build a clean, reproducible Character Prompt Builder release archive.

The packager never zips the working tree. It copies the declared release
inventory into a fresh stage, rebuilds the stage's metadata, and validates the
stage once with `validate.py`, which includes the tested dependency profile.
It writes a deterministic ZIP, extracts it, and compares the extracted tree
with the stage file by file. A short installed smoke then runs a few commands
from the extracted copy. The packager runs no test suite;
`scripts/run_checks.py` runs each suite once. Reports, an optional retained
stage and the checksum are verified before the archive becomes visible as the
final write.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from execution_contract import sha256_file
from package_metadata import (
    DEVELOPMENT_ARTIFACT_SUFFIXES,
    GENERATED_RELEASE_ARTIFACT_NAMES,
    VCS_DIR_NAMES,
    iter_release_files,
    load_package_metadata,
)

ROOT = Path(__file__).resolve().parents[1]


def progress(message: str) -> None:
    print(f"[package] {message}", file=sys.stderr, flush=True)

GENERATED_REPORT_NAMES = set(GENERATED_RELEASE_ARTIFACT_NAMES) - {"MANIFEST.json"}
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
} | set(VCS_DIR_NAMES)
EXCLUDED_SUFFIXES = set(DEVELOPMENT_ARTIFACT_SUFFIXES)
# Local state a Studio, a run or a developer machine leaves behind. A release
# carries none of it, so a tree that holds any of it is refused, not cleaned.
LOCAL_STATE_DIRECTORIES = {("logs", "operations"), ("production", "staging"), ("runtime", "snapshots")}
# A records database and its journal, write-ahead and shared-memory files.
LOCAL_STATE_FILE_PREFIXES = {("production", "records.sqlite3")}
VIRTUAL_ENVIRONMENT_NAMES = {".venv", "venv"}
VIRTUAL_ENVIRONMENT_MARKERS = {"pyvenv.cfg"}
CREDENTIAL_FILE_NAMES = {".env", ".netrc", ".pypirc"}
CREDENTIAL_NAME_PART = "credentials"
# The validation record names what the gates never exercise and what a pass
# does not establish, beside the platform and dependencies it ran with.
RELEASE_NOT_RUN = (
    "No test suite runs here; scripts/run_checks.py runs each suite once per change.",
    "No command sends a request to a real image service; the installed smoke uses the synthetic transport.",
    "No command asks a real service for a lost answer.",
)
RELEASE_LIMITATIONS = (
    "A pass checks contracts, records and bytes, not how good an image looks.",
    "The checks ran on the recorded platform and Python; another platform needs its own run.",
)


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
        encoding="utf-8",
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


def run_report(
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run one command that prints a JSON object, and return that object with its exit status.

    A non-zero exit or output that is not a JSON object sets `ok` to false and
    adds the reason to `errors`. The error output travels in `stderr`.
    """

    process = subprocess.run(
        list(command),
        cwd=str(cwd),
        env={**(os.environ if env is None else env), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    label = " ".join(Path(part).name if index < 2 else part for index, part in enumerate(command))
    problems: list[str] = []
    try:
        parsed = json.loads(process.stdout)
        if not isinstance(parsed, dict):
            raise ValueError("the output is not a JSON object")
        report: dict[str, Any] = parsed
    except ValueError as exc:
        report = {"ok": False}
        problems.append(f"{label} printed no JSON object: {exc}")
    if process.returncode != 0:
        problems.append(f"{label} exited with status {process.returncode}")
    listed = report.get("errors", [])
    if not isinstance(listed, list):
        listed = [f"{label} reported errors that are not an array"]
    if problems:
        report["ok"] = False
    report["errors"] = [*listed, *problems]
    if process.stderr.strip():
        report["stderr"] = process.stderr.strip()
    report["command_returncode"] = process.returncode
    return report


def isolated_environment(tree: Path, runtime_root: Path) -> dict[str, str]:
    """Return an environment whose CPB_HOME holds the tree's default pack state and nothing else.

    Every command the packager starts reads this configuration directory. A
    pack the builder installed for their own work therefore never enters a
    release check.
    """

    home = runtime_root / "home"
    home.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(tree / "config" / "default-pack-state.json", home / "pack-state.json")
    return {
        **os.environ,
        "CPB_HOME": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def stage_report_errors(
    validation: Mapping[str, Any],
    *,
    strict_release_tree: bool,
) -> list[str]:
    """Return what one stage's validation report fails to establish."""

    errors: list[str] = []
    if validation.get("ok") is not True or validation.get("command_returncode") != 0:
        errors.append("validation did not pass")
    listed = validation.get("errors")
    if listed:
        errors.append(f"validation reported errors: {list(listed)[:6]}")
    dependencies = validation.get("dependencies")
    if (
        not isinstance(dependencies, Mapping)
        or dependencies.get("profile") != "tested"
        or dependencies.get("ok") is not True
    ):
        errors.append("validation did not pass the tested dependency profile")
    manifest = validation.get("release_manifest")
    if not isinstance(manifest, Mapping) or manifest.get("strict_release_tree") is not strict_release_tree:
        errors.append("validation did not check the release manifest in the requested tree mode")
    return errors


def stage_counts(validation: Mapping[str, Any]) -> dict[str, int]:
    """Return the counts one stage's validation observed, for the release report."""

    manifest = validation.get("release_manifest")
    dependencies = validation.get("dependencies")
    packs = validation.get("default_packs")
    return {
        "files": int(validation.get("files") or 0),
        "manifest_files": int(manifest.get("manifest_files") or 0) if isinstance(manifest, Mapping) else 0,
        "tested_dependencies": len(dependencies.get("dependencies") or []) if isinstance(dependencies, Mapping) else 0,
        "default_pack_records": sum(
            int(row.get("records") or 0) for row in packs if isinstance(row, Mapping)
        ) if isinstance(packs, list) else 0,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def is_local_state(relative: Path, *, directory: bool) -> bool:
    """Whether one tree path is operation logs, production records or staging, a runtime snapshot, a virtual environment or credentials."""
    pair = tuple(part.lower() for part in relative.parts[-2:])
    name = relative.name.lower()
    if directory:
        return pair in LOCAL_STATE_DIRECTORIES or name in VIRTUAL_ENVIRONMENT_NAMES
    return (
        any(len(pair) == 2 and pair[0] == folder and name.startswith(prefix)
            for folder, prefix in LOCAL_STATE_FILE_PREFIXES)
        or name in VIRTUAL_ENVIRONMENT_MARKERS
        or name in CREDENTIAL_FILE_NAMES
        or name.startswith(".env.")
        or CREDENTIAL_NAME_PART in name
    )


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
        elif is_local_state(path.relative_to(root), directory=path.is_dir()):
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
    runtime_root: Path,
    *,
    strict_release_tree: bool = True,
) -> dict[str, Any]:
    """Validate one clean stage once with `scripts/validate.py` and return its report.

    The report includes the tested dependency profile. The tested pins lie
    inside the Visual ranges, and that check refuses a pin outside them, so a
    pass covers the Visual profile too. Writes `staged-validation.json`. A
    failed validation raises with its error output, so a CI log alone says why
    the stage was refused.
    """

    runtime_root.mkdir(parents=True, exist_ok=False)
    env = isolated_environment(stage_root, runtime_root)
    progress("staged: tree invariants and tested dependencies")
    command = [sys.executable, "scripts/validate.py", "."]
    if strict_release_tree:
        command.append("--strict-release-tree")
    validation = run_report(command, stage_root, env)
    write_json(reports_dir / "staged-validation.json", validation)
    errors = stage_report_errors(validation, strict_release_tree=strict_release_tree)
    if errors:
        stderr = str(validation.get("stderr") or "")[-1500:]
        raise RuntimeError(
            "staged release validation failed: "
            + "; ".join(errors[:12])
            + (f"\nvalidation stderr: ...{stderr}" if stderr else "")
        )
    return validation


def compare_release_trees(
    stage_hashes: Mapping[str, str],
    extracted_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Compare an extracted inventory and its file hashes with the validated stage."""

    missing = sorted(set(stage_hashes) - set(extracted_hashes))
    unexpected = sorted(set(extracted_hashes) - set(stage_hashes))
    changed = sorted(
        path
        for path in set(stage_hashes) & set(extracted_hashes)
        if stage_hashes[path] != extracted_hashes[path]
    )
    match = not (missing or unexpected or changed)
    return {
        "ok": match,
        "errors": [] if match else ["extracted tree differs from stage"],
        "stage_file_count": len(stage_hashes),
        "extracted_file_count": len(extracted_hashes),
        "missing_from_extracted": missing,
        "unexpected_in_extracted": unexpected,
        "content_mismatches": changed,
    }


def _smoke_command(
    name: str,
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
) -> tuple[dict[str, Any], str]:
    """Run one installed-smoke command and return its report row and its standard output."""

    started = time.monotonic()
    process = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=dict(env),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    row: dict[str, Any] = {
        "name": name,
        "command": [str(part) for part in command],
        "returncode": process.returncode,
        "seconds": round(time.monotonic() - started, 2),
    }
    if process.returncode != 0:
        row["output"] = (process.stdout + process.stderr)[-2000:]
    return row, process.stdout


def run_installed_smoke(root: Path, runtime_root: Path) -> dict[str, Any]:
    """Run a few commands from an installed copy; each must exit 0.

    The copy readies a commons-only pack runtime, prints the production
    workflow help and the session entry text, then builds and prepares the
    synthetic generation example. Every command reads CPB_HOME at a scratch
    configuration directory under `runtime_root`. Nothing is sent to an image service.
    """

    runtime_root.mkdir(parents=True, exist_ok=False)
    env = isolated_environment(root, runtime_root)
    python = sys.executable
    commons = json.loads((root / "packs" / "commons" / "pack.json").read_text(encoding="utf-8"))
    runtime = [
        "--state-file", str(runtime_root / "pack-state.json"),
        "--cache-dir", str(runtime_root / "cache"),
        "--managed-root", str(runtime_root / "managed"),
    ]
    commands: list[tuple[str, list[str], Path]] = [
        ("commons-only pack runtime",
         [python, "scripts/pack_cli.py", *runtime, "ready", "--only", str(commons["pack_id"])], root),
        ("production workflow help", [python, "scripts/production_workflow.py", "--help"], root),
        ("session entry", [python, "scripts/session_entry_points.py", *runtime], root),
    ]
    if (root / "examples" / "generation" / "build_example.py").is_file():
        commands.append((
            "synthetic generation example",
            [python, "examples/generation/build_example.py", "--out", str(runtime_root / "generation")],
            root,
        ))
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for name, command, cwd in commands:
        row, stdout = _smoke_command(name, command, cwd, env)
        rows.append(row)
        if name != "synthetic generation example" or row["returncode"] != 0:
            continue
        # The example prints the prepare command for the studio it built.
        try:
            printed = json.loads(stdout)
            prepare = [str(part) for part in printed["prepare_argv"]]
            studio = Path(printed["task"]).parent
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"the generation example printed no prepare command: {exc}")
            continue
        rows.append(_smoke_command("synthetic prepare", prepare, studio, env)[0])
    errors.extend(
        f"{row['name']} exited with status {row['returncode']}"
        for row in rows
        if row["returncode"] != 0
    )
    return {
        "ok": bool(rows) and not errors,
        "errors": errors,
        "seconds": round(time.monotonic() - started, 2),
        "commands": rows,
    }


def extract_archive(archive: Path, destination: Path, top_level: str) -> Path:
    """Extract a release archive into a new directory and return its top-level folder."""

    destination.mkdir()
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(destination)
    return destination / top_level


def check_installed(
    extracted_root: Path,
    stage_hashes: Mapping[str, str],
    reports_dir: Path,
    runtime_root: Path,
) -> dict[str, Any]:
    """Check an extracted copy against the validated stage, then run the installed smoke on it.

    The extracted inventory and every file hash must equal the stage's before
    any command runs. Writes `stage-extracted-tree-check.json` and
    `installed-smoke.json`, and reports whether the smoke left the copy
    unchanged.
    """

    extracted_hashes = tree_file_hashes(extracted_root)
    tree = compare_release_trees(stage_hashes, extracted_hashes)
    write_json(reports_dir / "stage-extracted-tree-check.json", tree)
    if not tree["ok"]:
        raise RuntimeError(
            "the extracted archive differs from the validated stage: "
            f"missing {tree['missing_from_extracted'][:5]}, "
            f"unexpected {tree['unexpected_in_extracted'][:5]}, "
            f"changed {tree['content_mismatches'][:5]}"
        )
    progress("installed smoke on the extracted copy")
    smoke = run_installed_smoke(extracted_root, runtime_root)
    write_json(reports_dir / "installed-smoke.json", smoke)
    if smoke["ok"] is not True:
        failed = [row for row in smoke["commands"] if row["returncode"] != 0]
        raise RuntimeError(
            "the installed smoke failed: "
            + "; ".join(smoke["errors"])
            + "".join(f"\n{row['name']}: ...{row.get('output', '')[-1500:]}" for row in failed)
        )
    return {
        "tree": tree,
        "smoke": smoke,
        "installed_smoke_read_only": tree_file_hashes(extracted_root) == extracted_hashes,
    }


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
    parser = _operation_context.ArgumentParser(description="Build one clean, unified Character Prompt Builder release ZIP.")
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
    generated_artifacts = run_report(
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

            validation = validate_stage(
                stage, candidate_reports_dir, temp_root / "staged-runtime"
            )
            staged_counts = stage_counts(validation)
            forbidden = collect_forbidden(stage)
            if forbidden:
                raise RuntimeError(
                    f"validation wrote forbidden artifacts into stage: {forbidden}"
                )
            stage_hashes = tree_file_hashes(stage)
            staged_validation_read_only = pre_validation_hashes == stage_hashes

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

            progress("compare the extracted archive with the stage")
            extracted_root = extract_archive(
                candidate_archive, temp_root / "extracted", package_name
            )
            installed = check_installed(
                extracted_root,
                stage_hashes,
                candidate_reports_dir,
                temp_root / "installed-runtime",
            )
            read_only_report = {
                "ok": staged_validation_read_only and installed["installed_smoke_read_only"],
                "errors": [],
                "staged_validation_read_only": staged_validation_read_only,
                "installed_smoke_read_only": installed["installed_smoke_read_only"],
            }
            if not staged_validation_read_only:
                read_only_report["errors"].append("staged validation modified the stage")
            if not installed["installed_smoke_read_only"]:
                read_only_report["errors"].append("the installed smoke modified the extracted copy")
            write_json(
                candidate_reports_dir / "validation-read-only-check.json",
                read_only_report,
            )
            if read_only_report["ok"] is not True:
                raise RuntimeError("; ".join(read_only_report["errors"]))

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
            installed_smoke = {
                "ok": True,
                "seconds": installed["smoke"]["seconds"],
                "commands": [row["name"] for row in installed["smoke"]["commands"]],
            }

            archive_check = {
                "ok": True,
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
                "staged_validation": staged_counts,
                "stage_extracted_tree_match": True,
                "installed_smoke": installed_smoke,
                "staged_validation_read_only": True,
                "installed_smoke_read_only": True,
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
                "staged_validation": staged_counts,
                "stage_extracted_tree_match": True,
                "installed_smoke": installed_smoke,
                "staged_validation_read_only": True,
                "installed_smoke_read_only": True,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "tested_requirements_sha256": sha256_file(stage / metadata.tested_requirements_file),
                "transport": "synthetic only",
                "not_run": list(RELEASE_NOT_RUN),
                "limitations": list(RELEASE_LIMITATIONS),
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
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
