#!/usr/bin/env python3
"""Build a sealed Scene Context Snapshot from a resolved world snapshot."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Sequence
from state_protocol import build_scene_context, load_json, write_json

def main(argv: Sequence[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="Build Scene Context Snapshot 2.0.")
    p.add_argument('--request',required=True); p.add_argument('--world-snapshot',required=True)
    p.add_argument('--character-snapshot',action='append',default=[]); p.add_argument('--out',required=True)
    a=p.parse_args(argv)
    try:
        value=build_scene_context(load_json(Path(a.request)),load_json(Path(a.world_snapshot)),[load_json(Path(x)) for x in a.character_snapshot])
        write_json(Path(a.out),value); print(json.dumps(value,ensure_ascii=False,indent=2)); return 0
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},ensure_ascii=False,indent=2)); return 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
