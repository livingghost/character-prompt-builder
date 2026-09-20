#!/usr/bin/env python3
"""Validate explicit protocol declarations and envelopes without discovering software.

A declaration states supported artifact profiles, not a product identity. Schema
locations are explicitly listed in this distribution's configuration. Received declarations are
ordinary input data. Direction is supplied by the operation and is never inferred
from a name, path, or equality of capability hashes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CAPABILITY_ARTIFACT = "integration-capability-manifest"
ENVELOPE_ARTIFACT = "interchange-envelope"
from io_budget import read_stream


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def content_hash(value: dict[str, Any], self_field: str) -> str:
    return sha256_json({k: v for k, v in value.items() if k != self_field})


def finalize(value: dict[str, Any], self_field: str) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result[self_field] = content_hash(result, self_field)
    return result


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("protocol input must be a regular file")
    with path.open("rb") as handle:
        raw = read_stream(handle)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    def invalid(token):
        raise ValueError("non-finite JSON number: " + token)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("protocol input must be an object")
    return value


def confined_path(root: Path, relative: str) -> Path:
    """Resolve only a declared relative filesystem path; no glob, ancestor or home search."""
    root = root.resolve(strict=True)
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("a nonempty relative path is required")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or relative == ".":
        raise ValueError("path must stay within the declared input directory")
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symbolic links are not protocol inputs")
    if not current.resolve().is_relative_to(root):
        raise ValueError("path escapes the declared input directory")
    return current


def capability_path(root: Path) -> Path:
    layout = read_json(confined_path(root, "config/protocol-layout.json"))
    path = layout.get("capabilities")
    if not isinstance(path, str):
        raise ValueError("protocol path configuration must declare capabilities")
    return confined_path(root, path)


def load_capabilities(root: Path) -> dict[str, Any]:
    return read_json(capability_path(root))


def _shape(value: Any, fields: set[str], where: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(where + " must be an object")
        return False
    if set(value) != fields:
        errors.append(f"{where} fields differ: missing={sorted(fields-set(value))}, unexpected={sorted(set(value)-fields)}")
    return True


def _strings(value: Any, where: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        errors.append(where + " must be an array of nonempty strings")
        return []
    if value != sorted(set(value)):
        errors.append(where + " must be sorted and unique")
    return value


def _hash(value: dict, field: str, errors: list[str], placeholder: bool = False) -> None:
    digest = value.get(field)
    if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        errors.append(field + " must be a lowercase SHA-256")
    elif placeholder and digest == "0" * 64:
        pass
    elif digest != content_hash(value, field):
        errors.append(field + " does not match canonical content")


def profile_hash(row: dict[str, Any]) -> str:
    return content_hash(row, "profile_sha256")


def validate_profile(row: Any, where: str, errors: list[str]) -> None:
    fields = {"profile", "artifact_types", "required_features", "supported_features", "unknown_optional_feature_policy", "unknown_required_feature_policy", "profile_sha256"}
    if not _shape(row, fields, where, errors):
        return
    if not isinstance(row.get("profile"), str) or not row["profile"].strip():
        errors.append(where + ".profile is empty")
    kinds = _strings(row.get("artifact_types"), where + ".artifact_types", errors)
    required = _strings(row.get("required_features"), where + ".required_features", errors)
    supported = _strings(row.get("supported_features"), where + ".supported_features", errors)
    if not kinds:
        errors.append(where + ".artifact_types is empty")
    if not set(required).issubset(supported):
        errors.append(where + ".required_features must be supported")
    if row.get("unknown_required_feature_policy") != "reject":
        errors.append(where + ": unknown required features must be rejected")
    if row.get("unknown_optional_feature_policy") not in {"preserve", "ignore"}:
        errors.append(where + ": invalid optional feature policy")
    _hash(row, "profile_sha256", errors)


def validate_capabilities(value: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not _shape(value, {"artifact_type", "interfaces", "manifest_sha256"}, "capability declaration", errors):
        return {"ok": False, "errors": errors}
    if value.get("artifact_type") != CAPABILITY_ARTIFACT:
        errors.append("invalid capability artifact_type")
    interfaces = value.get("interfaces")
    if _shape(interfaces, {"produces", "consumes"}, "interfaces", errors):
        for direction in ("produces", "consumes"):
            rows = interfaces.get(direction)
            if not isinstance(rows, list):
                errors.append("interfaces." + direction + " must be an array")
                continue
            names = []
            for i, row in enumerate(rows):
                validate_profile(row, f"interfaces.{direction}[{i}]", errors)
                if isinstance(row, dict) and isinstance(row.get("profile"), str):
                    names.append(row["profile"])
            if names != sorted(set(names)):
                errors.append("profile names must be sorted and unique within a direction")
    _hash(value, "manifest_sha256", errors)
    return {"ok": not errors, "errors": errors}


def find_interface(value: dict[str, Any], direction: str, profile: str) -> dict[str, Any] | None:
    for row in value.get("interfaces", {}).get(direction, []):
        if isinstance(row, dict) and row.get("profile") == profile:
            return row
    return None


def envelope_hash(value: dict[str, Any]) -> str:
    return content_hash(value, "envelope_sha256")


PAYLOAD_IDENTIFIERS = {'asset-render-specification': 'render_spec_id', 'candidate-manifest': 'manifest_id', 'character-identity-contract': 'contract_id', 'individual-morphology-contract': 'contract_id', 'prepared-reference-set': 'set_id', 'reference-bundle-plan': 'bundle_id', 'reference-use-plan': 'plan_id', 'shot-request': 'request_id', 'species-morphology-profile': 'profile_id', 'surface-lighting-plan': 'plan_id', 'visual-authority': 'authority_id', 'visual-evidence-bundle': 'bundle_id'}

PAYLOAD_IDENTIFIERS.update({'scene-persona-material': 'material_id', 'source-material-index': 'material_id', 'source-extraction-proposal': 'proposal_id'})

def payload_identity(value: dict[str, Any]) -> str:
    field = PAYLOAD_IDENTIFIERS.get(value.get("artifact_type"))
    if field is None or not isinstance(value.get(field), str) or not value[field]:
        raise ValueError("payload has no identifier in the selected public profile")
    return value[field]


def validate_envelope(value: Any, *, capabilities: dict[str, Any], direction: str,
                      declaration: dict[str, Any] | None = None,
                      payload_root: Path | None = None, allow_placeholder_hash: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    fields = {"artifact_type", "envelope_id", "contract_profile", "profile_sha256", "origin", "payload", "required_features", "optional_features", "extensions", "envelope_sha256"}
    if not _shape(value, fields, "envelope", errors):
        return {"ok": False, "errors": errors}
    errors.extend(validate_capabilities(capabilities)["errors"])
    if errors:
        return {"ok": False, "errors": errors, "payload_verified": False}
    if direction not in {"produces", "consumes"}:
        errors.append("direction must explicitly be produces or consumes")
    if value.get("artifact_type") != ENVELOPE_ARTIFACT:
        errors.append("invalid envelope artifact_type")
    for field in ("envelope_id", "contract_profile"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            errors.append(field + " must be a nonempty string")
    origin = value.get("origin")
    if _shape(origin, {"capability_manifest_sha256"}, "origin", errors):
        if not isinstance(origin.get("capability_manifest_sha256"), str) or not HASH_RE.fullmatch(origin["capability_manifest_sha256"]):
            errors.append("invalid origin capability hash")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        payload = {}
    else:
        required_fields = {"artifact_type", "artifact_id", "media_type", "sha256"}
        if not required_fields.issubset(payload) or set(payload) - required_fields - {"path"}:
            errors.append("payload fields differ from the contract")
        for field in ("artifact_type", "artifact_id", "media_type"):
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                errors.append("payload." + field + " must be a nonempty string")
        if not isinstance(payload.get("sha256"), str) or not HASH_RE.fullmatch(payload["sha256"]):
            errors.append("invalid payload SHA-256")
    if payload.get("media_type") != "application/json":
        errors.append("public profile payloads require application/json")
    required = _strings(value.get("required_features"), "required_features", errors)
    optional = _strings(value.get("optional_features"), "optional_features", errors)
    if set(required) & set(optional):
        errors.append("required and optional features overlap")
    if not isinstance(value.get("extensions"), dict):
        errors.append("extensions must be an object")
    _hash(value, "envelope_sha256", errors, allow_placeholder_hash)
    # Equality of declarations is never evidence of where a document came from.
    author_declaration = capabilities if direction == "produces" else declaration
    if author_declaration is None:
        errors.append("receive requires an explicitly supplied capability declaration")
    else:
        errors.extend(validate_capabilities(author_declaration)["errors"])
        if errors:
            return {"ok": False, "errors": errors, "payload_verified": False}
        emitted = find_interface(author_declaration, "produces", value.get("contract_profile"))
        operation_profile = find_interface(capabilities, direction, value.get("contract_profile"))
        if emitted is None:
            errors.append("declaration does not emit the named profile")
        if operation_profile is None:
            errors.append("configured capability declaration does not support the requested operation/profile")
        if isinstance(origin, dict) and origin.get("capability_manifest_sha256") != author_declaration.get("manifest_sha256"):
            errors.append("origin does not bind the supplied declaration")
        if emitted is not None:
            if value.get("profile_sha256") != emitted["profile_sha256"]:
                errors.append("profile_sha256 does not bind the declared profile")
            if payload.get("artifact_type") not in emitted["artifact_types"]:
                errors.append("payload.artifact_type is not declared by the emitted profile")
            if not set(emitted["required_features"]).issubset(required):
                errors.append("envelope omits mandatory emitted features")
            if not (set(required) | set(optional)).issubset(emitted["supported_features"]):
                errors.append("envelope asserts features not supported by its declaration")
        if operation_profile is not None:
            if payload.get("artifact_type") not in operation_profile["artifact_types"]:
                errors.append("payload.artifact_type is not declared by the selected operation profile")
            missing = set(required) - set(operation_profile["supported_features"])
            if missing:
                errors.append("unsupported required features: " + ", ".join(sorted(missing)))
            if not set(operation_profile["required_features"]).issubset(set(required) | set(optional)):
                errors.append("envelope does not carry the selected operation profile's required features")
    measured = False
    if payload_root is not None:
        try:
            file = confined_path(payload_root, payload.get("path"))
            if not file.is_file():
                raise ValueError("payload.path is not a file")
            with file.open("rb") as handle:
                raw = read_stream(handle)
            if hashlib.sha256(raw).hexdigest() != payload.get("sha256"):
                raise ValueError("payload.sha256 does not match payload bytes")
            if payload.get("media_type") == "application/json":
                import protocol_contract as contract
                data = read_json(file)
                if data.get("artifact_type") != payload.get("artifact_type"):
                    raise ValueError("payload type differs from envelope")
                if payload_identity(data) != payload.get("artifact_id"):
                    raise ValueError("payload identifier differs from envelope")
                report = contract.validate_artifact(data)
                if not report["ok"]:
                    raise ValueError("invalid public payload: " + "; ".join(report["errors"]))
            measured = True
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            errors.append(str(exc))
    return {"ok": not errors, "interface_role": direction, "payload_verified": measured,
            "canonical_adoption": False, "errors": errors}
