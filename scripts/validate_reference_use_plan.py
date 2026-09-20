#!/usr/bin/env python3
"""Validate one reference-use plan against its current active pack state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from catalog_cli import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from reference_runtime import validate_reference_use_plan


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        value: Any = json.loads(args.plan.read_text(encoding="utf-8"))
        report = validate_reference_use_plan(value)
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        report = {"ok": False, "errors": [str(exc)], "reference_count": 0}
    finally:
        configure_pack_runtime(None)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
