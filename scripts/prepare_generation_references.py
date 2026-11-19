#!/usr/bin/env python3
"""Prepare ordered image references for one exact generation target.

Catalog artifacts, caller-supplied files and accepted Studio artwork enter
through distinct source variants. The prepared result commits both the selected source bytes and the
actual model-facing transport bytes. SVG sources are safely rasterized from the
same selected artifact; the preparer never substitutes another guide artifact
and never falls back to text-only generation.
"""
from __future__ import annotations
import operation_context as _operation_context


import json


from pathlib import Path
from typing import Sequence
from pack_runtime_cli import add_pack_runtime_arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description="Prepare exact ordered caller-supplied image references."
    )
    selection_group = parser.add_mutually_exclusive_group()
    selection_group.add_argument(
        "--supplied-selection-file",
        type=Path,
        help='Ordered array of {"role":"scene","source":{"kind":"supplied-file",'
             '"reference_id":"scene","resolved_path":"/absolute/image.png"}}; '
             'files are measured here and scopes remain conservative',
    )
    parser.add_argument(
        "--state-selection-file",
        type=Path,
        help="Finalized state selection; supplied or Studio choices may append stateless and scene references",
    )
    selection_group.add_argument('--studio-selection-file', type=Path,
        help='Ordered {character, slot, role} choices; resolve each exact current Studio acceptance')
    selection_group.add_argument('--image-input-plan-file',
        help='Authored dispatcher image-input-plan: an absolute path, or a /-separated path below --studio; '
             'derive supplied files, order and exact scopes from this plan')
    parser.add_argument('--studio', type=Path,
        help='Studio root for --studio-selection-file or --image-input-plan-file; edit plan file paths are relative to it')
    parser.add_argument('--transport-mode', choices=['multi-image', 'single-board'], default='multi-image')
    parser.add_argument("--model", help="Explicit catalog model; optional when an image input plan declares its model")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-side", type=int, default=1536)
    parser.add_argument("--out", type=Path, required=True)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    import generation_references as implementation
    runtime = implementation.resolve_pack_runtime(parser, args)
    implementation.configure_pack_runtime(runtime.settings)
    try:
        if not any((args.state_selection_file, args.supplied_selection_file,
                    args.studio_selection_file, args.image_input_plan_file)):
            raise ValueError('provide a state selection, supplied choices, Studio choices or an image input plan')
        if args.image_input_plan_file is not None and args.state_selection_file is not None:
            raise ValueError('image input plans preserve their existing prepared state selection')
        if args.image_input_plan_file is None and not args.model:
            raise ValueError('--model is required for supplied, state or Studio reference preparation; no default model is selected')
        additional = []
        if args.studio_selection_file is not None:
            if args.studio is None:
                raise ValueError('--studio is required for a Studio selection')
            additional = implementation.resolve_studio_reference_choices(args.studio, implementation.read_json_array(args.studio_selection_file))
        elif args.supplied_selection_file is not None:
            additional = implementation.read_json_array(args.supplied_selection_file)
        if args.image_input_plan_file is not None:
            if args.studio is None:
                raise ValueError('--studio is required for an image input plan')
            from production_binding import studio_file
            plan_file = studio_file(args.studio, args.image_input_plan_file,
                                    option='--image-input-plan-file', root_option='--studio')
            prepared = implementation.prepare_image_input_references(implementation.read_json_object(plan_file),
                studio=args.studio, model=args.model, output_dir=args.output_dir,
                max_side=args.max_side, transport_mode=args.transport_mode)
        elif args.state_selection_file is not None:
            prepared = implementation.prepare_state_reference_selection(
                implementation.read_json_object(args.state_selection_file),
                model=args.model,
                output_dir=args.output_dir,
                max_side=args.max_side, transport_mode=args.transport_mode,
                additional_references=additional,
            )
        else:
            prepared = implementation.prepare_references(
                additional,
                model=args.model,
                output_dir=args.output_dir,
                max_side=args.max_side, transport_mode=args.transport_mode,
            )
        implementation.write_json_atomic(args.out, prepared)
        print(json.dumps(prepared, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        diagnostic = getattr(exc, "diagnostic", None)
        # A diagnostic's repair names the exact form to write; print it with the message.
        message = str(exc) + (" " + diagnostic.required_action if diagnostic is not None else "")
        print(json.dumps({"ok": False, "errors": [message]}, ensure_ascii=False, indent=2, allow_nan=False))
        return 1
    finally:
        implementation.configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
