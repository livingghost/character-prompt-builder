"""Synthetic request construction, source tracing and exact tuple tests."""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path
import execution_contract as c
import request_contract as rc
from input_evidence import InputEvidence
import model_rendition as mr
import request_validation as rv

class RequestContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.target={'service':'synthetic','model_identifier':'synthetic:model','operation':'generate'}
        self.execution={k:'a'*64 for k in ('service_execution_sha256','offering_contract_sha256','transport_sha256')}
        self.layout={'model':['model'],'operation':['operation'],'primary_text':['prompt'],'negative_text':['negative'],
            'output_count':['count'],'fixed_output_count':None,'seed':['seed'],'media':[{'index':0,'field':['images',0]}],
            'management':[['task_id']],'content':[{'id':'prompt','field':['prompt']},{'id':'negative','field':['negative']}],
            'fields':[{'id':'prompt','field':['prompt'],'kind':'content'},{'id':'seed','field':['seed'],'kind':'parameter'},
                      {'id':'count','field':['count'],'kind':'parameter'},{'id':'media:1','field':['images',0],'kind':'media'}]}
        self.request={'model':'synthetic:model','operation':'generate','prompt':'Authored text','negative':'Authored exclusion',
            'count':1,'seed':3,'images':['placeholder'],'task_id':'ephemeral'}
        self.media=[{'path':'/synthetic/input.png','sha256':'b'*64,'size':30,'media_type':'image/png','role':'reference',
            'dimensions':{'width':2,'height':2},'binding_ids':['reference:1']}]
    def tearDown(self):self.temp.cleanup()
    def seal(self):return rc.seal(self.request,self.layout,self.media,self.target,self.execution,[],[],{'output_kind':'image'})
    def save(self,name,value):
        raw=c.encoded(value);(self.root/name).write_bytes(raw);return {'path':name,'sha256':c.digest(raw)}
    def test_01_seal_revalidates(self):rc.validate_seal(self.seal())
    def test_02_task_identifier_does_not_change_commitment(self):
        first=self.seal();self.request['task_id']='different';self.assertEqual(first['request_sha256'],self.seal()['request_sha256'])
    def test_03_prompt_changes_request_not_fixed_profile(self):
        first=self.seal();self.request['prompt']='Other authored text';second=self.seal()
        self.assertNotEqual(first['request_sha256'],second['request_sha256']);self.assertEqual(first['profile'],second['profile'])
    def test_04_seed_changes_profile(self):
        first=self.seal();self.request['seed']=4;self.assertNotEqual(first['profile'],self.seal()['profile'])
    def test_05_count_changes_profile(self):
        first=self.seal();self.request['count']=2;self.assertNotEqual(first['profile'],self.seal()['profile'])
    def test_06_media_content_changes_commitment(self):
        first=self.seal();self.media[0]['sha256']='c'*64;self.media[0]['size']=32
        self.assertNotEqual(first['request_sha256'],self.seal()['request_sha256']);self.assertEqual(first['profile'],self.seal()['profile'])
    def test_07_media_dimensions_change_profile(self):
        first=self.seal();self.media[0]['dimensions']['width']=3;self.assertNotEqual(first['profile'],self.seal()['profile'])
    def test_08_materialization_changes_only_selected_media(self):
        sealed=self.seal();wire=rc.materialize(sealed,{0:'provider-input'});expected=dict(self.request,images=['provider-input'])
        self.assertEqual(wire,expected);rc.validate_wire(sealed,wire,{0:'provider-input'})
    def test_09_wire_prompt_mutation_refused(self):
        sealed=self.seal();wire=rc.materialize(sealed,{0:'provider-input'});wire['prompt']='mutated'
        with self.assertRaises(ValueError):rc.validate_wire(sealed,wire,{0:'provider-input'})
    def test_10_all_media_need_upload_results(self):
        with self.assertRaises(ValueError):rc.materialize(self.seal(),{})
    def test_11_missing_native_media_refused(self):
        self.layout['media']=[]
        with self.assertRaises(ValueError):self.seal()
    def test_12_media_cannot_be_management(self):
        self.layout['management'].append(['images'])
        with self.assertRaises(ValueError):self.seal()
    def test_13_model_cannot_be_content(self):
        self.layout['content'].append({'id':'other','field':['model']})
        with self.assertRaises(ValueError):self.seal()
    def test_14_changed_request_fails_its_seal(self):
        sealed=self.seal();sealed['request']['count']=2
        with self.assertRaises(ValueError):rc.validate_seal(sealed)
    def test_15_explicit_target_must_match_request(self):
        self.request['model']='other'
        with self.assertRaises(ValueError):self.seal()
    def test_15b_address_can_carry_the_model_and_operation(self):
        # A service that takes both in its address has no request field for them.
        del self.request['model'];del self.request['operation']
        self.layout['model']=None;self.layout['operation']=None
        sealed=self.seal();self.assertEqual(sealed['sealed']['target'],self.target)
        import request_renderer
        self.assertEqual(request_renderer.envelope_fields(sealed),[['task_id']])
    def test_16_count_is_integer_not_boolean(self):
        self.request['count']=True
        with self.assertRaises(ValueError):self.seal()
    def test_17_scalar_writer_records_range(self):
        writer=rc.RequestWriter();writer.write(['prompt'],'text',source_kind='authored',source_refs=[],transform_id='authored')
        self.assertEqual(writer.trace[0]['target_range'],{'start':0,'end':4})
    def test_18_conflicting_field_writers_refused(self):
        writer=rc.RequestWriter();writer.write(['request'],{'x':1},source_kind='authored',source_refs=[],transform_id='authored')
        with self.assertRaises(ValueError):writer.write(['request','x'],2,source_kind='model-setting',source_refs=[],transform_id='setting')
    def test_19_declared_defaults_keep_selected_values(self):
        writer=rc.RequestWriter();writer.write(['seed'],7,source_kind='authored',source_refs=[],transform_id='setting')
        writer.defaults({'seed':8,'count':1},[]);self.assertEqual(writer.request,{'seed':7,'count':1})
    def test_20_nested_writer_uses_structural_path(self):
        writer=rc.RequestWriter();writer.write(['control','value'],3,source_kind='model-setting',source_refs=[],transform_id='setting')
        self.assertEqual(writer.request,{'control':{'value':3}})
    def test_21_unknown_service_field_remains_execution_dependency(self):
        a=rc.execution_projection({'notes':'instruction'},'service');b=rc.execution_projection({'notes':'changed'},'service')
        self.assertNotEqual(a,b)
    def test_22_declared_service_label_is_display_only(self):
        self.assertEqual(rc.execution_projection({'label':'one','endpoint':'fixed'},'service'),rc.execution_projection({'label':'two','endpoint':'fixed'},'service'))
    def test_23_endpoint_is_execution_dependency(self):
        self.assertNotEqual(rc.execution_projection({'endpoint':'one'},'service'),rc.execution_projection({'endpoint':'two'},'service'))
    def test_24_pricing_has_separate_dependency(self):
        self.assertEqual(rc.execution_projection({'pricing':1},'service'),rc.execution_projection({'pricing':2},'service'))
    def test_25_execution_prose_remains_dependency(self):
        self.assertNotEqual(rc.execution_projection({'prompt_contract':{'notes':'one'}},'model'),rc.execution_projection({'prompt_contract':{'notes':'two'}},'model'))
    def test_26_subject_context_binds_request_not_api_profile(self):
        first=self.seal();second=rc.seal(self.request,self.layout,self.media,self.target,self.execution,[],[],{'output_kind':'image','subjects':{'a':'character-a'}})
        self.assertNotEqual(first['request_sha256'],second['request_sha256']);self.assertEqual(first['profile'],second['profile'])
    def test_27_fixed_single_output_has_no_invented_wire_field(self):
        self.layout['output_count']=None;self.layout['fixed_output_count']=1;self.layout['fields']=[x for x in self.layout['fields'] if x['id']!='count'];self.request.pop('count')
        sealed=self.seal();self.assertEqual(sealed['output_count'],1);self.assertNotIn('count',sealed['request'])
    def test_28_count_has_only_one_source(self):
        self.layout['fixed_output_count']=1
        with self.assertRaises(ValueError):self.seal()
    def test_29_two_metadata_paths_do_not_change_media_commitment(self):
        first=self.seal();self.media[0]['path']='/different/input.png';self.assertEqual(first['request_sha256'],self.seal()['request_sha256'])
    def test_30_bytes_are_rechecked(self):
        path=self.root/'input.bin';path.write_bytes(b'abc');item=rc.media_metadata(path,role='source');sealed=self.seal();sealed['media']=[item]
        rc.verify_media_bytes(sealed);path.write_bytes(b'abd')
        with self.assertRaises(ValueError):rc.verify_media_bytes(sealed)
    def test_31_evidence_captures_actual_bytes(self):
        ref=self.save('source.json',{'value':1});reader=InputEvidence(self.root);self.assertEqual(reader.json(ref),{'value':1});self.assertEqual(reader.snapshots['source.json']['sha256'],ref['sha256'])
    def test_32_historical_evidence_needs_no_current_file(self):
        ref=self.save('source.json',{'value':1});reader=InputEvidence(self.root);reader.read(ref);(self.root/'source.json').unlink()
        self.assertEqual(InputEvidence(None,snapshots=reader.snapshots,live=False).json(ref),{'value':1})
    def test_33_current_evidence_detects_source_changes(self):
        ref=self.save('source.json',{'value':1});reader=InputEvidence(self.root);reader.read(ref);self.save('source.json',{'value':2})
        with self.assertRaises(ValueError):reader.read(ref)
    def test_34_named_root_is_explicit(self):
        ref=self.save('source.json',{'value':1});ref['path']='@pack/synthetic/source.json'
        reader=InputEvidence(None,named_roots={'@pack/synthetic':self.root});self.assertEqual(reader.json(ref),{'value':1})
        with self.assertRaises(ValueError):InputEvidence(None).read(ref)
    def test_35_children_keep_their_pack_root(self):
        ref=self.save('source.json',{'value':1});reader=InputEvidence(None,named_roots={'@pack/synthetic':self.root})
        self.assertEqual(reader.at({'path':'@pack/synthetic/contract.json'}).json(ref),{'value':1})
    def test_36_path_traversal_refused(self):
        with self.assertRaises(ValueError):InputEvidence(self.root).resolve('../outside')
    def test_37_no_historical_snapshot_is_invented(self):
        with self.assertRaises(ValueError):InputEvidence(None,live=False).read({'path':'absent','sha256':'a'*64})
    def test_38_snapshot_hash_tampering_refused(self):
        ref=self.save('source.json',{'value':1});reader=InputEvidence(self.root);reader.read(ref);reader.snapshots['source.json']['sha256']='0'*64
        with self.assertRaises(ValueError):InputEvidence(None,snapshots=reader.snapshots,live=False)
    def test_39_profile_keeps_role(self):
        first=self.seal();self.media[0]['role']='source';self.assertNotEqual(first['profile'],self.seal()['profile'])
    def test_40_duplicate_semantic_field_ids_refused(self):
        self.layout['fields'].append(copy.deepcopy(self.layout['fields'][0]))
        with self.assertRaises(ValueError):self.seal()

    def test_nested_defaults_fill_only_absent_siblings(self):
        writer = rc.RequestWriter()
        writer.write(['settings'], {'quality': 'medium'}, source_kind='authored',
                     source_refs=[], transform_id='selected')
        writer.defaults({'settings': {'quality': 'high', 'expansion': 'disabled'}}, [])
        self.assertEqual(writer.request['settings'], {'quality': 'medium', 'expansion': 'disabled'})
        origins = {tuple(row['target_field']): row['source_kind'] for row in writer.trace}
        self.assertEqual(origins, {('settings', 'quality'): 'authored',
                                  ('settings', 'expansion'): 'model-setting'})

    def test_defaults_preserve_explicit_scalar_and_array(self):
        for value in (None, False, 0, 'selected', ['selected']):
            with self.subTest(value=value):
                writer = rc.RequestWriter()
                writer.write(['settings'], value, source_kind='authored',
                             source_refs=[], transform_id='selected')
                writer.defaults({'settings': {'other': 'default'}}, [])
                self.assertEqual(writer.request, {'settings': value})

    def test_empty_object_is_preserved_or_extended_by_defaults(self):
        writer = rc.RequestWriter()
        writer.write(['settings'], {}, source_kind='authored',
                     source_refs=[], transform_id='selected')
        writer.defaults({'empty': {}}, [])
        self.assertEqual(writer.request, {'settings': {}, 'empty': {}})
        writer.defaults({'settings': {'flag': False}}, [])
        self.assertEqual(writer.request, {'settings': {'flag': False}, 'empty': {}})
        self.assertEqual([x for x in writer.trace if x['target_field'] == ['settings']], [])

    def test_conflicting_object_write_is_atomic(self):
        writer = rc.RequestWriter()
        writer.write(['settings', 'z'], 1, source_kind='authored',
                     source_refs=[], transform_id='selected')
        before = copy.deepcopy((writer.request, writer.trace, writer.written))
        with self.assertRaises(ValueError):
            writer.write(['settings'], {'a': 2, 'z': 3}, source_kind='model-setting',
                         source_refs=[], transform_id='other')
        self.assertEqual((writer.request, writer.trace, writer.written), before)

    def test_container_type_failure_is_atomic(self):
        writer = rc.RequestWriter()
        writer.write(['settings'], [], source_kind='authored',
                     source_refs=[], transform_id='selected')
        before = copy.deepcopy((writer.request, writer.trace, writer.written))
        with self.assertRaises(ValueError):
            writer.write(['settings', 'flag'], True, source_kind='model-setting',
                         source_refs=[], transform_id='other')
        self.assertEqual((writer.request, writer.trace, writer.written), before)

    def test_same_write_distinguishes_boolean_and_integer(self):
        writer = rc.RequestWriter()
        writer.write(['flag'], True, source_kind='authored',
                     source_refs=[], transform_id='selected')
        with self.assertRaises(ValueError):
            writer.write(['flag'], 1, source_kind='model-setting',
                         source_refs=[], transform_id='other', same=True)

class RenditionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.reader=InputEvidence(self.root)
        self.target={'service':'synthetic','model_identifier':'synthetic:model','operation':'generate'}
        self.basis=self.save('basis.txt','Synthetic explicit conversion contract.');self.basis['locator']='complete declaration'
        self.binding={'reference_number':1,'attachment_number':1,'region_pixels':None,'role':'identity',
            'controls':['appearance'],'must_not_control':['pose']}
        self.kw={'segments':None,'authored_source':{'path':'authored.txt','sha256':'a'*64},'bindings':[],
            'reference_policy':None,'production_consumer':None,'context_policy':None,'policy_source':None,
            'reader':self.reader,'target':self.target,'dialect':'synthetic-dialect'}
    def tearDown(self):self.temp.cleanup()
    def save(self,name,value):
        raw=value.encode() if isinstance(value,str) else c.encoded(value);(self.root/name).write_bytes(raw)
        return {'path':name,'sha256':c.digest(raw)}
    def policy(self,mode,fields=None):
        contract={'artifact_type':'reference-render-contract','target':self.target,'dialects':['synthetic-dialect'],
            'mode':mode,'renderer':'reference-delivery' if mode=='prompt-prefix' else None,'fields':fields or [],'basis':self.basis}
        return {'mode':mode,'contract':self.save('reference.json',contract)}
    def test_01_authored_text_stays_exact(self):
        text='Production context: { "authored": true }';self.assertEqual(mr.compose(text,**self.kw)['text'],text)
    def test_02_authored_consumer_keeps_direction_out_of_prompt(self):
        self.kw['production_consumer']={'transport':'authored-rendition','direction':{'directives':['explicit']}}
        self.assertEqual(mr.compose('rendition',**self.kw)['text'],'rendition')
    def test_03_bounded_without_permission_refused(self):
        self.kw['production_consumer']={'transport':'bounded-context'}
        with self.assertRaises(ValueError):mr.compose('rendition',**self.kw)
    def test_04_bounded_records_origin(self):
        self.kw.update(production_consumer={'transport':'bounded-context','direction':{},'criteria':[],'world_views':[],'moment_views':[]},context_policy='prompt-prefix',policy_source=self.basis)
        result=mr.compose('rendition',**self.kw);self.assertEqual(result['trace'][0]['source_kind'],'production-context');self.assertTrue(result['text'].endswith('rendition'))
    def test_05_reference_without_policy_refused(self):
        self.kw['bindings']=[self.binding]
        with self.assertRaises(ValueError):mr.compose('rendition',**self.kw)
    def test_06_authored_reference_policy_adds_no_text(self):
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('authored-rendition'))
        result=mr.compose('rendition',**self.kw);self.assertEqual(result['text'],'rendition');self.assertEqual(result['review_requirements'][0]['binding_ids'],['reference:1'])
    def test_07_prefix_has_exact_written_range(self):
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('prompt-prefix'))
        result=mr.compose('rendition',**self.kw);last=result['trace'][-1]['target_range'];self.assertEqual(result['text'][last['start']:last['end']],'rendition')
    def test_08_wrong_declared_dialect_refused(self):
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('prompt-prefix'),dialect='other')
        with self.assertRaises(ValueError):mr.compose('rendition',**self.kw)
    def test_09_native_controls_preserve_all_authority(self):
        fields=[{'binding_field':key,'request_field':'control.'+key,'container':'ordered-array'} for key in ('attachment_number','role','controls','must_not_control')]
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('native-fields',fields))
        result=mr.compose('rendition',**self.kw);self.assertEqual(result['text'],'rendition');self.assertEqual(len(result['native_reference_controls']),4)
    def test_10_native_control_cannot_drop_exclusions(self):
        fields=[{'binding_field':key,'request_field':'control.'+key,'container':'ordered-array'} for key in ('attachment_number','role','controls')]
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('native-fields',fields))
        with self.assertRaises(ValueError):mr.compose('rendition',**self.kw)
    def test_11_native_control_cannot_drop_region(self):
        self.binding['region_pixels']={'x':0,'y':0,'width':2,'height':2}
        fields=[{'binding_field':key,'request_field':'control.'+key,'container':'ordered-array'} for key in ('attachment_number','role','controls','must_not_control')]
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('native-fields',fields))
        with self.assertRaises(ValueError):mr.compose('rendition',**self.kw)
    def test_12_recommendation_segments_keep_their_origin(self):
        self.kw['segments']=[{'source_kind':'model-setting','start':0,'end':3,'text':'A, '},{'source_kind':'authored','start':3,'end':4,'text':'B'}]
        result=mr.compose('A, B',**self.kw);self.assertEqual([x['source_kind'] for x in result['trace']],['model-setting','authored'])
    def test_13_segment_gap_refused(self):
        self.kw['segments']=[{'source_kind':'authored','start':1,'end':4,'text':'ext'}]
        with self.assertRaises(ValueError):mr.compose('text',**self.kw)
    def test_14_segment_wrong_bytes_refused(self):
        self.kw['segments']=[{'source_kind':'authored','start':0,'end':4,'text':'fake'}]
        with self.assertRaises(ValueError):mr.compose('text',**self.kw)
    def test_15_native_destination_overlap_refused(self):
        fields=[{'binding_field':key,'request_field':'control','container':'ordered-array'} for key in ('attachment_number','role','controls','must_not_control')]
        self.kw.update(bindings=[self.binding],reference_policy=self.policy('native-fields',fields))
        with self.assertRaises(ValueError):mr.compose('text',**self.kw)
    def test_16_reference_binding_position_is_structural(self):
        self.binding['reference_number']=2;self.kw['bindings']=[self.binding]
        with self.assertRaises(ValueError):mr.compose('text',**self.kw)
    def test_17_unrelated_prose_is_not_classified(self):
        text='The document contains 2boys, facing, general, 8k and {JSON}.'
        self.assertEqual(mr.compose(text,**self.kw)['text'],text)
    def test_18_no_automatic_assessment_is_added(self):
        result=mr.compose('text',**self.kw);self.assertNotIn('assessment',result);self.assertEqual(result['review_requirements'],[])

if __name__=='__main__':unittest.main()
