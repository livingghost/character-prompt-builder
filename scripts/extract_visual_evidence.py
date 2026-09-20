#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from pathlib import Path

from native_vector_visual_evidence import process_source


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract one native-dimension compact perceptual three-layer visual-evidence bundle."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New bundle directory; the destination must not already exist",
    )
    parser.add_argument(
        "--keep-rejected",
        type=Path,
        default=None,
        help=(
            "Keep a bundle that fails the perceptual fidelity gate in this new directory "
            "instead of discarding it; the destination must not already exist"
        ),
    )
    parser.add_argument("--record", action="append", default=[])
    parser.add_argument("--disposition", default="reference-evidence")
    args = parser.parse_args()
    source = args.source
    if not source.is_file():
        parser.error(f"source file does not exist: {source}")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    entry = {
        "source_sha256": source_sha,
        "source_media_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
        "canonical_record_ids": args.record,
        "disposition": args.disposition,
        "evidence_relation": "reference-evidence",
        "semantic_summary": "",
    }
    try:
        report = process_source(
            source, entry, args.output, rejected_output=args.keep_rejected
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
