#!/usr/bin/env python3
"""Compose maskless per-panel model results into a pristine Character Sheet.

The image model never receives the full renderer-owned sheet in this workflow.
This command verifies the renderer's panel request manifest, fits one declared
result PNG into each editable content rectangle for the board, and leaves every
other scaffold pixel unchanged.

The result file is the panel. The board holds a reduced copy of it for viewing,
and with --update-sidecar each slot is bound to the full-size result rather than
to anything cut back out of the board.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageOps

from execution_contract import sha256_file
from harvest_sheet_render import bind_slot_images, load_json_object, validate_layout

COMPOSITOR_ID = "compose_sheet_panel_fills"
PANEL_FILL_TRANSPORT = "panel-images"


def resolve_committed_file(
    manifest_dir: Path,
    record: Any,
    *,
    label: str,
) -> Path:
    if not isinstance(record, Mapping):
        raise ValueError(f"{label} must be an object")
    raw_path = record.get("path")
    expected_hash = record.get("sha256")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"{label}.path must be a non-empty string")
    relative = Path(raw_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label}.path must be a safe path relative to the request manifest")
    path = (manifest_dir / relative).resolve()
    try:
        path.relative_to(manifest_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"{label}.path escapes the render output") from exc
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    if not isinstance(expected_hash, str) or sha256_file(path) != expected_hash:
        raise ValueError(f"{label} hash differs from the panel request manifest")
    return path


def validate_request_target(
    request: Mapping[str, Any],
    layout_box: Mapping[str, Any],
) -> tuple[int, int, int, int]:
    target = request.get("target")
    if not isinstance(target, Mapping):
        raise ValueError(f"panel request {request.get('request_id')!r} target must be an object")
    expected = {
        "content_x": int(round(float(layout_box["content_x"]))),
        "content_y": int(round(float(layout_box["content_y"]))),
        "content_w": int(round(float(layout_box["content_w"]))),
        "content_h": int(round(float(layout_box["content_h"]))),
    }
    if any(target.get(key) != value for key, value in expected.items()):
        raise ValueError(
            f"panel request {request.get('request_id')!r} target differs from sheet-layout.json"
        )
    return (
        expected["content_x"],
        expected["content_y"],
        expected["content_w"],
        expected["content_h"],
    )


def compose_panel_fills(
    request_manifest_path: Path,
    results_dir: Path,
    *,
    out_path: Path,
    composition_manifest_path: Path | None = None,
    update_sidecar_path: Path | None = None,
    generation_package: Path | None = None,
    only: Sequence[str] | None = None,
    allow_missing: bool = False,
) -> dict[str, Any]:
    if generation_package is not None and update_sidecar_path is None:
        raise ValueError("--generation-package requires --update-sidecar")
    if only is not None and update_sidecar_path is None:
        raise ValueError("--only requires --update-sidecar")
    request_manifest_path = request_manifest_path.resolve(strict=True)
    manifest_dir = request_manifest_path.parent
    manifest = load_json_object(request_manifest_path, label="panel request manifest")
    producer = manifest.get("producer")
    transport = manifest.get("transport")
    if not isinstance(producer, Mapping) or producer.get("id") != "render_character_sheet":
        raise ValueError("panel request manifest has an unknown producer")
    if not isinstance(transport, Mapping) or transport.get("id") != PANEL_FILL_TRANSPORT:
        raise ValueError("panel request manifest is not a panel-images transport")
    if transport.get("full_sheet_model_input") is not False:
        raise ValueError("panel-images transport must prohibit full-sheet model input")
    if transport.get("pixel_edit_mask_required") is not False:
        raise ValueError("panel-images transport must not require a model-side edit mask")

    scaffold_path = resolve_committed_file(
        manifest_dir, manifest.get("scaffold"), label="scaffold"
    )
    layout_path = resolve_committed_file(manifest_dir, manifest.get("layout"), label="layout")
    layout = load_json_object(layout_path, label="sheet layout")
    canvas_width, canvas_height, boxes = validate_layout(layout)
    editable_boxes = {
        str(box.get("resolved_slot_id", box["slot_id"])): box
        for box in boxes
        if box.get("harvest")
    }

    raw_requests = manifest.get("requests")
    if not isinstance(raw_requests, list) or not raw_requests:
        raise ValueError("panel request manifest must contain at least one request")
    requests: list[Mapping[str, Any]] = []
    request_ids: set[str] = set()
    result_names: set[str] = set()
    for index, raw_request in enumerate(raw_requests):
        if not isinstance(raw_request, Mapping):
            raise ValueError(f"panel request {index} must be an object")
        request_id = raw_request.get("request_id")
        result_file = raw_request.get("result_file")
        if not isinstance(request_id, str) or not request_id or request_id in request_ids:
            raise ValueError(f"panel request {index} has an invalid or duplicate request_id")
        if (
            not isinstance(result_file, str)
            or not result_file.lower().endswith(".png")
            or Path(result_file).name != result_file
            or result_file in result_names
        ):
            raise ValueError(f"panel request {request_id!r} has an invalid or duplicate result_file")
        prompt_path = resolve_committed_file(
            manifest_dir,
            raw_request.get("prompt"),
            label=f"panel request {request_id} prompt",
        )
        prompt_text = prompt_path.read_text(encoding="utf-8")
        if "Return artwork only" not in prompt_text or "profile block" not in prompt_text:
            raise ValueError(f"panel request {request_id!r} does not prohibit renderer-owned content")
        request_ids.add(request_id)
        result_names.add(result_file)
        requests.append(raw_request)
    if request_ids != set(editable_boxes):
        missing = sorted(set(editable_boxes) - request_ids)
        extra = sorted(request_ids - set(editable_boxes))
        raise ValueError(
            f"panel request set differs from editable layout panels; missing={missing}, extra={extra}"
        )

    results_dir = results_dir.resolve(strict=True)
    if not results_dir.is_dir():
        raise ValueError(f"results_dir must be a directory: {results_dir}")
    with Image.open(scaffold_path) as scaffold_source:
        scaffold = scaffold_source.convert("RGB")
    if scaffold.size != (canvas_width, canvas_height):
        raise ValueError("scaffold dimensions differ from sheet-layout.json")
    composed = scaffold.copy()
    result_records: list[dict[str, Any]] = []
    # A staged fill accepts the identity anchor before the other panels exist;
    # a panel without a result then stays as the scaffold drew it.
    missing_results: list[str] = []
    present: list[Mapping[str, Any]] = []
    for request in requests:
        request_id = str(request["request_id"])
        result_file = str(request["result_file"])
        result_path = (results_dir / result_file).resolve()
        try:
            result_path.relative_to(results_dir)
        except ValueError as exc:
            raise ValueError(f"panel result escapes results_dir: {result_file}") from exc
        if not result_path.is_file():
            if allow_missing:
                missing_results.append(request_id)
                continue
            raise ValueError(f"panel result is missing for {request_id}: {result_file}")
        present.append(request)
        x, y, width, height = validate_request_target(request, editable_boxes[request_id])
        with Image.open(result_path) as result_source:
            result = result_source.convert("RGB")
        fitted = ImageOps.contain(result, (width, height), method=Image.Resampling.LANCZOS)
        panel = Image.new("RGB", (width, height), (255, 255, 255))
        offset_x = (width - fitted.width) // 2
        offset_y = (height - fitted.height) // 2
        panel.paste(fitted, (offset_x, offset_y))
        composed.paste(panel, (x, y))
        result_records.append(
            {
                "request_id": request_id,
                "file": result_file,
                "sha256": sha256_file(result_path),
                "source_size": {"w": result.width, "h": result.height},
                "fitted_size": {"w": fitted.width, "h": fitted.height},
                "offset": {"x": offset_x, "y": offset_y},
                "target": {"x": x, "y": y, "w": width, "h": height},
            }
        )

    sidecar_report = None
    if update_sidecar_path is not None:
        update_sidecar_path = update_sidecar_path.resolve()
        if not update_sidecar_path.is_file():
            raise ValueError(f"--update-sidecar does not exist: {update_sidecar_path}")
        accepted = present
        if only is not None:
            wanted = {str(slot_id) for slot_id in only}
            known = {str(request["slot_id"]) for request in requests} | {
                str(request.get("resolved_slot_id", request["slot_id"])) for request in requests
            }
            unknown = sorted(wanted - known)
            if unknown:
                raise ValueError(f"--only names slots without a panel request: {', '.join(unknown)}")
            present_ids = {str(request["slot_id"]) for request in present} | {
                str(request.get("resolved_slot_id", request["slot_id"])) for request in present
            }
            absent = sorted(wanted - present_ids)
            if absent:
                raise ValueError(f"--only names slots whose result file is missing: {', '.join(absent)}")
            accepted = [
                request
                for request in present
                if str(request["slot_id"]) in wanted
                or str(request.get("resolved_slot_id", request["slot_id"])) in wanted
            ]
        sidecar_report = bind_slot_images(
            update_sidecar_path,
            images=[
                (
                    editable_boxes[str(request["request_id"])],
                    (results_dir / str(request["result_file"])).resolve(),
                )
                for request in accepted
            ],
            generation_package=generation_package.resolve() if generation_package else None,
        )

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(out_path, format="PNG")
    composition_manifest_path = (
        composition_manifest_path.resolve()
        if composition_manifest_path is not None
        else out_path.with_suffix(".panel-fill.json")
    )
    composition = {
        "compositor": {"id": COMPOSITOR_ID},
        "request_manifest": {
            "path": str(request_manifest_path),
            "sha256": sha256_file(request_manifest_path),
        },
        "scaffold_sha256": sha256_file(scaffold_path),
        "layout_sha256": sha256_file(layout_path),
        "results": result_records,
        "missing_results": missing_results,
        "output": {"path": str(out_path), "sha256": sha256_file(out_path)},
        "sidecar_update": sidecar_report,
    }
    composition_manifest_path.write_text(
        json.dumps(composition, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "output": out_path,
        "manifest": composition_manifest_path,
        "results": result_records,
        "missing_results": missing_results,
        "sidecar_update": sidecar_report,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_manifest", type=Path)
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument(
        "--update-sidecar",
        type=Path,
        help="accepted sheet-data.json; binds each slot to its full-size result file",
    )
    parser.add_argument(
        "--generation-package",
        type=Path,
        help="Generation Package for the results; requires --update-sidecar and must be inside the sheet folder",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="SLOT_ID",
        help="bind only these accepted slots; the board still shows every result",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="leave panels without a result as the scaffold drew them (a staged fill)",
    )
    args = parser.parse_args(argv)
    result = compose_panel_fills(
        args.request_manifest,
        args.results_dir,
        out_path=args.out,
        composition_manifest_path=args.manifest_out,
        update_sidecar_path=args.update_sidecar,
        generation_package=args.generation_package,
        only=args.only,
        allow_missing=args.allow_missing,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(result["output"]),
                "manifest": str(result["manifest"]),
                "result_count": len(result["results"]),
                "missing_results": result["missing_results"],
                "sidecar_update": result["sidecar_update"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
