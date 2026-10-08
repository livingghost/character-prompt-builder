#!/usr/bin/env python3
"""Build an offline, synthetic story and its automatic human reading Flow."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import story_timeline as timeline
from story_flow_fixtures import setup, graph_setup


def build(out: Path, *, graph: bool = False, merge: bool = False) -> dict:
    if graph: graph_setup(out, merge=merge)
    else: setup(out)
    result=timeline.refresh(out)
    if not result['ok'] or not result['ledger_ok']:
        raise ValueError(json.dumps(result))
    return {'ok':True,'synthetic':True,'view':str(out/timeline.OUTPUT) + ('#graph' if graph else ''),
            'scenes':0 if graph else 3,'semantic_verdict':None,
            'reading_question':'What explains the change from suspicion to entrusting the only escape key?'}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True,help='new synthetic Studio directory')
    parser.add_argument('--graph',action='store_true',help='synthetic cause fork and a recorded revision')
    parser.add_argument('--merge',action='store_true',help='with --graph, one revision replaces both branch accounts')
    args=parser.parse_args()
    if args.merge and not args.graph: parser.error('--merge requires --graph')
    print(json.dumps(build(args.out.resolve(),graph=args.graph,merge=args.merge),indent=2))
    return 0


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
