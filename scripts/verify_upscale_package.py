#!/usr/bin/env python3
"""Verify one committed Character Prompt Builder Upscale Package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from catalog_cli import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from state_protocol import parse_json
from upscale_package import verify_upscale_package


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    package_path = args.package.resolve(strict=True)
    value = parse_json(package_path.read_text(encoding="utf-8"))
    result = verify_upscale_package(value, package_root=package_path.parent)
    print(json.dumps({"ok": True, "package": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
