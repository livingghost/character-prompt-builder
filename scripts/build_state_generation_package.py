#!/usr/bin/env python3
"""Build a verified generation package from one concrete state artifact graph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from build_generation_payload import (
    build_payload,
    create_cli_package_staging,
    generation_package_error_messages,
    generation_package_recovery_path,
    materialize_cli_reference_bundle,
    publish_cli_generation_package,
    read_json,
    read_text,
    remove_cli_package_staging,
)
from catalog_cli import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from prepare_generation_references import validate_prepared_reference_set
from state_protocol import (
    artifact_hash,
    load_json,
    parse_json,
    validate_state_artifact_graph,
    write_json,
)


def build_package(
    *,
    model: str,
    prompt: str,
    negative_prompt: str,
    brief: str,
    creative_intent: dict[str, Any],
    production_spec: dict[str, Any],
    state_lineage: dict[str, Any],
    species_profile: dict[str, Any],
    individual_morphology: dict[str, Any],
    identity_contract: dict[str, Any],
    state_snapshot: dict[str, Any],
    scene_context: dict[str, Any],
    visual_projection: dict[str, Any],
    asset_render_spec: dict[str, Any],
    plot: dict[str, Any],
    parameters: dict[str, Any],
    retrieval_record: dict[str, Any] | None = None,
    integrated_prompt: str = "",
    native_negative: str = "",
    negative_provenance: dict[str, Any] | None = None,
    era_contract: dict[str, Any] | None = None,
    form_contract: dict[str, Any] | None = None,
    appearance_variant: dict[str, Any] | None = None,
    visual_authority: dict[str, Any] | None = None,
    visual_evidence_bundle: dict[str, Any] | None = None,
    prepared_reference_set: dict[str, Any] | None = None,
    prepared_reference_root: Path | None = None,
    negative_transport: str = "auto",
    critical_avoidance_integrated: bool = False,
    production_root: Path | None = None,
    production_run: str | None = None,
) -> dict[str, Any]:
    from prompt_retrieval import require_generation_retrieval
    require_generation_retrieval(retrieval_record, prompt=prompt, plot=plot)
    if state_lineage.get("mode") != "state-aware":
        raise ValueError("state-aware package requires state-lineage mode=state-aware")
    if production_spec.get("target_model") != model:
        raise ValueError("package model differs from production specification target_model")
    if asset_render_spec.get("target_model") != model:
        raise ValueError("package model differs from asset render specification target_model")
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
    expected_selection_graph = {
        "identity_contract_sha256": artifact_hash(identity_contract),
        "era_contract_sha256": artifact_hash(era_contract) if era_contract is not None else None,
        "appearance_variant_sha256": (
            artifact_hash(appearance_variant) if appearance_variant is not None else None
        ),
        "state_snapshot_sha256": artifact_hash(state_snapshot),
        "story_order": state_snapshot.get("story_order"),
    }
    for field, expected in expected_selection_graph.items():
        if selection.get(field) != expected:
            raise ValueError(
                f"reference-selection {field} differs from the supplied state graph"
            )
    graph_report = validate_state_artifact_graph(
        lineage=state_lineage,
        species_profile=species_profile,
        individual_morphology=individual_morphology,
        identity_contract=identity_contract,
        era_contract=era_contract,
        form_contract=form_contract,
        appearance_variant=appearance_variant,
        state_snapshot=state_snapshot,
        scene_context=scene_context,
        visual_projection=visual_projection,
        asset_render_spec=asset_render_spec,
        visual_authority=visual_authority,
        visual_evidence_bundle=visual_evidence_bundle,
        production_spec=production_spec,
    )
    if not graph_report.get("ok"):
        raise ValueError("invalid state artifact graph: " + "; ".join(graph_report["errors"]))

    payload = build_payload(
        plot=plot,
        retrieval_record=retrieval_record,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        integrated_prompt=integrated_prompt,
        native_negative=native_negative,
        negative_provenance=negative_provenance,
        brief=brief,
        creative_intent=creative_intent,
        production_spec=production_spec,
        state_lineage=state_lineage,
        state_snapshot=state_snapshot,
        prepared_reference_set=reference_set,
        prepared_reference_root=prepared_reference_root,
        parameters=parameters,
        negative_transport=negative_transport,
        critical_avoidance_integrated=critical_avoidance_integrated,
        production_root=production_root,
        production_run=production_run,
    )
    verification = verify_package(payload, package_root=prepared_reference_root)
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
) -> dict[str, Any]:
    from verify_generation_payload import verify

    return verify(payload, package_root=package_root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an exact state-aware CPB generation package."
    )
    parser.add_argument("--model", default="gpt-image-2.5-flare")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--negative-file")
    parser.add_argument("--integrated-prompt-file")
    parser.add_argument("--native-negative-file")
    parser.add_argument("--negative-provenance-file")
    parser.add_argument("--negative-transport", default="auto")
    parser.add_argument("--critical-avoidance-integrated", action="store_true")
    parser.add_argument("--brief", default="")
    parser.add_argument("--brief-file")
    parser.add_argument("--intent-file")
    parser.add_argument("--production-spec-file", required=True)
    parser.add_argument("--plot-file", required=True)
    parser.add_argument("--retrieval-record-file", required=True)
    parser.add_argument("--state-lineage-file", required=True)
    parser.add_argument("--species-profile-file", required=True)
    parser.add_argument("--individual-morphology-file", required=True)
    parser.add_argument("--identity-contract-file", required=True)
    parser.add_argument("--era-contract-file")
    parser.add_argument("--form-contract-file")
    parser.add_argument("--appearance-variant-file")
    parser.add_argument("--state-snapshot-file", required=True)
    parser.add_argument("--scene-context-file", required=True)
    parser.add_argument("--visual-projection-file", required=True)
    parser.add_argument("--asset-render-spec-file", required=True)
    parser.add_argument("--visual-authority-file")
    parser.add_argument("--visual-evidence-bundle-file")
    parser.add_argument(
        "--references-file",
        required=True,
        help=(
            "Canonical prepared-reference-set JSON. State-aware packages require its "
            "finalized reference-selection even when selected_references is empty."
        ),
    )
    parser.add_argument("--parameters", default="{}")
    parser.add_argument("--out", required=True)
    add_pack_runtime_arguments(parser)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--production-run")
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    staging_root: Path | None = None
    pending_error: BaseException | None = None
    payload: dict[str, Any] | None = None
    try:
        parameters = parse_json(args.parameters)
        if not isinstance(parameters, dict):
            raise ValueError("--parameters must be a JSON object")
        output_path = Path(args.out).resolve()
        staging_root, staged_json, _staged_companion_path, final_companion = (
            create_cli_package_staging(output_path)
        )
        references_path = Path(args.references_file).resolve(strict=True)
        staged_reference_set, staged_companion = materialize_cli_reference_bundle(
            read_json(str(references_path)),
            model=args.model,
            source_root=references_path.parent,
            staging_root=staging_root,
            companion_name=final_companion.name,
        )
        payload = build_package(
            model=args.model,
            prompt=read_text(args.prompt_file),
            negative_prompt=read_text(args.negative_file),
            integrated_prompt=read_text(args.integrated_prompt_file),
            native_negative=read_text(args.native_negative_file),
            negative_provenance=read_json(args.negative_provenance_file),
            brief=read_text(args.brief_file) if args.brief_file else args.brief,
            creative_intent=read_json(args.intent_file),
            production_spec=read_json(args.production_spec_file),
            plot=read_json(args.plot_file),
            retrieval_record=read_json(args.retrieval_record_file),
            state_lineage=read_json(args.state_lineage_file),
            species_profile=load_json(Path(args.species_profile_file)),
            individual_morphology=load_json(Path(args.individual_morphology_file)),
            identity_contract=load_json(Path(args.identity_contract_file)),
            era_contract=(
                load_json(Path(args.era_contract_file)) if args.era_contract_file else None
            ),
            form_contract=(
                load_json(Path(args.form_contract_file)) if args.form_contract_file else None
            ),
            appearance_variant=(
                load_json(Path(args.appearance_variant_file))
                if args.appearance_variant_file
                else None
            ),
            state_snapshot=load_json(Path(args.state_snapshot_file)),
            scene_context=load_json(Path(args.scene_context_file)),
            visual_projection=load_json(Path(args.visual_projection_file)),
            asset_render_spec=load_json(Path(args.asset_render_spec_file)),
            visual_authority=(
                load_json(Path(args.visual_authority_file)) if args.visual_authority_file else None
            ),
            visual_evidence_bundle=(
                load_json(Path(args.visual_evidence_bundle_file))
                if args.visual_evidence_bundle_file
                else None
            ),
            prepared_reference_set=staged_reference_set,
            prepared_reference_root=staging_root,
            parameters=parameters,
            negative_transport=args.negative_transport,
            critical_avoidance_integrated=args.critical_avoidance_integrated,
            production_root=args.production_root,
            production_run=args.production_run,
        )
        write_json(staged_json, payload)
        publish_cli_generation_package(
            output_path=output_path,
            staged_json=staged_json,
            staged_companion=staged_companion,
            final_companion=final_companion,
            staging_root=staging_root,
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        pending_error = exc
    except BaseException as exc:
        pending_error = exc
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
                        "state-aware generation package staging cleanup also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}{location}"
                    )
        finally:
            configure_pack_runtime(None)
    if pending_error is not None:
        print(
            json.dumps(
                {"ok": False, "errors": generation_package_error_messages(pending_error)},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        )
        return 1
    if payload is None:
        raise RuntimeError("state-aware generation package completed without a payload")
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
