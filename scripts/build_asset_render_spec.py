#!/usr/bin/env python3
"""Build and seal one scene- or reference-asset render specification.

The script does not invent art direction. It binds reviewed inputs and their
hashes into an Asset Render Specification so the state lineage can prove
which identity, state, scene context, and projection were used.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Sequence

from state_protocol import artifact_hash, finalize_artifact, load_json, resolve_growth_geometry, validate_artifact, write_json


def require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def build_render_spec(
    *,
    request: dict[str, Any],
    identity_contract: dict[str, Any],
    species_profile: dict[str, Any],
    individual_morphology: dict[str, Any],
    state_snapshot: dict[str, Any] | None = None,
    visual_projection: dict[str, Any] | None = None,
    era_contract: dict[str, Any] | None = None,
    appearance_variant: dict[str, Any] | None = None,
    form_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity_report = validate_artifact(identity_contract)
    if not identity_report.get("ok"):
        raise ValueError("invalid identity contract: " + "; ".join(identity_report.get("errors", [])))
    if identity_contract.get("artifact_type") != "character-identity-contract":
        raise ValueError("identity_contract must be a character-identity-contract")

    def checked(value: dict[str, Any] | None, kind: str) -> dict[str, Any] | None:
        if value is None:
            return None
        report = validate_artifact(value)
        if not report.get("ok"):
            raise ValueError(f"invalid {kind}: " + "; ".join(report.get("errors", [])))
        if value.get("artifact_type") != kind:
            raise ValueError(f"expected artifact_type {kind}")
        return value

    species_profile = checked(species_profile, "species-morphology-profile")
    individual_morphology = checked(individual_morphology, "individual-morphology-contract")
    if species_profile is None or individual_morphology is None:
        raise ValueError("species_profile and individual_morphology are required")
    species_hash = artifact_hash(species_profile)
    individual_hash = artifact_hash(individual_morphology)
    if identity_contract.get("species_morphology_profile_ref") != {"id": species_profile.get("profile_id"), "sha256": species_hash}:
        raise ValueError("identity contract species morphology reference does not match supplied profile")
    if identity_contract.get("individual_morphology_contract_ref") != {"id": individual_morphology.get("contract_id"), "sha256": individual_hash}:
        raise ValueError("identity contract individual morphology reference does not match supplied contract")
    if individual_morphology.get("character_id") != identity_contract.get("character_id"):
        raise ValueError("individual morphology contract belongs to another character")

    state_snapshot = checked(state_snapshot, "state-snapshot")
    if form_contract is not None and state_snapshot is None:
        raise ValueError("a form contract requires a state snapshot to bind its hash in the render lineage")
    visual_projection = checked(visual_projection, "visual-state-projection")
    era_contract = checked(era_contract, "era-contract")
    appearance_variant = checked(appearance_variant, "appearance-variant-contract")

    character_id = str(request.get("character_id") or identity_contract.get("character_id") or "")
    if character_id != identity_contract.get("character_id"):
        raise ValueError("request character_id differs from identity contract")
    if state_snapshot and state_snapshot.get("character_id") != character_id:
        raise ValueError("state snapshot belongs to another character")
    if state_snapshot and state_snapshot.get("species_profile_sha256") != species_hash:
        raise ValueError("state snapshot species morphology hash differs from supplied profile")
    if state_snapshot and state_snapshot.get("individual_morphology_sha256") != individual_hash:
        raise ValueError("state snapshot individual morphology hash differs from supplied contract")
    identity_hash = artifact_hash(identity_contract)
    if state_snapshot and state_snapshot.get("identity_contract_sha256") != identity_hash:
        raise ValueError("state snapshot identity hash differs from supplied identity contract")
    if state_snapshot and state_snapshot.get("era_contract_sha256") != (
        artifact_hash(era_contract) if era_contract else None
    ):
        raise ValueError("state snapshot era hash differs from supplied era contract")
    if state_snapshot and state_snapshot.get("appearance_variant_sha256") != (
        artifact_hash(appearance_variant) if appearance_variant else None
    ):
        raise ValueError("state snapshot appearance hash differs from supplied appearance variant")
    if visual_projection and visual_projection.get("character_id") != character_id:
        raise ValueError("visual projection belongs to another character")
    if visual_projection and state_snapshot is None:
        raise ValueError("visual projection requires the referenced state snapshot")
    if visual_projection and visual_projection.get("state_snapshot_sha256") != artifact_hash(state_snapshot):
        raise ValueError("visual projection state hash differs from supplied state snapshot")
    for name, contract in (("era contract", era_contract), ("appearance variant", appearance_variant)):
        if contract is None:
            continue
        if contract.get("character_id") != character_id:
            raise ValueError(f"{name} belongs to another character")
        if contract.get("parent_identity_contract_sha256") != identity_hash:
            raise ValueError(f"{name} parent identity hash differs from supplied identity contract")

    required = (
        "render_spec_id", "asset_id", "purpose", "view", "framing",
        "style_family_id", "target_model", "art_direction", "subject_resolution",
        "scene", "camera", "lighting", "prompt_scaffold",
    )
    missing = [key for key in required if request.get(key) in (None, "", {})]
    if missing:
        raise ValueError(f"render request missing fields: {missing}")

    subject_resolution = copy.deepcopy(require_object(request["subject_resolution"], "subject_resolution"))
    growth = resolve_growth_geometry(
        identity_contract, era_contract=era_contract, form_contract=form_contract,
        appearance_variant=appearance_variant, state_snapshot=state_snapshot,
    )
    if "growth_geometry" in subject_resolution and subject_resolution["growth_geometry"] != growth:
        raise ValueError("render request growth_geometry differs from resolved identity, approved variants and state")
    subject_resolution["growth_geometry"] = growth

    artifact = {
        "artifact_type": "asset-render-specification",
        "render_spec_id": str(request["render_spec_id"]),
        "asset_id": str(request["asset_id"]),
        "character_id": character_id,
        "purpose": str(request["purpose"]),
        "view": str(request["view"]),
        "framing": str(request["framing"]),
        "species_profile_sha256": species_hash,
        "individual_morphology_sha256": individual_hash,
        "identity_contract_sha256": identity_hash,
        "era_contract_sha256": artifact_hash(era_contract) if era_contract else None,
        "appearance_variant_sha256": artifact_hash(appearance_variant) if appearance_variant else None,
        "state_snapshot_sha256": state_snapshot.get("state_snapshot_sha256") if state_snapshot else None,
        "visual_state_projection_sha256": visual_projection.get("projection_sha256") if visual_projection else None,
        "visual_authority_sha256": request.get("visual_authority_sha256") or (identity_contract.get("visual_authority_ref") or {}).get("sha256"),
        "visual_evidence_bundle_sha256": request.get("visual_evidence_bundle_sha256"),
        "style_family_id": str(request["style_family_id"]),
        "target_model": str(request["target_model"]),
        "coverage_requirement_ids": list(request.get("coverage_requirement_ids", [])),
        "art_direction": require_object(request["art_direction"], "art_direction"),
        "subject_resolution": subject_resolution,
        "scene": require_object(request["scene"], "scene"),
        "camera": require_object(request["camera"], "camera"),
        "lighting": require_object(request["lighting"], "lighting"),
        "prompt_scaffold": str(request["prompt_scaffold"]).strip(),
        "selected_preset_ids": list(request.get("selected_preset_ids", [])),
        "render_spec_sha256": "0" * 64,
    }
    artifact = finalize_artifact(artifact)
    report = validate_artifact(artifact)
    if not report.get("ok"):
        raise ValueError("invalid render specification: " + "; ".join(report.get("errors", [])))
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an Asset Render Specification.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--identity-contract", required=True)
    parser.add_argument("--species-profile", required=True)
    parser.add_argument("--individual-morphology", required=True)
    parser.add_argument("--state-snapshot")
    parser.add_argument("--visual-projection")
    parser.add_argument("--era-contract")
    parser.add_argument("--appearance-variant")
    parser.add_argument("--form-contract")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        artifact = build_render_spec(
            request=load_json(Path(args.request)),
            identity_contract=load_json(Path(args.identity_contract)),
            species_profile=load_json(Path(args.species_profile)),
            individual_morphology=load_json(Path(args.individual_morphology)),
            state_snapshot=load_json(Path(args.state_snapshot)) if args.state_snapshot else None,
            visual_projection=load_json(Path(args.visual_projection)) if args.visual_projection else None,
            era_contract=load_json(Path(args.era_contract)) if args.era_contract else None,
            appearance_variant=load_json(Path(args.appearance_variant)) if args.appearance_variant else None,
            form_contract=load_json(Path(args.form_contract)) if args.form_contract else None,
        )
        write_json(Path(args.out), artifact)
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
