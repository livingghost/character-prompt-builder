#!/usr/bin/env python3
"""Build a Visual State Projection from identity, state, and scene context."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Sequence
from state_protocol import build_projection, load_json, write_json

def main(argv: Sequence[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="Build Visual State Projection 2.0.")
    p.add_argument('--identity-contract',required=True); p.add_argument('--species-profile',required=True); p.add_argument('--individual-morphology',required=True); p.add_argument('--state-snapshot',required=True)
    p.add_argument('--scene-context',required=True); p.add_argument('--request',required=True)
    p.add_argument('--previous'); p.add_argument('--out',required=True); a=p.parse_args(argv)
    try:
        value=build_projection(load_json(Path(a.identity_contract)),load_json(Path(a.species_profile)),load_json(Path(a.individual_morphology)),load_json(Path(a.state_snapshot)),load_json(Path(a.scene_context)),load_json(Path(a.request)),load_json(Path(a.previous)) if a.previous else None)
        write_json(Path(a.out),value); print(json.dumps(value,ensure_ascii=False,indent=2)); return 0
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},ensure_ascii=False,indent=2)); return 1
if __name__=='__main__': raise SystemExit(main())
