#!/usr/bin/env python3
"""Build, validate, and transactionally materialize visual-reference plans."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from catalog_cli import asset_lookup, configure_pack_runtime
from check_dependencies import check_profile
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from model_contract import model_reference_limit
from prepare_generation_references import (
    build_prepared_reference_set,
    canonical_reference_preamble,
    prepare_reference_use_plan_rows,
    resolve_model_record,
    sha256_file,
    validate_committed_source,
    validate_prepared_reference_set,
    write_json_atomic,
)
from reference_contract import (
    MODEL_TRANSPORT_MODES,
    PROMPT_TRANSPORT_MODES,
    TECHNICAL_CAPABILITIES,
    TRANSPORT_MODES,
    build_reference_item,
    build_surface_lighting_plan,
    finalize_reference_use_plan,
    normalize_selected_records,
    require_record_semantic_support,
    source_lighting_evidence_roles,
    technical_roles_for,
)
from reference_plan_cli_contract import (
    plan_cli_example,
    surface_argument_help,
    surface_lighting_schema,
)
from reference_active_validation import (
    active_canonical_records,
    validate_active_reference_use_plan,
)
from state_protocol import validate_artifact


ROOT = Path(__file__).resolve().parents[1]
SVG_MEDIA_TYPE = "image/svg+xml"

RELATION_PRIORITY = {
    "previously-reviewed-evidence": 0,
    "exact-duplicate-group": 1,
    "existing-family-variant": 2,
}


class VisualDependencyPreflightError(RuntimeError):
    """Structured stop condition for a required model-facing Visual profile."""

    def __init__(self, report: Mapping[str, Any]):
        self.report = copy.deepcopy(dict(report))
        missing = self.report.get("missing_packages") or []
        incompatible = self.report.get("incompatible_packages") or []
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(str(value) for value in missing))
        if incompatible:
            detail.append(
                "incompatible: " + ", ".join(str(value) for value in incompatible)
            )
        suffix = f" ({'; '.join(detail)})" if detail else ""
        super().__init__(
            "Visual dependency preflight failed before model-facing reference preparation"
            + suffix
            + f". Check with `{self.report['check_command']}`; install with "
            + f"`{self.report['install_command']}` only when environment changes are authorized."
        )


def visual_dependency_requirement(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Describe whether execution needs the Visual dependency profile."""

    items = list(plan.get("reference_items") or [])
    mode = str(plan.get("transport_mode") or "")
    if mode not in MODEL_TRANSPORT_MODES or not items:
        return {"required": False, "profile": None, "reasons": []}
    reasons: list[str] = []
    if any(
        isinstance(item, Mapping)
        and isinstance(item.get("source"), Mapping)
        and item["source"].get("media_type") == SVG_MEDIA_TYPE
        for item in items
    ):
        reasons.append("selected SVG references require deterministic PNG rasterization")
    if mode == "single-board":
        reasons.append("single-board transport requires raster composition")
    return {
        "required": bool(reasons),
        "profile": "visual" if reasons else None,
        "reasons": reasons,
    }


def preflight_visual_dependencies(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Check the Visual profile exactly when model-facing preparation needs it."""

    requirement = visual_dependency_requirement(plan)
    if not requirement["required"]:
        return requirement
    dependency_report = check_profile("visual")
    report = {**requirement, **dependency_report}
    if not report["ok"]:
        raise VisualDependencyPreflightError(report)
    return report


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _seed_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _asset_sort_key(detail: Mapping[str, Any]) -> tuple[int, str, str]:
    record = detail.get("record") if isinstance(detail.get("record"), Mapping) else {}
    relation = str(record.get("evidence_relation") or "")
    return (
        RELATION_PRIORITY.get(relation, 99),
        str(detail.get("source_pack") or ""),
        str(detail.get("asset_id") or ""),
    )


def _pack_source(asset: Mapping[str, Any], resource: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "pack-artifact",
        "pack_id": str(asset["source_pack"]),
        "asset_id": str(asset["asset_id"]),
        "artifact_id": str(resource["artifact_id"]),
        "resolved_path": str(resource["resolved_path"]),
        "media_type": str(resource["media_type"]),
        "sha256": str(resource["sha256"]),
    }


def _active_records() -> dict[str, Any]:
    return active_canonical_records()


def _active_record_ids() -> set[str]:
    return set(_active_records())


def build_reference_use_plan(
    selected_records: Any,
    *,
    transport_mode: str,
    source_lighting_mode: str,
    target_model: str | None = None,
    max_assets_per_record: int = 1,
    max_references: int | None = None,
    include_technical_roles: Sequence[str] | None = None,
    light_sources: Sequence[Mapping[str, Any]] = (),
    material_responses: Sequence[Mapping[str, Any]] = (),
    unresolved_decisions: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one deterministic plan from explicit record/use pairs."""

    selected = normalize_selected_records(selected_records)
    if transport_mode not in TRANSPORT_MODES:
        raise ValueError(f"transport_mode must be one of {sorted(TRANSPORT_MODES)}")
    if transport_mode in MODEL_TRANSPORT_MODES and not target_model:
        raise ValueError("model-facing transport requires target_model")
    if transport_mode in PROMPT_TRANSPORT_MODES and target_model is not None:
        raise ValueError("prompt transport requires target_model=null")
    if not isinstance(max_assets_per_record, int) or isinstance(max_assets_per_record, bool) or max_assets_per_record < 1:
        raise ValueError("max_assets_per_record must be a positive integer")
    if max_references is not None and (
        not isinstance(max_references, int)
        or isinstance(max_references, bool)
        or max_references < 1
    ):
        raise ValueError("max_references must be a positive integer when declared")
    effective_max_references = max_references
    if transport_mode in MODEL_TRANSPORT_MODES:
        model_id, model_record = resolve_model_record(str(target_model))
        if model_record.get("operation_kind") == "upscale":
            raise ValueError(
                f"target model {model_id!r} is an upscaler and cannot receive generation references"
            )
        declared_limit = model_reference_limit(model_record)
        if declared_limit is not None and transport_mode == "multi-image":
            effective_max_references = (
                declared_limit
                if max_references is None
                else min(max_references, declared_limit)
            )
    requested_roles = (
        None
        if include_technical_roles is None
        else set(str(value) for value in include_technical_roles)
    )
    if requested_roles is not None:
        unknown = sorted(requested_roles - set(TECHNICAL_CAPABILITIES))
        if unknown:
            raise ValueError(f"unknown technical roles: {unknown}")

    active_records = _active_records()
    missing_ids = sorted({row["record_id"] for row in selected} - set(active_records))
    if missing_ids:
        raise ValueError(f"unknown or inactive canonical record IDs: {missing_ids}")

    for record_use in selected:
        entry = active_records[record_use["record_id"]]
        require_record_semantic_support(
            entry.record,
            record_use["intended_influence"],
            record_kind=entry.kind,
            record_id=record_use["record_id"],
        )

    items: list[dict[str, Any]] = []
    unresolved_uses: list[str] = []
    for record_use in selected:
        record_id = record_use["record_id"]
        influence = record_use["intended_influence"]
        desired_roles = list(technical_roles_for(influence))
        if requested_roles is not None:
            desired_roles = [role for role in desired_roles if role in requested_roles]
        lookup = asset_lookup(record_id, summary=False)
        assets = lookup.get("assets")
        if not isinstance(assets, list):
            raise ValueError(
                f"asset lookup returned no complete asset list for canonical record {record_id!r}"
            )
        assets = sorted(assets, key=_asset_sort_key)
        selected_for_use = 0
        for asset in assets[:max_assets_per_record]:
            declared_scope = (asset.get("record") or {}).get("adoption_scope")
            if isinstance(declared_scope, Mapping) and declared_scope.get("intended_influence") != influence:
                raise ValueError(f"asset {asset.get('asset_id')!r} does not authorize adoption influence {influence!r}")
            resources = {
                str(resource.get("role") or ""): resource
                for resource in asset.get("resources", [])
                if isinstance(resource, Mapping)
                and str(resource.get("media_type") or "").startswith("image/")
            }
            for technical_role in desired_roles:
                resource = resources.get(technical_role)
                if resource is None:
                    continue
                item = build_reference_item(
                    precedence=len(items),
                    canonical_record_id=record_id,
                    intended_influence=influence,
                    asset_id=str(asset["asset_id"]),
                    artifact_id=str(resource["artifact_id"]),
                    technical_role=technical_role,
                    source=_pack_source(asset, resource),
                )
                items.append(item)
                selected_for_use += 1
                if effective_max_references is not None and len(items) > effective_max_references:
                    raise ValueError(
                        "automatic visual-reference activation exceeds the effective model/reference limit; "
                        "narrow the selected records or technical roles"
                    )
        if selected_for_use == 0:
            unresolved_uses.append(f"{record_id}={influence}")

    if unresolved_uses and items:
        raise ValueError(
            "some selected record uses have no suitable active artifact: "
            + ", ".join(unresolved_uses)
        )
    evidence_roles = source_lighting_evidence_roles(items)
    surface_plan = build_surface_lighting_plan(
        source_lighting_mode=source_lighting_mode,
        evidence_roles=evidence_roles,
        light_sources=light_sources,
        material_responses=material_responses,
        unresolved_decisions=unresolved_decisions,
    )
    zero_reason = None
    if not items:
        zero_reason = {
            "code": "no-suitable-active-asset",
            "record_ids": list(dict.fromkeys(row["record_id"] for row in selected)),
            "detail": (
                "No suitable active visual-reference artifact exists for the selected "
                "record uses: " + ", ".join(unresolved_uses)
            ),
        }
    seed = {
        "selected_records": selected,
        "transport_mode": transport_mode,
        "target_model": target_model,
        "items": [
            (
                item["canonical_record_id"],
                item["intended_influence"],
                item["asset_id"],
                item["artifact_id"],
            )
            for item in items
        ],
        "surface_lighting_plan_sha256": surface_plan["surface_lighting_plan_sha256"],
        "zero_reference_reason": zero_reason,
    }
    return finalize_reference_use_plan(
        {
            "artifact_type": "reference-use-plan",
            "plan_id": _seed_id("RUP", seed),
            "target_model": target_model,
            "transport_mode": transport_mode,
            "selected_records": selected,
            "reference_items": items,
            "surface_lighting_plan": surface_plan,
            "surface_lighting_plan_sha256": surface_plan[
                "surface_lighting_plan_sha256"
            ],
            "zero_reference_reason": zero_reason,
            "reference_use_plan_sha256": "0" * 64,
        }
    )


def validate_reference_use_plan(plan: Any) -> dict[str, Any]:
    """Validate plan shape, hashes, authority, active pack state, and record links."""

    report = validate_active_reference_use_plan(plan)
    errors = list(report.get("errors", []))
    if not isinstance(plan, Mapping):
        return {"ok": False, "errors": errors, "reference_count": 0}
    for index, item in enumerate(plan.get("reference_items") or []):
        if isinstance(item, Mapping):
            try:
                validate_committed_source(
                    item.get("source"), f"reference_items[{index}].source"
                )
            except (ValueError, OSError, RuntimeError, SystemExit) as exc:
                errors.append(
                    f"reference_items[{index}] committed source validation failed: {exc}"
                )
    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "reference_count": len(plan.get("reference_items") or []),
    }


def _validate_state_eligibility(
    plan: Mapping[str, Any],
    reference_selection: Any | None,
) -> dict[str, Any] | None:
    if reference_selection is None:
        return None
    if not isinstance(reference_selection, Mapping):
        raise ValueError("reference_selection must be an object")
    report = validate_artifact(dict(reference_selection))
    if not report.get("ok"):
        raise ValueError("invalid reference-selection artifact: " + "; ".join(report["errors"]))
    if reference_selection.get("unresolved_requirements"):
        raise ValueError("reference_selection has unresolved state requirements")
    available: dict[str, list[Mapping[str, Any]]] = {}
    for selected in reference_selection.get("selected_references") or []:
        if isinstance(selected, Mapping):
            available.setdefault(canonical_json(selected.get("source")), []).append(selected)
    for index, item in enumerate(plan.get("reference_items") or []):
        matches = available.get(canonical_json(item.get("source"))) or []
        if not matches:
            raise ValueError(
                f"reference_items[{index}] is not eligible in reference_selection"
            )
        influence = item.get("intended_influence")
        compatible_index = next(
            (
                candidate_index
                for candidate_index, selected in enumerate(matches)
                if influence in selected.get("intended_influence", [])
            ),
            None,
        )
        if compatible_index is None:
            raise ValueError(
                f"reference_items[{index}] intended influence is state-ineligible"
            )
        matches.pop(compatible_index)
    return copy.deepcopy(dict(reference_selection))


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_." else "-"
        for character in value
    ).strip("-.") or "reference"


def _copy_exact_bytes(
    source_path: Path,
    destination_path: Path,
    *,
    expected_sha256: str | None = None,
) -> str:
    """Copy bytes without inheriting source mode and verify the delivered hash."""

    source = Path(source_path)
    destination = Path(destination_path)
    source_hash = sha256_file(source)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ValueError(f"source hash changed before copy: {source}")
    shutil.copyfile(source, destination)
    os.chmod(destination, stat.S_IREAD | stat.S_IWRITE)
    delivered_hash = sha256_file(destination)
    if delivered_hash != source_hash:
        raise ValueError(f"copied bytes differ from source: {destination}")
    return delivered_hash


def _remove_tree(path: Path) -> None:
    """Remove a transaction tree even if a carrier became read-only."""

    def make_writable_and_retry(function: Any, failed_path: str, _exc_info: Any) -> None:
        os.chmod(failed_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        function(failed_path)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def _copy_prompt_artifacts(
    plan: Mapping[str, Any],
    *,
    package_root: Path,
) -> list[dict[str, Any]]:
    destination = package_root / "reference-artifacts"
    items = list(plan.get("reference_items") or [])
    if items:
        destination.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for item in items:
        source = validate_committed_source(item["source"], "reference item source")
        src = Path(source["resolved_path"])
        suffix = src.suffix.lower() or ".bin"
        filename = (
            f"{int(item['precedence']):03d}-{_safe_name(str(item['semantic_role']))}-"
            f"{_safe_name(str(item['artifact_id']))}{suffix}"
        )
        destination_path = destination / filename
        delivered_hash = _copy_exact_bytes(
            src,
            destination_path,
            expected_sha256=str(source["sha256"]),
        )
        rows.append(
            {
                "semantic_role": item["semantic_role"],
                "source_sha256": source["sha256"],
                "delivered_path": destination_path.relative_to(package_root).as_posix(),
                "media_type": source["media_type"],
                "delivered_sha256": delivered_hash,
            }
        )
    return rows


def _build_board(
    prepared_rows: Sequence[Mapping[str, Any]],
    output_path: Path,
    *,
    max_side: int,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for single-board transport") from exc
    if not prepared_rows:
        raise ValueError("single-board transport requires at least one reference")
    images = []
    try:
        for row in prepared_rows:
            with Image.open(str(row["transport"]["resolved_path"])) as image:
                images.append(image.convert("RGB"))
        columns = 2 if len(images) > 1 else 1
        row_count = math.ceil(len(images) / columns)
        gutter = 16
        panel_width = max(1, (max_side - gutter * (columns + 1)) // columns)
        panel_height = max(1, (max_side - gutter * (row_count + 1)) // row_count)
        board = Image.new("RGB", (max_side, max_side), "white")
        panels: list[dict[str, Any]] = []
        try:
            for index, (image, row) in enumerate(zip(images, prepared_rows, strict=True)):
                image.thumbnail((panel_width, panel_height), Image.Resampling.LANCZOS)
                column = index % columns
                row_index = index // columns
                x = gutter + column * (panel_width + gutter) + (panel_width - image.width) // 2
                y = gutter + row_index * (panel_height + gutter) + (panel_height - image.height) // 2
                board.paste(image, (x, y))
                panels.append(
                    {
                        "semantic_role": row["role"],
                        "source_sha256": row["source"]["sha256"],
                        "transport_sha256": row["transport"]["sha256"],
                        "box": {
                            "x": x,
                            "y": y,
                            "width": image.width,
                            "height": image.height,
                        },
                    }
                )
            board.save(output_path, format="PNG", optimize=True)
        finally:
            board.close()
    finally:
        for image in images:
            image.close()
    return {
        "resolved_path": output_path.name,
        "media_type": "image/png",
        "sha256": sha256_file(output_path),
        "panels": panels,
    }


def _relativize_prepared_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    package_root: Path,
) -> list[dict[str, Any]]:
    root = package_root.resolve()
    relative_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        normalized = copy.deepcopy(dict(row))
        path = Path(normalized["transport"]["resolved_path"]).resolve()
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"selected_references[{index}] transport is outside the package root"
            ) from exc
        normalized["transport"]["resolved_path"] = relative.as_posix()
        relative_rows.append(normalized)
    return relative_rows


def _stage_direct_model_transports(
    rows: Sequence[Mapping[str, Any]],
    *,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Copy validated direct transports under the transactional package root."""

    staged_rows = [copy.deepcopy(dict(row)) for row in rows]
    direct_rows = [
        row
        for row in staged_rows
        if isinstance(row.get("transport"), Mapping)
        and isinstance(row["transport"].get("derivation"), Mapping)
        and row["transport"]["derivation"].get("mode") == "direct"
    ]
    if not direct_rows:
        return staged_rows
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(staged_rows):
        transport = row.get("transport")
        if not isinstance(transport, Mapping):
            continue
        derivation = transport.get("derivation")
        if not isinstance(derivation, Mapping) or derivation.get("mode") != "direct":
            continue
        source = validate_committed_source(
            row.get("source"), f"selected_references[{index}].source"
        )
        source_path = Path(source["resolved_path"])
        if Path(str(transport.get("resolved_path") or "")).resolve() != source_path.resolve():
            raise ValueError(
                f"selected_references[{index}] direct transport path differs from source"
            )
        if transport.get("sha256") != source["sha256"]:
            raise ValueError(
                f"selected_references[{index}] direct transport hash differs from source"
            )
        if transport.get("media_type") != source["media_type"]:
            raise ValueError(
                f"selected_references[{index}] direct transport media type differs from source"
            )
        suffix = source_path.suffix.lower() or ".bin"
        filename = (
            f"{index:03d}-{_safe_name(str(row.get('role') or 'reference'))}-"
            f"{source['sha256'][:16]}{suffix}"
        )
        destination_path = destination / filename
        delivered_hash = _copy_exact_bytes(
            source_path,
            destination_path,
            expected_sha256=str(source["sha256"]),
        )
        row["transport"] = {
            "resolved_path": str(destination_path),
            "media_type": source["media_type"],
            "sha256": delivered_hash,
            "derivation": {"mode": "direct"},
        }
    return staged_rows


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _preflight_optional_file(path: Path | None, field: str) -> Path | None:
    if path is None:
        return None
    resolved = Path(path).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{field} must identify a file")
    return resolved


def execute_reference_use_plan(
    plan: Mapping[str, Any],
    *,
    output_dir: Path,
    prompt_file: Path | None = None,
    negative_file: Path | None = None,
    reference_selection: Mapping[str, Any] | None = None,
    max_side: int = 1536,
) -> dict[str, Any]:
    """Materialize one complete package and publish it only after full validation."""

    validation = validate_reference_use_plan(plan)
    if not validation["ok"]:
        raise ValueError("invalid reference-use plan: " + "; ".join(validation["errors"]))
    if not isinstance(max_side, int) or isinstance(max_side, bool) or max_side < 1:
        raise ValueError("max_side must be a positive integer")
    prompt_source = _preflight_optional_file(prompt_file, "prompt_file")
    negative_source = _preflight_optional_file(negative_file, "negative_file")
    state_selection = _validate_state_eligibility(plan, reference_selection)
    plan_items = list(plan.get("reference_items") or [])
    requested_mode = str(plan["transport_mode"])
    materialized_mode = requested_mode if plan_items else "none"
    materialized_target = plan.get("target_model") if plan_items else None
    if requested_mode in MODEL_TRANSPORT_MODES and plan_items:
        unresolved = plan["surface_lighting_plan"].get("unresolved_decisions") or []
        if unresolved:
            raise ValueError(
                "model-facing execution is blocked by unresolved surface-lighting decisions: "
                + "; ".join(str(value) for value in unresolved)
            )
        preflight_visual_dependencies(plan)

    final_dir = Path(output_dir).resolve()
    preexisted = final_dir.exists()
    if preexisted:
        if not final_dir.is_dir():
            raise ValueError(f"output path is not a directory: {final_dir}")
        if any(final_dir.iterdir()):
            raise ValueError(f"output directory must be empty: {final_dir}")
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{final_dir.name}.staging-", dir=final_dir.parent)
    ).resolve()
    committed = False
    try:
        _write_json(staging / "reference-use-plan.json", plan)
        _write_json(staging / "surface-lighting-plan.json", plan["surface_lighting_plan"])
        if prompt_source is not None:
            _copy_exact_bytes(prompt_source, staging / "final-prompt.txt")
        if negative_source is not None:
            _copy_exact_bytes(negative_source, staging / "final-negative.txt")

        prompt_artifacts = _copy_prompt_artifacts(plan, package_root=staging)
        if requested_mode == "svg-bundle" and any(
            row["media_type"] != "image/svg+xml" for row in prompt_artifacts
        ):
            raise ValueError("svg-bundle transport accepts SVG artifacts only")

        prepared_absolute: list[dict[str, Any]] = []
        board: dict[str, Any] | None = None
        if requested_mode in MODEL_TRANSPORT_MODES and plan_items:
            prepared_absolute = prepare_reference_use_plan_rows(
                plan,
                model=str(plan["target_model"]),
                output_dir=staging / "model-references",
                reference_selection=state_selection,
                max_side=max_side,
            )
            prepared_absolute = _stage_direct_model_transports(
                prepared_absolute,
                output_dir=staging / "model-references",
            )
            if requested_mode == "single-board":
                board = _build_board(
                    prepared_absolute,
                    staging / "reference-board.png",
                    max_side=max_side,
                )
        prepared_rows = _relativize_prepared_rows(
            prepared_absolute,
            package_root=staging,
        )
        preamble = canonical_reference_preamble(
            transport_mode=materialized_mode,
            selected_references=prepared_rows,
            reference_use_plan=plan,
            single_board=board,
        )
        (staging / "reference-preamble.txt").write_text(preamble, encoding="utf-8", newline="\n")
        prepared_set = build_prepared_reference_set(
            transport_mode=materialized_mode,
            target_model=(str(materialized_target) if materialized_target is not None else None),
            selected_references=prepared_rows,
            reference_selection=state_selection,
            reference_use_plan=plan,
            zero_reference_reason=plan.get("zero_reference_reason"),
            reference_preamble=preamble,
            prompt_artifacts=prompt_artifacts,
            single_board=board,
            package_root=staging,
        )
        _write_json(staging / "prepared-reference-set.json", prepared_set)
        validate_prepared_reference_set(
            prepared_set,
            model=(str(materialized_target) if materialized_target is not None else None),
            package_root=staging,
        )
        final_plan_report = validate_reference_use_plan(plan)
        if not final_plan_report["ok"]:
            raise ValueError(
                "reference-use plan changed before publication: "
                + "; ".join(final_plan_report["errors"])
            )

        if preexisted:
            final_dir.rmdir()
        os.replace(staging, final_dir)
        committed = True
        validated = validate_prepared_reference_set(
            prepared_set,
            model=(str(materialized_target) if materialized_target is not None else None),
            package_root=final_dir,
        )
        return validated
    except Exception:
        if committed and final_dir.is_dir():
            _remove_tree(final_dir)
        if preexisted and not final_dir.exists():
            final_dir.mkdir()
        raise
    finally:
        if staging.exists():
            _remove_tree(staging)


def _parse_record_use(value: str) -> dict[str, str]:
    record_id, separator, influence = str(value).partition("=")
    if not separator or not record_id or not influence:
        raise argparse.ArgumentTypeError(
            "record use must be RECORD_ID=INTENDED_INFLUENCE"
        )
    try:
        return normalize_selected_records(
            [{"record_id": record_id, "intended_influence": influence}]
        )[0]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return parsed


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_stdout(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def add_reference_plan_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the canonical planning argument contract to a CLI parser."""
    parser.add_argument(
        "--record-use",
        action="append",
        type=_parse_record_use,
        required=True,
        help="Canonical record use as RECORD_ID=INTENDED_INFLUENCE.",
    )
    parser.add_argument(
        "--transport-mode",
        choices=sorted(TRANSPORT_MODES),
        default="prompt-artifacts",
    )
    parser.add_argument("--target-model")
    parser.add_argument(
        "--source-lighting-mode",
        choices=["preserve", "rescope", "replace"],
        required=True,
    )
    parser.add_argument(
        "--light-source-json",
        action="append",
        type=_parse_json_object,
        default=[],
        help=surface_argument_help("light_source"),
    )
    parser.add_argument(
        "--material-response-json",
        action="append",
        type=_parse_json_object,
        default=[],
        help=surface_argument_help("material_response"),
    )
    parser.add_argument("--unresolved-decision", action="append", default=[])
    parser.add_argument("--max-assets-per-record", type=int, default=1)
    parser.add_argument("--max-references", type=int, default=None)
    parser.add_argument(
        "--technical-role",
        action="append",
        choices=sorted(TECHNICAL_CAPABILITIES),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or execute record-scoped visual-reference plans."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser(
        "plan",
        help="Build a reference-use plan",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_reference_plan_arguments(plan_parser)
    plan_parser.add_argument("--out", type=Path, required=True)
    add_pack_runtime_arguments(plan_parser)

    execute_parser = subparsers.add_parser(
        "execute", help="Transactionally materialize one canonical reference package"
    )
    execute_parser.add_argument("--plan", type=Path, required=True)
    execute_parser.add_argument("--output-dir", type=Path, required=True)
    execute_parser.add_argument("--prompt-file", type=Path)
    execute_parser.add_argument("--negative-file", type=Path)
    execute_parser.add_argument("--reference-selection", type=Path)
    execute_parser.add_argument("--max-side", type=int, default=1536)
    add_pack_runtime_arguments(execute_parser)

    example_parser = subparsers.add_parser(
        "example", help="Print a schema-derived CLI example"
    )
    example_parser.add_argument("example_name", choices=("plan",))

    schema_parser = subparsers.add_parser(
        "schema", help="Print a canonical JSON Schema"
    )
    schema_parser.add_argument(
        "schema_name", choices=("surface-lighting-plan",)
    )

    args = parser.parse_args(argv)
    if args.command == "example":
        _write_stdout(plan_cli_example())
        return 0
    if args.command == "schema":
        _write_stdout(surface_lighting_schema())
        return 0
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        if args.command == "plan":
            plan = build_reference_use_plan(
                args.record_use,
                transport_mode=args.transport_mode,
                source_lighting_mode=args.source_lighting_mode,
                target_model=args.target_model,
                max_assets_per_record=args.max_assets_per_record,
                max_references=args.max_references,
                include_technical_roles=args.technical_role,
                light_sources=args.light_source_json,
                material_responses=args.material_response_json,
                unresolved_decisions=args.unresolved_decision,
            )
            args.out.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(args.out, plan)
            _write_stdout(plan)
        else:
            selection = (
                _load_json_object(args.reference_selection)
                if args.reference_selection is not None
                else None
            )
            prepared = execute_reference_use_plan(
                _load_json_object(args.plan),
                output_dir=args.output_dir,
                prompt_file=args.prompt_file,
                negative_file=args.negative_file,
                reference_selection=selection,
                max_side=args.max_side,
            )
            _write_stdout(prepared)
        return 0
    except VisualDependencyPreflightError as exc:
        _write_stdout(
            {
                "ok": False,
                "error_code": "visual-dependency-preflight-failed",
                "errors": [str(exc)],
                "dependency_preflight": exc.report,
            }
        )
        return 1
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        _write_stdout({"ok": False, "errors": [str(exc)]})
        return 1
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    raise SystemExit(main())
