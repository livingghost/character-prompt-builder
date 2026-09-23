#!/usr/bin/env python3
"""Verify and export an exact Character Prompt Builder generation payload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from build_generation_payload import (
    generation_input_sha256,
    require_concrete_sha256,
    sha256_json,
    sha256_text,
    validate_generation_package_carrier_paths,
)
from catalog_cli import configure_pack_runtime
from model_contract import generation_media_counts, select_offering, validate_generation_parameters
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from prepare_generation_references import (
    host_reference_transports,
    validate_prepared_reference_set,
)
from state_protocol import find_non_finite_numbers, parse_json

VALID_MODES = {"separate-field", "integrated-critical", "native-subset", "retained-only"}
VALID_INTEGRATED_METHODS = {
    "authored-affirmative",
    "primary-prompt-certified",
    "no-negative-required",
    "unavailable",
}
VALID_NATIVE_METHODS = {"verbatim-native-subset", "no-negative-required", "unavailable"}
GENERATION_CONTRACT_FIELDS = {
    "route_reading_sha256", "visual_continuity_sha256", "request_validation_sha256", "input_snapshots_sha256",
    "forward_verified_prompt_transport",
    "forward_verified_negative_transport",
    "forward_ordered_reference_transports",
    "do_not_reconstruct_from_chat",
    "negative_transport_mode",
    "prompt_sha256",
    "negative_prompt_sha256",
    "native_negative_sha256",
    "production_spec_sha256",
    "plot_sha256",
    "retrieval_record_sha256",
    "state_lineage_sha256",
    "prepared_reference_set_sha256",
    "generation_input_sha256",
    "negative_transport_instruction",
    "prompt_recommendations_sha256",
}
GENERATION_PACKAGE_FIELDS = {
    "route_reading", "route_reading_sha256", "visual_continuity", "visual_continuity_sha256",
    "request_validation", "request_validation_sha256", "input_snapshots", "input_snapshots_sha256",
    "production_binding",
    "status",
    "model",
    "source_brief",
    "composition_prompt",
    "retrieval_record",
    "creative_intent",
    "production_spec",
    "production_spec_sha256",
    "plot",
    "plot_sha256",
    "retrieval_record_sha256",
    "state_lineage",
    "state_lineage_sha256",
    "prepared_reference_set",
    "prepared_reference_set_sha256",
    "generation_input_sha256",
    "generation_payload",
    "generation_contract",
}
GENERATION_PAYLOAD_FIELDS = {
    "prompt",
    "negative_prompt",
    "native_negative",
    "transports",
    "negative_transport",
    "negative_provenance",
    "prompt_recommendations",
    "parameters",
    "service",
    "prompt_sha256",
    "negative_prompt_sha256",
    "native_negative_sha256",
    "prompt_recommendations_sha256",
}
TRANSPORTS_FIELDS = {"separate", "integrated", "native_subset", "paste_instructions"}
SEPARATE_FIELDS = {
    "available",
    "channel",
    "method",
    "prompt",
    "negative",
    "prompt_sha256",
    "negative_sha256",
}
INTEGRATED_FIELDS = {"available", "channel", "method", "text", "sha256"}
NATIVE_FIELDS = {
    "available",
    "channel",
    "method",
    "prompt",
    "negative",
    "prompt_sha256",
    "negative_sha256",
}
PASTE_INSTRUCTION_FIELDS = {
    "single_prompt_field",
    "prompt_plus_negative_fields",
    "prompt_plus_native_negative",
}
NEGATIVE_TRANSPORT_FIELDS = {
    "mode",
    "channel",
    "instruction",
    "critical_avoidance_integrated",
    "send_full_negative_verbatim",
    "send_native_negative_verbatim",
}
NEGATIVE_PROVENANCE_FIELDS = {
    "activated_sources",
    "diagnostic_sources_retained",
    "semantic_exclusions_user_supplied",
    "affirmative_translations",
}


def _require_exact_fields(value: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual == expected:
        return
    details: list[str] = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unexpected " + ", ".join(extra))
    raise ValueError(f"{field} has an invalid shape (" + "; ".join(details) + ")")

def load_payload(path: Path) -> dict[str, Any]:
    data = parse_json(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def verify_transports(data: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    gp = data.get("generation_payload")
    if not isinstance(gp, dict):
        return ["generation_payload is missing"], {}
    transports = gp.get("transports")
    if not isinstance(transports, dict):
        return ["payload has no transports block"], {}
    try:
        _require_exact_fields(transports, TRANSPORTS_FIELDS, "generation_payload.transports")
    except ValueError as exc:
        errors.append(str(exc))
    prompt = str(gp.get("prompt") or "")
    negative = str(gp.get("negative_prompt") or "")
    native_negative = str(gp.get("native_negative") or "")

    separate = transports.get("separate")
    if not isinstance(separate, dict) or separate.get("available") is not True:
        errors.append("separate transport is unavailable")
    else:
        try:
            _require_exact_fields(separate, SEPARATE_FIELDS, "transports.separate")
        except ValueError as exc:
            errors.append(str(exc))
        if separate.get("channel") != "prompt_plus_negative_fields":
            errors.append("separate transport channel is invalid")
        if separate.get("method") != "verbatim-separate-fields":
            errors.append("separate transport method is invalid")
        if str(separate.get("prompt") or "") != prompt:
            errors.append("separate transport prompt differs from primary prompt")
        if str(separate.get("negative") or "") != negative:
            errors.append("separate transport negative differs from portable negative")
        if sha256_text(str(separate.get("prompt") or "")) != separate.get("prompt_sha256"):
            errors.append("separate transport prompt hash mismatch")
        if sha256_text(str(separate.get("negative") or "")) != separate.get("negative_sha256"):
            errors.append("separate transport negative hash mismatch")

    integrated = transports.get("integrated")
    if not isinstance(integrated, dict):
        errors.append("integrated transport is missing")
    else:
        try:
            _require_exact_fields(integrated, INTEGRATED_FIELDS, "transports.integrated")
        except ValueError as exc:
            errors.append(str(exc))
        available = integrated.get("available") is True
        method = str(integrated.get("method") or "")
        text = str(integrated.get("text") or "")
        if integrated.get("channel") != "single_prompt_field":
            errors.append("integrated transport channel is invalid")
        if method not in VALID_INTEGRATED_METHODS:
            errors.append("integrated transport method is invalid")
        if available and not text:
            errors.append("integrated transport is marked available but empty")
        if not available and text:
            errors.append("unavailable integrated transport contains text")
        if sha256_text(text) != integrated.get("sha256"):
            errors.append("integrated transport hash mismatch")
        if method in {"primary-prompt-certified", "no-negative-required"} and text != prompt:
            errors.append("certified integrated transport differs from primary prompt")
        if negative and not available:
            errors.append("negative-bearing payload has no affirmative integrated transport")

    native = transports.get("native_subset")
    if not isinstance(native, dict):
        errors.append("native-subset transport is missing")
    else:
        try:
            _require_exact_fields(native, NATIVE_FIELDS, "transports.native_subset")
        except ValueError as exc:
            errors.append(str(exc))
        available = native.get("available") is True
        method = str(native.get("method") or "")
        nprompt = str(native.get("prompt") or "")
        nnegative = str(native.get("negative") or "")
        if method not in VALID_NATIVE_METHODS:
            errors.append("native-subset transport method is invalid")
        if available:
            if native.get("channel") != "prompt_plus_native_negative":
                errors.append("native-subset transport channel is invalid")
            if nprompt != prompt:
                errors.append("native-subset prompt differs from primary prompt")
            if nnegative != native_negative:
                errors.append("native-subset negative differs from declared native negative")
        elif nprompt or nnegative:
            errors.append("unavailable native-subset transport contains text")
        if not available and native_negative:
            errors.append("declared native negative has no available native-subset transport")
        if method == "verbatim-native-subset" and not nnegative:
            errors.append("verbatim native-subset transport is empty")
        if method == "no-negative-required" and (negative or nnegative):
            errors.append("no-negative-required native transport contains an avoidance payload")
        if sha256_text(nprompt) != native.get("prompt_sha256"):
            errors.append("native-subset prompt hash mismatch")
        if sha256_text(nnegative) != native.get("negative_sha256"):
            errors.append("native-subset negative hash mismatch")

    instructions = transports.get("paste_instructions")
    if not isinstance(instructions, dict):
        errors.append("transport paste instructions are missing")
    else:
        try:
            _require_exact_fields(
                instructions,
                PASTE_INSTRUCTION_FIELDS,
                "transports.paste_instructions",
            )
        except ValueError as exc:
            errors.append(str(exc))
        for channel in (
            "single_prompt_field",
            "prompt_plus_negative_fields",
            "prompt_plus_native_negative",
        ):
            if not isinstance(instructions.get(channel), str) or not instructions[channel].strip():
                errors.append(f"transport paste instruction is missing: {channel}")

    provenance = gp.get("negative_provenance")
    if isinstance(provenance, dict):
        translations = provenance.get("affirmative_translations", {})
        if not isinstance(translations, dict):
            errors.append("negative provenance affirmative_translations is invalid")
        elif translations:
            integrated_text = str((integrated or {}).get("text") or "")
            for source, translated_text in translations.items():
                if not isinstance(source, str) or not isinstance(translated_text, str) or not translated_text.strip():
                    errors.append("affirmative translation entry is invalid")
                    continue
                if translated_text not in integrated_text:
                    errors.append(f"declared affirmative coverage for `{source}` is absent from the integrated rendition")
    return errors, transports


def _selected_rendition(mode: str, transports: dict[str, Any]) -> dict[str, Any]:
    key = {
        "separate-field": "separate",
        "integrated-critical": "integrated",
        "native-subset": "native_subset",
        "retained-only": "integrated",
    }[mode]
    rendition = transports.get(key)
    if not isinstance(rendition, dict) or rendition.get("available") is not True:
        raise ValueError(f"selected transport rendition is unavailable: {key}")
    return rendition


def _verify(
    data: dict[str, Any],
    *,
    package_root: Path | None = None,
    live: bool,
    project: Path | None = None,
    reading_ledgers: list[Path] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("generation package must be an object")
    _require_exact_fields(data, GENERATION_PACKAGE_FIELDS, "generation package")
    import input_contracts
    input_reader, validation_report = input_contracts.verify_fields(data, root=project or package_root, live=live)
    input_reader.basis(data['visual_continuity']['basis'])
    for field in ('request_validation_sha256','input_snapshots_sha256'):
        if data['generation_contract'].get(field) != data[field]:
            raise ValueError('generation contract '+field+' mismatch')
    from route_reading import require_route_reading, validate_record_content, GENERATION_ROUTES
    validate_record_content(data["route_reading"])
    if live:
        require_route_reading(data["route_reading"], project=project, ledgers=reading_ledgers,
                              package_root=package_root, routes=GENERATION_ROUTES)
    reading_hash = sha256_json(data["route_reading"])
    if data["route_reading_sha256"] != reading_hash or data["generation_contract"].get("route_reading_sha256") != reading_hash:
        raise ValueError("route reading hash mismatch")
    if (data.get("state_lineage") or {}).get("mode") == "state-aware":
        if data["route_reading"]["route"] != "state-series" and "state-series" not in data["route_reading"]["features"]:
            raise ValueError("state-aware generation requires the state-series reading")
    from production_binding import validate as validate_production_binding
    validate_production_binding(data["production_binding"], data.get("composition_prompt", ""))
    non_finite = find_non_finite_numbers(data)
    if non_finite:
        raise ValueError("non-finite numbers are not permitted: " + ", ".join(non_finite))
    if data.get("status") != "ready":
        raise ValueError("payload status is not ready")
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    payload = data.get("generation_payload")
    contract = data.get("generation_contract")
    if not isinstance(payload, dict) or not isinstance(contract, dict):
        raise ValueError("generation payload or contract is missing")
    _require_exact_fields(payload, GENERATION_PAYLOAD_FIELDS, "generation payload")
    _require_exact_fields(contract, GENERATION_CONTRACT_FIELDS, "generation contract")
    selected_transport_declaration = payload.get("negative_transport")
    if not isinstance(selected_transport_declaration, dict):
        raise ValueError("negative transport declaration is missing")
    _require_exact_fields(
        selected_transport_declaration,
        NEGATIVE_TRANSPORT_FIELDS,
        "generation_payload.negative_transport",
    )
    provenance_shape = payload.get("negative_provenance")
    if not isinstance(provenance_shape, dict):
        raise ValueError("negative provenance declaration is missing")
    _require_exact_fields(
        provenance_shape,
        NEGATIVE_PROVENANCE_FIELDS,
        "generation_payload.negative_provenance",
    )
    recommendation_audit = payload.get("prompt_recommendations")
    if not isinstance(recommendation_audit, dict):
        raise ValueError("prompt recommendation audit is missing")
    _require_exact_fields(
        recommendation_audit,
        {
            "resolved_model_id",
            "merge_mode",
            "positive",
            "negative",
            "integrated",
            "negative_preset",
        },
        "generation_payload.prompt_recommendations",
    )
    recommendation_entry_fields = {
        "declared", "applied", "mode", "reason", "recommended_text", "source_text", "limit", "segments"
    }
    for name in ("positive", "negative"):
        entry = recommendation_audit.get(name)
        if not isinstance(entry, dict):
            raise ValueError(f"prompt recommendation {name} audit is invalid")
        _require_exact_fields(
            entry, recommendation_entry_fields,
            f"generation_payload.prompt_recommendations.{name}",
        )
    integrated_audit = recommendation_audit.get("integrated")
    if integrated_audit is not None:
        if not isinstance(integrated_audit, dict):
            raise ValueError("integrated prompt recommendation audit is invalid")
        _require_exact_fields(
            integrated_audit, recommendation_entry_fields,
            "generation_payload.prompt_recommendations.integrated",
        )
    from model_contract import validate_recommendation_audit
    validate_recommendation_audit(recommendation_audit['positive'],payload['prompt'])
    validate_recommendation_audit(recommendation_audit['negative'],payload['negative_prompt'])
    if integrated_audit is not None:
        validate_recommendation_audit(integrated_audit,payload['transports']['integrated']['text'])
    recommendation_hash = sha256_json(recommendation_audit)
    for location, value in (
        (
            "generation_payload.prompt_recommendations_sha256",
            payload.get("prompt_recommendations_sha256"),
        ),
        (
            "generation_contract.prompt_recommendations_sha256",
            contract.get("prompt_recommendations_sha256"),
        ),
    ):
        if require_concrete_sha256(value, location) != recommendation_hash:
            raise ValueError(f"{location} mismatch")
    for field in (
        "forward_verified_prompt_transport",
        "forward_verified_negative_transport",
        "forward_ordered_reference_transports",
        "do_not_reconstruct_from_chat",
    ):
        if contract.get(field) is not True:
            raise ValueError(f"generation contract flag is disabled: {field}")

    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("generation parameters must be an object")
    model_id = model
    model_record = None
    offering = None
    if live:
        try:
            from build_generation_payload import resolve_model_record
    
            model_id, model_record = resolve_model_record(model)
        except ValueError:
            model_id = model
            model_record = None
        if model_record is not None:
            if model_record.get("operation_kind") == "upscale":
                raise ValueError(
                    f"model record {model_id!r} is an upscaler and is invalid in a Generation Package"
                )
            from prepare_generation_references import model_pack_root
    
            # The same check the builder made, from what the package carries: the
            # record's limits, then the offering's observed schema over the request
            # as the service would see it.
            reference_set = data.get("prepared_reference_set") or {}
            references = reference_set.get("selected_references") or [] if isinstance(reference_set, dict) else []
            mode = (payload.get("negative_transport") or {}).get("mode")
            declared = payload.get("service")
            if declared is not None and not isinstance(declared, dict):
                raise ValueError("generation_payload.service must be an object or null")
            selected = select_offering(model_record, (declared or {}).get("id"))
            offering = validate_generation_parameters(
                model_record,
                parameters,
                service=(declared or {}).get("id"),
                pack_root=model_pack_root(model_id),
                prompt=str(payload.get("prompt") or ""),
                negative_prompt=str(payload.get("negative_prompt") or "") if mode == "separate-field" else None,
                media_counts=None if selected is None else generation_media_counts(
                    selected, 1 if reference_set.get("single_board") else len(references)
                ),
            )
            expected = None if offering is None else {
                "id": offering["service"],
                "model_identifier": offering["model_identifier"],
                "observed_at": offering["observed_at"],
                "schema_snapshot": offering.get("schema_snapshot"),
            }
            if declared != expected:
                raise ValueError(
                    f"generation_payload.service is {declared!r}, and the model record's offering says {expected!r}"
                )
            positive_limit = model_record.get("max_positive_prompt_chars")
            negative_limit = model_record.get("max_negative_prompt_chars")
            if isinstance(positive_limit, int) and len(str(payload.get("prompt") or "")) > positive_limit:
                raise ValueError("prompt exceeds the active model character limit")
            if isinstance(negative_limit, int) and len(str(payload.get("negative_prompt") or "")) > negative_limit:
                raise ValueError("negative prompt exceeds the active model character limit")
        if model_record is not None:
            require_route_reading(data['route_reading'], project=project, ledgers=reading_ledgers,
                package_root=package_root, routes=GENERATION_ROUTES,
                dialect=model_record.get('prompt_dialect'))
    prompt = payload.get("prompt")
    negative = payload.get("negative_prompt")
    native_negative = payload.get("native_negative")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("prompt is empty")
    if not isinstance(negative, str) or not isinstance(native_negative, str):
        raise ValueError("negative prompt fields must be strings")

    prompt_hash = sha256_text(prompt)
    negative_hash = sha256_text(negative)
    native_hash = sha256_text(native_negative)
    for location, actual in (
        ("generation_payload.prompt_sha256", prompt_hash),
        ("generation_contract.prompt_sha256", prompt_hash),
        ("generation_payload.negative_prompt_sha256", negative_hash),
        ("generation_contract.negative_prompt_sha256", negative_hash),
        ("generation_payload.native_negative_sha256", native_hash),
        ("generation_contract.native_negative_sha256", native_hash),
    ):
        owner_name, field_name = location.split(".")
        owner = payload if owner_name == "generation_payload" else contract
        expected = require_concrete_sha256(owner.get(field_name), location)
        if expected != actual:
            raise ValueError(f"{location} mismatch")

    production_spec = data.get("production_spec")
    if not isinstance(production_spec, dict) or not production_spec:
        raise ValueError("a complete production specification is required")
    from production_spec import validate as validate_production_spec

    spec_report = validate_production_spec(production_spec, require_content=True)
    if not spec_report.get("ok"):
        raise ValueError(
            "invalid production specification: "
            + "; ".join(spec_report.get("errors", []))
        )
    if production_spec.get("target_model") != model:
        raise ValueError("package model differs from production specification target_model")
    production_spec_hash = sha256_json(production_spec)
    require_concrete_sha256(production_spec_hash, "computed production_spec_sha256")
    for location, value in (
        ("production_spec_sha256", data.get("production_spec_sha256")),
        ("generation_contract.production_spec_sha256", contract.get("production_spec_sha256")),
    ):
        if require_concrete_sha256(value, location) != production_spec_hash:
            raise ValueError(f"{location} mismatch")

    from prompt_plot import validate_prompt_plot

    plot = data.get("plot")
    if not isinstance(plot, dict):
        raise ValueError("the package carries no plot")
    plot_report = validate_prompt_plot(plot)
    if not plot_report["ok"]:
        raise ValueError("invalid plot: " + "; ".join(plot_report["errors"]))
    if not plot_report["approved"]:
        raise ValueError(
            "the package plot is not approved: "
            + ("; ".join(plot_report["approval_errors"]) or "it carries no approved block")
        )
    from prompt_retrieval import require_generation_retrieval
    composition_prompt = data.get("composition_prompt")
    if not isinstance(composition_prompt, str) or not composition_prompt.strip():
        raise ValueError("composition_prompt must contain the original authored prompt")
    require_generation_retrieval(data.get("retrieval_record"), prompt=composition_prompt, plot=plot)
    retrieval_hash = sha256_json(data["retrieval_record"])
    for location, value in (
        ("retrieval_record_sha256", data.get("retrieval_record_sha256")),
        ("generation_contract.retrieval_record_sha256", contract.get("retrieval_record_sha256")),
    ):
        if require_concrete_sha256(value, location) != retrieval_hash:
            raise ValueError(f"{location} mismatch")
    plot_hash = sha256_json(plot)
    require_concrete_sha256(plot_hash, "computed plot_sha256")
    for location, value in (
        ("plot_sha256", data.get("plot_sha256")),
        ("generation_contract.plot_sha256", contract.get("plot_sha256")),
    ):
        if require_concrete_sha256(value, location) != plot_hash:
            raise ValueError(f"{location} mismatch")

    state_lineage = data.get("state_lineage")
    if not isinstance(state_lineage, dict):
        raise ValueError("state lineage must be an object")
    from state_protocol import validate_artifact

    lineage_report = validate_artifact(state_lineage)
    if not lineage_report.get("ok"):
        raise ValueError("invalid state lineage: " + "; ".join(lineage_report.get("errors", [])))
    lineage_hash = require_concrete_sha256(
        state_lineage.get("lineage_sha256"), "state_lineage.lineage_sha256"
    )
    for location, value in (
        ("state_lineage_sha256", data.get("state_lineage_sha256")),
        ("generation_contract.state_lineage_sha256", contract.get("state_lineage_sha256")),
    ):
        if require_concrete_sha256(value, location) != lineage_hash:
            raise ValueError(f"{location} mismatch")
    state_context = production_spec.get("state_context", {})
    if state_context.get("state_lineage_sha256") != lineage_hash:
        raise ValueError("production specification state-lineage hash mismatch")
    if state_context.get("mode") != state_lineage.get("mode"):
        raise ValueError("production specification state mode differs from lineage")

    from prepare_generation_references import validate_prepared_reference_content
    reference_validator = validate_prepared_reference_set if live else validate_prepared_reference_content
    reference_set = reference_validator(
        data.get("prepared_reference_set"),
        model=model,
        package_root=package_root,
    )
    validate_generation_package_carrier_paths(reference_set, package_root=package_root)
    from visual_continuity import validate_content as validate_visual_content, require as require_visual
    validate_visual_content(data['visual_continuity'], production_spec)
    visual_hash = sha256_json(data['visual_continuity'])
    if data['visual_continuity_sha256'] != visual_hash or contract['visual_continuity_sha256'] != visual_hash:
        raise ValueError('visual continuity hash mismatch')
    if live:
        require_visual(data['visual_continuity'], production_spec=production_spec,
                       prepared=reference_set, root=project or package_root)
    reference_set_hash = require_concrete_sha256(
        reference_set.get("prepared_reference_set_sha256"),
        "prepared_reference_set.prepared_reference_set_sha256",
    )
    if require_concrete_sha256(
        data.get("prepared_reference_set_sha256"), "prepared_reference_set_sha256"
    ) != reference_set_hash:
        raise ValueError("prepared_reference_set_sha256 mismatch")
    if require_concrete_sha256(
        contract.get("prepared_reference_set_sha256"),
        "generation_contract.prepared_reference_set_sha256",
    ) != reference_set_hash:
        raise ValueError("generation contract prepared-reference-set hash mismatch")
    if reference_set["transport_mode"] in {"prompt-artifacts", "svg-bundle"}:
        raise ValueError(
            f"{reference_set['transport_mode']} prepared references cannot be forwarded "
            "to model generation"
        )
    reference_selection = reference_set["reference_selection"]
    reference_selection_hash = reference_set["reference_selection_sha256"]
    lineage_mode = state_lineage.get("mode")
    if lineage_mode == "state-aware":
        if reference_selection is None or reference_selection_hash is None:
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
    elif lineage_mode == "stateless":
        if reference_selection is not None or reference_selection_hash is not None:
            raise ValueError("stateless generation must use a null reference-selection origin")
    else:
        raise ValueError(f"unsupported state lineage mode: {lineage_mode!r}")

    creative_intent = data.get("creative_intent")
    if not isinstance(creative_intent, dict):
        raise ValueError("creative intent must be an object")
    from revision_contract import require_intent_revision
    require_intent_revision(creative_intent)
    if creative_intent.get("production_spec_sha256") != production_spec_hash:
        raise ValueError("creative intent production-specification hash mismatch")
    if creative_intent.get("state_lineage_sha256") != lineage_hash:
        raise ValueError("creative intent state-lineage hash mismatch")

    provenance = payload.get("negative_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("negative provenance declaration is missing")
    for key in (
        "activated_sources",
        "diagnostic_sources_retained",
        "semantic_exclusions_user_supplied",
    ):
        if not isinstance(provenance.get(key), list):
            raise ValueError(f"negative provenance field is invalid: {key}")
    translations = provenance.get("affirmative_translations")
    if not isinstance(translations, dict):
        raise ValueError("negative provenance affirmative_translations is invalid")
    for source, text in translations.items():
        if not isinstance(source, str) or not isinstance(text, str) or not text.strip():
            raise ValueError("affirmative translation entry is invalid")

    transport_errors, transports = verify_transports(data)
    if transport_errors:
        raise ValueError("; ".join(transport_errors))
    transport = payload.get("negative_transport")
    if not isinstance(transport, dict):
        raise ValueError("negative transport declaration is missing")
    mode = str(transport.get("mode") or "")
    if mode not in VALID_MODES:
        raise ValueError(f"invalid negative transport mode: {mode}")
    rendition = _selected_rendition(mode, transports)
    channel = transport.get("channel")
    if not isinstance(channel, str) or channel != rendition.get("channel"):
        raise ValueError("selected transport channel differs from its committed rendition")
    instruction = transport.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("selected transport instruction is missing")
    if contract.get("negative_transport_mode") != mode:
        raise ValueError("negative transport mode differs between payload and contract")
    if contract.get("negative_transport_instruction") != instruction:
        raise ValueError("negative transport instruction differs between payload and contract")
    if transport.get("send_full_negative_verbatim") is not (mode == "separate-field"):
        raise ValueError("full-negative transmission flag differs from the selected transport")
    if transport.get("send_native_negative_verbatim") is not (mode == "native-subset"):
        raise ValueError("native-negative transmission flag differs from the selected transport")
    if not isinstance(transport.get("critical_avoidance_integrated"), bool):
        raise ValueError("critical-avoidance integration declaration must be boolean")

    generation_input_hash = generation_input_sha256(data)
    require_concrete_sha256(generation_input_hash, "computed generation_input_sha256")
    for location, value in (
        ("generation_input_sha256", data.get("generation_input_sha256")),
        ("generation_contract.generation_input_sha256", contract.get("generation_input_sha256")),
    ):
        if require_concrete_sha256(value, location) != generation_input_hash:
            raise ValueError(f"{location} mismatch")

    selected_transport = {
        "mode": mode,
        "channel": channel,
        "instruction": instruction,
        "rendition": rendition,
    }
    if not live:
        return {'content_verified': True, 'generation_input_sha256': generation_input_hash,
                'production_spec': production_spec, 'prepared_reference_set': reference_set,
                'route_reading_sha256': reading_hash,
                'unmeasured': ['Current execution eligibility', 'Current source ownership',
                               'Visual meaning and suitability', 'Current renderer reproducibility']}
    effective_prompt = rendition['text' if mode in {'integrated-critical','retained-only'} else 'prompt']
    host_forwarding = {
        "model": model,
        "parameters": parameters,
        "selected_transport": selected_transport,
        "reference_preamble": reference_set["reference_preamble"],
        "effective_prompt": effective_prompt,
        "effective_prompt_sha256": sha256_text(effective_prompt),
        "selected_references": host_reference_transports(
            reference_set,
            package_root=package_root,
        ),
        "generation_input_sha256": generation_input_hash,
    }
    from request_renderer import prepare_forwarding
    rendered_input = prepare_forwarding(data, {'selected_transport':selected_transport,'host_forwarding':host_forwarding},
        root=project or package_root, model_id=model_id, model=model_record, offering=offering)
    if rendered_input['input_snapshots'] != data['input_snapshots']:
        raise ValueError('execution policy evidence is not completely captured in the generation input')
    host_forwarding = rendered_input['host_forwarding']
    return {
        **{key:rendered_input[key] for key in ('bindings','review_requirements','execution_policy')},
        'request_validation_report': validation_report,
        "verified": True,
        "model": model,
        "prompt": prompt,
        "negative_prompt": negative,
        "native_negative": native_negative,
        "negative_transport_mode": mode,
        "negative_transport_instruction": instruction,
        "negative_provenance": provenance,
        "creative_intent": creative_intent,
        "production_spec": production_spec,
        "production_spec_sha256": production_spec_hash,
        "state_lineage": state_lineage,
        "state_lineage_sha256": lineage_hash,
        "prepared_reference_set": reference_set,
        "prepared_reference_set_sha256": reference_set_hash,
        "generation_input_sha256": generation_input_hash,
        "parameters": parameters,
        "selected_transport": selected_transport,
        "host_forwarding": host_forwarding,
        "prompt_sha256": prompt_hash,
        "negative_prompt_sha256": negative_hash,
        "native_negative_sha256": native_hash,
        "transports": transports,
    }


def verify(data: dict[str, Any], *, package_root: Path | None = None,
           project: Path | None = None, reading_ledgers: list[Path] | None = None) -> dict[str, Any]:
    """Verify a current execution input using active sources and reading evidence."""
    return _verify(data, package_root=package_root, live=True, project=project,
                   reading_ledgers=reading_ledgers)


def verify_content(data: dict[str, Any], *, package_root: Path | None = None) -> dict[str, Any]:
    """Verify recorded content; this result does not authorize a new execution."""
    return _verify(data, package_root=package_root, live=False)


def emit_paste_for_target(
    data: dict[str, Any],
    target: str,
    *,
    package_root: Path | None = None,
    project: Path | None = None,
) -> dict[str, Any]:
    """Export only the already committed transport; never infer a new one."""

    result = verify(data, package_root=package_root, project=project)
    if target != result["model"]:
        raise ValueError(
            f"requested target {target!r} differs from committed model {result['model']!r}"
        )
    selected = result["selected_transport"]
    rendition = selected["rendition"]
    exported = {
        "target": target,
        "mode": selected["mode"],
        "channel": selected["channel"],
        "instruction": selected["instruction"],
        "parameters": result["parameters"],
        "selected_references": result["host_forwarding"]["selected_references"],
        "reference_preamble": result["host_forwarding"]["reference_preamble"],
        "generation_input_sha256": result["generation_input_sha256"],
    }
    if selected["mode"] == "separate-field":
        exported.update(
            paste_prompt=result["host_forwarding"]["effective_prompt"],
            paste_prompt_sha256=result["host_forwarding"]["effective_prompt_sha256"],
            paste_negative=rendition["negative"],
        )
    elif selected["mode"] == "native-subset":
        exported.update(
            paste_prompt=result["host_forwarding"]["effective_prompt"],
            paste_prompt_sha256=result["host_forwarding"]["effective_prompt_sha256"],
            native_negative=rendition["negative"],
        )
    else:
        exported.update(
            paste_prompt=result["host_forwarding"]["effective_prompt"],
            paste_prompt_sha256=result["host_forwarding"]["effective_prompt_sha256"],
            integration_method=rendition["method"],
        )
    return exported


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an exact Character Prompt Builder payload.")
    parser.add_argument("payload")
    parser.add_argument("--studio-root", type=Path, help="Source and studio root for live visual checks")
    parser.add_argument("--prompt-out")
    parser.add_argument("--negative-out")
    parser.add_argument("--native-negative-out")
    parser.add_argument("--payload-out")
    parser.add_argument(
        "--target",
        help=(
            "Emit the package's already committed paste-ready rendition. The value must "
            "exactly match the committed model; no transport is inferred."
        ),
    )
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)

    try:
        data = load_payload(Path(args.payload))
        payload_path = Path(args.payload).resolve()
        result = verify(data, package_root=payload_path.parent, project=args.studio_root)
        if args.target:
            result["paste"] = emit_paste_for_target(
                data,
                args.target,
                package_root=payload_path.parent,
                project=args.studio_root,
            )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        result = {
            "verified": False,
            "errors": [str(exc)],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    finally:
        configure_pack_runtime(None)

    if args.prompt_out:
        Path(args.prompt_out).write_text(
            result["host_forwarding"]["effective_prompt"] + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.negative_out:
        Path(args.negative_out).write_text(result["negative_prompt"] + "\n", encoding="utf-8", newline="\n")
    if args.native_negative_out:
        Path(args.native_negative_out).write_text(result["native_negative"] + "\n", encoding="utf-8", newline="\n")
    if args.payload_out:
        Path(args.payload_out).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
