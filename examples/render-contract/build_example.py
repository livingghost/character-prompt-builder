#!/usr/bin/env python3
"""Exercise a synthetic rendering contract without a service or generated image."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_contract_lib as r

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify the local synthetic example')
    parser.add_argument('--out', type=Path, help='New contract file; never overwrite')
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    def load(name):
        return json.loads((here / name).read_text(encoding='utf-8'))
    try:
        model, intent, parameters = load('model.json'), load('intent.json'), load('parameters.json')
        prompt = (here / 'prompt.txt').read_text(encoding='utf-8').strip()
        plan = r.compile_contract(model, None, intent, parameters, prompt=prompt, reference_count=0)
        r.verify_contract(plan, intent=intent, parameters=plan['parameters'], prompt=prompt, record=model, reference_count=0)
        r.dispatch_values(plan, seed=17, count=1)
        r.check_wire(plan, {**plan['parameters'], 'seed':17, 'numberResults':1},seed=17,count=1)
        if args.out:
            with args.out.open('x', encoding='utf-8', newline='\n') as target:
                target.write(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
        print(r.summary(plan))
        print(json.dumps({'ok':True,'synthetic':True,'network_calls':0,'images_generated':0}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]}));return 1

if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
