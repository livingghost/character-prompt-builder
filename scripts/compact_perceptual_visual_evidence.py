#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from rasterio.features import shapes
from skimage.color import deltaE_ciede2000, rgb2lab
from skimage.metrics import structural_similarity

from execution_contract import sha256_file

PROFILES: tuple[dict[str, Any], ...] = (
    {"id": "compact-96", "colors": 96, "filter": "meanshift", "sp": 3, "sr": 8, "median": 3},
    {"id": "balanced-128", "colors": 128, "filter": "meanshift", "sp": 3, "sr": 8, "median": 3},
    {"id": "detail-192", "colors": 192, "filter": "meanshift", "sp": 2, "sr": 6, "median": 3},
    {"id": "detail-256", "colors": 256, "filter": "bilateral", "diameter": 5, "sigma_color": 8.0, "sigma_space": 5.0, "median": 0},
)

QUALITY_THRESHOLDS: dict[str, float] = {
    "psnr_min": 28.0,
    "ssim_min": 0.90,
    "tile_ssim_min": 0.75,
    "mean_ciede2000_max": 3.5,
    "p95_ciede2000_max": 12.0,
    "edge_f1_min": 0.88,
    "mean_absolute_error_max": 6.0,
}


def cjson(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_source_content(source: Path, entry: dict[str, Any]) -> str:
    """Return the declared digest after verifying the exact source bytes."""

    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    source_sha = str(entry.get("source_sha256") or "")
    if len(source_sha) != 64 or any(character not in "0123456789abcdef" for character in source_sha):
        raise ValueError("entry.source_sha256 must be a lowercase 64-character SHA-256")
    if sha256_file(source) != source_sha:
        raise ValueError("entry.source_sha256 does not match source content")
    return source_sha


def finalize(value: dict[str, Any], field: str) -> dict[str, Any]:
    clone = dict(value)
    clone.pop(field, None)
    value[field] = hash_bytes(cjson(clone).encode("utf-8"))
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def resize_max(rgb: np.ndarray, max_side: int) -> np.ndarray:
    height, width = rgb.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale == 1.0:
        return rgb
    return cv2.resize(rgb, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA)


def quantize(rgb: np.ndarray, profile: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if profile["filter"] == "meanshift":
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        filtered = cv2.pyrMeanShiftFiltering(
            bgr,
            int(profile["sp"]),
            int(profile["sr"]),
            maxLevel=1,
        )
        work = cv2.cvtColor(filtered, cv2.COLOR_BGR2RGB)
    else:
        work = cv2.bilateralFilter(
            rgb,
            int(profile["diameter"]),
            float(profile["sigma_color"]),
            float(profile["sigma_space"]),
        )
    quantized = Image.fromarray(work, "RGB").quantize(
        colors=int(profile["colors"]),
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    labels = np.asarray(quantized, dtype=np.uint8)
    palette = np.asarray(quantized.getpalette(), dtype=np.uint8).reshape(-1, 3)[: int(profile["colors"])]
    median = int(profile.get("median", 0))
    if median:
        labels = cv2.medianBlur(labels, median)
    candidate = palette[labels]
    return labels, palette, candidate


def edge_f1(source: np.ndarray, candidate: np.ndarray) -> float:
    source_edges = cv2.Canny(cv2.cvtColor(source, cv2.COLOR_RGB2GRAY), 50, 150) > 0
    candidate_edges = cv2.Canny(cv2.cvtColor(candidate, cv2.COLOR_RGB2GRAY), 50, 150) > 0
    kernel = np.ones((3, 3), np.uint8)
    source_dilated = cv2.dilate(source_edges.astype(np.uint8), kernel) > 0
    candidate_dilated = cv2.dilate(candidate_edges.astype(np.uint8), kernel) > 0
    precision = float(np.count_nonzero(candidate_edges & source_dilated) / max(1, np.count_nonzero(candidate_edges)))
    recall = float(np.count_nonzero(source_edges & candidate_dilated) / max(1, np.count_nonzero(source_edges)))
    return 0.0 if precision + recall == 0.0 else float(2.0 * precision * recall / (precision + recall))


def tile_ssim_min(source: np.ndarray, candidate: np.ndarray, divisions: int = 4) -> float:
    height, width = source.shape[:2]
    values: list[float] = []
    for row in range(divisions):
        y0 = round(row * height / divisions)
        y1 = round((row + 1) * height / divisions)
        for column in range(divisions):
            x0 = round(column * width / divisions)
            x1 = round((column + 1) * width / divisions)
            tile_source = source[y0:y1, x0:x1]
            tile_candidate = candidate[y0:y1, x0:x1]
            values.append(
                float(
                    structural_similarity(
                        tile_source,
                        tile_candidate,
                        channel_axis=2,
                        data_range=255,
                    )
                )
            )
    return min(values)


def metrics(source: np.ndarray, candidate: np.ndarray) -> dict[str, float | int]:
    difference = source.astype(np.float32) - candidate.astype(np.float32)
    mse = float(np.mean(difference * difference))
    psnr = 999.0 if mse == 0.0 else float(10.0 * math.log10((255.0 * 255.0) / mse))
    mae = float(np.mean(np.abs(difference)))
    measured_source = resize_max(source, 768)
    measured_candidate = cv2.resize(
        candidate,
        (measured_source.shape[1], measured_source.shape[0]),
        interpolation=cv2.INTER_AREA,
    )
    ssim = float(
        structural_similarity(
            measured_source,
            measured_candidate,
            channel_axis=2,
            data_range=255,
        )
    )
    delta = deltaE_ciede2000(
        rgb2lab(measured_source.astype(np.float32) / 255.0),
        rgb2lab(measured_candidate.astype(np.float32) / 255.0),
    )
    return {
        "psnr": psnr,
        "ssim": ssim,
        "tile_ssim_min": tile_ssim_min(measured_source, measured_candidate),
        "mean_ciede2000": float(np.mean(delta)),
        "p95_ciede2000": float(np.percentile(delta, 95)),
        "edge_f1": edge_f1(measured_source, measured_candidate),
        "mean_absolute_error": mae,
        "measurement_max_side": 768,
    }


def passes(measurements: dict[str, float | int]) -> bool:
    return bool(
        float(measurements["psnr"]) >= QUALITY_THRESHOLDS["psnr_min"]
        and float(measurements["ssim"]) >= QUALITY_THRESHOLDS["ssim_min"]
        and float(measurements["tile_ssim_min"]) >= QUALITY_THRESHOLDS["tile_ssim_min"]
        and float(measurements["mean_ciede2000"]) <= QUALITY_THRESHOLDS["mean_ciede2000_max"]
        and float(measurements["p95_ciede2000"]) <= QUALITY_THRESHOLDS["p95_ciede2000_max"]
        and float(measurements["edge_f1"]) >= QUALITY_THRESHOLDS["edge_f1_min"]
        and float(measurements["mean_absolute_error"]) <= QUALITY_THRESHOLDS["mean_absolute_error_max"]
    )


def ring_path(ring: list[list[float]]) -> str:
    points = [(int(round(x)), int(round(y))) for x, y in ring]
    if len(points) > 1 and points[-1] == points[0]:
        points.pop()
    if len(points) < 3:
        return ""
    x0, y0 = points[0]
    commands = [f"M{x0} {y0}"]
    for x, y in points[1:]:
        dx = x - x0
        dy = y - y0
        if dy == 0:
            commands.append(f"h{dx}")
        elif dx == 0:
            commands.append(f"v{dy}")
        else:
            commands.append(f"l{dx} {dy}")
        x0, y0 = x, y
    commands.append("z")
    return "".join(commands)


def write_label_svg(
    labels: np.ndarray,
    palette: np.ndarray,
    output: Path,
    *,
    transparent_labels: set[int] | None = None,
    background: str | None = None,
) -> dict[str, int]:
    transparent_labels = transparent_labels or set()
    height, width = labels.shape
    by_label: dict[int, list[str]] = defaultdict(list)
    component_count = 0
    ring_count = 0
    vertex_count = 0
    for geometry, raw_label in shapes(labels.astype(np.int16), connectivity=8):
        label = int(raw_label)
        if label in transparent_labels:
            continue
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for polygon in polygons:
            for ring in polygon:
                encoded = ring_path(ring)
                if encoded:
                    by_label[label].append(encoded)
                    ring_count += 1
                    vertex_count += max(0, encoded.count("h") + encoded.count("v") + encoded.count("l") + 1)
        component_count += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges">'
        )
        if background is not None:
            stream.write(f'<rect width="{width}" height="{height}" fill="{background}"/>')
        for label in sorted(by_label):
            red, green, blue = (int(value) for value in palette[label])
            stream.write(
                f'<path fill="#{red:02x}{green:02x}{blue:02x}" fill-rule="evenodd" '
                f'd="{"".join(by_label[label])}"/>'
            )
        if not by_label:
            stream.write('<path fill="none" d="M0 0z"/>')
        stream.write("</svg>\n")
    return {
        "path_count": len(by_label),
        "contour_component_count": component_count,
        "ring_count": ring_count,
        "vertex_count": vertex_count,
        "unique_color_count": len(by_label),
        "svg_bytes": output.stat().st_size,
    }


def write_binary_svg(mask: np.ndarray, output: Path, *, foreground: str = "#ffffff", background: str | None = None) -> dict[str, int]:
    labels = mask.astype(np.uint8)
    palette = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
    if foreground != "#ffffff":
        palette[1] = tuple(int(foreground[index:index+2], 16) for index in (1, 3, 5))
    return write_label_svg(labels, palette, output, transparent_labels={0} if background is None else set(), background=background)


def extract_audit_layers(source_rgb: np.ndarray, derived: Path, source_ref: str, source_sha: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audit_rgb = resize_max(source_rgb, 840)
    height, width = audit_rgb.shape[:2]

    # Conservative automatic foreground mask. It is evidence, not an approval claim.
    grab = np.zeros((height, width), np.uint8)
    inset_x = max(1, round(width * 0.025))
    inset_y = max(1, round(height * 0.025))
    rectangle = (inset_x, inset_y, max(1, width - 2 * inset_x), max(1, height - 2 * inset_y))
    bg_model = np.zeros((1, 65), np.float64)
    fg_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(audit_rgb, grab, rectangle, bg_model, fg_model, 3, cv2.GC_INIT_WITH_RECT)
        subject = np.where((grab == cv2.GC_FGD) | (grab == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
        subject = cv2.morphologyEx(subject, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        subject = cv2.morphologyEx(subject, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        coverage = float(subject.mean())
        if coverage < 0.03 or coverage > 0.995:
            subject[:] = 1
            coverage = 1.0
    except cv2.error:
        subject = np.ones((height, width), np.uint8)
        coverage = 1.0
    subject_path = derived / "subject-mask.svg"
    subject_stats = write_binary_svg(subject, subject_path, foreground="#ffffff", background="#000000")

    gray = cv2.cvtColor(audit_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.bilateralFilter(gray, 5, 18, 5)
    thresholds = np.percentile(gray, [16, 34, 52, 70, 86]).astype(np.uint8)
    tone_labels = np.digitize(gray, thresholds, right=False).astype(np.uint8) + 1
    edges = cv2.Canny(gray, 55, 145) > 0
    tone_labels[edges] = 0
    tone_palette = np.array(
        [[12, 12, 12], [35, 35, 35], [72, 72, 72], [112, 112, 112], [156, 156, 156], [204, 204, 204], [242, 242, 242]],
        dtype=np.uint8,
    )
    structural_path = derived / "structural-line-tone.svg"
    structural_stats = write_label_svg(tone_labels, tone_palette, structural_path)

    color_rgb = resize_max(source_rgb, 640)
    color_profile = {"id": "audit-16", "colors": 16, "filter": "meanshift", "sp": 3, "sr": 10, "median": 3}
    color_labels, color_palette, _ = quantize(color_rgb, color_profile)
    color_path = derived / "color-audit.svg"
    color_stats = write_label_svg(color_labels, color_palette, color_path)
    counts = np.bincount(color_labels.ravel(), minlength=len(color_palette))
    total = int(color_labels.size)
    probes = {
        "artifact_type": "palette-probes",
        "source_ref_id": source_ref,
        "source_sha256": source_sha,
        "working_dimensions": {"width": int(color_labels.shape[1]), "height": int(color_labels.shape[0])},
        "colors": [
            {
                "hex": f"#{int(color_palette[index][0]):02x}{int(color_palette[index][1]):02x}{int(color_palette[index][2]):02x}",
                "fraction": float(counts[index] / total),
            }
            for index in np.argsort(-counts)
            if counts[index] > 0
        ],
    }
    finalize(probes, "palette_probes_sha256")
    probes_path = derived / "palette-probes.json"
    write_json(probes_path, probes)

    hsv = cv2.cvtColor(color_rgb, cv2.COLOR_RGB2HSV)
    saturation_mask = (hsv[:, :, 1] >= 110) & (hsv[:, :, 2] >= 55)
    hue_labels = np.zeros(hsv.shape[:2], dtype=np.uint8)
    hue_labels[saturation_mask] = (hsv[:, :, 0][saturation_mask] // 15 + 1).astype(np.uint8)
    hue_palette = np.zeros((13, 3), dtype=np.uint8)
    for index in range(1, 13):
        hue = np.uint8([[[min(179, (index - 1) * 15 + 7), 220, 235]]])
        hue_palette[index] = cv2.cvtColor(hue, cv2.COLOR_HSV2RGB)[0, 0]
    saturation_path = derived / "saturation-rescue.svg"
    saturation_stats = write_label_svg(hue_labels, hue_palette, saturation_path, transparent_labels={0})

    value = hsv[:, :, 2]
    saturation = hsv[:, :, 1]
    highlight = ((value >= max(220, int(np.percentile(value, 94)))) & (saturation <= 125)).astype(np.uint8)
    specular_path = derived / "specular-audit.svg"
    specular_stats = write_binary_svg(highlight, specular_path, foreground="#ffffff", background=None)

    artifacts = []
    for artifact_id, role, path in (
        ("subject-mask", "subject-mask", subject_path),
        ("structural-line-tone", "structural-line-tone", structural_path),
        ("color-audit", "color-audit", color_path),
        ("saturation-rescue", "saturation-rescue", saturation_path),
        ("specular-audit", "specular-audit", specular_path),
        ("palette-probes", "palette-probes", probes_path),
    ):
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "role": role,
                "path": f"derived-visual/{path.name}",
                "media_type": "application/json" if path.suffix == ".json" else "image/svg+xml",
                "sha256": sha256_file(path),
            }
        )
    audit = {
        "artifact_type": "audit-extraction-set",
        "audit_id": f"AUD-{source_sha[:16]}",
        "source_ref_id": source_ref,
        "source_sha256": source_sha,
        "working_dimensions": {"width": width, "height": height},
        "subject_mask_coverage": coverage,
        "artifacts": artifacts,
        "statistics": {
            "subject_mask": subject_stats,
            "structural_line_tone": structural_stats,
            "color_audit": color_stats,
            "saturation_rescue": saturation_stats,
            "specular_audit": specular_stats,
        },
        "notes": [
            "Layer B is intentionally simplified for measurement and runtime-guide preparation.",
            "Automatic mask extraction is not a human review or owner approval claim.",
        ],
    }
    finalize(audit, "audit_extraction_set_sha256")
    audit_path = derived / "audit-extraction-set.json"
    write_json(audit_path, audit)
    artifacts.append(
        {
            "artifact_id": "audit-extraction-set",
            "role": "audit-extraction-set",
            "path": "derived-visual/audit-extraction-set.json",
            "media_type": "application/json",
            "sha256": sha256_file(audit_path),
        }
    )
    return artifacts, audit


def process_one(job: tuple[str, dict[str, Any], str]) -> dict[str, Any]:
    source_value, entry, evidence_root_value = job
    source = Path(source_value)
    evidence_root = Path(evidence_root_value)
    source_sha = verify_source_content(source, entry)
    prefix = source_sha[:16]
    source_ref = f"SRC-{prefix}"
    bundle_dir = evidence_root / prefix
    derived = bundle_dir / "derived-visual"
    derived.mkdir(parents=True, exist_ok=True)

    source_rgb = np.asarray(Image.open(source).convert("RGB"), dtype=np.uint8)
    height, width = source_rgb.shape[:2]
    attempts: list[dict[str, Any]] = []
    selected: tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, dict[str, Any]] | None = None
    for profile in PROFILES:
        labels, palette, candidate = quantize(source_rgb, profile)
        measurements = metrics(source_rgb, candidate)
        accepted = passes(measurements)
        attempts.append({"profile": dict(profile), "metrics": measurements, "passed": accepted})
        if accepted:
            selected = (profile, labels, palette, candidate, measurements)
            break
    if selected is None:
        profile = PROFILES[-1]
        labels, palette, candidate = quantize(source_rgb, profile)
        measurements = metrics(source_rgb, candidate)
        selected = (profile, labels, palette, candidate, measurements)
        attempts[-1] = {"profile": dict(profile), "metrics": measurements, "passed": False}

    profile, labels, palette, candidate, accepted_metrics = selected
    archival_path = derived / "faithful-archival.svg"
    archival_stats = write_label_svg(labels, palette, archival_path)
    archival_sha = sha256_file(archival_path)

    record_refs = [str(value) for value in entry.get("canonical_record_ids") or []]
    semantic = {
        "artifact_type": "semantic-region-map",
        "region_map_id": f"SRM-{prefix}",
        "source_ref_id": source_ref,
        "source_sha256": source_sha,
        "coordinate_space": {"width": width, "height": height},
        "regions": [],
        "canonical_record_refs": record_refs,
        "notes": ["No semantic SVG element mapping is asserted unless authored separately."],
    }
    finalize(semantic, "semantic_region_map_sha256")
    semantic_path = derived / "semantic-regions.json"
    write_json(semantic_path, semantic)

    layer_b_artifacts, audit = extract_audit_layers(source_rgb, derived, source_ref, source_sha)

    runtime = {
        "artifact_type": "runtime-attachment-build",
        "build_id": f"RT-{prefix}",
        "source_ref_id": source_ref,
        "source_sha256": source_sha,
        "recipes": [
            {
                "recipe_id": "structural-guide",
                "inputs": ["structural-line-tone"],
                "output_media_type": "image/png",
                "output_policy": "disposable",
                "recommended_max_side": 1536,
                "preamble": "Use the attached structural guide for composition, pose, overlap, count, and silhouette. Do not copy its reduced tone treatment as the final rendering finish.",
            },
            {
                "recipe_id": "structural-guide-with-palette",
                "inputs": ["structural-line-tone", "palette-probes"],
                "output_media_type": "image/png",
                "output_policy": "disposable",
                "recommended_max_side": 1536,
                "preamble": "Use the structural guide for geometry and the palette evidence for local color organization. Preserve the requested medium and finish rather than reproducing the audit abstraction.",
            },
        ],
        "notes": ["Layer C stores build recipes only. Runtime raster attachments are not persisted in the package."],
    }
    finalize(runtime, "runtime_attachment_build_sha256")
    runtime_path = derived / "runtime-attachment-build.json"
    write_json(runtime_path, runtime)

    vector = {
        "artifact_type": "vectorization-result",
        "source_ref_id": source_ref,
        "source_sha256": source_sha,
        "source_media_type": str(entry.get("source_media_type") or "image/jpeg"),
        "native_dimensions": {"width": width, "height": height},
        "archival_svg_sha256": archival_sha,
        "candidate_pixel_sha256": hash_bytes(candidate.tobytes()),
        "method": "native-uniform-compact-perceptual-palette-connected-contours",
        "selected_profile": dict(profile),
        "attempts": attempts,
        "quality_thresholds": dict(QUALITY_THRESHOLDS),
        "accepted_metrics": accepted_metrics,
        "quality_passed": passes(accepted_metrics),
        "statistics": archival_stats,
        "constraints": {
            "resized": False,
            "resampled": False,
            "raster_payload_embedded": False,
            "external_raster_reference": False,
            "contour_simplification": False,
            "small_region_deletion": False,
            "regional_quality_allocation": False,
            "uniform_full_frame_profile": True,
            "perceptual_palette_reduction": True,
            "edge_preserving_smoothing": True,
        },
    }
    finalize(vector, "vectorization_result_sha256")
    vector_path = derived / "vectorization-result.json"
    write_json(vector_path, vector)

    authority = {
        "artifact_type": "visual-authority",
        "authority_id": f"VA-{prefix}",
        "source_ref_id": source_ref,
        "mode": "source-derived",
        "authority_scope": "reference-evidence",
        "source_sha256": source_sha,
        "source_media_type": str(entry.get("source_media_type") or "image/jpeg"),
        "source_dimensions": {"width": width, "height": height},
        "archival_vector": {
            "artifact_id": "faithful-archival-vector",
            "path": "derived-visual/faithful-archival.svg",
            "sha256": archival_sha,
            "representation": "native-full-color-compact-perceptual-path-vector",
            "source_payload_embedded": False,
            "external_raster_reference": False,
        },
        "canonical_record_refs": record_refs,
        "notes": [
            "The source raster is authoritative only at derivation time.",
            "Layer A preserves native dimensions while using one uniform perceptual profile across the complete frame.",
        ],
    }
    finalize(authority, "visual_authority_sha256")
    authority_path = bundle_dir / "visual-authority.json"
    write_json(authority_path, authority)

    artifacts: list[dict[str, Any]] = [
        {
            "artifact_id": "faithful-archival-vector",
            "role": "faithful-archival-vector",
            "path": "derived-visual/faithful-archival.svg",
            "media_type": "image/svg+xml",
            "sha256": archival_sha,
        },
        {
            "artifact_id": "vectorization-result",
            "role": "vectorization-result",
            "path": "derived-visual/vectorization-result.json",
            "media_type": "application/json",
            "sha256": sha256_file(vector_path),
        },
        {
            "artifact_id": "semantic-regions",
            "role": "semantic-region-map",
            "path": "derived-visual/semantic-regions.json",
            "media_type": "application/json",
            "sha256": sha256_file(semantic_path),
        },
    ]
    artifacts.extend(layer_b_artifacts)
    artifacts.append(
        {
            "artifact_id": "runtime-attachment-build",
            "role": "runtime-attachment-build",
            "path": "derived-visual/runtime-attachment-build.json",
            "media_type": "application/json",
            "sha256": sha256_file(runtime_path),
        }
    )

    bundle = {
        "artifact_type": "visual-evidence-bundle",
        "bundle_id": f"VE-{prefix}",
        "source_ref_id": source_ref,
        "source_sha256": source_sha,
        "source_dimensions": {"width": width, "height": height},
        "visual_authority_ref": {"id": authority["authority_id"], "sha256": authority["visual_authority_sha256"]},
        "layers": {
            "A": "native-dimension compact perceptual archival vector",
            "B": "audit extraction set",
            "C": "disposable runtime attachment build recipes",
        },
        "representation": "native-dimension-compact-perceptual-path-vector",
        "artifacts": artifacts,
        "canonical_record_refs": record_refs,
        "disposition": str(entry.get("disposition") or "reference-evidence"),
        "evidence_relation": str(entry.get("evidence_relation") or "reference-evidence"),
        "semantic_summary": str(entry.get("semantic_summary") or ""),
        "notes": [
            "The bundle contains all three visual-evidence layers in one portable package.",
            "Assistant-generated images and conversational work products are outside the admitted source corpus.",
        ],
    }
    finalize(bundle, "visual_evidence_bundle_sha256")
    bundle_path = bundle_dir / "visual-evidence-bundle.json"
    write_json(bundle_path, bundle)

    return {
        "source_sha256": source_sha,
        "profile_id": profile["id"],
        "quality_passed": vector["quality_passed"],
        "metrics": accepted_metrics,
        "svg_bytes": archival_path.stat().st_size,
        "layer_b_bytes": sum((bundle_dir / item["path"]).stat().st_size for item in layer_b_artifacts),
        "path_count": archival_stats["path_count"],
        "contour_component_count": archival_stats["contour_component_count"],
        "visual_authority_sha256": authority["visual_authority_sha256"],
        "visual_evidence_bundle_sha256": bundle["visual_evidence_bundle_sha256"],
    }



def process_source(
    source: Path,
    entry: dict[str, Any],
    output: Path,
    *,
    rejected_output: Path | None = None,
) -> dict[str, Any]:
    """Build one portable three-layer visual-evidence bundle.

    The output is derived from source content but does not record the source
    filename, local path, conversation identifier, or workflow approval state.
    ``output`` must name a directory that does not already exist.

    Only a bundle that satisfies the perceptual fidelity gate is published to
    ``output``. A bundle that fails the gate is moved to ``rejected_output``
    when one is given, and otherwise discarded with the working directory, so a
    rejected bundle never reaches a corpus path by default. ``rejected_output``
    must also name a directory that does not already exist. The report is
    returned with ``ok`` false rather than raised, because the ``metrics`` it
    carries are what tells the caller how far the source missed.
    """

    source = Path(source)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(
            f"output directory must not already exist: {output}"
        )
    if rejected_output is not None:
        rejected_output = Path(rejected_output)
        if rejected_output.exists() or rejected_output.is_symlink():
            raise FileExistsError(
                f"rejected output directory must not already exist: {rejected_output}"
            )
    source_sha = verify_source_content(source, entry)
    output.parent.mkdir(parents=True, exist_ok=True)
    published: Path | None = None
    rejected: Path | None = None
    with tempfile.TemporaryDirectory(prefix="cpb-visual-evidence-", dir=str(output.parent)) as temp_value:
        temp_root = Path(temp_value)
        result = process_one((str(source), entry, str(temp_root)))
        generated = temp_root / source_sha[:16]
        if not generated.is_dir():
            raise RuntimeError("single-source extraction did not produce a bundle directory")
        if result["quality_passed"]:
            shutil.move(str(generated), str(output))
            published = output
        elif rejected_output is not None:
            rejected_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(generated), str(rejected_output))
            rejected = rejected_output
    report: dict[str, Any] = {
        "ok": bool(result["quality_passed"]),
        "source_ref_id": f"SRC-{source_sha[:16]}",
        "profile_id": result["profile_id"],
        "metrics": result["metrics"],
        "svg_bytes": result["svg_bytes"],
        "layer_b_bytes": result["layer_b_bytes"],
        "output": str(published) if published is not None else None,
        "rejected_output": str(rejected) if rejected is not None else None,
    }
    if not result["quality_passed"]:
        report["errors"] = ["perceptual fidelity gate not satisfied"]
    return report

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=max(1, min(6, os.cpu_count() or 1)))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    pack_root = args.pack_root.resolve()
    corpus_root = pack_root / "resources" / "reference-corpus"
    manifest_path = corpus_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_map = json.loads(args.source_map.read_text(encoding="utf-8"))
    evidence_root = corpus_root / "visual-evidence"
    jobs = [
        (source_map[entry["source_sha256"]]["paths"][0], entry, str(evidence_root))
        for entry in manifest["entries"]
    ]
    # Verify the complete batch before creating or modifying the evidence tree.
    # Workers repeat this check immediately before their first output write.
    for source_value, entry, _ in jobs:
        verify_source_content(Path(source_value), entry)
    evidence_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one, job): job[1]["source_sha256"] for job in jobs}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            if index % 5 == 0 or index == len(futures):
                print(f"[compact-vector] {index}/{len(futures)}", flush=True)

    by_sha = {value["source_sha256"]: value for value in results}
    for entry in manifest["entries"]:
        result = by_sha[entry["source_sha256"]]
        entry["visual_authority_ref"]["sha256"] = result["visual_authority_sha256"]
        entry["visual_evidence_bundle_ref"]["sha256"] = result["visual_evidence_bundle_sha256"]
    manifest["evidence_bundle_count"] = len(results)
    manifest["coverage_policy"] = (
        "Every admitted user-provided source hash has one portable three-layer compact perceptual visual-evidence bundle."
    )
    manifest["notes"] = [
        "Only user-provided source hashes are admitted.",
        "Layer A preserves native dimensions with a uniform full-frame perceptual profile; Layers B and C provide audit and disposable runtime preparation.",
    ]
    finalize(manifest, "reference_corpus_manifest_sha256")
    write_json(manifest_path, manifest)

    results.sort(key=lambda item: item["source_sha256"])
    report = {
        "ok": all(value["quality_passed"] for value in results),
        "method": "native-uniform-compact-perceptual-palette-connected-contours",
        "source_count": len(results),
        "profile_counts": {
            profile["id"]: sum(value["profile_id"] == profile["id"] for value in results)
            for profile in PROFILES
        },
        "total_archival_svg_bytes": sum(value["svg_bytes"] for value in results),
        "total_layer_b_bytes": sum(value["layer_b_bytes"] for value in results),
        "min_archival_svg_bytes": min(value["svg_bytes"] for value in results),
        "max_archival_svg_bytes": max(value["svg_bytes"] for value in results),
        "quality_failures": [value["source_sha256"] for value in results if not value["quality_passed"]],
        "results": results,
    }
    write_json(args.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
