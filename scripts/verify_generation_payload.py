#!/usr/bin/env python3
"""Verify and export an exact Character Prompt Builder generation payload."""
from __future__ import annotations
import operation_context as _operation_context

import json
from pathlib import Path
from typing import Sequence
from pack_runtime_cli import add_pack_runtime_arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description="Verify an exact Character Prompt Builder payload.",
        epilog="A relative path is a /-separated path below --studio-root; an absolute path is taken as given. "
        "Each output is a new file holding the verified text exactly.",
    )
    parser.add_argument("payload", help="The Generation Package JSON")
    parser.add_argument("--studio-root", type=Path, help="Source and studio root for live visual checks and relative paths")
    parser.add_argument("--prompt-out", help="New file for the effective prompt")
    parser.add_argument("--negative-out", help="New file for the portable negative prompt")
    parser.add_argument("--native-negative-out", help="New file for the native negative subset")
    parser.add_argument("--payload-out", help="New file for the verification result")
    parser.add_argument(
        "--target",
        help=(
            "Emit the package's already committed paste-ready rendition. The value must "
            "exactly match the committed model; no transport is inferred."
        ),
    )
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    import generation_payload_validation as implementation
    runtime = implementation.resolve_pack_runtime(parser, args)
    implementation.configure_pack_runtime(runtime.settings)

    from production_binding import new_output, studio_file, report_failure, write_new
    try:
        root = args.studio_root.absolute() if args.studio_root is not None else None
        payload_path = studio_file(root, args.payload, option="payload", root_option="--studio-root").resolve()
        outputs = []
        for option, render in implementation.OUTPUTS:
            value = getattr(args, option[2:].replace("-", "_"))
            if value is not None:
                outputs.append((option, value, new_output(root, value, option=option, root_option="--studio-root"), render))
        if len({path.absolute() for _, _, path, _ in outputs}) != len(outputs):
            raise ValueError("each output option needs its own new file")
        data = implementation.load_payload(payload_path)
        result = implementation.verify(data, package_root=payload_path.parent, studio=args.studio_root)
        if args.target:
            result["paste"] = implementation.emit_paste_for_target(
                data,
                args.target,
                package_root=payload_path.parent,
                studio=args.studio_root,
            )
        for option, value, path, render in outputs:
            write_new(path, render(result), option=option, value=value)
    except (ValueError, OSError) as exc:
        return report_failure(exc, phase="package-verification")
    finally:
        implementation.configure_pack_runtime(None)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
