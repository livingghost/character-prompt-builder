#!/usr/bin/env python3
"""Validate, resolve, project, and hash Shared State Protocol artifacts.

This utility is deterministic support code. It never invents canon, emotional
meaning, culture rules, visual direction, or final prompt prose. Those remain
agent and user decisions. The tool validates explicit artifacts, resolves
approved event history, extracts scene state, assembles an authored visual
projection, and prepares reference-bundle plans from declared coverage needs.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from package_metadata import PACKAGE_NAME
import protocol_contract as public_contract
from temporal_state import (
    array_index, decode_pointer, get_pointer, _parent_for_pointer, apply_change, entity_root, precondition_holds, _is_lifecycle_change, _state_path_key, validate_temporal_inputs, _approved_events_as_of, _change_is_active, _restartable_epochs, _process_operations, apply_event, resolve_world
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"

# This registry is the validation boundary for typed CPB artifacts.  Schema
# selection must never be derived from an untrusted artifact_type string.
ARTIFACT_SCHEMA_FILES = {
    "render-intent": "render-intent.schema.json",
    "render-contract": "render-contract.schema.json",
    "adoption-receipt": "adoption-receipt.schema.json",
    "appearance-adaptation-proposal": "appearance-adaptation-proposal.schema.json",
    "appearance-variant-contract": "appearance-variant-contract.schema.json",
    "asset-render-specification": "asset-render-specification.schema.json",
    "audit-extraction-set": "audit-extraction-set.schema.json",
    "candidate-manifest": "candidate-manifest.schema.json",
    "character-identity-contract": "character-identity-contract.schema.json",
    "character-state-schema": "character-state-schema.schema.json",
    "drift-observation": "drift-observation.schema.json",
    "environment-snapshot": "environment-snapshot.schema.json",
    "external-contract-reference": "external-contract-reference.schema.json",
    "era-contract": "era-contract.schema.json",
    "form-contract": "form-contract.schema.json",
    "individual-morphology-contract": "individual-morphology-contract.schema.json",
    "integration-capability-manifest": "integration-capability-manifest.schema.json",
    "interchange-envelope": "interchange-envelope.schema.json",
    "inventory-state": "inventory-state.schema.json",
    "observed-render-state": "observed-render-state.schema.json",
    "prompt-plot": "prompt-plot.schema.json",
    "prompt-retrieval-record": "prompt-retrieval-record.schema.json",
    "reference-bundle-plan": "reference-bundle-plan.schema.json",
    "reference-corpus-manifest": "reference-corpus-manifest.schema.json",
    "reference-selection": "reference-selection.schema.json",
    "reference-use-plan": "reference-use-plan.schema.json",
    "prepared-reference-set": "prepared-reference-set.schema.json",
    "surface-lighting-plan": "surface-lighting-plan.schema.json",
    "upscale-package": "upscale-package.schema.json",
    "reference-semantic-region-map": "reference-semantic-region-map.schema.json",
    "reference-visual-authority": "reference-visual-authority.schema.json",
    "relationship-projection": "relationship-projection.schema.json",
    "relationship-state": "relationship-state.schema.json",
    "runtime-attachment-build": "runtime-attachment-build.schema.json",
    "scene-context-snapshot": "scene-context-snapshot.schema.json",
    "semantic-region-map": "semantic-region-map.schema.json",
    "species-morphology-profile": "species-morphology-profile.schema.json",
    "state-aware-reference-binding": "state-aware-reference-binding.schema.json",
    "state-event": "state-event.schema.json",
    "state-lineage": "state-lineage.schema.json",
    "state-process": "state-process.schema.json",
    "state-snapshot": "state-snapshot.schema.json",
    "vectorization-result": "vectorization-result.schema.json",
    "visual-authority": "visual-authority.schema.json",
    "visual-evidence-bundle": "visual-evidence-bundle.schema.json",
    "visual-state-projection": "visual-state-projection.schema.json",
    "wardrobe-state": "wardrobe-state.schema.json",
    "world-state-snapshot": "world-state-snapshot.schema.json",
}

ARTIFACT_SCHEMA_FILES.update({kind: kind + '.schema.json' for kind in ('scene-persona-material', 'source-material-index', 'source-extraction-proposal')})

ZERO_SHA256 = "0" * 64
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
UTC_RFC3339_RE = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)

SELF_HASH_FIELDS = {
    "audit-extraction-set": "audit_extraction_set_sha256",
    "integration-capability-manifest": "manifest_sha256",
    "interchange-envelope": "envelope_sha256",
    "reference-corpus-manifest": "reference_corpus_manifest_sha256",
    "reference-semantic-region-map": "semantic_region_map_sha256",
    "reference-visual-authority": "visual_authority_sha256",
    "runtime-attachment-build": "runtime_attachment_build_sha256",
    "vectorization-result": "vectorization_result_sha256",
    "species-morphology-profile": "species_profile_sha256",
    "individual-morphology-contract": "individual_morphology_sha256",
    "world-state-snapshot": "world_state_sha256",
    "state-snapshot": "state_snapshot_sha256",
    "relationship-state": "relationship_state_sha256",
    "environment-snapshot": "environment_snapshot_sha256",
    "wardrobe-state": "wardrobe_state_sha256",
    "inventory-state": "inventory_state_sha256",
    "scene-context-snapshot": "context_snapshot_sha256",
    "relationship-projection": "relationship_projection_sha256",
    "visual-state-projection": "projection_sha256",
    "state-aware-reference-binding": "binding_sha256",
    "asset-render-specification": "render_spec_sha256",
    "reference-bundle-plan": "bundle_plan_sha256",
    "candidate-manifest": "candidate_manifest_sha256",
    "adoption-receipt": "adoption_receipt_sha256",
    "observed-render-state": "observation_sha256",
    "drift-observation": "drift_observation_sha256",
    "state-lineage": "lineage_sha256",
    "appearance-adaptation-proposal": "proposal_sha256",
    "reference-selection": "selection_sha256",
    "reference-use-plan": "reference_use_plan_sha256",
    "prepared-reference-set": "prepared_reference_set_sha256",
    "surface-lighting-plan": "surface_lighting_plan_sha256",
    "upscale-package": "upscale_package_sha256",
    "visual-authority": "visual_authority_sha256",
    "semantic-region-map": "semantic_region_map_sha256",
    "visual-evidence-bundle": "visual_evidence_bundle_sha256",
}

STATE_LINEAGE_ARTIFACT_FIELDS = {
    "species_profile_sha256": "species-morphology-profile",
    "individual_morphology_sha256": "individual-morphology-contract",
    "identity_contract_sha256": "character-identity-contract",
    "era_contract_sha256": "era-contract",
    "form_contract_sha256": "form-contract",
    "appearance_variant_sha256": "appearance-variant-contract",
    "state_snapshot_sha256": "state-snapshot",
    "scene_context_sha256": "scene-context-snapshot",
    "visual_projection_sha256": "visual-state-projection",
    "asset_render_spec_sha256": "asset-render-specification",
    "visual_authority_sha256": "visual-authority",
    "visual_evidence_bundle_sha256": "visual-evidence-bundle",
}

STATE_AWARE_REQUIRED_LINEAGE_FIELDS = (
    "species_profile_sha256",
    "individual_morphology_sha256",
    "identity_contract_sha256",
    "state_snapshot_sha256",
    "scene_context_sha256",
    "visual_projection_sha256",
    "asset_render_spec_sha256",
)

ENTITY_BUCKETS = {
    "character": "characters",
    "relationship": "relationships",
    "environment": "environments",
    "prop": "props",
    "world": "world",
}

STATE_MUTATION_OPERATIONS = frozenset({
    "set", "replace", "merge", "remove", "append", "increment",
})
PROCESS_LIFECYCLE_OPERATIONS = frozenset({
    "interrupt-process", "restart-process",
})




STATE_SECTION_NAMES = (
    "physical_state",
    "appearance_state",
    "wardrobe_state",
    "equipment_state",
    "inventory_state",
    "emotional_state",
    "performance_state",
    "knowledge_state",
    "social_role_state",
    "character_specific_state",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def find_non_finite_numbers(value: Any, path: str = "$") -> list[str]:
    """Return paths containing floats that JSON cannot represent portably."""

    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(find_non_finite_numbers(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_non_finite_numbers(child, f"{path}[{index}]"))
    elif isinstance(value, float) and not math.isfinite(value):
        findings.append(path)
    return findings


def is_valid_utc_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or UTC_RFC3339_RE.fullmatch(value) is None:
        return False
    try:
        dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def parse_json(text: str) -> Any:
    """Parse strict JSON, rejecting Python's non-standard NaN/Infinity tokens."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result
    return json.loads(text, parse_constant=_reject_json_constant, object_pairs_hook=unique_object)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def is_concrete_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value)) and value != ZERO_SHA256


def find_placeholder_hashes(value: Any, path: str = "$") -> list[str]:
    """Return hash-valued fields that use the all-zero placeholder digest."""
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if (key == "sha256" or key.endswith("_sha256")) and child == ZERO_SHA256:
                findings.append(child_path)
            findings.extend(find_placeholder_hashes(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_placeholder_hashes(child, f"{path}[{index}]"))
    return findings


def load_json(path: Path) -> dict[str, Any]:
    data = parse_json(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return data


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = parse_json(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"JSONL record must be an object at {path}:{line_number}")
        records.append(item)
    return records


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def artifact_type(data: dict[str, Any]) -> str:
    value = str(data.get("artifact_type") or "")
    if not value:
        raise ValueError("artifact_type is required")
    return value


def schema_for(data: dict[str, Any]) -> dict[str, Any]:
    kind = artifact_type(data)
    if kind in public_contract.ARTIFACT_TYPES:
        return public_contract.schema_for(data)
    schema_name = ARTIFACT_SCHEMA_FILES.get(kind)
    if schema_name is None:
        raise ValueError(f"no schema registered for artifact_type: {kind}")
    path = SCHEMA_DIR / schema_name
    if not path.is_file():
        raise ValueError(f"registered schema is missing for artifact_type {kind}: {schema_name}")
    schema = load_json(path)
    unsupported = unsupported_schema_keywords(schema)
    if unsupported:
        raise ValueError(
            f"{path.name} uses schema keywords this validator does not implement: "
            + ", ".join(unsupported)
        )
    return schema


def artifact_content_for_hash(data: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(data)
    field = SELF_HASH_FIELDS.get(str(value.get("artifact_type") or ""))
    if field:
        value.pop(field, None)
    return value


def artifact_hash(data: dict[str, Any]) -> str:
    if data.get("artifact_type") in public_contract.ARTIFACT_TYPES:
        return public_contract.artifact_hash(data)
    return sha256_json(artifact_content_for_hash(data))


def finalize_artifact(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("artifact_type") in public_contract.ARTIFACT_TYPES:
        return public_contract.finalize_artifact(data)
    result = copy.deepcopy(data)
    kind = artifact_type(result)
    field = SELF_HASH_FIELDS.get(kind)
    if field:
        result[field] = artifact_hash(result)
    return result


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _json_pointer(root: Any, fragment: str) -> dict[str, Any]:
    if fragment in {"", "#"}:
        if not isinstance(root, dict):
            raise ValueError("schema root must be an object")
        return root
    pointer = fragment[1:] if fragment.startswith("#") else fragment
    if not pointer.startswith("/"):
        raise ValueError(f"unsupported schema reference fragment: {fragment}")
    current = root
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list) and _ARRAY_INDEX.match(token) and int(token) < len(current):
            current = current[int(token)]
            continue
        raise ValueError(f"schema reference does not exist: {fragment}")
    if not isinstance(current, dict):
        raise ValueError(f"schema reference does not identify a schema object: {fragment}")
    return current


def _resolve_ref(ref: str, root_schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if ref.startswith("http://") or ref.startswith("https://"):
        raise ValueError(f"remote schema references are unsupported: {ref}")
    if ref.startswith("#"):
        return _json_pointer(root_schema, ref), root_schema
    relative, separator, fragment = ref.partition("#")
    path = (SCHEMA_DIR / relative).resolve()
    if SCHEMA_DIR.resolve() not in path.parents and path != SCHEMA_DIR.resolve():
        raise ValueError(f"schema reference escapes schema directory: {ref}")
    referenced_root = load_json(path)
    if separator:
        return _json_pointer(referenced_root, f"#{fragment}"), referenced_root
    return referenced_root, referenced_root


# Keywords this validator actually enforces. Anything outside this set and the
# annotation set below would be written down as a constraint and never applied.
SUPPORTED_SCHEMA_KEYWORDS = frozenset({
    "$ref", "$defs", "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
    "const", "enum", "type",
    "minLength", "maxLength", "pattern", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems", "uniqueItems", "items", "contains",
    "minProperties", "maxProperties", "required", "properties",
    "propertyNames", "additionalProperties", "dependentRequired",
})

# Documentation keywords. They carry no validation semantics, so ignoring them
# loses nothing.
ANNOTATION_SCHEMA_KEYWORDS = frozenset({
    "$schema", "$id", "$comment", "title", "description",
    "examples", "default", "deprecated", "readOnly", "writeOnly",
})


def unsupported_schema_keywords(schema: Any, path: str = "$") -> list[str]:
    """Report schema keywords this validator would silently ignore.

    A keyword that is neither implemented nor a pure annotation is a silent
    no-op: the constraint is authored but never enforced. The whole schema
    document is walked rather than only the parts one instance happens to
    exercise, because an unimplemented keyword in an unvisited branch is
    exactly the case that would otherwise stay invisible.

    Local `$defs` are walked and may be reached through JSON pointer
    references. Remote schema references remain unsupported.
    """
    findings: list[str] = []
    if not isinstance(schema, dict):
        return findings
    for key in schema:
        if key not in SUPPORTED_SCHEMA_KEYWORDS and key not in ANNOTATION_SCHEMA_KEYWORDS:
            findings.append(f"{path}.{key}")
    for key in ("items", "additionalProperties", "propertyNames", "not", "if", "then", "else", "contains"):
        findings.extend(unsupported_schema_keywords(schema.get(key), f"{path}.{key}"))
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            findings.extend(unsupported_schema_keywords(child, f"{path}.properties.{name}"))
    definitions = schema.get("$defs")
    if isinstance(definitions, dict):
        for name, child in definitions.items():
            findings.extend(unsupported_schema_keywords(child, f"{path}.$defs.{name}"))
    for key in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(key)
        if isinstance(branches, list):
            for index, child in enumerate(branches):
                findings.extend(unsupported_schema_keywords(child, f"{path}.{key}[{index}]"))
    return findings


def _no_alternative(path: str, branch_errors: list[list[str]]) -> str:
    """One line naming what each alternative still needs, in schema order."""
    needs = [item[0].removeprefix(f"{path}: ") for item in branch_errors if item]
    detail = f": {'; or '.join(needs)}" if needs else ""
    return f"{path}: value matches none of the {len(branch_errors)} alternatives{detail}"


def validate_against_schema(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
    _root_schema: dict[str, Any] | None = None,
) -> list[str]:
    """Validate the subset of JSON Schema used by this package."""
    root_schema = schema if _root_schema is None else _root_schema
    errors: list[str] = []
    if "$ref" in schema:
        resolved, resolved_root = _resolve_ref(str(schema["$ref"]), root_schema)
        errors.extend(validate_against_schema(value, resolved, path, resolved_root))
        siblings = {key: item for key, item in schema.items() if key != "$ref"}
        if siblings:
            errors.extend(validate_against_schema(value, siblings, path, root_schema))
        return errors

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for branch in all_of:
            if isinstance(branch, dict):
                errors.extend(validate_against_schema(value, branch, path, root_schema))

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        branch_errors = [
            validate_against_schema(value, branch, path, root_schema)
            for branch in any_of
            if isinstance(branch, dict)
        ]
        if not branch_errors or not any(not item for item in branch_errors):
            errors.append(_no_alternative(path, branch_errors))

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        branch_errors = [
            validate_against_schema(value, branch, path, root_schema)
            for branch in one_of
            if isinstance(branch, dict)
        ]
        matching = sum(1 for item in branch_errors if not item)
        if matching == 0:
            errors.append(_no_alternative(path, branch_errors))
        elif matching > 1:
            errors.append(
                f"{path}: value matches {matching} of the {len(branch_errors)} alternatives; exactly one must match"
            )

    not_schema = schema.get("not")
    if isinstance(not_schema, dict):
        if not validate_against_schema(value, not_schema, path, root_schema):
            errors.append(f"{path}: value satisfies a forbidden schema")

    condition = schema.get("if")
    if isinstance(condition, dict):
        branch = "then" if not validate_against_schema(value, condition, path, root_schema) else "else"
        consequence = schema.get(branch)
        if isinstance(consequence, dict):
            errors.extend(validate_against_schema(value, consequence, path, root_schema))

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not in {schema['enum']!r}")

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, str(item)) for item in types):
            errors.append(f"{path}: expected type {types}, got {type(value).__name__}")
            return errors

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            errors.append(f"{path}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            errors.append(f"{path}: string is longer than maxLength")
        pattern = schema.get("pattern")
        if pattern:
            expr = str(pattern)
            # This repo's schemas anchor every pattern with ^...$. Python's
            # re.search matches $ before a trailing newline, so values like
            # "A1\n" would slip through anchored patterns and only fail
            # later in downstream consumers. Match the full string for
            # anchored patterns; unanchored patterns keep find semantics.
            if expr.startswith("^") and expr.endswith("$"):
                matched = re.fullmatch(expr[1:-1], value) is not None
            else:
                matched = re.search(expr, value) is not None
            if not matched:
                errors.append(f"{path}: string does not match pattern {expr!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{path}: number must be finite")
            return errors
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value is above maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: value is not above {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(f"{path}: value is not below {schema['exclusiveMaximum']}")
        step = schema.get("multipleOf")
        if isinstance(step, (int, float)) and not isinstance(step, bool) and step > 0:
            quotient = value / step
            if abs(quotient - round(quotient)) > 1e-9:
                errors.append(f"{path}: value is not a multiple of {step}")

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(f"{path}: array is shorter than minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: array is longer than maxItems")
        contains = schema.get("contains")
        if isinstance(contains, dict) and not any(
            not validate_against_schema(item, contains, f"{path}[{index}]", root_schema)
            for index, item in enumerate(value)
        ):
            errors.append(f"{path}: no item satisfies contains")
        if schema.get("uniqueItems"):
            encoded = [canonical_json(item) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    validate_against_schema(item, item_schema, f"{path}[{index}]", root_schema)
                )

    if isinstance(value, dict):
        if len(value) < int(schema.get("minProperties", 0)):
            errors.append(f"{path}: object has fewer properties than minProperties")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            errors.append(f"{path}: object has more properties than maxProperties")
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                errors.append(f"{path}: missing required property {name!r}")
        dependent = schema.get("dependentRequired")
        if isinstance(dependent, dict):
            for name, needed in dependent.items():
                if name in value and isinstance(needed, list):
                    for other in needed:
                        if other not in value:
                            errors.append(f"{path}: {name!r} requires {other!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for name, child_schema in properties.items():
                if name in value and isinstance(child_schema, dict):
                    errors.extend(
                        validate_against_schema(value[name], child_schema, f"{path}.{name}", root_schema)
                    )
        property_names = schema.get("propertyNames")
        if isinstance(property_names, dict):
            for name in value:
                errors.extend(
                    validate_against_schema(
                        str(name), property_names, f"{path}.<property-name:{name}>", root_schema
                    )
                )
        if isinstance(properties, dict):
            extras = sorted(set(value) - set(properties))
            additional = schema.get("additionalProperties", True)
            if additional is False and extras:
                errors.append(f"{path}: unexpected properties {extras}")
            elif isinstance(additional, dict):
                for name in extras:
                    errors.extend(
                        validate_against_schema(value[name], additional, f"{path}.{name}", root_schema)
                    )

    if schema.get("$id") == "declared-structures.schema.json" and not errors:
        from structure_contract import validate_structure_map
        errors.extend(validate_structure_map(value, path))
    return errors




def _mapping(value: Any) -> dict[str, Any]:
    """Read a container that is expected to be an object, or nothing at all.

    An off-type container is read as empty so the cross-invariants pass over it
    without raising; the type error itself is already reported by the schema.
    """
    return value if isinstance(value, dict) else {}


def validate_cross_invariants(
    data: dict[str, Any],
    *,
    allow_placeholder_hashes: bool = False,
) -> list[str]:
    if data.get("artifact_type") in public_contract.ARTIFACT_TYPES:
        return public_contract.validate_cross_invariants(data, allow_placeholder_hashes=allow_placeholder_hashes)
    errors: list[str] = []
    kind = artifact_type(data)

    if kind == "state-aware-reference-binding":
        story_range = data.get("effective_story_range")
        if isinstance(story_range, dict):
            start = story_range.get("from_order")
            end = story_range.get("to_order")
            if (
                isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
                and end < start
            ):
                errors.append(
                    "state-aware reference binding effective_story_range.to_order "
                    "must be greater than or equal to from_order"
                )

    if kind == "adoption-receipt":
        if not is_valid_utc_rfc3339(data.get("issued_at")):
            errors.append("adoption receipt issued_at must be a valid UTC RFC3339 timestamp")
        for index, adoption in enumerate(data.get("adoptions", [])):
            if not isinstance(adoption, dict):
                continue
            story_range = adoption.get("effective_story_range")
            if not isinstance(story_range, dict):
                continue
            start = story_range.get("from_order")
            end = story_range.get("to_order")
            if (
                isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
                and end < start
            ):
                errors.append(
                    f"adoptions[{index}].effective_story_range.to_order must be "
                    "greater than or equal to from_order"
                )
    if kind == "state-event":
        changes = data.get("changes", [])
        evidence = data.get("evidence", [])
        if data.get("canon_status") == "approved" and not evidence:
            errors.append("approved state-event requires at least one evidence record")
        entity_pairs = {
            (str(change.get("entity_type")), str(change.get("entity_id")))
            for change in changes if isinstance(change, dict)
        }
        if len(entity_pairs) > 1 and data.get("atomic") is not True:
            errors.append("multi-entity state-event must set atomic=true")
        target_ids = {str(item) for item in data.get("targets", [])}
        changed_ids = {pair[1] for pair in entity_pairs}
        if not changed_ids.issubset(target_ids):
            errors.append(
                "state-event targets omit changed entities: "
                f"{sorted(changed_ids - target_ids)}"
            )
        has_scene_local = any(
            isinstance(change, dict) and change.get("persistence") == "scene-local"
            for change in changes
        )
        if has_scene_local and not data.get("scene_context_id"):
            errors.append("scene-local state-event requires scene_context_id")
        if data.get("scene_context_id") and not has_scene_local:
            errors.append("state-event scene_context_id is only valid with a scene-local change")
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                continue
            operation = change.get("operation")
            if operation in PROCESS_LIFECYCLE_OPERATIONS:
                continue
            persistence = change.get("persistence")
            until = change.get("effective_until_order")
            if until is not None and int(until) <= int(data.get("effective_order", 0)):
                errors.append(
                    f"changes[{index}]: effective_until_order must be later than the event"
                )
            if persistence == "temporary-until-cleared":
                if until is None and not change.get("clear_event_id"):
                    errors.append(
                        f"changes[{index}]: temporary state requires effective_until_order or clear_event_id"
                    )
            if persistence == "scene-local":
                forbidden = sorted(
                    field for field in ("process_id", "clear_event_id", "effective_until_order")
                    if field in change
                )
                if forbidden:
                    errors.append(
                        f"changes[{index}]: scene-local change cannot declare {forbidden}"
                    )
            if persistence in {"decaying", "progressive"}:
                if not change.get("process_id"):
                    errors.append(
                        f"changes[{index}]: {persistence} state requires process_id"
                    )
                if operation not in {"set", "replace"}:
                    errors.append(
                        f"changes[{index}]: {persistence} state requires set or replace"
                    )
            elif change.get("process_id"):
                errors.append(
                    f"changes[{index}]: process_id is only valid for decaying or progressive state"
                )
            if persistence in {"persistent-until-superseded", "era-level", "form-level"}:
                forbidden = sorted(
                    field for field in ("clear_event_id", "effective_until_order")
                    if field in change
                )
                if forbidden:
                    errors.append(
                        f"changes[{index}]: {persistence} change cannot declare {forbidden}"
                    )
            if operation in {"set", "replace", "merge", "append", "increment"} and "value" not in change:
                errors.append(f"changes[{index}]: operation {operation} requires value")

    if kind == "state-process":
        offsets = [item.get("offset") for item in data.get("milestones", []) if isinstance(item, dict)]
        if offsets != sorted(offsets) or len(offsets) != len(set(offsets)):
            errors.append("state-process milestone offsets must be unique and ascending")
        if offsets and offsets[0] != 0:
            errors.append("state-process milestones must begin at offset 0")
        until = data.get("effective_until_order")
        if until is not None and int(until) <= int(data.get("started_order", 0)):
            errors.append("state-process effective_until_order must be later than started_order")
        if data.get("canon_status") == "approved" and not data.get("evidence"):
            errors.append("approved state-process requires evidence")

    if kind == "character-state-schema":
        value_required_operators = {
            "equals", "not-equals", "contains", "greater-than",
            "greater-or-equal", "less-than", "less-or-equal",
        }
        seen_rule_ids: set[str] = set()
        for rule_index, rule in enumerate(data.get("environment_adaptation_rules", [])):
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("rule_id") or "")
            if rule_id in seen_rule_ids:
                errors.append(
                    f"environment_adaptation_rules[{rule_index}]: duplicate rule_id {rule_id!r}"
                )
            seen_rule_ids.add(rule_id)
            for condition_index, condition in enumerate(rule.get("when", [])):
                if not isinstance(condition, dict):
                    continue
                operator = str(condition.get("operator") or "")
                if operator in value_required_operators and "value" not in condition:
                    errors.append(
                        "environment_adaptation_rules"
                        f"[{rule_index}].when[{condition_index}]: operator {operator!r} requires value"
                    )

    if kind == "species-morphology-profile":
        feature_ids = [str(item.get("feature_id") or "") for item in data.get("standard_features", []) if isinstance(item, dict)]
        if len(feature_ids) != len(set(feature_ids)):
            errors.append("species-morphology-profile feature IDs must be unique")
        region_ids = [
            str(item.get("region_id") or "")
            for item in _mapping(data.get("body_plan")).get("region_map", [])
            if isinstance(item, dict)
        ]
        if len(region_ids) != len(set(region_ids)):
            errors.append("species-morphology-profile region IDs must be unique")
        coverage_ids = [str(item.get("requirement_id") or "") for item in data.get("coverage_requirements", []) if isinstance(item, dict)]
        if len(coverage_ids) != len(set(coverage_ids)):
            errors.append("species-morphology-profile coverage requirement IDs must be unique")
        feature_set = set(feature_ids)
        region_set = set(region_ids)
        relationship_ids: list[str] = []
        for index, relationship in enumerate(data.get("feature_relationships", [])):
            if not isinstance(relationship, dict):
                continue
            relationship_id = str(relationship.get("relationship_id") or "")
            relationship_ids.append(relationship_id)
            unknown = sorted(set(str(item) for item in relationship.get("feature_refs", [])) - feature_set)
            if unknown:
                errors.append(f"feature_relationships[{index}]: unknown feature refs {unknown}")
        if len(relationship_ids) != len(set(relationship_ids)):
            errors.append("species-morphology-profile relationship IDs must be unique")
        for index, feature in enumerate(data.get("standard_features", [])):
            if not isinstance(feature, dict):
                continue
            for parent in _mapping(feature.get("attachment_topology")).get("parent_feature_refs", []):
                if str(parent) not in feature_set and str(parent) not in region_set:
                    errors.append(f"standard_features[{index}]: unknown attachment parent {parent!r}")
            for dependency in feature.get("cross_feature_dependencies", []):
                if not isinstance(dependency, dict):
                    continue
                unknown = sorted(set(str(item) for item in dependency.get("related_feature_refs", [])) - feature_set)
                if unknown:
                    errors.append(f"standard_features[{index}]: unknown cross-feature refs {unknown}")
        for index, capability in enumerate(data.get("functional_capabilities", [])):
            if not isinstance(capability, dict):
                continue
            unknown = sorted(set(str(item) for item in capability.get("carrier_feature_refs", [])) - feature_set)
            if unknown:
                errors.append(f"functional_capabilities[{index}]: unknown carrier feature refs {unknown}")
        reviewed = set(str(item) for item in _mapping(data.get("inventory_completeness")).get("reviewed_feature_groups", []))
        used_groups = set(str(item.get("feature_group")) for item in data.get("standard_features", []) if isinstance(item, dict))
        if not used_groups.issubset(reviewed):
            errors.append(f"inventory_completeness omits used feature groups: {sorted(used_groups-reviewed)}")
        frame_model = data.get("frame_character_model", {})
        if isinstance(frame_model, dict):
            variants = [frame_model.get("default")] + list(frame_model.get("allowed_individual_variants", []))
            frame_ids = [str(item.get("frame_character_id") or "") for item in variants if isinstance(item, dict)]
            if len(frame_ids) != len(set(frame_ids)):
                errors.append("species-morphology-profile frame character IDs must be unique")

    if kind == "individual-morphology-contract":
        feature_ids = [str(item.get("feature_id") or "") for item in data.get("feature_realizations", []) if isinstance(item, dict)]
        if len(feature_ids) != len(set(feature_ids)):
            errors.append("individual-morphology-contract feature IDs must be unique")
        for index, item in enumerate(data.get("feature_realizations", [])):
            if not isinstance(item, dict):
                continue
            absent = item.get("status") == "absent"
            resolved = item.get("resolved_feature")
            if absent and (item.get("actual_count") not in (0, "0", "absent") or resolved is not None):
                errors.append(f"feature_realizations[{index}]: absent feature requires count zero and resolved_feature=null")
            if not absent and not isinstance(resolved, dict):
                errors.append(f"feature_realizations[{index}]: present feature requires resolved_feature")
            if item.get("status") == "additional" and item.get("species_feature_ref") is not None:
                errors.append(f"feature_realizations[{index}]: additional feature must not cite a species feature")
            if item.get("status") not in {"additional", "absent"} and not item.get("species_feature_ref"):
                errors.append(f"feature_realizations[{index}]: inherited or modified feature requires species_feature_ref")
        coverage_ids = [str(item.get("requirement_id") or "") for item in data.get("coverage_requirements", []) if isinstance(item, dict)]
        if len(coverage_ids) != len(set(coverage_ids)):
            errors.append("individual-morphology-contract coverage requirement IDs must be unique")
        feature_set = set(feature_ids)
        instance_ids: list[str] = []
        for index, item in enumerate(data.get("feature_realizations", [])):
            if not isinstance(item, dict):
                continue
            instance_ids.extend(str(value) for value in item.get("instance_ids", []))
            attachment = item.get("attachment_realization", {})
            for parent in attachment.get("parent_feature_refs", []) if isinstance(attachment, dict) else []:
                if str(parent) not in feature_set:
                    errors.append(f"feature_realizations[{index}]: unknown individual attachment parent {parent!r}")
        if len(instance_ids) != len(set(instance_ids)):
            errors.append("individual-morphology-contract instance IDs must be globally unique")
        relationship_ids: list[str] = []
        known_refs = feature_set | set(instance_ids)
        for index, relationship in enumerate(data.get("feature_relationship_realizations", [])):
            if not isinstance(relationship, dict):
                continue
            relationship_ids.append(str(relationship.get("relationship_id") or ""))
            unknown = sorted(set(str(item) for item in relationship.get("feature_instance_refs", [])) - known_refs)
            if unknown:
                errors.append(f"feature_relationship_realizations[{index}]: unknown feature instance refs {unknown}")
        if len(relationship_ids) != len(set(relationship_ids)):
            errors.append("individual-morphology-contract relationship IDs must be unique")
        measurement_ids = [
            str(item.get("measurement_id") or "")
            for item in data.get("load_bearing_part_measurements", [])
            if isinstance(item, dict)
        ]
        if len(measurement_ids) != len(set(measurement_ids)):
            errors.append("individual-morphology-contract measurement IDs must be unique")
        inventory = data.get("inventory_completeness", {})
        if isinstance(inventory, dict):
            if inventory.get("individual_features_resolved") != len(data.get("feature_realizations", [])):
                errors.append("inventory_completeness.individual_features_resolved must equal feature_realizations length")
            if inventory.get("unresolved_count") != len(data.get("unresolved_features", [])):
                errors.append("inventory_completeness.unresolved_count must equal unresolved_features length")

    if kind == "character-identity-contract":
        for field in ("species_morphology_profile_ref", "individual_morphology_contract_ref"):
            ref = data.get(field)
            if not isinstance(ref, dict) or not ref.get("id") or not ref.get("sha256"):
                errors.append(f"character-identity-contract requires {field}")

    if kind == "visual-authority":
        if data.get("mode") == "text-only":
            if data.get("archival_vector") is not None:
                errors.append("text-only visual authority must not contain archival_vector")
        else:
            for field in ("source_sha256", "source_media_type", "source_dimensions"):
                if data.get(field) in (None, ""):
                    errors.append(f"source-derived visual authority requires {field}")
            archival = data.get("archival_vector")
            if not isinstance(archival, dict):
                errors.append("source-derived visual authority requires archival_vector")
            else:
                if archival.get("source_payload_embedded") is not False:
                    errors.append("archival vector must not embed raster payload")
                if archival.get("external_raster_reference") is not False:
                    errors.append("archival vector must not reference external raster")

    if kind == "semantic-region-map":
        region_ids = [str(item.get("region_id") or "") for item in data.get("regions", []) if isinstance(item, dict)]
        if len(region_ids) != len(set(region_ids)):
            errors.append("semantic-region-map region IDs must be unique")
        width = float(_mapping(data.get("coordinate_space")).get("width") or 0)
        height = float(_mapping(data.get("coordinate_space")).get("height") or 0)
        for index, region in enumerate(data.get("regions", [])):
            if not isinstance(region, dict):
                continue
            box = region.get("bounding_box", {})
            if isinstance(box, dict) and (
                float(box.get("x") or 0) + float(box.get("width") or 0) > width
                or float(box.get("y") or 0) + float(box.get("height") or 0) > height
            ):
                errors.append(f"regions[{index}]: bounding box exceeds coordinate space")

    if kind == "visual-evidence-bundle":
        artifacts = [item for item in data.get("artifacts", []) if isinstance(item, dict)]
        artifact_ids = [str(item.get("artifact_id") or "") for item in artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            errors.append("visual-evidence-bundle artifact IDs must be unique")
        roles = {str(item.get("role") or "") for item in artifacts}
        required_roles = {
            "faithful-archival-vector", "vectorization-result", "semantic-region-map",
            "subject-mask", "structural-line-tone", "color-audit", "saturation-rescue",
            "specular-audit", "palette-probes", "audit-extraction-set",
            "runtime-attachment-build",
        }
        missing_roles = sorted(required_roles - roles)
        extra_roles = sorted(roles - required_roles)
        if missing_roles:
            errors.append(f"visual-evidence-bundle omits three-layer roles: {missing_roles}")
        if extra_roles:
            errors.append(f"visual-evidence-bundle has unknown roles: {extra_roles}")
        svg_roles = {
            "faithful-archival-vector", "subject-mask", "structural-line-tone",
            "color-audit", "saturation-rescue", "specular-audit",
        }
        for index, item in enumerate(artifacts):
            role = str(item.get("role") or "")
            media_type = str(item.get("media_type") or "")
            expected = "image/svg+xml" if role in svg_roles else "application/json"
            if media_type != expected:
                errors.append(f"artifacts[{index}]: {role} requires {expected}")
        layers = data.get("layers")
        if not isinstance(layers, dict) or set(layers) != {"A", "B", "C"}:
            errors.append("visual-evidence-bundle must declare Layers A, B, and C")

    if kind == "appearance-variant-contract":
        if data.get("variant_class") == "grooming" and not isinstance(data.get("growth_geometry"), dict):
            errors.append("grooming appearance variant requires growth_geometry")

    if kind == "visual-state-projection":
        resolved = data.get("resolved_morphology", {})
        if isinstance(resolved, dict):
            visible_ids = [str(item.get("feature_id") or "") for item in resolved.get("visible_feature_instances", []) if isinstance(item, dict)]
            if len(visible_ids) != len(set(visible_ids)):
                errors.append("visual-state-projection resolved morphology feature IDs must be unique")
            hidden_ids = [str(item) for item in resolved.get("hidden_or_out_of_frame_feature_refs", [])]
            overlap = sorted(set(visible_ids) & set(hidden_ids))
            if overlap:
                errors.append(f"visual-state-projection morphology cannot be both visible and hidden: {overlap}")
            measurement_ids = [
                str(item.get("measurement_id") or "")
                for item in resolved.get("load_bearing_part_measurements", [])
                if isinstance(item, dict)
            ]
            if len(measurement_ids) != len(set(measurement_ids)):
                errors.append("resolved morphology measurement IDs must be unique")
            inventory = resolved.get("inventory_proof", {})
            if isinstance(inventory, dict):
                if inventory.get("declared_visible_count") != len(visible_ids):
                    errors.append("resolved morphology declared_visible_count differs from visible feature count")
                if inventory.get("declared_hidden_count") != len(hidden_ids):
                    errors.append("resolved morphology declared_hidden_count differs from hidden feature count")
        for group_name in ("visible_identity_features", "visible_state_deltas"):
            for index, item in enumerate(data.get(group_name, [])):
                if not isinstance(item, dict):
                    continue
                if item.get("priority") == "signature" and not item.get("carriers"):
                    errors.append(f"{group_name}[{index}]: visible signature item requires carriers")

    if kind == "observed-render-state" and data.get("canonized") is not False:
        errors.append("observed-render-state cannot canonize output automatically")

    if kind == "reference-bundle-plan":
        assets = [item for item in data.get("assets", []) if isinstance(item, dict)]
        asset_ids = [str(item.get("asset_id")) for item in assets]
        if len(asset_ids) != len(set(asset_ids)):
            errors.append("reference-bundle-plan asset IDs must be unique")
        render_spec_files = [str(item.get("render_spec_file")) for item in assets]
        if len(render_spec_files) != len(set(render_spec_files)):
            errors.append("reference-bundle-plan render specification files must be unique")
        render_spec_hashes = [str(item.get("render_spec_sha256")) for item in assets]
        if len(render_spec_hashes) != len(set(render_spec_hashes)):
            errors.append("reference-bundle-plan render_spec_sha256 values must be unique")
        if data.get("unresolved_requirements"):
            errors.append("reference-bundle-plan has unresolved coverage requirements")
        expected_matrix: dict[str, list[str]] = {}
        for asset in assets:
            asset_id = asset.get("asset_id")
            requirement_ids = asset.get("coverage_requirement_ids")
            if not isinstance(asset_id, str) or not isinstance(requirement_ids, list):
                continue
            for requirement_id in requirement_ids:
                if isinstance(requirement_id, str):
                    expected_matrix.setdefault(requirement_id, []).append(asset_id)
        if data.get("coverage_matrix") != expected_matrix:
            errors.append(
                "reference-bundle-plan coverage_matrix must exactly match the ordered "
                "asset coverage_requirement_ids projection"
            )

    if kind == "reference-selection":
        required_features = data.get("required_state_features", [])
        selected = data.get("selected_references", [])
        unresolved = data.get("unresolved_requirements", [])
        binding_ids: list[str] = []
        covered_in_order: list[str] = []
        for index, item in enumerate(selected):
            if not isinstance(item, dict):
                continue
            binding_ids.append(str(item.get("binding_id") or ""))
            covers = [str(value) for value in item.get("covers", [])]
            unsupported = {
                str(value) for value in item.get("unsupported_or_occluded_state", [])
            }
            overlap = sorted(set(covers) & unsupported)
            if overlap:
                errors.append(
                    f"selected_references[{index}] cannot both cover and mark state "
                    f"unsupported or occluded: {overlap}"
                )
            covered_in_order.extend(covers)
        if len(binding_ids) != len(set(binding_ids)):
            errors.append("reference-selection binding IDs must be unique")
        if len(covered_in_order) != len(set(covered_in_order)):
            errors.append("reference-selection state features may be covered only once")
        if set(covered_in_order) & set(unresolved):
            errors.append(
                "reference-selection covered and unresolved state features must not overlap"
            )
        if set(covered_in_order) | set(unresolved) != set(required_features):
            errors.append(
                "reference-selection covered and unresolved state features must exactly "
                "partition required_state_features"
            )

    if kind == "state-lineage":
        mode = data.get("mode")
        if mode == "state-aware":
            for name in STATE_AWARE_REQUIRED_LINEAGE_FIELDS:
                if not is_concrete_sha256(data.get(name)):
                    errors.append(f"state-aware lineage requires a concrete {name}")
            for name in STATE_LINEAGE_ARTIFACT_FIELDS:
                value = data.get(name)
                if value is not None and not is_concrete_sha256(value):
                    errors.append(f"state-aware lineage {name} must be null or a concrete lowercase SHA-256")
        elif mode == "stateless":
            populated = [name for name in STATE_LINEAGE_ARTIFACT_FIELDS if data.get(name) is not None]
            if populated:
                errors.append(f"stateless lineage nodes must be null: {populated}")

    if not allow_placeholder_hashes:
        for path in find_placeholder_hashes(data):
            errors.append(f"{path}: all-zero SHA-256 placeholders are not valid runtime hashes")

    self_field = SELF_HASH_FIELDS.get(kind)
    if self_field:
        expected = data.get(self_field)
        if expected == ZERO_SHA256 and allow_placeholder_hashes:
            return errors
        if not is_concrete_sha256(expected):
            errors.append(f"{self_field} must be a concrete lowercase SHA-256")
        elif artifact_hash(data) != expected:
            errors.append(f"{self_field} does not match canonical artifact content")

    return errors


def validate_artifact(
    data: dict[str, Any],
    *,
    allow_placeholder_hashes: bool = False,
) -> dict[str, Any]:
    if isinstance(data, dict) and data.get("artifact_type") in public_contract.ARTIFACT_TYPES:
        return public_contract.validate_artifact(data, allow_placeholder_hashes=allow_placeholder_hashes)
    errors: list[str] = []
    non_finite = find_non_finite_numbers(data)
    errors.extend(f"{path}: number must be finite" for path in non_finite)
    try:
        schema = schema_for(data)
        errors.extend(validate_against_schema(data, schema))
        errors.extend(
            validate_cross_invariants(
                data,
                allow_placeholder_hashes=allow_placeholder_hashes,
            )
        )
    except (ValueError, TypeError, KeyError, AttributeError, OSError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    return {
        "artifact_type": data.get("artifact_type"),
        "ok": not errors,
        "errors": errors,
        "content_sha256": (
            artifact_hash(data) if data.get("artifact_type") and not non_finite else None
        ),
    }


def _changed_growth_paths(before: Any, after: Any, path: str = "") -> list[str]:
    """Return exact changed JSON pointers; arrays retain their declared order."""
    if isinstance(before, dict) and isinstance(after, dict):
        changed: list[str] = []
        for key in sorted(set(before) | set(after)):
            child = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in before or key not in after:
                changed.append(child)
            else:
                changed.extend(_changed_growth_paths(before[key], after[key], child))
        return changed
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [child for index, (left, right) in enumerate(zip(before, after))
                for child in _changed_growth_paths(left, right, f"{path}/{index}")]
    return [] if type(before) is type(after) and before == after else [path]


def _checked_growth(value: Any, name: str) -> dict[str, Any]:
    schema = load_json(ROOT / "schemas" / "growth-geometry.schema.json")
    errors = validate_against_schema(value, schema)
    if errors:
        raise ValueError(f"invalid {name}: " + "; ".join(errors))
    from structure_contract import structure_view
    # Inspect the declared structure map without altering its source bytes
    # or broadening its geometry permissions.
    return structure_view(value, "growth-geometry")["source_contract"]


def _checked_growth_parent(
    value: dict[str, Any], kind: str, identity: dict[str, Any]
) -> None:
    report = validate_artifact(value)
    if not report["ok"] or value.get("artifact_type") != kind:
        raise ValueError(f"invalid {kind}: " + "; ".join(report.get("errors", [])))
    if value.get("character_id") != identity.get("character_id"):
        raise ValueError(f"{kind} belongs to another character")
    if value.get("parent_identity_contract_sha256") != artifact_hash(identity):
        raise ValueError(f"{kind} parent identity hash does not match the supplied identity")
    if value.get("canon_status") != "approved":
        raise ValueError(f"{kind} must be approved before it can resolve growth geometry")


def resolve_growth_geometry(
    identity_contract: dict[str, Any],
    *,
    era_contract: dict[str, Any] | None = None,
    form_contract: dict[str, Any] | None = None,
    appearance_variant: dict[str, Any] | None = None,
    state_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve authored geometry once for renderers, production and graph checks.

    An approved era or form may declare a complete replacement. An appearance
    variant may change only the exact JSON pointers the resolved identity lists
    in variant_fields. Current grooming is serialized as condition annotations;
    it never overwrites permanent geometry or the authority that permits edits.
    Inputs are neither mutated nor inferred from species, material or prose.
    """
    report = validate_artifact(identity_contract)
    if not report["ok"] or identity_contract.get("artifact_type") != "character-identity-contract":
        raise ValueError("invalid character identity for growth resolution: " + "; ".join(report.get("errors", [])))
    geometry = _checked_growth(identity_contract.get("stable_identity", {}).get("growth_geometry"),
                               "stable_identity.growth_geometry")
    for contract, kind, field in (
        (era_contract, "era-contract", "approved_changes"),
        (form_contract, "form-contract", "surface_system"),
    ):
        if contract is None:
            continue
        _checked_growth_parent(contract, kind, identity_contract)
        declaration = contract.get(field, {})
        if "growth_geometry" in declaration:
            geometry = _checked_growth(declaration["growth_geometry"], f"{kind}.{field}.growth_geometry")
    if appearance_variant is not None:
        _checked_growth_parent(appearance_variant, "appearance-variant-contract", identity_contract)
        # There is one canonical geometry field, not a competing declaration
        # hidden inside the free-form appearance description.
        if "growth_geometry" in appearance_variant.get("appearance_definition", {}):
            raise ValueError("appearance_definition must not shadow the top-level growth_geometry")
        variant_geometry = appearance_variant.get("growth_geometry")
        if variant_geometry is not None:
            variant_geometry = _checked_growth(variant_geometry, "appearance-variant-contract.growth_geometry")
            changed = _changed_growth_paths(geometry, variant_geometry)
            prefix = "/stable_identity/growth_geometry"
            allowed = set(geometry["variant_fields"])
            # A variant cannot grant itself permission or remove identity locks.
            protected = ("/variant_fields", "/identity_lock_fields", "/representation")
            forbidden = [path for path in changed
                         if prefix + path not in allowed
                         or any(path == key or path.startswith(key + "/") for key in protected)]
            if forbidden:
                raise ValueError("appearance variant changes growth outside authorized variant_fields: "
                                 + ", ".join(prefix + path for path in forbidden))
            geometry = variant_geometry
    if state_snapshot is not None:
        report = validate_artifact(state_snapshot)
        if not report["ok"] or state_snapshot.get("artifact_type") != "state-snapshot":
            raise ValueError("invalid state snapshot for growth resolution: " + "; ".join(report.get("errors", [])))
        if state_snapshot.get("character_id") != identity_contract.get("character_id"):
            raise ValueError("state snapshot belongs to another character")
        expected = {
            "identity_contract_sha256": artifact_hash(identity_contract),
            "era_contract_sha256": artifact_hash(era_contract) if era_contract is not None else None,
            "form_contract_sha256": artifact_hash(form_contract) if form_contract is not None else None,
            "appearance_variant_sha256": artifact_hash(appearance_variant) if appearance_variant is not None else None,
        }
        for field, digest in expected.items():
            if state_snapshot.get(field) != digest:
                raise ValueError(f"state snapshot {field} differs from supplied growth authority")
        grooming = state_snapshot.get("appearance_state", {}).get("grooming")
        if grooming is not None:
            # A single canonical string preserves arbitrary authored condition
            # structure without inventing anatomy or interpreting natural text.
            condition = "/appearance_state/grooming = " + canonical_json(grooming)
            if condition not in geometry["grooming_state"]:
                geometry["grooming_state"].append(condition)
    return geometry


def validate_reference_bundle_graph(
    *,
    plan: dict[str, Any],
    render_specs_by_file: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate the semantic edges from a bundle plan to its render specs."""

    errors: list[str] = []
    plan_report = validate_artifact(plan)
    if plan.get("artifact_type") != "reference-bundle-plan":
        errors.append("bundle plan has the wrong artifact_type")
    if not plan_report.get("ok"):
        errors.extend(f"bundle plan: {item}" for item in plan_report.get("errors", []))

    shared_fields = (
        "character_id",
        "species_profile_sha256",
        "individual_morphology_sha256",
        "identity_contract_sha256",
        "era_contract_sha256",
        "appearance_variant_sha256",
        "visual_authority_sha256",
        "visual_evidence_bundle_sha256",
        "style_family_id",
    )
    for index, row in enumerate(plan.get("assets", [])):
        if not isinstance(row, dict):
            continue
        prefix = f"assets[{index}]"
        file_name = str(row.get("render_spec_file") or "")
        render_spec = render_specs_by_file.get(file_name)
        if not isinstance(render_spec, dict):
            errors.append(f"{prefix}: render specification is missing for {file_name!r}")
            continue
        render_report = validate_artifact(render_spec)
        if render_spec.get("artifact_type") != "asset-render-specification":
            errors.append(f"{prefix}: linked artifact is not an asset-render-specification")
        if not render_report.get("ok"):
            errors.extend(
                f"{prefix}: {item}" for item in render_report.get("errors", [])
            )
        if row.get("render_spec_sha256") != artifact_hash(render_spec):
            errors.append(f"{prefix}: render specification hash does not match the linked artifact")
        if row.get("asset_id") != render_spec.get("asset_id"):
            errors.append(f"{prefix}: asset_id does not match the linked render specification")
        if row.get("coverage_requirement_ids") != render_spec.get("coverage_requirement_ids"):
            errors.append(f"{prefix}: coverage requirements differ from the linked render specification")
        for field in shared_fields:
            if plan.get(field) != render_spec.get(field):
                errors.append(f"{prefix}: {field} differs from the bundle plan")

    return {
        "ok": not errors,
        "errors": errors,
    }


def validate_state_artifact_graph(
    *,
    lineage: dict[str, Any],
    species_profile: dict[str, Any] | None = None,
    individual_morphology: dict[str, Any] | None = None,
    identity_contract: dict[str, Any] | None = None,
    era_contract: dict[str, Any] | None = None,
    form_contract: dict[str, Any] | None = None,
    appearance_variant: dict[str, Any] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    scene_context: dict[str, Any] | None = None,
    visual_projection: dict[str, Any] | None = None,
    asset_render_spec: dict[str, Any] | None = None,
    visual_authority: dict[str, Any] | None = None,
    visual_evidence_bundle: dict[str, Any] | None = None,
    production_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one state-aware CPB artifact graph and every declared edge.

    Hash equality alone is not graph validation.  This routine validates each
    concrete artifact, checks the lineage digest for the matching artifact
    type, and then checks IDs, character ownership, timeline/context links,
    parent contracts, and the production/render handoff.
    """
    errors: list[str] = []
    artifacts = {
        "species_profile_sha256": species_profile,
        "individual_morphology_sha256": individual_morphology,
        "identity_contract_sha256": identity_contract,
        "era_contract_sha256": era_contract,
        "form_contract_sha256": form_contract,
        "appearance_variant_sha256": appearance_variant,
        "state_snapshot_sha256": state_snapshot,
        "scene_context_sha256": scene_context,
        "visual_projection_sha256": visual_projection,
        "asset_render_spec_sha256": asset_render_spec,
        "visual_authority_sha256": visual_authority,
        "visual_evidence_bundle_sha256": visual_evidence_bundle,
    }
    artifact_hashes: dict[str, str | None] = {}

    lineage_report = validate_artifact(lineage)
    if not lineage_report.get("ok"):
        errors.extend(f"state-lineage: {item}" for item in lineage_report.get("errors", []))
    if lineage.get("artifact_type") != "state-lineage":
        errors.append("lineage must have artifact_type state-lineage")
    mode = str(lineage.get("mode") or "")

    for field, expected_type in STATE_LINEAGE_ARTIFACT_FIELDS.items():
        value = artifacts[field]
        if value is None:
            artifact_hashes[field] = None
            if lineage.get(field) is not None:
                errors.append(f"lineage declares {field}, but the artifact was not supplied")
            continue
        if not isinstance(value, dict):
            artifact_hashes[field] = None
            errors.append(f"{expected_type} must be a JSON object")
            continue
        if value.get("artifact_type") != expected_type:
            errors.append(
                f"{field}: expected artifact_type {expected_type}, got {value.get('artifact_type')}"
            )
        report = validate_artifact(value)
        if not report.get("ok"):
            errors.extend(f"{expected_type}: {item}" for item in report.get("errors", []))
        digest = artifact_hash(value)
        artifact_hashes[field] = digest
        if lineage.get(field) != digest:
            errors.append(f"lineage {field} does not match the supplied {expected_type}")

    if mode == "stateless":
        supplied = [field for field, value in artifacts.items() if value is not None]
        if supplied:
            errors.append(f"stateless artifact graph must not contain state artifacts: {supplied}")
        if production_spec is not None:
            from production_spec import validate as validate_production_spec

            report = validate_production_spec(production_spec, require_content=True)
            if not report.get("ok"):
                errors.extend(f"production-specification: {item}" for item in report.get("errors", []))
            state_context = production_spec.get("state_context", {})
            if state_context.get("mode") != "stateless":
                errors.append("stateless production specification must declare mode=stateless")
        return {
            "ok": not errors,
            "mode": mode,
            "character_id": None,
            "artifact_hashes": artifact_hashes,
            "errors": errors,
        }

    if mode != "state-aware":
        errors.append(f"unsupported state artifact graph mode: {mode!r}")

    required_objects = {
        "species-morphology-profile": species_profile,
        "individual-morphology-contract": individual_morphology,
        "character-identity-contract": identity_contract,
        "state-snapshot": state_snapshot,
        "scene-context-snapshot": scene_context,
        "visual-state-projection": visual_projection,
        "asset-render-specification": asset_render_spec,
        "production-specification": production_spec,
    }
    for name, value in required_objects.items():
        if value is None:
            errors.append(f"state-aware artifact graph requires {name}")

    # Return all structural errors together instead of dereferencing missing
    # required nodes and hiding the rest of the graph report.
    if any(value is None for value in required_objects.values()):
        return {
            "ok": False,
            "mode": mode,
            "character_id": None,
            "artifact_hashes": artifact_hashes,
            "errors": errors,
        }

    assert species_profile is not None
    assert individual_morphology is not None
    assert identity_contract is not None
    assert state_snapshot is not None
    assert scene_context is not None
    assert visual_projection is not None
    assert asset_render_spec is not None
    assert production_spec is not None

    species_hash = artifact_hash(species_profile)
    individual_hash = artifact_hash(individual_morphology)
    identity_hash = artifact_hash(identity_contract)
    state_hash = artifact_hash(state_snapshot)
    context_hash = artifact_hash(scene_context)
    projection_hash = artifact_hash(visual_projection)
    render_hash = artifact_hash(asset_render_spec)
    character_id = str(identity_contract.get("character_id") or "")

    expected_species_ref = {
        "id": species_profile.get("profile_id"),
        "sha256": species_hash,
    }
    expected_individual_ref = {
        "id": individual_morphology.get("contract_id"),
        "sha256": individual_hash,
    }
    if individual_morphology.get("species_profile_ref") != expected_species_ref:
        errors.append("individual morphology species_profile_ref does not match the supplied profile")
    if identity_contract.get("species_morphology_profile_ref") != expected_species_ref:
        errors.append("identity contract species morphology reference does not match the supplied profile")
    if identity_contract.get("individual_morphology_contract_ref") != expected_individual_ref:
        errors.append("identity contract individual morphology reference does not match the supplied contract")
    if individual_morphology.get("domain") != identity_contract.get("domain"):
        errors.append("individual morphology domain differs from identity contract")
    if species_profile.get("domain") != identity_contract.get("domain"):
        errors.append("species morphology domain differs from identity contract")

    character_nodes = {
        "individual morphology": individual_morphology,
        "state snapshot": state_snapshot,
        "visual projection": visual_projection,
        "asset render specification": asset_render_spec,
        "era contract": era_contract,
        "form contract": form_contract,
        "appearance variant": appearance_variant,
    }
    for name, value in character_nodes.items():
        if value is not None and value.get("character_id") != character_id:
            errors.append(f"{name} belongs to another character")

    optional_parent_nodes = (
        ("era contract", era_contract),
        ("form contract", form_contract),
        ("appearance variant", appearance_variant),
    )
    for name, value in optional_parent_nodes:
        if value is not None and value.get("parent_identity_contract_sha256") != identity_hash:
            errors.append(f"{name} parent identity hash does not match the supplied identity")

    expected_optional_hashes = {
        "era_contract_sha256": artifact_hash(era_contract) if era_contract is not None else None,
        "form_contract_sha256": artifact_hash(form_contract) if form_contract is not None else None,
        "appearance_variant_sha256": (
            artifact_hash(appearance_variant) if appearance_variant is not None else None
        ),
    }
    expected_state_hashes = {
        "species_profile_sha256": species_hash,
        "individual_morphology_sha256": individual_hash,
        "identity_contract_sha256": identity_hash,
        **expected_optional_hashes,
    }
    for field, expected in expected_state_hashes.items():
        if state_snapshot.get(field) != expected:
            errors.append(f"state snapshot {field} does not match the supplied graph")

    matching_context_rows = [
        item
        for item in scene_context.get("active_character_snapshots", [])
        if isinstance(item, dict) and item.get("character_id") == character_id
    ]
    expected_context_row = {
        "character_id": character_id,
        "snapshot_id": state_snapshot.get("snapshot_id"),
        "state_snapshot_sha256": state_hash,
    }
    if expected_context_row not in matching_context_rows:
        errors.append("scene context does not contain the supplied character state snapshot")
    if len(matching_context_rows) != 1:
        errors.append("scene context must contain exactly one snapshot for the graph character")
    if scene_context.get("timeline_id") != state_snapshot.get("timeline_id"):
        errors.append("scene context timeline differs from state snapshot timeline")
    if scene_context.get("scene_context_id") != state_snapshot.get("scene_context_id"):
        errors.append("scene context ID differs from state snapshot target scene")
    story_order = state_snapshot.get("story_order")
    start = scene_context.get("story_order_start")
    end = scene_context.get("story_order_end")
    if isinstance(story_order, int) and isinstance(start, int) and story_order < start:
        errors.append("state snapshot precedes the scene context range")
    if isinstance(story_order, int) and isinstance(end, int) and story_order > end:
        errors.append("state snapshot follows the scene context range")

    if visual_projection.get("state_snapshot_sha256") != state_hash:
        errors.append("visual projection state snapshot hash does not match the supplied snapshot")
    if visual_projection.get("scene_context_sha256") != context_hash:
        errors.append("visual projection scene context hash does not match the supplied context")
    resolved = visual_projection.get("resolved_morphology", {})
    if isinstance(resolved, dict):
        if resolved.get("species_profile_ref") != expected_species_ref:
            errors.append("visual projection resolved species reference does not match the graph")
        if resolved.get("individual_morphology_ref") != expected_individual_ref:
            errors.append("visual projection resolved individual reference does not match the graph")

    expected_render_hashes = {
        "species_profile_sha256": species_hash,
        "individual_morphology_sha256": individual_hash,
        "identity_contract_sha256": identity_hash,
        "era_contract_sha256": expected_optional_hashes["era_contract_sha256"],
        "appearance_variant_sha256": expected_optional_hashes["appearance_variant_sha256"],
        "state_snapshot_sha256": state_hash,
        "visual_state_projection_sha256": projection_hash,
        "visual_authority_sha256": (
            artifact_hash(visual_authority) if visual_authority is not None else None
        ),
        "visual_evidence_bundle_sha256": (
            artifact_hash(visual_evidence_bundle) if visual_evidence_bundle is not None else None
        ),
    }
    for field, expected in expected_render_hashes.items():
        if asset_render_spec.get(field) != expected:
            errors.append(f"asset render specification {field} does not match the supplied graph")

    authority_ref = identity_contract.get("visual_authority_ref")
    if visual_authority is None:
        if authority_ref is not None:
            errors.append("identity declares visual authority, but no visual-authority artifact was supplied")
    else:
        expected_authority_ref = {
            "id": visual_authority.get("authority_id"),
            "sha256": artifact_hash(visual_authority),
        }
        if authority_ref != expected_authority_ref:
            errors.append("identity visual authority reference does not match the supplied artifact")
    if visual_evidence_bundle is not None:
        if visual_authority is None:
            errors.append("visual evidence bundle requires a supplied visual-authority artifact")
        else:
            expected_authority_ref = {
                "id": visual_authority.get("authority_id"),
                "sha256": artifact_hash(visual_authority),
            }
            if visual_evidence_bundle.get("visual_authority_ref") != expected_authority_ref:
                errors.append("visual evidence bundle authority reference does not match the graph")

    from production_spec import validate as validate_production_spec

    production_report = validate_production_spec(production_spec, require_content=True)
    if not production_report.get("ok"):
        errors.extend(
            f"production-specification: {item}"
            for item in production_report.get("errors", [])
        )
    state_context = production_spec.get("state_context", {})
    if state_context.get("mode") != "state-aware":
        errors.append("state-aware production specification must declare mode=state-aware")
    if state_context.get("state_lineage_sha256") != lineage.get("lineage_sha256"):
        errors.append("production specification state-lineage hash mismatch")
    expected_scene_ref = {
        "id": scene_context.get("scene_context_id"),
        "sha256": context_hash,
    }
    if state_context.get("scene_context_ref") != expected_scene_ref:
        errors.append("production specification scene context reference does not match the graph")

    subject_rows = [
        item
        for item in production_spec.get("subjects", [])
        if isinstance(item, dict) and item.get("id") == character_id
    ]
    if len(subject_rows) != 1:
        errors.append("production specification must contain exactly one subject for the graph character")
    else:
        subject = subject_rows[0]
        expected_subject_refs = {
            "species_morphology_profile_ref": expected_species_ref,
            "individual_morphology_contract_ref": expected_individual_ref,
            "identity_contract_ref": {
                "id": identity_contract.get("contract_id"),
                "sha256": identity_hash,
            },
            "state_snapshot_ref": {
                "id": state_snapshot.get("snapshot_id"),
                "sha256": state_hash,
            },
            "visual_projection_ref": {
                "id": visual_projection.get("projection_id"),
                "sha256": projection_hash,
            },
        }
        for field, expected in expected_subject_refs.items():
            if subject.get(field) != expected:
                errors.append(f"production specification subject {field} does not match the graph")
        if subject.get("domain") != identity_contract.get("domain"):
            errors.append("production specification subject domain differs from identity contract")

    try:
        expected_growth = resolve_growth_geometry(
            identity_contract, era_contract=era_contract, form_contract=form_contract,
            appearance_variant=appearance_variant, state_snapshot=state_snapshot,
        )
        if len(subject_rows) == 1 and subject_rows[0].get("growth_geometry") != expected_growth:
            errors.append("production specification growth_geometry differs from resolved identity, approved variants and state")
        if _mapping(asset_render_spec.get("subject_resolution")).get("growth_geometry") != expected_growth:
            errors.append("asset render specification growth_geometry differs from resolved identity, approved variants and state")
    except ValueError as exc:
        errors.append("growth resolution: " + str(exc))

    production_render_fields = (
        "target_model",
        "art_direction",
        "scene",
        "camera",
        "lighting",
        "selected_preset_ids",
    )
    for field in production_render_fields:
        if production_spec.get(field) != asset_render_spec.get(field):
            errors.append(f"production specification {field} differs from the asset render specification")

    return {
        "ok": not errors,
        "mode": mode,
        "character_id": character_id,
        "artifact_hashes": artifact_hashes,
        "render_spec_sha256": render_hash,
        "errors": errors,
    }


_ARRAY_INDEX = re.compile(r"^(?:0|[1-9][0-9]*)$")


































def extract_character_snapshot(
    world_snapshot: dict[str, Any],
    *,
    character_id: str,
    species_profile_hash: str,
    individual_morphology_hash: str,
    identity_hash: str,
    era_hash: str | None,
    form_hash: str | None,
    appearance_hash: str | None,
    snapshot_id: str,
) -> dict[str, Any]:
    world_report = validate_artifact(world_snapshot)
    if not world_report["ok"]:
        raise ValueError("invalid world-state snapshot: " + "; ".join(world_report["errors"]))
    state = world_snapshot.get("entities", {}).get("characters", {}).get(character_id)
    if not isinstance(state, dict):
        raise ValueError(f"character is absent from world snapshot: {character_id}")
    result = {
        "artifact_type": "state-snapshot",
        "snapshot_id": snapshot_id,
        "character_id": character_id,
        "timeline_id": world_snapshot["timeline_id"],
        "scene_context_id": world_snapshot["scene_context_id"],
        "story_order": world_snapshot["story_order"],
        "story_time": world_snapshot["story_time"],
        "species_profile_sha256": species_profile_hash,
        "individual_morphology_sha256": individual_morphology_hash,
        "identity_contract_sha256": identity_hash,
        "era_contract_sha256": era_hash,
        "form_contract_sha256": form_hash,
        "appearance_variant_sha256": appearance_hash,
        "applied_event_ids": list(world_snapshot.get("applied_event_ids", [])),
        "applied_process_milestones": list(world_snapshot.get("applied_process_milestones", [])),
        **{name: copy.deepcopy(state.get(name, {})) for name in STATE_SECTION_NAMES},
        "uncertainties": copy.deepcopy(state.get("uncertainties", [])),
        "state_snapshot_sha256": "0" * 64,
    }
    return finalize_artifact(result)

def build_scene_context(
    request: dict[str, Any],
    world_snapshot: dict[str, Any],
    character_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    world_report = validate_artifact(world_snapshot)
    if not world_report["ok"]:
        raise ValueError("invalid world-state snapshot: " + "; ".join(world_report["errors"]))
    if world_snapshot.get("scene_context_id") != request.get("scene_context_id"):
        raise ValueError("world snapshot target scene does not match the context request")
    if world_snapshot.get("timeline_id") != request.get("timeline_id"):
        raise ValueError("world snapshot timeline does not match the context request")
    world_order = world_snapshot.get("story_order")
    if (
        not isinstance(world_order, int)
        or world_order < int(request["story_order_start"])
        or world_order > int(request["story_order_end"])
    ):
        raise ValueError("world snapshot order is outside the context request range")
    active_ids = request.get("active_character_ids", [])
    if not isinstance(active_ids, list) or any(not isinstance(x, str) or not x for x in active_ids):
        raise ValueError("active_character_ids must be a list of nonempty identifiers")
    if len(set(active_ids)) != len(active_ids):
        raise ValueError("duplicate active character ID")
    snapshot_by_id = {}
    for snapshot in character_snapshots:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("character_id"), str):
            raise ValueError("invalid character snapshot input")
        cid = snapshot["character_id"]
        if cid in snapshot_by_id:
            raise ValueError("duplicate character snapshot ID: " + cid)
        snapshot_by_id[cid] = snapshot
    missing = [item for item in active_ids if item not in snapshot_by_id]
    if missing:
        raise ValueError(f"missing character snapshots for active characters: {missing}")
    active_refs = []
    for character_id in active_ids:
        snapshot = snapshot_by_id[character_id]
        report = validate_artifact(snapshot)
        if not report["ok"]:
            raise ValueError(f"invalid state snapshot for {character_id}: {'; '.join(report['errors'])}")
        if snapshot.get("scene_context_id") != request.get("scene_context_id"):
            raise ValueError(
                f"state snapshot target scene differs for active character {character_id}"
            )
        for field in ("timeline_id", "story_order", "story_time"):
            if snapshot.get(field) != world_snapshot.get(field):
                raise ValueError(f"state snapshot {field} differs from world for {character_id}")
        world_character = world_snapshot.get("entities", {}).get("characters", {}).get(character_id)
        if not isinstance(world_character, dict):
            raise ValueError(f"selected character is absent from world: {character_id}")
        for section in STATE_SECTION_NAMES:
            if canonical_json(snapshot.get(section, {})) != canonical_json(world_character.get(section, {})):
                raise ValueError(f"state snapshot {section} differs from world for {character_id}")
        for field in ("applied_event_ids", "applied_process_milestones"):
            if snapshot.get(field, []) != world_snapshot.get(field, []):
                raise ValueError(f"snapshot history differs from world for {character_id}: {field}")
        active_refs.append({
            "character_id": character_id,
            "snapshot_id": snapshot["snapshot_id"],
            "state_snapshot_sha256": snapshot["state_snapshot_sha256"],
        })

    entities = world_snapshot.get("entities", {})
    environment_id = request.get("environment_id")
    environment_value = {}
    if environment_id:
        if str(environment_id) not in entities.get("environments", {}):
            raise ValueError("selected environment is absent from world: " + str(environment_id))
        environment_value = copy.deepcopy(entities["environments"][str(environment_id)])
    for field in ("relationship_ids", "prop_ids"):
        ids = request.get(field, [])
        if not isinstance(ids, list) or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{field} must contain unique nonempty IDs")
    relationship_values = []
    for relationship_id in request.get("relationship_ids", []):
        value = entities.get("relationships", {}).get(str(relationship_id))
        if value is None:
            raise ValueError("selected relationship is absent from world: " + str(relationship_id))
        if value is not None:
            relationship_values.append({"relationship_id": relationship_id, "state": copy.deepcopy(value)})
    prop_values = []
    for prop_id in request.get("prop_ids", []):
        value = entities.get("props", {}).get(str(prop_id))
        if value is None:
            raise ValueError("selected prop is absent from world: " + str(prop_id))
        if value is not None:
            prop_values.append({"prop_id": prop_id, "state": copy.deepcopy(value)})

    result = {
        "artifact_type": "scene-context-snapshot",
        "scene_context_id": str(request["scene_context_id"]),
        "timeline_id": str(request["timeline_id"]),
        "story_order_start": int(request["story_order_start"]),
        "story_order_end": int(request["story_order_end"]),
        "story_time_start": str(request["story_time_start"]),
        "story_time_end": str(request["story_time_end"]),
        "location_snapshot": copy.deepcopy(request.get("location_snapshot", {})),
        "environment_snapshot": environment_value,
        "active_character_snapshots": active_refs,
        "relationship_snapshots": relationship_values,
        "prop_and_inventory_bindings": prop_values,
        "social_context": copy.deepcopy(request.get("social_context", {})),
        "viewer_disclosure_state": copy.deepcopy(request.get("viewer_disclosure_state", {})),
        "planned_events": copy.deepcopy(request.get("planned_events", [])),
        "context_snapshot_sha256": "0" * 64,
    }
    return finalize_artifact(result)


def _identity_features(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    for detail in contract.get("distinctive_details", []):
        if isinstance(detail, dict) and detail.get("id"):
            features[str(detail["id"])] = {
                "feature_id": str(detail["id"]),
                "wording": str(detail.get("prompt") or detail.get("label") or detail["id"]),
                "priority": str(detail.get("identity_priority") or "supporting"),
                "source": "distinctive-detail",
                "carriers": ["reference-media", "text", "review"],
            }
    for anchor in contract.get("anchor_fragments", []):
        if isinstance(anchor, dict) and anchor.get("anchor_id"):
            features[str(anchor["anchor_id"])] = {
                "feature_id": str(anchor["anchor_id"]),
                "wording": str(anchor.get("wording") or ""),
                "priority": str(anchor.get("priority") or "supporting"),
                "source": "anchor-fragment",
                "carriers": list(anchor.get("carriers", [])),
                "required_when": list(anchor.get("required_when", [])),
                "omit_when": list(anchor.get("omit_when", [])),
            }
    return features


def _resolve_path_items(snapshot: dict[str, Any], items: Iterable[Any], *, group: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        if isinstance(raw, str):
            item = {"path": raw}
        elif isinstance(raw, dict):
            item = raw
        else:
            raise ValueError(f"{group}[{index}] must be a string or object")
        path = str(item.get("path") or "")
        if not path:
            raise ValueError(f"{group}[{index}] is missing path")
        value = get_pointer(snapshot, path, missing=None)
        result.append({
            "path": path,
            "label": str(item.get("label") or path.rsplit("/", 1)[-1]),
            "value": value,
            "wording": str(item.get("wording") or ""),
            "priority": str(item.get("priority") or "supporting"),
            "carriers": list(item.get("carriers", [])),
        })
    return result


def resolve_morphology_projection(
    species_profile: dict[str, Any],
    individual_morphology: dict[str, Any],
    state_snapshot: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Resolve exact shot-visible morphology without inventing missing anatomy."""
    for artifact, expected in (
        (species_profile, "species-morphology-profile"),
        (individual_morphology, "individual-morphology-contract"),
    ):
        report = validate_artifact(artifact)
        if not report["ok"] or artifact.get("artifact_type") != expected:
            raise ValueError(f"invalid {expected}: " + "; ".join(report.get("errors", [])))

    species_hash = artifact_hash(species_profile)
    individual_hash = artifact_hash(individual_morphology)
    species_ref = individual_morphology.get("species_profile_ref", {})
    if species_ref.get("id") != species_profile.get("profile_id") or species_ref.get("sha256") != species_hash:
        raise ValueError("individual morphology species_profile_ref does not match supplied profile")
    if state_snapshot.get("species_profile_sha256") != species_hash:
        raise ValueError("state snapshot species profile hash differs from supplied profile")
    if state_snapshot.get("individual_morphology_sha256") != individual_hash:
        raise ValueError("state snapshot individual morphology hash differs from supplied contract")

    feature_by_id = {
        str(item.get("feature_id")): item
        for item in individual_morphology.get("feature_realizations", [])
        if isinstance(item, dict) and item.get("feature_id")
    }
    requested_visible = [str(item) for item in request.get("visible_morphology_feature_ids", [])]
    if not requested_visible:
        requested_visible = [
            feature_id for feature_id, item in feature_by_id.items()
            if item.get("identity_priority") == "signature" and item.get("status") != "absent"
        ]
    visible: list[dict[str, Any]] = []
    for feature_id in requested_visible:
        item = feature_by_id.get(feature_id)
        if item is None:
            raise ValueError(f"unknown morphology feature ID: {feature_id}")
        if item.get("status") == "absent":
            raise ValueError(f"absent morphology feature cannot be required visible: {feature_id}")
        if not isinstance(item.get("resolved_feature"), dict):
            raise ValueError(f"morphology feature lacks resolved_feature: {feature_id}")
        visible.append(copy.deepcopy(item))

    explicit_hidden = list(dict.fromkeys(str(item) for item in request.get("occluded_morphology_feature_ids", [])))
    for feature_id in explicit_hidden:
        if feature_id not in feature_by_id:
            raise ValueError(f"unknown occluded morphology feature ID: {feature_id}")
    automatically_hidden = [
        feature_id for feature_id, item in feature_by_id.items()
        if feature_id not in requested_visible and item.get("status") != "absent"
    ]
    hidden_feature_refs = list(dict.fromkeys(explicit_hidden + automatically_hidden))
    state_deltas = _resolve_path_items(
        state_snapshot,
        request.get("morphology_state_paths", []),
        group="morphology_state_paths",
    )
    obligations = list(dict.fromkeys(
        [str(item) for item in request.get("morphology_visibility_obligations", [])]
        + [
            f"preserve {item.get('feature_id')} count, attachment, shape, surface, and declared individual differences"
            for item in visible
        ]
    ))
    crop_requirements = list(dict.fromkeys(str(item) for item in request.get("morphology_crop_and_occlusion_requirements", [])))
    expression_channels = []
    species_channels = {
        str(item.get("channel_id")): copy.deepcopy(item)
        for item in species_profile.get("expression_system", [])
        if isinstance(item, dict) and item.get("channel_id")
    }
    individual_channels = {
        str(item.get("channel_id")): copy.deepcopy(item)
        for item in individual_morphology.get("individual_expression_signature", [])
        if isinstance(item, dict) and item.get("channel_id")
    }
    expression_projection: list[dict[str, Any]] = []
    requested_expression = {
        str(item.get("channel_id")): copy.deepcopy(item)
        for item in request.get("morphology_expression_projection", [])
        if isinstance(item, dict) and item.get("channel_id")
    }
    for channel_id in sorted(set(species_channels) | set(individual_channels)):
        species_channel = species_channels.get(channel_id)
        individual_channel = individual_channels.get(channel_id)
        expression_channels.append({
            "channel_id": channel_id,
            "species_capability": species_channel,
            "individual_signature": individual_channel,
        })
        authored = requested_expression.get(channel_id)
        if authored is not None:
            expression_projection.append(authored)
        else:
            expression_projection.append({
                "channel_id": channel_id,
                "carrier_feature_refs": list((species_channel or {}).get("carrier_feature_refs", [])),
                "configuration": str((individual_channel or {}).get("baseline_bias") or (species_channel or {}).get("neutral_state") or "neutral declared state"),
                "meaning_candidates": list((species_channel or {}).get("readable_meanings", [])),
                "tool_refs": list((species_channel or {}).get("external_tool_refs", [])),
            })
    count_checks = [
        f"{item.get('feature_id')}: actual_count={item.get('actual_count')} and attachment={item.get('attachment_realization', {}).get('attachment_landmarks', [])}"
        for item in visible
    ]
    return {
        "species_profile_ref": {
            "id": str(species_profile["profile_id"]),
            "sha256": species_hash,
        },
        "individual_morphology_ref": {
            "id": str(individual_morphology["contract_id"]),
            "sha256": individual_hash,
        },
        "active_form": str(individual_morphology.get("life_stage_and_form", {}).get("active_form") or "baseline"),
        "body_plan": {
            "species_body_plan": copy.deepcopy(species_profile.get("body_plan", {})),
            "individual_measurements": copy.deepcopy(individual_morphology.get("individual_measurements", {})),
            "life_stage_and_form": copy.deepcopy(individual_morphology.get("life_stage_and_form", {})),
        },
        "frame_character": copy.deepcopy(individual_morphology.get("frame_character") or species_profile.get("frame_character_model", {}).get("default") or {}),
        "measurement_pass_status": str(request.get("measurement_pass_status") or ("complete" if individual_morphology.get("load_bearing_part_measurements") or request.get("morphology_load_bearing_part_measurements") else "not-required")),
        "load_bearing_part_measurements": copy.deepcopy(
            request.get("morphology_load_bearing_part_measurements")
            if request.get("morphology_load_bearing_part_measurements") is not None
            else individual_morphology.get("load_bearing_part_measurements", [])
        ),
        "visible_feature_instances": visible,
        "hidden_or_out_of_frame_feature_refs": hidden_feature_refs,
        "feature_relationships": copy.deepcopy(individual_morphology.get("feature_relationship_realizations", [])),
        "surface_and_marking_map": copy.deepcopy(individual_morphology.get("surface_and_marking_map", [])),
        "expression_channels": expression_channels,
        "expression_projection": expression_projection,
        "communication_and_expression_tools": copy.deepcopy(
            individual_morphology.get("communication_and_expression_tool_realizations", [])
        ),
        "identity_invariants": copy.deepcopy(individual_morphology.get("identity_invariants", [])),
        "inventory_proof": {
            "declared_visible_count": len(visible),
            "declared_hidden_count": len(hidden_feature_refs),
            "unresolved_count": len(individual_morphology.get("unresolved_features", [])),
            "count_and_attachment_checks": count_checks,
        },
        "current_state_deltas": state_deltas,
        "visible_obligations": obligations,
        "crop_and_occlusion_requirements": crop_requirements,
        "uncertainties": copy.deepcopy(state_snapshot.get("uncertainties", [])),
    }

def projection_semantic_content(value: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "resolved_morphology", "visible_identity_features", "visible_state_deltas", "performance_cues",
        "wardrobe_and_accessory_state", "held_or_visible_props",
        "relationship_blocking_cues", "environmental_body_responses",
        "occluded_or_irrelevant_features", "reference_asset_requirements",
        "text_anchor_fragments", "review_dimensions",
    )
    return {key: value.get(key) for key in keys}

def build_projection(
    identity_contract: dict[str, Any],
    species_profile: dict[str, Any],
    individual_morphology: dict[str, Any],
    state_snapshot: dict[str, Any],
    scene_context: dict[str, Any],
    request: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    for artifact in (identity_contract, state_snapshot, scene_context):
        report = validate_artifact(artifact)
        if not report["ok"]:
            raise ValueError(f"invalid {artifact.get('artifact_type')}: {'; '.join(report['errors'])}")
    species_hash = artifact_hash(species_profile)
    individual_hash = artifact_hash(individual_morphology)
    if identity_contract.get("species_morphology_profile_ref") != {
        "id": species_profile.get("profile_id"), "sha256": species_hash
    }:
        raise ValueError("identity contract species morphology reference does not match supplied profile")
    if identity_contract.get("individual_morphology_contract_ref") != {
        "id": individual_morphology.get("contract_id"), "sha256": individual_hash
    }:
        raise ValueError("identity contract individual morphology reference does not match supplied contract")
    if individual_morphology.get("character_id") != identity_contract.get("character_id"):
        raise ValueError("individual morphology contract belongs to another character")
    if request.get("character_id") != identity_contract.get("character_id"):
        raise ValueError("projection request character_id differs from identity contract")

    character_id = identity_contract["character_id"]
    if state_snapshot.get("character_id") != character_id or state_snapshot.get("identity_contract_sha256") != artifact_hash(identity_contract):
        raise ValueError("state snapshot does not bind the supplied identity")
    if state_snapshot["scene_context_id"] != scene_context["scene_context_id"] or state_snapshot["timeline_id"] != scene_context["timeline_id"]:
        raise ValueError("projection snapshot and scene context have different scope")
    if not scene_context["story_order_start"] <= state_snapshot["story_order"] <= scene_context["story_order_end"]:
        raise ValueError("projection snapshot is outside the scene context range")
    binding = {"character_id": character_id, "snapshot_id": state_snapshot["snapshot_id"], "state_snapshot_sha256": artifact_hash(state_snapshot)}
    if binding not in scene_context["active_character_snapshots"]:
        raise ValueError("scene context does not bind the projection's exact character snapshot")
    features = _identity_features(identity_contract)
    visible_features: list[dict[str, Any]] = []
    for feature_id in request.get("visible_identity_feature_ids", []):
        if str(feature_id) not in features:
            raise ValueError(f"unknown identity feature ID: {feature_id}")
        visible_features.append(copy.deepcopy(features[str(feature_id)]))

    text_anchors: list[dict[str, Any]] = []
    for anchor_id in request.get("text_anchor_ids", []):
        feature = features.get(str(anchor_id))
        if not feature or feature.get("source") != "anchor-fragment":
            raise ValueError(f"unknown anchor fragment ID: {anchor_id}")
        text_anchors.append(copy.deepcopy(feature))

    projection = {
        "artifact_type": "visual-state-projection",
        "projection_id": str(request["projection_id"]),
        "character_id": str(request["character_id"]),
        "state_snapshot_sha256": str(state_snapshot["state_snapshot_sha256"]),
        "scene_context_sha256": str(scene_context["context_snapshot_sha256"]),
        "resolved_morphology": resolve_morphology_projection(
            species_profile, individual_morphology, state_snapshot, request
        ),
        "visible_identity_features": visible_features,
        "visible_state_deltas": _resolve_path_items(state_snapshot, request.get("visible_state_paths", []), group="visible_state_paths"),
        "performance_cues": copy.deepcopy(request.get("performance_cues", [])),
        "wardrobe_and_accessory_state": _resolve_path_items(state_snapshot, request.get("wardrobe_paths", []), group="wardrobe_paths"),
        "held_or_visible_props": _resolve_path_items(state_snapshot, request.get("prop_paths", []), group="prop_paths"),
        "relationship_blocking_cues": copy.deepcopy(request.get("relationship_blocking_cues", [])),
        "environmental_body_responses": copy.deepcopy(request.get("environmental_body_responses", [])),
        "occluded_or_irrelevant_features": _resolve_path_items(state_snapshot, request.get("occluded_state_paths", []), group="occluded_state_paths"),
        "reference_asset_requirements": copy.deepcopy(request.get("reference_asset_requirements", [])),
        "text_anchor_fragments": text_anchors,
        "review_dimensions": list(dict.fromkeys(str(item) for item in request.get("review_dimensions", []))),
        "prompt_regeneration_required": True,
        "projection_sha256": "0" * 64,
    }
    if previous:
        projection["prompt_regeneration_required"] = (
            projection_semantic_content(projection) != projection_semantic_content(previous)
            or projection["state_snapshot_sha256"] != previous.get("state_snapshot_sha256")
            or projection["scene_context_sha256"] != previous.get("scene_context_sha256")
        )
    return finalize_artifact(projection)

COVERAGE_POLICIES = ("core-coverage", "series-coverage", "motion-evaluation")


def anchor_text_for_view(contract: dict[str, Any], tokens: set[str]) -> list[str]:
    chosen: list[str] = []
    for anchor in contract.get("anchor_fragments", []):
        if not isinstance(anchor, dict):
            continue
        required_when = set(str(item) for item in anchor.get("required_when", []))
        omit_when = set(str(item) for item in anchor.get("omit_when", []))
        if omit_when & tokens:
            continue
        if not required_when or required_when & tokens or anchor.get("priority") == "signature":
            wording = str(anchor.get("wording") or "").strip()
            if wording:
                chosen.append(wording)
    return chosen


def plan_reference_bundle(
    contract: dict[str, Any],
    *,
    species_profile: dict[str, Any],
    individual_morphology: dict[str, Any],
    style_family_id: str,
    target_model: str,
    policy: str,
    out_dir: Path,
    era_contract: dict[str, Any] | None = None,
    appearance_variant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = validate_artifact(contract)
    if not report["ok"]:
        raise ValueError("invalid identity contract: " + "; ".join(report["errors"]))
    if policy not in COVERAGE_POLICIES:
        raise ValueError(f"unknown coverage policy: {policy}")
    identity_hash = artifact_hash(contract)
    species_report = validate_artifact(species_profile)
    if not species_report["ok"] or species_profile.get("artifact_type") != "species-morphology-profile":
        raise ValueError("invalid species morphology profile: " + "; ".join(species_report.get("errors", [])))
    individual_report = validate_artifact(individual_morphology)
    if not individual_report["ok"] or individual_morphology.get("artifact_type") != "individual-morphology-contract":
        raise ValueError("invalid individual morphology contract: " + "; ".join(individual_report.get("errors", [])))
    species_hash = artifact_hash(species_profile)
    individual_hash = artifact_hash(individual_morphology)
    species_ref = contract.get("species_morphology_profile_ref", {})
    individual_ref = contract.get("individual_morphology_contract_ref", {})
    if species_ref.get("id") != species_profile.get("profile_id") or species_ref.get("sha256") != species_hash:
        raise ValueError("identity contract species morphology reference does not match supplied profile")
    if individual_ref.get("id") != individual_morphology.get("contract_id") or individual_ref.get("sha256") != individual_hash:
        raise ValueError("identity contract individual morphology reference does not match supplied contract")
    if individual_morphology.get("character_id") != contract.get("character_id"):
        raise ValueError("individual morphology contract belongs to another character")
    if individual_morphology.get("domain") != contract.get("domain") or species_profile.get("domain") != contract.get("domain"):
        raise ValueError("morphology domain differs from character identity domain")
    era_hash: str | None = None
    appearance_hash: str | None = None
    if era_contract is not None:
        era_report = validate_artifact(era_contract)
        if not era_report["ok"] or era_contract.get("artifact_type") != "era-contract":
            raise ValueError("invalid era contract: " + "; ".join(era_report.get("errors", [])))
        if era_contract.get("character_id") != contract.get("character_id"):
            raise ValueError("era contract belongs to another character")
        era_hash = artifact_hash(era_contract)
    if appearance_variant is not None:
        appearance_report = validate_artifact(appearance_variant)
        if not appearance_report["ok"] or appearance_variant.get("artifact_type") != "appearance-variant-contract":
            raise ValueError("invalid appearance variant: " + "; ".join(appearance_report.get("errors", [])))
        if appearance_variant.get("character_id") != contract.get("character_id"):
            raise ValueError("appearance variant belongs to another character")
        appearance_hash = artifact_hash(appearance_variant)
    declared_views = contract.get("reference_views")
    if not declared_views:
        raise ValueError("reference planning requires explicit reference_views and camera contracts")
    requirements = [item for item in contract.get("coverage_requirements", []) if isinstance(item, dict)]
    reference_candidates = {
        name: {"view": row["view"], "framing": row["framing"],
               "tokens": set(row["coverage_tokens"]), "camera": copy.deepcopy(row["camera"])}
        for name, row in sorted(declared_views.items())
    }
    selected: list[str] = [] if requirements else list(reference_candidates)

    # Add candidates greedily until every declared requirement has at least one acceptable view.
    def requirement_covered(req: dict[str, Any], candidates: list[str]) -> bool:
        acceptable = set(str(item) for item in req.get("acceptable_views", []))
        return any(acceptable & reference_candidates[name]["tokens"] for name in candidates)

    unresolved = [req for req in requirements if not requirement_covered(req, selected)]
    while unresolved:
        best_name: str | None = None
        best_score = 0
        for name, candidate in reference_candidates.items():
            if name in selected:
                continue
            score = sum(bool(set(req.get("acceptable_views", [])) & candidate["tokens"]) for req in unresolved)
            if score > best_score:
                best_name, best_score = name, score
        if not best_name or best_score == 0:
            break
        selected.append(best_name)
        unresolved = [req for req in requirements if not requirement_covered(req, selected)]

    asset_rows: list[dict[str, Any]] = []
    pending_render_specs: list[tuple[str, dict[str, Any]]] = []
    coverage_matrix: dict[str, list[str]] = {str(req["requirement_id"]): [] for req in requirements}
    stable = copy.deepcopy(contract.get("stable_identity", {}))
    stable["growth_geometry"] = resolve_growth_geometry(
        contract, era_contract=era_contract, appearance_variant=appearance_variant,
    )
    stable["species_morphology_profile"] = copy.deepcopy(species_profile)
    stable["individual_morphology_contract"] = copy.deepcopy(individual_morphology)
    if era_contract is not None:
        stable["era_changes"] = copy.deepcopy(era_contract.get("approved_changes", {}))
    if appearance_variant is not None:
        stable["appearance_variant"] = copy.deepcopy(appearance_variant.get("appearance_definition", {}))
    character_id = str(contract["character_id"])

    for index, name in enumerate(selected, 1):
        candidate = reference_candidates[name]
        tokens = set(candidate["tokens"])
        requirement_ids = []
        for req in requirements:
            if set(req.get("acceptable_views", [])) & tokens:
                rid = str(req["requirement_id"])
                requirement_ids.append(rid)
        asset_id = f"{character_id}-A{index:02d}"
        render_spec_id = f"ARS-{asset_id}"
        anchors = anchor_text_for_view(contract, tokens)
        identity_summary = "; ".join(
            str(stable.get(key) or "").strip()
            for key in ("species_or_base_form", "body_plan", "proportions", "head_and_face", "structure_notes", "surfaces_and_markings", "appendages", "asymmetry_rules", "identity_accessories")
            if str(stable.get(key) or "").strip()
        )
        scaffold = (
            f"Create a {candidate['framing']} character reference in {candidate['view']} view. "
            f"Preserve the approved identity: {identity_summary}. "
            + ("Visible signature anchors: " + "; ".join(anchors) + ". " if anchors else "")
            + "Use neutral production lighting, clear unobstructed declared structure, and the selected concrete style family consistently. "
            + "This is a reference asset: prioritize measurable identity, attachment, markings, proportions, and silhouette over scene storytelling."
        )
        spec = {
                "artifact_type": "asset-render-specification",
            "render_spec_id": render_spec_id,
            "asset_id": asset_id,
            "character_id": character_id,
            "purpose": name,
            "view": candidate["view"],
            "framing": candidate["framing"],
            "species_profile_sha256": species_hash,
            "individual_morphology_sha256": individual_hash,
            "identity_contract_sha256": identity_hash,
            "era_contract_sha256": era_hash,
            "appearance_variant_sha256": appearance_hash,
            "state_snapshot_sha256": None,
            "visual_state_projection_sha256": None,
            "visual_authority_sha256": (contract.get("visual_authority_ref") or {}).get("sha256"),
            "visual_evidence_bundle_sha256": None,
            "style_family_id": style_family_id,
            "target_model": target_model,
            "coverage_requirement_ids": requirement_ids,
            "art_direction": {
                "center_of_appeal": "measurable character identity and consistent design",
                "composition": f"{candidate['view']} {candidate['framing']}",
                "medium": style_family_id,
                "detail_hierarchy": "declared identity landmarks, silhouette, attachments and local details",
            },
            "subject_resolution": copy.deepcopy(stable),
            "scene": {"background": "plain neutral reference background", "storytelling": "none"},
            "camera": copy.deepcopy(candidate["camera"]),
            "lighting": {"key": "neutral soft directional light", "fill": "clean neutral fill", "color": "stable local color"},
            "prompt_scaffold": scaffold,
            "selected_preset_ids": [style_family_id],
            "render_spec_sha256": "0" * 64,
        }
        spec = finalize_artifact(spec)
        spec_report = validate_artifact(spec)
        if not spec_report.get("ok"):
            raise ValueError(
                f"invalid generated render specification {render_spec_id}: "
                + "; ".join(spec_report.get("errors", []))
            )
        file_name = f"{asset_id}-{name}.render-spec.json"
        pending_render_specs.append((file_name, spec))
        asset_rows.append({
            "asset_id": asset_id,
            "purpose": name,
            "render_spec_file": file_name,
            "render_spec_sha256": spec["render_spec_sha256"],
            "coverage_requirement_ids": requirement_ids,
        })
        for rid in requirement_ids:
            coverage_matrix[rid].append(asset_id)

    unresolved_ids = [str(req["requirement_id"]) for req in unresolved]
    plan = {
        "artifact_type": "reference-bundle-plan",
        "bundle_id": f"RB-{character_id}",
        "character_id": character_id,
        "species_profile_sha256": species_hash,
        "individual_morphology_sha256": individual_hash,
        "identity_contract_sha256": identity_hash,
        "era_contract_sha256": era_hash,
        "appearance_variant_sha256": appearance_hash,
        "visual_authority_sha256": (contract.get("visual_authority_ref") or {}).get("sha256"),
        "visual_evidence_bundle_sha256": None,
        "style_family_id": style_family_id,
        "coverage_policy": policy,
        "assets": asset_rows,
        "coverage_matrix": coverage_matrix,
        "unresolved_requirements": unresolved_ids,
        "generated_by": PACKAGE_NAME,
        "notes": [
            "The plan is generation intent, not approved canon.",
            "Actual images require direct inspection and a separate candidate manifest before adoption.",
        ],
        "bundle_plan_sha256": "0" * 64,
    }
    plan = finalize_artifact(plan)
    plan_report = validate_artifact(plan)
    if not plan_report.get("ok"):
        raise ValueError(
            "invalid generated reference bundle plan: "
            + "; ".join(plan_report.get("errors", []))
        )

    # The output directory is the commit boundary.  No child file is written
    # until every child render specification and the enclosing plan validate.
    out_dir.mkdir(parents=True, exist_ok=True)
    for file_name, spec in pending_render_specs:
        write_json(out_dir / file_name, spec)
    write_json(out_dir / "reference-bundle-plan.json", plan)
    return plan


def build_lineage(args: argparse.Namespace) -> dict[str, Any]:
    def hash_file(path_value: str | None, expected_type: str | None = None) -> str | None:
        if not path_value:
            return None
        data = load_json(Path(path_value))
        if expected_type and data.get("artifact_type") != expected_type:
            raise ValueError(f"expected {expected_type}, got {data.get('artifact_type')}: {path_value}")
        report = validate_artifact(data)
        if not report["ok"]:
            raise ValueError(f"invalid artifact {path_value}: {'; '.join(report['errors'])}")
        return artifact_hash(data)

    if args.mode == "stateless":
        supplied = [
            name
            for name in (
                "species_profile",
                "individual_morphology",
                "identity_contract",
                "era_contract",
                "form_contract",
                "appearance_variant",
                "state_snapshot",
                "scene_context",
                "visual_projection",
                "asset_render_spec",
                "visual_authority",
                "visual_evidence_bundle",
            )
            if getattr(args, name, None)
        ]
        if supplied:
            raise ValueError(f"stateless lineage does not accept state artifacts: {supplied}")
        node_hashes = {field: None for field in STATE_LINEAGE_ARTIFACT_FIELDS}
    else:
        node_hashes = {
            "species_profile_sha256": hash_file(
                args.species_profile, "species-morphology-profile"
            ),
            "individual_morphology_sha256": hash_file(
                args.individual_morphology, "individual-morphology-contract"
            ),
            "identity_contract_sha256": hash_file(
                args.identity_contract, "character-identity-contract"
            ),
            "era_contract_sha256": hash_file(args.era_contract, "era-contract"),
            "form_contract_sha256": hash_file(args.form_contract, "form-contract"),
            "appearance_variant_sha256": hash_file(
                args.appearance_variant, "appearance-variant-contract"
            ),
            "state_snapshot_sha256": hash_file(args.state_snapshot, "state-snapshot"),
            "scene_context_sha256": hash_file(
                args.scene_context, "scene-context-snapshot"
            ),
            "visual_projection_sha256": hash_file(
                args.visual_projection, "visual-state-projection"
            ),
            "asset_render_spec_sha256": hash_file(
                args.asset_render_spec, "asset-render-specification"
            ),
            "visual_authority_sha256": hash_file(
                args.visual_authority, "visual-authority"
            ),
            "visual_evidence_bundle_sha256": hash_file(
                args.visual_evidence_bundle, "visual-evidence-bundle"
            ),
        }

    result = {
        "artifact_type": "state-lineage",
        "mode": args.mode,
        **node_hashes,
        "lineage_sha256": ZERO_SHA256,
    }
    return finalize_artifact(result)



_MISSING = object()


def _compare(left: Any, operator: str, right: Any) -> bool:
    """Evaluate one rule comparison without raising on absent or incompatible data.

    Environment rules are optional proposals, not state mutations. A rule whose
    JSON pointer does not resolve, or whose value cannot participate in the
    requested comparison, is simply not satisfied. This mirrors event
    preconditions, where a missing path evaluates false unless the operator is
    ``not-exists``.
    """

    if operator == "exists":
        return left is not _MISSING
    if operator == "not-exists":
        return left is _MISSING
    if left is _MISSING:
        return False
    if operator == "equals":
        return left == right
    if operator == "not-equals":
        return left != right
    if operator == "contains":
        try:
            return right in left
        except TypeError:
            return False
    try:
        if operator == "greater-than":
            return left > right
        if operator == "greater-or-equal":
            return left >= right
        if operator == "less-than":
            return left < right
        if operator == "less-or-equal":
            return left <= right
    except TypeError:
        return False
    raise ValueError(f"unsupported comparison operator: {operator}")


def propose_environment_adaptations(
    state_schema: dict[str, Any],
    environment_snapshot: dict[str, Any],
    *,
    character_id: str,
    proposal_id: str,
) -> dict[str, Any]:
    for artifact in (state_schema, environment_snapshot):
        report = validate_artifact(artifact)
        if not report["ok"]:
            raise ValueError(f"invalid {artifact.get('artifact_type')}: {'; '.join(report['errors'])}")
    if state_schema.get("character_id") != character_id:
        raise ValueError("state schema character_id differs from requested character")

    matched: list[str] = []
    proposals: list[dict[str, Any]] = []
    for raw_rule in state_schema.get("environment_adaptation_rules", []):
        if not isinstance(raw_rule, dict):
            continue
        rule_id = str(raw_rule.get("rule_id") or "")
        conditions = raw_rule.get("when", [])
        if not rule_id or not isinstance(conditions, list):
            continue
        satisfied = True
        for condition in conditions:
            if not isinstance(condition, dict):
                satisfied = False
                break
            path = str(condition.get("path") or "")
            operator = str(condition.get("operator") or "equals")
            current = get_pointer(environment_snapshot, path, missing=_MISSING)
            if not _compare(current, operator, condition.get("value")):
                satisfied = False
                break
        if satisfied:
            matched.append(rule_id)
            proposal = copy.deepcopy(raw_rule.get("proposal", {}))
            if isinstance(proposal, dict):
                proposal.setdefault("rule_id", rule_id)
                # Environment rules may propose identity-affecting presentation
                # changes, but they cannot lower the approval boundary authored
                # by this protocol.
                proposal["requires_human_approval"] = True
                proposals.append(proposal)

    result = {
        "artifact_type": "appearance-adaptation-proposal",
        "proposal_id": proposal_id,
        "character_id": character_id,
        "environment_snapshot_sha256": str(environment_snapshot["environment_snapshot_sha256"]),
        "matched_rule_ids": matched,
        "proposals": proposals,
        "approval_required": True,
        "status": "proposed",
        "proposal_sha256": "0" * 64,
    }
    return finalize_artifact(result)


def select_state_references(
    bindings: list[dict[str, Any]],
    *,
    selection_id: str,
    identity_hash: str,
    era_hash: str | None,
    appearance_hash: str | None,
    state_hash: str | None,
    story_order: int,
    required_features: list[str],
    limit: int,
) -> dict[str, Any]:
    from prepare_generation_references import validate_committed_source

    if (
        not isinstance(required_features, list)
        or any(not isinstance(value, str) or not value for value in required_features)
        or len(set(required_features)) != len(required_features)
    ):
        raise ValueError("required_features must contain unique non-empty strings")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("reference selection limit must be a non-negative integer")
    if not isinstance(story_order, int) or isinstance(story_order, bool):
        raise ValueError("story_order must be an integer")

    eligible: list[dict[str, Any]] = []
    for binding in bindings:
        report = validate_artifact(binding)
        if not report["ok"]:
            raise ValueError(f"invalid reference binding {binding.get('binding_id')}: {'; '.join(report['errors'])}")
        canonical_source = validate_committed_source(
            binding.get("source"),
            f"reference binding {binding.get('binding_id')}.source",
        )
        if canonical_source != binding.get("source"):
            raise ValueError(
                f"reference binding {binding.get('binding_id')}.source is not canonical"
            )
        if binding.get("identity_contract_sha256") != identity_hash:
            continue
        if binding.get("era_contract_sha256") not in {None, era_hash}:
            continue
        if binding.get("appearance_variant_sha256") not in {None, appearance_hash}:
            continue
        if binding.get("state_snapshot_sha256") not in {None, state_hash}:
            continue
        story_range = binding.get("effective_story_range", {})
        start = story_range["from_order"]
        end = story_range.get("to_order")
        if story_order < start or (end is not None and story_order > end):
            continue
        # A binding superseded for future scenes remains usable inside a closed
        # range, because to_order already bounds it. An open-ended superseded
        # binding carries no such bound, so it must not be selected at all.
        if binding.get("superseded_for_future_scenes") is True and end is None:
            continue
        eligible.append(binding)

    def source_order_key(item: dict[str, Any]) -> str:
        source = item["source"]
        return source.get("asset_id") or source.get("reference_id")

    def selected_reference(item: dict[str, Any], covers: list[str]) -> dict[str, Any]:
        return {
            "binding_id": item["binding_id"],
            "role": item["role"],
            "source": copy.deepcopy(item["source"]),
            "covers": covers,
            "intended_influence": copy.deepcopy(item.get("intended_influence", [])),
            "review_dimensions": copy.deepcopy(item.get("review_dimensions", [])),
            "unsupported_or_occluded_state": copy.deepcopy(
                item.get("unsupported_or_occluded_state", [])
            ),
            "unsupported_assumptions": copy.deepcopy(
                item.get("unsupported_assumptions", [])
            ),
        }

    remaining = set(required_features)
    selected: list[dict[str, Any]] = []
    candidates = list(eligible)
    while remaining and candidates and len(selected) < limit:
        best = min(
            candidates,
            key=lambda item: (
                -len(remaining & set(item.get("visibly_supported_state", []))),
                source_order_key(item),
                item["binding_id"],
            ),
        )
        coverage = remaining & set(best.get("visibly_supported_state", []))
        if not coverage:
            break
        selected.append(selected_reference(best, sorted(coverage)))
        remaining -= coverage
        candidates.remove(best)

    # When there are no explicit feature obligations, choose the strongest generic identity binding.
    if not required_features and eligible and limit > 0:
        ranked = sorted(
            eligible,
            key=lambda item: (
                "identity" not in item.get("intended_influence", []),
                -len(item.get("visibly_supported_state", [])),
                source_order_key(item),
            ),
        )
        selected = [selected_reference(item, []) for item in ranked[:limit]]

    result = {
        "artifact_type": "reference-selection",
        "selection_id": selection_id,
        "identity_contract_sha256": identity_hash,
        "era_contract_sha256": era_hash,
        "appearance_variant_sha256": appearance_hash,
        "state_snapshot_sha256": state_hash,
        "story_order": story_order,
        "required_state_features": list(required_features),
        "selected_references": selected,
        "unresolved_requirements": sorted(remaining),
        "selection_sha256": "0" * 64,
    }
    return finalize_artifact(result)

def parse_processes(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = parse_json(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("artifact_type") == "state-process":
        return [data]
    if not isinstance(data, list):
        raise ValueError("process file must contain one state-process object or an array")
    if not all(isinstance(item, dict) for item in data):
        raise ValueError("process array must contain objects")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    # Import the pack runtime boundary only after this module has finished
    # defining the schema validator used by pack_manager. A module-level import
    # would create a state_protocol -> catalog -> pack_manager cycle.
    from catalog_cli import configure_pack_runtime
    from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime

    parser = argparse.ArgumentParser(description="Manage Shared State Protocol artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("artifacts", nargs="+")

    finalize_cmd = sub.add_parser("finalize")
    finalize_cmd.add_argument("artifact")
    finalize_cmd.add_argument("--out", required=True)

    hash_cmd = sub.add_parser("hash")
    hash_cmd.add_argument("artifact")

    resolve_cmd = sub.add_parser("resolve-world")
    resolve_cmd.add_argument("--base-state", required=True)
    resolve_cmd.add_argument("--events", required=True)
    resolve_cmd.add_argument("--processes")
    resolve_cmd.add_argument("--timeline", required=True)
    resolve_cmd.add_argument("--scene-context-id", required=True)
    resolve_cmd.add_argument("--story-order", type=int, required=True)
    resolve_cmd.add_argument("--story-time", required=True)
    resolve_cmd.add_argument("--snapshot-id", required=True)
    resolve_cmd.add_argument("--out", required=True)

    extract_cmd = sub.add_parser("extract-character")
    extract_cmd.add_argument("--world-snapshot", required=True)
    extract_cmd.add_argument("--character-id", required=True)
    extract_cmd.add_argument("--species-profile", required=True)
    extract_cmd.add_argument("--individual-morphology", required=True)
    extract_cmd.add_argument("--identity-contract", required=True)
    extract_cmd.add_argument("--era-contract")
    extract_cmd.add_argument("--form-contract")
    extract_cmd.add_argument("--appearance-variant")
    extract_cmd.add_argument("--snapshot-id", required=True)
    extract_cmd.add_argument("--out", required=True)

    context_cmd = sub.add_parser("build-context")
    context_cmd.add_argument("--request", required=True)
    context_cmd.add_argument("--world-snapshot", required=True)
    context_cmd.add_argument("--character-snapshot", action="append", default=[])
    context_cmd.add_argument("--out", required=True)

    projection_cmd = sub.add_parser("build-projection")
    projection_cmd.add_argument("--species-profile", required=True)
    projection_cmd.add_argument("--individual-morphology", required=True)
    projection_cmd.add_argument("--identity-contract", required=True)
    projection_cmd.add_argument("--state-snapshot", required=True)
    projection_cmd.add_argument("--scene-context", required=True)
    projection_cmd.add_argument("--request", required=True)
    projection_cmd.add_argument("--previous")
    projection_cmd.add_argument("--out", required=True)

    bundle_cmd = sub.add_parser("plan-reference-bundle")
    bundle_cmd.add_argument("--identity-contract", required=True)
    bundle_cmd.add_argument("--species-profile", required=True)
    bundle_cmd.add_argument("--individual-morphology", required=True)
    bundle_cmd.add_argument("--style-family", required=True)
    bundle_cmd.add_argument("--target-model", required=True)
    bundle_cmd.add_argument("--policy", choices=sorted(COVERAGE_POLICIES), default="series-coverage")
    bundle_cmd.add_argument("--era-contract")
    bundle_cmd.add_argument("--appearance-variant")
    bundle_cmd.add_argument("--out-dir", required=True)

    lineage_cmd = sub.add_parser("make-lineage")
    lineage_cmd.add_argument("--mode", choices=["stateless", "state-aware"], required=True)
    lineage_cmd.add_argument("--species-profile")
    lineage_cmd.add_argument("--individual-morphology")
    lineage_cmd.add_argument("--identity-contract")
    lineage_cmd.add_argument("--era-contract")
    lineage_cmd.add_argument("--form-contract")
    lineage_cmd.add_argument("--appearance-variant")
    lineage_cmd.add_argument("--state-snapshot")
    lineage_cmd.add_argument("--scene-context")
    lineage_cmd.add_argument("--visual-projection")
    lineage_cmd.add_argument("--asset-render-spec")
    lineage_cmd.add_argument("--visual-authority")
    lineage_cmd.add_argument("--visual-evidence-bundle")
    lineage_cmd.add_argument("--out", required=True)

    adapt_cmd = sub.add_parser("propose-environment-adaptations")
    adapt_cmd.add_argument("--state-schema", required=True)
    adapt_cmd.add_argument("--environment-snapshot", required=True)
    adapt_cmd.add_argument("--character-id", required=True)
    adapt_cmd.add_argument("--proposal-id", required=True)
    adapt_cmd.add_argument("--out", required=True)

    select_cmd = sub.add_parser("select-references")
    select_cmd.add_argument("--bindings", required=True, help="JSON array or object with a bindings array")
    select_cmd.add_argument("--selection-id", required=True)
    select_cmd.add_argument("--identity-contract", required=True)
    select_cmd.add_argument("--era-contract")
    select_cmd.add_argument("--appearance-variant")
    select_cmd.add_argument("--state-snapshot")
    select_cmd.add_argument("--story-order", type=int, required=True)
    select_cmd.add_argument("--required-feature", action="append", default=[])
    select_cmd.add_argument("--limit", type=int, default=3)
    select_cmd.add_argument("--out", required=True)
    add_pack_runtime_arguments(select_cmd)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            reports = []
            for item in args.artifacts:
                data = load_json(Path(item))
                report = validate_artifact(data)
                report["file"] = item
                reports.append(report)
            result = {"ok": all(item["ok"] for item in reports), "artifacts": reports}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1

        if args.command == "finalize":
            data = finalize_artifact(load_json(Path(args.artifact)))
            report = validate_artifact(data)
            if not report["ok"]:
                raise ValueError("invalid finalized artifact: " + "; ".join(report["errors"]))
            write_json(Path(args.out), data)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0

        if args.command == "hash":
            data = load_json(Path(args.artifact))
            print(json.dumps({"artifact_type": data.get("artifact_type"), "sha256": artifact_hash(data)}, indent=2))
            return 0

        if args.command == "resolve-world":
            base = load_json(Path(args.base_state))
            events = load_jsonl(Path(args.events))
            processes = parse_processes(args.processes)
            result = resolve_world(
                base_state=base, events=events, processes=processes,
                timeline_id=args.timeline, story_order=args.story_order,
                story_time=args.story_time, snapshot_id=args.snapshot_id,
                scene_context_id=args.scene_context_id,
            )
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("resolved world snapshot is invalid: " + "; ".join(report["errors"]))
            write_json(Path(args.out), result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "extract-character":
            species_profile = load_json(Path(args.species_profile))
            individual_morphology = load_json(Path(args.individual_morphology))
            identity = load_json(Path(args.identity_contract))
            result = extract_character_snapshot(
                load_json(Path(args.world_snapshot)), character_id=args.character_id,
                species_profile_hash=artifact_hash(species_profile),
                individual_morphology_hash=artifact_hash(individual_morphology),
                identity_hash=artifact_hash(identity),
                era_hash=artifact_hash(load_json(Path(args.era_contract))) if args.era_contract else None,
                form_hash=artifact_hash(load_json(Path(args.form_contract))) if args.form_contract else None,
                appearance_hash=artifact_hash(load_json(Path(args.appearance_variant))) if args.appearance_variant else None,
                snapshot_id=args.snapshot_id,
            )
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("character snapshot is invalid: " + "; ".join(report["errors"]))
            write_json(Path(args.out), result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "build-context":
            request = load_json(Path(args.request))
            world = load_json(Path(args.world_snapshot))
            snapshots = [load_json(Path(path)) for path in args.character_snapshot]
            result = build_scene_context(request, world, snapshots)
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("scene context is invalid: " + "; ".join(report["errors"]))
            write_json(Path(args.out), result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "build-projection":
            result = build_projection(
                load_json(Path(args.identity_contract)),
                load_json(Path(args.species_profile)),
                load_json(Path(args.individual_morphology)),
                load_json(Path(args.state_snapshot)),
                load_json(Path(args.scene_context)),
                load_json(Path(args.request)),
                load_json(Path(args.previous)) if args.previous else None,
            )
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("visual state projection is invalid: " + "; ".join(report["errors"]))
            write_json(Path(args.out), result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "plan-reference-bundle":
            result = plan_reference_bundle(
                load_json(Path(args.identity_contract)),
                species_profile=load_json(Path(args.species_profile)),
                individual_morphology=load_json(Path(args.individual_morphology)),
                style_family_id=args.style_family,
                target_model=args.target_model, policy=args.policy, out_dir=Path(args.out_dir),
                era_contract=load_json(Path(args.era_contract)) if args.era_contract else None,
                appearance_variant=load_json(Path(args.appearance_variant)) if args.appearance_variant else None,
            )
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("reference bundle plan is invalid: " + "; ".join(report["errors"]))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "make-lineage":
            result = build_lineage(args)
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("state lineage is invalid: " + "; ".join(report["errors"]))
            write_json(Path(args.out), result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "propose-environment-adaptations":
            result = propose_environment_adaptations(
                load_json(Path(args.state_schema)), load_json(Path(args.environment_snapshot)),
                character_id=args.character_id, proposal_id=args.proposal_id,
            )
            report = validate_artifact(result)
            if not report["ok"]:
                raise ValueError("appearance adaptation proposal is invalid: " + "; ".join(report["errors"]))
            write_json(Path(args.out), result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "select-references":
            runtime = resolve_pack_runtime(parser, args)
            configure_pack_runtime(runtime.settings)
            try:
                raw = parse_json(Path(args.bindings).read_text(encoding="utf-8"))
                bindings = raw.get("bindings", []) if isinstance(raw, dict) else raw
                if not isinstance(bindings, list) or not all(isinstance(item, dict) for item in bindings):
                    raise ValueError("bindings file must be an array or an object containing a bindings array")
                result = select_state_references(
                    bindings, selection_id=args.selection_id,
                    identity_hash=artifact_hash(load_json(Path(args.identity_contract))),
                    era_hash=artifact_hash(load_json(Path(args.era_contract))) if args.era_contract else None,
                    appearance_hash=artifact_hash(load_json(Path(args.appearance_variant))) if args.appearance_variant else None,
                    state_hash=artifact_hash(load_json(Path(args.state_snapshot))) if args.state_snapshot else None,
                    story_order=args.story_order, required_features=args.required_feature, limit=args.limit,
                )
                report = validate_artifact(result)
                if not report["ok"]:
                    raise ValueError("reference selection is invalid: " + "; ".join(report["errors"]))
                write_json(Path(args.out), result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            finally:
                configure_pack_runtime(None)

        raise AssertionError(args.command)
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
