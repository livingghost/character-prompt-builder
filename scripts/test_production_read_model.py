"""Read ownership, mutation invalidation and forced verification of real runs."""
from __future__ import annotations

from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_compiler as compiler
import production_fixtures
import production_store as store
import production_workflow as workflow
import production_execution as execution
import execution_lifecycle as lifecycle
import runtime_snapshot
import studio
import studio_activity
from production_diagnostics import ProductionError, compare_exact
from production_read_model import RunSnapshot, RunView
from owned_json import freeze, mutable


class RunReadBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.home = production_fixtures.scratch_home(cls.base / 'home')
        cls.home.__enter__()
        cls.addClassCleanup(cls.home.__exit__, None, None, None)
        from catalog_retrieval import runtime
        cls.addClassCleanup(runtime.configure_pack_runtime, None)
        cls.case = fixtures.create(cls.base / 'template', cls.base / 'runtime')
        cls.run_id = workflow.prepare(cls.case['root'], 'task.json')['run']

    def setUp(self):
        self.root = fixtures.copy_studio(self.case['root'], self.base / self._testMethodName)
        from catalog_retrieval import runtime
        runtime.configure_pack_runtime(self.case['settings'])

    def test_nested_reads_do_not_reopen_storage_and_cannot_mutate_each_other(self):
        with runtime_snapshot.public_call(), \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication, \
             patch.object(store, 'read_history', wraps=store.read_history) as history:
            first = workflow.load_run(self.root, self.run_id)
            self.assertIsInstance(first, RunSnapshot)
            expected = first.prepared['task']['criteria'][0]['text']
            first.prepared['task']['criteria'][0]['text'] = 'Caller-owned edit'
            first.consumer['caller-edit'] = True
            first.rows.append({'event': 'caller-edit'})
            with patch.object(c, 'read', side_effect=AssertionError('A nested run read must use decoded values')):
                second = workflow.load_run(self.root, self.run_id)
            self.assertEqual(second.prepared['task']['criteria'][0]['text'], expected)
            self.assertNotIn('caller-edit', second.consumer)
            self.assertEqual(second.rows, [])
            self.assertEqual((publication.call_count, history.call_count), (1, 1))

    def test_internal_view_shares_values_and_status_uses_the_verified_index(self):
        with runtime_snapshot.public_call():
            held = workflow.read_run(self.root, self.run_id)
            self.assertIsInstance(held, RunView)
            self.assertIs(held.rows.lifecycle, held.lifecycle)
            self.assertIs(held.lifecycle.prepared, held.prepared)
            with patch.object(RunView, 'snapshot', side_effect=AssertionError('read-only work must not export a run')), \
                 patch.object(store, 'authority', side_effect=AssertionError('read-only work must not export current grants')), \
                 patch.object(lifecycle.ReplayState, '__init__', side_effect=AssertionError('reuse the verified lifecycle')), \
                 patch.object(compiler, 'acquire_publication', side_effect=AssertionError('reuse the verified publication')):
                again = workflow.read_run(self.root, self.run_id)
                report = execution.status(self.root, self.run_id)
            self.assertIs(again, held)
            self.assertTrue(report['ok'], report)
            for action in (lambda: held.prepared['task']['criteria'][0].update(text='Changed'),
                           lambda: held.consumer.update(changed=True),
                           lambda: held.rows.append({}),
                           lambda: held.lifecycle.executions.update(changed={}),
                           lambda: setattr(held.lifecycle, 'closed', 'completion'),
                           lambda: delattr(held.lifecycle, '_sealed'),
                           lambda: setattr(held.rows, 'lifecycle', None),
                           lambda: delattr(held.rows, 'lifecycle'),
                           lambda: held.artifacts['execution-plan.json']['operations'].clear()):
                with self.assertRaises(TypeError):
                    action()

    def test_decoded_artifact_uses_the_bytes_that_passed_publication_verification(self):
        directory = workflow.run_dir(self.root, self.run_id)
        package = directory / 'package.json'
        expected = c.decode(package.read_bytes())
        original = c.read
        original_load = c.load
        captured = []

        def change_after_read(path, *args, **kwargs):
            raw = original(path, *args, **kwargs)
            if path == package:
                captured.append(path)
                path.write_bytes(raw + b' ')
            return raw

        def refuse_publication_reopen(path, *args, **kwargs):
            if Path(path).parent == directory:
                raise AssertionError('published JSON must come from its read owner')
            return original_load(path, *args, **kwargs)

        with runtime_snapshot.public_call():
            with patch.object(c, 'read', side_effect=change_after_read):
                held = workflow.read_run(self.root, self.run_id)
            self.assertEqual(captured, [package])
            self.assertEqual(held.artifacts['package.json'], expected)
            with patch.object(c, 'load', side_effect=AssertionError('compiled artifacts are owned values')):
                compiled = execution.compiled(self.root, self.run_id, loaded=held)
            self.assertIs(compiled[4], held.artifacts['package.json'])
            with patch.object(c, 'load', side_effect=refuse_publication_reopen):
                handoff = held.artifacts['execution-plan.json']['handoff']
                workflow.handoff_intent(self.root, self.run_id, handoff['recipient'], handoff['method'])
                workflow.review_basis(self.root, self.run_id)
            with self.assertRaises(ProductionError) as caught:
                workflow.read_run(self.root, self.run_id, force=True)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_candidate_reads_receive_decoded_values_without_lazy_interpretation(self):
        decisions = fixtures.fill_decisions(self.root, self.run_id, 'synthetic-decisions.json')
        result = execution.execute(self.root, self.run_id, decisions_file=decisions)
        candidate = result['runs'][0]['candidates'][0]
        directory = workflow.run_dir(self.root, self.run_id)
        raw = {name: (directory / name).read_bytes() for name in
               ('package.json', 'request-contract.json', 'execution-plan.json', 'execution-target.json')}

        with patch.object(c, 'decode', wraps=c.decode) as decode, runtime_snapshot.public_call():
            held = workflow.read_run(self.root, self.run_id)
            interpreted = Counter(name for call in decode.call_args_list for name, data in raw.items()
                                  if call.args[0] == data)
            self.assertEqual(interpreted, {name: 1 for name in raw})
            with patch.object(c, 'decode', side_effect=AssertionError('domain values must already be decoded')):
                self.assertTrue(all(isinstance(held.artifacts[name], dict) for name in raw))
            draft = workflow.draft_review(self.root, self.run_id, candidate)
            state = workflow.candidate_state(self.root, self.run_id, candidate)
            self.assertEqual(draft['candidate'], candidate)
            self.assertEqual(state['evaluation'], 'unreviewed')
            workflow.review_basis(self.root, self.run_id, candidate)
            first = execution.compiled(self.root, self.run_id, loaded=held)
            again = execution.compiled(self.root, self.run_id, loaded=held)
            self.assertIs(first[4], again[4])
            interpreted = Counter(name for call in decode.call_args_list for name, data in raw.items()
                                  if call.args[0] == data)
            self.assertEqual(interpreted, {name: 1 for name in raw})

    def test_new_boundaries_reacquire_documents_and_event_evidence(self):
        directory = workflow.run_dir(self.root, self.run_id)
        raw = {name: (directory / name).read_bytes() for name in
               ('manifest.json', 'prepared.json', 'consumer.json', 'execution-plan.json')}
        with runtime_snapshot.public_call(), \
             patch.object(c, 'decode', wraps=c.decode) as decode, \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as acquire:
            first = workflow.read_run(self.root, self.run_id)
            plan = first.artifacts['execution-plan.json']
            with store.transaction(self.root):
                transaction = workflow.read_run(self.root, self.run_id)
                self.assertIsNot(transaction.prepared, first.prepared)
                self.assertIsNot(transaction.artifacts['execution-plan.json'], plan)
                self.assertEqual(transaction.artifacts['execution-plan.json'], plan)
                self.assertIsNot(transaction.evidence, first.evidence)
                self.assertIsNot(transaction.lifecycle, first.lifecycle)
                forced = workflow.read_run(self.root, self.run_id, force=True)
                self.assertIsNot(forced.prepared, transaction.prepared)
                self.assertIsNot(forced.artifacts['execution-plan.json'], transaction.artifacts['execution-plan.json'])
                self.assertEqual(forced.artifacts['execution-plan.json'], plan)
                self.assertIsNot(forced.evidence, transaction.evidence)
            after = workflow.read_run(self.root, self.run_id)
            self.assertIsNot(after.prepared, forced.prepared)
            self.assertIsNot(after.artifacts['execution-plan.json'], plan)
            self.assertEqual(after.artifacts['execution-plan.json'], plan)
            self.assertIsNot(after.evidence, forced.evidence)
            self.assertEqual(acquire.call_count, 4)
            interpreted = Counter(name for call in decode.call_args_list for name, data in raw.items()
                                  if call.args[0] == data)
            self.assertEqual(interpreted, {name: 4 for name in raw})

    def test_transaction_boundary_without_run_read_discards_publication_proof(self):
        with runtime_snapshot.public_call():
            held = workflow.read_run(self.root, self.run_id)
            path = held.directory / 'request-contract.json'
            with store.transaction(self.root):
                path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaises(ProductionError) as caught:
                workflow.read_run(self.root, self.run_id)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_failed_nested_fresh_read_cannot_restore_the_parent_success(self):
        with runtime_snapshot.public_call():
            observed = workflow.read_run(self.root, self.run_id)
            path = observed.directory / 'consumer.json'
            with runtime_snapshot.public_call(fresh=True):
                path.write_bytes(path.read_bytes() + b' ')
                with self.assertRaises(ProductionError) as inner:
                    workflow.read_run(self.root, self.run_id, force=True)
                self.assertEqual(inner.exception.diagnostic.code, 'ARTIFACT_CORRUPT')
            # The old value remains an observation. It cannot certify another
            # acquisition after the newer boundary already observed damage.
            self.assertEqual(observed.prepared['run'], self.run_id)
            with self.assertRaises(ProductionError) as outer:
                workflow.read_run(self.root, self.run_id)
            self.assertEqual(outer.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_fresh_read_inside_a_transaction_discards_its_enclosing_observation(self):
        with runtime_snapshot.public_call(), store.transaction(self.root):
            observed = workflow.read_run(self.root, self.run_id)
            path = observed.directory / 'consumer.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with runtime_snapshot.public_call(fresh=True):
                with self.assertRaises(ProductionError) as inner:
                    workflow.read_run(self.root, self.run_id)
                self.assertEqual(inner.exception.diagnostic.code, 'ARTIFACT_CORRUPT')
            with self.assertRaises(ProductionError) as outer:
                workflow.read_run(self.root, self.run_id)
            self.assertEqual(outer.exception.diagnostic.code, 'ARTIFACT_CORRUPT')
            self.assertEqual(observed.consumer, c.decode(original))
            path.write_bytes(original)
            recovered = workflow.read_run(self.root, self.run_id)
            self.assertIsNot(recovered, observed)
            self.assertEqual(recovered.consumer, observed.consumer)

    def test_another_current_acquisition_reads_changed_sources_without_a_success_marker(self):
        with runtime_snapshot.public_call(), store.transaction(self.root):
            first = workflow.read_current(self.root, self.run_id)
            source = self.root / 'prompt.txt'
            before = source.read_bytes()
            dependency = next(item for item in first.view.prepared['dependencies']
                              if item['space'] == 'studio' and item['path'] == 'prompt.txt')
            self.assertEqual(first.sources.dependency(dependency).content, before)
            source.write_bytes(before + b' A changed source.')
            with self.assertRaises(ProductionError) as changed:
                workflow.read_current(self.root, self.run_id)
            self.assertEqual(changed.exception.diagnostic.code, 'SOURCE_CHANGED')
            self.assertEqual(first.sources.dependency(dependency).content, before)
            with self.assertRaises(ProductionError):
                workflow.assert_current(self.root, self.run_id)

    def test_rechecked_publication_reacquires_evidence_added_after_publication(self):
        loaded = workflow.read_run(self.root, self.run_id)
        intent = next(item for item in loaded.artifacts['execution-plan.json']['operations']
                      if item['operation'] == 'direction')
        authorization = production_fixtures.grant(self.root, self.run_id, intent)
        held = workflow.read_run(self.root, self.run_id)
        evidence = workflow.find(held.rows, 'authorization', authorization)['data']['files'][0]
        path = held.directory / 'objects' / evidence['sha256']
        raw = path.read_bytes()
        manifest = compiler.read_manifest(held.directory)
        self.assertNotIn('objects/' + evidence['sha256'], {item['path'] for item in manifest['files']})

        for boundary in ('force', 'transaction'):
            with self.subTest(boundary=boundary), runtime_snapshot.public_call():
                before = workflow.read_run(self.root, self.run_id)
                self.assertEqual(before.evidence.read(evidence['sha256']), raw)
                path.write_bytes(raw + b' changed')
                try:
                    if boundary == 'force':
                        with self.assertRaises(ProductionError) as caught:
                            workflow.read_run(self.root, self.run_id, force=True)
                    else:
                        with store.transaction(self.root), self.assertRaises(ProductionError) as caught:
                            workflow.read_run(self.root, self.run_id)
                    self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_MISSING')
                    with self.assertRaises(ProductionError):
                        workflow.read_run(self.root, self.run_id)
                    self.assertEqual(before.evidence.read(evidence['sha256']), raw)
                finally:
                    path.write_bytes(raw)

    def test_interpreted_dispatcher_documents_keep_their_semantic_bindings(self):
        directory = workflow.run_dir(self.root, self.run_id)
        original = c.load(directory / 'prepared.json')
        documents = {name: c.load(directory / name) for name in
                     ('package.json', 'request-contract.json', 'execution-plan.json')}
        cases = ('package', 'plan', 'plan-request', 'request-binding', 'request-seal')
        for defect in cases:
            with self.subTest(defect=defect):
                prepared, values = copy.deepcopy(original), copy.deepcopy(documents)
                if defect == 'package':
                    prepared['compiled']['package_sha256'] = '0' * 64
                    name = 'package.json'
                elif defect == 'plan':
                    prepared['compiled']['plan_sha256'] = '0' * 64
                    name = 'execution-plan.json'
                elif defect == 'plan-request':
                    name = 'execution-plan.json'
                    values[name]['request_sha256'] = '0' * 64
                    prepared['compiled']['plan_sha256'] = c.content_id(values[name])
                else:
                    name = 'request-contract.json'
                    if defect == 'request-binding':
                        values[name]['request_sha256'] = '0' * 64
                    else:
                        values[name]['request']['unsealed-field'] = True
                for _ in range(2):
                    with self.assertRaises(ValueError):
                        compiler.validate_execution_documents(prepared, freeze(values))

        missing = freeze({'package.json': documents['package.json']})
        with self.assertRaises(KeyError):
            compiler.validate_execution_documents(original, missing)
        extra = copy.deepcopy(original)
        extra['compiled']['undeclared-binding'] = '0' * 64
        with self.assertRaises(ProductionError):
            compiler.validate_execution_documents(extra, freeze(documents))

    def test_current_authority_is_separate_from_the_published_input(self):
        with runtime_snapshot.public_call():
            held = workflow.read_run(self.root, self.run_id)
            original = copy.deepcopy(held.prepared)
            prior = workflow.current_authority(self.root, held.prepared)
            updated = mutable(prior.document)
            updated['grants'][0]['actor'] = 'Updated synthetic actor'
            c.atomic(self.root / 'updated-authority.json', c.encoded(updated))
            changed = store.import_authority(self.root, 'updated-authority.json', expected=prior.event['sha256'])
            current = workflow.current_authority(self.root, held.prepared)
            self.assertEqual(current.event['sha256'], changed['sha256'])
            self.assertEqual(current.document, updated)
            self.assertNotEqual(current.document, prior.document)
            intent = held.artifacts['execution-plan.json']['operations'][0]
            draft = workflow.draft_authorization_from(held, current, updated['grants'][0]['id'], intent)
            self.assertEqual(draft['actor'], 'Updated synthetic actor')
            draft['payload']['caller-edit'] = True
            self.assertNotIn('caller-edit', intent['payload'])
            self.assertEqual(held.prepared, original)
            self.assertEqual(workflow.read_run(self.root, self.run_id).prepared, original)

    def test_input_capture_uses_the_authority_evidence_acquired_with_its_grants(self):
        authority = store.read_authority(self.root, self.case['task']['task_id'])
        expected = {item['sha256']: item['raw'] for item in authority.evidence}
        reads = Counter()
        original_read = c.read

        def count(path, *args, **kwargs):
            path = Path(path)
            if path.parent == self.root / 'production/objects':
                reads[path.name] += 1
            return original_read(path, *args, **kwargs)

        with patch.object(c, 'read', side_effect=count), \
             patch.object(store, 'read_authority', wraps=store.read_authority) as acquire, \
             patch.object(store, 'authority_record', side_effect=AssertionError('use the acquired authority event')):
            prepared, _, dependencies, blobs = workflow.snapshot(self.root, 'task.json')
        self.assertEqual(acquire.call_count, 1)
        self.assertEqual(reads, Counter({key: 1 for key in expected}))
        self.assertEqual(prepared['authority'], authority.document)
        self.assertTrue(all(blobs[key] == raw for key, raw in expected.items()))
        self.assertTrue(set(expected).issubset({item['sha256'] for item in dependencies if item['space'] == 'evidence'}))

    def test_submission_shares_authority_bytes_and_preserves_distinct_readings_of_one_source(self):
        import request_scope
        loaded = workflow.read_run(self.root, self.run_id)
        prior = store.read_authority(self.root, self.case['task']['task_id'])
        intent = next(item for item in loaded.artifacts['execution-plan.json']['operations']
                      if item['operation'] == 'submit')
        rendered = intent['payload']['request_contract']
        basis = next(item for item in prior.evidence if item['purpose'] == 'authority-declaration')
        ref = {key: basis[key] for key in ('path', 'sha256', 'locator')}
        content = next(key for key, value in rendered['fields'].items() if value['kind'] == 'content')
        case = request_scope.build_case(rendered, identifier='synthetic-case',
            productions=[loaded.prepared['task']['production_id']],
            variations={content: {'kind': 'authored-content', 'source': ref, 'criterion': 'synthetic-content'}},
            review_criteria=['synthetic-content'])
        amended = mutable(prior.document)
        amended['grants'][0]['request_scope'] = {'plan': ref, 'cases': [case]}
        fixtures.write(self.root / 'scoped-authority.json', amended)
        store.import_authority(self.root, 'scoped-authority.json', expected=prior.event['sha256'])
        authority = store.read_authority(self.root, prior.task_id)
        same_object = [item for item in authority.evidence if item['sha256'] == basis['sha256']]
        self.assertEqual(len(same_object), 2)
        self.assertIs(same_object[0]['raw'], same_object[1]['raw'])
        with self.assertRaises(TypeError):
            authority.evidence[0]['raw'] = b'Caller change'

        # The delegation keeps its first reading while this exact approval
        # cites a later reading of that same growing source.
        latest = basis['raw'] + b'Explicit synthetic approval of this exact request.\n'
        (self.root / basis['path']).write_bytes(latest)
        request = workflow.draft_authorization_from(loaded, authority, 'fixture-grant', intent)
        request['reason'] = 'Explicit synthetic authority ownership regression; not user consent.'
        decision = request['request_decision']
        decision['case'] = case['id']
        decision['assessments'] = [{'criterion': 'synthetic-content', 'request_sha256': rendered['request_sha256'],
            'conclusion': 'satisfied', 'reason': 'Explicit synthetic fixture assessment.'}]
        decision['principal_approval'] = {'request_sha256': rendered['request_sha256'],
            'principal': authority.document['issuer'], 'evidence': {**ref, 'sha256': c.digest(latest)}}
        production_fixtures.assess_rendition(decision['rendition_review'])
        fixtures.write(self.root / 'scoped-request.json', request)
        reads = Counter()
        original_read = c.read

        def count(path, *args, **kwargs):
            path = Path(path)
            if path.parent == self.root / 'production/objects':
                reads[path.name] += 1
            return original_read(path, *args, **kwargs)

        with patch.object(c, 'read', side_effect=count), \
             patch.object(store, 'read_authority', wraps=store.read_authority) as acquire, \
             patch.object(store, 'authority_record', side_effect=AssertionError('reuse the acquired authority event')), \
             patch.object(store, 'stable_bytes', wraps=store.stable_bytes) as live:
            row = workflow.authorize_value(self.root, self.run_id, request, evidence_files=['scoped-request.json'])
        self.assertEqual(acquire.call_count, 1)
        self.assertEqual(reads, Counter({item['sha256']: 1 for item in authority.evidence}))
        self.assertEqual(sum(call.args[1] == basis['path'] for call in live.call_args_list), 1)
        witnesses = [item for item in row['data']['files'] if item['path'] == basis['path']]
        self.assertEqual({(item['sha256'], item['purpose']) for item in witnesses},
                         {(basis['sha256'], 'request-scope'), (c.digest(latest), 'principal-approval')})

        (self.root / basis['path']).unlink()
        with store.transaction(self.root):
            current = workflow.read_run(self.root, self.run_id)
            checked = store.read_authority(self.root, prior.task_id)
            with patch.object(store, 'authority_record', side_effect=AssertionError('reuse checked authority')), \
                 patch.object(store, 'verify_evidence', side_effect=AssertionError('reuse checked evidence')), \
                 patch.object(store, 'stable_bytes', side_effect=AssertionError('consume only saved readings')):
                permitted = workflow._permission(self.root, current.prepared, current.rows,
                    row['sha256'], **intent, authority=checked)
                owner = workflow._owner_acceptance_witnesses(self.root, current.prepared, checked,
                    {'principal': checked.document['issuer'], 'evidence': ref})
            self.assertEqual(permitted, request)
            self.assertEqual(owner[0]['raw'], basis['raw'])
            self.assertIs(store.captured_authority_inputs(checked), checked.evidence)

    def test_new_authority_acquisition_rechecks_saved_evidence_after_an_owned_read(self):
        task_id = self.case['task']['task_id']
        with runtime_snapshot.public_call():
            held = store.read_authority(self.root, task_id)
            item = held.evidence[0]
            (self.root / 'production/objects' / item['sha256']).write_bytes(b'Changed authority evidence')
            self.assertEqual(store.captured_authority_inputs(held)[0]['raw'], item['raw'])
            with store.transaction(self.root), self.assertRaises(ProductionError) as caught:
                workflow.current_authority(self.root, workflow.read_run(self.root, self.run_id).prepared)
            self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        exported = mutable(held.document)
        exported['grants'].clear()
        self.assertTrue(held.document['grants'])

    def test_impact_discovery_reacquires_registered_inputs_after_an_owned_read(self):
        with runtime_snapshot.public_call():
            held = workflow.read_run(self.root, self.run_id)
            bindings = runtime_snapshot._run_bindings(self.root)
            self.assertEqual([run for run, _ in bindings], [self.run_id])
            self.assertEqual(bindings[0][1], held.prepared['runtime_snapshot']['binding'])
            path = held.directory / 'prepared.json'
            changed = c.load(path)
            changed['runtime_snapshot']['binding']['records'].clear()
            path.write_bytes(c.encoded(changed))
            self.assertEqual(runtime_snapshot._run_bindings(self.root), ())
            self.assertEqual(bindings[0][1], held.prepared['runtime_snapshot']['binding'])

    def test_impact_discovery_checks_only_registered_input_and_discards_corruption(self):
        with patch.object(compiler, 'acquire_publication', side_effect=AssertionError('do not verify unrelated media')), \
             patch.object(store, 'read_history', side_effect=AssertionError('do not replay unrelated events')):
            with runtime_snapshot.public_call():
                bindings = runtime_snapshot._run_bindings(self.root)
                self.assertEqual([run for run, _ in bindings], [self.run_id])
                with self.assertRaises(TypeError):
                    bindings[0][1]['records'].clear()
            path = workflow.run_dir(self.root, self.run_id) / 'prepared.json'
            changed = c.load(path)
            changed['runtime_snapshot']['binding']['records'].clear()
            path.write_bytes(c.encoded(changed))
            with runtime_snapshot.public_call():
                self.assertEqual(runtime_snapshot._run_bindings(self.root), ())

    def test_committed_write_replaces_the_current_read_history(self):
        with runtime_snapshot.public_call():
            before = workflow.load_run(self.root, self.run_id)
            workflow.abandon_task(self.root, before.prepared['task']['task_id'],
                                  actor='Synthetic author', reason='Synthetic closure')
            after = workflow.load_run(self.root, self.run_id)
            self.assertEqual(before.rows, [])
            self.assertEqual([row['event'] for row in after.rows], ['abandoned'])

    def test_projection_reloads_a_run_changed_outside_the_parent_read_scope(self):
        original = studio.write_gallery
        observed = []

        def record_projection(root, *args, read=None, **kwargs):
            observed.extend(row['event'] for row in read.run(self.run_id).rows)
            return original(root, *args, read=read, **kwargs)

        with runtime_snapshot.public_call():
            read = studio.StudioRead(self.root)
            loaded = read.run(self.run_id)
            self.assertEqual(loaded.rows, [])
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(workflow.abandon_task, self.root, loaded.prepared['task']['task_id'],
                            actor='Synthetic author', reason='Concurrent synthetic closure').result(timeout=20)
            # The caller still owns its original observation until it starts
            # the publisher's independent read boundary.
            self.assertEqual(read.run(self.run_id).rows, [])
            with patch.object(studio, 'write_gallery', side_effect=record_projection):
                result = studio_activity.refresh(self.root, read=read, views={'gallery'})
            self.assertTrue(result['ok'], result)
            self.assertEqual(observed, ['abandoned'])
            self.assertEqual([row['event'] for row in read.run(self.run_id).rows], ['abandoned'])

    def test_rollback_discards_uncommitted_decoded_events(self):
        with runtime_snapshot.public_call():
            self.assertEqual(workflow.load_run(self.root, self.run_id).rows, [])
            with self.assertRaisesRegex(RuntimeError, 'abort fixture'):
                with store.transaction(self.root):
                    loaded = workflow.load_run(self.root, self.run_id)
                    workflow.append_record(loaded.directory, loaded.prepared, loaded.rows, 'abandoned',
                                           {'actor': 'Synthetic author', 'reason': 'Rolled back fixture'})
                    self.assertEqual(workflow.load_run(self.root, self.run_id).rows[-1]['event'], 'abandoned')
                    raise RuntimeError('abort fixture')
            self.assertEqual(workflow.load_run(self.root, self.run_id).rows, [])

    def test_force_and_new_public_calls_detect_changed_publication(self):
        with runtime_snapshot.public_call():
            loaded = workflow.load_run(self.root, self.run_id)
            consumer = loaded.directory / 'consumer.json'
            consumer.write_bytes(consumer.read_bytes() + b' ')
            self.assertEqual(workflow.load_run(self.root, self.run_id).consumer, loaded.consumer)
            with self.assertRaises(ProductionError):
                workflow.load_run(self.root, self.run_id, force=True)
            with self.assertRaises(ProductionError):
                workflow.load_run(self.root, self.run_id)
        with runtime_snapshot.public_call(), self.assertRaises(ProductionError):
            workflow.load_run(self.root, self.run_id)

    def test_rolled_back_registration_cannot_survive_as_a_decoded_run(self):
        loaded = workflow.load_run(self.root, self.run_id)
        with store.transaction(self.root) as connection:
            connection.execute('DELETE FROM runs WHERE run_id=?', (self.run_id,))
        with runtime_snapshot.public_call():
            with self.assertRaisesRegex(RuntimeError, 'abort registration'):
                with store.transaction(self.root):
                    store.register_run(self.root, self.run_id, loaded.prepared, loaded.directory)
                    self.assertEqual(workflow.load_run(self.root, self.run_id).rows, [])
                    raise RuntimeError('abort registration')
            with self.assertRaises(ProductionError) as caught:
                workflow.load_run(self.root, self.run_id)
            self.assertEqual(caught.exception.diagnostic.code, 'RUN_NOT_REGISTERED')


class OwnedJsonTests(unittest.TestCase):
    def test_freeze_shares_aliases_across_builtin_and_fallback_containers(self):
        from collections import UserDict

        class Items(list):
            pass

        child = {'values': [None, True, 1, 1.0, 'text', b'bytes']}
        owned = freeze({'value': 2})
        owned_list = freeze([owned])
        held = freeze({'array': [child, child], 'mapping': UserDict({'child': child}),
                       'subclass': Items([child]), 'tuple': (child,), 'set': {'token'},
                       'owned': owned, 'owned_list': owned_list})
        for alias in (held['array'][1], held['mapping']['child'],
                      held['subclass'][0], held['tuple'][0]):
            self.assertIs(alias, held['array'][0])
        self.assertIs(held['owned'], owned)
        self.assertIs(held['owned_list'], owned_list)
        self.assertEqual(held['set'], frozenset({'token'}))
        child['values'].append('source changed')
        self.assertEqual(held['array'][0]['values'], [None, True, 1, 1.0, 'text', b'bytes'])
        with self.assertRaises(TypeError):
            held['mapping']['child']['values'].append('owner changed')

    def test_operation_comparison_preserves_json_types_with_owned_containers(self):
        value = {'array': [{'count': 1, 'enabled': True, 'weight': 1.0}]}
        compare_exact(value, freeze(value))
        compare_exact(freeze(value), value)
        for wrong in (True, 1.0, '1'):
            with self.assertRaises(ProductionError) as caught:
                compare_exact(freeze({'count': 1}), {'count': wrong})
            self.assertEqual(caught.exception.diagnostic.pointer, '$.count')

    def test_frozen_json_preserves_serialization_and_exports_independent_edits(self):
        source = {'nested': [{'value': 1}], 'empty': {}}
        held = freeze(source)
        self.assertEqual(c.encoded(held), c.encoded(source))
        self.assertIs(freeze(held), held)
        source['nested'][0]['value'] = 2
        self.assertEqual(held['nested'][0]['value'], 1)
        for exported in (mutable(held), copy.deepcopy(held)):
            exported['nested'][0]['value'] = 3
            exported['nested'].append({})
        self.assertEqual(held['nested'], [{'value': 1}])
        with self.assertRaises(TypeError):
            held['nested'][0]['value'] = 4
        with self.assertRaises(TypeError):
            held['nested'] += [{}]
        held.__init__({'replacement': True})
        held['nested'].__init__([{'replacement': True}])
        self.assertEqual(held['nested'], [{'value': 1}])
        self.assertNotIn('replacement', held)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
