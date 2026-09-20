#!/usr/bin/env python3
"""Validate semantic contracts for named resources understood by the core.

Content packs may bind any opaque resource name. The small set listed here is
different: core workflows read these logical resources and therefore require
their behavioral invariants to remain stable regardless of which pack is the
explicitly selected provider.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from search_prompt_vocabulary import VocabularyError, validate_vocabulary
from prompt_writing_guide import (
    PromptWritingGuideError,
    validate_prompt_writing_guide,
)


SEMANTIC_EXCLUSION_SOURCE = "semantic_exclusions"
SEMANTIC_EXCLUSION_SUFFIX = "only when the user explicitly excludes them."
DIAGNOSTIC_ONLY_NEGATIVE_SOURCES = (
    "scene_failure_modes",
    "atomic_misreadings",
)
IDENTITY_AUTHORITY_PREFIX = (
    "explicit user species anchor",
    "approved Character Identity Contract",
)
PRESERVE_SPECIES_RULE = "preserve-user-or-contract-species"


def medium_selection_allowed(
    project_defaults: Mapping[str, Any],
    medium_families: Sequence[str],
    *,
    explicit_hybrid_request: bool,
) -> bool:
    """Apply the selected project-defaults medium policy to one request."""
    policy = project_defaults.get("medium_policy")
    if not isinstance(policy, Mapping):
        raise ValueError("medium_policy must be an object")
    families = tuple(dict.fromkeys(str(value) for value in medium_families if value))
    if len(families) <= 1:
        return True
    if policy.get("single_medium_family_by_default") is not True:
        return True
    if policy.get("hybrid_requires_explicit_request") is True:
        return bool(explicit_hybrid_request)
    return True


def negative_source_emission_allowed(
    negative_policy: Mapping[str, Any],
    source_id: str,
    *,
    user_explicitly_excluded: bool = False,
) -> bool:
    """Apply the selected negative-policy source activation boundary."""
    if source_id == SEMANTIC_EXCLUSION_SOURCE:
        rule = str(negative_policy.get("semantic_exclusion_rule") or "").strip()
        if not rule.endswith(SEMANTIC_EXCLUSION_SUFFIX):
            raise ValueError("semantic exclusions must be user-request-only")
        return bool(user_explicitly_excluded)

    diagnostic = negative_policy.get("diagnostic_only_sources")
    if isinstance(diagnostic, Mapping) and source_id in diagnostic:
        row = diagnostic[source_id]
        if not isinstance(row, Mapping):
            raise ValueError(f"diagnostic-only source {source_id!r} must be an object")
        return row.get("automatic_emission") is True

    automatic = negative_policy.get("automatic_sources")
    if isinstance(automatic, Mapping) and source_id in automatic:
        return True
    raise ValueError(f"unknown negative-policy source: {source_id}")


def validate_project_defaults(value: Any) -> list[str]:
    """Return current medium-policy contract errors for project-defaults."""
    if not isinstance(value, Mapping):
        return ["project-defaults must contain an object"]
    policy = value.get("medium_policy")
    if not isinstance(policy, Mapping):
        return ["medium_policy must be an object"]

    errors: list[str] = []
    if policy.get("single_medium_family_by_default") is not True:
        errors.append("medium_policy.single_medium_family_by_default must be true")
    if policy.get("hybrid_requires_explicit_request") is not True:
        errors.append("medium_policy.hybrid_requires_explicit_request must be true")
    try:
        if not medium_selection_allowed(
            value,
            ["single-medium"],
            explicit_hybrid_request=False,
        ):
            errors.append("the selected medium policy must allow one medium family")
        if medium_selection_allowed(
            value,
            ["medium-a", "medium-b"],
            explicit_hybrid_request=False,
        ):
            errors.append("the selected medium policy must reject an unrequested hybrid")
        if not medium_selection_allowed(
            value,
            ["medium-a", "medium-b"],
            explicit_hybrid_request=True,
        ):
            errors.append("the selected medium policy must allow an explicitly requested hybrid")
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def validate_negative_policy(value: Any) -> list[str]:
    """Return source-activation contract errors for negative-policy."""
    if not isinstance(value, Mapping):
        return ["negative-policy must contain an object"]
    errors: list[str] = []
    try:
        if negative_source_emission_allowed(
            value,
            SEMANTIC_EXCLUSION_SOURCE,
            user_explicitly_excluded=False,
        ):
            errors.append("semantic exclusions must not emit without an explicit user exclusion")
        if not negative_source_emission_allowed(
            value,
            SEMANTIC_EXCLUSION_SOURCE,
            user_explicitly_excluded=True,
        ):
            errors.append("an explicit user exclusion must be eligible for negative emission")
    except ValueError as exc:
        errors.append(str(exc))

    diagnostic = value.get("diagnostic_only_sources")
    for source_id in DIAGNOSTIC_ONLY_NEGATIVE_SOURCES:
        row = diagnostic.get(source_id) if isinstance(diagnostic, Mapping) else None
        if not isinstance(row, Mapping):
            errors.append(f"diagnostic_only_sources.{source_id} must be an object")
            continue
        if row.get("automatic_emission") is not False:
            errors.append(
                f"diagnostic_only_sources.{source_id}.automatic_emission must be false"
            )
            continue
        if negative_source_emission_allowed(value, source_id):
            errors.append(f"diagnostic-only source {source_id} must not emit automatically")
    return errors


def validate_species_scaffold_map(value: Any) -> list[str]:
    """Return identity-authority errors for species-scaffold-map."""
    if not isinstance(value, Mapping):
        return ["species-scaffold-map must contain an object"]
    errors: list[str] = []
    raw_authorities = value.get("identity_authority_order")
    authorities = list(raw_authorities) if isinstance(raw_authorities, list) else []
    if authorities[:2] != list(IDENTITY_AUTHORITY_PREFIX):
        errors.append(
            "identity_authority_order must begin with explicit user species anchor "
            "and approved Character Identity Contract"
        )

    mappings = value.get("species_to_scaffold")
    if not isinstance(mappings, Mapping) or not mappings:
        errors.append("species_to_scaffold must be a non-empty object")
        return errors
    for species_id, row in mappings.items():
        if not isinstance(row, Mapping):
            errors.append(f"species_to_scaffold.{species_id} must be an object")
        elif row.get("identity_rule") != PRESERVE_SPECIES_RULE:
            errors.append(
                f"species_to_scaffold.{species_id}.identity_rule must be "
                f"{PRESERVE_SPECIES_RULE!r}"
            )
    return errors


def validate_species_scaffold_targets(
    value: Any,
    active_species_record_ids: Sequence[str] | set[str],
) -> list[str]:
    """Require one scaffold mapping for every active species record, and no others."""
    errors = validate_species_scaffold_map(value)
    if errors or not isinstance(value, Mapping):
        return errors
    mappings = value.get("species_to_scaffold")
    if not isinstance(mappings, Mapping):
        return errors
    expected = {str(record_id) for record_id in active_species_record_ids}
    observed = {str(record_id) for record_id in mappings}
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing:
        errors.append(f"missing active species scaffold mappings: {missing}")
    if extra:
        errors.append(f"unknown species scaffold mappings: {extra}")
    if value.get("species_count") != len(expected):
        errors.append(
            "species_count must equal the active species record count "
            f"({len(expected)})"
        )
    return errors


def validate_discovery_lanes(value: Any) -> list[str]:
    """Return provider-local structure errors for discovery-lanes."""
    if not isinstance(value, Mapping):
        return ["discovery-lanes must contain an object"]
    lanes = value.get("lanes")
    if not isinstance(lanes, list):
        return ["lanes must be an array"]
    errors: list[str] = []
    for index, lane in enumerate(lanes):
        if not isinstance(lane, Mapping):
            errors.append(f"lanes[{index}] must be an object")
            continue
        lane_id = str(lane.get("id") or f"index-{index}")
        preferred = lane.get("preferred_scene_ids")
        if preferred is not None and (
            not isinstance(preferred, list)
            or any(not isinstance(target, str) or not target for target in preferred)
        ):
            errors.append(
                f"lane {lane_id!r} preferred_scene_ids must be an array of non-empty IDs"
            )
    return errors


def validate_discovery_lane_targets(
    value: Any,
    canonical_record_ids: Sequence[str] | set[str],
) -> list[str]:
    """Resolve every preferred scene against the active canonical record set."""
    errors = validate_discovery_lanes(value)
    if errors or not isinstance(value, Mapping):
        return errors
    available = {str(record_id) for record_id in canonical_record_ids}
    for index, lane in enumerate(value.get("lanes") or []):
        if not isinstance(lane, Mapping):
            continue
        lane_id = str(lane.get("id") or f"index-{index}")
        for target in lane.get("preferred_scene_ids") or []:
            if str(target) not in available:
                errors.append(
                    f"lane {lane_id!r} references missing preferred scene {str(target)!r}"
                )
    return errors


def validate_prompt_vocabulary(value: Any) -> list[str]:
    """Return schema and uniqueness errors for a prompt-vocabulary resource."""
    try:
        validate_vocabulary(value)
    except VocabularyError as exc:
        return [str(exc)]
    return []


def validate_prompt_writing_resource(value: Any) -> list[str]:
    """Return schema and uniqueness errors for a prompt-writing-guide resource."""
    try:
        validate_prompt_writing_guide(value)
    except PromptWritingGuideError as exc:
        return [str(exc)]
    return []


KNOWN_RESOURCE_VALIDATORS: dict[str, Callable[[Any], list[str]]] = {
    "discovery-lanes": validate_discovery_lanes,
    "negative-policy": validate_negative_policy,
    "project-defaults": validate_project_defaults,
    "prompt-vocabulary": validate_prompt_vocabulary,
    "prompt-writing-guide": validate_prompt_writing_resource,
    "species-scaffold-map": validate_species_scaffold_map,
}


def validate_known_resource(name: str, value: Any) -> list[str]:
    """Validate one core-interpreted named resource; unknown names stay opaque."""
    validator = KNOWN_RESOURCE_VALIDATORS.get(str(name))
    return validator(value) if validator is not None else []
