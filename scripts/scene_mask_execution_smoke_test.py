#!/usr/bin/env python3
"""Mask-to-provider-wire and immutable recovery tests. Synthetic only."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import execution_contract as c
import production_compiler as compiler
import production_case_fixtures as base
import production_workflow as w
import scene_mask_fixtures as fixture
import scene_mask_planner as masks
import transport_synthetic as transport


class ProductionMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.case=fixture.production(Path(self.temp.name)/'studio',Path(self.temp.name)/'runtime')
        self.root=self.case['root']
    def write(self,path,value):
        (self.root/path).write_bytes(c.encoded(value))
    def check(self):
        return compiler.check_task(self.root,'task.json')
    def prepare(self):
        result=w.prepare(self.root,'task.json');run=result['run']
        base.fill_decisions(self.root,run,'decisions.json')
        return run
    def directory(self,run):return self.root/'production/runs'/run
    def execute(self,run):return w.execute(self.root,run,decisions_file='decisions.json')
    def test_dispatch_sends_three_separate_byte_bound_inputs_and_retains_each(self):
        self.assertTrue(self.check()['ok'])
        run=self.prepare()
        contract=c.load(self.directory(run)/'request-contract.json')
        self.assertEqual([r['role'] for r in contract['media']],['composition','mask image','reference images'])
        expected=[c.digest(c.read(Path(r['path']))) for r in contract['media']]
        self.assertEqual(expected,[r['sha256'] for r in contract['media']])
        with patch.object(transport,'send',wraps=transport.send) as sender, patch.object(transport,'upload_bytes',wraps=transport.upload_bytes) as upload:
            self.execute(run)
        self.assertEqual(upload.call_count,3);self.assertEqual(sender.call_count,1)
        self.assertEqual([c.digest(row.args[0]) for row in upload.call_args_list],expected)
        wire=sender.call_args.args[0]
        self.assertTrue(wire['seed_image'].startswith('synthetic:'+expected[0]+':'))
        self.assertTrue(wire['mask_image'].startswith('synthetic:'+expected[1]+':'))
        self.assertTrue(wire['inputs']['references'][0].startswith('synthetic:'+expected[2]+':'))
        journals=list((self.root/'runs').glob('*/request-contract.json'));self.assertEqual(len(journals),1)
        journal=c.load(journals[0]);self.assertEqual(len(journal['media']),3)
        for row in journal['media']:
            self.assertEqual(c.digest(c.read(Path(row['path']))),row['sha256'])
        _,_,_,rows=w.load_run(self.root,run)
        candidate=next(r for r in rows if r['event']=='candidate')['data']['files'][0]
        self.assertEqual(c.digest(c.read(self.root/candidate['path'])),candidate['sha256'])
        self.assertFalse(any(r['event'] in {'selection','completion','adoption'} for r in rows))
    def test_prepare_pins_all_transitive_mask_dependencies(self):
        run=self.prepare();_,prepared,_,_=w.load_run(self.root,run)
        paths={d['path'] for d in prepared['dependencies'] if d['space']=='studio'}
        self.assertTrue({'mask-binding.json','mask-review.json','masks/a/bundle.json','masks/a/mask.png',
                         'source.png','front.png','sleeve-a.png','sleeve-b.png','protected.png','guidance.png'}<=paths)
    def test_mutated_region_prevents_send(self):
        run=self.prepare();Image.new('L',(32,32),255).save(self.root/'front.png')
        with patch.object(transport,'send',side_effect=AssertionError('must not send')) as sender:
            with self.assertRaises(ValueError):self.execute(run)
        sender.assert_not_called()
    def test_mutated_review_prevents_send(self):
        run=self.prepare();review=c.load(self.root/'mask-review.json');review['verdict']='reject';self.write('mask-review.json',review)
        with patch.object(transport,'send',side_effect=AssertionError('must not send')) as sender:
            with self.assertRaises(ValueError):self.execute(run)
        sender.assert_not_called()
    def test_mutated_mask_prevents_send(self):
        run=self.prepare();Image.new('L',(32,32),255).save(self.root/'masks/a/mask.png')
        with patch.object(transport,'send',side_effect=AssertionError('must not send')) as sender:
            with self.assertRaises(ValueError):self.execute(run)
        sender.assert_not_called()
    def test_optional_guidance_is_not_fabricated(self):
        binding=c.load(self.root/'mask-binding.json');binding['guidance']=None;self.write('mask-binding.json',binding)
        run=self.prepare();contract=c.load(self.directory(run)/'request-contract.json')
        self.assertEqual(len(contract['media']),2)
        self.assertNotIn('inputs',contract['request'])
        self.execute(run)
    def test_no_feature_cannot_silently_skip_mask(self):
        task=c.load(self.root/'task.json');task['features'].remove(masks.FEATURE);self.write('task.json',task)
        self.assertFalse(self.check()['ok'])
    def test_feature_without_binding_cannot_silently_send_unmasked(self):
        task=c.load(self.root/'task.json');del task['generation']['mask_binding'];self.write('task.json',task)
        self.assertFalse(self.check()['ok'])
    def test_absent_applied_source_is_rejected(self):
        task=c.load(self.root/'task.json');task['sources']=[r for r in task['sources'] if r['path']!='source.png'];self.write('task.json',task)
        self.assertFalse(self.check()['ok'])
    def test_changed_dimensions_are_rejected(self):
        params=c.load(self.root/'parameters.json');params['width']=64;self.write('parameters.json',params)
        self.assertFalse(self.check()['ok'])
    def test_no_native_mask_field_is_rejected(self):
        import pack_manager
        from catalog_retrieval import runtime
        models=c.load(self.case['pack']/'records/models.json');del models['records'][0]['offerings'][0]['request_keys']['mask image']
        base.write(self.case['pack']/'records/models.json',models);pack_manager.write_lock(self.case['pack']);runtime.configure_pack_runtime(self.case['settings'])
        from prompt_retrieval import settle_retrieval_record
        record=c.load(self.root/'retrieval.json');record['pack_state']=runtime.load_pack_catalog().fingerprint
        self.write('retrieval.json',settle_retrieval_record(record,prompt=(self.root/'prompt.txt').read_text(encoding='utf-8'),plot=c.load(self.root/'plot.json')))
        result=self.check();self.assertFalse(result['ok'])
        self.assertIn('no native mask image',str(result))
    def test_resume_uses_existing_result_without_sending_again(self):
        run=self.prepare();self.execute(run)
        with patch.object(transport,'send',side_effect=AssertionError('duplicate send')) as sender, patch.object(transport,'upload_bytes',side_effect=AssertionError('duplicate upload')) as upload:
            w.resume(self.root,run)
        sender.assert_not_called();upload.assert_not_called()
    def test_bundle_mask_change_is_detected_during_check(self):
        Image.new('L',(32,32),255).save(self.root/'masks/a/mask.png')
        self.assertFalse(self.check()['ok'])
    def test_unanswered_semantic_review_is_rejected(self):
        review=c.load(self.root/'mask-review.json');review['verdict']=None;self.write('mask-review.json',review)
        binding=c.load(self.root/'mask-binding.json');binding['review']['sha256']=c.digest(c.read(self.root/'mask-review.json'));self.write('mask-binding.json',binding)
        self.assertFalse(self.check()['ok'])
    def test_source_remains_unchanged_through_execution(self):
        before=c.read(self.root/'source.png');run=self.prepare();self.execute(run)
        self.assertEqual(c.read(self.root/'source.png'),before)


class NativeRequestTests(unittest.TestCase):
    def data(self):
        from request_contract import MANAGEMENT_VALUE
        verified={'host_forwarding':{'effective_prompt':'Synthetic image-edit request for a constructed shape.',
            'parameters':{'width':32,'height':32,'strength':.7},'selected_transport':{'mode':'separate-field','rendition':{'negative':'synthetic unwanted marks'}},
            'reference_media_role':'seed-image','selected_references':[{'resolved_path':'/source.png'}],
            'technical_media':[{'resolved_path':'/mask.png','role':'mask image','field':['inputs','maskImage'],'many':False},
                               {'resolved_path':'/guide.png','role':'reference images','field':['inputs','referenceImages'],'many':True}]}}
        offering={'service':'runware','model_identifier':'synthetic:test-only','request_keys':{'prompt':['positivePrompt'],'negative prompt':['negativePrompt'],
            'model':['model'],'seed image':['inputs.seedImage'],'mask image':['inputs.maskImage'],'reference images':['inputs.referenceImages']}}
        return verified,offering,{'operations':{'imageInference':{}}}
    def test_runware_request_uses_native_media_not_prompt_attachments(self):
        import transport_runware as rw
        v,o,s=self.data();result=rw.compile_request(v,o,s,{'/source.png':'SOURCE','/mask.png':'MASK','/guide.png':'GUIDANCE'})
        self.assertEqual(result['request']['inputs'],{'seedImage':'SOURCE','maskImage':'MASK','referenceImages':['GUIDANCE']})
        self.assertEqual([r['index'] for r in result['layout']['media']],[0,1,2])
    def test_conflicting_parameter_cannot_override_native_mask(self):
        import transport_runware as rw
        v,o,s=self.data();v['host_forwarding']['parameters']['inputs.maskImage']='OTHER'
        with self.assertRaises(ValueError):rw.compile_request(v,o,s)
    def test_optional_guidance_omitted_on_native_wire(self):
        import transport_runware as rw
        v,o,s=self.data();v['host_forwarding']['technical_media'].pop()
        result=rw.compile_request(v,o,s)
        self.assertEqual(set(result['request']['inputs']),{'seedImage','maskImage'})


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure();unittest.main(verbosity=2)
