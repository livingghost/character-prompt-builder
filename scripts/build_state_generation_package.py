#!/usr/bin/env python3
"""Build a verified generation package from concrete character state graphs in one scene."""
from __future__ import annotations
import operation_context as _operation_context
import json
from pathlib import Path
from typing import Any, Sequence
from pack_runtime_cli import add_pack_runtime_arguments
from generation_cli_arguments import TRANSPORT_MODES, add_production_arguments


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
    import state_generation_builder as implementation
    runtime = implementation.resolve_pack_runtime(parser, args)
    implementation.configure_pack_runtime(runtime.settings)
    staging_root: Path | None = None
    pending_error: BaseException | None = None
    payload: dict[str, Any] | None = None
    failure_phase = "package-construction"
    try:
        from production_binding import new_output, studio_file
        root = args.production_root.absolute()
        output_path = new_output(root, args.out, option="--out", root_option="--production-root")
        loaded = implementation.prepared_run(root, args.production_run)
        chosen = implementation.generation_inputs(args, root, implementation.run_inputs(loaded[1], loaded[2]))
        production_spec = chosen["production_spec"]
        model = args.model or production_spec.get("target_model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("the production specification names no target_model; pass --model")

        def graph(option: str) -> dict[str, Any] | None:
            return implementation.studio_document(root, getattr(args, option[2:].replace("-", "_")), option)

        brief = implementation.studio_text(root, args.brief_file, "--brief-file") if args.brief_file else args.brief
        staging_root, staged_json, _staged_companion_path, final_companion = (
            implementation.create_cli_package_staging(output_path)
        )
        references_path = studio_file(root, args.references_file, option="--references-file",
                                       root_option="--production-root").resolve(strict=True)
        staged_reference_set, staged_companion = implementation.materialize_cli_reference_bundle(
            implementation.studio_document(root, str(references_path), "--references-file"),
            model=model,
            source_root=references_path.parent,
            staging_root=staging_root,
            companion_name=final_companion.name,
        )
        state_graphs = implementation.parse_json(implementation.studio_text(root, args.state_graphs_file, "--state-graphs-file"))
        state_graphs = implementation.validate_subject_state_graphs(state_graphs, production_spec=production_spec,
            reference_selection=staged_reference_set['reference_selection'])
        work_ids = {graph['identity_contract']['character_id']: graph['identity_contract']['character_id']
                    for graph in state_graphs}
        derived = implementation.production_inputs(args, model=model, production_spec=production_spec,
                                    prepared_reference_set=staged_reference_set, staging_root=staging_root,
                                    work_ids=work_ids, loaded=loaded)
        payload = implementation.build_package(
            execution=derived['execution'],
            model=model,
            prompt=loaded[3]["instructions"],
            negative_prompt=implementation.studio_text(root, args.negative_file, "--negative-file"),
            integrated_prompt=implementation.studio_text(root, args.integrated_prompt_file, "--integrated-prompt-file"),
            native_negative=implementation.studio_text(root, args.native_negative_file, "--native-negative-file"),
            negative_provenance=graph("--negative-provenance-file") or {},
            brief=brief,
            creative_intent=chosen['creative_intent'],
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
        implementation.write_json(staged_json, payload)
        failure_phase = "publication"
        from route_reading import copy_issuance
        copy_issuance(derived["route_reading"], output_path.parent / "reads.jsonl", ledgers=[staging_root / "reads.jsonl"])
        implementation.publish_cli_generation_package(
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
                and implementation.generation_package_recovery_path(pending_error) is None
            ):
                try:
                    implementation.remove_cli_package_staging(staging_root)
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
            implementation.configure_pack_runtime(None)
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
