#!/usr/bin/env python3
"""Exercise a moment query and the artifact-bearing production workflow with fixtures."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import authorial_intent_audit
import production_fixtures as fixture


def write(root: Path, name: str, value):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return p


def change(path, value=None, *, entity_type='world', entity_id='WORLD', operation='set', **extra):
    row={'entity_type':entity_type,'entity_id':entity_id,'path':path,'operation':operation,
         'persistence':'persistent-until-superseded',**extra}
    if operation!='remove':row['value']=value
    return row


def event(identifier, order, changes, **extra):
    return {'artifact_type':'state-event','event_id':identifier,'timeline_id':'main',
        'event_scope':'background-process','targets':sorted({c['entity_id'] for c in changes}),
        'effective_order':order,'effective_from':f'story:{order}','recorded_at':'synthetic fixture',
        'occurrence':'offscreen','canon_status':'approved','atomic':True,
        'cause':{'type':'test-declaration','reference':'DESIGN'},'preconditions':[],
        'changes':changes,'evidence':[{'source_id':'DESIGN','locator':'Test premise','basis':'author-decision'}],
        'supersedes_event_ids':[],**extra}


def process(identifier='RECOVERY', start=10, *, path='/physical_state/condition', entity_type='character', entity_id='A'):
    return {'artifact_type':'state-process','process_id':identifier,'timeline_id':'main','entity_type':entity_type,
        'entity_id':entity_id,'path':path,'process_type':'authored progression','started_order':start,
        'milestones':[{'offset':0,'state':'tired'},{'offset':10,'state':'ready'}],
        'interruption_policy':'fixed','canon_status':'approved',
        'evidence':[{'source_id':'DESIGN','locator':'Test progression','basis':'author-decision'}]}


def pin(root, query):
    for row in query['sources']:
        row['sha256']=hashlib.sha256((root/row['path']).read_bytes()).hexdigest()
    write(root,'query.json',query)


def write_inputs(root: Path):
    root.mkdir(parents=True,exist_ok=True)
    base={'characters':{'A':{'mood':'tense','knows_signal':False,'physical_state':{'condition':'resting'}},
                        'B':{'knows_signal':False,'belief':'the signal has not arrived'}},
          'relationships':{},'environments':{'SPACE':{'light':'soft'}},'props':{},
          'world':{'signal':True,'work_streams':{'one':{'status':'pending'},'two':{'status':'pending'}},
                   'commitments':{'reply':{'status':'unresolved'}},'items':['A','B','C']}}
    events=[event('START_ONE',10,[change('/work_streams/one/status','active')]),
            event('START_TWO',10,[change('/work_streams/two/status','active')]),
            event('ATTENTION',10,[change('/attention','task',entity_type='character',entity_id='A',persistence='scene-local')],scene_context_id='CTX:work.room'),
            event('LEARN',20,[change('/knows_signal',True,entity_type='character',entity_id='A')]),
            event('END_ONE',30,[change('/work_streams/one/status','complete')])]
    write(root,'base.json',base);write(root,'events.jsonl',''.join(json.dumps(x)+'\n' for x in events));write(root,'processes.json',[])
    write(root,'coverage.json',{'timeline_id':'main','start_order':0,'through_order':100,'basis':'Synthetic authored coverage, not a completeness claim.'})
    write(root,'design.md','# Test premise\nSynthetic state and decisions; not a user-approved story. PRIVATE_DESIGN_NOTE\n')
    write(root,'persona.md','# Portrayal fixture\n## Earlier period\nA answers briefly and shows uncertainty through pauses. PRIVATE_PERSONA_NOTE\n## Later period\nA initiates conversation and allows longer answers.\n')
    intent='### Intent steady\n'+''.join('- **'+f+'**: '+('adopted' if f=='status' else 'Synthetic portrayal decision for this fixture.')+'\n' for f in authorial_intent_audit.REQUIRED_FIELDS)
    write(root,'intent.md',intent)
    evidence=[{'source_id':'DESIGN','locator':'Test premise','basis':'author-decision'}]
    query={'artifact_type':'story-context-query','query_id':'moment.demo','sources':[{'source_id':i,'path':p,'sha256':'0'*64} for i,p in [('BASE','base.json'),('EVENTS','events.jsonl'),('PROCESSES','processes.json'),('COVERAGE','coverage.json'),('DESIGN','design.md'),('PERSONA','persona.md'),('INTENT','intent.md')]],
        'timeline':{'timeline_id':'main','base_source':'BASE','events_source':'EVENTS','processes_source':'PROCESSES',
                    'base_provenance':[{'pointer':p,'evidence':evidence} for p in ['/characters/A','/characters/B','/environments/SPACE','/world']]},
        'at':{'story_order':15,'story_time':'between the declared changes'},'coverage_source_id':'COVERAGE',
        'scene_context_ids':['CTX:work.room'],
        'indexes':[{'index_id':'work','scene_context_id':None,'pointer':'/world/work_streams','group_by':'/status'}],
        'requirements':[{'requirement_id':'active','scene_context_id':'CTX:work.room','pointer':'/world/work_streams/one/status','test':'equals','value':'active','purpose':'This view depicts the activity before completion.'}],
        'author_bindings':[{'binding_id':'voice','role':'persona epoch','source_id':'PERSONA','selector':{'kind':'section','heading':'## Earlier period'},'start_order':0,'end_order':20,'scene_context_ids':[]},
                           {'binding_id':'intent','role':'portrayal intent','source_id':'INTENT','selector':{'kind':'intent','intent_id':'steady'},'start_order':0,'end_order':None,'scene_context_ids':[]}],
        'views':[{'view_id':'depiction.main','recipient':'writer','purpose':'A bounded moment portrayal','scene_context_id':'CTX:work.room',
                 'fields':['/characters/A/mood','/characters/A/attention','/environments/SPACE/light'],
                 'requirement_ids':['active'],'guidance':[{'binding_ids':['voice','intent'],'instruction':'Keep the response concise; show the pause without making the character evasive.'}],
                 'instructions':['Depict the selected moment, not a new event.']}]}
    pin(root,query)
    return query


def run(out: Path):
    if out.exists():raise ValueError('choose a new output directory')
    q=write_inputs(out);log=[]
    def command(script,*args):
        argv=[sys.executable,'-B',str(ROOT/'scripts'/script),*map(str,args)]
        p=subprocess.run(argv,cwd=out,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True)
        log.append({'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});write(out,'commands.json',log)
        if p.returncode:raise ValueError(p.stdout+p.stderr)
        return json.loads(p.stdout)
    command('story_context.py','inspect','--root',out,'--query','query.json')
    command('story_context.py','build','--root',out,'--query','query.json','--out',out/'moment','--require-fields')
    command('story_context.py','verify','--root',out,'--query','query.json','--bundle',out/'moment','--require-fields')
    import work_ledger
    task=work_ledger.begin(out,'Synthetic moment delivery',['prepare','deliver'])
    write(out,'delivery.txt','Write one sentence using the selected moment fields and guidance.\n')
    spec={'task_id':task['task_id'],'route':'story-context','features':[], 'sources':[],
        'delivery':{'path':'delivery.txt','transport':'bounded-context','translation_notes':'Selected state and explicit portrayal instruction only.'},
        'criteria':[{'id':'moment','strength':'hard','text':'Respect the selected moment and portrayal direction.'}],
        'world_views':[],'moment_views':[{'query':'query.json','bundle':'moment','view_id':'depiction.main'}]}
    fixture.task(out,spec)
    write(out,'task.json',spec)
    result=command('production_workflow.py','prepare','--root',out,'--task','task.json');rid=result['run']
    def workflow(op,*args):return command('production_workflow.py',op,'--root',out,'--run',rid,*args)
    def authorize(intent):
        number=len(log);ip=f'intent-{number}.json';rp=f'authorization-{number}.json'
        write(out,ip,intent)
        request=workflow('draft-authorization','--grant','fixture-grant','--intent',ip,'--out',rp)
        request['reason']='Explicit synthetic fixture declaration; not user consent.'
        write(out,rp,request)
        return workflow('authorize','--file',rp)['sha256']
    intent=workflow('handoff-intent','--recipient','synthetic writer','--method','manual')
    workflow('handoff','--recipient','synthetic writer','--method','manual','--authorization',authorize(intent))
    write(out,'output.txt','A pauses in the soft light, then gives a brief answer.\n')
    candidate=workflow('capture','--artifact','output.txt','--note','Handwritten fixture, not generated media.')
    review=workflow('draft-review','--candidate',candidate['sha256'],'--out','review.json')
    review.update(reviewer='synthetic reviewer',observations=[{'locator':{'kind':'whole'},'observation':'The sentence uses only the declared fields and direction.'}],conclusion='Fixture inspection, not user approval.')
    review['checks'][0].update(verdict='pass',observation_indices=[0],reason='Literal fixture inspection.')
    fixture.observation(review)
    write(out,'review.json',review);workflow('review','--file','review.json')
    selection=workflow('draft-selection','--candidate',candidate['sha256'],'--out','selection.json')
    selection.update(selector=fixture.ACTOR,reason='Exercise delivery without canon adoption.')
    write(out,'selection.json',selection)
    selection['authorization']=authorize(workflow('selection-intent','--file','selection.json'))
    write(out,'selection.json',selection);workflow('select','--file','selection.json');workflow('complete')
    for i in (1,2):work_ledger.step_done(out,i)
    work_ledger.finish(out)
    result=workflow('resume');write(out,'result.json',result)
    return {'ok':result['ok'] and result['next']=='done','run':rid,'commands':len(log),'fixture_only':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--inputs-only',action='store_true');a=parser.parse_args()
    if a.inputs_only:
        if a.out.exists():raise ValueError('choose a new directory')
        write_inputs(a.out);print(json.dumps({'ok':True,'inputs':str(a.out)}))
    else:print(json.dumps(run(a.out.absolute()),indent=2))
