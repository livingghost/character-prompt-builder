"""Current low-level request and formal-event boundaries; no network generation."""
from __future__ import annotations
import read_context
import production_fixtures as authoring_fixtures
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import execution_contract as c
import production_case_fixtures as f
import production_execution as execution
import production_store as store
import production_operations as workflow
import execution_lifecycle as accounting
import transport_synthetic
from production_diagnostics import ProductionError
from test_production_execution import decisions

import production_fixtures


class BoundaryTests(unittest.TestCase):
    @staticmethod
    def build_case(base):
        case = f.create(base / 'studio', base / 'runtime')
        return case, {'run': workflow.prepare(case['root'], 'task.json')['run']}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = f.CaseTemplate.for_class(cls, cls.build_case)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.case, metadata = f.CaseTemplate.for_test(
            self, Path(self.temp.name), self.build_case, getattr(type(self), 'template', None))
        self.root = self.case['root']
        self.run = metadata['run']
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

    @f.cold_case
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
        self.assertFalse(any(r['event'] in {'handoff','execution-created'} for r in store.event_rows(self.root,self.run)))

    def test_changed_package_cannot_claim_prepared_run(self):
        journal,rendered,tokens=self.authorized_journal()
        package=copy.deepcopy(self.data[4]);package['composition_prompt']+=' altered'
        with self.assertRaises(ProductionError) as caught:
            workflow.claim_dispatch(self.root,self.run,package,journal.path,self.data[6]['operations'][-1],tokens['submit'],rendered=rendered,authentication=None)
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
            workflow.claim_dispatch(self.root,self.run,self.data[4],journal.path,self.data[6]['operations'][-1],tokens['submit'],rendered=altered,authentication=None)
        self.assertTrue(caught.exception.diagnostic.pointer.startswith('$.request_contract'))
        self.assertEqual(accounting.all_states(self.root),[])

    def test_wrong_recipient_is_rejected_before_handoff(self):
        with self.assertRaises(ProductionError) as caught:
            workflow.handoff_intent(self.root,self.run,'another-recipient','dispatcher')
        self.assertEqual(caught.exception.diagnostic.pointer,'$.handoff.recipient')
        self.assertEqual(store.event_rows(self.root,self.run),[])

    def test_no_authorization_or_execution_claim_from_arbitrary_database_columns(self):
        journal,rendered,tokens=self.authorized_journal()
        with store.transaction(self.root) as db:
            db.execute('UPDATE events SET input_sha256=? WHERE scope=? AND sequence=1',('a'*64,self.run))
        with self.assertRaises(ProductionError) as caught:store.event_rows(self.root,self.run)
        self.assertEqual(caught.exception.diagnostic.code,'EVENT_CHAIN_CORRUPT')
        self.assertEqual(caught.exception.diagnostic.details['event'],1)

    def test_a_recorded_file_without_its_size_names_the_event_and_the_field(self):
        self.authorized_journal()
        granted=next(row for row in store.event_rows(self.root,self.run) if row['event']=='authorization')
        data=copy.deepcopy(granted['data']);data['files'][0].pop('size')
        recorded=store.append(self.root,self.run,granted['input_sha256'],'authorization',data)
        with self.assertRaises(ProductionError) as caught:workflow.load_run(self.root,self.run)
        found=caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'],found['run'],found['event'],found['kind'],found['sequence'],found['field']),
                         ('EVENT_CHAIN_CORRUPT',self.run,recorded['sha256'],'authorization',recorded['sequence'],'size'))
        self.assertIn(f"authorization event at sequence {recorded['sequence']}",found['message'])

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


    def test_execution_keeps_owned_runtime_after_claim_and_new_audit_detects_storage_damage(self):
        import operation_context as operations
        import runtime_snapshot
        decision_file = decisions(self.root, self.run)
        descriptor = self.data[1]['runtime_snapshot']
        directory = runtime_snapshot.path(self.root, descriptor)
        snapshot = runtime_snapshot.read(directory, descriptor)
        pack = snapshot['packs'][0]
        pinned = directory / 'packs' / pack['pack_id'] / pack['files'][0]['path']
        original_claim = workflow._claim_dispatch_from
        operation = operations.Operation('synthetic-integrity-boundary')
        token = operations._CURRENT.set(operation)
        def corrupt_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            pinned.write_bytes(pinned.read_bytes() + b'\ncorrupt')
            return claim
        try:
            with read_context.public_call():
                owned = runtime_snapshot.acquire_runtime(directory, descriptor)
                with patch.object(workflow, '_claim_dispatch_from', side_effect=corrupt_after_claim), \
                     patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
                    result = execution.execute(self.root, self.run, decisions_file=decision_file)
                self.assertTrue(result['execution_completed'], result)
                self.assertEqual(send.call_count, 1)
                self.assertIs(runtime_snapshot.acquire_runtime(directory, descriptor), owned)
                expected = copy.deepcopy(self.data[5]['request'])
                actual = send.call_args.args[0]
                expected['request_id'] = actual['request_id']
                self.assertEqual(actual, expected)
                with self.assertRaises(ProductionError) as caught:
                    runtime_snapshot.acquire_runtime(directory, descriptor, force_verify=True)
                self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
            with read_context.public_call(), self.assertRaises(ProductionError):
                runtime_snapshot.acquire_runtime(directory, descriptor)
            rows = store.event_rows(self.root, self.run)
            self.assertEqual(sum(row['event'] == 'external-step' and row['data']['step'] == 'send'
                                 for row in rows), 1)
        finally:
            operation.finish(0)
            operations._CURRENT.reset(token)

    def test_api_execution_uses_owned_snapshot_and_current_consent_without_logger(self):
        import operation_context as operations
        import runtime_snapshot
        decision_file = decisions(self.root, self.run)
        original_read = runtime_snapshot.acquire_runtime
        original_notices = runtime_snapshot.current_notices
        forced = []
        comparisons = []
        def observe(*args, **kwargs):
            if kwargs.get('force_verify'):
                forced.append(True)
            return original_read(*args, **kwargs)
        def compare(*args, **kwargs):
            comparisons.append(True)
            return original_notices(*args, **kwargs)
        original_send = transport_synthetic.send
        def send_saved(*args, **kwargs):
            self.assertEqual(comparisons, [])
            return original_send(*args, **kwargs)
        token = operations._CURRENT.set(None)
        try:
            with patch.object(runtime_snapshot, 'acquire_runtime', side_effect=observe), \
                 patch.object(runtime_snapshot, 'current_notices', side_effect=compare), \
                 patch.object(transport_synthetic, 'send', side_effect=send_saved) as send:
                result = execution.execute(self.root, self.run, decisions_file=decision_file)
            self.assertTrue(result['execution_completed'])
            self.assertEqual(forced, [])
            self.assertEqual(send.call_count, 1)
            # Only returned navigation compares current drafts. External steps
            # keep the operation's saved runtime and check current consent.
            self.assertEqual(len(comparisons), 1)
        finally:
            operations._CURRENT.reset(token)

    def test_draft_execution_uses_the_prepared_request_without_reading_live_sources(self):
        import runtime_snapshot
        original_notices = runtime_snapshot.current_notices
        compared = []
        def compare(*args, **kwargs):
            compared.append(True)
            return original_notices(*args, **kwargs)
        with patch.object(runtime_snapshot, 'current_notices', side_effect=compare):
            drafted = execution.draft_execution(self.root, self.run, 'fixture-grant')['choices']
        self.assertEqual(len(drafted['decisions']), len(self.data[6]['operations']))
        self.assertEqual(compared, [])

    def test_nested_rollback_rechecks_sources_left_changed_by_the_interrupted_writer(self):
        import runtime_snapshot
        with read_context.public_call(), store.transaction(self.root):
            workflow.assert_current(self.root, self.run)
            with self.assertRaisesRegex(RuntimeError, 'synthetic interrupted writer'):
                with store.transaction(self.root):
                    loaded = workflow.read_run(self.root, self.run)
                    (self.root / 'prompt.txt').write_text('Changed source survives a database rollback.\n', encoding='utf-8')
                    workflow.append_record(loaded, 'abandoned',
                        {'actor': 'Synthetic author', 'reason': 'Synthetic transaction that will roll back.'})
                    self.assertEqual(workflow.read_run(self.root, self.run).rows[-1]['event'], 'abandoned')
                    raise RuntimeError('synthetic interrupted writer')
            self.assertEqual(workflow.read_run(self.root, self.run).rows, [])
            workflow.assert_current(self.root, self.run)
            failures, notices = workflow.freshness(self.root, self.run)
            self.assertEqual(failures, [])
            [notice] = [item for item in notices if item['code'] == 'SOURCE_CHANGED']
            self.assertEqual((notice['file'], notice['severity']), ('prompt.txt', 'warning'))

    def assert_saved_request_sent(self, send, result):
        self.assertEqual(send.call_count, 1)
        expected = copy.deepcopy(self.data[5]['request'])
        actual = send.call_args.args[0]
        # The synthetic transport fills this declared management field once.
        expected['request_id'] = actual['request_id']
        self.assertEqual(actual, expected)
        self.assertTrue(result['execution_completed'])
        report = result['runs'][0]
        self.assertEqual(report['readiness'], 'ready')
        self.assertEqual(report['freshness_diagnostics'], [])
        self.assertIn(('SOURCE_CHANGED', 'warning'),
                      [(row['code'], row['severity']) for row in report['freshness_notices']])

    def source_changed_after_preflight(self, *, preauthorized: bool) -> None:
        decision_file = decisions(self.root, self.run)
        if preauthorized:
            execution.authorize_decisions(self.root, self.run, decision_file, self.data[1], self.data[6])
        original_preflight = execution.require_recording

        def edit_after_preflight(*args, **kwargs):
            result = original_preflight(*args, **kwargs)
            (self.root / 'prompt.txt').write_text('A source edited after the execution preflight.\n', encoding='utf-8')
            return result

        with patch.object(execution, 'require_recording', side_effect=edit_after_preflight), \
             patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            result = execution.execute(self.root, self.run, decisions_file=None if preauthorized else decision_file)
        self.assert_saved_request_sent(send, result)

    def test_source_edited_during_preflight_keeps_the_saved_request_when_authorizing(self):
        self.source_changed_after_preflight(preauthorized=False)

    def test_source_edited_during_preflight_keeps_the_saved_request_with_existing_authorizations(self):
        self.source_changed_after_preflight(preauthorized=True)

    def test_editable_choices_and_reading_key_do_not_replace_an_explicit_saved_request(self):
        import production_inputs
        draft = authoring_fixtures.authoring_inputs(self.root, 'task.json', 'work/editable')
        self.run = workflow.prepare(self.root, choices=draft['choices_file'])['run']
        self.data = execution.compiled(self.root, self.run)
        prepared = self.data[1]
        choices = self.root / draft['choices_file']
        authored = c.load(choices)
        # Formatting and a new context's reading selection belong to the
        # editable draft; neither changes the request selected by run ID.
        choices.write_text(json.dumps(authored, indent=4) + '\n', encoding='utf-8')
        workflow.assert_current(self.root, self.run)
        authored['reading']['reading_key'] = 'a-new-context-will-fill-its-own-reading-key'
        choices.write_bytes(c.encoded(authored))
        source = self.root / prepared['authoring']['source_map']['authoring.delivery']['file']
        source.unlink()
        approved = decisions(self.root, self.run)
        with patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            result = execution.execute(self.root, self.run, decisions_file=approved)
        self.assert_saved_request_sent(send, result)
        self.assertEqual(workflow.read_run(self.root, self.run).prepared['input_sha256'], prepared['input_sha256'])
        self.assertTrue({draft['choices_file'], source.relative_to(self.root).as_posix()} <=
                        {item['file'] for item in result['runs'][0]['freshness_notices']})

    def test_source_deleted_after_claim_keeps_the_saved_request(self):
        decision_file = decisions(self.root, self.run)
        original_claim = workflow._claim_dispatch_from
        def edit_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            (self.root / 'prompt.txt').unlink()
            return claim
        with patch.object(workflow, '_claim_dispatch_from', side_effect=edit_after_claim), \
             patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
            result = execution.execute(self.root, self.run, decisions_file=decision_file)
        self.assert_saved_request_sent(send, result)
        rows = store.event_rows(self.root, self.run)
        self.assertTrue(any(row['event'] == 'dispatch-claim' for row in rows))
        self.assertEqual(len([row for row in rows if row['event'] == 'external-step']), 1)

    def test_source_edited_during_the_send_is_reported_without_blocking_the_saved_run(self):
        decision_file = decisions(self.root, self.run)
        original_send = transport_synthetic.send
        def edit_during_send(*args, **kwargs):
            (self.root / 'prompt.txt').write_text('A prompt edited while the provider worked.\n', encoding='utf-8')
            return original_send(*args, **kwargs)
        with patch.object(transport_synthetic, 'send', side_effect=edit_during_send) as send:
            result = execution.execute(self.root, self.run, decisions_file=decision_file)
        self.assert_saved_request_sent(send, result)

    def prepared_external_claim(self) -> tuple[str, str]:
        import production_fixtures as fixture
        task = c.load(self.root / 'task.json')
        task['execution'] = 'external'
        task['generation'] = {'production_spec': task['generation']['production_spec']}
        fixture.external_image_input(self.root, task)
        from reading_fixtures import task_reading
        task_reading(self.root, task)
        f.write(self.root / 'task.json', task)
        run = workflow.prepare(self.root, 'task.json')['run']
        fixture.handoff(self.root, run, 'synthetic external host', 'manual')
        token = fixture.grant(self.root, run, workflow.external_intent(self.root, run, 1))
        return run, token

    def test_source_edited_inside_the_external_claim_keeps_the_saved_request(self):
        run, token = self.prepared_external_claim()
        prepared = workflow.read_run(self.root, run)
        before = prepared.consumer
        source_path = next(row['path'] for row in prepared.prepared['task']['sources'] if row['id'] == 'brief')
        original_commit = accounting.commit_effect
        def edit_after_commit(*args, **kwargs):
            row = original_commit(*args, **kwargs)
            (self.root / source_path).write_text('A brief edited inside the claim transaction.\n', encoding='utf-8')
            return row
        with patch.object(accounting, 'commit_effect', side_effect=edit_after_commit):
            claim = workflow.claim_external(self.root, run, 1, token)
        loaded = workflow.read_run(self.root, run)
        self.assertEqual(loaded.consumer, before)
        self.assertEqual(claim['data']['external_request_sha256'], before['image_input']['external_request']['sha256'])
        self.assertEqual(len([row for row in loaded.rows if row['event'] == 'external-step']), 1)
        failures, notices = workflow.freshness(self.root, run)
        self.assertEqual(failures, [])
        self.assertIn(('SOURCE_CHANGED', source_path), [(item['code'], item.get('file')) for item in notices])

    def test_external_claim_keeps_owned_request_when_its_stored_object_changes(self):
        run, token = self.prepared_external_claim()
        original_commit = accounting.commit_effect
        with read_context.public_call():
            held = workflow.read_run(self.root, run)
            dependency = next(item for item in held.prepared['dependencies'] if item['space'] == 'studio')
            key = dependency['sha256']
            original = held.evidence.read(key)
            self.assertEqual(c.digest(original), key)

            def corrupt_after_commit(*args, **kwargs):
                row = original_commit(*args, **kwargs)
                (held.directory / 'objects' / key).write_bytes(b'corrupt stored source snapshot')
                return row

            with patch.object(accounting, 'commit_effect', side_effect=corrupt_after_commit):
                claim = workflow.claim_external(self.root, run, 1, token)
            current = workflow.read_run(self.root, run)
            self.assertIs(current.consumer, held.consumer)
            self.assertIs(current.evidence, held.evidence)
            self.assertEqual(current.evidence.read(key), original)
            self.assertEqual(claim['data']['external_request_sha256'],
                             held.consumer['image_input']['external_request']['sha256'])
            self.assertEqual(claim['data']['authorizations'], [token])
            steps = [row for row in current.rows if row['event'] == 'external-step']
            self.assertEqual(len(steps), 1)
            self.assertEqual((steps[0]['data']['step'], steps[0]['data']['claim']),
                             ('external-send', claim['sha256']))
            with self.assertRaises(ProductionError) as forced:
                workflow.read_run(self.root, run, force=True)
            self.assertEqual(forced.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        with read_context.public_call(), self.assertRaises(ProductionError) as audited:
            workflow.read_run(self.root, run)
        self.assertEqual(audited.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')

    def test_send_keeps_owned_run_bytes_after_its_stored_object_changes(self):
        decision_file = decisions(self.root, self.run)
        directory = workflow.run_dir(self.root, self.run)
        dependency = next(item for item in self.data[1]['dependencies'] if item['space'] == 'studio')
        original_claim = workflow._claim_dispatch_from
        def corrupt_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            (directory / 'objects' / dependency['sha256']).write_bytes(b'corrupt stored source snapshot')
            return claim
        with read_context.public_call():
            held = workflow.read_run(self.root, self.run)
            original = held.evidence.read(dependency['sha256'])
            self.assertEqual(c.digest(original), dependency['sha256'])
            with patch.object(workflow, '_claim_dispatch_from', side_effect=corrupt_after_claim), \
                 patch.object(transport_synthetic, 'send', wraps=transport_synthetic.send) as send:
                result = execution.execute(self.root, self.run, decisions_file=decision_file)
            self.assertTrue(result['execution_completed'], result)
            self.assertEqual(send.call_count, 1)
            expected = copy.deepcopy(self.data[5]['request'])
            actual = send.call_args.args[0]
            expected['request_id'] = actual['request_id']
            self.assertEqual(actual, expected)
            current = workflow.read_run(self.root, self.run)
            self.assertIs(current.prepared, held.prepared)
            self.assertIs(current.evidence, held.evidence)
            self.assertEqual(current.evidence.read(dependency['sha256']), original)
            with self.assertRaises(ProductionError) as forced:
                workflow.read_run(self.root, self.run, force=True)
            self.assertEqual(forced.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        with read_context.public_call(), self.assertRaises(ProductionError) as audited:
            workflow.read_run(self.root, self.run)
        self.assertEqual(audited.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        rows = store.event_rows(self.root, self.run)
        self.assertEqual(sum(row['event'] == 'external-step' and row['data']['step'] == 'send' for row in rows), 1)

    def test_api_send_keeps_owned_runtime_and_new_audit_detects_changed_storage(self):
        import operation_context as operations
        import runtime_snapshot
        decision_file = decisions(self.root, self.run)
        descriptor = self.data[1]['runtime_snapshot']
        directory = runtime_snapshot.path(self.root, descriptor)
        pack = runtime_snapshot.read(directory, descriptor)['packs'][0]
        pinned = directory / 'packs' / pack['pack_id'] / pack['files'][0]['path']
        original = pinned.read_bytes()
        original_claim = workflow._claim_dispatch_from
        original_send = transport_synthetic.send
        owners = []
        def corrupt_after_claim(*args, **kwargs):
            claim = original_claim(*args, **kwargs)
            owners.append(runtime_snapshot.acquire_runtime(directory, descriptor))
            pinned.write_bytes(original + b'\ncorrupt')
            return claim
        def send_owned(*args, **kwargs):
            self.assertIs(runtime_snapshot.acquire_runtime(directory, descriptor), owners[0])
            self.assertEqual(owners[0].read_pack(pack['pack_id'], pack['files'][0]['path']), original)
            expected = copy.deepcopy(self.data[5]['request'])
            expected['request_id'] = args[0]['request_id']
            self.assertEqual(args[0], expected)
            return original_send(*args, **kwargs)
        token = operations._CURRENT.set(None)
        try:
            with patch.object(workflow, '_claim_dispatch_from', side_effect=corrupt_after_claim), \
                 patch.object(transport_synthetic, 'send', side_effect=send_owned) as send:
                result = execution.execute(self.root, self.run, decisions_file=decision_file)
            self.assertTrue(result['execution_completed'], result)
            self.assertEqual(send.call_count, 1)
            with read_context.public_call(), self.assertRaises(ProductionError) as audited:
                workflow.assert_current(self.root, self.run)
            self.assertEqual(audited.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
        finally:
            operations._CURRENT.reset(token)
        rows = store.event_rows(self.root, self.run)
        self.assertEqual(sum(row['event'] == 'external-step' and row['data']['step'] == 'send' for row in rows), 1)


class PublicationBoundaryTests(unittest.TestCase):
    def test_nested_metadata_is_part_of_immutable_publication(self):
        import production_compiler as compiler
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            artifacts = ArtifactSet(directory)
            for name in ('manifest.json', 'owner.json', 'failure.json'):
                artifacts.write('references/' + name, c.encoded({'source': name}))
            c.atomic(directory / 'owner.json', c.encoded({'operation_id': 'fixture'}))
            manifest = compiler.write_manifest(directory, artifacts)
            self.assertEqual({item['path'] for item in manifest['files']},
                             {'references/manifest.json', 'references/owner.json', 'references/failure.json'})
            compiler.verify_publication(directory)
            (directory / 'references/manifest.json').write_bytes(b'changed')
            with self.assertRaises(ProductionError) as caught:
                compiler.verify_publication(directory)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_unknown_stage_member_is_kept_without_becoming_a_publication(self):
        import production_compiler as compiler
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            artifacts = ArtifactSet(directory)
            artifacts.write('delivery.txt', b'authored content')
            extra = directory / 'runtime' / 'records' / 'unexpected.json'
            c.atomic(extra, b'preserved unexpected bytes')
            with self.assertRaises(ProductionError) as caught:
                compiler.write_manifest(directory, artifacts)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_SET_MISMATCH')
            self.assertIn('runtime/records/unexpected.json', caught.exception.diagnostic.details['unexpected'])
            self.assertEqual(extra.read_bytes(), b'preserved unexpected bytes')
            self.assertFalse((directory / 'manifest.json').exists())

    def test_published_inputs_keep_their_membership_as_other_owners_write_later_files(self):
        import production_compiler as compiler
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            artifacts = ArtifactSet(directory)
            artifacts.write('inputs/task.json', b'{}\n')
            original = compiler.write_manifest(directory, artifacts)
            c.object_store(directory, b'later candidate evidence')
            c.atomic(directory / 'review-draft.json', b'{}\n')
            self.assertEqual(compiler.verify_publication(directory), original)
            self.assertEqual(artifacts.files(), original['files'])
            (directory / 'inputs/task.json').write_bytes(b'changed original bytes')
            with self.assertRaises(ProductionError) as caught:
                compiler.verify_publication(directory)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_companion_copy_uses_every_owned_file_and_refuses_an_extra(self):
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            artifacts = ArtifactSet(base / 'source')
            artifacts.write('bundle/manifest.json', b'{"approved":true}\n')
            artifacts.write('bundle/image.bin', b'exact carrier bytes')
            companion = artifacts.subtree('bundle')
            companion.copy_to(base / 'first')
            self.assertEqual((base / 'first/manifest.json').read_bytes(), b'{"approved":true}\n')
            self.assertEqual((base / 'first/image.bin').read_bytes(), b'exact carrier bytes')
            extra = base / 'source/bundle/unowned.bin'
            c.atomic(extra, b'unowned')
            with self.assertRaises(ProductionError) as caught:
                companion.copy_to(base / 'second')
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_SET_MISMATCH')
            self.assertFalse((base / 'second').exists())
            self.assertEqual(extra.read_bytes(), b'unowned')

    def test_declarations_validate_structure_before_duplicate_or_conflict_checks(self):
        import publication_artifacts
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            row = {'path': 'item.txt', 'sha256': c.digest(b'first'), 'size': 5}
            for bad in ([{**row, 'path': []}], [row, row], [{**row, 'size': True}], [{**row, 'path': '../item.txt'}]):
                with self.subTest(rows=bad), self.assertRaises(ProductionError) as caught:
                    ArtifactSet(root, bad)
                self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_MANIFEST_CORRUPT')
                self.assertEqual(caught.exception.diagnostic.required_action, publication_artifacts.DECLARATION_DAMAGED)
            with self.assertRaises(ProductionError) as caught:
                ArtifactSet(root, [row, row], damaged='Synthetic repair of the holder of these rows.')
            self.assertEqual(caught.exception.diagnostic.required_action, 'Synthetic repair of the holder of these rows.')
            artifacts = ArtifactSet(root, [row], damaged='Synthetic repair of the holder of these rows.')
            with self.assertRaises(ProductionError) as caught:
                artifacts.add('item.txt', b'different')
            conflict = caught.exception.diagnostic.as_dict()
            self.assertEqual((conflict['code'], conflict['path'], conflict['required_action']),
                             ('ARTIFACT_MANIFEST_CORRUPT', 'item.txt', publication_artifacts.OPERATION_CONFLICT))
            self.assertEqual(artifacts.files(), [row])

    def test_an_explicitly_declared_control_remains_a_verified_member(self):
        import production_compiler as compiler
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            artifacts = ArtifactSet(directory)
            artifacts.write('delivery.txt', b'delivery')
            artifacts.write('owner.json', c.encoded({'operation_id': 'synthetic-owner'}))
            manifest = compiler.write_manifest(directory, artifacts)
            self.assertEqual(compiler.verify_publication(directory), manifest)
            (directory / 'owner.json').write_bytes(c.encoded({'operation_id': 'changed-owner'}))
            with self.assertRaises(ProductionError) as caught:
                compiler.verify_publication(directory)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_a_rewrite_requires_the_producer_to_own_the_existing_file(self):
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            c.atomic(directory / 'plan.json', b'unclaimed bytes')
            artifacts = ArtifactSet(directory)
            with self.assertRaises(FileExistsError):
                artifacts.write('plan.json', b'new producer bytes', replace=True)
            self.assertEqual((directory / 'plan.json').read_bytes(), b'unclaimed bytes')
            self.assertEqual(artifacts.files(), [])

    def test_producer_paths_keep_link_spelling_until_the_shared_owner_checks_it(self):
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            directory = base / 'stage'
            artifacts = ArtifactSet(directory)
            artifacts.write('owned/item.bin', b'original internal bytes')
            outside = base / 'outside/item.bin'
            c.atomic(outside, b'original outside bytes')
            for label, target in (('internal', directory / 'owned/item.bin'), ('outside', outside)):
                with self.subTest(target=label):
                    leaf = directory / (label + '-link.bin')
                    folder = directory / (label + '-folder')
                    try:
                        leaf.symlink_to(target)
                        folder.symlink_to(target.parent, target_is_directory=True)
                    except (OSError, NotImplementedError) as exc:
                        self.skipTest('Symlink creation is unavailable: ' + str(exc))
                    original = target.read_bytes()
                    for path in (leaf, folder / target.name):
                        with self.assertRaises(ValueError):
                            artifacts.write(path, b'changed through alias', replace=True)
                        self.assertEqual(target.read_bytes(), original)

    def test_producer_path_accepts_the_declared_root_spelling(self):
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'parent').mkdir()
            spelling = base / 'parent' / '..' / 'stage'
            artifacts = ArtifactSet(spelling)
            artifacts.write(spelling / 'item.txt', b'owned bytes')
            artifacts.require_membership()
            self.assertEqual(artifacts.root, (base / 'stage').resolve())
            self.assertEqual(artifacts.files(), [{'path': 'item.txt', 'sha256': c.digest(b'owned bytes'), 'size': 11}])

if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
