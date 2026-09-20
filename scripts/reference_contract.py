#!/usr/bin/env python3
"""Canonical record-scoped authority and surface-lighting contracts.

This module is intentionally independent of the catalog and filesystem. Runtime
code supplies canonical records and committed sources; this module determines
the only authority those sources may receive for one declared intended use.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from state_protocol import finalize_artifact, validate_artifact


INTENDED_INFLUENCES = (
    "identity",
    "pose-camera",
    "outfit",
    "surface-finish",
    "lighting",
    "environment",
    "prop-accessory",
    "local-color",
)

TECHNICAL_CAPABILITIES = (
    "adopted-reference",
    "faithful-archival-vector",
    "structural-line-tone",
    "color-audit",
    "saturation-rescue",
    "specular-audit",
    "subject-mask",
)

ZERO_REFERENCE_CODES = (
    "no-canonical-record-selected",
    "no-suitable-active-asset",
    "user-declined-visual-references",
    "state-ineligible",
)

MODEL_TRANSPORT_MODES = frozenset({"multi-image", "single-board"})
PROMPT_TRANSPORT_MODES = frozenset({"prompt-artifacts", "svg-bundle"})
TRANSPORT_MODES = MODEL_TRANSPORT_MODES | PROMPT_TRANSPORT_MODES


_INFLUENCE_CONTROLS: dict[str, tuple[str, ...]] = {
    "identity": (
        "permanent character identity",
        "species and stable anatomy",
        "permanent marking layout",
        "stable hair, mane, fur-tuft, body-fur distribution, and grooming topology",
    ),
    "pose-camera": (
        "target pose and body gesture",
        "target camera framing and crop",
        "target silhouette and overlap order",
    ),
    "outfit": (
        "garment and wearable construction",
        "garment material class",
        "garment local color",
        "wearable placement and layering",
    ),
    "surface-finish": (
        "declared material response and surface finish",
        "declared highlight character",
        "declared rendering-medium finish",
    ),
    "lighting": (
        "target light direction, color, and relative intensity",
        "target shadow topology",
        "target highlight response under the declared lighting",
    ),
    "environment": (
        "environment geometry and spatial layout",
        "background composition",
        "subject-background separation",
    ),
    "prop-accessory": (
        "prop and accessory geometry",
        "prop and accessory placement",
        "prop and accessory material and local color",
    ),
    "local-color": (
        "declared local-color regions",
        "declared palette relationships",
    ),
}


_PAIR_CONTROLS: dict[tuple[str, str], tuple[str, ...]] = {
    ("faithful-archival-vector", "identity"): _INFLUENCE_CONTROLS["identity"],
    ("faithful-archival-vector", "outfit"): _INFLUENCE_CONTROLS["outfit"],
    ("faithful-archival-vector", "lighting"): _INFLUENCE_CONTROLS["lighting"],
    ("faithful-archival-vector", "surface-finish"): (
        "source-supported material response and surface finish",
        "source-supported rendering-medium finish",
    ),
    ("faithful-archival-vector", "prop-accessory"): _INFLUENCE_CONTROLS[
        "prop-accessory"
    ],
    ("faithful-archival-vector", "local-color"): _INFLUENCE_CONTROLS["local-color"],
    ("structural-line-tone", "pose-camera"): _INFLUENCE_CONTROLS["pose-camera"],
    ("structural-line-tone", "outfit"): (
        "garment and wearable construction",
        "wearable placement and layering",
    ),
    ("structural-line-tone", "environment"): (
        "environment geometry and spatial layout",
        "background composition",
    ),
    ("structural-line-tone", "prop-accessory"): (
        "prop and accessory geometry",
        "prop and accessory placement",
    ),
    ("color-audit", "identity"): ("permanent marking layout",),
    ("color-audit", "outfit"): ("garment local color",),
    ("color-audit", "surface-finish"): (
        "source-supported broad material-value relationships",
    ),
    ("color-audit", "prop-accessory"): (
        "prop and accessory material and local color",
    ),
    ("color-audit", "local-color"): _INFLUENCE_CONTROLS["local-color"],
    ("saturation-rescue", "local-color"): (
        "small declared high-saturation accents",
    ),
    ("specular-audit", "surface-finish"): (
        "candidate highlight placement and density evidence",
    ),
    ("specular-audit", "lighting"): (
        "candidate highlight placement under the declared target lighting",
    ),
    ("specular-audit", "prop-accessory"): (
        "candidate prop and accessory highlight placement",
    ),
    ("subject-mask", "pose-camera"): (
        "target silhouette",
        "subject-background separation",
    ),
    ("subject-mask", "environment"): ("subject-background separation",),
}


# A user-adopted image carries only its receipt-approved influence; the
# active validator additionally checks that bound scope on its source asset.
_PAIR_CONTROLS.update({("adopted-reference", influence): controls
                       for influence, controls in _INFLUENCE_CONTROLS.items()})

_TECHNICAL_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "adopted-reference": ("all visual dimensions outside the explicitly approved adoption scope",),
    "faithful-archival-vector": (
        "source pose, camera, crop, environment, lighting, and temporary state unless independently authorized",
    ),
    "structural-line-tone": (
        "final local color, material finish, lighting color, and rendering medium",
    ),
    "color-audit": (
        "pose, camera, identity topology, material class, and lighting direction",
    ),
    "saturation-rescue": (
        "base color, geometry, identity, pose, material, and lighting",
    ),
    "specular-audit": (
        "local color, identity topology, pose, shadow topology, and material class by itself",
    ),
    "subject-mask": (
        "identity detail, local color, material, lighting, and internal anatomy",
    ),
}


_INFLUENCE_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "identity": (
        "gaze, facial expression, mouth state, perspiration, and other transient body state",
        "outfit, props, pose, camera, environment, and lighting unless independently authorized",
        "wind, wetness, motion, or scene-driven hair, mane, tuft, fur, and grooming displacement",
    ),
    "pose-camera": (
        "character identity, species, permanent markings, outfit, local color, material, and lighting",
    ),
    "outfit": (
        "character identity, species, anatomy, permanent markings, hair or fur identity, gaze, expression, and transient body state",
        "source pose, camera, environment, and lighting",
    ),
    "surface-finish": (
        "identity, species, geometry, pose, camera, outfit construction, local color, and environment",
    ),
    "lighting": (
        "identity, species, geometry, pose, camera, outfit construction, local color, and environment geometry",
    ),
    "environment": (
        "character identity, species, anatomy, markings, outfit, expression, local color, and transient body state",
    ),
    "prop-accessory": (
        "character identity, species, anatomy, markings, outfit, pose, camera, expression, and environment",
    ),
    "local-color": (
        "identity topology, species, geometry, pose, camera, material class, lighting direction, and environment",
    ),
}


_LAYERS = {
    "adopted-reference": "A",
    "faithful-archival-vector": "A",
    "structural-line-tone": "B",
    "color-audit": "B",
    "saturation-rescue": "B",
    "specular-audit": "B",
    "subject-mask": "B",
}


_COMPLETE_SOURCE_LIGHTING_TECHNICAL_ROLES = frozenset(
    {"faithful-archival-vector", "adopted-reference"}
)
_MISSING_SOURCE_LIGHTING_REASON = (
    "source lighting cannot be preserved without complete lighting-authorized "
    "visual evidence"
)


# Canonical-record support is deliberately independent from record kind and
# category.  Those classifications may route discovery, but they are not
# evidence that a record actually contains the semantics a reference is asked
# to control.  Field-name signals cover structured defaults and contracts;
# text signals cover affirmative labels, tags, search phrases, and prose
# contracts.  Negative/diagnostic branches never grant authority.
_SEMANTIC_FIELD_SIGNALS: dict[str, frozenset[str]] = {
    "identity": frozenset(
        {
            "identity",
            "character_identity",
            "subject_identity",
            "subject",
            "species",
            "subspecies",
            "morphology",
            "anatomy",
            "body",
            "body_type",
            "build",
            "head",
            "head_shape",
            "face",
            "facial_structure",
            "marking",
            "markings",
            "coat",
            "fur",
            "hair",
            "mane",
            "tuft",
            "grooming",
            "surface",
            "surface_identity",
        }
    ),
    "pose-camera": frozenset(
        {
            "pose",
            "camera",
            "composition",
            "framing",
            "crop",
            "shot",
            "shot_type",
            "gesture",
            "movement",
            "staging",
            "viewpoint",
            "perspective",
            "body_language",
            "hand_placement",
            "leg_placement",
            "head_gaze",
        }
    ),
    "outfit": frozenset(
        {
            "outfit",
            "wardrobe",
            "garment",
            "garments",
            "clothing",
            "costume",
            "uniform",
            "armor",
            "wearable",
            "apparel",
        }
    ),
    "surface-finish": frozenset(
        {
            "surface",
            "surface_finish",
            "material",
            "materials",
            "material_response",
            "texture",
            "rendering",
            "rendering_medium",
            "finish",
            "roughness",
            "gloss",
            "specular",
            "sheen",
            "skin_detail",
            "coat_texture",
            "wetness",
        }
    ),
    "lighting": frozenset(
        {
            "lighting",
            "light",
            "lights",
            "light_sources",
            "illumination",
            "shadow",
            "shadows",
            "shadow_topology",
            "highlight",
            "highlights",
            "rim_light",
        }
    ),
    "environment": frozenset(
        {
            "environment",
            "background",
            "setting",
            "location",
            "world",
            "environment_geometry",
        }
    ),
    "prop-accessory": frozenset(
        {
            "prop",
            "props",
            "accessory",
            "accessories",
            "equipment",
            "item",
            "items",
            "object",
            "objects",
            "inventory",
            "weapon",
            "tool",
        }
    ),
    "local-color": frozenset(
        {
            "local_color",
            "color",
            "colors",
            "color_role",
            "palette",
            "hue",
            "coat_palette",
            "marking_color",
            "skin_tone",
            "hair_color",
        }
    ),
}

_SEMANTIC_TEXT_SIGNALS: dict[str, tuple[str, ...]] = {
    "identity": (
        "character identity",
        "subject identity",
        "species",
        "subspecies",
        "anatomy",
        "morphology",
        "body build",
        "body proportions",
        "head shape",
        "facial structure",
        "permanent marking",
        "fur pattern",
        "coat pattern",
        "hair style",
        "hairstyle",
        "mane",
        "fur tuft",
        "grooming topology",
    ),
    "pose-camera": (
        "pose",
        "camera",
        "framing",
        "crop",
        "composition",
        "gesture",
        "movement",
        "viewpoint",
        "perspective",
        "body language",
        "shot type",
    ),
    "outfit": (
        "outfit",
        "wardrobe",
        "garment",
        "clothing",
        "costume",
        "uniform",
        "armor",
        "wearable",
        "apparel",
        "blazer",
        "jacket",
        "shirt",
        "trousers",
        "dress",
    ),
    "surface-finish": (
        "surface finish",
        "material response",
        "material",
        "texture",
        "rendering medium",
        "roughness",
        "gloss",
        "specular",
        "sheen",
        "wetness",
    ),
    "lighting": (
        "lighting",
        "light source",
        "key light",
        "rim light",
        "illumination",
        "shadow",
        "highlight",
        "backlit",
    ),
    "environment": (
        "environment",
        "background",
        "setting",
        "location",
        "studio",
        "interior",
        "exterior",
        "street",
        "room",
        "forest",
        "landscape",
    ),
    "prop-accessory": (
        "prop",
        "accessory",
        "equipment",
        "inventory",
        "weapon",
        "tool",
    ),
    "local-color": (
        "local color",
        "local colour",
        "color palette",
        "colour palette",
        "palette relationship",
        "color region",
        "colour region",
        "hue relationship",
    ),
}

_NEGATIVE_SEMANTIC_BRANCHES = frozenset(
    {
        "failure",
        "failures",
        "failure_mode",
        "failure_modes",
        "misreading",
        "misreadings",
        "misreadings_to_avoid",
        "negative",
        "negative_prompt",
        "avoid",
        "forbidden",
        "unsupported",
        "unsupported_assumptions",
        "exclusion",
        "exclusions",
        "constraint",
        "constraints",
        "must_not",
        "do_not",
        "prohibited",
    }
)

_AFFIRMATIVE_TEXT_BRANCHES = frozenset(
    {
        "label",
        "tags",
        "search_terms",
        "defaults",
        "contracts",
        "contract",
        "invariants",
        "must_preserve",
        "visual_function",
        "image_promise",
        "prompt",
        "rendering",
        "positive_correction",
        "staging",
        "description",
    }
)

_GENERIC_IDENTITY_VALUES = frozenset(
    {
        "subject",
        "one subject",
        "the subject",
        "fixture subject",
        "one fixture subject",
        "character",
        "one character",
        "the character",
        "same character",
        "figure",
        "one figure",
        "person",
        "one person",
    }
)


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


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _normalized_semantic_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(character if character.isalnum() else "_" for character in text)
    return "_".join(part for part in normalized.split("_") if part)


def _semantic_text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.strip().lower().replace("_", "-").split())
    if isinstance(value, Mapping):
        return " ".join(_semantic_text(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return " ".join(_semantic_text(child) for child in value)
    return "" if value is None else str(value).strip().lower()


def _has_substantive_value(value: Any, *, intended_influence: str) -> bool:
    text = " ".join(_semantic_text(value).replace("-", " ").split())
    if not text:
        return False
    if intended_influence == "identity" and text in _GENERIC_IDENTITY_VALUES:
        return False
    return True


def _contains_semantic_signal(text: str, signal: str) -> bool:
    def words(value: str) -> str:
        return " ".join(
            "".join(character if character.isalnum() else " " for character in value)
            .lower()
            .split()
        )

    normalized_text = words(text)
    normalized_signal = words(signal)
    return bool(normalized_signal) and f" {normalized_signal} " in f" {normalized_text} "


def semantic_support_for_record(
    canonical_record: Any,
    intended_influence: str,
    *,
    record_kind: str | None = None,
) -> dict[str, Any]:
    """Return affirmative canonical-record evidence for one intended use.

    Kind is used only to make scene identity stricter; it never grants support.
    Category is intentionally absent from this API because routing metadata is
    not semantic authority.  Evidence comes from the complete active record.
    """

    if intended_influence not in INTENDED_INFLUENCES:
        raise ValueError(f"unsupported intended influence: {intended_influence!r}")
    if not isinstance(canonical_record, Mapping):
        return {
            "supported": False,
            "intended_influence": intended_influence,
            "evidence_paths": [],
            "reason": "canonical record must be an object",
        }

    field_signals = _SEMANTIC_FIELD_SIGNALS[intended_influence]
    text_signals = _SEMANTIC_TEXT_SIGNALS[intended_influence]
    evidence: list[tuple[str, bool]] = []

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                key = _normalized_semantic_key(raw_key)
                child_path = (*path, key or str(raw_key))
                if key in _NEGATIVE_SEMANTIC_BRANCHES:
                    continue
                if key in field_signals and _has_substantive_value(
                    child,
                    intended_influence=intended_influence,
                ):
                    evidence.append(("$." + ".".join(child_path), True))
                visit(child, child_path)
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, child in enumerate(value):
                visit(child, (*path, f"[{index}]"))
            return
        if not path or not isinstance(value, str) or not value.strip():
            return
        affirmative_branch = next(
            (part for part in path if part in _AFFIRMATIVE_TEXT_BRANCHES),
            None,
        )
        if affirmative_branch is None:
            return
        text = " ".join(_semantic_text(value).replace("-", " ").split())
        if any(_contains_semantic_signal(text, signal) for signal in text_signals):
            evidence.append(("$." + ".".join(path), False))

    visit(canonical_record, ())
    ordered_evidence = list(dict.fromkeys(path for path, _strong in evidence))
    strong_identity_evidence = any(strong for _path, strong in evidence)
    supported = bool(ordered_evidence)
    if str(record_kind or "") == "scene" and intended_influence == "identity":
        supported = strong_identity_evidence
    return {
        "supported": supported,
        "intended_influence": intended_influence,
        "evidence_paths": ordered_evidence,
        "reason": (
            "affirmative canonical-record evidence found"
            if supported
            else "no affirmative canonical-record semantic evidence"
        ),
    }


def require_record_semantic_support(
    canonical_record: Any,
    intended_influence: str,
    *,
    record_kind: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    """Raise when an intended influence exceeds active record semantics."""

    report = semantic_support_for_record(
        canonical_record,
        intended_influence,
        record_kind=record_kind,
    )
    if not report["supported"]:
        identity = str(record_id or "<unknown-record>")
        raise ValueError(
            f"canonical record {identity!r} does not affirmatively support "
            f"intended influence {intended_influence!r}"
        )
    return report


def normalize_selected_records(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("selected_records must be a non-empty JSON array")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or set(raw) != {"record_id", "intended_influence"}:
            raise ValueError(
                f"selected_records[{index}] must contain exactly record_id and intended_influence"
            )
        record_id = raw.get("record_id")
        influence = raw.get("intended_influence")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"selected_records[{index}].record_id must be a non-empty string")
        if influence not in INTENDED_INFLUENCES:
            raise ValueError(
                f"selected_records[{index}].intended_influence must be one of {list(INTENDED_INFLUENCES)}"
            )
        pair = (record_id, str(influence))
        if pair in seen:
            raise ValueError(f"selected_records[{index}] duplicates an earlier record use")
        seen.add(pair)
        normalized.append({"record_id": record_id, "intended_influence": str(influence)})
    return normalized


def technical_roles_for(intended_influence: str) -> tuple[str, ...]:
    if intended_influence not in INTENDED_INFLUENCES:
        raise ValueError(f"unsupported intended influence: {intended_influence!r}")
    return tuple(
        role
        for role in TECHNICAL_CAPABILITIES
        if (role, intended_influence) in _PAIR_CONTROLS
    )


def source_lighting_evidence_roles(
    reference_items: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Return traceable semantic roles that can support full source-light preservation."""

    return sorted(
        str(item.get("semantic_role") or "")
        for item in reference_items
        if item.get("intended_influence") == "lighting"
        and item.get("technical_role")
        in _COMPLETE_SOURCE_LIGHTING_TECHNICAL_ROLES
        and str(item.get("semantic_role") or "")
    )


def authority_for(technical_role: str, intended_influence: str) -> dict[str, list[str]]:
    controls = _PAIR_CONTROLS.get((technical_role, intended_influence))
    if controls is None:
        raise ValueError(
            f"technical role {technical_role!r} cannot serve intended influence "
            f"{intended_influence!r}"
        )
    exclusions = _unique(
        [
            "scene-conditioned presentation outside the declared intended influence",
            *_INFLUENCE_EXCLUSIONS[intended_influence],
            *_TECHNICAL_EXCLUSIONS[technical_role],
        ]
    )
    return {"controls": list(controls), "must_not_control": exclusions}


def state_authority_for(intended_influences: Sequence[str]) -> dict[str, list[str]]:
    if isinstance(intended_influences, (str, bytes)) or not isinstance(
        intended_influences, Sequence
    ):
        raise ValueError("state intended influences must be an array")
    influences = _unique([str(value) for value in intended_influences])
    if not influences or any(value not in INTENDED_INFLUENCES for value in influences):
        raise ValueError("state intended influences must use the canonical non-empty vocabulary")
    controls = _unique(
        [control for influence in influences for control in _INFLUENCE_CONTROLS[influence]]
    )
    exclusions = ["scene-conditioned presentation outside the declared intended influences"]
    for influence in influences:
        exclusions.extend(_INFLUENCE_EXCLUSIONS[influence])
    return {"controls": controls, "must_not_control": _unique(exclusions)}


def semantic_role_for(
    technical_role: str,
    intended_influence: str,
    precedence: int,
) -> str:
    if (technical_role, intended_influence) not in _PAIR_CONTROLS:
        authority_for(technical_role, intended_influence)
    if not isinstance(precedence, int) or isinstance(precedence, bool) or precedence < 0:
        raise ValueError("precedence must be a non-negative integer")
    return f"{intended_influence}-{technical_role}-{precedence + 1}"


def rule_for(technical_role: str, intended_influence: str) -> dict[str, Any]:
    authority = authority_for(technical_role, intended_influence)
    controls = "; ".join(authority["controls"])
    exclusions = "; ".join(authority["must_not_control"])
    return {
        "layer": _LAYERS[technical_role],
        "authority": authority,
        "preamble": (
            f"Use this {technical_role} only for {intended_influence}: {controls}. "
            f"It must not control {exclusions}."
        ),
    }


def build_reference_item(
    *,
    precedence: int,
    canonical_record_id: str,
    intended_influence: str,
    asset_id: str,
    artifact_id: str,
    technical_role: str,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(canonical_record_id, str) or not canonical_record_id:
        raise ValueError("canonical_record_id must be a non-empty string")
    if not isinstance(asset_id, str) or not asset_id:
        raise ValueError("asset_id must be a non-empty string")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("artifact_id must be a non-empty string")
    rule = rule_for(technical_role, intended_influence)
    return {
        "precedence": precedence,
        "semantic_role": semantic_role_for(technical_role, intended_influence, precedence),
        "layer": rule["layer"],
        "canonical_record_id": canonical_record_id,
        "intended_influence": intended_influence,
        "asset_id": asset_id,
        "artifact_id": artifact_id,
        "technical_role": technical_role,
        "source": copy.deepcopy(dict(source)),
        "authority": copy.deepcopy(rule["authority"]),
        "preamble": rule["preamble"],
    }


def build_surface_lighting_plan(
    *,
    source_lighting_mode: str,
    evidence_roles: Sequence[str],
    light_sources: Sequence[Mapping[str, Any]] = (),
    material_responses: Sequence[Mapping[str, Any]] = (),
    unresolved_decisions: Sequence[str] = (),
) -> dict[str, Any]:
    if source_lighting_mode not in {"preserve", "rescope", "replace"}:
        raise ValueError("source_lighting_mode must be preserve, rescope, or replace")
    roles = sorted(set(str(value) for value in evidence_roles if str(value)))
    lights = [copy.deepcopy(dict(value)) for value in light_sources]
    materials = [copy.deepcopy(dict(value)) for value in material_responses]
    unresolved = _unique([str(value) for value in unresolved_decisions])
    if source_lighting_mode == "preserve":
        prefix = "preserve source-supported"
        if not roles:
            unresolved.append(_MISSING_SOURCE_LIGHTING_REASON)
    else:
        prefix = "translate into target-scene" if source_lighting_mode == "rescope" else "use target-scene"
        if not lights:
            unresolved.append("target light sources are not defined")
        if not materials:
            unresolved.append("target material responses are not defined")
    unresolved = _unique(unresolved)
    raw = {
        "artifact_type": "surface-lighting-plan",
        "plan_id": _seed_id(
            "SLP",
            {
                "mode": source_lighting_mode,
                "roles": roles,
                "lights": lights,
                "materials": materials,
                "unresolved": unresolved,
            },
        ),
        "source_lighting_mode": source_lighting_mode,
        "source_evidence_roles": roles,
        "light_sources": lights,
        "shadow_topology": {
            "form_shadow": f"{prefix} form-shadow organization",
            "cast_shadow": f"{prefix} cast-shadow relationships",
            "contact_shadow": f"{prefix} contact shadows at actual support and overlap points",
            "ambient_occlusion": f"{prefix} restrained ambient occlusion at joints and contact seams",
            "edge_hardness": f"{prefix} shadow-edge hierarchy",
            "hue_shift": f"{prefix} shadow hue relationships",
            "occluder_receiver_rules": [],
        },
        "highlight_response": {
            "broad_sheen": f"{prefix} broad sheen by material",
            "hard_specular": f"{prefix} hard specular marks by material",
            "rim_light": f"{prefix} rim-light behavior only where declared",
            "lobe_width": f"{prefix} highlight-lobe width by material",
            "edge_character": f"{prefix} highlight-edge character",
            "reflection_tint": f"{prefix} reflection tint",
            "protected_highlight_islands": [],
        },
        "material_responses": materials,
        "unresolved_decisions": unresolved,
        "surface_lighting_plan_sha256": "0" * 64,
    }
    result = finalize_artifact(raw)
    report = validate_surface_lighting_plan(result)
    if not report["ok"]:
        raise ValueError("invalid surface-lighting plan: " + "; ".join(report["errors"]))
    return result


def validate_surface_lighting_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"ok": False, "errors": ["surface-lighting plan must be an object"]}
    report = validate_artifact(dict(value))
    errors = list(report.get("errors", []))
    if value.get("artifact_type") != "surface-lighting-plan":
        errors.append("artifact_type must be surface-lighting-plan")
    roles = value.get("source_evidence_roles")
    if isinstance(roles, list) and roles != sorted(roles):
        errors.append("source_evidence_roles must be sorted")
    mode = value.get("source_lighting_mode")
    unresolved = value.get("unresolved_decisions")
    unresolved_values = unresolved if isinstance(unresolved, list) else []
    if mode == "preserve" and not roles:
        if _MISSING_SOURCE_LIGHTING_REASON not in unresolved_values:
            errors.append(
                "preserve mode without complete lighting-authorized visual evidence "
                "must remain explicitly unresolved"
            )
    if mode in {"rescope", "replace"}:
        if not value.get("light_sources") and not any(
            "light source" in str(item) for item in unresolved_values
        ):
            errors.append("target light sources are neither defined nor explicitly unresolved")
        if not value.get("material_responses") and not any(
            "material response" in str(item) for item in unresolved_values
        ):
            errors.append("target material responses are neither defined nor explicitly unresolved")
    return {"ok": not errors, "errors": errors}


def _validate_zero_reason(
    value: Any,
    *,
    selected_record_ids: Sequence[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return ["zero_reference_reason must be an object when no reference item is selected"]
    if set(value) != {"code", "record_ids", "detail"}:
        errors.append("zero_reference_reason fields are invalid")
    if value.get("code") not in ZERO_REFERENCE_CODES:
        errors.append("zero_reference_reason.code is unsupported")
    record_ids = value.get("record_ids")
    if not isinstance(record_ids, list) or any(
        not isinstance(item, str) or not item for item in record_ids
    ):
        errors.append("zero_reference_reason.record_ids must be an array of non-empty strings")
    elif record_ids != list(dict.fromkeys(selected_record_ids)):
        errors.append("zero_reference_reason.record_ids must exactly cover selected record IDs")
    if not isinstance(value.get("detail"), str) or not value.get("detail"):
        errors.append("zero_reference_reason.detail must be a non-empty string")
    return errors


def validate_reference_use_plan_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"ok": False, "errors": ["reference-use plan must be an object"]}
    report = validate_artifact(dict(value))
    errors = list(report.get("errors", []))
    try:
        selected = normalize_selected_records(value.get("selected_records"))
    except ValueError as exc:
        selected = []
        errors.append(str(exc))
    selected_pairs = {
        (row["record_id"], row["intended_influence"])
        for row in selected
    }
    items = value.get("reference_items")
    if not isinstance(items, list):
        items = []
    precedence = [
        item.get("precedence") if isinstance(item, Mapping) else None
        for item in items
    ]
    if precedence != list(range(len(items))):
        errors.append("reference item precedence must be contiguous and ordered from zero")
    roles = [
        str(item.get("semantic_role") or "")
        for item in items
        if isinstance(item, Mapping)
    ]
    if len(roles) != len(set(roles)):
        errors.append("semantic roles must be unique; unnamed reference averaging is forbidden")
    represented: set[tuple[str, str]] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            errors.append(f"reference_items[{index}] must be an object")
            continue
        pair = (
            str(item.get("canonical_record_id") or ""),
            str(item.get("intended_influence") or ""),
        )
        if pair not in selected_pairs:
            errors.append(f"reference_items[{index}] is not authorized by selected_records")
        else:
            represented.add(pair)
        technical_role = str(item.get("technical_role") or "")
        try:
            expected_authority = authority_for(technical_role, pair[1])
            expected_role = semantic_role_for(technical_role, pair[1], index)
            expected_rule = rule_for(technical_role, pair[1])
        except ValueError as exc:
            errors.append(f"reference_items[{index}]: {exc}")
            continue
        if item.get("authority") != expected_authority:
            errors.append(f"reference_items[{index}].authority is not canonical")
        if item.get("semantic_role") != expected_role:
            errors.append(f"reference_items[{index}].semantic_role is not canonical")
        if item.get("layer") != expected_rule["layer"]:
            errors.append(f"reference_items[{index}].layer is not canonical")
        if item.get("preamble") != expected_rule["preamble"]:
            errors.append(f"reference_items[{index}].preamble is not canonical")
        source = item.get("source")
        if isinstance(source, Mapping):
            if source.get("asset_id") != item.get("asset_id"):
                errors.append(f"reference_items[{index}].asset_id differs from source")
            if source.get("artifact_id") != item.get("artifact_id"):
                errors.append(f"reference_items[{index}].artifact_id differs from source")
    zero_reason = value.get("zero_reference_reason")
    if items:
        if represented != selected_pairs:
            errors.append("every selected record use must be represented by a reference item")
        if zero_reason is not None:
            errors.append("zero_reference_reason must be null when references are selected")
    else:
        selected_ids = [row["record_id"] for row in selected]
        errors.extend(_validate_zero_reason(zero_reason, selected_record_ids=selected_ids))
        if isinstance(zero_reason, Mapping) and zero_reason.get("code") == "no-canonical-record-selected":
            errors.append("reference-use plans cannot use no-canonical-record-selected")
    surface_report = validate_surface_lighting_plan(value.get("surface_lighting_plan"))
    errors.extend(f"surface_lighting_plan: {item}" for item in surface_report["errors"])
    nested = value.get("surface_lighting_plan")
    if isinstance(nested, Mapping):
        expected_lighting_roles = source_lighting_evidence_roles(
            [item for item in items if isinstance(item, Mapping)]
        )
        if nested.get("source_evidence_roles") != expected_lighting_roles:
            errors.append(
                "surface_lighting_plan.source_evidence_roles must exactly match "
                "complete lighting-authorized reference item semantic roles"
            )
        if value.get("surface_lighting_plan_sha256") != nested.get(
            "surface_lighting_plan_sha256"
        ):
            errors.append("surface_lighting_plan_sha256 differs from the embedded plan")
    mode = value.get("transport_mode")
    target_model = value.get("target_model")
    if mode in MODEL_TRANSPORT_MODES and not isinstance(target_model, str):
        errors.append("model-facing transport requires target_model")
    if mode in PROMPT_TRANSPORT_MODES and target_model is not None:
        errors.append("prompt transport requires target_model to be null")
    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "reference_count": len(items),
    }


def finalize_reference_use_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("reference-use plan must be an object")
    result = copy.deepcopy(dict(value))
    nested = result.get("surface_lighting_plan")
    if not isinstance(nested, Mapping):
        raise ValueError("reference-use plan requires a surface-lighting plan")
    finalized_surface = finalize_artifact(dict(nested))
    surface_report = validate_surface_lighting_plan(finalized_surface)
    if not surface_report["ok"]:
        raise ValueError("invalid surface-lighting plan: " + "; ".join(surface_report["errors"]))
    result["surface_lighting_plan"] = finalized_surface
    result["surface_lighting_plan_sha256"] = finalized_surface[
        "surface_lighting_plan_sha256"
    ]
    result["reference_use_plan_sha256"] = "0" * 64
    finalized = finalize_artifact(result)
    report = validate_reference_use_plan_contract(finalized)
    if not report["ok"]:
        raise ValueError("invalid reference-use plan: " + "; ".join(report["errors"]))
    return finalized


__all__ = [
    "INTENDED_INFLUENCES",
    "MODEL_TRANSPORT_MODES",
    "PROMPT_TRANSPORT_MODES",
    "TECHNICAL_CAPABILITIES",
    "TRANSPORT_MODES",
    "ZERO_REFERENCE_CODES",
    "authority_for",
    "build_reference_item",
    "build_surface_lighting_plan",
    "finalize_reference_use_plan",
    "normalize_selected_records",
    "require_record_semantic_support",
    "rule_for",
    "semantic_support_for_record",
    "semantic_role_for",
    "source_lighting_evidence_roles",
    "state_authority_for",
    "technical_roles_for",
    "validate_reference_use_plan_contract",
    "validate_surface_lighting_plan",
]
