#!/usr/bin/env python3
"""Build a verified generation package from concrete character state graphs in one scene."""
from __future__ import annotations
import operation_context as _operation_context

import json
from pathlib import Path
from typing import Any, Sequence

from build_generation_payload import (
    TRANSPORT_MODES,
    add_production_arguments,
    build_payload,
    create_cli_package_staging,
    generation_inputs,
    generation_package_recovery_path,
    materialize_cli_reference_bundle,
    prepared_run,
    production_inputs,
    studio_document,
    studio_text,
    publish_cli_generation_package,
    remove_cli_package_staging,
    run_inputs,
)
from catalog_cli import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from prepare_generation_references import validate_prepared_reference_set
from state_protocol import (
    artifact_hash,
    validate_subject_state_graphs,
    parse_json,
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
    from prompt_retrieval import require_generation_retrieval
    require_generation_retrieval(retrieval_record, prompt=prompt, plot=plot)
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
    verification = verify_package(payload, package_root=prepared_reference_root, studio=visual_root or production_root or prepared_reference_root)
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
) -> dict[str, Any]:
    from verify_generation_payload import verify

    return verify(payload, package_root=package_root, studio=studio)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description="Build an exact state-aware Character Prompt Builder generation package from a prepared run.",
        epilog="The prompt is the run's delivery. The run's production specification, plot, retrieval record and "
        "parameters are read from its snapshot when its task declares them; the matching option names them otherwise. "
        "A relative file argument is a /-separated path below --production-root.",
    )
    parser.add_argument("--model", help="The model record; the production specification's target_model when omitted")
    parser.add_argument("--negative-file", help="Portable negative prompt, a UTF-8 text file")
    parser.add_argument("--integrated-prompt-file",
                        help="Authored rendition for the selected single-prompt interface")
    parser.add_argument("--native-negative-file", help="Authored native negative text, a UTF-8 text file")
    parser.add_argument("--negative-provenance-file", help="JSON object listing activated and retained sources and user exclusions")
    parser.add_argument("--negative-transport", choices=sorted(TRANSPORT_MODES), default="auto",
                        help="How the named target interface receives avoidance instructions")
    parser.add_argument("--critical-avoidance-integrated", action="store_true",
                        help="Certify the primary prompt as the reviewed single-field rendition, including necessary exclusions")
    brief = parser.add_mutually_exclusive_group()
    brief.add_argument("--brief", default="", help="The request in words")
    brief.add_argument("--brief-file", help="The request as a UTF-8 text file")
    parser.add_argument("--intent-file", help="JSON containing image_promise, chosen_direction, and related notes")
    parser.add_argument("--production-spec-file", help="Reviewed Production Specification JSON, when the run declares none")
    parser.add_argument("--plot-file", help="The approved plot this picture was drawn from, when the run declares none")
    parser.add_argument("--retrieval-record-file",
                        help="Settled retrieval record bound to the run's prompt and the plot, when the run declares none")
    parser.add_argument("--state-graphs-file", required=True,
                        help="JSON array of each state-aware subject's concrete graph nodes")
    parser.add_argument(
        "--references-file",
        required=True,
        help=(
            "Canonical prepared-reference-set JSON. State-aware packages require its "
            "finalized reference-selection even when selected_references is empty."
        ),
    )
    parser.add_argument("--parameters-file",
                        help="UTF-8 JSON parameter object file, or - for stdin, when the run declares none")
    add_pack_runtime_arguments(parser)
    parser.add_argument("--out", required=True, help="New Generation Package file; an existing file is kept")
    add_production_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    staging_root: Path | None = None
    pending_error: BaseException | None = None
    payload: dict[str, Any] | None = None
    failure_phase = "package-construction"
    try:
        from production_binding import new_output, studio_file
        root = args.production_root.absolute()
        output_path = new_output(root, args.out, option="--out", root_option="--production-root")
        loaded = prepared_run(root, args.production_run)
        chosen = generation_inputs(args, root, run_inputs(loaded[1], loaded[2]))
        production_spec = chosen["production_spec"]
        model = args.model or production_spec.get("target_model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("the production specification names no target_model; pass --model")

        def graph(option: str) -> dict[str, Any] | None:
            return studio_document(root, getattr(args, option[2:].replace("-", "_")), option)

        brief = studio_text(root, args.brief_file, "--brief-file") if args.brief_file else args.brief
        staging_root, staged_json, _staged_companion_path, final_companion = (
            create_cli_package_staging(output_path)
        )
        references_path = studio_file(root, args.references_file, option="--references-file",
                                       root_option="--production-root").resolve(strict=True)
        staged_reference_set, staged_companion = materialize_cli_reference_bundle(
            studio_document(root, str(references_path), "--references-file"),
            model=model,
            source_root=references_path.parent,
            staging_root=staging_root,
            companion_name=final_companion.name,
        )
        state_graphs = parse_json(studio_text(root, args.state_graphs_file, "--state-graphs-file"))
        state_graphs = validate_subject_state_graphs(state_graphs, production_spec=production_spec,
            reference_selection=staged_reference_set['reference_selection'])
        work_ids = {graph['identity_contract']['character_id']: graph['identity_contract']['character_id']
                    for graph in state_graphs}
        derived = production_inputs(args, model=model, production_spec=production_spec,
                                    prepared_reference_set=staged_reference_set, staging_root=staging_root,
                                    work_ids=work_ids, loaded=loaded)
        payload = build_package(
            model=model,
            prompt=loaded[3]["instructions"],
            negative_prompt=studio_text(root, args.negative_file, "--negative-file"),
            integrated_prompt=studio_text(root, args.integrated_prompt_file, "--integrated-prompt-file"),
            native_negative=studio_text(root, args.native_negative_file, "--native-negative-file"),
            negative_provenance=graph("--negative-provenance-file") or {},
            brief=brief,
            creative_intent=graph("--intent-file") or {},
            production_spec=production_spec,
            plot=chosen["plot"],
            retrieval_record=chosen["retrieval_record"],
            request_validation=derived["request_validation"], input_root=derived["root"],
            route_reading=derived["route_reading"],
            visual_continuity=derived["visual_continuity"],
            visual_root=derived["root"],
            reading_ledgers=[staging_root / "reads.jsonl"],
            state_graphs=state_graphs,
            prepared_reference_set=staged_reference_set,
            prepared_reference_root=staging_root,
            parameters=chosen["parameters"],
            negative_transport=args.negative_transport,
            critical_avoidance_integrated=args.critical_avoidance_integrated,
            production_root=derived["root"],
            production_run=derived["run"],
        )
        write_json(staged_json, payload)
        failure_phase = "publication"
        from route_reading import copy_issuance
        copy_issuance(derived["route_reading"], output_path.parent / "reads.jsonl", ledgers=[staging_root / "reads.jsonl"])
        publish_cli_generation_package(
            output_path=output_path,
            staged_json=staged_json,
            staged_companion=staged_companion,
            final_companion=final_companion,
            staging_root=staging_root,
        )
    except (ValueError, OSError) as exc:
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
        from production_binding import report_failure
        return report_failure(pending_error, phase=failure_phase)
    if payload is None:
        raise RuntimeError("state-aware generation package completed without a payload")
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
