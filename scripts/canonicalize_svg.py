#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from visual_evidence import canonicalize_svg

def main() -> int:
    parser=argparse.ArgumentParser(description="Validate and canonicalize one safe static SVG.")
    parser.add_argument("source")
    parser.add_argument("output")
    args=parser.parse_args()
    try:
        result=canonicalize_svg(Path(args.source).resolve(), Path(args.output).resolve())
    except (ValueError,OSError) as exc:
        result={"ok":False,"errors":[str(exc)]}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get("ok") else 1
if __name__=="__main__": raise SystemExit(main())
