#!/usr/bin/env python3
"""Draft changes through declared compiler fields with synthetic recorded evidence."""
import copy
from pathlib import Path
import unittest
import request_contract as rc
import request_contract_smoke_test as fixture
from input_evidence import InputEvidence
import production_variation as variation
from smoke_fixtures import isolate_home

isolate_home()

class FieldTests(fixture.RequestContractTests):
    def test_variation_seed_changes_exact_tuple(self):
        before=self.seal();changed,diff=variation.apply_changes(before,{'seed':4},self.root,InputEvidence(self.root))
        self.assertEqual(changed['request']['seed'],4);self.assertNotEqual(before['profile'],changed['profile'])
        self.assertEqual(before['request']['seed'],3)
    def test_variation_content_is_not_a_parameter_measurement(self):
        before=self.seal();changed,_=variation.apply_changes(before,{'prompt':'Other explicit content.'},self.root,InputEvidence(self.root))
        self.assertEqual(before['profile'],changed['profile']);self.assertNotEqual(before['request_sha256'],changed['request_sha256'])
    def test_variation_cannot_mutate_model_as_content(self):
        with self.assertRaises(ValueError):variation.apply_changes(self.seal(),{'model':'other'},self.root,InputEvidence(self.root))
    def test_variation_cannot_invent_a_field(self):
        with self.assertRaises(ValueError):variation.apply_changes(self.seal(),{'unknown-field':1},self.root,InputEvidence(self.root))
    def test_variation_rejects_empty_change(self):
        with self.assertRaises(ValueError):variation.apply_changes(self.seal(),{'seed':3},self.root,InputEvidence(self.root))

import reimplementation_smoke_test as dispatch_fixture
import execution_contract as c
import production_workflow as workflow

class RecordedVariationTests(dispatch_fixture.UpscaleIntegration):
    def make_variation(self):
        self.call()
        rows=workflow.load_run(self.root,self.run)[3]
        results=workflow.find(rows,'dispatch-results')
        workflow.capture(self.root,self.run,results['data']['files'][0]['path'],'Synthetic acquired comparison candidate.')
        candidates=[row for row in workflow.load_run(self.root,self.run)[3] if row['event']=='candidate']
        self.assertTrue(candidates)
        (self.root/'changes.json').write_bytes(c.encoded({'candidate':candidates[0]['sha256'],'changes':{'scale':4},'reason':'Synthetic scale comparison.'}))
    def test_draft_uses_actual_upscale_request_without_new_authority(self):
        self.make_variation();before=copy.deepcopy(workflow.load_run(self.root,self.run)[3])
        result=variation.draft(self.root,self.run,'changes.json','variation')
        self.assertEqual(result['state'],'draft');self.assertEqual(workflow.load_run(self.root,self.run)[3],before)
        task=c.load(self.root/'variation/production-task.json');original=workflow.load_run(self.root,self.run)[1]['task']
        self.assertEqual(task['production_id'],original['production_id']);self.assertFalse(result['external_effect'])
        self.assertEqual(self.transport.send.call_count,1)
    def test_draft_keeps_unchanged_source_evidence(self):
        self.make_variation();result=variation.draft(self.root,self.run,'changes.json','variation')
        choices=c.load(self.root/'variation/choices.json')['choices']
        self.assertEqual(choices['source_run'],self.run);self.assertIsNotNone(choices['reading']['reading_key'])
        self.assertTrue(result['profile_changed'])

    def test_changed_upscale_source_updates_the_explicit_source_and_action(self):
        self.make_variation()
        from PIL import Image
        Image.new('RGB',(8,8),'white').save(self.root/'other.png')
        change=c.load(self.root/'changes.json');change['changes']={'media:1':{'path':'other.png'}}
        (self.root/'changes.json').write_bytes(c.encoded(change))
        result=variation.draft(self.root,self.run,'changes.json','variation')
        action=next(x for x in result['next_actions'] if x['operation']=='build-upscale-request')
        self.assertEqual(action['args']['source'],'other.png')
        task=c.load(self.root/'variation/production-task.json')
        self.assertIn('other.png',[x['path'] for x in task['sources']])
        self.assertNotIn('source.png',[x['path'] for x in task['sources']])

    def test_upscale_parameter_uses_the_declared_model_setting(self):
        self.make_variation()
        change=c.load(self.root/'changes.json');change['changes']={'parameter:variant':'other'}
        (self.root/'changes.json').write_bytes(c.encoded(change))
        result=variation.draft(self.root,self.run,'changes.json','variation')
        action=next(x for x in result['next_actions'] if x['operation']=='build-upscale-request')
        self.assertEqual(action['args']['settings'],{'variant':'other'})
        self.assertFalse(result['external_effect'])


import argparse
import contextlib
import io
from unittest.mock import patch
import feature_workflow_smoke_test as generation_fixture
import production_fixtures
import request_renderer
import transport_runware

class GenerationVariationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):generation_fixture.FeatureWorkflowTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        generation_fixture.FeatureWorkflowTests.tearDownClass.__func__(cls)
        generation_fixture.catalog_cli.configure_pack_runtime(None)
    setUp=generation_fixture.FeatureWorkflowTests.setUp
    def test_actual_compiler_generation_and_variation(self):
        import dispatch
        import input_contracts
        from request_validation_fixtures import interface_validation
        from build_generation_payload import generation_input_sha256
        from prepare_generation_references import resolve_model_record
        from verify_generation_payload import verify
        run=production_fixtures.prepare_dispatch(self.root,generation_fixture.PROMPT)
        package=production_fixtures.bind_package(self.root,run,self.package)
        _,record=resolve_model_record(package['model'])
        offering={'service':'synthetic','model_identifier':package['model'],
                  'request_keys':{'prompt':['positivePrompt'],'negative prompt':['negativePrompt']},
                  'observed_at':'2000-01-01','constraints':{}}
        from render_contract_fixtures import profile
        import render_contract_lib as rendering
        offering['execution_profile']=profile(seed=True)
        record=copy.deepcopy(record);record['offerings']=[offering]
        self.enterContext(patch('build_generation_payload.resolve_model_record',return_value=(package['model'],record)))
        package['render_contract']=rendering.compile_contract(record,offering,package['production_spec']['render_intent'],
            package['generation_payload']['parameters'],prompt=package['composition_prompt'],reference_count=0)
        package['generation_payload']['service']={key:offering.get(key) for key in ('model_identifier','observed_at','schema_snapshot')}
        package['generation_payload']['service']['id']=offering['service']
        service={'operations':{'imageInference':{}},'endpoint':{'base_url':'https://example.invalid/not-contacted'}}
        validation=interface_validation(self.root,target={'service':'synthetic','model_identifier':package['model'],
            'operation':'imageInference'},record=record,offering=offering,service_record=service,
            transport=transport_runware,reference_mode='prompt-prefix')
        reader,_=input_contracts.capture_validation(validation,root=self.root)
        reader.basis(package['visual_continuity']['basis'])
        input_contracts.attach(package,validation,reader)
        for key in ('request_validation_sha256','input_snapshots_sha256'):
            package['generation_contract'][key]=package[key]
        package['generation_input_sha256']=generation_input_sha256(package)
        package['generation_contract']['generation_input_sha256']=package['generation_input_sha256']
        path=self.root/'bound.json';path.write_bytes(c.encoded(package))
        rendered=request_renderer.generation(package,verify(package,package_root=self.root,project=self.root),
            record,offering,service,transport_runware,seed=7,count=1)
        authorization=production_fixtures.grant(self.root,run,workflow.submission_intent(package,rendered=rendered,
            seed=7,count=1,offering=offering,service=service))
        options=argparse.Namespace(package=path,service=None,profiles=None,seed=7,count=1,send=True,
            character='C01',slot='base.front',note='Synthetic generated candidate.',
            production_authorization=authorization)
        def save(url,destination,hosts):
            from PIL import Image
            Image.new('RGB',(24,24)).save(destination)
            return c.digest(destination.read_bytes())
        answer={'data':[{'taskUUID':'synthetic','imageURL':'https://example.invalid/result','seed':7}]}
        with patch.object(dispatch,'resolve_model_record',return_value=(package['model'],record)),patch.object(dispatch,'service_for',return_value=('synthetic',service,transport_runware)),patch.object(dispatch,'api_key',return_value='not-a-key'),patch.object(dispatch,'save',side_effect=save),patch.object(transport_runware,'send',return_value=answer) as send,patch.object(transport_runware,'upload_bytes',side_effect=AssertionError('unexpected upload')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dispatch.dispatch_generation(options,self.root),0)
        self.assertEqual(send.call_count,1)
        import model_observation
        observed=model_observation._derive(model_observation.capture(self.root,run))
        self.assertEqual(observed['target']['service'],'synthetic')
        rows=workflow.load_run(self.root,run)[3];results=workflow.find(rows,'dispatch-results')
        candidate=workflow.capture(self.root,run,results['data']['files'][0]['path'],'Synthetic comparison only.')
        (self.root/'changes.json').write_bytes(c.encoded({'candidate':candidate['sha256'],'changes':{'seed':9},'reason':'Compare the declared synthetic seed.'}))
        before=copy.deepcopy(workflow.load_run(self.root,run)[3])
        result=variation.draft(self.root,run,'changes.json','variation')
        self.assertEqual(workflow.load_run(self.root,run)[3],before)
        self.assertTrue(result['profile_changed'])
        self.assertTrue((self.root/'variation/prepared-reference-set.json').is_file())
        choices=c.load(self.root/'variation/choices.json')['choices']
        self.assertEqual(choices['visual']['subjects'].keys(),package['visual_continuity']['subjects'].keys())

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
