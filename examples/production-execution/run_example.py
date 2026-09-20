#!/usr/bin/env python3
"""Synthetic end-to-end CLI fixture. No generated fiction or human approval."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SKILL/'scripts'))
import production_fixtures as fixture


def run(out: Path) -> dict:
    if out.exists(): raise ValueError('choose a new output directory')
    out.mkdir(parents=True)
    log=[]
    def command(script: str, *args: str, parse: bool = True):
        argv=[sys.executable,'-B',str(SKILL/'scripts'/script),*map(str,args)]
        p=subprocess.run(argv,cwd=out,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        log.append({'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        (out/'commands.json').write_text(json.dumps(log,indent=2)+'\n')
        if p.returncode: raise ValueError(p.stdout+p.stderr)
        return json.loads(p.stdout) if parse else p.stdout
    def write(name,value): (out/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    command('work_ledger.py','--studio',out,'begin','--goal','Synthetic unpeopled room fixture','--step','prepare','--step','deliver',parse=False)
    task_id=json.loads((out/'work/current.json').read_text())['task_id']
    (out/'world.md').write_text('A room contains one lamp. No characters are specified.\n')
    (out/'delivery.txt').write_text('Describe the declared room in one sentence.\n')
    spec={'task_id':task_id,'route':'development','features':[],
          'sources':[{'id':'world','path':'world.md','role':'world','disposition':'applied','locator':'whole','reason':'Synthetic fixture premise.'}],
          'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Minimal declared-world fixture.'},
          'criteria':[{'id':'world','strength':'hard','text':'One lamp, no added characters.'}], 'world_views':[]}
    fixture.task(out,spec)
    write('task.json',spec)
    result=command('production_workflow.py','prepare','--root',out,'--task','task.json'); rid=result['run']
    def workflow(op,*args): return command('production_workflow.py',op,'--root',out,'--run',rid,*args)
    def authorize(intent):
        number=len(log); ip=f'intent-{number}.json'; rp=f'authorization-{number}.json'
        write(ip,intent)
        request=workflow('draft-authorization','--grant','fixture-grant','--intent',ip,'--out',rp)
        request['reason']='Explicit synthetic fixture declaration; not user consent.'
        write(rp,request)
        return workflow('authorize','--file',rp)['sha256']
    intent=workflow('handoff-intent','--recipient','synthetic fixture','--method','manual')
    workflow('handoff','--recipient','synthetic fixture','--method','manual','--authorization',authorize(intent))
    (out/'output.txt').write_text('One lamp stands in the room.\n')
    candidate=workflow('capture','--artifact','output.txt','--note','Handwritten synthetic fixture, not model output.')
    review=workflow('draft-review','--candidate',candidate['sha256'],'--out','review.json')
    review.update(reviewer='synthetic-test-reviewer',observations=[{'locator':{'kind':'lines','start':1,'end':1},'observation':'The fixture names one lamp and no character.'}],conclusion='Synthetic positive fixture, not user approval.')
    review['checks'][0].update(verdict='pass',observation_indices=[0],reason='Literal fixture inspection.')
    fixture.observation(review)
    write('review.json',review); workflow('review','--file','review.json')
    selection=workflow('draft-selection','--candidate',candidate['sha256'],'--out','selection.json')
    selection.update(selector=fixture.ACTOR,reason='Exercise the delivery-only path.')
    write('selection.json',selection)
    selection['authorization']=authorize(workflow('selection-intent','--file','selection.json'))
    write('selection.json',selection); workflow('select','--file','selection.json')
    workflow('complete')
    for i in [1,2]: command('work_ledger.py','--studio',out,'step',i,parse=False)
    command('work_ledger.py','--studio',out,'finish',parse=False)
    resumed=workflow('resume'); workflow('impact')
    final={'ok':resumed['ok'] and resumed['next']=='done','run':rid,'commands':len(log),'output':str(out/'output.txt'),'fixture_only':True}
    write('result.json',final); return final


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    print(json.dumps(run(a.out.absolute()),indent=2))
if __name__=='__main__': main()
