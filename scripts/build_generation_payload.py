#!/usr/bin/env python3
"""Package an agent-authored prompt for exact downstream image generation.

The script does not interpret the brief or write the prompt. It records the
creative decision, hashes every transmitted text payload, and declares how the
target interface receives avoidance instructions. It binds the package to the
prepared production run and derives the route reading, the request check and
visual continuity from that run, the active pack and the stated decisions.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from catalog_cli import configure_pack_runtime
from model_contract import (
    apply_positive_recommendation,
    apply_prompt_recommendations,
    generation_media_counts,
    select_offering,
    validate_generation_parameters,
)
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from prepare_generation_references import (
    build_prepared_reference_set,
    empty_stateless_reference_set,
    resolve_model_record as resolve_reference_model_record,
    sha256_file,
    validate_prepared_reference_set,
)
from prepare_generation_references import model_pack_root
from state_protocol import find_non_finite_numbers, parse_json

TRANSPORT_MODES = {
    "auto",
    "separate-field",
    "integrated-critical",
    "native-subset",
    "retained-only",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NEGATIVE_PROVENANCE_FIELDS = {
    "activated_sources",
    "diagnostic_sources_retained",
    "semantic_exclusions_user_supplied",
    "affirmative_translations",
}
MEDIA_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}
_RECOVERY_STAGING_ATTRIBUTE = "_cpb_generation_package_recovery_staging"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def require_concrete_sha256(value: Any, field: str) -> str:
    digest = str(value or "")
    if not SHA256_RE.fullmatch(digest) or digest == "0" * 64:
        raise ValueError(f"{field} must be a nonzero lowercase SHA-256")
    return digest


def validate_generation_package_carrier_paths(
    prepared_reference_set: dict[str, Any],
    *,
    package_root: Path | None,
) -> str | None:
    """Require every signed carrier to resolve inside one `.references` companion."""

    carriers: list[tuple[str, Any]] = []
    for index, row in enumerate(prepared_reference_set.get("selected_references") or []):
        transport = row.get("transport") if isinstance(row, dict) else None
        carriers.append(
            (
                f"prepared_reference_set.selected_references[{index}].transport.resolved_path",
                transport.get("resolved_path") if isinstance(transport, dict) else None,
            )
        )
    for index, artifact in enumerate(prepared_reference_set.get("prompt_artifacts") or []):
        carriers.append(
            (
                f"prepared_reference_set.prompt_artifacts[{index}].delivered_path",
                artifact.get("delivered_path") if isinstance(artifact, dict) else None,
            )
        )
    board = prepared_reference_set.get("single_board")
    if isinstance(board, dict):
        carriers.append(
            ("prepared_reference_set.single_board.resolved_path", board.get("resolved_path"))
        )
    companion_names: set[str] = set()
    for field, stored in carriers:
        if not isinstance(stored, str) or not stored or "\\" in stored:
            raise ValueError(f"{field} must be a canonical package-relative POSIX path")
        path = PurePosixPath(stored)
        if path.is_absolute() or path.as_posix() != stored or len(path.parts) < 2:
            raise ValueError(f"{field} must be stored beneath a package companion")
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"{field} escapes its package companion")
        companion = path.parts[0]
        if (
            companion == ".references"
            or not companion.endswith(".references")
            or any(character in companion for character in '<>:"/\\|?*')
        ):
            raise ValueError(f"{field} is outside a named .references companion")
        companion_names.add(companion)
    if len(companion_names) > 1:
        raise ValueError("Generation Package carriers span multiple .references companions")
    companion_name = next(iter(companion_names), None)
    if companion_name is None:
        return None
    if package_root is None:
        raise ValueError("Generation Package carriers require package_root")
    root = Path(package_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Generation Package package_root is not a directory: {root}")
    companion_root = (root / companion_name).resolve(strict=True)
    try:
        companion_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("Generation Package companion escapes package_root") from exc
    if not companion_root.is_dir():
        raise ValueError("Generation Package companion is not a directory")
    for field, stored in carriers:
        resolved = (root / Path(str(stored))).resolve(strict=True)
        try:
            resolved.relative_to(companion_root)
        except ValueError as exc:
            raise ValueError(f"{field} resolves outside its package companion") from exc
        if not resolved.is_file():
            raise ValueError(f"{field} does not identify a companion file")
    return companion_name


def generation_commitment_projection(data: dict[str, Any]) -> dict[str, Any]:
    """Return the one canonical, pure projection committed for generation.

    The helper intentionally performs no I/O and does not infer target behavior.
    Builder and verifier hash this exact projection, eliminating parallel hash
    definitions that can drift as the package grows.
    """

    payload = data.get("generation_payload")
    if not isinstance(payload, dict):
        raise ValueError("generation_payload is missing")
    transports = payload.get("transports")
    selected_transport = payload.get("negative_transport")
    if not isinstance(transports, dict):
        raise ValueError("payload has no transports block")
    if not isinstance(selected_transport, dict):
        raise ValueError("negative transport declaration is missing")
    prepared_reference_set = data.get("prepared_reference_set")
    if not isinstance(prepared_reference_set, dict):
        raise ValueError("prepared_reference_set is missing")
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("generation parameters must be an object")
    provenance = payload.get("negative_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("negative provenance declaration is missing")

    return {
        "route_reading_sha256": data["route_reading_sha256"],
        "visual_continuity_sha256": data["visual_continuity_sha256"],
        "request_validation_sha256": data["request_validation_sha256"],
        "input_snapshots_sha256": data["input_snapshots_sha256"],
        "production_binding": data["production_binding"],
        "model": data.get("model"),
        "render_contract": data["render_contract"],
        "parameters": parameters,
        "prompt": payload.get("prompt"),
        "negative_prompt": payload.get("negative_prompt"),
        "integrated_prompt": (transports.get("integrated") or {}).get("text"),
        "native_negative": payload.get("native_negative"),
        "negative_provenance": provenance,
        "prompt_recommendations": payload.get("prompt_recommendations"),
        "transports": transports,
        "selected_transport": selected_transport,
        "prepared_reference_set": prepared_reference_set,
        "prepared_reference_set_sha256": data.get("prepared_reference_set_sha256"),
        "production_spec_sha256": data.get("production_spec_sha256"),
        "state_lineage_sha256": data.get("state_lineage_sha256"),
        "plot_sha256": data.get("plot_sha256"),
        "composition_prompt": data.get("composition_prompt"),
        "retrieval_record_sha256": data.get("retrieval_record_sha256"),
    }


def generation_input_sha256(data: dict[str, Any]) -> str:
    return sha256_json(generation_commitment_projection(data))


def read_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8").strip()


def read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    data = parse_json(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON input must be an object")
    return data


def resolve_model_record(model: str) -> tuple[str, dict[str, Any]]:
    """Resolve an exact catalog ID, label, or declared alias.

    Automatic transport deliberately has no silent fallback. A newly added
    model becomes usable as soon as a valid model record is added to an enabled
    pack. An unknown target must either be added to that catalog or be packaged
    with an explicit ``--negative-transport`` value.
    """

    return resolve_reference_model_record(model)


def normalize_negative_provenance(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is not None and not isinstance(value, dict):
        raise ValueError("negative provenance must be an object")
    provenance = dict(value or {})
    unexpected = sorted(set(provenance) - NEGATIVE_PROVENANCE_FIELDS)
    if unexpected:
        raise ValueError(
            "negative provenance contains unexpected fields: " + ", ".join(unexpected)
        )
    for key in (
        "activated_sources",
        "diagnostic_sources_retained",
        "semantic_exclusions_user_supplied",
    ):
        item = provenance.setdefault(key, [])
        if not isinstance(item, list):
            raise ValueError(f"negative provenance field must be a list: {key}")
    translations = provenance.setdefault("affirmative_translations", {})
    if not isinstance(translations, dict):
        raise ValueError("negative provenance affirmative_translations must be an object")
    for key, text in translations.items():
        if not isinstance(key, str) or not isinstance(text, str) or not text.strip():
            raise ValueError("affirmative_translations must map source IDs to non-empty text")
    return provenance


def selected_medium_sources(production_spec: dict[str, Any], declared: list[Any]) -> list[Any]:
    """The declared sources, plus the render profile and style family the specification selects.

    The negative policy activates a selected render profile or style family
    whenever one is selected, so the package records it without being told.
    """

    from production_spec import UNSPECIFIED

    visual = production_spec.get("visual_language")
    visual = visual if isinstance(visual, dict) else {}
    sources = list(declared)
    for kind, key in (("render-profile", "render_profile"), ("style-family", "style_family")):
        value = visual.get(key)
        if isinstance(value, str) and value.strip() and value != UNSPECIFIED:
            source = f"{kind}:{value}"
            if source not in sources:
                sources.append(source)
    return sources


def infer_negative_transport(model: str) -> str:
    """Return the transport mode declared by the canonical model catalog."""

    model_id, record = resolve_model_record(model)
    mode = str(record.get("negative_transport_mode") or "")
    if mode not in TRANSPORT_MODES - {"auto"}:
        raise ValueError(
            f"model record {model_id!r} has invalid negative_transport_mode {mode!r}"
        )
    return mode


def build_transports(
    *,
    prompt: str,
    negative_prompt: str,
    integrated_prompt: str,
    critical_avoidance_integrated: bool,
    native_negative: str,
) -> dict[str, Any]:
    """Build three explicit, independently hashed interface renditions.

    No negative text is appended mechanically to a positive prompt. A
    negative-bearing package therefore needs an agent-authored affirmative
    integrated rendition, or a certification that the primary prompt already
    contains the required affirmative construction language.
    """
    separate = {
        "available": True,
        "channel": "prompt_plus_negative_fields",
        "method": "verbatim-separate-fields",
        "prompt": prompt,
        "negative": negative_prompt,
        "prompt_sha256": sha256_text(prompt),
        "negative_sha256": sha256_text(negative_prompt),
    }

    integrated_text = ""
    integrated_method = "unavailable"
    integrated_available = False
    if integrated_prompt.strip():
        integrated_text = integrated_prompt.strip()
        integrated_method = "authored-affirmative"
        integrated_available = True
    elif critical_avoidance_integrated:
        integrated_text = prompt
        integrated_method = "primary-prompt-certified"
        integrated_available = True
    elif not negative_prompt:
        integrated_text = prompt
        integrated_method = "no-negative-required"
        integrated_available = True

    integrated = {
        "available": integrated_available,
        "channel": "single_prompt_field",
        "method": integrated_method,
        "text": integrated_text,
        "sha256": sha256_text(integrated_text),
    }

    native_available = bool(native_negative) or not negative_prompt
    native_method = "verbatim-native-subset" if native_negative else (
        "no-negative-required" if not negative_prompt else "unavailable"
    )
    native_subset = {
        "available": native_available,
        "channel": "prompt_plus_native_negative",
        "method": native_method,
        "prompt": prompt if native_available else "",
        "negative": native_negative if native_available else "",
        "prompt_sha256": sha256_text(prompt if native_available else ""),
        "negative_sha256": sha256_text(native_negative if native_available else ""),
    }

    return {
        "separate": separate,
        "integrated": integrated,
        "native_subset": native_subset,
        "paste_instructions": {
            "single_prompt_field": (
                "Paste transports.integrated.text as the only prompt. The text must be an "
                "agent-authored affirmative rendition or the certified primary prompt."
            ),
            "prompt_plus_negative_fields": (
                "Paste transports.separate.prompt into the positive field and "
                "transports.separate.negative into the independent negative field, verbatim."
            ),
            "prompt_plus_native_negative": (
                "Paste transports.native_subset.prompt as the main prompt and transmit "
                "transports.native_subset.negative through the platform's concise native "
                "negative syntax, verbatim."
            ),
        },
    }


def transport_instruction(mode: str) -> str:
    instructions = {
        "separate-field": (
            "Use transports.separate: send its prompt and negative verbatim to the "
            "independent positive and negative fields."
        ),
        "integrated-critical": (
            "Use transports.integrated: send its text verbatim through the single prompt "
            "field. The integrated rendition contains the affirmative construction language."
        ),
        "native-subset": (
            "Use transports.native_subset: send its prompt verbatim and transmit its concise "
            "negative through the platform's native negative syntax."
        ),
        "retained-only": (
            "Use transports.integrated when available. The portable separate negative remains "
            "in the package for traceability because the target has no characterized negative field."
        ),
    }
    return instructions[mode]


def build_payload(
    *,
    model: str,
    prompt: str,
    negative_prompt: str,
    brief: str,
    creative_intent: dict[str, Any],
    parameters: dict[str, Any],
    negative_transport: str = "auto",
    critical_avoidance_integrated: bool = False,
    integrated_prompt: str = "",
    native_negative: str = "",
    negative_provenance: dict[str, Any] | None = None,
    production_spec: dict[str, Any] | None = None,
    state_lineage: dict[str, Any] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    prepared_reference_set: dict[str, Any] | None = None,
    prepared_reference_root: Path | None = None,
    plot: dict[str, Any] | None = None,
    retrieval_record: dict[str, Any] | None = None,
    visual_continuity: dict[str, Any] | None = None,
    visual_root: Path | None = None,
    request_validation: dict[str, Any] | None = None,
    input_root: Path | None = None,
    route_reading: dict[str, Any] | None = None,
    reading_ledgers: list[Path] | None = None,
    service: str | None = None,
    production_root: Path | None = None,
    production_run: str | None = None,
) -> dict[str, Any]:
    from route_reading import require_route_reading, GENERATION_ROUTES
    if route_reading is None:
        raise ValueError("generation requires a route reading")
    require_route_reading(route_reading, ledgers=reading_ledgers, project=production_root,
                          package_root=prepared_reference_root, routes=GENERATION_ROUTES)
    reading_hash = sha256_json(route_reading)
    input_values = {
        "creative_intent": creative_intent,
        "parameters": parameters,
        "negative_provenance": negative_provenance,
        "production_spec": production_spec,
        "state_lineage": state_lineage,
        "state_snapshot": state_snapshot,
        "prepared_reference_set": prepared_reference_set,
    }
    non_finite = find_non_finite_numbers(input_values)
    if non_finite:
        raise ValueError("non-finite numbers are not permitted: " + ", ".join(non_finite))
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    model = model.strip()
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must not be empty")
    if not isinstance(negative_prompt, str):
        raise ValueError("negative_prompt must be a string")
    if not isinstance(integrated_prompt, str) or not isinstance(native_negative, str):
        raise ValueError("integrated and native negative prompts must be strings")
    composition_prompt = prompt.strip()
    prompt = prompt.strip()
    negative_prompt = negative_prompt.strip()
    integrated_prompt = integrated_prompt.strip()
    native_negative = native_negative.strip()
    provenance = normalize_negative_provenance(negative_provenance)
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    parameters = dict(parameters)
    if negative_transport not in TRANSPORT_MODES:
        raise ValueError(f"unknown negative transport mode: {negative_transport}")

    model_id = model
    model_record: dict[str, Any] | None = None
    try:
        model_id, model_record = resolve_model_record(model)
    except ValueError:
        if negative_transport == "auto":
            raise
    from model_contract import _merge_one
    _,positive_audit=_merge_one(prompt,'',mode='advisory-only',limit=None,field='prompt')
    _,negative_audit=_merge_one(negative_prompt,'',mode='advisory-only',limit=None,field='negative_prompt')
    recommendation_audit={'resolved_model_id':model_id if model_record is not None else None,
        'merge_mode':'advisory-only','positive':positive_audit,'negative':negative_audit,
        'integrated':None,'negative_preset':''}
    if model_record is not None:
        if model_record.get("operation_kind") == "upscale":
            raise ValueError(
                f"model record {model_id!r} is an upscaler; use build_upscale_package.py"
            )
        prompt, negative_prompt, recommendation_audit = apply_prompt_recommendations(
            model_record,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )
        recommendation_audit["resolved_model_id"] = model_id
        if integrated_prompt:
            integrated_prompt, integrated_audit = apply_positive_recommendation(
                model_record, prompt=integrated_prompt
            )
            recommendation_audit["integrated"] = integrated_audit
    mode = (
        str(model_record.get("negative_transport_mode") or "")
        if negative_transport == "auto" and model_record is not None
        else negative_transport
    )
    if mode not in TRANSPORT_MODES - {"auto"}:
        raise ValueError(f"invalid negative transport mode: {mode!r}")

    if native_negative and not negative_prompt:
        raise ValueError("native_negative requires a portable negative_prompt")

    transports = build_transports(
        prompt=prompt,
        negative_prompt=negative_prompt,
        integrated_prompt=integrated_prompt,
        critical_avoidance_integrated=critical_avoidance_integrated,
        native_negative=native_negative,
    )

    # A negative-bearing package must remain usable when moved to a model that
    # has only one prompt field. The affirmative rendition is semantic agent
    # work and is never synthesized by string concatenation.
    if negative_prompt and not transports["integrated"]["available"]:
        raise ValueError(
            "negative-bearing payloads require an agent-authored integrated prompt, "
            "or --critical-avoidance-integrated when the primary prompt already contains "
            "the affirmative construction requirements"
        )
    if mode == "native-subset" and negative_prompt and not transports["native_subset"]["available"]:
        raise ValueError("native-subset targets require a concise native negative payload")
    if mode in {"integrated-critical", "retained-only"} and not transports["integrated"]["available"]:
        raise ValueError("the selected target requires an available integrated transport")

    prompt_hash = sha256_text(prompt)
    negative_hash = sha256_text(negative_prompt)
    native_hash = sha256_text(native_negative)
    from production_spec import require as require_production_spec, require_lineage
    require_production_spec(production_spec)
    production_spec = dict(production_spec)
    if production_spec.get("target_model") != model:
        raise ValueError("package model differs from production specification target_model")
    production_spec_hash = sha256_json(production_spec)
    provenance["activated_sources"] = selected_medium_sources(production_spec, provenance["activated_sources"])
    # A single prompt field receives no negative, so the prompt itself states
    # each active source affirmatively, and the provenance names those words.
    if mode in {"integrated-critical", "retained-only"}:
        untranslated = sorted({str(source) for source in provenance["activated_sources"]}
                              - set(provenance["affirmative_translations"]))
        if untranslated:
            raise ValueError(
                "the target has no negative field, so the prompt states each active negative source affirmatively; "
                "name those words in --negative-provenance-file, for example "
                + json.dumps({"affirmative_translations": {untranslated[0]: "<words copied from the prompt>"}})
                + "; without words: " + ", ".join(untranslated)
            )

    from state_protocol import artifact_hash, finalize_artifact, validate_artifact
    if state_lineage is not None and not isinstance(state_lineage, dict):
        raise ValueError("state lineage must be an object")
    if state_lineage:
        state_lineage = dict(state_lineage)
    else:
        state_lineage = finalize_artifact({
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
        })
    lineage_report = validate_artifact(state_lineage)
    if not lineage_report.get("ok"):
        raise ValueError("invalid state lineage: " + "; ".join(lineage_report.get("errors", [])))
    lineage_hash = require_concrete_sha256(
        state_lineage.get("lineage_sha256"), "state_lineage.lineage_sha256"
    )
    require_lineage(production_spec, state_lineage)

    reference_set = validate_prepared_reference_set(
        prepared_reference_set
        if prepared_reference_set is not None
        else empty_stateless_reference_set(),
        model=model,
        package_root=prepared_reference_root,
    )
    validate_generation_package_carrier_paths(
        reference_set,
        package_root=prepared_reference_root,
    )
    if reference_set["transport_mode"] in {"prompt-artifacts", "svg-bundle"}:
        raise ValueError(
            f"{reference_set['transport_mode']} prepared references are prompt-package "
            "artifacts and cannot be used for model generation"
        )
    reference_selection = reference_set["reference_selection"]
    reference_selection_hash = reference_set["reference_selection_sha256"]
    prepared_reference_set_hash = require_concrete_sha256(
        reference_set["prepared_reference_set_sha256"],
        "prepared_reference_set.prepared_reference_set_sha256",
    )
    # The request as the service will see it is checked here: against the model
    # record's own limits, and against the service's observed parameter schema
    # when the record's offering points at one. Nothing has been uploaded yet,
    # so media stand in as placeholders and only their number is judged.
    from render_contract_lib import compile_contract
    if model_record is None:
        raise ValueError("generation requires a registered exact model with an execution profile")
    selected_execution_offering = select_offering(model_record, service)
    render_contract = compile_contract(model_record, selected_execution_offering,
        production_spec["render_intent"], parameters, prompt=composition_prompt,
        reference_count=1 if reference_set.get("single_board") else len(reference_set.get("selected_references") or []))
    parameters = render_contract["parameters"]
    service_summary: dict[str, Any] | None = None
    offering = None
    if model_record is not None:
        references = reference_set.get("selected_references") or []
        # The render contract has already resolved every applicable package control.
        offering = select_offering(model_record, service)
        media_counts: dict[str, int] | None = None
        if offering is not None:
            media_counts = generation_media_counts(
                offering, 1 if reference_set.get("single_board") else len(references),
                media_role=render_contract["model_card"]["execution_profile"]["modes"][production_spec["render_intent"]["execution_mode"]]["media"]
            )
        offering = validate_generation_parameters(
            model_record,
            parameters,
            service=service,
            pack_root=model_pack_root(model_id),
            prompt=prompt,
            negative_prompt=negative_prompt if mode == "separate-field" else None,
            media_counts=media_counts,
        )
        if offering is not None:
            service_summary = {
                "id": offering["service"],
                "model_identifier": offering["model_identifier"],
                "observed_at": offering["observed_at"],
                "schema_snapshot": offering.get("schema_snapshot"),
            }
    elif service:
        raise ValueError(f"model {model!r} has no record here, so a request through {service!r} cannot be checked")
    lineage_mode = state_lineage.get("mode")
    if lineage_mode == "state-aware":
        if reference_selection is None:
            raise ValueError(
                "state-aware generation requires a finalized reference-selection, "
                "including when no references are selected"
            )
        for field in (
            "identity_contract_sha256",
            "era_contract_sha256",
            "appearance_variant_sha256",
            "state_snapshot_sha256",
        ):
            if reference_selection.get(field) != state_lineage.get(field):
                raise ValueError(
                    f"reference-selection {field} differs from state lineage"
                )
        if not isinstance(state_snapshot, dict) or state_snapshot.get("artifact_type") != "state-snapshot":
            raise ValueError(
                "state-aware generation requires the supplied state-snapshot; use "
                "build_state_generation_package.py for full graph validation"
            )
        snapshot_report = validate_artifact(state_snapshot)
        if not snapshot_report.get("ok"):
            raise ValueError(
                "invalid supplied state-snapshot: "
                + "; ".join(snapshot_report.get("errors", []))
            )
        if artifact_hash(state_snapshot) != state_lineage.get("state_snapshot_sha256"):
            raise ValueError("supplied state-snapshot hash differs from state lineage")
        if reference_selection.get("story_order") != state_snapshot.get("story_order"):
            raise ValueError(
                "reference-selection story_order differs from the supplied state-snapshot"
            )
    elif lineage_mode == "stateless":
        if state_snapshot is not None:
            raise ValueError("stateless generation must not supply a state-snapshot")
        if reference_selection is not None or reference_selection_hash is not None:
            raise ValueError("stateless generation must use a null reference-selection origin")
    else:
        raise ValueError(f"unsupported state lineage mode: {lineage_mode!r}")

    from prompt_plot import validate_prompt_plot

    if not isinstance(plot, dict):
        raise ValueError("generation requires the approved plot the picture was drawn from")
    plot_report = validate_prompt_plot(plot)
    if not plot_report["ok"]:
        raise ValueError("invalid plot: " + "; ".join(plot_report["errors"]))
    if not plot_report["approved"]:
        raise ValueError(
            "generation follows approval: "
            + ("; ".join(plot_report["approval_errors"]) or "the plot carries no approved block")
        )
    from prompt_retrieval import require_generation_retrieval
    require_generation_retrieval(retrieval_record, prompt=composition_prompt, plot=plot)
    retrieval_hash = sha256_json(retrieval_record)
    plot_hash = sha256_json(plot)

    if not isinstance(creative_intent, dict):
        raise ValueError("creative intent must be an object")
    from revision_contract import require_intent_revision
    require_intent_revision(creative_intent)
    creative_intent = dict(creative_intent)
    creative_intent["production_spec_sha256"] = production_spec_hash
    creative_intent["state_lineage_sha256"] = lineage_hash
    creative_intent.setdefault("style_family", "")
    selected_instruction = transport_instruction(mode)
    selected_channels = {
        "separate-field": "prompt_plus_negative_fields",
        "integrated-critical": "single_prompt_field",
        "native-subset": "prompt_plus_native_negative",
        "retained-only": "single_prompt_field",
    }
    if visual_continuity is None:
        raise ValueError('generation requires a visual continuity input')
    from visual_continuity import require as require_visual
    require_visual(visual_continuity, production_spec=production_spec,
                   prepared=reference_set,
                   root=visual_root or production_root or prepared_reference_root)
    visual_hash = sha256_json(visual_continuity)
    result = {
        "status": "ready",
        "model": model,
        "render_contract": render_contract,
        "source_brief": brief.strip(),
        "creative_intent": creative_intent,
        "production_spec": production_spec,
        "production_spec_sha256": production_spec_hash,
        "composition_prompt": composition_prompt,
        "retrieval_record": retrieval_record,
        "retrieval_record_sha256": retrieval_hash,
        "plot": plot,
        "plot_sha256": plot_hash,
        "state_lineage": state_lineage,
        "state_lineage_sha256": lineage_hash,
        "prepared_reference_set": reference_set,
        "prepared_reference_set_sha256": prepared_reference_set_hash,
        "generation_input_sha256": "",
        "generation_payload": {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "native_negative": native_negative,
            "transports": transports,
            "negative_transport": {
                "mode": mode,
                "channel": selected_channels[mode],
                "instruction": selected_instruction,
                "critical_avoidance_integrated": bool(critical_avoidance_integrated or integrated_prompt),
                "send_full_negative_verbatim": mode == "separate-field",
                "send_native_negative_verbatim": mode == "native-subset",
            },
            "negative_provenance": provenance,
            "prompt_recommendations": recommendation_audit,
            "parameters": parameters,
            "service": service_summary,
            "prompt_sha256": prompt_hash,
            "negative_prompt_sha256": negative_hash,
            "native_negative_sha256": native_hash,
            "prompt_recommendations_sha256": sha256_json(recommendation_audit),
        },
        "generation_contract": {
            "forward_verified_prompt_transport": True,
            "forward_verified_negative_transport": True,
            "forward_ordered_reference_transports": True,
            "do_not_reconstruct_from_chat": True,
            "negative_transport_mode": mode,
            "prompt_sha256": prompt_hash,
            "negative_prompt_sha256": negative_hash,
            "native_negative_sha256": native_hash,
            "prompt_recommendations_sha256": sha256_json(recommendation_audit),
            "production_spec_sha256": production_spec_hash,
            "plot_sha256": plot_hash,
            "retrieval_record_sha256": retrieval_hash,
            "state_lineage_sha256": lineage_hash,
            "prepared_reference_set_sha256": prepared_reference_set_hash,
            "generation_input_sha256": "",
            "negative_transport_instruction": selected_instruction,
        },
    }
    from production_binding import create as create_production_binding
    result["visual_continuity"] = visual_continuity
    result["visual_continuity_sha256"] = visual_hash
    result["generation_contract"]["visual_continuity_sha256"] = visual_hash
    result["route_reading"] = route_reading
    result["route_reading_sha256"] = reading_hash
    result["generation_contract"]["route_reading_sha256"] = reading_hash
    result["production_binding"] = create_production_binding(production_root, production_run, composition_prompt)
    if request_validation is None:
        raise ValueError('generation requires an explicit request validation record')
    import input_contracts
    reader, _ = input_contracts.capture_validation(request_validation, root=input_root or production_root or visual_root or prepared_reference_root)
    reader.basis(visual_continuity['basis'])
    input_contracts.attach(result, request_validation, reader)
    from request_renderer import prepare_forwarding
    selected_key = {'separate-field':'separate','native-subset':'native_subset','integrated-critical':'integrated','retained-only':'integrated'}[mode]
    result_forward = prepare_forwarding(result, {'selected_transport': {'mode':mode, 'rendition':transports[selected_key]},
        'host_forwarding': {}}, root=input_root or production_root or visual_root or prepared_reference_root,
        model_id=model_id, model=model_record, offering=offering)
    reader.snapshots.update(result_forward['input_snapshots'])
    input_contracts.attach(result, request_validation, reader)
    generation_input_hash = generation_input_sha256(result)
    result["generation_input_sha256"] = generation_input_hash
    result["generation_contract"]["generation_input_sha256"] = generation_input_hash
    return result


def _resolve_reference_carrier(stored_path: Any, *, source_root: Path) -> Path:
    if not isinstance(stored_path, str) or not stored_path:
        raise ValueError("reference carrier path must be a non-empty string")
    candidate = Path(stored_path)
    if candidate.is_absolute():
        return candidate.resolve(strict=True)
    root = Path(source_root).resolve(strict=True)
    resolved = (root / candidate).resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("package-relative reference carrier escapes its source root") from exc
    return resolved


def _copy_reference_carrier(
    *,
    stored_path: Any,
    expected_sha256: str,
    media_type: str,
    source_root: Path,
    staging_root: Path,
    companion_name: str,
    relative_destination: Path,
) -> str:
    source = _resolve_reference_carrier(stored_path, source_root=source_root)
    if sha256_file(source) != expected_sha256:
        raise ValueError(f"reference carrier changed before staging: {source}")
    suffix = MEDIA_SUFFIXES.get(media_type)
    if suffix is None:
        raise ValueError(f"unsupported reference carrier media type: {media_type!r}")
    destination_relative = relative_destination.with_suffix(suffix)
    destination = staging_root / companion_name / destination_relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The package commits exact carrier bytes, not source filesystem metadata.
    # copy2 would propagate a Windows read-only attribute into the transaction
    # staging tree, where it can prevent rollback cleanup and mask the actual
    # build failure. A newly created destination inherits only normal staging
    # permissions and therefore never requires mutating the source to clean up.
    with source.open("rb") as source_stream, destination.open("xb") as destination_stream:
        shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)
    if sha256_file(destination) != expected_sha256:
        raise ValueError(f"staged reference carrier hash mismatch: {destination}")
    return (Path(companion_name) / destination_relative).as_posix()


def remove_cli_package_staging(staging_root: Path) -> None:
    """Remove only transaction-owned staging, retrying Windows read-only entries."""

    root = Path(staging_root).resolve(strict=True)

    def retry_writable(function: Any, path: str, exc_info: Any) -> None:
        candidate = Path(path).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            raise exc_info[1]
        try:
            current = stat.S_IMODE(candidate.lstat().st_mode)
            writable = current | stat.S_IWUSR | stat.S_IRUSR
            if candidate.is_dir():
                writable |= stat.S_IXUSR
            os.chmod(candidate, writable)
        except OSError:
            pass
        function(path)

    shutil.rmtree(root, onerror=retry_writable)


def generation_package_recovery_path(error: BaseException | None) -> Path | None:
    """Return transaction staging that must survive an incomplete rollback."""

    if error is None:
        return None
    stored = getattr(error, _RECOVERY_STAGING_ATTRIBUTE, None)
    return Path(stored) if isinstance(stored, str) and stored else None


def generation_package_error_messages(error: BaseException) -> list[str]:
    """Serialize the primary failure and every rollback/cleanup note in order, each once."""

    messages = list(dict.fromkeys(getattr(error, "errors", None) or [str(error)]))
    messages.extend(
        str(note)
        for note in getattr(error, "__notes__", ())
        if str(note) and str(note) not in messages
    )
    return messages


def materialize_cli_reference_bundle(
    prepared_reference_set: dict[str, Any],
    *,
    model: str,
    source_root: Path,
    staging_root: Path,
    companion_name: str,
) -> tuple[dict[str, Any], Path | None]:
    """Copy every portable carrier and return a set rebased to the final companion name."""

    validated = validate_prepared_reference_set(
        prepared_reference_set,
        model=model,
        package_root=source_root,
    )
    selected = copy.deepcopy(validated["selected_references"])
    prompt_artifacts = copy.deepcopy(validated["prompt_artifacts"])
    board = copy.deepcopy(validated["single_board"])
    carrier_count = 0
    sources = [row['source'] for row in selected]
    if validated['reference_use_plan'] is not None:
        sources.extend(item['source'] for item in validated['reference_use_plan']['reference_items'])
    for source in sources:
        import execution_contract as execution
        raw = execution.read(Path(source['resolved_path']))
        if execution.digest(raw) != source['sha256']:
            raise ValueError('reference source changed while recording its snapshot')
        destination = staging_root / companion_name / 'sources' / source['sha256']
        if destination.exists():
            if execution.read(destination) != raw:
                raise ValueError('recorded source collision')
        else:
            execution.atomic(destination, raw)
    for index, row in enumerate(selected):
        transport = row["transport"]
        transport["resolved_path"] = _copy_reference_carrier(
            stored_path=transport["resolved_path"],
            expected_sha256=transport["sha256"],
            media_type=transport["media_type"],
            source_root=source_root,
            staging_root=staging_root,
            companion_name=companion_name,
            relative_destination=Path("model-references")
            / f"{index:03d}-{transport['sha256'][:16]}",
        )
        carrier_count += 1
    for index, artifact in enumerate(prompt_artifacts):
        artifact["delivered_path"] = _copy_reference_carrier(
            stored_path=artifact["delivered_path"],
            expected_sha256=artifact["delivered_sha256"],
            media_type=artifact["media_type"],
            source_root=source_root,
            staging_root=staging_root,
            companion_name=companion_name,
            relative_destination=Path("prompt-artifacts")
            / f"{index:03d}-{artifact['delivered_sha256'][:16]}",
        )
        carrier_count += 1
    if board is not None:
        board["resolved_path"] = _copy_reference_carrier(
            stored_path=board["resolved_path"],
            expected_sha256=board["sha256"],
            media_type=board["media_type"],
            source_root=source_root,
            staging_root=staging_root,
            companion_name=companion_name,
            relative_destination=Path("board")
            / f"reference-board-{board['sha256'][:16]}",
        )
        carrier_count += 1
    rebased = build_prepared_reference_set(
        transport_mode=validated["transport_mode"],
        target_model=validated["target_model"],
        selected_references=selected,
        reference_selection=validated["reference_selection"],
        reference_use_plan=validated["reference_use_plan"],
        zero_reference_reason=validated["zero_reference_reason"],
        prompt_artifacts=prompt_artifacts,
        single_board=board,
        package_root=staging_root,
    )
    companion = staging_root / companion_name
    return rebased, (companion if carrier_count else None)


def create_cli_package_staging(output_path: Path) -> tuple[Path, Path, Path, Path]:
    output = Path(output_path).resolve()
    parent = output.parent
    if not parent.is_dir():
        raise ValueError(f"generation package parent does not exist: {parent}")
    if output.exists() and not output.is_file():
        raise ValueError(f"generation package output is not a regular file: {output}")
    companion = output.with_name(output.stem + ".references")
    if companion.exists():
        raise ValueError(f"generation package companion already exists: {companion}")
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{output.stem}-generation-package-", dir=parent)
    )
    return staging_root, staging_root / output.name, staging_root / companion.name, companion


def publish_cli_generation_package(
    *,
    output_path: Path,
    staged_json: Path,
    staged_companion: Path | None,
    final_companion: Path,
    staging_root: Path,
) -> None:
    """Publish JSON and its companion as one rollback-protected transaction."""

    output = Path(output_path).resolve()
    if final_companion.exists():
        raise ValueError(f"generation package companion already exists: {final_companion}")
    previous = staging_root / ".previous-generation-package.json"
    had_previous = output.is_file()
    companion_published = False
    try:
        if had_previous:
            os.replace(output, previous)
        if staged_companion is not None:
            os.replace(staged_companion, final_companion)
            companion_published = True
        os.replace(staged_json, output)
    except Exception as original_error:
        rollback_errors: list[Exception] = []
        if companion_published and final_companion.exists():
            try:
                os.replace(final_companion, staged_companion)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
        if previous.exists():
            try:
                os.replace(previous, output)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
        for rollback_error in rollback_errors:
            original_error.add_note(
                "generation package rollback also failed: "
                f"{type(rollback_error).__name__}: {rollback_error}"
            )
        if rollback_errors:
            recovery_root = staging_root.resolve()
            setattr(
                original_error,
                _RECOVERY_STAGING_ATTRIBUTE,
                str(recovery_root),
            )
            original_error.add_note(
                "generation package rollback is incomplete; recovery staging was "
                f"preserved at {recovery_root}"
            )
        raise


def add_production_arguments(parser: argparse.ArgumentParser) -> None:
    """Name the prepared run and the decisions a builder cannot derive from it."""
    parser.add_argument("--production-root", type=Path, required=True,
                        help="Studio root holding the prepared production run and the project's input evidence")
    parser.add_argument("--production-run", help="Prepared run; the open work task's current run when omitted")
    parser.add_argument("--request-validation-file",
                        help="Request check with its own evidence and execution policy; when omitted, the builder "
                        "derives it from the observed schema the active pack's offering names")
    parser.add_argument("--visual-continuity-file",
                        help="Complete visual continuity record; when omitted, --continuity states the decisions")
    parser.add_argument("--continuity", action="append", default=[], metavar="SUBJECT=DECISION",
                        help="once for each production subject: one-off; undecided for the first images of a "
                        "character that may recur; recurring once the author has accepted an identity image")
    parser.add_argument("--character", action="append", default=[], metavar="SUBJECT=CHARACTER",
                        help="The studio character a subject is recorded under; required for a recurring subject")
    parser.add_argument("--sheet-panel", action="store_true", help="The image fills a character sheet panel")


def _subject_values(values: Sequence[str], flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        subject, separator, item = value.partition("=")
        if not separator or not subject or not item or subject in result:
            raise ValueError(f"{flag} takes SUBJECT=VALUE, once for each subject")
        result[subject] = item
    return result


def production_inputs(
    args: argparse.Namespace,
    *,
    model: str,
    production_spec: dict[str, Any],
    prepared_reference_set: dict[str, Any] | None,
    staging_root: Path,
    work_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Read the prepared run and derive every input the author did not write.

    The route reading comes from the run. The request check comes from the active
    pack's offering unless a record is supplied. Visual continuity is built from
    the stated decisions unless a record is supplied.
    """
    import production_workflow
    import work_ledger
    from route_reading import copy_issuance, ledger_candidates

    root = args.production_root.absolute()
    run = args.production_run or work_ledger.require_open(root).get("production_run")
    if not run:
        raise ValueError("the open work task has no prepared production run; prepare one first")
    _, prepared, consumer, _ = production_workflow.assert_current(root, run)
    reading = prepared["route_reading"]
    copy_issuance(reading, staging_root / "reads.jsonl", ledgers=ledger_candidates(project=root))
    reference_set = prepared_reference_set if prepared_reference_set is not None else empty_stateless_reference_set()

    stated = bool(args.continuity or args.character or args.sheet_panel)
    if args.visual_continuity_file:
        if stated:
            raise ValueError("--visual-continuity-file already states continuity; drop --continuity, --character and --sheet-panel")
        visual = read_json(args.visual_continuity_file)
    else:
        if not args.continuity:
            raise ValueError("state each production subject's continuity with --continuity SUBJECT=DECISION")
        from visual_continuity import from_decisions
        visual = from_decisions(
            _subject_values(args.continuity, "--continuity"), production_spec=production_spec,
            prepared=reference_set, root=root, characters=_subject_values(args.character, "--character"),
            work_ids=work_ids, sheet_panel=args.sheet_panel,
        )

    if args.request_validation_file:
        validation = read_json(args.request_validation_file)
    else:
        if reference_set.get("selected_references") or reference_set.get("single_board"):
            raise ValueError("a package with references needs --request-validation-file with its execution policy")
        if consumer["transport"] != "authored-rendition":
            raise ValueError("bounded production context needs --request-validation-file with its execution policy")
        import runtime_evidence
        import service_profile
        import transport_contract
        from catalog_retrieval.runtime import load_pack_catalog
        from request_validation import from_offering

        model_id, record = resolve_model_record(model)
        offering = select_offering(record, getattr(args, "service", None))
        if offering is None:
            raise ValueError(f"model record {model_id!r} is exposed on no service here; supply --request-validation-file")
        resource = load_pack_catalog().resources.get("service-profiles")
        if resource is None:
            raise ValueError("the active packs provide no service-profiles resource")
        try:
            service = service_profile.load_service(offering["service"], Path(resource.path))
        except service_profile.PackError as exc:
            raise ValueError(str(exc)) from exc
        transport = transport_contract.load(service["transport"])
        validation = from_offering(model_id, record, offering, service, transport, runtime_evidence.reader(root))
    return {"root": root, "run": run, "route_reading": reading,
            "visual_continuity": visual, "request_validation": validation}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an exact Character Prompt Builder generation payload.")
    parser.add_argument("--model", default="gpt-image-2.5-flare")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--negative-file")
    parser.add_argument(
        "--integrated-prompt-file",
        help=(
            "Agent-authored affirmative rendition for single-prompt interfaces. "
            "Required whenever a portable negative exists unless the primary prompt "
            "is certified with --critical-avoidance-integrated."
        ),
    )
    parser.add_argument("--native-negative-file", help="Concise native negative subset, for example a Midjourney --no payload")
    parser.add_argument("--negative-provenance-file", help="JSON object listing activated, retained, and translated negative sources")
    parser.add_argument(
        "--negative-transport",
        choices=sorted(TRANSPORT_MODES),
        default="auto",
        help="How the named target interface receives avoidance instructions.",
    )
    parser.add_argument(
        "--critical-avoidance-integrated",
        action="store_true",
        help="Certify that the primary positive prompt already contains the critical affirmative construction requirements.",
    )
    parser.add_argument("--brief", default="")
    parser.add_argument("--brief-file")
    parser.add_argument("--intent-file", help="JSON containing image_promise, chosen_direction, and related notes")
    parser.add_argument("--production-spec-file", required=True, help="Reviewed Production Specification JSON")
    parser.add_argument("--plot-file", required=True, help="The approved plot this picture was drawn from")
    parser.add_argument("--retrieval-record-file", required=True, help="Settled retrieval record bound to this authored prompt and plot")
    parser.add_argument("--state-lineage-file", help="Optional Shared State Protocol lineage JSON; omitted means stateless")
    parser.add_argument(
        "--references-file",
        help=(
            "Canonical prepared-reference-set JSON produced by reference_runtime.py "
            "or the supplied-file preparer."
        ),
    )
    parser.add_argument("--parameters", default="{}", help="JSON object with model parameters")
    parser.add_argument(
        "--service",
        help="The service the request goes through, by its key in the service-profiles resource; "
        "needed only when the model record is exposed on more than one",
    )
    add_pack_runtime_arguments(parser)
    parser.add_argument("--out", required=True)
    add_production_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    staging_root: Path | None = None
    pending_error: BaseException | None = None
    payload: dict[str, Any] | None = None
    try:
        brief = read_text(args.brief_file) if args.brief_file else args.brief
        parameters = parse_json(args.parameters)
        if not isinstance(parameters, dict):
            raise ValueError("--parameters must be a JSON object")
        state_lineage_input = read_json(args.state_lineage_file)
        if state_lineage_input.get("mode") == "state-aware":
            raise ValueError(
                "build_generation_payload.py is the stateless CLI; use "
                "build_state_generation_package.py for a state-aware artifact graph"
            )
        output_path = Path(args.out).resolve()
        staging_root, staged_json, _staged_companion_path, final_companion = (
            create_cli_package_staging(output_path)
        )
        staged_reference_set: dict[str, Any] | None = None
        staged_companion: Path | None = None
        if args.references_file:
            references_path = Path(args.references_file).resolve(strict=True)
            source_reference_set = read_json(str(references_path))
            staged_reference_set, staged_companion = materialize_cli_reference_bundle(
                source_reference_set,
                model=args.model,
                source_root=references_path.parent,
                staging_root=staging_root,
                companion_name=final_companion.name,
            )
        production_spec = read_json(args.production_spec_file)
        derived = production_inputs(args, model=args.model, production_spec=production_spec,
                                    prepared_reference_set=staged_reference_set, staging_root=staging_root)
        payload = build_payload(
            plot=read_json(args.plot_file),
            retrieval_record=read_json(args.retrieval_record_file),
            request_validation=derived["request_validation"], input_root=derived["root"],
            route_reading=derived["route_reading"],
            visual_continuity=derived["visual_continuity"],
            visual_root=derived["root"],
            reading_ledgers=[staging_root / "reads.jsonl"],
            model=args.model,
            prompt=read_text(args.prompt_file),
            negative_prompt=read_text(args.negative_file),
            integrated_prompt=read_text(args.integrated_prompt_file),
            native_negative=read_text(args.native_negative_file),
            negative_provenance=read_json(args.negative_provenance_file),
            brief=brief,
            creative_intent=read_json(args.intent_file),
            production_spec=production_spec,
            state_lineage=state_lineage_input,
            prepared_reference_set=staged_reference_set,
            prepared_reference_root=staging_root,
            parameters=parameters,
            negative_transport=args.negative_transport,
            critical_avoidance_integrated=args.critical_avoidance_integrated,
            service=args.service,
            production_root=derived["root"],
            production_run=derived["run"],
        )
        # Writing is the commit point. Re-read every selected reference and verify
        # the exact package contract before creating or replacing the output file.
        from verify_generation_payload import verify

        verify(payload, package_root=staging_root, project=derived["root"])
        staged_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        from route_reading import copy_issuance
        copy_issuance(derived["route_reading"], output_path.parent / "reads.jsonl", ledgers=[staging_root / "reads.jsonl"])
        publish_cli_generation_package(
            output_path=output_path,
            staged_json=staged_json,
            staged_companion=staged_companion,
            final_companion=final_companion,
            staging_root=staging_root,
        )
    except (ValueError, OSError) as error:
        pending_error = error
    except BaseException as error:
        pending_error = error
        raise
    finally:
        try:
            if (
                staging_root is not None
                and staging_root.exists()
                and generation_package_recovery_path(pending_error) is None
            ):
                try:
                    remove_cli_package_staging(staging_root)
                except Exception as cleanup_error:
                    if pending_error is None:
                        raise
                    location = (
                        f"; transaction staging remains at {staging_root.resolve()}"
                        if staging_root.exists()
                        else ""
                    )
                    pending_error.add_note(
                        "generation package staging cleanup also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}{location}"
                    )
        finally:
            configure_pack_runtime(None)
    if pending_error is not None:
        print(json.dumps({"ok": False, "errors": generation_package_error_messages(pending_error)},
                         ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    if payload is None:
        raise RuntimeError("generation package completed without a payload")
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
