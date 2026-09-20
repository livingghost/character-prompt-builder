#!/usr/bin/env python3
"""Plan a coverage-driven reference bundle from a Character Identity Contract."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Sequence
from state_protocol import load_json, plan_reference_bundle

def build_plan(*, identity_contract, species_profile, individual_morphology, style_family, target_model, policy, out_dir, era_contract=None, appearance_variant=None):
    return plan_reference_bundle(
        identity_contract,
        species_profile=species_profile,
        individual_morphology=individual_morphology,
        style_family_id=style_family,
        target_model=target_model,
        policy=policy,
        out_dir=out_dir,
        era_contract=era_contract,
        appearance_variant=appearance_variant,
    )

def main(argv: Sequence[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="Build a Reference Bundle Plan 2.0.")
    p.add_argument('--identity-contract',required=True); p.add_argument('--species-profile',required=True); p.add_argument('--individual-morphology',required=True); p.add_argument('--style-family',required=True)
    p.add_argument('--target-model',required=True); p.add_argument('--policy',choices=['core-coverage','series-coverage','motion-evaluation'],default='core-coverage')
    p.add_argument('--era-contract'); p.add_argument('--appearance-variant'); p.add_argument('--out-dir',required=True)
    a=p.parse_args(argv)
    try:
        out=Path(a.out_dir)
        value=build_plan(identity_contract=load_json(Path(a.identity_contract)),species_profile=load_json(Path(a.species_profile)),individual_morphology=load_json(Path(a.individual_morphology)),style_family=a.style_family,target_model=a.target_model,policy=a.policy,out_dir=out,era_contract=load_json(Path(a.era_contract)) if a.era_contract else None,appearance_variant=load_json(Path(a.appearance_variant)) if a.appearance_variant else None)
        print(json.dumps(value,ensure_ascii=False,indent=2)); return 0
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},ensure_ascii=False,indent=2)); return 1
if __name__=='__main__': raise SystemExit(main())
