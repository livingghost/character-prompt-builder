#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from visual_evidence import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    root = Path(args.path)
    errors: list[str] = []
    dirs: list[Path] = []
    if (root / "visual-evidence-bundle.json").is_file():
        dirs = [root]
    elif root.is_dir():
        dirs = sorted(path for path in root.iterdir() if path.is_dir())
        if not dirs:
            errors.append(f"no visual-evidence bundle directory found under {root}")
    else:
        errors.append(f"not a bundle directory or a directory of bundles: {root}")
    reports = [validate_bundle(directory) for directory in dirs]
    errors.extend(error for report in reports for error in report["errors"])
    print(
        json.dumps(
            {
                "ok": not errors,
                "bundles": len(reports),
                "errors": errors,
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
