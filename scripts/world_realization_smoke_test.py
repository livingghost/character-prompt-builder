#!/usr/bin/env python3
"""Current-plan tests for provenance, independent states, scoped exports and review.

    python scripts/world_realization_smoke_test.py

Fresh authored fixtures only; no archived format/version-pair checks or model calls.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import world_realization as wr
import portrayal_principles as pp
from authorial_intent_audit import REQUIRED_FIELDS
from state_protocol import validate_artifact

ROOT=Path(__file__).resolve().parents[1]
SHELL='/props/LAMP/appearance/shell'
SIGNAL='/props/LAMP/appearance/signal'


def json_write(path: Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def evidence():
    return [{'source_id':'WORLD','locator':'World decisions / fixture conditions','basis':'author-decision'}]


def event(identifier='EV_LIGHT', order=10, value='bright'):
    return {'artifact_type':'state-event','event_id':identifier,'timeline_id':'main',
        'event_scope':'appearance-state','targets':['LAMP'],'effective_order':order,'effective_from':f'story:{order}',
        'recorded_at':'2026-09-16T00:00:00Z','disclosed_at':None,'occurrence':'offscreen','canon_status':'approved',
        'atomic':False,'cause':{'type':'author-decision','reference':'WORLD:fixture conditions'},'preconditions':[],
        'changes':[{'entity_type':'prop','entity_id':'LAMP','path':'/appearance/signal','operation':'set',
                    'value':value,'persistence':'persistent-until-superseded','visual_priority':'supporting'}],
        'evidence':evidence(),'supersedes_event_ids':[],'notes':[]}


def make_fixture(root: Path) -> dict:
    root.mkdir(parents=True,exist_ok=True)
    base={'characters':{},'relationships':{},'environments':{'ROOM':{'light':'ambient','weather':'dry'}},
          'props':{'LAMP':{'appearance':{'shell':'ribbed','signal':'dark'},'physical_state':{'condition':'intact'},'owner':None}},
          'world':{'public_rule':'unanswered','author_secret':'SECRET_MARKER_NOT_FOR_CONSUMER'}}
    json_write(root/'base.json',base)
    (root/'events.jsonl').write_text(json.dumps(event())+'\n',encoding='utf-8')
    json_write(root/'processes.json',[])
    world='# World decisions\n\n## Fixture conditions\n\n'
    world+='Synthetic example, not user-adopted story canon. One unpeopled room contains a ribbed signal lamp. Its emitted signal turns bright at order 10. The shell remains ribbed. Weather stays dry. Ownership is explicitly null. The public rule is deliberately unanswered. An author-only test marker exists solely to test bounded export.\n'
    (root/'world.md').write_text(world,encoding='utf-8')
    values={key:f'Authored synthetic {key.replace("_"," ")} for this example only.' for key in REQUIRED_FIELDS}
    values.update(status='adopted',basis='Fixture author decision, not user approval.',subject_scope='The lamp in this worked example.',
      portrayal_aim='Make the same lamp recognizable while its emitted signal changes.',recognition_anchors='The ribbed shell persists.',
      variation_envelope='Signal emission may change at its recorded event; shell construction does not.',contrast_and_cadence='Later view, earlier view, then later view again. No character arc.',
      information_boundary='Author-only test marker must not enter the consumer view.',review_basis='Synthetic structural checks only, not an inspected image.')
    (root/'intent.md').write_text('# Example intent\n\n### Intent i-lamp\n\n'+'\n'.join(f'- **{k}**: {v}' for k,v in values.items())+'\n',encoding='utf-8')
    sources=[{'source_id':i,'path':f,'sha256':hashlib.sha256((root/f).read_bytes()).hexdigest()}
             for i,f in [('BASE','base.json'),('EVENTS','events.jsonl'),('PROCESSES','processes.json'),('WORLD','world.md'),('INTENT','intent.md')]]
    units=[]
    for identifier,opening,closing in [('AFTER',10,12),('BEFORE',0,0),('RETURN',12,12)]:
        units.append({'unit_id':identifier,'medium':'prose','timeline_id':'main','scene_context_id':'ROOM',
          'opening':{'story_order':opening,'story_time':f'story:{opening}'},'closing':{'story_order':closing,'story_time':f'story:{closing}'},
          'portrayal_sources':['WORLD'],'intent_refs':[{'source_id':'INTENT','intent_id':'i-lamp'}],
          'reference_queries':[{'query_id':'SHELL','at':'opening','entity_pointer':'/props/LAMP','role':'shell-construction','facets':[SHELL]},
                               {'query_id':'SIGNAL','at':'opening','entity_pointer':'/props/LAMP','role':'signal-state','facets':[SIGNAL]}],
          'views':[{'view_id':'WRITER','recipient':'scoped-prose-writer','purpose':'Describe only the currently supplied visible conditions.',
                    'state_fields':[{'at':'opening','pointer':SHELL},{'at':'opening','pointer':SIGNAL}],
                    'reference_query_ids':['SHELL'], 'instructions':['Keep the shell recognizable; describe the current signal without inventing a cause or a person.']}],
          'review_note':'No actual output has been evaluated. This fixture tests state and export structure only.'})
    plan={'artifact_type':'world-realization-plan','plan_id':'EXAMPLE','status':'draft','basis':'Synthetic authored demonstration, not creator approval.',
      'sources':sources,'timelines':[{'timeline_id':'main','base_source':'BASE','events_source':'EVENTS','processes_source':'PROCESSES',
       'base_provenance':[{'pointer':p,'evidence':evidence()} for p in ['/props/LAMP','/environments/ROOM','/world']]}],
      'units':units,'links':[{'from_unit':'AFTER','to_unit':'RETURN','relation':'continuous','basis':'Same unchanged emitted signal at connected boundaries.',
          'assertions':[{'from_pointer':SIGNAL,'to_pointer':SIGNAL,'comparison':'equal'}]},
         {'from_unit':'BEFORE','to_unit':'AFTER','relation':'ellipsis','basis':'Explicit time omission; no inferred image adjacency.','assertions':[]}]}
    json_write(root/'plan.json',plan)
    return plan


class RealizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='cpb-realization-current-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project';self.plan=make_fixture(self.root)

    def save(self): json_write(self.root/'plan.json',self.plan)
    def run_plan(self): self.save();return wr.compile_plan(self.root,'plan.json')
    def refresh(self,identifier):
        row=next(s for s in self.plan['sources'] if s['source_id']==identifier)
        row['sha256']=hashlib.sha256((self.root/row['path']).read_bytes()).hexdigest()
    def change_json(self,filename,callback,source):
        value=json.loads((self.root/filename).read_text(encoding="utf-8"));callback(value);json_write(self.root/filename,value);self.refresh(source)
    def set_events(self,events):
        (self.root/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events), encoding='utf-8');self.refresh('EVENTS')
    def test_current_example_compiles(self): self.assertTrue(self.run_plan()['ok'])
    def test_deterministic_build(self): self.assertEqual(self.run_plan(),self.run_plan())
    def test_no_source_mutation(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir()};wr.compile_plan(self.root,'plan.json')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})
    def test_presentation_order_not_sorted_into_story_order(self):
        self.assertEqual(self.run_plan()['presentation_order'],['AFTER','BEFORE','RETURN'])
    def test_flashback_does_not_inherit_render_order_state(self):
        units=self.run_plan()['units'];self.assertEqual(units[0]['views'][0]['state_fields'][1]['value'],'bright')
        self.assertEqual(units[1]['views'][0]['state_fields'][1]['value'],'dark')
    def test_snapshots_validate_in_existing_state_protocol(self):
        for u in self.run_plan()['units']:
            for s in u['boundaries'].values(): self.assertTrue(validate_artifact(s)['ok'])
    def test_no_characters_required(self):
        self.assertEqual(self.run_plan()['units'][0]['boundaries']['opening']['entities']['characters'],{})
    def test_medium_is_not_restricted_to_film(self):
        for medium in ['prose','single-image','audio','tabletop','abstract installation']:
            self.plan['units'][0]['medium']=medium;self.assertEqual(self.run_plan()['units'][0]['medium'],medium)
    def test_empty_scaffold_is_not_claimed_completed(self):
        self.plan=json.loads((ROOT/'templates/realization/world-realization-plan.json').read_text(encoding='utf-8'))
        result=self.run_plan();self.assertTrue(result['ok']);self.assertEqual(result['units'],[])
        self.assertTrue(any('Empty plan' in x for x in result['review_notes']))
    def test_duplicate_unit_id(self):
        self.plan['units'][1]['unit_id']='AFTER'
        with self.assertRaises(ValueError): self.run_plan()
    def test_duplicate_source_id(self):
        self.plan['sources'].append(dict(self.plan['sources'][0]))
        with self.assertRaises(ValueError): self.run_plan()
    def test_missing_timeline(self):
        self.plan['units'][0]['timeline_id']='missing'
        with self.assertRaises(ValueError): self.run_plan()
    def test_boolean_order_is_not_an_integer_target(self):
        self.plan['units'][0]['opening']['story_order']=True
        with self.assertRaises(ValueError): self.run_plan()
    def test_unrecorded_base_basis_blocks(self):
        self.plan['timelines'][0]['base_provenance']=[]
        with self.assertRaisesRegex(ValueError,'no recorded basis'):self.run_plan()
    def test_basis_for_missing_pointer_blocks(self):
        self.plan['timelines'][0]['base_provenance'][0]['pointer']='/props/missing'
        with self.assertRaises(ValueError):self.run_plan()
    def test_event_evidence_locators_retained(self):
        self.assertEqual(self.run_plan()['units'][0]['event_basis'][0]['evidence'],evidence())
    def test_empty_approved_event_evidence_blocks(self):
        e=event();e['evidence']=[];self.set_events([e])
        with self.assertRaises(ValueError):self.run_plan()
    def test_unknown_evidence_source_blocks(self):
        e=event();e['evidence'][0]['source_id']='missing';self.set_events([e])
        with self.assertRaises(ValueError):self.run_plan()
    def test_inference_is_not_automatically_approved(self):
        e=event();e['canon_status']='proposed';e['evidence'][0]['basis']='inference';self.set_events([e])
        self.assertEqual(self.run_plan()['units'][0]['views'][0]['state_fields'][1]['value'],'dark')
    def test_future_event_does_not_change_earlier_snapshot(self):
        self.set_events([event(),event('EV_FUTURE',50,'destroyed')])
        self.assertEqual(self.run_plan()['units'][0]['views'][0]['state_fields'][1]['value'],'bright')
    def test_scene_local_change_uses_actual_target(self):
        e=event();e['changes'][0]['persistence']='scene-local';e['scene_context_id']='OTHER';self.set_events([e])
        self.assertEqual(self.run_plan()['units'][0]['views'][0]['state_fields'][1]['value'],'dark')
    def test_process_uses_authored_milestones_not_interpolation(self):
        e=event();e['changes'][0].update(persistence='progressive',process_id='PROC',value=0)
        process={'artifact_type':'state-process','process_id':'PROC','timeline_id':'main','entity_type':'prop','entity_id':'LAMP',
          'path':'/appearance/signal','process_type':'authored-strength','started_order':10,'effective_until_order':None,
          'milestones':[{'offset':0,'state':0},{'offset':5,'state':10}],
          'interruption_policy':'supersedable-by-event','canon_status':'approved','evidence':evidence(),'notes':[]}
        self.set_events([e]);json_write(self.root/'processes.json',[process]);self.refresh('PROCESSES')
        result=self.run_plan();self.assertEqual(result['units'][0]['boundaries']['closing']['entities']['props']['LAMP']['appearance']['signal'],0)
        self.assertEqual(result['units'][0]['process_basis'][0]['process_id'],'PROC')
    def test_atomic_failed_precondition_does_not_write_base(self):
        e=event();e['preconditions']=[{'entity_type':'prop','entity_id':'LAMP','path':'/appearance/shell','operator':'equals','value':'wrong'}]
        self.set_events([e]);before=(self.root/'base.json').read_bytes()
        with self.assertRaises(ValueError):self.run_plan()
        self.assertEqual(before,(self.root/'base.json').read_bytes())
    def test_world_bucket_is_aggregate_not_fake_entity_map(self):
        e=event();e['targets']=['WORLD'];e['changes'][0].update(entity_type='world',entity_id='WORLD',path='/public_rule',value='updated')
        self.set_events([e]);result=self.run_plan()
        self.assertEqual(result['units'][0]['boundaries']['opening']['entities']['world']['public_rule'],'updated')
    def test_consumer_omits_unselected_secret_and_raw_sources(self):
        packet=self.run_plan()['units'][0]['views'][0];body=json.dumps(packet)
        for marker in ['SECRET_MARKER_NOT_FOR_CONSUMER','author_secret','world.md','portrayal_aim','event_basis']:
            self.assertNotIn(marker,body)
    def test_container_export_is_not_allowed(self):
        self.plan['units'][0]['views'][0]['state_fields'][0]['pointer']='/props/LAMP/appearance'
        with self.assertRaisesRegex(ValueError,'scalar leaves'):self.run_plan()
    def test_missing_is_not_null_or_absent_anatomy(self):
        view=self.plan['units'][0]['views'][0];view['state_fields']=[{'at':'opening','pointer':'/props/LAMP/owner'}, {'at':'opening','pointer':'/props/LAMP/unknown'}]
        a,b=self.run_plan()['units'][0]['views'][0]['state_fields']
        self.assertEqual((a['present'],a['value']),(True,None));self.assertFalse(b['present']);self.assertNotIn('value',b)
    def test_explicit_world_leaf_view(self):
        self.plan['units'][0]['views'][0]['state_fields']=[{'at':'opening','pointer':'/world/public_rule'}]
        self.assertEqual(self.run_plan()['units'][0]['views'][0]['state_fields'][0]['value'],'unanswered')
    def test_unrequested_closing_not_exported(self):
        self.assertTrue(all(x['at']=='opening' for x in self.run_plan()['units'][0]['views'][0]['state_fields']))
    def test_declared_proposed_intent_is_a_note_not_adoption(self):
        p=self.root/'intent.md';p.write_text(p.read_text(encoding='utf-8').replace('**status**: adopted','**status**: proposed'),encoding='utf-8');self.refresh('INTENT')
        result=self.run_plan();self.assertTrue(any('not recorded as adopted' in x for x in result['review_notes']))
        self.assertEqual(result['units'][0]['intent_refs'][0]['declared_status'],'proposed')
    def test_dangling_intent_blocks(self):
        self.plan['units'][0]['intent_refs'][0]['intent_id']='i-missing'
        with self.assertRaises(ValueError):self.run_plan()
    def test_query_same_relevant_state_same_key(self):
        units=self.run_plan()['units'];self.assertEqual(units[0]['reference_queries'][0]['state_key'],units[1]['reference_queries'][0]['state_key'])
    def test_query_changed_relevant_facet_changes_key(self):
        units=self.run_plan()['units'];self.assertNotEqual(units[0]['reference_queries'][1]['state_key'],units[1]['reference_queries'][1]['state_key'])
    def test_query_role_changes_key(self):
        before=self.run_plan()['units'][0]['reference_queries'][0]['state_key'];self.plan['units'][0]['reference_queries'][0]['role']='other-role'
        self.assertNotEqual(before,self.run_plan()['units'][0]['reference_queries'][0]['state_key'])
    def test_query_other_entity_facet_blocks(self):
        self.plan['units'][0]['reference_queries'][0]['facets']=['/environments/ROOM/light']
        with self.assertRaises(ValueError):self.run_plan()
    def test_query_missing_facet_blocks(self):
        self.plan['units'][0]['reference_queries'][0]['facets']=['/props/LAMP/unknown']
        with self.assertRaises(ValueError):self.run_plan()
    def test_query_scalar_leaf_required(self):
        self.plan['units'][0]['reference_queries'][0]['facets']=['/props/LAMP/appearance']
        with self.assertRaises(ValueError):self.run_plan()
    def test_no_implicit_adjacency_comparison(self):
        self.plan['links']=[];result=self.run_plan();self.assertEqual(result['continuity_checks'],[])
    def test_declared_boundary_mismatch_is_diagnostic(self):
        self.plan['links'][0]['to_unit']='BEFORE';self.plan['links'][0]['relation']='authored-comparison'
        result=self.run_plan();self.assertFalse(result['ok']);self.assertFalse(result['continuity_checks'][0]['passed'])
    def test_missing_on_both_sides_is_not_proven_equal(self):
        self.plan['links'][0]['assertions']=[{'from_pointer':'/props/LAMP/unknown','to_pointer':'/props/LAMP/unknown','comparison':'equal'}]
        self.assertFalse(self.run_plan()['ok'])
    def test_different_assertion(self):
        self.plan['links'][0].update(to_unit='BEFORE',relation='revisit');self.plan['links'][0]['assertions'][0]['comparison']='different'
        self.assertTrue(self.run_plan()['ok'])
    def test_failed_continuity_does_not_publish(self):
        self.plan['links'][0]['assertions'][0]['comparison']='different';result=self.run_plan()
        with self.assertRaises(ValueError):wr.publish(result,Path(self.tmp.name)/'out')
        self.assertFalse((Path(self.tmp.name)/'out').exists())
    def test_self_contained_bundle_rebuild_verifies(self):
        result=self.run_plan();out=Path(self.tmp.name)/'out';wr.publish(result,out)
        self.assertTrue(wr.verify_bundle(self.root,'plan.json',out)['ok'])
    def test_tampered_consumer_fails_verification(self):
        result=self.run_plan();out=Path(self.tmp.name)/'out';wr.publish(result,out)
        p=out/'consumer/AFTER--WRITER.json';p.write_text(p.read_text(encoding='utf-8').replace('ribbed','smooth'),encoding='utf-8')
        self.assertFalse(wr.verify_bundle(self.root,'plan.json',out)['ok'])
    def test_extra_file_in_bundle_is_reported(self):
        result=self.run_plan();out=Path(self.tmp.name)/'out';wr.publish(result,out);(out/'consumer/leak.txt').write_text('secret',encoding='utf-8')
        self.assertIn('consumer/leak.txt',wr.verify_bundle(self.root,'plan.json',out)['mismatched_files'])
    def test_existing_output_is_not_overwritten(self):
        out=Path(self.tmp.name)/'out';out.mkdir()
        with self.assertRaises(ValueError):wr.publish(self.run_plan(),out)
    def test_stale_source_blocks_rebuild(self):
        (self.root/'world.md').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):self.run_plan()
    def test_impact_reaches_dependent_units(self):
        (self.root/'world.md').write_text('changed',encoding='utf-8');self.save();result=wr.impact(self.root,'plan.json')
        self.assertFalse(result['ok']);self.assertEqual(len(result['affected_units']),3)
    def test_unused_source_change_has_no_invented_unit_dependency(self):
        (self.root/'unused.txt').write_text('a',encoding='utf-8');self.plan['sources'].append({'source_id':'UNUSED','path':'unused.txt','sha256':hashlib.sha256(b'a').hexdigest()})
        self.save();(self.root/'unused.txt').write_text('b',encoding='utf-8');self.assertEqual(wr.impact(self.root,'plan.json')['affected_units'],[])
    def test_missing_source_impact_still_reports(self):
        (self.root/'world.md').unlink();self.save();self.assertFalse(wr.impact(self.root,'plan.json')['ok'])
    def test_traversal_blocks(self):
        self.plan['sources'][0]['path']='../base.json'
        with self.assertRaises(ValueError):self.run_plan()
    def test_source_symlink_blocks(self):
        p=self.root/'link.json';p.symlink_to(self.root/'base.json');self.plan['sources'][0]['path']='link.json'
        with self.assertRaises(ValueError):self.run_plan()
    def test_remote_path_blocks_without_network(self):
        self.plan['sources'][0]['path']='https://example.invalid/source'
        with self.assertRaises(ValueError):self.run_plan()
    def test_explicit_read_budget(self):
        self.save()
        with self.assertRaises(ValueError):wr.read_bytes(self.root/'plan.json',maximum=1)
        self.assertEqual(wr.read_bytes(self.root/'plan.json'),(self.root/'plan.json').read_bytes())
    def test_compilation_uses_declared_complete_scope(self):
        self.run_plan()
        self.assertEqual(wr.read_bytes(self.root/'world.md'),(self.root/'world.md').read_bytes())
    def test_pointer_escape_exactness(self):
        self.assertEqual(wr.at_pointer({'a/b':{'~x':2}},'/a~1b/~0x'),(True,2))
        with self.assertRaises(ValueError):wr.tokens('/x~2')
    def test_duplicate_json_keys_block(self):
        (self.root/'plan.json').write_text('{"plan_id":"A","plan_id":"B"}',encoding="utf-8")
        with self.assertRaises(ValueError):wr.compile_plan(self.root,'plan.json')
    def test_nonfinite_json_blocks(self):
        p=self.root/'base.json';p.write_text('{"x":NaN}', encoding='utf-8');self.refresh('BASE')
        with self.assertRaises(ValueError):self.run_plan()
    def test_cli_inspect_returns_json(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=wr.main(['inspect','--root',str(self.root),'--plan','plan.json'])
        self.assertEqual(code,0);self.assertTrue(json.loads(output.getvalue())['ok'])
    def test_cli_build_and_verify(self):
        out=Path(self.tmp.name)/'out'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wr.main(['build','--root',str(self.root),'--plan','plan.json','--out',str(out)]),0)
            self.assertEqual(wr.main(['verify','--root',str(self.root),'--plan','plan.json','--bundle',str(out)]),0)
    def test_cli_errors_return_json_without_source_writes(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=wr.main(['inspect','--root',str(self.root),'--plan','missing.json'])
        self.assertEqual(code,1);self.assertFalse(json.loads(output.getvalue())['ok'])


class PrincipleTests(unittest.TestCase):
    def test_full_records_validate(self):self.assertEqual(pp.validate(pp.load()),[])
    def test_search_hits_report_tokens_not_quality(self):
        rows=pp.search(pp.load(),'steady contrast');self.assertTrue(rows);self.assertIn('matched_terms',rows[0]);self.assertNotIn('score',rows[0])
    def test_unknown_search_does_not_invent_record(self):self.assertEqual(pp.search(pp.load(),'xyzzy-quux'),[])
    def test_stable_and_switch_are_distinct_records(self):
        records={r['id']:r for r in pp.load()['records']}
        self.assertNotEqual(records['persistence']['recognition_logic'],records['designed-contrast']['recognition_logic'])
    def test_record_has_bounded_adoption_and_counterexample(self):
        for r in pp.load()['records']:
            self.assertIn('proposal',r['adoption_instruction']);self.assertTrue(r['counterexample']);self.assertIn('CPB-authored',r['source_basis'])
    def test_duplicate_record_id_reports(self):
        data=pp.load();data['records'].append(copy.deepcopy(data['records'][0]));self.assertTrue(pp.validate(data))
    def test_empty_meaning_field_reports(self):
        data=pp.load();data['records'][0]['recognition_logic']='';self.assertTrue(pp.validate(data))
    def test_inspect_unknown_id_errors(self):
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(pp.main(['inspect','missing']),1)
    def test_inspect_returns_complete_record(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(pp.main(['inspect','persistence']),0)
        self.assertEqual(set(json.loads(output.getvalue())['record']),set(pp.TEXT_FIELDS+pp.LIST_FIELDS))


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
