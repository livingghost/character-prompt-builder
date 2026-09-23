#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from native_vector_visual_evidence import process_source
from validate_reference_corpus import _declared_catalog_thumbnails
from visual_evidence import inspect_svg, object_hash, render_svg, validate_bundle


def main() -> int:
    checks = 0
    skipped: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        height, width = 180, 240
        y, x = np.mgrid[0:height, 0:width]
        rgb = np.zeros((height, width, 3), np.uint8)
        rgb[:, :, 0] = x * 255 // max(1, width - 1)
        rgb[:, :, 1] = y * 255 // max(1, height - 1)
        rgb[:, :, 2] = (x + y) * 255 // max(1, width + height - 2)
        rgb[40:140, 70:175] = [39, 112, 202]
        rgb[68:112, 105:143] = [244, 198, 62]
        source = root / "source.png"
        Image.fromarray(rgb).save(source)
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()

        bundle_dir = root / "bundle"
        report = process_source(
            source,
            {
                "source_sha256": source_sha,
                "source_media_type": "image/png",
                "canonical_record_ids": ["smoke-record"],
                "disposition": "reference-evidence",
            },
            bundle_dir,
        )
        if not report.get("ok"):
            raise RuntimeError(f"single-source extraction failed: {report}")
        checks += 1

        bundle_report = validate_bundle(bundle_dir)
        if not bundle_report.get("ok"):
            raise RuntimeError(f"single-source bundle validation failed: {bundle_report}")
        checks += 1

        tamper_root = root / "tampered"
        tamper_root.mkdir()
        tamper_serial = 0

        def tampered(mutate: "Callable[[Path], None]") -> dict:
            """Copy the good bundle, break it, re-seal its self-hash, validate it."""

            nonlocal tamper_serial
            tamper_serial += 1
            copy = tamper_root / f"case-{tamper_serial:02d}"
            shutil.copytree(bundle_dir, copy)
            mutate(copy)
            bundle_json = copy / "visual-evidence-bundle.json"
            value = json.loads(bundle_json.read_text(encoding="utf-8"))
            value["visual_evidence_bundle_sha256"] = object_hash(
                value, "visual_evidence_bundle_sha256"
            )
            bundle_json.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            return validate_bundle(copy)

        def bundle_artifact(value: dict, role: str) -> dict:
            for entry in value["artifacts"]:
                if entry.get("role") == role:
                    return entry
            raise RuntimeError(f"bundle does not declare {role}")

        def edit_bundle(copy: Path, mutate: "Callable[[dict], None]") -> None:
            bundle_json = copy / "visual-evidence-bundle.json"
            value = json.loads(bundle_json.read_text(encoding="utf-8"))
            mutate(value)
            bundle_json.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        def swap_roles(copy: Path) -> None:
            def mutate(value: dict) -> None:
                first = bundle_artifact(value, "subject-mask")
                second = bundle_artifact(value, "specular-audit")
                first["path"], second["path"] = second["path"], first["path"]
                first["sha256"], second["sha256"] = second["sha256"], first["sha256"]

            edit_bundle(copy, mutate)

        swap_report = tampered(swap_roles)
        if swap_report.get("ok") or not any(
            "must name derived-visual/subject-mask.svg" in error
            for error in swap_report.get("errors", [])
        ):
            raise RuntimeError(f"swapped Layer B roles were accepted: {swap_report}")
        checks += 1

        def collide_roles(copy: Path) -> None:
            def mutate(value: dict) -> None:
                target = bundle_artifact(value, "specular-audit")
                first = bundle_artifact(value, "subject-mask")
                first["path"] = target["path"]
                first["sha256"] = target["sha256"]

            edit_bundle(copy, mutate)

        collide_report = tampered(collide_roles)
        if collide_report.get("ok"):
            raise RuntimeError(f"two roles naming one file were accepted: {collide_report}")
        checks += 1

        def replace_color_audit(copy: Path) -> None:
            replacement = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4" '
                'viewBox="0 0 4 4"><path fill="#654321" d="M0 0h4v4H0z"/></svg>'
            )
            target = copy / "derived-visual/color-audit.svg"
            target.write_text(replacement, encoding="utf-8", newline="\n")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()

            def mutate(value: dict) -> None:
                bundle_artifact(value, "color-audit")["sha256"] = digest

            edit_bundle(copy, mutate)

        replaced_report = tampered(replace_color_audit)
        if replaced_report.get("ok") or not any(
            "audit extraction set hash disagrees with the bundle for color-audit" in error
            for error in replaced_report.get("errors", [])
        ):
            raise RuntimeError(
                f"a Layer B file rebuilt behind the audit set was accepted: {replaced_report}"
            )
        checks += 1

        def break_source_identity(copy: Path) -> None:
            vector_path = copy / "derived-visual/vectorization-result.json"
            vector_value = json.loads(vector_path.read_text(encoding="utf-8"))
            vector_value["source_sha256"] = "f" * 64
            vector_value["vectorization_result_sha256"] = object_hash(
                vector_value, "vectorization_result_sha256"
            )
            vector_path.write_text(
                json.dumps(vector_value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            digest = hashlib.sha256(vector_path.read_bytes()).hexdigest()

            def mutate(value: dict) -> None:
                bundle_artifact(value, "vectorization-result")["sha256"] = digest

            edit_bundle(copy, mutate)

        identity_report = tampered(break_source_identity)
        if identity_report.get("ok") or not any(
            "source_sha256 disagrees with the bundle" in error
            for error in identity_report.get("errors", [])
        ):
            raise RuntimeError(
                f"a derived file claiming a different source was accepted: {identity_report}"
            )
        checks += 1

        def break_authority_ref(copy: Path) -> None:
            def mutate(value: dict) -> None:
                value["visual_authority_ref"] = {"id": "VA-deadbeef", "sha256": "0" * 64}

            edit_bundle(copy, mutate)

        authority_report = tampered(break_authority_ref)
        authority_errors = [
            error
            for error in authority_report.get("errors", [])
            if "visual_authority_ref" in error
        ]
        if authority_report.get("ok") or len(authority_errors) != 2:
            raise RuntimeError(
                f"a forged visual_authority_ref was accepted: {authority_report}"
            )
        checks += 1

        expected = {
            "faithful-archival.svg",
            "vectorization-result.json",
            "semantic-regions.json",
            "subject-mask.svg",
            "structural-line-tone.svg",
            "color-audit.svg",
            "saturation-rescue.svg",
            "specular-audit.svg",
            "palette-probes.json",
            "audit-extraction-set.json",
            "runtime-attachment-build.json",
        }
        actual = {path.name for path in (bundle_dir / "derived-visual").iterdir() if path.is_file()}
        if expected != actual:
            raise RuntimeError(f"three-layer artifact set mismatch: {sorted(expected ^ actual)}")
        checks += 1

        archival = bundle_dir / "derived-visual/faithful-archival.svg"
        text = archival.read_text(encoding="utf-8")
        if "<image" in text.lower() or "data:image/" in text.lower() or "href=" in text.lower():
            raise RuntimeError("archival SVG contains a raster payload or external reference")
        checks += 1

        cli_bundle = root / "cli-bundle"
        cli = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("extract_visual_evidence.py")),
                str(source),
                "--output",
                str(cli_bundle),
                "--record",
                "smoke-record",
            ],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if cli.returncode != 0:
            raise RuntimeError("single-image extraction CLI failed: " + cli.stdout + "\n" + cli.stderr)
        try:
            cli_report = json.loads(cli.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"single-image extraction CLI returned invalid JSON: {cli.stdout}") from exc
        if not cli_report.get("ok") or not validate_bundle(cli_bundle).get("ok"):
            raise RuntimeError("single-image extraction CLI did not create a valid bundle")
        checks += 1

        def validate_cli(argument: Path) -> tuple[int, dict]:
            run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(Path(__file__).with_name("validate_visual_evidence.py")),
                    str(argument),
                ],
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            try:
                return run.returncode, json.loads(run.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "validate_visual_evidence.py did not return JSON: "
                    + run.stdout
                    + "\n"
                    + run.stderr
                ) from exc

        empty_bundle_root = root / "empty-bundle-root"
        empty_bundle_root.mkdir()
        empty_code, empty_json = validate_cli(empty_bundle_root)
        if (
            empty_code != 1
            or empty_json.get("ok")
            or empty_json.get("bundles") != 0
            or not any(
                "no visual-evidence bundle" in error for error in empty_json.get("errors", [])
            )
        ):
            raise RuntimeError(f"an empty bundle directory validated green: {empty_json}")
        checks += 1

        missing_code, missing_json = validate_cli(root / "does-not-exist")
        if missing_code != 1 or not any(
            "not a bundle directory" in error for error in missing_json.get("errors", [])
        ):
            raise RuntimeError(f"a nonexistent path was not reported structurally: {missing_json}")
        checks += 1

        real_code, real_json = validate_cli(bundle_dir)
        if real_code != 0 or not real_json.get("ok") or real_json.get("bundles") != 1:
            raise RuntimeError(f"a real bundle did not validate through the CLI: {real_json}")
        checks += 1

        safe = root / "safe.svg"
        safe.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
            '<path fill="#123456" d="M0 0h10v10H0z"/></svg>',
            encoding="utf-8",
        )
        safe_hash, safe_errors = inspect_svg(safe)
        if safe_errors or not safe_hash:
            raise RuntimeError(f"safe SVG inspection failed: {safe_errors}")
        checks += 1

        production_render = root / "production-svg-render" / "output.png"
        repeated_render = root / "production-svg-render" / "repeated.png"
        render_svg(safe, production_render, width=17, height=13)
        render_svg(safe, repeated_render, width=17, height=13)
        if not production_render.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("production SVG rasterization did not write a PNG")
        if repeated_render.read_bytes() != production_render.read_bytes():
            raise RuntimeError("the same SVG at the same size rasterized to different PNG bytes")
        with Image.open(production_render) as rendered:
            if rendered.format != "PNG" or rendered.size != (17, 13):
                raise RuntimeError(
                    "production SVG rasterization returned unexpected output: "
                    f"format={rendered.format!r}, size={rendered.size!r}"
                )
            pixels = rendered.convert("RGBA")
            if pixels.getpixel((8, 6)) != (0x12, 0x34, 0x56, 255) or pixels.getpixel((0, 6))[3] != 0:
                raise RuntimeError(
                    "the drawing did not fit the requested size as its viewBox declares"
                )
        checks += 1

        unsafe = root / "unsafe-middle.svg"
        unsafe.write_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0z"/><!--'
            + b"x" * (2 << 20)
            + b'--><script>alert(1)</script><path d="M1 1z"/></svg>'
        )
        _, unsafe_errors = inspect_svg(unsafe)
        if not any("forbidden SVG construct" in value for value in unsafe_errors):
            raise RuntimeError("middle-of-file active SVG content was not rejected")
        checks += 1

        unsafe_namespaced = root / "unsafe-namespaced-script.svg"
        unsafe_namespaced.write_text(
            '<svg:svg xmlns:svg="http://www.w3.org/2000/svg"><svg:path d="M0 0z"/>'
            '<svg:script>alert(1)</svg:script></svg:svg>',
            encoding="utf-8",
        )
        _, namespaced_errors = inspect_svg(unsafe_namespaced)
        if not any("forbidden SVG construct" in value for value in namespaced_errors):
            raise RuntimeError("namespaced active SVG content was not rejected")
        checks += 1

        unsafe_href = root / "unsafe-relative-href.svg"
        unsafe_href.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0z"/>'
            '<use href="other.svg#shape"/></svg>',
            encoding="utf-8",
        )
        _, href_errors = inspect_svg(unsafe_href)
        if not any("forbidden SVG construct" in value for value in href_errors):
            raise RuntimeError("relative external SVG reference was not rejected")
        checks += 1

        occupied_output = root / "occupied-bundle"
        occupied_output.mkdir()
        occupied_sentinel = occupied_output / "user-data.txt"
        occupied_sentinel.write_text("preserve me\n", encoding="utf-8")
        try:
            process_source(
                source,
                {
                    "source_sha256": source_sha,
                    "source_media_type": "image/png",
                    "canonical_record_ids": ["smoke-record"],
                    "disposition": "reference-evidence",
                },
                occupied_output,
            )
            raise RuntimeError("pre-existing visual-evidence output was accepted")
        except FileExistsError:
            pass
        if occupied_sentinel.read_text(encoding="utf-8") != "preserve me\n":
            raise RuntimeError("visual-evidence output replacement modified user data")
        checks += 1

        empty_output = root / "pre-existing-empty-bundle"
        empty_output.mkdir()
        try:
            process_source(
                source,
                {
                    "source_sha256": source_sha,
                    "source_media_type": "image/png",
                    "canonical_record_ids": ["smoke-record"],
                    "disposition": "reference-evidence",
                },
                empty_output,
            )
            raise RuntimeError("pre-existing empty output directory was accepted")
        except FileExistsError:
            pass
        checks += 1

        noise_source = root / "perceptual-gate-noise.png"
        Image.fromarray(
            np.random.default_rng(7).integers(0, 256, size=(128, 128, 3), dtype=np.uint8)
        ).save(noise_source)
        noise_entry = {
            "source_sha256": hashlib.sha256(noise_source.read_bytes()).hexdigest(),
            "source_media_type": "image/png",
            "canonical_record_ids": ["smoke-record"],
            "disposition": "reference-evidence",
        }
        discarded_output = root / "rejected-output"
        discarded_report = process_source(noise_source, noise_entry, discarded_output)
        if discarded_report.get("ok"):
            # The gate runs every profile; if uniform noise ever clears it, this
            # fixture no longer exercises rejection and the case is not a failure.
            skipped.append("perceptual gate rejection: uniform noise satisfied the gate")
        else:
            if discarded_report.get("output") is not None:
                raise RuntimeError(
                    f"a rejected bundle reported a published output: {discarded_report}"
                )
            if discarded_output.exists():
                raise RuntimeError("a rejected bundle was published to --output")
            leftovers = [
                path.name
                for path in root.iterdir()
                if path.name.startswith("cpb-visual-evidence-")
            ]
            if leftovers:
                raise RuntimeError(f"rejected extraction left a working directory: {leftovers}")
            checks += 1

            kept_output = root / "kept"
            kept_report = process_source(
                noise_source, noise_entry, root / "kept-output", rejected_output=kept_output
            )
            if kept_report.get("ok") or (root / "kept-output").exists():
                raise RuntimeError(f"a rejected bundle was published to --output: {kept_report}")
            if not (kept_output / "visual-evidence-bundle.json").is_file():
                raise RuntimeError(f"--keep-rejected did not keep the bundle: {kept_report}")
            kept_errors = validate_bundle(kept_output).get("errors", [])
            if "perceptual fidelity gate not satisfied" not in kept_errors:
                raise RuntimeError(f"a kept rejected bundle validated: {kept_errors}")
            checks += 1

        occupied_rejected = root / "occupied-rejected"
        occupied_rejected.mkdir()
        try:
            process_source(
                source,
                {
                    "source_sha256": source_sha,
                    "source_media_type": "image/png",
                    "canonical_record_ids": ["smoke-record"],
                    "disposition": "reference-evidence",
                },
                root / "unused-output",
                rejected_output=occupied_rejected,
            )
            raise RuntimeError("a pre-existing --keep-rejected destination was accepted")
        except FileExistsError:
            pass
        if (root / "unused-output").exists():
            raise RuntimeError("a refused --keep-rejected destination still wrote --output")
        checks += 1

        compact_pack = root / "compact-batch-pack"
        compact_corpus = compact_pack / "resources" / "reference-corpus"
        compact_corpus.mkdir(parents=True)
        wrong_source_sha = "0" * 64
        (compact_corpus / "manifest.json").write_text(
            json.dumps({"entries": [{"source_sha256": wrong_source_sha}]}) + "\n",
            encoding="utf-8",
        )
        compact_source_map = root / "compact-source-map.json"
        compact_source_map.write_text(
            json.dumps({wrong_source_sha: {"paths": [str(source)]}}) + "\n",
            encoding="utf-8",
        )
        compact_report = root / "compact-batch-report.json"
        compact_cli = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("compact_perceptual_visual_evidence.py")),
                "--pack-root",
                str(compact_pack),
                "--source-map",
                str(compact_source_map),
                "--workers",
                "1",
                "--report",
                str(compact_report),
            ],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if compact_cli.returncode == 0 or "does not match source content" not in compact_cli.stderr:
            raise RuntimeError(
                "compact batch did not reject source bytes with the wrong declared hash: "
                + compact_cli.stdout
                + "\n"
                + compact_cli.stderr
            )
        if (compact_corpus / "visual-evidence").exists() or compact_report.exists():
            raise RuntimeError("compact batch wrote output before source hash verification")
        checks += 1

        raster_calls: list[dict[str, object]] = []
        fake_resvg = types.ModuleType("resvg_py")

        def fake_svg_to_bytes(**kwargs: object) -> bytes:
            raster_calls.append(kwargs)
            return b"fake-png"

        fake_resvg.svg_to_bytes = fake_svg_to_bytes  # type: ignore[attr-defined]
        previous_resvg = sys.modules.get("resvg_py")
        sys.modules["resvg_py"] = fake_resvg
        try:
            unsafe_render_output = root / "unsafe-render" / "output.png"
            try:
                render_svg(unsafe_href, unsafe_render_output)
                raise RuntimeError("unsafe SVG was sent to the rasterizer")
            except ValueError as exc:
                if "unsafe or non-self-contained" not in str(exc):
                    raise
            if raster_calls or unsafe_render_output.parent.exists():
                raise RuntimeError("unsafe SVG produced rasterizer or filesystem output")
            checks += 1

            safe_render_output = root / "safe-render" / "output.png"
            render_svg(safe, safe_render_output)
            if len(raster_calls) != 1 or safe_render_output.read_bytes() != b"fake-png":
                raise RuntimeError("validated SVG did not reach the rasterizer")
            checks += 1
        finally:
            if previous_resvg is None:
                sys.modules.pop("resvg_py", None)
            else:
                sys.modules["resvg_py"] = previous_resvg

        thumbnail_pack = root / "thumbnail-pack"
        thumbnail_corpus = thumbnail_pack / "resources" / "reference-corpus"
        thumbnail_path = (
            thumbnail_corpus
            / "visual-evidence"
            / "example"
            / "derived-visual"
            / "catalog-thumbnail.webp"
        )
        thumbnail_path.parent.mkdir(parents=True)
        thumbnail_path.write_bytes(b"RIFF\x04\x00\x00\x00WEBP")
        thumbnail_sha = hashlib.sha256(thumbnail_path.read_bytes()).hexdigest()
        declaration_relative = "resources/reference-corpus/catalog-thumbnails.json"
        (thumbnail_pack / "pack.json").write_text(
            json.dumps(
                {
                    "content": {
                        "resource_bindings": {"catalog-thumbnails": declaration_relative}
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        declaration_path = thumbnail_pack / declaration_relative
        declaration_path.write_text(
            json.dumps(
                {
                    "format": "character-prompt-builder-catalog-thumbnails",
                    "assets": {
                        "visual-evidence-example": {
                            "path": thumbnail_path.relative_to(thumbnail_pack).as_posix(),
                            "media_type": "image/webp",
                            "sha256": thumbnail_sha,
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        declared, declaration_errors = _declared_catalog_thumbnails(
            thumbnail_pack, thumbnail_corpus
        )
        expected_thumbnail = thumbnail_path.relative_to(thumbnail_corpus).as_posix()
        if declaration_errors or declared != {expected_thumbnail}:
            raise RuntimeError(
                f"declared catalog thumbnail was not accepted: {declaration_errors}, {declared}"
            )
        checks += 1

        declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
        declaration["assets"]["visual-evidence-example"]["sha256"] = "0" * 64
        declaration_path.write_text(json.dumps(declaration) + "\n", encoding="utf-8")
        _, declaration_errors = _declared_catalog_thumbnails(thumbnail_pack, thumbnail_corpus)
        if not any("sha256 mismatch" in error for error in declaration_errors):
            raise RuntimeError("tampered catalog thumbnail was accepted")
        checks += 1

        print(
            json.dumps(
                {
                    "ok": True,
                    "checks": checks,
                    "skipped_checks": skipped,
                    "source_dimensions": {"width": width, "height": height},
                    "three_layer_bundle": True,
                    "single_source_cli": True,
                    "full_file_security_scan": True,
                    "production_svg_render": True,
                    "compact_batch_source_hash_gate": True,
                    "declared_catalog_thumbnail_gate": True,
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
