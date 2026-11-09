#!/usr/bin/env python3
"""Save authored text, deliver its exact bytes locally, and record its review."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SKILL/'scripts'))
import production_authoring
import reading_fixtures
from io_budget import environment_seconds


def run(out: Path) -> dict:
    if out.exists(): raise ValueError('choose a new output directory')
    out.mkdir(parents=True)
    log=[]
    def invoke(argv, *, parse=True):
        p=subprocess.run(argv,cwd=out,capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=environment_seconds('EXAMPLE_COMMAND_TIMEOUT_SECONDS'))
        stdout,stderr=p.stdout.decode('utf-8'),p.stderr.decode('utf-8')
        log.append({'argv':argv,'returncode':p.returncode,'stdout':stdout,'stderr':stderr})
        (out/'commands.json').write_text(json.dumps(log,indent=2)+'\n',encoding='utf-8')
        if p.returncode: raise ValueError(stdout+stderr)
        return json.loads(stdout) if parse else stdout
    def command(script: str, *args: str, parse: bool = True):
        return invoke([sys.executable,'-B',str(SKILL/'scripts'/script),*map(str,args)],parse=parse)
    def write(name,value): (out/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    command('work_ledger.py','--studio',out,'begin','--goal','Write, deliver and review a synthetic room sentence','--step','compose',parse=False)
    task_id=json.loads((out/'work/current.json').read_text(encoding='utf-8'))['task_id']
    (out/'world.md').write_bytes(b'A room contains one lamp. No characters are specified.\n')
    (out/'delivery.txt').write_bytes(b'One lamp stands in the room.\n')
    spec=production_authoring.seed(out,route='development',artifact='text',execution='authored',task_id=task_id)
    spec.update(sources=[{'id':'world','path':'world.md','role':'world','disposition':'applied','locator':'whole','reason':'Synthetic fixture premise.'}],
        criteria=[{'id':'world','strength':'hard','text':'One lamp, no added characters.','evidence':'text'}],
        authored={'requirements':['save','delivery','review']})
    spec['direction'].update(purpose='Write one sentence about the declared empty room.',
        intended_effect='Preserve the supplied room and lamp without adding a cast.',basis=['world'])
    reading_fixtures.task_reading(out,spec)
    write('task.json',spec)
    draft=command('production_workflow.py','draft-inputs','--root',out,'--task','task.json','--out-dir','editing')
    choices=json.loads((out/draft['choices_file']).read_text(encoding='utf-8'))
    choices['reading']['reading_key']=json.loads((out/spec['route_reading']).read_text(encoding='utf-8'))['reading_key']
    write(draft['choices_file'],choices)
    result=command('production_workflow.py','save','--root',out,'--choices',draft['choices_file']); rid=result['run']
    def workflow(op,*args): return command('production_workflow.py',op,'--root',out,'--run',rid,*args)
    workflow('deliver','--to','deliveries/sentence.txt')
    workflow('workspace','--phase','input')
    if (out/'deliveries/sentence.txt').read_bytes() != b'One lamp stands in the room.\n':
        raise ValueError('the delivered text differs from the authored fixture')
    workflow('workspace','--phase','review')
    review=workflow('draft-review','--out','review.json')
    review.update(reviewer='Synthetic text reviewer',observations=[{
        'evidence':'candidate','locator':{'kind':'whole'},
        'observation':'The actual saved sentence names one lamp in the room and introduces no character.',
        'interpretation':'It preserves the declared room and lamp.',
        'limitations':['Literal fixture inspection only; no generated-image or audience assessment.']}],
        conclusion='The saved text preserves the supplied fixture premise.')
    review['checks'][0].update(verdict='pass',observation_indices=[0],
        reason='Compared the actual saved sentence with the retained world premise.')
    write('review.json',review)
    workflow('review-authored','--file','review.json')
    command('work_ledger.py','--studio',out,'step','1',parse=False)
    command('work_ledger.py','--studio',out,'finish','--run',rid,parse=False)
    resumed=workflow('status'); workflow('impact')
    final={'ok':resumed['ok'] and resumed['runs'][0]['task_disposition']=='completed' and resumed['runs'][0]['next_action'] is None,
        'run':rid,'commands':len(log),'output':result['artifact'],'fixture_only':True,
        'delivery_channel':'local file','network_calls':0}
    write('result.json',final); return final


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    print(json.dumps(run(a.out.absolute()),indent=2))
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    main()
