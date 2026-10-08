#!/usr/bin/env python3
"""Synthetic normal evolution, revision, scope and conflict inspection regressions."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import state_ledger as ledger
import temporal_state as temporal
from story_timeline_fixtures import event, process, setup


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.base = {'characters': {'C01': {'social_role_state': {'occupation': 'base'},
            'physical_state': {'strength': 0}, 'appearance': {'coat': 'blue'}, 'items': ['a','b','c']}}}

    def resolve(self, rows, at, scene=None, processes=None, **kwargs):
        return ledger.Ledger(self.base, rows, processes).resolve(timeline_id='main', story_order=at,
            story_time='label', scene_context_id=scene, **kwargs)

    def occupation(self, result):
        self.assertTrue(result['ok'], result)
        return result['snapshot']['entities']['characters']['C01']['social_role_state']['occupation']

    def test_schema_error_does_not_hide_independent_reference_diagnostics(self):
        from story_timeline_fixtures import event
        import temporal_state
        source=event('SOURCE',1)
        source['changes'][0].update(persistence='temporary-until-cleared',clear_event_id='MISSING')
        later=event('LATER',20)
        bad_revision=event('REVISION',10,supersedes=['LATER'])
        bad_revision['event_scope']='social-role-state'
        malformed={'artifact_type':'state-event','changes':None,'supersedes_event_ids':[{}]}
        problems=temporal_state.validate_temporal_inputs(events=[source,source,later,bad_revision,malformed],processes=[])
        for message in ('duplicate event_id','unknown clear_event_id','supersession must be strictly later','requires an editorial-revision'):
            self.assertTrue(any(message in row for row in problems),problems)

    def test_normal_repeated_path_changes_are_not_revisions(self):
        rows = [event('E1',1,'apprentice'),event('E2',20,'craftsperson')]
        original=copy.deepcopy(rows)
        self.assertTrue(ledger.Ledger(self.base,rows).audit()['ok'])
        self.assertEqual(self.occupation(self.resolve(rows,1)),'apprentice')
        self.assertEqual(self.occupation(self.resolve(rows,20)),'craftsperson')
        self.assertEqual(rows,original)
        self.assertEqual(self.resolve(rows,20)['event_status']['E1']['status'],'applied-in-replay')

    def test_sparse_orders_are_normal(self):
        self.assertTrue(ledger.Ledger(self.base,[event('E1',-50),event('E2',10000,'later')]).audit()['ok'])

    def test_simultaneous_disjoint_changes_are_normal(self):
        rows=[event('E1',2),event('E2',2,'red',path='/appearance/coat')]
        self.assertTrue(ledger.Ledger(self.base,rows).audit()['ok'])

    def test_simultaneous_overlapping_changes_name_events_and_paths(self):
        result=ledger.Ledger(self.base,[event('E1',2),event('E2',2,'different')]).audit()
        issue=next(r for r in result['diagnostics'] if r['code']=='TEMPORAL_CONFLICT')
        self.assertEqual(issue['event_ids'],['E1','E2'])
        self.assertIn('/characters/C01/social_role_state/occupation',issue['paths'])
        self.assertIsNone(self.resolve([event('E1',2),event('E2',2,'different')],2)['snapshot'])

    def test_same_order_local_changes_on_different_scenes_do_not_compete(self):
        rows=[event('E1',2,'A',scene='SC1'),event('E2',2,'B',scene='SC2')]
        self.assertTrue(ledger.Ledger(self.base,rows).audit()['ok'])
        self.assertEqual(self.occupation(self.resolve(rows,2,'SC1')),'A')
        self.assertEqual(self.occupation(self.resolve(rows,2,'SC2')),'B')
        self.assertEqual(self.occupation(self.resolve(rows,2)),'base')

    def test_scene_local_is_named_not_inferred_from_time(self):
        rows=[event('E1',2,'scene value',scene='SC1')]
        self.assertEqual(self.occupation(self.resolve(rows,30,'OTHER')),'base')
        self.assertEqual(self.occupation(self.resolve(rows,30,'SC1')),'scene value')
        self.assertEqual(self.resolve(rows,30,'OTHER')['event_status']['E1']['status'],'other-scene-only')

    def test_scene_local_missing_context_uses_existing_validation(self):
        row=event();row['changes'][0]['persistence']='scene-local'
        result=ledger.Ledger(self.base,[row]).audit()
        self.assertFalse(result['ok']);self.assertIn('requires scene_context_id',str(result))
        self.assertEqual(result['diagnostics'][0]['pointer'],'/events/0')

    def test_missing_changed_target_is_structural_not_narrative_inference(self):
        row=event();row['targets']=['OTHER']
        self.assertIn('targets omit changed entities',str(ledger.Ledger(self.base,[row]).audit()))
        row['targets']=['C01','OTHER'];self.assertTrue(ledger.Ledger(self.base,[row]).audit()['ok'])

    def test_supersession_is_whole_event_and_future_filtered(self):
        first=event('E1',1,'apprentice');first['changes'].append(copy.deepcopy(first['changes'][0]))
        first['changes'][1].update(path='/appearance/coat',value='green')
        revision=event('REV',30,'already qualified',supersedes=['E1'])
        before=self.resolve([first,revision],20);after=self.resolve([first,revision],30)
        self.assertEqual(self.occupation(before),'apprentice');self.assertEqual(self.occupation(after),'already qualified')
        self.assertEqual(before['snapshot']['entities']['characters']['C01']['appearance']['coat'],'green')
        self.assertEqual(after['snapshot']['entities']['characters']['C01']['appearance']['coat'],'blue')
        self.assertEqual(after['event_status']['E1']['status'],'revised-at-selected-order')

    def test_unknown_self_cycle_and_cross_timeline_are_diagnosed(self):
        cases=[ [event('R',2,supersedes=['absent'])], [event('SELF',2,supersedes=['SELF'])],
            [event('A',1,supersedes=['B']),event('B',2,supersedes=['A'])],
            [event('A',1,timeline='other'),event('R',2,supersedes=['A'])] ]
        for rows in cases:
            with self.subTest(ids=[r['event_id'] for r in rows]):
                result=ledger.Ledger(self.base,rows).audit();self.assertFalse(result['ok'])
        self.assertIn('SUPERSESSION_CYCLE',str(ledger.Ledger(self.base,cases[2]).audit()))

    def test_later_revision_cannot_hide_earlier_conflict_from_audit(self):
        rows=[event('E1',1),event('E2',1,'different'),event('R',30,'revised',supersedes=['E1'])]
        self.assertTrue(self.resolve(rows,30)['ok'])
        result=ledger.Ledger(self.base,rows).audit();self.assertFalse(result['ok'])
        self.assertTrue(any(row.get('story_order')==1 for row in result['diagnostics']))

    def test_story_and_disclosure_text_are_never_date_sorted(self):
        a=event('EARLIER',1);a.update(effective_from='tomorrow',recorded_at='2030-01-01T00:00:00Z',disclosed_at='before anything')
        b=event('LATER',20,'later');b.update(effective_from='yesterday',recorded_at='2000-01-01T00:00:00Z')
        result=ledger.Ledger(self.base,[b,a]).audit();self.assertTrue(result['ok'],result)
        self.assertEqual(self.occupation(self.resolve([b,a],20)),'later')

    def test_proposed_rejected_and_superseded_are_not_applied(self):
        for status in ('proposed','rejected','superseded'):
            row=event(status=status)
            self.assertEqual(self.occupation(self.resolve([row],20)),'base')

    def test_trace_matches_public_resolver_and_does_not_mutate_inputs(self):
        rows=[event('E1',1),event('E2',20,'later')];base=copy.deepcopy(self.base)
        answer=self.resolve(rows,20)
        direct=temporal.resolve_world(base_state=self.base,events=rows,processes=[],timeline_id='main',
            story_order=20,story_time='label',snapshot_id=answer['snapshot']['snapshot_id'],scene_context_id=None)
        self.assertEqual(direct,answer['snapshot']);self.assertEqual(base,self.base)
        self.assertEqual(answer['trace'][0]['before'],{'present':True,'value':'base'})
        self.assertEqual(answer['trace'][-1]['after'],{'present':True,'value':'later'})

    def test_process_milestones_use_same_resolver_no_interpolation(self):
        proc=process()
        answer=self.resolve([],12,processes=[proc]);self.assertTrue(answer['ok'])
        self.assertEqual(answer['snapshot']['entities']['characters']['C01']['physical_state']['strength'],0)
        self.assertEqual(len(answer['trace']),1)
        later=self.resolve([],15,processes=[proc]);self.assertEqual(later['trace'][-1]['after']['value'],10)

    def test_event_after_same_order_milestone_uses_existing_phase_precedence(self):
        row=event('CHANGE',15,50,path='/physical_state/strength')
        answer=self.resolve([row],15,processes=[process()]);self.assertTrue(answer['ok'],answer)
        self.assertEqual(answer['snapshot']['entities']['characters']['C01']['physical_state']['strength'],50)
        self.assertEqual([t['kind'] for t in answer['trace']],['process','process','event'])

    def test_linked_offset_zero_applies_once_and_keeps_both_lineages(self):
        row=event('START',10,0,path='/physical_state/strength',persistence='progressive');row['changes'][0]['process_id']='P1'
        answer=self.resolve([row],10,processes=[process()]);self.assertTrue(answer['ok'],answer)
        self.assertEqual(len(answer['trace']),1)
        self.assertEqual(answer['snapshot']['applied_process_milestones'],['P1@epoch-initial:offset-0'])

    def test_temporary_change_expires_at_declared_exclusive_order(self):
        row=event('TEMP',1,'temporary',persistence='temporary-until-cleared');row['changes'][0]['effective_until_order']=3
        self.assertEqual(self.occupation(self.resolve([row],2)),'temporary')
        self.assertEqual(self.occupation(self.resolve([row],3)),'base')

    def test_failed_precondition_does_not_assert_partial_state(self):
        row=event();row['preconditions']=[{'entity_type':'character','entity_id':'C01','path':'/missing','operator':'exists'}]
        answer=self.resolve([row],20);self.assertFalse(answer['ok']);self.assertIsNone(answer['snapshot']);self.assertEqual(answer['trace'],[])
        self.assertFalse(ledger.Ledger(self.base,[row]).audit()['ok'])

    def test_array_structure_conflict_and_world_aggregate_are_preserved(self):
        a=event('A',1,None,path='/items/0',operation='remove');a['changes'][0].pop('value')
        b=event('B',1,'replace',path='/items/1')
        self.assertFalse(ledger.Ledger(self.base,[a,b]).audit()['ok'])
        a=event('A',1,1,path='/flag',entity='arbitrary-A',kind='world')
        b=event('B',1,2,path='/flag',entity='arbitrary-B',kind='world')
        self.assertFalse(ledger.Ledger(self.base,[a,b]).audit()['ok'])

    def test_invalid_records_and_duplicate_ids_are_located(self):
        cases=[[None],[{'artifact_type':'other'}],[event(),event()]]
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertFalse(ledger.Ledger(self.base,rows).audit()['ok'])
        self.assertFalse(ledger.Ledger([],[]).audit()['ok'])

    def test_structure_is_validated_once_for_many_selected_views(self):
        rows=[event('E'+str(i),i,str(i)) for i in range(150)]
        with patch.object(temporal,'validate_artifact',wraps=temporal.validate_artifact) as validate:
            compiled=ledger.Ledger(self.base,rows)
            for at in (0,40,90,149):self.assertTrue(compiled.resolve(timeline_id='main',story_order=at,story_time='point',scene_context_id=None)['ok'])
            self.assertTrue(compiled.audit()['ok'])
            self.assertEqual(validate.call_count,len(rows))

    def test_long_revision_chain_has_no_recursive_graph_walk(self):
        rows=[event('E'+str(i),i,str(i),supersedes=['E'+str(i-1)] if i else None) for i in range(1100)]
        self.assertFalse(ledger.Ledger(self.base,rows).diagnostics)

    def test_validate_ledger_cli_does_not_write_a_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'fixture';setup(root,create_studio=False)
            before={p.relative_to(root):p.read_bytes() for p in (root/'state').iterdir()}
            cmd=[sys.executable,str(Path(__file__).with_name('state_protocol.py')),'validate-ledger','--base-state',str(root/'state/world-state-base.json'),'--events',str(root/'state/events.jsonl')]
            result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertTrue(json.loads(result.stdout)['ok'])
            self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in (root/'state').iterdir()})


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
