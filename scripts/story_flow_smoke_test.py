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

    def test_contextual_depiction_keeps_visibility_and_existing_event_links(self):
        value=self.fixture['scenes'][2]
        contextual={'id':'c1','beat':'The accusation remains unresolved for Mara.','visibility':'context'}
        value['beats'].append(contextual)
        value['realization']['units'][0]['composition']=[{
            'statement':'Stay close to the offered key and the space between their hands.',
            'from':['b1','c1']}]
        self.write('narrative/scenes/key-plot.json',value)
        ledger_before=(self.root/'state/events.jsonl').read_bytes()
        data=self.model();key=next(n for n in self.scenes(data) if n['scene_id']=='key')
        self.assertTrue(key['report']['ok'],key['report']['errors'])
        self.assertEqual(key['scene_record']['beats'][-1],contextual)
        self.assertEqual(key['scene_record']['state_changes'],value['state_changes'])
        expected=next(n['key'] for n in data['flow']['nodes'] if n.get('event_id')=='E-key')
        self.assertEqual(key['event_keys'],[expected])
        self.assertEqual({n['event_id'] for n in data['flow']['nodes'] if n['kind']=='event'},
                         {e['event_id'] for e in self.fixture['events']})
        self.assertEqual((self.root/'state/events.jsonl').read_bytes(),ledger_before)

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

    def test_present_null_config_does_not_elect_absent_configuration_defaults_for_narrative_only(self):
        for name in ('state/world-state-base.json','state/events.jsonl'):(self.root/name).unlink()
        c.atomic_write_json(self.root/timeline.CONFIG,None)
        report=timeline.refresh(self.root)
        self.assertFalse(report['ok']);self.assertIn('required story input is missing',report['message'])

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
        empty=self.root.parent/'empty'
        for prefix in ('','story/'):(empty/(prefix+'narrative/scenes')).mkdir(parents=True)
        self.assertFalse(timeline.configured(empty))
        for prefix in ('','story/'):
            c.atomic_write_json(empty/(prefix+'narrative/scenes/material.json'),{'artifact_type':'some-material'})
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


class SeriesLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name)

    def fixture(self,name,prefix='',**options):
        root=self.directory/name
        return root,setup(root,series_prefix=prefix,**options)

    def model(self,root):return timeline.build_model(root,root/timeline.OUTPUT)[0]

    def scenes(self,data):return [row for row in data['flow']['nodes'] if row['kind']=='scene']

    def test_conventional_layouts_keep_content_and_declared_path_bases(self):
        for prefix in ('','story/'):
            with self.subTest(prefix=prefix):
                root,fixture=self.fixture('nested' if prefix else 'root',prefix)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()
                        and 'work' not in p.relative_to(root).parts}
                output=root/'views/deep/story.html'
                result=timeline.refresh(root,out=Path('views/deep/story.html'))
                self.assertTrue(result['ok'],result)
                self.assertFalse(timeline.refresh(root,out=Path('views/deep/story.html'))['written'])
                data,_=timeline.build_model(root,output)
                self.assertEqual(data['flow']['narrative_source']['path'],prefix+'narrative/narrative.json')
                self.assertEqual(data['flow']['narrative_source']['href'],'../../'+prefix+'narrative/narrative.json')
                by_id={row['scene_id']:row for row in self.scenes(data)}
                for source in fixture['scenes']:
                    node=by_id[source['scene_id']]
                    self.assertEqual(node['scene_record'],source)
                    self.assertEqual(node['source']['path'],prefix+f"narrative/scenes/{source['scene_id']}-plot.json")
                    self.assertEqual(node['source']['href'],'../../'+node['source']['path'])
                    self.assertEqual(node['context_source']['path'],prefix+source['setting']['scene_context'])
                    self.assertEqual(node['context_source']['href'],'../../'+node['context_source']['path'])
                    self.assertEqual(len(node['event_keys']),1)
                    self.assertFalse(node['report']['approved'])
                self.assertEqual(data['source_links']['base'],'../../state/world-state-base.json')
                self.assertEqual(data['source_paths']['events'],'state/events.jsonl')
                self.assertEqual(data['events'][0]['references'][0]['href'],'../../decision.txt')
                self.assertEqual(data['flow']['diagnostics'],[])
                self.assertTrue(all(path.read_bytes()==raw for path,raw in before.items()))

    def test_each_layout_reads_narrative_and_scenes_before_state_exists(self):
        import studio_activity
        import validate_studio
        for prefix in ('','story/'):
            for sources in ('both','narrative','scenes'):
                with self.subTest(prefix=prefix,sources=sources):
                    name=('nested-' if prefix else 'root-')+sources
                    root,_=self.fixture(name,prefix,include_state=False,include_scenes=sources!='narrative')
                    if sources=='scenes':(root/(prefix+'narrative/narrative.json')).unlink()
                    self.assertTrue(timeline.configured(root))
                    result=studio_activity.refresh(root)
                    self.assertTrue(result['story_timeline']['ok'],result)
                    self.assertEqual(validate_studio.validate(root),[])
                    data=self.model(root)
                    self.assertEqual(data['events'],[]);self.assertEqual(data['views'],[])
                    self.assertEqual(len(self.scenes(data)),0 if sources=='narrative' else 3)
                    for path in ('state/world-state-base.json','state/events.jsonl','state/timeline-view.json'):
                        self.assertFalse((root/path).exists())

    def test_empty_scaffold_and_other_material_do_not_compete_with_authored_series(self):
        for prefix,other in (('','story/'),('story/','')):
            with self.subTest(prefix=prefix):
                root,_=self.fixture('nested' if prefix else 'root',prefix,include_state=False)
                path=other+'narrative/scenes/material.json'
                c.atomic_write_json(root/path,{'artifact_type':'some-material'})
                data=self.model(root)
                self.assertEqual(len(self.scenes(data)),3)
                self.assertEqual(data['flow']['narrative_source']['path'],prefix+'narrative/narrative.json')
                facts={row['path']:row for row in data['inputs']}
                self.assertEqual(facts[other+'narrative/narrative.json']['status'],'missing')
                self.assertEqual(facts[path]['status'],'present')
                self.assertEqual({row['path'] for row in data['source_collections']},
                                 {'narrative/scenes','story/narrative/scenes'})

    def test_unreadable_narrative_only_retains_its_failure_in_the_reading_view(self):
        from story_timeline_smoke_test import data_from_html
        for prefix in ('','story/'):
            for failure in ('directory','permission'):
                with self.subTest(prefix=prefix,failure=failure):
                    root,_=self.fixture(('nested-' if prefix else 'root-')+failure,prefix,
                                        include_state=False,include_scenes=False)
                    relative=prefix+'narrative/narrative.json';path=root/relative
                    original=path.read_bytes()
                    if failure=='directory':path.unlink();path.mkdir()
                    read=c.read
                    def source_read(source,**kwargs):
                        if failure=='permission' and Path(source).resolve()==path.resolve():
                            raise PermissionError('synthetic narrative access denied')
                        return read(source,**kwargs)
                    with patch.object(c,'read',side_effect=source_read):
                        self.assertTrue(timeline.configured(root))
                        result=timeline.refresh(root)
                    self.assertTrue(result['ok'],result)
                    data=data_from_html(root/timeline.OUTPUT)
                    notice=next(row for row in data['flow']['diagnostics']
                                if row['code']=='FLOW_NARRATIVE_UNAVAILABLE')
                    facts={row['path']:row for row in data['inputs']}
                    fact=facts[relative]
                    self.assertEqual(fact['status'],'failed');self.assertIsNone(fact['sha256'])
                    self.assertNotIn('bytes',fact)
                    self.assertEqual(notice['source_path'],relative)
                    self.assertEqual(notice['message'],fact['failure']['message'])
                    self.assertEqual(data['flow']['narrative_source'],
                                     {'path':relative,'sha256':None,'href':None})
                    self.assertIsNone(data['flow']['narrative_report'])
                    self.assertEqual(data['events'],[]);self.assertEqual(data['views'],[])
                    self.assertEqual(self.scenes(data),[])
                    for name in ('state/world-state-base.json','state/events.jsonl','state/timeline-view.json'):
                        self.assertFalse((root/name).exists())
                    if failure=='directory':self.assertTrue(path.is_dir())
                    else:self.assertEqual(path.read_bytes(),original)

    def test_unreadable_narrative_preserves_the_required_state_pair(self):
        for prefix in ('','story/'):
            for existing,missing in (('state/world-state-base.json','state/events.jsonl'),
                                     ('state/events.jsonl','state/world-state-base.json')):
                with self.subTest(prefix=prefix,existing=existing):
                    root,fixture=self.fixture(('nested-' if prefix else 'root-')+Path(existing).stem,prefix,
                                              include_state=False,include_scenes=False)
                    path=root/(prefix+'narrative/narrative.json');path.unlink();path.mkdir()
                    if existing.endswith('.json'):c.atomic_write_json(root/existing,fixture['base'])
                    else:(root/existing).write_text('',encoding='utf-8')
                    before=(root/existing).read_bytes()
                    result=timeline.refresh(root)
                    self.assertFalse(result['ok'],result)
                    self.assertEqual(result['message'],'required story input is missing: '+missing)
                    self.assertEqual((root/existing).read_bytes(),before)
                    self.assertFalse((root/missing).exists())

    def test_collection_changes_in_either_location_invalidate_the_snapshot(self):
        for prefix in ('','story/'):
            for change in ('add','remove','rename'):
                with self.subTest(prefix=prefix,change=change):
                    root,_=self.fixture(('nested-' if prefix else 'root-')+change)
                    path=root/(prefix+'narrative/scenes/material.json')
                    c.atomic_write_json(path,{'artifact_type':'some-material'})
                    _,inputs=timeline.build_model(root,root/timeline.OUTPUT)
                    if change=='add':c.atomic_write_json(path.with_name('added.json'),{'artifact_type':'some-material'})
                    elif change=='remove':path.unlink()
                    else:path.rename(path.with_name('renamed.json'))
                    with self.assertRaisesRegex(ValueError,'collection changed') as caught:inputs.recheck()
                    self.assertIn(prefix+'narrative/scenes',str(caught.exception))

    def test_two_authored_locations_fail_even_when_one_draft_is_invalid(self):
        for kind in ('narrative','null','empty-object','malformed','scene-only'):
            with self.subTest(kind=kind):
                root,fixture=self.fixture(kind)
                if kind=='scene-only':
                    c.atomic_write_json(root/'story/narrative/scenes/gate.json',fixture['scenes'][0])
                else:
                    path=root/'story/narrative/narrative.json'
                    c.atomic_write_json(path,{'narrative':fixture['narrative'],'null':None,
                                              'empty-object':{},'malformed':{}}[kind])
                    if kind=='malformed':path.write_text('{',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'multiple narrative series') as caught:self.model(root)
                self.assertIn('narrative/, story/narrative/',str(caught.exception))

    def test_present_invalid_narrative_keeps_source_fact_and_reading_notice(self):
        cases={'null':None,'empty-object':{},'array':[],'number':0,
               'text':'unfinished draft','malformed':None}
        for prefix in ('','story/'):
            for label,value in cases.items():
                with self.subTest(prefix=prefix,label=label):
                    root,_=self.fixture(('nested-' if prefix else 'root-')+label,prefix,
                                        include_state=False,include_scenes=False)
                    path=prefix+'narrative/narrative.json';c.atomic_write_json(root/path,value)
                    if label=='malformed':(root/path).write_text('{',encoding='utf-8')
                    before=(root/path).read_bytes();data=self.model(root)
                    report=data['flow']['narrative_report']
                    if label=='malformed':self.assertIsNone(report)
                    else:
                        self.assertFalse(report['ok']);self.assertFalse(report['approved'])
                    source=data['flow']['narrative_source']
                    self.assertEqual(source,{'path':path,'href':path,'sha256':c.digest(before)})
                    code='FLOW_NARRATIVE_UNAVAILABLE' if label=='malformed' else 'FLOW_NARRATIVE_INVALID'
                    self.assertTrue(any(row['code']==code and row['source_path']==path
                                        for row in data['flow']['diagnostics']))
                    self.assertEqual(data['events'],[]);self.assertEqual(data['views'],[])
                    self.assertEqual((root/path).read_bytes(),before)

    def test_nested_context_uses_declared_series_without_other_root_fallback(self):
        root,fixture=self.fixture('nested','story/')
        pointer=fixture['scenes'][0]['setting']['scene_context']
        c.atomic_write_json(root/pointer,context('SC-other',100,109))
        gate=next(row for row in self.scenes(self.model(root)) if row['scene_id']=='gate')
        self.assertEqual(gate['scene_context_id'],'SC-gate')
        self.assertEqual(gate['scene_record']['setting']['scene_context'],pointer)
        (root/'story'/pointer).unlink()
        data=self.model(root);gate=next(row for row in self.scenes(data) if row['scene_id']=='gate')
        self.assertIsNone(gate['context_source']);self.assertEqual(gate['event_keys'],[])
        self.assertIn('story/'+pointer,str(data['flow']['diagnostics']))
        self.assertNotIn(pointer,{row['path'] for row in data['inputs']})

    def test_nested_writes_refresh_their_sources_and_report_actual_notice_paths(self):
        from state_protocol import write_json
        from story_timeline_smoke_test import data_from_html
        root,fixture=self.fixture('nested','story/')
        timeline.notify_state_write(root/'story/narrative/narrative.json')
        first=data_from_html(root/timeline.OUTPUT)
        scene_path=root/'story/narrative/scenes/gate-plot.json'
        value=fixture['scenes'][0];value['proposition']='A revised author account.'
        c.atomic_write_json(scene_path,value);timeline.notify_state_write(scene_path)
        second=data_from_html(root/timeline.OUTPUT)
        self.assertNotEqual(first['projection_id'],second['projection_id'])
        write_json(root/'story/state/contexts/gate.json',context('SC-gate',2,9))
        data=data_from_html(root/timeline.OUTPUT)
        gate=next(row for row in self.scenes(data) if row['scene_id']=='gate')
        self.assertEqual(gate['start_order'],2);self.assertEqual(gate['event_keys'],[])
        scene_path.write_text('{',encoding='utf-8');timeline.notify_state_write(scene_path)
        data=data_from_html(root/timeline.OUTPUT)
        notice=next(row for row in data['flow']['diagnostics'] if row['code']=='FLOW_SCENE_REVIEW')
        self.assertEqual(notice['source_path'],'story/narrative/scenes/gate-plot.json')

    def test_projection_reuses_discovered_scenes_and_shared_context_bytes(self):
        for prefix in ('','story/'):
            with self.subTest(prefix=prefix):
                root,fixture=self.fixture('nested' if prefix else 'root',prefix)
                value=fixture['scenes'][1]
                value['setting']['scene_context']=fixture['scenes'][0]['setting']['scene_context']
                c.atomic_write_json(root/(prefix+'narrative/scenes/routes-plot.json'),value)
                original=timeline.Inputs.read
                with patch.object(timeline.Inputs,'read',autospec=True,side_effect=original) as read, \
                     patch.object(c,'read',wraps=c.read) as disk_read:
                    self.model(root)
                counts={}
                for call in read.call_args_list:
                    name=call.args[1]
                    if '/scenes/' in name:counts[name]=counts.get(name,0)+1
                self.assertEqual(list(counts.values()),[1,1,1])
                target=(root/(prefix+value['setting']['scene_context'])).resolve()
                self.assertEqual(sum(Path(call.args[0])==target for call in disk_read.call_args_list),1)

    def test_unsafe_alternative_boundaries_cannot_select_a_readable_series(self):
        outside=self.directory/'outside';outside.mkdir()
        sentinel=outside/'source.json';sentinel.write_text('{"sentinel":"outside source"}',encoding='utf-8')
        for index,location in enumerate(('story','story/narrative','story/narrative/narrative.json',
                                         'story/narrative/scenes')):
            with self.subTest(location=location):
                root,_=self.fixture('boundary-'+str(index))
                path=root/location;path.parent.mkdir(parents=True,exist_ok=True)
                target=sentinel if path.suffix=='.json' else outside
                try:path.symlink_to(target,target_is_directory=target.is_dir())
                except OSError:self.skipTest('symlinks unavailable')
                with patch.object(c,'read',wraps=c.read) as read:
                    self.assertTrue(timeline.configured(root))
                    with self.assertRaisesRegex(ValueError,'symbolic link'):self.model(root)
                self.assertFalse(any(Path(call.args[0]).resolve().is_relative_to(outside)
                                     for call in read.call_args_list))

    def test_unreadable_alternative_collection_is_not_an_empty_scaffold(self):
        root,_=self.fixture('collection')
        directory=root/'story/narrative/scenes';directory.mkdir(parents=True)
        original=timeline.os.walk
        def denied(path,*args,**kwargs):
            if Path(path).resolve()==directory.resolve():
                if kwargs.get('onerror'):
                    kwargs['onerror'](PermissionError('synthetic directory enumeration denied'))
                return iter(())
            return original(path,*args,**kwargs)
        with patch.object(timeline.os,'walk',side_effect=denied):
            with self.assertRaisesRegex(ValueError,'story/narrative/scenes') as caught:self.model(root)
        self.assertIn('synthetic directory enumeration denied',str(caught.exception))

    def test_nested_child_and_context_symlinks_remain_source_notices_without_target_reads(self):
        root,_=self.fixture('nested','story/')
        outside=self.directory/'outside';outside.mkdir()
        sentinel=outside/'source.json';sentinel.write_text('{"sentinel":"outside source"}',encoding='utf-8')
        paths=[root/'story/narrative/scenes/link.json',root/'story/narrative/scenes/linked',
               root/'story/state/contexts/gate.json']
        paths[-1].unlink()
        try:
            for path in paths:
                target=outside if path.name=='linked' else sentinel
                path.symlink_to(target,target_is_directory=target.is_dir())
        except OSError:self.skipTest('symlinks unavailable')
        with patch.object(c,'read',wraps=c.read) as read:data=self.model(root)
        self.assertNotIn('outside source',str(data))
        self.assertFalse(any(Path(call.args[0]).resolve().is_relative_to(outside) for call in read.call_args_list))
        gate=next(row for row in self.scenes(data) if row['scene_id']=='gate')
        self.assertEqual(gate['event_keys'],[]);self.assertIsNone(gate['context_source'])
        notices={row['source_path'] for row in data['flow']['diagnostics']}
        self.assertTrue({'story/narrative/scenes/link.json','story/narrative/scenes/linked',
                         'story/narrative/scenes/gate-plot.json'}.issubset(notices))
        failed={row['path']:row for row in data['inputs'] if row['status']=='failed'}
        self.assertEqual(set(failed),{path.relative_to(root).as_posix() for path in paths})
        self.assertTrue(all(row['sha256'] is None and 'bytes' not in row for row in failed.values()))


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
