#!/usr/bin/env python3
"""Prepare ordered image references for one exact generation target.

Catalog-owned artifacts and caller-supplied files enter through distinct source
variants. The prepared result commits both the selected source bytes and the
actual model-facing transport bytes. SVG sources are safely rasterized from the
same selected artifact; the preparer never substitutes another guide artifact
and never falls back to text-only generation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
import os
import re
import shutil
import struct
import tempfile
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence

from catalog_cli import (
    active_pack_artifact_sources,
    configure_pack_runtime,
    load_pack_catalog,
)
from execution_contract import atomic_write_json, sha256_file
from package_metadata import calver_key
from model_contract import model_reference_limit
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from reference_active_validation import validate_active_reference_use_plan
from reference_contract import state_authority_for, validate_reference_use_plan_contract
from state_protocol import finalize_artifact, parse_json, validate_artifact
from visual_evidence import inspect_svg, render_svg


ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,179}$")
BINDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
UUIDV7_RE = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-7[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$"
)
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MEDIA_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")

DIRECT_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
SVG_MEDIA_TYPE = "image/svg+xml"
PNG_MEDIA_TYPE = "image/png"
SVG_RENDERER = "resvg-py"

PACK_SOURCE_FIELDS = frozenset(
    {
        "kind",
        "pack_id",
        "asset_id",
        "artifact_id",
        "resolved_path",
        "media_type",
        "sha256",
    }
)
SUPPLIED_SELECTION_FIELDS = frozenset({"kind", "reference_id", "resolved_path"})
SUPPLIED_SOURCE_FIELDS = frozenset(
    {"kind", "reference_id", "resolved_path", "media_type", "sha256"}
)
TRANSPORT_FIELDS = frozenset({"resolved_path", "media_type", "sha256", "derivation"})
DIRECT_DERIVATION_FIELDS = frozenset({"mode"})
SVG_DERIVATION_FIELDS = frozenset(
    {
        "mode",
        "renderer_id",
        "renderer_release",
        "source_sha256",
        "output_dimensions",
        "max_side",
    }
)
PREPARED_REFERENCE_SET_FIELDS = frozenset(
    {
        "artifact_type",
        "set_id",
        "transport_mode",
        "target_model",
        "reference_selection",
        "reference_selection_sha256",
        "reference_use_plan",
        "reference_use_plan_sha256",
        "surface_lighting_plan_sha256",
        "zero_reference_reason",
        "reference_preamble",
        "prompt_artifacts",
        "selected_references",
        "single_board",
        "prepared_reference_set_sha256",
    }
)
GENERIC_PREPARED_REFERENCE_FIELDS = frozenset(
    {"role", "source", "transport", "authority"}
)
STATE_SCOPE_FIELDS = (
    "binding_id",
    "covers",
    "intended_influence",
    "review_dimensions",
    "unsupported_or_occluded_state",
    "unsupported_assumptions",
)
STATE_PREPARED_REFERENCE_FIELDS = frozenset(
    {"role", "source", "transport", "authority", *STATE_SCOPE_FIELDS}
)
AUTHORITY_FIELDS = frozenset({"controls", "must_not_control"})
PROMPT_ARTIFACT_FIELDS = frozenset(
    {"semantic_role", "source_sha256", "delivered_path", "media_type", "delivered_sha256"}
)
SINGLE_BOARD_FIELDS = frozenset({"resolved_path", "media_type", "sha256", "panels"})
SINGLE_BOARD_PANEL_FIELDS = frozenset(
    {"semantic_role", "source_sha256", "transport_sha256", "box"}
)
SINGLE_BOARD_BOX_FIELDS = frozenset({"x", "y", "width", "height"})
REFERENCE_TRANSPORT_MODES = frozenset(
    {"none", "prompt-artifacts", "multi-image", "single-board", "svg-bundle"}
)
ZERO_REFERENCE_CODES = frozenset(
    {
        "no-canonical-record-selected",
        "no-suitable-active-asset",
        "user-declined-visual-references",
        "state-ineligible",
    }
)

_MODEL_CACHE: tuple[str, dict[str, dict[str, Any]]] | None = None


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _require_exact_fields(value: Mapping[str, Any], expected: frozenset[str], field: str) -> None:
    actual = set(value)
    if actual == set(expected):
        return
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    details: list[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unexpected " + ", ".join(extra))
    raise ValueError(f"{field} has an invalid shape ({'; '.join(details)})")


def _require_string(value: Any, field: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        raise ValueError(f"{field} has an invalid format")
    return value


def _require_sha256(value: Any, field: str) -> str:
    digest = _require_string(value, field, SHA256_RE)
    if digest == "0" * 64:
        raise ValueError(f"{field} must be a nonzero SHA-256")
    return digest


def _canonical_existing_file(value: Any, field: str, *, require_canonical: bool) -> Path:
    raw = _require_string(value, field)
    supplied = Path(raw)
    if not supplied.is_absolute():
        raise ValueError(f"{field} must be an absolute path")
    resolved = supplied.resolve(strict=True)
    if require_canonical and str(resolved) != raw:
        raise ValueError(f"{field} is not canonical")
    if not resolved.is_file():
        raise ValueError(f"{field} is not a file: {resolved}")
    return resolved


def _resolve_packaged_file(
    value: Any,
    field: str,
    *,
    package_root: Path | None,
) -> tuple[str, Path]:
    """Resolve an absolute path or a package-relative path without changing its commitment."""

    raw = _require_string(value, field)
    supplied = Path(raw)
    if supplied.is_absolute():
        resolved = supplied.resolve(strict=True)
    else:
        if package_root is None:
            raise ValueError(f"{field} is relative and requires package_root")
        base = Path(package_root).resolve(strict=True)
        if not base.is_dir():
            raise ValueError(f"package_root is not a directory: {base}")
        resolved = (base / supplied).resolve(strict=True)
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"{field} escapes package_root") from exc
    if not resolved.is_file():
        raise ValueError(f"{field} is not a file: {resolved}")
    return raw, resolved


def detect_image_media_type(path: Path) -> str:
    with Path(path).open("rb") as stream:
        prefix = stream.read(4096)
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp"
    lower = prefix.lower().lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
    if b"<svg" in lower or re.search(br"<[a-z0-9_.-]+:svg(?:[\s>])", lower):
        return SVG_MEDIA_TYPE
    raise ValueError(f"Unsupported or unrecognized image bytes: {path}")


def _png_dimensions(path: Path) -> tuple[int, int]:
    with Path(path).open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or not header.startswith(b"\x89PNG\r\n\x1a\n") or header[12:16] != b"IHDR":
        raise ValueError(f"Invalid PNG transport: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        raise ValueError(f"PNG transport has invalid dimensions: {path}")
    return width, height


def _jpeg_dimensions(path: Path) -> tuple[int, int]:
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    with Path(path).open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            raise ValueError(f"Invalid JPEG transport: {path}")
        while True:
            byte = stream.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            while byte == b"\xff":
                byte = stream.read(1)
            if not byte:
                break
            marker = byte[0]
            if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            raw_length = stream.read(2)
            if len(raw_length) != 2:
                break
            length = struct.unpack(">H", raw_length)[0]
            if length < 2:
                break
            if marker in sof_markers:
                payload = stream.read(5)
                if len(payload) != 5:
                    break
                height, width = struct.unpack(">HH", payload[1:5])
                if width > 0 and height > 0:
                    return width, height
                break
            stream.seek(length - 2, 1)
    raise ValueError(f"JPEG dimensions are unavailable: {path}")


def _webp_dimensions(path: Path) -> tuple[int, int]:
    with Path(path).open("rb") as stream:
        data = stream.read(32)
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError(f"Invalid WebP transport: {path}")
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        b0, b1, b2, b3 = data[21:25]
        width = 1 + b0 + ((b1 & 0x3F) << 8)
        height = 1 + (b1 >> 6) + (b2 << 2) + ((b3 & 0x0F) << 10)
        return width, height
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        if width and height:
            return width, height
    raise ValueError(f"WebP dimensions are unavailable: {path}")


def image_dimensions(path: Path, media_type: str) -> tuple[int, int]:
    if media_type == "image/png":
        return _png_dimensions(path)
    if media_type == "image/jpeg":
        return _jpeg_dimensions(path)
    if media_type == "image/webp":
        return _webp_dimensions(path)
    raise ValueError(f"Dimensions are not supported for media type {media_type!r}")


def _numeric_svg_length(value: str) -> float | None:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*", value)
    if not match:
        return None
    number = float(match.group(1))
    return number if math.isfinite(number) and number > 0 else None


def svg_dimensions(path: Path) -> tuple[int, int]:
    try:
        root = ET.fromstring(Path(path).read_bytes())
    except ET.ParseError as exc:
        raise ValueError(f"SVG XML is invalid: {path}: {exc}") from exc
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        raise ValueError(f"SVG root element is invalid: {path}")
    width = _numeric_svg_length(str(root.attrib.get("width") or ""))
    height = _numeric_svg_length(str(root.attrib.get("height") or ""))
    if width is None or height is None:
        parts = str(root.attrib.get("viewBox") or "").replace(",", " ").split()
        if len(parts) != 4:
            raise ValueError(f"SVG has no concrete width/height or valid viewBox: {path}")
        try:
            _x, _y, width, height = (float(value) for value in parts)
        except ValueError as exc:
            raise ValueError(f"SVG viewBox is invalid: {path}") from exc
        if not all(math.isfinite(value) for value in (width, height)) or width <= 0 or height <= 0:
            raise ValueError(f"SVG viewBox dimensions are invalid: {path}")
    return max(1, round(width)), max(1, round(height))


def raster_dimensions_for_max_side(path: Path, max_side: int) -> tuple[int, int]:
    width, height = svg_dimensions(path)
    scale = min(1.0, max_side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def normalize_model_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _model_records() -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    """Every enabled model record by id, and the root of the pack each came from."""
    global _MODEL_CACHE
    catalog = load_pack_catalog()
    if _MODEL_CACHE is None or _MODEL_CACHE[0] != catalog.fingerprint:
        records: dict[str, dict[str, Any]] = {}
        roots: dict[str, Path] = {}
        for entry in catalog.entries:
            if entry.kind == "model" and entry.record.get("id"):
                records[str(entry.record["id"])] = dict(entry.record)
                roots[str(entry.record["id"])] = Path(entry.source_root)
        if not records:
            raise ValueError("Enabled packs must provide at least one model record")
        _MODEL_CACHE = (catalog.fingerprint, records, roots)
    return _MODEL_CACHE[1], _MODEL_CACHE[2]


def model_pack_root(model_id: str) -> Path | None:
    """The root of the pack that holds a resolved model record, for files the record points at."""
    _records, roots = _model_records()
    return roots.get(model_id)


def resolve_model_record(model: str) -> tuple[str, dict[str, Any]]:
    records, _roots = _model_records()
    raw = _require_string(model, "model").strip()
    if raw in records:
        return raw, records[raw]
    wanted = normalize_model_name(raw)
    matches: list[tuple[str, dict[str, Any]]] = []
    for model_id, record in records.items():
        names = [model_id, str(record.get("label") or "")]
        aliases = record.get("aliases") or []
        if not isinstance(aliases, list):
            raise ValueError(f"model record {model_id!r} aliases must be an array")
        names.extend(str(value) for value in aliases)
        if wanted and wanted in {normalize_model_name(value) for value in names if value}:
            matches.append((model_id, record))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous model name {model!r}; use one canonical model ID: "
            + ", ".join(sorted(model_id for model_id, _record in matches))
        )
    raise ValueError(f"unknown model {model!r}; use a model record from an enabled pack")


def model_reference_media_types(model: str, *, required: bool) -> frozenset[str]:
    model_id, record = resolve_model_record(model)
    raw = record.get("reference_input_media_types")
    if raw is None:
        if required:
            raise ValueError(
                f"model record {model_id!r} does not declare reference_input_media_types"
            )
        return frozenset()
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(value, str) or not MEDIA_TYPE_RE.fullmatch(value) for value in raw)
        or len(set(raw)) != len(raw)
    ):
        raise ValueError(
            f"model record {model_id!r} has invalid reference_input_media_types"
        )
    return frozenset(raw)


@dataclass(frozen=True)
class _ReferenceContext:
    active: bool = True
    source_archive: Path | None = None

    def path(self, source: Mapping[str, Any], field: str) -> Path:
        declared = _require_string(source.get('resolved_path'), field + '.resolved_path')
        if self.active:
            return _canonical_existing_file(declared, field + '.resolved_path', require_canonical=True)
        digest = _require_sha256(source.get('sha256'), field + '.sha256')
        if self.source_archive is not None:
            import execution_contract as execution
            archived = execution.local(self.source_archive, digest, exists=False)
            if archived.is_file():
                if sha256_file(archived) != digest:
                    raise ValueError(field + ' archived source byte hash mismatch')
                return archived
        # An unchanged original can also supply the recorded byte evidence.
        # Active catalog membership and ownership are not consulted here.
        path = _canonical_existing_file(declared, field + '.resolved_path', require_canonical=True)
        if sha256_file(path) != digest:
            raise ValueError(field + ' needs the original recorded source bytes')
        return path


_LIVE_REFERENCES = _ReferenceContext()


def _validate_pack_source(source: Mapping[str, Any], field: str, *, context: _ReferenceContext = _LIVE_REFERENCES) -> dict[str, Any]:
    _require_exact_fields(source, PACK_SOURCE_FIELDS, field)
    canonical: dict[str, Any] = {
        "kind": "pack-artifact",
        "pack_id": _require_string(source.get("pack_id"), f"{field}.pack_id", UUIDV7_RE),
        "asset_id": _require_string(source.get("asset_id"), f"{field}.asset_id", IDENTIFIER_RE),
        "artifact_id": _require_string(
            source.get("artifact_id"), f"{field}.artifact_id", IDENTIFIER_RE
        ),
        "resolved_path": _require_string(source.get("resolved_path"), f"{field}.resolved_path"),
        "media_type": _require_string(
            source.get("media_type"), f"{field}.media_type", MEDIA_TYPE_RE
        ),
        "sha256": _require_sha256(source.get("sha256"), f"{field}.sha256"),
    }
    if source.get("kind") != "pack-artifact":
        raise ValueError(f"{field}.kind must be pack-artifact")
    path = context.path(canonical, field)
    if context.active:
        expected = active_pack_artifact_sources().get(
            (canonical["pack_id"], canonical["asset_id"], canonical["artifact_id"])
        )
        if expected is None:
            raise ValueError(f"{field} does not identify an active pack artifact")
        if canonical != expected:
            raise ValueError(f"{field} differs from its active pack artifact declaration")
    actual_hash = sha256_file(path)
    if actual_hash != canonical["sha256"]:
        raise ValueError(f"{field} source byte hash mismatch")
    actual_media = detect_image_media_type(path)
    if actual_media != canonical["media_type"]:
        raise ValueError(f"{field} source media type differs from its file bytes")
    return canonical


def _prepare_supplied_source(source: Mapping[str, Any], field: str) -> dict[str, Any]:
    _require_exact_fields(source, SUPPLIED_SELECTION_FIELDS, field)
    if source.get("kind") != "supplied-file":
        raise ValueError(f"{field}.kind must be supplied-file")
    reference_id = _require_string(
        source.get("reference_id"), f"{field}.reference_id", IDENTIFIER_RE
    )
    path = _canonical_existing_file(
        source.get("resolved_path"), f"{field}.resolved_path", require_canonical=False
    )
    media_type = detect_image_media_type(path)
    return {
        "kind": "supplied-file",
        "reference_id": reference_id,
        "resolved_path": str(path),
        "media_type": media_type,
        "sha256": sha256_file(path),
    }


def _validate_supplied_source(source: Mapping[str, Any], field: str, *, context: _ReferenceContext = _LIVE_REFERENCES) -> dict[str, Any]:
    _require_exact_fields(source, SUPPLIED_SOURCE_FIELDS, field)
    if source.get("kind") != "supplied-file":
        raise ValueError(f"{field}.kind must be supplied-file")
    canonical = {
        "kind": "supplied-file",
        "reference_id": _require_string(
            source.get("reference_id"), f"{field}.reference_id", IDENTIFIER_RE
        ),
        "resolved_path": _require_string(source.get("resolved_path"), f"{field}.resolved_path"),
        "media_type": _require_string(
            source.get("media_type"), f"{field}.media_type", MEDIA_TYPE_RE
        ),
        "sha256": _require_sha256(source.get("sha256"), f"{field}.sha256"),
    }
    path = context.path(canonical, field)
    if sha256_file(path) != canonical["sha256"]:
        raise ValueError(f"{field} source byte hash mismatch")
    if detect_image_media_type(path) != canonical["media_type"]:
        raise ValueError(f"{field} source media type differs from its file bytes")
    return canonical


def _validate_source(source: Any, field: str, *, context: _ReferenceContext = _LIVE_REFERENCES) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        raise ValueError(f"{field} must be an object")
    kind = source.get("kind")
    if kind == "pack-artifact":
        return _validate_pack_source(source, field, context=context)
    if kind == "supplied-file":
        return _validate_supplied_source(source, field, context=context)
    raise ValueError(f"{field}.kind must be pack-artifact or supplied-file")


def validate_committed_source(source: Any, field: str = "source") -> dict[str, Any]:
    """Validate one fully committed source against its current authoritative bytes."""

    return _validate_source(source, field)


def _validate_transport(
    transport: Any,
    source: Mapping[str, Any],
    field: str,
    *,
    package_root: Path | None,
    context: _ReferenceContext = _LIVE_REFERENCES,
) -> dict[str, Any]:
    if not isinstance(transport, Mapping):
        raise ValueError(f"{field} must be an object")
    _require_exact_fields(transport, TRANSPORT_FIELDS, field)
    stored_path, path = _resolve_packaged_file(
        transport.get("resolved_path"),
        f"{field}.resolved_path",
        package_root=package_root,
    )
    media_type = _require_string(
        transport.get("media_type"), f"{field}.media_type", MEDIA_TYPE_RE
    )
    digest = _require_sha256(transport.get("sha256"), f"{field}.sha256")
    if sha256_file(path) != digest:
        raise ValueError(f"{field} byte hash mismatch")
    if detect_image_media_type(path) != media_type:
        raise ValueError(f"{field} media type differs from its file bytes")
    derivation = transport.get("derivation")
    if not isinstance(derivation, Mapping):
        raise ValueError(f"{field}.derivation must be an object")
    mode = derivation.get("mode")
    if mode == "direct":
        _require_exact_fields(derivation, DIRECT_DERIVATION_FIELDS, f"{field}.derivation")
        if media_type not in DIRECT_MEDIA_TYPES:
            raise ValueError(f"{field} direct media type is unsupported")
        if (
            media_type != source["media_type"]
            or digest != source["sha256"]
        ):
            raise ValueError(f"{field} direct transport differs from its source bytes")
        image_dimensions(path, media_type)
        normalized_derivation: dict[str, Any] = {"mode": "direct"}
    elif mode == "svg-rasterization":
        _require_exact_fields(derivation, SVG_DERIVATION_FIELDS, f"{field}.derivation")
        if source["media_type"] != SVG_MEDIA_TYPE:
            raise ValueError(f"{field} svg-rasterization source is not SVG")
        source_path = context.path(source, field + ".source")
        source_digest, svg_errors = inspect_svg(source_path, require_path_element=False)
        if svg_errors:
            raise ValueError("SVG source is unsafe: " + "; ".join(svg_errors))
        if source_digest != source["sha256"]:
            raise ValueError(f"{field} SVG inspection hash differs from source hash")
        if media_type != PNG_MEDIA_TYPE:
            raise ValueError(f"{field} svg-rasterization transport must be image/png")
        if _require_string(
            derivation.get("renderer_id"), f"{field}.derivation.renderer_id", IDENTIFIER_RE
        ) != SVG_RENDERER:
            raise ValueError(f"{field}.derivation.renderer_id must be {SVG_RENDERER}")
        renderer_release = _require_string(
            derivation.get("renderer_release"), f"{field}.derivation.renderer_release"
        )
        if context.active:
            try:
                installed_renderer_release = importlib.metadata.version(SVG_RENDERER)
            except importlib.metadata.PackageNotFoundError as exc:
                raise RuntimeError(
                    f"{SVG_RENDERER} is required to verify SVG-derived references; "
                    "install requirements-visual.txt"
                ) from exc
            if renderer_release != installed_renderer_release:
                raise ValueError(
                    f"{field}.derivation.renderer_release differs from the installed {SVG_RENDERER} release"
                )
        if _require_sha256(
            derivation.get("source_sha256"), f"{field}.derivation.source_sha256"
        ) != source["sha256"]:
            raise ValueError(f"{field}.derivation.source_sha256 mismatch")
        dimensions = derivation.get("output_dimensions")
        if not isinstance(dimensions, Mapping):
            raise ValueError(f"{field}.derivation.output_dimensions must be an object")
        _require_exact_fields(
            dimensions, frozenset({"width", "height"}), f"{field}.derivation.output_dimensions"
        )
        width = dimensions.get("width")
        height = dimensions.get("height")
        max_side = derivation.get("max_side")
        if (
            not isinstance(width, int) or isinstance(width, bool) or width < 1
            or not isinstance(height, int) or isinstance(height, bool) or height < 1
            or not isinstance(max_side, int) or isinstance(max_side, bool) or max_side < 1
        ):
            raise ValueError(f"{field} raster dimensions and max_side must be positive integers")
        if max(width, height) > max_side:
            raise ValueError(f"{field} raster dimensions exceed max_side")
        expected_dimensions = raster_dimensions_for_max_side(
            source_path, max_side
        )
        if (width, height) != expected_dimensions:
            raise ValueError(
                f"{field} raster dimensions differ from the deterministic max_side derivation"
            )
        if image_dimensions(path, media_type) != (width, height):
            raise ValueError(f"{field} raster dimensions differ from PNG bytes")
        if context.active:
            with tempfile.TemporaryDirectory(prefix="cpb-verify-svg-raster-") as temporary:
                recomputed_path = Path(temporary) / "recomputed.png"
                render_svg(
                    source_path,
                    recomputed_path,
                    width=width,
                    height=height,
                )
                if recomputed_path.read_bytes() != path.read_bytes():
                    raise ValueError(
                        f"{field} PNG bytes do not match deterministic SVG rasterization"
                    )
        normalized_derivation = {
            "mode": "svg-rasterization",
            "renderer_id": SVG_RENDERER,
            "renderer_release": renderer_release,
            "source_sha256": source["sha256"],
            "output_dimensions": {"width": width, "height": height},
            "max_side": max_side,
        }
    else:
        raise ValueError(f"{field}.derivation.mode must be direct or svg-rasterization")
    return {
        "resolved_path": stored_path,
        "media_type": media_type,
        "sha256": digest,
        "derivation": normalized_derivation,
    }


def _validate_non_empty_string_set(
    value: Any,
    field: str,
    *,
    require_non_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicates")
    if require_non_empty and not value:
        raise ValueError(f"{field} must not be empty")
    return list(value)


def _validate_authority(value: Any, field: str) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    _require_exact_fields(value, AUTHORITY_FIELDS, field)
    authority = {
        "controls": _validate_non_empty_string_set(
            value.get("controls"), f"{field}.controls", require_non_empty=True
        ),
        "must_not_control": _validate_non_empty_string_set(
            value.get("must_not_control"),
            f"{field}.must_not_control",
            require_non_empty=True,
        ),
    }
    from reference_delivery import validate_authority_scope
    validate_authority_scope(authority)
    return authority


def conservative_authority(
    role: str,
    *,
    intended_influence: Sequence[str] = (),
    unsupported_or_occluded_state: Sequence[str] = (),
    unsupported_assumptions: Sequence[str] = (),
) -> dict[str, list[str]]:
    """Return the narrow authority used when no Reference Use Plan is supplied."""

    controls = [str(value) for value in intended_influence if str(value)]
    if not controls:
        controls = [f"only the evidence explicitly named by the {role} role"]
    exclusions = [
        *(str(value) for value in unsupported_or_occluded_state if str(value)),
        *(str(value) for value in unsupported_assumptions if str(value)),
        "any identity, state, pose, camera, environment, lighting, material, color, or style "
        "attribute outside the declared role",
    ]
    return {
        "controls": list(dict.fromkeys(controls)),
        "must_not_control": list(dict.fromkeys(exclusions)),
    }


def _reference_preamble_for_plan(plan: Mapping[str, Any]) -> str:
    lines = [
        "Use the following references only for their declared roles and precedence.",
        "Do not average identities, scenes, materials, colors, or lighting across unnamed roles.",
    ]
    for item in plan.get("reference_items", []):
        lines.append(
            f"Reference {int(item['precedence']) + 1} ({item['semantic_role']}): "
            f"{item['preamble']}"
        )
    surface = plan["surface_lighting_plan"]
    lines.append(
        "Surface and lighting mode: " + surface["source_lighting_mode"] + ". "
        "The surface-lighting plan, not the specular mask alone, controls "
        "shadow topology, material response, and highlight behavior."
    )
    return "\n".join(lines) + "\n"


def canonical_reference_preamble(
    *,
    transport_mode: str,
    selected_references: Sequence[Mapping[str, Any]],
    reference_use_plan: Mapping[str, Any] | None,
    single_board: Mapping[str, Any] | None = None,
) -> str:
    """Derive instructions from committed authority and actual delivery positions."""

    if transport_mode == "none":
        return ""
    from reference_delivery import instructions
    base = (_reference_preamble_for_plan(reference_use_plan) if reference_use_plan is not None
            else _reference_preamble_for_prepared_rows(selected_references))
    return base + instructions(transport_mode, selected_references, single_board)


def _validated_reference_use_plan(value: Any, *, context: _ReferenceContext = _LIVE_REFERENCES) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("artifact_type") != "reference-use-plan":
        raise ValueError("reference_use_plan must be a reference-use-plan artifact")
    report = validate_artifact(value)
    if not report.get("ok"):
        raise ValueError("invalid reference-use-plan artifact: " + "; ".join(report["errors"]))
    nested = value.get("surface_lighting_plan")
    if not isinstance(nested, dict) or nested.get("artifact_type") != "surface-lighting-plan":
        raise ValueError("reference_use_plan has no surface-lighting-plan artifact")
    nested_report = validate_artifact(nested)
    if not nested_report.get("ok"):
        raise ValueError(
            "invalid embedded surface-lighting-plan artifact: "
            + "; ".join(nested_report["errors"])
        )
    if value.get("surface_lighting_plan_sha256") != nested.get(
        "surface_lighting_plan_sha256"
    ):
        raise ValueError(
            "reference_use_plan.surface_lighting_plan_sha256 does not match the embedded plan"
        )
    contract_report = validate_reference_use_plan_contract(value)
    if not contract_report.get("ok"):
        raise ValueError(
            "invalid reference-use-plan contract: "
            + "; ".join(contract_report.get("errors", []))
        )
    if context.active:
        active_report = validate_active_reference_use_plan(value)
        if not active_report.get("ok"):
            raise ValueError(
                "invalid active reference-use-plan: "
                + "; ".join(active_report.get("errors", []))
            )
    for index, item in enumerate(value.get("reference_items", [])):
        source = _validate_source(item.get("source"), f"reference_items[{index}].source", context=context)
        if source != item.get("source"):
            raise ValueError(f"reference_items[{index}].source is not canonical")
    return copy.deepcopy(value)


def _validate_zero_reference_reason(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    _require_exact_fields(value, frozenset({"code", "record_ids", "detail"}), field)
    code = _require_string(value.get("code"), f"{field}.code")
    if code not in ZERO_REFERENCE_CODES:
        raise ValueError(f"{field}.code is unsupported")
    record_ids = _validate_non_empty_string_set(value.get("record_ids"), f"{field}.record_ids")
    if code == "no-canonical-record-selected" and record_ids:
        raise ValueError(f"{field}.record_ids must be empty when no canonical record was selected")
    if code != "no-canonical-record-selected" and not record_ids:
        raise ValueError(f"{field}.record_ids must identify the affected canonical records")
    detail = _require_string(value.get("detail"), f"{field}.detail")
    return {"code": code, "record_ids": record_ids, "detail": detail}


def _validated_reference_selection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("artifact_type") != "reference-selection":
        raise ValueError("reference_selection must be a reference-selection artifact")
    from state_protocol import validate_artifact

    report = validate_artifact(value)
    if not report.get("ok"):
        raise ValueError("invalid reference-selection artifact: " + "; ".join(report["errors"]))
    unresolved = value.get("unresolved_requirements")
    if unresolved:
        raise ValueError(
            "reference-selection has unresolved requirements and cannot be prepared: "
            + ", ".join(str(item) for item in unresolved)
        )
    return copy.deepcopy(value)


def validate_prepared_references(value: Any, *, model: str,
                                 reference_selection: dict[str, Any] | None = None,
                                 reference_use_plan: dict[str, Any] | None = None,
                                 package_root: Path | None = None) -> list[dict[str, Any]]:
    return _validate_prepared_references(value, model=model,
        reference_selection=reference_selection, reference_use_plan=reference_use_plan,
        package_root=package_root)


def _validate_prepared_references(
    value: Any,
    *,
    model: str,
    reference_selection: dict[str, Any] | None = None,
    reference_use_plan: dict[str, Any] | None = None,
    package_root: Path | None = None,
    context: _ReferenceContext = _LIVE_REFERENCES,
) -> list[dict[str, Any]]:
    """Validate every prepared byte, authority, and optional state/plan scope."""

    if not isinstance(value, list):
        raise ValueError("selected_references must be a JSON array")
    selection_rows: list[Any] | None = None
    plan_items: list[Any] | None = None
    expected_state_rows: list[dict[str, Any]] | None = None
    if reference_selection is not None:
        selection = _validated_reference_selection(reference_selection)
        selection_rows = selection["selected_references"]
    if reference_use_plan is not None:
        plan = _validated_reference_use_plan(reference_use_plan, context=context)
        plan_items = plan["reference_items"]
        if len(value) != len(plan_items):
            raise ValueError(
                "selected_references length must exactly match reference_use_plan order"
            )
        if selection_rows is not None:
            available: dict[str, list[dict[str, Any]]] = {}
            for selected in selection_rows:
                if not isinstance(selected, dict):
                    raise ValueError("reference_selection selected reference must be an object")
                available.setdefault(canonical_json(selected.get("source")), []).append(selected)
            expected_state_rows = []
            for index, item in enumerate(plan_items):
                if not isinstance(item, dict):
                    raise ValueError(f"reference_use_plan.reference_items[{index}] must be an object")
                matches = available.get(canonical_json(item.get("source"))) or []
                influence = item.get("intended_influence")
                match_index = next(
                    (
                        candidate_index
                        for candidate_index, candidate in enumerate(matches)
                        if influence in candidate.get("intended_influence", [])
                    ),
                    None,
                )
                if match_index is None:
                    raise ValueError(
                        f"reference_use_plan.reference_items[{index}] source and intended "
                        "influence are not eligible in reference_selection"
                    )
                expected_state_rows.append(matches.pop(match_index))
    elif selection_rows is not None:
        if len(value) != len(selection_rows):
            raise ValueError(
                "selected_references length must exactly match reference_selection order"
            )
        expected_state_rows = selection_rows
    allowed_media = (
        model_reference_media_types(model, required=True) if value and context.active else frozenset()
    )
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        field = f"selected_references[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{field} must be an object")
        expected_fields = (
            STATE_PREPARED_REFERENCE_FIELDS
            if selection_rows is not None
            else GENERIC_PREPARED_REFERENCE_FIELDS
        )
        _require_exact_fields(raw, expected_fields, field)
        role = _require_string(raw.get("role"), f"{field}.role", ROLE_RE)
        source = _validate_source(raw.get("source"), f"{field}.source", context=context)
        transport = _validate_transport(
            raw.get("transport"),
            source,
            f"{field}.transport",
            package_root=package_root, context=context,
        )
        authority = _validate_authority(raw.get("authority"), f"{field}.authority")
        if context.active and transport["media_type"] not in allowed_media:
            raise ValueError(
                f"{field} transport media type {transport['media_type']!r} is not declared "
                f"by model {model!r}"
            )
        normalized: dict[str, Any] = {
            "role": role,
            "source": source,
            "transport": transport,
            "authority": authority,
        }
        if selection_rows is not None:
            assert expected_state_rows is not None
            expected = expected_state_rows[index]
            if not isinstance(expected, dict):
                raise ValueError(
                    f"reference_selection.selected_references[{index}] must be an object"
                )
            normalized["binding_id"] = _require_string(
                raw.get("binding_id"), f"{field}.binding_id", BINDING_ID_RE
            )
            for scope_field in STATE_SCOPE_FIELDS[1:]:
                normalized[scope_field] = _validate_non_empty_string_set(
                    raw.get(scope_field),
                    f"{field}.{scope_field}",
                    require_non_empty=(scope_field == "intended_influence"),
                )
            projected = {
                "binding_id": expected.get("binding_id"),
                "role": expected.get("role"),
                "source": expected.get("source"),
                "covers": expected.get("covers"),
                "intended_influence": expected.get("intended_influence"),
                "review_dimensions": expected.get("review_dimensions"),
                "unsupported_or_occluded_state": expected.get(
                    "unsupported_or_occluded_state"
                ),
                "unsupported_assumptions": expected.get("unsupported_assumptions"),
            }
            actual_projection = {
                key: normalized[key]
                for key in projected
            }
            if actual_projection != projected:
                raise ValueError(
                    f"{field} is not the exact ordered scope projection of "
                    "reference_selection"
                )
        if plan_items is not None:
            plan_item = plan_items[index]
            expected_role = (
                str(expected_state_rows[index].get("role"))
                if expected_state_rows is not None
                else str(plan_item.get("semantic_role"))
            )
            if role != expected_role:
                raise ValueError(f"{field}.role differs from its plan/state authority role")
            if source != plan_item.get("source"):
                raise ValueError(f"{field}.source differs from reference_use_plan")
            if authority != plan_item.get("authority"):
                raise ValueError(f"{field}.authority differs from reference_use_plan")
            if expected_state_rows is not None:
                intended_influence = plan_item.get("intended_influence")
                if intended_influence not in expected_state_rows[index]["intended_influence"]:
                    raise ValueError(
                        f"{field} uses a plan influence that is not eligible in "
                        "reference_selection"
                    )
        else:
            if source.get("kind") == "pack-artifact":
                raise ValueError(
                    f"{field} uses a pack-artifact without an explicit Reference Use Plan"
                )
            expected_authority = (
                state_authority_for(normalized["intended_influence"])
                if selection_rows is not None
                else conservative_authority(role)
            )
            if authority != expected_authority:
                raise ValueError(f"{field}.authority is not the canonical conservative authority")
        validated.append(normalized)
    if validated != value:
        raise ValueError("selected references are not in canonical prepared form")
    return validated


def _default_zero_reference_reason(
    code: str,
    *,
    record_ids: Sequence[str] = (),
    detail: str | None = None,
) -> dict[str, Any]:
    details = {
        "no-canonical-record-selected": "No canonical record was selected for visual-reference activation.",
        "no-suitable-active-asset": "The selected canonical records have no suitable active visual-reference asset.",
        "user-declined-visual-references": "The user explicitly declined visual-reference transport.",
        "state-ineligible": "No selected visual reference is eligible for the requested story state.",
    }
    reason = {
        "code": code,
        "record_ids": list(dict.fromkeys(str(value) for value in record_ids)),
        "detail": detail or details.get(code, ""),
    }
    return _validate_zero_reference_reason(reason, "zero_reference_reason")


def _prepared_set_id(value: Mapping[str, Any]) -> str:
    projection = {
        "transport_mode": value.get("transport_mode"),
        "target_model": value.get("target_model"),
        "reference_selection_sha256": value.get("reference_selection_sha256"),
        "reference_use_plan_sha256": value.get("reference_use_plan_sha256"),
        "zero_reference_reason": value.get("zero_reference_reason"),
        "prompt_artifacts": value.get("prompt_artifacts"),
        "selected_references": value.get("selected_references"),
        "single_board": value.get("single_board"),
    }
    digest = hashlib.sha256(canonical_json(projection).encode("utf-8")).hexdigest()[:20]
    return f"PRS-{digest}"


def _validate_prompt_artifacts(
    value: Any,
    *,
    package_root: Path | None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("prompt_artifacts must be a JSON array")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        field = f"prompt_artifacts[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{field} must be an object")
        _require_exact_fields(raw, PROMPT_ARTIFACT_FIELDS, field)
        stored_path, path = _resolve_packaged_file(
            raw.get("delivered_path"),
            f"{field}.delivered_path",
            package_root=package_root,
        )
        delivered_hash = _require_sha256(
            raw.get("delivered_sha256"), f"{field}.delivered_sha256"
        )
        if sha256_file(path) != delivered_hash:
            raise ValueError(f"{field} delivered byte hash mismatch")
        media_type = _require_string(
            raw.get("media_type"), f"{field}.media_type", MEDIA_TYPE_RE
        )
        if detect_image_media_type(path) != media_type:
            raise ValueError(f"{field} media type differs from its file bytes")
        rows.append(
            {
                "semantic_role": _require_string(
                    raw.get("semantic_role"), f"{field}.semantic_role", ROLE_RE
                ),
                "source_sha256": _require_sha256(
                    raw.get("source_sha256"), f"{field}.source_sha256"
                ),
                "delivered_path": stored_path,
                "media_type": media_type,
                "delivered_sha256": delivered_hash,
            }
        )
    return rows


def _validate_single_board(
    value: Any,
    *,
    references: Sequence[Mapping[str, Any]],
    package_root: Path | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("single_board must be an object or null")
    _require_exact_fields(value, SINGLE_BOARD_FIELDS, "single_board")
    stored_path, path = _resolve_packaged_file(
        value.get("resolved_path"),
        "single_board.resolved_path",
        package_root=package_root,
    )
    media_type = _require_string(value.get("media_type"), "single_board.media_type")
    if media_type != PNG_MEDIA_TYPE or detect_image_media_type(path) != PNG_MEDIA_TYPE:
        raise ValueError("single_board must contain PNG bytes")
    digest = _require_sha256(value.get("sha256"), "single_board.sha256")
    if sha256_file(path) != digest:
        raise ValueError("single_board byte hash mismatch")
    board_width, board_height = image_dimensions(path, PNG_MEDIA_TYPE)
    panels = value.get("panels")
    if not isinstance(panels, list) or not panels:
        raise ValueError("single_board.panels must be a non-empty JSON array")
    if len(panels) != len(references):
        raise ValueError("single_board.panels must exactly match selected_references order")
    normalized_panels: list[dict[str, Any]] = []
    for index, (raw, reference) in enumerate(zip(panels, references, strict=True)):
        field = f"single_board.panels[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{field} must be an object")
        _require_exact_fields(raw, SINGLE_BOARD_PANEL_FIELDS, field)
        box = raw.get("box")
        if not isinstance(box, Mapping):
            raise ValueError(f"{field}.box must be an object")
        _require_exact_fields(box, SINGLE_BOARD_BOX_FIELDS, f"{field}.box")
        normalized_box: dict[str, int] = {}
        for coordinate in ("x", "y", "width", "height"):
            number = box.get(coordinate)
            minimum = 0 if coordinate in {"x", "y"} else 1
            if not isinstance(number, int) or isinstance(number, bool) or number < minimum:
                raise ValueError(f"{field}.box.{coordinate} is invalid")
            normalized_box[coordinate] = number
        if (
            normalized_box["x"] + normalized_box["width"] > board_width
            or normalized_box["y"] + normalized_box["height"] > board_height
        ):
            raise ValueError(f"{field}.box exceeds the board dimensions")
        source_hash = _require_sha256(raw.get("source_sha256"), f"{field}.source_sha256")
        transport_hash = _require_sha256(
            raw.get("transport_sha256"), f"{field}.transport_sha256"
        )
        if source_hash != reference["source"]["sha256"]:
            raise ValueError(f"{field}.source_sha256 differs from the original source")
        if transport_hash != reference["transport"]["sha256"]:
            raise ValueError(f"{field}.transport_sha256 differs from the prepared transport")
        semantic_role = _require_string(
            raw.get("semantic_role"), f"{field}.semantic_role", ROLE_RE
        )
        if semantic_role != reference["role"]:
            raise ValueError(f"{field}.semantic_role differs from selected_references")
        normalized_panels.append(
            {
                "semantic_role": semantic_role,
                "source_sha256": source_hash,
                "transport_sha256": transport_hash,
                "box": normalized_box,
            }
        )
    return {
        "resolved_path": stored_path,
        "media_type": PNG_MEDIA_TYPE,
        "sha256": digest,
        "panels": normalized_panels,
    }


def validate_prepared_reference_set(value: Any, *, model: str | None = None,
                                    package_root: Path | None = None) -> dict[str, Any]:
    """Validate source activity, target constraints and every delivered byte."""
    return _validate_prepared_reference_set(value, model=model, package_root=package_root)


def validate_prepared_reference_content(value: Any, *, model: str | None = None,
                                        package_root: Path | None = None) -> dict[str, Any]:
    """Verify recorded bytes and relations without approving a new delivery."""
    from build_generation_payload import validate_generation_package_carrier_paths
    companion = validate_generation_package_carrier_paths(value, package_root=package_root)
    archive = (package_root / companion / 'sources') if package_root is not None and companion else None
    return _validate_prepared_reference_set(value, model=model, package_root=package_root,
                                            context=_ReferenceContext(False, archive))


def _validate_prepared_reference_set(
    value: Any,
    *,
    model: str | None = None,
    package_root: Path | None = None,
    context: _ReferenceContext = _LIVE_REFERENCES,
) -> dict[str, Any]:
    """Validate the sole canonical reference-set artifact and every referenced byte."""

    if not isinstance(value, dict):
        raise ValueError("prepared reference input must be a JSON object")
    _require_exact_fields(value, PREPARED_REFERENCE_SET_FIELDS, "prepared reference set")
    if value.get("artifact_type") != "prepared-reference-set":
        raise ValueError("prepared reference input must be a prepared-reference-set artifact")
    artifact_report = validate_artifact(value)
    if not artifact_report.get("ok"):
        raise ValueError("invalid prepared-reference-set artifact: " + "; ".join(artifact_report["errors"]))

    set_id = _require_string(value.get("set_id"), "set_id")
    if not set_id.startswith("PRS-"):
        raise ValueError("set_id must begin with PRS-")
    mode = _require_string(value.get("transport_mode"), "transport_mode")
    if mode not in REFERENCE_TRANSPORT_MODES:
        raise ValueError("transport_mode is unsupported")
    target_model = value.get("target_model")
    if target_model is not None:
        target_model = _require_string(target_model, "target_model")
    if mode == "none" and target_model is not None:
        raise ValueError("none transport must have target_model=null")
    if mode in {"prompt-artifacts", "svg-bundle"} and target_model is not None:
        raise ValueError(f"{mode} transport must have target_model=null")
    if mode in {"multi-image", "single-board"}:
        if target_model is None:
            raise ValueError(f"{mode} transport requires target_model")
        if model is not None and target_model != model:
            raise ValueError("prepared reference target_model differs from generation model")

    selection_value = value.get("reference_selection")
    selection_hash_value = value.get("reference_selection_sha256")
    if selection_value is None:
        if selection_hash_value is not None:
            raise ValueError("reference_selection_sha256 must be null when reference_selection is null")
        selection = None
        selection_hash = None
    else:
        selection = _validated_reference_selection(selection_value)
        selection_hash = _require_sha256(
            selection_hash_value, "reference_selection_sha256"
        )
        if selection_hash != selection.get("selection_sha256"):
            raise ValueError(
                "reference_selection_sha256 does not match reference_selection.selection_sha256"
            )

    plan_value = value.get("reference_use_plan")
    plan_hash_value = value.get("reference_use_plan_sha256")
    surface_hash_value = value.get("surface_lighting_plan_sha256")
    if plan_value is None:
        if plan_hash_value is not None or surface_hash_value is not None:
            raise ValueError("plan and surface hashes must be null when reference_use_plan is null")
        plan = None
        plan_hash = None
        surface_hash = None
    else:
        plan = _validated_reference_use_plan(plan_value, context=context)
        plan_hash = _require_sha256(plan_hash_value, "reference_use_plan_sha256")
        surface_hash = _require_sha256(
            surface_hash_value, "surface_lighting_plan_sha256"
        )
        if plan_hash != plan.get("reference_use_plan_sha256"):
            raise ValueError("reference_use_plan_sha256 does not match reference_use_plan")
        if surface_hash != plan["surface_lighting_plan"].get("surface_lighting_plan_sha256"):
            raise ValueError("surface_lighting_plan_sha256 does not match reference_use_plan")
        if mode == "none":
            if plan.get("reference_items"):
                raise ValueError("none transport may embed only a zero-item reference-use plan")
        else:
            if plan.get("transport_mode") != mode:
                raise ValueError("transport_mode differs from reference_use_plan")
            if plan.get("target_model") != target_model:
                raise ValueError("target_model differs from reference_use_plan")
        if (
            mode in {"multi-image", "single-board"}
            and plan["surface_lighting_plan"].get("unresolved_decisions")
        ):
            raise ValueError("surface-lighting plan has unresolved decisions")

    zero_reason_value = value.get("zero_reference_reason")
    zero_reason = (
        None
        if zero_reason_value is None
        else _validate_zero_reference_reason(zero_reason_value, "zero_reference_reason")
    )
    if plan is not None and zero_reason != plan.get("zero_reference_reason"):
        raise ValueError("zero_reference_reason differs from reference_use_plan")

    prompt_artifacts = _validate_prompt_artifacts(
        value.get("prompt_artifacts"), package_root=package_root
    )
    if mode in {"prompt-artifacts", "svg-bundle"} and plan is None:
        raise ValueError(f"{mode} transport requires a reference-use plan")
    if plan is None and prompt_artifacts:
        raise ValueError("plan-null prepared references must not contain prompt_artifacts")
    effective_model = target_model or model or ""
    references = _validate_prepared_references(
        value.get("selected_references"),
        model=effective_model,
        reference_selection=selection, context=context,
        reference_use_plan=(plan if mode in {"multi-image", "single-board"} else None),
        package_root=package_root,
    )
    if context.active and mode in {"multi-image", "single-board"}:
        model_id, model_record = resolve_model_record(str(target_model))
        if model_record.get("operation_kind") == "upscale":
            raise ValueError(
                f"target model {model_id!r} is an upscaler and cannot accept generation references"
            )
        reference_limit = model_reference_limit(model_record)
        delivered_count = 1 if mode == "single-board" and references else len(references)
        if reference_limit is not None and delivered_count > reference_limit:
            raise ValueError(
                f"prepared references exceed model {model_id!r} max_reference_images="
                f"{reference_limit}"
            )
    board = _validate_single_board(
        value.get("single_board"),
        references=references,
        package_root=package_root,
    )
    preamble = value.get("reference_preamble")
    if not isinstance(preamble, str):
        raise ValueError("reference_preamble must be a string")

    plan_items = plan.get("reference_items", []) if plan is not None else []
    if plan is not None:
        if len(prompt_artifacts) != len(plan_items):
            raise ValueError("prompt_artifacts must exactly match reference_use_plan order")
        for index, (artifact, item) in enumerate(zip(prompt_artifacts, plan_items, strict=True)):
            source = item.get("source") or {}
            if (
                artifact["semantic_role"] != item.get("semantic_role")
                or artifact["source_sha256"] != source.get("sha256")
            ):
                raise ValueError(
                    f"prompt_artifacts[{index}] differs from reference_use_plan"
                )
            if artifact["delivered_sha256"] != source.get("sha256"):
                raise ValueError(
                    f"prompt_artifacts[{index}] is not an exact copy of its committed source"
                )
            if artifact["media_type"] != source.get("media_type"):
                raise ValueError(
                    f"prompt_artifacts[{index}] media type differs from its committed source"
                )

    expected_preamble = canonical_reference_preamble(
        transport_mode=mode,
        selected_references=references,
        reference_use_plan=plan,
        single_board=board,
    )
    if preamble != expected_preamble:
        raise ValueError("reference_preamble is not the canonical authority projection")

    has_visual_reference = bool(prompt_artifacts or references or board)
    if has_visual_reference and zero_reason is not None:
        raise ValueError("zero_reference_reason must be null when references are prepared")
    if not has_visual_reference and zero_reason is None:
        raise ValueError("zero_reference_reason is required when no reference is prepared")
    if mode == "none":
        if has_visual_reference or board is not None:
            raise ValueError("none transport must contain no reference payload")
    if mode == "prompt-artifacts" and (not prompt_artifacts or references or board is not None):
        raise ValueError("prompt-artifacts transport has an invalid payload projection")
    if mode == "svg-bundle":
        if (
            not prompt_artifacts
            or references
            or board is not None
            or any(row["media_type"] != SVG_MEDIA_TYPE for row in prompt_artifacts)
        ):
            raise ValueError("svg-bundle transport has an invalid payload projection")
    if mode == "multi-image" and (not references or board is not None):
        raise ValueError("multi-image transport requires selected references and no board")
    if mode == "single-board":
        if not references or board is None:
            raise ValueError("single-board transport requires selected references and a board")
        if context.active:
            allowed_media = model_reference_media_types(str(target_model), required=True)
            if PNG_MEDIA_TYPE not in allowed_media:
                raise ValueError("target model does not accept the single-board PNG transport")

    concrete_hash = _require_sha256(
        value.get("prepared_reference_set_sha256"), "prepared_reference_set_sha256"
    )
    normalized = {
        "artifact_type": "prepared-reference-set",
        "set_id": set_id,
        "transport_mode": mode,
        "target_model": target_model,
        "reference_selection": selection,
        "reference_selection_sha256": selection_hash,
        "reference_use_plan": plan,
        "reference_use_plan_sha256": plan_hash,
        "surface_lighting_plan_sha256": surface_hash,
        "zero_reference_reason": zero_reason,
        "reference_preamble": preamble,
        "prompt_artifacts": prompt_artifacts,
        "selected_references": references,
        "single_board": board,
        "prepared_reference_set_sha256": concrete_hash,
    }
    if normalized != value:
        raise ValueError("prepared reference set is not in canonical form")
    return normalized


def finalize_prepared_reference_set(
    value: Mapping[str, Any],
    *,
    model: str | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Seal and validate one canonical prepared-reference-set artifact."""

    raw = copy.deepcopy(dict(value))
    raw["artifact_type"] = "prepared-reference-set"
    raw.setdefault("set_id", _prepared_set_id(raw))
    raw["prepared_reference_set_sha256"] = "0" * 64
    sealed = finalize_artifact(raw)
    return validate_prepared_reference_set(
        sealed,
        model=model,
        package_root=package_root,
    )


def build_prepared_reference_set(
    *,
    transport_mode: str,
    target_model: str | None,
    selected_references: Sequence[Mapping[str, Any]] = (),
    reference_selection: Mapping[str, Any] | None = None,
    reference_use_plan: Mapping[str, Any] | None = None,
    zero_reference_reason: Mapping[str, Any] | None = None,
    reference_preamble: str | None = None,
    prompt_artifacts: Sequence[Mapping[str, Any]] = (),
    single_board: Mapping[str, Any] | None = None,
    set_id: str | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """Build the sole canonical prepared-reference-set shape."""

    selection = copy.deepcopy(dict(reference_selection)) if reference_selection is not None else None
    plan = copy.deepcopy(dict(reference_use_plan)) if reference_use_plan is not None else None
    prepared_rows = [copy.deepcopy(dict(row)) for row in selected_references]
    canonical_preamble = canonical_reference_preamble(
        transport_mode=transport_mode,
        selected_references=prepared_rows,
        reference_use_plan=plan,
        single_board=single_board,
    )
    if reference_preamble is not None and reference_preamble != canonical_preamble:
        raise ValueError("reference_preamble differs from the canonical authority projection")
    raw: dict[str, Any] = {
        "artifact_type": "prepared-reference-set",
        "set_id": set_id or "",
        "transport_mode": transport_mode,
        "target_model": target_model,
        "reference_selection": selection,
        "reference_selection_sha256": (
            selection.get("selection_sha256") if selection is not None else None
        ),
        "reference_use_plan": plan,
        "reference_use_plan_sha256": (
            plan.get("reference_use_plan_sha256") if plan is not None else None
        ),
        "surface_lighting_plan_sha256": (
            (plan.get("surface_lighting_plan") or {}).get("surface_lighting_plan_sha256")
            if plan is not None
            else None
        ),
        "zero_reference_reason": (
            copy.deepcopy(dict(zero_reference_reason))
            if zero_reference_reason is not None
            else None
        ),
        "reference_preamble": canonical_preamble,
        "prompt_artifacts": [copy.deepcopy(dict(row)) for row in prompt_artifacts],
        "selected_references": prepared_rows,
        "single_board": copy.deepcopy(dict(single_board)) if single_board is not None else None,
        "prepared_reference_set_sha256": "0" * 64,
    }
    if not raw["set_id"]:
        raw["set_id"] = _prepared_set_id(raw)
    return finalize_prepared_reference_set(
        raw,
        model=target_model,
        package_root=package_root,
    )


def empty_stateless_reference_set(
    *,
    zero_reference_reason: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    reason = (
        dict(zero_reference_reason)
        if zero_reference_reason is not None
        else _default_zero_reference_reason("no-canonical-record-selected")
    )
    return build_prepared_reference_set(
        transport_mode="none",
        target_model=None,
        zero_reference_reason=reason,
    )


def host_reference_transports(
    reference_set: Mapping[str, Any],
    *,
    package_root: Path | None = None,
) -> list[dict[str, str]]:
    mode = str(reference_set.get("transport_mode") or "")
    if mode == "none":
        return []
    if mode == "single-board":
        board = reference_set.get("single_board")
        if not isinstance(board, Mapping):
            raise ValueError("single-board reference set has no board")
        _stored, path = _resolve_packaged_file(
            board.get("resolved_path"),
            "single_board.resolved_path",
            package_root=package_root,
        )
        return [
            {
                "role": "composite-reference-board",
                "resolved_path": str(path),
                "media_type": str(board["media_type"]),
                "sha256": str(board["sha256"]),
            }
        ]
    if mode != "multi-image":
        raise ValueError(f"{mode} transport is not valid for model generation")
    rows: list[dict[str, str]] = []
    for index, reference in enumerate(reference_set.get("selected_references") or []):
        transport = reference["transport"]
        _stored, path = _resolve_packaged_file(
            transport.get("resolved_path"),
            f"selected_references[{index}].transport.resolved_path",
            package_root=package_root,
        )
        rows.append(
            {
                "role": str(reference["role"]),
                "resolved_path": str(path),
                "media_type": str(transport["media_type"]),
                "sha256": str(transport["sha256"]),
            }
        )
    return rows


def _preflight_selection_item(raw: Any, index: int) -> tuple[str, dict[str, Any]]:
    field = f"selections[{index}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{field} must be an object")
    _require_exact_fields(raw, frozenset({"role", "source"}), field)
    role = _require_string(raw.get("role"), f"{field}.role", ROLE_RE)
    source = raw.get("source")
    if not isinstance(source, Mapping):
        raise ValueError(f"{field}.source must be an object")
    if source.get("kind") == "pack-artifact":
        normalized = _validate_pack_source(source, f"{field}.source")
    elif source.get("kind") == "supplied-file":
        normalized = _prepare_supplied_source(source, f"{field}.source")
    else:
        raise ValueError(f"{field}.source.kind must be pack-artifact or supplied-file")
    _validate_source_prepareability(normalized, field)
    return role, normalized


def _validate_source_prepareability(source: Mapping[str, Any], field: str) -> None:
    if source["media_type"] == SVG_MEDIA_TYPE:
        digest, errors = inspect_svg(
            Path(source["resolved_path"]), require_path_element=False
        )
        if errors:
            raise ValueError("SVG source is unsafe: " + "; ".join(errors))
        if digest != source["sha256"]:
            raise ValueError(f"{field}.source SVG inspection hash mismatch")
        svg_dimensions(Path(source["resolved_path"]))
    elif source["media_type"] in DIRECT_MEDIA_TYPES:
        image_dimensions(Path(source["resolved_path"]), source["media_type"])
    else:
        raise ValueError(
            f"{field}.source media type {source['media_type']!r} cannot be prepared"
        )


def _preflight_committed_item(raw: Any, index: int) -> tuple[str, dict[str, Any]]:
    field = f"selections[{index}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{field} must be an object")
    _require_exact_fields(raw, frozenset({"role", "source"}), field)
    role = _require_string(raw.get("role"), f"{field}.role", ROLE_RE)
    source = _validate_source(raw.get("source"), f"{field}.source")
    _validate_source_prepareability(source, field)
    return role, source


def _validate_output_target(output_dir: Path) -> tuple[Path, bool]:
    output_dir = Path(output_dir).resolve()
    output_dir_preexisted = output_dir.exists()
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output directory path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise ValueError(f"output directory must be empty: {output_dir}")
    if not output_dir.parent.is_dir():
        raise ValueError(f"output directory parent does not exist: {output_dir.parent}")
    return output_dir, output_dir_preexisted


def _materialize_preflight(
    preflight: list[tuple[str, dict[str, Any]]],
    *,
    model: str,
    output_dir: Path,
    max_side: int,
) -> list[dict[str, Any]]:
    if not isinstance(max_side, int) or isinstance(max_side, bool) or max_side < 1:
        raise ValueError("max_side must be a positive integer")
    output_dir, output_dir_preexisted = _validate_output_target(output_dir)

    allowed_media = (
        model_reference_media_types(model, required=True) if preflight else frozenset()
    )
    for index, (_role, source) in enumerate(preflight):
        target_media = PNG_MEDIA_TYPE if source["media_type"] == SVG_MEDIA_TYPE else source["media_type"]
        if target_media not in allowed_media:
            raise ValueError(
                f"selections[{index}] cannot produce a reference media type declared by model {model!r}"
            )

    needs_raster = any(source["media_type"] == SVG_MEDIA_TYPE for _role, source in preflight)
    renderer_release = ""
    if needs_raster:
        try:
            renderer_release = importlib.metadata.version(SVG_RENDERER)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"{SVG_RENDERER} is required to prepare SVG references; install requirements-visual.txt"
            ) from exc

    staging: Path | None = None
    committed_output = False
    try:
        if needs_raster:
            staging = Path(
                tempfile.mkdtemp(prefix=f".{output_dir.name}-prepare-", dir=str(output_dir.parent))
            ).resolve()
        prepared: list[dict[str, Any]] = []
        for index, (role, source) in enumerate(preflight):
            source_path = Path(source["resolved_path"])
            if source["media_type"] in DIRECT_MEDIA_TYPES:
                transport = {
                    "resolved_path": str(source_path),
                    "media_type": source["media_type"],
                    "sha256": source["sha256"],
                    "derivation": {"mode": "direct"},
                }
            else:
                assert staging is not None
                width, height = raster_dimensions_for_max_side(source_path, max_side)
                filename = f"{index:03d}-{role}-{source['sha256'][:16]}.png"
                staged_path = staging / filename
                final_path = output_dir / filename
                render_svg(source_path, staged_path, width=width, height=height)
                if detect_image_media_type(staged_path) != PNG_MEDIA_TYPE:
                    raise ValueError(f"SVG renderer did not produce PNG bytes: {source_path}")
                if image_dimensions(staged_path, PNG_MEDIA_TYPE) != (width, height):
                    raise ValueError(f"SVG renderer produced unexpected dimensions: {source_path}")
                transport = {
                    "resolved_path": str(final_path),
                    "media_type": PNG_MEDIA_TYPE,
                    "sha256": sha256_file(staged_path),
                    "derivation": {
                        "mode": "svg-rasterization",
                        "renderer_id": SVG_RENDERER,
                        "renderer_release": renderer_release,
                        "source_sha256": source["sha256"],
                        "output_dimensions": {"width": width, "height": height},
                        "max_side": max_side,
                    },
                }
            prepared.append(
                {
                    "role": role,
                    "source": source,
                    "transport": transport,
                    "authority": conservative_authority(role),
                }
            )

        if needs_raster:
            assert staging is not None
            if output_dir.exists():
                output_dir.rmdir()
            os.replace(staging, output_dir)
            staging = None
            committed_output = True
        # These are deliberately intermediate rows.  The two callers attach
        # either conservative supplied-file authority or the complete plan/
        # state scope before invoking the public canonical validator.  Treating
        # this midpoint as a plan-null artifact would incorrectly reject valid
        # pack artifacts whose explicit plan is attached by the caller.
        return prepared
    except Exception:
        if committed_output and output_dir.is_dir():
            shutil.rmtree(output_dir)
            if output_dir_preexisted:
                output_dir.mkdir()
        raise
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def prepare_references(
    selections: Any,
    *,
    model: str,
    output_dir: Path,
    max_side: int = 1536,
) -> dict[str, Any]:
    if not isinstance(selections, list):
        raise ValueError("selection input must be a JSON array")
    for index, raw in enumerate(selections):
        source = raw.get("source") if isinstance(raw, Mapping) else None
        if not isinstance(source, Mapping) or source.get("kind") != "supplied-file":
            raise ValueError(
                f"selection[{index}] must be a supplied-file; active pack artifacts require "
                "an explicit Reference Use Plan executed by reference_runtime.py"
            )
    preflight = [_preflight_selection_item(raw, index) for index, raw in enumerate(selections)]
    references = _materialize_preflight(
        preflight,
        model=model,
        output_dir=output_dir,
        max_side=max_side,
    )
    if not references:
        return empty_stateless_reference_set()
    return build_prepared_reference_set(
        transport_mode="multi-image",
        target_model=model,
        selected_references=references,
    )
def _reference_preamble_for_prepared_rows(
    references: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "Use each reference only for its declared role and authority. Do not average unnamed attributes."
    ]
    for index, reference in enumerate(references, 1):
        authority = reference["authority"]
        lines.append(
            f"Reference {index} ({reference['role']}) controls: "
            + "; ".join(str(value) for value in authority["controls"])
            + ". It must not control: "
            + "; ".join(str(value) for value in authority["must_not_control"])
            + "."
        )
    return "\n".join(lines) + "\n"


def prepare_reference_use_plan_rows(
    reference_use_plan: Any,
    *,
    model: str,
    output_dir: Path,
    reference_selection: Any | None = None,
    max_side: int = 1536,
) -> list[dict[str, Any]]:
    """Materialize plan-ordered model rows, optionally intersected with state eligibility."""

    plan = _validated_reference_use_plan(reference_use_plan)
    if plan.get("transport_mode") not in {"multi-image", "single-board"}:
        raise ValueError("reference-use plan is not model-facing")
    if plan.get("target_model") != model:
        raise ValueError("reference-use plan target_model differs from model")
    selection = (
        _validated_reference_selection(reference_selection)
        if reference_selection is not None
        else None
    )
    matched_state_rows: list[dict[str, Any]] | None = None
    if selection is not None:
        available: dict[str, list[dict[str, Any]]] = {}
        for selected in selection["selected_references"]:
            available.setdefault(canonical_json(selected["source"]), []).append(selected)
        matched_state_rows = []
        for index, item in enumerate(plan["reference_items"]):
            matches = available.get(canonical_json(item["source"])) or []
            influence = item.get("intended_influence")
            match_index = next(
                (
                    candidate_index
                    for candidate_index, candidate in enumerate(matches)
                    if influence in candidate.get("intended_influence", [])
                ),
                None,
            )
            if match_index is None:
                raise ValueError(
                    f"reference_use_plan.reference_items[{index}] source and intended "
                    "influence are not eligible in reference_selection"
                )
            matched = matches.pop(match_index)
            matched_state_rows.append(matched)
    committed = []
    for index, item in enumerate(plan["reference_items"]):
        role = (
            matched_state_rows[index]["role"]
            if matched_state_rows is not None
            else item["semantic_role"]
        )
        committed.append({"role": role, "source": item["source"]})
    preflight = [
        _preflight_committed_item(raw, index)
        for index, raw in enumerate(committed)
    ]
    materialized = _materialize_preflight(
        preflight,
        model=model,
        output_dir=output_dir,
        max_side=max_side,
    )
    references: list[dict[str, Any]] = []
    for index, prepared in enumerate(materialized):
        row: dict[str, Any] = {
            "role": prepared["role"],
            "source": prepared["source"],
            "transport": prepared["transport"],
            "authority": copy.deepcopy(plan["reference_items"][index]["authority"]),
        }
        if matched_state_rows is not None:
            selected = matched_state_rows[index]
            row.update(
                binding_id=copy.deepcopy(selected["binding_id"]),
                covers=copy.deepcopy(selected["covers"]),
                intended_influence=copy.deepcopy(selected["intended_influence"]),
                review_dimensions=copy.deepcopy(selected["review_dimensions"]),
                unsupported_or_occluded_state=copy.deepcopy(
                    selected["unsupported_or_occluded_state"]
                ),
                unsupported_assumptions=copy.deepcopy(selected["unsupported_assumptions"]),
            )
        references.append(row)
    return validate_prepared_references(
        references,
        model=model,
        reference_selection=selection,
        reference_use_plan=plan,
    )


def prepare_state_reference_selection(
    selection: Any,
    *,
    model: str,
    output_dir: Path,
    max_side: int = 1536,
    zero_reference_reason: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a state selection and prepare its ordered committed sources."""

    selection = _validated_reference_selection(selection)
    pack_backed = [
        index
        for index, item in enumerate(selection["selected_references"])
        if (item.get("source") or {}).get("kind") == "pack-artifact"
    ]
    if pack_backed:
        raise ValueError(
            "state selection contains pack-artifact references at indexes "
            + ", ".join(str(index) for index in pack_backed)
            + "; active pack artifacts require an explicit Reference Use Plan executed "
            "by reference_runtime.py"
        )
    committed = [
        {"role": item["role"], "source": item["source"]}
        for item in selection["selected_references"]
    ]
    preflight = [
        _preflight_committed_item(raw, index)
        for index, raw in enumerate(committed)
    ]
    materialized = _materialize_preflight(
        preflight,
        model=model,
        output_dir=output_dir,
        max_side=max_side,
    )
    references: list[dict[str, Any]] = []
    for selected, prepared in zip(selection["selected_references"], materialized):
        references.append(
            {
                "binding_id": copy.deepcopy(selected["binding_id"]),
                "role": prepared["role"],
                "source": prepared["source"],
                "transport": prepared["transport"],
                "authority": state_authority_for(selected["intended_influence"]),
                "covers": copy.deepcopy(selected["covers"]),
                "intended_influence": copy.deepcopy(selected["intended_influence"]),
                "review_dimensions": copy.deepcopy(selected["review_dimensions"]),
                "unsupported_or_occluded_state": copy.deepcopy(
                    selected["unsupported_or_occluded_state"]
                ),
                "unsupported_assumptions": copy.deepcopy(
                    selected["unsupported_assumptions"]
                ),
            }
        )
    if not references:
        return build_prepared_reference_set(
            transport_mode="none",
            target_model=None,
            reference_selection=selection,
            zero_reference_reason=(
                dict(zero_reference_reason)
                if zero_reference_reason is not None
                else _default_zero_reference_reason(
                    "no-canonical-record-selected",
                    detail=(
                        "The finalized state-aware selection contains no visual-reference "
                        "binding and no canonical record-scoped plan was supplied."
                    ),
                )
            ),
        )
    return build_prepared_reference_set(
        transport_mode="multi-image",
        target_model=model,
        reference_selection=selection,
        selected_references=references,
    )


def read_json_array(path: Path) -> list[Any]:
    data = parse_json(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("selection input must be a JSON array")
    return data


def read_json_object(path: Path) -> dict[str, Any]:
    data = parse_json(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("state selection input must be a JSON object")
    return data


def write_json_atomic(path: Path, value: Any) -> None:
    """Write an output JSON file whole into a folder that already exists."""
    path = Path(path)
    if not path.parent.is_dir():
        raise ValueError(f"output JSON parent does not exist: {path.parent}")
    atomic_write_json(path, value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare exact ordered caller-supplied image references."
    )
    selection_group = parser.add_mutually_exclusive_group(required=True)
    selection_group.add_argument(
        "--supplied-selection-file",
        type=Path,
        help="Ordered supplied-file selection array; files are measured here",
    )
    selection_group.add_argument(
        "--state-selection-file",
        type=Path,
        help="Finalized reference-selection artifact with committed source provenance",
    )
    parser.add_argument("--model", default="gpt-image-2.5-flare")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-side", type=int, default=1536)
    parser.add_argument("--out", type=Path, required=True)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        if args.state_selection_file is not None:
            prepared = prepare_state_reference_selection(
                read_json_object(args.state_selection_file),
                model=args.model,
                output_dir=args.output_dir,
                max_side=args.max_side,
            )
        else:
            prepared = prepare_references(
                read_json_array(args.supplied_selection_file),
                model=args.model,
                output_dir=args.output_dir,
                max_side=args.max_side,
            )
        write_json_atomic(args.out, prepared)
        print(json.dumps(prepared, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
