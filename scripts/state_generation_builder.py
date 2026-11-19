#!/usr/bin/env python3
"""Build a verified generation package from concrete character state graphs in one scene."""
from __future__ import annotations
import operation_context as _operation_context

import json
from pathlib import Path
from typing import Any, Sequence

from generation_payload_builder import build_payload, create_cli_package_staging, generation_inputs, generation_package_recovery_path, materialize_cli_reference_bundle, prepared_run, production_inputs, studio_document, studio_text, publish_cli_generation_package, remove_cli_package_staging, run_inputs
from generation_cli_arguments import TRANSPORT_MODES, add_production_arguments
from catalog_api import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from generation_references import validate_prepared_reference_set
from state_protocol import (
    artifact_hash,
    validate_subject_state_graphs,
    parse_json,
    write_json,
)


def build_package(
    *,
    execution: str,
    model: str,
    prompt: str,
    negative_prompt: str,
    brief: str,
    creative_intent: dict[str, Any],
    production_spec: dict[str, Any],
    state_graphs: list[dict[str, Any]],
    plot: dict[str, Any],
    parameters: dict[str, Any],
    retrieval_record: dict[str, Any] | None = None,
    visual_continuity: dict[str, Any] | None = None,
    visual_root: Path | None = None,
    request_validation: dict[str, Any] | None = None,
    input_root: Path | None = None,
    route_reading: dict[str, Any] | None = None,
    reading_ledgers: list[Path] | None = None,
    integrated_prompt: str = "",
    native_negative: str = "",
    negative_provenance: dict[str, Any] | None = None,
    prepared_reference_set: dict[str, Any] | None = None,
    prepared_reference_root: Path | None = None,
    negative_transport: str = "auto",
    critical_avoidance_integrated: bool = False,
    production_root: Path | None = None,
    production_run: str | None = None,
) -> dict[str, Any]:
    # State packaging requires a settled construction record before graph work.
    # Its binding is checked by the shared generation input owner only after
    # selecting the actual text transport and expanding reference directions.
    from prompt_retrieval import require_settled_retrieval_record
    require_settled_retrieval_record(retrieval_record)
    if production_spec.get("target_model") != model:
        raise ValueError("package model differs from production specification target_model")
    if prepared_reference_set is None:
        raise ValueError(
            "state-aware package requires a prepared reference set, including when "
            "no references are selected"
        )
    reference_set = validate_prepared_reference_set(
        prepared_reference_set,
        model=model,
        package_root=prepared_reference_root,
    )
    selection = reference_set["reference_selection"]
    if not isinstance(selection, dict):
        raise ValueError("state-aware package requires a finalized reference-selection")
    state_graphs = validate_subject_state_graphs(state_graphs, production_spec=production_spec,
        reference_selection=selection)
    primary_hash = production_spec['state_context']['state_lineage_sha256']
    primary = next(graph for graph in state_graphs if graph['lineage']['lineage_sha256'] == primary_hash)

    payload = build_payload(
        execution=execution,
        plot=plot,
        retrieval_record=retrieval_record,
        request_validation=request_validation, input_root=input_root,
        route_reading=route_reading,
        visual_continuity=visual_continuity, visual_root=visual_root,
        reading_ledgers=reading_ledgers,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        integrated_prompt=integrated_prompt,
        native_negative=native_negative,
        negative_provenance=negative_provenance,
        brief=brief,
        creative_intent=creative_intent,
        production_spec=production_spec,
        state_lineage=primary["lineage"],
        state_snapshot=primary["state_snapshot"],
        state_graphs=state_graphs,
        prepared_reference_set=reference_set,
        prepared_reference_root=prepared_reference_root,
        parameters=parameters,
        negative_transport=negative_transport,
        critical_avoidance_integrated=critical_avoidance_integrated,
        production_root=production_root,
        production_run=production_run,
    )
    verification = verify_package(payload, package_root=prepared_reference_root,
        studio=visual_root or production_root or prepared_reference_root, execution=execution)
    if verification.get("verified") is not True:
        raise ValueError(
            "generated package failed verification: "
            + "; ".join(verification.get("errors", []))
        )
    return payload


def verify_package(
    payload: dict[str, Any],
    *,
    package_root: Path | None = None,
    studio: Path | None = None,
    execution: str | None = None,
) -> dict[str, Any]:
    from generation_payload_validation import verify

    return verify(payload, package_root=package_root, studio=studio, execution=execution)
