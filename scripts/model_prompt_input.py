"""Resolve prompt authoring from a selected record without model classification.

The record owns the documented wording and vocabulary requirements. Missing
input evidence stays unknown without preventing drafting or claiming that a
form is unsupported. Actual no-text, grammar and interface limits still apply.
"""
from __future__ import annotations

import copy
from datetime import date
from pathlib import Path
from typing import Any, Mapping

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "model-prompt-input.schema.json"


def _check(value: Any, schema: dict[str, Any], where: str) -> None:
    from state_protocol import validate_against_schema

    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError(where + ": " + "; ".join(errors))


def _check_dates(value: Mapping[str, Any]) -> None:
    for index, basis in enumerate(value["basis"]):
        try:
            date.fromisoformat(basis["observed_at"])
        except ValueError:
            raise ValueError(f"prompt_input.basis[{index}].observed_at: expected a calendar date") from None


def validate_prompt_input(value: Any) -> None:
    """Validate a declared input workflow and its evidence; infer no defaults."""
    from state_protocol import read_schema
    schema = read_schema(SCHEMA_PATH)
    _check(value, schema, "prompt_input")
    _check_dates(value)


def resolve_prompt_input(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate declared input, or retain absent evidence as an unresolved input.

    Pack validation still requires its authored declaration. An acquired target
    can omit classification; no provider claim or evidence is fabricated for it.
    An explicitly supplied malformed declaration is never replaced by the default.
    """
    if not isinstance(record, Mapping):
        raise ValueError("model prompt input: expected a model record")
    selected = dict(record)
    if "prompt_input" not in selected:
        selected["prompt_input"] = {"mode": "unresolved", "forms": [], "vocabularies": [], "basis": []}
    _check(selected, {"$ref": "model-prompt-input.schema.json#/$defs/model-record"},
           "model prompt input")
    value = selected["prompt_input"]
    _check_dates(value)
    return copy.deepcopy(value)


def _authoring_plan(record: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    """Turn documented choices into writing instructions, not an exclusivity claim."""
    mode = value["mode"]
    forms = list(value["forms"])
    available = list(forms)
    if {"tags", "natural-language"}.issubset(forms):
        available.append("mixed")
    if mode == "none":
        surface, preferred = "absent", None
        composition = ["Use the selected operation's media and controls; it has no text prompt surface."]
    elif mode == "unresolved":
        surface, preferred = "unknown", "unspecified"
        composition = [
            "Write the requested depiction in the user's requested form; otherwise use clear interface-neutral wording.",
            "Input-form evidence remains unknown. Continue drafting and checking known interface constraints without treating unknown forms as unsupported.",
        ]
    elif mode == "tag-based":
        surface, preferred = "present", "tags"
        composition = [
            "Build the rendition from searched concepts using the selected family's spelling, controls and ordering.",
        ]
        if "mixed" in available:
            composition.append("Natural-language wording and mixtures are available when useful for the requested meaning; an explicit tags-only request keeps its form.")
    else:
        surface = "present"
        preferred = "natural-language" if "natural-language" in forms else "structured-caption"
        composition = [
            "Describe the subject, action, relationships and visible scene directly, following the selected model's prompt style and ordering."
            if preferred == "natural-language" else
            "Write the scene in the documented structured-caption form, following the selected model's prompt style and ordering.",
        ]
    if mode != "none":
        composition.extend([
            "Preserve the requested depiction and any explicitly requested form; apply the exact parser and channel constraints separately.",
            "The available wording is documented guidance, not an exhaustive list of permitted forms or proof that unlisted forms fail.",
        ])
    required = mode == "tag-based"
    return {
        "text_surface": surface,
        "evidence_status": "unresolved" if mode == "unresolved" else "declared",
        "preferred_wording": preferred,
        "available_wording": available,
        "composition": composition,
        "vocabulary": {
            "required": required,
            "action": "search-vocabulary" if required else "no-text" if mode == "none" else "not-required",
            "vocabularies": list(value["vocabularies"]),
            "dialect": record.get("prompt_dialect"),
        },
        "prompt_style": copy.deepcopy(record.get("prompt_style")),
        "ordering": copy.deepcopy(record.get("ordering")),
    }


def prompt_input_card(record: Mapping[str, Any]) -> dict[str, Any]:
    """Deliver the writing plan, exact evidence and automatic vocabulary requirement."""
    value = resolve_prompt_input(record)
    return {
        "prompt_input": value,
        "prompt_dialect": record.get("prompt_dialect"),
        "requires_vocabulary_search": value["mode"] == "tag-based",
        "prompt_authoring": _authoring_plan(record, value),
    }
