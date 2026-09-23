#!/usr/bin/env python3
"""Audit duplicates and safely remove presets or redundant Visual Evidence.

Duplicate reports are advisory. Near visual or semantic similarity never
authorizes automatic deletion. Mutations are dry-runs unless ``--apply`` and
an exact ``--confirm`` value are both supplied.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

sys.dont_write_bytecode = True

from execution_contract import TEMPORARY_PREFIX
from pack_manager import (
    PackError,
    PackRecord,
    atomic_write_json,
    calver_key,
    canonical_json,
    sha256_bytes,
    sha256_file,
    validate_pack,
    write_lock,
)
from search_discovery import infer_discovery_group, infer_variant_of


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
EVIDENCE_ASSET_ID_RE = re.compile(r"^visual-evidence-[a-f0-9]{16}$")
# ``execution_contract.atomic`` writes the prefix and sixteen hex digits beside its
# destination. A process killed between the write and the rename leaves that
# file behind, and the lock inventory then refuses the pack.
ORPHAN_TEMPORARY_RE = re.compile("^" + re.escape(TEMPORARY_PREFIX) + "[0-9a-f]{16}$")
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"})
SOFT_REFERENCE_FIELDS = frozenset({"distinct_from"})
# Pack trees are never read by the report-only external scan: one of them is the
# pack under maintenance and the rest may be private. Generated and derived trees
# are excluded because they are rebuilt rather than edited.
EXTERNAL_SCAN_EXCLUDED_ROOTS = frozenset({"packs", "catalog", "dist", "cpb-output"})
EXTERNAL_SCAN_SUFFIXES = frozenset({
    ".json", ".jsonl", ".md", ".txt", ".py", ".toml", ".yaml", ".yml", ".cfg", ".ini", ".csv",
})
EVIDENCE_REFERENCE_FIELDS = frozenset({"canonical_record_ids", "canonical_record_refs"})
SEMANTIC_FIELDS = (
    "label",
    "image_promise",
    "visual_function",
    "prompt",
    "staging",
    "defaults",
    "must_preserve",
    "tags",
    "outcome_summary",
    "search_profile",
)
STOPWORDS = frozenset({
    "the", "and", "with", "that", "from", "into", "this", "one", "for",
    "while", "rather", "than", "remain", "remains", "keep", "clear", "each",
    "scene", "image", "adult", "subject", "visible", "specific", "around",
})


class MaintenanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecordLocation:
    kind: str
    category: str | None
    record: dict[str, Any]
    path: Path
    relative: str
    index: int


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaintenanceError(f"Cannot read JSON {path}: {exc}") from exc


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _file_sha_for_json(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _finalize(value: dict[str, Any], field: str) -> None:
    clone = dict(value)
    clone.pop(field, None)
    value[field] = sha256_bytes(canonical_json(clone).encode("utf-8"))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validated_pack(pack_root: Path, *, verify_lock: bool = True):
    root = pack_root.resolve()
    validation = validate_pack(root, require_lock=verify_lock, verify_lock=verify_lock)
    errors = [issue.message for issue in validation.issues if issue.severity == "error"]
    if errors:
        raise MaintenanceError("Pack validation failed: " + "; ".join(errors))
    if not validation.manifest:
        raise MaintenanceError("Pack manifest is unavailable")
    return validation


def _record_locations(validation: Any) -> list[RecordLocation]:
    root = validation.root
    documents: dict[str, dict[str, Any]] = {}
    counters: dict[str, int] = defaultdict(int)
    output: list[RecordLocation] = []
    for row in validation.records:
        relative = str(row.source_file)
        document = documents.get(relative)
        if document is None:
            document = _read_json(root / relative)
            documents[relative] = document
        index = counters[relative]
        counters[relative] += 1
        records = document.get("records") or []
        if index >= len(records) or records[index].get("id") != row.record.get("id"):
            matches = [i for i, value in enumerate(records) if value.get("id") == row.record.get("id")]
            if len(matches) != 1:
                raise MaintenanceError(f"Cannot locate record {row.record.get('id')!r} in {relative}")
            index = matches[0]
        output.append(RecordLocation(
            kind=row.kind,
            category=row.category,
            record=records[index],
            path=root / relative,
            relative=relative,
            index=index,
        ))
    return output


def _walk_strings(value: Any, pointer: tuple[str | int, ...] = ()) -> Iterable[tuple[tuple[str | int, ...], str]]:
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, (*pointer, index))
    elif isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk_strings(child, (*pointer, str(key)))


def _pointer_text(pointer: Sequence[str | int]) -> str:
    return "/" + "/".join(str(value).replace("~", "~0").replace("/", "~1") for value in pointer)


def _nearest_field(pointer: Sequence[str | int]) -> str:
    for value in reversed(pointer):
        if isinstance(value, str):
            return value
    return ""


def _record_owner_pointer(location: RecordLocation, pointer: Sequence[str | int]) -> bool:
    return len(pointer) >= 2 and pointer[0] == "records" and pointer[1] == location.index


def _pack_json_candidates(validation: Any) -> list[str]:
    paths = {str(row.source_file) for row in validation.records}
    paths.update(str(value) for value in validation.resource_files)
    paths.discard("pack.lock.json")
    paths.add("pack.json")
    return sorted(paths)


def _scan_references(
    validation: Any,
    target: RecordLocation,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    target_id = str(target.record["id"])
    root = validation.root
    for relative in _pack_json_candidates(validation):
        path = root / relative
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in {".json", ".jsonl", ".md", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if target_id not in text:
            continue
        if path.suffix.lower() not in {".json", ".jsonl"}:
            blockers.append({"path": relative, "pointer": None, "field": None, "type": "text-reference"})
            continue
        values: list[Any]
        if path.suffix.lower() == ".jsonl":
            values = []
            for line_number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    values.append({"line": line_number, "value": json.loads(line)})
                except json.JSONDecodeError as exc:
                    raise MaintenanceError(f"Invalid JSONL {relative}:{line_number}: {exc}") from exc
        else:
            values = [_read_json(path)]
        for outer_index, value in enumerate(values):
            outer_prefix: tuple[str | int, ...] = () if len(values) == 1 else (outer_index,)
            for pointer, string in _walk_strings(value, outer_prefix):
                if string != target_id:
                    continue
                if relative == target.relative and _record_owner_pointer(target, pointer):
                    continue
                field = _nearest_field(pointer)
                row = {"path": relative, "pointer": _pointer_text(pointer), "field": field}
                if field in SOFT_REFERENCE_FIELDS:
                    row["type"] = "soft-relation"
                    soft.append(row)
                elif field in EVIDENCE_REFERENCE_FIELDS:
                    row["type"] = "evidence-link"
                    evidence.append(row)
                else:
                    row["type"] = "blocking-reference"
                    blockers.append(row)
    return blockers, soft, evidence


def _product_root(pack_root: Path) -> Path | None:
    """Find the product tree that owns ``pack_root``, if the pack sits inside one."""

    root = pack_root.resolve()
    for candidate in (root, *root.parents):
        if (candidate / "package-manifest.toml").is_file():
            return candidate
    return None


def _scan_external_evaluations(product_root: Path, target_id: str) -> list[dict[str, Any]]:
    """Report core release contracts that require ``target_id`` to keep existing.

    The contract lives outside every pack, so a pack-local scan cannot see it,
    yet ``scripts/default_release_smoke_test.py`` fails the moment the record it
    names disappears. Blocking here moves that failure to planning time.
    """

    from package_metadata import CORE_RELEASE_REGRESSION_CONTRACT

    rows: list[dict[str, Any]] = []
    for relative in (CORE_RELEASE_REGRESSION_CONTRACT,):
        path = product_root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if target_id not in text:
            continue
        values: list[Any]
        if path.suffix.lower() == ".jsonl":
            values = []
            for line_number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    values.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise MaintenanceError(f"Invalid JSONL {relative}:{line_number}: {exc}") from exc
        else:
            values = [_read_json(path)]
        for outer_index, value in enumerate(values):
            outer_prefix: tuple[str | int, ...] = () if len(values) == 1 else (outer_index,)
            for pointer, string in _walk_strings(value, outer_prefix):
                if string != target_id:
                    continue
                rows.append({
                    "path": relative,
                    "pointer": _pointer_text(pointer),
                    "field": _nearest_field(pointer),
                    "type": "external-evaluation-reference",
                })
    return rows


def _external_text_occurrences(product_root: Path, pack_root: Path, target_id: str) -> list[dict[str, Any]]:
    """List every other place in the product tree that mentions ``target_id``.

    This is reported, never blocking. Release history prose cannot be rewritten,
    so an occurrence here is something an owner reads before deciding, not a
    permanent refusal. Pack roots are skipped so no private pack is read.
    """

    rows: list[dict[str, Any]] = []
    for current, dirnames, filenames in os.walk(product_root):
        current_path = Path(current)
        relative_dir = current_path.relative_to(product_root).as_posix()
        if relative_dir == ".":
            dirnames[:] = sorted(
                name for name in dirnames
                if name not in EXTERNAL_SCAN_EXCLUDED_ROOTS and not name.startswith(".")
            )
        else:
            dirnames[:] = sorted(
                name for name in dirnames
                if name != "__pycache__" and not name.startswith(".")
            )
        for name in sorted(filenames):
            path = current_path / name
            if path.is_symlink() or path.suffix.lower() not in EXTERNAL_SCAN_SUFFIXES:
                continue
            if _is_within(path, pack_root):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if target_id not in text:
                continue
            relative = path.relative_to(product_root).as_posix()
            for line_number, line in enumerate(text.splitlines(), 1):
                if target_id in line:
                    rows.append({
                        "path": relative,
                        "line": line_number,
                        "type": "external-text-occurrence",
                    })
    return rows


def _bound_resource(validation: Any, name: str) -> Path | None:
    relative = validation.resource_bindings.get(name)
    return (validation.root / relative).resolve() if relative else None


def _parse_occurrences(values: Sequence[str]) -> dict[str, int]:
    output: dict[str, int] = {}
    for value in values:
        sha, separator, count_text = value.partition("=")
        if not separator or not SHA256_RE.fullmatch(sha):
            raise MaintenanceError("--source-occurrence must use lowercase SHA256=COUNT")
        try:
            count = int(count_text)
        except ValueError as exc:
            raise MaintenanceError("source occurrence count must be an integer") from exc
        if count < 1:
            raise MaintenanceError("source occurrence count must be positive")
        output[sha] = count
    return output


def _parse_evidence_groups(values: Sequence[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    seen: set[str] = set()
    for value in values:
        group = [item.strip() for item in value.split(",") if item.strip()]
        if len(group) < 2:
            raise MaintenanceError("--group requires KEEP_ASSET_ID,DUPLICATE_ASSET_ID[,DUPLICATE_ASSET_ID...]")
        for asset_id in group:
            if not EVIDENCE_ASSET_ID_RE.fullmatch(asset_id):
                raise MaintenanceError(f"Invalid Visual Evidence asset id: {asset_id!r}")
            if asset_id in seen:
                raise MaintenanceError(f"Visual Evidence asset appears in more than one group: {asset_id}")
            seen.add(asset_id)
        groups.append(group)
    if not groups:
        raise MaintenanceError("At least one --group is required")
    return groups


def build_removal_plan(
    pack_root: Path,
    record_id: str,
    *,
    evidence_mode: str,
    source_occurrences: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    validation = _validated_pack(pack_root)
    locations = _record_locations(validation)
    matches = [row for row in locations if row.record.get("id") == record_id]
    if len(matches) != 1:
        raise MaintenanceError(f"Expected exactly one record {record_id!r}, found {len(matches)}")
    target = matches[0]
    blockers, soft, evidence_references = _scan_references(validation, target)
    product_root = _product_root(validation.root)
    external_references: list[dict[str, Any]] = []
    if product_root is None:
        external_scan: dict[str, Any] = {"executed": False, "reason": "product root is unavailable"}
    else:
        evaluation_blockers = _scan_external_evaluations(product_root, record_id)
        blockers.extend(evaluation_blockers)
        external_references = _external_text_occurrences(product_root, validation.root, record_id)
        external_scan = {
            "executed": True,
            "product_root": str(product_root),
            "evaluation_reference_count": len(evaluation_blockers),
            "reported_occurrence_count": len(external_references),
        }
    manifest_path = _bound_resource(validation, "reference-corpus-manifest")
    evidence_entries: list[dict[str, Any]] = []
    occurrence_map = dict(source_occurrences or {})
    if manifest_path and manifest_path.is_file():
        manifest = _read_json(manifest_path)
        evidence_entries = [
            entry for entry in manifest.get("entries") or []
            if record_id in (entry.get("canonical_record_ids") or [])
        ]
    purge_errors: list[str] = []
    if evidence_mode == "purge":
        for entry in evidence_entries:
            sha = str(entry.get("source_sha256") or "")
            remaining = [value for value in entry.get("canonical_record_ids") or [] if value != record_id]
            if remaining:
                purge_errors.append(f"{sha}: evidence also belongs to {remaining}")
            if entry.get("evidence_relation") == "exact-duplicate-group" and sha not in occurrence_map:
                purge_errors.append(f"{sha}: exact duplicate group requires --source-occurrence {sha}=COUNT")
    blockers.extend(
        {"path": "reference-corpus", "pointer": None, "field": None, "type": "purge-precondition", "message": value}
        for value in purge_errors
    )
    return {
        "ok": True,
        "operation": "remove-preset-plan",
        "dry_run": True,
        "pack_root": str(validation.root),
        "pack_id": validation.pack_id,
        "current_release": validation.release,
        "record": {
            "id": record_id,
            "kind": target.kind,
            "category": target.category,
            "source_file": target.relative,
            "label": target.record.get("label"),
        },
        "evidence_mode": evidence_mode,
        "evidence_entry_count": len(evidence_entries),
        "evidence_source_sha256": [entry.get("source_sha256") for entry in evidence_entries],
        "soft_unlinks": soft,
        "evidence_links": evidence_references,
        "blocking_references": blockers,
        "external_scan": external_scan,
        "external_references": external_references,
        "can_apply": not blockers,
        "source_occurrences": occurrence_map,
        "safety": {
            "near_matches_are_never_removed": True,
            "confirmation_required": record_id,
            "quarantine_outside_pack_required": True,
        },
    }


def build_evidence_consolidation_plan(
    pack_root: Path,
    groups: Sequence[Sequence[str]],
    *,
    source_occurrences: Mapping[str, int] | None = None,
    remove_all: bool = False,
) -> dict[str, Any]:
    validation = _validated_pack(pack_root)
    manifest_path = _bound_resource(validation, "reference-corpus-manifest")
    thumbnail_path = _bound_resource(validation, "catalog-thumbnails")
    if not manifest_path or not manifest_path.is_file():
        raise MaintenanceError("reference-corpus-manifest is unavailable")
    if not thumbnail_path or not thumbnail_path.is_file():
        raise MaintenanceError("catalog-thumbnails is unavailable")

    manifest = _read_json(manifest_path)
    thumbnails = _read_json(thumbnail_path).get("assets") or {}
    entries_by_sha = {str(entry.get("source_sha256")): entry for entry in manifest.get("entries") or []}
    assets: dict[str, Mapping[str, Any]] = {}
    for row in validation.records:
        if row.kind == "asset" and row.record.get("asset_type") == "visual-evidence-bundle":
            assets[str(row.record.get("id"))] = row.record

    normalized = [list(group) for group in groups]
    flattened = [asset_id for group in normalized for asset_id in group]
    if len(flattened) != len(set(flattened)):
        raise MaintenanceError("Each Visual Evidence asset may appear in only one consolidation group")
    minimum_group_size = 1 if remove_all else 2
    if any(len(group) < minimum_group_size for group in normalized):
        raise MaintenanceError("Each consolidation group requires one keeper and at least one duplicate")
    if not flattened:
        raise MaintenanceError("At least one Visual Evidence asset is required")
    for asset_id in flattened:
        if not EVIDENCE_ASSET_ID_RE.fullmatch(asset_id):
            raise MaintenanceError(f"Invalid Visual Evidence asset id: {asset_id!r}")

    blockers: list[dict[str, Any]] = []
    occurrence_map = dict(source_occurrences or {})
    described_groups: list[dict[str, Any]] = []
    removal_shas: set[str] = set()
    corpus_root = manifest_path.parent
    for group in normalized:
        described: list[dict[str, Any]] = []
        for position, asset_id in enumerate(group):
            asset = assets.get(asset_id)
            if asset is None:
                blockers.append({"asset_id": asset_id, "message": "Visual Evidence asset record is unavailable"})
                continue
            sha = str(asset.get("source_sha256") or "")
            entry = entries_by_sha.get(sha)
            if entry is None:
                blockers.append({"asset_id": asset_id, "message": f"Manifest entry is unavailable for {sha}"})
                continue
            expected_id = f"visual-evidence-{sha[:16]}"
            if asset_id != expected_id:
                blockers.append({"asset_id": asset_id, "message": f"Asset id does not match source SHA256 {sha}"})
            if asset_id not in thumbnails:
                blockers.append({"asset_id": asset_id, "message": "Catalog thumbnail mapping is unavailable"})
            bundle_dir = corpus_root / "visual-evidence" / sha[:16]
            if not bundle_dir.is_dir() or not _is_within(bundle_dir, corpus_root / "visual-evidence"):
                blockers.append({"asset_id": asset_id, "message": f"Evidence directory is unavailable or unsafe: {bundle_dir}"})
            role = "delete" if remove_all or position > 0 else "keep"
            if role == "delete":
                if sha in removal_shas:
                    blockers.append({"asset_id": asset_id, "message": f"Source SHA256 is duplicated in the removal plan: {sha}"})
                removal_shas.add(sha)
                if entry.get("evidence_relation") == "exact-duplicate-group" and sha not in occurrence_map:
                    blockers.append({
                        "asset_id": asset_id,
                        "message": f"Exact duplicate source group requires --source-occurrence {sha}=COUNT",
                    })
            described.append({
                "asset_id": asset_id,
                "role": role,
                "source_sha256": sha,
                "canonical_record_ids": list(entry.get("canonical_record_ids") or []),
                "evidence_relation": entry.get("evidence_relation"),
            })
        described_groups.append({"keeper": None if remove_all else group[0], "members": described})

    operation = "remove-evidence-plan" if remove_all else "consolidate-evidence-plan"
    confirmation = (
        f"DELETE-{len(removal_shas)}-VISUAL-EVIDENCE"
        if remove_all
        else f"DELETE-{len(removal_shas)}-DUPLICATE-EVIDENCE"
    )
    return {
        "ok": True,
        "operation": operation,
        "dry_run": True,
        "pack_root": str(validation.root),
        "pack_id": validation.pack_id,
        "current_release": validation.release,
        "groups": described_groups,
        "group_count": len(normalized),
        "delete_count": len(removal_shas),
        "source_file_count_decrement": sum(occurrence_map.get(sha, 1) for sha in removal_shas),
        "blocking_references": blockers,
        "can_apply": not blockers,
        "source_occurrences": occurrence_map,
        "safety": {
            "keepers_are_never_removed": not remove_all,
            "near_matches_are_never_inferred": True,
            "confirmation_required": confirmation,
            "quarantine_outside_pack_required": True,
        },
    }


def build_evidence_removal_plan(
    pack_root: Path,
    asset_ids: Sequence[str],
    *,
    source_occurrences: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    return build_evidence_consolidation_plan(
        pack_root,
        [list(asset_ids)],
        source_occurrences=source_occurrences,
        remove_all=True,
    )


def _remove_soft_relations(document: dict[str, Any], target_id: str) -> bool:
    changed = False
    for record in document.get("records") or []:
        for field in SOFT_REFERENCE_FIELDS:
            value = record.get(field)
            if isinstance(value, list) and target_id in value:
                record[field] = [item for item in value if item != target_id]
                if not record[field]:
                    record.pop(field, None)
                changed = True
    return changed


def _update_manifest_counts(manifest: dict[str, Any]) -> None:
    entries = manifest.get("entries") or []
    manifest["unique_source_count"] = len(entries)
    manifest["evidence_bundle_count"] = len(entries)
    manifest["canonical_evidence_count"] = sum(
        1 for entry in entries if entry.get("disposition") == "canonical-preset-evidence"
    )
    manifest["excluded_noncanonical_count"] = sum(
        1 for entry in entries if entry.get("disposition") == "excluded-noncanonical-artifact"
    )
    _finalize(manifest, "reference_corpus_manifest_sha256")


def _artifact_by_role(bundle: Mapping[str, Any], role: str) -> Mapping[str, Any] | None:
    for artifact in bundle.get("artifacts") or []:
        if artifact.get("role") == role or artifact.get("artifact_id") == role:
            return artifact
    return None


def _quarantine_orphaned_thumbnail(
    pack_root: Path,
    thumbnail_map: Any,
    prefix: str,
    quarantined_evidence_paths: list[Path],
) -> None:
    """Retire the catalog thumbnail of evidence that just lost its last record.

    Dropping the mapping alone is not enough: the WebP stays in the corpus as an
    unreferenced raster, which ``scripts/validate_reference_corpus.py`` refuses
    outright. The file leaves with the mapping, into the same quarantine the
    transaction can restore from.
    """

    if not isinstance(thumbnail_map, dict):
        return
    assets = thumbnail_map.get("assets")
    if not isinstance(assets, dict):
        return
    mapping = assets.pop(f"visual-evidence-{prefix}", None)
    if not isinstance(mapping, Mapping):
        return
    relative = str(mapping.get("path") or "")
    if not relative:
        return
    orphan = (pack_root / relative).resolve()
    if not orphan.is_file() or not _is_within(orphan, pack_root):
        return
    if any(_is_within(orphan, existing) for existing in quarantined_evidence_paths):
        return
    quarantined_evidence_paths.append(orphan)


def _prepare_evidence_changes(
    validation: Any,
    record_id: str,
    evidence_mode: str,
    occurrence_map: Mapping[str, int],
    staged: dict[Path, Any | None],
) -> list[Path]:
    manifest_path = _bound_resource(validation, "reference-corpus-manifest")
    if not manifest_path or not manifest_path.is_file():
        return []
    manifest = copy.deepcopy(_read_json(manifest_path))
    corpus_root = manifest_path.parent
    targets = [
        entry for entry in manifest.get("entries") or []
        if record_id in (entry.get("canonical_record_ids") or [])
    ]
    if not targets:
        return []

    thumbnail_path = _bound_resource(validation, "catalog-thumbnails")
    thumbnail_map = copy.deepcopy(_read_json(thumbnail_path)) if thumbnail_path and thumbnail_path.is_file() else None
    asset_documents: dict[Path, dict[str, Any]] = {}
    for row in validation.records:
        if row.kind != "asset" or row.record.get("asset_type") != "visual-evidence-bundle":
            continue
        path = validation.root / row.source_file
        if path not in asset_documents:
            asset_documents[path] = copy.deepcopy(_read_json(path))

    quarantined_evidence_paths: list[Path] = []
    remove_shas: set[str] = set()
    for entry in targets:
        sha = str(entry["source_sha256"])
        prefix = sha[:16]
        remaining = [value for value in entry.get("canonical_record_ids") or [] if value != record_id]
        if evidence_mode == "purge":
            if remaining:
                raise MaintenanceError(f"Cannot purge shared evidence {sha}")
            remove_shas.add(sha)
            count = occurrence_map.get(sha, 1)
            manifest["source_file_count"] = int(manifest.get("source_file_count") or 0) - count
            if manifest["source_file_count"] < 0:
                raise MaintenanceError("source_file_count would become negative")
            bundle_dir = corpus_root / "visual-evidence" / prefix
            if not bundle_dir.is_dir() or not _is_within(bundle_dir, corpus_root / "visual-evidence"):
                raise MaintenanceError(f"Evidence directory is unavailable or unsafe: {bundle_dir}")
            quarantined_evidence_paths.append(bundle_dir)
            if isinstance(thumbnail_map, dict):
                thumbnail_map.get("assets", {}).pop(f"visual-evidence-{prefix}", None)
            continue

        authority_path = corpus_root / str(entry["visual_authority_ref"]["path"])
        bundle_path = corpus_root / str(entry["visual_evidence_bundle_ref"]["path"])
        authority = copy.deepcopy(_read_json(authority_path))
        bundle = copy.deepcopy(_read_json(bundle_path))
        semantic_artifact = _artifact_by_role(bundle, "semantic-region-map")
        if not semantic_artifact:
            raise MaintenanceError(f"Evidence bundle lacks semantic-region-map: {sha}")
        semantic_path = bundle_path.parent / str(semantic_artifact["path"])
        semantic = copy.deepcopy(_read_json(semantic_path))
        semantic["canonical_record_refs"] = remaining
        _finalize(semantic, "semantic_region_map_sha256")
        semantic_file_sha = _file_sha_for_json(semantic)
        authority["canonical_record_refs"] = remaining
        _finalize(authority, "visual_authority_sha256")
        for artifact in bundle.get("artifacts") or []:
            if artifact.get("role") == "semantic-region-map":
                artifact["sha256"] = semantic_file_sha
        bundle["canonical_record_refs"] = remaining
        bundle["visual_authority_ref"]["sha256"] = authority["visual_authority_sha256"]
        if remaining:
            entry["canonical_record_ids"] = remaining
        else:
            entry["canonical_record_ids"] = []
            entry["disposition"] = "excluded-noncanonical-artifact"
            bundle["disposition"] = "excluded-noncanonical-artifact"
        _finalize(bundle, "visual_evidence_bundle_sha256")
        entry["visual_authority_ref"]["sha256"] = authority["visual_authority_sha256"]
        entry["visual_evidence_bundle_ref"]["sha256"] = bundle["visual_evidence_bundle_sha256"]
        staged[semantic_path] = semantic
        staged[authority_path] = authority
        staged[bundle_path] = bundle

        for asset_path, document in asset_documents.items():
            for asset in list(document.get("records") or []):
                if asset.get("source_sha256") != sha:
                    continue
                if remaining:
                    asset["canonical_record_ids"] = remaining
                    for artifact in asset.get("artifacts") or []:
                        if artifact.get("role") == "semantic-region-map":
                            artifact["sha256"] = semantic_file_sha
                else:
                    document["records"].remove(asset)
                    _quarantine_orphaned_thumbnail(
                        validation.root,
                        thumbnail_map,
                        prefix,
                        quarantined_evidence_paths,
                    )

    if remove_shas:
        manifest["entries"] = [
            entry for entry in manifest.get("entries") or []
            if entry.get("source_sha256") not in remove_shas
        ]
        for document in asset_documents.values():
            document["records"] = [
                asset for asset in document.get("records") or []
                if asset.get("source_sha256") not in remove_shas
            ]

    _update_manifest_counts(manifest)
    staged[manifest_path] = manifest
    if thumbnail_path and thumbnail_map is not None:
        thumbnail_map["assets"] = dict(sorted(thumbnail_map.get("assets", {}).items()))
        if thumbnail_map != _read_json(thumbnail_path):
            staged[thumbnail_path] = thumbnail_map
    for asset_path, document in asset_documents.items():
        if document.get("records") != _read_json(asset_path).get("records"):
            staged[asset_path] = document if document.get("records") else None
    return quarantined_evidence_paths


def _prepare_evidence_consolidation(
    validation: Any,
    plan: Mapping[str, Any],
    staged: dict[Path, Any | None],
) -> list[Path]:
    manifest_path = _bound_resource(validation, "reference-corpus-manifest")
    thumbnail_path = _bound_resource(validation, "catalog-thumbnails")
    if not manifest_path or not manifest_path.is_file():
        raise MaintenanceError("reference-corpus-manifest is unavailable")
    if not thumbnail_path or not thumbnail_path.is_file():
        raise MaintenanceError("catalog-thumbnails is unavailable")

    manifest = copy.deepcopy(_read_json(manifest_path))
    thumbnail_map = copy.deepcopy(_read_json(thumbnail_path))
    occurrence_map = {str(key): int(value) for key, value in (plan.get("source_occurrences") or {}).items()}
    remove_ids: set[str] = set()
    remove_shas: set[str] = set()
    for group in plan.get("groups") or []:
        for member in group.get("members") or []:
            if member.get("role") != "delete":
                continue
            remove_ids.add(str(member["asset_id"]))
            remove_shas.add(str(member["source_sha256"]))
    if len(remove_ids) != int(plan.get("delete_count") or 0) or len(remove_shas) != len(remove_ids):
        raise MaintenanceError("Evidence consolidation plan is internally inconsistent")

    entries_by_sha = {str(entry.get("source_sha256")): entry for entry in manifest.get("entries") or []}
    missing_shas = sorted(remove_shas - set(entries_by_sha))
    if missing_shas:
        raise MaintenanceError("Manifest entries disappeared after planning: " + ", ".join(missing_shas))
    decrement = sum(occurrence_map.get(sha, 1) for sha in remove_shas)
    manifest["source_file_count"] = int(manifest.get("source_file_count") or 0) - decrement
    if manifest["source_file_count"] < 0:
        raise MaintenanceError("source_file_count would become negative")
    manifest["entries"] = [
        entry for entry in manifest.get("entries") or []
        if entry.get("source_sha256") not in remove_shas
    ]
    _update_manifest_counts(manifest)
    staged[manifest_path] = manifest

    thumbnail_assets = thumbnail_map.get("assets")
    if not isinstance(thumbnail_assets, dict):
        raise MaintenanceError("catalog-thumbnails assets mapping is unavailable")
    for asset_id in remove_ids:
        if thumbnail_assets.pop(asset_id, None) is None:
            raise MaintenanceError(f"Catalog thumbnail disappeared after planning: {asset_id}")
    thumbnail_map["assets"] = dict(sorted(thumbnail_assets.items()))
    staged[thumbnail_path] = thumbnail_map

    found_ids: set[str] = set()
    asset_documents: dict[Path, dict[str, Any]] = {}
    for row in validation.records:
        if row.kind != "asset" or row.record.get("asset_type") != "visual-evidence-bundle":
            continue
        path = validation.root / row.source_file
        if path not in asset_documents:
            asset_documents[path] = copy.deepcopy(_read_json(path))
    for path, document in asset_documents.items():
        kept_records = []
        for asset in document.get("records") or []:
            if asset.get("id") in remove_ids:
                found_ids.add(str(asset["id"]))
            else:
                kept_records.append(asset)
        if kept_records != document.get("records"):
            document["records"] = kept_records
            staged[path] = document if kept_records else None
    missing_ids = sorted(remove_ids - found_ids)
    if missing_ids:
        raise MaintenanceError("Asset records disappeared after planning: " + ", ".join(missing_ids))

    corpus_root = manifest_path.parent
    evidence_dirs: list[Path] = []
    for sha in sorted(remove_shas):
        bundle_dir = corpus_root / "visual-evidence" / sha[:16]
        if not bundle_dir.is_dir() or not _is_within(bundle_dir, corpus_root / "visual-evidence"):
            raise MaintenanceError(f"Evidence directory is unavailable or unsafe: {bundle_dir}")
        evidence_dirs.append(bundle_dir)
    return evidence_dirs


def _contract_updates(validation: Any, staged: dict[Path, Any | None]) -> Path | None:
    contract_path = _bound_resource(validation, "release-evaluation-contract")
    manifest_path = _bound_resource(validation, "reference-corpus-manifest")
    if not contract_path or not contract_path.is_file():
        return None
    contract = copy.deepcopy(_read_json(contract_path))
    if manifest_path and manifest_path in staged and staged[manifest_path] is not None:
        manifest = staged[manifest_path]
        corpus = contract.get("reference_corpus")
        if isinstance(corpus, dict):
            corpus["expected_searchable_asset_count"] = manifest["canonical_evidence_count"]
            corpus["expected_source_file_count"] = manifest["source_file_count"]
            corpus["expected_evidence_bundle_count"] = manifest["evidence_bundle_count"]
    staged[contract_path] = contract
    return contract_path


def _quarantine_base(pack_root: Path, requested: Path | None) -> Path:
    base = requested.resolve() if requested else (pack_root.parent / ".preset-quarantine").resolve()
    if _is_within(base, pack_root):
        raise MaintenanceError("Quarantine root must be outside the pack root")
    return base


def _quarantine_path(pack_root: Path, record_id: str, requested: Path | None) -> Path:
    base = _quarantine_base(pack_root, requested)
    token = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return base / pack_root.name / f"{token}-{record_id}-{uuid.uuid4().hex[:8]}"


def _relative_posix(pack_root: Path, paths: Iterable[Path]) -> list[str]:
    root = pack_root.resolve()
    return sorted(path.resolve().relative_to(root).as_posix() for path in paths)


def _write_transaction_record(
    quarantine: Path,
    pack_root: Path,
    *,
    pack_id: str,
    operation: str,
    prior_release: str,
    new_release: str,
    touched: Iterable[Path],
    evidence: Iterable[Path],
) -> Path:
    """Record the transaction in quarantine before the pack is touched.

    The backup copies are already complete when this runs, so a process killed
    by a signal that Python never observes - an out-of-memory ``SIGKILL`` runs
    no ``except``, no ``finally`` and no ``atexit`` handler - still leaves a
    complete prior image next to the record that names it.
    """

    path = quarantine / "transaction.json"
    atomic_write_json(path, {
        "pack_root": str(pack_root.resolve()),
        "pack_id": pack_id,
        "operation": operation,
        "prior_release": prior_release,
        "new_release": new_release,
        "touched": _relative_posix(pack_root, touched),
        "evidence": _relative_posix(pack_root, evidence),
        "state": "started",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    return path


def _set_transaction_state(path: Path, state: str) -> None:
    if not path.is_file():
        return
    record = _read_json(path)
    record["state"] = state
    atomic_write_json(path, record)


def _copy_backup(pack_root: Path, quarantine: Path, path: Path) -> None:
    relative = path.resolve().relative_to(pack_root.resolve())
    destination = quarantine / "files" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def _restore_backups(pack_root: Path, quarantine: Path, touched: Iterable[Path]) -> None:
    for path in touched:
        relative = path.resolve().relative_to(pack_root.resolve())
        backup = quarantine / "files" / relative
        if backup.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, path)
        elif path.exists():
            path.unlink()


def _apply_staged(staged: Mapping[Path, Any | None]) -> None:
    for path, value in sorted(staged.items(), key=lambda row: str(row[0])):
        if value is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write_json(path, value)


def _update_preservation_contract(pack_root: Path, contract_path: Path | None) -> None:
    if not contract_path or not contract_path.is_file():
        return
    from pack_release_gate import authored_metrics

    validation = validate_pack(pack_root, require_lock=False, verify_lock=False)
    errors = [issue.message for issue in validation.issues if issue.severity == "error"]
    if errors:
        raise MaintenanceError("Cannot compute preservation metrics: " + "; ".join(errors))
    metrics = authored_metrics(validation)
    contract = _read_json(contract_path)
    preservation = contract.get("preservation")
    if isinstance(preservation, dict):
        preservation["expected_record_count"] = metrics["record_count"]
        preservation["expected_record_content_sha256"] = metrics["record_content_sha256"]
        preservation["expected_explicit_lexical_tuple_count"] = metrics["explicit_lexical_tuple_count"]
        preservation["expected_explicit_lexical_tuples_sha256"] = metrics["explicit_lexical_tuples_sha256"]
        preservation["expected_search_profile_alias_tuple_count"] = metrics["search_profile_alias_tuple_count"]
        preservation["expected_search_profile_alias_tuples_sha256"] = metrics["search_profile_alias_tuples_sha256"]
        preservation["expected_noncanonical_id_alias_count"] = metrics["noncanonical_id_alias_count"]
        atomic_write_json(contract_path, contract)


def apply_removal(
    plan: Mapping[str, Any],
    *,
    new_release: str,
    confirm: str,
    quarantine_root: Path | None,
) -> dict[str, Any]:
    record_id = str(plan["record"]["id"])
    if confirm != record_id:
        raise MaintenanceError(f"--confirm must equal {record_id!r}")
    if not plan.get("can_apply"):
        raise MaintenanceError("Removal is blocked by inbound references or purge preconditions")
    pack_root = Path(str(plan["pack_root"])).resolve()
    validation = _validated_pack(pack_root)
    try:
        if calver_key(new_release, field="release") <= calver_key(str(validation.release), field="release"):
            raise MaintenanceError("--release must be newer than the current pack release")
    except ValueError as exc:
        raise MaintenanceError(str(exc)) from exc

    locations = _record_locations(validation)
    target = next(row for row in locations if row.record.get("id") == record_id)
    staged: dict[Path, Any | None] = {}
    documents: dict[Path, dict[str, Any]] = {}
    for row in locations:
        if row.path not in documents:
            documents[row.path] = copy.deepcopy(_read_json(row.path))
    target_document = documents[target.path]
    target_document["records"] = [record for record in target_document["records"] if record.get("id") != record_id]
    staged[target.path] = target_document if target_document["records"] else None
    for path, document in documents.items():
        if _remove_soft_relations(document, record_id):
            staged[path] = document if document.get("records") else None

    occurrence_map = {str(key): int(value) for key, value in (plan.get("source_occurrences") or {}).items()}
    quarantined_evidence_paths = _prepare_evidence_changes(
        validation,
        record_id,
        str(plan["evidence_mode"]),
        occurrence_map,
        staged,
    )
    contract_path = _contract_updates(validation, staged)
    pack_path = pack_root / "pack.json"
    pack_data = copy.deepcopy(_read_json(pack_path))
    pack_data["release"] = new_release
    staged[pack_path] = pack_data
    lock_path = pack_root / "pack.lock.json"
    quarantine = _quarantine_path(pack_root, record_id, quarantine_root)
    quarantine.mkdir(parents=True, exist_ok=False)
    touched = set(staged)
    touched.add(lock_path)
    for path in sorted(touched, key=str):
        if path.is_file():
            _copy_backup(pack_root, quarantine, path)
    atomic_write_json(quarantine / "removal-plan.json", dict(plan))
    transaction_path = _write_transaction_record(
        quarantine,
        pack_root,
        pack_id=str(validation.pack_id),
        operation="remove-preset",
        prior_release=str(validation.release),
        new_release=new_release,
        touched=touched,
        evidence=quarantined_evidence_paths,
    )
    moved_evidence: list[tuple[Path, Path]] = []
    try:
        _apply_staged(staged)
        for source in quarantined_evidence_paths:
            relative = source.relative_to(pack_root)
            destination = quarantine / "evidence" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            moved_evidence.append((source, destination))
        _update_preservation_contract(pack_root, contract_path)
        validation_after = validate_pack(pack_root, require_lock=False, verify_lock=False)
        errors = [issue.message for issue in validation_after.issues if issue.severity == "error"]
        if errors:
            raise MaintenanceError("Mutated pack is invalid: " + "; ".join(errors))
        lock = write_lock(pack_root)
        released = validate_pack(pack_root, require_lock=True, verify_lock=True)
        released_errors = [issue.message for issue in released.issues if issue.severity == "error"]
        if released_errors:
            raise MaintenanceError("Released pack is invalid: " + "; ".join(released_errors))
    except BaseException:
        lock_path.unlink(missing_ok=True)
        for source, destination in reversed(moved_evidence):
            source.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                os.replace(destination, source)
        _restore_backups(pack_root, quarantine, touched)
        _set_transaction_state(transaction_path, "rolled-back")
        raise
    _set_transaction_state(transaction_path, "completed")
    return {
        "ok": True,
        "operation": "remove-preset",
        "dry_run": False,
        "record_id": record_id,
        "evidence_mode": plan["evidence_mode"],
        "release": new_release,
        "quarantine_path": str(quarantine),
        "recoverable": True,
        "locked_file_count": len(lock.get("files") or []),
        "next_steps": [
            "run the owning pack release gate",
            "regenerate any catalog that includes this pack",
        ],
    }


def apply_evidence_consolidation(
    plan: Mapping[str, Any],
    *,
    new_release: str,
    confirm: str,
    quarantine_root: Path | None,
) -> dict[str, Any]:
    required_confirmation = str((plan.get("safety") or {}).get("confirmation_required") or "")
    if not required_confirmation or confirm != required_confirmation:
        raise MaintenanceError(f"--confirm must equal {required_confirmation!r}")
    if not plan.get("can_apply"):
        raise MaintenanceError("Evidence mutation is blocked by failed preconditions")
    pack_root = Path(str(plan["pack_root"])).resolve()
    validation = _validated_pack(pack_root)
    try:
        if calver_key(new_release, field="release") <= calver_key(str(validation.release), field="release"):
            raise MaintenanceError("--release must be newer than the current pack release")
    except ValueError as exc:
        raise MaintenanceError(str(exc)) from exc

    staged: dict[Path, Any | None] = {}
    quarantined_evidence_paths = _prepare_evidence_consolidation(validation, plan, staged)
    contract_path = _contract_updates(validation, staged)
    pack_path = pack_root / "pack.json"
    pack_data = copy.deepcopy(_read_json(pack_path))
    pack_data["release"] = new_release
    staged[pack_path] = pack_data
    lock_path = pack_root / "pack.lock.json"
    removing = plan.get("operation") == "remove-evidence-plan"
    quarantine = _quarantine_path(
        pack_root,
        "visual-evidence-removal" if removing else "duplicate-evidence",
        quarantine_root,
    )
    quarantine.mkdir(parents=True, exist_ok=False)
    touched = set(staged)
    touched.add(lock_path)
    for path in sorted(touched, key=str):
        if path.is_file():
            _copy_backup(pack_root, quarantine, path)
    atomic_write_json(
        quarantine / ("evidence-removal-plan.json" if removing else "consolidation-plan.json"),
        dict(plan),
    )
    transaction_path = _write_transaction_record(
        quarantine,
        pack_root,
        pack_id=str(validation.pack_id),
        operation="remove-evidence" if removing else "consolidate-evidence",
        prior_release=str(validation.release),
        new_release=new_release,
        touched=touched,
        evidence=quarantined_evidence_paths,
    )
    moved_evidence: list[tuple[Path, Path]] = []
    try:
        _apply_staged(staged)
        for source in quarantined_evidence_paths:
            relative = source.relative_to(pack_root)
            destination = quarantine / "evidence" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            moved_evidence.append((source, destination))
        _update_preservation_contract(pack_root, contract_path)
        validation_after = validate_pack(pack_root, require_lock=False, verify_lock=False)
        errors = [issue.message for issue in validation_after.issues if issue.severity == "error"]
        if errors:
            raise MaintenanceError("Mutated pack is invalid: " + "; ".join(errors))
        lock = write_lock(pack_root)
        released = validate_pack(pack_root, require_lock=True, verify_lock=True)
        released_errors = [issue.message for issue in released.issues if issue.severity == "error"]
        if released_errors:
            raise MaintenanceError("Released pack is invalid: " + "; ".join(released_errors))
    except BaseException:
        lock_path.unlink(missing_ok=True)
        for source, destination in reversed(moved_evidence):
            source.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                os.replace(destination, source)
        _restore_backups(pack_root, quarantine, touched)
        _set_transaction_state(transaction_path, "rolled-back")
        raise
    _set_transaction_state(transaction_path, "completed")
    return {
        "ok": True,
        "operation": "remove-evidence" if removing else "consolidate-evidence",
        "dry_run": False,
        "group_count": plan["group_count"],
        "deleted_evidence_count": plan["delete_count"],
        "release": new_release,
        "quarantine_path": str(quarantine),
        "recoverable": True,
        "locked_file_count": len(lock.get("files") or []),
        "next_steps": [
            "run the owning pack release gate",
            "regenerate any catalog that includes this pack",
        ],
    }


def _orphan_temporaries(pack_root: Path) -> list[Path]:
    return sorted(
        path for path in pack_root.rglob("*")
        if path.is_file() and ORPHAN_TEMPORARY_RE.fullmatch(path.name)
    )


def _select_transaction(pack_root: Path, base: Path, name: str | None) -> tuple[Path, dict[str, Any]]:
    directory = base / pack_root.name
    if not directory.is_dir():
        raise MaintenanceError(f"No quarantined transaction is available under {directory}")
    rows: list[tuple[Path, dict[str, Any]]] = []
    for child in sorted((row for row in directory.iterdir() if row.is_dir()), key=lambda row: row.name, reverse=True):
        if name and child.name != name:
            continue
        record_path = child / "transaction.json"
        if not record_path.is_file():
            continue
        record = _read_json(record_path)
        if not isinstance(record, dict):
            raise MaintenanceError(f"Transaction record is not an object: {record_path}")
        rows.append((child, record))
    if not rows:
        suffix = f" named {name!r}" if name else ""
        raise MaintenanceError(f"No quarantined transaction record is available under {directory}{suffix}")
    started = [row for row in rows if str(row[1].get("state")) == "started"]
    if not started:
        newest, record = rows[0]
        raise MaintenanceError(
            f"Transaction {newest.name} is {str(record.get('state'))!r}; only an interrupted "
            "transaction left in the 'started' state can be restored"
        )
    return started[0]


def build_restore_plan(
    pack_root: Path,
    *,
    quarantine_root: Path | None = None,
    transaction: str | None = None,
) -> dict[str, Any]:
    """Plan the recovery of a pack whose maintenance transaction never finished.

    This deliberately does not call ``_validated_pack``. The pack this command
    exists for is the one a killed transaction left invalid, so requiring it to
    validate first would refuse every case worth restoring.
    """

    root = pack_root.resolve()
    if not (root / "pack.json").is_file():
        raise MaintenanceError(f"Pack root is unavailable: {root}")
    base = _quarantine_base(root, quarantine_root)
    directory, record = _select_transaction(root, base, transaction)
    recorded_root = Path(str(record.get("pack_root") or "")).resolve()
    if recorded_root != root:
        raise MaintenanceError(f"Quarantined transaction belongs to {recorded_root}, not {root}")
    backups = directory / "files"
    touched = [str(value) for value in record.get("touched") or []]
    evidence = [str(value) for value in record.get("evidence") or []]
    return {
        "ok": True,
        "operation": "restore-pack-plan",
        "dry_run": True,
        "pack_root": str(root),
        "pack_id": record.get("pack_id"),
        "transaction": directory.name,
        "quarantine_path": str(directory),
        "interrupted_operation": record.get("operation"),
        "interrupted_at": record.get("started_at"),
        "prior_release": record.get("prior_release"),
        "abandoned_release": record.get("new_release"),
        "restore_files": [value for value in touched if (backups / value).is_file()],
        "delete_files": [value for value in touched if not (backups / value).is_file()],
        "restore_evidence": [value for value in evidence if (directory / "evidence" / value).exists()],
        "orphan_temporary_files": [path.relative_to(root).as_posix() for path in _orphan_temporaries(root)],
        "can_apply": True,
        "safety": {
            "confirmation_required": record.get("pack_id"),
            "current_pack_is_copied_before_restore": True,
        },
    }


def apply_restore(plan: Mapping[str, Any], *, confirm: str) -> dict[str, Any]:
    required = str(plan.get("pack_id") or "")
    if not required or confirm != required:
        raise MaintenanceError(f"--confirm must equal {required!r}")
    root = Path(str(plan["pack_root"])).resolve()
    directory = Path(str(plan["quarantine_path"])).resolve()
    transaction_path = directory / "transaction.json"
    if not transaction_path.is_file():
        raise MaintenanceError(f"Quarantined transaction record is unavailable: {transaction_path}")

    snapshot = directory.parent / f"{directory.name}-pre-restore-{uuid.uuid4().hex[:8]}"
    shutil.copytree(root, snapshot / "files")

    removed_temporaries = [path.relative_to(root).as_posix() for path in _orphan_temporaries(root)]
    for path in _orphan_temporaries(root):
        path.unlink()

    restored_evidence: list[str] = []
    for relative in plan.get("restore_evidence") or []:
        source = directory / "evidence" / str(relative)
        if not source.exists():
            continue
        destination = root / str(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        restored_evidence.append(str(relative))

    restored_files: list[str] = []
    for relative in plan.get("restore_files") or []:
        backup = directory / "files" / str(relative)
        if not backup.is_file():
            continue
        destination = root / str(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, destination)
        restored_files.append(str(relative))

    deleted_files: list[str] = []
    for relative in plan.get("delete_files") or []:
        destination = root / str(relative)
        if destination.is_file():
            destination.unlink()
            deleted_files.append(str(relative))

    validation = validate_pack(root, require_lock=True, verify_lock=True)
    errors = [issue.message for issue in validation.issues if issue.severity == "error"]
    _set_transaction_state(transaction_path, "restored")
    return {
        "ok": not errors,
        "operation": "restore-pack",
        "dry_run": False,
        "pack_root": str(root),
        "pack_id": required,
        "transaction": directory.name,
        "quarantine_path": str(directory),
        "pre_restore_copy": str(snapshot),
        "release": validation.release,
        "restored_files": restored_files,
        "restored_evidence": restored_evidence,
        "deleted_files": deleted_files,
        "removed_temporary_files": removed_temporaries,
        "validation": {"valid": bool(validation.valid), "errors": errors},
        "recoverable": True,
        "next_steps": [
            "run the owning pack release gate",
            "regenerate any catalog that includes this pack",
        ],
    }


def _flatten_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from _flatten_text(child)
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _flatten_text(child)


def _semantic_tokens(record: Mapping[str, Any]) -> set[str]:
    text_parts: list[str] = []
    for field in SEMANTIC_FIELDS:
        text_parts.extend(_flatten_text(record.get(field)))
    text = " ".join(text_parts).lower().replace("_", "-")
    return {
        token for token in re.findall(r"[a-z0-9]+", text)
        if len(token) > 2 and token not in STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def _semantic_candidates(
    records: Sequence[PackRecord],
    *,
    threshold: float,
    include_vocabulary: bool,
    max_pairs: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    selected = [
        row for row in records
        if row.kind not in {"asset", "model", "recipe"}
        and (include_vocabulary or row.record.get("curation_status") == "curated")
    ]
    signatures = [_semantic_tokens(row.record) for row in selected]
    groups: dict[str, list[str]] = defaultdict(list)
    for row in selected:
        groups[infer_discovery_group(row.kind, row.record)].append(str(row.record.get("id")))
    variant_groups = [
        {"discovery_group": group, "record_ids": sorted(ids), "record_count": len(ids)}
        for group, ids in sorted(groups.items()) if len(ids) > 1
    ]
    candidates: list[dict[str, Any]] = []
    for index, left in enumerate(selected):
        if not signatures[index]:
            continue
        for right_index in range(index + 1, len(selected)):
            right = selected[right_index]
            if left.kind != right.kind:
                continue
            similarity = _jaccard(signatures[index], signatures[right_index])
            if similarity < threshold:
                continue
            left_id = str(left.record.get("id"))
            right_id = str(right.record.get("id"))
            left_group = infer_discovery_group(left.kind, left.record)
            right_group = infer_discovery_group(right.kind, right.record)
            declared_distinct = (
                right_id in (left.record.get("distinct_from") or [])
                or left_id in (right.record.get("distinct_from") or [])
            )
            if left_group == right_group:
                classification = "same-discovery-group"
            elif declared_distinct:
                classification = "declared-distinct"
            else:
                classification = "semantic-overlap"
            candidates.append({
                "left": left_id,
                "right": right_id,
                "kind": left.kind,
                "left_category": left.category,
                "right_category": right.category,
                "similarity": round(similarity, 4),
                "classification": classification,
                "left_discovery_group": left_group,
                "right_discovery_group": right_group,
                "recommended_action": (
                    "retain-as-declared-variants" if classification != "semantic-overlap"
                    else "human-review-for-grouping-or-lossless-merge"
                ),
            })
    candidates.sort(key=lambda row: (-row["similarity"], row["left"], row["right"]))
    truncated = len(candidates) > max_pairs
    return candidates[:max_pairs], variant_groups, truncated


def _visual_dependencies():
    try:
        import numpy as np
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise MaintenanceError(
            "Visual duplicate scanning requires the visual dependency profile: "
            "python scripts/check_dependencies.py --profile visual"
        ) from exc
    return np, Image, ImageOps


def _dct_matrix(np: Any, size: int) -> Any:
    matrix = np.empty((size, size), dtype=np.float64)
    factor = math.pi / (2.0 * size)
    matrix[0, :] = math.sqrt(1.0 / size)
    scale = math.sqrt(2.0 / size)
    for row in range(1, size):
        for column in range(size):
            matrix[row, column] = scale * math.cos((2 * column + 1) * row * factor)
    return matrix


def _bits_hex(bits: Iterable[bool]) -> str:
    value = 0
    count = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
        count += 1
    width = max(1, (count + 3) // 4)
    return f"{value:0{width}x}"


def _image_fingerprint(path: Path, *, identifier: str, scope: str, source_sha256: str | None = None) -> dict[str, Any]:
    np, Image, ImageOps = _visual_dependencies()
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            pixels = image.tobytes()
            normalized = hashlib.sha256(
                width.to_bytes(8, "big") + height.to_bytes(8, "big") + pixels
            ).hexdigest()
            gray = image.resize((32, 32), Image.Resampling.LANCZOS).convert("L")
            array = np.asarray(gray, dtype=np.float64)
            matrix = _dct_matrix(np, 32)
            dct = matrix @ array @ matrix.T
            low = dct[:8, :8].flatten()
            median = float(np.median(low[1:]))
            phash = _bits_hex(value > median for value in low)
            difference = np.asarray(
                image.resize((9, 8), Image.Resampling.LANCZOS).convert("L"),
                dtype=np.int16,
            )
            dhash = _bits_hex((difference[:, 1:] > difference[:, :-1]).flatten())
            structure = np.asarray(
                image.resize((16, 16), Image.Resampling.LANCZOS).convert("L"),
                dtype=np.uint8,
            ).flatten().tolist()
            mean_rgb = [round(float(value), 2) for value in np.asarray(image, dtype=np.float64).mean(axis=(0, 1))]
    except Exception as exc:
        raise MaintenanceError(f"Cannot fingerprint image {path}: {exc}") from exc
    return {
        "id": identifier,
        "scope": scope,
        "path": str(path),
        "raw_sha256": sha256_file(path),
        "source_sha256": source_sha256,
        "normalized_pixel_sha256": normalized,
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 6),
        "phash64": phash,
        "dhash64": dhash,
        "structure16": structure,
        "mean_rgb": mean_rgb,
    }


def _hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _color_distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def _structure_comparison(left: Sequence[int], right: Sequence[int]) -> tuple[float, float]:
    if len(left) != len(right) or not left:
        return 0.0, 255.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    numerator = sum(a * b for a, b in zip(left_centered, right_centered))
    denominator = math.sqrt(
        sum(value * value for value in left_centered)
        * sum(value * value for value in right_centered)
    )
    correlation = numerator / denominator if denominator > 1e-9 else 0.0
    mae = sum(abs(a - b) for a, b in zip(left, right)) / len(left)
    return correlation, mae


def _exact_groups(fingerprints: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in fingerprints:
        groups[str(row[field])].append(row)
    return [
        {
            field: value,
            "members": [
                {"id": row["id"], "scope": row["scope"], "path": row["path"]}
                for row in members
            ],
            "member_count": len(members),
        }
        for value, members in sorted(groups.items()) if len(members) > 1
    ]


def _near_visual_candidates(
    fingerprints: Sequence[Mapping[str, Any]],
    *,
    phash_distance: int,
    max_pairs: int,
    record_lookup: Mapping[str, Mapping[str, Any]],
    asset_records: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    output: list[dict[str, Any]] = []
    for index, left in enumerate(fingerprints):
        for right in fingerprints[index + 1:]:
            if left["scope"] == right["scope"] == "catalog-thumbnail" and left.get("source_sha256") == right.get("source_sha256"):
                continue
            if left["raw_sha256"] == right["raw_sha256"]:
                continue
            p_distance = _hamming(str(left["phash64"]), str(right["phash64"]))
            d_distance = _hamming(str(left["dhash64"]), str(right["dhash64"]))
            aspect_delta = abs(float(left["aspect_ratio"]) - float(right["aspect_ratio"]))
            color_distance = _color_distance(left["mean_rgb"], right["mean_rgb"])
            correlation, gray_mae = _structure_comparison(left["structure16"], right["structure16"])
            same_declared_source = (
                left["scope"] != right["scope"]
                and left.get("source_sha256")
                and left.get("source_sha256") == right.get("source_sha256")
            )
            # A supplied file whose raw digest is already bound to a corpus asset is
            # an expected provenance match, not a near-duplicate candidate.  It is
            # reported separately by duplicate_report().
            if same_declared_source:
                continue
            visually_close = (
                aspect_delta <= 0.08
                and (
                    (p_distance <= phash_distance and d_distance <= 12 and correlation >= 0.88)
                    or (
                        p_distance <= max(2, phash_distance // 2)
                        and d_distance <= 8
                        and correlation >= 0.80
                        and gray_mae <= 38.0
                    )
                )
            )
            if not visually_close:
                continue
            left_asset = asset_records.get(str(left.get("source_sha256") or ""), {})
            right_asset = asset_records.get(str(right.get("source_sha256") or ""), {})
            left_ids = [str(value) for value in left_asset.get("canonical_record_ids") or []]
            right_ids = [str(value) for value in right_asset.get("canonical_record_ids") or []]
            similarities = []
            same_groups = set()
            for left_id in left_ids:
                for right_id in right_ids:
                    left_record = record_lookup.get(left_id)
                    right_record = record_lookup.get(right_id)
                    if not left_record or not right_record:
                        continue
                    similarities.append(_jaccard(_semantic_tokens(left_record), _semantic_tokens(right_record)))
                    left_group = infer_discovery_group("scene", left_record)
                    right_group = infer_discovery_group("scene", right_record)
                    if left_group == right_group:
                        same_groups.add(left_group)
            output.append({
                "left": {"id": left["id"], "scope": left["scope"], "path": left["path"], "canonical_record_ids": left_ids},
                "right": {"id": right["id"], "scope": right["scope"], "path": right["path"], "canonical_record_ids": right_ids},
                "phash_distance": p_distance,
                "dhash_distance": d_distance,
                "aspect_ratio_delta": round(aspect_delta, 6),
                "mean_rgb_distance": round(color_distance, 3),
                "structure_correlation": round(correlation, 4),
                "grayscale_mae": round(gray_mae, 3),
                "semantic_similarity": round(max(similarities), 4) if similarities else None,
                "shared_discovery_groups": sorted(same_groups),
                "classification": "near-visual-candidate",
                "recommended_action": "human-review-never-auto-delete",
            })
    output.sort(key=lambda row: (
        row["phash_distance"], row["dhash_distance"], row["aspect_ratio_delta"],
        row["left"]["id"], row["right"]["id"],
    ))
    truncated = len(output) > max_pairs
    return output[:max_pairs], truncated


def duplicate_report(
    pack_root: Path,
    *,
    source_dir: Path | None,
    semantic_threshold: float,
    phash_distance: int,
    include_vocabulary: bool,
    semantic_only: bool,
    max_pairs: int,
) -> dict[str, Any]:
    validation = _validated_pack(pack_root)
    semantic, variant_groups, semantic_truncated = _semantic_candidates(
        validation.records,
        threshold=semantic_threshold,
        include_vocabulary=include_vocabulary,
        max_pairs=max_pairs,
    )
    report: dict[str, Any] = {
        "ok": True,
        "operation": "duplicate-candidate-report",
        "advisory_only": True,
        "pack_root": str(validation.root),
        "pack_id": validation.pack_id,
        "release": validation.release,
        "thresholds": {
            "semantic_jaccard": semantic_threshold,
            "phash_hamming_distance": phash_distance,
        },
        "variant_groups": variant_groups,
        "semantic_candidates": semantic,
        "semantic_candidates_truncated": semantic_truncated,
        "policy": {
            "exact_content": "reuse one content-addressed source",
            "pixel_identical": "review metadata-only differences",
            "near_visual": "human review required",
            "semantic_overlap": "group variants or prove a lossless merge",
            "automatic_deletion": False,
        },
    }
    if semantic_only:
        report["visual_scan"] = {"executed": False, "reason": "--semantic-only"}
        return report

    fingerprints: list[dict[str, Any]] = []
    thumbnail_path = _bound_resource(validation, "catalog-thumbnails")
    asset_records = {
        str(row.record.get("source_sha256") or ""): row.record
        for row in validation.records
        if row.kind == "asset" and row.record.get("asset_type") == "visual-evidence-bundle"
    }
    if thumbnail_path and thumbnail_path.is_file():
        thumbnail_map = _read_json(thumbnail_path)
        for asset_id, value in sorted((thumbnail_map.get("assets") or {}).items()):
            path = validation.root / str(value.get("path") or "")
            source_sha = str(asset_id).removeprefix("visual-evidence-")
            matching = [sha for sha in asset_records if sha.startswith(source_sha)]
            declared_sha = matching[0] if len(matching) == 1 else None
            fingerprints.append(_image_fingerprint(
                path,
                identifier=str(asset_id),
                scope="catalog-thumbnail",
                source_sha256=declared_sha,
            ))
    if source_dir:
        source_root = source_dir.resolve()
        if not source_root.is_dir():
            raise MaintenanceError(f"Source directory is unavailable: {source_root}")
        for path in sorted(source_root.rglob("*"), key=lambda value: str(value).lower()):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in IMAGE_SUFFIXES:
                fingerprint = _image_fingerprint(
                    path,
                    identifier=path.relative_to(source_root).as_posix(),
                    scope="source-file",
                )
                raw_sha = str(fingerprint["raw_sha256"])
                if raw_sha in asset_records:
                    fingerprint["source_sha256"] = raw_sha
                fingerprints.append(fingerprint)
    exact_bytes = _exact_groups(fingerprints, "raw_sha256")
    exact_pixels = _exact_groups(fingerprints, "normalized_pixel_sha256")
    record_lookup = {str(row.record.get("id")): row.record for row in validation.records}
    near_visual, visual_truncated = _near_visual_candidates(
        fingerprints,
        phash_distance=phash_distance,
        max_pairs=max_pairs,
        record_lookup=record_lookup,
        asset_records=asset_records,
    )
    report["visual_scan"] = {
        "executed": True,
        "fingerprint_count": len(fingerprints),
        "catalog_thumbnail_count": sum(row["scope"] == "catalog-thumbnail" for row in fingerprints),
        "source_file_count": sum(row["scope"] == "source-file" for row in fingerprints),
        "exact_byte_groups": exact_bytes,
        "exact_normalized_pixel_groups": exact_pixels,
        "source_corpus_matches": [
            {
                "source_file": row["id"],
                "source_sha256": row["source_sha256"],
                "canonical_record_ids": asset_records.get(str(row["source_sha256"]), {}).get("canonical_record_ids") or [],
            }
            for row in fingerprints
            if row["scope"] == "source-file" and row.get("source_sha256")
        ],
        "near_visual_candidates": near_visual,
        "near_visual_candidates_truncated": visual_truncated,
        "fingerprints": fingerprints,
    }
    return report


def _write_report(path: Path | None, value: Mapping[str, Any]) -> None:
    if path:
        atomic_write_json(path.resolve(), dict(value))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit duplicates and safely remove pack-owned presets or Visual Evidence"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    duplicates = sub.add_parser("duplicates", help="Report exact, visual, semantic, and variant candidates")
    duplicates.add_argument("pack_root", type=Path)
    duplicates.add_argument("--source-dir", type=Path)
    duplicates.add_argument("--semantic-threshold", type=float, default=0.72)
    duplicates.add_argument("--phash-distance", type=int, default=8)
    duplicates.add_argument("--include-vocabulary", action="store_true")
    duplicates.add_argument("--semantic-only", action="store_true")
    duplicates.add_argument("--max-pairs", type=int, default=500)
    duplicates.add_argument("--report-out", type=Path)

    remove = sub.add_parser("remove", help="Plan or apply one record removal")
    remove.add_argument("pack_root", type=Path)
    remove.add_argument("record_id")
    remove.add_argument("--evidence", choices=("keep", "purge"), default="keep")
    remove.add_argument("--source-occurrence", action="append", default=[], metavar="SHA256=COUNT")
    remove.add_argument("--apply", action="store_true")
    remove.add_argument("--confirm")
    remove.add_argument("--release")
    remove.add_argument("--quarantine-root", type=Path)
    remove.add_argument("--report-out", type=Path)

    consolidate = sub.add_parser(
        "consolidate-evidence",
        help="Plan or apply explicit Visual Evidence groups, keeping the first asset in each group",
    )
    consolidate.add_argument("pack_root", type=Path)
    consolidate.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="KEEP_ID,DUPLICATE_ID[,DUPLICATE_ID...]",
    )
    consolidate.add_argument("--source-occurrence", action="append", default=[], metavar="SHA256=COUNT")
    consolidate.add_argument("--apply", action="store_true")
    consolidate.add_argument("--confirm")
    consolidate.add_argument("--release")
    consolidate.add_argument("--quarantine-root", type=Path)
    consolidate.add_argument("--report-out", type=Path)

    remove_evidence = sub.add_parser(
        "remove-evidence",
        help="Plan or apply explicit Visual Evidence removal without deleting linked presets",
    )
    remove_evidence.add_argument("pack_root", type=Path)
    remove_evidence.add_argument("asset_ids", nargs="+")
    remove_evidence.add_argument("--source-occurrence", action="append", default=[], metavar="SHA256=COUNT")
    remove_evidence.add_argument("--apply", action="store_true")
    remove_evidence.add_argument("--confirm")
    remove_evidence.add_argument("--release")
    remove_evidence.add_argument("--quarantine-root", type=Path)
    remove_evidence.add_argument("--report-out", type=Path)

    restore = sub.add_parser(
        "restore",
        help="Restore a pack from a quarantined transaction that was killed before it finished",
    )
    restore.add_argument("pack_root", type=Path)
    restore.add_argument("--quarantine-root", type=Path)
    restore.add_argument("--transaction", metavar="QUARANTINE_DIRECTORY_NAME")
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--confirm")
    restore.add_argument("--report-out", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "duplicates":
            if not 0.0 < args.semantic_threshold <= 1.0:
                raise MaintenanceError("--semantic-threshold must be in (0, 1]")
            if not 0 <= args.phash_distance <= 64:
                raise MaintenanceError("--phash-distance must be between 0 and 64")
            if args.max_pairs < 1:
                raise MaintenanceError("--max-pairs must be positive")
            report = duplicate_report(
                args.pack_root,
                source_dir=args.source_dir,
                semantic_threshold=args.semantic_threshold,
                phash_distance=args.phash_distance,
                include_vocabulary=args.include_vocabulary,
                semantic_only=args.semantic_only,
                max_pairs=args.max_pairs,
            )
        elif args.command == "remove":
            occurrence_map = _parse_occurrences(args.source_occurrence)
            plan = build_removal_plan(
                args.pack_root,
                args.record_id,
                evidence_mode=args.evidence,
                source_occurrences=occurrence_map,
            )
            if args.apply:
                if not args.release:
                    raise MaintenanceError("--apply requires --release")
                if not args.confirm:
                    raise MaintenanceError("--apply requires --confirm RECORD_ID")
                report = apply_removal(
                    plan,
                    new_release=args.release,
                    confirm=args.confirm,
                    quarantine_root=args.quarantine_root,
                )
            else:
                report = plan
        elif args.command == "consolidate-evidence":
            occurrence_map = _parse_occurrences(args.source_occurrence)
            groups = _parse_evidence_groups(args.group)
            plan = build_evidence_consolidation_plan(
                args.pack_root,
                groups,
                source_occurrences=occurrence_map,
            )
            if args.apply:
                if not args.release:
                    raise MaintenanceError("--apply requires --release")
                if not args.confirm:
                    raise MaintenanceError("--apply requires --confirm CONFIRMATION")
                report = apply_evidence_consolidation(
                    plan,
                    new_release=args.release,
                    confirm=args.confirm,
                    quarantine_root=args.quarantine_root,
                )
            else:
                report = plan
        elif args.command == "restore":
            plan = build_restore_plan(
                args.pack_root,
                quarantine_root=args.quarantine_root,
                transaction=args.transaction,
            )
            if args.apply:
                if not args.confirm:
                    raise MaintenanceError("--apply requires --confirm PACK_ID")
                report = apply_restore(plan, confirm=args.confirm)
            else:
                report = plan
        else:
            occurrence_map = _parse_occurrences(args.source_occurrence)
            plan = build_evidence_removal_plan(
                args.pack_root,
                args.asset_ids,
                source_occurrences=occurrence_map,
            )
            if args.apply:
                if not args.release:
                    raise MaintenanceError("--apply requires --release")
                if not args.confirm:
                    raise MaintenanceError("--apply requires --confirm CONFIRMATION")
                report = apply_evidence_consolidation(
                    plan,
                    new_release=args.release,
                    confirm=args.confirm,
                    quarantine_root=args.quarantine_root,
                )
            else:
                report = plan
        _write_report(args.report_out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1
    except (MaintenanceError, PackError, OSError, ValueError) as exc:
        report = {"ok": False, "operation": args.command, "error": str(exc)}
        if getattr(args, "report_out", None):
            _write_report(args.report_out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
