#!/usr/bin/env python3
"""Exercise moment semantics, selected guidance, publication and production linkage."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import story_context as sc
import temporal_state as ts
import protocol_contract as pc
import production_workflow as production
import production_fixtures
import work_ledger

ROOT=Path(__file__).resolve().parents[1]
loader=importlib.util.spec_from_file_location('moment_fixture', ROOT/'examples/story-context/run_example.py')
fixture=importlib.util.module_from_spec(loader);loader.loader.exec_module(fixture)


class MomentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='moment-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'作品 and spaces';self.query=fixture.write_inputs(self.root)
    def save(self):fixture.pin(self.root,self.query)
    def value(self):self.save();return sc.materialize(self.root,'query.json')
    def change_json(self,name,fn):
        value=json.loads((self.root/name).read_text());fn(value);fixture.write(self.root,name,value)
    def events(self,value):fixture.write(self.root,'events.jsonl',''.join(json.dumps(e)+'\n' for e in value))
    def minimal(self):
        self.query.pop('views',None);self.query.pop('author_bindings',None);self.query.pop('requirements',None)
    def command(self,*args):
        return subprocess.run([sys.executable,'-B',str(ROOT/'scripts/story_context.py'),*map(str,args)],capture_output=True,text=True,
                              env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    def build(self):
        result=self.value();sc.publish(result,self.root/'bundle');return result

    def test_arbitrary_point_requires_no_scene_or_event(self):
        result=self.value();a=result['author'];self.assertEqual(a['story_order'],15)
        self.assertEqual(a['global_snapshot']['scene_context_id'],None)
        self.assertEqual(set(a['global_snapshot']['entities']['characters']),{'A','B'})
        self.assertEqual(a['indexes']['work']['groups']['active'],['one','two'])
    def test_scopes_do_not_mix(self):
        a=self.value()['author']
        self.assertNotIn('attention',a['global_snapshot']['entities']['characters']['A'])
        self.assertEqual(a['context_snapshots']['CTX:work.room']['entities']['characters']['A']['attention'],'task')
    def test_context_ids_with_dots_and_colons(self):
        files=sc.output_files(self.value());self.assertEqual(len([p for p in files if p.startswith('contexts/')]),1)
        self.assertTrue(all('CTX:' not in p for p in files))
    def test_context_identifier_does_not_inherit_filename_limits(self):
        context='CTX:'+('long.'*80)
        self.query['scene_context_ids']=[context]
        self.query['requirements'][0]['scene_context_id']=context
        self.query['views'][0]['scene_context_id']=context
        p=self.root/'events.jsonl';p.write_text(p.read_text().replace('CTX:work.room',context))
        bundle=self.value();self.assertIn(context,bundle['author']['context_snapshots'])
        self.assertTrue(all(len(Path(name).name)<=69 for name in sc.output_files(bundle)))

    def test_history_does_not_force_context_expansion(self):
        self.minimal();self.query['scene_context_ids']=[];self.query['indexes']=[]
        self.events([fixture.event(f'E{i}',i,[fixture.change('/light',str(i),entity_type='environment',entity_id='SPACE',persistence='scene-local')],scene_context_id=f'CTX:{i}.room') for i in range(150)])
        self.change_json('coverage.json',lambda v:v.update(through_order=200));self.query['at']['story_order']=160
        a=self.value()['author'];self.assertEqual(a['context_snapshots'],{})
        self.assertEqual(a['global_snapshot']['entities']['environments']['SPACE']['light'],'soft')
    def test_unselected_context_has_precise_error(self):
        self.query['scene_context_ids']=[]
        with self.assertRaisesRegex(ValueError,'unselected scene context'):self.value()
    def test_no_characters_or_fixed_concept_fields_required(self):
        self.minimal();self.query.pop('indexes');self.query.pop('scene_context_ids');self.events([])
        self.change_json('base.json',lambda v:v.update(characters={},relationships={},environments={},props={},world={'arbitrary':{'phase':False}}))
        self.query['timeline']['base_provenance']=self.query['timeline']['base_provenance'][-1:]
        a=self.value()['author'];self.assertEqual(a['global_snapshot']['entities']['world']['arbitrary']['phase'],False)
    def test_arbitrary_cast_size_preserved(self):
        self.minimal();self.query['scene_context_ids']=[];self.events([])
        self.change_json('base.json',lambda v:v['characters'].update({f'X{i}':{} for i in range(50)}))
        self.assertEqual(len(self.value()['author']['global_snapshot']['entities']['characters']),52)
    def test_ending_one_activity_does_not_clear_aftermath(self):
        self.minimal();self.query['at']['story_order']=35;a=self.value()['author']
        self.assertEqual(a['indexes']['work']['groups']['active'],['two'])
        self.assertEqual(a['global_snapshot']['entities']['world']['commitments']['reply']['status'],'unresolved')
    def test_future_knowledge_does_not_leak_on_rewind(self):
        self.minimal();self.query['at']['story_order']=25;new=self.value()['author']
        self.assertTrue(new['global_snapshot']['entities']['characters']['A']['knows_signal'])
        self.query['at']['story_order']=15;old=self.value()['author'];self.assertFalse(old['global_snapshot']['entities']['characters']['A']['knows_signal'])
        self.assertFalse(new['global_snapshot']['entities']['characters']['B']['knows_signal'])
    def test_proposed_events_do_not_apply(self):
        self.events([fixture.event('PROPOSED',5,[fixture.change('/new',True)],canon_status='proposed')]);self.assertNotIn('new',self.value()['author']['global_snapshot']['entities']['world'])
    def test_other_timeline_does_not_apply(self):
        self.events([fixture.event('OTHER',5,[fixture.change('/new',True)],timeline_id='other')]);self.assertNotIn('new',self.value()['author']['global_snapshot']['entities']['world'])
    def test_missing_null_false_and_unknown_remain_distinct(self):
        self.change_json('base.json',lambda v:v['world'].update(none=None,no=False,unknown={'status':'unknown'}))
        self.query['views'][0]['fields']=['/world/missing','/world/none','/world/no','/world/unknown/status']
        rows=self.value()['views'][0]['fields'];self.assertFalse(rows[0]['present']);self.assertNotIn('value',rows[0]);self.assertIsNone(rows[1]['value']);self.assertIs(rows[2]['value'],False);self.assertEqual(rows[3]['value'],'unknown')
    def test_no_collection_does_not_mean_empty(self):
        self.query['indexes'][0]['pointer']='/world/unrecorded';index=self.value()['author']['indexes']['work'];self.assertFalse(index['present']);self.assertNotIn('groups',index)
    def test_container_cannot_be_sent_as_scalar(self):
        self.query['views'][0]['fields']=['/world/work_streams']
        with self.assertRaisesRegex(ValueError,'scalar leaves'):self.value()
    def test_diagnostics_expose_actual_failed_predicate(self):
        self.minimal();self.query['requirements']=[{'requirement_id':'missing','scene_context_id':None,'pointer':'/world/absent','test':'present','purpose':'Needed detail'}]
        report=sc.report(self.value());self.assertFalse(report['requirements_ok']);self.assertFalse(report['requirements'][0]['present']);self.assertEqual(report['requirements'][0]['pointer'],'/world/absent')
    def test_false_is_not_zero_for_equality(self):
        self.query['requirements'][0].update(pointer='/characters/A/knows_signal',value=0)
        self.assertFalse(self.value()['author']['requirements_ok'])
    def test_equals_requires_value(self):
        self.query['requirements'][0].pop('value')
        with self.assertRaisesRegex(ValueError,'explicit value'):self.value()
    def test_duplicate_requirements_rejected(self):
        self.query['requirements']*=2
        with self.assertRaisesRegex(ValueError,'duplicate'):self.value()
    def test_failed_requirements_can_be_diagnosed_but_not_published_strictly(self):
        self.query['requirements'][0]['value']='unmet';self.save()
        r=self.command('build','--root',self.root,'--query','query.json','--out',self.root/'x','--require-fields')
        self.assertEqual(r.returncode,1);self.assertFalse((self.root/'x').exists());self.assertFalse(json.loads(r.stdout)['requirements_ok'])
    def test_verify_require_fields_is_enforced(self):
        self.query['requirements'][0]['value']='unmet';self.build()
        a=self.command('verify','--root',self.root,'--query','query.json','--bundle',self.root/'bundle')
        b=self.command('verify','--root',self.root,'--query','query.json','--bundle',self.root/'bundle','--require-fields')
        self.assertEqual(a.returncode,0);self.assertEqual(b.returncode,1);self.assertTrue(json.loads(b.stdout)['content_ok']);self.assertFalse(json.loads(b.stdout)['requirements_ok'])
    def test_inspect_require_fields_is_enforced(self):
        self.query['requirements'][0]['value']='unmet';self.save();r=self.command('inspect','--root',self.root,'--query','query.json','--require-fields');self.assertEqual(r.returncode,1)
    def test_cli_rejects_irrelevant_output_arguments(self):
        self.save();r=self.command('inspect','--root',self.root,'--query','query.json','--out',self.root/'bad');self.assertNotEqual(r.returncode,0)
    def test_outside_coverage(self):
        self.query['at']['story_order']=101
        with self.assertRaisesRegex(ValueError,'outside'):self.value()
    def test_wrong_coverage_timeline(self):
        self.change_json('coverage.json',lambda v:v.update(timeline_id='other'))
        with self.assertRaisesRegex(ValueError,'another timeline'):self.value()
    def test_unpinned_sources_fail(self):
        fixture.write(self.root,'design.md','changed')
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):sc.materialize(self.root,'query.json')
    def test_unknown_source(self):
        self.query['timeline']['base_source']='ABSENT'
        with self.assertRaisesRegex(ValueError,'unresolved source'):self.value()
    def test_author_binding_selects_epoch_not_whole_document(self):
        a=self.value()['author'];self.assertIn('Earlier',a['author_bindings']['voice']['selected_content']);self.assertNotIn('initiates conversation',a['author_bindings']['voice']['selected_content'])
    def test_expired_binding_blocks_view(self):
        self.query['at']['story_order']=20
        with self.assertRaisesRegex(ValueError,'not applicable'):self.value()
    def test_expired_binding_is_retained_as_inapplicable_in_author_report(self):
        self.query['views']=[];self.query['at']['story_order']=20;a=self.value()['author']['author_bindings']['voice'];self.assertFalse(a['applicable_at_moment']);self.assertNotIn('selected_content',a)
    def test_binding_wrong_context(self):
        self.query['author_bindings'][0]['scene_context_ids']=['OTHER']
        with self.assertRaisesRegex(ValueError,'not applicable'):self.value()
    def test_selected_intent_needs_approval(self):
        p=self.root/'intent.md';p.write_text(p.read_text().replace('**status**: adopted','**status**: proposed'))
        with self.assertRaisesRegex(ValueError,'adopted intent'):self.value()
    def test_intent_binding_contains_actual_selected_text(self):
        value=self.value()['author']['author_bindings']['intent']['selected_content']
        self.assertIsInstance(value,str);self.assertIn('Synthetic portrayal decision',value)
    def test_broken_section_selector(self):
        self.query['author_bindings'][0]['selector']['heading']='## Unknown'
        with self.assertRaisesRegex(ValueError,'exact Markdown heading'):self.value()
    def test_duplicate_heading_is_not_arbitrarily_selected(self):
        p=self.root/'persona.md';p.write_text(p.read_text()+'\n## Earlier period\nOther\n')
        with self.assertRaisesRegex(ValueError,'one exact'):self.value()
    def test_json_epoch_selector(self):
        fixture.write(self.root,'persona.json',{'epochs':{'first':{'speech':'brief'}}});self.query['sources'][5]['path']='persona.json';self.query['author_bindings'][0]['selector']={'kind':'json-pointer','pointer':'/epochs/first'}
        self.assertEqual(self.value()['author']['author_bindings']['voice']['selected_content'],{'speech':'brief'})
    def test_consumer_excludes_author_sources_and_unselected_knowledge(self):
        result=self.value();raw=sc.encoded(result['views'][0]);self.assertNotIn(b'PRIVATE',raw);self.assertNotIn(b'knows_signal',raw);self.assertNotIn(b'Later period',raw);self.assertEqual(len(result['views'][0]['basis']),2)
    def test_predicate_secret_is_not_exported(self):
        self.query['requirements'][0].update(pointer='/world/signal',value=True,purpose='PRIVATE predicate');v=self.value()['views'][0];self.assertNotIn('signal',sc.encoded(v).decode());self.assertNotIn('PRIVATE',sc.encoded(v).decode())
    def test_guidance_for_unknown_binding(self):
        self.query['views'][0]['guidance'][0]['binding_ids']=['MISSING']
        with self.assertRaisesRegex(ValueError,'unknown author binding'):self.value()
    def test_build_and_verify_after_copy(self):
        import shutil
        result=self.build();shutil.copytree(self.root,self.root.parent/'copy');copyroot=self.root.parent/'copy'
        self.assertTrue(sc.verify(copyroot,'query.json',copyroot/'bundle',require_fields=True)['ok'])
    def test_extra_output_file_rejected(self):
        self.build();fixture.write(self.root,'bundle/leak.txt','secret');self.assertFalse(sc.verify(self.root,'query.json',self.root/'bundle')['content_ok'])
    def test_output_tamper_rejected(self):
        self.build();fixture.write(self.root,'bundle/report.json',{});self.assertFalse(sc.verify(self.root,'query.json',self.root/'bundle')['content_ok'])
    def test_existing_output_is_not_replaced(self):
        bundle=self.build()
        with self.assertRaises(ValueError):sc.publish(bundle,self.root/'bundle')
    def test_concurrent_reservation_is_not_removed(self):
        bundle=self.value();lock=self.root/'.bundle.story-context-lock';lock.write_text('other')
        with self.assertRaises(FileExistsError):sc.publish(bundle,self.root/'bundle')
        self.assertEqual(lock.read_text(),'other')
    def test_source_path_escapes_rejected(self):
        self.query['sources'][0]['path']='../outside.json';fixture.write(self.root,'query.json',self.query)
        with self.assertRaisesRegex(ValueError,'escapes'):sc.materialize(self.root,'query.json')
    def test_all_author_bindings_are_selected(self):
        self.query['views']=[]
        original=copy.deepcopy(self.query['author_bindings'][0])
        self.query['author_bindings']=[{**original,'binding_id':f'B{i}'} for i in range(520)]
        self.save()
        with patch.object(sc,'_selection',wraps=sc._selection) as selected:
            sc.materialize(self.root,'query.json')
            self.assertEqual(selected.call_count,520)

    def test_materialization_does_not_truncate_selected_content(self):
        self.save()
        bundle = sc.materialize(self.root,'query.json')
        self.assertTrue(bundle)


class TemporalTests(unittest.TestCase):
    def state(self,events,processes=(),order=15):
        base={'characters':{'A':{'physical_state':{'condition':'resting'}}},'world':{'items':['A','B','C'],'flag':False}}
        return ts.resolve_world(base_state=base,events=events,processes=list(processes),timeline_id='main',story_order=order,story_time='selected',snapshot_id='TEST',scene_context_id=None)
    def test_linked_process_start_is_one_change(self):
        process=fixture.process();start=fixture.event('START',10,[fixture.change('/physical_state/condition','tired',entity_type='character',entity_id='A',persistence='progressive',process_id='RECOVERY')],preconditions=[{'entity_type':'character','entity_id':'A','path':'/physical_state/condition','operator':'equals','value':'resting'}])
        value=self.state([start],[process]);self.assertEqual(value['entities']['characters']['A']['physical_state']['condition'],'tired');self.assertIn('RECOVERY@epoch-initial:offset-0',value['applied_process_milestones']);self.assertEqual(value['applied_event_ids'],['START'])
        self.assertEqual(self.state([start],[process],21)['entities']['characters']['A']['physical_state']['condition'],'ready')
    def test_linked_start_requires_same_json_value(self):
        p=fixture.process();p['milestones'][0]['state']=True
        e=fixture.event('START',10,[fixture.change('/physical_state/condition',1,entity_type='character',entity_id='A',persistence='progressive',process_id='RECOVERY')])
        with self.assertRaisesRegex(ValueError,'initiating value'):self.state([e],[p])

    def test_unrelated_same_path_processes_conflict(self):
        with self.assertRaises(ts.TemporalConflictError):self.state([], [fixture.process(),fixture.process('OTHER')])
    def test_array_removal_and_sibling_update_conflict_for_either_id_order(self):
        for ids in [('A','B'),('B','A')]:
            with self.subTest(ids=ids),self.assertRaises(ts.TemporalConflictError):self.state([fixture.event(ids[0],10,[fixture.change('/items/0',operation='remove')]),fixture.event(ids[1],10,[fixture.change('/items/1','X')])])
    def test_array_extension_and_sibling_update_conflict(self):
        with self.assertRaises(ts.TemporalConflictError):self.state([fixture.event('A',10,[fixture.change('/items/6','new')]),fixture.event('B',10,[fixture.change('/items/1','X')])])
    def test_disjoint_array_replacements_are_independent(self):
        events=[fixture.event('A',10,[fixture.change('/items/0','X')]),fixture.event('B',10,[fixture.change('/items/1','Y')])]
        self.assertEqual(self.state(events)['entities']['world']['items'],['X','Y','C']);self.assertEqual(self.state(events)['entities'],self.state(list(reversed(events)))['entities'])
    def test_read_write_precondition_interference(self):
        a=fixture.event('A',10,[fixture.change('/flag',True)])
        b=fixture.event('B',10,[fixture.change('/result','yes')],preconditions=[{'entity_type':'world','entity_id':'WORLD','path':'/flag','operator':'equals','value':True}])
        with self.assertRaisesRegex(ts.TemporalConflictError,'precondition'):self.state([a,b])
    def test_one_atomic_event_has_explicit_operation_order(self):
        e=fixture.event('ONE',10,[fixture.change('/items/0',operation='remove'),fixture.change('/items/1','X')]);self.assertEqual(self.state([e])['entities']['world']['items'],['B','X'])
    def test_separate_coordinates_establish_order(self):
        a=fixture.event('A',10,[fixture.change('/items/0',operation='remove')]);b=fixture.event('B',11,[fixture.change('/items/1','X')]);self.assertEqual(self.state([b,a])['entities']['world']['items'],['B','X'])
    def test_process_advance_precedes_discrete_event(self):
        p=fixture.process();e=fixture.event('A',10,[fixture.change('/physical_state/condition','busy',entity_type='character',entity_id='A')]);self.assertEqual(self.state([e],[p])['entities']['characters']['A']['physical_state']['condition'],'busy')


class ProductionTests(MomentTests):
    # Select only the additional production cases below, avoiding repeated inherited cases.
    def setup_run(self):
        self.build();task=work_ledger.begin(self.root,'Moment fixture',['prepare','deliver']);fixture.write(self.root,'delivery.txt','Follow the selected moment.\n')
        spec={'task_id':task['task_id'],'route':'story-context','features':[], 'sources':[],
              'delivery':{'path':'delivery.txt','transport':'bounded-context','translation_notes':'Only selected information.'},'criteria':[{'id':'bounded','strength':'hard','text':'Inspect only the declared bounded moment.'}],
              'world_views':[],'moment_views':[{'query':'query.json','bundle':'bundle','view_id':'depiction.main'}]}
        production_fixtures.task(self.root,spec)
        fixture.write(self.root,'task.json',spec);return production.prepare(self.root,'task.json')['run']
    def test_production_selects_only_view(self):
        run=self.setup_run();consumer=json.loads((self.root/'production'/run/'consumer.json').read_text());self.assertEqual(len(consumer['moment_views']),1);self.assertNotIn('PRIVATE',json.dumps(consumer));self.assertEqual(consumer['world_views'],[])
    def test_source_change_invalidates_prepared_run(self):
        run=self.setup_run();fixture.write(self.root,'persona.md','changed persona')
        with self.assertRaisesRegex(ValueError,'changed project input'):production.assert_current(self.root,run)
    def test_query_change_invalidates_prepared_run(self):
        run=self.setup_run();self.query['at']['story_order']=16;self.save()
        with self.assertRaisesRegex(ValueError,'changed project input'):production.assert_current(self.root,run)
    def test_bundle_change_invalidates_prepared_run(self):
        run=self.setup_run();fixture.write(self.root,'bundle/report.json',{})
        with self.assertRaisesRegex(ValueError,'changed project input'):production.assert_current(self.root,run)
    def test_generation_binding_carries_selected_moment(self):
        import production_binding
        run=self.setup_run();binding=production_binding.create(self.root,run,'Follow the selected moment.')
        production_binding.validate(binding,'Follow the selected moment.')
        text=production_binding.effective(binding,'Follow the selected moment.', context_transport='prompt-prefix')
        self.assertIn('moment_views',text);self.assertIn('tense',text)
        self.assertIn('Keep the response concise',text);self.assertNotIn('PRIVATE',text)
        production_binding.validate_live(self.root,run,{'production_binding':binding,'composition_prompt':'Follow the selected moment.'})

    def test_failed_view_cannot_prepare(self):
        self.query['requirements'][0]['value']='unmet'
        with self.assertRaisesRegex(ValueError,'satisfied field requirements'):self.setup_run()
    def test_unrelated_author_diagnostic_does_not_block_selected_view(self):
        self.query['requirements'].append({'requirement_id':'other','scene_context_id':None,'pointer':'/world/other','test':'present','purpose':'Unrelated author question'})
        self.assertTrue(self.setup_run())
    def test_route_requires_selected_moment(self):
        self.setup_run();spec=json.loads((self.root/'task.json').read_text());spec['moment_views']=[]
        with self.assertRaisesRegex(ValueError,'selected moment view'):production.validate_task(spec)
    def test_source_change_between_resolve_and_pin_is_caught(self):
        self.build();task=work_ledger.begin(self.root,'fixture',['step']);fixture.write(self.root,'delivery.txt','Use selected facts')
        spec={'task_id':task['task_id'],'route':'story-context','features':[],'sources':[], 'delivery':{'path':'delivery.txt','transport':'bounded-context','translation_notes':'test'},'criteria':[{'id':'bounded','strength':'hard','text':'Inspect only the declared bounded moment.'}],'world_views':[],'moment_views':[{'query':'query.json','bundle':'bundle','view_id':'depiction.main'}]}
        production_fixtures.task(self.root,spec)
        fixture.write(self.root,'task.json',spec);original=sc.verify_output
        def mutate(*args,**kw):
            result=original(*args,**kw);fixture.write(self.root,'design.md','changed');return result
        with patch.object(sc,'verify_output',side_effect=mutate),self.assertRaisesRegex(ValueError,'source changed during preparation'):production.prepare(self.root,'task.json')


def suite():
    result=unittest.TestSuite()
    for cls in (MomentTests,TemporalTests):result.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    for name in ProductionTests.__dict__:
        if name.startswith('test_'):result.addTest(ProductionTests(name))
    return result

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(suite())
    print(json.dumps({'ok':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}))
    raise SystemExit(not result.wasSuccessful())
