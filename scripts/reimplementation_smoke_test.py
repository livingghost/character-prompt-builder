#!/usr/bin/env python3
"""Current integrated scene reuse and authorized upscale tests, with no network calls.

Only the external service and its credentials/schema are synthetic. Preparation,
authority, exact input claims, real image package verification, recording and
recovery use their operational implementations. No artistic success is inferred.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import execution_contract as c
import material_support as m
import scene_persona as scene
import production_binding as binding
import production_workflow as workflow
import production_fixtures as fixture
import work_ledger
import studio
import dispatch
from create_authoring_example import create
from smoke_fixtures import isolate_home

isolate_home()


class SceneIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        create(self.root)
        started = work_ledger.begin(self.root, 'Synthetic authoring integration', ['prepare', 'deliver'])
        (self.root/'delivery.txt').write_text('Only the public rendition, not private author notes.', encoding='utf-8')
        self.spec = {'task_id':started['task_id'], 'route':'performance','features':['scene-persona'],
            'sources':[], 'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'No private source copying.'},
            'criteria':[{'id':'scope','strength':'hard','text':'Use only the prepared scope.'}], 'world_views':[],
            'scene_materials':[{'plan':'scene-plan.json','bundle':'scene-material'}]}
        fixture.task(self.root, self.spec)
        self.write_task()

    def write_task(self):
        (self.root/'task.json').write_bytes(c.encoded(self.spec))

    def prepare(self):
        return workflow.prepare(self.root, 'task.json')['run']

    def test_document_and_whole_sources_are_pinned(self):
        run = self.prepare()
        _,prepared,consumer,_ = workflow.load_run(self.root,run)
        self.assertEqual(consumer['authoring_materials'][0]['document'], (self.root/'scene-material/persona.md').read_text())
        deps = {x['path'] for x in prepared['dependencies'] if x['space']=='project'}
        self.assertTrue({'originals/subject.md','originals/scene.md','scene-plan.json','scene-material/persona.md'} <= deps)
        self.assertNotIn('templates/narrative/personas/persona-template.md', {x['path'] for x in prepared['route']['reads']})

    def test_author_notes_are_not_appended_to_generation_prompt(self):
        run = self.prepare()
        value = binding.create(self.root,run,(self.root/'delivery.txt').read_text())
        binding.validate(value,(self.root/'delivery.txt').read_text())
        actual = binding.effective(value,'PUBLIC_RENDERING_ONLY')
        self.assertEqual(actual,'PUBLIC_RENDERING_ONLY')
        self.assertNotIn('Controlling definition',actual)

    def test_unquoted_source_edit_invalidates_reuse(self):
        run=self.prepare()
        p=self.root/'originals/subject.md'
        p.write_text(p.read_text()+'A newly declared exception outside the selected excerpt.\n')
        self.assertFalse(workflow.status(self.root,run)['ok'])
        with self.assertRaisesRegex(ValueError,'complete source changed'):
            self.prepare()

    def test_changed_derived_document_is_not_accepted(self):
        p=self.root/'scene-material/persona.md';p.write_text(p.read_text()+'Unexpected new direction.\n')
        with self.assertRaisesRegex(ValueError,'stale|modified'):
            self.prepare()

    def test_feature_needs_explicit_material(self):
        self.spec['scene_materials']=[];self.write_task()
        with self.assertRaisesRegex(ValueError,'scene_materials'):
            self.prepare()

    def test_material_needs_explicit_feature(self):
        self.spec['route']='development';self.spec['features']=[];self.write_task()
        with self.assertRaisesRegex(ValueError,'scene_materials'):
            self.prepare()

    def test_accepted_public_snapshot_needs_no_original_files(self):
        value=m.decode((self.root/'scene-material/material.json').read_bytes())
        (self.root/'received.json').write_bytes(m.encoded(value))
        self.spec['scene_materials']=[{'artifact':'received.json','accepted_content_sha256':value['content_sha256'],
            'accepted_by':'synthetic-reviewer','acceptance_basis':'Accept this explicit immutable snapshot for this scoped fixture.'}]
        self.write_task()
        for p in (self.root/'originals').iterdir():p.unlink()
        run=self.prepare();consumer=workflow.load_run(self.root,run)[2]
        self.assertEqual(consumer['authoring_materials'][0]['source_integrity'],'snapshot-only-originals-not-checked')

    def test_snapshot_hash_requires_the_exact_accepted_content(self):
        value=m.decode((self.root/'scene-material/material.json').read_bytes())
        (self.root/'received.json').write_bytes(m.encoded(value))
        self.spec['scene_materials']=[{'artifact':'received.json','accepted_content_sha256':'f'*64,
            'accepted_by':'synthetic-reviewer','acceptance_basis':'Deliberately mismatched test declaration.'}]
        self.write_task()
        with self.assertRaisesRegex(ValueError,'accepted content'):
            self.prepare()


class UpscaleIntegration(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        from upscale_package_smoke_test import model_rows
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=studio.init(Path(self.temp.name)/'studio','synthetic-upscale','Offline integrated fixture')
        studio.add_character(self.root,'subject','')
        self.source=self.root/'source.png';Image.new('RGB',(8,8)).save(self.source)
        self.record=model_rows()[0];self.model=self.record['id']
        self.settings={'variant':'general'}
        import transport_runware
        import request_renderer
        from request_validation_fixtures import interface_validation
        self.offering={'service':'synthetic','model_identifier':'fixture:model','observed_at':'2000-01-01',
                       'setting_keys':{'variant':'variant'},'request_keys':{'input image':['inputImage']}}
        self.service={'id':'synthetic','endpoint':{'base_url':'https://example.invalid'},'operations':{'imageUpscale':{}}}
        self.transport=SimpleNamespace(__file__=transport_runware.__file__, compile_upscale=transport_runware.compile_upscale,
            RESULT_HOSTS=frozenset({'example.invalid'}),
            upload_bytes=Mock(),send=Mock(),rejections=Mock(return_value=[]),results=Mock(),
            observation_outcome=Mock(return_value='accepted'))
        target={'service':'synthetic','model_identifier':'fixture:model','operation':'imageUpscale'}
        validation=interface_validation(self.root,target=target,record=self.record,offering=self.offering,
            service_record=self.service,transport=self.transport,reference_mode='authored-rendition')
        self.validation_file=self.root/'validation.json';self.validation_file.write_bytes(c.encoded(validation))
        self.request=binding.upscale_request(self.root,self.source,self.model,2,self.settings,None,request_validation=validation)
        sources=[{'id':'source','path':'source.png','role':'upscale-source','disposition':'applied','locator':'whole','reason':'Exact synthetic source image.'}]
        self.run=fixture.prepare_dispatch(self.root,c.encoded(self.request).decode(),route='upscale',sources=sources)
        rendered=request_renderer.upscale(self.request,self.record,self.offering,self.service,self.transport,self.source,self.settings,root=self.root)
        self.intent=workflow.submission_intent(self.request,rendered=rendered,seed=None,count=1,offering=self.offering,service=self.service)
        self.authorization=fixture.grant(self.root,self.run,self.intent)
        self.options=argparse.Namespace(send=True,character='subject',slot='base.front',source=self.source,
            model=self.model,scale=2,settings=json.dumps(self.settings),guidance=None,service=None,profiles=None,note='Synthetic fixture only',
            production_authorization=self.authorization,
            request_validation_file=self.validation_file)
        self.entries=[{'url':'https://example.invalid/fixture.png','id':'fixture'}]
        def send(_request,*args):
            rows=workflow.load_run(self.root,self.run)[3]
            self.assertTrue(any(r['event']=='dispatch-claim' for r in rows),'claim must precede send')
            return {'data':'synthetic-response'}
        def upload(*args):
            self.assertTrue(any(r['event']=='dispatch-claim' for r in workflow.load_run(self.root,self.run)[3]))
            return 'synthetic-upload-id'
        self.transport.upload_bytes.side_effect=upload
        self.transport.send.side_effect=send
        self.transport.results.side_effect=lambda answer:list(self.entries)
        def save(url,path,hosts):
            Image.new('RGB',(16,16)).save(path)
            return c.digest(path.read_bytes())
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        for name,kw in {'resolve_model_record':{'return_value':(self.model,self.record)},'select_offering':{'return_value':self.offering},
            'service_for':{'return_value':('synthetic',self.service,self.transport)},'model_pack_root':{'return_value':self.root},
            'validate_generation_parameters':{},'api_key':{'return_value':'SYNTHETIC-NO-CREDENTIAL'},'save':{'side_effect':save}}.items():
            self.stack.enter_context(patch.object(dispatch,name,**kw))
        self.stack.enter_context(patch('upscale_package.resolve_model_record',return_value=(self.model,self.record)))

    def call(self):return dispatch.dispatch_upscale(self.options,self.root)
    def test_exact_request_claim_results_and_real_package(self):
        self.assertEqual(self.call(),0)
        rows=workflow.load_run(self.root,self.run)[3]
        self.assertEqual(sum(r['event']=='dispatch-claim' for r in rows),1)
        result=workflow.find(rows,'dispatch-results')['data']
        self.assertEqual(len(result['files']),1)
        self.assertTrue(any(x['path'].endswith('upscale-package-1.json') for x in result['evidence']))
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'subject'))),1)

    def test_absent_authorization_blocks_before_upload(self):
        self.options.production_authorization=None
        with self.assertRaisesRegex(ValueError,'authorization'):self.call()
        self.transport.upload_bytes.assert_not_called();self.transport.send.assert_not_called()

    def test_altered_scale_blocks_before_upload(self):
        self.options.scale=4
        with self.assertRaisesRegex(ValueError,'prepared delivery'):self.call()
        self.transport.upload_bytes.assert_not_called()

    def test_source_changed_after_preparation_blocks_before_upload(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.call()
        self.transport.upload_bytes.assert_not_called()

    def test_extra_result_is_kept_but_not_an_authorized_success(self):
        self.entries.append({'url':'https://example.invalid/other.png','id':'other'})
        self.assertEqual(self.call(),1)
        self.assertFalse(any(r['event']=='dispatch-results' for r in workflow.load_run(self.root,self.run)[3]))
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'subject'))),2)

    def test_ambiguous_remote_failure_never_retries(self):
        self.transport.send.side_effect=OSError('Synthetic connection lost after submit')
        with self.assertRaises(OSError):self.call()
        with self.assertRaisesRegex(ValueError,'already claimed'):self.call()
        self.assertEqual(self.transport.send.call_count,1)
        self.assertEqual(self.transport.upload_bytes.call_count,1)

    def test_acquired_result_recovers_locally_and_idempotently(self):
        with patch.object(studio,'iterate',side_effect=OSError('Synthetic recording failure')):
            with self.assertRaises(OSError):self.call()
        first=workflow.recover_recording(self.root,self.run)
        second=workflow.recover_recording(self.root,self.run)
        self.assertEqual(first['iterations'],second['iterations'])
        self.assertEqual(first['network_calls'],0)
        self.assertEqual(self.transport.send.call_count,1)
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'subject'))),1)

    def test_generation_also_requires_a_prepared_submission_context(self):
        with self.assertRaisesRegex(ValueError,'prepared production run'):
            dispatch.require_submission(self.options,None)


if __name__=='__main__':
    unittest.main(verbosity=2)
