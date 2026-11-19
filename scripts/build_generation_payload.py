#!/usr/bin/env python3
"""Package an agent-authored prompt for exact downstream image generation.

The script does not interpret the brief or write the prompt. It records the
creative decision, hashes every transmitted text payload, and declares how the
target interface receives avoidance instructions. It binds the package to the
prepared production run and derives the route reading, the request check and
visual continuity from that run, the active pack and the stated decisions.
The prompt is the run's delivery, and the specification, plot, retrieval record
and parameters the run's task declares come from the run's published snapshot.
"""
from __future__ import annotations
import operation_context as _operation_context


import json


from pathlib import Path
from typing import Any, Sequence
from pack_runtime_cli import add_pack_runtime_arguments
from generation_cli_arguments import TRANSPORT_MODES, add_production_arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description="Build an exact Character Prompt Builder generation payload from a prepared run.",
        epilog="The prompt is the run's delivery. The run's production specification, plot, retrieval record and "
        "parameters are read from its snapshot when its task declares them; the matching option names them otherwise. "
        "A relative file argument is a /-separated path below --production-root.",
    )
    parser.add_argument("--model", help="The model record; the production specification's target_model when omitted")
    parser.add_argument("--negative-file", help="Portable negative prompt, a UTF-8 text file")
    parser.add_argument(
        "--integrated-prompt-file",
        help=(
            "Authored rendition for the selected single-prompt interface. "
            "When a portable negative exists, supply this rendition or certify the primary prompt "
            "with --critical-avoidance-integrated."
        ),
    )
    parser.add_argument("--native-negative-file", help="Authored native negative text for the selected interface")
    parser.add_argument("--negative-provenance-file", help="JSON object listing activated and retained sources and user exclusions")
    parser.add_argument(
        "--negative-transport",
        choices=sorted(TRANSPORT_MODES),
        default="auto",
        help="How the named target interface receives avoidance instructions.",
    )
    parser.add_argument(
        "--critical-avoidance-integrated",
        action="store_true",
        help="Certify the primary prompt as the reviewed single-field rendition, including necessary exclusions.",
    )
    brief = parser.add_mutually_exclusive_group()
    brief.add_argument("--brief", default="", help="The request in words")
    brief.add_argument("--brief-file", help="The request as a UTF-8 text file")
    parser.add_argument("--intent-file", help="JSON containing image_promise, chosen_direction, and related notes")
    parser.add_argument("--production-spec-file", help="Reviewed Production Specification JSON, when the run declares none")
    parser.add_argument("--render-intent-file", help="Rendering intent when neither the run nor a selected specification supplies it")
    parser.add_argument("--plot-file", help="The approved plot this picture was drawn from, when the run declares none")
    parser.add_argument("--retrieval-record-file",
                        help="Settled retrieval record bound to the run's prompt and the plot, when the run declares none")
    parser.add_argument("--state-lineage-file", help="Optional Shared State Protocol lineage JSON; omitted means stateless")
    parser.add_argument(
        "--references-file",
        help=(
            "Canonical prepared-reference-set JSON produced by reference_runtime.py "
            "or the supplied-file preparer."
        ),
    )
    parser.add_argument("--parameters-file",
                        help="UTF-8 JSON parameter object file, or - for stdin, when the run declares none")
    parser.add_argument(
        "--service",
        help="The service the request goes through, by its key in the service-profiles resource; "
        "needed only when the model record is exposed on more than one",
    )
    add_pack_runtime_arguments(parser)
    parser.add_argument("--out", required=True, help="New Generation Package file; an existing file is kept")
    add_production_arguments(parser)
    args = parser.parse_args(argv)
    import generation_payload_builder as implementation
    runtime = implementation.resolve_pack_runtime(parser, args)
    implementation.configure_pack_runtime(runtime.settings)
    staging_root: Path | None = None
    pending_error: BaseException | None = None
    payload: dict[str, Any] | None = None
    try:
        from production_binding import new_output, studio_file
        root = args.production_root.absolute()
        output_path = new_output(root, args.out, option="--out", root_option="--production-root")
        state_lineage_input = implementation.studio_document(root, args.state_lineage_file, "--state-lineage-file")
        if state_lineage_input is not None and state_lineage_input.get("mode") == "state-aware":
            raise ValueError(
                "build_generation_payload.py is the stateless CLI; use "
                "build_state_generation_package.py for a state-aware artifact graph"
            )
        loaded = implementation.prepared_run(root, args.production_run)
        chosen = implementation.generation_inputs(args, root, implementation.run_inputs(loaded[1], loaded[2]))
        production_spec = chosen["production_spec"]
        selected_generation=loaded[2]['task'].get('generation') or {}
        model = args.model or (production_spec or {}).get("target_model") or selected_generation.get('model')
        if not isinstance(model, str) or not model.strip():
            raise ValueError("the prepared input names no model; pass --model")
        render_intent=(production_spec or {}).get('render_intent') or selected_generation.get('render_intent')
        if args.render_intent_file:
            if render_intent is not None:
                raise ValueError('the prepared input already supplies render intent')
            render_intent=implementation.studio_document(root,args.render_intent_file,'--render-intent-file')
        brief = implementation.studio_text(root, args.brief_file, "--brief-file") if args.brief_file else args.brief
        staging_root, staged_json, _staged_companion_path, final_companion = (
            implementation.create_cli_package_staging(output_path)
        )
        staged_reference_set: dict[str, Any] | None = None
        staged_companion: Path | None = None
        if args.references_file:
            references_path = studio_file(root, args.references_file, option="--references-file",
                                           root_option="--production-root").resolve(strict=True)
            source_reference_set = implementation.studio_document(root, str(references_path), "--references-file")
            staged_reference_set, staged_companion = implementation.materialize_cli_reference_bundle(
                source_reference_set,
                model=model,
                source_root=references_path.parent,
                staging_root=staging_root,
                companion_name=final_companion.name,
            )
        derived = implementation.production_inputs(args, model=model, production_spec=production_spec,
                                    prepared_reference_set=staged_reference_set, staging_root=staging_root,
                                    loaded=loaded)
        from catalog_retrieval.runtime import load_pack_catalog
        from render_contract_lib import RenderPresets
        render_presets = RenderPresets(source=load_pack_catalog().builder_inputs)
        payload = implementation.build_payload(
            execution=derived['execution'],
            plot=chosen["plot"],
            retrieval_record=chosen["retrieval_record"],
            request_validation=derived["request_validation"], input_root=derived["root"],
            route_reading=derived["route_reading"],
            visual_continuity=derived["visual_continuity"],
            visual_root=derived["root"],
            reading_ledgers=[staging_root / "reads.jsonl"],
            model=model,
            prompt=loaded[3]["instructions"],
            negative_prompt=implementation.studio_text(root, args.negative_file, "--negative-file"),
            integrated_prompt=implementation.studio_text(root, args.integrated_prompt_file, "--integrated-prompt-file"),
            native_negative=implementation.studio_text(root, args.native_negative_file, "--native-negative-file"),
            negative_provenance=implementation.studio_document(root, args.negative_provenance_file, "--negative-provenance-file") or {},
            brief=brief,
            creative_intent=chosen['creative_intent'],
            production_spec=production_spec,
            render_intent=render_intent,
            state_lineage=state_lineage_input,
            prepared_reference_set=staged_reference_set,
            prepared_reference_root=staging_root,
            parameters=chosen["parameters"],
            negative_transport=args.negative_transport,
            critical_avoidance_integrated=args.critical_avoidance_integrated,
            service=args.service,
            production_root=derived["root"],
            production_run=derived["run"],
            render_presets=render_presets,
        )
        # Writing is the commit point. Re-read every selected reference and verify
        # the exact package contract before creating the output file.
        from generation_payload_validation import verify

        verify(payload, package_root=staging_root, studio=derived["root"], execution=derived['execution'],
               render_presets=render_presets)
        staged_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        from route_reading import copy_issuance
        copy_issuance(derived["route_reading"], output_path.parent / "reads.jsonl", ledgers=[staging_root / "reads.jsonl"])
        implementation.publish_cli_generation_package(
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
                        "generation package staging cleanup also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}{location}"
                    )
        finally:
            implementation.configure_pack_runtime(None)
    if pending_error is not None:
        from production_binding import report_failure
        return report_failure(pending_error, phase="package-construction")
    if payload is None:
        raise RuntimeError("generation package completed without a payload")
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
