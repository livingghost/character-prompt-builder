#!/usr/bin/env python3
"""Validate public artifacts, their schema constraints and content commitments.

Only the JSON Schema keywords explicitly implemented here are permitted.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import math
from functools import lru_cache
import re
from pathlib import Path
from typing import Any, Iterable, Sequence
ROOT = Path(__file__).resolve().parents[1]
_ARRAY_INDEX = re.compile(r"^(?:0|[1-9][0-9]*)$")


ZERO_SHA256 = "0" * 64



SHA256_RE = re.compile(r"^[a-f0-9]{64}$")



UTC_RFC3339_RE = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z$"
)



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



STATE_MUTATION_OPERATIONS = frozenset({
    "set", "replace", "merge", "remove", "append", "increment",
})



PROCESS_LIFECYCLE_OPERATIONS = frozenset({
    "interrupt-process", "restart-process",
})



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




@lru_cache(maxsize=16)
def _checked_registry_bytes(raw: bytes) -> dict[str, Any]:
    value = parse_json(raw.decode("utf-8"))
    content = {key: item for key, item in value.items() if key != "contract_set_sha256"}
    if sha256_json(content) != value.get("contract_set_sha256"):
        raise ValueError("public contract manifest hash mismatch")
    rows = value["schemas"]
    if len({row["schema"] for row in rows}) != len(rows):
        raise ValueError("duplicate schema in the public manifest")
    if value["semantics"]["path"] != "protocols/semantics.md":
        raise ValueError("invalid semantic contract path")
    return value


def registry() -> dict[str, Any]:
    # Cache parsing by exact bytes, never by a pathname or a timestamp. Re-read
    # commitments on every use, so edits cannot reuse a stale validated cache.
    value = _checked_registry_bytes((ROOT / "protocols/contract-manifest.json").read_bytes())
    semantics = value["semantics"]
    if hashlib.sha256((ROOT / semantics["path"]).read_bytes()).hexdigest() != semantics["sha256"]:
        raise ValueError("semantic contract byte hash mismatch")
    return copy.deepcopy(value)


@lru_cache(maxsize=128)
def _checked_schema_bytes(raw: bytes) -> dict[str, Any]:
    value = parse_json(raw.decode("utf-8"))
    unsupported = unsupported_schema_keywords(value)
    if unsupported:
        raise ValueError("unsupported schema keywords: " + ", ".join(unsupported))
    return value


def schema_path(key: str) -> Path:
    if key not in {row["schema"] for row in registry()["schemas"]}:
        raise ValueError(f"unregistered public schema: {key}")
    group, name = key.split("/", 1)
    layout = load_json(ROOT / "config" / "protocol-layout.json")
    base = (ROOT / layout[group]).resolve()
    path = (base / name).resolve()
    if ROOT.resolve() not in base.parents or base not in path.parents:
        raise ValueError("schema path leaves the distribution directory")
    return path


def schema_named(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError("schema references must name a registered schema file")
    keys = [row["schema"] for row in registry()["schemas"] if row["schema"].split("/", 1)[1] == name]
    if len(keys) != 1:
        raise ValueError(f"schema name is not unique and registered: {name}")
    path = schema_path(keys[0])
    raw = path.read_bytes()
    expected = next(row["sha256"] for row in registry()["schemas"] if row["schema"] == keys[0])
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("public schema byte hash mismatch: " + keys[0])
    return copy.deepcopy(_checked_schema_bytes(raw))


def schema_for(data: dict[str, Any]) -> dict[str, Any]:
    kind = artifact_type(data)
    entry = registry()["artifacts"].get(kind)
    if entry is None:
        raise ValueError(f"no public schema registered for artifact_type: {kind}")
    return schema_named(entry["schema"].split("/", 1)[1])


SELF_HASH_FIELDS = {kind: row["self_hash_field"] for kind, row in registry()["artifacts"].items() if row["self_hash_field"]}
ARTIFACT_TYPES = frozenset(registry()["artifacts"])


def artifact_content_for_hash(data: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(data)
    field = SELF_HASH_FIELDS.get(str(value.get("artifact_type") or ""))
    if field:
        value.pop(field, None)
    return value



def artifact_hash(data: dict[str, Any]) -> str:
    return sha256_json(artifact_content_for_hash(data))



def finalize_artifact(data: dict[str, Any]) -> dict[str, Any]:
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
    if ref.startswith("#"):
        return _json_pointer(root_schema, ref), root_schema
    name, separator, fragment = ref.partition("#")
    referenced = schema_named(name)
    return (_json_pointer(referenced, "#" + fragment) if separator else referenced), referenced


SUPPORTED_SCHEMA_KEYWORDS = frozenset({
    "$ref", "$defs", "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
    "const", "enum", "type",
    "minLength", "maxLength", "pattern", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems", "uniqueItems", "items", "contains",
    "minProperties", "maxProperties", "required", "properties",
    "propertyNames", "additionalProperties", "dependentRequired",
})



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

    In-document `$defs` are walked and may be reached through JSON pointer
    references. References are resolved from the registered files; no network resources are fetched.
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
            details = [item[0] for item in branch_errors if item]
            suffix = f"; first branch errors: {details}" if details else ""
            errors.append(f"{path}: value does not satisfy anyOf{suffix}")

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        branch_errors = [
            validate_against_schema(value, branch, path, root_schema)
            for branch in one_of
            if isinstance(branch, dict)
        ]
        matching = sum(1 for item in branch_errors if not item)
        if matching != 1:
            errors.append(
                f"{path}: value must satisfy exactly one oneOf branch, matched {matching}"
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
        errors.extend(validate_structure_map(value, path))
    return errors



def _mapping(value: Any) -> dict[str, Any]:
    """Read a container that is expected to be an object, or nothing at all.

    An off-type container is read as empty so the cross-invariants pass over it
    without raising; the type error itself is already reported by the schema.
    """
    return value if isinstance(value, dict) else {}



def _state_invariants(
    data: dict[str, Any],
    *,
    allow_placeholder_hashes: bool = False,
) -> list[str]:
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



def validate_structure_map(value: Any, path: str = "$.structures") -> list[str]:
    """Relational constraints that JSON Schema cannot express by itself.

    Geometry text is authored, not interpreted. Overlap of natural-language
    locations cannot be inferred: structure-specific exceptions name both their target and
    the properties they replace. Global values are never overwritten in place.
    """
    if not isinstance(value, dict) or any(not isinstance(row, dict) for row in value.values()):
        return []  # Structural/type failures are reported by the schema.
    errors: list[str] = []
    parents: dict[str, list[str]] = {}
    overrides: dict[str, list[str]] = {}
    for sid, row in value.items():
        parent = row.get("parent_id")
        parents[sid] = [parent] if isinstance(parent, str) else []
        attachments = row.get("attachment_ids", [])
        attachments = attachments if isinstance(attachments, list) else []
        overrides[sid] = []
        rules = row.get("overrides", [])
        rules = rules if isinstance(rules, list) else []
        seen_rules: set[tuple[str, str]] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            target = rule.get("structure_id")
            if not isinstance(target, str):
                continue
            overrides[sid].append(target)
            properties = rule.get("properties", [])
            for prop in properties if isinstance(properties, list) else []:
                if not isinstance(prop, str):
                    continue
                if (target, prop) in seen_rules:
                    errors.append(f"{path}.{sid}: duplicate override of {target}.{prop}")
                seen_rules.add((target, prop))
                source_geometry = row.get("geometry", {})
                target_geometry = value.get(target, {}).get("geometry", {})
                if not isinstance(source_geometry, dict) or prop not in source_geometry:
                    errors.append(f"{path}.{sid}: override property {prop!r} has no value on this structure")
                if target in value and (not isinstance(target_geometry, dict) or prop not in target_geometry):
                    errors.append(f"{path}.{sid}: override property {prop!r} is not declared by {target}")
        for target in parents[sid] + attachments + overrides[sid]:
            if not isinstance(target, str):
                continue
            if target == sid:
                errors.append(f"{path}.{sid}: self reference is not permitted")
            elif target not in value:
                errors.append(f"{path}.{sid}: unknown structure reference {target!r}")
            elif row.get("presence") in {"present", "partial"} and value[target].get("presence") == "absent":
                errors.append(f"{path}.{sid}: present structure references explicitly absent carrier {target!r}")

    # Parent and override graphs are DAGs. Attachments may legitimately form rings.
    # Use iterative traversal so hostile/deep declarations cannot exhaust recursion.
    for name, graph in (("parent", parents), ("override", overrides)):
        done: set[str] = set()
        active: set[str] = set()
        for start in graph:
            if start in done:
                continue
            stack: list[tuple[str, bool]] = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    active.discard(node)
                    done.add(node)
                    continue
                if node in active:
                    errors.append(f"{path}: cyclic {name} relation at {node!r}")
                    continue
                if node in done or node not in graph:
                    continue
                active.add(node)
                stack.append((node, True))
                stack.extend((target, False) for target in graph[node])
    return errors



EXTERNAL_RIG_MOVES = {"pan", "tilt", "track", "dolly", "crane", "arc", "orbit", "handheld-follow", "locked"}



EMBODIED_MOVES = {"held", "look", "turn", "lean", "crouch", "stand", "walk", "step", "stumble-recover"}



DEVICE_MOVES = {"held", "pan", "tilt", "walk", "step", "handheld-follow", "device-zoom", "locked"}



FIXED_MOVES = {"locked", "mechanical-pan", "mechanical-tilt"}



def _viewpoint_invariants(data: dict[str, Any], *, allow_placeholder_hashes: bool = False) -> list[str]:
    errors: list[str] = []
    kind = artifact_type(data)
    if kind == "viewpoint-profile":
        family = data.get("profile_family")
        owner = data.get("camera_ownership")
        if family == "external" and owner != "external_camera":
            errors.append("external viewpoint profile requires camera_ownership=external_camera")
        if family == "embodied-first-person" and owner != "character_body":
            errors.append("embodied first-person profile requires camera_ownership=character_body")
        if family == "device-first-person" and owner not in {"held_device", "worn_device", "vehicle_or_machine_sensor"}:
            errors.append("device first-person profile requires a device camera owner")
        if family == "fixed-diegetic" and owner != "fixed_diegetic_camera":
            errors.append("fixed diegetic profile requires camera_ownership=fixed_diegetic_camera")

    if kind == "shot-camera-spec":
        family = str(data.get("profile_family"))
        owner = str(data.get("camera_ownership"))
        camera_owner = data.get("camera_owner_character_id")
        movement_type = str((data.get("movement") or {}).get("type") or "")
        if family == "external":
            if owner != "external_camera":
                errors.append("external shot requires external_camera ownership")
            if camera_owner not in (None, ""):
                errors.append("external shot must not assign camera_owner_character_id")
            if movement_type not in EXTERNAL_RIG_MOVES:
                errors.append(f"external shot movement type is unsupported: {movement_type}")
        elif family == "embodied-first-person":
            if owner != "character_body" or not camera_owner:
                errors.append("embodied first-person shot requires a character camera owner")
            if movement_type not in EMBODIED_MOVES:
                errors.append(f"embodied first-person shot uses detached or unsupported movement: {movement_type}")
            if str(camera_owner) in set(data.get("visible_subjects", [])):
                visible_regions = data.get("visible_body_regions", {}).get(str(camera_owner), [])
                if "external full body" in visible_regions:
                    errors.append("embodied first-person shot cannot show the camera owner externally without a separate construction")
        elif family == "device-first-person":
            if owner not in {"held_device", "worn_device", "vehicle_or_machine_sensor"}:
                errors.append("device first-person shot requires device ownership")
            if movement_type not in DEVICE_MOVES:
                errors.append(f"device shot movement type is unsupported: {movement_type}")
        elif family == "fixed-diegetic":
            if owner != "fixed_diegetic_camera":
                errors.append("fixed diegetic shot requires fixed camera ownership")
            if movement_type not in FIXED_MOVES:
                errors.append(f"fixed diegetic shot movement type is unsupported: {movement_type}")
        if data.get("knowledge_scope") == "character_restricted" and not data.get("focal_character_ids"):
            errors.append("character-restricted shot requires at least one focal character")
        if data.get("point_of_audition") == "character_subjective" and not data.get("audition_character_id"):
            errors.append("character-subjective audition requires audition_character_id")

    if kind == "scene-viewpoint-plan":
        shots = data.get("shots", [])
        ids = [str(item.get("shot_id")) for item in shots if isinstance(item, dict)]
        orders = [item.get("order_index") for item in shots if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            errors.append("scene viewpoint plan contains duplicate shot IDs")
        if len(orders) != len(set(orders)):
            errors.append("scene viewpoint plan contains duplicate shot order indices")
        if orders and sorted(orders) != list(range(1, len(orders) + 1)):
            errors.append("shot order indices must form a consecutive sequence starting at 1")

    if kind == "viewpoint-transition":
        if data.get("from_shot") == data.get("to_shot"):
            errors.append("viewpoint transition must connect different shots")
        if data.get("from_profile") != data.get("to_profile") and not data.get("trigger"):
            errors.append("profile change requires a concrete transition trigger")
        # Continuity prose is authored in the work's language. Presence and
        # structure are schema constraints; meaning is not an English keyword test.

    if kind == "shot-continuity-ledger":
        entries = data.get("shot_entries", [])
        ids = [str(item.get("shot_id")) for item in entries if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            errors.append("continuity ledger contains duplicate shot entries")
        prop_states: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for prop_id, owner in (entry.get("prop_ownership") or {}).items():
                if prop_id in prop_states and owner != prop_states[prop_id]:
                    # Ownership may change only when transition requirements call it out.
                    mentioned = any(prop_id in " ".join(map(str, t.get("continuity_requirements", []))) for t in data.get("transition_entries", []) if isinstance(t, dict))
                    if not mentioned:
                        errors.append(f"prop ownership changes without a declared transition requirement: {prop_id}")
                prop_states[prop_id] = str(owner)

    return errors



def validate_cross_invariants(data: dict[str, Any], *, allow_placeholder_hashes: bool = False) -> list[str]:
    errors = _state_invariants(data, allow_placeholder_hashes=allow_placeholder_hashes)
    errors.extend(_viewpoint_invariants(data, allow_placeholder_hashes=allow_placeholder_hashes))
    kind = artifact_type(data)
    if kind == "scene-persona-material":
        from scene_persona import public_errors
        errors.extend(public_errors(data))
    elif kind in {"source-material-index", "source-extraction-proposal"}:
        from source_material import public_errors
        errors.extend(public_errors(data))
    if kind == "state-event" and data.get("supersedes_event_ids"):
        if data.get("event_scope") != "editorial-revision" or data.get("occurrence") != "editorial":
            errors.append("supersedes_event_ids requires an editorial-revision event with occurrence=editorial")
    for k, field, ids in [
        ("candidate-manifest", "candidates", ("candidate_id", "asset_id")),
        ("adoption-receipt", "adoptions", ("candidate_id", "asset_registry_id")),
    ]:
        if kind == k:
            for name in ids:
                values = [row[name] for row in data[field]]
                if len(values) != len(set(values)):
                    errors.append(f"{k}: {name} values must be unique")
    if kind == "scene-context-snapshot":
        if data["story_order_end"] < data["story_order_start"]:
            errors.append("scene-context story_order_end must not precede story_order_start")
        ids = [row["character_id"] for row in data["active_character_snapshots"]]
        if len(ids) != len(set(ids)):
            errors.append("scene-context active character identifiers must be unique")
    if kind == "shot-request":
        fields = ("species_profile_sha256_by_character", "individual_morphology_sha256_by_character", "identity_contract_sha256_by_character", "state_snapshot_sha256_by_character", "visible_morphology_feature_refs_by_character")
        keys = set(data["identity_contract_sha256_by_character"])
        for field in fields:
            if set(data[field]) != keys:
                errors.append(f"{field} keys must match identity bindings")
        if keys and data["deliverable"] != "production-prompt":
            if not data["visible_identity_obligations"]:
                errors.append("visual-media request with characters requires visible_identity_obligations")
            if not any(data["visible_morphology_feature_refs_by_character"].values()):
                errors.append("visual-media request with characters requires visible morphology feature refs")
    return errors


def validate_artifact(data: dict[str, Any], *, allow_placeholder_hashes: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    digest = None
    try:
        if not isinstance(data, dict):
            raise ValueError("public artifact must be an object")
        non_finite = find_non_finite_numbers(data)
        errors.extend(f"{path}: number must be finite" for path in non_finite)
        errors.extend(validate_against_schema(data, schema_for(data)))
        if not errors:
            errors.extend(validate_cross_invariants(data, allow_placeholder_hashes=allow_placeholder_hashes))
        if not non_finite:
            digest = artifact_hash(data)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RecursionError) as exc:
        errors.append(str(exc))
    return {"artifact_type": data.get("artifact_type") if isinstance(data, dict) else None,
            "ok": not errors, "errors": errors, "content_sha256": digest}
