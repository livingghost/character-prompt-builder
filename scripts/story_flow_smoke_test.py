#!/usr/bin/env python3
"""Automatic human story projection, source boundaries and synchronization."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import story_flow as flow
import story_timeline as timeline
from state_ledger import Ledger
from story_timeline_fixtures import setup as ledger_setup, event, process, view, write_events
from story_flow_fixtures import setup, scene, context


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'studio';self.fixture=setup(self.root)
    def model(self):
        return timeline.build_model(self.root,self.root/timeline.OUTPUT)[0]
    def scenes(self,data):
        return [n for n in data['flow']['nodes'] if n['kind']=='scene']
    def write(self,name,value):
        c.atomic_write_json(self.root/name,value)

    def test_normal_sources_produce_readable_scenes_without_flow_authored_input(self):
        data=self.model()
        self.assertTrue(data['ok']);self.assertEqual(len(self.scenes(data)),3)
        self.assertEqual(self.scenes(data)[0]['title'],self.fixture['scenes'][0]['proposition'])
        self.assertEqual(data['flow']['default_order'],'presentation')
        self.assertFalse((self.root/'state/flow.json').exists())
        self.assertEqual(data['flow']['names']['C01'],'Mara')

    def test_exact_scene_context_links_events_not_similar_scene_names(self):
        data=self.model();scenes=self.scenes(data)
        self.assertTrue(all(len(s['event_keys'])==1 for s in scenes))
        value=self.fixture['scenes'][0];value['setting'].pop('scene_context')
        self.write('narrative/scenes/gate-plot.json',value)
        data=self.model();gate=next(n for n in self.scenes(data) if n['scene_id']=='gate')
        self.assertIsNone(gate['timeline_id']);self.assertEqual(gate['event_keys'],[])
        self.assertIn('E-accusation',str(data['flow']['nodes']))

    def test_no_state_inputs_still_produce_a_narrative_reading_view(self):
        for p in ['state/events.jsonl','state/world-state-base.json','state/timeline-view.json']:(self.root/p).unlink()
        self.assertTrue(timeline.configured(self.root))
        result=timeline.refresh(self.root);self.assertTrue(result['ok'],result)
        data=self.model();self.assertEqual(data['events'],[]);self.assertEqual(data['views'],[])
        self.assertEqual(len(self.scenes(data)),3);self.assertIsNone(data['source_links']['base'])

    def test_one_missing_half_of_existing_state_is_not_silently_replaced(self):
        (self.root/'state/world-state-base.json').unlink()
        report=timeline.refresh(self.root)
        self.assertFalse(report['ok']);self.assertIn('missing',report['message'])

    def test_ledger_without_scenes_uses_verbatim_notes_and_changes(self):
        for p in (self.root/'narrative').rglob('*.json'):p.unlink()
        data=self.model()
        nodes=data['flow']['nodes']
        self.assertEqual(len(nodes),3);self.assertEqual(nodes[0]['title'],self.fixture['events'][0]['notes'][0])
        self.assertEqual(data['flow']['default_order'],'story')

    def test_missing_account_is_not_written_by_the_projector(self):
        rows=self.fixture['events'];rows[0]['notes']=[];rows[0]['cause']={'type':'author-decision','reference':'Decision A'}
        write_events(self.root,rows);data=self.model()
        n=next(n for n in data['flow']['nodes'] if n.get('event_id')=='E-accusation')
        self.assertEqual(n['title'],'Decision A')
        self.assertIn('recorded text',n['title_basis'])

    def test_presentation_order_does_not_invent_or_sort_story_time(self):
        sc=self.fixture['scenes'][2];self.write('state/contexts/key.json',context('SC-key',-20,-10))
        data=self.model()
        self.assertEqual([t['chapter_id'] for t in data['flow']['presentation_tracks'] if t['kind']=='presentation'],['ch1','ch2','ch3'])
        first=data['flow']['story_tracks'][0]['groups'][0]
        self.assertEqual(first['position'],-20)

    def test_parallel_equal_positions_remain_peers_and_timelines_are_separate(self):
        rows=[event('A',1,'x',path='/appearance/a'),event('B',1,'y',path='/appearance/b'),
              event('OTHER',1,'z',timeline='other')]
        write_events(self.root,rows);data=self.model()
        track=next(t for t in data['flow']['story_tracks'] if t.get('timeline_id')=='main')
        group=next(g for g in track['groups'] if g['position']==1)
        self.assertEqual(len(group['keys']),2)
        self.assertFalse(any(r['kind']=='cause' for r in data['flow']['relations']))

    def test_whole_event_revision_and_real_changes_use_original_resolver(self):
        rows=[event('OLD',1,'red',path='/appearance/coat'),event('REV',10,'green',path='/appearance/coat',supersedes=['OLD'])]
        rows[0]['changes'].append({**rows[0]['changes'][0],'path':'/physical/location','value':'town'})
        base=self.fixture['base'];base['characters']['C01']['physical']={'location':'home'};self.write('state/world-state-base.json',base)
        write_events(self.root,rows);data=self.model()
        after=data['views'][1]['snapshot']['entities']['characters']['C01']
        self.assertEqual(after['appearance']['coat'],'green');self.assertEqual(after['physical']['location'],'home')
        self.assertEqual([r['kind'] for r in data['flow']['relations']],['revision'])

    def test_cause_prose_matching_an_id_does_not_become_an_edge(self):
        rows=[event('A',1),event('B',2,'second')]
        rows[1]['cause']={'type':'author-decision','reference':'A'};write_events(self.root,rows)
        self.assertEqual(self.model()['flow']['relations'],[])

    def test_explicit_cause_link_uses_one_declared_id(self):
        rows=[event('A',1),event('B',2,'second')];rows[1]['cause']={'type':'event','reference':'A'}
        write_events(self.root,rows);data=self.model()
        self.assertEqual([r['kind'] for r in data['flow']['relations']],['cause'])

    def test_unresolvable_cause_does_not_invent_a_parent(self):
        rows=[event('A',1)];rows[0]['cause']={'type':'event','reference':'not-recorded'}
        write_events(self.root,rows);data=self.model()
        self.assertEqual(data['flow']['relations'],[]);self.assertTrue(data['ok'])
        self.assertIn('FLOW_CAUSE_UNRESOLVED',str(data['flow']['diagnostics']))

    def test_process_is_readable_without_becoming_a_new_event(self):
        self.write('state/processes.json',[process()]);(self.root/'state/timeline-view.json').unlink()
        data=self.model();self.assertEqual(len(data['events']),3)
        nodes=[n for n in data['flow']['nodes'] if n['kind']=='process']
        self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['process_record']['milestones'][1]['state'],10)

    def test_structurally_valid_motivation_gap_is_not_a_machine_verdict(self):
        data=self.model()
        self.assertTrue(data['ok'])
        self.assertIn('no reconciliation',str(data['flow']['nodes']))
        self.assertNotIn('STORY_CONTRADICTION',str(data['diagnostics']))
        self.assertEqual(data['flow']['narrative']['questions'][0]['status'],'open')

    def test_scene_rewrites_and_additions_and_removals_change_projection(self):
        first=self.model()['projection_id']
        value=self.fixture['scenes'][1];value['proposition']='A different authored route.'
        self.write('narrative/scenes/routes-plot.json',value)
        second=self.model()['projection_id'];self.assertNotEqual(first,second)
        (self.root/'narrative/scenes/routes-plot.json').unlink()
        third=self.model()['projection_id'];self.assertNotEqual(second,third)
        self.assertEqual(len(self.scenes(self.model())),2)

    def test_collection_is_rechecked_before_atomic_publication(self):
        model,inputs=timeline.build_model(self.root,self.root/timeline.OUTPUT)
        self.write('narrative/scenes/new-plot.json',self.fixture['scenes'][0])
        with self.assertRaisesRegex(ValueError,'collection changed'):inputs.recheck()

    def test_duplicate_scene_ids_do_not_silently_select_latest_file(self):
        self.write('narrative/scenes/alternate.json',self.fixture['scenes'][0]);data=self.model()
        duplicates=[n for n in self.scenes(data) if n['scene_id']=='gate']
        self.assertEqual(len(duplicates),2)
        self.assertTrue(all(not n['event_keys'] for n in duplicates))
        self.assertIn('FLOW_SCENE_ID_AMBIGUOUS',str(data['flow']['diagnostics']))

    def test_partial_scene_file_has_a_visible_diagnostic(self):
        (self.root/'narrative/scenes/routes-plot.json').write_text('{"artifact_type":',encoding='utf-8')
        data=self.model();self.assertTrue(data['ok'])
        self.assertIn('could not be read',str(data['flow']['diagnostics']))
        self.assertEqual(len(self.scenes(data)),3)

    def test_other_json_beside_scene_is_not_promoted_to_story_scene(self):
        self.write('narrative/scenes/material.json',{'artifact_type':'some-material','note':'not a scene'})
        self.assertEqual(len(self.scenes(self.model())),3)

    def test_unapproved_sources_remain_readable_and_are_not_approved(self):
        data=self.model()
        self.assertTrue(all(n['report']['ok'] and not n['report']['approved'] for n in self.scenes(data)))
        self.assertFalse(data['flow']['narrative_report']['approved'])

    def test_narrative_revision_mismatch_is_reported_without_fabricated_repair(self):
        n=self.fixture['narrative'];n['questions'][0]['statement']='Was the accusation reliable?'
        self.write('narrative/narrative.json',n);data=self.model()
        self.assertIn('different narrative revision',str(data['flow']['diagnostics']))
        self.assertEqual(self.scenes(data)[0]['scene_record']['narrative_sha256'],self.fixture['scenes'][0]['narrative_sha256'])

    def test_scene_context_hash_mismatch_prevents_join(self):
        path='state/contexts/gate.json';x=c.load(self.root/path);x['story_order_start']=3;self.write(path,x)
        data=self.model();node=next(n for n in self.scenes(data) if n['scene_id']=='gate')
        self.assertIsNone(node['scene_context_id']);self.assertEqual(node['event_keys'],[])

    def test_unsafe_scene_context_is_not_followed(self):
        sc=self.fixture['scenes'][0];sc['setting']['scene_context']='../../outside.json'
        self.write('narrative/scenes/gate-plot.json',sc);data=self.model()
        self.assertIn('invalid',str(data['flow']['diagnostics']).lower())
        self.assertFalse(any('../' in dep['path'] for dep in data['inputs']))

    def test_symlink_scene_does_not_read_target_bytes(self):
        target=self.root.parent/'outside.json';target.write_text('{"secret":"not for Flow"}',encoding='utf-8')
        try:(self.root/'narrative/scenes/link.json').symlink_to(target)
        except OSError:self.skipTest('symlinks unavailable')
        data=self.model();self.assertNotIn('not for Flow',str(data))
        self.assertIn('FLOW_SCENE_REVIEW',str(data['flow']['diagnostics']))

    def test_character_names_arbitrary_record_text_is_preserved(self):
        n=self.fixture['narrative'];n['characters'][0]['name']='検討者'
        self.write('narrative/narrative.json',n)
        self.assertEqual(self.model()['flow']['names']['C01'],'検討者')

    def test_many_records_build_flow_without_per_node_resolver_calls(self):
        rows=[event('E'+str(i),i,str(i)) for i in range(500)]
        write_events(self.root,rows)
        original=Ledger.resolve
        with patch.object(Ledger,'resolve',autospec=True,side_effect=original) as resolve:
            data=self.model()
        self.assertEqual(len([n for n in data['flow']['nodes'] if n['kind']=='event']),500)
        self.assertLess(resolve.call_count,15)
        self.assertEqual(len(data['flow']['state_paths']),1)

    def test_projection_keeps_author_sources_byte_identical(self):
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        timeline.refresh(self.root);timeline.refresh(self.root)
        self.assertTrue(all((self.root/name).read_bytes()==raw for name,raw in before.items()))

    def test_sync_regenerates_story_after_normal_source_edits(self):
        import studio_activity
        first=studio_activity.refresh(self.root)['story_timeline'];self.assertTrue(first['ok'])
        sc=self.fixture['scenes'][0];sc['proposition']='An updated author account.'
        self.write('narrative/scenes/gate-plot.json',sc)
        second=studio_activity.refresh(self.root)['story_timeline']
        self.assertNotEqual(first['projection_id'],second['projection_id'])
        self.assertIn('An updated author account.',(self.root/timeline.OUTPUT).read_text(encoding='utf-8'))

    def test_default_config_no_manual_flow_mapping_or_extra_summary_file(self):
        (self.root/'state/timeline-view.json').unlink()
        result=timeline.refresh(self.root);self.assertTrue(result['ok'])
        self.assertEqual(len(self.scenes(self.model())),3)
        self.assertFalse((self.root/'state/timeline-view.json').exists())

    def test_malformed_narrative_is_reading_notice_not_fake_approval(self):
        (self.root/'narrative/narrative.json').write_text('{',encoding='utf-8')
        data=self.model();self.assertTrue(data['ok'])
        self.assertIsNone(data['flow']['narrative_report']);self.assertIn('FLOW_NARRATIVE_UNAVAILABLE',str(data['flow']['diagnostics']))


    def test_empty_scene_scaffold_does_not_create_a_story_ledger(self):
        empty=self.root.parent/'empty';(empty/'narrative/scenes').mkdir(parents=True)
        self.assertFalse(timeline.configured(empty))

    def test_known_state_writer_updates_context_link_without_flow_file(self):
        timeline.refresh(self.root)
        from state_protocol import write_json
        write_json(self.root/'state/contexts/key.json',context('SC-key',22,29))
        page=(self.root/timeline.OUTPUT).read_text(encoding='utf-8')
        import re
        data=json.loads(re.search(r'<script id="timeline-data" type="application/json">(.*?)</script>',page,re.S)[1])
        node=next(n for n in data['flow']['nodes'] if n.get('scene_id')=='key')
        self.assertEqual(node['start_order'],22)
        self.assertEqual(node['event_keys'],[])

    def test_missing_declared_chapter_is_visible_as_source_gap_not_invented_scene(self):
        (self.root/'narrative/scenes/key-plot.json').unlink();data=self.model()
        missing=[n for n in data['flow']['nodes'] if n['kind']=='chapter']
        self.assertEqual(len(missing),1);self.assertEqual(missing[0]['chapter_id'],'ch3')
        self.assertIsNone(missing[0]['timeline_id'])

    def test_each_scene_is_read_once_by_the_projection_owner(self):
        original=timeline.Inputs.read
        with patch.object(timeline.Inputs,'read',autospec=True,side_effect=original) as read:
            self.model()
        counts={}
        for call in read.call_args_list:
            name=call.args[1]
            if name.startswith('narrative/scenes/'):counts[name]=counts.get(name,0)+1
        self.assertEqual(list(counts.values()),[1,1,1])


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
