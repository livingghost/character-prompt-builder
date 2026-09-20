#!/usr/bin/env python3
"""Build one self-contained Character Prompt Builder Upscale Package."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Sequence

from catalog_cli import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from upscale_package import build_upscale_package, verify_upscale_package


def _copy_regular(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"image input must not be a symbolic link: {source}")
    resolved = source.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"image input must be a regular file: {resolved}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--source-image", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--scale-factor", type=float, required=True)
    parser.add_argument("--settings", default="{}", help="JSON object of declared upscaler settings")
    parser.add_argument("--guidance-prompt")
    parser.add_argument(
        "--audit-status",
        choices=["auto", "not-required", "pending", "passed", "failed"],
        default="auto",
    )
    parser.add_argument("--audit-note", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    settings = json.loads(args.settings)
    if not isinstance(settings, dict):
        raise ValueError("--settings must be a JSON object")
    output_path = args.out.resolve()
    companion_name = output_path.stem + ".images"
    companion_path = output_path.with_name(companion_name)
    if output_path.exists() or companion_path.exists():
        raise ValueError("output JSON and companion directory must not already exist")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_path.stem}.staging-", dir=output_path.parent))
    promoted_companion = False
    try:
        staged_companion = staging / companion_name
        source_suffix = args.source_image.suffix.lower()
        output_suffix = args.output_image.suffix.lower()
        staged_source = staged_companion / ("source" + source_suffix)
        staged_output = staged_companion / ("output" + output_suffix)
        _copy_regular(args.source_image, staged_source)
        _copy_regular(args.output_image, staged_output)
        from prepare_generation_references import resolve_model_record
        _model_id, record = resolve_model_record(args.model)
        required = record.get("upscaler_class") in {"generative", "creative"}
        audit_status = args.audit_status
        if audit_status == "auto":
            audit_status = "pending" if required else "not-required"
        package = build_upscale_package(
            model=args.model,
            source_image=staged_source,
            output_image=staged_output,
            package_root=staging,
            source_stored_path=f"{companion_name}/{staged_source.name}",
            output_stored_path=f"{companion_name}/{staged_output.name}",
            scale_factor=args.scale_factor,
            settings=settings,
            guidance_prompt=args.guidance_prompt,
            audit_status=audit_status,
            audit_notes=list(args.audit_note),
        )
        staged_json = staging / output_path.name
        staged_json.write_text(
            json.dumps(package, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_upscale_package(package, package_root=staging)
        os.replace(staged_companion, companion_path)
        promoted_companion = True
        try:
            os.replace(staged_json, output_path)
        except Exception:
            shutil.rmtree(companion_path, ignore_errors=True)
            promoted_companion = False
            raise
        try:
            verify_upscale_package(package, package_root=output_path.parent)
        except Exception:
            output_path.unlink(missing_ok=True)
            shutil.rmtree(companion_path, ignore_errors=True)
            promoted_companion = False
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if promoted_companion and not output_path.exists():
            shutil.rmtree(companion_path, ignore_errors=True)
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
