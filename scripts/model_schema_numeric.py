"""Enforce provider numeric and pinned media constraints without altering State Protocol.

Media rules consume ordered metadata derived from the actual input bytes.
Unknown operations, nested extensions and missing media evidence remain
unmeasured. A `when.present` guard tests presence rather than truthiness.
"""
from __future__ import annotations
import math
from fractions import Fraction
from typing import Any
from state_protocol import validate_against_schema as _validate
from state_protocol import unsupported_schema_keywords as _unsupported

_MISSING = object()


def _boolean_schema_nodes(schema: Any) -> Any:
    """Project boolean schema nodes to equivalent object schemas for the checker.

    Literal values under const, enum and examples retain their original types.
    Observed schema documents stay unchanged.
    """
    if schema is True:
        return {}
    if schema is False:
        return {"not": {}}
    if not isinstance(schema, dict):
        return schema
    result = dict(schema)
    for key in ("properties", "$defs", "patternProperties", "dependentSchemas"):
        if isinstance(schema.get(key), dict):
            result[key] = {name: _boolean_schema_nodes(node) for name, node in schema[key].items()}
    for key in ("items", "propertyNames", "not", "if", "then", "else", "contains"):
        if key in schema:
            result[key] = _boolean_schema_nodes(schema[key])
    if isinstance(schema.get("additionalProperties"), dict):
        result["additionalProperties"] = _boolean_schema_nodes(schema["additionalProperties"])
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        if isinstance(schema.get(key), list):
            result[key] = [_boolean_schema_nodes(node) for node in schema[key]]
    return result

def _get(value: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value

def _number(value: Any) -> bool:
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))

def _paths(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(p, str) and p and all(p.split(".")) for p in value)

def _guard_valid(rule: dict) -> bool:
    when = rule.get("when")
    return when is None or (
        isinstance(when, dict) and set(when) == {"present"} and _paths(when["present"]))

def _active(rule: Any, value: Any) -> bool:
    # Unknown guards must not cause an unverified rule to disappear.
    if value is _MISSING or not isinstance(rule, dict) or not _guard_valid(rule):
        return True
    paths = (rule.get("when") or {}).get("present", [])
    return all(_get(value, path) is not _MISSING for path in paths)

def _supported(rule: Any) -> bool:
    if not isinstance(rule, dict) or set(rule) - {"operation","parameters","minimum","maximum","when"}:
        return False
    parameters = rule.get("parameters")
    if (rule.get("operation") not in {"area","ratio"} or not _paths(parameters)
            or len(parameters) != 2 or len(set(parameters)) != 2 or not _guard_valid(rule)):
        return False
    bounds = [rule[k] for k in ("minimum","maximum") if k in rule]
    return (bool(bounds) and all(_number(x) for x in bounds)
            and ("minimum" not in rule or "maximum" not in rule or rule["minimum"] <= rule["maximum"]))


def _media_supported(rule: Any) -> bool:
    if not isinstance(rule, dict) or set(rule) - {"operation","parameters","minimum","maximum","when","scope"}:
        return False
    parameters = rule.get("parameters")
    if (rule.get("operation") not in {"fileSize","width","height"}
            or rule.get("scope") != "each" or not _paths(parameters)
            or len(parameters) != 1 or not _guard_valid(rule)):
        return False
    bounds = [rule[k] for k in ("minimum","maximum") if k in rule]
    return (bool(bounds) and all(_number(x) and x >= 0 for x in bounds)
            and ("minimum" not in rule or "maximum" not in rule or rule["minimum"] <= rule["maximum"]))


def _media_check(rule: dict, value: Any, media: Any, where: str) -> tuple[bool, list[str]]:
    """Return whether a media rule is measured and any violations of it.

    The caller binds each dot path to metadata in request-array order. Missing
    evidence stays unmeasured; supplied inconsistent evidence is refused.
    """
    if value is _MISSING:
        return False, []
    parameter = rule["parameters"][0]
    inputs = _get(value, parameter)
    if inputs is _MISSING:
        return True, []  # Optional media is absent; JSON Schema owns requiredness.
    if not isinstance(inputs, list):
        return False, [where + ": media parameter " + parameter + " must be an array"]
    if not inputs and (not isinstance(media, dict) or parameter not in media):
        return True, []
    if media is None or isinstance(media, dict) and parameter not in media:
        return False, []
    if not isinstance(media, dict) or not isinstance(media.get(parameter), list):
        return False, [where + ": media metadata must map " + parameter + " to an ordered array"]
    rows = media[parameter]
    if len(rows) != len(inputs):
        return False, [where + ": media metadata count must match " + parameter + " input count"]
    field = "size" if rule["operation"] == "fileSize" else rule["operation"]
    errors = []
    complete = True
    for index, row in enumerate(rows):
        amount = row.get(field) if isinstance(row, dict) else None
        valid = type(amount) is int and (amount >= 0 if field == "size" else amount > 0)
        item = where + f": {parameter}[{index}]"
        if not valid:
            complete = False
            errors.append(item + ": pinned media metadata needs a valid integer " + field)
            continue
        for key, comparator in (("minimum", lambda a,b: a < b), ("maximum", lambda a,b: a > b)):
            if key in rule and comparator(Fraction(amount), Fraction(str(rule[key]))):
                errors.append(item + f": {rule['operation']} violates {key}={rule[key]}")
    return complete, errors


def unsupported_schema_keywords(schema: Any, path: str = "$", *, value: Any = _MISSING,
                                media: dict | None = None) -> list[str]:
    found = _unsupported(schema, path)
    if not isinstance(schema, dict) or "x-constraints" not in schema:
        return found
    rules = schema["x-constraints"]
    if not isinstance(rules, list):
        return found
    found = [item for item in found if item != path + ".x-constraints"]
    for i, rule in enumerate(rules):
        if not _active(rule, value) or _supported(rule):
            continue
        where = f"{path}.x-constraints[{i}]"
        if _media_supported(rule) and _media_check(rule, value, media, where)[0]:
            continue
        found.append(where)
    return found

def validate_against_schema(value: Any, schema: dict, path: str = "$", *,
                            media: dict | None = None) -> list[str]:
    errors = _validate(value, _boolean_schema_nodes(schema), path)
    rules = schema.get("x-constraints", [])
    if not isinstance(rules, list):
        return errors
    for index, rule in enumerate(rules):
        if not _active(rule, value):
            continue
        where = f"{path}.x-constraints[{index}]"
        if _media_supported(rule):
            errors.extend(_media_check(rule, value, media, where)[1])
            continue
        if not _supported(rule):
            continue
        left, right = [_get(value, key) for key in rule["parameters"]]
        if left is _MISSING or right is _MISSING:
            continue  # Required fields and paired-presence rules belong to JSON Schema.
        if not _number(left) or not _number(right):
            errors.append(where + ": numeric operands must be finite numbers, not booleans")
            continue
        a, b = Fraction(str(left)), Fraction(str(right))
        if rule["operation"] == "ratio":
            if b == 0:
                errors.append(where + ": ratio denominator is zero")
                continue
            result = a / b
        else:
            result = a * b
        for key, comparator in (("minimum", lambda a,b: a < b), ("maximum", lambda a,b: a > b)):
            if key in rule and comparator(result,Fraction(str(rule[key]))):
                errors.append(where + f": {rule['operation']} of {rule['parameters']} violates {key}={rule[key]}")
    return errors
