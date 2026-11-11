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
        environment = production_fixtures.scratch_home(self.base / 'home')
        environment.start();self.addCleanup(environment.stop)
        self.case=f.create(b/'日本語 studio',b/'runtime',with_alternate=True)
        self.root=self.case['root'];self.parent=workflow.prepare(self.root,'task.json');self.run=self.parent['run']

    def target(self,**kwargs):
        return variation.retarget(self.root,self.run,kwargs.pop('task','retarget/task.json'),
                                  reason='Explicit synthetic comparison of targets.',**kwargs)

    def editable_target(self):
        import production_inputs
        result = production_inputs.draft_inputs(self.root, None, 'editor', from_run=self.run,
                                               model=f.ALTERNATE_MODEL_ID, service='synthetic')
        return result, c.load(self.root / result['choices_file'])

    def reassess(self, choices):
        import request_validation
        import runtime_evidence
        f.alternate_task(self.root)
        choices['reading']['reading_key'] = c.load(self.root / 'retarget/reading.json')['reading_key']
        choices['validation'] = request_validation.draft_choices(
            c.load(self.root / 'retarget/validation.json'), runtime_evidence.reader(self.root))
        choices['authoring']['documents']['parameters']['steps'] = 22
        f.write(self.root / 'editor/choices.json', choices)

    def test_reopened_target_retains_authored_work_and_exposes_current_guidance(self):
        result, choices = self.editable_target()
        parent = workflow.read_run(self.root, self.run)
        self.assertEqual(choices['target'], {'kind': 'catalog', 'model': f.ALTERNATE_MODEL_ID, 'service': 'synthetic'})
        for field in ('criteria', 'direction', 'sources'):
            self.assertEqual(choices['authoring']['task'][field], parent.prepared['task'][field])
        self.assertEqual((self.root / choices['authoring']['delivery']['file']).read_text(encoding='utf-8'), f.PROMPT)
        original = parent.artifacts['package.json']['request_validation']
        self.assertEqual(choices['validation']['execution_policy'], original['execution_policy']['path'])
        self.assertEqual(choices['validation']['contract'], original['contract']['path'])
        self.assertEqual(choices['reading']['reading_key'], parent.prepared['route_reading']['reading_key'])
        gap = next(item for item in result['unresolved'] if item['code'] == 'TARGET_GUIDANCE_REQUIRED')
        self.assertEqual(gap['next_action']['args']['model'], f.ALTERNATE_MODEL_ID)
        self.assertEqual(result['target_knowledge']['model'], f.ALTERNATE_MODEL_ID)
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_editable_retarget_uses_current_evidence_and_preserves_parent_lineage(self):
        _, choices = self.editable_target()
        self.reassess(choices)
        child = variation.retarget(self.root, self.run, choices='editor/choices.json',
                                   reason='The synthetic author selected the alternate interface.', prepare=True)
        self.assertEqual(child['request_preview']['model'], 'synthetic:alternate')
        self.assertEqual(child['request_preview']['steps'], 22)
        loaded = workflow.read_run(self.root, child['run'])
        self.assertEqual(loaded.prepared['parent']['run'], self.run)
        self.assertEqual(loaded.prepared['parent']['kind'], 'retarget')
        self.assertEqual(loaded.prepared['task']['criteria'], self.case['task']['criteria'])
        self.assertEqual(loaded.artifacts['package.json']['production_spec']['target_model'], f.ALTERNATE_MODEL_ID)
        self.assertEqual(loaded.artifacts['package.json']['request_validation']['target']['model_identifier'], 'synthetic:alternate')
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_public_continuation_tracks_edited_targets_and_retains_the_parent(self):
        settings = self.case['settings']
        runtime = ['--state-file', str(settings.state_file.resolve()), '--cache-dir', str(settings.cache_dir.resolve()),
                   '--managed-root', str(settings.managed_root.resolve()), '--pack-root', str(self.case['pack'].resolve())]
        cli = [sys.executable, str(Path(__file__).resolve().parent / 'production_workflow.py')]
        environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
            'CPB_HOME': str(production_fixtures.scratch_home_dir(self.base / 'continuation-home'))}

        def invoke(argv):
            result = subprocess.run(argv, cwd=self.base, env=environment, capture_output=True,
                                    text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)

        def inspect_action():
            report = invoke([*cli, 'inspect-inputs', '--root', str(self.root), *runtime])
            current = next(row for row in report['inputs'] if row.get('current'))
            self.assertEqual(current['choices'], 'editor/choices.json')
            self.assertEqual(current['unresolved'], [], current)
            return next(action for action in current['next_actions']
                        if action.get('operation') in {'prepare', 'retarget'})

        parent = workflow.read_run(self.root, self.run)
        original_sources = {row['id']: (row, (self.root / row['path']).read_bytes())
                            for row in parent.prepared['task']['sources']}
        draft = invoke([*cli, 'draft-inputs', '--root', str(self.root), '--from-run', self.run,
                        '--out-dir', 'editor', *runtime])
        initial = next(action for action in draft['next_actions'] if action.get('operation') == 'prepare')
        self.assertNotIn('--from', initial['argv'])
        original = c.load(self.root / 'editor/choices.json')
        changed = copy.deepcopy(original)
        changed['target']['model'] = f.ALTERNATE_MODEL_ID
        self.reassess(changed)
        selected = inspect_action()
        self.assertEqual(selected['operation'], 'retarget')
        self.assertEqual(selected['args']['from'], self.run)
        self.assertEqual(selected['args']['reason'], '<retarget-reason>')
        self.assertTrue(selected['requires_author_input'])

        # Reopening recomputes guidance from current editable choices, including
        # their actual target-specific reading and validation evidence.
        f.write(self.root / 'editor/choices.json', original)
        self.assertEqual(inspect_action()['operation'], 'prepare')
        f.write(self.root / 'editor/choices.json', changed)
        selected = inspect_action()
        self.assertEqual(selected['operation'], 'retarget')
        argv = list(selected['argv'])
        self.assertEqual(argv[argv.index('--from') + 1], self.run)
        self.assertIn('--prepare', argv)
        for option in ('--state-file', '--cache-dir', '--managed-root', '--pack-root'):
            self.assertEqual(argv[argv.index(option) + 1], runtime[runtime.index(option) + 1])
        reason = 'Compare the explicitly selected alternate synthetic interface while retaining the source brief.'
        argv[argv.index('--reason') + 1] = reason
        child = invoke(argv)
        actual = workflow.read_run(self.root, child['run'])
        self.assertEqual(actual.prepared['parent']['run'], self.run)
        self.assertEqual(actual.prepared['parent']['kind'], 'retarget')
        self.assertEqual(actual.prepared['parent']['reason'], reason)
        self.assertEqual(actual.prepared['task']['criteria'], parent.prepared['task']['criteria'])
        self.assertEqual(child['request_preview']['model'], 'synthetic:alternate')
        self.assertEqual(child['request_preview']['prompt'], self.parent['request_preview']['prompt'])
        for source in actual.prepared['task']['sources']:
            original_source, raw = original_sources[source['id']]
            self.assertEqual({key: value for key, value in source.items() if key != 'path'},
                             {key: value for key, value in original_source.items() if key != 'path'})
            self.assertEqual((self.root / source['path']).read_bytes(), raw)
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_applicable_reopened_evidence_and_reading_produce_the_same_validation(self):
        import production_inputs
        parent = workflow.read_run(self.root, self.run)
        result = production_inputs.draft_inputs(self.root, None, 'unchanged', from_run=self.run)
        self.assertEqual(result['unresolved'], [])
        child = workflow.prepare(self.root, choices=result['choices_file'])
        actual = workflow.read_run(self.root, child['run'])
        self.assertEqual(actual.artifacts['package.json']['request_validation'], parent.artifacts['package.json']['request_validation'])
        self.assertEqual(actual.prepared['route_reading'], parent.prepared['route_reading'])
        self.assertEqual({key: value for key, value in child['request_preview'].items() if key != 'request_id'},
                         {key: value for key, value in self.parent['request_preview'].items() if key != 'request_id'})

    def test_restoration_reads_captured_validation_evidence(self):
        import production_inputs
        parent = workflow.read_run(self.root, self.run)
        validation = parent.artifacts['package.json']['request_validation']
        (self.root / validation['contract']['path']).unlink()
        (self.root / 'validation.json').unlink()
        result = production_inputs.draft_inputs(self.root, None, 'restored', from_run=self.run)
        self.assertEqual(result['choices']['validation']['contract'], validation['contract']['path'])
        self.assertEqual(result['choices']['validation']['execution_policy'], validation['execution_policy']['path'])
        self.assertEqual(result['choices']['authoring']['task']['criteria'], self.case['task']['criteria'])

    def test_selected_policy_reports_its_scope_when_the_target_changes(self):
        import production_inputs
        _, choices = self.editable_target()
        f.alternate_task(self.root)
        choices['reading']['reading_key'] = c.load(self.root / 'retarget/reading.json')['reading_key']
        f.write(self.root / 'editor/choices.json', choices)
        report = production_inputs.compile_choices(self.root, 'editor/choices.json').report
        problem = next(item for item in report['diagnostics'] if item['code'] == 'VALIDATION_POLICY_REQUIRED')
        self.assertEqual(problem['file'], choices['validation']['execution_policy'])
        self.assertIn('execution policy', problem['required_action'])
        self.assertEqual(len(store.runs(self.root)), 1)

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
        reading['documents'][0]['sha256']='0'*64
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
        from reading_fixtures import fixture_reading
        f.write(self.root/'reading.json',fixture_reading(route='generation',studio=self.root,
            ledger=self.root/'work/reads.jsonl',model=f.MODEL_ID,service='synthetic', execution='dispatcher'))
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


class ReferenceRetargetTests(unittest.TestCase):
    def test_reference_mode_switch_and_plain_prompt_retry_keep_authored_work(self):
        import production_inputs
        with tempfile.TemporaryDirectory(prefix='cpb-reference-retarget-') as temporary:
            base = Path(temporary)
            case = f.create(base / 'studio', base / 'runtime', with_alternate=True)
            root = case['root']
            scenario = f.reference_retarget_case(case)
            parent = scenario['parent']
            before = workflow.read_run(root, parent['run'])
            original_package = Path(parent['package']).read_bytes()
            authority = store.authority_record(root, before.prepared['task']['task_id'])
            inherited = scenario['inherited_choices']
            self.assertEqual(inherited['validation'], {'mode': 'target-schema', 'contract': None, 'evidence': None,
                'execution_policy': before.artifacts['package.json']['request_validation']['execution_policy']['path']})
            self.assertEqual(inherited['authoring']['task']['criteria'], before.prepared['task']['criteria'])
            self.assertEqual((root / inherited['authoring']['delivery']['file']).read_text(encoding='utf-8'), f.REFERENCE_RETRY_PROMPT)

            checked = production_inputs.compile_choices(root, scenario['choices_file']).report
            self.assertTrue(checked['publishable'], checked['diagnostics'])
            self.assertEqual(len(store.runs(root)), 1)
            child = variation.retarget(root, parent['run'], choices=scenario['choices_file'],
                reason='Compare explicitly selected synthetic reference operations.', prepare=True)
            after = workflow.read_run(root, child['run'])
            self.assertEqual(child['request_preview']['prompt'], f.REFERENCE_RETRY_PROMPT)
            self.assertEqual(child['request_preview']['steps'], 22)
            self.assertNotIn('seed', child['request_preview'])
            self.assertEqual(child['request_preview']['inputs']['references'], parent['request_preview']['inputs']['references'])
            for field in ('criteria', 'direction', 'task_id', 'production_id', 'authority'):
                self.assertEqual(after.prepared['task'][field], before.prepared['task'][field], field)
            for old, new in zip(before.prepared['task']['sources'], after.prepared['task']['sources'], strict=True):
                self.assertEqual({key: value for key, value in old.items() if key != 'path'},
                                 {key: value for key, value in new.items() if key != 'path'})
                self.assertEqual((root / old['path']).read_bytes(), (root / new['path']).read_bytes())
            self.assertEqual(after.prepared['identity_coverage'], before.prepared['identity_coverage'])
            self.assertEqual(after.prepared['parent']['run'], parent['run'])
            self.assertEqual(after.prepared['parent']['kind'], 'retarget')
            self.assertEqual(store.authority_record(root, before.prepared['task']['task_id']), authority)

            old_validation = before.artifacts['package.json']['request_validation']
            new_validation = after.artifacts['package.json']['request_validation']
            self.assertNotEqual(new_validation['contract'], old_validation['contract'])
            self.assertEqual(new_validation['target']['model_identifier'], 'synthetic:alternate')
            self.assertNotEqual(new_validation['offering_contract_sha256'], old_validation['offering_contract_sha256'])
            self.assertFalse(any(row['scope'] == '$.x-constraints[0]' for row in old_validation['unmeasured']))
            self.assertTrue(any(row['scope'] == '$.x-constraints[0]' for row in new_validation['unmeasured']))
            self.assertEqual(after.artifacts['package.json']['render_contract']['intent'], {
                'artifact_type': 'render-intent', 'execution_mode': 'instruction-edit'})

            # Reopen the new target, then edit only the ordinary prompt file.
            # The selected reference scope and independent review basis persist.
            draft = production_inputs.draft_inputs(root, None, 'reference-prompt-retry', from_run=child['run'])
            prompt = 'The blue robot carries a small yellow toolbox through an open doorway.'
            f.write(root / draft['choices']['authoring']['delivery']['file'], prompt)
            revised = workflow.prepare(root, choices=draft['choices_file'])
            revised_view = workflow.read_run(root, revised['run'])
            self.assertEqual(revised['request_preview']['prompt'], prompt)
            self.assertEqual(revised_view.prepared['task']['criteria'], before.prepared['task']['criteria'])
            self.assertEqual(revised_view.prepared['identity_coverage'], before.prepared['identity_coverage'])
            self.assertEqual(revised_view.artifacts['package.json']['request_validation'], new_validation)
            self.assertEqual(Path(parent['package']).read_bytes(), original_package)
            self.assertEqual(workflow.read_run(root, parent['run']).prepared, before.prepared)
            self.assertEqual(len(store.runs(root)), 3)
            for run in (parent['run'], child['run'], revised['run']):
                self.assertEqual(store.event_rows(root, run), [])

    def test_reference_delivery_without_an_execution_policy_asks_for_one(self):
        import production_inputs
        with tempfile.TemporaryDirectory(prefix='cpb-reference-policy-') as temporary:
            base = Path(temporary)
            case = f.create(base / 'studio', base / 'runtime', with_alternate=True)
            root = case['root']
            scenario = f.reference_retarget_case(case)
            choices = c.load(root / scenario['parent_choices_file'])
            for label, validation in (('the selected validation names no policy', {**choices['validation'], 'execution_policy': None}),
                                      ('no validation is selected', None)):
                with self.subTest(label):
                    f.write(root / scenario['parent_choices_file'], {**choices, 'validation': validation})
                    report = production_inputs.compile_choices(root, scenario['parent_choices_file']).report
                    self.assertFalse(report['publishable'])
                    problem = next(item for item in report['diagnostics'] if item['code'] == 'VALIDATION_POLICY_REQUIRED')
                    self.assertEqual(problem['phase'], 'request-validation-evidence')
                    self.assertIn('choices.validation.execution_policy', problem['required_action'])
            self.assertEqual(len(store.runs(root)), 1)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
