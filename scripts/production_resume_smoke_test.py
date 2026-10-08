#!/usr/bin/env python3
"""Current execution recovery and visibility, using real synthetic run records."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
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
        # The suggested command names the checked root, as the command line does.
        self.assertEqual(action['argv'][1:5],['scripts/production_workflow.py','draft-execution','--root',str(self.root.resolve())])
        self.assertTrue(action['draft'].startswith(f'production/decisions/{self.run}/execution/'))
        self.assertEqual(action['argv'][-2:], ['--out', action['draft']])
        self.assertEqual(whole['current_task']['task_id'],report['task_id'])

    def test_unreadable_current_task_is_reported_not_raised(self):
        (self.root/'work'/'current.json').write_text('{not json',encoding='utf-8')
        report=status(self.root)
        self.assertIsNone(report['current_task']['task_id'])
        self.assertEqual(report['current_task']['diagnostics'][0]['file'],'work/current.json')
        self.assertEqual(report['runs'][0]['integrity'],'intact')

    def test_unreadable_authority_blocks_readiness_and_status_is_not_ok(self):
        from production_diagnostics import ProductionError
        refusal=ProductionError('AUTHORITY_STATE_CORRUPT','Synthetic damaged authority state.',phase='integrity')
        with patch.object(store,'authority',side_effect=refusal):
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
        self.assertTrue(item['freshness_diagnostics'])
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

    def test_every_freshness_problem_is_reported(self):
        task=c.load(self.root/'task.json');task['criteria'][0]['text']='A deliberately different current task criterion.'
        fixtures.write(self.root/'task.json',task)
        (self.root/'prompt.txt').write_text('A deliberately changed synthetic prompt.',encoding='utf-8')
        report=status(self.root,self.run)['runs'][0]
        self.assertTrue({'task.json','prompt.txt'} <= {d['file'] for d in report['freshness_diagnostics']})
        self.assertEqual(report['next_action']['command'],'prepare')

    def test_changed_task_scope_is_blocked_without_corrupting_history(self):
        task=c.load(self.root/'task.json');task['criteria'][0]['text']='A deliberately different current task criterion.'
        fixtures.write(self.root/'task.json',task)
        report=status(self.root,self.run)['runs'][0]
        self.assertEqual(report['integrity'],'intact')
        self.assertEqual(report['readiness'],'blocked')
        self.assertTrue(any(d['file']=='task.json' for d in report['freshness_diagnostics']))


class OutcomeStatementCliTests(unittest.TestCase):
    """draft-outcome and resume --outcome-file through the public CLI, after a lookup found no task.

    The test builds its studio from an empty folder, so the uncopied setup stays covered end to end.
    """

    def cli(self, root: Path, *arguments: str) -> tuple[int, dict]:
        import os
        import subprocess
        import sys
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


class AuthoredResumeTests(unittest.TestCase):
    def test_text_work_has_handoff_and_capture_not_generation_requirements(self):
        import work_ledger
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);task_id=work_ledger.begin(root,'Synthetic prose',['write'])['task_id']
            fixtures.write(root/'delivery.txt','A synthetic sentence.\n')
            task={'task_id':task_id,'route':'development','features':[],'sources':[],
                  'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Explicit authored text.'},
                  'criteria':[{'id':'text','strength':'hard','text':'A sentence exists.'}],'world_views':[]}
            production_fixtures.task(root,task);fixtures.write(root/'task.json',task)
            run=workflow.prepare(root,'task.json')['run']
            self.assertEqual(checked(execution.resume(root,run))['runs'][0]['next_action']['command'],'handoff')
            production_fixtures.handoff(root,run,'synthetic author','manual')
            self.assertEqual(checked(execution.resume(root,run))['runs'][0]['next_action']['command'],'capture')
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
