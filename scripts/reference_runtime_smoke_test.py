#!/usr/bin/env python3
"""Behavior-level smoke tests for automatic visual-reference activation."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

from catalog_cli import configure_pack_runtime
from check_dependencies import check_profile, install_command
from pack_manager import PackSettings, write_lock
from prepare_generation_references import (
    host_reference_transports,
    validate_prepared_reference_set,
)
from reference_contract import canonical_json, finalize_reference_use_plan
from reference_runtime import (
    VisualDependencyPreflightError,
    build_reference_use_plan,
    execute_reference_use_plan,
    validate_reference_use_plan,
)
from state_protocol import finalize_artifact

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK_ID = "01a0043b-2250-720d-87b7-f1e6fd7ed230"
FIXTURE_PACK_ID = "01a00500-0000-7000-8000-000000000001"
FIXTURE_RECORD_ID = "fixture-visual-reference-scene"
DIRECT_RASTER_RECORD_ID = "fixture-direct-raster-scene"
UNSUPPORTED_RECORD_ID = "fixture-environment-only-scene"
DEFAULT_PROVIDERS = {
    "archetype-policy": DEFAULT_PACK_ID,
    "discovery-lanes": DEFAULT_PACK_ID,
    "negative-policy": DEFAULT_PACK_ID,
    "project-defaults": DEFAULT_PACK_ID,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _fixture_png() -> bytes:
    """Return a deterministic dependency-free 2x2 RGB PNG."""

    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    rows = b"\x00\xff\x00\x00\x00\xff\x00" + b"\x00\x00\x00\xff\xff\xff\xff"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(rows, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _make_tree_read_only(root: Path) -> None:
    for path in Path(root).rglob("*"):
        if path.is_file():
            os.chmod(path, stat.S_IREAD)


def _write_fixture_pack(root: Path) -> Path:
    """Create a tiny released pack that proves activation without user content."""

    pack = root / "fixture-pack"
    records = pack / "records"
    bundle_root = pack / "resources" / "visual-evidence"
    derived = bundle_root / "derived-visual"
    records.mkdir(parents=True)
    derived.mkdir(parents=True)
    direct_raster_path = bundle_root / "direct-raster.png"
    direct_raster_path.write_bytes(_fixture_png())
    direct_raster_sha256 = _sha256(direct_raster_path)

    svg_bodies = {
        "faithful-archival-vector": (
            "faithful-archival.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
            'viewBox="0 0 240 180"><path fill="#3b5f89" d="M20 20H220V160H20Z"/>'
            '<path fill="#f2d2a2" d="M80 45H160V135H80Z"/></svg>\n',
        ),
        "subject-mask": (
            "subject-mask.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
            'viewBox="0 0 240 180"><path fill="#000" d="M0 0H240V180H0Z"/>'
            '<path fill="#fff" d="M80 45H160V135H80Z"/></svg>\n',
        ),
        "structural-line-tone": (
            "structural-line-tone.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
            'viewBox="0 0 240 180"><path fill="#ddd" d="M0 0H240V180H0Z"/>'
            '<path fill="#555" d="M80 45H160V135H80Z"/></svg>\n',
        ),
        "color-audit": (
            "color-audit.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
            'viewBox="0 0 240 180"><path fill="#3b5f89" d="M0 0H120V180H0Z"/>'
            '<path fill="#f2d2a2" d="M120 0H240V180H120Z"/></svg>\n',
        ),
        "saturation-rescue": (
            "saturation-rescue.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
            'viewBox="0 0 240 180"><path fill="#000" d="M0 0H240V180H0Z"/>'
            '<path fill="#ff5a00" d="M105 70H135V100H105Z"/></svg>\n',
        ),
        "specular-audit": (
            "specular-audit.svg",
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
            'viewBox="0 0 240 180"><path fill="#000" d="M0 0H240V180H0Z"/>'
            '<path fill="#fff" d="M110 55H130V75H110Z"/></svg>\n',
        ),
    }
    role_to_name: dict[str, str] = {}
    for role, (name, body) in svg_bodies.items():
        path = derived / name
        path.write_text(body, encoding="utf-8", newline="\n")
        role_to_name[role] = name

    json_payloads = {
        "vectorization-result": ("vectorization-result.json", {"fixture": True}),
        "semantic-region-map": ("semantic-regions.json", {"regions": []}),
        "palette-probes": ("palette-probes.json", {"colors": ["#3b5f89", "#f2d2a2"]}),
        "audit-extraction-set": ("audit-extraction-set.json", {"fixture": True}),
        "runtime-attachment-build": (
            "runtime-attachment-build.json",
            {"recipes": [{"id": "fixture-structural-guide", "input_role": "structural-line-tone"}]},
        ),
    }
    for role, (name, payload) in json_payloads.items():
        path = derived / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        role_to_name[role] = name

    artifact_ids = [
        "faithful-archival-vector",
        "vectorization-result",
        "semantic-regions",
        "subject-mask",
        "structural-line-tone",
        "color-audit",
        "saturation-rescue",
        "specular-audit",
        "palette-probes",
        "audit-extraction-set",
        "runtime-attachment-build",
    ]
    id_to_role = {
        "faithful-archival-vector": "faithful-archival-vector",
        "vectorization-result": "vectorization-result",
        "semantic-regions": "semantic-region-map",
        "subject-mask": "subject-mask",
        "structural-line-tone": "structural-line-tone",
        "color-audit": "color-audit",
        "saturation-rescue": "saturation-rescue",
        "specular-audit": "specular-audit",
        "palette-probes": "palette-probes",
        "audit-extraction-set": "audit-extraction-set",
        "runtime-attachment-build": "runtime-attachment-build",
    }
    role_name_lookup = {
        **role_to_name,
        "semantic-region-map": role_to_name["semantic-region-map"],
    }
    artifacts: list[dict[str, str]] = []
    bundle_artifacts: list[dict[str, str]] = []
    resource_refs: list[str] = []
    for artifact_id in artifact_ids:
        role = id_to_role[artifact_id]
        name = role_name_lookup[role]
        path = derived / name
        pack_relative = path.relative_to(pack).as_posix()
        bundle_relative = path.relative_to(bundle_root).as_posix()
        media_type = "image/svg+xml" if path.suffix == ".svg" else "application/json"
        digest = _sha256(path)
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "role": role,
                "path": pack_relative,
                "media_type": media_type,
                "sha256": digest,
            }
        )
        bundle_artifacts.append(
            {
                "artifact_id": artifact_id,
                "role": role,
                "path": bundle_relative,
                "media_type": media_type,
                "sha256": digest,
            }
        )
        resource_refs.append(pack_relative)

    source_sha = hashlib.sha256(b"reference-runtime-smoke-fixture").hexdigest()
    bundle = {
        "artifact_type": "visual-evidence-bundle",
        "bundle_id": "VE-FIXTURE",
        "source_ref_id": "SRC-FIXTURE",
        "source_sha256": source_sha,
        "source_dimensions": {"width": 240, "height": 180},
        "visual_authority_ref": {
            "id": "VA-FIXTURE",
            "sha256": hashlib.sha256(b"fixture-visual-authority").hexdigest(),
        },
        "layers": {
            "A": "native-dimension compact perceptual archival vector",
            "B": "audit extraction set",
            "C": "disposable runtime attachment build recipes",
        },
        "representation": "native-dimension-compact-perceptual-path-vector",
        "artifacts": bundle_artifacts,
        "canonical_record_refs": [FIXTURE_RECORD_ID],
        "disposition": "canonical-preset-evidence",
        "evidence_relation": "previously-reviewed-evidence",
        "semantic_summary": "Self-contained reference-runtime smoke fixture.",
        "notes": ["Generated only inside a temporary smoke-test directory."],
        "visual_evidence_bundle_sha256": "0" * 64,
    }
    bundle_no_hash = dict(bundle)
    bundle_no_hash.pop("visual_evidence_bundle_sha256", None)
    bundle["visual_evidence_bundle_sha256"] = hashlib.sha256(
        json.dumps(
            bundle_no_hash,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    bundle_path = bundle_root / "visual-evidence-bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    bundle_pack_relative = bundle_path.relative_to(pack).as_posix()
    resource_refs.append(bundle_pack_relative)

    direct_bundle_root = bundle_root / "direct-raster-bundle"
    direct_derived = direct_bundle_root / "derived-visual"
    direct_derived.mkdir(parents=True)
    direct_artifacts: list[dict[str, str]] = []
    direct_bundle_artifacts: list[dict[str, str]] = []
    direct_resource_refs: list[str] = []
    for artifact in artifacts:
        source_path = pack / artifact["path"]
        direct_name = Path(artifact["path"]).name
        direct_path = direct_derived / direct_name
        if artifact["role"] == "subject-mask":
            direct_path = direct_derived / "subject-mask.png"
            direct_path.write_bytes(_fixture_png())
            media_type = "image/png"
        else:
            direct_path.write_bytes(source_path.read_bytes())
            media_type = artifact["media_type"]
        digest = _sha256(direct_path)
        pack_relative = direct_path.relative_to(pack).as_posix()
        bundle_relative = direct_path.relative_to(direct_bundle_root).as_posix()
        direct_artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "role": artifact["role"],
                "path": pack_relative,
                "media_type": media_type,
                "sha256": digest,
            }
        )
        direct_bundle_artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "role": artifact["role"],
                "path": bundle_relative,
                "media_type": media_type,
                "sha256": digest,
            }
        )
        direct_resource_refs.append(pack_relative)
    direct_bundle = {
        "artifact_type": "visual-evidence-bundle",
        "bundle_id": "VE-DIRECT-RASTER-FIXTURE",
        "source_ref_id": "SRC-DIRECT-RASTER",
        "source_sha256": direct_raster_sha256,
        "source_dimensions": {"width": 2, "height": 2},
        "visual_authority_ref": {
            "id": "VA-DIRECT-RASTER-FIXTURE",
            "sha256": hashlib.sha256(b"direct-raster-visual-authority").hexdigest(),
        },
        "layers": {
            "A": "native-dimension compact perceptual archival vector",
            "B": "audit extraction set",
            "C": "disposable runtime attachment build recipes",
        },
        "representation": "native-dimension-compact-perceptual-path-vector",
        "artifacts": direct_bundle_artifacts,
        "canonical_record_refs": [DIRECT_RASTER_RECORD_ID],
        "disposition": "canonical-preset-evidence",
        "evidence_relation": "previously-reviewed-evidence",
        "semantic_summary": "Self-contained direct-raster runtime fixture.",
        "notes": ["Generated only inside a temporary smoke-test directory."],
        "visual_evidence_bundle_sha256": "0" * 64,
    }
    direct_bundle_no_hash = dict(direct_bundle)
    direct_bundle_no_hash.pop("visual_evidence_bundle_sha256", None)
    direct_bundle["visual_evidence_bundle_sha256"] = hashlib.sha256(
        json.dumps(
            direct_bundle_no_hash,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    direct_bundle_path = direct_bundle_root / "visual-evidence-bundle.json"
    direct_bundle_path.write_text(
        json.dumps(direct_bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    direct_resource_refs.append(direct_bundle_path.relative_to(pack).as_posix())
    direct_subject_artifact = next(
        artifact for artifact in direct_artifacts if artifact["role"] == "subject-mask"
    )

    pack_manifest = {
        "pack_id": FIXTURE_PACK_ID,
        "name": "Reference Runtime Smoke Fixture",
        "description": "Temporary behavior-level fixture created by the smoke test.",
        "release": "2026.08.16.1",
        "content": {
            "record_globs": ["records/**/*.json"],
            "resource_globs": ["resources/**/*"],
            "resource_bindings": {},
        },
        "capabilities": ["scene-records", "searchable-assets", "evidence-artifact-reference", "visual-evidence"],
        "dependencies": [],
        "optional_dependencies": [],
        "replaces": [],
        "license": "GPL-3.0-only",
    }
    (pack / "pack.json").write_text(
        json.dumps(pack_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    scene = {
        "kind": "scene",
        "records": [
            {
                "id": FIXTURE_RECORD_ID,
                "label": "Fixture visual reference scene",
                "curation_status": "curated",
                "domain": "shared",
                "domains": ["shared"],
                "defaults": {
                    "subject": "one recurring anthropomorphic black panther character",
                    "species": "anthropomorphic black panther",
                    "body": "tall muscular body with stable feline proportions",
                    "surface": "short black fur with stable facial and body-fur distribution",
                    "outfit": "a fitted blue field jacket with a fixed layered construction",
                    "pose": "standing three-quarter pose with one hand at the hip",
                    "composition": "three-quarter character portrait",
                    "camera": "eye-level 70mm portrait framing",
                    "local_color": "black fur, blue jacket, and warm tan accent regions",
                    "lighting": "soft neutral key with a restrained rim light",
                    "environment": "plain off-white studio background"
                },
                "must_preserve": [
                    "the black-panther species, muscular proportions, and stable fur distribution",
                    "the blue field-jacket construction when outfit authority is selected"
                ],
                "tags": ["fixture visual reference", "black panther", "blue field jacket"],
                "search_terms": [
                    {
                        "phrase": "fixture visual reference",
                        "facet": "scene",
                        "weight": 1.0,
                        "source": "author",
                    }
                ],
            },
            {
                "id": DIRECT_RASTER_RECORD_ID,
                "label": "Fixture direct raster scene",
                "curation_status": "curated",
                "domain": "shared",
                "domains": ["shared"],
                "defaults": {
                    "pose": "a stable full-body action pose",
                    "camera": "eye-level full-body framing",
                },
                "tags": ["fixture direct raster"],
                "search_terms": [
                    {
                        "phrase": "fixture direct raster",
                        "facet": "scene",
                        "weight": 1.0,
                        "source": "author",
                    }
                ],
            },
            {
                "id": UNSUPPORTED_RECORD_ID,
                "label": "Fixture empty studio environment",
                "curation_status": "curated",
                "domain": "shared",
                "domains": ["shared"],
                "defaults": {
                    "environment": "an empty off-white studio cyclorama",
                    "lighting": "large soft overhead studio source"
                },
                "tags": ["empty studio environment"],
                "search_terms": [
                    {
                        "phrase": "empty studio environment",
                        "facet": "environment",
                        "weight": 1.0,
                        "source": "author"
                    }
                ]
            }
        ],
    }
    (records / "scene.json").write_text(
        json.dumps(scene, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    asset = {
        "kind": "asset",
        "records": [
            {
                "id": "fixture-visual-evidence-asset",
                "label": "Fixture visual evidence asset",
                "category": "visual-evidence",
                "curation_status": "curated",
                "asset_type": "visual-evidence-bundle",
                "description": "Self-contained visual-reference runtime fixture.",
                "tags": ["visual evidence", "smoke fixture"],
                "search_terms": [
                    {
                        "phrase": "fixture visual evidence",
                        "facet": "asset",
                        "weight": 1.0,
                        "source": "author",
                    }
                ],
                "source_ref_id": "SRC-FIXTURE",
                "source_sha256": source_sha,
                "source_media_type": "image/png",
                "source_dimensions": {"width": 240, "height": 180},
                "disposition": "canonical-preset-evidence",
                "evidence_relation": "previously-reviewed-evidence",
                "canonical_record_ids": [FIXTURE_RECORD_ID],
                "primary_resource": artifacts[0]["path"],
                "resource_refs": resource_refs,
                "artifacts": artifacts,
            },
            {
                "id": "fixture-direct-raster-asset",
                "label": "Fixture direct raster asset",
                "category": "visual-evidence",
                "curation_status": "curated",
                "asset_type": "visual-evidence-bundle",
                "description": "Self-contained direct-raster runtime fixture.",
                "tags": ["visual evidence", "direct raster", "smoke fixture"],
                "search_terms": [
                    {
                        "phrase": "fixture direct raster",
                        "facet": "asset",
                        "weight": 1.0,
                        "source": "author",
                    }
                ],
                "source_ref_id": "SRC-DIRECT-RASTER",
                "source_sha256": direct_raster_sha256,
                "source_media_type": "image/png",
                "source_dimensions": {"width": 2, "height": 2},
                "disposition": "canonical-preset-evidence",
                "evidence_relation": "previously-reviewed-evidence",
                "canonical_record_ids": [DIRECT_RASTER_RECORD_ID],
                "primary_resource": direct_subject_artifact["path"],
                "resource_refs": direct_resource_refs,
                "artifacts": direct_artifacts,
            },
        ],
    }
    (records / "asset.json").write_text(
        json.dumps(asset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_lock(pack)
    return pack


def _record(checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped_checks: list[dict[str, str]] = []
    visual_report = check_profile("visual")
    environment_prerequisites = [
        {
            "profile": "visual",
            "ok": bool(visual_report["ok"]),
            "required_for": [
                "SVG rasterization for multi-image transport",
                "single-board raster composition",
            ],
            "check_command": visual_report["check_command"],
            "install_command": visual_report["install_command"],
            "missing_packages": visual_report["missing_packages"],
            "incompatible_packages": visual_report["incompatible_packages"],
        }
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="cpb-reference-runtime-") as td:
            temp = Path(td)
            fixture_pack = _write_fixture_pack(temp)
            state = temp / "pack-state.json"
            def activate_fixture(enabled: bool = True) -> None:
                state.write_text(
                    json.dumps(
                        {
                            "pack_roots": [str(fixture_pack)],
                            "enabled_packs": (
                                [DEFAULT_PACK_ID, FIXTURE_PACK_ID]
                                if enabled
                                else [DEFAULT_PACK_ID]
                            ),
                            "resource_providers": DEFAULT_PROVIDERS,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                configure_pack_runtime(None)
                managed_root = (temp / "managed").resolve()
                configure_pack_runtime(
                    PackSettings(
                        roots=((ROOT / "packs" / "commons").resolve(),),
                        state_file=state.resolve(),
                        cache_dir=(temp / "cache").resolve(),
                        managed_root=managed_root,
                        quarantine_root=(managed_root / ".quarantine").resolve(),
                    )
                )

            def use(influence: str) -> list[dict[str, str]]:
                return [
                    {
                        "record_id": FIXTURE_RECORD_ID,
                        "intended_influence": influence,
                    }
                ]

            lights = [
                {
                    "light_id": "key",
                    "direction": "upper-left front",
                    "apparent_size": "large softbox",
                    "color": "neutral daylight",
                    "relative_intensity": "primary",
                    "softness": "soft",
                }
            ]
            materials = [
                {
                    "material": "fixture surface",
                    "roughness": "matte",
                    "specular_strength": "low",
                    "highlight_shape": "broad and soft",
                    "wetness": "dry",
                    "anisotropy": "none",
                }
            ]
            activate_fixture()

            malformed_reports = [
                validate_reference_use_plan(value)
                for value in (None, [], "text", 7)
            ]
            _record(
                checks,
                "non-object-validator-inputs-return-structured-errors",
                all(
                    isinstance(report, dict)
                    and report.get("ok") is False
                    and isinstance(report.get("errors"), list)
                    for report in malformed_reports
                ),
                str(malformed_reports),
            )
            try:
                build_reference_use_plan(
                    [],
                    transport_mode="prompt-artifacts",
                    source_lighting_mode="preserve",
                )
                empty_rejected = False
            except ValueError:
                empty_rejected = True
            _record(
                checks,
                "empty-record-use-list-is-rejected",
                empty_rejected,
                "selected_records must be non-empty",
            )

            environment_plan = build_reference_use_plan(
                use("environment"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            environment_report = validate_reference_use_plan(environment_plan)
            _record(
                checks,
                "record-scoped-plan-validates-against-active-pack",
                environment_report["ok"],
                str(environment_report),
            )
            environment_roles = {
                item["technical_role"] for item in environment_plan["reference_items"]
            }
            _record(
                checks,
                "environment-use-activates-structure-and-subject-mask",
                {"structural-line-tone", "subject-mask"}.issubset(environment_roles)
                and "faithful-archival-vector" not in environment_roles,
                str(sorted(environment_roles)),
            )

            outfit_plan = build_reference_use_plan(
                use("outfit"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            outfit_controls = [
                control
                for item in outfit_plan["reference_items"]
                for control in item["authority"]["controls"]
            ]
            _record(
                checks,
                "outfit-use-cannot-control-source-identity",
                any("garment" in control for control in outfit_controls)
                and not any(
                    token in control
                    for control in outfit_controls
                    for token in ("identity", "species", "anatomy", "marking", "hair", "fur")
                )
                and all(
                    "scene-conditioned presentation outside the declared intended influence"
                    in item["authority"]["must_not_control"]
                    for item in outfit_plan["reference_items"]
                ),
                str(outfit_controls),
            )

            identity_plan = build_reference_use_plan(
                use("identity"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            identity_text = canonical_json(
                [item["authority"] for item in identity_plan["reference_items"]]
            )
            _record(
                checks,
                "identity-use-keeps-stable-grooming-and-excludes-transient-presentation",
                "stable hair, mane, fur-tuft" in identity_text
                and "perspiration" in identity_text
                and "scene-conditioned presentation" in identity_text,
                identity_text,
            )

            pose_plan = build_reference_use_plan(
                use("pose-camera"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            pose_controls = canonical_json(
                [item["authority"]["controls"] for item in pose_plan["reference_items"]]
            )
            _record(
                checks,
                "pose-camera-use-cannot-control-identity-color-or-lighting",
                "pose" in pose_controls
                and not any(
                    token in pose_controls
                    for token in ("identity", "local color", "lighting", "species")
                ),
                pose_controls,
            )

            combined_plan = build_reference_use_plan(
                [
                    {"record_id": FIXTURE_RECORD_ID, "intended_influence": "identity"},
                    {"record_id": FIXTURE_RECORD_ID, "intended_influence": "outfit"},
                ],
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            try:
                build_reference_use_plan(
                    [
                        {
                            "record_id": FIXTURE_RECORD_ID,
                            "intended_influence": "identity",
                        },
                        {
                            "record_id": FIXTURE_RECORD_ID,
                            "intended_influence": "identity",
                        },
                    ],
                    transport_mode="prompt-artifacts",
                    source_lighting_mode="preserve",
                )
                duplicate_record_use_rejected = False
                duplicate_record_use_detail = "identical record use unexpectedly accepted"
            except ValueError as exc:
                duplicate_record_use_rejected = True
                duplicate_record_use_detail = str(exc)
            _record(
                checks,
                "combined-identity-and-outfit-retain-distinct-record-authority",
                combined_plan["selected_records"]
                == [
                    {"record_id": FIXTURE_RECORD_ID, "intended_influence": "identity"},
                    {"record_id": FIXTURE_RECORD_ID, "intended_influence": "outfit"},
                ]
                and all(
                    item["intended_influence"] == "identity"
                    for item in combined_plan["reference_items"]
                    if any("permanent character identity" == control for control in item["authority"]["controls"])
                )
                and duplicate_record_use_rejected,
                canonical_json(
                    {
                        "accepted_distinct_influences": combined_plan[
                            "selected_records"
                        ],
                        "rejected_identical_pair": duplicate_record_use_detail,
                    }
                ),
            )
            _record(
                checks,
                "subject-mask-selection-is-reachable",
                any(item["technical_role"] == "subject-mask" for item in pose_plan["reference_items"]),
                canonical_json([item["technical_role"] for item in pose_plan["reference_items"]]),
            )

            surface_mutation = copy.deepcopy(environment_plan)
            surface_mutation["surface_lighting_plan"]["source_lighting_mode"] = "replace"
            surface_report = validate_reference_use_plan(surface_mutation)
            _record(
                checks,
                "nested-surface-plan-hash-mutation-is-rejected",
                not surface_report["ok"]
                and any("surface" in error or "hash" in error for error in surface_report["errors"]),
                str(surface_report["errors"]),
            )

            prompt = temp / "prompt.txt"
            negative = temp / "negative.txt"
            prompt.write_text("A complete reviewed prompt.\n", encoding="utf-8")
            negative.write_text("Focused technical exclusions.\n", encoding="utf-8")
            prompt_dir = temp / "prompt-artifacts"
            prepared_prompt = execute_reference_use_plan(
                environment_plan,
                output_dir=prompt_dir,
                prompt_file=prompt,
                negative_file=negative,
                max_side=384,
            )
            copied = list((prompt_dir / "reference-artifacts").glob("*.svg"))
            _record(
                checks,
                "prompt-package-delivers-exact-svg-bytes-with-relative-paths",
                len(copied) == len(environment_plan["reference_items"])
                and all(not Path(row["delivered_path"]).is_absolute() for row in prepared_prompt["prompt_artifacts"])
                and all(row["source_sha256"] == row["delivered_sha256"] for row in prepared_prompt["prompt_artifacts"]),
                canonical_json(prepared_prompt["prompt_artifacts"]),
            )
            _record(
                checks,
                "prompt-package-includes-complete-contract-and-prompt-files",
                all(
                    (prompt_dir / name).is_file()
                    for name in (
                        "final-prompt.txt",
                        "final-negative.txt",
                        "reference-use-plan.json",
                        "surface-lighting-plan.json",
                        "reference-preamble.txt",
                        "prepared-reference-set.json",
                    )
                ),
                str(prompt_dir),
            )

            moved_dir = temp / "moved-prompt-package"
            prompt_dir.rename(moved_dir)
            try:
                moved_valid = validate_prepared_reference_set(
                    prepared_prompt,
                    package_root=moved_dir,
                )
                moved_ok = moved_valid["prepared_reference_set_sha256"] == prepared_prompt["prepared_reference_set_sha256"]
            except ValueError:
                moved_ok = False
            _record(
                checks,
                "moved-prompt-package-resolves-relative-artifact-paths",
                moved_ok,
                str(moved_dir),
            )

            unresolved_prompt_plan = build_reference_use_plan(
                use("environment"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="rescope",
            )
            unresolved_prompt_dir = temp / "unresolved-prompt"
            unresolved_prompt = execute_reference_use_plan(
                unresolved_prompt_plan,
                output_dir=unresolved_prompt_dir,
            )
            _record(
                checks,
                "prompt-only-package-preserves-unresolved-lighting-for-review",
                bool(
                    unresolved_prompt["reference_use_plan"]["surface_lighting_plan"]["unresolved_decisions"]
                ),
                canonical_json(
                    unresolved_prompt["reference_use_plan"]["surface_lighting_plan"]["unresolved_decisions"]
                ),
            )

            state_selection = finalize_artifact(
                {
                    "artifact_type": "reference-selection",
                    "selection_id": "SEL-ineligible",
                    "identity_contract_sha256": "1" * 64,
                    "era_contract_sha256": None,
                    "appearance_variant_sha256": None,
                    "state_snapshot_sha256": None,
                    "story_order": 0,
                    "required_state_features": [],
                    "selected_references": [
                        {
                            "binding_id": "BIND-ineligible",
                            "role": "identity-reference",
                            "source": copy.deepcopy(outfit_plan["reference_items"][0]["source"]),
                            "covers": [],
                            "intended_influence": ["identity"],
                            "review_dimensions": [],
                            "unsupported_or_occluded_state": [],
                            "unsupported_assumptions": [],
                        }
                    ],
                    "unresolved_requirements": [],
                    "selection_sha256": "0" * 64,
                }
            )
            state_output = temp / "state-ineligible"
            try:
                execute_reference_use_plan(
                    outfit_plan,
                    output_dir=state_output,
                    reference_selection=state_selection,
                )
                state_rejected = False
            except ValueError:
                state_rejected = not state_output.exists()
            _record(
                checks,
                "state-ineligible-reference-cannot-enter-prepared-package",
                state_rejected,
                str(state_output),
            )

            unresolved_model_plan = build_reference_use_plan(
                use("pose-camera"),
                transport_mode="multi-image",
                target_model="gpt-image-2.5-flare",
                source_lighting_mode="replace",
            )
            unresolved_model_dir = temp / "unresolved-model"
            try:
                execute_reference_use_plan(
                    unresolved_model_plan,
                    output_dir=unresolved_model_dir,
                    max_side=128,
                )
                unresolved_rejected = False
            except ValueError:
                unresolved_rejected = not unresolved_model_dir.exists()
            _record(
                checks,
                "unresolved-lighting-blocks-model-facing-execution",
                unresolved_rejected,
                str(unresolved_model_dir),
            )

            multi_plan = build_reference_use_plan(
                use("pose-camera"),
                transport_mode="multi-image",
                target_model="gpt-image-2.5-flare",
                source_lighting_mode="replace",
                light_sources=lights,
                material_responses=materials,
            )
            board_plan = build_reference_use_plan(
                use("pose-camera"),
                transport_mode="single-board",
                target_model="gpt-image-2.5-flare",
                source_lighting_mode="replace",
                light_sources=lights,
                material_responses=materials,
            )
            direct_plan = build_reference_use_plan(
                [
                    {
                        "record_id": DIRECT_RASTER_RECORD_ID,
                        "intended_influence": "pose-camera",
                    }
                ],
                transport_mode="multi-image",
                target_model="gpt-image-2.5-flare",
                source_lighting_mode="replace",
                light_sources=lights,
                material_responses=materials,
                include_technical_roles=["subject-mask"],
            )
            direct_dir = temp / "direct-raster-multi-image"
            with patch(
                "reference_runtime.check_profile",
                side_effect=AssertionError(
                    "direct-raster multi-image must not inspect Visual dependencies"
                ),
            ):
                prepared_direct = execute_reference_use_plan(
                    direct_plan,
                    output_dir=direct_dir,
                    max_side=128,
                )
            direct_references = prepared_direct["selected_references"]
            direct_row = direct_references[0] if len(direct_references) == 1 else {}
            direct_transport = direct_row.get("transport") or {}
            direct_source = direct_row.get("source") or {}
            direct_transport_path = direct_dir / str(
                direct_transport.get("resolved_path") or ""
            )
            _record(
                checks,
                "direct-raster-multi-image-is-copied-under-package-without-visual",
                len(direct_references) == 1
                and not Path(str(direct_transport["resolved_path"])).is_absolute()
                and direct_transport_path.is_file()
                and direct_transport["media_type"] == "image/png"
                and direct_transport["derivation"] == {"mode": "direct"}
                and direct_transport["sha256"] == direct_source["sha256"]
                and direct_transport["sha256"] == _sha256(direct_transport_path),
                canonical_json(direct_references),
            )

            read_only_source = Path(
                direct_plan["reference_items"][0]["source"]["resolved_path"]
            )
            os.chmod(read_only_source, stat.S_IREAD)
            try:
                direct_rollback_dir = temp / "direct-raster-rollback"
                direct_rollback_dir.mkdir()

                def fail_before_commit(
                    _prepared_set: Any,
                    *,
                    package_root: Path,
                    **_kwargs: Any,
                ) -> None:
                    _make_tree_read_only(Path(package_root))
                    raise RuntimeError("forced pre-commit validation failure")

                try:
                    with patch(
                        "reference_runtime.check_profile",
                        side_effect=AssertionError(
                            "direct-raster multi-image must not inspect Visual dependencies"
                        ),
                    ), patch(
                        "reference_runtime.validate_prepared_reference_set",
                        side_effect=fail_before_commit,
                    ):
                        execute_reference_use_plan(
                            direct_plan,
                            output_dir=direct_rollback_dir,
                            max_side=128,
                        )
                    direct_rollback_ok = False
                except RuntimeError as exc:
                    direct_rollback_ok = (
                        str(exc) == "forced pre-commit validation failure"
                        and direct_rollback_dir.is_dir()
                        and not any(direct_rollback_dir.iterdir())
                        and not list(
                            temp.glob(f".{direct_rollback_dir.name}.staging-*")
                        )
                    )
                _record(
                    checks,
                    "direct-raster-post-copy-failure-restores-empty-output",
                    direct_rollback_ok,
                    str(direct_rollback_dir),
                )

                post_commit_dir = temp / "direct-raster-post-commit-rollback"
                post_commit_dir.mkdir()
                validation_calls = 0

                def fail_after_commit(
                    prepared_set: Any,
                    *,
                    package_root: Path,
                    **kwargs: Any,
                ) -> Any:
                    nonlocal validation_calls
                    validation_calls += 1
                    if validation_calls == 1:
                        return validate_prepared_reference_set(
                            prepared_set,
                            package_root=package_root,
                            **kwargs,
                        )
                    _make_tree_read_only(Path(package_root))
                    raise RuntimeError("forced post-commit validation failure")

                try:
                    with patch(
                        "reference_runtime.check_profile",
                        side_effect=AssertionError(
                            "direct-raster multi-image must not inspect Visual dependencies"
                        ),
                    ), patch(
                        "reference_runtime.validate_prepared_reference_set",
                        side_effect=fail_after_commit,
                    ):
                        execute_reference_use_plan(
                            direct_plan,
                            output_dir=post_commit_dir,
                            max_side=128,
                        )
                    post_commit_rollback_ok = False
                except RuntimeError as exc:
                    post_commit_rollback_ok = (
                        str(exc) == "forced post-commit validation failure"
                        and validation_calls == 2
                        and post_commit_dir.is_dir()
                        and not any(post_commit_dir.iterdir())
                        and not list(temp.glob(f".{post_commit_dir.name}.staging-*"))
                    )
                _record(
                    checks,
                    "direct-raster-post-commit-failure-restores-empty-output",
                    post_commit_rollback_ok,
                    str(post_commit_dir),
                )
            finally:
                os.chmod(read_only_source, stat.S_IREAD | stat.S_IWRITE)
            if visual_report["ok"]:
                multi_dir = temp / "multi-image"
                prepared_multi = execute_reference_use_plan(
                    multi_plan,
                    output_dir=multi_dir,
                    prompt_file=prompt,
                    max_side=128,
                )
                source_hashes = {
                    row["source"]["sha256"]
                    for row in prepared_multi["selected_references"]
                }
                transport_paths = {
                    row["transport"]["resolved_path"]
                    for row in prepared_multi["selected_references"]
                }
                _record(
                    checks,
                    "multi-image-uses-two-independent-role-scoped-transports",
                    len(prepared_multi["selected_references"]) >= 2
                    and len(source_hashes) >= 2
                    and len(transport_paths)
                    == len(prepared_multi["selected_references"])
                    and all(not Path(path).is_absolute() for path in transport_paths),
                    canonical_json(prepared_multi["selected_references"]),
                )
                forwarded_multi = host_reference_transports(
                    prepared_multi,
                    package_root=multi_dir,
                )
                _record(
                    checks,
                    "multi-image-host-forwarding-resolves-only-verified-transports",
                    len(forwarded_multi) == len(prepared_multi["selected_references"])
                    and all(
                        Path(row["resolved_path"]).is_file()
                        for row in forwarded_multi
                    ),
                    canonical_json(forwarded_multi),
                )

                board_dir = temp / "single-board"
                prepared_board = execute_reference_use_plan(
                    board_plan,
                    output_dir=board_dir,
                    max_side=256,
                )
                board = prepared_board["single_board"]
                panels = board["panels"] if isinstance(board, dict) else []
                panel_hashes_correct = all(
                    panel["source_sha256"] == reference["source"]["sha256"]
                    and panel["transport_sha256"]
                    == reference["transport"]["sha256"]
                    for panel, reference in zip(
                        panels,
                        prepared_board["selected_references"],
                        strict=True,
                    )
                )
                _record(
                    checks,
                    "single-board-keeps-source-transport-and-board-hashes-distinct",
                    isinstance(board, dict)
                    and not Path(board["resolved_path"]).is_absolute()
                    and len(panels) == len(prepared_board["selected_references"])
                    and panel_hashes_correct
                    and any(
                        panel["source_sha256"] != panel["transport_sha256"]
                        for panel in panels
                    )
                    and board["sha256"]
                    == _sha256(board_dir / board["resolved_path"]),
                    canonical_json(board),
                )
                forwarded_board = host_reference_transports(
                    prepared_board,
                    package_root=board_dir,
                )
                _record(
                    checks,
                    "single-board-host-forwarding-exposes-only-composite-board",
                    len(forwarded_board) == 1
                    and forwarded_board[0]["role"]
                    == "composite-reference-board"
                    and forwarded_board[0]["sha256"] == board["sha256"],
                    canonical_json(forwarded_board),
                )

                rollback_dir = temp / "rollback-output"
                rollback_dir.mkdir()
                try:
                    failing_plan = build_reference_use_plan(
                        use("pose-camera"),
                        transport_mode="multi-image",
                        target_model="missing-model",
                        source_lighting_mode="replace",
                        light_sources=lights,
                        material_responses=materials,
                    )
                    execute_reference_use_plan(
                        failing_plan,
                        output_dir=rollback_dir,
                        prompt_file=prompt,
                    )
                    rollback_ok = False
                except (ValueError, RuntimeError):
                    rollback_ok = rollback_dir.is_dir() and not any(
                        rollback_dir.iterdir()
                    )
                _record(
                    checks,
                    "failed-materialization-restores-preexisting-empty-output",
                    rollback_ok,
                    str(rollback_dir),
                )
            else:
                blocked_dir = temp / "visual-preflight-blocked"
                try:
                    execute_reference_use_plan(
                        multi_plan,
                        output_dir=blocked_dir,
                        prompt_file=prompt,
                        max_side=128,
                    )
                    structured_preflight = False
                    preflight_detail = "model-facing execution unexpectedly continued"
                except VisualDependencyPreflightError as exc:
                    preflight_detail = canonical_json(exc.report)
                    structured_preflight = (
                        not blocked_dir.exists()
                        and exc.report.get("required") is True
                        and exc.report.get("profile") == "visual"
                        and exc.report.get("check_command")
                        == "python scripts/check_dependencies.py --profile visual"
                        and exc.report.get("install_command")
                        == install_command("visual")[0]
                    )
                _record(
                    checks,
                    "model-facing-svg-rasterization-stops-at-structured-visual-preflight",
                    structured_preflight,
                    preflight_detail,
                )
                for name in (
                    "multi-image-uses-two-independent-role-scoped-transports",
                    "multi-image-host-forwarding-resolves-only-verified-transports",
                    "single-board-keeps-source-transport-and-board-hashes-distinct",
                    "single-board-host-forwarding-exposes-only-composite-board",
                    "failed-materialization-restores-preexisting-empty-output",
                ):
                    skipped_checks.append(
                        {
                            "name": name,
                            "reason": "Visual profile is not available in this environment",
                        }
                    )

            zero_plan = build_reference_use_plan(
                use("local-color"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="rescope",
                include_technical_roles=["subject-mask"],
            )
            zero_dir = temp / "zero-package"
            prepared_zero = execute_reference_use_plan(zero_plan, output_dir=zero_dir)
            _record(
                checks,
                "zero-reference-package-requires-structured-reason",
                prepared_zero["transport_mode"] == "none"
                and prepared_zero["zero_reference_reason"]["code"]
                == "no-suitable-active-asset"
                and prepared_zero["zero_reference_reason"]["record_ids"]
                == [FIXTURE_RECORD_ID],
                canonical_json(prepared_zero["zero_reference_reason"]),
            )
            unexplained = copy.deepcopy(zero_plan)
            unexplained["zero_reference_reason"] = None
            try:
                finalize_reference_use_plan(unexplained)
                unexplained_rejected = False
            except ValueError:
                unexplained_rejected = True
            _record(
                checks,
                "unexplained-zero-activation-is-rejected",
                unexplained_rejected,
                "zero_reference_reason cannot be null",
            )

            impossible = copy.deepcopy(prepared_prompt)
            impossible["prompt_artifacts"] = []
            impossible["prepared_reference_set_sha256"] = "0" * 64
            impossible = finalize_artifact(impossible)
            try:
                validate_prepared_reference_set(impossible, package_root=moved_dir)
                impossible_rejected = False
            except ValueError:
                impossible_rejected = True
            _record(
                checks,
                "impossible-transport-shape-is-rejected",
                impossible_rejected,
                "prompt-artifacts mode cannot omit its plan artifacts",
            )

            duplicate = copy.deepcopy(environment_plan)
            duplicate["reference_items"][1]["semantic_role"] = duplicate["reference_items"][0]["semantic_role"]
            duplicate_report = validate_reference_use_plan(duplicate)
            _record(
                checks,
                "unnamed-reference-averaging-is-rejected",
                not duplicate_report["ok"]
                and any("semantic roles must be unique" in error for error in duplicate_report["errors"]),
                str(duplicate_report["errors"]),
            )

            fabricated = copy.deepcopy(environment_plan)
            fabricated["reference_items"][0]["asset_id"] = "fabricated-asset"
            fabricated["reference_items"][0]["source"]["asset_id"] = "fabricated-asset"
            fabricated = finalize_reference_use_plan(fabricated)
            fabricated_report = validate_reference_use_plan(fabricated)
            _record(
                checks,
                "fabricated-pack-artifact-is-rejected",
                not fabricated_report["ok"],
                str(fabricated_report["errors"]),
            )
            stale = copy.deepcopy(environment_plan)
            stale["reference_items"][0]["source"]["sha256"] = "b" * 64
            stale = finalize_reference_use_plan(stale)
            stale_report = validate_reference_use_plan(stale)
            _record(
                checks,
                "stale-pack-source-hash-is-rejected",
                not stale_report["ok"],
                str(stale_report["errors"]),
            )

            plans_by_mode = [
                environment_plan,
                build_reference_use_plan(
                    use("environment"),
                    transport_mode="svg-bundle",
                    source_lighting_mode="preserve",
                ),
                multi_plan,
                board_plan,
            ]
            activate_fixture(False)
            inactive_reports = [validate_reference_use_plan(item) for item in plans_by_mode]
            _record(
                checks,
                "inactive-pack-is-rejected-in-every-transport-mode",
                all(report["ok"] is False for report in inactive_reports),
                canonical_json(inactive_reports),
            )
            activate_fixture(True)

            try:
                build_reference_use_plan(
                    [
                        {
                            "record_id": UNSUPPORTED_RECORD_ID,
                            "intended_influence": "identity",
                        }
                    ],
                    transport_mode="prompt-artifacts",
                    source_lighting_mode="preserve",
                )
                unsupported_scope_rejected = False
                unsupported_scope_detail = "plan unexpectedly built"
            except ValueError as exc:
                unsupported_scope_detail = str(exc)
                unsupported_scope_rejected = (
                    "does not affirmatively support intended influence 'identity'"
                    in unsupported_scope_detail
                )
            _record(
                checks,
                "unsupported-record-influence-is-rejected-before-artifact-selection",
                unsupported_scope_rejected,
                unsupported_scope_detail,
            )

            scene_path = fixture_pack / "records" / "scene.json"
            original_scene_text = scene_path.read_text(encoding="utf-8")
            try:
                changed_scene = json.loads(original_scene_text)
                active_scene = next(
                    record
                    for record in changed_scene["records"]
                    if record["id"] == FIXTURE_RECORD_ID
                )
                active_scene["defaults"] = {
                    "outfit": "a fitted blue field jacket",
                    "pose": "standing three-quarter pose",
                    "camera": "eye-level portrait framing",
                    "lighting": "soft neutral key",
                    "environment": "plain off-white studio background",
                }
                active_scene.pop("must_preserve", None)
                active_scene["tags"] = ["fixture visual reference"]
                scene_path.write_text(
                    json.dumps(changed_scene, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                write_lock(fixture_pack)
                activate_fixture(True)
                stale_scope_report = validate_reference_use_plan(identity_plan)
                stale_scope_rejected = (
                    stale_scope_report["ok"] is False
                    and any(
                        "semantic scope is invalid" in error
                        for error in stale_scope_report["errors"]
                    )
                )
            finally:
                scene_path.write_text(
                    original_scene_text,
                    encoding="utf-8",
                    newline="\n",
                )
                write_lock(fixture_pack)
                activate_fixture(True)
            _record(
                checks,
                "stale-active-record-semantic-scope-is-rejected",
                stale_scope_rejected,
                canonical_json(stale_scope_report),
            )

            legitimate_multi_scope = build_reference_use_plan(
                [
                    {"record_id": FIXTURE_RECORD_ID, "intended_influence": "identity"},
                    {"record_id": FIXTURE_RECORD_ID, "intended_influence": "outfit"},
                ],
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            legitimate_multi_scope_report = validate_reference_use_plan(
                legitimate_multi_scope
            )
            represented_influences = {
                item["intended_influence"]
                for item in legitimate_multi_scope["reference_items"]
            }
            _record(
                checks,
                "legitimate-multi-scope-scene-supports-identity-and-outfit",
                legitimate_multi_scope_report["ok"]
                and represented_influences == {"identity", "outfit"},
                canonical_json(
                    {
                        "validation": legitimate_multi_scope_report,
                        "represented_influences": sorted(represented_influences),
                    }
                ),
            )
            environment_surface_plan = environment_plan["surface_lighting_plan"]
            _record(
                checks,
                "non-lighting-reference-cannot-authorize-source-lighting-preservation",
                environment_surface_plan["source_evidence_roles"] == []
                and any(
                    "source lighting cannot be preserved" in decision
                    for decision in environment_surface_plan["unresolved_decisions"]
                ),
                canonical_json(environment_surface_plan),
            )
            lighting_plan = build_reference_use_plan(
                use("lighting"),
                transport_mode="prompt-artifacts",
                source_lighting_mode="preserve",
            )
            lighting_surface_plan = lighting_plan["surface_lighting_plan"]
            forged_partial_lighting = copy.deepcopy(lighting_plan)
            specular_semantic_role = next(
                item["semantic_role"]
                for item in forged_partial_lighting["reference_items"]
                if item["technical_role"] == "specular-audit"
            )
            forged_partial_lighting["surface_lighting_plan"][
                "source_evidence_roles"
            ] = [specular_semantic_role]
            forged_partial_lighting["surface_lighting_plan"] = finalize_artifact(
                forged_partial_lighting["surface_lighting_plan"]
            )
            forged_partial_lighting["surface_lighting_plan_sha256"] = (
                forged_partial_lighting["surface_lighting_plan"][
                    "surface_lighting_plan_sha256"
                ]
            )
            forged_partial_lighting["reference_use_plan_sha256"] = "0" * 64
            forged_partial_lighting = finalize_artifact(forged_partial_lighting)
            forged_partial_report = validate_reference_use_plan(
                forged_partial_lighting
            )
            _record(
                checks,
                "partial-lighting-evidence-cannot-authorize-full-source-lighting-preservation",
                any(
                    item["semantic_role"]
                    in lighting_surface_plan["source_evidence_roles"]
                    for item in lighting_plan["reference_items"]
                    if item["technical_role"] == "faithful-archival-vector"
                )
                and lighting_surface_plan["unresolved_decisions"] == []
                and forged_partial_report["ok"] is False
                and any(
                    "must exactly match complete lighting-authorized" in error
                    for error in forged_partial_report["errors"]
                ),
                canonical_json(
                    {
                        "complete": lighting_surface_plan,
                        "forged_partial": forged_partial_report,
                    }
                ),
            )
    except Exception as exc:  # keep output structured
        errors.append(str(exc))
    finally:
        configure_pack_runtime(None)

    failed = [row for row in checks if not row["passed"]]
    errors.extend(f"{row['name']}: {row['detail']}" for row in failed)
    contract_ok = not errors
    complete = contract_ok and not skipped_checks
    status = (
        "passed"
        if complete
        else "passed-with-environment-skips"
        if contract_ok
        else "failed"
    )
    return {
        "ok": contract_ok,
        "complete": complete,
        "status": status,
        "contract_checks": {
            "ok": contract_ok,
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "total": len(checks),
        },
        "environment_prerequisites": {
            "ok": all(row["ok"] for row in environment_prerequisites),
            "profiles": environment_prerequisites,
        },
        "checks": checks,
        "skipped_checks": skipped_checks,
        "errors": errors,
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)
