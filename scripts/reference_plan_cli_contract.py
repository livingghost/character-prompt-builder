#!/usr/bin/env python3
"""Derive reference-plan CLI help and examples from the canonical schema."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SURFACE_LIGHTING_SCHEMA = ROOT / "schemas" / "surface-lighting-plan.schema.json"
SURFACE_LIGHTING_TEMPLATE = ROOT / "templates" / "surface-lighting-plan.json"


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


@lru_cache(maxsize=1)
def surface_lighting_schema() -> dict[str, Any]:
    """Return the canonical Surface and Lighting Plan JSON Schema."""

    return _load_object(SURFACE_LIGHTING_SCHEMA)


@lru_cache(maxsize=1)
def surface_lighting_template() -> dict[str, Any]:
    """Return the canonical example artifact used to derive compact CLI examples."""

    return _load_object(SURFACE_LIGHTING_TEMPLATE)


def _array_item_contract(property_name: str) -> tuple[tuple[str, ...], dict[str, Any]]:
    schema = surface_lighting_schema()
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError("surface-lighting-plan schema has no properties object")
    array_schema = properties.get(property_name)
    if not isinstance(array_schema, Mapping):
        raise ValueError(
            f"surface-lighting-plan schema has no {property_name!r} property"
        )
    item_schema = array_schema.get("items")
    if not isinstance(item_schema, Mapping):
        raise ValueError(f"{property_name} has no object item schema")
    required = item_schema.get("required")
    item_properties = item_schema.get("properties")
    if not isinstance(required, list) or not all(isinstance(value, str) for value in required):
        raise ValueError(f"{property_name}.items.required must be a string array")
    if not isinstance(item_properties, Mapping):
        raise ValueError(f"{property_name}.items.properties must be an object")
    return tuple(required), dict(item_properties)


def _template_item(property_name: str, required: tuple[str, ...]) -> dict[str, Any]:
    values = surface_lighting_template().get(property_name)
    if not isinstance(values, list) or not values or not isinstance(values[0], Mapping):
        raise ValueError(
            f"surface-lighting-plan template requires one {property_name} example"
        )
    example = dict(values[0])
    missing = [field for field in required if field not in example]
    extras = [field for field in example if field not in required]
    if missing or extras:
        raise ValueError(
            f"{property_name} template/schema drift: missing={missing}, extras={extras}"
        )
    return {field: example[field] for field in required}


def surface_lighting_argument_contract() -> dict[str, Any]:
    """Return the schema-derived contracts for repeatable planning arguments."""

    light_required, _light_properties = _array_item_contract("light_sources")
    material_required, _material_properties = _array_item_contract("material_responses")
    return {
        "canonical_schema": SURFACE_LIGHTING_SCHEMA.relative_to(ROOT).as_posix(),
        "light_source": {
            "argument": "--light-source-json",
            "required_fields": list(light_required),
            "example": _template_item("light_sources", light_required),
        },
        "material_response": {
            "argument": "--material-response-json",
            "required_fields": list(material_required),
            "example": _template_item("material_responses", material_required),
        },
    }


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def surface_argument_help(contract_name: str) -> str:
    contract = surface_lighting_argument_contract()[contract_name]
    return (
        "Repeatable JSON object. Required fields: "
        + ", ".join(contract["required_fields"])
        + ".\nExample: "
        + compact_json(contract["example"])
        + "\nCanonical schema: "
        + surface_lighting_argument_contract()["canonical_schema"]
    )


def plan_cli_example() -> dict[str, Any]:
    """Return a discoverable minimal planning example without pack-specific IDs."""

    contract = surface_lighting_argument_contract()
    return {
        "command": "plan",
        "description": (
            "Replace scene-record-id and the pack runtime values with active values. "
            "Repeat record-use and surface arguments when the plan needs more than one."
        ),
        "argv": [
            "plan",
            "--record-use",
            "scene-record-id=pose-camera",
            "--transport-mode",
            "prompt-artifacts",
            "--source-lighting-mode",
            "replace",
            "--light-source-json",
            compact_json(contract["light_source"]["example"]),
            "--material-response-json",
            compact_json(contract["material_response"]["example"]),
            "--out",
            "reference-use-plan.json",
            "--state-file",
            "/path/to/pack-state.json",
            "--cache-dir",
            "/path/to/catalog-cache",
            "--managed-root",
            "/path/to/managed-packs",
        ],
        "surface_lighting_arguments": contract,
        "notes": [
            "Do not pass --target-model for prompt-artifacts or svg-bundle.",
            "Pass --target-model for multi-image or single-board.",
            "Use the same explicit pack runtime arguments for plan and execute.",
            "Append --pack-root /path/to/additional-pack-root for each additional discovery root.",
        ],
    }


__all__ = [
    "SURFACE_LIGHTING_SCHEMA",
    "compact_json",
    "plan_cli_example",
    "surface_argument_help",
    "surface_lighting_argument_contract",
    "surface_lighting_schema",
]
