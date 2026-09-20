#!/usr/bin/env python3
"""Validate a Reference Use Plan against the active canonical catalog.

The structural Reference Use Plan contract intentionally cannot prove that a
record or asset is still active.  This module supplies that catalog-dependent
boundary without depending on either the runtime planner or the reference
preparer, so every consumer can apply the same active-record semantics and
record-to-artifact linkage rules.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from catalog_cli import asset_lookup, load_entries
from reference_contract import (
    normalize_selected_records,
    require_record_semantic_support,
    validate_reference_use_plan_contract,
)


def _pack_source(
    asset: Mapping[str, Any],
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the only canonical source metadata for one active artifact."""

    return {
        "kind": "pack-artifact",
        "pack_id": str(asset["source_pack"]),
        "asset_id": str(asset["asset_id"]),
        "artifact_id": str(resource["artifact_id"]),
        "resolved_path": str(resource["resolved_path"]),
        "media_type": str(resource["media_type"]),
        "sha256": str(resource["sha256"]),
    }


def active_canonical_records() -> dict[str, Any]:
    """Return the unique active non-asset canonical-record index."""

    records: dict[str, Any] = {}
    for entry in load_entries():
        if entry.kind == "asset":
            continue
        record_id = str(entry.record.get("id") or "")
        if not record_id:
            continue
        if record_id in records:
            raise ValueError(
                f"active catalog contains duplicate non-asset record id {record_id!r}"
            )
        records[record_id] = entry
    return records


def validate_active_reference_use_plan(plan: Any) -> dict[str, Any]:
    """Validate structural truth, active semantics, and exact asset linkage.

    Active catalog entries are the authority.  A signed plan remains invalid
    when it names an inactive record, assigns an influence unsupported by that
    record's current semantic content, or rewrites any record/asset/resource
    relationship or source metadata.
    """

    contract = validate_reference_use_plan_contract(plan)
    errors = list(contract.get("errors", []))
    if not isinstance(plan, Mapping):
        return {
            "ok": False,
            "errors": list(dict.fromkeys(errors)),
            "reference_count": 0,
        }

    try:
        selected_records = normalize_selected_records(plan.get("selected_records"))
    except ValueError as exc:
        selected_records = []
        errors.append(str(exc))

    try:
        active_records = active_canonical_records()
    except (ValueError, OSError, RuntimeError, SystemExit) as exc:
        errors.append(f"active canonical catalog is unavailable: {exc}")
        active_records = {}

    for index, selected in enumerate(selected_records):
        record_id = selected["record_id"]
        entry = active_records.get(record_id)
        if entry is None:
            errors.append(
                f"selected_records[{index}] identifies an unknown, inactive, "
                "or non-canonical asset record"
            )
            continue
        try:
            require_record_semantic_support(
                entry.record,
                selected["intended_influence"],
                record_kind=entry.kind,
                record_id=record_id,
            )
        except ValueError as exc:
            errors.append(f"selected_records[{index}] semantic scope is invalid: {exc}")

    items = plan.get("reference_items")
    if not isinstance(items, list):
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        field = f"reference_items[{index}]"
        record_id = str(item.get("canonical_record_id") or "")
        source = item.get("source")
        if not isinstance(source, Mapping):
            errors.append(f"{field}.source must be an object")
            continue
        if record_id not in active_records:
            errors.append(
                f"{field} does not identify an active non-asset canonical record"
            )
            continue
        try:
            lookup = asset_lookup(record_id, summary=False)
            assets = lookup.get("assets")
            if not isinstance(assets, list):
                raise ValueError(
                    f"asset lookup returned no complete asset list for {record_id!r}"
                )
        except (ValueError, OSError, RuntimeError, SystemExit) as exc:
            errors.append(f"{field} active asset lookup failed: {exc}")
            continue
        matching_assets = [
            asset
            for asset in assets
            if str(asset.get("asset_id") or "") == str(item.get("asset_id") or "")
            and str(asset.get("source_pack") or "") == str(source.get("pack_id") or "")
        ]
        if len(matching_assets) != 1:
            errors.append(
                f"{field} does not identify exactly one active asset linked to "
                "its canonical record"
            )
            continue
        asset = matching_assets[0]
        declared_scope = (asset.get("record") or {}).get("adoption_scope")
        if item.get("technical_role") == "adopted-reference":
            if not isinstance(declared_scope, Mapping) or declared_scope.get("intended_influence") != item.get("intended_influence"):
                errors.append(f"{field} exceeds its explicitly approved adoption scope")
                continue
        resources = [
            resource
            for resource in asset.get("resources", [])
            if isinstance(resource, Mapping)
            and str(resource.get("artifact_id") or "")
            == str(item.get("artifact_id") or "")
            and str(resource.get("role") or "")
            == str(item.get("technical_role") or "")
        ]
        if len(resources) != 1:
            errors.append(
                f"{field} artifact and technical role do not identify exactly "
                "one active resource"
            )
            continue
        if _pack_source(asset, resources[0]) != dict(source):
            errors.append(
                f"{field}.source differs from its active record-to-artifact link"
            )

    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "reference_count": len(items),
    }


__all__ = [
    "active_canonical_records",
    "validate_active_reference_use_plan",
]
