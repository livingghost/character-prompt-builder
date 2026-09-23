#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from execution_contract import sha256_file

_FORBIDDEN_ACTIVE_TAGS = (
    b"<image",
    b"<script",
    b"<foreignobject",
    b"<animate",
    b"<animatemotion",
    b"<animatetransform",
    b"<set",
    b"<use",
    b"<audio",
    b"<video",
    b"<iframe",
    b"<object",
    b"<embed",
    b"<style",
)
_FORBIDDEN_DECLARATIONS = (b"<!doctype", b"<!entity")
_FORBIDDEN_LITERAL_MARKERS = (
    b"data:image/", b"<?xml-stylesheet", b"@import", b"url(",
    b"javascript:", b"vbscript:", b"expression(", b"behavior:",
    b"-moz-binding:",
)
_RESOURCE_ATTRIBUTE_NAMES = (b"href", b"xlink:href", b"src")
_EVENT_ATTRIBUTE_RE = re.compile(br"^on[a-z0-9_-]+$")


def _contains_prefixed_active_tag(data: bytes) -> bytes | None:
    """Reject namespaced forms such as ``<svg:script>``.

    XML permits namespace prefixes before a local element name. Literal
    ``<script`` checks do not cover that syntax, so inspect the short lexical
    neighbourhood around each ``:<active-name>`` occurrence.
    """

    local_names = (
        b"image", b"script", b"foreignobject", b"animate", b"animatemotion",
        b"animatetransform", b"set", b"use", b"audio", b"video", b"iframe",
        b"object", b"embed", b"style",
    )
    name_bytes = b"abcdefghijklmnopqrstuvwxyz0123456789_.-"
    terminators = b" \t\r\n/>"
    for local_name in local_names:
        marker = b":" + local_name
        offset = 0
        while True:
            index = data.find(marker, offset)
            if index < 0:
                break
            after = index + len(marker)
            if after < len(data) and data[after] not in terminators:
                offset = index + len(marker)
                continue
            start = index - 1
            while start >= 0 and data[start] in name_bytes:
                start -= 1
            if start >= 0 and data[start:start + 1] == b"<" and start + 1 < index:
                return data[start:after]
            offset = index + len(marker)
    return None


def _iter_marker_windows(data: bytes, marker: bytes, *, radius: int = 256):
    """Yield bounded windows around each literal marker occurrence.

    Normal archival SVGs contain none of the resource or event markers, so the
    fast path is a single C-level ``bytes.find``. If a marker is present, only
    a small local slice is inspected rather than applying a regular expression
    to a multi-megabyte path stream.
    """

    offset = 0
    while True:
        index = data.find(marker, offset)
        if index < 0:
            return
        yield data[max(0, index - radius): min(len(data), index + len(marker) + radius)]
        offset = index + len(marker)


def _contains_resource_attribute(data: bytes) -> bytes | None:
    for name in _RESOURCE_ATTRIBUTE_NAMES:
        for window in _iter_marker_windows(data, name):
            # Attribute names must be preceded by XML whitespace or ``<`` and
            # followed by optional whitespace plus ``=``. The bounded regex is
            # deliberately local, avoiding corpus-size backtracking.
            pattern = re.compile(
                rb"(?:^|[\s<])" + re.escape(name) + rb"\s*=",
                re.I,
            )
            match = pattern.search(window)
            if match:
                return match.group(0)
    return None


def _contains_event_attribute(data: bytes) -> bytes | None:
    # Only inspect tokens that begin after XML whitespace. This rejects event
    # handler attributes such as ``onclick=`` while ignoring arbitrary text in
    # path data.
    for marker in (b" on", b"\non", b"\ron", b"\ton"):
        for window in _iter_marker_windows(data, marker, radius=96):
            index = window.find(marker)
            if index < 0:
                continue
            pos = index + len(marker)
            end = pos
            while end < len(window) and (
                97 <= window[end] <= 122
                or 48 <= window[end] <= 57
                or window[end] in (45, 95)
            ):
                end += 1
            token = b"on" + window[pos:end]
            cursor = end
            while cursor < len(window) and window[cursor] in b" \t\r\n":
                cursor += 1
            if (
                cursor < len(window)
                and window[cursor: cursor + 1] == b"="
                and _EVENT_ATTRIBUTE_RE.match(token)
            ):
                return token + b"="
    return None



def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def object_hash(obj: dict[str, Any], field: str) -> str:
    clone = dict(obj)
    clone.pop(field, None)
    return hashlib.sha256(canonical_json(clone).encode("utf-8")).hexdigest()


def inspect_svg(
    path: Path,
    *,
    require_path_element: bool = True,
) -> tuple[str | None, list[str]]:
    """Hash and inspect every byte of an SVG using bounded streaming.

    Security inspection is always complete, including multi-gigabyte
    artifacts. The common path-only form uses literal byte searches. Resource
    and event-attribute checks inspect only small windows around rare markers,
    avoiding whole-file regular expressions and preserving linear performance.
    The inspection mode is fixed: every byte is hashed and checked.
    """

    path = Path(path)
    errors: list[str] = []
    if not path.is_file():
        return None, [f"{path}: SVG file is missing"]
    if path.is_symlink():
        return None, [f"{path}: symbolic links are not accepted as managed SVG artifacts"]

    digest = hashlib.sha256()
    overlap = b""
    found_svg = False
    found_path = False
    found_close = False
    matched: set[str] = set()

    with path.open("rb") as stream:
        while True:
            chunk = stream.read(32 << 20)
            if not chunk:
                break
            digest.update(chunk)
            sample = overlap + chunk
            lower = sample.lower()

            found_svg = found_svg or b"<svg" in lower
            found_path = found_path or b"<path" in lower
            found_close = found_close or b"</svg>" in lower

            for marker in _FORBIDDEN_ACTIVE_TAGS:
                if marker in lower:
                    matched.add(marker.decode("ascii"))
            if b":" in lower:
                prefixed = _contains_prefixed_active_tag(lower)
                if prefixed:
                    matched.add(prefixed.decode("utf-8", errors="replace"))
            for marker in _FORBIDDEN_DECLARATIONS:
                if marker in lower:
                    matched.add(marker.decode("ascii"))
            for marker in _FORBIDDEN_LITERAL_MARKERS:
                if marker in lower:
                    matched.add(marker.decode("ascii"))

            if b"href" in lower or b"src" in lower:
                match = _contains_resource_attribute(lower)
                if match:
                    matched.add(match.decode("utf-8", errors="replace"))
            if b" on" in lower or b"\non" in lower or b"\ron" in lower or b"\ton" in lower:
                match = _contains_event_attribute(lower)
                if match:
                    matched.add(match.decode("utf-8", errors="replace"))

            # The overlap is larger than any supported XML attribute or tag
            # token, so constructs split across chunk boundaries are detected.
            overlap = sample[-4096:]

    if not found_svg:
        errors.append(f"{path}: SVG root element not found")
    if require_path_element and not found_path:
        errors.append(f"{path}: SVG path element not found")
    if not found_close:
        errors.append(f"{path}: SVG closing element not found")
    for value in sorted(matched):
        errors.append(f"{path}: forbidden SVG construct matched {value!r}")
    return digest.hexdigest(), errors



def validate_svg(path: Path) -> list[str]:
    """Validate a corpus-managed perceptual SVG, including its path contract."""

    return inspect_svg(path, require_path_element=True)[1]


def validate_svg_for_render(path: Path) -> list[str]:
    """Validate any self-contained, inactive SVG before model-facing rasterization.

    Runtime references may be ordinary authored SVGs composed from safe shapes
    such as ``rect`` or ``circle``. Requiring a ``path`` element belongs to the
    managed visual-evidence corpus contract, not to generic render safety.
    """

    return inspect_svg(path, require_path_element=False)[1]


#: role -> (artifact_id, bundle-relative path, media_type).
#:
#: The values are the literals that ``compact_perceptual_visual_evidence`` writes
#: when it builds a bundle. Binding a declared role to its file is what stops a
#: bundle from renaming one audit layer into another after the fact.
BUNDLE_ARTIFACT_CONTRACT: dict[str, tuple[str, str, str]] = {
    "faithful-archival-vector": (
        "faithful-archival-vector",
        "derived-visual/faithful-archival.svg",
        "image/svg+xml",
    ),
    "vectorization-result": (
        "vectorization-result",
        "derived-visual/vectorization-result.json",
        "application/json",
    ),
    "semantic-region-map": (
        "semantic-regions",
        "derived-visual/semantic-regions.json",
        "application/json",
    ),
    "subject-mask": (
        "subject-mask",
        "derived-visual/subject-mask.svg",
        "image/svg+xml",
    ),
    "structural-line-tone": (
        "structural-line-tone",
        "derived-visual/structural-line-tone.svg",
        "image/svg+xml",
    ),
    "color-audit": (
        "color-audit",
        "derived-visual/color-audit.svg",
        "image/svg+xml",
    ),
    "saturation-rescue": (
        "saturation-rescue",
        "derived-visual/saturation-rescue.svg",
        "image/svg+xml",
    ),
    "specular-audit": (
        "specular-audit",
        "derived-visual/specular-audit.svg",
        "image/svg+xml",
    ),
    "palette-probes": (
        "palette-probes",
        "derived-visual/palette-probes.json",
        "application/json",
    ),
    "audit-extraction-set": (
        "audit-extraction-set",
        "derived-visual/audit-extraction-set.json",
        "application/json",
    ),
    "runtime-attachment-build": (
        "runtime-attachment-build",
        "derived-visual/runtime-attachment-build.json",
        "application/json",
    ),
}

#: The Layer B roles that ``audit-extraction-set.json`` lists on its own.
_AUDIT_SET_ROLES = (
    "subject-mask",
    "structural-line-tone",
    "color-audit",
    "saturation-rescue",
    "specular-audit",
    "palette-probes",
)


def _safe_bundle_path(bundle_dir: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"artifact path is not bundle-relative: {relative}")
    path = bundle_dir / rel
    resolved_parent = path.parent.resolve()
    bundle_resolved = bundle_dir.resolve()
    if resolved_parent != bundle_resolved and bundle_resolved not in resolved_parent.parents:
        raise ValueError(f"artifact path escapes bundle: {relative}")
    return path


def validate_bundle(bundle_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    hash_cache: dict[Path, str] = {}
    bundle_dir = Path(bundle_dir)
    required = [
        "visual-evidence-bundle.json",
        "visual-authority.json",
        "derived-visual/faithful-archival.svg",
        "derived-visual/vectorization-result.json",
        "derived-visual/semantic-regions.json",
        "derived-visual/subject-mask.svg",
        "derived-visual/structural-line-tone.svg",
        "derived-visual/color-audit.svg",
        "derived-visual/saturation-rescue.svg",
        "derived-visual/specular-audit.svg",
        "derived-visual/palette-probes.json",
        "derived-visual/audit-extraction-set.json",
        "derived-visual/runtime-attachment-build.json",
    ]
    for rel in required:
        path = bundle_dir / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
        elif path.is_symlink():
            errors.append(f"managed artifact must not be a symbolic link: {rel}")
    if errors:
        return {"ok": False, "errors": errors}

    try:
        bundle = json.loads((bundle_dir / "visual-evidence-bundle.json").read_text(encoding="utf-8"))
        authority = json.loads((bundle_dir / "visual-authority.json").read_text(encoding="utf-8"))
        vector = json.loads((bundle_dir / "derived-visual/vectorization-result.json").read_text(encoding="utf-8"))
        semantic = json.loads((bundle_dir / "derived-visual/semantic-regions.json").read_text(encoding="utf-8"))
        audit = json.loads((bundle_dir / "derived-visual/audit-extraction-set.json").read_text(encoding="utf-8"))
        runtime = json.loads((bundle_dir / "derived-visual/runtime-attachment-build.json").read_text(encoding="utf-8"))
        palette = json.loads((bundle_dir / "derived-visual/palette-probes.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [str(exc)]}

    svg_paths = {
        bundle_dir / "derived-visual/faithful-archival.svg",
        bundle_dir / "derived-visual/subject-mask.svg",
        bundle_dir / "derived-visual/structural-line-tone.svg",
        bundle_dir / "derived-visual/color-audit.svg",
        bundle_dir / "derived-visual/saturation-rescue.svg",
        bundle_dir / "derived-visual/specular-audit.svg",
    }
    svg_hashes: dict[Path, str] = {}
    for svg_path in svg_paths:
        digest, svg_errors = inspect_svg(svg_path)
        errors.extend(svg_errors)
        if digest is not None:
            svg_hashes[svg_path] = digest

    if bundle.get("artifact_type") != "visual-evidence-bundle":
        errors.append("wrong bundle artifact_type")
    if set((bundle.get("layers") or {}).keys()) != {"A", "B", "C"}:
        errors.append("visual-evidence bundle must declare Layers A, B, and C")
    if bundle.get("representation") != "native-dimension-compact-perceptual-path-vector":
        errors.append("unexpected bundle representation")
    if bundle.get("visual_evidence_bundle_sha256") != object_hash(bundle, "visual_evidence_bundle_sha256"):
        errors.append("bundle self-hash mismatch")
    if authority.get("visual_authority_sha256") != object_hash(authority, "visual_authority_sha256"):
        errors.append("authority self-hash mismatch")
    if vector.get("vectorization_result_sha256") != object_hash(vector, "vectorization_result_sha256"):
        errors.append("vectorization self-hash mismatch")
    if semantic.get("semantic_region_map_sha256") != object_hash(semantic, "semantic_region_map_sha256"):
        errors.append("semantic map self-hash mismatch")
    if audit.get("audit_extraction_set_sha256") != object_hash(audit, "audit_extraction_set_sha256"):
        errors.append("audit extraction set self-hash mismatch")
    if runtime.get("runtime_attachment_build_sha256") != object_hash(runtime, "runtime_attachment_build_sha256"):
        errors.append("runtime attachment build self-hash mismatch")
    if palette.get("palette_probes_sha256") != object_hash(palette, "palette_probes_sha256"):
        errors.append("palette probes self-hash mismatch")

    archival_svg = bundle_dir / "derived-visual/faithful-archival.svg"
    archival_vector = authority.get("archival_vector") or {}
    if archival_vector.get("source_payload_embedded"):
        errors.append("archival vector embeds source payload")
    if archival_vector.get("external_raster_reference"):
        errors.append("archival vector references external raster")
    declared_svg_hash = archival_vector.get("sha256")
    if vector.get("archival_svg_sha256") != declared_svg_hash:
        errors.append("vectorization and authority SVG hashes disagree")
    if svg_hashes.get(archival_svg) is not None and declared_svg_hash != svg_hashes[archival_svg]:
        errors.append("archival vector hash mismatch")
    expected_bytes = (vector.get("statistics") or {}).get("svg_bytes")
    if expected_bytes is not None and archival_svg.stat().st_size != expected_bytes:
        errors.append("archival vector byte count mismatch")

    constraints = vector.get("constraints") or {}
    for key in (
        "resized",
        "resampled",
        "raster_payload_embedded",
        "external_raster_reference",
        "contour_simplification",
        "small_region_deletion",
        "regional_quality_allocation",
    ):
        if constraints.get(key):
            errors.append(f"constraint must be false: {key}")
    if not constraints.get("uniform_full_frame_profile"):
        errors.append("compact archival vector must use one uniform full-frame profile")

    metrics = vector.get("accepted_metrics") or {}
    thresholds = vector.get("quality_thresholds") or {}
    if (
        metrics.get("psnr", -1) < thresholds.get("psnr_min", 28)
        or metrics.get("ssim", -1) < thresholds.get("ssim_min", 0.90)
        or metrics.get("tile_ssim_min", -1) < thresholds.get("tile_ssim_min", 0.75)
        or metrics.get("mean_ciede2000", 999) > thresholds.get("mean_ciede2000_max", 3.5)
        or metrics.get("p95_ciede2000", 999) > thresholds.get("p95_ciede2000_max", 12)
        or metrics.get("edge_f1", -1) < thresholds.get("edge_f1_min", 0.88)
        or metrics.get("mean_absolute_error", 999) > thresholds.get("mean_absolute_error_max", 6)
        or not vector.get("quality_passed")
    ):
        errors.append("perceptual fidelity gate not satisfied")

    allowed = set(BUNDLE_ARTIFACT_CONTRACT)
    declared = bundle.get("artifacts")
    declared = declared if isinstance(declared, list) else []
    declared_roles = [item.get("role") if isinstance(item, dict) else None for item in declared]
    declared_ids = [item.get("artifact_id") if isinstance(item, dict) else None for item in declared]
    roles = set(declared_roles)
    if roles != allowed:
        errors.append(f"bundle artifact roles do not match the three-layer contract: {sorted(roles)}")
    if len(declared) != len(BUNDLE_ARTIFACT_CONTRACT):
        errors.append(
            f"bundle must declare {len(BUNDLE_ARTIFACT_CONTRACT)} artifacts, not {len(declared)}"
        )
    if len(declared_roles) != len(set(declared_roles)):
        errors.append("bundle declares the same artifact role more than once")
    if len(declared_ids) != len(set(declared_ids)):
        errors.append("bundle declares the same artifact_id more than once")

    artifact_hashes: dict[str, str] = {}
    for artifact in declared:
        if not isinstance(artifact, dict):
            errors.append("bundle artifact entry must be an object")
            continue
        role = artifact.get("role")
        contract = BUNDLE_ARTIFACT_CONTRACT.get(role) if isinstance(role, str) else None
        try:
            path = _safe_bundle_path(bundle_dir, str(artifact["path"]))
        except (KeyError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if contract is not None:
            expected_id, expected_path, expected_media_type = contract
            if str(artifact.get("path")) != expected_path:
                errors.append(
                    f"artifact role {role} must name {expected_path}, "
                    f"not {str(artifact.get('path'))!r}"
                )
                continue
            if artifact.get("artifact_id") != expected_id:
                errors.append(
                    f"artifact role {role} must declare artifact_id {expected_id}, "
                    f"not {artifact.get('artifact_id')!r}"
                )
            if artifact.get("media_type") != expected_media_type:
                errors.append(
                    f"artifact role {role} must declare media_type {expected_media_type}, "
                    f"not {artifact.get('media_type')!r}"
                )
        if not path.is_file():
            errors.append(f"missing artifact {artifact.get('path')}")
            continue
        if path.is_symlink():
            errors.append(f"artifact must not be a symbolic link: {artifact.get('path')}")
            continue
        digest = svg_hashes.get(path) or hash_cache.setdefault(path, sha256_file(path))
        if digest != artifact.get("sha256"):
            errors.append(f"artifact hash mismatch {artifact.get('path')}")
        if isinstance(role, str):
            artifact_hashes[role] = digest

    audit_artifacts = audit.get("artifacts")
    audit_artifacts = audit_artifacts if isinstance(audit_artifacts, list) else []
    audit_by_role: dict[str, dict[str, Any]] = {}
    for entry in audit_artifacts:
        if not isinstance(entry, dict):
            errors.append("audit extraction set artifact entry must be an object")
            continue
        role = entry.get("role")
        if not isinstance(role, str) or role not in _AUDIT_SET_ROLES:
            errors.append(f"audit extraction set lists an unexpected role: {role!r}")
            continue
        if role in audit_by_role:
            errors.append(f"audit extraction set lists {role} more than once")
            continue
        audit_by_role[role] = entry
    for role in _AUDIT_SET_ROLES:
        entry = audit_by_role.get(role)
        if entry is None:
            errors.append(f"audit extraction set does not list {role}")
            continue
        expected_id, expected_path, expected_media_type = BUNDLE_ARTIFACT_CONTRACT[role]
        if entry.get("path") != expected_path:
            errors.append(
                f"audit extraction set role {role} must name {expected_path}, "
                f"not {entry.get('path')!r}"
            )
        if entry.get("artifact_id") != expected_id:
            errors.append(
                f"audit extraction set role {role} must declare artifact_id {expected_id}, "
                f"not {entry.get('artifact_id')!r}"
            )
        if entry.get("media_type") != expected_media_type:
            errors.append(
                f"audit extraction set role {role} must declare media_type "
                f"{expected_media_type}, not {entry.get('media_type')!r}"
            )
        digest = artifact_hashes.get(role)
        if digest is not None and entry.get("sha256") != digest:
            errors.append(f"audit extraction set hash disagrees with the bundle for {role}")

    for label, derived_value in (
        ("visual-authority.json", authority),
        ("derived-visual/vectorization-result.json", vector),
        ("derived-visual/semantic-regions.json", semantic),
        ("derived-visual/audit-extraction-set.json", audit),
        ("derived-visual/runtime-attachment-build.json", runtime),
        ("derived-visual/palette-probes.json", palette),
    ):
        for field in ("source_sha256", "source_ref_id"):
            if derived_value.get(field) != bundle.get(field):
                errors.append(f"{label} {field} disagrees with the bundle")

    authority_ref = bundle.get("visual_authority_ref")
    authority_ref = authority_ref if isinstance(authority_ref, dict) else {}
    if authority_ref.get("id") != authority.get("authority_id"):
        errors.append("visual_authority_ref id disagrees with visual-authority.json")
    if authority_ref.get("sha256") != authority.get("visual_authority_sha256"):
        errors.append("visual_authority_ref sha256 disagrees with visual-authority.json")
    return {
        "ok": not errors,
        "errors": errors,
        "source_sha256": bundle.get("source_sha256"),
        "bundle_id": bundle.get("bundle_id"),
    }


def render_svg(svg: Path, output: Path, width: int | None = None, height: int | None = None) -> None:
    svg = Path(svg)
    output = Path(output)
    errors = validate_svg_for_render(svg)
    if errors:
        raise ValueError(
            "SVG rasterization rejected unsafe or non-self-contained input:\n"
            + "\n".join(errors)
        )
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError(
            "CairoSVG is required for SVG rasterization; install requirements-visual.txt"
        ) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=svg.read_bytes(),
        write_to=str(output),
        output_width=width,
        output_height=height,
    )


def canonicalize_svg(source: Path, output: Path) -> dict[str, Any]:
    errors = validate_svg(source)
    if errors:
        return {"ok": False, "errors": errors}
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    return {"ok": True, "output": str(output), "sha256": sha256_file(output)}
