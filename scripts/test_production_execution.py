"""Current execution contract, with real local PNG bytes and no paid service."""
from __future__ import annotations
import copy
import io
import json
import os
import read_context
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_execution as execution
import production_operations as workflow
import production_store as store
import execution_lifecycle as accounting
import transport_synthetic
from production_diagnostics import ProductionError


def decisions(root: Path, run: str) -> str:
    from production_fixtures import ACTOR
    value = execution.draft_execution(root, run, 'fixture-grant')['choices']
    authority = store.authority(root, workflow.load_run(root, run)[1]['task']['task_id'])
    for request in value['decisions']:
        request['reason'] = 'Explicit synthetic fixture decision. Not user consent.'
        if request['operation'] == 'submit':
            request['request_decision']['principal_approval'] = {
                'path': authority['evidence']['path'], 'locator': authority['evidence']['locator']}
            from production_fixtures import assess_rendition
            assess_rendition(request['request_decision']['rendition_review'])
    path = f'decisions-{run}.json'
    fixtures.write(root / path, value)
    return path


class FixtureConstructionTests(unittest.TestCase):
    def test_complete_case_issues_one_selected_reading_and_binds_final_task(self):
        import production_fixtures
        import route_reading
        from catalog_retrieval import runtime

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        self.enterContext(patch.dict(os.environ))
        self.addCleanup(runtime.configure_pack_runtime, None)
        bound_tasks = []
        original_bind = production_fixtures.bind_work_basis

        def bind(root, task, **options):
            bound_tasks.append(copy.deepcopy(task))
            return original_bind(root, task, **options)

        with patch.object(route_reading, 'issue', wraps=route_reading.issue) as issue, \
                patch.object(production_fixtures, 'bind_work_basis', side_effect=bind) as binding:
            case = fixtures.create(base / 'studio', base / 'runtime', with_authority=False)

        self.assertEqual(issue.call_count, 1)
        self.assertEqual(binding.call_count, 1)
        root, task = case['root'], case['task']
        for field in ('generation', 'recording', 'authority', 'route_reading'):
            self.assertEqual(bound_tasks[0][field], task[field], field)
        self.assertEqual(bound_tasks[0]['direction']['decisions'], task['direction']['decisions'])
        self.assertEqual(bound_tasks[0]['direction']['decisions'][0]['expression'], 'flat graphic portrait')
        self.assertIsNone(task['authority'])
        self.assertEqual(task['route_reading'], 'reading.json')
        self.assertEqual(issue.call_args.kwargs['ledger'], root / 'work/reads.jsonl')
        record = c.load(root / task['route_reading'])
        self.assertEqual((record['model']['id'], record['model']['service']),
                         (fixtures.MODEL_ID, 'synthetic'))
        model = next(entry.record for entry in runtime.load_pack_catalog().entries
                     if entry.record.get('id') == fixtures.MODEL_ID)
        os.environ.pop('CPB_READS_LEDGER', None)
        row = route_reading.require_route_reading(record, studio=root, routes={'generation'},
            operation='prepare', execution='dispatcher', model_record=model, service='synthetic')
        self.assertEqual(row['key_sha256'], c.digest(record['reading_key'].encode('ascii')))
        (root / 'work/reads.jsonl').unlink()
        with self.assertRaisesRegex(ValueError, 'no issuance row'):
            route_reading.require_route_reading(record, studio=root)


class ExecutionTests(unittest.TestCase):
    @staticmethod
    def build(base):
        case = fixtures.create(base / 'studio', base / 'runtime')
        return case, {'run': workflow.prepare(case['root'], 'task.json')['run']}

    @classmethod
    def setUpClass(cls):
        cls._case_template = fixtures.CaseTemplate.for_class(cls, cls.build)

    def setUp(self):
        from production_compiler import published_preparation
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.case, metadata = fixtures.CaseTemplate.for_test(self, base, self.build, self._case_template)
        self.root = self.case['root']
        self.run = metadata['run']
        self.prepared = published_preparation(self.root, self.run)

    @fixtures.cold_case
    def test_execute_registers_candidate_and_records_results_once(self):
        result = execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(len(result['runs'][0]['candidates']), 1)
        recorded = accounting.summary(self.root)
        self.assertEqual((recorded['submissions'], recorded['captured_outputs']), (1, 1))
        self.assertEqual(recorded['reported_cost'], {'USD': '0'})
        self.assertEqual(recorded['executions'][0]['status'], 'complete')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Resume must not send')):
            again = execution.resume(self.root, self.run)
        self.assertEqual(len(again['runs'][0]['candidates']), 1)
        self.assertEqual(accounting.summary(self.root), recorded)

    def test_managed_batch_projects_prepared_and_captured_child_records(self):
        from build_batch_plan import project_managed_batch
        before=project_managed_batch(self.root,[self.run],label='Synthetic child group')
        self.assertEqual(before['summary']['submission'],{'unclaimed':1})
        self.assertEqual(before['summary']['captured_candidates'],0)
        plan=workflow.read_run(self.root,self.run).artifacts['execution-plan.json']
        self.assertEqual(before['jobs'][0]['model'],plan['model'])
        self.assertEqual(before['jobs'][0]['transport'],plan['transport'])
        execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        history=store.event_rows(self.root,self.run)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('Projection must not send')):
            report=project_managed_batch(self.root,[self.run])
        self.assertEqual(report['summary']['submission'],{'acknowledged':1})
        self.assertEqual(report['summary']['captured_candidates'],1)
        self.assertEqual(report['summary']['evaluation'],{'unreviewed':1})
        self.assertEqual(report['summary']['disposition'],{'pending':1})
        self.assertEqual(report['summary']['current_selections'],0)
        self.assertEqual(report['jobs'][0]['adoptions'],[])
        actual=next(row for row in history if row['event']=='candidate')
        self.assertEqual(report['jobs'][0]['candidates'][0]['captured_files'],actual['data']['files'])
        self.assertEqual(store.event_rows(self.root,self.run),history)

    def test_managed_batch_preserves_a_failed_attempt_and_an_unstarted_child(self):
        from build_batch_plan import project_managed_batch
        another=workflow.prepare(self.root,'task.json')['run']
        with patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic unknown send outcome')):
            execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        report=project_managed_batch(self.root,[self.run,another])
        self.assertEqual([row['run'] for row in report['jobs']],[self.run,another])
        self.assertEqual(report['summary']['submission'],{'outcome_unknown':1,'unclaimed':1})
        self.assertEqual(report['summary']['captured_candidates'],0)
        with self.assertRaisesRegex(ValueError,'repeats a child run'):
            project_managed_batch(self.root,[self.run,self.run])

    def test_managed_batch_cli_retains_every_output_from_one_child(self):
        from build_batch_plan import main
        from contextlib import redirect_stdout
        task=c.load(self.root/'task.json');task['generation']['count']=2
        fixtures.write(self.root/'two-output-task.json',task)
        run=workflow.prepare(self.root,'two-output-task.json')['run']
        execution.execute(self.root,run,decisions_file=decisions(self.root,run))
        target=self.root/'batch-report.json'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['project','--root',str(self.root),'--run',run,'--out',str(target)]),0)
        report=c.load(target)
        self.assertEqual(report['summary']['captured_candidates'],2)
        self.assertEqual(report['jobs'][0]['planned_outputs'],2)
        self.assertEqual(len(report['jobs'][0]['candidates']),2)
        self.assertEqual(report['summary']['evaluation'],{'unreviewed':2})


    def test_missing_authority_has_no_execution_claim(self):
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_REQUIRED')
        self.assertEqual(store.event_rows(self.root, self.run), [])
        self.assertEqual(accounting.all_states(self.root), [])
        # The dispatch journal is written at the claim boundary, so a refused execute leaves none.
        self.assertEqual([path for path in (self.root / 'runs').glob('*') if path.is_dir()], [])

    def test_missing_direction_does_not_commit_submission(self):
        path = decisions(self.root, self.run)
        value = c.load(self.root / path)
        value['decisions'] = value['decisions'][1:]
        fixtures.write(self.root / path, value)
        with self.assertRaises(ProductionError):
            execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(store.event_rows(self.root, self.run), [])

    def test_incomplete_whole_input_assessment_cannot_authorize_a_send(self):
        path = decisions(self.root, self.run)
        value = c.load(self.root / path)
        submit = next(row for row in value['decisions'] if row['operation'] == 'submit')
        review = submit['request_decision']['rendition_review']
        self.assertEqual(value['request_sha256'], execution.compiled(self.root, self.run)[6]['request_sha256'])
        complete = copy.deepcopy(review)
        for change in ('missing-criterion', 'unmeasured-ownership',
                       'not-satisfied', 'unmeasured', 'different-input'):
            with self.subTest(change=change):
                altered = copy.deepcopy(complete)
                if change == 'missing-criterion':
                    altered['assessments'].pop()
                elif change == 'unmeasured-ownership':
                    next(item for item in altered['assessments'] if item['criterion'] == 'ownership')['conclusion'] = 'unmeasured'
                elif change in {'not-satisfied', 'unmeasured'}:
                    assessment = next(item for item in altered['assessments'] if item['criterion'] == 'finished-image')
                    assessment.update(conclusion=change,
                        reason='Synthetic reviewer leaves the same-subject action conflict unresolved.')
                else:
                    value['input_sha256'] = '0' * 64
                submit['request_decision']['rendition_review'] = altered
                fixtures.write(self.root / path, value)
                with patch.object(transport_synthetic, 'send') as send:
                    with self.assertRaises(ValueError):
                        execution.execute(self.root, self.run, decisions_file=path)
                    send.assert_not_called()
                self.assertEqual(store.event_rows(self.root, self.run), [])
                self.assertEqual(accounting.all_states(self.root), [])


    def test_timeout_retains_execution_and_resume_never_sends(self):
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic timeout')) as send:
            result = execution.execute(self.root, self.run, decisions_file=path)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(result['runs'][0]['submission'], 'outcome_unknown')
        state = accounting.all_states(self.root)[0]
        self.assertEqual(state['status'], 'started')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            again = execution.resume(self.root, self.run)
        self.assertEqual(again['runs'][0]['submission'], 'outcome_unknown')
        self.assertEqual(len(accounting.all_states(self.root)), 1)
        # The synthetic service never received the request, so its lookup has no answer.
        asked = [row['data'] for row in store.event_rows(self.root, self.run)
                 if row['event'] == 'execution-outcome' and row['data'].get('lookup')]
        self.assertEqual([item['lookup'] for item in asked], ['no-answer'])
        self.assertTrue(asked[0]['evidence'][0]['path'].endswith('/lookup-001.json'))
        self.assertEqual(again['runs'][0]['next_action']['command'], 'draft-outcome')

    def lost_answer(self):
        """A send the synthetic service carried out, whose answer never reached the dispatcher."""
        actual = transport_synthetic.send
        def lose(request, service, key):
            actual(request, service, key)
            raise TimeoutError('Synthetic answer loss after the service carried out the request')
        return lose

    def test_lost_answer_is_reconciled_through_provider_lookup(self):
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=self.lost_answer()) as send:
            first = execution.execute(self.root, self.run, decisions_file=path)
            self.assertEqual(first['runs'][0]['submission'], 'outcome_unknown')
            again = execution.resume(self.root, self.run)
            self.assertEqual(send.call_count, 1)
        item = again['runs'][0]
        self.assertTrue(again['execution_completed'])
        self.assertEqual((item['submission'], item['capture'], item['registration']), ('acknowledged', 'complete', 'registered'))
        self.assertEqual(len(item['candidates']), 1)
        receipt = [row['data'] for row in store.event_rows(self.root, self.run)
                   if row['event'] == 'execution-outcome' and row['data']['submission'] == 'acknowledged']
        self.assertEqual([row['reconciled'] for row in receipt], ['provider-lookup'])
        names = {entry['path'].rsplit('/', 1)[1] for entry in receipt[0]['evidence']}
        self.assertTrue({'request.json', 'lookup-001.json', 'answer.json', 'transport-outcome.json'} <= names)
        self.assertEqual(accounting.summary(self.root)['submissions'], 1)

    def test_evidenced_not_executed_statement_allows_a_new_approved_run(self):
        path = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic timeout')):
            execution.execute(self.root, self.run, decisions_file=path)
        execution.resume(self.root, self.run)
        statement = execution.draft_outcome(self.root, self.run)
        fixtures.write(self.root / 'provider-task-list.txt', 'Synthetic provider task export: no task with this identifier.\n')
        authority = store.authority(self.root, workflow.load_run(self.root, self.run)[1]['task']['task_id'])
        statement.update(actor=authority['issuer'], reason='The provider task list holds no task for this request.',
                         evidence={'path': 'provider-task-list.txt', 'sha256': c.sha256_file(self.root / 'provider-task-list.txt'),
                                   'locator': 'whole export'})
        fixtures.write(self.root / 'outcome.json', statement)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            result = execution.resume(self.root, self.run, outcome_file='outcome.json')
        item = result['runs'][0]
        self.assertEqual(item['submission'], 'not_executed')
        self.assertEqual(item['effects'], [{'step': 'send', 'operation': 'send', 'result': 'not_executed'}])
        self.assertEqual(item['execution']['status'], 'started')
        self.assertEqual(item['next_action']['command'], 'repeat')
        self.assertEqual(accounting.summary(self.root)['submissions'], 1)

    def test_send_boundary_records_provider_identifiers_before_io(self):
        execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        rows = store.event_rows(self.root, self.run)
        send = next(row['data'] for row in rows if row['event'] == 'external-step' and row['data']['step'] == 'send')
        claim = workflow.find(rows, 'dispatch-claim')
        request = c.load(c.local(self.root, claim['data']['journal']) / 'request.json')
        self.assertEqual(send['identifiers'], [{'field': ['request_id'], 'value': request['request_id']}])
        outcome = next(row['data'] for row in rows if row['event'] == 'execution-outcome')
        self.assertIn('transport-outcome.json', {entry['path'].rsplit('/', 1)[1] for entry in outcome['evidence']})

    def test_interruption_before_send_boundary_is_claimed_not_unknown(self):
        begin = accounting.begin_step
        def interrupt(*args, **kwargs):
            if kwargs['step'] == 'send':
                raise OSError('Synthetic interruption before the durable send boundary')
            return begin(*args, **kwargs)
        with patch.object(accounting, 'begin_step', side_effect=interrupt), patch.object(transport_synthetic, 'send') as send:
            with self.assertRaises(OSError):
                execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
            send.assert_not_called()
        item = execution.status(self.root, self.run)['runs'][0]
        self.assertEqual((item['submission'], item['send_started']), ('claimed', False))
        self.assertEqual(workflow.find(store.event_rows(self.root, self.run), 'execution-outcome')['data']['submission'], 'claimed')
        self.assertEqual(item['next_action']['command'], 'resume')
        self.assertTrue(execution.resume(self.root, self.run)['execution_completed'])

    def test_send_in_progress_is_send_started(self):
        seen = []
        actual = transport_synthetic.send
        def observe(request, service, key):
            seen.append(execution.status(self.root, self.run)['runs'][0]['submission'])
            return actual(request, service, key)
        with patch.object(transport_synthetic, 'send', side_effect=observe):
            execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertEqual(seen, ['send_started'])

    def test_saved_answer_without_receipt_is_unknown_until_resume_registers_it(self):
        acknowledge = execution._acknowledge
        with patch.object(execution, '_acknowledge', side_effect=OSError('Synthetic receipt storage failure')):
            with self.assertRaises(OSError):
                execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        # The saved answer file alone is not a formal acknowledgement.
        self.assertEqual(execution.status(self.root, self.run)['runs'][0]['submission'], 'outcome_unknown')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')), \
                patch.object(execution, '_acknowledge', side_effect=acknowledge):
            result = execution.resume(self.root, self.run)
        self.assertTrue(result['execution_completed'])
        receipt = [row['data'] for row in store.event_rows(self.root, self.run)
                   if row['event'] == 'execution-outcome' and row['data']['submission'] == 'acknowledged']
        self.assertEqual([row['reconciled'] for row in receipt], ['saved-answer'])

    def test_duplicate_execute_is_not_repeat(self):
        path = decisions(self.root, self.run)
        execution.execute(self.root, self.run, decisions_file=path)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'DISPATCH_ALREADY_CLAIMED')

    def test_saved_response_recovered_after_candidate_transaction_failure(self):
        path = decisions(self.root, self.run)
        with patch.object(workflow, 'record_dispatch_results', side_effect=OSError('Synthetic disk error')):
            with self.assertRaises(OSError):
                execution.execute(self.root, self.run, decisions_file=path)
        self.assertFalse(any(row['event'] == 'candidate' for row in store.event_rows(self.root, self.run)))
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No retransmission')):
            result = execution.resume(self.root, self.run)
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(len(result['runs'][0]['candidates']), 1)



    def test_invalid_upscale_dimensions_are_captured_but_not_completed(self):
        import base64
        base = Path(self.temp.name)
        case = fixtures.create(base / 'upscale-studio', base / 'upscale-runtime', with_upscale=True)
        root = case['root']
        task = fixtures.upscale_task(root)
        prepared = workflow.prepare(root, task)
        run = prepared['run']
        path = decisions(root, run)
        original_send = transport_synthetic.send

        def malformed(request, service, key):
            answer = original_send(request, service, key)
            # Source is 32x32 and scale=2, so the contract requires 64x64.
            answer['data'][0]['data'] = base64.b64encode(
                transport_synthetic._png(61, 64, b'\x70\x40\x20')
            ).decode('ascii')
            return answer

        with patch.object(transport_synthetic, 'send', side_effect=malformed):
            result = execution.execute(root, run, decisions_file=path)
        self.assertFalse(result['ok'])
        self.assertFalse(result['execution_completed'])
        self.assertEqual(result['runs'][0]['capture'], 'complete')
        self.assertEqual(len(result['runs'][0]['candidates']), 1)
        self.assertIn('UPSCALE_OUTPUT_CONTRACT_MISMATCH', {item['code'] for item in result['warnings']})
        claim = workflow.find(store.event_rows(root, run), 'dispatch-claim')
        journal = c.local(root, claim['data']['journal']) / 'run.json'
        self.assertEqual(c.load(journal)['status'], 'capture-invalid')
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('Resume must not send')):
            again = execution.resume(root, run)
        self.assertFalse(again['execution_completed'])
        self.assertEqual(len(again['runs'][0]['candidates']), 1)

    def test_revocation_does_not_mutate_input(self):
        path = decisions(self.root, self.run)
        original = workflow.load_run(self.root, self.run)[1]['input_sha256']
        document = c.load(self.root / 'fixture-authority.json')
        document['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        fixtures.write(self.root / 'authority-update.json', document)
        prior = store.authority_record(self.root, document['task_id'])
        store.import_authority(self.root, 'authority-update.json', expected=prior['sha256'])
        self.assertEqual(workflow.assert_current(self.root, self.run)[1]['input_sha256'], original)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=path)
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_REVOKED')
        self.assertEqual(accounting.all_states(self.root), [])



class ExternalEffectAccountingTests(unittest.TestCase):
    """Local fixture fees verify actual per-effect accounting, never provider billing."""
    @staticmethod
    def build(base):
        case = fixtures.create(base / 'studio', base / 'runtime', with_upscale=True)
        return case, {}

    @classmethod
    def setUpClass(cls):
        cls._case_template = fixtures.CaseTemplate.for_class(cls, cls.build)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        case, _ = fixtures.CaseTemplate.for_test(self, base, self.build, self._case_template)
        self.root=case['root']
        # The sealed request names private source-media paths in this Studio.
        self.task_path=fixtures.upscale_task(self.root)
        self.run=workflow.prepare(self.root,self.task_path)['run']
        self.decision=decisions(self.root,self.run)
        self.original_upload=transport_synthetic.upload_media
        self.original_send=transport_synthetic.send

    def uploader(self,amount='0.1'):
        def upload(*args,**kwargs):
            value=self.original_upload(*args,**kwargs)
            value['usage']=None if amount is None else {'currency':'USD','amount':amount,'final':True}
            value['response']['synthetic_charge']=value['usage']
            return value
        return upload

    def sender(self,amount='0.3'):
        def send(*args,**kwargs):
            value=self.original_send(*args,**kwargs)
            value['usage']=None if amount is None else {'currency':'USD','amount':amount,'final':True}
            return value
        return send

    def recorded(self):
        return accounting.summary(self.root)

    @fixtures.cold_case
    def test_upload_and_send_actuals_are_added_once(self):
        with patch.object(transport_synthetic,'upload_media',side_effect=self.uploader()),patch.object(transport_synthetic,'send',side_effect=self.sender()):
            execution.execute(self.root,self.run,decisions_file=self.decision)
        group=self.recorded()
        self.assertEqual(group['reported_cost'],{'USD':'0.4'})
        self.assertTrue(group['usage_complete'])
        self.assertEqual(group['submissions'],1)
        self.assertEqual(len(group['executions'][0]['effect_results']),3)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No repeat send')),patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('No repeat upload')):
            execution.resume(self.root,self.run)
        self.assertEqual(self.recorded()['reported_cost'],group['reported_cost'])

    def test_unknown_upload_charge_is_not_zero_when_send_cost_is_known(self):
        with patch.object(transport_synthetic,'upload_media',side_effect=self.uploader(None)),patch.object(transport_synthetic,'send',side_effect=self.sender()):
            execution.execute(self.root,self.run,decisions_file=self.decision)
        group=self.recorded()
        self.assertEqual(group['reported_cost'],{'USD':'0.3'})
        self.assertFalse(group['usage_complete'])
        self.assertEqual(group['executions'][0]['status'],'complete')
        self.assertEqual(group['captured_outputs'],1)

    def test_known_upload_fee_survives_send_timeout(self):
        with patch.object(transport_synthetic,'upload_media',side_effect=self.uploader()),patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic send timeout')):
            result=execution.execute(self.root,self.run,decisions_file=self.decision)
        self.assertEqual(result['runs'][0]['submission'],'outcome_unknown')
        group=self.recorded()
        self.assertEqual(group['reported_cost'],{'USD':'0.1'})
        self.assertFalse(group['usage_complete'])
        self.assertEqual(group['submissions'],1)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No repeat send')),patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('No repeat upload')):
            execution.resume(self.root,self.run)


    def test_completed_upload_is_reused_when_send_never_started(self):
        begin=accounting.begin_step
        def interrupt(*args,**kwargs):
            if kwargs['step']=='send':
                raise OSError('Synthetic interruption before the durable send boundary')
            return begin(*args,**kwargs)
        with patch.object(transport_synthetic,'upload_media',side_effect=self.uploader()) as upload,patch.object(accounting,'begin_step',side_effect=interrupt):
            with self.assertRaises(OSError):
                execution.execute(self.root,self.run,decisions_file=self.decision)
        self.assertEqual(upload.call_count,1)
        item=execution.status(self.root,self.run)['runs'][0]
        self.assertEqual(item['submission'],'claimed')
        self.assertEqual(item['effects'],[{'step':'upload:0','operation':'upload','result':'executed'}])
        with patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('Do not upload twice')),patch.object(transport_synthetic,'send',side_effect=self.sender()) as send:
            result=execution.resume(self.root,self.run)
        self.assertEqual(send.call_count,1)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(self.recorded()['reported_cost'],{'USD':'0.4'})

    def test_upload_and_send_keep_owned_runtime_and_new_audit_detects_archive_damage(self):
        import runtime_snapshot
        import request_contract as rc
        descriptor=workflow.read_run(self.root,self.run).prepared['runtime_snapshot']
        rendered=execution.compiled(self.root,self.run)[5]
        directory=runtime_snapshot.path(self.root,descriptor)
        snapshot=c.load(directory/'snapshot.json')
        pack,relative=sorted((pack['pack_id'],item['path']) for pack in snapshot['packs'] for item in pack['files'])[0]
        member=directory/'packs'/pack/relative
        original=member.read_bytes()
        upload=self.uploader()
        sender=self.sender()
        media_bytes=Path(rendered['media'][0]['path']).read_bytes()
        uploaded={}

        def upload_then_change_archive(*args,**kwargs):
            self.assertEqual(args[0],media_bytes)
            result=upload(*args,**kwargs)
            uploaded[0]=result['provider_id']
            member.write_bytes(original+b'\n')
            return result

        def send_owned_request(*args,**kwargs):
            self.assertIs(runtime_snapshot.acquire_runtime(directory,descriptor),owned)
            self.assertEqual(owned.read_pack(pack,relative),original)
            expected=rc.materialize(rendered,uploaded)
            # Only the declared per-request identifiers are assigned at send.
            for field in rendered['layout']['management']:
                rc.put(expected,field,rc.get(args[0],field))
            self.assertEqual(args[0],expected)
            return sender(*args,**kwargs)

        with read_context.public_call():
            owned=runtime_snapshot.acquire_runtime(directory,descriptor)
            with patch.object(transport_synthetic,'upload_media',side_effect=upload_then_change_archive) as upload_call, \
                    patch.object(transport_synthetic,'send',side_effect=send_owned_request) as send:
                result=execution.execute(self.root,self.run,decisions_file=self.decision)
            self.assertTrue(result['execution_completed'],result)
            self.assertEqual((upload_call.call_count,send.call_count),(1,1))
            self.assertEqual(owned.read_pack(pack,relative),original)
            with self.assertRaises(ProductionError) as caught:
                runtime_snapshot.acquire_runtime(directory,descriptor,force_verify=True)
            self.assertEqual(caught.exception.diagnostic.code,'RUNTIME_SNAPSHOT_CORRUPT')
        rows=store.event_rows(self.root,self.run)
        claim=workflow.find(rows,'dispatch-claim')
        journal=self.root/claim['data']['journal']
        receipt_path=journal/'upload-001.json'
        receipt_bytes=receipt_path.read_bytes()
        receipt=c.decode(receipt_bytes)
        self.assertTrue(receipt['response']['synthetic'])
        self.assertEqual(receipt['provider_id'],receipt['response']['media_id'])
        self.assertEqual(receipt['usage'],{'currency':'USD','amount':'0.1','final':True})
        steps=[row['data']['step'] for row in rows if row['event']=='external-step']
        self.assertEqual((steps.count('upload:0'),steps.count('send')),(1,1))
        effects=[row['data'] for row in rows if row['event']=='external-effect-result']
        self.assertEqual(len(effects),3)
        upload_effect=next(item for item in effects if item['step']=='upload:0')
        self.assertEqual(upload_effect['evidence'][0]['sha256'],c.digest(receipt_bytes))
        self.assertTrue((journal/'answer.json').exists())
        recorded=self.recorded()
        self.assertEqual(recorded['reported_cost'],{'USD':'0.4'})
        self.assertEqual((recorded['submissions'],recorded['captured_outputs']),(1,1))

        with read_context.public_call(), self.assertRaises(ProductionError) as audited:
            workflow.assert_current(self.root,self.run)
        self.assertEqual(audited.exception.diagnostic.code,'RUNTIME_SNAPSHOT_CORRUPT')
        self.assertEqual(receipt_path.read_bytes(),receipt_bytes)
        self.assertEqual(self.recorded(),recorded)

    def test_refused_upload_is_recorded_and_requires_new_approval(self):
        import transport_contract
        refusal=transport_contract.Refused('Synthetic refusal of the upload',{'errors':[{'code':'synthetic-upload-refused'}]})
        with patch.object(transport_synthetic,'upload_media',side_effect=refusal),patch.object(transport_synthetic,'send') as send:
            result=execution.execute(self.root,self.run,decisions_file=self.decision)
            send.assert_not_called()
        self.assertFalse(result['execution_completed'])
        item=result['runs'][0]
        self.assertEqual(item['submission'],'claimed')
        self.assertEqual(item['effects'],[{'step':'upload:0','operation':'upload','result':'rejected'}])
        self.assertEqual(item['execution']['status'],'started')
        self.assertEqual(item['next_action']['command'],'repeat')
        outcome=workflow.find(store.event_rows(self.root,self.run),'execution-outcome')['data']
        self.assertEqual((outcome['submission'],outcome['code']),('claimed','PROVIDER_REJECTION'))
        self.assertTrue(outcome['evidence'][0]['path'].endswith('/upload-001-refused.json'))
        self.assertEqual(self.recorded()['reported_cost'],{})

    def unanswered_upload(self):
        """Execute with an upload whose exchange ends without an answer, and return the diagnostic."""
        with patch.object(transport_synthetic,'upload_media',side_effect=TimeoutError('Synthetic upload timeout')):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run,decisions_file=self.decision)
        return caught.exception.diagnostic

    def test_unanswered_upload_is_reported_and_never_reissued(self):
        first=self.unanswered_upload()
        self.assertEqual((first.code,first.details['steps']),('REMOTE_OUTCOME_UNKNOWN',['upload:0']))
        self.assertIn('Synthetic upload timeout',first.details['cause'])
        rows=store.event_rows(self.root,self.run)
        self.assertEqual([(row['data']['submission'],row['data']['code']) for row in rows if row['event']=='execution-outcome'],
                         [('claimed','REMOTE_OUTCOME_UNKNOWN')])
        journal=c.local(self.root,workflow.find(rows,'dispatch-claim')['data']['journal'])
        self.assertEqual(c.load(journal/'upload-001-indeterminate.json'),
                         {'outcome':'indeterminate','reason':'the upload ended without a provider answer (TimeoutError)',
                          'http_status':None,'body':None})
        item=execution.status(self.root,self.run)['runs'][0]
        self.assertEqual(item['submission'],'claimed')
        self.assertEqual(item['effects'],[{'step':'upload:0','operation':'upload','result':'unanswered'}])
        self.assertEqual(item['next_action']['command'],'repeat')
        self.assertFalse(item['authentication']['required'])
        for attempt in range(2):
            with patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('No repeated upload')),patch.object(transport_synthetic,'send',side_effect=AssertionError('No send after unknown upload')):
                with self.assertRaises(ProductionError) as caught:
                    execution.resume(self.root,self.run)
            diagnostic=caught.exception.diagnostic
            self.assertEqual((diagnostic.code,diagnostic.details['steps']),('REMOTE_OUTCOME_UNKNOWN',['upload:0']))
            self.assertIn('repeat --from '+self.run+' --prepare',diagnostic.required_action)
            self.assertEqual(diagnostic.details['next_action'],item['next_action'])
        self.assertEqual(store.event_rows(self.root,self.run),rows)
        self.assertEqual(self.recorded()['executions'][0]['status'],'started')
        self.assertEqual(self.recorded()['submissions'],0)

    def test_unanswered_upload_keeps_what_the_exchange_returned(self):
        import transport_contract
        # A storage answer whose stored bytes could not be verified still names the identifier it issued.
        body=b'{"data":[{"taskType":"mediaStorage","mediaUUID":"be012743-84d6-4e79-8bfb-cff57e622e1b"}]}'
        unknown=transport_contract.Indeterminate(
            'the upload returned an identifier but stored content verification failed (ValueError)',status=200,body=body)
        with patch.object(transport_synthetic,'upload_media',side_effect=unknown):
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root,self.run,decisions_file=self.decision)
        diagnostic=caught.exception.diagnostic
        rows=store.event_rows(self.root,self.run)
        base=workflow.find(rows,'dispatch-claim')['data']['journal']
        saved=c.local(self.root,base)/'upload-001-indeterminate.json'
        self.assertEqual(c.load(saved),{'outcome':'indeterminate','reason':unknown.reason,'http_status':200,
                                        'body':body.decode('utf-8')})
        self.assertEqual(diagnostic.details['evidence'],[base+'/upload-001-indeterminate.json'])
        self.assertIn(base+'/upload-001-indeterminate.json',diagnostic.required_action)
        # The stop record names the unknown upload and keeps the exchange's evidence in the run.
        stopped=workflow.find(rows,'execution-outcome')['data']
        self.assertEqual((stopped['code'],stopped['unknown_uploads']),('REMOTE_OUTCOME_UNKNOWN',['upload:0']))
        self.assertEqual([item['path'] for item in stopped['evidence']],[base+'/upload-001-indeterminate.json'])
        self.assertEqual(c.object_read(workflow.run_dir(self.root,self.run),stopped['evidence'][0]['sha256']),saved.read_bytes())
        with patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('No repeated upload')):
            with self.assertRaises(ProductionError) as again:
                execution.resume(self.root,self.run)
        self.assertEqual(again.exception.diagnostic.details['evidence'],[base+'/upload-001-indeterminate.json'])
        self.assertEqual(store.event_rows(self.root,self.run),rows)

    def test_outcome_statement_without_a_send_names_the_continuation_of_the_run(self):
        statement=lambda run:fixtures.write(self.root/'outcome.json',execution.draft_outcome(self.root,run))
        begin=accounting.begin_step
        def interrupt(*args,**kwargs):
            if kwargs['step']=='send':
                raise OSError('Synthetic interruption before the durable send boundary')
            return begin(*args,**kwargs)
        with patch.object(accounting,'begin_step',side_effect=interrupt):
            with self.assertRaises(OSError):
                execution.execute(self.root,self.run,decisions_file=self.decision)
        another=workflow.prepare(self.root,self.task_path)['run']
        with patch.object(transport_synthetic,'upload_media',side_effect=TimeoutError('Synthetic upload timeout')):
            with self.assertRaises(ProductionError):
                execution.execute(self.root,another,decisions_file=decisions(self.root,another))
        unsent=workflow.prepare(self.root,self.task_path)['run']
        for run,command in ((self.run,'resume'),(another,'repeat'),(unsent,'draft-execution')):
            with self.subTest(command=command):
                if run==unsent:
                    # No claim exists yet, so no statement can be drafted; the refusal does not read the file.
                    fixtures.write(self.root/'outcome.json',{'run':run,'outcome':'not_executed'})
                else:
                    statement(run)
                rows=store.event_rows(self.root,run)
                with patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('No upload')), \
                        patch.object(transport_synthetic,'send',side_effect=AssertionError('No send')):
                    with self.assertRaises(ProductionError) as caught:
                        execution.resume(self.root,run,outcome_file='outcome.json')
                diagnostic=caught.exception.diagnostic
                action=execution.status(self.root,run)['runs'][0]['next_action']
                self.assertEqual((diagnostic.code,action['command']),('OUTCOME_STATEMENT_NOT_APPLICABLE',command))
                self.assertEqual(diagnostic.details['next_action'],action)
                self.assertIn(action['reason'],diagnostic.required_action)
                self.assertEqual(store.event_rows(self.root,run),rows)

    def test_unanswered_upload_continues_with_a_newly_prepared_run(self):
        import production_variation
        self.unanswered_upload()
        action=execution.status(self.root,self.run)['runs'][0]['next_action']
        self.assertEqual(action['argv'][-3:],['--from',self.run,'--prepare'])
        child=production_variation.derive(self.root,self.run,prepare=True)['run']
        self.assertEqual(execution.status(self.root,child)['runs'][0]['submission'],'unclaimed')
        with patch.object(transport_synthetic,'upload_media',side_effect=self.uploader()) as upload,patch.object(transport_synthetic,'send',side_effect=self.sender()) as send:
            result=execution.execute(self.root,child,decisions_file=decisions(self.root,child))
        self.assertTrue(result['execution_completed'])
        self.assertEqual((upload.call_count,send.call_count),(1,1))
        self.assertEqual(execution.status(self.root,self.run)['runs'][0]['next_action']['command'],'repeat')

    def test_upload_still_in_progress_is_not_reported_as_unknown(self):
        # No stop is recorded while the owner operation runs; this process is that operation.
        with patch.object(execution,'_record_execution_failure'):
            with patch.object(transport_synthetic,'upload_media',side_effect=TimeoutError('Synthetic upload timeout')):
                with self.assertRaises(ProductionError):
                    execution.execute(self.root,self.run,decisions_file=self.decision)
        action=execution.status(self.root,self.run)['runs'][0]['next_action']
        self.assertEqual(action['command'],'status')
        self.assertIn('still uploading',action['reason'])
        with patch.object(transport_synthetic,'upload_media',side_effect=AssertionError('No repeated upload')):
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'DISPATCH_ALREADY_CLAIMED')
        self.assertIn('Wait for that operation to end',caught.exception.diagnostic.required_action)
        with patch.object(execution,'_sender_alive',return_value=False):
            self.assertEqual(execution.status(self.root,self.run)['runs'][0]['next_action']['command'],'repeat')
            with self.assertRaises(ProductionError) as caught:
                execution.resume(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'REMOTE_OUTCOME_UNKNOWN')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
