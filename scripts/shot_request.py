#!/usr/bin/env python3
"""Validate an arriving shot-request and its optional bindings.

The tool verifies the shared boundary artifact and hashes. It does not invent art
direction, choose presets, or turn the request into a finished image prompt.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import protocol_contract as public_contract
from pathlib import Path
from typing import Any, Sequence

from state_protocol import (
    SELF_HASH_FIELDS,
    artifact_hash as state_artifact_hash,
    load_json,
    validate_artifact,
)

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DELIVERABLES = {
    "start-frame", "end-frame", "boundary-frame", "shot-reference",
    "production-prompt", "character-reference",
}
VIEWPOINT_HASH_FIELDS = {
    "shot-camera-spec": "camera_spec_sha256",
    "shot-visual-projection": "projection_sha256",
    "shot-request": "request_sha256",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def viewpoint_hash(value: dict[str, Any]) -> str:
    return public_contract.artifact_hash(value)


def parse_binding(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"binding must use CHARACTER_ID=PATH: {raw}")
        key, path = raw.split("=", 1)
        key = key.strip()
        if not key or key in result:
            raise ValueError(f"invalid or duplicate binding key: {key!r}")
        result[key] = Path(path).resolve()
    return result




def validate_request(value: dict[str, Any], *, allow_placeholder_hash: bool = False) -> list[str]:
    if value.get("artifact_type") != "shot-request":
        return ["artifact_type must be shot-request"]
    return public_contract.validate_artifact(value, allow_placeholder_hashes=allow_placeholder_hash)["errors"]


def validate_bound_artifact(
    path: Path,
    expected_type: str,
    expected_hash: str,
    *,
    state: bool,
) -> list[str]:
    errors: list[str] = []
    try:
        value = load_json(path)
    except Exception as exc:
        return [f"{path}: {exc}"]
    if value.get("artifact_type") != expected_type:
        errors.append(f"{path}: expected artifact_type {expected_type}")
        return errors
    if state:
        schema_report = validate_artifact(value)
        if not schema_report.get("ok"):
            errors.append(
                f"{path}: artifact schema validation failed: "
                + "; ".join(schema_report.get("errors", []))
            )
        actual = state_artifact_hash(value)
        declared_field = SELF_HASH_FIELDS.get(expected_type)
    else:
        schema_report = public_contract.validate_artifact(value)
        if not schema_report["ok"]:
            errors.extend(f"{path}: {item}" for item in schema_report["errors"])
        actual = viewpoint_hash(value)
        declared_field = VIEWPOINT_HASH_FIELDS.get(expected_type)
    if declared_field and value.get(declared_field) != actual:
        errors.append(f"{path}: {declared_field} does not match canonical content")
    if actual != expected_hash:
        errors.append(f"{path}: canonical hash does not match request binding")
    return errors


def validate_bundle(
    request: dict[str, Any], *, species_profile_files: dict[str, Path],
    individual_morphology_files: dict[str, Path], identity_files: dict[str, Path],
    state_files: dict[str, Path], scene_context: Path | None,
    camera_spec: Path | None, shot_projection: Path | None, require_complete: bool = False,
) -> dict[str, Any]:
    errors = validate_request(request)
    checked: list[str] = []
    species_map = request.get("species_profile_sha256_by_character", {})
    individual_map = request.get("individual_morphology_sha256_by_character", {})
    identity_map = request.get("identity_contract_sha256_by_character", {})
    state_map = request.get("state_snapshot_sha256_by_character", {})
    morphology_refs = request.get("visible_morphology_feature_refs_by_character", {})
    for character_id, path in species_profile_files.items():
        expected = species_map.get(character_id)
        if expected is None:
            errors.append(f"species profile supplied for unbound character: {character_id}")
            continue
        errors.extend(validate_bound_artifact(path, "species-morphology-profile", expected, state=True))
        checked.append(f"species-profile:{character_id}")
    for character_id, path in individual_morphology_files.items():
        expected = individual_map.get(character_id)
        if expected is None:
            errors.append(f"individual morphology supplied for unbound character: {character_id}")
            continue
        errors.extend(validate_bound_artifact(path, "individual-morphology-contract", expected, state=True))
        checked.append(f"individual-morphology:{character_id}")
    for character_id, path in identity_files.items():
        expected = identity_map.get(character_id)
        if expected is None:
            errors.append(f"identity file supplied for unbound character: {character_id}")
            continue
        errors.extend(validate_bound_artifact(path, "character-identity-contract", expected, state=True))
        checked.append(f"identity:{character_id}")
    for character_id, path in state_files.items():
        expected = state_map.get(character_id)
        if expected is None:
            errors.append(f"state snapshot supplied for unbound character: {character_id}")
            continue
        errors.extend(validate_bound_artifact(path, "state-snapshot", expected, state=True))
        checked.append(f"state:{character_id}")
    for character_id in sorted(set(species_profile_files) & set(individual_morphology_files) & set(identity_files)):
        species = load_json(species_profile_files[character_id])
        individual = load_json(individual_morphology_files[character_id])
        identity = load_json(identity_files[character_id])
        species_hash = state_artifact_hash(species)
        individual_hash = state_artifact_hash(individual)
        if individual.get("character_id") != character_id:
            errors.append(f"individual morphology character_id mismatch for {character_id}")
        if individual.get("species_profile_ref") != {"id": species.get("profile_id"), "sha256": species_hash}:
            errors.append(f"individual morphology species reference mismatch for {character_id}")
        if identity.get("species_morphology_profile_ref") != {"id": species.get("profile_id"), "sha256": species_hash}:
            errors.append(f"identity species morphology reference mismatch for {character_id}")
        if identity.get("individual_morphology_contract_ref") != {"id": individual.get("contract_id"), "sha256": individual_hash}:
            errors.append(f"identity individual morphology reference mismatch for {character_id}")
        known_features = {str(item.get("feature_id")) for item in individual.get("feature_realizations", []) if isinstance(item, dict)}
        unknown = sorted(set(morphology_refs.get(character_id, [])) - known_features)
        if unknown:
            errors.append(f"request cites unknown morphology features for {character_id}: {unknown}")

    if scene_context:
        errors.extend(validate_bound_artifact(scene_context, "scene-context-snapshot", str(request.get("scene_context_sha256")), state=True))
        checked.append("scene-context")
    if camera_spec:
        errors.extend(validate_bound_artifact(camera_spec, "shot-camera-spec", str(request.get("camera_spec_sha256")), state=False))
        checked.append("camera-spec")
    if shot_projection:
        errors.extend(validate_bound_artifact(shot_projection, "shot-visual-projection", str(request.get("shot_projection_sha256")), state=False))
        checked.append("shot-projection")
    # Content equality alone cannot prove that artifacts describe the same scene.
    if not errors:
        for cid, path in identity_files.items():
            if load_json(path)["character_id"] != cid:
                errors.append(f"identity character_id mismatch for {cid}")
        for cid, path in state_files.items():
            snap = load_json(path)
            if snap["character_id"] != cid:
                errors.append(f"state character_id mismatch for {cid}")
            for field, mapping in (("species_profile_sha256", species_map), ("individual_morphology_sha256", individual_map), ("identity_contract_sha256", identity_map)):
                if snap[field] != mapping[cid]:
                    errors.append(f"state lineage mismatch for {cid}: {field}")
        context = load_json(scene_context) if scene_context else None
        if context is not None:
            if context["scene_context_id"] != request["scene_id"]:
                errors.append("request scene_id differs from scene context")
            active = {x["character_id"]: x for x in context["active_character_snapshots"]}
            for cid, expected in state_map.items():
                if cid not in active or active[cid]["state_snapshot_sha256"] != expected:
                    errors.append(f"context does not bind request state for {cid}")
            for cid, path in state_files.items():
                snap = load_json(path)
                if snap["timeline_id"] != context["timeline_id"] or snap["scene_context_id"] != context["scene_context_id"] or not context["story_order_start"] <= snap["story_order"] <= context["story_order_end"]:
                    errors.append(f"state temporal or scene scope mismatch for {cid}")
        for label, path in (("camera", camera_spec), ("shot projection", shot_projection)):
            if path is None:
                continue
            value = load_json(path)
            for field in ("scene_id", "shot_id", "viewpoint_profile_id"):
                if value[field] != request[field]:
                    errors.append(f"{label} {field} differs from request")
            if value["state_snapshot_sha256_by_character"] != state_map:
                errors.append(f"{label} state bindings differ from request")
            if label == "shot projection":
                for field in ("camera_spec_sha256", "scene_context_sha256"):
                    if value[field] != request[field]:
                        errors.append(f"shot projection {field} differs from request")
    expected = {f"{prefix}:{cid}" for prefix in ("species-profile", "individual-morphology", "identity", "state") for cid in identity_map}
    expected.update({"scene-context", "camera-spec", "shot-projection"})
    unverified = sorted(expected - set(checked))
    if require_complete and unverified:
        errors.append("missing required binding files: " + ", ".join(unverified))
    return {
        "validator": "shot-handoff",
        "request_id": request.get("request_id"),
        "scene_id": request.get("scene_id"),
        "shot_id": request.get("shot_id"),
        "viewpoint_profile_id": request.get("viewpoint_profile_id"),
        "deliverable": request.get("deliverable"),
        "checked_bindings": checked,
        "unverified_bindings": unverified,
        "complete": not errors and not unverified,
        "ok": not errors,
        "errors": errors,
        "artistic_quality_evaluated": False,
    }


def plot_link_notes(request: dict[str, Any]) -> list[str]:
    """What the request leaves unsaid about where the shot came from.

    A missing link is not an error: a request may be made for something that
    has no scene plot. It is a question nobody answered, and a reader that passes
    it in silence lets one frame carry two approvals that never meet.
    """

    notes: list[str] = []
    if not isinstance(request, dict):
        return notes
    if request.get("scene_plot_sha256") is None:
        notes.append(
            "scene plot: the request names no scene_plot_sha256, so the approved plot this shot "
            "was planned in cannot be carried into the prompt plot's source, and this side's "
            "own plot will be a second approval that names nothing above it"
        )
    elif request.get("narrative_sha256") is None:
        notes.append(
            "narrative: the request names a scene plot and no narrative_sha256, so the chapter "
            "and arcs the scene belongs to cannot be carried"
        )
    return notes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an arriving shot-request")
    parser.add_argument("request")
    parser.add_argument("--allow-placeholder-hash", action="store_true")
    parser.add_argument("--require-complete", action="store_true", help="Require every lineage, context, camera and projection binding file")
    parser.add_argument("--species-profile", action="append", default=[], metavar="CHARACTER_ID=PATH")
    parser.add_argument("--individual-morphology", action="append", default=[], metavar="CHARACTER_ID=PATH")
    parser.add_argument("--identity", action="append", default=[], metavar="CHARACTER_ID=PATH")
    parser.add_argument("--state", action="append", default=[], metavar="CHARACTER_ID=PATH")
    parser.add_argument("--scene-context")
    parser.add_argument("--camera-spec")
    parser.add_argument("--shot-projection")
    args = parser.parse_args(argv)
    request: dict[str, Any] | None = None
    try:
        request = load_json(Path(args.request))
        if args.allow_placeholder_hash and args.require_complete:
            raise ValueError("complete binding verification requires concrete artifacts")
        if args.allow_placeholder_hash and not any((
            args.species_profile, args.individual_morphology, args.identity, args.state,
            args.scene_context, args.camera_spec, args.shot_projection,
        )):
            errors = validate_request(request, allow_placeholder_hash=True)
            report = {
                "validator": "shot-handoff",
                "ok": not errors, "errors": errors,
                "template_validation": True, "artistic_quality_evaluated": False,
            }
        else:
            report = validate_bundle(
                request,
                species_profile_files=parse_binding(args.species_profile),
                individual_morphology_files=parse_binding(args.individual_morphology),
                identity_files=parse_binding(args.identity),
                state_files=parse_binding(args.state),
                scene_context=Path(args.scene_context).resolve() if args.scene_context else None,
                camera_spec=Path(args.camera_spec).resolve() if args.camera_spec else None,
                shot_projection=Path(args.shot_projection).resolve() if args.shot_projection else None,
                require_complete=args.require_complete,
            )
    except (ValueError, OSError, TypeError, KeyError, AttributeError, UnicodeError) as exc:
        report = {"validator": "shot-handoff", "ok": False, "errors": [str(exc)], "artistic_quality_evaluated": False}
    notes = plot_link_notes(request) if isinstance(request, dict) else []
    if notes:
        report["unmeasured"] = notes
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
