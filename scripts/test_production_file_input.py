"""File/stdin inputs use the same current contracts, with no real generation."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import execution_contract as c
import production_case_fixtures as cases
import production_workflow as workflow

import production_fixtures


class ObjectInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'日本語 studio';self.root.mkdir()

    def test_file_and_stdin_preserve_unicode_and_whitespace(self):
        raw=c.encoded({'text':'  日本語\n  Exact text.  ','size':[32,64]})
        (self.root/'設定.json').write_bytes(raw)
        file_value=c.read_json_object('設定.json',root=self.root)
        with patch('sys.stdin',io.TextIOWrapper(io.BytesIO(raw),encoding='utf-8')):
            stream_value=c.read_json_object('-',root=self.root)
        self.assertEqual(file_value,stream_value)
        self.assertEqual(file_value['text'],'  日本語\n  Exact text.  ')

    def test_duplicate_json_keys_are_invalid_in_both_inputs(self):
        raw=b'{"steps":20,"steps":1}'
        (self.root/'parameters.json').write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'duplicate JSON key'):
            c.read_json_object('parameters.json',root=self.root)
        with patch('sys.stdin',io.StringIO(raw.decode())):
            with self.assertRaisesRegex(ValueError,'duplicate JSON key'):c.read_json_object('-')

    def test_nonfinite_numbers_are_not_provider_parameters(self):
        for raw in ('{"strength": NaN}','{"strength": Infinity}'):
            with self.subTest(raw=raw),patch('sys.stdin',io.StringIO(raw)):
                with self.assertRaisesRegex(ValueError,'non-finite'):c.read_json_object('-')

    def test_nonobject_rejected_by_same_contract(self):
        (self.root/'parameters.json').write_text('[]',encoding='utf-8')
        for source in ('parameters.json','-'):
            with self.subTest(source=source),patch('sys.stdin',io.StringIO('[]')):
                with self.assertRaisesRegex(ValueError,'expected a JSON object'):
                    c.read_json_object(source,root=self.root,label='--parameters-file')

    def test_invalid_utf8_does_not_get_replaced(self):
        (self.root/'bad.json').write_bytes(b'{"text":"\xff"}')
        with self.assertRaises(UnicodeDecodeError):c.read_json_object('bad.json',root=self.root)

    def test_relative_input_cannot_escape_the_studio(self):
        outside=self.root.parent/'outside.json';outside.write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError):c.read_json_object('../outside.json',root=self.root)

    def test_advisory_recommendation_preserves_each_authored_rendition(self):
        from model_contract import apply_prompt_recommendations,validate_recommendation_audit
        prompt='  Authored prompt.\r\n';negative='\tExcluded feature.  '
        actual,exclusions,audit=apply_prompt_recommendations({'id':'synthetic','recommendation_merge_mode':'advisory-only'},prompt=prompt,negative_prompt=negative)
        self.assertEqual(actual,prompt);self.assertEqual(exclusions,negative)
        validate_recommendation_audit(audit['positive'],prompt)
        validate_recommendation_audit(audit['negative'],negative)

    def test_integrated_rendition_preserves_authored_whitespace(self):
        from build_generation_payload import build_transports
        integrated='  Exact affirmative rendition.\r\n'
        result=build_transports(prompt='ordinary prompt',negative_prompt='exclusion',integrated_prompt=integrated,
                                native_negative='',critical_avoidance_integrated=False)
        self.assertEqual(result['integrated']['text'],integrated)

    def test_explicit_absolute_file_has_one_meaning(self):
        outside=self.root.parent/'chosen file.json';outside.write_text('{"steps":20}',encoding='utf-8')
        self.assertEqual(c.read_json_object(outside,root=self.root),{'steps':20})


class PackageFileInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.case=cases.create(self.base/'日本語 studio',self.base/'runtime')
        self.root=self.case['root']
        self.script=Path(__file__).resolve().parent/'build_generation_payload.py'
        s=self.case['settings']
        self.runtime=['--state-file',str(s.state_file),'--cache-dir',str(s.cache_dir),'--managed-root',str(s.managed_root),
                      '--pack-root',str(self.case['pack'])]

    def external_run(self) -> str:
        """A run whose task names no generation documents, so the builder takes them as files."""
        task=c.load(self.root/'task.json');task.pop('generation');task['execution']='external'
        cases.write(self.root/'external-task.json',task)
        return workflow.prepare(self.root,'external-task.json')['run']

    def build(self,run,name,*extra,stdin=None):
        args=[sys.executable,str(self.script),'--production-root',str(self.root),'--production-run',run,
              '--model',self.case['model'],'--request-validation-file','validation.json','--continuity','robot=one-off',
              '--service','synthetic',*self.runtime,*extra,'--out',name]
        return subprocess.run(args,input=stdin,cwd=self.base,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1',
                                  'CPB_HOME':str(production_fixtures.scratch_home_dir(self.base/'home'))},
                              capture_output=True,text=True,encoding='utf-8',timeout=120)

    def documents(self):
        return ['--plot-file','plot.json','--retrieval-record-file','retrieval.json','--production-spec-file','spec.json']

    def test_actual_builder_file_and_stdin_match_from_other_cwd(self):
        run=self.external_run()
        file_run=self.build(run,'from-file.json',*self.documents(),'--parameters-file','parameters.json')
        self.assertEqual(file_run.returncode,0,file_run.stdout+file_run.stderr)
        stream_run=self.build(run,'from-stdin.json',*self.documents(),'--parameters-file','-',
                              stdin=(self.root/'parameters.json').read_text(encoding='utf-8'))
        self.assertEqual(stream_run.returncode,0,stream_run.stdout+stream_run.stderr)
        left=json.loads(file_run.stdout);right=json.loads(stream_run.stdout)
        self.assertEqual(left['generation_payload'],right['generation_payload'])
        self.assertEqual(left['generation_input_sha256'],right['generation_input_sha256'])
        self.assertEqual(len(workflow.status(self.root)['runs']),1)

    def test_authored_whitespace_survives_prepare_and_actual_cli(self):
        from prompt_retrieval import settle_retrieval_record
        prompt = '  ' + cases.PROMPT + '\r\n\t'
        (self.root/'prompt.txt').write_bytes(prompt.encode('utf-8'))
        record=settle_retrieval_record(c.load(self.root/'retrieval.json'),prompt=prompt,plot=c.load(self.root/'plot.json'))
        cases.write(self.root/'retrieval.json',record)
        prepared=workflow.prepare(self.root,'task.json')
        self.assertEqual(prepared['request_preview']['prompt'],prompt)
        completed=self.build(prepared['run'],'whitespace.json')
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        package=json.loads(completed.stdout)
        self.assertEqual(package['composition_prompt'],prompt)
        self.assertEqual(package['generation_payload']['transports']['separate']['prompt'],prompt)

    def test_actual_builder_rejects_nonobject_before_publication(self):
        run=self.external_run()
        result=self.build(run,'not-created.json',*self.documents(),'--parameters-file','-',stdin='[]')
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        self.assertIn('--parameters-file: expected a JSON object',' '.join(item['message'] for item in json.loads(result.stdout)['diagnostics']))
        self.assertFalse((self.root/'not-created.json').exists())
        self.assertFalse(list(self.root.glob('.not-created*')))


class WorkflowStandardInputTests(unittest.TestCase):
    """A JSON input of production_workflow.py read from - is kept, as read, as an object of its run."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.root=cases.create(self.base/'日本語 studio',self.base/'runtime')['root']
        self.run=workflow.prepare(self.root,'task.json')['run']
        self.env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','CPB_HOME':str(production_fixtures.scratch_home_dir(self.base/'home'))}

    def cli(self,*args,stdin=b'',code=0):
        completed=subprocess.run([sys.executable,str(Path(__file__).resolve().parent/'production_workflow.py'),*args],
                                 input=stdin,cwd=self.base,env=self.env,capture_output=True,timeout=300)
        output=completed.stdout.decode('utf-8')
        self.assertEqual(completed.returncode,code,output+completed.stderr.decode('utf-8'))
        return json.loads(output)

    def test_execution_decisions_from_stdin_are_kept_as_a_run_object(self):
        import production_store as store
        raw=(self.root/cases.fill_decisions(self.root,self.run,'decisions.json')).read_bytes()
        result=self.cli('execute','--root',str(self.root),'--run',self.run,'--decisions-file','-',stdin=raw)
        self.assertTrue(result['execution_completed'])
        receipts=[row for row in store.event_rows(self.root,self.run) if row['event']=='authorization']
        held=f'production/runs/{self.run}/objects/{c.digest(raw)}'
        self.assertEqual({held},{item['path'] for row in receipts for item in row['data']['files'] if item['purpose']=='authorization-request'})

    def test_standard_input_feeds_one_input_per_call(self):
        result=self.cli('adoption-intent','--root',str(self.root),'--run',self.run,'--candidate','synthetic','--character','robot',
                        '--iteration','synthetic','--approval','-','--registration-record','-',stdin=b'{}',code=2)
        self.assertEqual(result['diagnostics'][0]['code'],'INPUT_SCHEMA_INVALID')
        self.assertIn('--approval, --registration-record',result['diagnostics'][0]['message'])

    def test_logs_without_a_root_read_the_configuration_directory(self):
        self.cli('new-production-id')
        listed=self.cli('logs')
        self.assertTrue(listed['operations'])
        exported=self.cli('logs-export','--out',str(self.base/'exported'),'--without-streams')
        self.assertIn('stdout.log and stderr.log console output',exported['excluded'])
        refused=self.cli('logs-export','--out',str(self.base/'exported'),code=2)
        self.assertEqual(refused['diagnostics'][0]['code'],'OUTPUT_ALREADY_EXISTS')


class UpscaleStudioPathTests(unittest.TestCase):
    def test_upscale_cli_resolves_all_declared_json_files_from_studio(self):
        import production_case_fixtures as fixture
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=fixture.create(base/'日本語 studio',base/'runtime',with_upscale=True)['root']
            task=c.load(root/fixture.upscale_task(root));original=c.load(root/task['delivery']['path'])
            fixture.write(root/'upscale/intent.json',original['render_intent'])
            fixture.write(root/'upscale/validation-record.json',original['request_validation'])
            fixture.write(root/'upscale/settings.json',original['settings'])
            script=Path(__file__).resolve().with_name('production_binding.py')
            completed=subprocess.run([sys.executable,str(script),'--root',str(root),'--source',original['source']['path'],
                '--model',original['model'],'--scale',str(original['scale_factor']),
                '--settings-file','upscale/settings.json','--render-intent','upscale/intent.json',
                '--request-validation-file','upscale/validation-record.json','--out','upscale/from-cli.json'],
                cwd=base,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','CPB_HOME':str(production_fixtures.scratch_home_dir(base/'home'))},
                capture_output=True,text=True,encoding='utf-8',timeout=120)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
            self.assertTrue(json.loads(completed.stdout)['ok'])
            self.assertEqual(c.load(root/'upscale/from-cli.json'),original)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
