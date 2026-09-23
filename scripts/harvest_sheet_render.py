#!/usr/bin/env python3
"""Crop a model-filled Character Sheet PNG into deterministic slot images.

The command reads sheet-layout.json from render_character_sheet.py, verifies that
the filled image preserves the scaffold aspect ratio and renderer-owned protected
regions, crops only harvestable white drawing regions, and writes a hash-bearing
harvest manifest. Optional sidecar update is explicit so an unreviewed filled
sheet remains candidate material until the owner accepts it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from character_sheet import sheet_status, validate_sidecar
from execution_contract import atomic_write_json, sha256_file


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def validate_layout(layout: Mapping[str, Any]) -> tuple[int, int, list[dict[str, Any]]]:
    canvas = layout.get("canvas")
    if not isinstance(canvas, Mapping):
        raise ValueError("layout.canvas must be an object")
    width = canvas.get("w")
    height = canvas.get("h")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise ValueError("layout.canvas must contain positive integer w and h")
    raw_boxes = layout.get("boxes")
    if not isinstance(raw_boxes, list) or not raw_boxes:
        raise ValueError("layout.boxes must be a non-empty array")

    boxes: list[dict[str, Any]] = []
    slot_ids: set[str] = set()
    output_names: set[str] = set()
    for index, raw_box in enumerate(raw_boxes):
        if not isinstance(raw_box, dict):
            raise ValueError(f"layout.boxes[{index}] must be an object")
        slot_id = raw_box.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            raise ValueError(f"layout.boxes[{index}].slot_id must be a non-empty string")
        if slot_id in slot_ids:
            raise ValueError(f"layout contains duplicate slot_id {slot_id!r}")
        slot_ids.add(slot_id)
        harvest = raw_box.get("harvest", True)
        if not isinstance(harvest, bool):
            raise ValueError(f"layout box {slot_id} harvest must be boolean")
        for key in ("content_x", "content_y", "content_w", "content_h"):
            value = raw_box.get(key)
            if not isinstance(value, (int, float)):
                raise ValueError(f"layout box {slot_id} {key} must be numeric")
        x = float(raw_box["content_x"])
        y = float(raw_box["content_y"])
        box_width = float(raw_box["content_w"])
        box_height = float(raw_box["content_h"])
        if x < 0 or y < 0 or box_width <= 0 or box_height <= 0:
            raise ValueError(f"layout box {slot_id} has invalid crop geometry")
        if x + box_width > width or y + box_height > height:
            raise ValueError(f"layout box {slot_id} crop escapes the canvas")
        output_name = raw_box.get("output_name") or slot_id.replace(".", "-") + ".png"
        if not isinstance(output_name, str) or not output_name.lower().endswith(".png"):
            raise ValueError(f"layout box {slot_id} output_name must be a PNG filename")
        if Path(output_name).name != output_name or output_name in {".", ".."}:
            raise ValueError(f"layout box {slot_id} output_name must be a plain filename")
        if harvest:
            if output_name in output_names:
                raise ValueError(f"layout contains duplicate harvest output_name {output_name!r}")
            output_names.add(output_name)
        box = dict(raw_box)
        box["output_name"] = output_name
        box["aliases"] = [
            alias for alias in raw_box.get("aliases", []) if isinstance(alias, str) and alias
        ]
        boxes.append(box)
    return width, height, boxes


def relative_file(path: Path, *, root: Path, label: str) -> str:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must identify a regular file")
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be inside the Character Sheet folder") from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label} must be a safe relative path")
    return relative.as_posix()


def ensure_output_inside_sheet(out_dir: Path, *, sheet_root: Path) -> None:
    root = sheet_root.resolve(strict=True)
    resolved = out_dir.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("--out must be inside the Character Sheet folder when --update-sidecar is used") from exc
    cursor = root
    for part in resolved.relative_to(root).parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise ValueError("--out must not traverse a symbolic link")


def sidecar_slot_id(sidecar: Mapping[str, Any], box: Mapping[str, Any]) -> str:
    slots = sidecar.get("slots")
    if isinstance(slots, Mapping):
        for slot_id in (box["slot_id"], *box.get("aliases", [])):
            if slot_id in slots:
                return slot_id
    return str(box["slot_id"])


def bind_slot_images(
    sidecar_path: Path,
    *,
    images: Sequence[tuple[Mapping[str, Any], Path]],
    generation_package: Path | None,
) -> dict[str, Any]:
    """Point each slot at the image that is its accepted evidence.

    `images` pairs a layout box with the file to bind. The file is whatever the
    caller holds at full size: a model result in the panel-images transport, or a
    crop of the filled sheet in the masked-sheet transport.
    """

    sheet_root = sidecar_path.parent.resolve(strict=True)
    sidecar = load_json_object(sidecar_path, label="sheet-data.json")
    normalized = validate_sidecar(sidecar, sheet_root=sheet_root, verify_files=False)
    package_relative = None
    if generation_package is not None:
        package_relative = relative_file(
            generation_package, root=sheet_root, label="--generation-package"
        )
    slots = normalized.setdefault("slots", {})
    for box, image_path in images:
        slot_id = sidecar_slot_id(normalized, box)
        slot = slots.setdefault(slot_id, {"image_path": "", "generation_package": ""})
        slot["image_path"] = relative_file(image_path, root=sheet_root, label=f"slot {slot_id} image")
        if package_relative is not None:
            slot["generation_package"] = package_relative
        slot.pop("image_sha256", None)
        slot.pop("generation_package_sha256", None)
    normalized["sheet_status"] = sheet_status(normalized)
    validate_sidecar(normalized, sheet_root=sheet_root, verify_files=False)
    atomic_write_json(sidecar_path, normalized)
    return {
        "path": str(sidecar_path),
        "sha256": sha256_file(sidecar_path),
        "sheet_status": normalized["sheet_status"],
        "generation_package": package_relative,
    }


def update_sidecar(
    sidecar_path: Path,
    *,
    out_dir: Path,
    crops: Sequence[Mapping[str, Any]],
    generation_package: Path | None,
) -> dict[str, Any]:
    return bind_slot_images(
        sidecar_path,
        images=[(crop["layout_box"], out_dir / crop["file"]) for crop in crops],
        generation_package=generation_package,
    )


def harvest_sheet(
    filled_png: Path,
    *,
    layout_path: Path,
    out_dir: Path,
    only: Sequence[str] | None = None,
    aspect_tolerance: float = 0.01,
    scaffold_path: Path | None = None,
    edit_mask_path: Path | None = None,
    update_sidecar_path: Path | None = None,
    generation_package: Path | None = None,
) -> dict[str, Any]:
    if aspect_tolerance < 0 or aspect_tolerance > 0.1:
        raise ValueError("aspect_tolerance must be between 0 and 0.1")
    if generation_package is not None and update_sidecar_path is None:
        raise ValueError("--generation-package requires --update-sidecar")
    if not filled_png.is_file():
        raise ValueError(f"filled PNG does not exist: {filled_png}")
    if not layout_path.is_file():
        raise ValueError(f"layout manifest does not exist: {layout_path}")
    layout = load_json_object(layout_path, label="sheet-layout.json")
    canvas_width, canvas_height, boxes = validate_layout(layout)
    harvestable = [box for box in boxes if box.get("harvest", True)]
    known = {box["slot_id"] for box in harvestable}
    requested = set(only or [])
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError("--only contains unknown or non-harvestable slot ids: " + ", ".join(unknown))
    selected = [box for box in harvestable if not requested or box["slot_id"] in requested]
    if not selected:
        raise ValueError("no harvestable panels were selected")

    from PIL import Image, ImageChops, ImageFilter, ImageOps

    with Image.open(filled_png) as source:
        image = source.convert("RGB")
    scale_x = image.width / canvas_width
    scale_y = image.height / canvas_height
    aspect_drift = abs(scale_x / scale_y - 1.0)
    if aspect_drift > aspect_tolerance:
        raise ValueError(
            "filled image aspect ratio differs from the scaffold: "
            f"drift={aspect_drift:.6f}, tolerance={aspect_tolerance:.6f}"
        )

    scaffold_path = (scaffold_path or layout_path.with_name("sheet-render.png")).resolve()
    edit_mask_path = (edit_mask_path or layout_path.with_name("sheet-edit-mask.png")).resolve()
    if not scaffold_path.is_file():
        raise ValueError(f"scaffold PNG does not exist: {scaffold_path}")
    if not edit_mask_path.is_file():
        raise ValueError(f"edit mask PNG does not exist: {edit_mask_path}")
    with Image.open(scaffold_path) as scaffold_source:
        scaffold = scaffold_source.convert("RGB")
    with Image.open(edit_mask_path) as mask_source:
        edit_mask = mask_source.convert("L")
    if scaffold.size != (canvas_width, canvas_height):
        raise ValueError("scaffold PNG dimensions do not match layout.canvas")
    if edit_mask.size != (canvas_width, canvas_height):
        raise ValueError("edit mask dimensions do not match layout.canvas")

    scaffold_scaled = scaffold.resize(image.size, Image.Resampling.LANCZOS)
    mask_scaled = edit_mask.resize(image.size, Image.Resampling.NEAREST)
    editable_guard = mask_scaled.point(lambda value: 255 if value >= 128 else 0).filter(
        ImageFilter.MaxFilter(5)
    )
    protected_mask = ImageOps.invert(editable_guard)
    difference = ImageChops.difference(scaffold_scaled, image)
    red, green, blue = difference.split()
    maximum_difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    histogram = maximum_difference.histogram(mask=protected_mask)
    protected_pixels = sum(histogram)
    if protected_pixels <= 0:
        raise ValueError("edit mask declares no protected pixels to verify")
    changed_pixels = sum(histogram[33:])
    protected_mean_difference = sum(
        value * count for value, count in enumerate(histogram)
    ) / protected_pixels
    protected_changed_ratio = changed_pixels / protected_pixels
    protected_mean_tolerance = 5.0
    protected_changed_ratio_tolerance = 0.01
    if (
        protected_mean_difference > protected_mean_tolerance
        or protected_changed_ratio > protected_changed_ratio_tolerance
    ):
        raise ValueError(
            "filled image protected regions differ from the scaffold; panel coordinates, "
            "labels, borders, profile facts, or color key were changed: "
            f"mean_difference={protected_mean_difference:.6f}, "
            f"changed_ratio={protected_changed_ratio:.6f}"
        )
    protected_verification = {
        "scaffold": str(scaffold_path),
        "scaffold_sha256": sha256_file(scaffold_path),
        "edit_mask": str(edit_mask_path),
        "edit_mask_sha256": sha256_file(edit_mask_path),
        "protected_pixels": protected_pixels,
        "mean_difference": protected_mean_difference,
        "mean_tolerance": protected_mean_tolerance,
        "changed_pixel_threshold": 32,
        "changed_ratio": protected_changed_ratio,
        "changed_ratio_tolerance": protected_changed_ratio_tolerance,
    }

    if update_sidecar_path is not None:
        update_sidecar_path = update_sidecar_path.resolve()
        if not update_sidecar_path.is_file():
            raise ValueError(f"--update-sidecar does not exist: {update_sidecar_path}")
        ensure_output_inside_sheet(out_dir, sheet_root=update_sidecar_path.parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    crops: list[dict[str, Any]] = []
    for box in selected:
        left = round(float(box["content_x"]) * scale_x)
        top = round(float(box["content_y"]) * scale_y)
        right = round((float(box["content_x"]) + float(box["content_w"])) * scale_x)
        bottom = round((float(box["content_y"]) + float(box["content_h"])) * scale_y)
        left = max(0, min(left, image.width))
        top = max(0, min(top, image.height))
        right = max(left + 1, min(right, image.width))
        bottom = max(top + 1, min(bottom, image.height))
        crop_image = image.crop((left, top, right, bottom))
        output_path = out_dir / box["output_name"]
        crop_image.save(output_path, format="PNG")
        crops.append(
            {
                "slot_id": box["slot_id"],
                "aliases": list(box.get("aliases", [])),
                "file": box["output_name"],
                "sha256": sha256_file(output_path),
                "source_crop": {"x": left, "y": top, "w": right - left, "h": bottom - top},
                "layout_crop": {
                    "x": box["content_x"],
                    "y": box["content_y"],
                    "w": box["content_w"],
                    "h": box["content_h"],
                },
                "layout_box": box,
            }
        )

    sidecar_report = None
    if update_sidecar_path is not None:
        sidecar_report = update_sidecar(
            update_sidecar_path,
            out_dir=out_dir.resolve(),
            crops=crops,
            generation_package=generation_package.resolve() if generation_package else None,
        )

    manifest_crops = []
    for crop in crops:
        manifest_crops.append({key: value for key, value in crop.items() if key != "layout_box"})
    manifest = {
        "harvester": {"id": "harvest_sheet_render"},
        "source": str(filled_png.resolve()),
        "source_sha256": sha256_file(filled_png),
        "layout": str(layout_path.resolve()),
        "layout_sha256": sha256_file(layout_path),
        "canvas": {"w": canvas_width, "h": canvas_height},
        "filled_image": {"w": image.width, "h": image.height},
        "scale": {"x": scale_x, "y": scale_y, "aspect_drift": aspect_drift},
        "aspect_tolerance": aspect_tolerance,
        "protected_region_verification": protected_verification,
        "crops": manifest_crops,
        "sidecar_update": sidecar_report,
    }
    manifest_path = out_dir / "harvest-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path,
        "crops": manifest_crops,
        "sidecar_update": sidecar_report,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filled_png", type=Path, help="model-filled Character Sheet PNG")
    parser.add_argument("--layout", type=Path, help="sheet-layout.json (default: beside the filled PNG)")
    parser.add_argument("--out", type=Path, required=True, help="output directory for harvested slot PNGs")
    parser.add_argument("--only", nargs="+", help="canonical slot ids to harvest (default: every harvestable panel)")
    parser.add_argument(
        "--aspect-tolerance",
        type=float,
        default=0.01,
        help="maximum relative X/Y scale drift before refusing the crop (default: 0.01)",
    )
    parser.add_argument(
        "--scaffold",
        type=Path,
        help="renderer scaffold PNG (default: sheet-render.png beside the layout)",
    )
    parser.add_argument(
        "--edit-mask",
        type=Path,
        help="renderer edit mask PNG (default: sheet-edit-mask.png beside the layout)",
    )
    parser.add_argument(
        "--update-sidecar",
        type=Path,
        help="accepted sheet-data.json to update after harvesting; omission keeps all crops as candidates",
    )
    parser.add_argument(
        "--generation-package",
        type=Path,
        help="Generation Package for the filled sheet; requires --update-sidecar and must be inside the sheet folder",
    )
    args = parser.parse_args(argv)

    filled_png = args.filled_png.resolve()
    layout_path = (args.layout or args.filled_png.with_name("sheet-layout.json")).resolve()
    out_dir = args.out.resolve()
    result = harvest_sheet(
        filled_png,
        layout_path=layout_path,
        out_dir=out_dir,
        only=args.only,
        aspect_tolerance=args.aspect_tolerance,
        scaffold_path=args.scaffold.resolve() if args.scaffold else None,
        edit_mask_path=args.edit_mask.resolve() if args.edit_mask else None,
        update_sidecar_path=args.update_sidecar,
        generation_package=args.generation_package,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "crops": len(result["crops"]),
                "out": str(out_dir),
                "manifest": str(result["manifest"]),
                "sidecar_update": result["sidecar_update"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
