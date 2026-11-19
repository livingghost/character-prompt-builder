#!/usr/bin/env python3
"""Build, validate, and transactionally materialize visual-reference plans."""
from __future__ import annotations
import operation_context as _operation_context
import argparse


import json


from collections.abc import Sequence
from pathlib import Path

from pack_runtime_cli import add_pack_runtime_arguments
from reference_plan_cli_contract import add_reference_plan_arguments
from reference_contract import INTENDED_INFLUENCES


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description="Build or execute record-scoped visual-reference plans."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser(
        "plan",
        help="Build a reference-use plan",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_reference_plan_arguments(plan_parser)
    plan_parser.add_argument("--out", type=Path, required=True)
    add_pack_runtime_arguments(plan_parser)

    execute_parser = subparsers.add_parser(
        "execute", help="Transactionally materialize one canonical reference package"
    )
    execute_parser.add_argument("--plan", type=Path, required=True)
    execute_parser.add_argument("--output-dir", type=Path, required=True)
    execute_parser.add_argument("--prompt-file", type=Path)
    execute_parser.add_argument("--negative-file", type=Path)
    execute_parser.add_argument("--reference-selection", type=Path)
    additional_group = execute_parser.add_mutually_exclusive_group()
    additional_group.add_argument('--supplied-selection-file', type=Path,
        help='Append ordered direct supplied/Studio references after plan and direct state rows')
    additional_group.add_argument('--studio-selection-file', type=Path,
        help='Append ordered current Studio slot choices with subject_uses')
    execute_parser.add_argument('--studio', type=Path)
    execute_parser.add_argument("--max-side", type=int, default=1536)
    add_pack_runtime_arguments(execute_parser)

    example_parser = subparsers.add_parser(
        "example", help="Print a schema-derived CLI example"
    )
    example_parser.add_argument("example_name", choices=("plan",))

    schema_parser = subparsers.add_parser(
        "schema", help="Print a canonical JSON Schema"
    )
    schema_parser.add_argument(
        "schema_name", choices=("surface-lighting-plan",)
    )
    capabilities_parser = subparsers.add_parser(
        "capabilities", help="Inspect supported reference contributions before selecting their scope")
    capabilities_parser.add_argument('--influence', choices=INTENDED_INFLUENCES)

    args = parser.parse_args(argv)
    import reference_plan_runtime as implementation
    if args.command == "example":
        implementation._write_stdout(implementation.plan_cli_example())
        return 0
    if args.command == "schema":
        implementation._write_stdout(implementation.surface_lighting_schema())
        return 0
    if args.command == 'capabilities':
        from reference_contract import control_capabilities
        influences = [args.influence] if args.influence else INTENDED_INFLUENCES
        implementation._write_stdout({'available_contributions': {
            influence: {role: control_capabilities(influence, role)
                        for role in implementation.technical_roles_for(influence)} for influence in influences},
            'selection': 'JSON record uses select supported selected_controls explicitly. RECORD=INFLUENCE explicitly selects the whole supported use. control_expressions supplies actual input wording for selected controls.'})
        return 0
    runtime = implementation.resolve_pack_runtime(parser, args)
    implementation.configure_pack_runtime(runtime.settings)
    try:
        if args.command == "plan":
            plan = implementation.build_reference_use_plan(
                args.record_use,
                transport_mode=args.transport_mode,
                source_lighting_mode=args.source_lighting_mode,
                target_model=args.target_model,
                max_assets_per_record=args.max_assets_per_record,
                max_references=args.max_references,
                include_technical_roles=args.technical_role,
                light_sources=args.light_source_json,
                material_responses=args.material_response_json,
                unresolved_decisions=args.unresolved_decision,
            )
            args.out.parent.mkdir(parents=True, exist_ok=True)
            implementation.write_json_atomic(args.out, plan)
            implementation._write_stdout(plan)
        else:
            selection = (
                implementation._load_json_object(args.reference_selection)
                if args.reference_selection is not None
                else None
            )
            additional = None
            if args.studio_selection_file is not None:
                if args.studio is None:
                    raise ValueError('--studio is required for a Studio selection')
                additional = implementation.resolve_studio_reference_choices(args.studio, implementation.read_json_array(args.studio_selection_file))
            elif args.supplied_selection_file is not None:
                additional = implementation.read_json_array(args.supplied_selection_file)
            prepared = implementation.execute_reference_use_plan(
                implementation._load_json_object(args.plan),
                output_dir=args.output_dir,
                prompt_file=args.prompt_file,
                negative_file=args.negative_file,
                reference_selection=selection,
                additional_references=additional,
                max_side=args.max_side,
            )
            implementation._write_stdout(prepared)
        return 0
    except implementation.DependencyPreflightError as exc:
        implementation._write_stdout(
            {
                "ok": False,
                "error_code": "dependency-preflight-failed",
                "errors": [str(exc)],
                "dependency_preflight": exc.report,
            }
        )
        return 1
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        implementation._write_stdout({"ok": False, "errors": [str(exc)]})
        return 1
    finally:
        implementation.configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
