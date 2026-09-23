#!/usr/bin/env python3
"""Exercise the exact prepared-reference generation commitment end to end."""
from __future__ import annotations

from visual_fixtures import fixture_visual, fixture_root
from reading_fixtures import fixture_reading
import contextlib
import copy
import io
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable
from unittest import mock

import catalog_cli
import build_generation_payload as generation_builder
from build_generation_payload import (
    build_payload,
    generation_input_sha256,
    main as _build_main,
    materialize_cli_reference_bundle,
)
from catalog_cli import configure_pack_runtime
from pack_manager import (
    atomic_write_json,
    default_settings,
    save_state,
    sha256_file,
    validate_pack,
    write_lock,
)
import production_spec
from production_spec import validate as validate_production_spec
from prompt_plot import content_sha256
from prepare_generation_references import (
    build_prepared_reference_set,
    empty_stateless_reference_set,
    main as prepare_main,
    prepare_references,
    validate_prepared_reference_set,
)
from reference_contract import build_reference_item
from reference_runtime import build_reference_use_plan, execute_reference_use_plan
from state_protocol import finalize_artifact, validate_artifact
from verify_generation_payload import main as _verify_main, verify_transports
from visual_fixtures import emit_paste_for_target, verify
from visual_evidence import render_svg


from smoke_fixtures import fixture_retrieval, cli_with_fixture_retrieval, isolate_home

isolate_home()


def verify_main(argv):
    from catalog_retrieval import runtime
    with runtime.using_pack_runtime(runtime._PACK_SETTINGS):
        return _verify_main([*argv, "--studio-root", str(fixture_root())])


def build_main(argv):
    from catalog_retrieval import runtime
    with runtime.using_pack_runtime(runtime._PACK_SETTINGS):
        return cli_with_fixture_retrieval(_build_main, argv)


def build_errors(argv) -> list[str]:
    """The errors the builder CLI printed; an empty list when it built the package."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = build_main(argv)
    return [] if code == 0 else json.loads(stdout.getvalue())["errors"]


PACK_ID = "0198b360-1234-7abc-8def-0123456789ab"
SPOOFED_PACK_ID = "0198b360-5678-7abc-8def-0123456789ab"
MODEL_ID = "fixture-image-model"
INTEGRATED_MODEL_ID = "fixture-integrated-image-model"
NATIVE_MODEL_ID = "fixture-native-negative-model"
# A model one service exposes, whose offering points at the service's observed
# parameter schema: only 1024x1024, at most one reference image.
OFFERED_MODEL_ID = "fixture-offered-model"
OFFERED_SNAPSHOT = "resources/observed-schemas/fixture-offered-model.svc.json"
OFFERED_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "const": "vendor:offered@1"},
        "positivePrompt": {"type": "string", "minLength": 1},
        "negativePrompt": {"type": "string", "minLength": 1},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "steps": {"type": "integer", "minimum": 1, "maximum": 50},
        "inputs": {
            "type": "object",
            "properties": {"referenceImages": {"type": "array", "minItems": 1, "maxItems": 1}},
            "additionalProperties": False,
        },
    },
    "required": ["model", "positivePrompt", "width", "height"],
    "allOf": [
        {"dependentRequired": {"width": ["height"], "height": ["width"]}},
        {"oneOf": [{"title": "1K (1:1)", "properties": {"width": {"const": 1024}, "height": {"const": 1024}}}]},
    ],
    "additionalProperties": False,
}
# A model whose one service takes the prepared reference as a single seed image
# rather than a list: one image goes on that key, and a second has nowhere to go.
SEED_MODEL_ID = "fixture-seed-image-model"
SEED_SNAPSHOT = "resources/observed-schemas/fixture-seed-image-model.svc.json"
SEED_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "const": "vendor:seeded@1"},
        "positivePrompt": {"type": "string", "minLength": 1},
        "negativePrompt": {"type": "string", "minLength": 1},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "seedImage": {"type": "string", "minLength": 1},
    },
    "required": ["model", "positivePrompt", "width", "height"],
    "allOf": [
        {"dependentRequired": {"width": ["height"], "height": ["width"]}},
        {"oneOf": [{"title": "1K (1:1)", "properties": {"width": {"const": 1024}, "height": {"const": 1024}}}]},
    ],
    "additionalProperties": False,
}
JPEG_ONLY_MODEL_ID = "fixture-jpeg-only-model"
NO_MEDIA_MODEL_ID = "fixture-no-media-model"
UNKNOWN_EXPLICIT_MODEL_ID = "fixture-unregistered-retained-model"
ASSET_ID = "fixture-reference-asset"
ARTIFACT_ID = "fixture-generic-svg"
HOST_REFERENCE_FIELDS = ["role", "resolved_path", "media_type", "sha256"]
ROOT = Path(__file__).resolve().parents[1]
PILOT_PRODUCTION_SPEC = (
    ROOT / "examples" / "state-aware-pilot" / "generated" / "production-specification.json"
)
_UNSET = object()

PROMPT = "A poised synthetic character in quiet studio light."
NEGATIVE = "unintended text, malformed anatomy"
NATIVE_NEGATIVE = "text, malformed anatomy"
INTEGRATED_PROMPT = (
    "A poised synthetic character with coherent anatomy in quiet, clean, "
    "text-free studio light."
)
# The render profile and style family the pilot specification selects, which
# the negative policy activates whenever they are selected.
_PILOT_VISUAL = json.loads(PILOT_PRODUCTION_SPEC.read_text(encoding="utf-8"))["visual_language"]
MEDIUM_SOURCES = [f"render-profile:{_PILOT_VISUAL['render_profile']}", f"style-family:{_PILOT_VISUAL['style_family']}"]
NEGATIVE_PROVENANCE = {
    "activated_sources": ["generation-hygiene", *MEDIUM_SOURCES],
    "diagnostic_sources_retained": ["anatomy-review"],
    "semantic_exclusions_user_supplied": [],
    "affirmative_translations": {"anatomy-review": "coherent anatomy", "generation-hygiene": "text-free",
                                 MEDIUM_SOURCES[0]: "clean", MEDIUM_SOURCES[1]: "poised"},
}
GENERIC_DISTINCTIVE_DETAIL = {
    "id": "detail-1",
    "feature_type": "healed scar",
    "target_region": "right eyebrow and upper cheek",
    "laterality": "right",
    "landmark_relation": (
        "starts above the outer eyebrow and ends below the outer eye corner"
    ),
    "count_or_distribution": "one",
    "relative_size": "length about one and a half eye heights",
    "shape_and_path": "narrow slightly irregular diagonal line",
    "orientation": "diagonal downward toward the cheek",
    "color_and_value": "one value lighter than the local skin",
    "depth_and_relief": "shallow healed depression",
    "edge_and_texture": "soft healed edges",
    "surface_interaction": (
        "follows the facial plane and subtly changes local texture"
    ),
    "age_or_condition": "fully healed",
    "visibility_and_occlusion": "visible in frontal and three-quarter views",
    "identity_priority": "signature",
    "continuity_rules": ["subject-relative right side remains fixed"],
    "source_confidence": "explicit-user",
}


class SmokeFailure(AssertionError):
    pass


class CheckCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            raise SmokeFailure(message)


def _model_record(
    model_id: str,
    label: str,
    media_types: list[str] | None,
    *,
    negative_transport_mode: str = "separate-field",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": model_id,
        "label": label,
        "aliases": [model_id.replace("-", " ")],
        "operation_kind": "generation",
        "offerings": [],
        "supports_negative_prompt": negative_transport_mode != "integrated-critical",
        "prompt_style": "Clear natural-language art direction with explicit constraints.",
        "negative_transport_mode": negative_transport_mode,
        "negative_transport_notes": (
            "Transmit avoidance instructions through the explicitly declared fixture transport."
        ),
        "ordering": ["subject", "scene", "rendering", "constraints"],
        "search_terms": [
            {
                "phrase": label.lower(),
                "facet": "model",
                "weight": 1.0,
                "source": "author",
            }
        ],
    }
    if media_types is not None:
        record["reference_input_media_types"] = media_types
    return record


def _write_fixture_pack(pack_root: Path) -> Path:
    (pack_root / "records").mkdir(parents=True)
    (pack_root / "resources").mkdir()
    atomic_write_json(
        pack_root / "pack.json",
        {
            "pack_id": PACK_ID,
            "name": "Generation Reference Smoke Pack",
            "description": "Released fixture pack for exact generation-reference tests.",
            "release": "2026.01.01.1",
            "content": {
                "record_globs": ["records/**/*.json"],
                "resource_globs": ["resources/**/*"],
                "resource_bindings": {"service-profiles": "resources/service-profiles.json"},
            },
            "capabilities": ["model-adapters", "visual-reference-assets"],
            "dependencies": [],
            "optional_dependencies": [],
            "replaces": [],
            "license": "GPL-3.0-only",
        },
    )
    atomic_write_json(
        pack_root / "resources" / "service-profiles.json",
        {"services": {"runware": {
            "label": "Synthetic offline image interface",
            "transport": "runware",
            "endpoint": {"base_url": "https://example.invalid/synthetic", "method": "POST"},
            "auth": {"env_var": "SYNTHETIC_OFFLINE_KEY"},
            "operations": {"imageInference": {}},
        }}},
    )
    atomic_write_json(
        pack_root / "records" / "canonical.json",
        {
            "kind": "module",
            "category": "species",
            "records": [
                {
                    "id": "fixture-generic-subject",
                    "label": "Fixture generic subject",
                    "curation_status": "curated",
                    "category": "species",
                    "prompt": "a safe generic fixture subject",
                    "domains": ["shared"],
                    "tags": ["fixture", "generic subject"],
                    "search_terms": [
                        {
                            "phrase": "generic fixture subject",
                            "facet": "species",
                            "weight": 1.0,
                            "source": "author",
                        }
                    ],
                },
                {
                    "id": "fixture-unlinked-subject",
                    "label": "Fixture unlinked subject",
                    "curation_status": "curated",
                    "category": "species",
                    "prompt": "a safe generic fixture subject",
                    "domains": ["shared"],
                    "tags": ["fixture", "generic subject", "unlinked"],
                    "search_terms": [
                        {
                            "phrase": "unlinked fixture subject",
                            "facet": "species",
                            "weight": 1.0,
                            "source": "author",
                        }
                    ],
                }
            ],
        },
    )
    atomic_write_json(
        pack_root / "records" / "models.json",
        {
            "kind": "model",
            "records": [
                _model_record(
                    MODEL_ID,
                    "Fixture image model",
                    ["image/png", "image/jpeg", "image/webp"],
                ),
                _model_record(
                    INTEGRATED_MODEL_ID,
                    "Fixture integrated image model",
                    ["image/png", "image/jpeg", "image/webp"],
                    negative_transport_mode="integrated-critical",
                ),
                _model_record(
                    NATIVE_MODEL_ID,
                    "Fixture native negative model",
                    ["image/png", "image/jpeg", "image/webp"],
                    negative_transport_mode="native-subset",
                ),
                _model_record(
                    JPEG_ONLY_MODEL_ID,
                    "Fixture JPEG-only model",
                    ["image/jpeg"],
                ),
                _model_record(
                    NO_MEDIA_MODEL_ID,
                    "Fixture model without media declaration",
                    None,
                ),
                {
                    **_model_record(
                        OFFERED_MODEL_ID,
                        "Fixture offered model",
                        ["image/png", "image/jpeg", "image/webp"],
                    ),
                    "recommended_parameters": {"steps": 20, "guidance": [3, 5]},
                    "offerings": [
                        {
                            "service": "runware",
                            "model_identifier": "vendor:offered@1",
                            "request_keys": {"model": ["model"], "prompt": ["positivePrompt"],
                                             "negative prompt": ["negativePrompt"],
                                             "reference images": ["inputs.referenceImages"]},
                            "parameter_keys": {"steps": "steps"},
                            "constraints": {"reference_images": {"max": 1}, "geometry": "1024x1024 only"},
                            "observed_at": "2026-09-13",
                            "schema_snapshot": OFFERED_SNAPSHOT,
                        }
                    ],
                },
                {
                    **_model_record(
                        SEED_MODEL_ID,
                        "Fixture seed image model",
                        ["image/png", "image/jpeg", "image/webp"],
                    ),
                    "offerings": [
                        {
                            "service": "runware",
                            "model_identifier": "vendor:seeded@1",
                            "request_keys": {"model": ["model"], "prompt": ["positivePrompt"],
                                             "negative prompt": ["negativePrompt"], "seed image": ["seedImage"]},
                            "constraints": {"reference_images": {"max": 1}, "geometry": "1024x1024 only"},
                            "observed_at": "2026-09-13",
                            "schema_snapshot": SEED_SNAPSHOT,
                        }
                    ],
                },
            ],
        },
    )
    atomic_write_json(
        pack_root / OFFERED_SNAPSHOT,
        {
            "artifact_type": "observed-parameter-schema",
            "model_id": OFFERED_MODEL_ID,
            "service": "runware",
            "model_identifier": "vendor:offered@1",
            "observed_at": "2026-09-13",
            "source": "the fixture service's model schema endpoint",
            "unenforced": [],
            "schema": OFFERED_SCHEMA,
        },
    )
    atomic_write_json(
        pack_root / SEED_SNAPSHOT,
        {
            "artifact_type": "observed-parameter-schema",
            "model_id": SEED_MODEL_ID,
            "service": "runware",
            "model_identifier": "vendor:seeded@1",
            "observed_at": "2026-09-13",
            "source": "the fixture service's model schema endpoint",
            "unenforced": [],
            "schema": SEED_SCHEMA,
        },
    )

    svg_path = pack_root / "resources" / "generic-reference.svg"
    svg_path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64">
  <rect width="96" height="64" rx="8" fill="#20252b"/>
  <circle cx="48" cy="32" r="20" fill="#d4a85f"/>
</svg>
""",
        encoding="utf-8",
        newline="\n",
    )
    svg_hash = sha256_file(svg_path)
    atomic_write_json(
        pack_root / "records" / "assets.json",
        {
            "kind": "asset",
            "records": [
                {
                    "id": ASSET_ID,
                    "label": "Fixture generic evidence artifact",
                    "curation_status": "curated",
                    "category": "visual-reference",
                    "asset_type": "reference-guide",
                    "description": "Safe generic rectangle-and-circle reference geometry.",
                    "source_ref_id": "fixture-generic-svg-source",
                    "source_sha256": svg_hash,
                    "source_media_type": "image/svg+xml",
                    "source_dimensions": {"width": 96, "height": 64},
                    "disposition": "fixture-only",
                    "evidence_relation": "provides generic geometry for the smoke test",
                    "canonical_record_ids": ["fixture-generic-subject"],
                    "primary_resource": "resources/generic-reference.svg",
                    "resource_refs": ["resources/generic-reference.svg"],
                    "artifacts": [
                        {
                            "artifact_id": ARTIFACT_ID,
                            "role": "faithful-archival-vector",
                            "path": "resources/generic-reference.svg",
                            "media_type": "image/svg+xml",
                            "sha256": svg_hash,
                        }
                    ],
                    "tags": ["fixture", "generic svg", "visual reference"],
                }
            ],
        },
    )
    write_lock(pack_root)
    return svg_path


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _stateless_lineage() -> dict[str, Any]:
    return finalize_artifact(
        {
            "artifact_type": "state-lineage",
            "mode": "stateless",
            "species_profile_sha256": None,
            "individual_morphology_sha256": None,
            "identity_contract_sha256": None,
            "era_contract_sha256": None,
            "form_contract_sha256": None,
            "appearance_variant_sha256": None,
            "state_snapshot_sha256": None,
            "scene_context_sha256": None,
            "visual_projection_sha256": None,
            "asset_render_spec_sha256": None,
            "visual_authority_sha256": None,
            "visual_evidence_bundle_sha256": None,
        }
    )


APPROVED_PLOT = {
    "artifact_type": "prompt-plot",
    "story": [
        {"id": "s1", "beat": "The character is photographed for a reference study.", "visibility": "visible"},
    ],
    "derived": [
        {"kind": "shows", "statement": "the character against a plain ground", "from": ["s1"]},
        {"kind": "placement", "statement": "the character stands centred", "from": ["s1"]},
        {"kind": "composition", "statement": "a knee-up view at eye height", "from": ["s1"]},
        {"kind": "must_preserve", "statement": "the declared proportions", "from": ["s1"]},
        {"kind": "free", "statement": "the ground exact tone"},
    ],
}
APPROVED_PLOT["approved"] = {
    "by": "the person who owns the brief",
    "at": "2026-09-11T00:00:00Z",
    "content_sha256": content_sha256(APPROVED_PLOT),
}


def _production_spec(model: str) -> dict[str, Any]:
    """The pilot's full scene as a stateless one-off: no lineage and no contract references."""
    value = json.loads(PILOT_PRODUCTION_SPEC.read_text(encoding="utf-8"))
    value["source_brief"] = "Exact one-off generation reference smoke test."
    value["target_model"] = model
    value["state_context"] = {"mode": "stateless", "notes": []}
    for subject in value["subjects"]:
        for field in (
            "species_morphology_profile_ref",
            "individual_morphology_contract_ref",
            "identity_contract_ref",
            "state_snapshot_ref",
            "visual_projection_ref",
        ):
            subject.pop(field)
    return value


def _package(
    prepared_reference_set: Any,
    *,
    model: str = MODEL_ID,
    negative_prompt: str = NEGATIVE,
    integrated_prompt: str = INTEGRATED_PROMPT,
    native_negative: str = "",
    negative_transport: str = "auto",
    production_target_model: str | None = None,
    parameters: dict[str, Any] | None = None,
    production_spec_override: Any = _UNSET,
    prepared_reference_root: Path | None = None,
    negative_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    production_spec = (
        _production_spec(production_target_model or model)
        if production_spec_override is _UNSET
        else production_spec_override
    )
    from request_validation_fixtures import fixture_validation
    if model == UNKNOWN_EXPLICIT_MODEL_ID:
        from request_validation_fixtures import interface_validation
        import request_renderer
        validation = interface_validation(
            fixture_root(),
            target={"service": "synthetic-host", "model_identifier": model, "operation": "generation"},
            record={}, offering={},
            service_record={"id": "synthetic-host", "endpoint": {"base_url": "https://example.invalid/synthetic-interface"},
                            "operations": {"generation": {}}},
            transport=request_renderer, reference_mode="prompt-prefix",
        )
    else:
        validation = fixture_validation(fixture_root(), model, reference_mode='prompt-prefix')

    return build_payload(request_validation=validation, input_root=fixture_root(), visual_continuity=fixture_visual(production_spec), visual_root=fixture_root(), route_reading=fixture_reading(route='generation'), 
        retrieval_record=fixture_retrieval(PROMPT, APPROVED_PLOT),
        plot=copy.deepcopy(APPROVED_PLOT),
        model=model,
        prompt=PROMPT,
        negative_prompt=negative_prompt,
        integrated_prompt=integrated_prompt,
        native_negative=native_negative,
        brief="Exact one-off generation reference smoke test.",
        creative_intent={"image_promise": "A coherent character study."},
        parameters=(parameters if parameters is not None else {"size": "1024x1024", "quality": "high"}),
        negative_transport=negative_transport,
        negative_provenance=copy.deepcopy(NEGATIVE_PROVENANCE if negative_provenance is None else negative_provenance),
        production_spec=production_spec,
        prepared_reference_set=prepared_reference_set,
        prepared_reference_root=prepared_reference_root,
    )


def _forwarding_preserves_declared_parts(verified: dict[str, Any], prompt: str, reference_count: int) -> bool:
    """Check the declared transform's coverage without recognizing prompt words."""
    forwarded = verified["host_forwarding"]
    text = forwarded["effective_prompt"]
    cursor = 0
    authored = []
    reference_parts = []
    for item in forwarded["prompt_trace"]:
        start, end = item["target_range"]["start"], item["target_range"]["end"]
        if start != cursor or not start <= end <= len(text):
            return False
        cursor = end
        if item["source_kind"] in {"authored", "model-setting"}:
            authored.append(text[start:end])
        elif item["source_kind"] == "reference-binding":
            if item["transform_id"] != "reference-delivery" or not item["source_refs"] or end == start:
                return False
            reference_parts.append(item)
        else:
            return False
    expected = ["reference:" + str(i+1) for i in range(reference_count)]
    actual = [binding for part in reference_parts for binding in part["binding_ids"]]
    return (cursor == len(text) and "".join(authored) == prompt and actual == expected
            and len(reference_parts) == (1 if reference_count else 0))


def _verify_rejected(
    candidate: dict[str, Any],
    *,
    package_root: Path | None = None,
) -> bool:
    try:
        verify(candidate, package_root=package_root)
    except (ValueError, OSError):
        return True
    return False


def _resign_generation_package(candidate: dict[str, Any]) -> dict[str, Any]:
    """Re-sign a mutated reference set and the package commitment around it."""

    result = copy.deepcopy(candidate)
    result["prepared_reference_set"] = finalize_artifact(
        result["prepared_reference_set"]
    )
    set_hash = result["prepared_reference_set"]["prepared_reference_set_sha256"]
    result["prepared_reference_set_sha256"] = set_hash
    result["generation_contract"]["prepared_reference_set_sha256"] = set_hash
    commitment = generation_input_sha256(result)
    result["generation_input_sha256"] = commitment
    result["generation_contract"]["generation_input_sha256"] = commitment
    return result


def run() -> dict[str, Any]:
    checked = CheckCounter()
    mutation_count = 0
    configure_pack_runtime(None)
    catalog_cli.clear_runtime_caches()
    try:
        with tempfile.TemporaryDirectory(prefix="cpb-generation-reference-") as temporary:
            # Resolve once: staging paths recorded by the checks below are
            # resolved, so a non-canonical temporary directory (an 8.3 short
            # name or a junction, as on some Windows runners) would otherwise
            # make every glob-versus-recorded-path comparison fail.
            root = Path(temporary).resolve()
            pack_root = root / "packs" / "generation-reference-smoke"
            pack_svg = _write_fixture_pack(pack_root)
            report = validate_pack(pack_root, require_lock=True, verify_lock=True)
            checked(report.valid, f"released fixture pack is invalid: {report.to_dict()}")
            checked(report.lock_present, "released fixture pack has no lock")

            state_file = root / "pack-state.json"
            cache_dir = root / "cache"
            managed_root = root / "managed"
            save_state(
                state_file,
                {
                    "pack_roots": [],
                    "enabled_packs": [PACK_ID],
                    "resource_providers": {"service-profiles": PACK_ID},
                },
            )
            checked(state_file.is_file(), "explicit pack state was not written")
            runtime_arguments = [
                "--state-file",
                str(state_file),
                "--cache-dir",
                str(cache_dir),
                "--managed-root",
                str(managed_root),
                "--pack-root",
                str(pack_root),
            ]
            settings = default_settings(
                extra_roots=(pack_root,),
                state_file=state_file,
                cache_dir=cache_dir,
                managed_root=managed_root,
                default_enabled_packs=(),
                default_resource_providers={"service-profiles": PACK_ID},
            )

            configure_pack_runtime(settings)
            catalog_cli.clear_runtime_caches()
            fixture_plan = build_reference_use_plan(
                [
                    {
                        "record_id": "fixture-generic-subject",
                        "intended_influence": "identity",
                    }
                ],
                transport_mode="multi-image",
                source_lighting_mode="preserve",
                target_model=MODEL_ID,
                include_technical_roles=["faithful-archival-vector"],
            )
            checked(
                fixture_plan["selected_records"]
                == [
                    {
                        "record_id": "fixture-generic-subject",
                        "intended_influence": "identity",
                    }
                ],
                "explicit canonical record use changed during reference planning",
            )
            checked(
                len(fixture_plan["reference_items"]) == 1
                and fixture_plan["reference_items"][0]["technical_role"]
                == "faithful-archival-vector",
                "canonical record-use plan did not activate its linked SVG",
            )
            selected_pack = [
                {
                    "role": "permanent-identity",
                    "source": copy.deepcopy(fixture_plan["reference_items"][0]["source"]),
                }
            ]
            checked(
                set(selected_pack[0]) == {"role", "source"},
                "explicit plan projection returned a stale flat reference shape",
            )
            checked(
                set(selected_pack[0]["source"])
                == {
                    "kind",
                    "pack_id",
                    "asset_id",
                    "artifact_id",
                    "resolved_path",
                    "media_type",
                    "sha256",
                },
                "explicit plan projection returned an incomplete pack-artifact source",
            )
            checked(
                selected_pack[0]["source"]["kind"] == "pack-artifact"
                and selected_pack[0]["source"]["pack_id"] == PACK_ID
                and selected_pack[0]["source"]["artifact_id"] == ARTIFACT_ID,
                "catalog selector changed pack provenance",
            )

            supplied_svg = root / "supplied-scene.svg"
            supplied_svg.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
  <circle cx="40" cy="40" r="32" fill="#456b8b"/>
  <rect x="26" y="26" width="28" height="28" fill="#f0d8a8"/>
</svg>
""",
                encoding="utf-8",
                newline="\n",
            )
            supplied_selection = {
                "role": "scene-geometry",
                "source": {
                    "kind": "supplied-file",
                    "reference_id": "supplied-scene",
                    "resolved_path": str(supplied_svg.resolve(strict=True)),
                },
            }
            supplied_identity_selection = {
                "role": "permanent-identity",
                "source": {
                    "kind": "supplied-file",
                    "reference_id": "supplied-identity",
                    "resolved_path": str(pack_svg.resolve(strict=True)),
                },
            }
            selections_by_count = [
                [],
                [supplied_identity_selection],
                [supplied_identity_selection, supplied_selection],
            ]

            prompt_file = root / "prompt.txt"
            negative_file = root / "negative.txt"
            integrated_file = root / "integrated.txt"
            provenance_file = root / "negative-provenance.json"
            production_spec_file = root / "production-specification.json"
            plot_file = root / "prompt-plot.json"
            state_lineage_file = root / "state-lineage.json"
            prompt_file.write_text(PROMPT + "\n", encoding="utf-8", newline="\n")
            negative_file.write_text(NEGATIVE + "\n", encoding="utf-8", newline="\n")
            integrated_file.write_text(
                INTEGRATED_PROMPT + "\n", encoding="utf-8", newline="\n"
            )
            _write_json(provenance_file, NEGATIVE_PROVENANCE)
            _write_json(plot_file, APPROVED_PLOT)
            fixture_lineage = _stateless_lineage()
            _write_json(state_lineage_file, fixture_lineage)
            _write_json(
                production_spec_file,
                _production_spec(MODEL_ID),
            )

            prepared_round_trips: list[dict[str, Any]] = []
            packages: list[dict[str, Any]] = []
            verified_round_trips: list[dict[str, Any]] = []
            for count, selections in enumerate(selections_by_count):
                selection_file = root / f"selections-{count}.json"
                prepared_file = root / f"prepared-{count}.json"
                transport_dir = root / f"transports-{count}"
                _write_json(selection_file, selections)
                with contextlib.redirect_stdout(io.StringIO()):
                    prepare_exit = prepare_main(
                        [
                            "--supplied-selection-file",
                            str(selection_file),
                            "--model",
                            MODEL_ID,
                            "--output-dir",
                            str(transport_dir),
                            "--max-side",
                            "128",
                            "--out",
                            str(prepared_file),
                            *runtime_arguments,
                        ]
                    )
                checked(prepare_exit == 0, f"{count}-reference preparation failed")
                prepared = json.loads(prepared_file.read_text(encoding="utf-8"))
                checked(
                    set(prepared)
                    == {
                        "artifact_type",
                        "set_id",
                        "transport_mode",
                        "target_model",
                        "reference_selection",
                        "reference_selection_sha256",
                        "reference_use_plan",
                        "reference_use_plan_sha256",
                        "surface_lighting_plan_sha256",
                        "zero_reference_reason",
                        "reference_preamble",
                        "prompt_artifacts",
                        "selected_references",
                        "single_board",
                        "prepared_reference_set_sha256",
                    },
                    f"{count}-reference preparation did not return the canonical boundary",
                )
                checked(
                    prepared["artifact_type"] == "prepared-reference-set"
                    and prepared["reference_selection"] is None
                    and prepared["reference_selection_sha256"] is None
                    and prepared["reference_use_plan"] is None,
                    f"{count}-reference stateless preparation invented selection lineage",
                )
                checked(
                    (
                        count == 0
                        and prepared["transport_mode"] == "none"
                        and prepared["target_model"] is None
                        and prepared["zero_reference_reason"]["code"]
                        == "no-canonical-record-selected"
                    )
                    or (
                        count > 0
                        and prepared["transport_mode"] == "multi-image"
                        and prepared["target_model"] == MODEL_ID
                        and prepared["zero_reference_reason"] is None
                    ),
                    f"{count}-reference preparation chose an invalid transport mode",
                )
                checked(
                    len(prepared["selected_references"]) == count,
                    f"{count}-reference preparation changed count",
                )
                prepared_round_trips.append(prepared)

                package_file = root / f"generation-package-{count}.json"
                with contextlib.redirect_stdout(io.StringIO()):
                    build_exit = build_main(
                        [
                            "--model",
                            MODEL_ID,
                            "--prompt-file",
                            str(prompt_file),
                            "--negative-file",
                            str(negative_file),
                            "--integrated-prompt-file",
                            str(integrated_file),
                            "--negative-provenance-file",
                            str(provenance_file),
                            "--negative-transport",
                            "auto",
                            "--plot-file",
                            str(plot_file),
                            "--production-spec-file",
                            str(production_spec_file),
                            "--state-lineage-file",
                            str(state_lineage_file),
                            "--brief",
                            "Exact shared-runtime reference round trip.",
                            "--references-file",
                            str(prepared_file),
                            "--parameters",
                            json.dumps({"size": "1024x1024", "quality": "high"}),
                            "--out",
                            str(package_file),
                            *runtime_arguments,
                        ]
                    )
                checked(build_exit == 0, f"{count}-reference package build failed")
                package = json.loads(package_file.read_text(encoding="utf-8"))
                packaged_set = package["prepared_reference_set"]
                companion_dir = package_file.with_name(package_file.stem + ".references")
                checked(
                    package["prepared_reference_set_sha256"]
                    == packaged_set["prepared_reference_set_sha256"]
                    and package["generation_contract"]["prepared_reference_set_sha256"]
                    == packaged_set["prepared_reference_set_sha256"]
                    and (
                        (count == 0 and packaged_set == prepared and not companion_dir.exists())
                        or (
                            count > 0
                            and companion_dir.is_dir()
                            and [
                                (row["role"], row["source"], row["authority"])
                                for row in packaged_set["selected_references"]
                            ]
                            == [
                                (row["role"], row["source"], row["authority"])
                                for row in prepared["selected_references"]
                            ]
                            and all(
                                not Path(row["transport"]["resolved_path"]).is_absolute()
                                and row["transport"]["resolved_path"].startswith(
                                    companion_dir.name + "/"
                                )
                                for row in packaged_set["selected_references"]
                            )
                        )
                    ),
                    f"{count}-reference package did not publish one portable canonical set",
                )
                checked(
                    "reference_selection" not in package
                    and "reference_selection_sha256" not in package
                    and "selected_references" not in package["generation_payload"],
                    f"{count}-reference package retained a duplicate reference truth",
                )
                packages.append(package)

                verified_file = root / f"verified-{count}.json"
                with contextlib.redirect_stdout(io.StringIO()):
                    verify_exit = verify_main(
                        [
                            str(package_file),
                            "--target",
                            MODEL_ID,
                            "--payload-out",
                            str(verified_file),
                            *runtime_arguments,
                        ]
                    )
                checked(verify_exit == 0, f"{count}-reference package did not verify")
                verified = json.loads(verified_file.read_text(encoding="utf-8"))
                checked(verified["verified"] is True, f"{count}-reference verification is false")
                checked(
                    verified["prepared_reference_set"] == packaged_set
                    and verified["prepared_reference_set_sha256"]
                    == packaged_set["prepared_reference_set_sha256"],
                    f"{count}-reference verification changed the canonical prepared set",
                )
                checked(
                    verified["prepared_reference_set"]["reference_selection"] is None
                    and verified["prepared_reference_set"]["reference_selection_sha256"]
                    is None,
                    f"{count}-reference verification invented selection lineage",
                )
                checked(
                    [row["role"] for row in verified["host_forwarding"]["selected_references"]]
                    == [row["role"] for row in prepared["selected_references"]],
                    f"{count}-reference host forwarding changed caller order",
                )
                checked(
                    all(
                        list(row) == HOST_REFERENCE_FIELDS
                        for row in verified["host_forwarding"]["selected_references"]
                    ),
                    f"{count}-reference host forwarding exposed source/provenance fields",
                )
                checked(
                    _forwarding_preserves_declared_parts(verified, PROMPT, count)
                    and verified["paste"]["paste_prompt"] == verified["host_forwarding"]["effective_prompt"],
                    f"{count}-reference declared conversion or authored rendition was not preserved",
                )
                verified_round_trips.append(verified)

            readonly_carrier = Path(
                prepared_round_trips[1]["selected_references"][0]["transport"][
                    "resolved_path"
                ]
            ).resolve(strict=True)
            readonly_source_hash = sha256_file(readonly_carrier)
            original_carrier_mode = stat.S_IMODE(readonly_carrier.stat().st_mode)
            readonly_mode = original_carrier_mode & ~(
                stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
            )
            os.chmod(readonly_carrier, readonly_mode)
            observed_readonly_mode = stat.S_IMODE(readonly_carrier.stat().st_mode)
            try:
                missing_prompt = root / "missing-readonly-carrier-prompt.txt"
                precommit_output = root / "readonly-precommit-generation.json"
                precommit_previous = b"prior precommit generation output\n"
                precommit_output.write_bytes(precommit_previous)
                precommit_companion = precommit_output.with_name(
                    precommit_output.stem + ".references"
                )
                precommit_staging_before = set(
                    root.glob(
                        f".{precommit_output.stem}-generation-package-*"
                    )
                )
                precommit_errors = build_errors(
                            [
                                "--model",
                                MODEL_ID,
                                "--prompt-file",
                                str(missing_prompt),
                                "--negative-file",
                                str(negative_file),
                                "--integrated-prompt-file",
                                str(integrated_file),
                                "--negative-provenance-file",
                                str(provenance_file),
                                "--negative-transport",
                                "auto",
                                "--plot-file",
                                str(plot_file),
                                "--production-spec-file",
                                str(production_spec_file),
                                "--state-lineage-file",
                                str(state_lineage_file),
                                "--references-file",
                                str(root / "prepared-1.json"),
                                "--out",
                                str(precommit_output),
                                *runtime_arguments,
                            ]
                )
                checked(
                    len(precommit_errors) == 1
                    and missing_prompt.name in precommit_errors[0]
                    and precommit_output.read_bytes() == precommit_previous
                    and not precommit_companion.exists()
                    and set(
                        root.glob(
                            f".{precommit_output.stem}-generation-package-*"
                        )
                    )
                    == precommit_staging_before
                    and sha256_file(readonly_carrier) == readonly_source_hash
                    and stat.S_IMODE(readonly_carrier.stat().st_mode)
                    == observed_readonly_mode,
                    "read-only carrier precommit failure masked its original error, "
                    "changed its source/output, or leaked transaction staging",
                )

                postcommit_output = root / "readonly-postcommit-generation.json"
                postcommit_previous = b"prior postcommit generation output\n"
                postcommit_output.write_bytes(postcommit_previous)
                postcommit_companion = postcommit_output.with_name(
                    postcommit_output.stem + ".references"
                )
                postcommit_staging_before = set(
                    root.glob(
                        f".{postcommit_output.stem}-generation-package-*"
                    )
                )
                real_replace = os.replace
                injected_message = "injected post-companion publication failure"
                injected_count = 0
                staged_carriers_writable = False

                def fail_json_publication(source: Any, destination: Any) -> None:
                    nonlocal injected_count, staged_carriers_writable
                    source_path = Path(source)
                    destination_path = Path(destination)
                    if (
                        source_path.name == postcommit_output.name
                        and destination_path.resolve() == postcommit_output.resolve()
                        and source_path.parent.name.startswith(
                            f".{postcommit_output.stem}-generation-package-"
                        )
                    ):
                        injected_count += 1
                        carrier_files = [
                            path
                            for path in postcommit_companion.rglob("*")
                            if path.is_file()
                        ]
                        staged_carriers_writable = bool(carrier_files) and all(
                            stat.S_IMODE(path.stat().st_mode) & stat.S_IWUSR
                            for path in carrier_files
                        )
                        raise OSError(injected_message)
                    real_replace(source, destination)

                with mock.patch.object(
                    generation_builder.os,
                    "replace",
                    side_effect=fail_json_publication,
                ):
                    postcommit_errors = build_errors(
                                [
                                    "--model",
                                    MODEL_ID,
                                    "--prompt-file",
                                    str(prompt_file),
                                    "--negative-file",
                                    str(negative_file),
                                    "--integrated-prompt-file",
                                    str(integrated_file),
                                    "--negative-provenance-file",
                                    str(provenance_file),
                                    "--negative-transport",
                                    "auto",
                                    "--plot-file",
                                    str(plot_file),
                                    "--production-spec-file",
                                    str(production_spec_file),
                                    "--state-lineage-file",
                                    str(state_lineage_file),
                                    "--references-file",
                                    str(root / "prepared-1.json"),
                                    "--out",
                                    str(postcommit_output),
                                    *runtime_arguments,
                                ]
                    )
                checked(
                    postcommit_errors == [injected_message]
                    and injected_count == 1
                    and staged_carriers_writable
                    and postcommit_output.read_bytes() == postcommit_previous
                    and not postcommit_companion.exists()
                    and set(
                        root.glob(
                            f".{postcommit_output.stem}-generation-package-*"
                        )
                    )
                    == postcommit_staging_before
                    and sha256_file(readonly_carrier) == readonly_source_hash
                    and stat.S_IMODE(readonly_carrier.stat().st_mode)
                    == observed_readonly_mode,
                    "read-only carrier postcommit failure was masked, propagated its "
                    "mode, changed its source/output, or leaked transaction staging",
                )

                cleanup_output = root / "readonly-cleanup-failure-generation.json"
                cleanup_companion = cleanup_output.with_name(
                    cleanup_output.stem + ".references"
                )
                cleanup_staging_before = set(
                    root.glob(f".{cleanup_output.stem}-generation-package-*")
                )
                injected_cleanup_message = "injected transaction cleanup failure"
                cleanup_calls: list[Path] = []
                cleanup_stdout = io.StringIO()
                cleanup_error: BaseException | None = None

                def fail_transaction_cleanup(staging: Any) -> None:
                    cleanup_calls.append(Path(staging).resolve())
                    raise OSError(injected_cleanup_message)

                try:
                    with mock.patch.object(
                        generation_builder,
                        "remove_cli_package_staging",
                        side_effect=fail_transaction_cleanup,
                    ):
                        with contextlib.redirect_stdout(cleanup_stdout):
                            build_main(
                                [
                                    "--model",
                                    MODEL_ID,
                                    "--prompt-file",
                                    str(prompt_file),
                                    "--negative-file",
                                    str(negative_file),
                                    "--integrated-prompt-file",
                                    str(integrated_file),
                                    "--negative-provenance-file",
                                    str(provenance_file),
                                    "--negative-transport",
                                    "auto",
                                    "--plot-file",
                                    str(plot_file),
                                    "--production-spec-file",
                                    str(production_spec_file),
                                    "--state-lineage-file",
                                    str(state_lineage_file),
                                    "--references-file",
                                    str(root / "prepared-1.json"),
                                    "--out",
                                    str(cleanup_output),
                                    *runtime_arguments,
                                ]
                            )
                except BaseException as exc:
                    cleanup_error = exc
                cleanup_staging_after = set(
                    root.glob(f".{cleanup_output.stem}-generation-package-*")
                )
                leaked_cleanup_staging = cleanup_staging_after - cleanup_staging_before
                checked(
                    type(cleanup_error) is OSError
                    and str(cleanup_error) == injected_cleanup_message
                    and cleanup_stdout.getvalue() == ""
                    and cleanup_output.is_file()
                    and cleanup_companion.is_dir()
                    and len(cleanup_calls) == 1
                    and leaked_cleanup_staging == set(cleanup_calls),
                    "cleanup failure emitted a false success payload, changed the exact "
                    "error, or concealed its transaction staging",
                )
                for leaked_staging in leaked_cleanup_staging:
                    generation_builder.remove_cli_package_staging(leaked_staging)
            finally:
                os.chmod(readonly_carrier, original_carrier_mode | stat.S_IWUSR)

            moved_package_root = root / "moved-generation-package"
            moved_package_root.mkdir()
            source_package_file = root / "generation-package-2.json"
            source_companion = root / "generation-package-2.references"
            moved_package_file = moved_package_root / source_package_file.name
            moved_companion = moved_package_root / source_companion.name
            shutil.copy2(source_package_file, moved_package_file)
            shutil.copytree(source_companion, moved_companion)
            moved_package = json.loads(moved_package_file.read_text(encoding="utf-8"))
            configure_pack_runtime(settings)
            catalog_cli.clear_runtime_caches()
            moved_verified = verify(moved_package, package_root=moved_package_root)
            checked(
                moved_verified["verified"] is True
                and [
                    row["role"]
                    for row in moved_verified["host_forwarding"]["selected_references"]
                ]
                == ["permanent-identity", "scene-geometry"],
                "moved Generation Package plus companion did not verify",
            )
            checked(
                all(
                    Path(row["resolved_path"]).is_relative_to(moved_companion)
                    for row in moved_verified["host_forwarding"]["selected_references"]
                ),
                "moved Generation Package resolved carriers outside its moved companion",
            )

            checked(
                len({package["generation_input_sha256"] for package in packages}) == 3,
                "0/1/2 references did not produce distinct commitments",
            )
            prepared_mixed = prepared_round_trips[2]["selected_references"]
            packaged_mixed = packages[2]["prepared_reference_set"]["selected_references"]
            checked(
                [row["role"] for row in prepared_mixed]
                == ["permanent-identity", "scene-geometry"],
                "mixed pack/supplied reference order or roles changed",
            )
            checked(
                [row["source"]["kind"] for row in prepared_mixed]
                == ["supplied-file", "supplied-file"],
                "ordered supplied reference sources changed order",
            )
            checked(
                all(
                    row["authority"]["controls"]
                    and row["authority"]["must_not_control"]
                    for row in prepared_mixed
                ),
                "prepared references lost mandatory authority boundaries",
            )
            checked(
                all(
                    sha256_file(Path(row["source"]["resolved_path"]))
                    == row["source"]["sha256"]
                    for row in prepared_mixed
                ),
                "prepared source hashes do not match source bytes",
            )
            checked(
                all(
                    sha256_file(Path(row["transport"]["resolved_path"]))
                    == row["transport"]["sha256"]
                    for row in prepared_mixed
                ),
                "prepared transport hashes do not match model-facing bytes",
            )
            checked(
                all(
                    row["transport"]["media_type"] == "image/png"
                    and row["transport"]["derivation"]["mode"] == "svg-rasterization"
                    and row["transport"]["derivation"]["renderer_id"] == "resvg-py"
                    and row["transport"]["derivation"]["source_sha256"]
                    == row["source"]["sha256"]
                    and Path(row["transport"]["resolved_path"]).read_bytes().startswith(
                        b"\x89PNG\r\n\x1a\n"
                    )
                    for row in prepared_mixed
                ),
                "real SVG rasterization was not committed source-to-PNG",
            )
            host_mixed = verified_round_trips[2]["host_forwarding"]["selected_references"]
            checked(
                all(
                    host == {
                        "role": prepared["role"],
                        "resolved_path": str(
                            (
                                Path(prepared["transport"]["resolved_path"])
                                if Path(prepared["transport"]["resolved_path"]).is_absolute()
                                else root / prepared["transport"]["resolved_path"]
                            ).resolve(strict=True)
                        ),
                        "media_type": prepared["transport"]["media_type"],
                        "sha256": prepared["transport"]["sha256"],
                    }
                    for host, prepared in zip(host_mixed, packaged_mixed, strict=True)
                ),
                "host forwarding did not expose the exact transport-only projection",
            )

            configure_pack_runtime(settings)
            catalog_cli.clear_runtime_caches()
            runtime_plan = build_reference_use_plan(
                [
                    {
                        "record_id": "fixture-generic-subject",
                        "intended_influence": "identity",
                    }
                ],
                transport_mode="multi-image",
                source_lighting_mode="replace",
                target_model=MODEL_ID,
                include_technical_roles=["faithful-archival-vector"],
                light_sources=[
                    {
                        "light_id": "key",
                        "direction": "upper-left front",
                        "apparent_size": "large softbox",
                        "color": "neutral daylight",
                        "relative_intensity": "primary",
                        "softness": "soft",
                    }
                ],
                material_responses=[
                    {
                        "material": "fixture surface",
                        "roughness": "matte",
                        "specular_strength": "low",
                        "highlight_shape": "broad and soft",
                        "wetness": "dry",
                        "anisotropy": "none",
                    }
                ],
            )
            runtime_output = root / "runtime-generation-references"
            runtime_set = execute_reference_use_plan(
                runtime_plan,
                output_dir=runtime_output,
                max_side=128,
            )
            checked(
                runtime_set["reference_use_plan"] == runtime_plan
                and runtime_set["reference_use_plan_sha256"]
                == runtime_plan["reference_use_plan_sha256"]
                and runtime_set["surface_lighting_plan_sha256"]
                == runtime_plan["surface_lighting_plan_sha256"],
                "reference runtime did not embed its complete finalized plan",
            )
            runtime_package_root = root / "runtime-generation-package"
            runtime_package_root.mkdir()
            runtime_packaged_set, runtime_companion = materialize_cli_reference_bundle(
                runtime_set,
                model=MODEL_ID,
                source_root=runtime_output,
                staging_root=runtime_package_root,
                companion_name="runtime-generation-package.references",
            )
            checked(
                runtime_companion is not None and runtime_companion.is_dir(),
                "runtime plan carriers were not materialized into a package companion",
            )
            runtime_package = _package(
                runtime_packaged_set,
                prepared_reference_root=runtime_package_root,
            )
            runtime_verified = verify(runtime_package, package_root=runtime_package_root)
            checked(
                _forwarding_preserves_declared_parts(runtime_verified, PROMPT, len(runtime_set["selected_references"]))
                and len(runtime_verified["host_forwarding"]["selected_references"]) == 1,
                "runtime plan did not reach verified Generation Package host forwarding",
            )

            # A model one service exposes: the request is checked against that
            # service's observed parameter schema, and the offering it goes
            # through is committed in the package for the verifier to check again.
            try:
                _package(
                    empty_stateless_reference_set(),
                    model=OFFERED_MODEL_ID,
                    parameters={"width": 1000, "height": 1000},
                )
            except ValueError as exc:
                checked("refuses this request" in str(exc), f"the wrong refusal for a bad geometry: {exc}")
            else:
                checked(False, "a geometry the observed schema does not accept was packaged")
            offered_package = _package(
                empty_stateless_reference_set(),
                model=OFFERED_MODEL_ID,
                parameters={"width": 1024, "height": 1024},
            )
            checked(
                offered_package["generation_payload"]["service"]
                == {
                    "id": "runware",
                    "model_identifier": "vendor:offered@1",
                    "observed_at": "2026-09-13",
                    "schema_snapshot": OFFERED_SNAPSHOT,
                },
                "the offering the request goes through was not committed in the package",
            )
            checked(
                offered_package["generation_payload"]["parameters"] == {"width": 1024, "height": 1024, "steps": 20},
                "the record's single-valued recommendation was not filled in on the offering's request key",
            )
            chosen = _package(
                empty_stateless_reference_set(),
                model=OFFERED_MODEL_ID,
                parameters={"width": 1024, "height": 1024, "steps": 25},
            )
            checked(
                chosen["generation_payload"]["parameters"]["steps"] == 25,
                "a value the package sets was overwritten by the recommendation",
            )
            verify(offered_package)
            stale_offering = _resign_generation_package(offered_package)
            stale_offering["generation_payload"]["service"]["observed_at"] = "2026-01-01"
            checked(
                _verify_rejected(stale_offering),
                "a package whose committed offering differs from the record was verified",
            )
            extra_parameter = copy.deepcopy(offered_package)
            extra_parameter["generation_payload"]["parameters"]["cfg"] = 7
            checked(
                _verify_rejected(_resign_generation_package(extra_parameter)),
                "a parameter the observed schema does not take was verified",
            )

            # An offering that takes the prepared references as one seed image
            # rather than a list: the one reference goes on that key, and a
            # package that selected two is refused where it is built rather than
            # losing the rest in transit.
            seed_output = root / "seed-image-references"
            seed_set = prepare_references(
                [supplied_identity_selection],
                model=SEED_MODEL_ID,
                output_dir=seed_output,
                max_side=128,
            )
            seed_package_root = root / "seed-image-generation-package"
            seed_package_root.mkdir()
            seed_packaged_set, seed_companion = materialize_cli_reference_bundle(
                seed_set,
                model=SEED_MODEL_ID,
                source_root=seed_output,
                staging_root=seed_package_root,
                companion_name="seed-image-generation-package.references",
            )
            seed_package = _package(
                seed_packaged_set,
                model=SEED_MODEL_ID,
                parameters={"width": 1024, "height": 1024},
                prepared_reference_root=seed_package_root,
            )
            seed_verified = verify(seed_package, package_root=seed_package_root)
            checked(
                seed_companion is not None
                and seed_verified["verified"] is True
                and seed_package["generation_payload"]["service"]["model_identifier"]
                == "vendor:seeded@1"
                and len(seed_verified["host_forwarding"]["selected_references"]) == 1,
                "an offering that takes one seed image did not package and verify its one reference",
            )

            seed_pair_output = root / "seed-image-pair-references"
            seed_pair_set = prepare_references(
                [supplied_identity_selection, supplied_selection],
                model=SEED_MODEL_ID,
                output_dir=seed_pair_output,
                max_side=128,
            )
            seed_pair_package_root = root / "seed-image-pair-generation-package"
            seed_pair_package_root.mkdir()
            seed_pair_packaged_set, _ = materialize_cli_reference_bundle(
                seed_pair_set,
                model=SEED_MODEL_ID,
                source_root=seed_pair_output,
                staging_root=seed_pair_package_root,
                companion_name="seed-image-pair-generation-package.references",
            )
            try:
                _package(
                    seed_pair_packaged_set,
                    model=SEED_MODEL_ID,
                    parameters={"width": 1024, "height": 1024},
                    prepared_reference_root=seed_pair_package_root,
                )
            except ValueError as exc:
                checked(
                    "one image" in str(exc),
                    f"the wrong refusal for two references on a seed image: {exc}",
                )
            else:
                checked(False, "an offering that takes one seed image packaged two references")

            altered_prompt_artifact = runtime_output / "altered-reference.svg"
            altered_prompt_artifact.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64">
  <rect width="96" height="64" fill="#ff00ff"/>
</svg>
""",
                encoding="utf-8",
                newline="\n",
            )
            mismatched_prompt_artifact_set = copy.deepcopy(runtime_set)
            mismatched_artifact = mismatched_prompt_artifact_set["prompt_artifacts"][0]
            mismatched_artifact["delivered_path"] = altered_prompt_artifact.name
            mismatched_artifact["delivered_sha256"] = sha256_file(altered_prompt_artifact)
            mismatched_prompt_artifact_set = finalize_artifact(
                mismatched_prompt_artifact_set
            )
            try:
                validate_prepared_reference_set(
                    mismatched_prompt_artifact_set,
                    model=MODEL_ID,
                    package_root=runtime_output,
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure(
                    "prepared set accepted prompt-artifact bytes unrelated to their source"
                )
            checked(True, "prompt-artifact source-byte rejection was not reached")

            forged_plan = copy.deepcopy(runtime_plan)
            forged_plan["reference_items"][0]["authority"]["controls"].append(
                "undeclared source-scene authority"
            )
            forged_plan = finalize_artifact(forged_plan)
            try:
                build_prepared_reference_set(
                    transport_mode="multi-image",
                    target_model=MODEL_ID,
                    selected_references=runtime_set["selected_references"],
                    reference_use_plan=forged_plan,
                    prompt_artifacts=runtime_set["prompt_artifacts"],
                    package_root=runtime_output,
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure("prepared set accepted a forged rehashed plan authority")
            checked(True, "forged reference-use-plan rejection was not reached")

            unlinked_plan = copy.deepcopy(runtime_plan)
            unlinked_plan["selected_records"][0]["record_id"] = (
                "fixture-unlinked-subject"
            )
            unlinked_plan["reference_items"][0]["canonical_record_id"] = (
                "fixture-unlinked-subject"
            )
            unlinked_plan = finalize_artifact(unlinked_plan)
            try:
                build_prepared_reference_set(
                    transport_mode="multi-image",
                    target_model=MODEL_ID,
                    selected_references=runtime_set["selected_references"],
                    reference_use_plan=unlinked_plan,
                    prompt_artifacts=runtime_set["prompt_artifacts"],
                    package_root=runtime_output,
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure(
                    "prepared set accepted a re-signed active record-to-asset link forgery"
                )
            checked(True, "active record-to-asset link forgery rejection was not reached")

            semantic_plan = copy.deepcopy(runtime_plan)
            semantic_plan["selected_records"][0]["intended_influence"] = "outfit"
            original_item = semantic_plan["reference_items"][0]
            semantic_plan["reference_items"][0] = build_reference_item(
                precedence=0,
                canonical_record_id="fixture-generic-subject",
                intended_influence="outfit",
                asset_id=original_item["asset_id"],
                artifact_id=original_item["artifact_id"],
                technical_role=original_item["technical_role"],
                source=original_item["source"],
            )
            semantic_plan = finalize_artifact(semantic_plan)
            try:
                build_prepared_reference_set(
                    transport_mode="multi-image",
                    target_model=MODEL_ID,
                    selected_references=runtime_set["selected_references"],
                    reference_use_plan=semantic_plan,
                    prompt_artifacts=runtime_set["prompt_artifacts"],
                    package_root=runtime_output,
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure(
                    "prepared set accepted a re-signed unsupported semantic influence"
                )
            checked(True, "active record semantic-scope forgery rejection was not reached")

            configure_pack_runtime(settings)
            board_path = Path(prepared_mixed[0]["transport"]["resolved_path"])
            board = {
                "resolved_path": str(board_path),
                "media_type": "image/png",
                "sha256": sha256_file(board_path),
                "panels": [
                    {
                        "semantic_role": row["role"],
                        "source_sha256": row["source"]["sha256"],
                        "transport_sha256": row["transport"]["sha256"],
                        "box": {"x": index, "y": 0, "width": 1, "height": 1},
                    }
                    for index, row in enumerate(prepared_mixed)
                ],
            }
            single_board_set = build_prepared_reference_set(
                transport_mode="single-board",
                target_model=MODEL_ID,
                selected_references=prepared_mixed,
                single_board=board,
            )
            single_board_package_root = root / "single-board-generation-package"
            single_board_package_root.mkdir()
            single_board_packaged_set, single_board_companion = (
                materialize_cli_reference_bundle(
                    single_board_set,
                    model=MODEL_ID,
                    source_root=root,
                    staging_root=single_board_package_root,
                    companion_name="single-board-generation-package.references",
                )
            )
            checked(
                single_board_companion is not None
                and single_board_companion.is_dir(),
                "single-board carriers were not staged under one companion",
            )
            single_board_package = _package(
                single_board_packaged_set,
                prepared_reference_root=single_board_package_root,
            )
            single_board_verified = verify(
                single_board_package,
                package_root=single_board_package_root,
            )
            packaged_board_path = (
                single_board_package_root
                / single_board_packaged_set["single_board"]["resolved_path"]
            ).resolve(strict=True)
            checked(
                len(single_board_verified["host_forwarding"]["selected_references"]) == 1
                and single_board_verified["host_forwarding"]["selected_references"][0]
                == {
                    "role": "composite-reference-board",
                    "resolved_path": str(packaged_board_path),
                    "media_type": "image/png",
                    "sha256": sha256_file(board_path),
                },
                "single-board verification forwarded panel rows instead of only the board",
            )
            absolute_board_package = copy.deepcopy(single_board_package)
            absolute_board_package["prepared_reference_set"]["single_board"][
                "resolved_path"
            ] = str(packaged_board_path)
            absolute_board_package = _resign_generation_package(
                absolute_board_package
            )
            checked(
                _verify_rejected(
                    absolute_board_package,
                    package_root=single_board_package_root,
                ),
                "verifier accepted a re-signed absolute single-board carrier path",
            )
            mutation_count += 1
            try:
                build_prepared_reference_set(
                    transport_mode="multi-image",
                    target_model=MODEL_ID,
                    selected_references=prepared_mixed,
                    reference_preamble=(
                        "Use the same prepared bytes under an arbitrary instruction.\n"
                    ),
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure("prepared set accepted a noncanonical reference preamble")
            checked(True, "noncanonical reference-preamble rejection was not reached")
            resigned_preamble = copy.deepcopy(packages[2])
            resigned_preamble["prepared_reference_set"]["reference_preamble"] = (
                "Arbitrary instruction that is unrelated to committed row authority.\n"
            )
            resigned_preamble["prepared_reference_set"] = finalize_artifact(
                resigned_preamble["prepared_reference_set"]
            )
            resigned_preamble_hash = resigned_preamble["prepared_reference_set"][
                "prepared_reference_set_sha256"
            ]
            resigned_preamble["prepared_reference_set_sha256"] = resigned_preamble_hash
            resigned_preamble["generation_contract"][
                "prepared_reference_set_sha256"
            ] = resigned_preamble_hash
            resigned_preamble_commitment = generation_input_sha256(resigned_preamble)
            resigned_preamble["generation_input_sha256"] = resigned_preamble_commitment
            resigned_preamble["generation_contract"][
                "generation_input_sha256"
            ] = resigned_preamble_commitment
            checked(
                _verify_rejected(resigned_preamble, package_root=root),
                "verifier accepted a resigned noncanonical reference preamble",
            )
            mutation_count += 1

            try:
                build_prepared_reference_set(
                    transport_mode="prompt-artifacts",
                    target_model=None,
                    reference_preamble="Use this prompt artifact only as declared.\n",
                    prompt_artifacts=[
                        {
                            "semantic_role": "identity-appearance",
                            "source_sha256": sha256_file(pack_svg),
                            "delivered_path": str(pack_svg.resolve(strict=True)),
                            "media_type": "image/svg+xml",
                            "delivered_sha256": sha256_file(pack_svg),
                        }
                    ],
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure("prompt-artifacts accepted a plan-null authority boundary")
            checked(True, "plan-null prompt-artifacts rejection was not reached")

            resigned_planless_pack = copy.deepcopy(prepared_round_trips[1])
            resigned_planless_pack["selected_references"][0]["source"] = (
                copy.deepcopy(selected_pack[0]["source"])
            )
            resigned_planless_pack = finalize_artifact(resigned_planless_pack)
            schema_rejected_planless_pack = not validate_artifact(
                resigned_planless_pack
            ).get("ok")
            try:
                validate_prepared_reference_set(
                    resigned_planless_pack,
                    model=MODEL_ID,
                )
            except ValueError:
                validator_rejected_planless_pack = True
            else:
                validator_rejected_planless_pack = False
            checked(
                schema_rejected_planless_pack and validator_rejected_planless_pack,
                "schema or validator accepted a re-signed plan-null pack artifact",
            )

            relative_root = root / "relative-generation-package"
            relative_root.mkdir()
            relative_companion = relative_root / "relative-generation-package.references"
            relative_companion.mkdir()
            relative_transport = relative_companion / "reference.png"
            shutil.copy2(
                prepared_mixed[0]["transport"]["resolved_path"],
                relative_transport,
            )
            relative_row = copy.deepcopy(prepared_mixed[0])
            relative_row["transport"]["resolved_path"] = (
                "relative-generation-package.references/reference.png"
            )
            relative_set = build_prepared_reference_set(
                transport_mode="multi-image",
                target_model=MODEL_ID,
                selected_references=[relative_row],
                package_root=relative_root,
            )
            relative_package = _package(
                relative_set,
                prepared_reference_root=relative_root,
            )
            try:
                verify(relative_package)
            except ValueError as exc:
                checked(
                    "requires package_root" in str(exc),
                    "relative transport failed without a clear package_root error",
                )
            else:
                raise SmokeFailure("relative transport verified without package_root")
            relative_verified = verify(relative_package, package_root=relative_root)
            checked(
                relative_verified["host_forwarding"]["selected_references"][0][
                    "resolved_path"
                ]
                == str(relative_transport.resolve(strict=True)),
                "relative transport did not resolve under the actual package root",
            )

            configure_pack_runtime(settings)
            base = packages[2]
            checked(
                verify(base, package_root=root)["verified"] is True,
                "committed mixed package did not reverify",
            )

            selected_carrier = base["prepared_reference_set"][
                "selected_references"
            ][0]["transport"]["resolved_path"]
            absolute_selected_carrier = (root / selected_carrier).resolve(strict=True)
            absolute_carrier_package = copy.deepcopy(base)
            absolute_carrier_package["prepared_reference_set"][
                "selected_references"
            ][0]["transport"]["resolved_path"] = str(absolute_selected_carrier)
            absolute_carrier_package = _resign_generation_package(
                absolute_carrier_package
            )
            checked(
                _verify_rejected(absolute_carrier_package, package_root=root),
                "verifier accepted a re-signed absolute selected-reference carrier",
            )
            mutation_count += 1

            outside_carrier = root / "outside-reference.png"
            shutil.copy2(absolute_selected_carrier, outside_carrier)
            outside_carrier_package = copy.deepcopy(base)
            outside_carrier_package["prepared_reference_set"][
                "selected_references"
            ][0]["transport"]["resolved_path"] = outside_carrier.name
            outside_carrier_package = _resign_generation_package(
                outside_carrier_package
            )
            checked(
                _verify_rejected(outside_carrier_package, package_root=root),
                "verifier accepted a re-signed carrier outside its companion",
            )
            mutation_count += 1

            checked(
                len(runtime_packaged_set["prompt_artifacts"]) == 1,
                "runtime package did not preserve its one prompt artifact",
            )
            prompt_artifact_path = (
                runtime_package_root
                / runtime_packaged_set["prompt_artifacts"][0]["delivered_path"]
            ).resolve(strict=True)
            absolute_prompt_artifact_package = copy.deepcopy(runtime_package)
            absolute_prompt_artifact_package["prepared_reference_set"][
                "prompt_artifacts"
            ][0]["delivered_path"] = str(prompt_artifact_path)
            absolute_prompt_artifact_package = _resign_generation_package(
                absolute_prompt_artifact_package
            )
            checked(
                _verify_rejected(
                    absolute_prompt_artifact_package,
                    package_root=runtime_package_root,
                ),
                "verifier accepted a re-signed absolute prompt-artifact carrier",
            )
            mutation_count += 1

            distinctive_detail_spec = _production_spec(MODEL_ID)
            distinctive_detail_spec["subjects"][0]["distinctive_details"] = [
                copy.deepcopy(GENERIC_DISTINCTIVE_DETAIL)
            ]
            distinctive_detail_report = validate_production_spec(
                distinctive_detail_spec,
                require_content=True,
            )
            checked(
                distinctive_detail_report["ok"] is True
                and distinctive_detail_report["errors"] == [],
                "complete generic distinctive-detail fixture is not valid before mutation",
            )

            invalid_laterality_spec = copy.deepcopy(distinctive_detail_spec)
            invalid_laterality_spec["subjects"][0]["distinctive_details"][0][
                "laterality"
            ] = "viewer-left"
            invalid_laterality_report = validate_production_spec(
                invalid_laterality_spec,
                require_content=True,
            )
            expected_laterality_errors = [
                (
                    "$.subjects[0].distinctive_details[0].laterality: value "
                    "'viewer-left' is not in ['left', 'right', 'bilateral', "
                    "'centerline', 'distributed', 'variable']"
                ),
            ]
            checked(
                invalid_laterality_report["ok"] is False
                and invalid_laterality_report["errors"] == expected_laterality_errors,
                "viewer-relative distinctive-detail laterality did not produce the exact contract errors",
            )

            unexpected_subject_spec = copy.deepcopy(distinctive_detail_spec)
            unexpected_subject_spec["subjects"][0][
                "fixture_unexpected_subject_field"
            ] = True
            unexpected_subject_report = validate_production_spec(
                unexpected_subject_spec,
                require_content=True,
            )
            checked(
                unexpected_subject_report["ok"] is False
                and unexpected_subject_report["errors"]
                == [
                    "$.subjects[0]: unexpected properties "
                    "['fixture_unexpected_subject_field']",
                ],
                "unexpected production subject field was not reported exactly once by the subject contract",
            )

            try:
                _package(
                    empty_stateless_reference_set(),
                    production_spec_override=invalid_laterality_spec,
                    negative_transport="separate-field",
                )
            except production_spec.SpecificationError as exc:
                invalid_laterality_build_errors = exc.errors
            else:
                invalid_laterality_build_errors = []
            checked(
                invalid_laterality_build_errors
                == ["production specification: " + error for error in expected_laterality_errors],
                "build_payload accepted or misreported invalid distinctive-detail laterality",
            )

            unexpected_property_spec = copy.deepcopy(distinctive_detail_spec)
            unexpected_property_spec["unsupported_property"] = "not part of this contract"
            unexpected_property_report = validate_production_spec(
                unexpected_property_spec,
                require_content=True,
            )
            checked(
                unexpected_property_report["ok"] is False
                and unexpected_property_report["errors"]
                == ["$: unexpected properties ['unsupported_property']"],
                "unsupported production property did not produce current schema errors",
            )

            invalid_production_cases: list[tuple[str, Callable[[], dict[str, Any]]]] = [
                (
                    "empty production specification",
                    lambda: _package(
                        empty_stateless_reference_set(), production_spec_override={}
                    ),
                ),
                (
                    "package/production model mismatch",
                    lambda: _package(
                        empty_stateless_reference_set(),
                        production_target_model=JPEG_ONLY_MODEL_ID,
                    ),
                ),
                (
                    "non-finite generation parameter",
                    lambda: _package(
                        empty_stateless_reference_set(),
                        parameters={"guidance": float("nan")},
                    ),
                ),
            ]
            invalid_id_spec = _production_spec(MODEL_ID)
            invalid_id_spec["subjects"][0]["id"] = 7
            invalid_production_cases.append(
                (
                    "non-string production subject ID",
                    lambda: _package(
                        empty_stateless_reference_set(),
                        production_spec_override=invalid_id_spec,
                    ),
                )
            )
            for name, operation in invalid_production_cases:
                try:
                    operation()
                except (ValueError, TypeError):
                    pass
                else:
                    raise SmokeFailure(f"builder accepted {name}")
                checked(True, f"builder rejection was not reached: {name}")

            try:
                _package([])
            except (ValueError, TypeError):
                pass
            else:
                raise SmokeFailure("builder accepted a non-object prepared-reference set")
            checked(True, "non-object prepared-reference-set rejection was not reached")

            incomplete_reference_set = {
                "artifact_type": "prepared-reference-set",
            }
            try:
                _package(incomplete_reference_set)
            except (ValueError, TypeError):
                pass
            else:
                raise SmokeFailure("builder accepted an incomplete prepared-reference set")
            checked(True, "incomplete prepared-reference-set rejection was not reached")

            non_finite_package = copy.deepcopy(base)
            non_finite_package["generation_payload"]["parameters"]["guidance"] = float("inf")
            checked(
                _verify_rejected(non_finite_package, package_root=root),
                "verifier accepted a non-finite committed parameter",
            )
            mutation_count += 1

            mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
                ("model", lambda value: value.__setitem__("model", JPEG_ONLY_MODEL_ID)),
                (
                    "parameters",
                    lambda value: value["generation_payload"]["parameters"].__setitem__(
                        "quality", "low"
                    ),
                ),
                (
                    "prompt",
                    lambda value: value["generation_payload"].__setitem__(
                        "prompt", value["generation_payload"]["prompt"] + " changed"
                    ),
                ),
                (
                    "negative prompt",
                    lambda value: value["generation_payload"].__setitem__(
                        "negative_prompt",
                        value["generation_payload"]["negative_prompt"] + ", changed",
                    ),
                ),
                (
                    "negative provenance",
                    lambda value: value["generation_payload"]["negative_provenance"][
                        "activated_sources"
                    ].append("changed-source"),
                ),
                (
                    "reference role",
                    lambda value: value["prepared_reference_set"]["selected_references"][0].__setitem__(
                        "role", "changed-role"
                    ),
                ),
                (
                    "spoofed pack",
                    lambda value: value["prepared_reference_set"]["selected_references"][0][
                        "source"
                    ].__setitem__("pack_id", SPOOFED_PACK_ID),
                ),
                (
                    "source hash",
                    lambda value: value["prepared_reference_set"]["selected_references"][0][
                        "source"
                    ].__setitem__("sha256", "f" * 64),
                ),
                (
                    "transport hash",
                    lambda value: value["prepared_reference_set"]["selected_references"][0][
                        "transport"
                    ].__setitem__("sha256", "e" * 64),
                ),
                (
                    "reference order",
                    lambda value: value["prepared_reference_set"].__setitem__(
                        "selected_references",
                        list(reversed(value["prepared_reference_set"]["selected_references"])),
                    ),
                ),
                (
                    "reference authority",
                    lambda value: value["prepared_reference_set"]["selected_references"][0][
                        "authority"
                    ]["controls"].append("undeclared changed authority"),
                ),
                (
                    "prepared reference-set commitment",
                    lambda value: value.__setitem__("prepared_reference_set_sha256", "c" * 64),
                ),
                (
                    "undeclared top-level reference metadata",
                    lambda value: value.__setitem__("unexpected_reference_scope", None),
                ),
                (
                    "arbitrary top-level reference alias",
                    lambda value: value.__setitem__(
                        "references",
                        copy.deepcopy(value["prepared_reference_set"]["selected_references"]),
                    ),
                ),
                (
                    "arbitrary payload reference alias",
                    lambda value: value["generation_payload"].__setitem__(
                        "reference_use_plan",
                        value["prepared_reference_set"]["reference_use_plan"],
                    ),
                ),
                (
                    "generation commitment",
                    lambda value: value.__setitem__("generation_input_sha256", "d" * 64),
                ),
            ]
            for name, mutate in mutations:
                candidate = copy.deepcopy(base)
                mutate(candidate)
                checked(
                    _verify_rejected(candidate, package_root=root),
                    f"committed mutation was accepted: {name}",
                )
                mutation_count += 1

            original_source = pack_svg.read_bytes()
            try:
                pack_svg.write_bytes(original_source + b"changed-source")
                checked(
                    _verify_rejected(base, package_root=root),
                    "changed committed source bytes were accepted",
                )
                mutation_count += 1
            finally:
                pack_svg.write_bytes(original_source)
            checked(
                verify(base, package_root=root)["verified"] is True,
                "source restoration did not restore verification",
            )

            transport_png = (
                root / packaged_mixed[0]["transport"]["resolved_path"]
            ).resolve(strict=True)
            original_png = transport_png.read_bytes()
            try:
                transport_png.write_bytes(original_png + b"changed-transport")
                checked(
                    _verify_rejected(base, package_root=root),
                    "changed committed PNG bytes were accepted",
                )
                mutation_count += 1
            finally:
                transport_png.write_bytes(original_png)
            checked(
                verify(base, package_root=root)["verified"] is True,
                "PNG restoration did not restore verification",
            )

            replacement_svg = root / "replacement.svg"
            replacement_svg.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64" viewBox="0 0 96 64">
  <rect width="96" height="64" fill="#ff00ff"/>
</svg>
""",
                encoding="utf-8",
                newline="\n",
            )
            original_png = transport_png.read_bytes()
            try:
                dimensions = prepared_mixed[0]["transport"]["derivation"]["output_dimensions"]
                render_svg(
                    replacement_svg,
                    transport_png,
                    width=dimensions["width"],
                    height=dimensions["height"],
                )
                resigned_replacement = copy.deepcopy(base)
                replacement_transport = resigned_replacement["prepared_reference_set"][
                    "selected_references"
                ][0]["transport"]
                replacement_transport["sha256"] = sha256_file(transport_png)
                resigned_replacement["prepared_reference_set"] = finalize_artifact(
                    resigned_replacement["prepared_reference_set"]
                )
                resigned_set_hash = resigned_replacement["prepared_reference_set"][
                    "prepared_reference_set_sha256"
                ]
                resigned_replacement["prepared_reference_set_sha256"] = resigned_set_hash
                resigned_replacement["generation_contract"][
                    "prepared_reference_set_sha256"
                ] = resigned_set_hash
                replacement_commitment = generation_input_sha256(resigned_replacement)
                resigned_replacement["generation_input_sha256"] = replacement_commitment
                resigned_replacement["generation_contract"][
                    "generation_input_sha256"
                ] = replacement_commitment
                checked(
                    _verify_rejected(resigned_replacement, package_root=root),
                    "resigned arbitrary PNG replacement was accepted as an SVG derivation",
                )
                mutation_count += 1
            finally:
                transport_png.write_bytes(original_png)
            checked(
                verify(base, package_root=root)["verified"] is True,
                "deterministic PNG restoration did not restore verification",
            )

            def expect_prepare_failure(
                name: str,
                selections: list[dict[str, Any]],
                *,
                model: str = MODEL_ID,
            ) -> None:
                output_dir = root / f"failure-{name}"
                staging_before = set(root.glob(f".{output_dir.name}-prepare-*"))
                try:
                    prepare_references(
                        selections,
                        model=model,
                        output_dir=output_dir,
                        max_side=128,
                    )
                except (ValueError, OSError, RuntimeError):
                    pass
                else:
                    raise SmokeFailure(f"reference preparation accepted {name}")
                checked(not output_dir.exists(), f"failed {name} preparation wrote an output directory")
                checked(
                    set(root.glob(f".{output_dir.name}-prepare-*")) == staging_before,
                    f"failed {name} preparation left staging output",
                )

            spoofed_selection = copy.deepcopy(selected_pack[0])
            spoofed_selection["source"]["pack_id"] = SPOOFED_PACK_ID
            expect_prepare_failure("planless-pack-artifact", [selected_pack[0]])
            expect_prepare_failure("spoofed-pack", [spoofed_selection])

            changed_source_selection = copy.deepcopy(selected_pack[0])
            changed_source_selection["source"]["sha256"] = "f" * 64
            expect_prepare_failure("changed-source", [changed_source_selection])

            invalid_role_selection = copy.deepcopy(selected_pack[0])
            invalid_role_selection["role"] = "invalid role with spaces"
            expect_prepare_failure("invalid-role", [invalid_role_selection])

            unsafe_svg = root / "unsafe.svg"
            unsafe_svg.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">
  <script>alert('unsafe')</script><rect width="32" height="32"/>
</svg>
""",
                encoding="utf-8",
                newline="\n",
            )
            unsafe_selection = {
                "role": "unsafe-reference",
                "source": {
                    "kind": "supplied-file",
                    "reference_id": "unsafe-svg",
                    "resolved_path": str(unsafe_svg.resolve(strict=True)),
                },
            }
            expect_prepare_failure("unsafe-svg", [unsafe_selection])

            unsupported_source = root / "unsupported.gif"
            unsupported_source.write_bytes(b"GIF89a\x01\x00\x01\x00")
            unsupported_selection = {
                "role": "unsupported-source",
                "source": {
                    "kind": "supplied-file",
                    "reference_id": "unsupported-gif",
                    "resolved_path": str(unsupported_source.resolve(strict=True)),
                },
            }
            expect_prepare_failure("unsupported-source", [unsupported_selection])

            direct_png_selection = {
                "role": "unsupported-media",
                "source": {
                    "kind": "supplied-file",
                    "reference_id": "prepared-png",
                    "resolved_path": str(transport_png.resolve(strict=True)),
                },
            }
            expect_prepare_failure(
                "unsupported-media", [direct_png_selection], model=JPEG_ONLY_MODEL_ID
            )
            expect_prepare_failure("unknown-model", [selected_pack[0]], model="unknown-model")
            expect_prepare_failure(
                "model-missing-media", [selected_pack[0]], model=NO_MEDIA_MODEL_ID
            )

            nonempty_dir = root / "nonempty-output"
            nonempty_dir.mkdir()
            sentinel = nonempty_dir / "sentinel.txt"
            sentinel.write_text("do-not-replace", encoding="utf-8")
            try:
                prepare_references(
                    [selected_pack[0]],
                    model=MODEL_ID,
                    output_dir=nonempty_dir,
                    max_side=128,
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure("reference preparation accepted a non-empty output directory")
            checked(
                sentinel.read_text(encoding="utf-8") == "do-not-replace"
                and sorted(path.name for path in nonempty_dir.iterdir()) == ["sentinel.txt"],
                "non-empty output directory was modified",
            )

            configure_pack_runtime(None)
            invalid_selection_file = root / "invalid-selection.json"
            invalid_prepare_json = root / "invalid-prepared.json"
            invalid_prepare_dir = root / "invalid-prepared-transports"
            _write_json(invalid_selection_file, [invalid_role_selection])
            with contextlib.redirect_stdout(io.StringIO()):
                invalid_prepare_exit = prepare_main(
                    [
                        "--supplied-selection-file",
                        str(invalid_selection_file),
                        "--model",
                        MODEL_ID,
                        "--output-dir",
                        str(invalid_prepare_dir),
                        "--out",
                        str(invalid_prepare_json),
                        *runtime_arguments,
                    ]
                )
            checked(invalid_prepare_exit == 1, "prepare CLI accepted an invalid role")
            checked(
                not invalid_prepare_json.exists() and not invalid_prepare_dir.exists(),
                "failed prepare CLI wrote output",
            )

            missing_integrated_output = root / "missing-integrated-package.json"
            missing_integrated_companion = root / "missing-integrated-package.references"
            failed_build_staging_before = set(
                root.glob(".missing-integrated-package-generation-package-*")
            )
            if not build_errors(
                        [
                            "--model",
                            MODEL_ID,
                            "--prompt-file",
                            str(prompt_file),
                            "--negative-file",
                            str(negative_file),
                            "--plot-file",
                            str(plot_file),
                            "--production-spec-file",
                            str(production_spec_file),
                            "--state-lineage-file",
                            str(state_lineage_file),
                            "--references-file",
                            str(root / "prepared-1.json"),
                            "--out",
                            str(missing_integrated_output),
                            *runtime_arguments,
                        ]
            ):
                raise SmokeFailure(
                    "builder accepted a negative without affirmative integrated rendition"
                )
            checked(
                not missing_integrated_output.exists()
                and not missing_integrated_companion.exists()
                and set(root.glob(".missing-integrated-package-generation-package-*"))
                == failed_build_staging_before,
                "failed negative-transport build left JSON, companion, or staging output",
            )

            conflicting_output = root / "conflicting-package.json"
            conflicting_output.write_text("sentinel", encoding="utf-8")
            conflicting_companion = root / "conflicting-package.references"
            conflicting_companion.mkdir()
            conflicting_marker = conflicting_companion / "sentinel.txt"
            conflicting_marker.write_text("keep", encoding="utf-8")
            conflict_staging_before = set(
                root.glob(".conflicting-package-generation-package-*")
            )
            if not build_errors(
                        [
                            "--model",
                            MODEL_ID,
                            "--prompt-file",
                            str(prompt_file),
                            "--negative-file",
                            str(negative_file),
                            "--integrated-prompt-file",
                            str(integrated_file),
                            "--plot-file",
                            str(plot_file),
                            "--production-spec-file",
                            str(production_spec_file),
                            "--state-lineage-file",
                            str(state_lineage_file),
                            "--references-file",
                            str(root / "prepared-1.json"),
                            "--out",
                            str(conflicting_output),
                            *runtime_arguments,
                        ]
            ):
                raise SmokeFailure("builder replaced a pre-existing companion directory")
            checked(
                conflicting_output.read_text(encoding="utf-8") == "sentinel"
                and conflicting_marker.read_text(encoding="utf-8") == "keep"
                and set(root.glob(".conflicting-package-generation-package-*"))
                == conflict_staging_before,
                "companion conflict changed existing output or left staging residue",
            )

            configure_pack_runtime(settings)
            try:
                _package(
                    empty_stateless_reference_set(),
                    model="unknown-auto-model",
                    negative_transport="auto",
                )
            except ValueError:
                pass
            else:
                raise SmokeFailure("automatic negative transport accepted an unknown model")
            checked(True, "unknown auto model rejection was not reached")

            native_negative_file = root / "native-negative.txt"
            native_negative_file.write_text(
                NATIVE_NEGATIVE + "\n", encoding="utf-8", newline="\n"
            )
            native_production_spec_file = root / "native-production-specification.json"
            _write_json(
                native_production_spec_file,
                _production_spec(NATIVE_MODEL_ID),
            )
            native_package_file = root / "native-generation-package.json"
            with contextlib.redirect_stdout(io.StringIO()):
                native_build_exit = build_main(
                    [
                        "--model",
                        NATIVE_MODEL_ID,
                        "--prompt-file",
                        str(prompt_file),
                        "--negative-file",
                        str(negative_file),
                        "--integrated-prompt-file",
                        str(integrated_file),
                        "--native-negative-file",
                        str(native_negative_file),
                        "--negative-provenance-file",
                        str(provenance_file),
                        "--negative-transport",
                        "auto",
                        "--plot-file",
                        str(plot_file),
                        "--production-spec-file",
                        str(native_production_spec_file),
                        "--state-lineage-file",
                        str(state_lineage_file),
                        "--brief",
                        "Exact native-subset negative transport round trip.",
                        "--references-file",
                        str(root / "prepared-0.json"),
                        "--parameters",
                        json.dumps({"size": "1024x1024", "quality": "high"}),
                        "--out",
                        str(native_package_file),
                        *runtime_arguments,
                    ]
                )
            checked(
                native_build_exit == 0 and native_package_file.is_file(),
                "native-subset CLI build failed",
            )
            native_package = json.loads(native_package_file.read_text(encoding="utf-8"))
            native_payload = native_package["generation_payload"]
            native_declaration = native_payload["negative_transport"]
            native_rendition = native_payload["transports"]["native_subset"]
            checked(
                native_declaration
                == {
                    "mode": "native-subset",
                    "channel": "prompt_plus_native_negative",
                    "instruction": generation_builder.transport_instruction("native-subset"),
                    "critical_avoidance_integrated": True,
                    "send_full_negative_verbatim": False,
                    "send_native_negative_verbatim": True,
                }
                and native_payload["negative_prompt"] == NEGATIVE
                and native_payload["native_negative"] == NATIVE_NEGATIVE
                and native_payload["native_negative_sha256"]
                == generation_builder.sha256_text(NATIVE_NEGATIVE)
                and native_rendition
                == {
                    "available": True,
                    "channel": "prompt_plus_native_negative",
                    "method": "verbatim-native-subset",
                    "prompt": PROMPT,
                    "negative": NATIVE_NEGATIVE,
                    "prompt_sha256": generation_builder.sha256_text(PROMPT),
                    "negative_sha256": generation_builder.sha256_text(NATIVE_NEGATIVE),
                },
                "native-subset build did not commit the exact portable and native renditions",
            )

            native_verified_file = root / "native-verified.json"
            with contextlib.redirect_stdout(io.StringIO()):
                native_verify_exit = verify_main(
                    [
                        str(native_package_file),
                        "--target",
                        NATIVE_MODEL_ID,
                        "--payload-out",
                        str(native_verified_file),
                        *runtime_arguments,
                    ]
                )
            checked(
                native_verify_exit == 0 and native_verified_file.is_file(),
                "native-subset CLI verification failed",
            )
            configure_pack_runtime(settings)
            catalog_cli.clear_runtime_caches()
            native_verified = json.loads(native_verified_file.read_text(encoding="utf-8"))
            checked(
                native_verified["verified"] is True
                and native_verified["negative_transport_mode"] == "native-subset"
                and native_verified["native_negative"] == NATIVE_NEGATIVE
                and native_verified["negative_prompt"] == NEGATIVE
                and native_verified["selected_transport"]["rendition"] == native_rendition
                and native_verified["host_forwarding"]["effective_prompt"] == PROMPT
                and native_verified["negative_provenance"] == NEGATIVE_PROVENANCE,
                "native-subset verification changed its selected rendition or provenance",
            )
            native_export = emit_paste_for_target(
                native_package,
                NATIVE_MODEL_ID,
                package_root=root,
            )
            checked(
                native_verified["paste"] == native_export
                and set(native_export)
                == {
                    "target",
                    "mode",
                    "channel",
                    "instruction",
                    "parameters",
                    "selected_references",
                    "reference_preamble",
                    "generation_input_sha256",
                    "paste_prompt",
                    "paste_prompt_sha256",
                    "native_negative",
                }
                and native_export["target"] == NATIVE_MODEL_ID
                and native_export["mode"] == "native-subset"
                and native_export["channel"] == "prompt_plus_native_negative"
                and native_export["paste_prompt"] == PROMPT
                and native_export["paste_prompt_sha256"]
                == generation_builder.sha256_text(PROMPT)
                and native_export["native_negative"] == NATIVE_NEGATIVE
                and native_export["selected_references"] == []
                and native_export["reference_preamble"] == "",
                "native-subset export reconstructed text or exposed the portable negative field",
            )

            configure_pack_runtime(settings)
            catalog_cli.clear_runtime_caches()
            integrated_package = _package(
                empty_stateless_reference_set(),
                model=INTEGRATED_MODEL_ID,
                production_target_model=INTEGRATED_MODEL_ID,
            )
            integrated_payload = integrated_package["generation_payload"]
            integrated_declaration = integrated_payload["negative_transport"]
            integrated_rendition = integrated_payload["transports"]["integrated"]
            checked(
                integrated_declaration
                == {
                    "mode": "integrated-critical",
                    "channel": "single_prompt_field",
                    "instruction": generation_builder.transport_instruction(
                        "integrated-critical"
                    ),
                    "critical_avoidance_integrated": True,
                    "send_full_negative_verbatim": False,
                    "send_native_negative_verbatim": False,
                }
                and integrated_payload["negative_prompt"] == NEGATIVE
                and integrated_payload["transports"]["separate"]["negative"] == NEGATIVE
                and integrated_rendition
                == {
                    "available": True,
                    "channel": "single_prompt_field",
                    "method": "authored-affirmative",
                    "text": INTEGRATED_PROMPT,
                    "sha256": generation_builder.sha256_text(INTEGRATED_PROMPT),
                },
                "integrated-critical build did not preserve its portable and affirmative renditions",
            )
            integrated_verified = verify(integrated_package)
            checked(
                integrated_verified["verified"] is True
                and integrated_verified["negative_transport_mode"] == "integrated-critical"
                and integrated_verified["selected_transport"]["rendition"]
                == integrated_rendition
                and integrated_verified["host_forwarding"]["effective_prompt"]
                == INTEGRATED_PROMPT
                and integrated_verified["negative_provenance"] == NEGATIVE_PROVENANCE,
                "integrated-critical verification changed the authored affirmative rendition",
            )
            integrated_export = emit_paste_for_target(
                integrated_package,
                INTEGRATED_MODEL_ID,
            )
            checked(
                set(integrated_export)
                == {
                    "target",
                    "mode",
                    "channel",
                    "instruction",
                    "parameters",
                    "selected_references",
                    "reference_preamble",
                    "generation_input_sha256",
                    "paste_prompt",
                    "paste_prompt_sha256",
                    "integration_method",
                }
                and integrated_export["target"] == INTEGRATED_MODEL_ID
                and integrated_export["mode"] == "integrated-critical"
                and integrated_export["channel"] == "single_prompt_field"
                and integrated_export["paste_prompt"] == INTEGRATED_PROMPT
                and integrated_export["paste_prompt_sha256"]
                == generation_builder.sha256_text(INTEGRATED_PROMPT)
                and integrated_export["integration_method"] == "authored-affirmative"
                and integrated_export["selected_references"] == []
                and integrated_export["reference_preamble"] == "",
                "integrated-critical export did not emit only its committed rendition",
            )

            certified_prompt_file = root / "certified-primary-prompt.txt"
            certified_prompt_file.write_text(
                INTEGRATED_PROMPT + "\n", encoding="utf-8", newline="\n"
            )
            certified_production_spec_file = (
                root / "certified-primary-production-specification.json"
            )
            _write_json(
                certified_production_spec_file,
                _production_spec(INTEGRATED_MODEL_ID),
            )
            certified_references_file = root / "certified-primary-references.json"
            _write_json(certified_references_file, empty_stateless_reference_set())
            certified_package_file = root / "certified-primary-generation-package.json"
            with contextlib.redirect_stdout(io.StringIO()):
                certified_build_exit = build_main(
                    [
                        "--model",
                        INTEGRATED_MODEL_ID,
                        "--prompt-file",
                        str(certified_prompt_file),
                        "--negative-file",
                        str(negative_file),
                        "--negative-provenance-file",
                        str(provenance_file),
                        "--negative-transport",
                        "auto",
                        "--critical-avoidance-integrated",
                        "--plot-file",
                        str(plot_file),
                        "--production-spec-file",
                        str(certified_production_spec_file),
                        "--state-lineage-file",
                        str(state_lineage_file),
                        "--references-file",
                        str(certified_references_file),
                        "--out",
                        str(certified_package_file),
                        *runtime_arguments,
                    ]
                )
            configure_pack_runtime(settings)
            catalog_cli.clear_runtime_caches()
            checked(
                certified_build_exit == 0 and certified_package_file.is_file(),
                "certified-primary CLI build failed without an integrated prompt file",
            )
            certified_package = json.loads(
                certified_package_file.read_text(encoding="utf-8")
            )
            certified_payload = certified_package["generation_payload"]
            certified_declaration = certified_payload["negative_transport"]
            certified_rendition = certified_payload["transports"]["integrated"]
            certified_prompt_hash = generation_builder.sha256_text(INTEGRATED_PROMPT)
            checked(
                certified_declaration
                == {
                    "mode": "integrated-critical",
                    "channel": "single_prompt_field",
                    "instruction": generation_builder.transport_instruction(
                        "integrated-critical"
                    ),
                    "critical_avoidance_integrated": True,
                    "send_full_negative_verbatim": False,
                    "send_native_negative_verbatim": False,
                }
                and certified_payload["prompt"] == INTEGRATED_PROMPT
                and certified_payload["prompt_sha256"] == certified_prompt_hash
                and certified_rendition
                == {
                    "available": True,
                    "channel": "single_prompt_field",
                    "method": "primary-prompt-certified",
                    "text": INTEGRATED_PROMPT,
                    "sha256": certified_prompt_hash,
                },
                "certified-primary build did not commit the exact primary prompt rendition",
            )
            certified_verified = verify(certified_package)
            checked(
                certified_verified["verified"] is True
                and certified_verified["model"] == INTEGRATED_MODEL_ID
                and certified_verified["negative_transport_mode"]
                == "integrated-critical"
                and certified_verified["selected_transport"]["rendition"]
                == certified_rendition
                and certified_verified["host_forwarding"]["effective_prompt"]
                == INTEGRATED_PROMPT
                and certified_verified["host_forwarding"]["effective_prompt_sha256"]
                == certified_prompt_hash,
                "certified-primary verification changed the selected target or prompt",
            )
            certified_export = emit_paste_for_target(
                certified_package,
                INTEGRATED_MODEL_ID,
            )
            checked(
                certified_export["target"] == INTEGRATED_MODEL_ID
                and certified_export["mode"] == "integrated-critical"
                and certified_export["channel"] == "single_prompt_field"
                and certified_export["paste_prompt"] == INTEGRATED_PROMPT
                and certified_export["paste_prompt_sha256"] == certified_prompt_hash
                and certified_export["integration_method"]
                == "primary-prompt-certified"
                and "paste_negative" not in certified_export
                and "native_negative" not in certified_export,
                "certified-primary export did not emit the exact target transport",
            )

            retained_package = _package(
                empty_stateless_reference_set(),
                model=UNKNOWN_EXPLICIT_MODEL_ID,
                production_target_model=UNKNOWN_EXPLICIT_MODEL_ID,
                negative_transport="retained-only",
            )
            retained_payload = retained_package["generation_payload"]
            retained_rendition = retained_payload["transports"]["integrated"]
            checked(
                retained_package["model"] == UNKNOWN_EXPLICIT_MODEL_ID
                and retained_payload["negative_transport"]["mode"] == "retained-only"
                and retained_payload["negative_transport"]["channel"]
                == "single_prompt_field"
                and retained_payload["negative_prompt"] == NEGATIVE
                and retained_payload["negative_prompt_sha256"]
                == generation_builder.sha256_text(NEGATIVE)
                and retained_payload["transports"]["separate"]["negative"] == NEGATIVE
                and retained_rendition == integrated_rendition,
                "explicit retained-only build lost the unknown target or portable negative",
            )
            retained_verified = verify(retained_package)
            checked(
                retained_verified["verified"] is True
                and retained_verified["model"] == UNKNOWN_EXPLICIT_MODEL_ID
                and retained_verified["negative_transport_mode"] == "retained-only"
                and retained_verified["negative_prompt"] == NEGATIVE
                and retained_verified["selected_transport"]["rendition"]
                == retained_rendition
                and retained_verified["host_forwarding"]["effective_prompt"]
                == INTEGRATED_PROMPT,
                "explicit retained-only verification inferred a different unknown-model transport",
            )
            retained_export = emit_paste_for_target(
                retained_package,
                UNKNOWN_EXPLICIT_MODEL_ID,
            )
            checked(
                set(retained_export)
                == {
                    "target",
                    "mode",
                    "channel",
                    "instruction",
                    "parameters",
                    "selected_references",
                    "reference_preamble",
                    "generation_input_sha256",
                    "paste_prompt",
                    "paste_prompt_sha256",
                    "integration_method",
                }
                and retained_export["target"] == UNKNOWN_EXPLICIT_MODEL_ID
                and retained_export["mode"] == "retained-only"
                and retained_export["channel"] == "single_prompt_field"
                and retained_export["paste_prompt"] == INTEGRATED_PROMPT
                and retained_export["paste_prompt_sha256"]
                == generation_builder.sha256_text(INTEGRATED_PROMPT)
                and retained_export["integration_method"] == "authored-affirmative"
                and "paste_negative" not in retained_export
                and "native_negative" not in retained_export,
                "retained-only export exposed an uncharacterized negative channel",
            )

            # The policy activates the render profile and style family the
            # specification selects, whether or not the author declared them.
            declared_only = {"activated_sources": ["generation-hygiene"], "diagnostic_sources_retained": [],
                             "semantic_exclusions_user_supplied": [], "affirmative_translations": {}}
            medium_package = _package(empty_stateless_reference_set(), negative_provenance=declared_only)
            checked(
                medium_package["generation_payload"]["negative_provenance"]["activated_sources"]
                == ["generation-hygiene", *MEDIUM_SOURCES],
                "the build did not activate the render profile and style family its specification selects",
            )
            unselected_spec = _production_spec(MODEL_ID)
            unselected_spec["visual_language"].update({"render_profile": "unspecified", "style_family": None})
            unselected_package = _package(empty_stateless_reference_set(), negative_provenance=declared_only,
                                          production_spec_override=unselected_spec)
            checked(
                unselected_package["generation_payload"]["negative_provenance"]["activated_sources"]
                == ["generation-hygiene"],
                "an unspecified render profile or an absent style family activated a negative source",
            )
            # A single prompt field with no negative at all still owes affirmative
            # wording for every active source.
            try:
                _package(empty_stateless_reference_set(), model=INTEGRATED_MODEL_ID,
                         production_target_model=INTEGRATED_MODEL_ID, negative_prompt="", integrated_prompt="",
                         negative_provenance={})
                refusal = ""
            except ValueError as exc:
                refusal = str(exc)
            checked(
                "no negative field" in refusal and all(source in refusal for source in MEDIUM_SOURCES),
                "a target with no negative field accepted active sources without affirmative wording",
            )

            integrated_text_tamper = copy.deepcopy(integrated_package)
            integrated_text_tamper["generation_payload"]["transports"]["integrated"][
                "text"
            ] = "A changed integrated rendition without a matching hash."
            integrated_tamper_errors, _ = verify_transports(integrated_text_tamper)
            checked(
                integrated_tamper_errors.count("integrated transport hash mismatch") == 1,
                "integrated rendition tampering did not report its exact hash mismatch",
            )
            try:
                verify(integrated_text_tamper)
            except ValueError as exc:
                integrated_tamper_verify_error = str(exc)
            else:
                integrated_tamper_verify_error = ""
            checked(
                "recommendation audit differs from its recorded transformation" in integrated_tamper_verify_error,
                "full verification did not reject the rendition against its recorded transformation: " + integrated_tamper_verify_error,
            )
            mutation_count += 1

            missing_coverage = copy.deepcopy(integrated_package)
            missing_coverage_text = (
                "A poised synthetic character in a clean text-free quiet studio light."
            )
            missing_coverage["generation_payload"]["transports"]["integrated"][
                "text"
            ] = missing_coverage_text
            missing_coverage["generation_payload"]["transports"]["integrated"][
                "sha256"
            ] = generation_builder.sha256_text(missing_coverage_text)
            missing_coverage_errors, _ = verify_transports(missing_coverage)
            expected_coverage_error = (
                "declared affirmative coverage for `anatomy-review` is absent from the "
                "integrated rendition"
            )
            checked(
                expected_coverage_error in missing_coverage_errors
                and "integrated transport hash mismatch" not in missing_coverage_errors,
                "rehashed integrated rendition did not report the distinct affirmative-coverage error",
            )
            try:
                verify(missing_coverage)
            except ValueError as exc:
                missing_coverage_verify_error = str(exc)
            else:
                missing_coverage_verify_error = ""
            checked(
                "recommendation audit differs from its recorded transformation" in missing_coverage_verify_error,
                "full verification did not reject the changed rendition against its transformation: " + missing_coverage_verify_error,
            )
            mutation_count += 1

            verified_base = verify(base, package_root=root)
            exported = emit_paste_for_target(base, MODEL_ID, package_root=root)
            checked(
                verified_base["negative_transport_mode"] == "separate-field"
                and verified_base["selected_transport"]["rendition"]
                == base["generation_payload"]["transports"]["separate"]
                and verified_base["selected_transport"]["rendition"]["prompt"] == PROMPT
                and verified_base["selected_transport"]["rendition"]["negative"]
                == NEGATIVE
                and verified_base["selected_transport"]["rendition"]["prompt_sha256"]
                == generation_builder.sha256_text(PROMPT)
                and verified_base["selected_transport"]["rendition"]["negative_sha256"]
                == generation_builder.sha256_text(NEGATIVE)
                and exported["mode"] == "separate-field"
                and exported["channel"] == "prompt_plus_negative_fields",
                "separate-field negative transport was not preserved",
            )
            checked(
                set(exported)
                == {
                    "target",
                    "mode",
                    "channel",
                    "instruction",
                    "parameters",
                    "selected_references",
                    "reference_preamble",
                    "generation_input_sha256",
                    "paste_prompt",
                    "paste_prompt_sha256",
                    "paste_negative",
                }
                and exported["paste_prompt"]
                == verified_base["host_forwarding"]["effective_prompt"]
                and exported["paste_prompt_sha256"]
                == verified_base["host_forwarding"]["effective_prompt_sha256"]
                and exported["paste_negative"] == NEGATIVE
                and exported["selected_references"] == host_mixed,
                "committed export fields are incomplete or reconstructed",
            )
            checked(
                verified_base["negative_provenance"] == NEGATIVE_PROVENANCE
                and base["generation_payload"]["negative_provenance"] == NEGATIVE_PROVENANCE,
                "negative provenance was lost from the committed/verified package",
            )
            try:
                emit_paste_for_target(base, "another-model", package_root=root)
            except ValueError:
                pass
            else:
                raise SmokeFailure("host export retargeted a committed package")
            checked(True, "target mismatch rejection was not reached")

            tampered = copy.deepcopy(base)
            tampered["generation_payload"]["parameters"]["quality"] = "tampered"
            tampered_path = root / "tampered-package.json"
            _write_json(tampered_path, tampered)
            absent_verify_output = root / "failed-verification.json"
            with contextlib.redirect_stdout(io.StringIO()):
                failed_verify_exit = verify_main(
                    [
                        str(tampered_path),
                        "--payload-out",
                        str(absent_verify_output),
                        *runtime_arguments,
                    ]
                )
            checked(failed_verify_exit == 1, "verifier CLI accepted a changed commitment")
            checked(not absent_verify_output.exists(), "failed verifier CLI wrote output")

            protected_verify_output = root / "protected-verification.json"
            protected_verify_output.write_text("sentinel", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                protected_verify_exit = verify_main(
                    [
                        str(tampered_path),
                        "--payload-out",
                        str(protected_verify_output),
                        *runtime_arguments,
                    ]
                )
            checked(protected_verify_exit == 1, "verifier CLI accepted a protected-output failure")
            checked(
                protected_verify_output.read_text(encoding="utf-8") == "sentinel",
                "failed verifier CLI replaced a pre-existing output",
            )

            return {
                "ok": True,
                "checks": checked.count,
                "round_trip_reference_counts": [0, 1, 2],
                "supplied_reference_order_preserved": True,
                "svg_rasterization_exercised": True,
                "prepared_reference_set_contract_exercised": True,
                "stateless_reference_origin_is_null": True,
                "runtime_plan_round_trip_exercised": True,
                "portable_companion_exercised": True,
                "authority_preamble_forwarded": True,
                "transactional_publication_exercised": True,
                "manual_pack_bypass_rejected": True,
                "certified_primary_transport_exercised": True,
                "committed_mutations_rejected": mutation_count,
                "host_reference_fields": HOST_REFERENCE_FIELDS,
            }
    finally:
        configure_pack_runtime(None)
        catalog_cli.clear_runtime_caches()


def run_derived_inputs() -> dict[str, Any]:
    """Derived CLI inputs equal hand-supplied ones, and a changed run or package fails closed."""
    import production_fixtures
    import production_workflow
    import request_contract
    import request_validation
    import runtime_evidence
    import service_profile
    import studio
    import transport_runware
    from catalog_retrieval.runtime import load_pack_catalog
    from prepare_generation_references import resolve_model_record
    from verify_generation_payload import verify as verify_live
    from visual_continuity import file_ref

    checked = CheckCounter()
    model = "grok-imagine-image-2.0"
    commons = json.loads((Path(__file__).resolve().parents[1] / "packs/commons/pack.json").read_text(encoding="utf-8"))["pack_id"]
    schema_path = "@pack/" + commons + "/resources/observed-schemas/grok-imagine-image-2.0.runware.json"
    try:
        with tempfile.TemporaryDirectory(prefix="cpb-derived-") as temporary:
            base = Path(temporary).resolve()
            state = base / "pack-state.json"
            save_state(state, {"pack_roots": [], "enabled_packs": [commons], "resource_providers": {
                name: commons for name in ("service-profiles", "prompt-writing-guide", "prompt-dialects")}})
            runtime = ["--state-file", str(state), "--cache-dir", str(base / "cache"), "--managed-root", str(base / "managed")]
            configure_pack_runtime(default_settings(state_file=state, cache_dir=base / "cache", managed_root=base / "managed"))
            project = studio.init(base / "project", "derived-inputs", "Derived input checks")
            run_id = production_fixtures.prepare_dispatch(project, PROMPT)
            (base / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
            for name, value in {"plot.json": APPROVED_PLOT, "retrieval.json": fixture_retrieval(PROMPT, APPROVED_PLOT)}.items():
                atomic_write_json(base / name, value)
            # A first image of a person needs only the drafted specification: no
            # morphology contract and no lineage hash.
            drafted = io.StringIO()
            with contextlib.redirect_stdout(drafted):
                draft_exit = production_spec.main(["draft", str(base / "spec.json"), "--model", model, "--brief", PROMPT,
                                                   "--kind", "human", "--framing", "upper-thigh", "--continuity", "one-off"])
            lean = json.loads((base / "spec.json").read_text(encoding="utf-8"))
            checked(draft_exit == 0 and json.loads(drafted.getvalue())["build_with"]
                    == ["--production-spec-file", str(base / "spec.json"), "--continuity", "C01=one-off"],
                    "the draft does not name the builder arguments for its subject")
            checked(lean["state_context"] == {"mode": "stateless", "notes": []}
                    and not any(key.endswith("_ref") or key == "resolved_morphology" for key in lean["subjects"][0]),
                    "the drafted specification carries lineage or morphology references")
            from state_protocol import validate_state_artifact_graph
            graph = validate_state_artifact_graph(lineage=_stateless_lineage(), production_spec=lean)
            checked(graph["ok"], f"the stateless graph refuses the drafted specification: {graph['errors']}")
            with contextlib.redirect_stdout(io.StringIO()):
                checked(production_spec.main(["draft", str(base / "spec.json"), "--model", model, "--brief", PROMPT,
                                              "--kind", "human", "--framing", "upper-thigh", "--continuity", "one-off"]) == 1,
                        "the draft replaced an existing file")
            common = ["--model", model, "--prompt-file", str(base / "prompt.txt"), "--plot-file", str(base / "plot.json"),
                      "--retrieval-record-file", str(base / "retrieval.json"), "--production-spec-file", str(base / "spec.json"),
                      "--parameters", json.dumps({"width": 832, "height": 1248}), "--production-root", str(project), *runtime]

            def build(name: str, *extra: str) -> dict[str, Any]:
                with contextlib.redirect_stdout(io.StringIO()):
                    checked(_build_main([*common, "--out", str(base / name), *extra]) == 0, name + " was refused")
                return json.loads((base / name).read_text(encoding="utf-8"))

            def refusal(*extra: str) -> list[str]:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    if _build_main([*common, "--out", str(base / "refused.json"), *extra]) == 0:
                        raise SmokeFailure("builder accepted " + " ".join(extra))
                return json.loads(stdout.getvalue())["errors"]

            def refused(pattern: str, *extra: str) -> None:
                errors = refusal(*extra)
                checked(any(pattern in error for error in errors), f"expected {pattern!r}, got {errors}")

            derived = build("derived.json", "--continuity", "C01=one-off")
            checked(derived["production_spec"] == lean and derived["state_lineage"]["mode"] == "stateless",
                    "the package does not carry the drafted specification and a sealed stateless lineage")
            record = derived["request_validation"]
            checked(record["mode"] == "target-schema" and record["contract"] == record["evidence"]
                    and record["contract"]["path"] == schema_path, "derived request check does not name the pack schema")
            checked(derived["production_binding"]["run"] == run_id, "package is not bound to the open task's run")
            checked(derived["route_reading"] == production_workflow.load_run(project, run_id)[1]["route_reading"],
                    "route reading differs from the prepared run")

            # The same records written by hand give the identical generation input.
            model_id, model_record = resolve_model_record(model)
            offering = model_record["offerings"][0]
            service = service_profile.load_service("runware", Path(load_pack_catalog().resources["service-profiles"].path))
            hand_validation = request_validation.build_record(
                {"mode": "target-schema", "contract": schema_path, "evidence": schema_path, "execution_policy": None},
                runtime_evidence.reader(project),
                expected_target={"service": "runware", "model_identifier": "xai:grok-imagine@image-2.0", "operation": "imageInference"},
                execution=request_contract.execution_hashes(service, offering, Path(transport_runware.__file__), model=model_record, policy=None))
            basis = derived["visual_continuity"]["basis"]["path"]
            hand_visual = {"purpose": "image", "basis": file_ref(project, basis, locator="whole"), "subjects": {
                "C01": {"continuity": "one-off", "character_id": None, "studio_character": None, "identity_refs": []}}}
            atomic_write_json(base / "hand-validation.json", hand_validation)
            atomic_write_json(base / "hand-visual.json", hand_visual)
            hand = build("hand.json", "--request-validation-file", str(base / "hand-validation.json"),
                         "--visual-continuity-file", str(base / "hand-visual.json"), "--production-run", run_id)
            checked(hand["generation_input_sha256"] == derived["generation_input_sha256"]
                    and hand["request_validation"] == record and hand["visual_continuity"] == derived["visual_continuity"],
                    "derived inputs differ from the hand-supplied records")

            # Decisions stay explicit, and derivation refuses what it cannot prove.
            refused("state each production subject")
            refused("already states continuity", "--continuity", "C01=one-off", "--visual-continuity-file", str(base / "hand-visual.json"))
            refused("studio character", "--continuity", "C01=recurring")
            # The first images of a new character are undecided until the author accepts one.
            studio.add_character(project, "C01", "")
            refused("undecided exploration", "--continuity", "C01=recurring", "--character", "C01=C01")
            undecided = build("undecided.json", "--continuity", "C01=undecided", "--character", "C01=C01")
            checked(undecided["visual_continuity"]["subjects"]["C01"]["continuity"] == "undecided",
                    "an undecided first image of a studio character was refused")
            # Specification errors come back as JSON, each once, from the builder and the verifier.
            broken = copy.deepcopy(lean)
            broken["state_context"]["state_lineage_sha256"] = "a" * 64
            broken["camera"]["pitch_degrees"] = "level"
            broken["subjects"][0]["identity_contract_ref"] = {"id": "identity", "sha256": "b" * 64}
            atomic_write_json(base / "broken-spec.json", broken)
            errors = refusal("--production-spec-file", str(base / "broken-spec.json"), "--continuity", "C01=one-off")
            checked(len(errors) == 5 == len(set(errors))
                    and all(error.startswith("production specification: $.") for error in errors),
                    f"builder specification errors are not one JSON list with each error once: {errors}")
            tampered_spec = copy.deepcopy(derived)
            tampered_spec["production_spec"] = broken
            atomic_write_json(base / "broken-package.json", tampered_spec)
            verified_out = io.StringIO()
            with contextlib.redirect_stdout(verified_out):
                verify_exit = _verify_main([str(base / "broken-package.json"), "--studio-root", str(project), *runtime])
            verify_report = json.loads(verified_out.getvalue())
            checked(verify_exit == 1 and verify_report["verified"] is False and verify_report["errors"] == errors,
                    "verifier specification errors differ from the builder's")
            refused("each production subject", "--continuity", "C02=one-off")
            with mock.patch("production_workflow.assert_current", return_value=(None, {"route_reading": derived["route_reading"]},
                                                                                 {"transport": "bounded-context"}, [])):
                refused("bounded production context", "--continuity", "C01=one-off")

            # A tampered package or a changed prepared run fails closed.
            verify_live(derived, package_root=base, project=project)
            tampered = copy.deepcopy(derived)
            snapshot = tampered["input_snapshots"][schema_path]
            snapshot["base64"] = snapshot["base64"][:-4] + ("AAAA" if not snapshot["base64"].endswith("AAAA") else "BBBB")
            try:
                accepted = verify_live(tampered, package_root=base, project=project).get("verified") is True
            except ValueError:
                accepted = False
            checked(not accepted, "verifier accepted a tampered pack schema snapshot")
            (project / "fixture-delivery.txt").write_text(PROMPT + " changed", encoding="utf-8")
            refused("prepare a new run", "--continuity", "C01=one-off")
    finally:
        configure_pack_runtime(None)
        catalog_cli.clear_runtime_caches()
    return {"ok": True, "checks": checked.count}


def main() -> int:
    try:
        result = run()
        derived = run_derived_inputs()
        result["derived_input_checks"] = derived["checks"]
    except (SmokeFailure, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "errors": [str(exc)]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
