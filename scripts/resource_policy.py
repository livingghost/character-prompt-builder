#!/usr/bin/env python3
"""Validate the named resources the core understands.

Content packs may bind any resource name. The names listed here are different:
core workflows read them, so their contracts hold in every pack that binds them.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from search_prompt_vocabulary import VocabularyError, validate_vocabulary
from prompt_writing_guide import (
    PromptWritingGuideError,
    validate_prompt_writing_guide,
)


SEMANTIC_EXCLUSION_SOURCE = "semantic_exclusions"
DIAGNOSTIC_ONLY_NEGATIVE_SOURCES = (
    "scene_failure_modes",
    "atomic_misreadings",
)


def negative_source_emission_allowed(
    negative_policy: Mapping[str, Any],
    source_id: str,
    *,
    source_activated: bool = False,
    user_explicitly_excluded: bool = False,
) -> bool:
    """Check declared source authority and the author's activation decision."""
    if source_id == SEMANTIC_EXCLUSION_SOURCE:
        rule = negative_policy.get("semantic_exclusion_rule")
        if not isinstance(rule, Mapping) or rule.get("requires_user_exclusion") is not True:
            raise ValueError("semantic exclusions must be user-request-only")
        return bool(user_explicitly_excluded)

    diagnostic = negative_policy.get("diagnostic_only_sources")
    if isinstance(diagnostic, Mapping) and source_id in diagnostic:
        row = diagnostic[source_id]
        if not isinstance(row, Mapping):
            raise ValueError(f"diagnostic-only source {source_id!r} must be an object")
        return row.get("automatic_emission") is True

    candidates = negative_policy.get("candidate_sources")
    if isinstance(candidates, Mapping) and source_id in candidates:
        return bool(source_activated)
    raise ValueError(f"unknown negative-policy source: {source_id}")


def validate_pack_defaults(value: Any) -> list[str]:
    """Check declared authoring authority in pack-defaults."""
    if not isinstance(value, Mapping):
        return ["pack-defaults must contain an object"]

    errors: list[str] = []
    creative = value.get("creative_policy")
    if not isinstance(creative, Mapping):
        errors.append("creative_policy must be an object")
    else:
        for key, expected in (
            ("expression_knowledge_before_open_choices", True),
            ("agent_selects_expression", True),
            ("preset_names_or_ids_required_for_discovery", False),
        ):
            if creative.get(key) is not expected:
                errors.append(f"creative_policy.{key} must be {str(expected).lower()}")
    return errors


def validate_negative_policy(value: Any) -> list[str]:
    """Return source-activation contract errors for negative-policy."""
    if not isinstance(value, Mapping):
        return ["negative-policy must contain an object"]
    errors: list[str] = []
    candidates = value.get("candidate_sources")
    if not isinstance(candidates, Mapping):
        errors.append("candidate_sources must be an object")
    else:
        for source_id, source in candidates.items():
            if not isinstance(source_id, str) or not source_id.strip():
                errors.append("candidate source IDs must be nonempty strings")
            if (not isinstance(source, Mapping) or not isinstance(source.get("activation"), str)
                    or not source["activation"].strip()):
                errors.append(f"candidate source {source_id!r} requires activation guidance")
    rule = value.get("semantic_exclusion_rule")
    if isinstance(rule, Mapping) and (not isinstance(rule.get("guidance"), str) or not rule["guidance"].strip()):
        errors.append("semantic_exclusion_rule.guidance must be nonempty text")
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


def validate_model_selection_preferences(value: Any) -> list[str]:
    """Apply the same preference contract to pack resources and home overrides."""
    from model_suitability import validate_preferences
    try:
        validate_preferences(value)
    except (ValueError, TypeError) as exc:
        return [str(exc)]
    return []


KNOWN_RESOURCE_VALIDATORS: dict[str, Callable[[Any], list[str]]] = {
    "negative-policy": validate_negative_policy,
    "pack-defaults": validate_pack_defaults,
    "prompt-vocabulary": validate_prompt_vocabulary,
    "prompt-writing-guide": validate_prompt_writing_resource,
    "model-selection-preferences": validate_model_selection_preferences,
}


def validate_known_resource(name: str, value: Any) -> list[str]:
    """Validate one core-interpreted named resource; unknown names stay opaque."""
    validator = KNOWN_RESOURCE_VALIDATORS.get(str(name))
    return validator(value) if validator is not None else []
