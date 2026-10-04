"""Explicit target changes resolve complete new profiles without inheriting execution."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import execution_contract as c
import production_case_fixtures as f
import production_execution as execution
import production_variation as variation
import production_workflow as workflow
import production_store as store
from production_diagnostics import ProductionError,CompilationError

import production_fixtures


class RetargetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        b=Path(self.temp.name);self.base=b
        self.case=f.create(b/'日本語 studio',b/'runtime',with_alternate=True)
        self.root=self.case['root'];self.parent=workflow.prepare(self.root,'task.json');self.run=self.parent['run']

    def target(self,**kwargs):
        return variation.retarget(self.root,self.run,kwargs.pop('task','retarget/task.json'),
                                  reason='Explicit synthetic comparison of targets.',**kwargs)

    def test_target_change_needs_no_candidate_and_uses_new_profile(self):
        f.alternate_task(self.root)
        child=self.target(prepare=True)
        self.assertEqual(child['request_preview']['model'],'synthetic:alternate')
        self.assertEqual(child['request_preview']['steps'],22)
        directory,prepared,_,rows=workflow.load_run(self.root,child['run'])
        self.assertEqual(prepared['parent']['kind'],'retarget')
        self.assertEqual(prepared['parent']['run'],self.run)
        self.assertEqual(rows,[])
        profile=c.load(directory/'package.json')['render_contract']['model_card']['execution_profile']
        self.assertEqual(profile['id'],'synthetic-alternate-interface')
        self.assertEqual(profile['modes']['text-to-image']['controls']['steps']['schema']['maximum'],24)
        self.assertEqual(store.event_rows(self.root,self.run),[])
        self.assertFalse(child['authorization_inherited'])

    def test_different_target_rejects_parent_validation_evidence(self):
        path=f.alternate_task(self.root);task=c.load(self.root/path)
        task['generation']['request_validation']='validation.json';f.write(self.root/path,task)
        with self.assertRaises(CompilationError) as caught:self.target(prepare=True)
        self.assertTrue(any('target' in d['message'].lower() for d in caught.exception.report['diagnostics']))
        self.assertEqual(len(store.runs(self.root)),1)

    def test_new_profile_constraints_are_not_taken_from_parent(self):
        f.alternate_task(self.root,steps=5)
        with self.assertRaises(CompilationError):self.target(prepare=True)
        self.assertEqual(len(store.runs(self.root)),1)

    def test_unusable_reading_is_not_fabricated(self):
        f.alternate_task(self.root)
        reading=c.load(self.root/'retarget/reading.json')
        reading['applied'][0]['quote']='Invented text that was never present in the claimed source material for this target.'
        f.write(self.root/'retarget/reading.json',reading)
        with self.assertRaises(CompilationError):self.target(prepare=True)
        self.assertEqual(len(store.runs(self.root)),1)

    def test_same_target_names_correct_alternative_operations(self):
        with self.assertRaises(ProductionError) as caught:self.target(task='task.json',prepare=True)
        self.assertEqual(caught.exception.diagnostic.code,'RETARGET_NO_OP')
        self.assertEqual(len(store.runs(self.root)),1)

    def test_same_target_adopts_a_changed_runtime_with_lineage(self):
        import pack_manager
        import runtime_snapshot
        from catalog_retrieval import runtime
        path=self.case['pack']/'records/models.json';models=c.load(path)
        models['records'][0]['label']='Local synthetic image fixture, relabelled'
        f.write(path,models);pack_manager.write_lock(self.case['pack'])
        runtime.configure_pack_runtime(self.case['settings'])
        parent=workflow.load_run(self.root,self.run)[1]
        drift=runtime_snapshot.current_diagnostics(self.root,parent['runtime_snapshot'],run=self.run)
        self.assertEqual([row['code'] for row in drift],['PACK_CONTENT_MISMATCH'])
        self.assertEqual(drift[0]['actions'][-1]['operation'],'retarget')
        child=self.target(task='task.json',prepare=True)
        prepared=workflow.load_run(self.root,child['run'])[1]
        self.assertEqual(prepared['parent']['kind'],'retarget')
        self.assertEqual(prepared['parent']['changes'],[{'field':'runtime','before':parent['runtime_snapshot']['sha256'],
                                                        'after':prepared['runtime_snapshot']['sha256']}])
        self.assertEqual(runtime_snapshot.current_diagnostics(self.root,prepared['runtime_snapshot'],run=child['run']),[])
        self.assertEqual(store.event_rows(self.root,child['run']),[])

    def test_retarget_stays_within_its_work_task_and_series(self):
        from pack_manager import generate_uuid7
        path=f.alternate_task(self.root);task=c.load(self.root/path)
        task['production_id']=generate_uuid7();f.write(self.root/path,task)
        with self.assertRaises(ProductionError) as caught:self.target(prepare=True)
        self.assertEqual(caught.exception.diagnostic.code,'RETARGET_SCOPE_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.pointer,'$.production_id')

    def test_check_only_retarget_has_no_formal_side_effect(self):
        f.alternate_task(self.root)
        checked=self.target()
        self.assertTrue(checked['publishable'])
        self.assertFalse(checked['formal_run_created'])
        self.assertEqual(len(store.runs(self.root)),1)
        self.assertEqual(store.event_rows(self.root,self.run),[])

    def test_parent_decisions_do_not_authorize_new_target(self):
        from test_production_execution import decisions
        parent_decisions=decisions(self.root,self.run)
        f.alternate_task(self.root);child=self.target(prepare=True)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root,child['run'],decisions_file=parent_decisions)
        self.assertEqual(caught.exception.diagnostic.code,'AUTHORIZATION_MISMATCH')
        self.assertEqual(store.event_rows(self.root,child['run']),[])

    def test_retarget_resolves_new_current_runtime(self):
        import pack_manager
        from catalog_retrieval import runtime
        path=self.case['pack']/'records/models.json';models=c.load(path)
        model=models['records'][1]
        for profile in (model['execution_profile'],model['offerings'][0]['execution_profile']):
            profile['id']='synthetic-new-profile'
        f.write(path,models);pack_manager.write_lock(self.case['pack'])
        runtime.configure_pack_runtime(self.case['settings'])
        f.alternate_task(self.root);child=self.target(prepare=True)
        parent=workflow.load_run(self.root,self.run)[1];prepared=workflow.load_run(self.root,child['run'])[1]
        self.assertNotEqual(parent['runtime_snapshot']['sha256'],prepared['runtime_snapshot']['sha256'])
        self.assertEqual(c.load(Path(child['package']))['render_contract']['model_card']['execution_profile']['id'],'synthetic-new-profile')

    def test_public_cli_uses_explicit_runtime_from_another_cwd(self):
        f.alternate_task(self.root)
        script=Path(__file__).resolve().parent/'production_workflow.py';s=self.case['settings']
        argv=[sys.executable,str(script),'retarget','--root',str(self.root),'--from',self.run,'--task','retarget/task.json',
              '--reason','Synthetic target comparison.','--prepare','--state-file',str(s.state_file),'--cache-dir',str(s.cache_dir),
              '--managed-root',str(s.managed_root),'--pack-root',str(self.case['pack'])]
        completed=subprocess.run(argv,cwd=self.root.parent,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1',
                                 'CPB_HOME':str(production_fixtures.scratch_home_dir(self.base/'home'))},
                                 capture_output=True,text=True,encoding='utf-8',timeout=40)
        self.assertEqual(completed.returncode,0,completed.stderr+completed.stdout)
        value=json.loads(completed.stdout)
        self.assertEqual(value['execution_plan']['model'],f.ALTERNATE_MODEL_ID)
        self.assertFalse(value['authorization_inherited'])

    def test_upscale_target_change_uses_the_same_retarget_contract(self):
        case=f.create(self.base/'upscale studio',self.base/'upscale runtime',with_upscale=True,with_alternate_upscale=True)
        root=case['root'];parent_task=f.upscale_task(root);parent=workflow.prepare(root,parent_task)
        child_task=f.alternate_upscale_task(root)
        child=variation.retarget(root,parent['run'],child_task,reason='Explicit synthetic alternate upscaler comparison.',prepare=True)
        self.assertEqual(child['execution_plan']['model'],f.ALTERNATE_UPSCALE_MODEL_ID)
        self.assertEqual(child['execution_plan']['service'],'synthetic')
        self.assertIn('upscale-source',child['required_checks'])
        directory,prepared,_,rows=workflow.load_run(root,child['run'])
        self.assertEqual(prepared['parent']['kind'],'retarget');self.assertEqual(prepared['parent']['run'],parent['run']);self.assertEqual(rows,[])
        self.assertEqual(c.load(directory/'package.json')['artifact_type'],'upscale-request')

if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
