#!/usr/bin/env python3
"""Read-only story projection, safe publication, sync and explicit artwork tests."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import story_timeline as story
import studio
import studio_activity as activity
from story_timeline_fixtures import setup, event, process, view, write_events


def data_from_html(path: Path) -> dict:
    text=path.read_text(encoding='utf-8')
    match=re.search(r'<script id="timeline-data" type="application/json">(.*?)</script>',text,re.S)
    if not match:raise ValueError('no complete embedded projection')
    return json.loads(match[1])


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'studio'
        self.fixture=setup(self.root)
        self.output=self.root/story.OUTPUT

    def model(self):
        return story.build_model(self.root,self.output)[0]

    def config(self):return c.load(self.root/story.CONFIG)
    def save_config(self,v):c.atomic_write_json(self.root/story.CONFIG,v)

    def canonical_bytes(self):
        return {p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()
                and ('state' in p.relative_to(self.root).parts or p.name=='decision.txt')
                and p.suffix in {'.json','.jsonl','.txt'} and not p.name.endswith('.status.json')}

    def test_default_projection_and_exact_selected_values(self):
        result=story.refresh(self.root);self.assertTrue(result['ok'],result)
        data=data_from_html(self.output)
        self.assertEqual([row['event']['event_id'] for row in data['events']],['E1','E2'])
        self.assertEqual([row['snapshot']['entities']['characters']['C01']['social_role_state']['occupation'] for row in data['views']],['apprentice','craftsperson'])
        self.assertEqual(data['views'][1]['trace'][-1]['source_id'],'E2')

    def test_projection_never_writes_world_events_evidence_or_config(self):
        before=self.canonical_bytes();story.refresh(self.root);story.refresh(self.root)
        self.assertEqual(self.canonical_bytes(),before)

    def test_repeated_sync_is_idempotent_and_does_not_duplicate_activity(self):
        first=activity.refresh(self.root);data=self.output.read_bytes()
        before=activity.read_events(self.root)[0]
        again=activity.refresh(self.root)
        self.assertTrue(first['ok']);self.assertFalse(again['story_timeline']['written'])
        self.assertEqual(data,self.output.read_bytes());self.assertEqual(before,activity.read_events(self.root)[0])
        self.assertEqual(sum(row['event']=='story-timeline-refreshed' for row in before),1)
        self.assertNotIn('story-timeline-refreshed',(self.root/'state/events.jsonl').read_text(encoding='utf-8'))

    def test_external_base_change_requires_sync_and_updates_resolved_view(self):
        story.refresh(self.root);before=self.output.read_bytes()
        base=c.load(self.root/'state/world-state-base.json');base['characters']['C01']['appearance']={'coat':'blue'}
        c.atomic_write_json(self.root/'state/world-state-base.json',base)
        self.assertEqual(self.output.read_bytes(),before)
        self.assertTrue(activity.refresh(self.root)['ok']);after=data_from_html(self.output)
        self.assertEqual(after['views'][0]['snapshot']['entities']['characters']['C01']['appearance']['coat'],'blue')

    def test_recorded_time_edits_do_not_reorder_the_story(self):
        rows=self.fixture['events'];rows[0]['recorded_at']='2040-01-01T00:00:00Z';rows[1]['recorded_at']='2000-01-01T00:00:00Z'
        write_events(self.root,list(reversed(rows)));data=self.model()
        self.assertEqual([r['event']['event_id'] for r in data['events']],['E1','E2'])
        self.assertEqual(data['events'][0]['event']['recorded_at'],'2040-01-01T00:00:00Z')

    def test_scene_local_has_no_inferred_duration_and_explicit_view_scope(self):
        rows=[event('LOCAL',2,'visitor',scene='SC1')];write_events(self.root,rows)
        conf=self.config();conf['views']=[view('matching',3,scene='SC1'),view('other',3,scene='SC2'),view('shared',3)];self.save_config(conf)
        data=self.model();self.assertTrue(data['ok'])
        vals=[x['snapshot']['entities']['characters']['C01']['social_role_state']['occupation'] for x in data['views']]
        self.assertEqual(vals,['visitor','unassigned','unassigned'])
        self.assertNotIn('duration',data['events'][0]);self.assertIn('no inferred scene duration',data['semantics']['scene_local'])

    def test_invalid_event_is_visible_but_has_no_resolved_state(self):
        row=event();row['targets']=['wrong'];write_events(self.root,[row])
        result=story.refresh(self.root);self.assertTrue(result['ok']);self.assertFalse(result['ledger_ok'])
        data=data_from_html(self.output);self.assertEqual(len(data['events']),1)
        self.assertTrue(all(v['snapshot'] is None for v in data['views']))
        self.assertTrue(any(d['event_ids']==['E1'] for d in data['diagnostics'] if d.get('event_ids')))

    def test_conflict_shows_no_state_for_the_conflicting_view(self):
        write_events(self.root,[event('A',1),event('B',1,'opposed')]);data=self.model()
        self.assertFalse(data['ok']);self.assertIsNone(data['views'][0]['snapshot'])
        self.assertIn('TEMPORAL_CONFLICT',str(data['diagnostics']))

    def test_default_latest_views_are_labelled_order_not_inferred_story_time(self):
        conf=self.config();conf['views']=[];self.save_config(conf)
        data=self.model();self.assertEqual(data['views'][0]['view']['story_time'],'order:20')
        self.assertIn('not an authored story_time',data['views'][0]['view']['time_basis'])
        self.assertIsNone(data['views'][0]['view']['scene_context_id'])

    def test_empty_ledger_and_empty_world_are_not_populated_from_imagination(self):
        write_events(self.root,[]);conf=self.config();conf['views']=[];self.save_config(conf)
        c.atomic_write_json(self.root/'state/world-state-base.json',{})
        data=self.model();self.assertTrue(data['ok']);self.assertEqual(data['events'],[]);self.assertEqual(data['views'],[])

    def test_config_optional_default_paths_and_process_file(self):
        (self.root/story.CONFIG).unlink();c.atomic_write_json(self.root/'state/processes.json',[process()])
        data=self.model();self.assertTrue(data['ok'],data['diagnostics']);self.assertEqual(len(data['processes']),1)
        self.assertEqual(data['input_config']['processes'],'state/processes.json')

    def test_one_state_process_object_is_supported(self):
        conf=self.config();conf['processes']='state/processes.json';self.save_config(conf)
        c.atomic_write_json(self.root/'state/processes.json',process())
        self.assertEqual(len(self.model()['processes']),1)

    def test_missing_evidence_is_link_warning_not_an_invented_state_failure(self):
        (self.root/'decision.txt').unlink();data=self.model()
        self.assertTrue(data['ok']);self.assertTrue(data['views'][0]['ok'])
        self.assertIn('EVIDENCE_UNAVAILABLE',str(data['diagnostics']))
        self.assertIsNone(data['events'][0]['references'][0]['href'])

    def test_evidence_hash_change_has_no_clickable_stale_link(self):
        conf=self.config();conf['evidence_sources'][0]['sha256']='a'*64;self.save_config(conf)
        data=self.model();self.assertEqual(data['events'][0]['references'][0]['status'],'unavailable')
        self.assertIsNone(data['events'][0]['references'][0]['href'])

    def test_no_filename_based_scene_image_guessing(self):
        (self.root/'SC1-newest.png').write_bytes(b'not an image')
        data=self.model();self.assertEqual(data['scene_artwork'],[])

    def test_unsafe_evidence_urls_and_paths_are_not_linked(self):
        rows=self.fixture['events'];rows[0]['evidence']=[{'url':'javascript:alert(1)'},{'path':'../secret.txt'},{'url':'https://user:pass@example.com/path'}]
        write_events(self.root,rows);data=self.model()
        self.assertTrue(all(r['href'] is None for r in data['events'][0]['references']))
        self.assertTrue(all(r['status']=='unsafe-or-unavailable' for r in data['events'][0]['references']))

    def test_unbound_evidence_remains_recorded_and_is_not_fabricated(self):
        conf=self.config();conf['evidence_sources']=[];self.save_config(conf)
        row=self.model()['events'][0]['references'][0]
        self.assertEqual(row['status'],'unbound');self.assertIsNone(row['href']);self.assertEqual(row['record']['source_id'],'fixture-author')

    def test_html_escapes_embedded_script_and_preserves_original_value(self):
        malicious='</script><script>window.cpbInjected=true</script><img src=x onerror=alert(1)>'
        rows=[event('SAFE',1,malicious)];rows[0]['notes']=[malicious];write_events(self.root,rows)
        story.refresh(self.root);text=self.output.read_text(encoding='utf-8')
        self.assertNotIn(malicious,text);self.assertIn('\\u003c/script',text)
        self.assertEqual(data_from_html(self.output)['events'][0]['event']['notes'],[malicious])

    def test_malformed_jsonl_keeps_last_success_explicitly_stale(self):
        story.refresh(self.root);old=data_from_html(self.output)['projection_id']
        (self.root/'state/events.jsonl').write_text('{not json\n',encoding='utf-8')
        result=activity.refresh(self.root);self.assertFalse(result['ok']);self.assertTrue((self.root/'gallery.html').is_file())
        self.assertIn('Story timeline update failed',self.output.read_text(encoding='utf-8'))
        previous=self.output.with_suffix('.last-good.html');self.assertIn('STALE:',previous.read_text(encoding='utf-8'))
        self.assertEqual(data_from_html(previous)['projection_id'],old)
        self.assertIn('line 1',result['story_timeline']['message'])
        write_events(self.root,self.fixture['events']);self.assertTrue(activity.refresh(self.root)['ok'])
        self.assertFalse((self.root/'work/activity/projections-pending.json').exists())

    def test_failure_is_isolated_from_gallery_and_activity_views(self):
        story.refresh(self.root)
        with patch.object(story,'render_html',side_effect=OSError('synthetic timeline renderer failure')):
            row=event('E3',30,'later');write_events(self.root,self.fixture['events']+[row]);result=activity.refresh(self.root)
        self.assertFalse(result['ok']);self.assertTrue((self.root/'gallery.json').is_file())
        self.assertTrue((self.root/'work/activity/timeline.jsonl').is_file())
        self.assertTrue(activity.refresh(self.root)['ok'])

    def test_gallery_failure_does_not_prevent_story_publication(self):
        with patch.object(studio,'write_gallery',side_effect=OSError('synthetic gallery failure')):
            result=activity.refresh(self.root)
        self.assertFalse(result['ok']);self.assertTrue(result['story_timeline']['ok']);self.assertTrue(self.output.is_file())

    def test_changed_source_during_build_is_not_published_as_current(self):
        story.refresh(self.root);original=story.render_html
        def change(model,generated):
            write_events(self.root,[event('NEW',100,'new')]);return original(model,generated)
        conf=self.config();conf['views'][0]['label']='changed';self.save_config(conf)
        with patch.object(story,'render_html',side_effect=change):result=story.refresh(self.root)
        self.assertFalse(result['ok']);self.assertIn('changed during projection',result['message'])
        self.assertIn('No current state is asserted',self.output.read_text(encoding='utf-8'))
        self.assertTrue(story.refresh(self.root)['ok'])

    def test_projection_refuses_escape_symlink_and_foreign_output(self):
        for out in (Path('../outside.html'),Path('state/events.jsonl')):
            with self.subTest(out=out),self.assertRaises(ValueError):story.refresh(self.root,out=out)
        foreign=self.root/'foreign.html';foreign.write_text('original',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'not owned'):story.refresh(self.root,out=foreign)
        self.assertEqual(foreign.read_text(encoding='utf-8'),'original')
        target=self.root/'link.html'
        try:target.symlink_to(foreign)
        except (OSError,NotImplementedError):return
        with self.assertRaises(ValueError):story.refresh(self.root,out=target)

    def test_publication_never_overwrites_an_unrelated_status_file(self):
        story.refresh(self.root)
        status=self.output.with_suffix('.status.json')
        c.atomic_write_json(status,{'authored':'not a projection receipt'})
        before=status.read_bytes()
        with self.assertRaisesRegex(ValueError,'status path is not owned'):
            story.refresh(self.root)
        self.assertEqual(status.read_bytes(),before)

    def test_synthetic_example_is_in_release_and_runs_without_a_private_pack(self):
        from package_metadata import iter_release_files, load_package_metadata
        root=Path(__file__).resolve().parents[1]
        metadata=load_package_metadata(root)
        names={p.relative_to(root).as_posix() for p in iter_release_files(root,metadata.release_include,exclude_names=metadata.release_exclude_names)}
        self.assertIn('examples/story-timeline/build_example.py',names)
        out=Path(self.temp.name)/'standalone-example'
        cmd=[sys.executable,str(root/'examples/story-timeline/build_example.py'),'--out',str(out)]
        result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['synthetic'])
        data=data_from_html(out/story.OUTPUT)
        self.assertEqual((len(data['events']),len(data['views'])),(4,4))
        self.assertTrue(data['ok'])

    def test_inspect_does_not_publish_or_change_inputs(self):
        before=self.canonical_bytes()
        cmd=[sys.executable,str(Path(__file__).with_name('story_timeline.py')),'--studio',str(self.root),'--inspect']
        p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertTrue(json.loads(p.stdout)['ok']);self.assertFalse(self.output.exists());self.assertEqual(before,self.canonical_bytes())

    def test_cli_explicit_selection_and_subdirectory_links(self):
        cmd=[sys.executable,str(Path(__file__).with_name('story_timeline.py')),'--studio',str(self.root),
             '--timeline','main','--story-order','5','--story-time','chapter:between','--scene-context-id','SC1',
             '--out','views/nested/story.html']
        p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        data=data_from_html(self.root/'views/nested/story.html');self.assertEqual(data['views'][0]['view']['story_order'],5)
        self.assertEqual(data['source_links']['base'],'../../state/world-state-base.json')
        self.assertEqual(data['events'][0]['references'][0]['href'],'../../decision.txt')

    def test_many_records_validate_once_and_are_paginated_in_the_dom_contract(self):
        rows=[event('E'+str(i),i,str(i)) for i in range(500)];write_events(self.root,rows)
        import temporal_state
        with patch.object(temporal_state,'validate_artifact',wraps=temporal_state.validate_artifact) as validate:
            data=self.model();self.assertEqual(validate.call_count,500)
        self.assertEqual(len(data['events']),500)
        text=story.render_html(data,'2000-01-01T00:00:00Z')
        self.assertIn('pageSize=40',text)
        self.assertNotIn('<article',text)
        self.assertEqual(data['coverage']['queries_checked'],1)

    def test_state_protocol_finalized_base_write_refreshes_known_input(self):
        # This exercises notification independently of author editing; a normal
        # finalize command writes typed artifacts, including configured sources.
        story.refresh(self.root)
        base=c.load(self.root/'state/world-state-base.json');base['world']={'authored':'changed'}
        c.atomic_write_json(self.root/'state/world-state-base.json',base)
        story.notify_state_write(self.root/'state/world-state-base.json')
        self.assertEqual(data_from_html(self.output)['base']['world'],{'authored':'changed'})
        events=activity.read_events(self.root)[0];self.assertTrue(any(row['event']=='story-input-written' for row in events))


class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)/'studio';setup(self.root)
        studio.add_character(self.root,'robot','general')
        self.sheet=self.root/'characters/robot/sheet/sheet-data.json'
        from sheet_artifacts_smoke_test import accepted
        self.first=accepted(self.sheet)
        conf=c.load(self.root/story.CONFIG);conf['scene_artwork']=[{'timeline_id':'main','scene_context_id':'SC1','character':'robot','slot':'canon.primary','label':'Explicit scene artwork'}]
        c.atomic_write_json(self.root/story.CONFIG,conf);activity.refresh(self.root)

    def test_adoption_changes_image_not_story_order_and_automatically_refreshes(self):
        from sheet_artifacts_smoke_test import accepted
        before=data_from_html(self.root/story.OUTPUT)
        second=accepted(self.sheet,marker='replacement',color=(180,40,50))
        after=data_from_html(self.root/story.OUTPUT)
        self.assertEqual(after['scene_artwork'][0]['artifact_id'],second['artifact_id'])
        self.assertNotEqual(before['scene_artwork'][0]['artifact_id'],second['artifact_id'])
        self.assertEqual(before['events'],after['events'])
        self.assertEqual(before['views'][0]['snapshot'],after['views'][0]['snapshot'])

    def test_candidate_does_not_replace_accepted_scene_image(self):
        import sheet_artifacts as fills
        from sheet_artifacts_smoke_test import make_artifact
        candidate=make_artifact(self.sheet,marker='candidate')
        fills.register_candidates(self.sheet,[('canon.primary',candidate)])
        self.assertEqual(data_from_html(self.root/story.OUTPUT)['scene_artwork'][0]['artifact_id'],self.first['artifact_id'])

    def test_missing_selected_image_is_a_link_diagnostic_not_false_state(self):
        (self.sheet.parent/self.first['image']['path']).unlink()
        result=activity.refresh(self.root);self.assertTrue(result['ok'],result)
        data=data_from_html(self.root/story.OUTPUT);self.assertTrue(data['views'][0]['ok'])
        self.assertEqual(data['scene_artwork'][0]['status'],'unavailable');self.assertIsNone(data['scene_artwork'][0]['href'])
        self.assertIn('SCENE_ARTWORK_UNAVAILABLE',str(data['diagnostics']))

    def test_repeated_scene_bindings_verify_shared_artwork_once(self):
        import sheet_artifacts as fills
        conf=c.load(self.root/story.CONFIG);second=copy.deepcopy(conf['scene_artwork'][0]);second['scene_context_id']='SC2';conf['scene_artwork'].append(second)
        c.atomic_write_json(self.root/story.CONFIG,conf)
        with patch.object(fills,'_image_metadata',wraps=fills._image_metadata) as decode:
            model,_=story.build_model(self.root,self.root/story.OUTPUT)
            self.assertEqual(decode.call_count,1)
            self.assertEqual(len(model['scene_artwork']),2)


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
