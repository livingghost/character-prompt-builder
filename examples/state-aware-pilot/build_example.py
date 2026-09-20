#!/usr/bin/env python3
"""Rebuild the canonical Shared State Protocol pilot deterministically.

The builder consumes the checked-in identity, event, process, scene, projection,
and render requests. With no output argument it cleanly replaces only this
pilot's canonical generated tree. The public build(output_dir) and --out-dir
interfaces atomically install into an absent or empty custom directory and
preserve every non-empty caller-owned directory. No generated media quality is
claimed.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
CANONICAL_GENERATED = EXAMPLE / "generated"
sys.path.insert(0, str(ROOT / "scripts"))

from build_asset_render_spec import build_render_spec  # noqa: E402
from build_reference_bundle import build_plan  # noqa: E402
from build_state_generation_package import build_package  # noqa: E402
from prepare_generation_references import build_prepared_reference_set  # noqa: E402
from production_spec import validate as validate_production_spec  # noqa: E402
from state_protocol import (  # noqa: E402
    artifact_hash,
    build_projection,
    build_scene_context,
    extract_character_snapshot,
    finalize_artifact,
    load_json,
    load_jsonl,
    propose_environment_adaptations,
    resolve_world,
    resolve_growth_geometry,
    validate_artifact,
    write_json,
)
from verify_generation_payload import verify  # noqa: E402
from catalog_cli import configure_pack_runtime  # noqa: E402
from pack_manager import default_settings  # noqa: E402
from prompt_plot import content_sha256

COMMONS_PACK_ID = "01a0043b-2250-720d-87b7-f1e6fd7ed230"
DEFAULT_STYLE_FAMILY_ID = "style-family-clear-portrait"
DEFAULT_DOMAIN_REALIZATION_ID = "domain-realization-anthropomorphic-animal-baseline"
DEFAULT_RENDER_PROFILE_ID = "profile-clear-2d-illustration"
DEFAULT_ONLY_CANONICAL_RECORD_IDS = (
    DEFAULT_STYLE_FAMILY_ID,
    DEFAULT_DOMAIN_REALIZATION_ID,
    DEFAULT_RENDER_PROFILE_ID,
)

PROMPT = (
    "Create a polished cinematic 2D soft-cel office portrait of a tall broad-shouldered "
    "blue-gray anthropomorphic wolf in a left three-quarter medium close view. Preserve the "
    "long canine muzzle, thick charcoal brows, electric-cyan eyes, pale muzzle and chest, "
    "paired charcoal cheek wedges, one small cyan stud on the subject-left upper ear rim, "
    "and one healed triangular notch on the outer upper subject-left ear tip. He wears a dry "
    "closed field-office shirt and braces his left hand against the desk edge. His face presents "
    "controlled professional calm while shallow breathing, slight temple sweat, and tension "
    "concentrated in the left hand reveal stronger fear. He looks toward a trusted colleague "
    "and then briefly away, close but not touching. Use warm window light with cool neutral "
    "office fill, crisp facial markings, restrained soft modeling on broad fur and shoulder "
    "planes, and a quiet field-office background. Keep the transferred silver pendant absent "
    "from him because it is now carried by the colleague."
)

NEGATIVE = (
    "photorealistic rendering, 3D render, swapped left and right details, missing ear stud, "
    "intact left ear tip, extra pendant on the wolf, fused desk and hand, unreadable facial markings"
)

INTEGRATED_PROMPT = (
    "Create a polished cinematic 2D soft-cel office portrait of a tall broad-shouldered "
    "blue-gray anthropomorphic wolf in a left three-quarter medium close view. Preserve the "
    "long canine muzzle, thick charcoal brows, electric-cyan eyes, pale muzzle and chest, "
    "paired charcoal cheek wedges, one small cyan stud on the subject-left upper ear rim, "
    "and one healed triangular notch on the outer upper subject-left ear tip. He wears a dry "
    "closed field-office shirt and braces his clearly separated left hand against the desk edge. "
    "His face presents controlled professional calm while shallow breathing, slight temple sweat, "
    "and tension concentrated in the left hand reveal stronger fear. He looks toward a trusted "
    "colleague and then briefly away, close but not touching. Use a clearly illustrated soft-cel "
    "medium with stable left-right identity, clean anatomical hand-to-desk contact, crisp facial "
    "markings, warm window light, cool neutral office fill, and restrained soft modeling. The "
    "silver pendant belongs to the colleague and the wolf's neck and shirt remain visibly free "
    "of that pendant."
)


PLOT = {
    "artifact_type": "prompt-plot",
    "story": [
        {"id": "s1", "beat": "The character is rendered in the approved scene state.", "visibility": "visible"},
        {"id": "s2", "beat": "The events that produced that state happened before this image.", "visibility": "context"},
    ],
    "derived": [
        {"kind": "shows", "statement": "the character in the declared scene", "from": ["s1"]},
        {"kind": "placement", "statement": "the character stands in the declared position", "from": ["s1"]},
        {"kind": "composition", "statement": "the camera and framing the production specification declares", "from": ["s1"]},
        {"kind": "must_preserve", "statement": "every feature the identity contract fixes", "from": ["s1"]},
        {"kind": "free", "statement": "incidental light variation within the declared lighting"},
    ],
}
PLOT["approved"] = {
    "by": "the person who owns the brief",
    "at": "2026-09-11T00:00:00Z",
    "content_sha256": content_sha256(PLOT),
}

def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def checked_artifact(value: dict[str, Any], expected_type: str) -> dict[str, Any]:
    if value.get("artifact_type") != expected_type:
        raise ValueError(f"expected artifact_type {expected_type}, got {value.get('artifact_type')}")
    report = validate_artifact(value)
    if not report.get("ok"):
        raise ValueError(f"invalid {expected_type}: " + "; ".join(report.get("errors", [])))
    return value


def build_production_spec(
    *,
    identity: dict[str, Any],
    species_profile: dict[str, Any],
    individual_morphology: dict[str, Any],
    state: dict[str, Any],
    context: dict[str, Any],
    projection: dict[str, Any],
    lineage: dict[str, Any],
    render_request: dict[str, Any],
) -> dict[str, Any]:
    stable = copy.deepcopy(identity["stable_identity"])
    current_state = {
        "physical_state": copy.deepcopy(state["physical_state"]),
        "appearance_state": copy.deepcopy(state["appearance_state"]),
        "wardrobe_state": copy.deepcopy(state["wardrobe_state"]),
        "emotional_state": copy.deepcopy(state["emotional_state"]),
        "performance_state": copy.deepcopy(state["performance_state"]),
    }
    spec = {
        "source_brief": "State-aware field-office scene after an offscreen ear injury and a prop transfer.",
        "target_model": "gpt-image-2.5-flare",
        "creative_latitude": "directed",
        "image_promise": (
            "A polished close office portrait in which a familiar wolf maintains professional "
            "composure while subtle physical cues reveal fear, and every visible identity and "
            "state change matches the canonical timeline."
        ),
        "art_direction": copy.deepcopy(render_request["art_direction"]),
        "state_context": {
            "mode": "state-aware",
            "state_lineage_sha256": lineage["lineage_sha256"],
            "scene_context_ref": {
                "id": context["scene_context_id"],
                "sha256": context["context_snapshot_sha256"],
            },
            "notes": ["Compiled from approved state events at story order 25."],
        },
        "subjects": [
            {
                "id": identity["character_id"],
                "domain": identity["domain"],
                "species_morphology_profile_ref": {
                    "id": species_profile["profile_id"],
                    "sha256": species_profile["species_profile_sha256"],
                },
                "individual_morphology_contract_ref": {
                    "id": individual_morphology["contract_id"],
                    "sha256": individual_morphology["individual_morphology_sha256"],
                },
                "identity_contract_ref": {
                    "id": identity["contract_id"],
                    "sha256": artifact_hash(identity),
                },
                "resolved_morphology": copy.deepcopy(projection["resolved_morphology"]),
                "frame_character": copy.deepcopy(projection["resolved_morphology"]["frame_character"]),
                "load_bearing_part_measurements": copy.deepcopy(projection["resolved_morphology"]["load_bearing_part_measurements"]),
                "accessory_geometry": [
                {
                                "accessory_id": "C01-cyan-ear-stud",
                                "item_class": "small circular ear stud",
                                "count": 1,
                                "laterality_or_site": "subject-left upper ear rim",
                                "body_landmarks": [
                                                "subject-left ear base",
                                                "subject-left upper rim",
                                                "subject-left ear tip"
                                ],
                                "support_and_fastening": "one short post passes through the declared rim site",
                                "orientation": "stud face lies approximately parallel to the local outer ear surface",
                                "relative_dimensions": {
                                                "length": "short post contained within the ear thickness",
                                                "width": "stud face about one tenth of ear height",
                                                "thickness": "compact hard stud with a shallow face",
                                                "diameter_or_span": "about one tenth of subject-left ear height",
                                                "measurement_basis": "visible subject-left ear height and upper-rim thickness"
                                },
                                "repeated_elements": {
                                                "unit_size": "not applicable; one stud",
                                                "spacing": "not applicable; single item",
                                                "count_logic": "exactly one stud"
                                },
                                "shape_and_construction": "one compact circular stud face on one short post",
                                "material_and_finish": "polished metal or enamel with one compact highlight",
                                "color": "electric cyan independent of lighting",
                                "layer_order": "attached to and crossing the outer ear rim, outside the fur surface",
                                "body_and_garment_clearance": "clears ear fur and any collar or headwear",
                                "contact_and_pose_response": "moves rigidly with the ear and does not float when the ear rotates",
                                "articulation_and_mobility": "no independent articulation beyond the ear movement",
                                "visibility_and_occlusion": "must remain visible in left three-quarter and left-profile identity views unless deliberately occluded",
                                "continuity_rules": [
                                                "one stud remains on subject-left only",
                                                "stud scale and cyan color remain stable"
                                ],
                                "diagnostic_misreadings": [
                                                "stud mirrored to subject-right",
                                                "stud duplicated into a pair",
                                                "stud replaced by a hoop or floating dot"
                                ],
                                "source_confidence": "reference-clear"
                }
],
                "state_snapshot_ref": {
                    "id": state["snapshot_id"],
                    "sha256": state["state_snapshot_sha256"],
                },
                "visual_projection_ref": {
                    "id": projection["projection_id"],
                    "sha256": projection["projection_sha256"],
                },
                "identity": stable,
                "current_state": current_state,
                "proportions_and_form": (
                    "tall broad-shouldered wolf with a compact waist and stable upright canine body plan"
                ),
                "head_and_face": (
                    "long canine muzzle, thick angular brows, cyan eyes, upright ears, dense cheek ruff"
                ),
                "surfaces_and_markings": (
                    "blue-gray coat, pale muzzle and chest, paired charcoal cheek wedges"
                ),
                "distinctive_details": copy.deepcopy(identity.get("distinctive_details", [])),
                "performance": {
                    "felt_emotion": [
                        "strong fear",
                        "heat discomfort"
                    ],
                    "displayed_emotion": [
                        "professional composure",
                        "controlled calm"
                    ],
                    "masked_or_conflicted_emotion": [
                        "professional composure masking stronger fear"
                    ],
                    "intent": [
                        "maintain professional composure while privately responding to C02"
                    ],
                    "viewer_or_partner_relationship": [
                        "private close interaction with C02 without physical contact"
                    ],
                    "intensity": "moderate",
                    "temporal_phase": "held",
                    "channel_cues": [
                        {
                            "cue_id": "performance-gaze-c02",
                            "channel": "gaze",
                            "observation": "C01 looks toward C02 and then briefly away.",
                            "visual_instruction": "Aim the eyes toward C02 with a small evasive break in the held gaze.",
                            "laterality": "bilateral",
                            "intensity": "subtle",
                            "direction_or_target": "C02, followed by a brief off-target glance",
                            "visibility": "visible",
                            "evidence_status": "state-derived",
                            "confidence": "high",
                            "stability": "transient-action"
                        },
                        {
                            "cue_id": "performance-ears-before-head",
                            "channel": "ears",
                            "observation": "The ears react before the head turns.",
                            "visual_instruction": "Show a slight anticipatory ear rotation while the head remains more controlled.",
                            "laterality": "bilateral",
                            "intensity": "subtle",
                            "direction_or_target": "C02 before the head completes its response",
                            "visibility": "visible",
                            "evidence_status": "state-derived",
                            "confidence": "high",
                            "stability": "transient-action"
                        },
                        {
                            "cue_id": "performance-shallow-breath",
                            "channel": "breath-voice",
                            "observation": "Breathing remains shallow under the composed exterior.",
                            "visual_instruction": "Keep the chest and throat movement restrained, with only a slight held-breath tension.",
                            "laterality": "centerline",
                            "intensity": "subtle",
                            "direction_or_target": "upper chest and throat",
                            "visibility": "visible",
                            "evidence_status": "state-derived",
                            "confidence": "high",
                            "stability": "current-state"
                        },
                        {
                            "cue_id": "performance-left-hand-tension",
                            "channel": "arms-hands-manipulators",
                            "observation": "Tension concentrates in the subject-left hand braced on the desk edge.",
                            "visual_instruction": "Show controlled finger and tendon tension while preserving the complete desk-support contact chain.",
                            "laterality": "left",
                            "intensity": "moderate",
                            "direction_or_target": "desk edge",
                            "visibility": "visible",
                            "evidence_status": "state-derived",
                            "confidence": "high",
                            "stability": "current-state"
                        },
                        {
                            "cue_id": "performance-temple-sweat",
                            "channel": "physiology",
                            "observation": "Light sweat appears at the temples in the hot humid office.",
                            "visual_instruction": "Render sparse small perspiration at the temples as an environment response, not a stable identity mark.",
                            "laterality": "bilateral",
                            "intensity": "subtle",
                            "direction_or_target": "both temples",
                            "visibility": "visible",
                            "evidence_status": "state-derived",
                            "confidence": "high",
                            "stability": "environment-response"
                        }
                    ],
                    "interpretation_candidates": [
                        {
                            "meaning": "professional composure is containing stronger private fear",
                            "supported_by": [
                                "performance-gaze-c02",
                                "performance-ears-before-head",
                                "performance-shallow-breath",
                                "performance-left-hand-tension"
                            ],
                            "context": "C01 is close to C02 in a private office exchange after the approved injury and prop-transfer events.",
                            "confidence": "high",
                            "content_intensity": "general"
                        },
                        {
                            "meaning": "part of the visible strain is a physiological response to heat and humidity",
                            "supported_by": [
                                "performance-temple-sweat"
                            ],
                            "context": "The approved environment snapshot is hot and humid.",
                            "confidence": "high",
                            "content_intensity": "general"
                        }
                    ],
                    "selected_interpretation": {
                        "meaning": "professional composure masks stronger private fear while heat adds a separate mild physiological response",
                        "supported_by": [
                            "performance-gaze-c02",
                            "performance-ears-before-head",
                            "performance-shallow-breath",
                            "performance-left-hand-tension",
                            "performance-temple-sweat"
                        ],
                        "context": "The scene combines a private exchange with C02 and an approved hot humid environment.",
                        "confidence": "high",
                        "content_intensity": "general"
                    },
                    "ambiguity_notes": [
                        "Keep environment-caused perspiration separate from fear cues and from stable identity."
                    ],
                    "prompt_projection": {
                        "primary_clause": "professional composure masking stronger fear, with ears reacting before the head, a brief evasive gaze break, shallow breath, and tension concentrated in the desk-braced subject-left hand",
                        "supporting_clauses": [
                            "light bilateral temple sweat from the hot humid office"
                        ],
                        "search_facets": [
                            "masked fear",
                            "controlled composure",
                            "evasive gaze",
                            "ear-led reaction",
                            "shallow breath",
                            "tense braced hand",
                            "heat perspiration"
                        ],
                        "review_checks": [
                            "The gaze target remains C02 rather than the viewer.",
                            "Fear is carried by coordinated transient cues rather than a generic frightened face.",
                            "Perspiration remains sparse, environment-caused, and non-identifying.",
                            "The subject-left hand keeps valid contact with the desk edge."
                        ]
                    }
                },
                "wardrobe_and_accessories": (
                    "closed dry field-office shirt; cyan stud on the subject-left upper ear rim"
                ),
                "growth_geometry": resolve_growth_geometry(identity, state_snapshot=state),
                "garment_geometry": [
                    {'representation': 'declared-structures',
                     'structures': {'garment-construction': {'kind': 'closed field-office shirt',
                                                             'location': 'declared garment coverage',
                                                             'presence': 'present',
                                                             'geometry': {'layer_order': '1',
                                                                          'wear_state': 'worn',
                                                                          'fit_profile': 'tailored across '
                                                                                         'the shoulders and '
                                                                                         'chest with enough '
                                                                                         'ease for '
                                                                                         'desk-braced arms',
                                                                          'material_and_thickness': 'midweight '
                                                                                                    'matte '
                                                                                                    'woven '
                                                                                                    'cloth '
                                                                                                    'with '
                                                                                                    'crisp '
                                                                                                    'but '
                                                                                                    'flexible '
                                                                                                    'seams',
                                                                          'color_and_pattern': 'neutral '
                                                                                               'field-office '
                                                                                               'color with '
                                                                                               'no copied '
                                                                                               'logo or '
                                                                                               'insignia',
                                                                          'upper_edge_and_neckline': 'closed '
                                                                                                     'shirt '
                                                                                                     'neckline '
                                                                                                     'beneath '
                                                                                                     'a '
                                                                                                     'structured '
                                                                                                     'collar',
                                                                          'collar_or_hood_attachment': 'two '
                                                                                                       'collar '
                                                                                                       'points '
                                                                                                       'attach '
                                                                                                       'to '
                                                                                                       'the '
                                                                                                       'neckline '
                                                                                                       'and '
                                                                                                       'remain '
                                                                                                       'outside '
                                                                                                       'the '
                                                                                                       'neck '
                                                                                                       'fur',
                                                                          'shoulder_support': 'shoulder '
                                                                                              'seams follow '
                                                                                              'the shoulder '
                                                                                              'caps and '
                                                                                              'connect '
                                                                                              'cleanly to '
                                                                                              'the sleeves',
                                                                          'sleeve_or_armhole_geometry': 'set-in '
                                                                                                        'sleeves '
                                                                                                        'encircle '
                                                                                                        'the '
                                                                                                        'upper '
                                                                                                        'arms '
                                                                                                        'without '
                                                                                                        'cutting '
                                                                                                        'into '
                                                                                                        'the '
                                                                                                        'armpits',
                                                                          'side_panel_and_side_opening': 'continuous '
                                                                                                         'side '
                                                                                                         'seams '
                                                                                                         'cover '
                                                                                                         'the '
                                                                                                         'lateral '
                                                                                                         'torso',
                                                                          'front_panel_extent': 'two front '
                                                                                                'panels '
                                                                                                'cover the '
                                                                                                'chest and '
                                                                                                'abdomen and '
                                                                                                'meet at the '
                                                                                                'center '
                                                                                                'closure',
                                                                          'back_panel_extent': 'one '
                                                                                               'continuous '
                                                                                               'back panel '
                                                                                               'spans the '
                                                                                               'shoulder '
                                                                                               'blades and '
                                                                                               'waist',
                                                                          'hem_or_lower_edge': 'lower hem '
                                                                                               'continues '
                                                                                               'below the '
                                                                                               'crop and '
                                                                                               'remains '
                                                                                               'aligned with '
                                                                                               'the torso',
                                                                          'closure_and_fasteners': 'center-front '
                                                                                                   'closure '
                                                                                                   'remains '
                                                                                                   'shut and '
                                                                                                   'vertically '
                                                                                                   'aligned',
                                                                          'front_coverage': 'chest and '
                                                                                            'abdomen remain '
                                                                                            'fully covered',
                                                                          'side_coverage': 'lateral chest '
                                                                                           'and ribs remain '
                                                                                           'covered by '
                                                                                           'continuous '
                                                                                           'panels',
                                                                          'rear_coverage': 'back and '
                                                                                           'shoulder blades '
                                                                                           'remain covered',
                                                                          'anatomy_and_appendage_clearance': 'collar '
                                                                                                             'clears '
                                                                                                             'neck '
                                                                                                             'fur; '
                                                                                                             'sleeves '
                                                                                                             'clear '
                                                                                                             'elbow '
                                                                                                             'flexion; '
                                                                                                             'tail '
                                                                                                             'remains '
                                                                                                             'outside '
                                                                                                             'the '
                                                                                                             'shirt',
                                                                          'pose_response': 'desk-braced arm '
                                                                                           'tension creates '
                                                                                           'diagonal folds '
                                                                                           'from shoulder to '
                                                                                           'chest and elbow',
                                                                          'support_surface_response': 'the '
                                                                                                      'lower '
                                                                                                      'sleeve '
                                                                                                      'and '
                                                                                                      'cuff '
                                                                                                      'may '
                                                                                                      'compress '
                                                                                                      'against '
                                                                                                      'the '
                                                                                                      'desk '
                                                                                                      'while '
                                                                                                      'the '
                                                                                                      'cloth '
                                                                                                      'edge '
                                                                                                      'remains '
                                                                                                      'separate',
                                                                          'tension_drape_and_wrinkles': 'shallow '
                                                                                                        'tension '
                                                                                                        'lines '
                                                                                                        'radiate '
                                                                                                        'from '
                                                                                                        'the '
                                                                                                        'braced '
                                                                                                        'shoulder, '
                                                                                                        'elbow, '
                                                                                                        'and '
                                                                                                        'center '
                                                                                                        'closure'}}},
                     'source_confidence': 'preset-selected',
                     'garment_id': 'C01-office-shirt',
                     'garment_class': 'closed field-office shirt',
                     'coverage': 'coverage defined by the declared construction',
                     'continuity_rules': ['center closure stays shut',
                                          'collar points remain attached and symmetrical in neutral pose',
                                          'sleeves remain separate from forearms and desk',
                                          'shirt remains a woven layer rather than body paint']}
                ],
                "pose_and_body_geometry": (
                    "upright medium-close three-quarter office portrait with left hand braced on the desk edge"
                ),
                "hands": (
                    "left hand carries the visible tension and remains fully attached to the desk-support chain"
                ),
                "legs_and_feet": "outside the crop",
                "gaze_and_head": (
                    "looks toward C02, then briefly away, with the subject-left ear visible"
                ),
                "props_and_contacts": (
                    "desk edge supports the left hand; the transferred pendant is possessed by C02 "
                    "and does not appear on C01"
                ),
            }
        ],
        "scene": copy.deepcopy(render_request["scene"]),
        "camera": copy.deepcopy(render_request["camera"]),
        "lighting": copy.deepcopy(render_request["lighting"]),
        "visual_language": {
            "aesthetic_core": None,
            "style_family": DEFAULT_STYLE_FAMILY_ID,
            "domain_realizations": {
                "anthropomorphic-animal": DEFAULT_DOMAIN_REALIZATION_ID
            },
            "render_profile": DEFAULT_RENDER_PROFILE_ID,
            "aesthetic_touches": [],
        },
        "constraints": {
            "user_anchors": [
                "subject-left cyan ear stud",
                "healed left ear-tip notch",
                "cyan eyes",
                "paired cheek wedges",
            ],
            "purposeful_additions": [
                "subtle heat response from the approved environment snapshot"
            ],
            "consequential_assumptions": [],
            "construction_invariants": [
                "left-right identity remains stable",
                "desk-hand support remains continuous",
                "the pendant is absent from C01 after the atomic transfer",
            ],
        },
        "selected_preset_ids": list(DEFAULT_ONLY_CANONICAL_RECORD_IDS),
    }
    report = validate_production_spec(spec, require_content=True)
    if not report.get("ok"):
        raise ValueError("invalid generated production specification: " + "; ".join(report["errors"]))
    return spec


def _build_into(output_dir: Path) -> list[Path]:
    """Build the pilot with the pack runtime pinned to the tracked commons pack.

    The deterministic pilot must resolve identically on machines with private
    packs enabled and in clean environments: ``model="gpt-image-2.5-flare"`` resolves
    through the commons alias to the same canonical record everywhere.
    """

    with tempfile.TemporaryDirectory(prefix="cpb-pilot-runtime-") as workspace:
        root = Path(workspace)
        configure_pack_runtime(
            default_settings(
                state_file=root / "pack-state.json",
                cache_dir=root / "cache",
                default_enabled_packs=[COMMONS_PACK_ID],
            )
        )
        try:
            return _build_into_pinned(output_dir)
        finally:
            configure_pack_runtime(None)


def _build_into_pinned(output_dir: Path) -> list[Path]:
    generated = Path(output_dir).resolve()
    if generated.exists() and not generated.is_dir():
        raise ValueError(f"output path exists and is not a directory: {generated}")
    generated.mkdir(parents=True, exist_ok=True)

    species_profile = checked_artifact(load_json(EXAMPLE / "species-morphology-profile.json"), "species-morphology-profile")
    individual_morphology = checked_artifact(load_json(EXAMPLE / "individual-morphology-contract.json"), "individual-morphology-contract")
    identity = checked_artifact(load_json(EXAMPLE / "character-identity-contract.json"), "character-identity-contract")
    if individual_morphology["species_profile_ref"] != {"id": species_profile["profile_id"], "sha256": species_profile["species_profile_sha256"]}:
        raise ValueError("pilot individual morphology does not bind the pilot species profile")
    if identity["species_morphology_profile_ref"] != {"id": species_profile["profile_id"], "sha256": species_profile["species_profile_sha256"]}:
        raise ValueError("pilot identity does not bind the pilot species profile")
    if identity["individual_morphology_contract_ref"] != {"id": individual_morphology["contract_id"], "sha256": individual_morphology["individual_morphology_sha256"]}:
        raise ValueError("pilot identity does not bind the pilot individual morphology")
    state_schema = checked_artifact(load_json(EXAMPLE / "character-state-schema.json"), "character-state-schema")
    environment = checked_artifact(load_json(EXAMPLE / "environment-snapshot.json"), "environment-snapshot")
    base_state = load_json(EXAMPLE / "world-state-base.json")
    events = load_jsonl(EXAMPLE / "events.jsonl")
    processes_raw = json.loads((EXAMPLE / "processes.json").read_text(encoding="utf-8"))
    if not isinstance(processes_raw, list):
        raise ValueError("processes.json must contain an array")
    processes = [checked_artifact(item, "state-process") for item in processes_raw]

    world = resolve_world(
        base_state=base_state,
        events=events,
        processes=processes,
        timeline_id="main",
        story_order=25,
        story_time="story:EP03-SC01",
        snapshot_id="WORLD-main-25",
        scene_context_id="SC-EP03-01",
    )
    write_json(generated / "world-state-snapshot.json", world)

    state = extract_character_snapshot(
        world,
        character_id="C01",
        species_profile_hash=species_profile["species_profile_sha256"],
        individual_morphology_hash=individual_morphology["individual_morphology_sha256"],
        identity_hash=artifact_hash(identity),
        era_hash=None,
        form_hash=None,
        appearance_hash=None,
        snapshot_id="C01-main-25",
    )
    write_json(generated / "state-snapshot-C01.json", state)

    context_request = load_json(EXAMPLE / "scene-context-request.json")
    context = build_scene_context(context_request, world, [state])
    write_json(generated / "scene-context-snapshot.json", context)

    projection_request = load_json(EXAMPLE / "projection-request.json")
    projection = build_projection(identity, species_profile, individual_morphology, state, context, projection_request, None)
    write_json(generated / "visual-state-projection.json", projection)

    adaptation = propose_environment_adaptations(
        state_schema,
        environment,
        character_id="C01",
        proposal_id="ADAPT-EP03-SC01-C01",
    )
    write_json(generated / "appearance-adaptation-proposal.json", adaptation)

    render_request = load_json(EXAMPLE / "render-spec-request.json")
    render_spec = build_render_spec(
        request=render_request,
        identity_contract=identity,
        species_profile=species_profile,
        individual_morphology=individual_morphology,
        state_snapshot=state,
        visual_projection=projection,
    )
    write_json(generated / "asset-render-specification.json", render_spec)

    lineage = finalize_artifact(
        {
                "artifact_type": "state-lineage",
            "mode": "state-aware",
            "species_profile_sha256": species_profile["species_profile_sha256"],
            "individual_morphology_sha256": individual_morphology["individual_morphology_sha256"],
            "identity_contract_sha256": artifact_hash(identity),
            "era_contract_sha256": None,
            "form_contract_sha256": None,
            "appearance_variant_sha256": None,
            "state_snapshot_sha256": state["state_snapshot_sha256"],
            "scene_context_sha256": context["context_snapshot_sha256"],
            "visual_projection_sha256": projection["projection_sha256"],
            "asset_render_spec_sha256": render_spec["render_spec_sha256"],
            "visual_authority_sha256": None,
            "visual_evidence_bundle_sha256": None,
            "lineage_sha256": "0" * 64,
        }
    )
    checked_artifact(lineage, "state-lineage")
    write_json(generated / "state-lineage.json", lineage)

    production_spec = build_production_spec(
        identity=identity,
        species_profile=species_profile,
        individual_morphology=individual_morphology,
        state=state,
        context=context,
        projection=projection,
        lineage=lineage,
        render_request=render_request,
    )
    write_json(generated / "production-specification.json", production_spec)

    creative_intent = {
        "image_promise": production_spec["image_promise"],
        "chosen_direction": "polished state-aware office tension portrait",
        "medium_family": "cinematic 2D soft-cel anime illustration",
        "purposeful_additions": ["approved heat-response cues"],
        "aesthetic_core": None,
        "style_family": DEFAULT_STYLE_FAMILY_ID,
        "domain_realizations": {
            "anthropomorphic-animal": DEFAULT_DOMAIN_REALIZATION_ID
        },
        "render_profile": DEFAULT_RENDER_PROFILE_ID,
        "selected_preset_ids": copy.deepcopy(production_spec["selected_preset_ids"]),
    }
    negative_provenance = {
        "activated_sources": [
            "style-family:polished-soft-cel",
            "state-integrity:left-right",
            "state-integrity:prop-ownership",
        ],
        "diagnostic_sources_retained": [],
        "semantic_exclusions_user_supplied": [],
        "affirmative_translations": {
            "state-integrity:left-right": "stable left-right identity",
            "state-integrity:prop-ownership": (
                "the wolf's neck and shirt remain visibly free of that pendant"
            ),
        },
    }
    write_json(generated / "creative-intent.json", creative_intent)
    write_json(generated / "negative-provenance.json", negative_provenance)
    write_text(generated / "prompt.txt", PROMPT)
    write_text(generated / "negative.txt", NEGATIVE)
    write_text(generated / "integrated-prompt.txt", INTEGRATED_PROMPT)

    reference_selection = finalize_artifact(
        {
            "artifact_type": "reference-selection",
            "selection_id": f"SEL-C01-{context['scene_context_id']}",
            "identity_contract_sha256": artifact_hash(identity),
            "era_contract_sha256": None,
            "appearance_variant_sha256": None,
            "state_snapshot_sha256": artifact_hash(state),
            "story_order": state["story_order"],
            "required_state_features": [],
            "selected_references": [],
            "unresolved_requirements": [],
            "selection_sha256": "0" * 64,
        }
    )
    checked_artifact(reference_selection, "reference-selection")
    prepared_reference_set = build_prepared_reference_set(
        transport_mode="none",
        target_model=None,
        reference_selection=reference_selection,
        zero_reference_reason={
            "code": "no-canonical-record-selected",
            "record_ids": [],
            "detail": (
                "This deterministic state-aware pilot selects no canonical record-scoped "
                "visual reference; its full identity and scene contracts remain authoritative."
            ),
        },
    )
    write_json(generated / "reference-selection.json", reference_selection)
    write_json(generated / "prepared-reference-set.json", prepared_reference_set)

    write_json(generated / "prompt-plot.json", PLOT)
    from prompt_retrieval import settle_retrieval_record
    retrieval = settle_retrieval_record({
        "artifact_type": "prompt-retrieval-record", "pack_state": "illustrative-offline-pilot",
        "elements": [{"element": "illustrative pilot composition", "queries": ["state-aware pilot composition"],
                      "inspected_records": [], "outcome": "composed", "composed_wording": PROMPT,
                      "reason": "Illustrative deterministic fixture, not evidence of a production retrieval session."}],
    }, prompt=PROMPT, plot=PLOT)
    write_json(generated / "prompt-retrieval-record.json", retrieval)


    payload = build_package(
        model="gpt-image-2.5-flare",
        plot=PLOT,
        retrieval_record=retrieval,
        prompt=PROMPT,
        negative_prompt=NEGATIVE,
        integrated_prompt=INTEGRATED_PROMPT,
        native_negative="",
        negative_provenance=negative_provenance,
        brief=production_spec["source_brief"],
        creative_intent=creative_intent,
        production_spec=production_spec,
        state_lineage=lineage,
        species_profile=species_profile,
        individual_morphology=individual_morphology,
        identity_contract=identity,
        state_snapshot=state,
        scene_context=context,
        visual_projection=projection,
        asset_render_spec=render_spec,
        prepared_reference_set=prepared_reference_set,
        parameters={"size": "1024x1024", "quality": "high"},
        negative_transport="integrated-critical",
        critical_avoidance_integrated=False,
    )
    write_json(generated / "generation-package.json", payload)
    verification = verify(payload)
    if verification.get("verified") is not True:
        raise ValueError("generated package verification failed: " + "; ".join(verification.get("errors", [])))
    write_json(generated / "generation-package-verification.json", verification)

    bundle_dir = generated / "reference-bundle"
    plan = build_plan(
        identity_contract=identity,
        species_profile=species_profile,
        individual_morphology=individual_morphology,
        style_family=DEFAULT_STYLE_FAMILY_ID,
        target_model="gpt-image-2.5-flare",
        policy="core-coverage",
        out_dir=bundle_dir,
    )
    checked_artifact(plan, "reference-bundle-plan")

    return sorted(
        (path.relative_to(generated) for path in generated.rglob("*") if path.is_file()),
        key=lambda value: value.as_posix(),
    )


def _validated_generated_target(target: Path, pilot_root: Path) -> Path:
    resolved_pilot = Path(pilot_root).resolve()
    expected = resolved_pilot / "generated"
    target = Path(target)
    if target.is_symlink():
        raise ValueError(f"generated target must not be a symbolic link: {target}")
    if target.exists() and not target.is_dir():
        raise ValueError(f"generated target exists and is not a directory: {target}")
    resolved_target = target.resolve(strict=False)
    if resolved_target != expected or resolved_target.parent != resolved_pilot:
        raise ValueError(
            "generated target must be exactly the pilot generated directory: "
            f"{expected}"
        )
    return resolved_target


def _remove_internal_tree(path: Path, *, pilot_root: Path, prefix: str) -> None:
    resolved_pilot = Path(pilot_root).resolve()
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"refusing to remove symbolic-link tree: {path}")
    resolved = path.resolve(strict=False)
    if resolved.parent != resolved_pilot or not resolved.name.startswith(prefix):
        raise ValueError(f"refusing to remove unexpected pilot path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _replace_generated_tree(target: Path, *, pilot_root: Path) -> list[Path]:
    resolved_pilot = Path(pilot_root).resolve()
    resolved_pilot.mkdir(parents=True, exist_ok=True)
    target = _validated_generated_target(target, resolved_pilot)
    staging = Path(
        tempfile.mkdtemp(prefix=".generated-stage-", dir=str(resolved_pilot))
    ).resolve()
    backup: Path | None = None
    installed = False
    try:
        relative_files = _build_into(staging)
        if target.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=".generated-backup-", dir=str(resolved_pilot))
            ).resolve()
            backup.rmdir()
            os.replace(target, backup)
        try:
            os.replace(staging, target)
            installed = True
        except Exception:
            if backup is not None and backup.exists() and not target.exists():
                os.replace(backup, target)
                backup = None
            raise
        if backup is not None:
            _remove_internal_tree(
                backup,
                pilot_root=resolved_pilot,
                prefix=".generated-backup-",
            )
            backup = None
        return [target / relative for relative in relative_files]
    finally:
        if staging.exists():
            _remove_internal_tree(
                staging,
                pilot_root=resolved_pilot,
                prefix=".generated-stage-",
            )
        if backup is not None and backup.exists() and installed:
            _remove_internal_tree(
                backup,
                pilot_root=resolved_pilot,
                prefix=".generated-backup-",
            )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _build_new_output_tree(output_dir: Path) -> list[Path]:
    """Atomically install into an absent or empty custom output directory.

    A non-empty directory is caller-owned data and is never replaced. The build
    happens in a sibling staging tree, so a failed build does not leave a
    partially populated target.
    """

    requested = Path(output_dir)
    if requested.is_symlink():
        raise ValueError(f"custom output path must not be a symbolic link: {requested}")
    target = requested.resolve(strict=False)
    if target == Path(target.anchor):
        raise ValueError(f"custom output path must not be a filesystem root: {target}")
    if target.exists():
        if not target.is_dir():
            raise ValueError(f"custom output path exists and is not a directory: {target}")
        if next(target.iterdir(), None) is not None:
            raise ValueError(
                "custom output directory is not empty; existing content was preserved: "
                f"{target}"
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{target.name}-stage-",
        dir=str(target.parent),
    ) as temporary:
        staging = Path(temporary).resolve()
        relative_files = _build_into(staging)
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise ValueError(f"custom output path changed during build: {target}")
            if next(target.iterdir(), None) is not None:
                raise ValueError(
                    "custom output directory gained content during build; existing content "
                    f"was preserved: {target}"
                )
            target.rmdir()
        os.replace(staging, target)
    return [target / relative for relative in relative_files]


def build(output_dir: Path | None = None) -> list[Path]:
    """Build the pilot into its canonical tree or a safe custom output tree."""

    if output_dir is None:
        return _replace_generated_tree(CANONICAL_GENERATED, pilot_root=EXAMPLE)
    requested = Path(output_dir)
    if requested.is_symlink():
        raise ValueError(f"output path must not be a symbolic link: {requested}")
    if requested.resolve(strict=False) == CANONICAL_GENERATED.resolve():
        return _replace_generated_tree(CANONICAL_GENERATED, pilot_root=EXAMPLE)
    return _build_new_output_tree(requested)


def verify_deterministic() -> dict[str, Any]:
    canonical = _validated_generated_target(CANONICAL_GENERATED, EXAMPLE)
    if not canonical.is_dir():
        raise ValueError(f"canonical generated pilot is missing: {canonical}")
    with tempfile.TemporaryDirectory(prefix="cpb-state-pilot-verify-") as temporary:
        rebuilt = Path(temporary) / "generated"
        _build_into(rebuilt)
        canonical_bytes = _tree_bytes(canonical)
        rebuilt_bytes = _tree_bytes(rebuilt)
    if canonical_bytes != rebuilt_bytes:
        missing = sorted(set(canonical_bytes) - set(rebuilt_bytes))
        unexpected = sorted(set(rebuilt_bytes) - set(canonical_bytes))
        mismatched = sorted(
            name
            for name in set(canonical_bytes) & set(rebuilt_bytes)
            if canonical_bytes[name] != rebuilt_bytes[name]
        )
        raise ValueError(
            "canonical generated pilot is stale or non-deterministic: "
            f"missing={missing}, unexpected={unexpected}, mismatched={mismatched}"
        )
    return {"ok": True, "file_count": len(canonical_bytes)}


def replacement_self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cpb-state-pilot-replace-") as temporary:
        pilot_root = Path(temporary).resolve() / "state-aware-pilot"
        pilot_root.mkdir()
        target = pilot_root / "generated"
        first_files = _replace_generated_tree(target, pilot_root=pilot_root)
        sentinel = target / "unexpected-generated-artifact.sentinel"
        sentinel.write_text("unexpected\n", encoding="utf-8", newline="\n")
        second_files = _replace_generated_tree(target, pilot_root=pilot_root)
        if sentinel.exists():
            raise ValueError("clean pilot rebuild retained an unexpected generated artifact")
        second_bytes = _tree_bytes(target)
        third_files = _replace_generated_tree(target, pilot_root=pilot_root)
        third_bytes = _tree_bytes(target)
        if first_files != second_files or second_files != third_files:
            raise ValueError("clean pilot rebuild changed the expected file inventory")
        if second_bytes != third_bytes:
            raise ValueError("clean pilot rebuild is not byte-deterministic")
        required = {"reference-selection.json", "prepared-reference-set.json"}
        if not required.issubset(second_bytes):
            raise ValueError(
                f"clean pilot rebuild omitted required artifacts: {sorted(required-set(second_bytes))}"
            )
        return {
            "ok": True,
            "unexpected_sentinel_removed": True,
            "file_count": len(second_bytes),
            "deterministic": True,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild the canonical state-aware pilot.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-deterministic", action="store_true")
    mode.add_argument("--replacement-self-test", action="store_true")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help=(
            "Build into an absent or empty custom directory without replacing existing "
            "content; omit to rebuild the canonical generated tree."
        ),
    )
    args = parser.parse_args(argv)
    if args.out_dir is not None and (
        args.verify_deterministic or args.replacement_self_test
    ):
        parser.error("--out-dir applies only to a build, not a verification mode")
    try:
        if args.verify_deterministic:
            result = verify_deterministic()
        elif args.replacement_self_test:
            result = replacement_self_test()
        else:
            output_dir = args.out_dir or CANONICAL_GENERATED
            files = build(args.out_dir)
            result = {
                "ok": True,
                "output_dir": str(output_dir.resolve()),
                "file_count": len(files),
                "files": [path.as_posix() for path in files],
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
