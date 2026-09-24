#!/usr/bin/env python3
"""Focused regression tests for CPB state graphs and state-aware generation."""
from __future__ import annotations

from visual_fixtures import fixture_visual, fixture_root
from reading_fixtures import fixture_reading
import base64
import contextlib
import copy
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "state-aware-pilot"
GENERATED = EXAMPLE / "generated"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import build_generation_payload as generation_builder  # noqa: E402
import build_state_generation_package as state_generation_builder  # noqa: E402
from build_state_generation_package import build_package, main as _build_state_generation_main
from visual_fixtures import verify_package
from build_generation_payload import (  # noqa: E402
    main as _build_generation_main,
    materialize_cli_reference_bundle,
    remove_cli_package_staging,
)
import catalog_cli  # noqa: E402
from build_candidate_manifest import (  # noqa: E402
    build_manifest,
    validate_adoption_receipt,
    validate_candidate_manifest_lineage,
)
from catalog_cli import configure_pack_runtime  # noqa: E402
from default_only_example_resolution_smoke_test import (  # noqa: E402
    evaluate as evaluate_default_only_examples,
)
from pack_manager import (  # noqa: E402
    atomic_write_json,
    default_settings,
    save_state,
    sha256_file,
    validate_pack,
    write_lock,
)
from prepare_generation_references import (  # noqa: E402
    finalize_prepared_reference_set,
    prepare_state_reference_selection,
)
from reference_runtime import (  # noqa: E402
    build_reference_use_plan,
    execute_reference_use_plan,
)
from reference_contract import state_authority_for  # noqa: E402
from select_state_references import main as select_references_main  # noqa: E402
from prompt_plot import content_sha256  # noqa: E402
from state_protocol import (  # noqa: E402
    ARTIFACT_SCHEMA_FILES,
    STATE_AWARE_REQUIRED_LINEAGE_FIELDS,
    STATE_LINEAGE_ARTIFACT_FIELDS,
    ZERO_SHA256,
    artifact_hash,
    build_projection,
    build_scene_context,
    extract_character_snapshot,
    finalize_artifact,
    load_json,
    load_jsonl,
    plan_reference_bundle,
    precondition_holds,
    propose_environment_adaptations,
    resolve_world,
    schema_for,
    unsupported_schema_keywords,
    validate_against_schema,
    validate_artifact,
    validate_reference_bundle_graph,
    validate_state_artifact_graph,
    validate_temporal_inputs,
    select_state_references,
    write_json,
)


from smoke_fixtures import fixture_retrieval, cli_with_fixture_retrieval


def build_generation_main(argv):
    return cli_with_fixture_retrieval(_build_generation_main, argv)


def build_state_generation_main(argv):
    return cli_with_fixture_retrieval(_build_state_generation_main, argv)


STATE_REFERENCE_PACK_ID = "0198b361-1234-7abc-8def-0123456789ab"
SPOOFED_STATE_REFERENCE_PACK_ID = "0198b361-5678-7abc-8def-0123456789ab"
STATE_REFERENCE_RECORD_ID = "state-smoke-generic-subject"
STATE_REFERENCE_ASSET_ID = "state-smoke-pack-reference"
STATE_REFERENCE_ARTIFACT_ID = "state-smoke-generic-svg"
STATE_REFERENCE_DETAIL_ARTIFACT_ID = "state-smoke-color-audit-svg"
STATE_REFERENCE_MODEL = "gpt-image-2.5-flare"


def _load_pilot_builder() -> Any:
    path = EXAMPLE / "build_example.py"
    spec = importlib.util.spec_from_file_location("cpb_state_pilot_builder_smoke", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load state-aware pilot builder: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pilot_custom_output_regression() -> dict[str, Any]:
    errors: list[str] = []
    observed: dict[str, Any] = {}
    try:
        builder = _load_pilot_builder()
        with tempfile.TemporaryDirectory(prefix="cpb-pilot-public-output-") as temporary:
            temporary_root = Path(temporary)
            api_target = temporary_root / "api-output"
            api_files = builder.build(api_target)
            observed["api_file_count"] = len(api_files)
            required = {
                "generation-package.json",
                "state-lineage.json",
                "reference-bundle/reference-bundle-plan.json",
            }
            api_inventory = {
                path.relative_to(api_target).as_posix()
                for path in api_target.rglob("*")
                if path.is_file()
            }
            api_returned_inventory: set[str] = set()
            for path in api_files:
                try:
                    relative = path.resolve().relative_to(api_target.resolve())
                except ValueError:
                    errors.append(
                        f"public build(output_dir) returned a path outside its target: {path}"
                    )
                    continue
                if not path.is_file():
                    errors.append(
                        f"public build(output_dir) returned a non-existent file: {path}"
                    )
                api_returned_inventory.add(relative.as_posix())
            if api_returned_inventory != api_inventory:
                errors.append(
                    "public build(output_dir) return inventory differs from installed files"
                )
            if not required.issubset(api_inventory):
                errors.append(
                    "public build(output_dir) omitted required files: "
                    f"{sorted(required-api_inventory)}"
                )

            occupied = temporary_root / "occupied-output"
            occupied.mkdir()
            sentinel = occupied / "caller-owned.txt"
            sentinel.write_text("preserve exactly\n", encoding="utf-8", newline="\n")
            before = {path.name: path.read_bytes() for path in occupied.iterdir()}
            try:
                builder.build(occupied)
            except ValueError as exc:
                observed["api_nonempty_error"] = str(exc)
            else:
                errors.append("public build(output_dir) accepted a non-empty custom directory")
            after = {path.name: path.read_bytes() for path in occupied.iterdir()}
            if after != before:
                errors.append("public build(output_dir) altered caller-owned output content")

            cli_target = temporary_root / "cli-output"
            command = [
                sys.executable,
                "-B",
                str(EXAMPLE / "build_example.py"),
                "--out-dir",
                str(cli_target),
            ]
            first = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            observed["cli_first_returncode"] = first.returncode
            if first.returncode != 0:
                errors.append(
                    "--out-dir failed for a fresh target: "
                    + (first.stderr.strip() or first.stdout.strip())
                )
            else:
                try:
                    payload = json.loads(first.stdout)
                except json.JSONDecodeError as exc:
                    errors.append(f"--out-dir returned invalid JSON: {exc}")
                else:
                    if payload.get("output_dir") != str(cli_target.resolve()):
                        errors.append("--out-dir reported a different output directory")
                    cli_reported_files = payload.get("files")
                    if not isinstance(cli_reported_files, list):
                        errors.append("--out-dir omitted its installed file paths")
                    else:
                        cli_reported_inventory: set[str] = set()
                        for raw_path in cli_reported_files:
                            path = Path(str(raw_path))
                            try:
                                relative = path.resolve().relative_to(cli_target.resolve())
                            except ValueError:
                                errors.append(
                                    f"--out-dir reported a path outside its target: {path}"
                                )
                                continue
                            if not path.is_file():
                                errors.append(
                                    f"--out-dir reported a non-existent file: {path}"
                                )
                            cli_reported_inventory.add(relative.as_posix())
                        cli_actual_inventory = {
                            path.relative_to(cli_target).as_posix()
                            for path in cli_target.rglob("*")
                            if path.is_file()
                        }
                        if cli_reported_inventory != cli_actual_inventory:
                            errors.append(
                                "--out-dir reported inventory differs from installed files"
                            )
            cli_before = {
                path.relative_to(cli_target).as_posix(): path.read_bytes()
                for path in cli_target.rglob("*")
                if path.is_file()
            }
            second = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            observed["cli_second_returncode"] = second.returncode
            if second.returncode == 0:
                errors.append("--out-dir replaced a non-empty custom directory")
            cli_after = {
                path.relative_to(cli_target).as_posix(): path.read_bytes()
                for path in cli_target.rglob("*")
                if path.is_file()
            }
            if cli_after != cli_before:
                errors.append("failed --out-dir retry altered existing generated content")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"public pilot output regression failed: {exc}")
    return {"ok": not errors, "observed": observed, "errors": errors}


def _load_graph() -> dict[str, dict[str, Any]]:
    return {
        "lineage": load_json(GENERATED / "state-lineage.json"),
        "species_profile": load_json(EXAMPLE / "species-morphology-profile.json"),
        "individual_morphology": load_json(EXAMPLE / "individual-morphology-contract.json"),
        "identity_contract": load_json(EXAMPLE / "character-identity-contract.json"),
        "state_snapshot": load_json(GENERATED / "state-snapshot-C01.json"),
        "scene_context": load_json(GENERATED / "scene-context-snapshot.json"),
        "visual_projection": load_json(GENERATED / "visual-state-projection.json"),
        "asset_render_spec": load_json(GENERATED / "asset-render-specification.json"),
        "production_spec": load_json(GENERATED / "production-specification.json"),
    }


APPROVED_PLOT = {
    "artifact_type": "prompt-plot",
    "story": [
        {"id": "s1", "beat": "The character is rendered in the approved scene state.", "visibility": "visible"},
    ],
    "derived": [
        {"kind": "shows", "statement": "the character in the declared scene", "from": ["s1"]},
        {"kind": "placement", "statement": "the character stands in the declared position", "from": ["s1"]},
        {"kind": "composition", "statement": "the declared camera and framing", "from": ["s1"]},
        {"kind": "must_preserve", "statement": "the identity contract's declared features", "from": ["s1"]},
        {"kind": "free", "statement": "incidental light variation"},
    ],
}
APPROVED_PLOT["approved"] = {
    "by": "the person who owns the brief",
    "at": "2026-09-11T00:00:00Z",
    "content_sha256": content_sha256(APPROVED_PLOT),
}


def _payload_inputs(graph: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from request_validation_fixtures import fixture_validation
    return {
        "model": "gpt-image-2.5-flare",
        "request_validation": fixture_validation(fixture_root(), "gpt-image-2.5-flare", reference_mode="prompt-prefix"),
        "input_root": fixture_root(),
        "prompt": (GENERATED / "prompt.txt").read_text(encoding="utf-8"),
        "negative_prompt": (GENERATED / "negative.txt").read_text(encoding="utf-8"),
        "integrated_prompt": (GENERATED / "integrated-prompt.txt").read_text(encoding="utf-8"),
        "native_negative": "",
        "negative_provenance": load_json(GENERATED / "negative-provenance.json"),
        "brief": graph["production_spec"]["source_brief"],
        "creative_intent": load_json(GENERATED / "creative-intent.json"),
        "production_spec": graph["production_spec"],
        "plot": copy.deepcopy(APPROVED_PLOT),
        "retrieval_record": fixture_retrieval((GENERATED / "prompt.txt").read_text(encoding="utf-8"), APPROVED_PLOT),
        "state_lineage": graph["lineage"],
        "species_profile": graph["species_profile"],
        "individual_morphology": graph["individual_morphology"],
        "identity_contract": graph["identity_contract"],
        "state_snapshot": graph["state_snapshot"],
        "scene_context": graph["scene_context"],
        "visual_projection": graph["visual_projection"],
        "asset_render_spec": graph["asset_render_spec"],
        "parameters": {"size": "1024x1024", "quality": "high"},
        "negative_transport": "integrated-critical",
        "critical_avoidance_integrated": False,
    }


def _event(
    event_id: str,
    order: int,
    changes: list[dict[str, Any]],
    *,
    timeline_id: str = "main",
    scene_context_id: str | None = None,
    supersedes: list[str] | None = None,
) -> dict[str, Any]:
    event = {
        "artifact_type": "state-event",
        "event_id": event_id,
        "timeline_id": timeline_id,
        "event_scope": "physical-state",
        "targets": sorted({str(change["entity_id"]) for change in changes}),
        "effective_order": order,
        "effective_from": f"story:{order}",
        "recorded_at": "2026-08-15T00:00:00Z",
        "disclosed_at": None,
        "occurrence": "offscreen",
        "canon_status": "approved",
        "atomic": False,
        "cause": {"type": "smoke-test", "reference": event_id},
        "preconditions": [],
        "changes": changes,
        "evidence": [{"type": "smoke-test", "reference": event_id}],
        "supersedes_event_ids": list(supersedes or []),
        "notes": [],
    }
    if scene_context_id is not None:
        event["scene_context_id"] = scene_context_id
    return event


def _state_change(
    value: Any,
    *,
    persistence: str = "persistent-until-superseded",
    path: str = "/physical_state/condition",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "entity_type": "character",
        "entity_id": "C01",
        "path": path,
        "operation": "set",
        "value": value,
        "persistence": persistence,
        **extra,
    }


def _process(
    process_id: str,
    milestones: list[tuple[int, Any]],
    *,
    policy: str,
    started_order: int = 0,
    path: str = "/physical_state/condition",
) -> dict[str, Any]:
    return {
        "artifact_type": "state-process",
        "process_id": process_id,
        "timeline_id": "main",
        "entity_type": "character",
        "entity_id": "C01",
        "path": path,
        "process_type": "smoke-process",
        "started_order": started_order,
        "effective_until_order": None,
        "milestones": [
            {"offset": offset, "state": state, "label": f"milestone-{offset}"}
            for offset, state in milestones
        ],
        "interruption_policy": policy,
        "canon_status": "approved",
        "evidence": [{"type": "smoke-test", "reference": process_id}],
        "notes": [],
    }


def _resolve_temporal(
    events: list[dict[str, Any]],
    processes: list[dict[str, Any]],
    order: int,
    *,
    scene_context_id: str = "SC-A",
) -> dict[str, Any]:
    return resolve_world(
        base_state={
            "characters": {"C01": {"physical_state": {"condition": "base"}}},
            "relationships": {},
            "environments": {},
            "props": {},
            "world": {},
        },
        events=events,
        processes=processes,
        timeline_id="main",
        story_order=order,
        story_time=f"story:{order}",
        snapshot_id=f"WORLD-main-{order}-{scene_context_id}",
        scene_context_id=scene_context_id,
    )


def _condition(snapshot: dict[str, Any]) -> Any:
    return snapshot["entities"]["characters"]["C01"]["physical_state"]["condition"]


def _pilot_state_at(
    graph: dict[str, dict[str, Any]],
    order: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Resolve one exact pilot instant and its matching scene artifacts."""

    base_state = load_json(EXAMPLE / "world-state-base.json")
    events = load_jsonl(EXAMPLE / "events.jsonl")
    processes = json.loads((EXAMPLE / "processes.json").read_text(encoding="utf-8"))
    scene_context_id = f"SC-TIMELINE-{order}"
    world = resolve_world(
        base_state=base_state,
        events=events,
        processes=processes,
        timeline_id="main",
        story_order=order,
        story_time=f"story:{order}",
        snapshot_id=f"WORLD-main-{order}",
        scene_context_id=scene_context_id,
    )
    state = extract_character_snapshot(
        world,
        character_id="C01",
        species_profile_hash=artifact_hash(graph["species_profile"]),
        individual_morphology_hash=artifact_hash(graph["individual_morphology"]),
        identity_hash=artifact_hash(graph["identity_contract"]),
        era_hash=None,
        form_hash=None,
        appearance_hash=None,
        snapshot_id=f"C01-main-{order}",
    )
    context = build_scene_context(
        {
            "scene_context_id": scene_context_id,
            "timeline_id": "main",
            "story_order_start": order,
            "story_order_end": order,
            "story_time_start": f"story:{order}",
            "story_time_end": f"story:{order}",
            "active_character_ids": ["C01"],
            "relationship_ids": ["REL-C01-C02"],
            "environment_id": "LOC01",
            "prop_ids": ["P01"],
            "location_snapshot": {"location_id": "LOC01", "room": "timeline smoke"},
            "social_context": {},
            "viewer_disclosure_state": {},
            "planned_events": [],
        },
        world,
        [state],
    )
    return world, state, context


def _write_state_reference_pack(pack_root: Path) -> Path:
    """Write one valid released pack with an exact SVG asset and image model."""

    (pack_root / "records").mkdir(parents=True)
    (pack_root / "resources").mkdir()
    atomic_write_json(
        pack_root / "pack.json",
        {
            "pack_id": STATE_REFERENCE_PACK_ID,
            "name": "State Reference Smoke Pack",
            "description": "Released fixture pack for strict state-reference provenance tests.",
            "release": "2026.01.01.1",
            "content": {
                "record_globs": ["records/**/*.json"],
                "resource_globs": ["resources/**/*"],
                "resource_bindings": {},
            },
            "capabilities": ["model-adapters", "state-reference-assets"],
            "dependencies": [],
            "optional_dependencies": [],
            "replaces": [],
            "license": "GPL-3.0-only",
        },
    )
    atomic_write_json(
        pack_root / "records" / "canonical.json",
        {
            "kind": "module",
            "category": "species",
            "records": [
                {
                    "id": STATE_REFERENCE_RECORD_ID,
                    "label": "State smoke generic subject",
                    "curation_status": "curated",
                    "category": "species",
                    "prompt": "a safe generic state-reference fixture subject",
                    "domains": ["shared"],
                    "tags": ["fixture", "state reference"],
                    "search_terms": [
                        {
                            "phrase": "generic state reference subject",
                            "facet": "species",
                            "weight": 1.0,
                            "source": "author",
                        }
                    ],
                }
            ],
        },
    )
    from render_contract_fixtures import decorate
    atomic_write_json(
        pack_root / "records" / "models.json",
        {
            "kind": "model",
            "records": [
                decorate({
                    "id": "state-smoke-image-model",
                    "label": "State smoke image model",
                    "aliases": [STATE_REFERENCE_MODEL],
                    "operation_kind": "generation",
                    "offerings": [],
                    "supports_negative_prompt": False,
                    "prompt_style": "Clear natural-language art direction with exact state constraints.",
                    "negative_transport_mode": "integrated-critical",
                    "negative_transport_notes": "Use the reviewed affirmative integrated rendition.",
                    "reference_input_media_types": [
                        "image/png",
                        "image/jpeg",
                        "image/webp",
                    ],
                    "ordering": ["identity", "current state", "scene", "constraints"],
                    "search_terms": [
                        {
                            "phrase": "state smoke image model",
                            "facet": "model",
                            "weight": 1.0,
                            "source": "author",
                        }
                    ],
                })
            ],
        },
    )
    svg_path = pack_root / "resources" / "state-reference.svg"
    svg_path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64">
  <rect width="96" height="64" rx="8" fill="#26313a"/>
  <circle cx="48" cy="32" r="20" fill="#67c7dd"/>
</svg>
""",
        encoding="utf-8",
        newline="\n",
    )
    svg_hash = sha256_file(svg_path)
    detail_svg_path = pack_root / "resources" / "state-reference-color-audit.svg"
    detail_svg_path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64">
  <rect width="96" height="64" rx="8" fill="#314437"/>
  <circle cx="48" cy="32" r="20" fill="#75d9b4"/>
</svg>
""",
        encoding="utf-8",
        newline="\n",
    )
    detail_svg_hash = sha256_file(detail_svg_path)
    atomic_write_json(
        pack_root / "records" / "assets.json",
        {
            "kind": "asset",
            "records": [
                {
                    "id": STATE_REFERENCE_ASSET_ID,
                    "label": "State smoke generic evidence artifact",
                    "curation_status": "curated",
                    "category": "visual-reference",
                    "asset_type": "reference-guide",
                    "description": "Safe generic rectangle-and-circle state reference.",
                    "source_ref_id": "state-smoke-generic-source",
                    "source_sha256": svg_hash,
                    "source_media_type": "image/svg+xml",
                    "source_dimensions": {"width": 96, "height": 64},
                    "disposition": "fixture-only",
                    "evidence_relation": "supports strict state-reference provenance tests",
                    "canonical_record_ids": [STATE_REFERENCE_RECORD_ID],
                    "primary_resource": "resources/state-reference.svg",
                    "resource_refs": [
                        "resources/state-reference.svg",
                        "resources/state-reference-color-audit.svg",
                    ],
                    "artifacts": [
                        {
                            "artifact_id": STATE_REFERENCE_ARTIFACT_ID,
                            "role": "faithful-archival-vector",
                            "path": "resources/state-reference.svg",
                            "media_type": "image/svg+xml",
                            "sha256": svg_hash,
                        },
                        {
                            "artifact_id": STATE_REFERENCE_DETAIL_ARTIFACT_ID,
                            "role": "color-audit",
                            "path": "resources/state-reference-color-audit.svg",
                            "media_type": "image/svg+xml",
                            "sha256": detail_svg_hash,
                        }
                    ],
                    "tags": ["fixture", "state reference", "generic svg"],
                }
            ],
        },
    )
    write_lock(pack_root)
    return svg_path


def _write_supplied_svg(path: Path, *, fill: str) -> dict[str, Any]:
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="6" fill="{fill}"/>
  <circle cx="32" cy="32" r="18" fill="#d8e3eb"/>
</svg>
""",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "kind": "supplied-file",
        "reference_id": path.stem,
        "resolved_path": str(path.resolve(strict=True)),
        "media_type": "image/svg+xml",
        "sha256": sha256_file(path),
    }


def _prepared_transport_path(row: dict[str, Any], package_root: Path | None) -> Path:
    stored = Path(row["transport"]["resolved_path"])
    if stored.is_absolute():
        return stored
    if package_root is None:
        raise ValueError("relative prepared transport requires a package root")
    return package_root / stored


def _reference_binding(
    *,
    binding_id: str,
    role: str,
    source: dict[str, Any],
    identity_hash: str,
    state_hash: str | None,
    start: int,
    end: int | None,
    features: list[str],
    superseded: bool = False,
) -> dict[str, Any]:
    return finalize_artifact(
        {
            "artifact_type": "state-aware-reference-binding",
            "binding_id": binding_id,
            "role": role,
            "source": copy.deepcopy(source),
            "character_id": "C01",
            "identity_contract_sha256": identity_hash,
            "era_contract_sha256": None,
            "appearance_variant_sha256": None,
            "state_snapshot_sha256": state_hash,
            "effective_story_range": {"from_order": start, "to_order": end},
            "visibly_supported_state": features,
            "unsupported_or_occluded_state": [],
            "intended_influence": ["identity"],
            "unsupported_assumptions": ["scene_placement"],
            "review_dimensions": ["state-correctness"],
            "fallback_if_unstable": "regenerate a state-correct derivative",
            "superseded_for_future_scenes": superseded,
            "binding_sha256": ZERO_SHA256,
        }
    )


def _closed_value_property_names(
    schema: Any, owner: str | None = None, found: set[str] | None = None
) -> set[str]:
    """Property names whose subschema closes its value set anywhere inside it.

    A closed set is `enum` or `const`. The walk is recursive and attributes a
    closed set to the nearest enclosing property name, so a value set buried in
    `$defs`, in a combiner, or in an array item is reported under the property a
    reader would have to satisfy.
    """

    if found is None:
        found = set()
    if isinstance(schema, dict):
        if owner is not None and ("enum" in schema or "const" in schema):
            found.add(owner)
        for key, value in schema.items():
            if key in ("enum", "const"):
                continue
            if key == "properties" and isinstance(value, dict):
                for name, child in value.items():
                    _closed_value_property_names(child, name, found)
            else:
                _closed_value_property_names(value, owner, found)
    elif isinstance(schema, list):
        for item in schema:
            _closed_value_property_names(item, owner, found)
    return found


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    graph = _load_graph()

    default_only_examples = evaluate_default_only_examples(ROOT)
    check(
        "default-only runnable state record references resolve against packs/commons",
        default_only_examples.get("ok") is True,
        default_only_examples,
    )
    custom_output_regression = _pilot_custom_output_regression()
    check(
        "state-aware pilot public build and out-dir preserve existing custom output",
        custom_output_regression.get("ok") is True,
        custom_output_regression,
    )

    registry_errors = []
    for kind, filename in ARTIFACT_SCHEMA_FILES.items():
        path = ROOT / "schemas" / filename
        if not path.is_file() or load_json(path).get("properties", {}).get("artifact_type", {}).get("const") != kind:
            registry_errors.append({"artifact_type": kind, "schema": filename})
    check("artifact schema registry is explicit and populated",
          bool(ARTIFACT_SCHEMA_FILES)
          and len(set(ARTIFACT_SCHEMA_FILES.values())) == len(ARTIFACT_SCHEMA_FILES)
          and not registry_errors,
          {"registered": len(ARTIFACT_SCHEMA_FILES), "errors": registry_errors})
    unsupported_nested_schema = {
        "type": "object",
        "properties": {
            "absent": {
                "type": "string",
                "format": "email",
            }
        },
    }
    check(
        "unsupported schema keywords report the exact nested property path",
        unsupported_schema_keywords(unsupported_nested_schema)
        == ["$.properties.absent.format"],
        unsupported_schema_keywords(unsupported_nested_schema),
    )
    annotation_schema = {
        "title": "Annotation fixture",
        "description": "Root annotation.",
        "properties": {
            "present": {
                "type": "string",
                "title": "Nested annotation",
                "description": "Nested annotation text.",
            }
        },
    }
    check(
        "schema title and description annotations are not unsupported constraints",
        unsupported_schema_keywords(annotation_schema) == [],
        unsupported_schema_keywords(annotation_schema),
    )
    supported_composition_schema = {
        "type": "object",
        "required": ["present"],
        "properties": {
            "present": {
                "allOf": [
                    {"$ref": "#/$defs/non-empty"},
                    {"maxLength": 3},
                ]
            }
        },
        "$defs": {
            "non-empty": {
                "type": "string",
                "minLength": 1,
            }
        },
        "additionalProperties": False,
    }
    composition_findings = unsupported_schema_keywords(supported_composition_schema)
    valid_composition_errors = validate_against_schema(
        {"present": "abc"},
        supported_composition_schema,
    )
    all_of_errors = validate_against_schema(
        {"present": "abcd"},
        supported_composition_schema,
    )
    ref_errors = validate_against_schema(
        {"present": ""},
        supported_composition_schema,
    )
    check(
        "supported allOf and local $defs references are reported cleanly and enforced",
        composition_findings == []
        and valid_composition_errors == []
        and any("longer than maxLength" in message for message in all_of_errors)
        and any("shorter than minLength" in message for message in ref_errors),
        {
            "unsupported": composition_findings,
            "valid": valid_composition_errors,
            "allOf": all_of_errors,
            "$ref": ref_errors,
        },
    )
    try:
        schema_for({"artifact_type": "../state-lineage"})
    except ValueError as exc:
        check("unknown artifact type cannot select a schema path", "no schema registered" in str(exc))
    else:
        check("unknown artifact type cannot select a schema path", False)

    stateless = load_json(ROOT / "templates" / "state" / "state-lineage.template.json")
    stateless_report = validate_artifact(stateless)
    check(
        "stateless lineage uses null graph nodes and a concrete self hash",
        stateless_report.get("ok")
        and all(stateless.get(field) is None for field in STATE_LINEAGE_ARTIFACT_FIELDS)
        and stateless.get("lineage_sha256") != ZERO_SHA256,
        stateless_report.get("errors"),
    )
    state_aware_template = load_json(
        ROOT / "templates" / "state" / "state-lineage-state-aware.template.json"
    )
    state_aware_template_report = validate_artifact(state_aware_template)
    check(
        "state-aware lineage template preserves the complete required graph",
        state_aware_template_report.get("ok")
        and state_aware_template.get("mode") == "state-aware"
        and all(
            isinstance(state_aware_template.get(field), str)
            and len(state_aware_template[field]) == 64
            and state_aware_template[field] != ZERO_SHA256
            for field in STATE_AWARE_REQUIRED_LINEAGE_FIELDS
        )
        and state_aware_template.get("lineage_sha256")
        == artifact_hash(state_aware_template),
        state_aware_template_report.get("errors"),
    )
    temporary_event_template = load_json(
        ROOT
        / "templates"
        / "state"
        / "state-event-temporary-until-cleared.template.json"
    )
    temporary_event_report = validate_artifact(temporary_event_template)
    temporary_change = temporary_event_template.get("changes", [{}])[0]
    check(
        "temporary-state template preserves precondition clear and expiry relationships",
        temporary_event_report.get("ok")
        and bool(temporary_event_template.get("preconditions"))
        and temporary_change.get("persistence") == "temporary-until-cleared"
        and temporary_change.get("clear_event_id") == "EV-CLEAR-0001"
        and temporary_change.get("effective_until_order") == 20
        and "effective_until_order" not in temporary_event_template,
        temporary_event_report.get("errors"),
    )
    zero_self = copy.deepcopy(stateless)
    zero_self["lineage_sha256"] = ZERO_SHA256
    check(
        "runtime lineage rejects an all-zero self hash",
        not validate_artifact(zero_self).get("ok"),
    )
    populated_stateless = copy.deepcopy(stateless)
    populated_stateless["identity_contract_sha256"] = "a" * 64
    populated_stateless = finalize_artifact(populated_stateless)
    check(
        "stateless lineage rejects non-null state nodes",
        not validate_artifact(populated_stateless).get("ok"),
    )
    zero_state_aware = copy.deepcopy(graph["lineage"])
    zero_state_aware["state_snapshot_sha256"] = ZERO_SHA256
    zero_state_aware = finalize_artifact(zero_state_aware)
    check(
        "state-aware lineage rejects zero required node hashes",
        not validate_artifact(zero_state_aware).get("ok"),
    )
    stale_self_hash = copy.deepcopy(graph["state_snapshot"])
    stale_self_hash["story_time"] = "story:tampered"
    check(
        "runtime artifact rejects a stale self hash",
        not validate_artifact(stale_self_hash).get("ok"),
    )

    off_type_container: dict[str, Any] = {
        "artifact_type": "semantic-region-map",
        "coordinate_space": "not-an-object",
        "regions": [],
    }
    try:
        off_type_report = validate_artifact(off_type_container)
    except Exception as exc:  # noqa: BLE001 - a raised error is the failure
        check(
            "an off-type container is reported rather than raised",
            False,
            f"{type(exc).__name__}: {exc}",
        )
    else:
        check(
            "an off-type container is reported rather than raised",
            off_type_report.get("ok") is False
            and "$.coordinate_space: expected type ['object'], got str"
            in off_type_report.get("errors", []),
            off_type_report.get("errors"),
        )

    off_type_values = (None, 0, True, "", "x", [], [1], {}, {"a": 1}, 1.5)
    sweep_sources = sorted((ROOT / "templates" / "state").glob("*.json")) + sorted(
        EXAMPLE.glob("*.json")
    )
    sweep_documents = 0
    sweep_mutations = 0
    sweep_exceptions: list[str] = []
    sweep_accepted = 0
    for source in sweep_sources:
        document = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(
            document.get("artifact_type"), str
        ):
            continue
        sweep_documents += 1
        for field in list(document):
            if field == "artifact_type":
                continue
            for off_type_value in off_type_values:
                mutant = copy.deepcopy(document)
                mutant[field] = off_type_value
                sweep_mutations += 1
                try:
                    mutant_report = validate_artifact(
                        mutant,
                        allow_placeholder_hashes=True,
                    )
                except Exception as exc:  # noqa: BLE001 - the sweep counts raises
                    sweep_exceptions.append(
                        f"{source.name}:{field}={off_type_value!r}"
                        f" raised {type(exc).__name__}: {exc}"
                    )
                    continue
                if mutant_report.get("ok"):
                    sweep_accepted += 1
    check(
        "every off-type top-level field is reported rather than raised",
        sweep_documents > 0 and sweep_mutations > 0 and not sweep_exceptions,
        {
            "documents": sweep_documents,
            "mutations": sweep_mutations,
            "exceptions": len(sweep_exceptions),
            "accepted": sweep_accepted,
            "first_exceptions": sweep_exceptions[:5],
        },
    )

    growth_schema = load_json(ROOT / "schemas" / "growth-geometry.schema.json")
    growth_template = load_json(ROOT / "templates" / "growth-geometry-template.json")
    growth_errors = validate_against_schema(growth_template, growth_schema)
    check("growth template validates its declared structures", not growth_errors, growth_errors)
    identity_growth = graph["identity_contract"]["stable_identity"]["growth_geometry"]
    check(
        "identity growth structures retain their authored geometry",
        not validate_against_schema(identity_growth, growth_schema)
        and identity_growth["structures"]["ruff-cheeks-neck"]["presence"] == "present"
        and identity_growth["structures"]["terminal-tips"]["geometry"]["color_and_value"] == "dark charcoal",
    )
    grooming_state_paths = {
        "/appearance_state/grooming/fur_wetness/brow",
        "/appearance_state/grooming/fur_wetness/paws",
        "/appearance_state/grooming/claws/dirt",
        "/appearance_state/grooming/claws/polish_condition",
    }
    polish_variant_paths = {
        "/stable_identity/growth_geometry/structures/terminal-tips/geometry/color_and_value",
        "/stable_identity/growth_geometry/structures/terminal-tips/geometry/decoration",
        "/stable_identity/growth_geometry/structures/terminal-tips/geometry/finish",
    }
    pilot_state_schema = load_json(EXAMPLE / "character-state-schema.json")
    pilot_state_paths = {row.get("path") for row in pilot_state_schema["state_paths"]}
    pilot_mutable_paths = set(graph["individual_morphology"]["mutable_state_paths"])
    pilot_initial_grooming = pilot_state_schema["initial_state"]["appearance_state"]["grooming"]
    check(
        "pilot grooming variants retain exact appearance-state and approved polish ownership",
        grooming_state_paths.issubset(pilot_state_paths)
        and grooming_state_paths.issubset(pilot_mutable_paths)
        and set(identity_growth["variant_fields"]) == polish_variant_paths
        and pilot_initial_grooming["fur_wetness"] == {"brow": "dry", "paws": "dry"}
        and pilot_initial_grooming["claws"] == {"dirt": "clean", "polish_condition": "none"},
    )
    missing_geometry = copy.deepcopy(identity_growth)
    missing_geometry["structures"]["fur-tail"].pop("geometry")
    check("growth structures require explicit geometry", bool(validate_against_schema(missing_geometry, growth_schema)))
    undeclared_field = copy.deepcopy(growth_template)
    undeclared_field["unexpected_field"] = {}
    check("growth schema rejects undeclared covering fields", bool(validate_against_schema(undeclared_field, growth_schema)))
    closed_value_union = set()
    for schema_name in ("growth-geometry", "terminal-growth-contract", "declared-structures"):
        closed_value_union.update(_closed_value_property_names(load_json(ROOT / "schemas" / (schema_name + ".schema.json"))))
    check("growth contracts close value sets only for representation, presence and source confidence",
          closed_value_union == {"representation", "presence", "source_confidence"})
    declared_subject = copy.deepcopy(growth_template)
    declared_subject["structures"] = {
        "shell-feathers": {"kind": "barbed contour feathers", "location": "dorsal shell",
                           "presence": "present", "geometry": {"material": "machined ceramic", "direction": "follows the shell"}},
        "rim-tips": {"kind": "sheathed keratin projections", "location": "terminal rim",
                     "presence": "present", "geometry": {"length": "one sixth of carrier width"}},
    }
    declared_errors = validate_against_schema(declared_subject, growth_schema)
    empty_kind = copy.deepcopy(declared_subject); empty_kind["structures"]["shell-feathers"]["kind"] = ""
    empty_geometry = copy.deepcopy(declared_subject); empty_geometry["structures"]["rim-tips"]["geometry"] = {}
    check("growth contracts validate authored coverings and terminal structures",
          not declared_errors and bool(validate_against_schema(empty_kind, growth_schema))
          and bool(validate_against_schema(empty_geometry, growth_schema)), declared_errors)

    old_event = _event("EV-OLD", 1, [_state_change("old")])
    new_event = _event(
        "EV-NEW",
        10,
        [_state_change("new")],
        supersedes=["EV-OLD"],
    )
    # This is an authored editorial replacement, not an in-world reversal.
    new_event.update(event_scope="editorial-revision", occurrence="editorial")
    historical = _resolve_temporal([old_event, new_event], [], 5)
    current = _resolve_temporal([old_event, new_event], [], 10)
    check(
        "event supersession is future-filtered for historical snapshots",
        _condition(historical) == "old"
        and historical["applied_event_ids"] == ["EV-OLD"]
        and _condition(current) == "new"
        and current["applied_event_ids"] == ["EV-NEW"],
    )

    scene_event = _event(
        "EV-SCENE-A",
        1,
        [_state_change("scene-a", persistence="scene-local")],
        scene_context_id="SC-A",
    )
    matching_scene = _resolve_temporal([scene_event], [], 2, scene_context_id="SC-A")
    other_scene = _resolve_temporal([scene_event], [], 2, scene_context_id="SC-B")
    check(
        "scene-local state applies only to the exact requested scene and snapshots record it",
        _condition(matching_scene) == "scene-a"
        and _condition(other_scene) == "base"
        and matching_scene["scene_context_id"] == "SC-A"
        and other_scene["scene_context_id"] == "SC-B",
    )

    decay_process = _process(
        "PROC-DECAY",
        [(0, "initial"), (3, "middle"), (7, "final")],
        policy="fixed",
    )
    decay_event = _event(
        "EV-DECAY",
        0,
        [
            _state_change(
                "initial",
                persistence="decaying",
                process_id="PROC-DECAY",
            )
        ],
    )
    decay_at_five = _resolve_temporal([decay_event], [decay_process], 5)
    decay_at_six = _resolve_temporal([decay_event], [decay_process], 6)
    check(
        "decay uses only exact authored integer milestones and persists the latest milestone",
        _condition(decay_at_five) == "middle"
        and _condition(decay_at_six) == "middle"
        and decay_at_six["applied_process_milestones"]
        == [
            "PROC-DECAY@epoch-initial:offset-0",
            "PROC-DECAY@epoch-initial:offset-3",
        ],
    )

    restart_process = _process(
        "PROC-RESTART",
        [(0, "initial"), (5, "advanced")],
        policy="restartable",
    )
    restart_source = _event(
        "EV-RESTART-SOURCE",
        0,
        [
            _state_change(
                "initial",
                persistence="progressive",
                process_id="PROC-RESTART",
            )
        ],
    )
    interrupt = _event(
        "EV-INTERRUPT",
        3,
        [
            {
                "entity_type": "character",
                "entity_id": "C01",
                "path": "/physical_state/condition",
                "operation": "interrupt-process",
                "process_id": "PROC-RESTART",
            }
        ],
    )
    restart = _event(
        "EV-RESTART",
        10,
        [
            {
                "entity_type": "character",
                "entity_id": "C01",
                "path": "/physical_state/condition",
                "operation": "restart-process",
                "process_id": "PROC-RESTART",
            }
        ],
    )
    interrupted = _resolve_temporal(
        [restart_source, interrupt, restart], [restart_process], 9
    )
    restarted_before_offset = _resolve_temporal(
        [restart_source, interrupt, restart], [restart_process], 14
    )
    restarted_at_offset = _resolve_temporal(
        [restart_source, interrupt, restart], [restart_process], 15
    )
    check(
        "restartable process interrupts explicitly, never auto-resumes, and restarts a fresh epoch",
        _condition(interrupted) == "initial"
        and _condition(restarted_before_offset) == "initial"
        and _condition(restarted_at_offset) == "advanced"
        and "PROC-RESTART@epoch-restart-EV-RESTART-0:offset-5"
        in restarted_at_offset["applied_process_milestones"]
        and "PROC-RESTART@epoch-initial:offset-5"
        not in restarted_at_offset["applied_process_milestones"],
    )
    try:
        _resolve_temporal([restart_source, restart], [restart_process], 10)
    except ValueError as exc:
        check(
            "restartable process rejects restart without an inactive epoch",
            "requires a prior interrupt" in str(exc),
        )
    else:
        check("restartable process rejects restart without an inactive epoch", False)

    same_order_process = _process(
        "PROC-SAME-ORDER",
        [(0, "initial"), (5, "process-five")],
        policy="fixed",
    )
    same_order_source = _event(
        "EV-SAME-SOURCE",
        0,
        [
            _state_change(
                "initial",
                persistence="decaying",
                process_id="PROC-SAME-ORDER",
            )
        ],
    )
    same_order_event = _event("EV-SAME-ORDER", 5, [_state_change("event-five")])
    same_order_snapshot = _resolve_temporal(
        [same_order_source, same_order_event], [same_order_process], 5
    )
    check(
        "same-order precedence is deterministic with state events after milestones",
        _condition(same_order_snapshot) == "event-five",
    )

    pilot_world_base = load_json(EXAMPLE / "world-state-base.json")

    def _introducing_event(operator: str, **condition: Any) -> dict[str, Any]:
        event = _event(
            "EV-NEW-0001",
            1,
            [
                {
                    "entity_type": "prop",
                    "entity_id": "P99",
                    "path": "/state",
                    "operation": "set",
                    "value": "carried",
                    "persistence": "persistent-until-superseded",
                }
            ],
        )
        event["event_scope"] = "inventory-transfer"
        event["preconditions"] = [
            {
                "entity_type": "prop",
                "entity_id": "P99",
                "path": "/state",
                "operator": operator,
                **condition,
            }
        ]
        return event

    def _resolve_introducing(event: dict[str, Any]) -> dict[str, Any]:
        return resolve_world(
            base_state=pilot_world_base,
            events=[event],
            processes=[],
            timeline_id="main",
            story_order=1,
            story_time="story:1",
            snapshot_id="WORLD-main-1-SC-INTRODUCES",
            scene_context_id="SC-INTRODUCES",
        )

    introducing_event = _introducing_event("not-exists")
    introducing_report = validate_artifact(introducing_event)
    introducing_snapshot = _resolve_introducing(introducing_event)
    check(
        "an event may guard its own introduction of an entity with not-exists",
        introducing_report.get("ok") is True
        and introducing_snapshot["entities"]["props"]["P99"]["state"] == "carried",
        {
            "event": introducing_report.get("errors"),
            "props": introducing_snapshot["entities"]["props"],
        },
    )
    try:
        _resolve_introducing(_introducing_event("exists"))
    except ValueError as exc:
        check(
            "a precondition on an absent entity fails the event, not the resolve",
            "event precondition failed:" in str(exc)
            and "entity does not exist" not in str(exc),
            str(exc),
        )
    else:
        check("a precondition on an absent entity fails the event, not the resolve", False)

    absent_entity_world = {
        "characters": {"C01": {"physical_state": {}}},
        "props": {},
    }
    absent_entity_world_before = copy.deepcopy(absent_entity_world)
    absent_missing = precondition_holds(
        absent_entity_world,
        {
            "entity_type": "character",
            "entity_id": "C02",
            "path": "/physical_state",
            "operator": "not-exists",
        },
    )
    absent_present = precondition_holds(
        absent_entity_world,
        {
            "entity_type": "character",
            "entity_id": "C02",
            "path": "/physical_state",
            "operator": "exists",
        },
    )
    check(
        "an absent entity reads as an absent path and evaluating it leaves the world alone",
        absent_missing is True
        and absent_present is False
        and absent_entity_world == absent_entity_world_before,
        {
            "not_exists": absent_missing,
            "exists": absent_present,
            "world": absent_entity_world,
        },
    )

    supersedable_process = _process(
        "PROC-SUPERSEDABLE",
        [(0, "initial"), (5, "middle"), (10, "future-process-state")],
        policy="supersedable-by-event",
    )
    supersedable_source = _event(
        "EV-SUPERSEDABLE-SOURCE",
        0,
        [
            _state_change(
                "initial",
                persistence="progressive",
                process_id="PROC-SUPERSEDABLE",
            )
        ],
    )
    path_override = _event("EV-PATH-OVERRIDE", 6, [_state_change("override")])
    supersedable_snapshot = _resolve_temporal(
        [supersedable_source, path_override], [supersedable_process], 12
    )
    check(
        "supersedable process cancels future milestones at the first later same-path event",
        _condition(supersedable_snapshot) == "override"
        and "PROC-SUPERSEDABLE@epoch-initial:offset-5"
        in supersedable_snapshot["applied_process_milestones"]
        and "PROC-SUPERSEDABLE@epoch-initial:offset-10"
        not in supersedable_snapshot["applied_process_milestones"],
    )

    expiring = _event(
        "EV-EXPIRING",
        2,
        [
            _state_change(
                "temporary",
                persistence="temporary-until-cleared",
                effective_until_order=5,
            )
        ],
    )
    check(
        "per-change effective_until_order is exclusive and restores prior state",
        _condition(_resolve_temporal([expiring], [], 4)) == "temporary"
        and _condition(_resolve_temporal([expiring], [], 5)) == "base",
    )

    clearing = _event("EV-CLEAR", 4, [_state_change("cleared")])
    clearable = _event(
        "EV-CLEARABLE",
        1,
        [
            _state_change(
                "temporary",
                persistence="temporary-until-cleared",
                clear_event_id="EV-CLEAR",
            )
        ],
    )
    check(
        "per-change clear_event_id resolves a later matching event",
        _condition(_resolve_temporal([clearable, clearing], [], 3)) == "temporary"
        and _condition(_resolve_temporal([clearable, clearing], [], 4)) == "cleared",
    )

    fixed_with_action = copy.deepcopy(decay_process)
    fixed_with_action["process_id"] = "PROC-FIXED-ACTION"
    fixed_source = _event(
        "EV-FIXED-SOURCE",
        0,
        [
            _state_change(
                "initial",
                persistence="decaying",
                process_id="PROC-FIXED-ACTION",
            )
        ],
    )
    fixed_action = _event(
        "EV-FIXED-INTERRUPT",
        2,
        [
            {
                "entity_type": "character",
                "entity_id": "C01",
                "path": "/physical_state/condition",
                "operation": "interrupt-process",
                "process_id": "PROC-FIXED-ACTION",
            }
        ],
    )
    fixed_errors = validate_temporal_inputs(
        events=[fixed_source, fixed_action], processes=[fixed_with_action]
    )
    unknown_clear = _event(
        "EV-BAD-CLEAR",
        1,
        [
            _state_change(
                "bad",
                persistence="temporary-until-cleared",
                clear_event_id="EV-MISSING",
            )
        ],
    )
    bad_process = _process(
        "PROC-BAD-PATH",
        [(0, "initial")],
        policy="fixed",
        path="/physical_state/other",
    )
    bad_source = _event(
        "EV-BAD-PROCESS",
        0,
        [
            _state_change(
                "initial",
                persistence="decaying",
                process_id="PROC-BAD-PATH",
            )
        ],
    )
    wrong_timeline_clear = _event(
        "EV-WRONG-TIMELINE-CLEAR",
        6,
        [_state_change("cleared")],
        timeline_id="alternate",
    )
    cross_timeline_source = _event(
        "EV-CROSS-TIMELINE",
        1,
        [
            _state_change(
                "temporary",
                persistence="temporary-until-cleared",
                clear_event_id="EV-WRONG-TIMELINE-CLEAR",
            )
        ],
    )
    later_event = _event("EV-LATER", 20, [_state_change("later")])
    bad_order_superseder = _event(
        "EV-BAD-ORDER-SUPERSEDER",
        10,
        [_state_change("bad-order")],
        supersedes=["EV-LATER"],
    )
    invalid_errors = validate_temporal_inputs(
        events=[
            old_event,
            copy.deepcopy(old_event),
            unknown_clear,
            bad_source,
            wrong_timeline_clear,
            cross_timeline_source,
            later_event,
            bad_order_superseder,
        ],
        processes=[bad_process, copy.deepcopy(bad_process)],
    )
    check(
        "temporal validation rejects fixed lifecycle actions, duplicate IDs, and invalid references",
        any("rejects lifecycle actions" in item for item in fixed_errors)
        and any("duplicate event_id" in item for item in invalid_errors)
        and any("duplicate process_id" in item for item in invalid_errors)
        and any("unknown clear_event_id" in item for item in invalid_errors)
        and any("does not match change" in item for item in invalid_errors)
        and any("clear event is on another timeline" in item for item in invalid_errors)
        and any("supersession must be strictly later" in item for item in invalid_errors),
        {"fixed": fixed_errors, "invalid": invalid_errors},
    )

    graph_report = validate_state_artifact_graph(**graph)
    check("canonical state artifact graph validates", graph_report.get("ok"), graph_report.get("errors"))

    bad_graph = copy.deepcopy(graph)
    bad_projection = copy.deepcopy(bad_graph["visual_projection"])
    bad_projection["character_id"] = "C02"
    bad_projection = finalize_artifact(bad_projection)
    bad_render = copy.deepcopy(bad_graph["asset_render_spec"])
    bad_render["character_id"] = "C02"
    bad_render["visual_state_projection_sha256"] = artifact_hash(bad_projection)
    bad_render = finalize_artifact(bad_render)
    bad_lineage = copy.deepcopy(bad_graph["lineage"])
    bad_lineage["visual_projection_sha256"] = artifact_hash(bad_projection)
    bad_lineage["asset_render_spec_sha256"] = artifact_hash(bad_render)
    bad_lineage = finalize_artifact(bad_lineage)
    bad_production = copy.deepcopy(bad_graph["production_spec"])
    bad_production["state_context"]["state_lineage_sha256"] = bad_lineage["lineage_sha256"]
    bad_graph.update(
        visual_projection=bad_projection,
        asset_render_spec=bad_render,
        lineage=bad_lineage,
        production_spec=bad_production,
    )
    independently_valid = all(
        validate_artifact(item).get("ok")
        for item in (bad_projection, bad_render, bad_lineage)
    )
    crosswire_report = validate_state_artifact_graph(**bad_graph)
    check(
        "artifact graph rejects individually valid cross-character artifacts",
        independently_valid
        and not crosswire_report.get("ok")
        and any("another character" in item for item in crosswire_report.get("errors", [])),
        crosswire_report.get("errors"),
    )

    pilot_instants = {
        order: _pilot_state_at(graph, order)
        for order in (9, 10, 15, 19, 20, 21, 22, 25, 30)
    }
    world_at = {order: value[0] for order, value in pilot_instants.items()}
    state_at = {order: value[1] for order, value in pilot_instants.items()}
    context_at = {order: value[2] for order, value in pilot_instants.items()}
    c01_at = {
        order: world["entities"]["characters"]["C01"]
        for order, world in world_at.items()
    }
    prop_at = {
        order: world["entities"]["props"]["P01"]
        for order, world in world_at.items()
    }
    check(
        "pilot event timing resolves offscreen injury, masked emotion, long process, and atomic prop transfer",
        c01_at[9]["physical_state"] == {"left_ear_tip": "intact", "wound_stage": "none"}
        and c01_at[10]["physical_state"] == {"left_ear_tip": "notched", "wound_stage": "fresh_wound"}
        and c01_at[15]["physical_state"]["wound_stage"] == "closed_with_swelling"
        and c01_at[30]["physical_state"]["wound_stage"] == "pink_healing_scar"
        and c01_at[19]["emotional_state"]["felt_state"]["emotion"] == "neutral"
        and c01_at[20]["emotional_state"]["felt_state"]["emotion"] == "fear"
        and c01_at[20]["emotional_state"]["expressed_state"]["emotion"] == "calm"
        and c01_at[30]["emotional_state"]["felt_state"]["emotion"] == "neutral"
        and c01_at[21]["inventory_state"]["items"] == ["P01"]
        and prop_at[21]["possessed_by"] == "C01"
        and c01_at[22]["inventory_state"]["items"] == []
        and world_at[22]["entities"]["characters"]["C02"]["inventory_state"]["items"] == ["P01"]
        and prop_at[22]["possessed_by"] == "C02",
        {
            "injury": {order: c01_at[order]["physical_state"] for order in (9, 10, 15, 30)},
            "emotion": {order: c01_at[order]["emotional_state"] for order in (19, 20, 30)},
            "prop": {order: prop_at[order] for order in (21, 22)},
        },
    )

    projection_request = load_json(EXAMPLE / "projection-request.json")

    def temporal_projection(
        order: int,
        *,
        visible_paths: list[str],
        prop_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        request = copy.deepcopy(projection_request)
        request["projection_id"] = f"VSP-TIMELINE-{order}-{len(visible_paths)}-{len(prop_paths or [])}"
        request["visible_state_paths"] = visible_paths
        request["performance_cues"] = []
        request["wardrobe_paths"] = []
        request["prop_paths"] = list(prop_paths or [])
        request["relationship_blocking_cues"] = []
        request["environmental_body_responses"] = []
        request["occluded_state_paths"] = []
        request["reference_asset_requirements"] = []
        request["review_dimensions"] = []
        return build_projection(
            graph["identity_contract"],
            graph["species_profile"],
            graph["individual_morphology"],
            state_at[order],
            context_at[order],
            request,
            None,
        )

    injury_before = temporal_projection(9, visible_paths=["/physical_state/left_ear_tip"])
    injury_after = temporal_projection(10, visible_paths=["/physical_state/left_ear_tip"])
    wound_middle = temporal_projection(15, visible_paths=["/physical_state/wound_stage"])
    wound_late = temporal_projection(30, visible_paths=["/physical_state/wound_stage"])
    masked_before = temporal_projection(
        19,
        visible_paths=["/emotional_state/felt_state", "/emotional_state/expressed_state"],
    )
    masked_during = temporal_projection(
        20,
        visible_paths=["/emotional_state/felt_state", "/emotional_state/expressed_state"],
    )
    masked_after = temporal_projection(
        30,
        visible_paths=["/emotional_state/felt_state", "/emotional_state/expressed_state"],
    )
    prop_before = temporal_projection(21, visible_paths=[], prop_paths=["/inventory_state/items"])
    prop_after = temporal_projection(22, visible_paths=[], prop_paths=["/inventory_state/items"])

    def path_value(projection: dict[str, Any], group: str, path: str) -> Any:
        return next(
            row["value"]
            for row in projection[group]
            if row.get("path") == path
        )

    scoped_projection = build_projection(
        graph["identity_contract"],
        graph["species_profile"],
        graph["individual_morphology"],
        state_at[25],
        context_at[25],
        projection_request,
        None,
    )
    leak_probe_request = copy.deepcopy(projection_request)
    leak_probe_request["projection_id"] = "VSP-EXPLICIT-LEAK-PROBE"
    leak_probe_request["visible_state_paths"].append("/emotional_state/felt_state")
    leak_probe_request["prop_paths"] = ["/inventory_state/items"]
    leak_probe = build_projection(
        graph["identity_contract"],
        graph["species_profile"],
        graph["individual_morphology"],
        state_at[25],
        context_at[25],
        leak_probe_request,
        None,
    )
    scoped_visible_paths = {
        row["path"] for row in scoped_projection["visible_state_deltas"]
    }
    scoped_occluded_paths = {
        row["path"] for row in scoped_projection["occluded_or_irrelevant_features"]
    }
    check(
        "visual projection exposes state only when requested and at the resolved story instant",
        path_value(injury_before, "visible_state_deltas", "/physical_state/left_ear_tip") == "intact"
        and path_value(injury_after, "visible_state_deltas", "/physical_state/left_ear_tip") == "notched"
        and path_value(wound_middle, "visible_state_deltas", "/physical_state/wound_stage") == "closed_with_swelling"
        and path_value(wound_late, "visible_state_deltas", "/physical_state/wound_stage") == "pink_healing_scar"
        and path_value(masked_before, "visible_state_deltas", "/emotional_state/felt_state")["emotion"] == "neutral"
        and path_value(masked_during, "visible_state_deltas", "/emotional_state/felt_state")["emotion"] == "fear"
        and path_value(masked_during, "visible_state_deltas", "/emotional_state/expressed_state")["emotion"] == "calm"
        and path_value(masked_after, "visible_state_deltas", "/emotional_state/felt_state")["emotion"] == "neutral"
        and path_value(prop_before, "held_or_visible_props", "/inventory_state/items") == ["P01"]
        and path_value(prop_after, "held_or_visible_props", "/inventory_state/items") == []
        and "/emotional_state/felt_state" not in scoped_visible_paths
        and "/physical_state/wound_stage" not in scoped_visible_paths
        and "/physical_state/wound_stage" in scoped_occluded_paths
        and scoped_projection["held_or_visible_props"] == []
        and path_value(leak_probe, "visible_state_deltas", "/emotional_state/felt_state")["emotion"] == "fear"
        and path_value(leak_probe, "held_or_visible_props", "/inventory_state/items") == [],
        {
            "scoped_visible_paths": sorted(scoped_visible_paths),
            "scoped_occluded_paths": sorted(scoped_occluded_paths),
            "explicit_probe_paths": [
                row["path"] for row in leak_probe["visible_state_deltas"]
            ],
        },
    )

    same_semantics_request = copy.deepcopy(projection_request)
    same_semantics_request["projection_id"] = "VSP-SAME-SEMANTICS"
    unchanged_projection = build_projection(
        graph["identity_contract"],
        graph["species_profile"],
        graph["individual_morphology"],
        state_at[25],
        context_at[25],
        same_semantics_request,
        scoped_projection,
    )
    changed_semantics_request = copy.deepcopy(same_semantics_request)
    changed_semantics_request["projection_id"] = "VSP-CHANGED-SEMANTICS"
    changed_semantics_request["performance_cues"].append(
        {"cue": "one deliberate visible exhale", "purpose": "scene beat"}
    )
    changed_projection = build_projection(
        graph["identity_contract"],
        graph["species_profile"],
        graph["individual_morphology"],
        state_at[25],
        context_at[25],
        changed_semantics_request,
        scoped_projection,
    )
    different_scene_projection = build_projection(
        graph["identity_contract"],
        graph["species_profile"],
        graph["individual_morphology"],
        state_at[22],
        context_at[22],
        same_semantics_request,
        scoped_projection,
    )
    check(
        "scene prompt regeneration ignores artifact IDs but reacts to visible semantics and scene lineage",
        unchanged_projection["prompt_regeneration_required"] is False
        and changed_projection["prompt_regeneration_required"] is True
        and different_scene_projection["prompt_regeneration_required"] is True,
        {
            "id_only": unchanged_projection["prompt_regeneration_required"],
            "visible_change": changed_projection["prompt_regeneration_required"],
            "scene_change": different_scene_projection["prompt_regeneration_required"],
        },
    )

    state_schema = load_json(EXAMPLE / "character-state-schema.json")
    environment_snapshot = load_json(EXAMPLE / "environment-snapshot.json")
    state_schema_before = copy.deepcopy(state_schema)
    environment_before = copy.deepcopy(environment_snapshot)
    adaptation = propose_environment_adaptations(
        state_schema,
        environment_snapshot,
        character_id="C01",
        proposal_id="ADAPT-SMOKE",
    )
    attempted_gate_bypass = copy.deepcopy(state_schema)
    attempted_gate_bypass["environment_adaptation_rules"][0]["proposal"][
        "requires_human_approval"
    ] = False
    gated_adaptation = propose_environment_adaptations(
        attempted_gate_bypass,
        environment_snapshot,
        character_id="C01",
        proposal_id="ADAPT-GATE-BYPASS",
    )
    check(
        "environment adaptation remains a human-approval proposal and never mutates source state",
        validate_artifact(adaptation).get("ok") is True
        and adaptation["matched_rule_ids"] == ["ENV-hot-humid-wolf"]
        and adaptation["status"] == "proposed"
        and adaptation["approval_required"] is True
        and bool(adaptation["proposals"])
        and all(
            proposal.get("requires_human_approval") is True
            for proposal in adaptation["proposals"]
        )
        and validate_artifact(gated_adaptation).get("ok") is True
        and bool(gated_adaptation["proposals"])
        and all(
            proposal.get("requires_human_approval") is True
            for proposal in gated_adaptation["proposals"]
        )
        and state_schema == state_schema_before
        and environment_snapshot == environment_before,
        {
            "canonical": adaptation,
            "authored_false_is_forced_true": gated_adaptation["proposals"],
        },
    )

    missing_pointer_schema = copy.deepcopy(state_schema)
    missing_pointer_schema["environment_adaptation_rules"][0]["when"][0]["path"] = (
        "/missing_temperature"
    )
    missing_pointer_adaptation = propose_environment_adaptations(
        missing_pointer_schema,
        environment_snapshot,
        character_id="C01",
        proposal_id="ADAPT-MISSING-POINTER",
    )
    type_mismatch_schema = copy.deepcopy(state_schema)
    type_mismatch_schema["environment_adaptation_rules"][0]["when"][0]["value"] = "hot"
    type_mismatch_adaptation = propose_environment_adaptations(
        type_mismatch_schema,
        environment_snapshot,
        character_id="C01",
        proposal_id="ADAPT-TYPE-MISMATCH",
    )
    check(
        "missing JSON pointers and type-incompatible comparisons fail closed",
        adaptation["matched_rule_ids"] == ["ENV-hot-humid-wolf"]
        and validate_artifact(missing_pointer_adaptation).get("ok") is True
        and missing_pointer_adaptation["matched_rule_ids"] == []
        and missing_pointer_adaptation["proposals"] == []
        and validate_artifact(type_mismatch_adaptation).get("ok") is True
        and type_mismatch_adaptation["matched_rule_ids"] == []
        and type_mismatch_adaptation["proposals"] == [],
        {
            "positive_control": adaptation["matched_rule_ids"],
            "missing_pointer": missing_pointer_adaptation,
            "type_mismatch": type_mismatch_adaptation,
        },
    )

    reference_runtime_temp = tempfile.TemporaryDirectory(prefix="cpb-state-reference-runtime-")
    reference_runtime_root = Path(reference_runtime_temp.name)
    reference_pack_root = reference_runtime_root / "packs" / "state-reference-smoke"
    pack_svg_path = _write_state_reference_pack(reference_pack_root)
    reference_pack_report = validate_pack(
        reference_pack_root,
        require_lock=True,
        verify_lock=True,
    )
    check(
        "state-reference fixture is a valid locked released pack",
        reference_pack_report.valid and reference_pack_report.lock_present,
        reference_pack_report.to_dict(),
    )
    reference_state_file = reference_runtime_root / "pack-state.json"
    reference_cache_dir = reference_runtime_root / "cache"
    reference_managed_root = reference_runtime_root / "managed"
    save_state(
        reference_state_file,
        {
            "pack_roots": [],
            "enabled_packs": [STATE_REFERENCE_PACK_ID],
            "resource_providers": {},
        },
    )
    reference_runtime_arguments = [
        "--state-file",
        str(reference_state_file),
        "--cache-dir",
        str(reference_cache_dir),
        "--managed-root",
        str(reference_managed_root),
        "--pack-root",
        str(reference_pack_root),
    ]
    reference_settings = default_settings(
        extra_roots=(reference_pack_root,),
        state_file=reference_state_file,
        cache_dir=reference_cache_dir,
        managed_root=reference_managed_root,
        default_enabled_packs=(),
        default_resource_providers={},
    )
    configure_pack_runtime(reference_settings)
    active_sources = catalog_cli.active_pack_artifact_sources()
    pack_source = active_sources[
        (
            STATE_REFERENCE_PACK_ID,
            STATE_REFERENCE_ASSET_ID,
            STATE_REFERENCE_ARTIFACT_ID,
        )
    ]
    current_detail_source = active_sources[
        (
            STATE_REFERENCE_PACK_ID,
            STATE_REFERENCE_ASSET_ID,
            STATE_REFERENCE_DETAIL_ARTIFACT_ID,
        )
    ]
    supplied_root = reference_runtime_root / "supplied"
    supplied_root.mkdir()
    past_source = _write_supplied_svg(supplied_root / "past-reference.svg", fill="#35516a")
    wrong_state_source = _write_supplied_svg(
        supplied_root / "wrong-state-reference.svg", fill="#6a5135"
    )
    wrong_identity_source = _write_supplied_svg(
        supplied_root / "wrong-identity-reference.svg", fill="#6a354f"
    )

    identity_hash = artifact_hash(graph["identity_contract"])
    current_state_hash = state_at[25]["state_snapshot_sha256"]
    past_binding = _reference_binding(
        binding_id="BIND-PAST",
        role="historical-identity",
        source=past_source,
        identity_hash=identity_hash,
        state_hash=None,
        start=0,
        end=4,
        features=["left-ear-intact", "cyan-eyes"],
        superseded=True,
    )
    current_binding = _reference_binding(
        binding_id="BIND-CURRENT",
        role="current-identity",
        source=pack_source,
        identity_hash=identity_hash,
        state_hash=current_state_hash,
        start=5,
        end=None,
        features=["left-ear-notched", "cyan-eyes"],
    )
    current_binding["unsupported_or_occluded_state"] = ["rear-body-silhouette"]
    current_binding = finalize_artifact(current_binding)
    wrong_state_binding = _reference_binding(
        binding_id="BIND-WRONG-STATE",
        role="diagnostic-state",
        source=wrong_state_source,
        identity_hash=identity_hash,
        state_hash="e" * 64,
        start=5,
        end=None,
        features=["left-ear-notched", "cyan-eyes"],
    )
    wrong_identity_binding = _reference_binding(
        binding_id="BIND-WRONG-IDENTITY",
        role="diagnostic-identity",
        source=wrong_identity_source,
        identity_hash="f" * 64,
        state_hash=current_state_hash,
        start=5,
        end=None,
        features=["left-ear-notched", "cyan-eyes"],
    )
    reference_bindings = [
        past_binding,
        current_binding,
        wrong_state_binding,
        wrong_identity_binding,
    ]
    current_selection = select_state_references(
        reference_bindings,
        selection_id="SEL-CURRENT",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=current_state_hash,
        story_order=25,
        required_features=["left-ear-notched", "cyan-eyes"],
        limit=2,
    )
    flashback_selection = select_state_references(
        reference_bindings,
        selection_id="SEL-FLASHBACK",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=None,
        story_order=3,
        required_features=["left-ear-intact", "cyan-eyes"],
        limit=2,
    )
    state_mismatch_selection = select_state_references(
        [wrong_state_binding],
        selection_id="SEL-WRONG-STATE",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=current_state_hash,
        story_order=25,
        required_features=["left-ear-notched"],
        limit=1,
    )
    identity_mismatch_selection = select_state_references(
        [wrong_identity_binding],
        selection_id="SEL-WRONG-IDENTITY",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=current_state_hash,
        story_order=25,
        required_features=["left-ear-notched"],
        limit=1,
    )
    check(
        "reference selection binds identity, state hash, current range, and flashback range",
        all(
            validate_artifact(selection).get("ok") is True
            for selection in (
                current_selection,
                flashback_selection,
                state_mismatch_selection,
                identity_mismatch_selection,
            )
        )
        and [row["source"].get("asset_id") for row in current_selection["selected_references"]]
        == [STATE_REFERENCE_ASSET_ID]
        and [row["role"] for row in current_selection["selected_references"]]
        == ["current-identity"]
        and current_selection["selected_references"][0]["source"] == pack_source
        and sha256_file(pack_svg_path) == pack_source["sha256"]
        and pack_source["pack_id"] == STATE_REFERENCE_PACK_ID
        and pack_source["artifact_id"] == STATE_REFERENCE_ARTIFACT_ID
        and current_selection["identity_contract_sha256"] == identity_hash
        and current_selection["state_snapshot_sha256"] == current_state_hash
        and current_selection["unresolved_requirements"] == []
        and [row["source"].get("reference_id") for row in flashback_selection["selected_references"]]
        == ["past-reference"]
        and flashback_selection["selected_references"][0]["source"] == past_source
        and flashback_selection["state_snapshot_sha256"] is None
        and flashback_selection["unresolved_requirements"] == []
        and state_mismatch_selection["selected_references"] == []
        and state_mismatch_selection["unresolved_requirements"] == ["left-ear-notched"]
        and identity_mismatch_selection["selected_references"] == []
        and identity_mismatch_selection["unresolved_requirements"] == ["left-ear-notched"],
        {
            "current": current_selection,
            "flashback": flashback_selection,
            "wrong_state": state_mismatch_selection,
            "wrong_identity": identity_mismatch_selection,
        },
    )

    manual_pack_prepare_dir = reference_runtime_root / "manual-pack-prepare"
    manual_pack_prepare_error = ""
    try:
        prepare_state_reference_selection(
            current_selection,
            model=STATE_REFERENCE_MODEL,
            output_dir=manual_pack_prepare_dir,
            max_side=128,
        )
    except ValueError as exc:
        manual_pack_prepare_error = str(exc)
    check(
        "pack-backed state selection requires an explicit record-use plan",
        "require an explicit Reference Use Plan" in manual_pack_prepare_error
        and not manual_pack_prepare_dir.exists(),
        {
            "error": manual_pack_prepare_error,
            "output_exists": manual_pack_prepare_dir.exists(),
        },
    )

    unresolved_selection = copy.deepcopy(current_selection)
    unresolved_selection["required_state_features"].append(
        "unresolved-visible-state"
    )
    unresolved_selection["unresolved_requirements"] = ["unresolved-visible-state"]
    unresolved_selection = finalize_artifact(unresolved_selection)
    unresolved_prepare_dir = reference_runtime_root / "unresolved-selection-output"
    unresolved_prepare_error = ""
    try:
        prepare_state_reference_selection(
            unresolved_selection,
            model=STATE_REFERENCE_MODEL,
            output_dir=unresolved_prepare_dir,
            max_side=128,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        unresolved_prepare_error = str(exc)
    check(
        "schema-valid unresolved state selection cannot create prepared transports",
        validate_artifact(unresolved_selection).get("ok") is True
        and "unresolved requirements" in unresolved_prepare_error
        and not unresolved_prepare_dir.exists(),
        {
            "error": unresolved_prepare_error,
            "output_exists": unresolved_prepare_dir.exists(),
        },
    )

    invalid_supported_binding = copy.deepcopy(current_binding)
    invalid_supported_binding["visibly_supported_state"] = ["left-ear-notched", {"bad": True}]
    invalid_supported_binding = finalize_artifact(invalid_supported_binding)
    invalid_occluded_binding = copy.deepcopy(current_binding)
    invalid_occluded_binding["unsupported_or_occluded_state"] = ["hidden", "hidden", ""]
    invalid_occluded_binding = finalize_artifact(invalid_occluded_binding)
    reversed_range_binding = copy.deepcopy(current_binding)
    reversed_range_binding["effective_story_range"] = {"from_order": 20, "to_order": 10}
    reversed_range_binding = finalize_artifact(reversed_range_binding)
    invalid_binding_reports = [
        validate_artifact(binding)
        for binding in (
            invalid_supported_binding,
            invalid_occluded_binding,
            reversed_range_binding,
        )
    ]
    invalid_binding_selector_errors: list[str] = []
    for index, binding in enumerate(
        (invalid_supported_binding, invalid_occluded_binding, reversed_range_binding)
    ):
        try:
            select_state_references(
                [binding],
                selection_id=f"SEL-INVALID-BINDING-{index}",
                identity_hash=identity_hash,
                era_hash=None,
                appearance_hash=None,
                state_hash=current_state_hash,
                story_order=25,
                required_features=["left-ear-notched"],
                limit=1,
            )
        except ValueError as exc:
            invalid_binding_selector_errors.append(str(exc))
    check(
        "state binding rejects untyped state features, duplicates, empties, and reversed ranges",
        all(report.get("ok") is False for report in invalid_binding_reports)
        and len(invalid_binding_selector_errors) == 3
        and any(
            "greater than or equal to from_order" in error
            for error in invalid_binding_reports[2]["errors"]
        ),
        {
            "reports": invalid_binding_reports,
            "selector_errors": invalid_binding_selector_errors,
        },
    )

    past_path = Path(past_source["resolved_path"])
    original_past_bytes = past_path.read_bytes()
    changed_selection_error = ""
    changed_prepare_error = ""
    changed_prepare_dir = reference_runtime_root / "changed-supplied-output"
    try:
        past_path.write_bytes(original_past_bytes + b"changed")
        try:
            select_state_references(
                [past_binding],
                selection_id="SEL-CHANGED-SUPPLIED",
                identity_hash=identity_hash,
                era_hash=None,
                appearance_hash=None,
                state_hash=None,
                story_order=3,
                required_features=["left-ear-intact"],
                limit=1,
            )
        except (ValueError, OSError) as exc:
            changed_selection_error = str(exc)
        try:
            prepare_state_reference_selection(
                flashback_selection,
                model=STATE_REFERENCE_MODEL,
                output_dir=changed_prepare_dir,
                max_side=128,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            changed_prepare_error = str(exc)
    finally:
        past_path.write_bytes(original_past_bytes)
    check(
        "state selection and preparation reject changed supplied source bytes without output",
        "hash mismatch" in changed_selection_error
        and "hash mismatch" in changed_prepare_error
        and not changed_prepare_dir.exists(),
        {
            "selection_error": changed_selection_error,
            "prepare_error": changed_prepare_error,
        },
    )

    missing_selection_error = ""
    missing_prepare_error = ""
    missing_prepare_dir = reference_runtime_root / "missing-supplied-output"
    past_path.unlink()
    try:
        try:
            select_state_references(
                [past_binding],
                selection_id="SEL-MISSING-SUPPLIED",
                identity_hash=identity_hash,
                era_hash=None,
                appearance_hash=None,
                state_hash=None,
                story_order=3,
                required_features=["left-ear-intact"],
                limit=1,
            )
        except (ValueError, OSError) as exc:
            missing_selection_error = str(exc)
        try:
            prepare_state_reference_selection(
                flashback_selection,
                model=STATE_REFERENCE_MODEL,
                output_dir=missing_prepare_dir,
                max_side=128,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            missing_prepare_error = str(exc)
    finally:
        past_path.write_bytes(original_past_bytes)
    check(
        "state selection and preparation reject missing supplied source bytes without output",
        bool(missing_selection_error)
        and bool(missing_prepare_error)
        and not missing_prepare_dir.exists(),
        {
            "selection_error": missing_selection_error,
            "prepare_error": missing_prepare_error,
        },
    )

    # Stale means the artifact this binding was made against is not the one that
    # is there now, which is a difference in bytes and not in a declared version.
    stale_pack_binding = copy.deepcopy(current_binding)
    stale_pack_binding["source"]["sha256"] = "f" * 64
    stale_pack_binding = finalize_artifact(stale_pack_binding)
    spoofed_pack_binding = copy.deepcopy(current_binding)
    spoofed_pack_binding["source"]["pack_id"] = SPOOFED_STATE_REFERENCE_PACK_ID
    spoofed_pack_binding = finalize_artifact(spoofed_pack_binding)
    provenance_errors: list[str] = []
    for selection_id, binding in (
        ("SEL-STALE-PACK", stale_pack_binding),
        ("SEL-SPOOFED-PACK", spoofed_pack_binding),
    ):
        try:
            select_state_references(
                [binding],
                selection_id=selection_id,
                identity_hash=identity_hash,
                era_hash=None,
                appearance_hash=None,
                state_hash=current_state_hash,
                story_order=25,
                required_features=["left-ear-notched"],
                limit=1,
            )
        except ValueError as exc:
            provenance_errors.append(str(exc))
    check(
        "state selection rejects stale and spoofed active-pack provenance",
        len(provenance_errors) == 2
        and all(
            "active pack artifact" in error
            or "differs from its active pack artifact declaration" in error
            for error in provenance_errors
        ),
        provenance_errors,
    )

    identity_plan = build_reference_use_plan(
        [{"record_id": STATE_REFERENCE_RECORD_ID, "intended_influence": "identity"}],
        transport_mode="multi-image",
        target_model=STATE_REFERENCE_MODEL,
        source_lighting_mode="replace",
        include_technical_roles=["faithful-archival-vector"],
        light_sources=[
            {
                "light_id": "state-key",
                "direction": "front-left and above",
                "apparent_size": "large",
                "color": "neutral daylight",
                "relative_intensity": "primary",
                "softness": "soft",
            }
        ],
        material_responses=[
            {
                "material": "character surfaces",
                "roughness": "matte",
                "specular_strength": "low",
                "highlight_shape": "broad and soft",
                "wetness": "dry",
                "anisotropy": "none",
            }
        ],
    )
    prepared_current_root = reference_runtime_root / "prepared-current"
    prepared_current = execute_reference_use_plan(
        identity_plan,
        output_dir=prepared_current_root,
        reference_selection=current_selection,
        max_side=128,
    )
    prepared_flashback = prepare_state_reference_selection(
        flashback_selection,
        model=STATE_REFERENCE_MODEL,
        output_dir=reference_runtime_root / "prepared-flashback",
        max_side=128,
    )
    package_state_hash = artifact_hash(graph["state_snapshot"])
    package_story_order = int(graph["state_snapshot"]["story_order"])
    zero_selection = select_state_references(
        [],
        selection_id="SEL-CURRENT-ZERO",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=package_state_hash,
        story_order=package_story_order,
        required_features=[],
        limit=0,
    )
    zero_plan = build_reference_use_plan(
        [{"record_id": STATE_REFERENCE_RECORD_ID, "intended_influence": "identity"}],
        transport_mode="multi-image",
        target_model=STATE_REFERENCE_MODEL,
        source_lighting_mode="preserve",
        include_technical_roles=["subject-mask"],
    )
    prepared_zero_root = reference_runtime_root / "prepared-zero"
    prepared_zero = execute_reference_use_plan(
        zero_plan,
        output_dir=prepared_zero_root,
        reference_selection=zero_selection,
        max_side=128,
    )
    package_current_binding = copy.deepcopy(current_binding)
    package_current_binding["binding_id"] = "BIND-PACKAGE-CURRENT"
    package_current_binding["state_snapshot_sha256"] = package_state_hash
    package_current_binding = finalize_artifact(package_current_binding)
    package_current_selection = select_state_references(
        [package_current_binding],
        selection_id="SEL-PACKAGE-CURRENT",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=package_state_hash,
        story_order=package_story_order,
        required_features=["left-ear-notched", "cyan-eyes"],
        limit=1,
    )
    prepared_package_current_root = reference_runtime_root / "prepared-package-current"
    prepared_package_current = execute_reference_use_plan(
        identity_plan,
        output_dir=prepared_package_current_root,
        reference_selection=package_current_selection,
        max_side=128,
    )
    current_primary_binding = copy.deepcopy(current_binding)
    current_primary_binding["binding_id"] = "BIND-CURRENT-PRIMARY"
    current_primary_binding["state_snapshot_sha256"] = package_state_hash
    current_primary_binding["visibly_supported_state"] = ["left-ear-notched"]
    current_primary_binding = finalize_artifact(current_primary_binding)
    current_detail_binding = _reference_binding(
        binding_id="BIND-CURRENT-DETAIL",
        role="current-state-detail",
        source=current_detail_source,
        identity_hash=identity_hash,
        state_hash=package_state_hash,
        start=5,
        end=None,
        features=["cyan-eyes"],
    )
    current_detail_binding["unsupported_or_occluded_state"] = [
        "left-ear-silhouette"
    ]
    current_detail_binding["unsupported_assumptions"] = [
        "scene_placement",
        "full-body-proportions",
    ]
    current_detail_binding = finalize_artifact(current_detail_binding)
    multi_selection = select_state_references(
        [current_primary_binding, current_detail_binding],
        selection_id="SEL-CURRENT-MULTI",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=package_state_hash,
        story_order=package_story_order,
        required_features=["left-ear-notched", "cyan-eyes"],
        limit=2,
    )
    multi_identity_plan = build_reference_use_plan(
        [{"record_id": STATE_REFERENCE_RECORD_ID, "intended_influence": "identity"}],
        transport_mode="multi-image",
        target_model=STATE_REFERENCE_MODEL,
        source_lighting_mode="replace",
        include_technical_roles=["faithful-archival-vector", "color-audit"],
        light_sources=[
            {
                "light_id": "state-key",
                "direction": "front-left and above",
                "apparent_size": "large",
                "color": "neutral daylight",
                "relative_intensity": "primary",
                "softness": "soft",
            }
        ],
        material_responses=[
            {
                "material": "character surfaces",
                "roughness": "matte",
                "specular_strength": "low",
                "highlight_shape": "broad and soft",
                "wetness": "dry",
                "anisotropy": "none",
            }
        ],
    )
    prepared_multi_root = reference_runtime_root / "prepared-multi"
    prepared_multi = execute_reference_use_plan(
        multi_identity_plan,
        output_dir=prepared_multi_root,
        reference_selection=multi_selection,
        max_side=128,
    )
    current_rows = prepared_current["selected_references"]
    flashback_rows = prepared_flashback["selected_references"]
    multi_rows = prepared_multi["selected_references"]
    check(
        "state reference preparation intersects explicit record-use plans with state eligibility and commits portable PNG transports",
        len(current_rows) == 1
        and len(flashback_rows) == 1
        and len(multi_rows) == 2
        and identity_plan["selected_records"]
        == [
            {
                "record_id": STATE_REFERENCE_RECORD_ID,
                "intended_influence": "identity",
            }
        ]
        and current_rows[0]["role"]
        == current_selection["selected_references"][0]["role"]
        and current_rows[0]["source"]
        == current_selection["selected_references"][0]["source"]
        and flashback_rows[0]["role"]
        == flashback_selection["selected_references"][0]["role"]
        and flashback_rows[0]["source"]
        == flashback_selection["selected_references"][0]["source"]
        and flashback_rows[0]["authority"] == state_authority_for(["identity"])
        and prepared_current["reference_selection"] == current_selection
        and prepared_current["reference_selection_sha256"]
        == current_selection["selection_sha256"]
        and prepared_zero["reference_selection"] == zero_selection
        and prepared_zero["reference_selection_sha256"]
        == zero_selection["selection_sha256"]
        and prepared_zero["selected_references"] == []
        and prepared_zero["zero_reference_reason"]["code"]
        == "no-suitable-active-asset"
        and prepared_zero["zero_reference_reason"]["record_ids"]
        == [STATE_REFERENCE_RECORD_ID]
        and prepared_current["reference_use_plan"] == identity_plan
        and prepared_multi["reference_use_plan"] == multi_identity_plan
        and prepared_zero["reference_use_plan"] == zero_plan
        and all(
            not Path(row["transport"]["resolved_path"]).is_absolute()
            for row in (*current_rows, *multi_rows)
        )
        and [row["binding_id"] for row in multi_rows]
        == [
            "BIND-CURRENT-PRIMARY",
            "BIND-CURRENT-DETAIL",
        ]
        and all(
            row["transport"]["media_type"] == "image/png"
            and row["transport"]["derivation"]["mode"] == "svg-rasterization"
            and sha256_file(_prepared_transport_path(row, package_root))
            == row["transport"]["sha256"]
            for row, package_root in (
                *((row, prepared_current_root) for row in current_rows),
                *((row, None) for row in flashback_rows),
                *((row, prepared_multi_root) for row in multi_rows),
            )
        ),
        {
            "zero": prepared_zero,
            "current": prepared_current,
            "flashback": prepared_flashback,
            "multi": prepared_multi,
        },
    )
    check(
        "unsupported state and assumptions survive selection, preparation, and ordering",
        current_selection["selected_references"][0][
            "unsupported_or_occluded_state"
        ]
        == ["rear-body-silhouette"]
        and current_rows[0]["unsupported_or_occluded_state"]
        == ["rear-body-silhouette"]
        and current_rows[0]["unsupported_assumptions"] == ["scene_placement"]
        and {row["source"]["sha256"] for row in multi_rows}
        == {
            row["source"]["sha256"]
            for row in multi_selection["selected_references"]
        }
        and all(
            prepared["unsupported_or_occluded_state"]
            == selected["unsupported_or_occluded_state"]
            and prepared["unsupported_assumptions"]
            == selected["unsupported_assumptions"]
            for prepared in multi_rows
            for selected in multi_selection["selected_references"]
            if prepared["source"] == selected["source"]
        ),
        {"current": current_rows, "multi": multi_rows},
    )

    superseded_open_binding = _reference_binding(
        binding_id="BIND-SUPERSEDED-OPEN",
        role="superseded-identity",
        source=pack_source,
        identity_hash=identity_hash,
        state_hash=current_state_hash,
        start=5,
        end=None,
        features=["left-ear-notched"],
        superseded=True,
    )
    superseded_open_selection = select_state_references(
        [superseded_open_binding],
        selection_id="SEL-SUPERSEDED-OPEN",
        identity_hash=identity_hash,
        era_hash=None,
        appearance_hash=None,
        state_hash=current_state_hash,
        story_order=25,
        required_features=["left-ear-notched"],
        limit=1,
    )
    check(
        "open-ended superseded bindings are excluded while closed historical bindings remain usable",
        validate_artifact(superseded_open_selection).get("ok") is True
        and superseded_open_selection["selected_references"] == []
        and superseded_open_selection["unresolved_requirements"] == ["left-ear-notched"]
        and [
            row["source"].get("reference_id")
            for row in flashback_selection["selected_references"]
        ]
        == ["past-reference"],
        {
            "open_ended": superseded_open_selection,
            "closed_historical": flashback_selection,
        },
    )

    with tempfile.TemporaryDirectory(prefix="cpb-state-generation-smoke-") as temp_value:
        temp = Path(temp_value)
        round_trip_ok = True
        round_trip_details: list[Any] = []
        verified_packages: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
        for count, reference_set, reference_root in (
            (0, prepared_zero, prepared_zero_root),
            (1, prepared_package_current, prepared_package_current_root),
            (2, prepared_multi, prepared_multi_root),
        ):
            package_root = temp / f"generation-package-{count}"
            package_root.mkdir()
            packaged_reference_set, _companion = materialize_cli_reference_bundle(
                reference_set,
                model=STATE_REFERENCE_MODEL,
                source_root=reference_root,
                staging_root=package_root,
                companion_name=f"generation-package-{count}.references",
            )
            inputs = _payload_inputs(graph)
            if count:
                inputs["production_spec"] = copy.deepcopy(graph["production_spec"])
                inputs["production_spec"]["render_intent"]["execution_mode"] = "reference-guided"
            payload = build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'),
                **inputs,
                prepared_reference_set=packaged_reference_set,
                prepared_reference_root=package_root,
            )
            verification = verify_package(payload, package_root=package_root)
            observed = payload["prepared_reference_set"]["selected_references"]
            verified_packages[count] = (payload, verification)
            round_trip_details.append(
                {
                    "count": count,
                    "prepared_reference_set_sha256": payload[
                        "prepared_reference_set_sha256"
                    ],
                    "observed": observed,
                    "host_forwarding": verification["host_forwarding"][
                        "selected_references"
                    ],
                }
            )
            round_trip_ok = (
                round_trip_ok
                and verification.get("verified") is True
                and payload["prepared_reference_set"] == packaged_reference_set
                and payload["prepared_reference_set_sha256"]
                == packaged_reference_set["prepared_reference_set_sha256"]
                and observed == packaged_reference_set["selected_references"]
                and verification["prepared_reference_set"] == packaged_reference_set
                and verification["prepared_reference_set_sha256"]
                == packaged_reference_set["prepared_reference_set_sha256"]
                and len(verification["host_forwarding"]["selected_references"])
                == len(packaged_reference_set["selected_references"])
            )
        check(
            "state-aware wrapper preserves the portable canonical prepared set for zero, one, and multiple references",
            round_trip_ok,
            round_trip_details,
        )
        current_payload, current_verification = verified_packages[1]
        check(
            "state-aware package and verifier preserve unsupported state and assumptions end to end",
            current_payload["prepared_reference_set"]["selected_references"][0][
                "unsupported_or_occluded_state"
            ]
            == ["rear-body-silhouette"]
            and current_payload["prepared_reference_set"]["selected_references"][0][
                "unsupported_assumptions"
            ]
            == ["scene_placement"]
            and current_verification["prepared_reference_set"]["selected_references"][0][
                "unsupported_or_occluded_state"
            ]
            == ["rear-body-silhouette"]
            and current_verification["prepared_reference_set"]["selected_references"][0][
                "unsupported_assumptions"
            ]
            == ["scene_placement"],
            current_verification["prepared_reference_set"]["selected_references"],
        )

        missing_reference_errors: list[str] = []
        for arguments in (
            {},
            {
                "prepared_reference_set": {
                    "reference_selection_sha256": prepared_zero[
                        "reference_selection_sha256"
                    ],
                    "selected_references": [],
                }
            },
        ):
            try:
                build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), **_payload_inputs(graph), **arguments)
            except (TypeError, ValueError) as exc:
                missing_reference_errors.append(str(exc))
        check(
            "state-aware packaging rejects omitted prepared sets and omitted embedded selections",
            len(missing_reference_errors) == 2
            and any("requires a prepared reference set" in item for item in missing_reference_errors)
            and any("invalid shape" in item for item in missing_reference_errors),
            missing_reference_errors,
        )

        old_array_error = ""
        try:
            build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                **_payload_inputs(graph),
                prepared_reference_set=copy.deepcopy(current_rows),  # type: ignore[arg-type]
            )
        except (TypeError, ValueError) as exc:
            old_array_error = str(exc)
        check(
            "state-aware packaging rejects a non-object prepared-reference input",
            "must be a JSON object" in old_array_error,
            old_array_error,
        )

        prepared_zero_path = temp / "prepared-zero-reference-set.json"
        generic_state_output = temp / "generic-state-aware-package.json"
        write_json(prepared_zero_path, prepared_zero)
        generic_state_error = ""
        generic_state_stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(generic_state_stdout):
                generic_state_exit = build_generation_main(
                    [
                        "--model",
                        STATE_REFERENCE_MODEL,
                        "--prompt-file",
                        str(GENERATED / "prompt.txt"),
                        "--plot-file",
                        str(GENERATED / "prompt-plot.json"),
                        "--production-spec-file",
                        str(GENERATED / "production-specification.json"),
                        "--state-lineage-file",
                        str(GENERATED / "state-lineage.json"),
                        "--references-file",
                        str(prepared_zero_path),
                        "--out",
                        str(generic_state_output),
                        *reference_runtime_arguments,
                    ]
                )
            if generic_state_exit == 1:
                generic_state_error = "; ".join(json.loads(generic_state_stdout.getvalue())["errors"])
        finally:
            configure_pack_runtime(reference_settings)
        check(
            "generic generation CLI rejects state-aware graph bypass",
            "stateless CLI" in generic_state_error
            and "build_state_generation_package.py" in generic_state_error
            and not generic_state_output.exists(),
            generic_state_error,
        )

        state_cli_references = prepared_multi_root / "state-cli-references.json"
        write_json(state_cli_references, prepared_multi)

        def state_cli_arguments(
            *,
            prompt_path: Path,
            output_path: Path,
        ) -> list[str]:
            return [
                "--model",
                STATE_REFERENCE_MODEL,
                "--prompt-file",
                str(prompt_path),
                "--negative-file",
                str(GENERATED / "negative.txt"),
                "--integrated-prompt-file",
                str(GENERATED / "integrated-prompt.txt"),
                "--negative-provenance-file",
                str(GENERATED / "negative-provenance.json"),
                "--negative-transport",
                "integrated-critical",
                "--brief",
                str(graph["production_spec"]["source_brief"]),
                "--intent-file",
                str(GENERATED / "creative-intent.json"),
                "--plot-file",
                str(GENERATED / "prompt-plot.json"),
                "--production-spec-file",
                str(GENERATED / "production-specification.json"),
                "--state-lineage-file",
                str(GENERATED / "state-lineage.json"),
                "--species-profile-file",
                str(EXAMPLE / "species-morphology-profile.json"),
                "--individual-morphology-file",
                str(EXAMPLE / "individual-morphology-contract.json"),
                "--identity-contract-file",
                str(EXAMPLE / "character-identity-contract.json"),
                "--state-snapshot-file",
                str(GENERATED / "state-snapshot-C01.json"),
                "--scene-context-file",
                str(GENERATED / "scene-context-snapshot.json"),
                "--visual-projection-file",
                str(GENERATED / "visual-state-projection.json"),
                "--asset-render-spec-file",
                str(GENERATED / "asset-render-specification.json"),
                "--references-file",
                str(state_cli_references),
                "--parameters",
                json.dumps({"size": "1024x1024", "quality": "high"}),
                "--out",
                str(output_path),
                *reference_runtime_arguments,
            ]

        readonly_state_carrier = Path(
            prepared_multi["selected_references"][0]["transport"]["resolved_path"]
        )
        if not readonly_state_carrier.is_absolute():
            readonly_state_carrier = prepared_multi_root / readonly_state_carrier
        readonly_state_carrier = readonly_state_carrier.resolve(strict=True)
        readonly_state_hash = sha256_file(readonly_state_carrier)
        original_state_carrier_mode = stat.S_IMODE(readonly_state_carrier.stat().st_mode)
        readonly_state_mode = original_state_carrier_mode & ~(
            stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        )
        os.chmod(readonly_state_carrier, readonly_state_mode)
        observed_state_carrier_mode = stat.S_IMODE(readonly_state_carrier.stat().st_mode)
        try:
            missing_state_prompt = temp / "missing-state-cli-prompt.txt"
            state_precommit_output = temp / "state-readonly-precommit.json"
            state_precommit_previous = b"prior state-aware package\n"
            state_precommit_output.write_bytes(state_precommit_previous)
            state_precommit_companion = state_precommit_output.with_name(
                state_precommit_output.stem + ".references"
            )
            state_precommit_before = set(
                temp.glob(
                    f".{state_precommit_output.stem}-generation-package-*"
                )
            )
            state_precommit_stdout = io.StringIO()
            with contextlib.redirect_stdout(state_precommit_stdout):
                state_precommit_exit = build_state_generation_main(
                    state_cli_arguments(
                        prompt_path=missing_state_prompt,
                        output_path=state_precommit_output,
                    )
                )
            state_precommit_report = json.loads(state_precommit_stdout.getvalue())
            state_precommit_after = set(
                temp.glob(
                    f".{state_precommit_output.stem}-generation-package-*"
                )
            )
            state_precommit_observed = {
                "exit": state_precommit_exit == 1,
                "error": (
                    state_precommit_report.get("ok") is False
                    and missing_state_prompt.name
                    in state_precommit_report.get("errors", [""])[0]
                ),
                "prior_output": (
                    state_precommit_output.read_bytes() == state_precommit_previous
                ),
                "no_companion": not state_precommit_companion.exists(),
                "no_staging_leak": state_precommit_after == state_precommit_before,
                "source_hash": sha256_file(readonly_state_carrier)
                == readonly_state_hash,
                "source_mode": stat.S_IMODE(readonly_state_carrier.stat().st_mode)
                == observed_state_carrier_mode,
            }
            check(
                "state-aware CLI preserves a read-only source and prior output after a post-materialization failure",
                all(state_precommit_observed.values()),
                {"report": state_precommit_report, **state_precommit_observed},
            )

            state_cleanup_output = temp / "state-cleanup-failure.json"
            state_cleanup_previous = b"state cleanup failure prior output\n"
            state_cleanup_output.write_bytes(state_cleanup_previous)
            state_cleanup_before = set(
                temp.glob(f".{state_cleanup_output.stem}-generation-package-*")
            )
            state_cleanup_message = "injected state-aware cleanup failure"
            state_cleanup_stdout = io.StringIO()
            with mock.patch.object(
                state_generation_builder,
                "remove_cli_package_staging",
                side_effect=OSError(state_cleanup_message),
            ):
                with contextlib.redirect_stdout(state_cleanup_stdout):
                    state_cleanup_exit = build_state_generation_main(
                        state_cli_arguments(
                            prompt_path=missing_state_prompt,
                            output_path=state_cleanup_output,
                        )
                    )
            state_cleanup_report = json.loads(state_cleanup_stdout.getvalue())
            state_cleanup_after = set(
                temp.glob(f".{state_cleanup_output.stem}-generation-package-*")
            )
            state_cleanup_leaks = state_cleanup_after - state_cleanup_before
            state_cleanup_observed = {
                "exit": state_cleanup_exit == 1,
                "error_shape": state_cleanup_report.get("ok") is False
                and len(state_cleanup_report.get("errors", [])) == 2,
                "primary_error": missing_state_prompt.name
                in state_cleanup_report["errors"][0],
                "cleanup_error": state_cleanup_message
                in state_cleanup_report["errors"][1],
                "recovery_location": "transaction staging remains at"
                in state_cleanup_report["errors"][1],
                "prior_output": state_cleanup_output.read_bytes()
                == state_cleanup_previous,
                "one_staging_leak": len(state_cleanup_leaks) == 1,
            }
            check(
                "state-aware CLI reports both the primary error and cleanup failure without false success",
                all(state_cleanup_observed.values()),
                {"report": state_cleanup_report, **state_cleanup_observed},
            )
            for leaked_staging in state_cleanup_leaks:
                remove_cli_package_staging(leaked_staging)

            state_rollback_output = temp / "state-rollback-recovery.json"
            state_rollback_previous = b"recoverable prior state-aware package\n"
            state_rollback_output.write_bytes(state_rollback_previous)
            state_rollback_companion = state_rollback_output.with_name(
                state_rollback_output.stem + ".references"
            )
            state_rollback_before = set(
                temp.glob(f".{state_rollback_output.stem}-generation-package-*")
            )
            publish_failure = "injected state JSON publication failure"
            restore_failure = "injected prior state JSON restore failure"
            real_replace = os.replace

            def fail_state_publish_and_restore(source: Any, destination: Any) -> None:
                source_path = Path(source)
                destination_path = Path(destination)
                if (
                    source_path.name == state_rollback_output.name
                    and source_path.parent.name.startswith(
                        f".{state_rollback_output.stem}-generation-package-"
                    )
                    and destination_path.resolve() == state_rollback_output.resolve()
                ):
                    raise OSError(publish_failure)
                if (
                    source_path.name == ".previous-generation-package.json"
                    and destination_path.resolve() == state_rollback_output.resolve()
                ):
                    raise OSError(restore_failure)
                real_replace(source, destination)

            state_rollback_stdout = io.StringIO()
            with mock.patch.object(
                generation_builder.os,
                "replace",
                side_effect=fail_state_publish_and_restore,
            ):
                with contextlib.redirect_stdout(state_rollback_stdout):
                    state_rollback_exit = build_state_generation_main(
                        state_cli_arguments(
                            prompt_path=GENERATED / "prompt.txt",
                            output_path=state_rollback_output,
                        )
                    )
            state_rollback_report = json.loads(state_rollback_stdout.getvalue())
            state_rollback_after = set(
                temp.glob(f".{state_rollback_output.stem}-generation-package-*")
            )
            recovery_staging = state_rollback_after - state_rollback_before
            recovery_backup = (
                next(iter(recovery_staging)) / ".previous-generation-package.json"
                if len(recovery_staging) == 1
                else temp / "missing-recovery-backup"
            )
            check(
                "state-aware CLI preserves and reports the prior package when publication rollback is incomplete",
                state_rollback_exit == 1
                and state_rollback_report.get("ok") is False
                and len(state_rollback_report.get("errors", [])) == 3
                and state_rollback_report["errors"][0] == publish_failure
                and restore_failure in state_rollback_report["errors"][1]
                and "recovery staging was preserved at"
                in state_rollback_report["errors"][2]
                and len(recovery_staging) == 1
                and recovery_backup.read_bytes() == state_rollback_previous
                and not state_rollback_output.exists()
                and not state_rollback_companion.exists()
                and sha256_file(readonly_state_carrier) == readonly_state_hash
                and stat.S_IMODE(readonly_state_carrier.stat().st_mode)
                == observed_state_carrier_mode,
                state_rollback_report,
            )
            if recovery_backup.is_file():
                os.replace(recovery_backup, state_rollback_output)
            for leaked_staging in recovery_staging:
                remove_cli_package_staging(leaked_staging)
        finally:
            os.chmod(
                readonly_state_carrier,
                original_state_carrier_mode | stat.S_IWUSR,
            )
            configure_pack_runtime(reference_settings)
            catalog_cli.clear_runtime_caches()

        scope_mutation_errors: dict[str, str] = {}
        scope_mutations: dict[str, dict[str, Any]] = {}
        missing_scope = copy.deepcopy(prepared_multi)
        missing_scope["selected_references"][0].pop("review_dimensions")
        scope_mutations["omitted_scope"] = missing_scope
        changed_scope = copy.deepcopy(prepared_multi)
        changed_scope["selected_references"][0]["covers"] = [
            "invented-visible-state"
        ]
        scope_mutations["mutated_scope"] = changed_scope
        invalid_influence = copy.deepcopy(prepared_multi)
        invalid_influence["selected_references"][0]["intended_influence"].append(
            "scene-composition"
        )
        scope_mutations["invalid_influence"] = invalid_influence
        for name, reference_set in scope_mutations.items():
            try:
                reference_set = finalize_prepared_reference_set(
                    reference_set,
                    model=STATE_REFERENCE_MODEL,
                    package_root=prepared_multi_root,
                )
                build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                    **_payload_inputs(graph),
                    prepared_reference_set=reference_set,
                    prepared_reference_root=prepared_multi_root,
                )
            except ValueError as exc:
                scope_mutation_errors[name] = str(exc)
        check(
            "prepared state scope rejects omission, mutation, and invalid influence",
            set(scope_mutation_errors) == set(scope_mutations)
            and "invalid prepared-reference-set artifact"
            in scope_mutation_errors["omitted_scope"]
            and "exact ordered scope projection"
            in scope_mutation_errors["mutated_scope"]
            and "invalid prepared-reference-set artifact"
            in scope_mutation_errors["invalid_influence"],
            scope_mutation_errors,
        )

        reordered_reference_set = copy.deepcopy(prepared_multi)
        reordered_reference_set["selected_references"].reverse()
        source_mismatch_reference_set = copy.deepcopy(prepared_multi)
        source_mismatch_reference_set["selected_references"][0]["source"] = copy.deepcopy(
            prepared_multi["selected_references"][1]["source"]
        )
        source_mismatch_reference_set["selected_references"][0][
            "transport"
        ] = copy.deepcopy(prepared_multi["selected_references"][1]["transport"])
        ordered_projection_errors: dict[str, str] = {}
        for name, reference_set in (
            ("reordered", reordered_reference_set),
            ("source_mismatch", source_mismatch_reference_set),
        ):
            try:
                reference_set = finalize_prepared_reference_set(
                    reference_set,
                    model=STATE_REFERENCE_MODEL,
                    package_root=prepared_multi_root,
                )
                build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                    **_payload_inputs(graph),
                    prepared_reference_set=reference_set,
                    prepared_reference_root=prepared_multi_root,
                )
            except ValueError as exc:
                ordered_projection_errors[name] = str(exc)
        check(
            "prepared references reject reordered selection projections and source substitution",
            set(ordered_projection_errors) == {"reordered", "source_mismatch"}
            and all(
                "exact ordered scope projection" in error
                for error in ordered_projection_errors.values()
            ),
            ordered_projection_errors,
        )

        stale_outer_hash = copy.deepcopy(prepared_package_current)
        stale_outer_hash["reference_selection_sha256"] = "f" * 64
        stale_embedded_selection = copy.deepcopy(prepared_package_current)
        stale_embedded_selection["reference_selection"]["story_order"] += 1
        stale_selection_errors: dict[str, str] = {}
        for name, reference_set in (
            ("outer_hash", stale_outer_hash),
            ("embedded_self_hash", stale_embedded_selection),
        ):
            try:
                reference_set = finalize_prepared_reference_set(
                    reference_set,
                    model=STATE_REFERENCE_MODEL,
                    package_root=prepared_package_current_root,
                )
                build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                    **_payload_inputs(graph),
                    prepared_reference_set=reference_set,
                    prepared_reference_root=prepared_package_current_root,
                )
            except ValueError as exc:
                stale_selection_errors[name] = str(exc)
        check(
            "state-aware packaging rejects stale outer and embedded selection hashes",
            set(stale_selection_errors) == {"outer_hash", "embedded_self_hash"}
            and "does not match" in stale_selection_errors["outer_hash"]
            and "invalid reference-selection artifact"
            in stale_selection_errors["embedded_self_hash"],
            stale_selection_errors,
        )

        graph_mismatch_errors: dict[str, str] = {}
        graph_mutations = {
            "identity_contract_sha256": "1" * 64,
            "era_contract_sha256": "2" * 64,
            "appearance_variant_sha256": "3" * 64,
            "state_snapshot_sha256": "4" * 64,
            "story_order": int(graph["state_snapshot"]["story_order"]) + 1,
        }
        for field, bad_value in graph_mutations.items():
            reference_set = copy.deepcopy(prepared_package_current)
            reference_set["reference_selection"][field] = bad_value
            reference_set["reference_selection"] = finalize_artifact(
                reference_set["reference_selection"]
            )
            reference_set["reference_selection_sha256"] = reference_set[
                "reference_selection"
            ]["selection_sha256"]
            try:
                reference_set = finalize_prepared_reference_set(
                    reference_set,
                    model=STATE_REFERENCE_MODEL,
                    package_root=prepared_package_current_root,
                )
                build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                    **_payload_inputs(graph),
                    prepared_reference_set=reference_set,
                    prepared_reference_root=prepared_package_current_root,
                )
            except ValueError as exc:
                graph_mismatch_errors[field] = str(exc)
        check(
            "reference selection binds identity, era, appearance, state, and story order to the supplied graph",
            set(graph_mismatch_errors) == set(graph_mutations)
            and all(field in error for field, error in graph_mismatch_errors.items()),
            graph_mismatch_errors,
        )

        try:
            build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                **_payload_inputs(bad_graph),
                prepared_reference_set=prepared_zero,
                prepared_reference_root=prepared_zero_root,
            )
        except ValueError as exc:
            check(
                "state-aware wrapper rejects a cross-wired graph before packaging",
                "invalid state artifact graph" in str(exc),
            )
        else:
            check("state-aware wrapper rejects a cross-wired graph before packaging", False)

        mismatched_model_inputs = _payload_inputs(graph)
        mismatched_model_inputs["model"] = "different-image-model"
        try:
            build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                **mismatched_model_inputs,
                prepared_reference_set=prepared_zero,
                prepared_reference_root=prepared_zero_root,
            )
        except ValueError as exc:
            check(
                "state-aware wrapper binds the package model to the Production Specification",
                "package model differs" in str(exc),
                str(exc),
            )
        else:
            check(
                "state-aware wrapper binds the package model to the Production Specification",
                False,
            )

        mismatched_render_inputs = _payload_inputs(graph)
        mismatched_render_inputs["asset_render_spec"] = copy.deepcopy(
            graph["asset_render_spec"]
        )
        mismatched_render_inputs["asset_render_spec"]["target_model"] = (
            "different-image-model"
        )
        try:
            build_package(visual_continuity=fixture_visual(graph["production_spec"]), visual_root=fixture_root(), route_reading=fixture_reading(route='state-series'), 
                **mismatched_render_inputs,
                prepared_reference_set=prepared_zero,
                prepared_reference_root=prepared_zero_root,
            )
        except ValueError as exc:
            check(
                "state-aware wrapper binds the package model to the Asset Render Specification",
                "asset render specification target_model" in str(exc),
                str(exc),
            )
        else:
            check(
                "state-aware wrapper binds the package model to the Asset Render Specification",
                False,
            )

        identity_hash = artifact_hash(graph["identity_contract"])
        state_hash = artifact_hash(graph["state_snapshot"])
        binding = _reference_binding(
            binding_id="BIND-C01-SMOKE",
            role="current-identity",
            source=pack_source,
            identity_hash=identity_hash,
            state_hash=state_hash,
            start=0,
            end=None,
            features=["left-ear-notched"],
        )
        bindings_path = temp / "bindings.json"
        selection_path = temp / "selection.json"
        write_json(bindings_path, {"bindings": [binding]})
        selector_common_arguments = [
            "--bindings",
            str(bindings_path),
            "--selection-id",
            "SEL-SMOKE",
            "--identity-contract",
            str(EXAMPLE / "character-identity-contract.json"),
            "--state-snapshot",
            str(GENERATED / "state-snapshot-C01.json"),
            "--story-order",
            "25",
            "--required-feature",
            "left-ear-notched",
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            selector_exit = select_references_main(
                [
                    *selector_common_arguments,
                    "--out",
                    str(selection_path),
                    *reference_runtime_arguments,
                ]
            )
        selection = load_json(selection_path) if selection_path.is_file() else {}
        check(
            "standalone reference selector uses the core hash contract",
            selector_exit == 0
            and [
                row.get("source", {}).get("asset_id")
                for row in selection.get("selected_references", [])
            ]
            == [STATE_REFERENCE_ASSET_ID]
            and [row.get("role") for row in selection.get("selected_references", [])]
            == ["current-identity"]
            and selection["selected_references"][0]["source"] == pack_source,
            selection,
        )

        partial_runtime_vectors = [
            ["--state-file", str(reference_state_file)],
            ["--cache-dir", str(reference_cache_dir / "partial")],
            ["--managed-root", str(reference_managed_root / "partial")],
            [
                "--state-file",
                str(reference_state_file),
                "--cache-dir",
                str(reference_cache_dir / "partial-pair"),
            ],
            ["--pack-root", str(reference_pack_root)],
        ]
        partial_runtime_results: list[dict[str, Any]] = []
        for index, partial_runtime in enumerate(partial_runtime_vectors):
            partial_output = temp / f"partial-runtime-selection-{index}.json"
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    select_references_main(
                        [
                            *selector_common_arguments,
                            "--out",
                            str(partial_output),
                            *partial_runtime,
                        ]
                    )
            except SystemExit as exc:
                exit_code = exc.code
            else:
                exit_code = 0
            partial_runtime_results.append(
                {
                    "arguments": partial_runtime,
                    "exit_code": exit_code,
                    "output_exists": partial_output.exists(),
                }
            )
        check(
            "state reference selector rejects every partial shared pack runtime without output",
            all(
                row["exit_code"] == 2 and row["output_exists"] is False
                for row in partial_runtime_results
            ),
            partial_runtime_results,
        )

        off_type_bindings_path = temp / "off-type-bindings.json"
        off_type_bindings_path.write_text(
            json.dumps([1, 2], ensure_ascii=False),
            encoding="utf-8",
            newline="\n",
        )
        off_type_selection_path = temp / "off-type-selection.json"
        off_type_selector_arguments = list(selector_common_arguments)
        off_type_selector_arguments[
            off_type_selector_arguments.index("--bindings") + 1
        ] = str(off_type_bindings_path)
        off_type_stdout = io.StringIO()
        with contextlib.redirect_stdout(off_type_stdout):
            off_type_exit = select_references_main(
                [
                    *off_type_selector_arguments,
                    "--out",
                    str(off_type_selection_path),
                    *reference_runtime_arguments,
                ]
            )
        off_type_report = json.loads(off_type_stdout.getvalue())
        check(
            "the standalone selector reports a bindings file whose rows are not objects",
            off_type_exit == 1
            and off_type_report.get("errors", [None])[0]
            == "bindings file must be an array or an object containing a bindings array",
            off_type_report,
        )

        bundle_dir = temp / "valid-reference-bundle"
        plan = plan_reference_bundle(
            graph["identity_contract"],
            species_profile=graph["species_profile"],
            individual_morphology=graph["individual_morphology"],
            style_family_id="style-family-clear-portrait",
            target_model="gpt-image-2.5-flare",
            policy="core-coverage",
            out_dir=bundle_dir,
        )
        camera_required = set(
            load_json(ROOT / "schemas" / "camera-framing-contract.schema.json")["required"]
        )
        render_specs_by_file: dict[str, dict[str, Any]] = {}
        child_reports: list[bool] = []
        for row in plan["assets"]:
            child = load_json(bundle_dir / row["render_spec_file"])
            render_specs_by_file[row["render_spec_file"]] = child
            child_reports.append(
                validate_artifact(child).get("ok")
                and camera_required <= set(child["camera"])
                and set(child["camera"]) <= set(load_json(ROOT / "schemas" / "camera-framing-contract.schema.json")["properties"])
                and row["render_spec_sha256"] == artifact_hash(child)
            )
        bundle_graph_report = validate_reference_bundle_graph(
            plan=plan,
            render_specs_by_file=render_specs_by_file,
        )

        wrong_identity_child = copy.deepcopy(
            render_specs_by_file[plan["assets"][0]["render_spec_file"]]
        )
        wrong_identity_child["identity_contract_sha256"] = "f" * 64
        wrong_identity_child = finalize_artifact(wrong_identity_child)
        wrong_identity_plan = copy.deepcopy(plan)
        wrong_identity_plan["assets"][0]["render_spec_sha256"] = artifact_hash(
            wrong_identity_child
        )
        wrong_identity_plan = finalize_artifact(wrong_identity_plan)
        wrong_identity_children = copy.deepcopy(render_specs_by_file)
        wrong_identity_children[wrong_identity_plan["assets"][0]["render_spec_file"]] = (
            wrong_identity_child
        )
        wrong_identity_graph_report = validate_reference_bundle_graph(
            plan=wrong_identity_plan,
            render_specs_by_file=wrong_identity_children,
        )
        check(
            "reference bundle validates complete child cameras, links, and one identity hash",
            validate_artifact(plan).get("ok")
            and bool(child_reports)
            and all(child_reports)
            and bundle_graph_report["ok"] is True
            and {
                plan["identity_contract_sha256"],
                *(
                    child["identity_contract_sha256"]
                    for child in render_specs_by_file.values()
                ),
            }
            == {identity_hash}
            and validate_artifact(wrong_identity_child).get("ok") is True
            and validate_artifact(wrong_identity_plan).get("ok") is True
            and wrong_identity_graph_report["ok"] is False
            and any(
                "identity_contract_sha256 differs" in item
                for item in wrong_identity_graph_report["errors"]
            ),
            {
                "valid_graph": bundle_graph_report,
                "resigned_wrong_identity": wrong_identity_graph_report,
            },
        )

        render_hashes = [row["render_spec_sha256"] for row in plan["assets"]]
        duplicate_hash_plan = copy.deepcopy(plan)
        duplicate_hash_plan["assets"][1]["render_spec_sha256"] = (
            duplicate_hash_plan["assets"][0]["render_spec_sha256"]
        )
        duplicate_hash_plan = finalize_artifact(duplicate_hash_plan)
        duplicate_hash_report = validate_artifact(duplicate_hash_plan)
        unresolved_plan = copy.deepcopy(plan)
        unresolved_plan["unresolved_requirements"] = ["coverage-unresolved-smoke"]
        unresolved_plan = finalize_artifact(unresolved_plan)
        unresolved_plan_report = validate_artifact(unresolved_plan)
        check(
            "reference bundle requires unique render hashes and zero unresolved coverage",
            len(render_hashes) >= 2
            and len(render_hashes) == len(set(render_hashes))
            and plan["unresolved_requirements"] == []
            and duplicate_hash_report["ok"] is False
            and any(
                "render_spec_sha256 values must be unique" in item
                for item in duplicate_hash_report["errors"]
            )
            and unresolved_plan_report["ok"] is False
            and any(
                "unresolved coverage requirements" in item
                for item in unresolved_plan_report["errors"]
            ),
            {
                "render_hashes": render_hashes,
                "duplicate_mutation": duplicate_hash_report,
                "unresolved_mutation": unresolved_plan_report,
            },
        )

        matrix = plan["coverage_matrix"]
        first_requirement = next(iter(matrix))
        first_asset = matrix[first_requirement][0]
        another_asset = next(
            asset_id
            for asset_id in (row["asset_id"] for row in plan["assets"])
            if asset_id != first_asset
        )
        coverage_matrix_mutations: dict[str, Any] = {}
        scalar_matrix = copy.deepcopy(matrix)
        scalar_matrix[first_requirement] = first_asset
        coverage_matrix_mutations["scalar"] = scalar_matrix
        missing_matrix = copy.deepcopy(matrix)
        missing_matrix.pop(first_requirement)
        coverage_matrix_mutations["missing"] = missing_matrix
        extra_matrix = copy.deepcopy(matrix)
        extra_matrix["coverage-extra-smoke"] = [first_asset]
        coverage_matrix_mutations["extra"] = extra_matrix
        unknown_asset_matrix = copy.deepcopy(matrix)
        unknown_asset_matrix[first_requirement] = ["ASSET-UNKNOWN"]
        coverage_matrix_mutations["unknown-asset"] = unknown_asset_matrix
        duplicate_asset_matrix = copy.deepcopy(matrix)
        duplicate_asset_matrix[first_requirement] = [first_asset, first_asset]
        coverage_matrix_mutations["duplicate-asset"] = duplicate_asset_matrix
        stale_matrix = copy.deepcopy(matrix)
        stale_matrix[first_requirement] = [another_asset]
        coverage_matrix_mutations["stale"] = stale_matrix

        coverage_matrix_reports: dict[str, Any] = {}
        for mutation_name, mutation in coverage_matrix_mutations.items():
            corrupt_matrix_plan = copy.deepcopy(plan)
            corrupt_matrix_plan["coverage_matrix"] = mutation
            corrupt_matrix_plan = finalize_artifact(corrupt_matrix_plan)
            coverage_matrix_reports[mutation_name] = {
                "artifact": validate_artifact(corrupt_matrix_plan),
                "graph": validate_reference_bundle_graph(
                    plan=corrupt_matrix_plan,
                    render_specs_by_file=render_specs_by_file,
                ),
            }
        check(
            "reference bundle rejects scalar, missing, extra, unknown, duplicate, and stale coverage matrices",
            len(coverage_matrix_reports) == 6
            and all(
                report["artifact"]["ok"] is False and report["graph"]["ok"] is False
                for report in coverage_matrix_reports.values()
            ),
            coverage_matrix_reports,
        )

        candidate_path = temp / "candidate.png"
        candidate_path.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )
        inspection = {
            "manifest_id": "CM-SMOKE",
            "inspection_status": "inspected",
            "candidates": [
                {
                    "candidate_id": "CAN-SMOKE-01",
                    "asset_id": plan["assets"][0]["asset_id"],
                    "file": "candidate.png",
                    "visible_support": ["front identity"],
                    "unsupported_or_occluded": [],
                    "contradictions": [],
                    "recommendation": "adopt",
                }
            ],
        }
        plan_before_manifest = copy.deepcopy(plan)
        inspection_before_manifest = copy.deepcopy(inspection)
        manifest = build_manifest(plan=plan, inspection=inspection, base_dir=temp)
        manifest_before_adoption = copy.deepcopy(manifest)
        manifest_report = validate_artifact(manifest)
        manifest_lineage_report = validate_candidate_manifest_lineage(
            plan=plan,
            manifest=manifest,
        )
        stale_manifest = copy.deepcopy(manifest)
        stale_manifest["candidates"][0]["recommendation"] = "reject"
        stale_manifest_report = validate_artifact(stale_manifest)
        check(
            "candidate manifest is self-hashed and leaves its source plan and inspection immutable",
            manifest_report["ok"] is True
            and manifest["candidate_manifest_sha256"] == artifact_hash(manifest)
            and manifest_lineage_report["ok"] is True
            and plan == plan_before_manifest
            and inspection == inspection_before_manifest
            and stale_manifest_report["ok"] is False
            and any(
                "candidate_manifest_sha256 does not match canonical artifact content" in item
                for item in stale_manifest_report["errors"]
            ),
            {
                "manifest": manifest_report,
                "lineage": manifest_lineage_report,
                "stale_hash_mutation": stale_manifest_report,
            },
        )

        wrong_plan_manifest = copy.deepcopy(manifest)
        wrong_plan_manifest["bundle_plan_sha256"] = "a" * 64
        wrong_plan_manifest = finalize_artifact(wrong_plan_manifest)
        wrong_plan_manifest_report = validate_candidate_manifest_lineage(
            plan=plan,
            manifest=wrong_plan_manifest,
        )
        invalid_inspection = copy.deepcopy(inspection)
        invalid_inspection["candidates"][0]["recommendation"] = "accept"
        try:
            build_manifest(plan=plan, inspection=invalid_inspection, base_dir=temp)
        except ValueError as exc:
            invalid_inspection_error = str(exc)
        else:
            invalid_inspection_error = ""
        invalid_evidence_errors: list[str] = []
        for invalid_evidence in ("face", {"face": True}, 1, None, ["face", 7]):
            invalid_evidence_inspection = copy.deepcopy(inspection)
            invalid_evidence_inspection["candidates"][0]["visible_support"] = (
                invalid_evidence
            )
            try:
                build_manifest(
                    plan=plan,
                    inspection=invalid_evidence_inspection,
                    base_dir=temp,
                )
            except ValueError as exc:
                invalid_evidence_errors.append(str(exc))
        check(
            "candidate manifest rejects resigned links, invalid decisions, and scalar evidence arrays",
            validate_artifact(wrong_plan_manifest).get("ok") is True
            and wrong_plan_manifest_report["ok"] is False
            and any(
                "does not identify the bundle plan" in item
                for item in wrong_plan_manifest_report["errors"]
            )
            and "recommendation" in invalid_inspection_error
            and len(invalid_evidence_errors) == 5
            and all("visible_support" in item for item in invalid_evidence_errors),
            {
                "wrong_plan_link": wrong_plan_manifest_report,
                "invalid_inspection": invalid_inspection_error,
                "invalid_evidence_arrays": invalid_evidence_errors,
            },
        )

        registry_updates = [
            {
                "asset_registry_id": "ASSET-SMOKE-01",
                "effective_story_range": {"from_order": 0, "to_order": None},
                "supersedes": "ASSET-SMOKE-00",
                "registry_fields": {
                    "candidate_id": manifest["candidates"][0]["candidate_id"],
                    "continuity_role": "front identity",
                },
            }
        ]
        receipt = finalize_artifact(
            {
                "artifact_type": "adoption-receipt",
                "receipt_id": "AR-SMOKE",
                "issued_by": "ISSUER-SMOKE",
                "issued_at": "2026-08-15T00:00:00Z",
                "candidate_manifest_sha256": manifest["candidate_manifest_sha256"],
                "character_id": manifest["character_id"],
                "adoptions": [
                    {
                        "candidate_id": manifest["candidates"][0]["candidate_id"],
                        "asset_registry_id": "ASSET-SMOKE-01",
                        "effective_story_range": {"from_order": 0, "to_order": None},
                        "status": "adopted",
                    }
                ],
                "asset_registry_updates": copy.deepcopy(registry_updates),
                "adoption_receipt_sha256": ZERO_SHA256,
            }
        )
        receipt_round_trip = json.loads(json.dumps(receipt, ensure_ascii=False))
        adoption_report = validate_adoption_receipt(manifest=manifest, receipt=receipt)
        unknown_candidate_receipt = copy.deepcopy(receipt)
        unknown_candidate_receipt["adoptions"][0]["candidate_id"] = "CAN-UNKNOWN"
        unknown_candidate_receipt = finalize_artifact(unknown_candidate_receipt)
        unknown_candidate_report = validate_adoption_receipt(
            manifest=manifest,
            receipt=unknown_candidate_receipt,
        )
        wrong_manifest_receipt = copy.deepcopy(receipt)
        wrong_manifest_receipt["candidate_manifest_sha256"] = "b" * 64
        wrong_manifest_receipt = finalize_artifact(wrong_manifest_receipt)
        wrong_manifest_receipt_report = validate_adoption_receipt(
            manifest=manifest,
            receipt=wrong_manifest_receipt,
        )
        rejected_candidate_manifest = copy.deepcopy(manifest)
        rejected_candidate_manifest["candidates"][0]["recommendation"] = "reject"
        rejected_candidate_manifest = finalize_artifact(rejected_candidate_manifest)
        rejected_candidate_receipt = copy.deepcopy(receipt)
        rejected_candidate_receipt["candidate_manifest_sha256"] = (
            rejected_candidate_manifest["candidate_manifest_sha256"]
        )
        rejected_candidate_receipt = finalize_artifact(rejected_candidate_receipt)
        rejected_candidate_report = validate_adoption_receipt(
            manifest=rejected_candidate_manifest,
            receipt=rejected_candidate_receipt,
        )
        invalid_timestamp_receipt = copy.deepcopy(receipt)
        invalid_timestamp_receipt["issued_at"] = "2026-02-30T00:00:00Z"
        invalid_timestamp_receipt = finalize_artifact(invalid_timestamp_receipt)
        invalid_timestamp_report = validate_artifact(invalid_timestamp_receipt)
        malformed_range_receipt = copy.deepcopy(receipt)
        malformed_range_receipt["adoptions"][0]["effective_story_range"] = {
            "nonsense": True
        }
        malformed_range_receipt = finalize_artifact(malformed_range_receipt)
        malformed_range_report = validate_artifact(malformed_range_receipt)
        reverse_range_receipt = copy.deepcopy(receipt)
        reverse_range_receipt["adoptions"][0]["effective_story_range"] = {
            "from_order": 5,
            "to_order": 4,
        }
        reverse_range_receipt = finalize_artifact(reverse_range_receipt)
        reverse_range_report = validate_artifact(reverse_range_receipt)
        external_registry_receipt = copy.deepcopy(receipt)
        external_registry_receipt["registry_mutation"] = {"garbage": 1}
        external_registry_receipt = finalize_artifact(external_registry_receipt)
        external_registry_report = validate_artifact(external_registry_receipt)
        check(
            "consumer adoption validates the immutable candidate and manifest hash",
            validate_artifact(receipt).get("ok") is True
            and adoption_report["ok"] is True
            and validate_artifact(receipt_round_trip).get("ok") is True
            and receipt_round_trip["asset_registry_updates"] == registry_updates
            and receipt_round_trip["adoption_receipt_sha256"] == artifact_hash(
                receipt_round_trip
            )
            and manifest == manifest_before_adoption
            and validate_artifact(unknown_candidate_receipt).get("ok") is True
            and unknown_candidate_report["ok"] is False
            and any(
                "unknown candidate_id" in item
                for item in unknown_candidate_report["errors"]
            )
            and validate_artifact(wrong_manifest_receipt).get("ok") is True
            and wrong_manifest_receipt_report["ok"] is False
            and any(
                "does not identify the candidate manifest" in item
                for item in wrong_manifest_receipt_report["errors"]
            )
            and rejected_candidate_report["ok"] is False
            and any(
                "not recommended for adoption" in item
                for item in rejected_candidate_report["errors"]
            ),
            {
                "valid": adoption_report,
                "unknown_candidate_mutation": unknown_candidate_report,
                "wrong_manifest_mutation": wrong_manifest_receipt_report,
                "rejected_candidate_mutation": rejected_candidate_report,
            },
        )
        check(
            "adoption receipts reject invalid time, range, and unrecognized registry properties",
            invalid_timestamp_report["ok"] is False
            and malformed_range_report["ok"] is False
            and reverse_range_report["ok"] is False
            and external_registry_report["ok"] is False
            and any("UTC RFC3339" in item for item in invalid_timestamp_report["errors"])
            and any("effective_story_range" in item for item in malformed_range_report["errors"])
            and any("greater than or equal" in item for item in reverse_range_report["errors"])
            and any("unexpected properties" in item for item in external_registry_report["errors"]),
            {
                "timestamp": invalid_timestamp_report,
                "shape": malformed_range_report,
                "reverse": reverse_range_report,
                "registry": external_registry_report,
            },
        )

        unreachable_identity = copy.deepcopy(graph["identity_contract"])
        unreachable_identity["coverage_requirements"].append(
            {
                "requirement_id": "coverage-unreachable-smoke",
                "feature_refs": ["head.eye.pair"],
                "acceptable_views": ["unsupported-view-smoke"],
                "priority": "signature",
            }
        )
        failed_bundle_dir = temp / "invalid-reference-bundle"
        try:
            plan_reference_bundle(
                unreachable_identity,
                species_profile=graph["species_profile"],
                individual_morphology=graph["individual_morphology"],
                style_family_id="style-family-clear-portrait",
                target_model="gpt-image-2.5-flare",
                policy="core-coverage",
                out_dir=failed_bundle_dir,
            )
        except ValueError as exc:
            check(
                "invalid reference plan writes no child artifacts",
                "coverage_matrix.coverage-unreachable-smoke" in str(exc)
                and "minItems" in str(exc)
                and not failed_bundle_dir.exists(),
                str(exc),
            )
        else:
            check("invalid reference plan writes no child artifacts", False)

    configure_pack_runtime(None)
    catalog_cli.clear_runtime_caches()
    reference_runtime_temp.cleanup()
    return {
        "ok": all(item["passed"] for item in checks),
        "passed": sum(1 for item in checks if item["passed"]),
        "total": len(checks),
        "checks": checks,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
