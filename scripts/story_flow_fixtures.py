"""Synthetic story sources for Flow tests and the runnable demo.

The scenario intentionally leaves a motivation unexplained. Structural state
validity does not settle whether its author should add a reconciliation scene.
"""
from __future__ import annotations
from pathlib import Path
import copy

import execution_contract as c
from narrative import content_sha256
from protocol_contract import finalize_artifact
from story_timeline_fixtures import setup as setup_ledger, event, process, view


def narrative() -> dict:
    return {'artifact_type':'narrative','series_id':'harbor-story','timeline_id':'main','medium':'screen',
        'themes':[],
        'characters':[{'id':'C01','name':'Mara','persona':'narrative/personas/mara.md'},
                      {'id':'C02','name':'Ivo','persona':'narrative/personas/ivo.md'}],
        'arcs':[{'id':'trust','name':'Trust under pressure','type':'relationship','status':'in-progress',
                 'themes':[],'characters':['C01','C02'],'want':'Leave the harbor together.',
                 'need':'Decide what evidence can justify trust.'}],
        'chapters':[
            {'id':'ch1','number':1,'title':'The accusation','status':'complete','arcs':['trust'],
             'depicts':['A report changes how Mara reads her companion.'],'story_order_start':0,'story_order_end':9},
            {'id':'ch2','number':2,'title':'Separate routes','status':'in-progress','arcs':['trust'],
             'depicts':['The two cross the harbor on different routes.'],'story_order_start':10,'story_order_end':19},
            {'id':'ch3','number':3,'title':'The only key','status':'planned','arcs':['trust'],
             'depicts':['Mara places the means of escape in Ivo\'s hands.'],'story_order_start':20,'story_order_end':29}],
        'promises':[{'id':'key','statement':'The only escape key will decide who can leave.',
                     'status':'planted','planted':'ch1','arcs':['trust'],'characters':['C01','C02']}],
        'questions':[{'id':'betrayal','statement':'Did Ivo actually betray the group?','status':'open',
                      'introduced':'ch1','arcs':['trust'],'characters':['C01','C02']}],
        'knowledge':[{'id':'accusation','fact':'The accusation is a report, not proof.',
                     'known_by':['audience'],'learned_in':'ch1'}]}


def context(identifier: str, start: int, end: int, timeline: str = 'main') -> dict:
    value={'artifact_type':'scene-context-snapshot','scene_context_id':identifier,'timeline_id':timeline,
        'story_order_start':start,'story_order_end':end,'story_time_start':'order:'+str(start),
        'story_time_end':'order:'+str(end),'location_snapshot':{},'environment_snapshot':{},
        'active_character_snapshots':[],'relationship_snapshots':[],'prop_and_inventory_bindings':[],
        'social_context':{},'viewer_disclosure_state':{},'planned_events':[],'context_snapshot_sha256':'0'*64}
    return finalize_artifact(value)


def scene(identifier: str, chapter: str, number: int, proposition: str, beats: list[str],
          consequence: str, document: dict, *, context_path: str | None = None) -> dict:
    value={'artifact_type':'scene-plot','scene_id':identifier,'chapter':chapter,'order':number,
        'narrative_sha256':content_sha256(document),'arcs':['trust'],'characters':['C01','C02'],
        'themes':[],'focalization':{'kind':'external'},
        'setting':{'interior_exterior':'exterior','location':'harbor','where':'beside the flood gates',
                   'time_of_day':'before dawn'},
        'scene_function':proposition,'delivery_role':'Scene in the declared harbor story.','proposition':proposition,
        'beats':[{'id':'b'+str(i+1),'beat':text,'visibility':'visible'} for i,text in enumerate(beats)],
        'exchanges':[],
        'placement':[{'statement':'The participants occupy the described harbor location.','from':['b1']}],
        'must_preserve':[{'statement':'Preserve the actions recorded in this scene.','from':['b1']}],
        'free':[{'statement':'The lens and framing remain open.'}],
        'state_changes':[{'target':'the group','change':consequence,'from':['b'+str(len(beats))]}] if consequence else [],
        'relationship_delta':[],
        'realization':{'kind':'shots','units':[{'id':identifier+'-shot'+str(i+1),'focal_beat':'b'+str(i+1),
                       'shows':[{'statement':text,'from':['b'+str(i+1)]}],
                       'composition':[{'statement':'Observe the recorded action at eye level.','from':['b'+str(i+1)]}]} for i,text in enumerate(beats)]}}
    if context_path:value['setting']['scene_context']=context_path
    return value


def setup(root: Path, *, include_state: bool = True, include_scenes: bool = True) -> dict:
    rows=[
        event('E-accusation',1,'suspects Ivo',path='/emotional_state/trust',scene='SC-gate',persistence='persistent-until-superseded'),
        event('E-routes',11,'separate paths',path='/physical_state/location',scene='SC-routes',persistence='persistent-until-superseded'),
        event('E-key',21,'Ivo carries the key',path='/equipment_state/key',scene='SC-key',persistence='persistent-until-superseded')]
    notes=['Mara hears that Ivo betrayed the group and conceals the escape key.',
           'They approach the tower by separate routes; no reconciliation is recorded.',
           'Mara gives Ivo the only key and asks him to lead the escape.']
    for row,note in zip(rows,notes):
        row['notes']=[note];row['cause']={'type':'author-decision','reference':'Synthetic scenario source.'}
        row['changes'].append({**row['changes'][0], 'path':'/performance_state/current_action',
                               'value':note, 'persistence':'scene-local'})
    data=setup_ledger(root,events=rows,views=[
        {**view('gate',1,scene='SC-gate'),'label':'The accusation'},
        {**view('key',21,scene='SC-key'),'label':'The key changes hands'}])
    n=narrative();c.atomic_write_json(root/'narrative/narrative.json',n)
    specs=[
        ('gate','ch1','SC-gate',0,9,notes[0],['A messenger repeats the accusation.','Mara closes her hand around the key.'],'Mara remains suspicious.'),
        ('routes','ch2','SC-routes',10,19,notes[1],['Mara takes the river path.','Ivo crosses the market alone.'],'They reach the tower separately.'),
        ('key','ch3','SC-key',20,29,notes[2],['Mara places the only escape key in Ivo\'s hand.','Ivo leads while Mara follows.'],'Ivo controls their only means of escape.')]
    scenes=[]
    for ident,chapter,cid,start,end,proposition,beats,consequence in specs:
        path=f'state/contexts/{ident}.json';c.atomic_write_json(root/path,context(cid,start,end))
        sc=scene(ident,chapter,1,proposition,beats,consequence,n,context_path=path)
        scenes.append(sc)
        if include_scenes:c.atomic_write_json(root/f'narrative/scenes/{ident}-plot.json',sc)
    if not include_state:
        for name in ['state/timeline-view.json','state/world-state-base.json','state/events.jsonl']:
            (root/name).unlink()
    return {**data,'narrative':n,'scenes':scenes}


def graph_setup(root: Path, *, merge: bool = False) -> dict:
    """An authored cause fork and editorial revision, using no personal material."""
    a = event('A', 1, 'gate', path='/physical_state/location')
    b = event('B', 2, 'reconciled', path='/emotional_state/trust')
    d = event('D', 3, 'still uncertain', path='/emotional_state/trust',
              supersedes=['B', 'C'] if merge else ['B'])
    branch = event('C', 2, 'misunderstood', path='/social_role_state/occupation')
    a['notes'] = ['The companions meet at the gate.', 'They hear the same account from a messenger.']
    b['notes'] = ['One account records a reconciliation.', 'Mara accepts an explanation and offers her hand.']
    branch['notes'] = ['Another account records a misunderstanding.', 'Ivo reads the offered hand as a demand for the key.']
    d['notes'] = ['The later revision replaces the reconciliation account.',
                  'The author records that trust remains uncertain; the earlier account is retained for inspection.']
    b['cause'] = {'type': 'event', 'reference': 'A'}
    branch['cause'] = {'type': 'event', 'reference': 'A'}
    if merge:
        d['notes'][0] = 'One revision consolidates both earlier accounts.'
        d['changes'].append({**branch['changes'][0], 'value': 'explained'})
    return setup_ledger(root, events=[a, b, branch, d], views=[view('before-revision', 2), view('after-revision', 3)])
