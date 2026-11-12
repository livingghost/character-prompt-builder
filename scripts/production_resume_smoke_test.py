#!/usr/bin/env python3
"""Current execution recovery and visibility, using real synthetic run records."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_fixtures
import production_execution as execution
import production_workflow as workflow
import production_store as store
import production_variation as variation
import execution_lifecycle as accounting
import studio
import transport_synthetic
from test_production_execution import decisions


def checked(report: dict) -> dict:
    """The status report, refused unless it meets schemas/authoring/production-status.schema.json."""
    workflow.schema_check(report, 'status')
    return report


def status(root: Path, run: str | None = None, **options) -> dict:
    return checked(execution.status(root, run, **options))


class ResumeTests(unittest.TestCase):
    """Each test works on its own copy of one prepared studio and its own home.

    The class builds the pack, runtime state, catalog cache, studio, prepared
    run and its decision file once. No test here edits the pack or the runtime state.
    """
    @classmethod
    def setUpClass(cls):
        from catalog_retrieval import runtime
        temp=tempfile.TemporaryDirectory();cls.addClassCleanup(temp.cleanup)
        b=Path(temp.name);cls.enterClassContext(production_fixtures.scratch_home(b/'home'))
        cls.addClassCleanup(runtime.configure_pack_runtime,None)
        cls.case=fixtures.create(b/'studio',b/'runtime');cls.origin=cls.case['root']
        cls.prepared_run=workflow.prepare(cls.origin,'task.json')['run']
        cls.prepared_decisions=decisions(cls.origin,cls.prepared_run)

    def setUp(self):
        from catalog_retrieval import runtime
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        b=Path(self.temp.name);self.enterContext(production_fixtures.scratch_home(b/'home'))
        runtime.configure_pack_runtime(self.case['settings'])
        self.root=fixtures.copy_studio(self.origin,b/'studio')
        self.run=self.prepared_run
        # Every copy carries the same request_id, so each test meets a synthetic service that has answered nothing.
        self.enterContext(patch.dict(transport_synthetic._ANSWERED,clear=True))

    def decision_file(self) -> str:
        """The class's decision file for its prepared run; any other run drafts its own."""
        return self.prepared_decisions if self.run==self.prepared_run else decisions(self.root,self.run)

    def send(self):
        return checked(execution.execute(self.root,self.run,decisions_file=self.decision_file()))

    def paused(self):
        # The claim commits and the transmission is skipped, so no status report is returned.
        with patch.object(execution,'_transmit',return_value={'paused':True}):
            execution.execute(self.root,self.run,decisions_file=self.decision_file())

    def test_prepared_authorization_wait_is_not_failed_staging(self):
        whole=status(self.root,self.run)
        report=whole['runs'][0]
        self.assertEqual(report['preparation'],'prepared')
        self.assertEqual(report['submission'],'unclaimed')
        self.assertEqual(report['readiness'],'authorization_required')
        self.assertEqual(report['registration'],'unregistered')
        action=report['next_action']
        self.assertEqual(action['command'],'draft-execution')
        # The command keeps this interpreter, the checked root and the exact run.
        self.assertEqual(action['argv'], [
            os.path.abspath(sys.executable), str(Path(workflow.__file__).resolve()),
            'draft-execution', '--root', str(self.root.resolve()), '--run', self.run,
            '--out', action['draft'],
        ])
        self.assertTrue(action['draft'].startswith(f'production/decisions/{self.run}/execution/'))
        self.assertEqual(action['argv'][-2:], ['--out', action['draft']])
        self.assertEqual(whole['current_task']['task_id'],report['task_id'])
        self.assertEqual([item['selected_grant'] for item in report['authorization_requirements']['requirements']],
                         ['fixture-grant', 'fixture-grant'])

    def test_execute_keeps_current_readiness_and_complete_maintenance_findings(self):
        import production_compiler
        with patch.object(production_compiler, 'inspect_staging', wraps=production_compiler.inspect_staging) as stages, \
             patch.object(execution, 'unclaimed_journals', wraps=execution.unclaimed_journals) as journals, \
             patch.object(production_compiler, 'unregistered_publications', wraps=production_compiler.unregistered_publications) as publications, \
             patch.object(workflow, 'freshness', wraps=workflow.freshness) as freshness:
            result = self.send()
        self.assertTrue(result['execution_completed'])
        self.assertEqual(result['runs'][0]['readiness'], 'ready')
        self.assertEqual(result['runs'][0]['freshness_diagnostics'], [])
        self.assertEqual(result['runs'][0]['freshness_notices'], [])
        self.assertTrue(freshness.called)
        for field in ('current_task', 'staging', 'staging_details', 'unclaimed_journals', 'unregistered_publications'):
            self.assertIn(field, result)
        stages.assert_called_once()
        journals.assert_called_once()
        publications.assert_called_once()

    def test_status_accounting_uses_the_already_acquired_run(self):
        self.send()
        expected = accounting.summary(self.root, run=self.run, isolate=True)
        with patch.object(accounting, 'all_states', side_effect=AssertionError('Status already acquired the run history')):
            result = status(self.root, self.run)
        self.assertEqual(result['execution_records'], expected)
        self.assertEqual(result['runs'][0]['readiness'], 'ready')

    def test_status_keeps_first_cleanup_failure_and_each_audit_diagnostic(self):
        import production_compiler
        with patch.object(production_compiler, 'inspect_staging', return_value=[{'name': 'synthetic-stage'}]) as stages, \
             patch.object(execution, 'unclaimed_journals', side_effect=PermissionError('Synthetic journal enumeration failure')) as journals, \
             patch.object(production_compiler, 'unregistered_publications', side_effect=OSError('Synthetic publication enumeration failure')) as publications:
            result = status(self.root, self.run)
        self.assertEqual(result['staging'], [])
        first = result['staging_details'][0]['diagnostics'][0]
        journal = result['unclaimed_journals'][0]['diagnostics'][0]
        publication = result['unregistered_publications'][0]['diagnostics'][0]
        self.assertEqual(first, journal)
        self.assertEqual((first['phase'], first['message']), ('cleanup', 'Synthetic journal enumeration failure'))
        self.assertEqual((publication['phase'], publication['message']), ('publication', 'Synthetic publication enumeration failure'))
        self.assertTrue(first['required_action'])
        self.assertTrue(publication['required_action'])
        stages.assert_called_once()
        journals.assert_called_once()
        publications.assert_called_once()

    def test_unreadable_journal_keeps_durable_execution_accounting(self):
        sent = self.send()
        journal = self.root / sent['runs'][0]['journal']
        (journal / 'request-contract.json').write_text('{incomplete', encoding='utf-8')
        result = status(self.root, self.run)
        self.assertFalse(result['ok'])
        self.assertEqual(result['runs'][0]['integrity'], 'blocked')
        self.assertTrue(result['execution_records']['complete'])
        self.assertEqual(result['execution_records'], sent['execution_records'])

    def test_unreadable_current_task_is_reported_not_raised(self):
        (self.root/'work'/'current.json').write_text('{not json',encoding='utf-8')
        report=status(self.root)
        self.assertIsNone(report['current_task']['task_id'])
        self.assertEqual(report['current_task']['diagnostics'][0]['file'],'work/current.json')
        self.assertEqual(report['runs'][0]['integrity'],'intact')

    def test_unreadable_authority_blocks_readiness_and_status_is_not_ok(self):
        from production_diagnostics import ProductionError
        refusal=ProductionError('AUTHORITY_STATE_CORRUPT','Synthetic damaged authority state.',phase='integrity')
        with patch.object(store,'read_authority',side_effect=refusal):
            report=status(self.root,self.run)
        self.assertFalse(report['ok'])
        self.assertEqual(report['runs'][0]['readiness'],'blocked')
        self.assertIn('AUTHORITY_STATE_CORRUPT',{item['code'] for item in report['runs'][0]['readiness_diagnostics']})

    def test_status_does_not_create_receipts_or_claim(self):
        before=store.event_rows(self.root,self.run)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No status send')):
            execution.status(self.root,self.run)
        self.assertEqual(store.event_rows(self.root,self.run),before)
        self.assertEqual(accounting.all_states(self.root),[])

    def test_claimed_before_effect_resumes_the_same_claim(self):
        self.paused();claim=workflow.find(store.event_rows(self.root,self.run),'dispatch-claim')
        report=status(self.root,self.run)['runs'][0]
        self.assertEqual((report['submission'],report['send_started'],report['effects']),('claimed',False,[]))
        self.assertEqual(report['next_action']['command'],'resume')
        self.assertEqual(report['execution']['status'],'claimed')
        actual=transport_synthetic.send
        with patch.object(transport_synthetic,'send',wraps=actual) as send:
            result=execution.resume(self.root,self.run)
        self.assertEqual(send.call_count,1)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(workflow.find(store.event_rows(self.root,self.run),'dispatch-claim')['sha256'],claim['sha256'])

    def resume_cli(self,*arguments):
        """resume through the public CLI: the exit status, the printed JSON or None, and stderr."""
        completed=subprocess.run([sys.executable,str(Path(workflow.__file__)),'resume','--root',str(self.root),
                                  '--run',self.run,*arguments],capture_output=True,text=True,encoding='utf-8',
                                 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},check=False)
        return completed.returncode,(json.loads(completed.stdout) if completed.stdout.strip() else None),completed.stderr

    def test_resume_watch_through_the_cli(self):
        self.send()
        # A settled run needs one pass; the watch returns its result without waiting.
        code,report,_=self.resume_cli('--watch','--interval','30','--limit','60')
        self.assertEqual(code,0)
        self.assertTrue(checked(report)['execution_completed'])
        for arguments in (('--interval','5'),('--watch','--limit','0')):
            code,report,_=self.resume_cli(*arguments)
            diagnostic=report['diagnostics'][0]
            self.assertEqual((code,diagnostic['code']),(2,'INPUT_ARGUMENT_INVALID'),arguments)
            self.assertIn('--watch' if arguments[0]=='--interval' else '--limit',diagnostic['required_action'])
        code,report,stderr=self.resume_cli('--watch','--outcome-file','outcome.json')
        self.assertEqual((code,report),(2,None))
        self.assertIn('--outcome-file',stderr)

    def abandon(self):
        task_id=workflow.load_run(self.root,self.run)[1]['task']['task_id']
        workflow.abandon_task(self.root,task_id,actor='synthetic author',reason='Synthetic stop of the work task.')

    def test_abandoned_task_retains_claim_without_starting_effect(self):
        self.paused();self.abandon()
        item=status(self.root,self.run)['runs'][0]
        self.assertEqual((item['task_disposition'],item['submission']),('abandoned','claimed'))
        self.assertEqual(item['execution']['status'],'claimed')
        self.assertIsNone(item['next_action'])

    def test_abandoned_unknown_outcome_keeps_its_execution(self):
        with patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic unknown outcome')):
            self.send()
        self.abandon()
        whole=status(self.root,self.run);item=whole['runs'][0]
        self.assertEqual((item['task_disposition'],item['submission']),('abandoned','outcome_unknown'))
        self.assertEqual(item['execution']['status'],'started')
        self.assertEqual(whole['execution_records']['submissions'],1)
        self.assertEqual(item['next_action']['command'],'resume')

    def test_unknown_outcome_remains_visible_when_source_changes(self):
        with patch.object(transport_synthetic,'send',side_effect=TimeoutError('Synthetic unknown outcome')):
            self.send()
        (self.root/'prompt.txt').unlink()
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No resend')):
            result=execution.resume(self.root,self.run)
        item=checked(result)['runs'][0]
        self.assertEqual(item['integrity'],'intact')
        self.assertEqual(item['submission'],'outcome_unknown')
        self.assertEqual(item['freshness_diagnostics'],[])
        self.assertIn(('SOURCE_CHANGED','warning','prompt.txt'),
                      [(notice['code'],notice['severity'],notice['file']) for notice in item['freshness_notices']])
        # The provider was asked and gave no answer; the evidenced statement is the next step.
        self.assertEqual(item['next_action']['command'],'draft-outcome')

    def test_saved_response_recovers_after_source_and_evidence_deletion(self):
        with patch.object(workflow,'record_dispatch_results',side_effect=OSError('Synthetic registration failure')):
            with self.assertRaises(OSError):self.send()
        (self.root/'prompt.txt').unlink();(self.root/'fixture-authority-basis.txt').unlink()
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No resend')):
            report=execution.resume(self.root,self.run)
        self.assertEqual(report['runs'][0]['capture'],'complete')
        self.assertEqual(len(report['runs'][0]['candidates']),1)

    def test_display_failure_recovers_without_duplicate_candidates(self):
        with patch.object(studio,'iterate',side_effect=OSError('Synthetic Studio projection failure')):
            first=self.send()
        self.assertFalse(first['execution_completed'])
        self.assertEqual(len(first['runs'][0]['candidates']),1)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No resend')):
            second=execution.resume(self.root,self.run)
        self.assertTrue(second['execution_completed'])
        self.assertEqual(first['runs'][0]['candidates'],second['runs'][0]['candidates'])
        self.assertEqual(len(studio.read_iterations(studio.character_home(self.root,'robot'))),1)
        self.assertEqual(accounting.summary(self.root)['submissions'],1)

    def test_partial_outputs_register_without_waiting_for_missing_image(self):
        # The provider returned two outputs, but acquiring one fails once.
        task=c.load(self.root/'task.json');task['generation']['count']=2;fixtures.write(self.root/'two.json',task)
        self.run=workflow.prepare(self.root,'two.json')['run']
        import dispatch
        real=dispatch.inline_image;calls=[]
        def first_failure(data):
            calls.append(1)
            if len(calls)==1:raise ValueError('Synthetic damaged transfer')
            return real(data)
        with patch.object(dispatch,'inline_image',side_effect=first_failure):first=self.send()
        self.assertEqual(first['runs'][0]['capture'],'partial')
        self.assertEqual(len(first['runs'][0]['candidates']),1)
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('No resend')):
            second=execution.resume(self.root,self.run)
        self.assertEqual(second['runs'][0]['capture'],'complete')
        self.assertEqual(len(second['runs'][0]['candidates']),2)
        self.assertEqual(accounting.summary(self.root,run=self.run)['submissions'],1)

    def test_one_corrupt_run_does_not_hide_another(self):
        other=variation.derive(self.root,self.run,prepare=True)['run']
        checked(execution.execute(self.root,other,decisions_file=decisions(self.root,other)))
        (workflow.run_dir(self.root,self.run)/'consumer.json').write_text('{}',encoding='utf-8')
        result=status(self.root)
        by_id={row['run']:row for row in result['runs']}
        self.assertEqual(by_id[self.run]['integrity'],'blocked')
        self.assertEqual(by_id[self.run]['next_action']['command'],'status')
        self.assertEqual(by_id[other]['integrity'],'intact')
        self.assertEqual(by_id[other]['capture'],'complete')
        # The intact run keeps its execution records; the corrupt run is named instead of hiding it.
        self.assertFalse(result['execution_records']['complete'])
        self.assertIn(self.run,{item.get('run') for item in result['execution_records']['diagnostics']})
        group=result['execution_records']
        self.assertEqual(group['submissions'],1)
        self.assertIsInstance(result['unregistered_publications'],list)

    def test_every_current_draft_change_is_reported_without_blocking_saved_execution(self):
        task=c.load(self.root/'task.json');task['criteria'][0]['text']='A deliberately different current task criterion.'
        fixtures.write(self.root/'task.json',task)
        (self.root/'prompt.txt').write_text('A deliberately changed synthetic prompt.',encoding='utf-8')
        report=status(self.root,self.run)['runs'][0]
        self.assertEqual(report['freshness_diagnostics'],[])
        self.assertTrue({'task.json','prompt.txt'} <= {d['file'] for d in report['freshness_notices']})
        self.assertEqual(report['next_action']['command'],'draft-execution')

    def test_changed_draft_scope_leaves_the_saved_task_and_history_intact(self):
        before=workflow.read_run(self.root,self.run).prepared
        task=c.load(self.root/'task.json');task['criteria'][0]['text']='A deliberately different current task criterion.'
        fixtures.write(self.root/'task.json',task)
        report=status(self.root,self.run)['runs'][0]
        self.assertEqual(report['integrity'],'intact')
        self.assertEqual(report['readiness'],'authorization_required')
        self.assertEqual(report['freshness_diagnostics'],[])
        self.assertTrue(any(d['file']=='task.json' for d in report['freshness_notices']))
        self.assertEqual(workflow.read_run(self.root,self.run).prepared,before)


class OutcomeStatementCliTests(unittest.TestCase):
    """draft-outcome and resume --outcome-file through the public CLI, after a lookup found no task.

    The test builds its studio from an empty folder, so the uncopied setup stays covered end to end.
    """

    def cli(self, root: Path, *arguments: str) -> tuple[int, dict]:
        import os
        import subprocess
        import sys
        # These recovery assertions inspect complete declarations; ordinary CLI
        # navigation is covered independently by the status presentation suite.
        if arguments[0] == 'status':
            arguments = (*arguments, '--view', 'full')
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name('production_workflow.py')), *arguments,
                                    '--root', str(root)], capture_output=True, text=True, encoding='utf-8',
                                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, check=False)
        return completed.returncode, json.loads(completed.stdout)

    def test_statement_round_trip_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); case = fixtures.create(b/'studio', b/'runtime'); root = case['root']
            run = workflow.prepare(root, 'task.json')['run']
            with patch.object(transport_synthetic, 'send', side_effect=TimeoutError('Synthetic timeout')):
                execution.execute(root, run, decisions_file=decisions(root, run))
            action = checked(execution.resume(root, run))['runs'][0]['next_action']
            self.assertTrue(action['draft'].startswith(f'production/decisions/{run}/outcome/'))
            self.assertEqual(action['argv'][2:], ['draft-outcome', '--root', str(root), '--run', run, '--out', action['draft']])
            code, drafted = self.cli(root, 'draft-outcome', '--run', run, '--out', action['draft'])
            self.assertEqual(code, 0)
            self.assertEqual(c.load(root/action['draft']), drafted)
            fixtures.write(root/'provider-export.txt', 'Synthetic provider export without this task.\n')
            issuer = store.authority(root, workflow.load_run(root, run)[1]['task']['task_id'])['issuer']
            drafted.update(actor=issuer, reason='The provider export lists no task for this request.',
                           evidence={'path': 'provider-export.txt', 'sha256': c.sha256_file(root/'provider-export.txt'), 'locator': 'whole export'})
            fixtures.write(root/action['draft'], drafted)
            code, report = self.cli(root, 'resume', '--run', run, '--outcome-file', action['draft'])
            self.assertEqual(code, 0)
            item = checked(report)['runs'][0]
            self.assertEqual(item['submission'], 'not_executed')
            self.assertEqual(item['next_action']['command'], 'repeat')

    def test_custom_execution_draft_survives_reopen_authority_change_and_log_cleanup(self):
        import copy
        from production_fixtures import assess_rendition
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with production_fixtures.scratch_home(base / 'home'):
                case = fixtures.create(base / 'studio', base / 'runtime')
                root = case['root']
                run = workflow.prepare(root, 'task.json')['run']
                custom = 'work/upscale/execution-decisions.json'
                code, draft = self.cli(root, 'draft-execution', '--run', run, '--out', custom)
                self.assertEqual(code, 0, draft)
                self.assertEqual(c.load(root / custom), draft['choices'])
                choices = draft['choices']
                direction_reason = 'Explicit synthetic direction retained through authority changes; not user consent.'
                for choice in choices['decisions']:
                    choice['reason'] = direction_reason if choice['operation'] == 'direction' else 'Explicit synthetic submission; not user consent.'
                    if choice['operation'] == 'submit':
                        choice['request_decision']['principal_approval'] = copy.deepcopy(draft['authority']['document']['evidence'])
                        assess_rendition(choice['request_decision']['rendition_review'])
                fixtures.write(root / custom, choices)
                original_choices = (root / custom).read_bytes()
                code, reopened = self.cli(root, 'status', '--run', run)
                self.assertEqual(code, 0, reopened)
                observed = checked(reopened)['runs'][0]
                self.assertEqual(observed['next_action']['draft'], custom)
                self.assertEqual(reopened['current_task']['authoring']['decision_drafts'][0]['path'], custom)
                authority = observed['authority']['document']
                added = copy.deepcopy(authority['grants'][0])
                added.update(id='selection-only', operations=['select'], targets=['delivery'],
                             request_scope=None, submission_validation_modes=[])
                authority['grants'].append(added)
                source = observed['authority']['source_path']
                fixtures.write(root / source, authority)
                code, amended = self.cli(root, 'authority-import', '--file', source,
                    '--expected-event', observed['authority']['event_sha256'])
                self.assertEqual(code, 0, amended)
                code, cleaned = self.cli(root, 'logs-cleanup', '--before', '9999-01-01', '--apply')
                self.assertEqual(code, 0, cleaned)
                code, continued = self.cli(root, 'status', '--run', run)
                self.assertEqual(code, 0, continued)
                current = checked(continued)['runs'][0]
                self.assertEqual(current['next_action']['argv'][-2:], ['--decisions-file', custom])
                self.assertEqual(current['authority']['event_sha256'], amended['sha256'])
                self.assertEqual((root / custom).read_bytes(), original_choices)
                code, executed = self.cli(root, 'execute', '--run', run, '--decisions-file', custom)
                self.assertEqual(code, 0, executed)
                self.assertEqual(checked(executed)['runs'][0]['submission'], 'acknowledged')
                directions = [row['data']['request'] for row in store.event_rows(root, run)
                              if row['event'] == 'authorization' and row['data']['request']['operation'] == 'direction']
                self.assertEqual(directions[0]['reason'], direction_reason)

    def test_multiple_execution_drafts_are_presented_for_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with production_fixtures.scratch_home(base / 'home'):
                case = fixtures.create(base / 'studio', base / 'runtime')
                root = case['root']
                run = workflow.prepare(root, 'task.json')['run']
                paths = ['work/first-decisions.json', 'work/second-decisions.json']
                for path in paths:
                    code, drafted = self.cli(root, 'draft-execution', '--run', run, '--out', path)
                    self.assertEqual(code, 0, drafted)
                code, report = self.cli(root, 'status', '--run', run)
                self.assertEqual(code, 0, report)
                action = checked(report)['runs'][0]['next_action']
                self.assertTrue(action['requires_author_input'])
                self.assertEqual({item['draft'] for item in action['alternatives']}, set(paths))
                self.assertNotIn('draft', action)
                self.assertEqual(store.event_rows(root, run), [])


class AuthoringContinuationTests(unittest.TestCase):
    """Current authored choices remain reachable beside an existing prepared run."""

    def setUp(self):
        import production_inputs
        import work_ledger
        self.inputs = production_inputs
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        self.root = base / 'studio'
        self.root.mkdir()
        work = work_ledger.begin(self.root, 'Continue the synthetic written depiction.', ['Compose', 'Inspect'])
        fixtures.write(self.root / 'brief.txt', 'Synthetic brief: describe one quiet courtyard.')
        fixtures.write(self.root / 'delivery.txt', 'One quiet courtyard under a clear sky.')
        self.task = {'task_id': work['task_id'], 'route': 'development', 'features': [],
            'sources': [{'id': 'brief', 'path': 'brief.txt', 'role': 'design', 'disposition': 'applied',
                         'locator': 'whole', 'reason': 'The synthetic brief owns the requested subject.'}],
            'delivery': {'path': 'delivery.txt', 'translation_notes': 'One authored depiction.'},
            'criteria': [{'id': 'subject', 'strength': 'hard', 'text': 'Describe one quiet courtyard.'}],
            'world_views': []}
        production_fixtures.task(self.root, self.task)
        fixtures.write(self.root / 'task.json', self.task)
        drafted = self.inputs.draft_inputs(self.root, 'task.json', 'draft')
        self.choices_path = drafted['choices_file']
        self.choices = c.load(self.root / self.choices_path)
        reading = c.load(self.root / self.task['route_reading'])
        self.choices['reading']['reading_key'] = reading['reading_key']
        fixtures.write(self.root / self.choices_path, self.choices)
        built = self.inputs.build_inputs(self.root, 'task.json', self.choices_path, 'built')
        self.assertTrue(built['ok'], built)
        self.run = workflow.prepare(self.root, built['inputs']['production-task']['path'])['run']

    def test_prepared_input_context_keeps_the_commission_choices_and_source_locations(self):
        report = status(self.root)
        current = report['current_task']
        self.assertEqual(current['focus'], 'authored')
        context = current['authoring']['context']
        self.assertEqual(context['work']['goal'], 'Continue the synthetic written depiction.')
        self.assertEqual(context['input']['choices'], self.choices)
        self.assertEqual(context['input']['task_content']['criteria'], self.task['criteria'])
        source = next(item for item in context['input']['sources'] if item['id'] == 'brief')
        self.assertEqual(source['current_file'], str((self.root / 'brief.txt').resolve()))
        self.assertTrue(source['current_available'])

    def test_reediting_built_choices_returns_to_authoring_and_keeps_the_prepared_run(self):
        import copy
        import session_entry_points
        before = (self.root / 'built/production-task.json').read_bytes()
        self.choices['task_changes']['direction'] = copy.deepcopy(self.task['direction'])
        self.choices['task_changes']['direction']['purpose'] = 'A revised authored purpose for the same courtyard.'
        fixtures.write(self.root / self.choices_path, self.choices)
        events = store.event_rows(self.root, self.run)
        report = status(self.root)
        current = report['current_task']
        self.assertEqual(current['focus'], 'authoring')
        self.assertEqual(current['production_run'], self.run)
        self.assertEqual(current['next_actions'][0]['command'], 'save')
        context = current['authoring']['context']['input']
        self.assertTrue(context['changed_since_build'])
        self.assertEqual(context['task_content']['direction']['purpose'],
                         self.choices['task_changes']['direction']['purpose'])
        self.assertEqual(context['prepared_run'], self.run)
        lines = '\n'.join(session_entry_points.authoring_lines(self.root))
        self.assertLess(lines.index(str(self.root / self.choices_path)), lines.index('Saved authored revision: ' + self.run))
        self.assertEqual((self.root / 'built/production-task.json').read_bytes(), before)
        self.assertEqual(store.event_rows(self.root, self.run), events)

    def test_an_interrupted_choice_write_stays_current_without_hiding_the_existing_run(self):
        fixtures.write(self.root / self.choices_path, '{"reading":')
        report = status(self.root)
        current = report['current_task']
        self.assertEqual(current['focus'], 'authoring')
        self.assertEqual(current['next_actions'][0]['command'], 'edit-choices')
        selected = next(item for item in current['authoring']['inputs'] if item['current'])
        self.assertEqual(selected['choices'], self.choices_path)
        self.assertEqual(selected['unresolved'][0]['code'], 'authored-input-unreadable')
        self.assertEqual(selected['unresolved'][0]['path'], self.choices_path)
        self.assertEqual(selected['next_actions'][0]['path'], str((self.root / self.choices_path).resolve()))
        self.assertEqual(current['next_actions'][0], selected['next_actions'][0])
        self.assertIn('choices_diagnostic', current['authoring']['context']['input'])
        self.assertEqual(report['runs'][0]['run'], self.run)
        self.assertEqual(report['runs'][0]['integrity'], 'intact')

    def test_a_new_draft_from_an_existing_run_is_the_session_continuation(self):
        import session_entry_points
        saved=workflow.read_run(self.root,self.run)
        original=next(item for item in saved.prepared['task']['sources'] if item['id']=='brief')
        dependency=next(item for item in saved.prepared['dependencies'] if item['path']==original['path'])
        captured=saved.evidence.read(dependency['sha256'])
        fixtures.write(self.root/original['path'],'A later brief belongs to another intended revision.')
        drafted = self.inputs.draft_inputs(self.root, None, 'next-draft', from_run=self.run)
        report = status(self.root)
        current = report['current_task']
        self.assertEqual(current['focus'], 'authoring')
        context = current['authoring']['context']['input']
        self.assertEqual(context['choices_file'], str((self.root / drafted['choices_file']).resolve()))
        self.assertEqual(context['source_run'],self.run)
        parent=drafted['derived_from']['source_run']
        self.assertEqual((parent['run'],parent['input_sha256']),(self.run,saved.prepared['input_sha256']))
        source = next(item for item in context['sources'] if item['id'] == 'brief')
        self.assertEqual({key:source[key] for key in original if key!='path'},
                         {key:value for key,value in original.items() if key!='path'})
        retained=Path(source['current_file'])
        self.assertTrue(source['current_available'])
        self.assertEqual(retained,(self.root/source['path']).resolve())
        self.assertTrue(retained.is_relative_to(self.root/'next-draft'))
        self.assertEqual(retained.read_bytes(),captured)
        self.assertEqual(c.sha256_file(retained),dependency['sha256'])
        self.assertEqual(workflow.read_run(self.root,self.run).prepared,saved.prepared)
        lines = '\n'.join(session_entry_points.authoring_lines(self.root))
        self.assertLess(lines.index(str(self.root / drafted['choices_file'])), lines.index('Saved authored revision: ' + self.run))


class InitialAuthoringContinuationTests(unittest.TestCase):
    """Initial drafts retain their source and executable continuation after interruption."""

    def setUp(self):
        import production_inputs
        from production_inputs_smoke_test import AuthoringRecoveryTests
        AuthoringRecoveryTests.setUp(self)
        self.inputs = production_inputs

    def save_choices(self):
        (self.root / 'choices.json').write_bytes(c.encoded(self.choices))

    def initial(self):
        import copy
        drafted = self.inputs.draft_inputs(self.root, None, 'initial', route='development')
        choices = c.load(self.root / drafted['choices_file'])
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        choices['authoring']['task']['direction'] = copy.deepcopy(self.task['direction'])
        choices['authoring']['task']['criteria'] = copy.deepcopy(self.task['criteria'])
        delivery = choices['authoring']['delivery']
        fixtures.write(self.root / delivery['file'], 'A quiet courtyard under a clear sky.')
        fixtures.write(self.root / drafted['choices_file'], choices)
        return drafted, choices

    def test_initial_choices_provide_a_real_save_command_and_current_context(self):
        drafted, choices = self.initial()
        report = self.inputs.inspect_inputs(self.root)
        self.assertEqual(report['diagnostics'], [])
        action = report['next_actions'][0]
        self.assertEqual(action['command'], 'save')
        self.assertNotIn('--from-run', action['argv'])
        self.assertNotIn(None, action['argv'])
        self.assertEqual(report['context']['input']['choices'], choices)
        run = subprocess.run(action['argv'], capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        saved = json.loads(run.stdout)
        self.assertTrue(saved['saved'])
        task = workflow.read_run(self.root, saved['run']).prepared['task']
        self.assertEqual(task['task_id'], self.work['task_id'])
        self.assertEqual(task['criteria'], self.task['criteria'])
        self.assertEqual(Path(saved['artifact']).read_bytes(),
                         (self.root / choices['authoring']['delivery']['file']).read_bytes())
        self.assertFalse(self.inputs.inspect_inputs(self.root)['pending'])

    def test_reediting_initial_text_preserves_the_saved_revision_and_saves_again(self):
        drafted, choices = self.initial()
        saved = workflow.save(self.root, drafted['choices_file'])
        original = Path(saved['artifact'])
        before = original.read_bytes()
        edited = self.root / choices['authoring']['delivery']['file']
        edited.write_text('The same quiet courtyard after a light rain.', encoding='utf-8')
        report = self.inputs.inspect_inputs(self.root)
        self.assertTrue(report['context']['input']['changed_since_build'])
        self.assertEqual(report['context']['input']['task_content']['criteria'], self.task['criteria'])
        self.assertTrue(report['pending'])
        action = report['next_actions'][0]
        self.assertEqual(action['command'], 'save')
        self.assertNotIn('--from-run', action['argv'])
        run = subprocess.run(action['argv'], capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(original.read_bytes(), before)
        revised = json.loads(run.stdout)
        self.assertNotEqual(saved['run'], revised['run'])
        self.assertEqual(Path(revised['artifact']).read_bytes(), edited.read_bytes())
        self.assertFalse(self.inputs.inspect_inputs(self.root)['pending'])

    def test_unpublished_initial_draft_restarts_with_its_route_and_task(self):
        with patch.object(self.inputs, '_publish', side_effect=OSError('Synthetic draft interruption.')):
            with self.assertRaisesRegex(OSError, 'draft interruption'):
                self.inputs.draft_inputs(self.root, None, 'initial', route='development')
        report = self.inputs.inspect_inputs(self.root)
        self.assertEqual(report['diagnostics'], [])
        action = report['next_actions'][0]
        self.assertEqual(action['command'], 'draft-inputs')
        self.assertEqual(action['argv'][action['argv'].index('--route') + 1], 'development')
        self.assertEqual(action['argv'][action['argv'].index('--task-id') + 1], self.work['task_id'])
        self.assertNotIn('--from-run', action['argv'])
        run = subprocess.run(action['argv'], capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        drafted = json.loads(run.stdout)
        self.assertIsNone(drafted['choices']['reading']['reading_key'])
        self.assertEqual(drafted['choices']['authoring']['task']['task_id'], self.work['task_id'])


class AuthoredResumeTests(unittest.TestCase):
    def test_saved_text_resumes_at_requested_completion(self):
        import work_ledger
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);task_id=work_ledger.begin(root,'Synthetic prose',['write'])['task_id']
            fixtures.write(root/'delivery.txt','A synthetic sentence.\n')
            task={'task_id':task_id,'route':'development','features':[],'sources':[],
                  'delivery':{'path':'delivery.txt','translation_notes':'Explicit authored text.'},
                  'criteria':[{'id':'text','strength':'hard','text':'A sentence exists.'}],'world_views':[]}
            production_fixtures.task(root,task);fixtures.write(root/'task.json',task)
            run=workflow.prepare(root,'task.json')['run']
            shown=checked(execution.resume(root,run))['runs'][0]
            self.assertEqual(shown['next_action']['command'],'finish')
            self.assertEqual(shown['authored']['state'],'finished')
            self.assertIsNotNone(shown['authored']['saved'])
            work_ledger.step_done(root,1)
            work_ledger.finish(root,run)
            self.assertEqual(checked(execution.resume(root,run))['runs'][0]['task_disposition'],'completed')
            self.assertIsNone(work_ledger.read_current(root))
            self.assertFalse((workflow.run_dir(root,run)/'generation-package.json').exists())
            self.assertEqual(accounting.all_states(root),[])


@unittest.skipUnless(os.name=='nt','directory junctions are a Windows feature')
class JunctionRootTests(unittest.TestCase):
    """A studio root given through a directory junction names the same studio."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.enterContext(production_fixtures.scratch_home(base/'home'))
        case=fixtures.create(base/'studio',base/'runtime');self.studio=case['root']
        self.alias=base/'alias'
        made=subprocess.run(['cmd','/c','mklink','/J',str(self.alias),str(self.studio)],capture_output=True)
        if made.returncode!=0:self.skipTest('this file system makes no directory junction')
        self.enterContext(patch.dict(transport_synthetic._ANSWERED,clear=True))
        self.run=workflow.prepare(self.alias,'task.json')['run']

    def test_a_paused_execution_resumes_and_records_through_the_junction(self):
        with patch.object(execution,'_transmit',return_value={'paused':True}):
            execution.execute(self.alias,self.run,decisions_file=decisions(self.alias,self.run))
        result=checked(execution.resume(self.alias,self.run))
        self.assertTrue(result['execution_completed'],result.get('warnings'))
        rows=studio.read_iterations(studio.character_dir(self.alias,'robot'))
        self.assertEqual(len(rows),1)
        for name in ('result','answer'):
            self.assertTrue((self.studio/rows[0][name]['path']).is_file(),rows[0][name])
            self.assertFalse(Path(rows[0][name]['path']).is_absolute())
        self.assertEqual(status(self.alias,self.run)['runs'][0]['submission'],'acknowledged')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
