"""Asset lookup, artifact resolution, and provenance indexing."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from pack_cache import RuntimePackEntry

import catalog_retrieval.runtime as runtime
from catalog_retrieval.runtime import (
    Entry,
    _entry_from_runtime,
    _lru_get,
    _lru_put,
    load_pack_catalog,
)

_CONCRETE_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _resolve_owned_pack_path(entry: Entry, declared_path: Any) -> tuple[str, Path]:
    """Resolve one declared resource strictly inside its owning pack root."""
    relative = str(declared_path or "").strip().replace("\\", "/")
    candidate = Path(relative)
    if (
        not relative
        or candidate.is_absolute()
        or candidate.drive
        or relative.startswith("/")
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError(
            f"Asset {entry.record.get('id')!r} declares an invalid pack-relative path: "
            f"{declared_path!r}"
        )
    root = entry.source_root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Asset {entry.record.get('id')!r} resource escapes its owning pack: "
            f"{declared_path!r}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(
            f"Asset {entry.record.get('id')!r} resource is unavailable in its owning "
            f"pack: {relative}"
        )
    return relative, resolved


def resolve_asset_resources(entry: Entry) -> list[dict[str, Any]]:
    """Return declared artifact resources after ownership and shape validation.

    Cache construction already validates the released pack and its lock. This
    lookup deliberately does not rehash resources on every read; it validates
    the concrete SHA-256 declaration and resolves the path inside the exact pack
    that owns the asset record.
    """
    if entry.kind != "asset":
        raise ValueError(f"Record {entry.record.get('id')!r} is not an asset record")
    primary_resource = str(entry.record.get("primary_resource") or "").replace("\\", "/")
    declared_resource_refs = {
        str(value).strip().replace("\\", "/")
        for value in entry.record.get("resource_refs") or []
        if str(value).strip()
    }
    rows: list[dict[str, Any]] = []
    primary_count = 0
    for position, raw in enumerate(entry.record.get("artifacts") or []):
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifacts[{position}] is not an object"
            )
        artifact_id = str(raw.get("artifact_id") or "").strip()
        role = str(raw.get("role") or "").strip()
        media_type = str(raw.get("media_type") or "").strip()
        declared_sha256 = str(raw.get("sha256") or "").strip().lower()
        if not artifact_id:
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifacts[{position}] has no artifact_id"
            )
        if not role:
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifact {artifact_id!r} has no role"
            )
        if not media_type:
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifact {artifact_id!r} has no media_type"
            )
        if not _CONCRETE_SHA256.fullmatch(declared_sha256):
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifact {artifact_id!r} must declare "
                "one concrete SHA-256"
            )
        relative, resolved = _resolve_owned_pack_path(entry, raw.get("path"))
        if relative not in declared_resource_refs:
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifact {artifact_id!r} is not "
                "declared in resource_refs"
            )
        primary = relative == primary_resource
        primary_count += int(primary)
        rows.append({
            "source_pack": entry.source_pack,
            "pack_relative_path": relative,
            "resolved_path": str(resolved),
            "primary": primary,
            "artifact_id": artifact_id,
            "role": role,
            "media_type": media_type,
            "sha256": declared_sha256,
        })
    if primary_count != 1:
        raise ValueError(
            f"Asset {entry.record.get('id')!r} must resolve exactly one primary artifact; "
            f"resolved {primary_count}"
        )
    return rows


def _asset_detail(entry: Entry) -> dict[str, Any]:
    catalog = load_pack_catalog()
    asset_id = str(entry.record.get("id") or "")
    cache_key = (catalog.fingerprint, asset_id)
    cached = _lru_get(runtime._ASSET_DETAIL_CACHE, cache_key)
    if cached is not None:
        return cached
    detail = {
        "kind": "asset",
        "asset_id": asset_id,
        "source_pack": entry.source_pack,
        "source_file": entry.source_file,
        "record": dict(entry.record),
        "resources": resolve_asset_resources(entry),
    }
    _lru_put(runtime._ASSET_DETAIL_CACHE, cache_key, detail, runtime._MAX_RUNTIME_PROFILE_CACHE)
    return detail


def linked_asset_activation(record_id: Any) -> dict[str, Any]:
    """Return only the IDs needed to decide whether asset lookup is required."""
    linked = load_pack_catalog().assets_by_canonical_record.get(str(record_id), ())
    asset_ids = [
        str(packed.record.get("id") or "")
        for packed in linked
        if str(packed.record.get("id") or "")
    ]
    return {
        "asset_count": len(asset_ids),
        "asset_ids": asset_ids,
    }


def _asset_summary(entry: Entry) -> dict[str, Any]:
    """Return technical activation metadata without records or resolved paths."""
    artifacts: list[dict[str, str]] = []
    for position, raw in enumerate(entry.record.get("artifacts") or []):
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifacts[{position}] is not an object"
            )
        artifact_id = str(raw.get("artifact_id") or "").strip()
        role = str(raw.get("role") or "").strip()
        media_type = str(raw.get("media_type") or "").strip()
        if not artifact_id or not role or not media_type:
            raise ValueError(
                f"Asset {entry.record.get('id')!r} artifacts[{position}] must declare "
                "artifact_id, role, and media_type"
            )
        artifacts.append({
            "artifact_id": artifact_id,
            "role": role,
            "media_type": media_type,
        })
    return {
        "asset_id": str(entry.record.get("id") or ""),
        "artifacts": artifacts,
    }


def asset_lookup(lookup_id: str, *, summary: bool = False) -> dict[str, Any]:
    """Discover one asset or all assets linked to a canonical record.

    The result describes catalog records and their declared resources. It does
    not assign intended influence, authority, or precedence and therefore is
    not a generation-ready reference plan.
    """
    catalog = load_pack_catalog()
    requested = str(lookup_id)
    direct: RuntimePackEntry | None = None
    canonical_exists = False
    for packed in catalog.entries:
        if str(packed.record.get("id")) != requested:
            continue
        if packed.kind == "asset":
            direct = packed
        else:
            canonical_exists = True
        break
    if direct is not None:
        entries = [_entry_from_runtime(direct)]
        mode = "asset-id"
    elif canonical_exists:
        entries = [
            _entry_from_runtime(packed)
            for packed in catalog.assets_by_canonical_record.get(requested, ())
        ]
        mode = "canonical-record-id"
    else:
        raise SystemExit(f"Unknown asset or canonical record id: {requested}")
    assets = [
        _asset_summary(entry) if summary else _asset_detail(entry)
        for entry in entries
    ]
    return {
        "lookup_id": requested,
        "lookup_mode": mode,
        "asset_count": len(assets),
        "assets": assets,
    }


def active_pack_artifact_sources() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Index active pack-owned image artifacts for provenance validation."""

    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    for packed in load_pack_catalog().entries:
        if packed.kind != "asset":
            continue
        entry = _entry_from_runtime(packed)
        asset_id = str(entry.record.get("id") or "")
        for resource in resolve_asset_resources(entry):
            media_type = str(resource["media_type"])
            if not media_type.startswith("image/"):
                continue
            artifact_id = str(resource["artifact_id"])
            key = (entry.source_pack, asset_id, artifact_id)
            if key in sources:
                raise ValueError(
                    "Active catalog contains a duplicate pack asset artifact: "
                    f"{entry.source_pack}/{asset_id}/{artifact_id}"
                )
            sources[key] = {
                "kind": "pack-artifact",
                "pack_id": entry.source_pack,
                "asset_id": asset_id,
                "artifact_id": artifact_id,
                "resolved_path": str(resource["resolved_path"]),
                "media_type": media_type,
                "sha256": str(resource["sha256"]),
            }
    return sources
