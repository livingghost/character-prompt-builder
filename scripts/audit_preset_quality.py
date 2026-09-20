#!/usr/bin/env python3
"""Audit canonical preset authoring conformance and duplication risk.

This checks whether records marked as curated under the preset authoring
standard contain executable visual knowledge. It does not score artistic
quality and does not claim that a generator will follow every instruction.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from catalog_cli import configure_pack_runtime, load_entries, load_pack_catalog, load_search_index, named_resource_path
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from resource_policy import (
    validate_discovery_lane_targets,
    validate_known_resource,
    validate_species_scaffold_targets,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def word_count(value: Any) -> int:
    return len(re.findall(r"[A-Za-z0-9'-]+", str(value or "")))


def token_set(record: dict[str, Any]) -> set[str]:
    text = " ".join(
        str(record.get(key, ""))
        for key in ("label", "visual_function", "prompt", "rendering", "image_promise", "aesthetic_promise", "appeal_center", "realization_promise", "integration_prompt", "tags")
    ).lower().replace("_", " ")
    stop = {
        "the", "and", "with", "that", "from", "into", "this", "one", "for",
        "while", "rather", "than", "remain", "remains", "keep", "clear",
    }
    return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 2 and token not in stop}


@dataclass(frozen=True)
class Record:
    kind: str
    category: str
    record: dict[str, Any]
    source: str


def collect_records(root: Path) -> list[Record]:
    del root
    return [
        Record(
            entry.kind,
            str(entry.category or ""),
            entry.record,
            f"pack:{entry.source_pack}",
        )
        for entry in load_entries()
        if entry.kind not in {"asset", "model"}
    ]


def require_fields(record: Record, names: Iterable[str], errors: list[str]) -> None:
    rid = str(record.record.get("id") or "<missing-id>")
    for name in names:
        if record.record.get(name) in (None, "", [], {}):
            errors.append(f"{rid}: curated {record.kind} missing required field `{name}`")


def check_atomic(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    require_fields(record, (
        "category", "label", "visual_function", "prompt", "invariants",
        "misreadings_to_avoid", "tags", "domains", "applies_to",
    ), errors)
    if word_count(item.get("prompt")) < 24:
        errors.append(f"{rid}: curated atomic prompt is under-authored ({word_count(item.get('prompt'))} words)")
    if word_count(item.get("visual_function")) < 8:
        errors.append(f"{rid}: visual_function is too short to state the module's job")
    if len(item.get("invariants", [])) < 3:
        errors.append(f"{rid}: requires at least three adaptation invariants")
    if len(item.get("misreadings_to_avoid", [])) < 3:
        errors.append(f"{rid}: requires at least three nearby misreadings")
    normalized_label = re.sub(r"[^a-z0-9]+", " ", item.get("label", "").lower()).strip()
    normalized_prompt = re.sub(r"[^a-z0-9]+", " ", item.get("prompt", "").lower()).strip()
    if normalized_prompt == normalized_label or normalized_prompt in {f"a {normalized_label}", f"an {normalized_label}"}:
        errors.append(f"{rid}: prompt merely repeats the label")



def check_distinctive_detail(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    required = (
        "feature_type", "target_region", "laterality", "landmark_relation",
        "count_or_distribution", "relative_size", "shape_and_path", "orientation",
        "color_and_value", "depth_and_relief", "edge_and_texture",
        "surface_interaction", "age_or_condition", "visibility_and_occlusion",
        "identity_priority", "adaptation_limits",
    )
    require_fields(record, required, errors)
    if item.get("laterality") not in {"left", "right", "bilateral", "centerline", "distributed", "variable"}:
        errors.append(f"{rid}: distinctive-detail laterality is invalid")
    if item.get("identity_priority") not in {"signature", "supporting", "optional"}:
        errors.append(f"{rid}: distinctive-detail identity_priority is invalid")
    if word_count(item.get("landmark_relation")) < 6:
        errors.append(f"{rid}: landmark_relation is under-authored")
    if word_count(item.get("relative_size")) < 5:
        errors.append(f"{rid}: relative_size must use a local proportional anchor")
    if word_count(item.get("surface_interaction")) < 7:
        errors.append(f"{rid}: surface_interaction is under-authored")
    if word_count(item.get("visibility_and_occlusion")) < 7:
        errors.append(f"{rid}: visibility_and_occlusion is under-authored")
    if len(item.get("adaptation_limits", [])) < 2:
        errors.append(f"{rid}: requires at least two adaptation limits")

def check_profile(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    required = (
        "label", "medium_family", "visual_intent", "linework", "shape_language",
        "value_structure", "color_logic", "surface_policy", "lighting_response",
        "background_policy", "detail_hierarchy", "prompt", "rendering",
        "negative_terms", "best_for", "avoid_for", "domains", "domain_neutrality",
    )
    require_fields(record, required, errors)
    if word_count(item.get("rendering")) < 100:
        errors.append(f"{rid}: rendering grammar is summary-like ({word_count(item.get('rendering'))} words)")
    if item.get("prompt") != item.get("rendering"):
        warnings.append(f"{rid}: prompt and rendering differ; verify both retain the full grammar")
    if len(item.get("avoid_for", [])) < 2:
        errors.append(f"{rid}: avoid_for must bound the profile's medium use")
    if item.get("domains") != ["shared"]:
        errors.append(f"{rid}: curated rendering profile must use domains ['shared']")
    if word_count(item.get("domain_neutrality")) < 20:
        errors.append(f"{rid}: rendering profile needs an explicit domain-neutrality contract")


def check_aesthetic_core(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    required = (
        "label", "domains", "compatible_medium_families",
        "aesthetic_promise", "appeal_center",
        "silhouette_and_proportion_strategy",
        "performance_and_expression_strategy", "viewer_relationship_strategy",
        "composition_and_focal_strategy", "shape_and_rhythm_strategy",
        "surface_and_tactility_strategy", "color_and_light_strategy",
        "finish_and_detail_hierarchy", "integration_prompt",
        "domain_neutrality", "variation_axes", "best_for", "avoid_for", "tags",
    )
    require_fields(record, required, errors)
    if item.get("domains") != ["shared"]:
        errors.append(f"{rid}: universal aesthetic core must use domains ['shared']")
    if word_count(item.get("integration_prompt")) < 90:
        errors.append(f"{rid}: aesthetic-core integration prompt is summary-like ({word_count(item.get('integration_prompt'))} words)")
    for field in (
        "aesthetic_promise", "appeal_center",
        "silhouette_and_proportion_strategy",
        "performance_and_expression_strategy", "viewer_relationship_strategy",
        "composition_and_focal_strategy", "shape_and_rhythm_strategy",
        "surface_and_tactility_strategy", "color_and_light_strategy",
        "finish_and_detail_hierarchy", "domain_neutrality",
    ):
        if word_count(item.get(field)) < 20:
            errors.append(f"{rid}: aesthetic-core field `{field}` is under-authored ({word_count(item.get(field))} words)")
    if len(item.get("compatible_medium_families", [])) < 1:
        errors.append(f"{rid}: aesthetic core needs at least one compatible medium family")
    if len(item.get("variation_axes", [])) < 4:
        errors.append(f"{rid}: aesthetic core needs at least four variation axes")
    if len(item.get("best_for", [])) < 3:
        errors.append(f"{rid}: aesthetic core needs at least three best_for uses")
    if len(item.get("avoid_for", [])) < 2:
        errors.append(f"{rid}: aesthetic core needs at least two avoid_for boundaries")

    # A universal core defines appeal and art direction. Domain anatomy, surface
    # systems, and expressive organs belong in domain-realization records.
    positive = " ".join(
        str(item.get(field, "")) for field in (
            "aesthetic_promise", "appeal_center",
            "silhouette_and_proportion_strategy",
            "performance_and_expression_strategy", "viewer_relationship_strategy",
            "composition_and_focal_strategy", "shape_and_rhythm_strategy",
            "surface_and_tactility_strategy", "color_and_light_strategy",
            "finish_and_detail_hierarchy", "integration_prompt", "domain_neutrality",
        )
    ).lower()
    domain_specific = (
        " fur ", " muzzle ", " paw ", " paws ", " tail ", " beak ",
        " feather ", " feathers ", " skin ", " hair ", " chassis ",
        " optic ", " optics ", " sensor ", " sensors ", " hoof ",
        " hooves ", " wing ", " wings ", " manipulator ", " manipulators ",
    )
    padded = f" {positive} "
    found = sorted({term.strip() for term in domain_specific if term in padded})
    if found:
        errors.append(f"{rid}: universal aesthetic core contains domain-realization vocabulary: {found}")


def check_style_family(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    required = (
        "label", "domains", "medium_family", "base_render_profile_id",
        "compatible_render_profile_ids", "style_promise", "visual_signature",
        "line_system", "form_system", "value_and_shadow_system",
        "highlight_system", "color_system", "surface_system",
        "background_system", "detail_hierarchy", "touch_policy",
        "style_reference_guidance", "domain_overlays", "integration_prompt",
        "negative_policy", "negative_terms", "variation_axes", "best_for", "avoid_for", "tags",
    )
    require_fields(record, required, errors)
    if item.get("domains") != ["shared"]:
        errors.append(f"{rid}: concrete style family must use domains ['shared']")
    if word_count(item.get("integration_prompt")) < 100:
        errors.append(f"{rid}: style-family integration prompt is summary-like ({word_count(item.get('integration_prompt'))} words)")
    for name in (
        "line_system", "form_system", "value_and_shadow_system",
        "highlight_system", "color_system", "surface_system", "background_system",
    ):
        value = item.get(name)
        if not isinstance(value, dict) or len(value) < 3:
            errors.append(f"{rid}: style-family `{name}` needs at least three authored components")
        elif word_count(value) < 35:
            errors.append(f"{rid}: style-family `{name}` is under-authored ({word_count(value)} words)")
    overlays = item.get("domain_overlays")
    expected = {"human", "anthropomorphic-animal", "animal", "creature", "hybrid", "robot"}
    if not isinstance(overlays, dict) or set(overlays) != expected:
        errors.append(f"{rid}: domain_overlays must cover exactly {sorted(expected)}")
    else:
        overlay_fields = {"identity_and_form", "surface_translation", "performance_translation", "detail_priority", "integration"}
        for domain, overlay in overlays.items():
            if not isinstance(overlay, dict):
                errors.append(f"{rid}: domain overlay `{domain}` must be an object")
                continue
            missing = sorted(overlay_fields - set(overlay))
            if missing:
                errors.append(f"{rid}: domain overlay `{domain}` missing fields {missing}")
            for field in overlay_fields & set(overlay):
                if word_count(overlay.get(field)) < 8:
                    errors.append(f"{rid}: domain overlay `{domain}.{field}` is under-authored")
    if len(item.get("compatible_render_profile_ids", [])) < 1:
        errors.append(f"{rid}: style family needs at least one compatible render profile")
    if item.get("base_render_profile_id") not in item.get("compatible_render_profile_ids", []):
        errors.append(f"{rid}: base_render_profile_id must be included in compatible_render_profile_ids")
    if len(item.get("variation_axes", [])) < 4:
        errors.append(f"{rid}: style family needs at least four variation axes")
    if len(item.get("best_for", [])) < 3:
        errors.append(f"{rid}: style family needs at least three best_for uses")
    if len(item.get("avoid_for", [])) < 2:
        errors.append(f"{rid}: style family needs at least two avoid_for boundaries")


def check_domain_realization(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    required = (
        "label", "domains", "subject_domain", "realization_level",
        "realization_promise", "identity_and_silhouette", "performance_channels",
        "anatomy_and_weight", "surface_and_materials", "viewer_relationship",
        "motion_and_environment", "translation_rules", "integration_prompt",
        "extension_points", "best_for", "avoid_for", "tags",
    )
    require_fields(record, required, errors)
    domains = item.get("domains") or []
    subject_domain = item.get("subject_domain")
    if len(domains) != 1 or domains[0] != subject_domain or subject_domain == "shared":
        errors.append(f"{rid}: domain realization requires one exact non-shared subject domain")
    if item.get("realization_level") == "foundation" and item.get("base_realization") is not True:
        errors.append(f"{rid}: foundation domain realization must set base_realization true")
    for field in (
        "realization_promise", "identity_and_silhouette", "performance_channels",
        "anatomy_and_weight", "surface_and_materials", "viewer_relationship",
        "motion_and_environment",
    ):
        if word_count(item.get(field)) < 20:
            errors.append(f"{rid}: domain-realization field `{field}` is under-authored ({word_count(item.get(field))} words)")
    if word_count(item.get("integration_prompt")) < 90:
        errors.append(f"{rid}: domain-realization integration prompt is summary-like ({word_count(item.get('integration_prompt'))} words)")
    rules = item.get("translation_rules", {})
    required_rules = {"appeal_center", "shape_and_rhythm", "performance", "surface", "color_and_light", "detail_hierarchy"}
    missing_rules = sorted(required_rules - set(rules))
    if missing_rules:
        errors.append(f"{rid}: domain realization missing translation rules {missing_rules}")
    for name in required_rules & set(rules):
        if word_count(rules.get(name)) < 12:
            errors.append(f"{rid}: translation rule `{name}` is under-authored")
    if len(item.get("extension_points", [])) < 3:
        errors.append(f"{rid}: domain realization needs at least three extension points")
    if len(item.get("best_for", [])) < 3:
        errors.append(f"{rid}: domain realization needs at least three best_for uses")
    if len(item.get("avoid_for", [])) < 2:
        errors.append(f"{rid}: domain realization needs at least two avoid_for boundaries")


def check_scene(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    require_fields(record, (
        "label", "image_promise", "staging", "defaults", "must_preserve",
        "adaptable_fields", "failure_modes", "aspect_ratio", "domain",
    ), errors)
    staging = item.get("staging", {})
    for field in (
        "body_geometry", "action_geometry", "gaze_and_expression",
        "prop_or_contact_geometry", "focal_hierarchy", "depth_order",
    ):
        if not staging.get(field):
            errors.append(f"{rid}: missing staging.{field}")
        elif word_count(staging[field]) < 14:
            errors.append(f"{rid}: staging.{field} is under-authored ({word_count(staging[field])} words)")
    if word_count(item.get("image_promise")) < 16:
        errors.append(f"{rid}: image_promise is too short")
    if len(item.get("must_preserve", [])) < 4:
        errors.append(f"{rid}: requires at least four must_preserve relationships")
    if len(item.get("failure_modes", [])) < 4:
        errors.append(f"{rid}: requires at least four scene-specific failure modes")
    defaults = item.get("defaults", {})
    for field in ("subject", "body", "pose", "expression", "composition", "camera", "lighting", "environment", "mood", "constraints"):
        if defaults.get(field) in (None, "", []):
            errors.append(f"{rid}: defaults missing `{field}`")


def check_archetype(
    record: Record,
    errors: list[str],
    warnings: list[str],
    policy: Mapping[str, Any],
) -> None:
    item = record.record
    rid = item["id"]
    require_fields(record, (
        "label", "archetype_scope", "creation_basis", "evidence_scope",
        "identity_axes", "identity_invariants", "variable_fields",
        "identity_construction", "character_lock", "defaults", "constraints",
        "do_not_lock", "domain",
    ), errors)
    expected_scope = str(policy.get("curated_archetype_scope") or "recurring-character-identity")
    if item.get("archetype_scope") != expected_scope:
        errors.append(f"{rid}: archetype_scope must be `{expected_scope}`")
    allowed_basis = {str(value) for value in policy.get("creation_basis_values") or []}
    if allowed_basis and item.get("creation_basis") not in allowed_basis:
        errors.append(
            f"{rid}: unknown creation_basis `{item.get('creation_basis')}` "
            f"(allowed: {sorted(allowed_basis)})"
        )
    if word_count(item.get("evidence_scope")) < 10:
        errors.append(f"{rid}: evidence_scope is too short to explain why the identity is reusable")

    axes = item.get("identity_axes")
    if not isinstance(axes, Mapping):
        errors.append(f"{rid}: identity_axes must be an object")
        axes = {}
    required_axes = [str(value) for value in policy.get("required_identity_axes") or []]
    for axis in required_axes:
        value = axes.get(axis)
        if value in (None, "", [], {}):
            errors.append(f"{rid}: identity_axes missing required axis `{axis}`")
        elif axis != "subject_domain" and word_count(value) < 2:
            errors.append(f"{rid}: identity axis `{axis}` is under-authored")
    creation_gate = policy.get("creation_gate")
    # Core policy permits a prose creation gate; structured provider policies
    # can override the numeric minimum. Neither form should crash an audit.
    minimum_value = creation_gate.get("minimum_stable_axes", 5) if isinstance(creation_gate, Mapping) else 5
    if isinstance(minimum_value, bool) or not isinstance(minimum_value, int) or minimum_value < 1:
        errors.append(f"{rid}: creation_gate.minimum_stable_axes must be a positive integer")
        minimum_value = 5
    minimum_axes = minimum_value
    populated_axes = sum(1 for value in axes.values() if value not in (None, "", [], {}))
    if populated_axes < minimum_axes:
        errors.append(f"{rid}: requires at least {minimum_axes} populated stable identity axes")
    if axes.get("subject_domain") != item.get("domain"):
        errors.append(f"{rid}: identity_axes.subject_domain must equal domain `{item.get('domain')}`")

    if len(item.get("identity_invariants", [])) < 4:
        errors.append(f"{rid}: requires at least four identity invariants")
    if len(item.get("variable_fields", [])) < 4:
        errors.append(f"{rid}: variable_fields must explicitly protect presentation flexibility")
    if word_count(item.get("character_lock")) < 35:
        errors.append(f"{rid}: character_lock is too short to preserve identity")
    lock = item.get("character_lock", "").lower()
    transient_terms = ("rooftop", "couch", "low-angle", "sunny beach", "neon pool", "reclining pose")
    if any(term in lock for term in transient_terms):
        errors.append(f"{rid}: character_lock contains transient scene presentation")

    domain = item.get("domain")
    morphology_text = " ".join(
        str(value) for value in (
            lock,
            axes.get("morphology"),
            (item.get("defaults") or {}).get("morphology"),
        ) if value
    ).lower()
    if domain == "anthropomorphic-animal" and not any(
        term in morphology_text for term in ("anthropomorphic", "humanoid")
    ):
        errors.append(f"{rid}: anthropomorphic-animal archetype must state its humanoid or anthropomorphic body plan")
    if domain == "animal":
        if "natural" not in morphology_text:
            errors.append(f"{rid}: ordinary-animal archetype must state natural anatomy or body plan")
        forbidden = ("anthropomorphic", "humanoid body", "human hands", "humanlike hands")
        found = [term for term in forbidden if term in morphology_text]
        if found:
            errors.append(f"{rid}: ordinary-animal archetype contains anthropomorphic body-plan terms {found}")


def check_correction(record: Record, errors: list[str], warnings: list[str]) -> None:
    item = record.record
    rid = item["id"]
    require_fields(record, (
        "label", "trigger", "diagnosis", "positive_correction",
        "inspection_points", "avoidance_terms", "tags",
    ), errors)
    if word_count(item.get("positive_correction")) < 25:
        errors.append(f"{rid}: positive repair is under-authored ({word_count(item.get('positive_correction'))} words)")
    if len(item.get("inspection_points", [])) < 3:
        errors.append(f"{rid}: requires at least three inspection points")


def check_recipes(records: Sequence[Record], errors: list[str], warnings: list[str]) -> None:
    scenes = {r.record["id"]: r.record for r in records if r.kind == "scene"}
    profiles = {r.record["id"]: r.record for r in records if r.kind == "profile"}
    grammar_fields = (
        "medium_family", "visual_intent", "linework", "shape_language", "value_structure",
        "color_logic", "surface_policy", "lighting_response", "background_policy", "detail_hierarchy",
    )
    for record in records:
        if record.kind != "recipe" or record.record.get("curation_status") != "curated":
            continue
        item = record.record
        rid = item["id"]
        require_fields(record, (
            "image_promise", "scene_blueprint", "rendering_grammar", "prompt_template",
            "adaptation_rules", "must_preserve", "negative_terms", "input_slots",
        ), errors)
        scene = scenes.get(item.get("base_scene_id"))
        profile = profiles.get(item.get("render_profile_id"))
        if not scene:
            errors.append(f"{rid}: linked scene is missing")
            continue
        if not profile:
            errors.append(f"{rid}: linked rendering profile is missing")
            continue
        blueprint = item.get("scene_blueprint", {})
        if blueprint.get("staging") != scene.get("staging"):
            errors.append(f"{rid}: recipe staging snapshot does not preserve the canonical scene")
        if blueprint.get("must_preserve") != scene.get("must_preserve"):
            errors.append(f"{rid}: recipe must_preserve snapshot differs from the scene")
        expected_grammar = {field: profile.get(field) for field in grammar_fields}
        if item.get("rendering_grammar") != expected_grammar:
            errors.append(f"{rid}: recipe rendering grammar does not preserve the canonical profile")
        if word_count(item.get("prompt_template")) < 240:
            errors.append(f"{rid}: finished recipe prompt is summary-like ({word_count(item.get('prompt_template'))} words)")
        for value in scene.get("staging", {}).values():
            if str(value) not in item.get("prompt_template", ""):
                errors.append(f"{rid}: prompt_template omits a canonical staging field")
                break
        if len(item.get("adaptation_rules", [])) < 4:
            errors.append(f"{rid}: requires explicit adaptation rules")



def check_near_duplicates(records: Sequence[Record], warnings: list[str]) -> list[dict[str, Any]]:
    curated = [
        record for record in records
        if record.record.get("curation_status") == "curated"
        and record.kind != "recipe"
    ]
    findings: list[dict[str, Any]] = []
    for index, left in enumerate(curated):
        left_tokens = token_set(left.record)
        if not left_tokens:
            continue
        for right in curated[index + 1:]:
            if left.source != right.source:
                continue
            if left.kind != right.kind or left.category != right.category:
                continue
            if right.record.get("id") in left.record.get("distinct_from", []) or left.record.get("id") in right.record.get("distinct_from", []):
                continue
            right_tokens = token_set(right.record)
            similarity = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
            if similarity >= 0.82:
                pair = {
                    "left": left.record["id"],
                    "right": right.record["id"],
                    "kind": left.kind,
                    "category": left.category,
                    "jaccard": round(similarity, 3),
                }
                findings.append(pair)
                warnings.append(
                    f"near-duplicate curated records require human review: {pair['left']} <-> {pair['right']} ({pair['jaccard']})"
                )
    return findings



POSITIVE_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|avoid|avoiding|exclude|excluded|excluding|"
    r"prevent|preventing|omit|omits|omitted|omitting|refrain|refrains|refrained|refraining|"
    r"unless|except|free\s+of)\b"
    r"|\bdo\s+not\b|\bmust\s+not\b|\brather\s+than\b|\binstead\s+of\b"
    r"|\bas\s+opposed\s+to\b|\bunlike\b|\babsence\s+of\b"
    r"|\bnon[- ](?:linguistic|photoreal|photorealistic|literal|verbal)\b",
    re.IGNORECASE,
)


def _walk_text(value: Any, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_text(child, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_text(child, child_path)


def _positive_fields(record: Record) -> dict[str, Any]:
    item = record.record
    if record.kind == "module":
        names = ("visual_function", "prompt", "invariants")
    elif record.kind == "profile":
        names = (
            "visual_intent", "linework", "shape_language", "value_structure",
            "color_logic", "surface_policy", "lighting_response",
            "background_policy", "detail_hierarchy", "prompt", "rendering",
        )
    elif record.kind == "aesthetic-core":
        names = (
            "aesthetic_promise", "appeal_center",
            "silhouette_and_proportion_strategy",
            "performance_and_expression_strategy", "viewer_relationship_strategy",
            "composition_and_focal_strategy", "shape_and_rhythm_strategy",
            "surface_and_tactility_strategy", "color_and_light_strategy",
            "finish_and_detail_hierarchy", "integration_prompt", "domain_neutrality",
        )
    elif record.kind == "style-family":
        names = (
            "style_promise", "visual_signature", "line_system", "form_system",
            "value_and_shadow_system", "highlight_system", "color_system",
            "surface_system", "background_system", "detail_hierarchy",
            "touch_policy", "style_reference_guidance", "domain_overlays",
            "integration_prompt",
        )
    elif record.kind == "domain-realization":
        names = (
            "realization_promise", "identity_and_silhouette", "performance_channels",
            "anatomy_and_weight", "surface_and_materials", "viewer_relationship",
            "motion_and_environment", "translation_rules", "integration_prompt",
        )
    elif record.kind == "scene":
        names = ("image_promise", "staging", "defaults", "must_preserve")
    elif record.kind == "recipe":
        blueprint = item.get("scene_blueprint", {})
        positive_blueprint = {
            key: blueprint[key]
            for key in ("image_promise", "staging", "defaults", "must_preserve")
            if key in blueprint
        }
        values = {
            "image_promise": item.get("image_promise"),
            "scene_blueprint": positive_blueprint,
            "rendering_grammar": item.get("rendering_grammar"),
            "rendering": item.get("rendering"),
            "prompt_template": item.get("prompt_template"),
            "adaptation_rules": item.get("adaptation_rules"),
            "must_preserve": item.get("must_preserve"),
            "generation_defaults": item.get("generation_defaults"),
        }
        return {name: value for name, value in values.items() if value not in (None, "", [], {})}
    elif record.kind == "archetype":
        names = (
            "identity_axes", "identity_invariants", "identity_construction",
            "character_lock", "constraints",
        )
    elif record.kind == "correction":
        names = ("positive_correction",)
    else:
        names = ()
    return {name: item[name] for name in names if name in item}


def check_affirmative_positive_fields(records: Sequence[Record], errors: list[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for record in records:
        item = record.record
        if item.get("curation_status") != "curated":
            continue
        rid = str(item.get("id"))
        for root_name, value in _positive_fields(record).items():
            for subpath, text in _walk_text(value, root_name):
                if POSITIVE_NEGATION_RE.search(text):
                    findings.append({"id": rid, "kind": record.kind, "path": subpath, "text": text})
                    errors.append(f"{rid}: positive-facing field uses exclusion language at `{subpath}`")
    return findings




def check_positive_text_quality(records: Sequence[Record], errors: list[str]) -> list[dict[str, str]]:
    """Catch formatting and maintenance artifacts in curated prompt-facing data.

    This is deliberately generic: it checks punctuation duplication, repeated
    sentences, and known prompt-assembly meta instructions. It does not rewrite
    data or decide artistic meaning.
    """
    findings: list[dict[str, str]] = []
    forbidden_meta = (
        "explicit user requirements override",
        "do not shorten",
        "adapt identity details freely",
        "preserve the user's stated traits",
        "do not reconstruct from chat",
    )
    forbidden_placeholder = ("nearby but different result",)
    for record in records:
        item = record.record
        if item.get("curation_status") != "curated":
            continue
        rid = str(item.get("id"))
        for root_name, value in _positive_fields(record).items():
            for subpath, text in _walk_text(value, root_name):
                if re.search(r"\.{2,}", text):
                    findings.append({"id": rid, "path": subpath, "issue": "duplicate punctuation", "text": text})
                    errors.append(f"{rid}: duplicate punctuation in positive-facing field `{subpath}`")
                sentences = [
                    segment.strip()
                    for segment in re.split(r"(?<=[.!?])\s+", text)
                    if segment.strip()
                ]
                counts: dict[str, int] = {}
                for segment in sentences:
                    folded = re.sub(r"\s+", " ", segment.lower()).strip()
                    if len(folded) >= 28:
                        counts[folded] = counts.get(folded, 0) + 1
                repeated = [segment for segment, count in counts.items() if count > 1]
                if repeated:
                    findings.append({"id": rid, "path": subpath, "issue": "repeated sentence", "text": repeated[0]})
                    errors.append(f"{rid}: repeated sentence in positive-facing field `{subpath}`")
                # Also catch an adjacent sentence that restates the same long
                # opening hierarchy and merely appends a clause. This keeps
                # authored production prose concise without rewriting it.
                for left, right in zip(sentences, sentences[1:]):
                    left_words = re.findall(r"[a-z0-9]+", left.lower())
                    right_words = re.findall(r"[a-z0-9]+", right.lower())
                    prefix = min(8, len(left_words), len(right_words))
                    if prefix >= 6 and left_words[:prefix] == right_words[:prefix]:
                        findings.append({
                            "id": rid,
                            "path": subpath,
                            "issue": "repeated sentence opening",
                            "text": f"{left} | {right}",
                        })
                        errors.append(f"{rid}: adjacent sentences repeat the same opening in positive-facing field `{subpath}`")
                lower = text.lower()
                for phrase in forbidden_meta:
                    if phrase in lower:
                        findings.append({"id": rid, "path": subpath, "issue": "assembly meta instruction", "text": phrase})
                        errors.append(f"{rid}: prompt-facing field contains assembly meta instruction `{phrase}` at `{subpath}`")
                for phrase in forbidden_placeholder:
                    if phrase in lower:
                        findings.append({
                            "id": rid,
                            "path": subpath,
                            "issue": "placeholder summary language",
                            "text": phrase,
                        })
                        errors.append(
                            f"{rid}: prompt-facing field contains placeholder summary language "
                            f"`{phrase}` at `{subpath}`"
                        )
    return findings


def check_negative_scope(root: Path, records: Sequence[Record], errors: list[str]) -> None:
    del root
    policy_path = named_resource_path("negative-policy")
    assert policy_path is not None
    policy = load_json(policy_path)
    for message in validate_known_resource("negative-policy", policy):
        errors.append(f"selected negative-policy: {message}")
    required_automatic = {
        "generation_hygiene", "visible_limb_integrity", "hand_or_paw_integrity",
        "tail_integrity", "clothing_integrity", "held_prop_integrity",
        "selected_render_profile", "selected_style_family",
    }
    automatic = policy.get("automatic_sources", {})
    missing_automatic = sorted(required_automatic - set(automatic))
    if missing_automatic:
        errors.append(f"negative policy is missing feature-scoped automatic sources: {missing_automatic}")
    for source_id, source in automatic.items():
        if not isinstance(source, dict) or not source.get("activation"):
            errors.append(f"negative policy automatic source lacks activation: {source_id}")
    scenes = {r.record["id"]: r.record for r in records if r.kind == "scene"}
    profiles = {r.record["id"]: r.record for r in records if r.kind == "profile"}
    for record in records:
        item = record.record
        if item.get("curation_status") != "curated":
            continue
        rid = str(item.get("id"))
        if record.kind == "module":
            if item.get("misreading_policy", {}).get("automatic_prompt_injection") is not False:
                errors.append(f"{rid}: curated module misreadings require diagnostic-only policy")
        elif record.kind == "style-family":
            policy = item.get("negative_policy", {})
            if policy.get("scope") != "selected-style-family-only" or policy.get("automatic_merge") is not True:
                errors.append(f"{rid}: style-family negative terms require selected-style-family-only scope")
        elif record.kind == "profile":
            if item.get("negative_policy", {}).get("scope") != "medium-drift-and-rendering-failure":
                errors.append(f"{rid}: rendering profile negative scope is invalid")
        elif record.kind == "scene":
            if item.get("failure_mode_policy", {}).get("automatic_prompt_injection") is not False:
                errors.append(f"{rid}: scene failure modes require diagnostic-only policy")
        elif record.kind == "archetype":
            if item.get("do_not_lock_policy", {}).get("automatic_prompt_injection") is not False:
                errors.append(f"{rid}: archetype presentation-freedom metadata must stay out of prompts")
        elif record.kind == "correction":
            if item.get("avoidance_policy", {}).get("scope") != "active-correction-only":
                errors.append(f"{rid}: correction avoidance terms require active-correction-only scope")
        elif record.kind == "recipe":
            scene = scenes.get(item.get("base_scene_id"))
            profile = profiles.get(item.get("render_profile_id"))
            if item.get("negative_policy", {}).get("semantic_exclusions") != "user-request-only":
                errors.append(f"{rid}: recipe semantic exclusions must be user-request-only")
            if profile and item.get("negative_terms") != profile.get("negative_terms"):
                errors.append(f"{rid}: recipe negative terms must equal the selected profile's scoped terms")
            if scene and item.get("diagnostic_failure_modes") != scene.get("failure_modes"):
                errors.append(f"{rid}: recipe diagnostic failure modes must preserve the scene separately")
            bundles = item.get("negative_bundles", {})
            profile_bundle = bundles.get("profile_boundary", {})
            scene_bundle = bundles.get("scene_geometry", {})
            if profile and profile_bundle.get("terms") != profile.get("negative_terms"):
                errors.append(f"{rid}: recipe profile-boundary bundle differs from selected profile terms")
            if scene_bundle.get("automatic_merge") is not False:
                errors.append(f"{rid}: scene diagnostic failure modes must not merge automatically")
            if scene and scene_bundle.get("diagnostic_failure_modes") != scene.get("failure_modes"):
                errors.append(f"{rid}: scene diagnostic bundle must preserve the canonical failure modes")
            if bundles.get("global_policy", {}).get("source") != "cpb-resource:negative-policy":
                errors.append(f"{rid}: recipe does not reference the canonical negative policy")

CANONICAL_DOMAINS = {
    "human", "anthropomorphic-animal", "animal", "creature", "hybrid",
    "robot", "shared",
}

def _norm_text(value: Any) -> str:
    text = str(value or "").lower().replace("_", "-")
    return " ".join(re.sub(r"[^a-z0-9\-]+", " ", text).split())


def _fold(value: Any) -> str:
    """Comparison normalization: hyphens, underscores, whitespace, and
    punctuation all count as the same separator, so `foo-bar` == `foo bar`."""
    text = str(value or "").lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


MEDIUM_FAMILY_VOCABULARY = {
    "2D anime character illustration",
    "cinematic 2D soft-cel anime illustration",
    "flat 2D cartoon illustration",
    "bold 2D comic and anime poster",
    "2D game character splash illustration",
    "clean fantasy concept-sheet illustration",
    "painterly illustration",
    "photography / photorealism",
    "3D character rendering",
    "monochrome ink and manga illustration",
    "pixel art",
    "scientific and technical illustration",
}

_SUBJECT_ASSUMPTION_WORDS = ("anthro", "kemono", "furry")


def check_medium_family_vocabulary(records: Sequence[Record], errors: list[str]) -> None:
    """One closed family vocabulary joins profiles and aesthetic cores.

    Every rendering profile (any tier) must declare a medium_family from the
    canonical set, and every aesthetic-core compatibility value must be a
    member of the same set, so signature-to-profile matching never depends on
    free-text near-misses. Shared-scope profiles must also stay free of
    subject-assumption words; subject-specialized grammars declare their
    domain instead of implying it.
    """
    for record in records:
        item = record.record
        rid = str(item.get("id"))
        if record.kind == "profile":
            family = item.get("medium_family")
            if family not in MEDIUM_FAMILY_VOCABULARY:
                errors.append(f"{rid}: medium_family `{family}` is not in the canonical vocabulary")
            domains = item.get("domains") or ["shared"]
            if domains == ["shared"]:
                blob = " ".join(
                    str(item.get(k, "")) for k in (
                        "visual_intent", "linework", "shape_language", "value_structure",
                        "surface_language", "color_logic", "finish", "rendering",
                    )
                ).lower()
                found = sorted({w for w in _SUBJECT_ASSUMPTION_WORDS if w in blob})
                if found:
                    errors.append(f"{rid}: shared rendering profile contains subject-assumption words {found}; declare a domain scope or rephrase")
        if record.kind == "aesthetic-core":
            for value in item.get("compatible_medium_families", []):
                if value not in MEDIUM_FAMILY_VOCABULARY:
                    errors.append(f"{rid}: compatible_medium_families value `{value}` is not in the canonical vocabulary")
        if record.kind == "style-family":
            family = item.get("medium_family")
            if family not in MEDIUM_FAMILY_VOCABULARY:
                errors.append(f"{rid}: style-family medium_family `{family}` is not in the canonical vocabulary")


def check_active_catalog(errors: list[str]) -> None:
    """Fail when the runtime excluded an enabled pack from the audited catalog.

    An enabled pack whose lock no longer matches its files is dropped from the
    catalog while it remains listed as enabled and available, and the pack
    discovery stage reports no issue for it. Every record it owns then leaves
    the audited set silently, so the audit reports a clean catalog because it
    stopped reading the records rather than because they became correct. The
    exclusion is recorded as an error-severity catalog diagnostic, which is the
    same evidence the single-pack release gate already refuses to ignore.
    """

    catalog = load_pack_catalog()
    if catalog.active_pack_count < 1:
        errors.append("active catalog: no pack is active, so the audit examined no records")
    for diagnostic in catalog.diagnostics:
        if diagnostic.get("severity") != "error":
            continue
        code = diagnostic.get("code") or "catalog-diagnostic"
        message = diagnostic.get("message") or ""
        errors.append(f"active catalog: {code}: {message}".rstrip(": "))


def check_global_integrity(records: Sequence[Record], errors: list[str], warnings: list[str]) -> None:
    """Whole-catalog invariants, independent of curation status.

    These are the guards that would have caught the duplicated concepts and
    fragmented domain vocabulary found in review: exact-label collisions within
    a family, tags that merely copy the label, and domain values outside the
    canonical vocabulary.

    Collision detection is scoped to one pack. Only the bundled pack ships with
    this repository; any other pack in the tree belongs to whoever installed it
    and is never published from here. A label shared across that boundary is a
    layering choice on one machine, not a defect in the shipped catalog, and the
    remedy this check prints, merging the records and deleting one ID, cannot be
    carried out across packs at all. Leaving the scope open let an unmanaged pack
    make the managed one fail, which pushes the repair onto the shipped records.
    """
    seen: dict[tuple[str, str, str, str, tuple[str, ...]], str] = {}
    for record in records:
        item = record.record
        rid = str(item.get("id"))
        status = item.get("curation_status")
        if status not in (None, "curated", "vocabulary"):
            errors.append(f"{rid}: unknown curation_status `{status}`")
        raw_domains = item.get("domains") or ([item["domain"]] if item.get("domain") else [])
        canon: list[str] = []
        for value in raw_domains:
            n = _norm_text(value)
            if n and n not in CANONICAL_DOMAINS:
                errors.append(f"{rid}: unknown domain value `{value}` (canonical: {sorted(CANONICAL_DOMAINS)})")
            if n and n not in canon:
                canon.append(n)
        label = _fold(item.get("label"))
        if label:
            key = (record.source, record.kind, record.category or "", label, tuple(sorted(canon)))
            if key in seen:
                errors.append(
                    f"label collision: `{item.get('label')}` used by both {seen[key]} and {rid} "
                    f"({record.kind}/{record.category}); merge into one canonical record and delete the duplicate ID"
                )
            else:
                seen[key] = rid
        for tag in item.get("tags") or []:
            if _fold(tag) == label and label:
                errors.append(f"{rid}: tag `{tag}` merely copies the label; tags must add distinctive retrieval keys")


_COUNTED_FILES = {
    "render-profiles.json": "profiles", "aesthetic-cores.json": "cores",
    "style-families.json": "families", "domain-realizations.json": "realizations", "base-scenes.json": "scenes",
    "scene-recipes.json": "recipes", "character-archetypes.json": "archetypes",
    "corrections.json": "corrections",
}


def check_declared_counts(root: Path, errors: list[str]) -> None:
    del root, errors


def check_runtime_search_index(root: Path, records: Sequence[Record], errors: list[str]) -> None:
    index = load_search_index()
    canonical_ids = {str(record.record.get("id")) for record in records}
    canonical_ids.update(
        str(entry.record.get("id"))
        for entry in load_entries()
    )
    curated_ids = {
        str(record.record.get("id")) for record in records
        if record.record.get("curation_status") == "curated"
    }
    phrases = index.phrases
    if not isinstance(phrases, Mapping) or not phrases:
        errors.append("runtime search index phrases must be a non-empty object")
        phrases = {}
    for phrase, associations in phrases.items():
        if not str(phrase).strip():
            errors.append("runtime search index contains an empty phrase")
            continue
        if isinstance(associations, Mapping):
            associations = [associations]
        if not isinstance(associations, list) or not associations:
            errors.append(f"runtime search phrase `{phrase}` has no associations")
            continue
        seen: set[tuple[str, str, str]] = set()
        for association in associations:
            if not isinstance(association, Mapping):
                errors.append(f"runtime search phrase `{phrase}` has a non-object association")
                continue
            target = str(association.get("id") or "")
            facet = str(association.get("facet") or "")
            source = str(association.get("source") or "")
            if target not in canonical_ids:
                errors.append(f"runtime search phrase `{phrase}` targets unknown canonical ID `{target}`")
            if not facet:
                errors.append(f"runtime search phrase `{phrase}` association `{target}` lacks facet")
            if not source:
                errors.append(f"runtime search phrase `{phrase}` association `{target}` lacks source")
            try:
                weight = float(association.get("weight"))
            except (TypeError, ValueError):
                errors.append(f"runtime search phrase `{phrase}` association `{target}` has invalid weight")
            else:
                if not 0.0 < weight <= 2.0:
                    errors.append(f"runtime search phrase `{phrase}` association `{target}` weight is outside 0..2")
            key = (target, facet, source)
            if key in seen:
                errors.append(f"runtime search phrase `{phrase}` repeats association {key}")
            seen.add(key)

    profiles = index.records
    if not isinstance(profiles, Mapping):
        errors.append("runtime search index records must be an object")
        profiles = {}
    unknown_profiles = sorted(set(map(str, profiles)) - canonical_ids)
    if unknown_profiles:
        errors.append(f"runtime search profiles target unknown IDs: {unknown_profiles}")
    missing_profiles = sorted(curated_ids - set(map(str, profiles)))
    if missing_profiles:
        errors.append(f"curated records lack runtime discovery profiles: {missing_profiles}")
    for rid in sorted(curated_ids & set(map(str, profiles))):
        profile = profiles[rid]
        if not isinstance(profile, Mapping):
            errors.append(f"runtime discovery profile `{rid}` is not an object")
            continue
        aliases = [str(value).strip() for value in profile.get("aliases") or [] if str(value).strip()]
        if len(set(aliases)) < 3:
            errors.append(f"runtime discovery profile `{rid}` needs at least three distinct aliases")
        if not str(profile.get("outcome_summary") or "").strip():
            errors.append(f"runtime discovery profile `{rid}` lacks outcome_summary")
        if not str(profile.get("discovery_group") or "").strip():
            errors.append(f"runtime discovery profile `{rid}` lacks discovery_group")
        if not isinstance(profile.get("facets"), Mapping) or not profile.get("facets"):
            errors.append(f"runtime discovery profile `{rid}` lacks searchable facets")
        if not isinstance(profile.get("anchor_signature"), Mapping):
            errors.append(f"runtime discovery profile `{rid}` lacks anchor_signature")

    # Retrieval is source-language-independent at the package boundary. The calling
    # agent translates and normalizes the brief; the package must not accumulate locale-specific
    # word lists that drift independently of the canonical catalog.
    query_schema_path = root / "schemas" / "catalog-query.schema.json"
    query_template_path = root / "templates" / "catalog-query-template.json"
    if not query_schema_path.is_file():
        errors.append("missing schemas/catalog-query.schema.json")
    else:
        query_schema = load_json(query_schema_path)
        if query_schema.get("type") != "object":
            errors.append("catalog-query.schema.json must define an object schema")
        if "source_brief" not in (query_schema.get("properties") or {}):
            errors.append("catalog-query.schema.json must preserve source_brief as metadata")
        required_keywords = {"anyOf", "additionalProperties"}
        if not required_keywords.issubset(query_schema):
            errors.append(
                "catalog-query.schema.json must require canonical_query or non-empty anchors and reject unknown fields"
            )
        anchors_schema = (query_schema.get("properties") or {}).get("anchors") or {}
        if not all(key in anchors_schema for key in ("propertyNames", "additionalProperties")):
            errors.append(
                "catalog-query.schema.json anchors must validate facet names and values"
            )
    if not query_template_path.is_file():
        errors.append("missing templates/catalog-query-template.json")
    else:
        template = load_json(query_template_path)
        if not str(template.get("canonical_query") or "").strip():
            errors.append("catalog-query-template.json must include canonical_query")
        for facet, values in (template.get("anchors") or {}).items():
            rows = values if isinstance(values, list) else [values]
            if any(any(ord(ch) > 127 for ch in str(value)) for value in rows):
                errors.append(f"catalog-query-template.json anchor `{facet}` must be canonical ASCII English")
        if query_schema_path.is_file():
            from state_protocol import validate_against_schema

            template_schema_errors = validate_against_schema(template, query_schema)
            if template_schema_errors:
                errors.append(
                    "catalog-query-template.json fails the canonical schema: "
                    + "; ".join(template_schema_errors)
                )

    lanes_path = named_resource_path("discovery-lanes")
    if lanes_path is not None:
        lanes_resource = load_json(lanes_path)
        lanes = lanes_resource.get("lanes") or []
        for message in validate_discovery_lane_targets(
            lanes_resource,
            canonical_ids,
        ):
            errors.append(f"discovery-lanes.json: {message}")
        lane_ids: set[str] = set()
        for lane in lanes:
            if not isinstance(lane, Mapping):
                errors.append("discovery-lanes.json: every lane must be an object")
                continue
            lane_id = str(lane.get("id") or "")
            if not lane_id or lane_id in lane_ids:
                errors.append(f"discovery-lanes.json: invalid or duplicate lane id `{lane_id}`")
            lane_ids.add(lane_id)
            for field in ("style_family_id", "camera_id", "lighting_id"):
                target = str(lane.get(field) or "")
                if target not in canonical_ids:
                    errors.append(f"discovery-lanes.json: lane `{lane_id}` references missing {field} `{target}`")
def check_project_default(root: Path, records: Sequence[Record], errors: list[str]) -> None:
    del root
    defaults_path = named_resource_path("project-defaults")
    assert defaults_path is not None
    defaults = load_json(defaults_path)
    for message in validate_known_resource("project-defaults", defaults):
        errors.append(f"selected project-defaults: {message}")
    profile_id = str(defaults.get("default_render_profile") or "")
    profile = next((r.record for r in records if r.kind == "profile" and r.record.get("id") == profile_id), None)
    if not profile:
        errors.append(f"project default rendering profile is missing: {profile_id}")
    elif profile.get("curation_status") != "curated":
        errors.append(f"project default rendering profile must be curated: {profile_id}")

    cores = [r.record for r in records if r.kind == "aesthetic-core"]
    if defaults.get("default_aesthetic_core") not in (None, ""):
        errors.append("project defaults must not force an aesthetic core; art direction is authoritative")
    for core in cores:
        if core.get("domains") != ["shared"]:
            errors.append(f"universal aesthetic core must be shared: {core.get('id')}")

    creative_policy = defaults.get("creative_policy") or {}
    if creative_policy.get("sparse_brief_discovery_before_final_direction") is not True:
        errors.append("project defaults must enable sparse-brief discovery before final direction")
    if creative_policy.get("preset_names_or_ids_required_for_discovery") is not False:
        errors.append("project defaults must state that preset names or IDs are not required for discovery")
    if creative_policy.get("direction_cards_for_open_axes") is not True:
        errors.append("project defaults must enable direction cards for open axes")

    if defaults.get("default_style_family") not in (None, ""):
        errors.append("project defaults must not force a concrete style family; art direction is authoritative")
    families = [r.record for r in records if r.kind == "style-family"]
    profiles_by_id = {str(r.record.get("id")): r.record for r in records if r.kind == "profile"}
    for family in families:
        base_profile = str(family.get("base_render_profile_id") or "")
        if base_profile not in profiles_by_id:
            errors.append(f"style family references missing base render profile: {family.get('id')} -> {base_profile}")
        for profile_id in family.get("compatible_render_profile_ids", []):
            if str(profile_id) not in profiles_by_id:
                errors.append(f"style family references missing compatible render profile: {family.get('id')} -> {profile_id}")

    realization_defaults = defaults.get("default_domain_realization_by_domain", {})
    realizations = {str(r.record.get("id")): r.record for r in records if r.kind == "domain-realization"}
    expected_domains = CANONICAL_DOMAINS - {"shared"}
    if set(realization_defaults) != expected_domains:
        errors.append(
            "default domain-realization map must cover exactly the six subject domains: "
            f"expected {sorted(expected_domains)}, got {sorted(realization_defaults)}"
        )
    for domain, realization_id in realization_defaults.items():
        realization = realizations.get(str(realization_id))
        if not realization:
            errors.append(f"project default domain realization is missing: {realization_id}")
            continue
        if realization.get("subject_domain") != domain or realization.get("domains") != [domain]:
            errors.append(f"project domain realization does not match domain {domain}: {realization_id}")
        if realization.get("curation_status") != "curated":
            errors.append(f"project domain realization must be curated: {realization_id}")


def check_species_scaffold_policy(
    root: Path,
    records: Sequence[Record],
    errors: list[str],
) -> None:
    del root
    scaffold_path = named_resource_path("species-scaffold-map", required=False)
    if scaffold_path is None:
        return
    scaffold = load_json(scaffold_path)
    species_ids = {
        str(record.record.get("id") or "")
        for record in records
        if record.kind == "module"
        and record.category == "species"
        and record.record.get("id")
    }
    for message in validate_species_scaffold_targets(scaffold, species_ids):
        errors.append(f"selected species-scaffold-map: {message}")


def load_archetype_policy(root: Path, errors: list[str]) -> dict[str, Any]:
    del root
    path = named_resource_path("archetype-policy")
    assert path is not None
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"archetype-policy.json could not be read: {exc}")
        return {}
    required = (
        "curated_archetype_scope", "canonical_subject_domains",
        "required_identity_axes", "creation_basis_values", "creation_gate",
        "growth_policy", "tier_meaning", "domain_separation",
    )
    for key in required:
        if data.get(key) in (None, "", [], {}):
            errors.append(f"archetype-policy.json missing `{key}`")
    canonical = {str(value) for value in data.get("canonical_subject_domains") or []}
    expected = CANONICAL_DOMAINS - {"shared"}
    if canonical and canonical != expected:
        errors.append(
            "archetype-policy.json canonical_subject_domains must match the six subject domains: "
            f"expected {sorted(expected)}, got {sorted(canonical)}"
        )
    return data


def audit(root: Path, *, write_report: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    records = collect_records(root)
    archetype_policy = load_archetype_policy(root, errors)
    curated = [
        record for record in records
        if record.record.get("curation_status") == "curated"
    ]
    for record in curated:
        role = record.record.get("record_role")
        if not role:
            errors.append(f"{record.record.get('id')}: curated record missing record_role")
        if record.kind == "module":
            check_atomic(record, errors, warnings)
            if record.category == "distinctive-detail":
                check_distinctive_detail(record, errors, warnings)
        elif record.kind == "profile":
            check_profile(record, errors, warnings)
        elif record.kind == "aesthetic-core":
            check_aesthetic_core(record, errors, warnings)
        elif record.kind == "style-family":
            check_style_family(record, errors, warnings)
        elif record.kind == "domain-realization":
            check_domain_realization(record, errors, warnings)
        elif record.kind == "scene":
            check_scene(record, errors, warnings)
        elif record.kind == "archetype":
            check_archetype(record, errors, warnings, archetype_policy)
        elif record.kind == "correction":
            check_correction(record, errors, warnings)
    positive_language_findings = check_affirmative_positive_fields(records, errors)
    positive_text_quality_findings = check_positive_text_quality(records, errors)
    check_negative_scope(root, records, errors)
    check_global_integrity(records, errors, warnings)
    check_active_catalog(errors)
    check_medium_family_vocabulary(records, errors)
    check_declared_counts(root, errors)
    check_runtime_search_index(root, records, errors)
    check_project_default(root, records, errors)
    check_species_scaffold_policy(root, records, errors)
    check_recipes(records, errors, warnings)
    duplicate_findings = check_near_duplicates(records, warnings)
    report = {
        "audit": "preset-authoring-standard-conformance",
        "ok": not errors,
        "scope_note": (
            "Checks whole-catalog integrity (label collisions, tag hygiene, canonical domain vocabulary), curated-record structure including archetype identity-axis governance, concrete style families, domain overlays, and distinctive identity details, affirmative prompt-facing data, text-maintenance artifacts, scoped negative activation, canonical-detail preservation, strict canonical identifiers, recipe source preservation, and duplication risk. It does not score artistic quality."
        ),
        "records_total": len(records),
        "curated_records": len(curated),
        "tier_counts": {
            "curated": len(curated),
            "vocabulary": len(records) - len(curated),
        },
        "curated_by_kind": {
            kind: sum(1 for record in curated if record.kind == kind)
            for kind in sorted({record.kind for record in curated})
        },
        "archetype_counts": {
            "total": sum(1 for record in records if record.kind == "archetype"),
            "curated": sum(1 for record in curated if record.kind == "archetype"),
            "vocabulary": sum(
                1 for record in records
                if record.kind == "archetype" and record.record.get("curation_status") != "curated"
            ),
            "by_domain": {
                domain: sum(
                    1 for record in records
                    if record.kind == "archetype" and record.record.get("domain") == domain
                )
                for domain in sorted(CANONICAL_DOMAINS - {"shared"})
            },
        },
        "near_duplicate_findings": duplicate_findings,
        "positive_language_findings": positive_language_findings,
        "positive_text_quality_findings": positive_text_quality_findings,
        "errors": errors,
        "warnings": warnings,
    }
    if write_report:
        (root / "preset-authoring-audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_pack_runtime_arguments(parser)
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--report-out", help="Optional external JSON report path")
    args = parser.parse_args(argv)
    runtime_context = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime_context.settings)
    try:
        report = audit(Path(args.root).resolve(), write_report=False)
        if args.report_out:
            Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    finally:
        configure_pack_runtime(None)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
