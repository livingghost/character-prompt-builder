#!/usr/bin/env python3
"""Build and verify committed, portable CPB Upscale Packages."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from PIL import Image

from model_contract import validate_model_record
from prepare_generation_references import resolve_model_record
from state_protocol import artifact_hash, finalize_artifact, sha256_json, validate_artifact

IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
SETTING_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_record_sha256(record: Mapping[str, Any]) -> str:
    return sha256_json(dict(record))


def package_id_for(
    *,
    model_id: str,
    source_sha256: str,
    output_sha256: str,
    scale_factor: float,
    settings: Mapping[str, Any],
    guidance_prompt: str | None,
) -> str:
    seed = {
        "model": model_id,
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "scale_factor": float(scale_factor),
        "settings": dict(settings),
        "guidance_prompt": guidance_prompt,
    }
    return "UPK-" + sha256_json(seed)[:16]


def _canonical_stored_path(stored: str) -> str:
    if not isinstance(stored, str) or not stored or "\\" in stored:
        raise ValueError("stored image path must be a non-empty POSIX path")
    pure = PurePosixPath(stored)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("stored image path must be canonical and relative")
    return pure.as_posix()


def _image_metadata(path: Path, *, stored_path: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"image path must not be a symbolic link: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"image path must be a regular file: {resolved}")
    media_type = IMAGE_MEDIA_TYPES.get(resolved.suffix.lower())
    if media_type is None:
        guessed, _encoding = mimetypes.guess_type(resolved.name)
        raise ValueError(f"unsupported image media type {guessed!r}: {resolved}")
    with Image.open(resolved) as image:
        width, height = image.size
        image.verify()
    if width < 1 or height < 1:
        raise ValueError(f"image dimensions are invalid: {resolved}")
    return {
        "path": _canonical_stored_path(stored_path),
        "media_type": media_type,
        "sha256": sha256_file(resolved),
        "dimensions": {"width": int(width), "height": int(height)},
    }


def _resolve_stored_path(stored: str, *, package_root: Path) -> Path:
    canonical = _canonical_stored_path(stored)
    root = package_root.resolve(strict=True)
    candidate = root / Path(canonical)
    cursor = root
    for part in PurePosixPath(canonical).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("stored image path must not traverse a symbolic link")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("stored image path escapes package_root") from exc
    return resolved


def _setting_allowed(value: Any, allowed: list[Any]) -> bool:
    for item in allowed:
        if isinstance(value, bool) or isinstance(item, bool):
            if type(value) is type(item) and value == item:
                return True
            continue
        if isinstance(value, (int, float)) and isinstance(item, (int, float)):
            if float(value) == float(item):
                return True
            continue
        if type(value) is type(item) and value == item:
            return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return any(
            isinstance(item, str) and "numeric" in item.casefold()
            for item in allowed
        )
    return False


def validate_settings(record: Mapping[str, Any], settings: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(settings, Mapping):
        raise ValueError("settings must be an object")
    declared = record.get("upscale_settings")
    if not isinstance(declared, Mapping):
        raise ValueError("upscaler record has no settings contract")
    output: dict[str, Any] = {}
    for name, value in sorted(settings.items()):
        if not isinstance(name, str) or not SETTING_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid upscaler setting name: {name!r}")
        allowed = declared.get(name)
        if not isinstance(allowed, list) or not allowed:
            raise ValueError(f"undeclared upscaler setting: {name}")
        if not isinstance(value, (str, int, float, bool)) or not _setting_allowed(value, allowed):
            raise ValueError(
                f"upscaler setting {name!r} value {value!r} is outside the model contract"
            )
        output[name] = value
    return output


def _enforce_output_limits(
    record: Mapping[str, Any],
    *,
    settings: Mapping[str, Any],
    output_width: int,
    output_height: int,
) -> None:
    limits = record.get("output_limits")
    if not isinstance(limits, Mapping) or not limits:
        return
    max_megapixels: float | None = None
    if isinstance(limits.get("max_output_megapixels"), (int, float)):
        max_megapixels = float(limits["max_output_megapixels"])
    elif "personal_megapixels" in limits or "pro_megapixels" in limits:
        plan = settings.get("plan")
        key = f"{plan}_megapixels" if isinstance(plan, str) else ""
        if not key or key not in limits:
            raise ValueError(
                "the upscaler record has plan-dependent output limits; settings.plan is required"
            )
        max_megapixels = float(limits[key])
    if max_megapixels is not None:
        actual = output_width * output_height / 1_000_000
        if actual > max_megapixels + 1e-9:
            raise ValueError(
                f"output image is {actual:.6f} MP and exceeds the active limit of "
                f"{max_megapixels:g} MP"
            )


def _audit_ready(required: bool, status: str) -> bool:
    return status == "passed" if required else status in {"not-required", "passed"}


def build_upscale_package(
    *,
    model: str,
    source_image: Path,
    output_image: Path,
    package_root: Path,
    source_stored_path: str,
    output_stored_path: str,
    scale_factor: float,
    settings: Mapping[str, Any],
    guidance_prompt: str | None,
    audit_status: str,
    audit_notes: list[str],
) -> dict[str, Any]:
    model_id, record = resolve_model_record(model)
    semantic_errors = validate_model_record(record)
    if semantic_errors:
        raise ValueError("; ".join(semantic_errors))
    if record.get("operation_kind") != "upscale":
        raise ValueError(f"model record {model_id!r} is not an upscaler")
    if record.get("input_image_count") != 1:
        raise ValueError("the current Upscale Package contract supports exactly one source image")
    if isinstance(scale_factor, bool) or not isinstance(scale_factor, (int, float)):
        raise ValueError("scale_factor must be numeric")
    supported = [float(value) for value in record.get("supported_scale_factors") or []]
    if float(scale_factor) not in supported:
        raise ValueError(
            f"scale_factor {scale_factor!r} is not supported by model {model_id!r}: {supported}"
        )
    guidance = None if guidance_prompt is None else guidance_prompt.strip()
    if guidance == "":
        guidance = None
    if guidance and record.get("supports_guidance_prompt") is not True:
        raise ValueError(f"model {model_id!r} does not accept a guidance prompt")
    normalized_settings = validate_settings(record, settings)
    source = _image_metadata(source_image, stored_path=source_stored_path)
    output = _image_metadata(output_image, stored_path=output_stored_path)
    expected_width = round(source["dimensions"]["width"] * float(scale_factor))
    expected_height = round(source["dimensions"]["height"] * float(scale_factor))
    if (
        abs(output["dimensions"]["width"] - expected_width) > 1
        or abs(output["dimensions"]["height"] - expected_height) > 1
    ):
        raise ValueError(
            "output dimensions do not match source dimensions multiplied by scale_factor"
        )
    _enforce_output_limits(
        record,
        settings=normalized_settings,
        output_width=output["dimensions"]["width"],
        output_height=output["dimensions"]["height"],
    )
    audit_required = record.get("upscaler_class") in {"generative", "creative"}
    valid_statuses = (
        {"pending", "passed", "failed"}
        if audit_required
        else {"not-required", "passed", "failed"}
    )
    if audit_status not in valid_statuses:
        raise ValueError(
            f"audit_status {audit_status!r} is invalid for upscaler class "
            f"{record.get('upscaler_class')!r}"
        )
    if any(not isinstance(note, str) or not note.strip() for note in audit_notes):
        raise ValueError("audit notes must be non-empty strings")
    normalized_notes = [note.strip() for note in audit_notes]
    if len(normalized_notes) != len(set(normalized_notes)):
        raise ValueError("audit notes must be unique")
    package_id = package_id_for(
        model_id=model_id,
        source_sha256=source["sha256"],
        output_sha256=output["sha256"],
        scale_factor=float(scale_factor),
        settings=normalized_settings,
        guidance_prompt=guidance,
    )
    value = {
        "artifact_type": "upscale-package",
        "status": "ready" if _audit_ready(audit_required, audit_status) else "review-required",
        "package_id": package_id,
        "upscaler_model": model_id,
        "upscaler_record_sha256": canonical_record_sha256(record),
        "source_image": source,
        "output_image": output,
        "scale_factor": float(scale_factor),
        "settings": normalized_settings,
        "guidance_prompt": guidance,
        "post_upscale_identity_audit": {
            "required": audit_required,
            "status": audit_status,
            "notes": normalized_notes,
        },
        "upscale_package_sha256": "0" * 64,
    }
    result = finalize_artifact(value)
    report = validate_artifact(result)
    if not report.get("ok"):
        raise ValueError("invalid upscale package: " + "; ".join(report.get("errors", [])))
    # Confirm the committed carrier paths identify the exact bytes inspected above.
    source_carrier = _resolve_stored_path(
        result["source_image"]["path"], package_root=package_root
    )
    output_carrier = _resolve_stored_path(
        result["output_image"]["path"], package_root=package_root
    )
    if source_carrier != source_image.resolve(strict=True):
        raise ValueError("source_stored_path does not identify source_image")
    if output_carrier != output_image.resolve(strict=True):
        raise ValueError("output_stored_path does not identify output_image")
    return verify_upscale_package(result, package_root=package_root)


def verify_upscale_package(value: Any, *, package_root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("upscale package must be an object")
    report = validate_artifact(value)
    if not report.get("ok"):
        raise ValueError("invalid upscale package: " + "; ".join(report.get("errors", [])))
    if artifact_hash(value) != value.get("upscale_package_sha256"):
        raise ValueError("upscale_package_sha256 mismatch")
    model_id, record = resolve_model_record(str(value.get("upscaler_model") or ""))
    semantic_errors = validate_model_record(record)
    if semantic_errors:
        raise ValueError("; ".join(semantic_errors))
    if record.get("operation_kind") != "upscale":
        raise ValueError(f"model record {model_id!r} is not an upscaler")
    if record.get("input_image_count") != 1:
        raise ValueError("the committed upscaler no longer has a one-image input contract")
    if canonical_record_sha256(record) != value.get("upscaler_record_sha256"):
        raise ValueError("upscaler record changed after package construction")
    settings = validate_settings(record, value.get("settings") or {})
    source_path = _resolve_stored_path(value["source_image"]["path"], package_root=package_root)
    output_path = _resolve_stored_path(value["output_image"]["path"], package_root=package_root)
    source = _image_metadata(source_path, stored_path=value["source_image"]["path"])
    output = _image_metadata(output_path, stored_path=value["output_image"]["path"])
    if source != value.get("source_image"):
        raise ValueError("source image bytes or metadata changed")
    if output != value.get("output_image"):
        raise ValueError("output image bytes or metadata changed")
    factor = float(value.get("scale_factor"))
    if factor not in [float(item) for item in record.get("supported_scale_factors") or []]:
        raise ValueError("scale_factor is outside the active model contract")
    expected_width = round(source["dimensions"]["width"] * factor)
    expected_height = round(source["dimensions"]["height"] * factor)
    if (
        abs(output["dimensions"]["width"] - expected_width) > 1
        or abs(output["dimensions"]["height"] - expected_height) > 1
    ):
        raise ValueError("committed output dimensions do not match scale_factor")
    _enforce_output_limits(
        record,
        settings=settings,
        output_width=output["dimensions"]["width"],
        output_height=output["dimensions"]["height"],
    )
    guidance = value.get("guidance_prompt")
    if guidance and record.get("supports_guidance_prompt") is not True:
        raise ValueError("guidance prompt is not supported by the active model")
    expected_package_id = package_id_for(
        model_id=model_id,
        source_sha256=source["sha256"],
        output_sha256=output["sha256"],
        scale_factor=factor,
        settings=settings,
        guidance_prompt=guidance,
    )
    if value.get("package_id") != expected_package_id:
        raise ValueError("package_id does not match the committed operation")
    audit = value.get("post_upscale_identity_audit") or {}
    required = record.get("upscaler_class") in {"generative", "creative"}
    if audit.get("required") is not required:
        raise ValueError("identity audit requirement differs from the active model class")
    expected_status = "ready" if _audit_ready(required, str(audit.get("status"))) else "review-required"
    if value.get("status") != expected_status:
        raise ValueError("package readiness differs from the committed identity audit")
    return dict(value)
