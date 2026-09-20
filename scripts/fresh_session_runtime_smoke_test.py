#!/usr/bin/env python3
"""End-to-end fresh-session regression for prompt plus SVG delivery.

The test builds an isolated core containing only packs/commons plus a neutral
temporary fixture pack, then starts from a literal brief instead of record IDs.
It uses one explicit pack state and the documented public CLI subprocesses,
discovers a direction, retrieves identity and staging candidates in one
four-request batch process, inspects the selected canonical records, activates
linked evidence, and materializes exact source SVGs as prompt artifacts.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from package_metadata import load_package_metadata
from runtime_read_footprint import count_words as _count_words
from pack_manager import write_lock
from reference_contract import authority_for


ROOT = Path(__file__).resolve().parents[1]
BRIEF = "muscular anthropomorphic black panther"
DOMAIN = "anthropomorphic-animal"
REQUIRED_CONTENT_CAPABILITIES = {
    "character-archetypes",
    "searchable-assets",
    "evidence-artifact-reference",
    "visual-evidence",
}
REQUIRED_RUNTIME_RESOURCES = {"discovery-lanes"}
REQUIRED_TECHNICAL_ROLES = {"structural-line-tone", "subject-mask"}
IDENTITY_EXCLUDED_STATE = {
    "gaze": ("gaze", "eye contact", "eye direction"),
    "expression": ("expression",),
    "mouth": ("mouth", "smirk", "grin", "smile"),
    "perspiration": ("perspiration", "sweat"),
    "outfit": ("outfit", "clothing", "garment"),
    "lighting": ("lighting", "light source"),
}
RUNTIME_CONTEXT_PATHS = (
    Path("SKILL.md"),
    Path("references/runtime/prompt-composition.md"),
    Path("references/runtime/sparse-discovery.md"),
    Path("references/runtime/reference-prompt-artifacts.md"),
    Path("references/runtime/pack-state-quickstart.md"),
)
PROBE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "around",
    "as",
    "by",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "of",
    "on",
    "one",
    "or",
    "the",
    "their",
    "this",
    "through",
    "to",
    "toward",
    "while",
    "with",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _build_isolated_core(core_root: Path) -> Path:
    """Copy only declared core-release inputs, which include packs/commons alone."""

    metadata = load_package_metadata(ROOT)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    for relative in metadata.release_include:
        source = ROOT / relative
        destination = core_root / relative
        if source.is_dir():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination, ignore=ignore)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    copied_packs = sorted(
        path.name
        for path in (core_root / "packs").iterdir()
        if path.is_dir() and (path / "pack.json").is_file()
    )
    if copied_packs != ["commons"]:
        raise ValueError(
            "isolated core must contain only the declared commons pack; "
            f"found {copied_packs}"
        )
    return core_root.resolve()


def _build_fixture_pack(pack_container: Path) -> dict[str, Any]:
    """Author a minimal deterministic pack without using any external pack data."""

    fixture_root = pack_container / "fresh-session-fixture"
    fixture_root.mkdir(parents=True, exist_ok=False)
    archetype_id = "fixture-black-panther-archetype"
    scene_id = "fixture-low-angle-athletic-scene"
    asset_id = "fixture-low-angle-athletic-visual-evidence"
    pack_id = "0195c0de-0000-7000-8000-000000000001"

    structural_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
        'viewBox="0 0 240 180">\n'
        '  <rect width="240" height="180" fill="#f7f7f5"/>\n'
        '  <path d="M40 156 C58 122 72 92 105 76 C126 66 152 74 164 96 '
        'C178 119 172 143 204 156" fill="none" stroke="#222" '
        'stroke-width="8" stroke-linecap="round"/>\n'
        '  <circle cx="116" cy="58" r="25" fill="none" stroke="#222" '
        'stroke-width="7"/>\n'
        '  <path d="M82 105 L48 130 M148 106 L187 126 M105 126 L88 164 '
        'M145 127 L160 164" fill="none" stroke="#555" stroke-width="6" '
        'stroke-linecap="round"/>\n'
        '</svg>\n'
    ).encode("utf-8")
    subject_mask_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180" '
        'viewBox="0 0 240 180">\n'
        '  <rect width="240" height="180" fill="#000"/>\n'
        '  <circle cx="116" cy="58" r="27" fill="#fff"/>\n'
        '  <path d="M37 160 C54 124 74 86 106 76 C134 68 158 78 169 104 '
        'C180 130 184 145 207 160 Z" fill="#fff"/>\n'
        '</svg>\n'
    ).encode("utf-8")
    structural_relative = "resources/reference/structural-line-tone.svg"
    mask_relative = "resources/reference/subject-mask.svg"
    structural_path = fixture_root / structural_relative
    mask_path = fixture_root / mask_relative
    structural_path.parent.mkdir(parents=True, exist_ok=True)
    structural_path.write_bytes(structural_svg)
    mask_path.write_bytes(subject_mask_svg)
    structural_sha256 = hashlib.sha256(structural_svg).hexdigest()
    mask_sha256 = hashlib.sha256(subject_mask_svg).hexdigest()

    archetype = {
        "kind": "archetype",
        "records": [
            {
                "id": archetype_id,
                "label": "Muscular anthropomorphic black panther",
                "curation_status": "curated",
                "domain": DOMAIN,
                "domains": [DOMAIN],
                "character_lock": (
                    "A muscular upright black panther with a broad feline torso, "
                    "matte charcoal-black short fur, a compact feline muzzle, rounded "
                    "ears, amber irises, a thick tapered tail, and one swept-back crest "
                    "of longer head fur"
                ),
                "defaults": {
                    "gaze": "no automatic eye contact; follow the current action target",
                    "expression": "focused scene-specific concentration",
                    "mouth": "closed mouth with a relaxed jaw",
                    "perspiration": "dry coat with no sweat",
                    "outfit": "simple scene-specific athletic attire",
                    "lighting": "neutral scene-specific illumination",
                },
                "tags": [
                    "black panther",
                    "muscular feline",
                    "anthropomorphic animal",
                ],
                "search_terms": [
                    {
                        "phrase": BRIEF,
                        "facet": "archetype",
                        "weight": 10.0,
                        "source": "fixture",
                    },
                    {
                        "phrase": "black panther",
                        "facet": "species",
                        "weight": 9.0,
                        "source": "fixture",
                    },
                    {
                        "phrase": "muscular anthropomorphic feline",
                        "facet": "body_build",
                        "weight": 8.0,
                        "source": "fixture",
                    },
                ],
            }
        ],
    }
    scene = {
        "kind": "scene",
        "records": [
            {
                "id": scene_id,
                "label": "Low-angle athletic motion study",
                "curation_status": "curated",
                "domain": DOMAIN,
                "domains": [DOMAIN],
                "image_promise": (
                    "A low-angle athletic motion scene with a clear planted stance, "
                    "readable hand-to-ball contact, and layered depth."
                ),
                "staging": {
                    "body_geometry": (
                        "Plant the near foot under the center of mass while the torso "
                        "leans forward as one connected athletic volume."
                    ),
                    "action_geometry": (
                        "Lower one hand toward a ball beside the near knee and keep the "
                        "other arm open for balance."
                    ),
                    "prop_or_contact_geometry": (
                        "Show one precise hand-to-ball contact and a compressed ball "
                        "shadow directly below it."
                    ),
                    "depth_order": (
                        "Near foot and ball lead, the figure occupies the middle plane, "
                        "and two simple court marks recede behind."
                    ),
                },
                "performance_language": {
                    "channel_cues": [
                        {
                            "channel": "gaze",
                            "visual_instruction": (
                                "Aim both eyes toward the moving ball below and ahead "
                                "of the face."
                            ),
                        }
                    ]
                },
                "camera_contract": {
                    "framing_and_crop": (
                        "Use a moderately low three-quarter full-body framing with "
                        "clear space around the ball and planted foot."
                    )
                },
                "defaults": {
                    "subject": "one athletic character",
                    "body": "muscular proportions connected through the action line",
                    "pose": "low controlled dribble stance",
                    "expression": "focused attention on the action target",
                    "outfit": "plain sleeveless training top and shorts",
                    "composition": "diagonal action from face through hand to ball",
                    "camera": "moderately low three-quarter viewpoint",
                    "lighting": "broad neutral overhead key with open fill",
                    "environment": "minimal indoor practice court",
                    "mood": "controlled athletic concentration",
                },
                "tags": ["athletic motion", "low angle", "planted stance"],
                "search_terms": [
                    {
                        "phrase": "low-angle athletic motion scene clear planted",
                        "facet": "scene",
                        "weight": 10.0,
                        "source": "fixture",
                    },
                    {
                        "phrase": "athletic motion planted stance",
                        "facet": "scene",
                        "weight": 9.0,
                        "source": "fixture",
                    },
                    {
                        "phrase": "low angle ball contact action",
                        "facet": "scene",
                        "weight": 8.0,
                        "source": "fixture",
                    },
                ],
            }
        ],
    }
    asset = {
        "kind": "asset",
        "records": [
            {
                "id": asset_id,
                "label": "Neutral athletic pose visual evidence",
                "category": "visual-evidence",
                "asset_type": "visual-evidence",
                "description": (
                    "Test-only schematic evidence for pose, camera, silhouette, and "
                    "subject-background separation."
                ),
                "source_ref_id": "fixture-authored-athletic-structure",
                "source_sha256": structural_sha256,
                "source_media_type": "image/svg+xml",
                "source_dimensions": {"width": 240, "height": 180},
                "disposition": "generated deterministic test fixture",
                "evidence_relation": "structural evidence linked to the fixture scene",
                "canonical_record_ids": [scene_id],
                "primary_resource": structural_relative,
                "resource_refs": [structural_relative, mask_relative],
                "artifacts": [
                    {
                        "artifact_id": "fixture-structural-line-tone",
                        "role": "structural-line-tone",
                        "path": structural_relative,
                        "media_type": "image/svg+xml",
                        "sha256": structural_sha256,
                    },
                    {
                        "artifact_id": "fixture-subject-mask",
                        "role": "subject-mask",
                        "path": mask_relative,
                        "media_type": "image/svg+xml",
                        "sha256": mask_sha256,
                    },
                ],
                "tags": ["test fixture", "pose evidence", "evidence artifact"],
                "search_terms": [
                    {
                        "phrase": "athletic pose visual evidence",
                        "facet": "asset",
                        "weight": 1.0,
                        "source": "fixture",
                    }
                ],
            }
        ],
    }
    _write_json(fixture_root / "records" / "archetypes.json", archetype)
    _write_json(fixture_root / "records" / "scenes.json", scene)
    _write_json(fixture_root / "records" / "assets.json", asset)

    lane_specs = (
        (
            "grounded-drive",
            "Grounded drive",
            "grounded athletic drive",
            "style-family-sculpted-presence",
            "camera-low-three-quarter",
            "lighting-dusk-rim",
        ),
        (
            "diagonal-action",
            "Diagonal action",
            "diagonal athletic action",
            "style-family-clear-portrait",
            "camera-close-eye-level",
            "lighting-cool-window",
        ),
        (
            "contact-study",
            "Contact study",
            "clear ball contact study",
            "style-family-quiet-editorial",
            "camera-profile-space",
            "lighting-overcast-ambient",
        ),
        (
            "layered-court",
            "Layered court",
            "layered practice-court depth",
            "style-family-environmental-illustration",
            "camera-environmental-medium",
            "lighting-neutral-bounce",
        ),
    )
    lanes = []
    for priority, (
        suffix,
        label,
        summary,
        style_id,
        camera_id,
        lighting_id,
    ) in enumerate(lane_specs, start=1):
        lanes.append(
            {
                "id": f"fixture-{suffix}",
                "label": label,
                "domains": [DOMAIN],
                "priority": 110 - priority,
                "summary": (
                    f"A {summary} direction with a low camera, readable contact, "
                    "and a clean silhouette."
                ),
                "scene_query": "low-angle athletic motion scene clear planted",
                "style_family_id": style_id,
                "camera_id": camera_id,
                "camera_query": "athletic character camera",
                "lighting_id": lighting_id,
                "lighting_query": "clear athletic lighting",
                "preferred_scene_ids": [scene_id],
                "adds": [summary, "readable hand-to-ball contact"],
                "adjustable": ["action phase", "camera height", "court depth"],
            }
        )
    _write_json(
        fixture_root / "resources" / "discovery-lanes.json",
        {
            "purpose": "Deterministic fresh-session integration directions.",
            "count": len(lanes),
            "lanes": lanes,
        },
    )
    _write_json(
        fixture_root / "resources" / "fixture-maintenance-note.json",
        {
            "purpose": (
                "An intentionally unselected named resource for provider-boundary "
                "regression."
            )
        },
    )
    manifest = {
        "pack_id": pack_id,
        "name": "Fresh Session Integration Fixture",
        "description": (
            "Deterministic temporary records and SVGs used only by the self-contained "
            "fresh-session runtime regression."
        ),
        "release": "2026.01.01.1",
        "content": {
            "record_globs": ["records/**/*.json"],
            "resource_globs": ["resources/**/*"],
            "resource_bindings": {
                "discovery-lanes": "resources/discovery-lanes.json",
                "fixture-maintenance-note": (
                    "resources/fixture-maintenance-note.json"
                ),
            },
        },
        "capabilities": sorted(
            {
                *REQUIRED_CONTENT_CAPABILITIES,
                "scene-records",
                "sparse-brief-discovery",
            }
        ),
        "dependencies": [],
        "optional_dependencies": [],
        "replaces": [],
        "license": "CC0-1.0",
    }
    _write_json(fixture_root / "pack.json", manifest)
    lock = write_lock(fixture_root)
    return {
        "root": fixture_root.resolve(),
        "pack_container": pack_container.resolve(),
        "pack_id": pack_id,
        "lock_content_sha256": lock["content_sha256"],
        "svg_sha256": {
            "structural-line-tone": structural_sha256,
            "subject-mask": mask_sha256,
        },
    }


def _scene_probe(card: Mapping[str, Any]) -> str:
    """Derive a concise scene probe from card prose, never from its preset ID."""

    text = str(card.get("what_you_get") or "")
    if "Catalog staging option:" in text:
        text = text.split("Catalog staging option:", 1)[1]
    words = [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text)
        if token.lower() not in PROBE_STOP_WORDS
    ]
    probe = " ".join(words[:6])
    if len(probe.split()) < 3:
        raise ValueError("direction card did not provide a usable three-to-six-word probe")
    return probe


def _words(path: Path) -> int:
    return _count_words(path.read_text(encoding="utf-8"))


def _text_words(value: str) -> int:
    return _count_words(value)


def _run_cli(
    arguments: Sequence[str],
    *,
    cwd: Path,
    label: str,
    trace: list[dict[str, Any]],
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-B", *arguments]
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    trace.append(
        {
            "label": label,
            "argv": [str(value) for value in arguments],
            "returncode": result.returncode,
        }
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit {result.returncode}: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    return result


def _run_json_cli(
    arguments: Sequence[str],
    *,
    cwd: Path,
    label: str,
    trace: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    result = _run_cli(arguments, cwd=cwd, label=label, trace=trace)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not emit one JSON value: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} emitted {type(value).__name__}, not a JSON object")
    return value, result.stdout


def _run_expected_json_failure(
    arguments: Sequence[str],
    *,
    cwd: Path,
    label: str,
    trace: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    command = [sys.executable, "-B", *arguments]
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    trace.append(
        {
            "label": label,
            "argv": [str(value) for value in arguments],
            "returncode": result.returncode,
        }
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not emit one JSON value: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} emitted {type(value).__name__}, not a JSON object")
    if result.returncode == 0 or value.get("ok") is not False:
        raise RuntimeError(
            f"{label} did not produce the expected structured CLI failure"
        )
    return value, result.returncode


def _activate_runtime_packs(
    core_root: Path,
    pack_container: Path,
    runtime_root: Path,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one isolated runtime context entirely through public pack CLI calls."""

    runtime_root.mkdir(parents=True, exist_ok=True)
    state_path = runtime_root / "pack-state.json"
    cache_dir = runtime_root / "cache"
    managed_root = runtime_root / "managed"
    pack_prefix = [
        "scripts/pack_cli.py",
        "--state-file",
        str(state_path),
        "--cache-dir",
        str(cache_dir),
        "--managed-root",
        str(managed_root),
    ]

    root_add, _root_add_stdout = _run_json_cli(
        [*pack_prefix, "root-add", str(pack_container.resolve())],
        cwd=core_root,
        label="pack-root-add",
        trace=trace,
    )
    initial_state = dict(root_add.get("state") or {})
    initial_enabled = {str(value) for value in initial_state.get("enabled_packs") or []}
    if not initial_enabled:
        raise ValueError("the shipped runtime state did not enable a default pack")
    registered_roots = {
        str(Path(str(value)).resolve())
        for value in initial_state.get("pack_roots") or []
    }
    registered_container = str(pack_container.resolve())
    if registered_container not in registered_roots:
        raise ValueError("pack root-add did not register the packs container")

    listed, _listed_stdout = _run_json_cli(
        [*pack_prefix, "list"],
        cwd=core_root,
        label="pack-list-candidates",
        trace=trace,
    )
    pack_rows = {
        str(row.get("pack_id") or ""): dict(row)
        for row in listed.get("packs") or []
        if isinstance(row, Mapping) and row.get("pack_id")
    }
    if not pack_rows:
        raise ValueError("pack list did not discover any candidates")

    capable_candidates = sorted(
        pack_id
        for pack_id, row in pack_rows.items()
        if pack_id not in initial_enabled
        and row.get("valid") is True
        and REQUIRED_CONTENT_CAPABILITIES.issubset(
            {str(value) for value in row.get("capabilities") or []}
        )
    )
    if not capable_candidates:
        required = ", ".join(sorted(REQUIRED_CONTENT_CAPABILITIES))
        raise FileNotFoundError(
            "fresh-session integration requires a nondefault discovered pack with "
            f"capabilities: {required}"
        )
    content_pack_id = capable_candidates[0]

    inspections: dict[str, dict[str, Any]] = {}
    for pack_id in sorted(pack_rows):
        inspected, _inspected_stdout = _run_json_cli(
            [*pack_prefix, "inspect", pack_id],
            cwd=core_root,
            label=f"pack-inspect-{pack_id}",
            trace=trace,
        )
        inspections[pack_id] = inspected

    selected_inspection = inspections[content_pack_id]
    if selected_inspection.get("ok") is not True:
        raise ValueError(f"capable content pack did not pass inspect: {content_pack_id}")
    inspected_capabilities = {
        str(value)
        for value in (selected_inspection.get("manifest") or {}).get(
            "capabilities"
        )
        or []
    }
    if not REQUIRED_CONTENT_CAPABILITIES.issubset(inspected_capabilities):
        raise ValueError(
            f"pack list and inspect capabilities disagree for {content_pack_id}"
        )

    enabled = set(initial_enabled)
    enable_order: list[str] = []
    visiting: set[str] = set()

    def enable_with_dependencies(pack_id: str) -> None:
        if pack_id in enabled:
            return
        if pack_id in visiting:
            raise ValueError(f"pack dependency cycle reached while enabling {pack_id}")
        inspected = inspections.get(pack_id)
        if inspected is None:
            raise ValueError(f"required pack dependency was not discovered: {pack_id}")
        visiting.add(pack_id)
        manifest = dict(inspected.get("manifest") or {})
        for dependency in manifest.get("dependencies") or []:
            if not isinstance(dependency, Mapping) or not dependency.get("pack_id"):
                raise ValueError(f"pack {pack_id} has an invalid dependency declaration")
            enable_with_dependencies(str(dependency["pack_id"]))
        visiting.remove(pack_id)
        _run_json_cli(
            [*pack_prefix, "enable", pack_id],
            cwd=core_root,
            label=f"pack-enable-{pack_id}",
            trace=trace,
        )
        enabled.add(pack_id)
        enable_order.append(pack_id)

    enable_with_dependencies(content_pack_id)

    providers_before, _providers_before_stdout = _run_json_cli(
        [*pack_prefix, "provider-list"],
        cwd=core_root,
        label="pack-provider-list-before-selection",
        trace=trace,
    )
    provider_rows_before = {
        str(row.get("name") or ""): dict(row)
        for row in providers_before.get("resource_providers") or []
        if isinstance(row, Mapping) and row.get("name")
    }
    provider_select_commands: list[str] = []
    for resource_name in sorted(REQUIRED_RUNTIME_RESOURCES):
        provider = provider_rows_before.get(resource_name)
        if provider is None:
            raise ValueError(f"required runtime resource was not listed: {resource_name}")
        candidate_packs = {
            str(value) for value in provider.get("candidate_packs") or []
        }
        if content_pack_id not in candidate_packs:
            raise ValueError(
                f"capable content pack does not provide {resource_name}: "
                f"{content_pack_id}"
            )
        if provider.get("selected_pack") != content_pack_id:
            _run_json_cli(
                [
                    *pack_prefix,
                    "provider-select",
                    resource_name,
                    content_pack_id,
                ],
                cwd=core_root,
                label=f"pack-provider-select-{resource_name}",
                trace=trace,
            )
            provider_select_commands.append(resource_name)

    providers_after, _providers_after_stdout = _run_json_cli(
        [*pack_prefix, "provider-list"],
        cwd=core_root,
        label="pack-provider-list-after-selection",
        trace=trace,
    )
    provider_rows_after = {
        str(row.get("name") or ""): dict(row)
        for row in providers_after.get("resource_providers") or []
        if isinstance(row, Mapping) and row.get("name")
    }
    for resource_name in REQUIRED_RUNTIME_RESOURCES:
        provider = provider_rows_after.get(resource_name) or {}
        if provider.get("selected_pack") != content_pack_id or not provider.get(
            "resolved"
        ):
            raise ValueError(
                f"required provider selection did not resolve: {resource_name}"
            )

    unselected_rows = {
        name: row
        for name, row in provider_rows_after.items()
        if row.get("selected_pack") is None and not row.get("resolved")
    }
    unselected_diagnostics = [
        dict(row)
        for row in providers_after.get("diagnostics") or []
        if isinstance(row, Mapping)
        and row.get("code") == "resource-provider-unselected"
    ]
    warning_resources = {
        str(row.get("resource") or "")
        for row in unselected_diagnostics
        if row.get("severity") == "warning"
    }
    error_resources = {
        str(row.get("resource") or "")
        for row in unselected_diagnostics
        if row.get("severity") == "error"
    }
    if not unselected_rows or warning_resources != set(unselected_rows) or error_resources:
        raise ValueError(
            "provider-list did not report every unselected resource as warning-only"
        )

    failure_resource = sorted(warning_resources)[0]
    resource_failure, resource_failure_code = _run_expected_json_failure(
        [*pack_prefix, "resource", failure_resource],
        cwd=core_root,
        label="pack-resource-unselected-failure",
        trace=trace,
    )
    if failure_resource not in str(resource_failure.get("error") or ""):
        raise ValueError("unselected resource failure did not identify the resource")

    final_listing, _final_listing_stdout = _run_json_cli(
        [*pack_prefix, "list"],
        cwd=core_root,
        label="pack-list-active",
        trace=trace,
    )
    final_enabled = {
        str(value) for value in final_listing.get("enabled_packs") or []
    }
    final_rows = {
        str(row.get("pack_id") or ""): dict(row)
        for row in final_listing.get("packs") or []
        if isinstance(row, Mapping) and row.get("pack_id")
    }
    pack_roots = {
        pack_id: Path(str(final_rows[pack_id]["root"])).resolve()
        for pack_id in final_enabled
        if pack_id in final_rows
    }
    if set(pack_roots) != final_enabled:
        raise ValueError("final pack list did not expose every enabled pack root")

    content_manifest = dict(inspections[content_pack_id].get("manifest") or {})
    return {
        "state_path": state_path,
        "cache_dir": cache_dir,
        "managed_root": managed_root,
        "registered_container": registered_container,
        "initial_enabled": sorted(initial_enabled),
        "enabled_packs": sorted(final_enabled),
        "pack_roots": pack_roots,
        "content_pack_id": content_pack_id,
        "content_pack_root": pack_roots[content_pack_id],
        "content_manifest": content_manifest,
        "enable_order": enable_order,
        "provider_select_commands": provider_select_commands,
        "provider_rows": provider_rows_after,
        "unselected_warning_resources": sorted(warning_resources),
        "resource_failure": {
            "name": failure_resource,
            "returncode": resource_failure_code,
            "payload": resource_failure,
        },
    }


def _replace_option_value(arguments: list[str], option: str, value: str) -> None:
    try:
        index = arguments.index(option)
    except ValueError as exc:
        raise ValueError(f"plan example is missing {option}") from exc
    if index + 1 >= len(arguments):
        raise ValueError(f"plan example has no value for {option}")
    arguments[index + 1] = value


def _canonical_record_from_source(
    inspected: Mapping[str, Any],
    pack_roots: Mapping[str, Path],
) -> dict[str, Any]:
    pack_id = str(inspected.get("source_pack") or "")
    record_id = str(inspected.get("record_id") or "")
    source_file = str(inspected.get("source_file") or "")
    pack_root = pack_roots.get(pack_id)
    if pack_root is None or not source_file:
        raise ValueError(f"inspect output has no resolvable source for {record_id}")
    source_path = (pack_root / source_file).resolve()
    if pack_root.resolve() not in source_path.parents:
        raise ValueError(f"inspect source escapes its pack: {source_file}")
    value = json.loads(source_path.read_text(encoding="utf-8"))
    matches: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, Mapping):
            if str(node.get("id") or "") == record_id:
                matches.append(dict(node))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    if len(matches) != 1:
        raise ValueError(
            f"expected one canonical source record for {record_id}, found {len(matches)}"
        )
    return matches[0]


def _record(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: Any,
) -> bool:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    return bool(passed)


def _require(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: Any,
) -> None:
    if not _record(checks, name, passed, detail):
        raise AssertionError(name)


def _select_records(
    recommendation: Mapping[str, Any],
    batch: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    batch_rows = list(batch.get("results") or [])
    if len(batch_rows) != 4 or not all(row.get("ok") for row in batch_rows):
        raise ValueError("the four-request catalog batch did not complete")

    identity_hits = list((batch_rows[0].get("result") or {}).get("results") or [])
    archetype = next(
        (
            row
            for row in identity_hits
            if row.get("kind") == "archetype"
            and "black panther" in str(row.get("outcome_summary") or "").lower()
        ),
        None,
    )
    if archetype is None:
        raise ValueError("batch discovery did not return a black-panther archetype")

    cards = list(recommendation.get("direction_cards") or [])[:3]
    chosen_scene: dict[str, Any] | None = None
    for card, response in zip(cards, batch_rows[1:], strict=True):
        recommended_id = str((card.get("preset_ids") or {}).get("scene") or "")
        hits = list((response.get("result") or {}).get("results") or [])
        returned_recommendation = next(
            (row for row in hits if str(row.get("id") or "") == recommended_id),
            None,
        )
        if (
            returned_recommendation is not None
            and int(
                (returned_recommendation.get("linked_asset_activation") or {}).get(
                    "asset_count", 0
                )
            )
            > 0
        ):
            chosen_scene = returned_recommendation
            break
    if chosen_scene is None:
        raise ValueError(
            "no batch-confirmed recommended scene exposed linked visual evidence"
        )

    retrieval_inputs = [
        BRIEF,
        *[
            str((row.get("result") or {}).get("query_request", {}).get("canonical_query") or "")
            for row in batch_rows[1:]
        ],
    ]
    return dict(archetype), dict(chosen_scene), retrieval_inputs


def _compose_prompt(
    archetype_record: Mapping[str, Any],
    scene_record: Mapping[str, Any],
    identity_authority: Mapping[str, Any],
) -> str:
    character_lock = str(archetype_record["character_lock"])
    defaults = dict(scene_record.get("defaults") or {})
    staging = dict(scene_record.get("staging") or {})
    performance = dict(scene_record.get("performance_language") or {})
    gaze = "Aim both eyes toward the current action target beyond the camera."
    for cue in performance.get("channel_cues") or []:
        if isinstance(cue, Mapping) and cue.get("channel") == "gaze":
            gaze = str(cue.get("visual_instruction") or gaze)
            break

    current_state = {
        "gaze": gaze,
        "expression": str(
            defaults.get("expression") or "focused scene-specific concentration"
        ),
        "mouth": "a closed, set mouth appropriate to the current action",
        "perspiration": "dry presentation with no visible perspiration",
        "outfit": str(defaults.get("outfit") or "scene-appropriate original clothing"),
        "lighting": str(defaults.get("lighting") or "scene-specific target lighting"),
    }
    lines = [
        f"Create one coherent image for this brief: {BRIEF}.",
        "",
        f"Image promise: {scene_record.get('image_promise') or scene_record.get('label')}.",
        "",
        "Permanent identity authority:",
        character_lock + ".",
        "It controls only: " + "; ".join(identity_authority["controls"]) + ".",
        "It does not control any scene-conditioned presentation, including: "
        + "; ".join(identity_authority["must_not_control"])
        + ".",
        "",
        "Current scene-specific character state:",
        *[
            f"- {name}: {value}."
            for name, value in current_state.items()
        ],
        "",
        "Pose, contact, camera, and depth:",
        str(staging.get("body_geometry") or defaults.get("pose") or ""),
        str(staging.get("action_geometry") or ""),
        str(staging.get("prop_or_contact_geometry") or ""),
        str(staging.get("depth_order") or defaults.get("composition") or ""),
        str((scene_record.get("camera_contract") or {}).get("framing_and_crop") or defaults.get("camera") or ""),
        "",
        "Use the delivered structural-line-tone and subject-mask SVGs only for "
        "pose, camera, crop, silhouette, overlap order, and subject-background "
        "separation. Rebuild identity and all current state from the text above.",
    ]
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    selected_ids: dict[str, str] = {}
    summary: dict[str, Any] = {"brief": BRIEF}
    cli_trace: list[dict[str, Any]] = []
    batch_process_count = 0

    try:
        with tempfile.TemporaryDirectory(prefix="cpb-fresh-session-") as temporary:
            temporary_root = Path(temporary).resolve()
            core_root = _build_isolated_core(temporary_root / "core")
            fixture = _build_fixture_pack(temporary_root / "fixture-packs")
            activation = _activate_runtime_packs(
                core_root,
                Path(fixture["pack_container"]),
                temporary_root / "runtime",
                cli_trace,
            )
            state_path = Path(activation["state_path"])
            cache_dir = Path(activation["cache_dir"])
            managed_root = Path(activation["managed_root"])
            content_pack_root = str(activation["content_pack_root"])
            summary["isolated_core_root"] = str(core_root)
            summary["explicit_pack_state"] = str(state_path)
            summary["content_pack_root"] = content_pack_root
            summary["fixture"] = {
                "root": str(fixture["root"]),
                "lock_content_sha256": fixture["lock_content_sha256"],
                "svg_sha256": fixture["svg_sha256"],
            }
            pack_roots = dict(activation["pack_roots"])
            content_manifest = dict(activation["content_manifest"])
            content_pack_id = str(activation["content_pack_id"])
            _require(
                checks,
                "public-pack-activation-enables-default-and-capable-content",
                set(activation["enabled_packs"]) == set(pack_roots)
                and set(activation["initial_enabled"]).issubset(pack_roots)
                and content_pack_id in pack_roots
                and Path(content_pack_root).resolve() == Path(fixture["root"])
                and all(
                    pack_root.is_relative_to(core_root / "packs")
                    or pack_root == Path(fixture["root"])
                    for pack_root in pack_roots.values()
                )
                and REQUIRED_CONTENT_CAPABILITIES.issubset(
                    {str(value) for value in content_manifest.get("capabilities") or []}
                )
                and set(activation["provider_select_commands"]).issubset(
                    REQUIRED_RUNTIME_RESOURCES
                ),
                {
                    "registered_container": activation["registered_container"],
                    "initial_enabled": activation["initial_enabled"],
                    "enabled_packs": activation["enabled_packs"],
                    "content_pack_id": content_pack_id,
                    "content_capabilities": content_manifest.get("capabilities"),
                    "enable_order": activation["enable_order"],
                    "provider_select_commands": activation[
                        "provider_select_commands"
                    ],
                    "pack_roots": {
                        pack_id: str(pack_root)
                        for pack_id, pack_root in pack_roots.items()
                    },
                },
            )
            resource_failure = dict(activation["resource_failure"])
            failure_payload = dict(resource_failure.get("payload") or {})
            _require(
                checks,
                "unselected-provider-is-warning-and-direct-request-fails",
                bool(activation["unselected_warning_resources"])
                and resource_failure.get("name")
                in activation["unselected_warning_resources"]
                and int(resource_failure.get("returncode") or 0) != 0
                and failure_payload.get("ok") is False,
                {
                    "warning_count": len(
                        activation["unselected_warning_resources"]
                    ),
                    "requested_resource": resource_failure.get("name"),
                    "returncode": resource_failure.get("returncode"),
                    "failure": failure_payload,
                },
            )

            catalog_prefix = [
                "scripts/catalog_cli.py",
                "--state-file",
                str(state_path),
                "--cache-dir",
                str(cache_dir),
                "--managed-root",
                str(managed_root),
            ]
            runtime_arguments = [
                "--state-file",
                str(state_path),
                "--cache-dir",
                str(cache_dir),
                "--managed-root",
                str(managed_root),
            ]

            recommendation_request_path = temporary_root / "recommend-query.json"
            recommendation_request_path.write_text(
                json.dumps(
                    {
                        "canonical_query": BRIEF,
                        "domain": DOMAIN,
                        "anchors": {
                            "species": ["black panther"],
                            "body_build": ["muscular"],
                        },
                        "source_brief": BRIEF,
                        "source_language": "en",
                        "unresolved_terms": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            recommendation, _recommendation_stdout = _run_json_cli(
                [
                    *catalog_prefix,
                    "recommend",
                    "--query-json",
                    str(recommendation_request_path),
                    "--directions",
                    "4",
                ],
                cwd=core_root,
                label="catalog-recommend",
                trace=cli_trace,
            )
            analysis = dict(recommendation.get("query_analysis") or {})
            anchors = dict(analysis.get("normalized_anchors") or {})
            _require(
                checks,
                "sparse-recommend-preserves-literal-brief-anchors",
                anchors.get("species") == ["black panther"]
                and anchors.get("body_build") == ["muscular"]
                and anchors.get("domain") == [DOMAIN]
                and not recommendation.get("terms_without_alias"),
                analysis,
            )
            cards = list(recommendation.get("direction_cards") or [])
            _require(
                checks,
                "sparse-recommend-returns-four-whole-image-directions",
                len(cards) == 4,
                [card.get("title") for card in cards],
            )

            batch_requests: list[dict[str, Any]] = [
                {
                    "request_id": "identity-archetype",
                    "command": "search",
                    "canonical_query": BRIEF,
                    "domain": DOMAIN,
                    "kind": ["archetype"],
                    "limit": 6,
                }
            ]
            for index, card in enumerate(cards[:3], start=1):
                batch_requests.append(
                    {
                        "request_id": f"direction-{index}-scene",
                        "command": "search",
                        "canonical_query": _scene_probe(card),
                        "domain": DOMAIN,
                        "kind": ["scene"],
                        "limit": 6,
                    }
                )
            batch_path = temporary_root / "catalog-batch.json"
            batch_path.write_text(
                json.dumps(batch_requests, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            batch_help = _run_cli(
                [*catalog_prefix, "batch", "--help"],
                cwd=core_root,
                label="catalog-batch-help",
                trace=cli_trace,
            ).stdout
            batch_process_count += 1
            batch, _batch_stdout = _run_json_cli(
                [*catalog_prefix, "batch", "--input", str(batch_path)],
                cwd=core_root,
                label="catalog-batch",
                trace=cli_trace,
            )
            _require(
                checks,
                "one-batch-evaluates-four-ordered-probes",
                batch.get("request_count") == 4
                and batch.get("success_count") == 4
                and batch.get("error_count") == 0
                and [row.get("request_id") for row in batch.get("results") or []]
                == [row["request_id"] for row in batch_requests],
                {
                    "request_ids": [
                        row.get("request_id") for row in batch.get("results") or []
                    ],
                    "queries": [row["canonical_query"] for row in batch_requests],
                },
            )
            archetype_hit, scene_hit, retrieval_inputs = _select_records(
                recommendation,
                batch,
            )
            selected_ids = {
                "archetype": str(archetype_hit["id"]),
                "scene": str(scene_hit["id"]),
            }
            _require(
                checks,
                "retrieval-selects-records-without-id-inputs",
                all(
                    selected_id not in query
                    for selected_id in selected_ids.values()
                    for query in retrieval_inputs
                ),
                {"selected": selected_ids, "retrieval_inputs": retrieval_inputs},
            )

            inspections: dict[str, dict[str, Any]] = {}
            inspection_sizes: dict[str, int] = {}
            inspection_stdout_sizes: dict[str, int] = {}
            for role, record_id in selected_ids.items():
                inspected, inspected_stdout = _run_json_cli(
                    [*catalog_prefix, "inspect", record_id],
                    cwd=core_root,
                    label=f"catalog-inspect-{role}",
                    trace=cli_trace,
                )
                inspections[role] = inspected
                inspection_stdout_sizes[role] = len(inspected_stdout.encode("utf-8"))
                canonical_record = _canonical_record_from_source(inspected, pack_roots)
                canonical_bytes = len(
                    json.dumps(
                        canonical_record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                serialized = json.dumps(
                    inspected,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                inspection_sizes[role] = len(serialized.encode("utf-8"))
                activation = inspected.get("linked_asset_activation") or {}
                _require(
                    checks,
                    f"inspect-{role}-is-complete-and-asset-compact",
                    inspected.get("record") == canonical_record
                    and set(activation) == {"asset_count", "asset_ids"}
                    and "linked_assets" not in inspected
                    and "resources" not in inspected
                    and "resolved_asset_resources" not in inspected
                    and '"resolved_path"' not in serialized
                    and inspection_sizes[role] <= canonical_bytes + 4096,
                    {
                        "record_id": record_id,
                        "inspect_bytes": inspection_sizes[role],
                        "inspect_stdout_bytes": inspection_stdout_sizes[role],
                        "canonical_record_bytes": canonical_bytes,
                        "activation": activation,
                    },
                )

            activation_summaries: dict[str, dict[str, Any]] = {}
            for role, record_id in selected_ids.items():
                activation_summaries[role], _summary_stdout = _run_json_cli(
                    [*catalog_prefix, "asset-lookup", record_id, "--summary"],
                    cwd=core_root,
                    label=f"catalog-asset-summary-{role}",
                    trace=cli_trace,
                )
            full_asset_lookups: dict[str, dict[str, Any]] = {}
            for role, record_id in selected_ids.items():
                full_asset_lookups[role], _full_assets_stdout = _run_json_cli(
                    [*catalog_prefix, "asset-lookup", record_id],
                    cwd=core_root,
                    label=f"catalog-asset-full-{role}",
                    trace=cli_trace,
                )
            scene_roles = {
                str(resource.get("role"))
                for asset in full_asset_lookups["scene"].get("assets") or []
                for resource in asset.get("resources") or []
            }
            _require(
                checks,
                "full-asset-lookup-runs-for-every-selected-record",
                set(full_asset_lookups) == set(selected_ids)
                and full_asset_lookups["archetype"].get("asset_count") == 0
                and full_asset_lookups["scene"].get("asset_count", 0) > 0
                and all(
                    full_asset_lookups[role].get("asset_count")
                    == activation_summaries[role].get("asset_count")
                    for role in selected_ids
                )
                and REQUIRED_TECHNICAL_ROLES.issubset(scene_roles),
                {
                    role: {
                        "record_id": selected_ids[role],
                        "summary_asset_count": activation_summaries[role].get(
                            "asset_count"
                        ),
                        "full_asset_count": value.get("asset_count"),
                    }
                    for role, value in full_asset_lookups.items()
                },
            )
            asset_summary_json = json.dumps(
                activation_summaries,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            full_scene_json = json.dumps(
                full_asset_lookups["scene"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            _require(
                checks,
                "agent-facing-asset-summary-omits-complete-resources",
                all(
                    token not in asset_summary_json
                    for token in ('"record"', '"resources"', '"resolved_path"', '"sha256"')
                )
                and '"resources"' in full_scene_json
                and '"resolved_path"' in full_scene_json
                and '"sha256"' in full_scene_json,
                {
                    "summary_bytes": len(asset_summary_json.encode("utf-8")),
                    "full_scene_bytes": len(full_scene_json.encode("utf-8")),
                },
            )

            archetype_record = inspections["archetype"]["record"]
            scene_record = inspections["scene"]["record"]
            identity_authority = authority_for("faithful-archival-vector", "identity")
            controls_text = json.dumps(
                identity_authority["controls"], ensure_ascii=False
            ).lower()
            exclusions_text = json.dumps(
                identity_authority["must_not_control"], ensure_ascii=False
            ).lower()
            character_lock_text = str(archetype_record.get("character_lock") or "").lower()
            excluded_terms = {
                axis: next(
                    (term for term in terms if term in exclusions_text),
                    None,
                )
                for axis, terms in IDENTITY_EXCLUDED_STATE.items()
            }
            _require(
                checks,
                "identity-authority-excludes-all-scene-conditioned-axes",
                all(excluded_terms.values())
                and all(
                    not any(term in controls_text for term in terms)
                    for terms in IDENTITY_EXCLUDED_STATE.values()
                )
                and all(
                    not any(term in character_lock_text for term in terms)
                    for terms in IDENTITY_EXCLUDED_STATE.values()
                )
                and "scene-conditioned presentation" in exclusions_text,
                {
                    "controls": identity_authority["controls"],
                    "excluded_term_by_axis": excluded_terms,
                    "character_lock": archetype_record.get("character_lock"),
                },
            )
            archetype_defaults = dict(archetype_record.get("defaults") or {})
            transient_default_text = json.dumps(
                archetype_defaults, ensure_ascii=False
            ).lower()
            _require(
                checks,
                "archetype-transient-defaults-remain-outside-character-lock",
                all(
                    axis in archetype_defaults
                    for axis in ("expression", "outfit", "lighting")
                )
                and "eye contact" in transient_default_text
                and any(
                    term in transient_default_text
                    for term in IDENTITY_EXCLUDED_STATE["mouth"]
                )
                and "sweat" in transient_default_text,
                archetype_defaults,
            )

            example, example_stdout = _run_json_cli(
                ["scripts/reference_runtime.py", "example", "plan"],
                cwd=core_root,
                label="reference-plan-example",
                trace=cli_trace,
            )
            plan_argv = [str(value) for value in example.get("argv") or []]
            if not plan_argv or plan_argv[0] != "plan":
                raise ValueError("reference plan example does not contain plan argv")
            plan_path = temporary_root / "reference-use-plan.json"
            _replace_option_value(
                plan_argv,
                "--record-use",
                f"{selected_ids['scene']}=pose-camera",
            )
            _replace_option_value(plan_argv, "--out", str(plan_path))
            _replace_option_value(plan_argv, "--state-file", str(state_path))
            _replace_option_value(plan_argv, "--cache-dir", str(cache_dir))
            _replace_option_value(plan_argv, "--managed-root", str(managed_root))
            light_index = plan_argv.index("--light-source-json") + 1
            material_index = plan_argv.index("--material-response-json") + 1
            light_source = json.loads(plan_argv[light_index])
            light_source.update(
                {
                    "light_id": "target-key",
                    "direction": "upper-left front",
                    "apparent_size": "large overhead array",
                    "color": "neutral white",
                    "relative_intensity": "primary",
                    "softness": "moderately hard",
                }
            )
            material_response = json.loads(plan_argv[material_index])
            material_response.update(
                {
                    "material": "black-panther short coat",
                    "roughness": "mostly matte",
                    "specular_strength": "moderate",
                    "highlight_shape": "broad controlled highlights",
                    "wetness": "dry",
                    "anisotropy": "low along fur growth",
                }
            )
            plan_argv[light_index] = json.dumps(
                light_source, ensure_ascii=False, separators=(",", ":")
            )
            plan_argv[material_index] = json.dumps(
                material_response, ensure_ascii=False, separators=(",", ":")
            )
            plan_argv.extend(
                [
                    "--max-assets-per-record",
                    "1",
                    "--max-references",
                    "2",
                    *[
                        value
                        for role in sorted(REQUIRED_TECHNICAL_ROLES)
                        for value in ("--technical-role", role)
                    ],
                ]
            )
            plan, _plan_stdout = _run_json_cli(
                ["scripts/reference_runtime.py", *plan_argv],
                cwd=core_root,
                label="reference-plan",
                trace=cli_trace,
            )
            plan_file = _load_object(plan_path)
            plan_validation, _validation_stdout = _run_json_cli(
                [
                    "scripts/validate_reference_use_plan.py",
                    str(plan_path),
                    *runtime_arguments,
                ],
                cwd=core_root,
                label="reference-plan-validation",
                trace=cli_trace,
            )
            plan_roles = {
                str(item.get("technical_role"))
                for item in plan.get("reference_items") or []
            }
            pose_authority_text = json.dumps(
                [item.get("authority") for item in plan.get("reference_items") or []],
                ensure_ascii=False,
            ).lower()
            _require(
                checks,
                "pose-camera-plan-selects-exact-complementary-svg-roles",
                plan == plan_file
                and plan_validation.get("ok") is True
                and plan.get("transport_mode") == "prompt-artifacts"
                and plan.get("target_model") is None
                and plan_roles == REQUIRED_TECHNICAL_ROLES
                and len(plan.get("reference_items") or []) == 2
                and all(
                    item.get("source", {}).get("media_type") == "image/svg+xml"
                    for item in plan.get("reference_items") or []
                )
                and "scene-conditioned presentation" in pose_authority_text
                and "character identity" in pose_authority_text
                and "outfit" in pose_authority_text
                and "lighting" in pose_authority_text,
                {"roles": sorted(plan_roles), "validation": plan_validation},
            )

            composed_prompt = _compose_prompt(
                archetype_record,
                scene_record,
                identity_authority,
            )
            _require(
                checks,
                "composed-prompt-rebuilds-every-load-bearing-state-axis",
                BRIEF in composed_prompt
                and str(archetype_record["character_lock"]) in composed_prompt
                and str(scene_record.get("image_promise")) in composed_prompt
                and all(f"- {axis}:" in composed_prompt for axis in IDENTITY_EXCLUDED_STATE)
                and "structural-line-tone" in composed_prompt
                and "subject-mask" in composed_prompt,
                {
                    "prompt_bytes": len(composed_prompt.encode("utf-8")),
                    "scene_state_axes": sorted(IDENTITY_EXCLUDED_STATE),
                },
            )
            prompt_path = temporary_root / "prompt.txt"
            negative_path = temporary_root / "negative.txt"
            prompt_path.write_text(composed_prompt, encoding="utf-8", newline="\n")
            negative_path.write_text(
                "unintended text, logo, watermark, duplicated limbs, detached "
                "tail, malformed hands, broken contact geometry, floating prop\n",
                encoding="utf-8",
                newline="\n",
            )
            package_root = temporary_root / "prompt-package"
            execution, _execution_stdout = _run_json_cli(
                [
                    "scripts/reference_runtime.py",
                    "execute",
                    "--plan",
                    str(plan_path),
                    "--output-dir",
                    str(package_root),
                    "--prompt-file",
                    str(prompt_path),
                    "--negative-file",
                    str(negative_path),
                    *runtime_arguments,
                ],
                cwd=core_root,
                label="reference-execute",
                trace=cli_trace,
            )
            prepared = _load_object(package_root / "prepared-reference-set.json")
            prompt_artifacts = list(prepared.get("prompt_artifacts") or [])
            source_by_role = {
                str(item["semantic_role"]): item["source"]
                for item in plan["reference_items"]
            }
            hashes_ok = True
            hash_detail: list[dict[str, Any]] = []
            for artifact in prompt_artifacts:
                semantic_role = str(artifact["semantic_role"])
                source = source_by_role[semantic_role]
                source_path = Path(str(source["resolved_path"])).resolve()
                delivered_path = (
                    package_root / str(artifact["delivered_path"])
                ).resolve()
                source_hash = _sha256(source_path)
                delivered_hash = _sha256(delivered_path)
                row_ok = (
                    source_path.suffix.lower() == ".svg"
                    and delivered_path.suffix.lower() == ".svg"
                    and source_hash == str(source["sha256"])
                    and source_hash == str(artifact["source_sha256"])
                    and source_hash == str(artifact["delivered_sha256"])
                    and source_hash == delivered_hash
                )
                hashes_ok = hashes_ok and row_ok
                hash_detail.append(
                    {
                        "semantic_role": semantic_role,
                        "source": str(source_path),
                        "delivered": str(delivered_path),
                        "sha256": source_hash,
                        "passed": row_ok,
                    }
                )
            _require(
                checks,
                "prompt-artifacts-materialize-two-byte-identical-svgs",
                execution == prepared
                and execution.get("artifact_type") == "prepared-reference-set"
                and len(prompt_artifacts) == 2
                and hashes_ok
                and (package_root / "final-prompt.txt").read_bytes()
                == prompt_path.read_bytes()
                and (package_root / "final-negative.txt").read_bytes()
                == negative_path.read_bytes(),
                {
                    "artifact_type": execution.get("artifact_type"),
                    "set_id": execution.get("set_id"),
                    "transport_mode": execution.get("transport_mode"),
                    "artifacts": hash_detail,
                },
            )

            context_counts = {
                path.as_posix(): _words(ROOT / path) for path in RUNTIME_CONTEXT_PATHS
            }
            consumed_cli_words = {
                "catalog batch --help": _text_words(batch_help),
                "reference_runtime example plan": _text_words(example_stdout),
            }
            skill_words = context_counts["SKILL.md"]
            routed_document_words = sum(
                count for path, count in context_counts.items() if path != "SKILL.md"
            )
            combined_context_words = (
                skill_words
                + routed_document_words
                + sum(consumed_cli_words.values())
            )
            _require(
                checks,
                "fresh-session-runtime-context-is-fully-measured",
                set(context_counts)
                == {path.as_posix() for path in RUNTIME_CONTEXT_PATHS}
                and set(consumed_cli_words)
                == {
                    "catalog batch --help",
                    "reference_runtime example plan",
                }
                and all(value > 0 for value in context_counts.values())
                and all(value > 0 for value in consumed_cli_words.values())
                and combined_context_words
                == sum(context_counts.values()) + sum(consumed_cli_words.values()),
                {
                    "measurement": "static-lexical-words-not-host-tokens",
                    "skill_words": skill_words,
                    "routed_document_words": routed_document_words,
                    "consumed_cli_words": consumed_cli_words,
                    "combined_words": combined_context_words,
                    "files": context_counts,
                },
            )
            _require(
                checks,
                "four-probe-batch-uses-one-public-catalog-process",
                batch_process_count == 1
                and len(batch_requests) == 4
                and sum(row["label"] == "catalog-batch" for row in cli_trace) == 1,
                {
                    "batch_process_count": batch_process_count,
                    "batch_probe_count": len(batch_requests),
                    "inspection_bytes": inspection_sizes,
                    "inspection_stdout_bytes": inspection_stdout_sizes,
                },
            )
            summary.update(
                {
                    "selected_records": selected_ids,
                    "batch_probe_count": len(batch_requests),
                    "batch_process_count": batch_process_count,
                    "reference_roles": sorted(plan_roles),
                    "prompt_artifacts": hash_detail,
                    "context_words": {
                        "documents": context_counts,
                        "cli_outputs": consumed_cli_words,
                        "combined": combined_context_words,
                    },
                    "inspection_bytes": inspection_sizes,
                    "inspection_stdout_bytes": inspection_stdout_sizes,
                    "cli_trace": cli_trace,
                }
            )
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    failed = [row for row in checks if not row["passed"]]
    errors.extend(f"{row['name']}: {row['detail']}" for row in failed)
    return {
        "ok": not errors,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "total": len(checks),
        "skipped": 0,
        **summary,
        "checks": checks,
        "errors": errors,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
