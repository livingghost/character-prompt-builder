#!/usr/bin/env python3
"""Build one deterministic record-scoped visual reference-use plan."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
from pathlib import Path
from typing import Sequence

from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from reference_plan_cli_contract import add_reference_plan_arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    add_reference_plan_arguments(parser)
    parser.add_argument("--out", type=Path, required=True)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    from catalog_api import configure_pack_runtime
    from generation_references import write_json_atomic
    from reference_plan_runtime import build_reference_use_plan
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        plan = build_reference_use_plan(
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
        write_json_atomic(args.out, plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "errors": [str(exc)]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
