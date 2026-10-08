"""Input-derived variants and repeats of the current prepared-run contract."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import execution_contract as c
import production_case_fixtures as fixtures
import production_variation as variation
import production_workflow as workflow
import production_execution as execution
import production_store as store
from production_diagnostics import ProductionError, CompilationError


class VariationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        case = fixtures.create(base / 'studio', base / 'runtime')
        self.root = case['root']
        self.parent = workflow.prepare(self.root, 'task.json')
        self.run = self.parent['run']

    def change(self, values):
        fixtures.write(self.root / 'changes.json', {'changes': values, 'reason': 'Explicit synthetic input variation.'})
        return variation.derive(self.root, self.run, changes_file='changes.json', prepare=True)

    def test_parameter_variant_needs_no_candidate_or_claim(self):
        child = self.change({'parameter:steps': 22})
        self.assertNotEqual(child['run'], self.run)
        self.assertNotEqual(child['input_sha256'], self.parent['input_sha256'])
        self.assertEqual(child['request_preview']['steps'], 22)
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(store.event_rows(self.root, child['run']), [])
        a = workflow.load_run(self.root, self.run)[1]
        b = workflow.load_run(self.root, child['run'])[1]
        self.assertEqual(a['runtime_snapshot']['sha256'], b['runtime_snapshot']['sha256'])
        self.assertEqual(b['parent']['kind'], 'variant')
        self.assertEqual(b['parent']['basis'], [])

    def test_repeat_retains_input_but_has_its_own_run(self):
        child = variation.derive(self.root, self.run, prepare=True)
        self.assertNotEqual(child['run'], self.run)
        self.assertEqual(child['input_sha256'], self.parent['input_sha256'])
        self.assertEqual(child['execution_plan']['request_sha256'], self.parent['execution_plan']['request_sha256'])
        self.assertEqual(store.event_rows(self.root, child['run']), [])

    def test_unknown_field_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'arbitrary-internal-path': 'not permitted'})
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_UNKNOWN_FIELD')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_wrong_parameter_type_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 'twenty'})
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_TYPE_INVALID')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_no_op_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 20})
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_NO_OP')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_prompt_change_requires_real_retrieval_reassessment(self):
        with self.assertRaises(CompilationError) as caught:
            self.change({'prompt': fixtures.PROMPT + ' A small blue square sits on the ground.'})
        self.assertEqual(len(store.runs(self.root)), 1)
        self.assertIn('retrieval', str(caught.exception.report).lower())

    def test_prompt_change_with_explicit_reassessment(self):
        from prompt_retrieval import settle_retrieval_record
        prompt = fixtures.PROMPT + ' The same robot remains alone.'
        record = c.load(self.root / 'retrieval.json')
        # Authored by this test fixture; the runtime never creates this judgment.
        record = settle_retrieval_record(record, prompt=prompt, plot=c.load(self.root / 'plot.json'))
        fixtures.write(self.root / 'reassessed-retrieval.json', record)
        child = self.change({'prompt': prompt, 'retrieval-record': {'path': 'reassessed-retrieval.json'}})
        self.assertEqual(child['request_preview']['prompt'], prompt)

    def test_declared_task_fields_allow_reassessment_without_an_image(self):
        fields = self.parent['execution_plan']['mutable_fields']
        self.assertTrue({'direction','criteria','source-materials','route-reading',
                         'scene-materials','world-views','moment-views','features',
                         'state-lineage','state-snapshot'} <= set(fields))
        task = copy.deepcopy(workflow.load_run(self.root, self.run)[1]['task'])
        task['direction']['decisions'][0]['reason'] = 'An explicitly reassessed synthetic direction reason.'
        child = self.change({'direction': task['direction']})
        self.assertEqual(workflow.load_run(self.root, child['run'])[1]['task']['direction'], task['direction'])
        self.assertFalse(child['authorization_inherited'])

    def test_replaced_named_source_is_not_left_pointing_at_the_old_file(self):
        task = c.load(self.root/'task.json')
        task['sources'].append({'id':'intent-source','path':'creative-intent.json',
            'role':'intent','disposition':'applied','locator':'whole',
            'reason':'Synthetic authored intention source.'})
        fixtures.write(self.root/'source-task.json', task)
        self.run = workflow.prepare(self.root, 'source-task.json')['run']
        fixtures.write(self.root/'new-intent.json', {'image_promise':'Reassessed synthetic protocol demonstration.'})
        (self.root/'creative-intent.json').unlink()
        child = self.change({'creative-intent':{'path':'new-intent.json'}})
        prepared = workflow.load_run(self.root, child['run'])[1]
        self.assertEqual(next(x for x in prepared['task']['sources'] if x['id']=='intent-source')['path'], 'new-intent.json')
        self.assertNotIn('creative-intent.json', {d['path'] for d in prepared['dependencies'] if d['space']=='studio'})

    def test_repeat_mismatch_does_not_publish_a_run(self):
        import production_compiler as compiler
        original = compiler.compile_task
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            result.prepared['input_sha256'] = 'f'*64
            return result
        with patch.object(compiler, 'compile_task', side_effect=changed):
            with self.assertRaisesRegex(ProductionError, 'REPEAT_INPUT_MISMATCH'):
                variation.derive(self.root, self.run, prepare=True)
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_parent_decisions_cannot_authorize_repeat(self):
        from test_production_execution import decisions
        path = decisions(self.root, self.run)
        child = variation.derive(self.root, self.run, prepare=True)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, child['run'], decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(store.event_rows(self.root, child['run']), [])

    def test_missing_media_path_creates_no_run(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'references': {'path': 'missing-reference.json'}})
        diagnostic = caught.exception.diagnostic
        self.assertEqual((diagnostic.code, diagnostic.pointer, diagnostic.file),
                         ('CHANGES_PATH_INVALID', '$.changes.references.path', 'missing-reference.json'))
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_every_invalid_field_is_reported_at_once(self):
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 'twenty', 'arbitrary-internal-path': 1})
        rows = caught.exception.diagnostic.details['diagnostics']
        # The fixture writes keys in sorted order; problems follow the file order.
        self.assertEqual([(row['code'], row['pointer']) for row in rows],
                         [('CHANGES_UNKNOWN_FIELD', '$.changes.arbitrary-internal-path'),
                          ('CHANGES_TYPE_INVALID', '$.changes.parameter:steps')])
        self.assertEqual(caught.exception.diagnostic.code, 'CHANGES_UNKNOWN_FIELD')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_equal_json_in_the_same_directory_is_no_change(self):
        intent = c.load(self.root / 'creative-intent.json')
        (self.root / 'same-intent.json').write_text(json.dumps(intent, indent=4), encoding='utf-8')
        with self.assertRaises(ProductionError) as caught:
            self.change({'creative-intent': {'path': 'same-intent.json'}})
        self.assertEqual((caught.exception.diagnostic.code, caught.exception.diagnostic.pointer),
                         ('CHANGES_NO_OP', '$.changes.creative-intent'))

    def test_changes_from_stdin_equal_changes_from_a_file(self):
        value = {'changes': {'parameter:steps': 22}, 'reason': 'Explicit synthetic input variation.'}
        fixtures.write(self.root / 'changes.json', value)
        from_file = variation.derive(self.root, self.run, changes_file='changes.json')
        with patch('sys.stdin', io.TextIOWrapper(io.BytesIO(c.encoded(value)), encoding='utf-8')):
            from_stdin = variation.derive(self.root, self.run, changes_file='-')
        request = lambda result: {key: value for key, value in result['request_preview'].items() if key != 'request_id'}
        self.assertEqual(request(from_stdin), request(from_file))
        self.assertEqual(from_stdin['derivation']['changes'], from_file['derivation']['changes'])
        self.assertFalse(from_stdin['formal_run_created'])

    def test_target_fields_are_changed_by_retarget(self):
        specification = c.load(self.root / 'spec.json')
        specification['target_model'] = fixtures.ALTERNATE_MODEL_ID
        fixtures.write(self.root / 'other-spec.json', specification)
        for change, pointer in (({'model': fixtures.ALTERNATE_MODEL_ID}, '$.changes.model'),
                                ({'production-spec': {'path': 'other-spec.json'}}, '$.changes.production-spec.path')):
            with self.subTest(pointer=pointer):
                with self.assertRaises(ProductionError) as caught:
                    self.change(change)
                diagnostic = caught.exception.diagnostic
                self.assertEqual((diagnostic.code, diagnostic.pointer), ('TARGET_CHANGE_REQUIRED', pointer))
                self.assertIn('retarget --root', diagnostic.required_action)
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_transport_mode_change_is_revalidated_before_any_run(self):
        with self.assertRaises(CompilationError) as caught:
            self.change({'execution-mode': 'reference-guided'})
        self.assertIn('reference', json.dumps(caught.exception.report['diagnostics']).lower())
        self.assertEqual(len(store.runs(self.root)), 1)
        with self.assertRaises(ProductionError) as caught:
            self.change({'references': None})
        self.assertEqual((caught.exception.diagnostic.code, caught.exception.diagnostic.pointer),
                         ('CHANGES_NO_OP', '$.changes.references'))

    def test_observed_candidate_and_its_review_are_the_recorded_basis(self):
        from test_production_execution import decisions
        result = execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        candidate = result['runs'][0]['candidates'][0]
        review = workflow.draft_review(self.root, self.run, candidate)
        review.update(reviewer='Synthetic fixture reviewer - not user approval',
            observations=[{'evidence': 'candidate', 'locator': {'kind': 'whole'},
                'observation': 'The local fixture is a decoded 32 by 32 PNG.',
                'interpretation': 'Synthetic protocol assertion only; no model quality is assessed.',
                'limitations': ['Only the local fixture is examined.']}],
            checks=[{'criterion': 'output', 'verdict': 'pass', 'observation_indices': [0],
                     'reason': 'Explicit synthetic fixture decision.'}],
            conclusion='Synthetic fixture review.', unresolved=[])
        fixtures.write(self.root / 'review.json', review)
        recorded = workflow.review(self.root, self.run, 'review.json')
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Answer the reviewed synthetic candidate.'})
        child = variation.derive(self.root, self.run, changes_file='changes.json', prepare=True, candidates=[candidate])
        prepared = workflow.load_run(self.root, child['run'])[1]
        self.assertEqual(prepared['parent']['basis'], [{'candidate': candidate, 'review': recorded['sha256']}])

    def test_unknown_candidate_creates_no_input(self):
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Synthetic change.'})
        with self.assertRaises(ProductionError) as caught:
            variation.derive(self.root, self.run, changes_file='changes.json', prepare=True, candidates=['f' * 64])
        self.assertEqual(caught.exception.diagnostic.code, 'CANDIDATE_NOT_FOUND')
        self.assertFalse((self.root / 'production' / 'inputs').exists())
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_derived_inputs_are_published_inside_the_new_run(self):
        child = self.change({'parameter:steps': 22})
        prepared = workflow.load_run(self.root, child['run'])[1]
        prefix = f"production/runs/{child['run']}/inputs/"
        self.assertTrue(prepared['task_path'].startswith(prefix))
        owned = {d['path']: d['space'] for d in prepared['dependencies'] if d['path'].startswith(prefix)}
        self.assertEqual(owned, {prefix + 'task.json': 'task-source', prefix + 'parameters.json': 'task-source'})
        self.assertEqual(c.load(self.root / prefix / 'parameters.json')['steps'], 22)
        self.assertEqual(c.load(self.root / prefix / 'requested-changes.json')['changes'], {'parameter:steps': 22})
        workflow.assert_current(self.root, child['run'])
        repeated = variation.derive(self.root, child['run'], prepare=True)
        self.assertEqual(repeated['input_sha256'], child['input_sha256'])
        self.assertFalse((self.root / 'production' / 'inputs').exists())

    def test_unprepared_and_failed_derivations_leave_no_inputs(self):
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Synthetic check only.'})
        checked = variation.derive(self.root, self.run, changes_file='changes.json')
        self.assertIsNone(checked['run']);self.assertIsNone(checked['execution_plan']['run'])
        with self.assertRaises(CompilationError):
            self.change({'prompt': fixtures.PROMPT + ' A small blue square sits on the ground.'})
        self.assertFalse((self.root / 'production' / 'inputs').exists())
        self.assertEqual(len(store.runs(self.root)), 1)
        staged = [path for path in (self.root / 'production' / 'staging').iterdir() if (path / 'failure.json').is_file()]
        self.assertEqual(len(staged), 1)
        self.assertTrue((staged[0] / 'inputs' / 'prompt.txt').is_file())

    def test_a_run_without_references_gains_a_prepared_reference_set(self):
        from prepare_generation_references import prepare_references
        from transport_synthetic import _png
        c.atomic(self.root / 'variants/palette.png', _png(32, 32, b'\x50\x78\xa0'))
        references = prepare_references([{'role': 'palette', 'source': {'kind': 'supplied-file', 'reference_id': 'synthetic-palette',
            'resolved_path': str(self.root / 'variants/palette.png')}}], model=fixtures.MODEL_ID,
            output_dir=self.root / 'variants/reference-preparation')
        fixtures.write(self.root / 'variants/references.json', references)
        child = self.change({'references': {'path': 'variants/references.json'}, 'execution-mode': 'reference-guided'})
        self.assertEqual(len(child['request_preview']['inputs']['references']), 1)
        self.assertEqual(len(list(workflow.run_dir(self.root, child['run']).glob('package.*.references'))), 1)
        self.assertNotIn('inputs', self.parent['request_preview'])

    def test_changed_unreplaced_source_is_not_silently_reused(self):
        fixtures.write(self.root / 'creative-intent.json', {'image_promise': 'A different current author intent.'})
        with self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 22})
        self.assertEqual(caught.exception.diagnostic.code, 'SOURCE_CHANGED')

    def test_changed_installed_implementation_asks_for_a_new_preparation(self):
        import shutil
        installation = Path(self.temp.name) / 'installation'
        for source in workflow.load_run(self.root, self.run)[1]['dependencies']:
            if source['space'] == 'skill':
                target = installation / source['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(workflow.ROOT / source['path'], target)
        module = installation / 'scripts/production_compiler.py'
        module.write_bytes(module.read_bytes() + b'\n')
        with patch.object(workflow, 'ROOT', installation), self.assertRaises(ProductionError) as caught:
            self.change({'parameter:steps': 22})
        diagnostic = caught.exception.diagnostic
        self.assertEqual((diagnostic.code, diagnostic.phase, diagnostic.file),
                         ('IMPLEMENTATION_CHANGED', 'implementation', 'scripts/production_compiler.py'))
        self.assertEqual([row['run_id'] for row in store.runs(self.root)], [self.run])


class HierarchicalParameterTests(unittest.TestCase):
    def test_nested_control_is_changed_without_a_literal_dotted_key(self):
        import pack_manager
        original=fixtures.create_pack
        def nested(path,**kwargs):
            result=original(path,**kwargs);document=c.load(path/'records/models.json')
            for model in document['records']:
                for profile in [model['execution_profile'],*[offering['execution_profile'] for offering in model['offerings']]]:
                    for mode in profile['modes'].values():
                        control=mode['controls'].pop('settings')
                        control['schema']={'type':'integer','minimum':1,'maximum':10}
                        mode['controls']['settings.guidance']=control
            fixtures.write(path/'records/models.json',document);pack_manager.write_lock(path)
            return result
        with tempfile.TemporaryDirectory() as temporary,patch.object(fixtures,'create_pack',side_effect=nested):
            base=Path(temporary);root=fixtures.create(base/'studio',base/'runtime')['root']
            params=c.load(root/'parameters.json');params['settings']={'guidance':2};fixtures.write(root/'parameters.json',params)
            parent=workflow.prepare(root,'task.json')
            fixtures.write(root/'changes.json',{'changes':{'parameter:settings.guidance':3},'reason':'Synthetic nested control change.'})
            child=variation.derive(root,parent['run'],changes_file='changes.json',prepare=True)
            self.assertEqual(child['request_preview']['settings']['guidance'],3)
            self.assertNotIn('settings.guidance',child['request_preview'])
            self.assertEqual(parent['request_preview']['settings']['guidance'],2)
            self.assertEqual(store.event_rows(root,child['run']),[])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
