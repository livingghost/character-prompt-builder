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

    @contextlib.contextmanager
    def compilation_error(self, pattern):
        from production_diagnostics import CompilationError
        with self.assertRaises(CompilationError) as caught:
            yield
        self.assertRegex(json.dumps(caught.exception.report['diagnostics']), pattern)

    def prepare(self):
        return workflow.prepare(self.root, 'task.json')['run']

    def test_document_and_whole_sources_are_pinned(self):
        run = self.prepare()
        _,prepared,consumer,_ = workflow.load_run(self.root,run)
        self.assertEqual(consumer['authoring_materials'][0]['document'], (self.root/'scene-material/persona.md').read_text(encoding='utf-8'))
        deps = {x['path'] for x in prepared['dependencies'] if x['space']=='studio'}
        self.assertTrue({'originals/subject.md','originals/scene.md','scene-plan.json','scene-material/persona.md'} <= deps)
        self.assertNotIn('templates/narrative/personas/persona-template.md', {x['path'] for x in prepared['route']['reads']})

    def test_author_notes_are_not_appended_to_generation_prompt(self):
        run = self.prepare()
        value = binding.create(self.root,run,(self.root/'delivery.txt').read_text(encoding='utf-8'))
        binding.validate(value,(self.root/'delivery.txt').read_text(encoding='utf-8'))
        actual = binding.effective(value,'PUBLIC_RENDERING_ONLY')
        self.assertEqual(actual,'PUBLIC_RENDERING_ONLY')
        self.assertNotIn('Controlling definition',actual)

    def test_unquoted_source_edit_invalidates_reuse(self):
        run=self.prepare()
        p=self.root/'originals/subject.md'
        p.write_text(p.read_text(encoding='utf-8')+'A newly declared exception outside the selected excerpt.\n', encoding='utf-8')
        self.assertEqual(workflow.status(self.root,run)['runs'][0]['readiness'],'blocked')
        with self.compilation_error('complete source changed'):
            self.prepare()

    def test_changed_derived_document_is_not_accepted(self):
        p=self.root/'scene-material/persona.md';p.write_text(p.read_text(encoding='utf-8')+'Unexpected new direction.\n', encoding='utf-8')
        with self.compilation_error('stale|modified'):
            self.prepare()

    def test_an_image_task_refuses_a_text_material(self):
        fixture.task(self.root, self.spec, artifact='image'); self.write_task()
        with self.compilation_error('prepared for text, and a task that makes image widens its scope'):
            self.prepare()

    def test_a_text_task_accepts_an_image_material(self):
        plan = m.load(self.root, 'scene-plan.json'); plan['medium'] = 'image'
        (self.root/'image-plan.json').write_bytes(m.encoded(plan))
        scene.build(self.root, 'image-plan.json', 'image-material')
        self.spec['scene_materials'] = [{'plan':'image-plan.json','bundle':'image-material'}]; self.write_task()
        consumer = workflow.load_run(self.root, self.prepare())[2]
        self.assertIn('Medium: image', consumer['authoring_materials'][0]['document'])

    def test_feature_needs_explicit_material(self):
        self.spec['scene_materials']=[];self.write_task()
        with self.compilation_error('scene_materials'):
            self.prepare()

    def test_material_needs_explicit_feature(self):
        self.spec['route']='development';self.spec['features']=[];self.write_task()
        with self.compilation_error('scene_materials'):
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
        with self.compilation_error('accepted content'):
            self.prepare()


class UpscaleIntegration(unittest.TestCase):
    """Real compiler, permissions, transport bytes and recovery for one upscale."""
    def setUp(self):
        import production_case_fixtures as cases
        import production_execution as execution
        import transport_synthetic
        from test_production_execution import decisions
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);case=cases.create(base/'studio',base/'runtime',with_upscale=True)
        self.root=case['root'];self.case=case
        self.task=cases.upscale_task(self.root)
        self.run=workflow.prepare(self.root,self.task)['run']
        self.request=c.load(self.root/'upscale/input.json');self.source=self.root/'upscale/source.png'
        self.model=cases.UPSCALE_MODEL_ID;self.transport=transport_synthetic
        self.execution=execution;self.decision_file=decisions(self.root,self.run)
        self.upload=self.enterContext(patch.object(transport_synthetic,'upload_bytes',wraps=transport_synthetic.upload_bytes))
        self.send=self.enterContext(patch.object(transport_synthetic,'send',wraps=transport_synthetic.send))
        self.validation_file=self.root/'upscale/validation.json';self.validation_file.write_bytes(c.encoded(self.request['request_validation']))
        self.intent_file=self.root/'upscale/render-intent.json';self.intent_file.write_bytes(c.encoded(self.request['render_intent']))
        # The exact inputs the dispatcher's upscale preview compares with the sealed run.
        self.options=argparse.Namespace(source=self.source,model=self.model,scale=2,settings_file=None,
            character='robot',slot='candidate',guidance=None,request_validation_file=self.validation_file,
            render_intent=self.intent_file,pack_settings=case['settings'],preview_out=None)

    def call(self):
        """Execute the sealed upscale under the run's decision file: 0 when every output was captured."""
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            result=self.execution.execute(self.root,self.run,decisions_file=self.decision_file)
        return 0 if result.get('execution_completed') else 1

    def test_execute_and_recover_share_one_formal_record(self):
        self.assertEqual(self.call(),0)
        from PIL import Image
        result=workflow.load_run(self.root,self.run)
        candidate=workflow.find(result[3],'candidate')
        raw=c.object_read(result[0],candidate['data']['files'][0]['sha256'])
        with Image.open(io.BytesIO(raw)) as image:self.assertEqual(image.size,(64,64))
        initial=[row['sha256'] for row in result[3] if row['event']=='candidate']
        again=self.execution.resume(self.root,self.run)
        self.assertEqual(again['runs'][0]['candidates'],initial)
        self.assertEqual(self.send.call_count,1);self.assertEqual(self.upload.call_count,1)
        import reservation_lifecycle as budget
        used=budget.budget(self.root)['grants'][0]['consumed']
        self.assertEqual((used['uses'],used['outputs']),(1,1))

    def test_absent_authorization_blocks_before_upload(self):
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError) as caught:
            self.execution.execute(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'AUTHORIZATION_REQUIRED')
        self.upload.assert_not_called();self.send.assert_not_called()

    def test_altered_scale_is_refused_by_the_preview(self):
        self.options.scale=4
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError) as caught:
            dispatch.dispatch_upscale(self.options,self.root)
        self.assertEqual(caught.exception.diagnostic.code,'INPUT_CONSISTENCY_ERROR')
        self.upload.assert_not_called()

    def test_source_changed_after_preparation_blocks_before_upload(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.call()
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError) as caught:
            dispatch.dispatch_upscale(self.options,self.root)
        self.assertEqual(caught.exception.diagnostic.code,'SOURCE_CHANGED')
        self.upload.assert_not_called()

    def test_extra_outputs_are_candidates_but_not_complete(self):
        from transport_synthetic import send
        original=self.send._mock_wraps
        def extra(request,service,key):
            answer=original(request,service,key);answer['data'].append({**answer['data'][0],'id':'distinct-extra-output'});return answer
        self.send.side_effect=extra
        self.assertEqual(self.call(),1)
        report=self.execution.status(self.root,self.run)['runs'][0]
        self.assertEqual(report['capture'],'partial');self.assertEqual(len(report['candidates']),2)
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'robot'))),2)

    def test_timeout_keeps_unknown_outcome_without_resend(self):
        self.send.side_effect=TimeoutError('Synthetic post-send connection loss')
        self.assertEqual(self.call(),1)
        report=self.execution.resume(self.root,self.run)
        self.assertEqual(report['runs'][0]['submission'],'outcome_unknown')
        self.assertEqual(self.send.call_count,1);self.assertEqual(self.upload.call_count,1)

    def test_saved_response_recovers_after_original_source_removed(self):
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic registration failure')):
            with self.assertRaises(OSError):self.call()
        self.source.unlink()
        result=self.execution.resume(self.root,self.run)
        self.assertTrue(result['execution_completed']);self.assertEqual(self.send.call_count,1)
        self.assertTrue(result['runs'][0]['freshness_diagnostics'])

    def test_missing_image_acquisition_retains_response_then_resumes(self):
        with patch.object(dispatch,'inline_image',side_effect=ValueError('Synthetic failed transfer')):
            self.assertEqual(self.call(),1)
        self.assertEqual(self.execution.status(self.root,self.run)['runs'][0]['capture'],'partial')
        report=self.execution.resume(self.root,self.run)
        self.assertTrue(report['execution_completed']);self.assertEqual(self.send.call_count,1)

    def test_projection_failure_retains_production_candidate(self):
        with patch.object(studio,'iterate',side_effect=OSError('Synthetic projection failure')):
            self.assertEqual(self.call(),1)
        first=self.execution.resume(self.root,self.run);second=self.execution.resume(self.root,self.run)
        self.assertEqual(first['runs'][0]['candidates'],second['runs'][0]['candidates'])
        self.assertEqual(self.send.call_count,1)
        self.assertEqual(len(studio.read_iterations(studio.character_dir(self.root,'robot'))),1)

    def test_source_and_scale_are_verified_during_check(self):
        import production_compiler as compiler
        value=c.load(self.root/'upscale/input.json');value['scale_factor']=3
        (self.root/'upscale/input.json').write_bytes(c.encoded(value))
        checked=compiler.check_task(self.root,self.task)
        self.assertFalse(checked['ok']);self.assertTrue(any(item['code']=='CONTROL_NOT_AVAILABLE' for item in checked['diagnostics']))
        self.upload.assert_not_called();self.send.assert_not_called()

    def test_repeat_preserves_input_without_inheriting_claim(self):
        import production_variation as variation
        self.assertEqual(self.call(),0)
        child=variation.derive(self.root,self.run,prepare=True)
        self.assertEqual(child['input_sha256'],workflow.load_run(self.root,self.run)[1]['input_sha256'])
        self.assertEqual(workflow.load_run(self.root,child['run'])[3],[])
        self.assertEqual(self.send.call_count,1)

    def test_source_variant_is_explicit_and_reverified(self):
        import production_variation as variation
        from transport_synthetic import _png
        from production_case_fixtures import write
        from production_binding import upscale_request
        c.atomic(self.root/'upscale/other.png',_png(16,16,b'\x80\x90\xa0'))
        value=upscale_request(self.root,self.root/'upscale/other.png',self.model,2,{},None,
                             request_validation=self.request['request_validation'],render_intent=self.request['render_intent'])
        write(self.root/'upscale/other-input.json',value)
        write(self.root/'upscale/changes.json',{'changes':{'upscale-input':{'path':'upscale/other-input.json'}},'reason':'Explicit synthetic source change.'})
        child=variation.derive(self.root,self.run,changes_file='upscale/changes.json',prepare=True)
        self.assertNotEqual(child['input_sha256'],workflow.load_run(self.root,self.run)[1]['input_sha256'])
        self.assertEqual(workflow.load_run(self.root,child['run'])[3],[])


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
