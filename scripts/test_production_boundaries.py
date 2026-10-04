"""Current low-level request and formal-event boundaries; no network generation."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import execution_contract as c
import production_case_fixtures as f
import production_execution as execution
import production_store as store
import production_workflow as workflow
import reservation_lifecycle as accounting
import transport_synthetic
from production_diagnostics import ProductionError
from test_production_execution import decisions

import production_fixtures


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.case=f.create(base/'studio',base/'runtime');self.root=self.case['root']
        # Operations created directly in these tests log under the home directory.
        home=production_fixtures.scratch_home(base/'home');home.start();self.addCleanup(home.stop)
        self.run=workflow.prepare(self.root,'task.json')['run']
        self.data=execution.compiled(self.root,self.run)

    def authorized_journal(self):
        plan=self.data[6]
        with store.transaction(self.root):
            execution.authorize_decisions(self.root,self.run,decisions(self.root,self.run),self.data[1],plan)
        loaded=workflow.load_run(self.root,self.run)
        tokens=execution.receipts(self.root,loaded[1],loaded[3],plan)
        journal,rendered=execution._journal(self.root,self.run,self.data)
        hand=plan['handoff']
        workflow.handoff(self.root,self.run,hand['recipient'],hand['method'],tokens['direction'],journal=journal.path)
        return journal,rendered,tokens

    def test_dispatcher_handoff_is_recorded_only_by_execute(self):
        plan=self.data[6]
        with store.transaction(self.root):
            execution.authorize_decisions(self.root,self.run,decisions(self.root,self.run),self.data[1],plan)
        loaded=workflow.load_run(self.root,self.run)
        token=execution.receipts(self.root,loaded[1],loaded[3],plan)['direction']
        hand=plan['handoff']
        with self.assertRaises(ProductionError) as caught:
            workflow.handoff(self.root,self.run,hand['recipient'],'dispatcher',token)
        self.assertEqual(caught.exception.diagnostic.code,'HANDOFF_NOT_PERFORMED')
        self.assertIn('execute',caught.exception.diagnostic.required_action)
        self.assertFalse(any(r['event'] in {'handoff','reservation-created'} for r in store.event_rows(self.root,self.run)))

    def test_changed_package_cannot_claim_prepared_run(self):
        journal,rendered,tokens=self.authorized_journal()
        package=copy.deepcopy(self.data[4]);package['composition_prompt']+=' altered'
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_dispatch(self.root,self.run,package,{},journal.path,self.data[6]['operations'][-1],tokens['submit'],rendered=rendered)
        self.assertEqual(caught.exception.diagnostic.pointer,'$.package_sha256')
        self.assertEqual(accounting.all_states(self.root),[])
        self.assertFalse(any(r['event']=='dispatch-claim' for r in store.event_rows(self.root,self.run)))

    def test_changed_request_cannot_claim_prepared_run(self):
        journal,rendered,tokens=self.authorized_journal()
        # The changed request is sealed correctly, not merely malformed JSON.
        import request_contract as rc
        modified=copy.deepcopy(rendered)
        rc.put(modified['request'],modified['layout']['output_count'],2)
        altered=rc.seal(modified['request'],modified['layout'],modified['media'],modified['sealed']['target'],
            modified['sealed']['execution'],modified['request_trace'],modified['sealed']['bindings'],modified['sealed']['context'])
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_dispatch(self.root,self.run,self.data[4],{},journal.path,self.data[6]['operations'][-1],tokens['submit'],rendered=altered)
        self.assertTrue(caught.exception.diagnostic.pointer.startswith('$.request_contract'))
        self.assertEqual(accounting.all_states(self.root),[])

    def test_wrong_recipient_is_rejected_before_handoff(self):
        with self.assertRaises(ProductionError) as caught:
            workflow.handoff_intent(self.root,self.run,'another-recipient','dispatcher')
        self.assertEqual(caught.exception.diagnostic.pointer,'$.handoff.recipient')
        self.assertEqual(store.event_rows(self.root,self.run),[])

    def test_no_authorization_or_reservation_from_arbitrary_database_columns(self):
        journal,rendered,tokens=self.authorized_journal()
        with store.transaction(self.root) as db:
            db.execute('UPDATE events SET input_sha256=? WHERE scope=? AND sequence=1',('a'*64,self.run))
        with self.assertRaises(ProductionError) as caught:store.event_rows(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'EVENT_CHAIN_CORRUPT')
        self.assertEqual(caught.exception.diagnostic.details['event'],1)

    def test_malformed_event_has_recoverable_diagnostic(self):
        self.authorized_journal()
        with store.transaction(self.root) as db:
            db.execute('UPDATE events SET body=? WHERE scope=? AND sequence=1',(b'{"incomplete":',self.run))
        status=execution.status(self.root,self.run)
        self.assertFalse(status['ok'])
        error=status['runs'][0]['diagnostics'][0]
        self.assertEqual(error['code'],'EVENT_CHAIN_CORRUPT')
        self.assertEqual(error['run'],self.run)
        self.assertEqual(error['event'],1)
        self.assertEqual(len(error['expected']),64)

    def test_corrupt_saved_result_cannot_be_reviewed(self):
        result=execution.execute(self.root,self.run,decisions_file=decisions(self.root,self.run))
        candidate=workflow.find(store.event_rows(self.root,self.run),'candidate',result['runs'][0]['candidates'][0])
        path=workflow.run_dir(self.root,self.run)/'objects'/candidate['data']['files'][0]['sha256']
        path.write_bytes(b'not the captured PNG')
        with self.assertRaises(ProductionError):workflow.draft_review(self.root,self.run,candidate['sha256'])
        with patch.object(transport_synthetic,'send',side_effect=AssertionError('Corruption cannot cause resend')):
            with self.assertRaises(ProductionError):execution.resume(self.root,self.run)


    def test_runtime_changed_after_claim_blocks_io_even_with_operation_cache(self):
        import operation_context as operations
        import runtime_snapshot
        decision_file = decisions(self.root, self.run)
        descriptor = self.data[1]['runtime_snapshot']
        directory = runtime_snapshot.path(self.root, descriptor)
        snapshot = runtime_snapshot.read(directory, descriptor)
        pack = snapshot['packs'][0]
        pinned = directory / 'packs' / pack['pack_id'] / pack['files'][0]['path']
        original_claim = workflow.claim_dispatch
        operation = operations.Operation('synthetic-integrity-boundary')
        token = operations._CURRENT.set(operation)
        def corrupt_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            pinned.write_bytes(pinned.read_bytes() + b'\ncorrupt')
            return claim
        try:
            # Prime the per-operation cache, then change a resource after the
            # run claim. The actual irreversible boundary must hash again.
            runtime_snapshot.read(directory, descriptor)
            with patch.object(workflow, 'claim_dispatch', side_effect=corrupt_after_claim), \
                 patch.object(transport_synthetic, 'send') as send:
                with self.assertRaises(ProductionError) as caught:
                    execution.execute(self.root, self.run, decisions_file=decision_file)
            self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
            send.assert_not_called()
            rows = store.event_rows(self.root, self.run)
            self.assertFalse(any(row['event'] == 'external-step' for row in rows))
        finally:
            operation.finish(0)
            operations._CURRENT.reset(token)

    def test_api_execution_checks_snapshot_at_external_boundary_without_logger(self):
        import operation_context as operations
        import runtime_snapshot
        decision_file = decisions(self.root, self.run)
        original_read = runtime_snapshot.read
        original_current = runtime_snapshot.require_current
        forced = []
        comparisons = {'full': 0, 'forced': 0}
        def observe(*args, **kwargs):
            if kwargs.get('force_verify'):
                forced.append(True)
            return original_read(*args, **kwargs)
        def compare(*args, **kwargs):
            # A computed live-source check compares the packs once; the external boundary forces one more.
            comparisons['forced' if kwargs.get('force') else 'full'] += 1
            return original_current(*args, **kwargs)
        token = operations._CURRENT.set(None)
        try:
            with patch.object(runtime_snapshot, 'read', side_effect=observe), \
                 patch.object(runtime_snapshot, 'require_current', side_effect=compare), \
                 patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
                result = execution.execute(self.root, self.run, decisions_file=decision_file)
            self.assertTrue(result['execution_completed'])
            self.assertEqual(len(forced), 1)
            self.assertEqual(send.call_count, 1)
            # Preflight, the authorization transaction, the transaction right
            # before the send, and the status the call returns.
            self.assertLessEqual(comparisons['full'], 4)
            self.assertEqual(comparisons['forced'], 1)
        finally:
            operations._CURRENT.reset(token)

    def test_draft_execution_checks_live_sources_once(self):
        import runtime_snapshot
        original_current = runtime_snapshot.require_current
        full = []
        def compare(*args, **kwargs):
            full.append(kwargs.get('force', False))
            return original_current(*args, **kwargs)
        with patch.object(runtime_snapshot, 'require_current', side_effect=compare):
            drafted = execution.draft_execution(self.root, self.run, 'fixture-grant')
        self.assertEqual(len(drafted['authorizations']), len(self.data[6]['operations']))
        self.assertEqual(full, [False])

    def test_pinned_source_edited_after_claim_blocks_the_send(self):
        decision_file = decisions(self.root, self.run)
        original_claim = workflow.claim_dispatch
        def edit_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            (self.root / 'prompt.txt').write_text('A prompt edited after the claim.\n', encoding='utf-8')
            return claim
        with patch.object(workflow, 'claim_dispatch', side_effect=edit_after_claim), \
             patch.object(transport_synthetic, 'send') as send:
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root, self.run, decisions_file=decision_file)
        self.assertEqual((caught.exception.diagnostic.code, caught.exception.diagnostic.file), ('SOURCE_CHANGED', 'prompt.txt'))
        send.assert_not_called()
        rows = store.event_rows(self.root, self.run)
        self.assertTrue(any(row['event'] == 'dispatch-claim' for row in rows))
        self.assertFalse(any(row['event'] == 'external-step' for row in rows))

    def test_source_edited_during_the_send_blocks_the_returned_status(self):
        decision_file = decisions(self.root, self.run)
        original_send = transport_synthetic.send
        def edit_during_send(*args, **kwargs):
            (self.root / 'prompt.txt').write_text('A prompt edited while the provider worked.\n', encoding='utf-8')
            return original_send(*args, **kwargs)
        with patch.object(transport_synthetic, 'send', side_effect=edit_during_send) as send:
            result = execution.execute(self.root, self.run, decisions_file=decision_file)
        self.assertEqual(send.call_count, 1)
        report = result['runs'][0]
        self.assertEqual(report['readiness'], 'blocked')
        self.assertIn('SOURCE_CHANGED', [row['code'] for row in report['freshness_diagnostics']])

    def refused_external_claim(self, change) -> tuple[str, object]:
        """Claim an external run while `change(run)` runs right after the claim row; return the run and refusal."""
        import production_fixtures as fixture
        task = c.load(self.root / 'task.json'); task['execution'] = 'external'; f.write(self.root / 'task.json', task)
        run = workflow.prepare(self.root, 'task.json')['run']
        fixture.handoff(self.root, run, 'synthetic external host', 'manual')
        token = fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        original_commit = accounting.commit_effect
        def change_after_commit(*args, **kwargs):
            row = original_commit(*args, **kwargs)
            change(run)
            return row
        with patch.object(accounting, 'commit_effect', side_effect=change_after_commit):
            with self.assertRaises(ProductionError) as caught:
                workflow.claim_external(self.root, run, 1, token)
        events = {row['event'] for row in store.event_rows(self.root, run)}
        self.assertFalse(events & {'external-claim', 'external-step'})
        return run, caught.exception.diagnostic

    def test_source_edited_inside_the_external_claim_blocks_the_send_boundary(self):
        def edit(run):
            (self.root / 'brief.md').write_text('A brief edited inside the claim transaction.\n', encoding='utf-8')
        _, diagnostic = self.refused_external_claim(edit)
        self.assertEqual((diagnostic.code, diagnostic.file), ('SOURCE_CHANGED', 'brief.md'))

    def test_run_object_corrupted_inside_the_external_claim_blocks_the_send_boundary(self):
        def corrupt(run):
            prepared = workflow.load_run(self.root, run)[1]
            dependency = next(item for item in prepared['dependencies'] if item['space'] == 'studio')
            (workflow.run_dir(self.root, run) / 'objects' / dependency['sha256']).write_bytes(b'corrupt stored source snapshot')
        _, diagnostic = self.refused_external_claim(corrupt)
        self.assertEqual(diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')

    def test_corrupt_run_object_after_claim_blocks_the_send(self):
        decision_file = decisions(self.root, self.run)
        directory = workflow.run_dir(self.root, self.run)
        dependency = next(item for item in self.data[1]['dependencies'] if item['space'] == 'studio')
        original_claim = workflow.claim_dispatch
        def corrupt_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            (directory / 'objects' / dependency['sha256']).write_bytes(b'corrupt stored source snapshot')
            return claim
        with patch.object(workflow, 'claim_dispatch', side_effect=corrupt_after_claim), \
             patch.object(transport_synthetic, 'send') as send:
            with self.assertRaises(ProductionError) as caught:
                execution.execute(self.root, self.run, decisions_file=decision_file)
        self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        send.assert_not_called()
        self.assertFalse(any(row['event'] == 'external-step' for row in store.event_rows(self.root, self.run)))

    def test_runtime_changed_after_claim_blocks_io_in_an_api_call(self):
        import operation_context as operations
        import runtime_snapshot
        decision_file = decisions(self.root, self.run)
        descriptor = self.data[1]['runtime_snapshot']
        directory = runtime_snapshot.path(self.root, descriptor)
        pack = runtime_snapshot.read(directory, descriptor)['packs'][0]
        pinned = directory / 'packs' / pack['pack_id'] / pack['files'][0]['path']
        original_claim = workflow.claim_dispatch
        def corrupt_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            pinned.write_bytes(pinned.read_bytes() + b'\ncorrupt')
            return claim
        token = operations._CURRENT.set(None)
        try:
            with patch.object(workflow, 'claim_dispatch', side_effect=corrupt_after_claim), \
                 patch.object(transport_synthetic, 'send') as send:
                with self.assertRaises(ProductionError) as caught:
                    execution.execute(self.root, self.run, decisions_file=decision_file)
        finally:
            operations._CURRENT.reset(token)
        self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
        send.assert_not_called()
        self.assertFalse(any(row['event'] == 'external-step' for row in store.event_rows(self.root, self.run)))


class PublicationBoundaryTests(unittest.TestCase):
    def test_nested_metadata_is_part_of_immutable_publication(self):
        import production_compiler as compiler
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ('manifest.json', 'owner.json', 'failure.json'):
                c.atomic(directory / 'references' / name, c.encoded({'source': name}))
            c.atomic(directory / 'owner.json', c.encoded({'operation_id': 'fixture'}))
            manifest = compiler.write_manifest(directory)
            self.assertEqual({item['path'] for item in manifest['files']},
                             {'references/manifest.json', 'references/owner.json', 'references/failure.json'})
            compiler.verify_publication(directory)
            (directory / 'references/manifest.json').write_bytes(b'changed')
            with self.assertRaises(ProductionError) as caught:
                compiler.verify_publication(directory)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
