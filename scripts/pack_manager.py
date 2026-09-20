#!/usr/bin/env python3
"""Validate, discover, install, and activate Character Prompt Builder packs."""
from __future__ import annotations

import codecs
import hashlib
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import stat
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from package_metadata import calver_key
from model_contract import recommended_parameter_issues, validate_model_record
from resource_policy import KNOWN_RESOURCE_VALIDATORS, validate_known_resource
from state_protocol import unsupported_schema_keywords, validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas"
PACK_SCHEMA_PATH = SCHEMA_ROOT / "pack.schema.json"
PACK_LOCK_SCHEMA_PATH = SCHEMA_ROOT / "pack-lock.schema.json"
PACK_RECORD_SCHEMA_PATH = SCHEMA_ROOT / "pack-record-file.schema.json"
PACK_STATE_SCHEMA_PATH = SCHEMA_ROOT / "pack-state.schema.json"
VISUAL_EVIDENCE_BUNDLE_SCHEMA_PATH = SCHEMA_ROOT / "visual-evidence-bundle.schema.json"
DEFAULT_PACK_STATE_PATH = ROOT / "config" / "default-pack-state.json"
PACK_INITIALIZATION_PATH = ROOT / "config" / "pack-initialization.json"

PACK_ID_RE = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-7[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$"
)
RESOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class PackError(RuntimeError):
    """Raised when a pack operation cannot be completed safely."""


@dataclass(frozen=True)
class PackIssue:
    severity: str
    code: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path:
            output["path"] = self.path
        return output


@dataclass(frozen=True)
class PackRecord:
    kind: str
    category: str | None
    record: dict[str, Any]
    source_file: str


@dataclass
class PackValidation:
    root: Path
    manifest: dict[str, Any] | None = None
    records: list[PackRecord] = field(default_factory=list)
    resource_files: list[str] = field(default_factory=list)
    resource_bindings: dict[str, str] = field(default_factory=dict)
    issues: list[PackIssue] = field(default_factory=list)
    lock_present: bool = False

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def pack_id(self) -> str | None:
        if not self.manifest:
            return None
        value = self.manifest.get("pack_id")
        return str(value) if value else None

    @property
    def release(self) -> str | None:
        if not self.manifest:
            return None
        value = self.manifest.get("release")
        return str(value) if value else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.valid,
            "root": str(self.root),
            "pack_id": self.pack_id,
            "release": self.release,
            "lock_present": self.lock_present,
            "record_count": len(self.records),
            "resource_file_count": len(self.resource_files),
            "resource_bindings": dict(sorted(self.resource_bindings.items())),
            "errors": [
                issue.to_dict() for issue in self.issues if issue.severity == "error"
            ],
            "warnings": [
                issue.to_dict() for issue in self.issues if issue.severity == "warning"
            ],
        }


@dataclass(frozen=True)
class DiscoveredPack:
    root: Path
    manifest: dict[str, Any]

    @property
    def pack_id(self) -> str:
        return str(self.manifest["pack_id"])

    @property
    def release(self) -> str:
        return str(self.manifest["release"])


@dataclass(frozen=True)
class PackSettings:
    roots: tuple[Path, ...]
    state_file: Path
    cache_dir: Path
    managed_root: Path
    quarantine_root: Path
    default_enabled_packs: tuple[str, ...] = ()
    default_resource_providers: tuple[tuple[str, str], ...] = ()
    # Two different jobs. ``default_enabled_packs`` seeds a runtime that has no
    # state file yet; ``protected_pack_ids`` stands as a floor under explicit
    # user state and refuses to let those packs be disabled. Only the runtime
    # that uses the user's own state file carries the floor.
    protected_pack_ids: tuple[str, ...] = ()
    initialize_all_discovered: bool = False


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PackError(f"Invalid JSON in {path}: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate_uuid7() -> str:
    """Generate a lowercase RFC 9562 UUIDv7 without requiring Python 3.14."""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0x2 << 62)
        | random_b
    )
    generated = str(uuid.UUID(int=value))
    if not PACK_ID_RE.fullmatch(generated):
        raise RuntimeError("Generated UUID does not satisfy the UUIDv7 pack ID contract.")
    return generated


def initial_pack_release() -> str:
    """Initial release for a newly created independent pack, not the host product.

    The pack distribution contract uses calendar ordering and locks each release
    to immutable content. Updating an existing released pack remains explicit.
    """
    return datetime.now(timezone.utc).strftime("%Y.%m.%d") + ".1"


def initialize_pack(
    root: Path,
    *,
    name: str,
    release: str | None = None,
    description: str = "",
    license_id: str = "GPL-3.0-only",
) -> dict[str, Any]:
    """Create one empty development pack with a UUIDv7 identity."""
    root = root.resolve()
    if root.exists():
        if not root.is_dir():
            raise PackError(f"Pack initialization target is not a directory: {root}")
        if any(root.iterdir()):
            raise PackError(f"Pack initialization target is not empty: {root}")
    if not str(name).strip():
        raise PackError("Pack name must not be empty.")
    release = initial_pack_release() if release is None else release
    calver_key(release, field="pack release")
    root.mkdir(parents=True, exist_ok=True)
    (root / "records").mkdir(exist_ok=True)
    manifest: dict[str, Any] = {
        "pack_id": generate_uuid7(),
        "name": str(name).strip(),
        "release": release,
        "content": {
            "record_globs": ["records/**/*.json"],
            "resource_globs": [],
            "resource_bindings": {},
        },
        "capabilities": [],
        "dependencies": [],
        "optional_dependencies": [],
        "replaces": [],
        "license": license_id,
    }
    if description.strip():
        manifest["description"] = description.strip()
    atomic_write_json(root / "pack.json", manifest)
    report = validate_pack(root)
    if not report.valid:
        raise PackError(
            "Initialized pack failed validation: "
            + "; ".join(issue.message for issue in report.issues if issue.severity == "error")
        )
    return manifest


def _load_schema(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise PackError(f"Schema must be a JSON object: {path}")
    unsupported = unsupported_schema_keywords(value)
    if unsupported:
        raise PackError(
            f"Schema contains unsupported validation keywords: {path}: {unsupported}"
        )
    return value


def _schema_issues(value: Any, schema_path: Path, source_path: Path) -> list[PackIssue]:
    schema = _load_schema(schema_path)
    return [
        PackIssue("error", "schema", message, str(source_path))
        for message in validate_against_schema(value, schema)
    ]


def _safe_relative_pattern(pattern: str) -> bool:
    if not pattern or "\\" in pattern or pattern.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", pattern):
        return False
    parts = PurePosixPath(pattern).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _safe_relative_file(value: str) -> bool:
    if not _safe_relative_pattern(value) or any(character in value for character in "*?[]"):
        return False
    return not value.endswith("/")


def _is_link(path: Path) -> bool:
    """Whether ``path`` redirects elsewhere rather than holding its own bytes.

    A Windows directory junction is not a symbolic link, so ``is_symlink`` alone
    lets one carry bytes from outside the pack root under a pack-relative name.
    ``Path.is_junction`` arrived in Python 3.12 and this project supports 3.11,
    so it is consulted only where the running interpreter provides it.
    """

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if is_junction is not None else False


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PackError(f"Pack path escapes its root: {path}") from exc


def _expand_globs(root: Path, patterns: Sequence[str]) -> tuple[list[Path], list[PackIssue]]:
    files: dict[str, Path] = {}
    issues: list[PackIssue] = []
    for pattern in patterns:
        if not _safe_relative_pattern(str(pattern)):
            issues.append(
                PackIssue(
                    "error",
                    "unsafe-glob",
                    f"Content glob must be a safe POSIX-relative pattern: {pattern!r}",
                    "pack.json",
                )
            )
            continue
        matched = False
        for path in root.glob(str(pattern)):
            matched = True
            try:
                relative = _relative_path(root, path)
            except PackError as exc:
                issues.append(PackIssue("error", "path-escape", str(exc), str(path)))
                continue
            if _is_link(path):
                issues.append(
                    PackIssue(
                        "error",
                        "symbolic-link",
                        "Symbolic links and directory junctions are forbidden in packs.",
                        relative,
                    )
                )
            elif path.is_file():
                files[relative] = path
        if not matched:
            issues.append(
                PackIssue(
                    "warning",
                    "empty-glob",
                    f"Content glob matched no files: {pattern}",
                    "pack.json",
                )
            )
    return [files[key] for key in sorted(files)], issues


def _snapshot_issues(root: Path, offering: dict[str, Any]) -> list[str]:
    """What is wrong with the observed parameter schema an offering points at."""

    relative = str(offering.get("schema_snapshot"))
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        return [f"offering on {offering.get('service')!r}: schema_snapshot {relative!r} leaves the pack"]
    if not path.is_file():
        return [f"offering on {offering.get('service')!r}: schema_snapshot {relative!r} is not in the pack"]
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"offering on {offering.get('service')!r}: schema_snapshot {relative!r} did not load: {exc}"]
    issues: list[str] = []
    schema = snapshot.get("schema") if isinstance(snapshot, dict) else None
    if not isinstance(schema, dict):
        return [f"offering on {offering.get('service')!r}: schema_snapshot {relative!r} carries no schema"]
    for name in ("service", "model_identifier", "observed_at"):
        if snapshot.get(name) != offering.get(name):
            issues.append(
                f"offering on {offering.get('service')!r}: schema_snapshot {relative!r} records "
                f"{name} {snapshot.get(name)!r}, the offering {offering.get(name)!r}"
            )
    declared = ((schema.get("properties") or {}).get("model") or {}).get("const")
    if declared is not None and declared != offering.get("model_identifier"):
        issues.append(
            f"offering on {offering.get('service')!r}: the observed schema is for {declared!r}, "
            f"the offering names {offering.get('model_identifier')!r}"
        )
    return issues


def _all_pack_files(root: Path) -> tuple[list[Path], list[PackIssue]]:
    """Inventory every file the pack root itself holds.

    The walk is explicit rather than ``rglob`` so a redirecting entry is
    reported and never descended: walking through one would inventory bytes
    from outside the pack root under pack-relative names, and a junction that
    names an ancestor would not terminate.
    """

    files: list[Path] = []
    issues: list[PackIssue] = []

    def walk(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(root).as_posix()
            if _is_link(path):
                issues.append(
                    PackIssue(
                        "error",
                        "symbolic-link",
                        "Symbolic links and directory junctions are forbidden in packs.",
                        relative,
                    )
                )
            elif path.is_dir():
                walk(path)
            elif path.is_file():
                files.append(path)

    walk(root)
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    return files, issues


def _media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _file_role(relative: str) -> str:
    lower = relative.lower()
    if relative == "pack.json":
        return "manifest"
    if relative.startswith("records/") and lower.endswith(".json"):
        return "record"
    if relative.startswith("resources/"):
        return "resource"
    if relative.startswith("evidence/") or relative == "evidence-index.json":
        return "evidence"
    if lower.startswith("license") or lower.startswith("copying"):
        return "license"
    if lower.endswith(".md") or lower.endswith(".txt"):
        return "documentation"
    return "other"


def inventory_rows(root: Path) -> list[dict[str, Any]]:
    files, issues = _all_pack_files(root)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise PackError(errors[0].message)
    rows: list[dict[str, Any]] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative == "pack.lock.json":
            continue
        rows.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "media_type": _media_type(path),
                "role": _file_role(relative),
            }
        )
    return rows


def build_lock_data(root: Path) -> dict[str, Any]:
    validation = validate_pack(root, require_lock=False, verify_lock=False)
    if not validation.valid or not validation.manifest:
        raise PackError(
            "Cannot build a lock for an invalid pack: "
            + "; ".join(issue.message for issue in validation.issues if issue.severity == "error")
        )
    if not validation.records and not validation.resource_files:
        raise PackError(
            "Cannot build a released pack lock without at least one matched record or resource."
        )
    rows = inventory_rows(validation.root)
    return {
        "pack_id": validation.pack_id,
        "release": validation.release,
        "files": rows,
        "content_sha256": sha256_bytes(canonical_json(rows).encode("utf-8")),
    }


def is_project_pack(root: Path, manifest: Mapping[str, Any] | None = None) -> bool:
    """Only this checkout's commons is maintained by the core manifest.

    A third-party pack cannot opt out of locking by copying a UUID or setting
    an untrusted manifest flag. Symlinked pack roots are never exempt.
    """
    root = Path(root)
    expected = ROOT / "packs" / "commons"
    if root.is_symlink() or expected.is_symlink() or root.resolve() != expected.resolve():
        return False
    data = manifest if manifest is not None else load_json(root / "pack.json")
    return data.get("pack_id") == "01a0043b-2250-720d-87b7-f1e6fd7ed230"


def write_lock(root: Path) -> dict[str, Any]:
    """Write the canonical lock for ``root``.

    This low-level helper intentionally permits fixture and maintenance callers
    to rewrite a development pack. The public ``pack_cli.py build-lock`` command
    enforces released UUID/CalVer immutability before calling this function.
    """

    root = root.resolve()
    if is_project_pack(root):
        raise PackError("Bundled commons is core-managed and must not have pack.lock.json")
    data = build_lock_data(root)
    atomic_write_json(root / "pack.lock.json", data)
    return data


def _validate_lock(root: Path, manifest: Mapping[str, Any]) -> list[PackIssue]:
    lock_path = root / "pack.lock.json"
    issues: list[PackIssue] = []
    try:
        lock = load_json(lock_path)
    except PackError as exc:
        return [PackIssue("error", "invalid-lock-json", str(exc), "pack.lock.json")]
    issues.extend(_schema_issues(lock, PACK_LOCK_SCHEMA_PATH, lock_path))
    if not isinstance(lock, Mapping):
        return issues
    if lock.get("pack_id") != manifest.get("pack_id"):
        issues.append(
            PackIssue(
                "error",
                "lock-pack-id",
                "pack.lock.json pack_id does not match pack.json.",
                "pack.lock.json",
            )
        )
    if lock.get("release") != manifest.get("release"):
        issues.append(
            PackIssue(
                "error",
                "lock-release",
                "pack.lock.json release does not match pack.json.",
                "pack.lock.json",
            )
        )
    try:
        actual_rows = inventory_rows(root)
    except PackError as exc:
        issues.append(PackIssue("error", "lock-inventory", str(exc), "pack.lock.json"))
        return issues
    expected_rows = lock.get("files")
    if isinstance(expected_rows, list):
        declared_paths = [
            str(row.get("path")) for row in expected_rows if isinstance(row, Mapping)
        ]
        seen_declared_paths: set[str] = set()
        duplicate_declared_paths: set[str] = set()
        for declared_path in declared_paths:
            if declared_path in seen_declared_paths:
                duplicate_declared_paths.add(declared_path)
            seen_declared_paths.add(declared_path)
        duplicate_paths = sorted(duplicate_declared_paths)
        if duplicate_paths:
            issues.append(
                PackIssue(
                    "error",
                    "lock-duplicate-path",
                    f"pack.lock.json declares duplicate file paths: {duplicate_paths}",
                    "pack.lock.json",
                )
            )
        expected_by_path = {
            str(row.get("path")): row for row in expected_rows if isinstance(row, Mapping)
        }
        actual_by_path = {row["path"]: row for row in actual_rows}
        missing = sorted(set(expected_by_path) - set(actual_by_path))
        extra = sorted(set(actual_by_path) - set(expected_by_path))
        if missing:
            issues.append(
                PackIssue(
                    "error",
                    "lock-missing-files",
                    f"Files declared by the lock are missing: {missing}",
                    "pack.lock.json",
                )
            )
        if extra:
            issues.append(
                PackIssue(
                    "error",
                    "lock-extra-files",
                    f"Files not declared by the lock are present: {extra}",
                    "pack.lock.json",
                )
            )
        for relative in sorted(set(expected_by_path) & set(actual_by_path)):
            expected = expected_by_path[relative]
            actual = actual_by_path[relative]
            for key in ("bytes", "sha256", "media_type", "role"):
                if expected.get(key) != actual.get(key):
                    issues.append(
                        PackIssue(
                            "error",
                            "lock-file-mismatch",
                            f"Lock field {key!r} does not match the file inventory.",
                            relative,
                        )
                    )
                    break
        actual_content_hash = sha256_bytes(canonical_json(actual_rows).encode("utf-8"))
        if lock.get("content_sha256") != actual_content_hash:
            issues.append(
                PackIssue(
                    "error",
                    "lock-content-hash",
                    "pack.lock.json content_sha256 does not match the canonical inventory.",
                    "pack.lock.json",
                )
            )
    return issues


def _validate_asset_contract(
    root: Path,
    record: Mapping[str, Any],
    *,
    record_id: str,
    source_file: str,
    resource_file_set: set[str],
    lock_rows_by_path: Mapping[str, Mapping[str, Any]] | None,
) -> list[PackIssue]:
    """Cross-check one asset record, its resources, lock rows, and bundle manifest."""
    issues: list[PackIssue] = []
    raw_refs = record.get("resource_refs")
    resource_refs = {
        str(value) for value in raw_refs
    } if isinstance(raw_refs, list) else set()
    raw_artifacts = record.get("artifacts")
    artifacts = (
        [row for row in raw_artifacts if isinstance(row, Mapping)]
        if isinstance(raw_artifacts, list)
        else []
    )

    artifacts_by_id: dict[str, Mapping[str, Any]] = {}
    artifact_paths: set[str] = set()
    for artifact in artifacts:
        artifact_id = str(artifact.get("artifact_id") or "")
        relative = str(artifact.get("path") or "")
        if artifact_id in artifacts_by_id:
            issues.append(
                PackIssue(
                    "error",
                    "asset-duplicate-artifact-id",
                    f"Asset record {record_id!r} repeats artifact_id {artifact_id!r}.",
                    source_file,
                )
            )
        else:
            artifacts_by_id[artifact_id] = artifact
        if relative in artifact_paths:
            issues.append(
                PackIssue(
                    "error",
                    "asset-duplicate-artifact-path",
                    f"Asset record {record_id!r} repeats artifact path {relative!r}.",
                    source_file,
                )
            )
        artifact_paths.add(relative)
        if not _safe_relative_file(relative) or relative not in resource_file_set:
            issues.append(
                PackIssue(
                    "error",
                    "asset-artifact-resource",
                    f"Asset record {record_id!r} artifact {artifact_id!r} refers to an undeclared resource: {relative}",
                    source_file,
                )
            )
            continue
        if relative not in resource_refs:
            issues.append(
                PackIssue(
                    "error",
                    "asset-artifact-ref",
                    f"Asset record {record_id!r} artifact {artifact_id!r} is absent from resource_refs.",
                    source_file,
                )
            )
        expected_media_type = str(artifact.get("media_type") or "")
        expected_sha256 = str(artifact.get("sha256") or "")
        if lock_rows_by_path is not None:
            lock_row = lock_rows_by_path.get(relative)
            if lock_row is None:
                issues.append(
                    PackIssue(
                        "error",
                        "asset-artifact-lock-missing",
                        f"Asset record {record_id!r} artifact path is absent from the lock: {relative}",
                        source_file,
                    )
                )
            elif (
                lock_row.get("media_type") != expected_media_type
                or lock_row.get("sha256") != expected_sha256
            ):
                issues.append(
                    PackIssue(
                        "error",
                        "asset-artifact-lock-mismatch",
                        f"Asset record {record_id!r} artifact media_type or sha256 differs from the lock: {relative}",
                        source_file,
                    )
                )
        else:
            actual_path = root / relative
            if (
                _media_type(actual_path) != expected_media_type
                or sha256_file(actual_path) != expected_sha256
            ):
                issues.append(
                    PackIssue(
                        "error",
                        "asset-artifact-file-mismatch",
                        f"Asset record {record_id!r} artifact media_type or sha256 differs from the file: {relative}",
                        source_file,
                    )
                )

    if record.get("asset_type") != "visual-evidence-bundle":
        return issues

    bundle_refs = sorted(
        relative
        for relative in resource_refs
        if PurePosixPath(relative).name == "visual-evidence-bundle.json"
    )
    if len(bundle_refs) != 1:
        issues.append(
            PackIssue(
                "error",
                "asset-bundle-reference",
                f"Visual-evidence asset {record_id!r} requires exactly one visual-evidence-bundle.json resource_ref.",
                source_file,
            )
        )
        return issues
    bundle_relative = bundle_refs[0]
    bundle_path = root / bundle_relative
    try:
        bundle = load_json(bundle_path)
    except PackError as exc:
        issues.append(PackIssue("error", "asset-bundle-json", str(exc), bundle_relative))
        return issues
    issues.extend(_schema_issues(bundle, VISUAL_EVIDENCE_BUNDLE_SCHEMA_PATH, bundle_path))
    if not isinstance(bundle, Mapping):
        return issues

    duplicated_fields = (
        ("source_ref_id", "source_ref_id"),
        ("source_sha256", "source_sha256"),
        ("source_dimensions", "source_dimensions"),
        ("canonical_record_ids", "canonical_record_refs"),
        ("disposition", "disposition"),
        ("evidence_relation", "evidence_relation"),
    )
    for record_field, bundle_field in duplicated_fields:
        if record.get(record_field) != bundle.get(bundle_field):
            issues.append(
                PackIssue(
                    "error",
                    "asset-bundle-metadata-mismatch",
                    f"Asset record {record_id!r} field {record_field!r} differs from bundle field {bundle_field!r}.",
                    source_file,
                )
            )

    bundle_parent = PurePosixPath(bundle_relative).parent
    bundle_artifacts_by_id: dict[str, dict[str, Any]] = {}
    raw_bundle_artifacts = bundle.get("artifacts")
    if isinstance(raw_bundle_artifacts, list):
        for bundle_artifact in raw_bundle_artifacts:
            if not isinstance(bundle_artifact, Mapping):
                continue
            artifact_id = str(bundle_artifact.get("artifact_id") or "")
            raw_relative = str(bundle_artifact.get("path") or "")
            if artifact_id in bundle_artifacts_by_id:
                issues.append(
                    PackIssue(
                        "error",
                        "asset-bundle-duplicate-artifact-id",
                        f"Visual-evidence bundle repeats artifact_id {artifact_id!r}.",
                        bundle_relative,
                    )
                )
                continue
            if not _safe_relative_file(raw_relative):
                issues.append(
                    PackIssue(
                        "error",
                        "asset-bundle-artifact-path",
                        f"Visual-evidence bundle has an unsafe artifact path: {raw_relative!r}.",
                        bundle_relative,
                    )
                )
                continue
            bundle_artifacts_by_id[artifact_id] = {
                "artifact_id": artifact_id,
                "role": bundle_artifact.get("role"),
                "path": (bundle_parent / PurePosixPath(raw_relative)).as_posix(),
                "media_type": bundle_artifact.get("media_type"),
                "sha256": bundle_artifact.get("sha256"),
            }

    asset_ids = set(artifacts_by_id)
    bundle_ids = set(bundle_artifacts_by_id)
    if asset_ids != bundle_ids:
        issues.append(
            PackIssue(
                "error",
                "asset-bundle-artifact-set",
                f"Asset record {record_id!r} and its bundle declare different artifact IDs; missing={sorted(bundle_ids - asset_ids)}, extra={sorted(asset_ids - bundle_ids)}.",
                source_file,
            )
        )
    for artifact_id in sorted(asset_ids & bundle_ids):
        asset_artifact = artifacts_by_id[artifact_id]
        expected = bundle_artifacts_by_id[artifact_id]
        if any(asset_artifact.get(key) != expected.get(key) for key in (
            "artifact_id", "role", "path", "media_type", "sha256"
        )):
            issues.append(
                PackIssue(
                    "error",
                    "asset-bundle-artifact-mismatch",
                    f"Asset record {record_id!r} artifact {artifact_id!r} differs from its bundle manifest.",
                    source_file,
                )
            )
    return issues


def validate_pack(
    root: Path,
    *,
    require_lock: bool = False,
    verify_lock: bool = True,
) -> PackValidation:
    root = root.resolve()
    report = PackValidation(root=root)
    if not root.is_dir():
        report.issues.append(
            PackIssue("error", "missing-pack-root", "Pack root is not a directory.", str(root))
        )
        return report

    files, tree_issues = _all_pack_files(root)
    report.issues.extend(tree_issues)
    for path in files:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        found: set[str] = set()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    decoded = decoder.decode(chunk)
                    if "\u2014" in decoded:
                        found.add("\u2014")
                    if "\u2013" in decoded:
                        found.add("\u2013")
                decoded = decoder.decode(b"", final=True)
                if "\u2014" in decoded:
                    found.add("\u2014")
                if "\u2013" in decoded:
                    found.add("\u2013")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(root).as_posix()
        for character, name, codepoint in (
            ("\u2014", "em dash", "U+2014"),
            ("\u2013", "en dash", "U+2013"),
        ):
            if character in found:
                report.issues.append(
                    PackIssue(
                        "error",
                        "forbidden-punctuation",
                        f"Unicode {name} ({codepoint}) is forbidden in pack UTF-8 content.",
                        relative,
                    )
                )
    manifest_path = root / "pack.json"
    if manifest_path not in files and not manifest_path.is_file():
        report.issues.append(
            PackIssue("error", "missing-manifest", "Pack root must contain pack.json.", "pack.json")
        )
        return report
    try:
        manifest = load_json(manifest_path)
    except PackError as exc:
        report.issues.append(PackIssue("error", "invalid-manifest-json", str(exc), "pack.json"))
        return report
    if not isinstance(manifest, dict):
        report.issues.append(
            PackIssue("error", "manifest-type", "pack.json must contain an object.", "pack.json")
        )
        return report
    report.manifest = manifest
    report.issues.extend(_schema_issues(manifest, PACK_SCHEMA_PATH, manifest_path))

    try:
        calver_key(manifest.get("release"), field="pack release")
    except ValueError as exc:
        report.issues.append(PackIssue("error", "calver", str(exc), "pack.json"))

    pack_id = str(manifest.get("pack_id") or "")
    dependencies = manifest.get("dependencies") or []
    optional_dependencies = manifest.get("optional_dependencies") or []
    dependency_ids = [
        str(row.get("pack_id") or "")
        for row in list(dependencies) + list(optional_dependencies)
        if isinstance(row, Mapping)
    ]
    if pack_id and pack_id in dependency_ids:
        report.issues.append(
            PackIssue("error", "self-dependency", "A pack cannot depend on itself.", "pack.json")
        )
    if len(dependency_ids) != len(set(dependency_ids)):
        report.issues.append(
            PackIssue(
                "error",
                "duplicate-dependency",
                "Dependency pack IDs must be unique across required and optional dependencies.",
                "pack.json",
            )
        )

    content = manifest.get("content") if isinstance(manifest.get("content"), Mapping) else {}
    record_patterns = [str(value) for value in content.get("record_globs") or []]
    resource_patterns = [str(value) for value in content.get("resource_globs") or []]
    if not record_patterns and not resource_patterns:
        report.issues.append(
            PackIssue(
                "error",
                "empty-content",
                "A pack must declare at least one record or resource glob.",
                "pack.json",
            )
        )
    record_files, record_glob_issues = _expand_globs(root, record_patterns)
    resource_files, resource_glob_issues = _expand_globs(root, resource_patterns)
    report.issues.extend(record_glob_issues)
    report.issues.extend(resource_glob_issues)
    eligible_resource_files: list[Path] = []
    for path in resource_files:
        relative = path.relative_to(root).as_posix()
        if relative in {"pack.json", "pack.lock.json"} or relative.startswith("records/"):
            report.issues.append(
                PackIssue(
                    "error",
                    "resource-location",
                    "Resource globs may not select record files or pack control files.",
                    relative,
                )
            )
            continue
        eligible_resource_files.append(path)
    resource_files = eligible_resource_files
    report.resource_files = [path.relative_to(root).as_posix() for path in resource_files]
    resource_file_set = set(report.resource_files)
    lock_path = root / "pack.lock.json"
    lock_rows_by_path: dict[str, Mapping[str, Any]] | None = None
    if verify_lock and lock_path.is_file():
        try:
            lock_value = load_json(lock_path)
        except PackError:
            lock_value = None
        if isinstance(lock_value, Mapping) and isinstance(lock_value.get("files"), list):
            raw_lock_rows = lock_value["files"]
            if all(
                isinstance(row, Mapping) and isinstance(row.get("path"), str)
                for row in raw_lock_rows
            ):
                lock_rows_by_path = {}
                for row in raw_lock_rows:
                    lock_rows_by_path.setdefault(str(row["path"]), row)
    raw_bindings = content.get("resource_bindings") or {}
    if isinstance(raw_bindings, Mapping):
        for name, raw_path in sorted(raw_bindings.items(), key=lambda item: str(item[0])):
            relative = str(raw_path)
            if not _safe_relative_file(relative):
                report.issues.append(
                    PackIssue(
                        "error",
                        "unsafe-resource-binding",
                        f"Named resource {name!r} must use one safe POSIX-relative file path.",
                        "pack.json",
                    )
                )
            elif relative not in resource_file_set:
                report.issues.append(
                    PackIssue(
                        "error",
                        "unselected-resource-binding",
                        f"Named resource {name!r} is not selected by resource_globs: {relative}",
                        "pack.json",
                    )
                )
            else:
                report.resource_bindings[str(name)] = relative

    for name, relative in sorted(report.resource_bindings.items()):
        if name not in KNOWN_RESOURCE_VALIDATORS:
            continue
        try:
            resource_value = load_json(root / relative)
        except PackError as exc:
            report.issues.append(
                PackIssue(
                    "error",
                    "known-resource-contract",
                    f"Named resource {name!r} is not valid JSON: {exc}",
                    relative,
                )
            )
            continue
        for message in validate_known_resource(name, resource_value):
            report.issues.append(
                PackIssue(
                    "error",
                    "known-resource-contract",
                    f"Named resource {name!r}: {message}",
                    relative,
                )
            )

    seen_ids: dict[str, str] = {}
    for path in record_files:
        relative = path.relative_to(root).as_posix()
        if not relative.startswith("records/") or path.suffix.lower() != ".json":
            report.issues.append(
                PackIssue(
                    "error",
                    "record-location",
                    "Record globs may select only JSON files below records/.",
                    relative,
                )
            )
            continue
        try:
            document = load_json(path)
        except PackError as exc:
            report.issues.append(PackIssue("error", "invalid-record-json", str(exc), relative))
            continue
        report.issues.extend(_schema_issues(document, PACK_RECORD_SCHEMA_PATH, path))
        if not isinstance(document, Mapping):
            continue
        kind = str(document.get("kind") or "")
        category = str(document.get("category") or "") or None
        if kind == "module" and not category:
            report.issues.append(
                PackIssue(
                    "error",
                    "module-category",
                    "Module record files require a category.",
                    relative,
                )
            )
        for record in document.get("records") or []:
            if not isinstance(record, dict):
                continue
            record_id = str(record.get("id") or "")
            if not record_id:
                continue
            payload_category = str(record.get("category") or "") or None
            if kind == "module" and payload_category != category:
                report.issues.append(
                    PackIssue(
                        "error",
                        "module-record-category",
                        f"Module record {record_id!r} category {payload_category!r} "
                        f"does not match container category {category!r}.",
                        relative,
                    )
                )
            previous = seen_ids.get(record_id)
            if previous:
                report.issues.append(
                    PackIssue(
                        "error",
                        "duplicate-record-id",
                        f"Record ID {record_id!r} is already declared in {previous}.",
                        relative,
                    )
                )
                continue
            seen_ids[record_id] = relative
            if kind == "model":
                for message in validate_model_record(record):
                    report.issues.append(
                        PackIssue(
                            "error",
                            "model-record-contract",
                            message,
                            relative,
                        )
                    )
                # An offering that points at an observed parameter schema points at
                # a file in this pack, and that file names the same model.
                for offering in record.get("offerings") or []:
                    if not isinstance(offering, dict) or not offering.get("schema_snapshot"):
                        continue
                    for message in _snapshot_issues(root, offering):
                        report.issues.append(
                            PackIssue("error", "observed-schema", message, relative)
                        )
                    # A recommendation the offering maps to a request key must be one
                    # the observed schema accepts there.
                    for message in recommended_parameter_issues(record, offering, root):
                        report.issues.append(
                            PackIssue("error", "recommended-parameters", message, relative)
                        )
            if kind == "asset":
                references = record.get("resource_refs") or []
                if not isinstance(references, list) or not references:
                    report.issues.append(
                        PackIssue(
                            "error",
                            "asset-resource-refs",
                            f"Asset record {record_id!r} requires a non-empty resource_refs array.",
                            relative,
                        )
                    )
                    references = []
                normalized_refs = [str(value) for value in references]
                for resource_ref in normalized_refs:
                    if not _safe_relative_file(resource_ref) or resource_ref not in resource_file_set:
                        report.issues.append(
                            PackIssue(
                                "error",
                                "asset-resource-ref",
                                f"Asset record {record_id!r} refers to an undeclared resource: {resource_ref}",
                                relative,
                            )
                        )
                primary = str(record.get("primary_resource") or "")
                if primary and primary not in normalized_refs:
                    report.issues.append(
                        PackIssue(
                            "error",
                            "asset-primary-resource",
                            f"Asset record {record_id!r} primary_resource must also appear in resource_refs.",
                            relative,
                        )
                    )
                report.issues.extend(
                    _validate_asset_contract(
                        root,
                        record,
                        record_id=record_id,
                        source_file=relative,
                        resource_file_set=resource_file_set,
                        lock_rows_by_path=lock_rows_by_path,
                    )
                )
            search_terms = record.get("search_terms") or []
            if not isinstance(search_terms, list):
                report.issues.append(
                    PackIssue(
                        "error",
                        "search-terms-type",
                        f"Record {record_id!r} search_terms must be an array.",
                        relative,
                    )
                )
                search_terms = []
            for index, term in enumerate(search_terms):
                if not isinstance(term, Mapping):
                    report.issues.append(
                        PackIssue(
                            "error",
                            "search-term-type",
                            f"Record {record_id!r} search_terms[{index}] must be an object.",
                            relative,
                        )
                    )
                    continue
                phrase = str(term.get("phrase") or "").strip()
                facet = str(term.get("facet") or "").strip()
                source = str(term.get("source") or "").strip()
                try:
                    weight = float(term.get("weight"))
                except (TypeError, ValueError):
                    weight = float("nan")
                if not phrase:
                    report.issues.append(
                        PackIssue("error", "search-term-phrase", f"Record {record_id!r} has an invalid search phrase.", relative)
                    )
                if not re.fullmatch(r"[a-z][a-z0-9_-]*", facet):
                    report.issues.append(
                        PackIssue("error", "search-term-facet", f"Record {record_id!r} has an invalid search facet: {facet!r}.", relative)
                    )
                if not re.fullmatch(r"[a-z][a-z0-9_-]*", source):
                    report.issues.append(
                        PackIssue("error", "search-term-source", f"Record {record_id!r} has an invalid search source: {source!r}.", relative)
                    )
                if not math.isfinite(weight) or weight <= 0 or weight > 10:
                    report.issues.append(
                        PackIssue("error", "search-term-weight", f"Record {record_id!r} has an invalid search weight.", relative)
                    )
            record_category = (
                payload_category if kind == "module" else category or payload_category
            )
            report.records.append(PackRecord(kind, record_category, dict(record), relative))

    report.lock_present = lock_path.is_file()
    if not report.records and not report.resource_files:
        if report.lock_present:
            report.issues.append(
                PackIssue(
                    "error",
                    "empty-released-content",
                    "A locked pack must contain at least one matched record or resource.",
                    "pack.lock.json",
                )
            )
        else:
            report.issues.append(
                PackIssue(
                    "warning",
                    "empty-development-content",
                    "This unlocked development pack has no matched records or resources.",
                    "pack.json",
                )
            )
    project_owned = is_project_pack(root, manifest)
    if require_lock and not report.lock_present and not project_owned:
        report.issues.append(
            PackIssue(
                "error",
                "missing-lock",
                "Released and installed packs require pack.lock.json.",
                "pack.lock.json",
            )
        )
    elif report.lock_present and verify_lock:
        report.issues.extend(_validate_lock(root, manifest))
    elif not report.lock_present and not project_owned:
        report.issues.append(
            PackIssue(
                "warning",
                "development-pack",
                "pack.lock.json is absent; the directory is treated as a mutable development pack.",
                "pack.lock.json",
            )
        )
    return report


def require_valid(report: PackValidation) -> PackValidation:
    if report.valid:
        return report
    messages = [issue.message for issue in report.issues if issue.severity == "error"]
    raise PackError("Pack validation failed: " + "; ".join(messages))


def _user_data_home() -> Path:
    """Return the platform-independent persistent runtime-state directory."""
    return (Path.home() / ".character-prompt-builder").resolve()


def default_settings(
    *,
    extra_roots: Sequence[Path] = (),
    state_file: Path | None = None,
    cache_dir: Path | None = None,
    managed_root: Path | None = None,
    default_enabled_packs: Sequence[str] | None = None,
    default_resource_providers: Mapping[str, str] | None = None,
) -> PackSettings:
    state_home = _user_data_home()
    if state_file is not None:
        resolved_state_file = state_file.resolve()
    elif cache_dir is not None:
        resolved_state_file = (cache_dir.resolve().parent / "pack-state.json").resolve()
    else:
        resolved_state_file = (state_home / "pack-state.json").resolve()
    if cache_dir is not None:
        resolved_cache_dir = cache_dir.resolve()
    elif state_file is not None:
        resolved_cache_dir = (resolved_state_file.parent / "cache").resolve()
    else:
        resolved_cache_dir = (state_home / "cache").resolve()
    managed = (managed_root or ROOT / "packs").resolve()
    roots: list[Path] = [ROOT / "packs", managed]
    roots.extend(Path(value) for value in extra_roots)
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = root.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    if default_enabled_packs is None:
        initial_state = load_state(DEFAULT_PACK_STATE_PATH)
    if default_enabled_packs is None:
        resolved_defaults = tuple(initial_state["enabled_packs"])
    else:
        resolved_defaults = tuple(str(value) for value in default_enabled_packs)
    if default_resource_providers is None:
        resolved_default_providers = (
            tuple(sorted(initial_state["resource_providers"].items()))
            if default_enabled_packs is None
            else ()
        )
    else:
        resolved_default_providers = tuple(
            sorted((str(name), str(pack_id)) for name, pack_id in default_resource_providers.items())
        )
    # The floor belongs to the runtime that reads the user's own state file. A
    # runtime pointed at some other state file is an isolated one, and the
    # specification makes explicit user state the sole activation authority
    # there. The test is the resolved path, so naming the default path
    # explicitly keeps the floor and moving the state file elsewhere, however
    # it moved, drops it.
    isolated = resolved_state_file != (state_home / "pack-state.json").resolve()
    return PackSettings(
        roots=tuple(unique),
        state_file=resolved_state_file,
        cache_dir=resolved_cache_dir,
        managed_root=managed,
        quarantine_root=(managed / ".quarantine").resolve(),
        default_enabled_packs=resolved_defaults,
        default_resource_providers=resolved_default_providers,
        protected_pack_ids=() if isolated else resolved_defaults,
        initialize_all_discovered=(
            default_enabled_packs is None
            and load_json(PACK_INITIALIZATION_PATH)["enable_all_discovered"] is True
        ),
    )


def _manifest_only(pack_root: Path) -> tuple[dict[str, Any] | None, list[PackIssue]]:
    manifest_path = pack_root / "pack.json"
    try:
        value = load_json(manifest_path)
    except PackError as exc:
        return None, [PackIssue("error", "manifest", str(exc), str(manifest_path))]
    if not isinstance(value, dict):
        return None, [
            PackIssue("error", "manifest-type", "pack.json must contain an object.", str(manifest_path))
        ]
    issues = _schema_issues(value, PACK_SCHEMA_PATH, manifest_path)
    return value, issues


def configured_roots(
    settings: PackSettings,
    state: Mapping[str, Any] | None = None,
) -> tuple[Path, ...]:
    state_value = dict(state or load_effective_state(settings))
    roots = list(settings.roots)
    roots.extend(Path(value).expanduser().resolve() for value in state_value.get("pack_roots") or [])
    output: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = root.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            output.append(resolved)
    return tuple(output)


def _configured_pack_locations(
    settings: PackSettings,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    locations_by_path: dict[str, Path] = {}
    for root in configured_roots(settings, state):
        if not root.is_dir():
            continue
        if (root / "pack.json").is_file():
            resolved = root.resolve()
            locations_by_path[os.path.normcase(str(resolved))] = resolved
        else:
            for child in sorted(root.iterdir(), key=lambda value: value.name.lower()):
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and (child / "pack.json").is_file()
                ):
                    resolved = child.resolve()
                    locations_by_path[os.path.normcase(str(resolved))] = resolved
    return locations_by_path


def _discover_pack_locations(
    locations_by_path: Mapping[str, Path],
) -> tuple[dict[str, DiscoveredPack], list[PackIssue]]:
    discovered: dict[str, DiscoveredPack] = {}
    issues: list[PackIssue] = []

    claims: dict[str, list[tuple[Path, dict[str, Any], list[PackIssue]]]] = {}
    for pack_root in locations_by_path.values():
        manifest, manifest_issues = _manifest_only(pack_root)
        issues.extend(manifest_issues)
        if manifest is None:
            continue
        pack_id = str(manifest.get("pack_id") or "")
        if not PACK_ID_RE.fullmatch(pack_id):
            continue
        claims.setdefault(pack_id, []).append((pack_root, manifest, manifest_issues))

    for pack_id, rows in sorted(claims.items()):
        if len(rows) > 1:
            rendered = ", ".join(str(row[0]) for row in rows)
            issues.append(
                PackIssue(
                    "error",
                    "duplicate-pack-id",
                    f"Pack ID {pack_id!r} appears at multiple roots and every candidate is inactive: {rendered}.",
                )
            )
            continue
        pack_root, manifest, manifest_issues = rows[0]
        if any(issue.severity == "error" for issue in manifest_issues):
            continue
        discovered[pack_id] = DiscoveredPack(pack_root, manifest)
    return discovered, issues


def discover_packs(
    settings: PackSettings,
    state: Mapping[str, Any] | None = None,
) -> tuple[dict[str, DiscoveredPack], list[PackIssue]]:
    return _discover_pack_locations(_configured_pack_locations(settings, state))


def load_state(
    path: Path,
    *,
    default_enabled_packs: Sequence[str] = (),
    default_resource_providers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "pack_roots": [],
            "enabled_packs": [str(value) for value in default_enabled_packs],
            "resource_providers": {
                str(name): str(pack_id)
                for name, pack_id in (default_resource_providers or {}).items()
            },
        }
    value = load_json(path)
    if not isinstance(value, dict):
        raise PackError(f"Pack state must be an object: {path}")
    schema_errors = _schema_issues(value, PACK_STATE_SCHEMA_PATH, path)
    if schema_errors:
        raise PackError(
            f"Pack state failed schema validation: {schema_errors[0].message}: {path}"
        )
    unexpected = sorted(set(value) - {"pack_roots", "enabled_packs", "resource_providers"})
    if unexpected:
        raise PackError(f"Pack state contains unexpected fields {unexpected}: {path}")
    enabled = value.get("enabled_packs")
    if not isinstance(enabled, list) or any(not isinstance(item, str) for item in enabled):
        raise PackError(f"enabled_packs must be an array of pack IDs: {path}")
    if len(enabled) != len(set(enabled)):
        raise PackError(f"enabled_packs contains duplicate IDs: {path}")
    pack_roots = value.get("pack_roots", [])
    if not isinstance(pack_roots, list) or any(not isinstance(item, str) for item in pack_roots):
        raise PackError(f"pack_roots must be an array of directory paths: {path}")
    normalized_roots = [str(Path(value).expanduser().resolve()) for value in pack_roots]
    if len(normalized_roots) != len(set(os.path.normcase(value) for value in normalized_roots)):
        raise PackError(f"pack_roots contains duplicate paths: {path}")
    providers = value.get("resource_providers")
    if not isinstance(providers, dict) or any(
        not isinstance(name, str) or not isinstance(pack_id, str)
        for name, pack_id in providers.items()
    ):
        raise PackError(f"resource_providers must map resource names to pack IDs: {path}")
    return {
        "pack_roots": normalized_roots,
        "enabled_packs": list(enabled),
        "resource_providers": dict(sorted(providers.items())),
    }


def load_effective_state(settings: PackSettings) -> dict[str, Any]:
    """Load user state or the shipped initial state when no user state exists."""
    state = load_state(
        settings.state_file,
        default_enabled_packs=settings.default_enabled_packs,
        default_resource_providers=dict(settings.default_resource_providers),
    )
    if not settings.state_file.is_file() and settings.initialize_all_discovered:
        discovered, issues = discover_packs(settings, state)
        failures = [issue.message for issue in issues if issue.severity == "error"]
        if failures:
            raise PackError("Initial discovery failed: " + "; ".join(failures))
        state["enabled_packs"] = sorted(set(state["enabled_packs"]) | set(discovered))
        candidates: dict[str, list[str]] = {}
        for pack_id, pack in discovered.items():
            for name in pack.manifest.get("content", {}).get("resource_bindings", {}):
                candidates.setdefault(name, []).append(pack_id)
        for name, providers in candidates.items():
            if name not in state["resource_providers"] and len(providers) == 1:
                state["resource_providers"][name] = providers[0]
        # Competing providers without a declared default remain unresolved;
        # activation must never silently choose an arbitrary provider.
    return state


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    enabled = sorted(set(str(value) for value in state.get("enabled_packs") or []))
    roots: list[str] = []
    seen: set[str] = set()
    for value in state.get("pack_roots") or []:
        resolved = str(Path(value).expanduser().resolve())
        key = os.path.normcase(resolved)
        if key not in seen:
            seen.add(key)
            roots.append(resolved)
    providers = {
        str(name): str(pack_id)
        for name, pack_id in sorted((state.get("resource_providers") or {}).items())
    }
    value = {
        "pack_roots": roots,
        "enabled_packs": enabled,
        "resource_providers": providers,
    }
    schema_errors = _schema_issues(value, PACK_STATE_SCHEMA_PATH, path)
    if schema_errors:
        raise PackError(f"Pack state failed schema validation: {schema_errors[0].message}: {path}")
    atomic_write_json(path, value)


def add_pack_root(settings: PackSettings, root: Path) -> dict[str, Any]:
    state = load_effective_state(settings)
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise PackError(f"Pack root is not a directory: {resolved}")
    proposed = {
        "pack_roots": [*state["pack_roots"], str(resolved)],
        "enabled_packs": state["enabled_packs"],
        "resource_providers": state["resource_providers"],
    }
    discovered, _ = discover_packs(settings, proposed)
    missing = sorted(set(proposed["enabled_packs"]) - set(discovered))
    if missing:
        raise PackError(
            f"Adding this root would orphan enabled packs {missing}; disable them first. "
            "A pack UUID that appears under more than one root resolves from none of them."
        )
    save_state(settings.state_file, proposed)
    return load_effective_state(settings)


def remove_pack_root(settings: PackSettings, root: Path) -> dict[str, Any]:
    state = load_effective_state(settings)
    resolved_key = os.path.normcase(str(root.expanduser().resolve()))
    retained = [
        value
        for value in state["pack_roots"]
        if os.path.normcase(str(Path(value).resolve())) != resolved_key
    ]
    proposed = {
        "pack_roots": retained,
        "enabled_packs": state["enabled_packs"],
        "resource_providers": state["resource_providers"],
    }
    discovered, _ = discover_packs(settings, proposed)
    missing = sorted(set(proposed["enabled_packs"]) - set(discovered))
    if missing:
        raise PackError(
            f"Removing this root would orphan enabled packs {missing}; disable them first."
        )
    save_state(settings.state_file, proposed)
    return load_effective_state(settings)


def _required_pack_ids(manifest: Mapping[str, Any]) -> frozenset[str]:
    """The packs this one needs present. A dependency names a pack, not a version."""

    return frozenset(
        str(row.get("pack_id"))
        for row in manifest.get("dependencies") or []
        if isinstance(row, Mapping) and row.get("pack_id")
    )


def required_dependency_cycles(
    packs: Mapping[str, DiscoveredPack],
) -> list[tuple[str, ...]]:
    """Return canonical required-dependency cycles in the supplied pack set."""
    graph = {
        pack_id: sorted(set(_required_pack_ids(pack.manifest)) & set(packs))
        for pack_id, pack in packs.items()
    }
    visiting: list[str] = []
    visiting_set: set[str] = set()
    visited: set[str] = set()
    cycles: set[tuple[str, ...]] = set()

    def visit(pack_id: str) -> None:
        if pack_id in visited:
            return
        if pack_id in visiting_set:
            start = visiting.index(pack_id)
            cycle = visiting[start:]
            rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
            cycles.add(min(rotations))
            return
        visiting.append(pack_id)
        visiting_set.add(pack_id)
        for dependency_id in graph.get(pack_id, []):
            visit(dependency_id)
        visiting.pop()
        visiting_set.remove(pack_id)
        visited.add(pack_id)

    for pack_id in sorted(graph):
        visit(pack_id)
    return sorted(cycles)


def _resolve_enabled_from_discovery(
    state_value: Mapping[str, Any],
    discovered: Mapping[str, DiscoveredPack],
) -> list[DiscoveredPack]:
    enabled_ids = [str(value) for value in state_value.get("enabled_packs") or []]
    missing = sorted(set(enabled_ids) - set(discovered))
    if missing:
        raise PackError(f"Enabled packs are missing: {missing}")
    selected = [discovered[pack_id] for pack_id in enabled_ids]
    for item in selected:
        require_valid(validate_pack(item.root))
    selected_by_id = {item.pack_id: item for item in selected}
    cycles = required_dependency_cycles(selected_by_id)
    if cycles:
        rendered = [" -> ".join((*cycle, cycle[0])) for cycle in cycles]
        raise PackError("Required dependency cycles are forbidden: " + "; ".join(rendered))
    for item in selected:
        for dependency_id in sorted(_required_pack_ids(item.manifest)):
            if dependency_id not in selected_by_id:
                raise PackError(
                    f"Enabled pack {item.pack_id!r} requires enabled pack {dependency_id!r}."
                )
    return selected


def resolve_enabled(
    settings: PackSettings,
    state: Mapping[str, Any] | None = None,
) -> list[DiscoveredPack]:
    state_value = dict(state or load_effective_state(settings))
    discovered, _ = discover_packs(settings, state_value)
    return _resolve_enabled_from_discovery(state_value, discovered)


def _resolve_enabled_with_managed_candidate(
    settings: PackSettings,
    state: Mapping[str, Any],
    *,
    target: Path,
    candidate: Path,
) -> list[DiscoveredPack]:
    """Validate the enabled graph as it would exist after publishing candidate."""
    locations = _configured_pack_locations(settings, state)
    locations[os.path.normcase(str(target.resolve()))] = candidate.resolve()
    discovered, _ = _discover_pack_locations(locations)
    return _resolve_enabled_from_discovery(state, discovered)


def resolve_enabled_lenient(
    settings: PackSettings,
    state: Mapping[str, Any] | None = None,
) -> tuple[list[DiscoveredPack], list[PackIssue]]:
    """Resolve available enabled packs without retaining records from missing packs.

    Runtime lookup uses this form so an out-of-band pack deletion invalidates
    the cache immediately instead of making stale records searchable. Strict
    management operations continue to use ``resolve_enabled``.
    """
    state_value = dict(state or load_effective_state(settings))
    enabled_ids = [str(value) for value in state_value.get("enabled_packs") or []]
    discovered, discovery_issues = discover_packs(settings, state_value)
    issues: list[PackIssue] = list(discovery_issues)
    selected: list[DiscoveredPack] = []
    for pack_id in enabled_ids:
        pack = discovered.get(pack_id)
        if pack is None:
            issues.append(
                PackIssue(
                    "error",
                    "enabled-pack-unavailable",
                    f"Enabled pack is missing or has an invalid manifest: {pack_id}",
                )
            )
        else:
            selected.append(pack)
    return selected, issues


def enable_pack(settings: PackSettings, pack_id: str) -> dict[str, Any]:
    if not PACK_ID_RE.fullmatch(pack_id):
        raise PackError(f"Pack ID must be a lowercase UUIDv7: {pack_id!r}")
    state = load_effective_state(settings)
    discovered, _ = discover_packs(settings, state)
    target = discovered.get(pack_id)
    if target is None:
        raise PackError(f"Unknown pack ID: {pack_id}")
    required = _required_pack_ids(target.manifest)
    missing = sorted(set(required) - set(state["enabled_packs"]))
    if missing:
        raise PackError(f"Enable required dependencies first: {missing}")
    proposed = {
        "pack_roots": state["pack_roots"],
        "enabled_packs": sorted({*state["enabled_packs"], pack_id}),
        "resource_providers": state["resource_providers"],
    }
    resolve_enabled(settings, proposed)
    if pack_id in state["enabled_packs"]:
        return state
    save_state(settings.state_file, proposed)
    return proposed


def disable_pack(settings: PackSettings, pack_id: str, *, cascade: bool = False) -> dict[str, Any]:
    if not PACK_ID_RE.fullmatch(pack_id):
        raise PackError(f"Pack ID must be a lowercase UUIDv7: {pack_id!r}")
    if pack_id in settings.protected_pack_ids:
        raise PackError(
            f"Pack {pack_id!r} is a bundled default pack and cannot be disabled; "
            "it supplies the shipped catalog records and named resources every "
            "other pack resolves against."
        )
    state = load_effective_state(settings)
    enabled = set(state["enabled_packs"])
    if pack_id not in enabled:
        return state
    discovered, _ = discover_packs(settings)
    dependents = {
        current_id
        for current_id in enabled
        if current_id in discovered and pack_id in _required_pack_ids(discovered[current_id].manifest)
    }
    if dependents and not cascade:
        raise PackError(
            f"Pack {pack_id!r} is required by enabled packs {sorted(dependents)}; use cascade to disable them together."
        )
    removal = {pack_id}
    if cascade:
        changed = True
        while changed:
            changed = False
            for current_id in enabled - removal:
                if current_id not in discovered:
                    continue
                if set(_required_pack_ids(discovered[current_id].manifest)) & removal:
                    removal.add(current_id)
                    changed = True
    proposed = {
        "pack_roots": state["pack_roots"],
        "enabled_packs": sorted(enabled - removal),
        "resource_providers": state["resource_providers"],
    }
    save_state(settings.state_file, proposed)
    return proposed


def select_resource_provider(
    settings: PackSettings,
    name: str,
    pack_id: str,
) -> dict[str, Any]:
    """Select the sole enabled provider for one logical resource name."""
    if not RESOURCE_NAME_RE.fullmatch(name):
        raise PackError(f"Invalid logical resource name: {name!r}")
    if not PACK_ID_RE.fullmatch(pack_id):
        raise PackError(f"Pack ID must be a lowercase UUIDv7: {pack_id!r}")
    state = load_effective_state(settings)
    if pack_id not in state["enabled_packs"]:
        raise PackError(f"Resource provider pack is not enabled: {pack_id}")
    discovered, issues = discover_packs(settings, state)
    if pack_id not in discovered:
        matching = [issue.message for issue in issues if pack_id in issue.message]
        detail = f" ({matching[0]})" if matching else ""
        raise PackError(f"Resource provider pack is unavailable: {pack_id}{detail}")
    report = require_valid(validate_pack(discovered[pack_id].root))
    if name not in report.resource_bindings:
        raise PackError(f"Pack {pack_id} does not provide logical resource {name!r}.")
    proposed = {
        "pack_roots": state["pack_roots"],
        "enabled_packs": state["enabled_packs"],
        "resource_providers": {**state["resource_providers"], name: pack_id},
    }
    save_state(settings.state_file, proposed)
    return load_effective_state(settings)


def clear_resource_provider(settings: PackSettings, name: str) -> dict[str, Any]:
    """Remove the explicit provider selection for one logical resource."""
    if not RESOURCE_NAME_RE.fullmatch(name):
        raise PackError(f"Invalid logical resource name: {name!r}")
    state = load_effective_state(settings)
    providers = dict(state["resource_providers"])
    providers.pop(name, None)
    proposed = {
        "pack_roots": state["pack_roots"],
        "enabled_packs": state["enabled_packs"],
        "resource_providers": providers,
    }
    save_state(settings.state_file, proposed)
    return load_effective_state(settings)


def quick_pack_snapshot(pack: DiscoveredPack) -> dict[str, Any]:
    """What a pack is, as the bytes it holds rather than as what is said of it.

    A modification time is not content: a checkout, a copy or a restore moves it
    while the bytes stay identical, and a write that lands on the same size
    within the same clock tick leaves it unmoved while the bytes differ.
    Deciding to rebuild from one therefore rebuilds when nothing changed and can
    decline to rebuild when something did. A size is the same kind of proxy.

    A lock is a claim about the files, not the files. Hashing only the lock
    therefore cannot see a pack that drifted away from it, and the same bytes on
    disk would then name one catalog through a warm cache and another through a
    cold one, because a cold build validates the pack and drops it. Every file
    is hashed whether or not a lock is present, so this snapshot is a function
    of the pack's bytes and one disk state names exactly one catalog.
    """

    manifest_path = pack.root / "pack.json"
    lock_path = pack.root / "pack.lock.json"
    files, issues = _all_pack_files(pack.root)
    if issues:
        raise PackError(f"{issues[0].message} ({pack.pack_id}: {issues[0].path})")
    rows: list[dict[str, Any]] = [
        {
            "path": path.relative_to(pack.root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    # No declared release. A release is a claim written in pack.json, and the
    # hash of pack.json is already here, so changing the release changes this
    # snapshot through the hash and never through the claim. Naming it as well
    # would make a label an input to a decision that content already settles.
    return {
        "pack_id": pack.pack_id,
        "root": str(pack.root),
        "manifest_sha256": sha256_file(manifest_path),
        "lock_sha256": sha256_file(lock_path) if lock_path.is_file() else None,
        "files": rows,
    }


def active_snapshot(settings: PackSettings, *, strict: bool = False) -> dict[str, Any]:
    state = load_effective_state(settings)
    if strict:
        selected = resolve_enabled(settings, state)
        issues: list[PackIssue] = []
    else:
        selected, issues = resolve_enabled_lenient(settings, state)
    packs = [quick_pack_snapshot(pack) for pack in selected]
    # No product version. What built a cache is settled by hashing the modules
    # and schemas that build it, which _builder_fingerprint does, so naming the
    # version as well would rebuild every cache on a version bump that changed
    # nothing about building one.
    payload = {
        "enabled_packs": list(state.get("enabled_packs") or []),
        "resource_providers": dict(sorted((state.get("resource_providers") or {}).items())),
        "available_enabled_packs": [pack.pack_id for pack in selected],
        "discovery_issues": [issue.to_dict() for issue in issues],
        "packs": packs,
    }
    payload["fingerprint"] = sha256_bytes(canonical_json(payload).encode("utf-8"))
    return payload


def _safe_extract_zip(archive: Path, destination: Path) -> Path:
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            members: list[tuple[zipfile.ZipInfo, PurePosixPath, str, bool]] = []
            member_keys: set[str] = set()
            file_keys: set[str] = set()
            for info in infos:
                if info.flag_bits & 0x1:
                    raise PackError(
                        f"Encrypted archive members are not supported: {info.filename!r}"
                    )
                if "\\" in info.filename:
                    raise PackError(f"Archive member uses a backslash path: {info.filename!r}")
                member = PurePosixPath(info.filename)
                if (
                    member.is_absolute()
                    or not member.parts
                    or any(part in {"", ".", ".."} for part in member.parts)
                    or re.match(r"^[A-Za-z]:", member.parts[0])
                ):
                    raise PackError(f"Archive member has an unsafe path: {info.filename!r}")
                member_key = "/".join(os.path.normcase(part) for part in member.parts)
                if member_key in member_keys:
                    raise PackError(f"Archive contains a duplicate member path: {info.filename!r}")
                member_keys.add(member_key)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise PackError(f"Archive contains a symbolic link: {info.filename!r}")
                is_directory = info.is_dir()
                if not is_directory:
                    file_keys.add(member_key)
                members.append((info, member, member_key, is_directory))

            for info, member, member_key, _ in members:
                parts = member_key.split("/")
                for end in range(1, len(parts)):
                    if "/".join(parts[:end]) in file_keys:
                        raise PackError(
                            "Archive contains a file/directory path collision: "
                            f"{info.filename!r}"
                        )

            for info, member, _, is_directory in members:
                target = destination.joinpath(*member.parts)
                _relative_path(destination, target)
                if is_directory:
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
    except (zipfile.BadZipFile, EOFError) as exc:
        raise PackError(f"Invalid or truncated ZIP archive {archive}: {exc}") from exc
    if (destination / "pack.json").is_file():
        return destination
    roots = [
        child for child in destination.iterdir()
        if child.is_dir() and (child / "pack.json").is_file()
    ]
    if len(roots) != 1:
        raise PackError("Archive must contain pack.json at its root or in one top-level directory.")
    return roots[0]


def _source_pack_root(source: Path, temporary_root: Path) -> Path:
    source = source.resolve()
    if source.is_dir():
        return source
    if source.is_file() and source.suffix.lower() == ".zip":
        extracted = temporary_root / "extracted"
        extracted.mkdir()
        return _safe_extract_zip(source, extracted)
    raise PackError("Pack source must be a directory or a .zip archive.")


def _within(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    base = root.resolve()
    return resolved == base or base in resolved.parents


def _make_owner_writable(path: Path) -> None:
    mode = path.stat().st_mode
    owner_bits = stat.S_IWUSR
    if path.is_dir():
        owner_bits |= stat.S_IRUSR | stat.S_IXUSR
    path.chmod(mode | owner_bits)


def _copy_pack_tree(source: Path, destination: Path) -> None:
    """Copy exact file bytes without importing source permission metadata."""
    destination.mkdir()
    _make_owner_writable(destination)
    for source_path in sorted(source.iterdir(), key=lambda value: value.name):
        if _is_link(source_path):
            raise PackError(
                "Symbolic links and directory junctions are forbidden in packs: "
                f"{source_path}"
            )
        destination_path = destination / source_path.name
        if source_path.is_dir():
            _copy_pack_tree(source_path, destination_path)
        elif source_path.is_file():
            shutil.copyfile(source_path, destination_path)
            _make_owner_writable(destination_path)
        else:
            raise PackError(f"Unsupported pack filesystem entry: {source_path}")


def _remove_transaction_tree(path: Path) -> None:
    """Remove a transaction-owned tree, including read-only partial copies."""
    if not path.exists():
        return
    _make_owner_writable(path)
    for child in path.rglob("*"):
        _make_owner_writable(child)

    def retry_with_write_permission(function: Any, value: str, _: Any) -> None:
        target = Path(value)
        _make_owner_writable(target)
        function(value)

    shutil.rmtree(path, onerror=retry_with_write_permission)


def _note_secondary_failure(
    original: BaseException,
    operation: str,
    secondary: BaseException,
) -> None:
    if hasattr(original, "add_note"):
        original.add_note(f"{operation} also failed: {secondary}")


def install_pack(
    settings: PackSettings,
    source: Path,
    *,
    update: bool = False,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cpb-pack-install-") as temp:
        source_root = _source_pack_root(source, Path(temp))
        report = require_valid(validate_pack(source_root, require_lock=True))
        assert report.pack_id and report.release
        target = settings.managed_root.resolve() / report.pack_id
        if update and not target.exists():
            raise PackError(
                f"Cannot update pack {report.pack_id}: it is not installed in the managed root."
            )
        settings.managed_root.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or (
            hasattr(target, "is_junction") and target.is_junction()
        ):
            raise PackError(f"Managed pack target must not be a link: {target}")
        if not _within(target, settings.managed_root):
            raise PackError("Resolved installation target escapes the managed pack root.")
        if target.exists() and not update:
            raise PackError(f"Pack is already installed: {report.pack_id}")
        previous_release: str | None = None
        if target.exists():
            previous = require_valid(validate_pack(target))
            previous_release = previous.release
            if not previous_release or calver_key(report.release) <= calver_key(previous_release):
                raise PackError(
                    f"Update release must be newer than {previous_release}; got {report.release}."
                )
        staging = settings.managed_root / f".staging-{report.pack_id}-{uuid.uuid4().hex}"
        backup: Path | None = None
        quarantine_created = False
        try:
            _copy_pack_tree(source_root, staging)
            require_valid(validate_pack(staging, require_lock=True))
            state = load_effective_state(settings)
            if report.pack_id in state["enabled_packs"]:
                _resolve_enabled_with_managed_candidate(
                    settings,
                    state,
                    target=target,
                    candidate=staging,
                )
            if target.exists():
                quarantine_created = not settings.quarantine_root.exists()
                settings.quarantine_root.mkdir(parents=True, exist_ok=True)
                if not _within(settings.quarantine_root, settings.managed_root):
                    raise PackError("Quarantine must remain inside the managed pack root.")
                backup = settings.quarantine_root / (
                    f"{report.pack_id}-{previous_release}-replaced-{int(time.time())}-{uuid.uuid4().hex[:8]}"
                )
                os.replace(target, backup)
            os.replace(staging, target)
        except Exception as original:
            if backup is not None:
                try:
                    if backup.exists() and not target.exists():
                        os.replace(backup, target)
                except Exception as rollback_error:
                    _note_secondary_failure(
                        original,
                        f"Rollback to the original pack at {target}",
                        rollback_error,
                    )
            try:
                if staging.exists():
                    _remove_transaction_tree(staging)
            except Exception as cleanup_error:
                _note_secondary_failure(
                    original,
                    f"Cleanup of transaction staging directory {staging}",
                    cleanup_error,
                )
            try:
                if quarantine_created and settings.quarantine_root.exists():
                    if not any(settings.quarantine_root.iterdir()):
                        _make_owner_writable(settings.quarantine_root)
                        settings.quarantine_root.rmdir()
            except Exception as cleanup_error:
                _note_secondary_failure(
                    original,
                    f"Cleanup of transaction quarantine directory {settings.quarantine_root}",
                    cleanup_error,
                )
            raise
        return {
            "ok": True,
            "operation": "update" if update else "install",
            "pack_id": report.pack_id,
            "release": report.release,
            "path": str(target),
            "previous_release": previous_release,
            "recoverable_backup": str(backup) if backup else None,
        }


def remove_pack(settings: PackSettings, pack_id: str) -> dict[str, Any]:
    if not PACK_ID_RE.fullmatch(pack_id):
        raise PackError(f"Pack ID must be a lowercase UUIDv7: {pack_id!r}")
    state = load_effective_state(settings)
    if pack_id in state["enabled_packs"]:
        raise PackError("Disable the pack before removing it.")
    target = settings.managed_root.resolve() / pack_id
    if target.is_symlink() or (
        hasattr(target, "is_junction") and target.is_junction()
    ):
        raise PackError(f"Managed pack target must not be a link: {target}")
    if not _within(target, settings.managed_root) or not target.is_dir():
        raise PackError(f"Pack is not installed in the managed root: {pack_id}")
    release: str | None = None
    manifest, _ = _manifest_only(target)
    if isinstance(manifest, Mapping):
        candidate_release = manifest.get("release")
        try:
            calver_key(candidate_release, field="pack release")
        except ValueError:
            pass
        else:
            release = candidate_release
    settings.quarantine_root.mkdir(parents=True, exist_ok=True)
    if not _within(settings.quarantine_root, settings.managed_root):
        raise PackError("Quarantine must remain inside the managed pack root.")
    release_token = release or "unknown-release"
    quarantine = settings.quarantine_root / (
        f"{pack_id}-{release_token}-removed-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    )
    os.replace(target, quarantine)
    return {
        "ok": True,
        "operation": "remove",
        "pack_id": pack_id,
        "release": release,
        "quarantine_path": str(quarantine),
        "recoverable": True,
    }


def list_packs(
    settings: PackSettings,
    *,
    verify_lock: bool = True,
) -> dict[str, Any]:
    """List discovered packs without overstating runtime eligibility."""

    state = load_effective_state(settings)
    enabled = set(state["enabled_packs"])
    discovered, issues = discover_packs(settings, state)
    rows: list[dict[str, Any]] = []
    for pack_id, pack in sorted(discovered.items()):
        validation = validate_pack(pack.root, verify_lock=verify_lock)
        lock_issue_codes = {
            "invalid-lock-json", "lock-pack-id", "lock-release",
            "lock-inventory", "lock-duplicate-path", "lock-missing-files",
            "lock-extra-files", "lock-file-mismatch", "lock-content-hash",
            "missing-lock",
        }
        structurally_valid = not any(
            issue.severity == "error" and issue.code not in lock_issue_codes
            for issue in validation.issues
        )
        lock_errors = [
            issue for issue in validation.issues
            if issue.severity == "error" and issue.code in lock_issue_codes
        ]
        lock_verified = bool(
            verify_lock and validation.lock_present and not lock_errors
        )
        rows.append(
            {
                "pack_id": pack_id,
                "name": pack.manifest.get("name"),
                "release": pack.release,
                "capabilities": sorted(
                    str(value) for value in pack.manifest.get("capabilities") or []
                ),
                "enabled": pack_id in enabled,
                "root": str(pack.root),
                "lock_present": validation.lock_present,
                "lock_verified": lock_verified,
                "record_count": len(validation.records),
                "structurally_valid": structurally_valid,
                "valid": validation.valid if verify_lock else None,
                "errors": [
                    issue.to_dict()
                    for issue in validation.issues
                    if issue.severity == "error"
                ],
            }
        )
    return {
        "ok": not any(issue.severity == "error" for issue in issues),
        "lock_verification_requested": verify_lock,
        "state_file": str(settings.state_file),
        "roots": [str(root) for root in configured_roots(settings, state)],
        "enabled_packs": sorted(enabled),
        "resource_providers": state["resource_providers"],
        "packs": rows,
        "discovery_issues": [issue.to_dict() for issue in issues],
        # An id claimed by more than one enabled pack is excluded from the
        # catalog entirely, with no copy surviving, unless exactly one of them
        # declares that it replaces the others'. That is settled where the packs
        # are merged, however many there are, so it is reported here rather than
        # discovered by a lookup that comes back empty.
        "catalog_diagnostics": _catalog_diagnostics(settings),
    }


def _catalog_diagnostics(settings: PackSettings) -> list[dict[str, Any]]:
    try:
        from pack_cache import load_runtime_catalog

        return [dict(row) for row in load_runtime_catalog(settings).diagnostics]
    except Exception:  # noqa: BLE001 - listing packs must not fail on a cold cache
        return []


def initialize_state_file(settings: PackSettings) -> dict[str, Any]:
    """Persist the resolved state file when absent, then report discovery.

    The effective state is the existing state file when present, otherwise the
    shipped initial state. Persisting it makes the resolved location the
    durable activation authority for later commands that omit an explicit
    state path. The operation never rewrites an existing state file.
    """
    created = not settings.state_file.is_file()
    if created:
        save_state(settings.state_file, load_effective_state(settings))
    inventory = list_packs(settings)
    return {
        "ok": inventory["ok"],
        "operation": "state-init",
        "created": created,
        "state_file": inventory["state_file"],
        "cache_dir": str(settings.cache_dir),
        "managed_root": str(settings.managed_root),
        "enabled_packs": inventory["enabled_packs"],
        "resource_providers": inventory["resource_providers"],
        "disabled_discovered_packs": [
            row["pack_id"] for row in inventory["packs"] if not row["enabled"]
        ],
        "packs": inventory["packs"],
        "discovery_issues": inventory["discovery_issues"],
    }
