#!/usr/bin/env python3
"""Exercise portable Upscale Package construction, verification, and rejection paths."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from catalog_cli import configure_pack_runtime
from pack_manager import default_settings, write_lock
from state_protocol import finalize_artifact
from upscale_package import build_upscale_package, verify_upscale_package

ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "0190c000-0000-7000-8000-000000000077"
EXPECTED_CHECKS = 18


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def expect_error(fn: Callable[[], Any], text: str) -> bool:
    try:
        fn()
    except (ValueError, TypeError, OSError) as exc:
        return text in str(exc)
    return False


def make_image(path: Path, size: tuple[int, int], value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (value, value, value)).save(path, format="PNG")


def model_rows() -> list[dict[str, Any]]:
    """Return self-contained synthetic upscaler records."""

    return [
        {
            "id": "fixture-restorative-upscaler",
            "label": "Restorative upscaler fixture",
            "aliases": ["restorative fixture"],
            "operation_kind": "upscale",
            "offerings": [],
            "prompt_style": "image-to-image upscale operation",
            "ordering": ["input-image", "scale-parameters"],
            "search_terms": [
                {"phrase": "restorative fixture", "facet": "model", "weight": 1.0, "source": "tag"}
            ],
            "upscaler_class": "restorative",
            "supported_scale_factors": [2, 4],
            "input_image_count": 1,
            "supports_guidance_prompt": False,
            "upscale_settings": {"variant": ["general"]},
        },
        {
            "id": "fixture-creative-upscaler",
            "label": "Creative upscaler fixture",
            "aliases": ["creative fixture"],
            "operation_kind": "upscale",
            "offerings": [],
            "prompt_style": "optional guidance prompt for a creative upscale operation",
            "ordering": ["input-image", "scale-parameters"],
            "search_terms": [
                {"phrase": "creative fixture", "facet": "model", "weight": 1.0, "source": "tag"}
            ],
            "upscaler_class": "creative",
            "supported_scale_factors": [2, 4, 8],
            "input_image_count": 1,
            "supports_guidance_prompt": True,
            "upscale_settings": {
                "color_preservation": [False, True],
                "creativity": ["subtle", "low", "medium", "high", "max"],
                "face_recovery": [False, True],
                "plan": ["personal", "pro"],
                "variations": [1, 2, 3, 4],
            },
            "output_limits": {"personal_megapixels": 32, "pro_megapixels": 100},
        },
        {
            "id": "fixture-generative-upscaler",
            "label": "Generative upscaler fixture",
            "aliases": ["generative fixture"],
            "operation_kind": "upscale",
            "offerings": [],
            "prompt_style": "image-to-image upscale operation",
            "ordering": ["input-image", "scale-parameters"],
            "search_terms": [
                {"phrase": "generative fixture", "facet": "model", "weight": 1.0, "source": "tag"}
            ],
            "upscaler_class": "generative",
            "supported_scale_factors": [2, 3, 4],
            "input_image_count": 1,
            "supports_guidance_prompt": False,
            "upscale_settings": {
                "enhancement_strength": ["low", "medium", "high"],
                "grain": ["provider-defined numeric value"],
            },
        },
    ]


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory(prefix="cpb-upscale-smoke-") as raw:
        temp = Path(raw).resolve()
        pack_parent = temp / "packs"
        pack = pack_parent / "upscalers"
        write_json(
            pack / "pack.json",
            {
                "pack_id": PACK_ID,
                "name": "Upscale Package Smoke Pack",
                "description": "Isolated upscaler fixture.",
                "release": "2026.08.24.1",
                "content": {
                    "record_globs": ["records/**/*.json"],
                    "resource_globs": ["resources/**/*"],
                    "resource_bindings": {},
                },
                "capabilities": ["model-adapters"],
                "dependencies": [],
                "optional_dependencies": [],
                "replaces": [],
                "license": "GPL-3.0-only",
            },
        )
        write_json(pack / "records/models.json", {"kind": "model", "records": model_rows()})
        write_lock(pack)
        state_file = temp / "state.json"
        write_json(
            state_file,
            {
                "pack_roots": [str(pack_parent)],
                "enabled_packs": [PACK_ID],
                "resource_providers": {},
            },
        )
        settings = default_settings(
            state_file=state_file,
            cache_dir=temp / "cache",
            managed_root=temp / "managed",
        )
        configure_pack_runtime(settings)

        package_root = temp / "package"
        source = package_root / "images/source.png"
        output = package_root / "images/output.png"
        make_image(source, (2, 2), 40)
        make_image(output, (4, 4), 80)

        restorative = build_upscale_package(
            model="fixture-restorative-upscaler",
            source_image=source,
            output_image=output,
            package_root=package_root,
            source_stored_path="images/source.png",
            output_stored_path="images/output.png",
            scale_factor=2,
            settings={"variant": "general"},
            guidance_prompt=None,
            audit_status="not-required",
            audit_notes=[],
        )
        check("restorative package becomes ready", restorative["status"] == "ready")
        verified = verify_upscale_package(restorative, package_root=package_root)
        check("restorative package round-trips", verified == restorative)
        check("package commits source bytes", restorative["source_image"]["sha256"] != "0" * 64)
        check("package commits output bytes", restorative["output_image"]["sha256"] != "0" * 64)
        check("package uses portable relative paths", not Path(restorative["source_image"]["path"]).is_absolute())

        original_output = output.read_bytes()
        make_image(output, (4, 4), 120)
        check(
            "output mutation is rejected",
            expect_error(lambda: verify_upscale_package(restorative, package_root=package_root), "output image bytes"),
        )
        output.write_bytes(original_output)
        verify_upscale_package(restorative, package_root=package_root)

        check(
            "unsupported scale is rejected",
            expect_error(
                lambda: build_upscale_package(
                    model="fixture-restorative-upscaler",
                    source_image=source,
                    output_image=output,
                    package_root=package_root,
                    source_stored_path="images/source.png",
                    output_stored_path="images/output.png",
                    scale_factor=3,
                    settings={"variant": "general"},
                    guidance_prompt=None,
                    audit_status="not-required",
                    audit_notes=[],
                ),
                "not supported",
            ),
        )
        check(
            "undeclared setting is rejected",
            expect_error(
                lambda: build_upscale_package(
                    model="fixture-restorative-upscaler",
                    source_image=source,
                    output_image=output,
                    package_root=package_root,
                    source_stored_path="images/source.png",
                    output_stored_path="images/output.png",
                    scale_factor=2,
                    settings={"creativity": "high"},
                    guidance_prompt=None,
                    audit_status="not-required",
                    audit_notes=[],
                ),
                "undeclared upscaler setting",
            ),
        )
        check(
            "unsupported guidance prompt is rejected",
            expect_error(
                lambda: build_upscale_package(
                    model="fixture-restorative-upscaler",
                    source_image=source,
                    output_image=output,
                    package_root=package_root,
                    source_stored_path="images/source.png",
                    output_stored_path="images/output.png",
                    scale_factor=2,
                    settings={"variant": "general"},
                    guidance_prompt="invent richer detail",
                    audit_status="not-required",
                    audit_notes=[],
                ),
                "does not accept a guidance prompt",
            ),
        )
        check(
            "path traversal is rejected",
            expect_error(
                lambda: build_upscale_package(
                    model="fixture-restorative-upscaler",
                    source_image=source,
                    output_image=output,
                    package_root=package_root,
                    source_stored_path="../source.png",
                    output_stored_path="images/output.png",
                    scale_factor=2,
                    settings={"variant": "general"},
                    guidance_prompt=None,
                    audit_status="not-required",
                    audit_notes=[],
                ),
                "canonical and relative",
            ),
        )

        creative_pending = build_upscale_package(
            model="fixture-creative-upscaler",
            source_image=source,
            output_image=output,
            package_root=package_root,
            source_stored_path="images/source.png",
            output_stored_path="images/output.png",
            scale_factor=2,
            settings={
                "color_preservation": True,
                "creativity": "low",
                "face_recovery": False,
                "plan": "personal",
                "variations": 1,
            },
            guidance_prompt="preserve the existing silhouette and markings",
            audit_status="pending",
            audit_notes=["Identity census not yet completed."],
        )
        check("creative pending audit requires review", creative_pending["status"] == "review-required")
        verify_upscale_package(creative_pending, package_root=package_root)
        check("review-required creative package remains verifiable", True)

        creative_ready = build_upscale_package(
            model="fixture-creative-upscaler",
            source_image=source,
            output_image=output,
            package_root=package_root,
            source_stored_path="images/source.png",
            output_stored_path="images/output.png",
            scale_factor=2,
            settings={
                "color_preservation": True,
                "creativity": "low",
                "face_recovery": False,
                "plan": "personal",
                "variations": 1,
            },
            guidance_prompt="preserve the existing silhouette and markings",
            audit_status="passed",
            audit_notes=["Census verified against the canonical sheet."],
        )
        check("creative passed audit becomes ready", creative_ready["status"] == "ready")
        verify_upscale_package(creative_ready, package_root=package_root)
        check("ready creative package verifies", True)

        tampered = copy.deepcopy(creative_ready)
        tampered["settings"]["creativity"] = "max"
        tampered = finalize_artifact(tampered)
        check(
            "committed setting mutation invalidates the operation identity",
            expect_error(
                lambda: verify_upscale_package(tampered, package_root=package_root),
                "package_id",
            ),
        )

        failed_restorative = build_upscale_package(
            model="fixture-restorative-upscaler",
            source_image=source,
            output_image=output,
            package_root=package_root,
            source_stored_path="images/source.png",
            output_stored_path="images/output.png",
            scale_factor=2,
            settings={"variant": "general"},
            guidance_prompt=None,
            audit_status="failed",
            audit_notes=["Unexpected line drift."],
        )
        check("failed optional audit blocks readiness", failed_restorative["status"] == "review-required")

        wonder = build_upscale_package(
            model="fixture-generative-upscaler",
            source_image=source,
            output_image=output,
            package_root=package_root,
            source_stored_path="images/source.png",
            output_stored_path="images/output.png",
            scale_factor=2,
            settings={"enhancement_strength": "low", "grain": 0.25},
            guidance_prompt=None,
            audit_status="passed",
            audit_notes=["Identity surfaces remain stable."],
        )
        check("declared numeric setting is accepted", wonder["settings"]["grain"] == 0.25)
        check("generative passed audit becomes ready", wonder["status"] == "ready")

    configure_pack_runtime(None)
    report = {
        "ok": len(results) == EXPECTED_CHECKS and all(row["passed"] for row in results),
        "checks": len(results),
        "expected_checks": EXPECTED_CHECKS,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
