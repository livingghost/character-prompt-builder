#!/usr/bin/env python3
"""Inspect the actual authoring work and its derived changes.

The work contains its acquired baseline and one editable candidate. This report
reads that candidate; publication uses the same owner and actual content.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import operation_context


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()



def inspect_work(value: dict) -> dict:
    from authoring_work import resolve_work
    resolved = resolve_work(value, complete=True)
    return {key: item for key, item in resolved.items() if key != 'content'}


def main(argv: Sequence[str] | None = None) -> int:
    parser = operation_context.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('work', type=Path, help='The actual authoring work to inspect')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    import execution_contract as c
    report = inspect_work(c.decode(args.work.read_bytes()))
    if args.out:
        from pack_manager import atomic_write_json
        atomic_write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(operation_context.run_cli(main))
