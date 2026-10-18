#!/usr/bin/env python3
"""Execute a complete synthetic mask-to-candidate pipeline, without network."""
from pathlib import Path
import argparse
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import execution_contract as c
import scene_mask_fixtures as f
import production_case_fixtures as base
import production_workflow as workflow
import scene_mask_planner as masks


def run(out:Path)->dict:
    if out.exists():raise FileExistsError('Use a new example directory.')
    case=f.production(out/'studio',out/'runtime');root=case['root']
    from production_compiler import check_task
    checked=check_task(root,'task.json')
    if not checked['ok']:raise RuntimeError(checked)
    prepared=workflow.prepare(root,'task.json');run=prepared['run']
    directory=root/'production/runs'/run
    preview=c.load(directory/'request-preview.json')
    base.fill_decisions(root,run,'decisions.json')
    status=workflow.execute(root,run,decisions_file='decisions.json')
    state=status['runs'][0]
    if not state['candidates']:raise RuntimeError(status)
    _,_,_,rows=workflow.load_run(root,run)
    candidate=next(row for row in rows if row['event']=='candidate')
    item=candidate['data']['files'][0]
    report=masks.compare(root,'mask-binding.json',item['path'],'comparison')
    result={'synthetic':True,'live_provider_calls':0,'mask_binding':str(root/'mask-binding.json'),
            'run':run,'request_preview':str(directory/'request-preview.json'),
            'candidate_path':str(root/item['path']),'candidate_sha256':item['sha256'],
            'comparison':report,'provider_image_quality':'not-tested','user_acceptance':'not-requested',
            'source_png_preserved':c.digest((root/'source.png').read_bytes())==c.load(root/'mask-plan.json')['source']['sha256']}
    (out/'result.json').write_bytes(c.encoded(result));return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path);parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as folder:
            result=run(Path(folder)/'example')
    elif args.out:result=run(args.out.resolve())
    else:parser.error('Use --out or --check.')
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
