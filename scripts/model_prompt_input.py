"""Read a model's explicit prompt-input contract without guessing from its name.

The record owns the selected input workflow and its evidence. Tag-based input
requires vocabulary search even when the model also accepts descriptive prose.
An unresolved target remains unresolved until an author supplies its evidence.
"""
from __future__ import annotations

import copy
import json
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
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    _check(value, schema, "prompt_input")
    _check_dates(value)


def resolve_prompt_input(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return an exact copy after validating the input and owning family together."""
    if not isinstance(record, Mapping):
        raise ValueError("model prompt input: expected a model record")
    _check(dict(record), {"$ref": "model-prompt-input.schema.json#/$defs/model-record"},
           "model prompt input")
    value = record["prompt_input"]
    _check_dates(value)
    return copy.deepcopy(value)


def prompt_input_card(record: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the selected workflow, evidence, and vocabulary-search obligation."""
    value = resolve_prompt_input(record)
    return {
        "prompt_input": value,
        "prompt_dialect": record.get("prompt_dialect"),
        "requires_vocabulary_search": value["mode"] == "tag-based",
    }
