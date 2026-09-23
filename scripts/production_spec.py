#!/usr/bin/env python3
"""Create, validate, inspect, and hash scene-specific CPB production specs.

Production Specification is a scene render specification. Stable identity
and temporal canon live in separate contracts and state artifacts; this file
records their exact references and the resolved visual result for one image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

from state_protocol import find_non_finite_numbers, parse_json, validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "production-spec-template.json"
VALID_DOMAINS = {"human", "anthropomorphic-animal", "animal", "creature", "hybrid", "robot"}
SUBJECT_FIELDS = {
    "id", "domain", "species_morphology_profile_ref", "individual_morphology_contract_ref",
    "identity_contract_ref", "state_snapshot_ref", "visual_projection_ref", "resolved_morphology",
    "frame_character", "load_bearing_part_measurements", "accessory_geometry",
    "identity", "current_state", "proportions_and_form", "head_and_face",
    "surfaces_and_markings", "distinctive_details", "performance",
    "wardrobe_and_accessories", "growth_geometry", "garment_geometry",
    "pose_and_body_geometry", "hands",
    "legs_and_feet", "gaze_and_head", "props_and_contacts", "structure_notes",
}
OPTIONAL_SUBJECT_FIELDS = {"head_and_face", "hands", "legs_and_feet", "gaze_and_head", "structure_notes"}
ART_FIELDS = {
    "center_of_appeal", "subject_relationship", "composition_and_visual_hierarchy",
    "medium_family", "shape_and_rhythm", "surface_and_tactility",
    "color_and_light", "detail_hierarchy",
}
HASH_RE = re.compile(r"^[a-f0-9]{64}$")

CAMERA_SCHEMA = json.loads((ROOT / "schemas" / "camera-framing-contract.schema.json").read_text(encoding="utf-8"))
GROWTH_SCHEMA = json.loads((ROOT / "schemas" / "growth-geometry.schema.json").read_text(encoding="utf-8"))
GARMENT_SCHEMA = json.loads((ROOT / "schemas" / "garment-geometry.schema.json").read_text(encoding="utf-8"))
PERFORMANCE_SCHEMA = json.loads((ROOT / "schemas" / "performance-language.schema.json").read_text(encoding="utf-8"))
RESOLVED_MORPHOLOGY_SCHEMA = json.loads((ROOT / "schemas" / "resolved-morphology.schema.json").read_text(encoding="utf-8"))
FRAME_CHARACTER_SCHEMA = json.loads((ROOT / "schemas" / "frame-character.schema.json").read_text(encoding="utf-8"))
PART_MEASUREMENT_SCHEMA = json.loads((ROOT / "schemas" / "part-measurement.schema.json").read_text(encoding="utf-8"))
ACCESSORY_GEOMETRY_SCHEMA = json.loads((ROOT / "schemas" / "accessory-geometry.schema.json").read_text(encoding="utf-8"))
PRODUCTION_SPEC_SCHEMA = json.loads((ROOT / "schemas" / "production-spec.schema.json").read_text(encoding="utf-8"))





def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    data = parse_json(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("production spec must be a JSON object")
    return data


def validate_ref(value: Any, field: str, errors: list[str], *, required: bool) -> None:
    if value is None:
        if required:
            errors.append(f"{field} is required for state-aware production")
        return
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object or null")
        return
    reference_id = value.get("id")
    if not isinstance(reference_id, str) or not reference_id:
        errors.append(f"{field}.id must be a non-empty string")
    reference_hash = value.get("sha256")
    if not isinstance(reference_hash, str) or not HASH_RE.fullmatch(reference_hash):
        errors.append(f"{field}.sha256 must be a lowercase SHA-256 digest")


def validate_distinctive_details(subject_index: int, details: Any, errors: list[str]) -> None:
    if not isinstance(details, list):
        errors.append(f"subjects[{subject_index}].distinctive_details must be an array")
        return
    required_detail = {
        "id", "feature_type", "target_region", "laterality",
        "landmark_relation", "count_or_distribution", "relative_size",
        "shape_and_path", "orientation", "color_and_value", "depth_and_relief",
        "edge_and_texture", "surface_interaction", "age_or_condition",
        "visibility_and_occlusion", "identity_priority", "continuity_rules",
        "source_confidence",
    }
    valid_laterality = {"left", "right", "bilateral", "centerline", "distributed", "variable"}
    valid_priority = {"signature", "supporting", "optional"}
    valid_confidence = {"explicit-user", "reference-clear", "reference-approximate", "preset-selected", "user-confirmed"}
    seen: set[str] = set()
    for detail_index, detail in enumerate(details):
        label = f"subjects[{subject_index}].distinctive_details[{detail_index}]"
        if not isinstance(detail, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(required_detail - set(detail))
        if missing:
            errors.append(f"{label} missing fields: {missing}")
        unexpected = sorted(set(detail) - required_detail)
        if unexpected:
            errors.append(f"{label} unexpected fields: {unexpected}")
        detail_id = detail.get("id")
        if not isinstance(detail_id, str) or not detail_id:
            errors.append(f"{label}.id must be a non-empty string")
        elif detail_id in seen:
            errors.append(f"subjects[{subject_index}] duplicate distinctive detail id: {detail_id}")
        seen.add(detail_id)
        if detail.get("laterality") not in valid_laterality:
            errors.append(f"{label}.laterality is invalid")
        if detail.get("identity_priority") not in valid_priority:
            errors.append(f"{label}.identity_priority is invalid")
        if detail.get("source_confidence") not in valid_confidence:
            errors.append(f"{label}.source_confidence is invalid")
        if not isinstance(detail.get("continuity_rules"), list):
            errors.append(f"{label}.continuity_rules must be an array")


def validate(data: dict[str, Any], *, require_content: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    non_finite = find_non_finite_numbers(data)
    errors.extend(f"{path}: number must be finite" for path in non_finite)
    errors.extend(validate_against_schema(data, PRODUCTION_SPEC_SCHEMA))
    required = {
        "source_brief", "target_model", "creative_latitude",
        "image_promise", "art_direction", "state_context", "subjects", "scene",
        "camera", "lighting", "visual_language", "constraints", "selected_preset_ids",
    }
    missing = sorted(required - set(data))
    if missing:
        errors.append(f"missing top-level fields: {missing}")
    unexpected = sorted(set(data) - required)
    if unexpected:
        errors.append(f"unexpected top-level fields: {unexpected}")
    if data.get("creative_latitude") not in {"minimal", "directed", "expansive"}:
        errors.append("creative_latitude is invalid")

    art = data.get("art_direction")
    if not isinstance(art, dict):
        errors.append("art_direction must be an object")
    else:
        art_missing = sorted(ART_FIELDS - set(art))
        if art_missing:
            errors.append(f"art_direction missing fields: {art_missing}")
        art_unexpected = sorted(set(art) - ART_FIELDS)
        if art_unexpected:
            errors.append(f"art_direction unexpected fields: {art_unexpected}")
        if require_content and any(
            not isinstance(art.get(key), str) or not art[key].strip()
            for key in ART_FIELDS
        ):
            errors.append("complete art_direction fields are required")

    state_context = data.get("state_context")
    state_aware = False
    if not isinstance(state_context, dict):
        errors.append("state_context must be an object")
    else:
        state_required = {"mode", "state_lineage_sha256", "scene_context_ref"}
        state_missing = sorted(state_required - set(state_context))
        if state_missing:
            errors.append(f"state_context missing fields: {state_missing}")
        state_allowed = state_required | {"notes"}
        state_unexpected = sorted(set(state_context) - state_allowed)
        if state_unexpected:
            errors.append(f"state_context unexpected fields: {state_unexpected}")
        mode = state_context.get("mode")
        if mode not in {"stateless", "state-aware"}:
            errors.append("state_context.mode is invalid")
        state_aware = mode == "state-aware"
        lineage_hash = state_context.get("state_lineage_sha256")
        if not isinstance(lineage_hash, str) or not HASH_RE.fullmatch(lineage_hash):
            errors.append("state_context.state_lineage_sha256 must be a lowercase SHA-256 digest")
        validate_ref(state_context.get("scene_context_ref"), "state_context.scene_context_ref", errors, required=state_aware)
        if mode == "stateless" and state_context.get("scene_context_ref") is not None:
            errors.append("stateless production spec must not contain scene_context_ref")

    subjects = data.get("subjects")
    if not isinstance(subjects, list):
        errors.append("subjects must be an array")
    else:
        seen: set[str] = set()
        for index, subject in enumerate(subjects):
            if not isinstance(subject, dict):
                errors.append(f"subjects[{index}] must be an object")
                continue
            subject_missing = sorted(SUBJECT_FIELDS - OPTIONAL_SUBJECT_FIELDS - set(subject))
            if subject_missing:
                errors.append(f"subjects[{index}] missing fields: {subject_missing}")
            subject_unexpected = sorted(set(subject) - SUBJECT_FIELDS)
            if subject_unexpected:
                errors.append(f"subjects[{index}] unexpected fields: {subject_unexpected}")
            subject_id = subject.get("id")
            if not isinstance(subject_id, str) or not subject_id:
                errors.append(f"subjects[{index}].id must be a non-empty string")
            elif subject_id in seen:
                errors.append(f"duplicate subject id: {subject_id}")
            seen.add(subject_id)
            if subject.get("domain") not in VALID_DOMAINS:
                errors.append(f"subjects[{index}].domain is invalid")
            validate_ref(subject.get("species_morphology_profile_ref"), f"subjects[{index}].species_morphology_profile_ref", errors, required=state_aware)
            validate_ref(subject.get("individual_morphology_contract_ref"), f"subjects[{index}].individual_morphology_contract_ref", errors, required=state_aware)
            validate_ref(subject.get("identity_contract_ref"), f"subjects[{index}].identity_contract_ref", errors, required=state_aware)
            validate_ref(subject.get("state_snapshot_ref"), f"subjects[{index}].state_snapshot_ref", errors, required=state_aware)
            validate_ref(subject.get("visual_projection_ref"), f"subjects[{index}].visual_projection_ref", errors, required=state_aware)
            if not isinstance(subject.get("current_state"), dict):
                errors.append(f"subjects[{index}].current_state must be an object")
            resolved = subject.get("resolved_morphology")
            errors.extend(validate_against_schema(
                resolved, RESOLVED_MORPHOLOGY_SCHEMA,
                f"$.subjects[{index}].resolved_morphology"
            ))
            frame_character = subject.get("frame_character")
            errors.extend(validate_against_schema(
                frame_character, FRAME_CHARACTER_SCHEMA, f"$.subjects[{index}].frame_character"
            ))
            if isinstance(resolved, dict) and resolved.get("frame_character") != frame_character:
                errors.append(f"subjects[{index}].frame_character must match resolved_morphology.frame_character")
            measurements = subject.get("load_bearing_part_measurements")
            if not isinstance(measurements, list):
                errors.append(f"subjects[{index}].load_bearing_part_measurements must be an array")
            else:
                seen_measurements: set[str] = set()
                for measurement_index, measurement in enumerate(measurements):
                    errors.extend(validate_against_schema(
                        measurement, PART_MEASUREMENT_SCHEMA,
                        f"$.subjects[{index}].load_bearing_part_measurements[{measurement_index}]"
                    ))
                    if isinstance(measurement, dict):
                        measurement_id = measurement.get("measurement_id")
                        if isinstance(measurement_id, str) and measurement_id in seen_measurements:
                            errors.append(f"subjects[{index}] duplicate measurement_id: {measurement_id}")
                        if isinstance(measurement_id, str):
                            seen_measurements.add(measurement_id)
                if isinstance(resolved, dict) and resolved.get("load_bearing_part_measurements") != measurements:
                    errors.append(f"subjects[{index}].load_bearing_part_measurements must match resolved morphology")
            accessories = subject.get("accessory_geometry")
            if not isinstance(accessories, list):
                errors.append(f"subjects[{index}].accessory_geometry must be an array")
            else:
                seen_accessories: set[str] = set()
                for accessory_index, accessory in enumerate(accessories):
                    errors.extend(validate_against_schema(
                        accessory, ACCESSORY_GEOMETRY_SCHEMA,
                        f"$.subjects[{index}].accessory_geometry[{accessory_index}]"
                    ))
                    if isinstance(accessory, dict):
                        accessory_id = accessory.get("accessory_id")
                        if isinstance(accessory_id, str) and accessory_id in seen_accessories:
                            errors.append(f"subjects[{index}] duplicate accessory_id: {accessory_id}")
                        if isinstance(accessory_id, str):
                            seen_accessories.add(accessory_id)
            validate_distinctive_details(index, subject.get("distinctive_details"), errors)
            errors.extend(validate_against_schema(
                subject.get("performance"), PERFORMANCE_SCHEMA, f"$.subjects[{index}].performance"
            ))
            errors.extend(validate_against_schema(
                subject.get("growth_geometry"), GROWTH_SCHEMA, f"$.subjects[{index}].growth_geometry"
            ))
            garments = subject.get("garment_geometry")
            if not isinstance(garments, list):
                errors.append(f"subjects[{index}].garment_geometry must be an array")
            else:
                seen_garments: set[str] = set()
                for garment_index, garment in enumerate(garments):
                    errors.extend(validate_against_schema(
                        garment, GARMENT_SCHEMA, f"$.subjects[{index}].garment_geometry[{garment_index}]"
                    ))
                    if isinstance(garment, dict):
                        garment_id = garment.get("garment_id")
                        if isinstance(garment_id, str) and garment_id in seen_garments:
                            errors.append(f"subjects[{index}] duplicate garment_id: {garment_id}")
                        if isinstance(garment_id, str):
                            seen_garments.add(garment_id)

    for key in ("scene", "camera", "lighting", "visual_language", "constraints"):
        if not isinstance(data.get(key), dict):
            errors.append(f"{key} must be an object")
    errors.extend(validate_against_schema(data.get("camera"), CAMERA_SCHEMA, "$.camera"))
    if not isinstance(data.get("selected_preset_ids"), list):
        errors.append("selected_preset_ids must be an array")
    if require_content:
        for field in ("source_brief", "target_model", "image_promise"):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{field} is required")

    return {
        "ok": not errors,
        "errors": errors,
        "sha256": digest(data) if not non_finite else None,
        "state_mode": state_context.get("mode") if isinstance(state_context, dict) else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage a CPB Production Specification.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("out")
    val = sub.add_parser("validate")
    val.add_argument("spec")
    val.add_argument("--require-content", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("spec")
    hs = sub.add_parser("hash")
    hs.add_argument("spec")
    args = parser.parse_args(argv)

    if args.command == "init":
        data = load(TEMPLATE)
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        result: dict[str, Any] = {"created": args.out}
    else:
        data = load(Path(args.spec))
        if args.command == "validate":
            result = validate(data, require_content=args.require_content)
        elif args.command == "show":
            result = data
        else:
            result = {"sha256": digest(data)}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if not isinstance(result, dict) or result.get("ok", True) else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
