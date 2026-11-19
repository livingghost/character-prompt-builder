"""Read ownership, mutation invalidation and forced verification of real runs."""
from __future__ import annotations
import read_context

from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
import contextvars
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as fixtures
import production_compiler as compiler
import production_fixtures
import production_store as store
import production_operations as workflow
import production_execution as execution
import execution_lifecycle as lifecycle
import runtime_snapshot
import studio_workspace as studio
import studio_activity
from production_diagnostics import ProductionError, compare_exact
from production_read_model import DecisionRead, EvidenceReader, RunReader, RunSnapshot, RunView
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
        with read_context.public_call(), \
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
        with read_context.public_call():
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

    def test_preparation_hands_its_checked_documents_to_the_first_run_read(self):
        with read_context.public_call():
            # The predecessor is an independent published input, already owned
            # when the operation prepares its successor.
            workflow.read_run(self.root, self.run_id)
            with patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as acquire:
                result = workflow.prepare(self.root, 'task.json')
                held = workflow.read_run(self.root, result['run'])
                self.assertEqual(acquire.call_count, 1)
                self.assertEqual(held.directory, workflow.run_dir(self.root, result['run']))
                self.assertEqual(held.prepared['input_sha256'], result['input_sha256'])
                with patch.object(compiler, 'acquire_publication',
                                  side_effect=AssertionError('keep the producer-owned publication')):
                    again = workflow.read_run(self.root, result['run'])
                self.assertIs(again, held)
        # A later operation still checks saved bytes rather than accepting the
        # earlier producer's successful observation.
        path = held.directory / 'consumer.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with read_context.public_call(), self.assertRaises(ProductionError):
            workflow.read_run(self.root, result['run'])

    def test_published_input_handoff_does_not_survive_registration_rollback(self):
        result = None
        with read_context.public_call():
            with self.assertRaisesRegex(RuntimeError, 'discard registration'):
                with store.transaction(self.root):
                    result = workflow.prepare(self.root, 'task.json')
                    self.assertEqual(workflow.read_run(self.root, result['run']).prepared['run'], result['run'])
                    raise RuntimeError('discard registration')
            with self.assertRaises(ValueError):
                workflow.read_run(self.root, result['run'])

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

        with read_context.public_call():
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

        with patch.object(c, 'decode', wraps=c.decode) as decode, read_context.public_call():
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

    def test_transactions_keep_owned_inputs_and_force_reacquires_them(self):
        directory = workflow.run_dir(self.root, self.run_id)
        raw = {name: (directory / name).read_bytes() for name in
               ('manifest.json', 'prepared.json', 'consumer.json', 'execution-plan.json')}
        with read_context.public_call(), \
             patch.object(c, 'decode', wraps=c.decode) as decode, \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as acquire:
            first = workflow.read_run(self.root, self.run_id)
            plan = first.artifacts['execution-plan.json']
            with store.transaction(self.root):
                transaction = workflow.read_run(self.root, self.run_id)
                self.assertIs(transaction.prepared, first.prepared)
                self.assertIs(transaction.artifacts['execution-plan.json'], plan)
                self.assertIs(transaction.evidence, first.evidence)
                self.assertIs(transaction.lifecycle, first.lifecycle)
                forced = workflow.read_run(self.root, self.run_id, force=True)
                self.assertIsNot(forced.prepared, transaction.prepared)
                self.assertIsNot(forced.artifacts['execution-plan.json'], transaction.artifacts['execution-plan.json'])
                self.assertEqual(forced.artifacts['execution-plan.json'], plan)
                self.assertIsNot(forced.evidence, transaction.evidence)
            after = workflow.read_run(self.root, self.run_id)
            self.assertIs(after.prepared, forced.prepared)
            self.assertIs(after.artifacts['execution-plan.json'], forced.artifacts['execution-plan.json'])
            self.assertEqual(after.artifacts['execution-plan.json'], plan)
            self.assertIs(after.evidence, forced.evidence)
            self.assertEqual(acquire.call_count, 2)
            interpreted = Counter(name for call in decode.call_args_list for name, data in raw.items()
                                  if call.args[0] == data)
            self.assertEqual(interpreted, {name: 2 for name in raw})

    def test_empty_transaction_keeps_owned_inputs_until_forced_acquisition(self):
        with read_context.public_call():
            held = workflow.read_run(self.root, self.run_id)
            path = held.directory / 'request-contract.json'
            with store.transaction(self.root):
                path.write_bytes(path.read_bytes() + b' ')
            self.assertIs(workflow.read_run(self.root, self.run_id).artifacts, held.artifacts)
            with self.assertRaises(ProductionError) as caught:
                workflow.read_run(self.root, self.run_id, force=True)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

    def test_failed_nested_fresh_read_cannot_restore_the_parent_success(self):
        with read_context.public_call():
            observed = workflow.read_run(self.root, self.run_id)
            path = observed.directory / 'consumer.json'
            with read_context.public_call(fresh=True):
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
        with read_context.public_call(), store.transaction(self.root):
            observed = workflow.read_run(self.root, self.run_id)
            path = observed.directory / 'consumer.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with read_context.public_call(fresh=True):
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

    def test_execution_reads_saved_sources_and_navigation_observes_each_current_edit(self):
        from live_source_read import LiveSourceRead
        with read_context.public_call(), store.transaction(self.root):
            first = workflow.read_current(self.root, self.run_id)
            source = self.root / 'prompt.txt'
            before = source.read_bytes()
            dependency = next(item for item in first.view.prepared['dependencies']
                              if item['space'] == 'studio' and item['path'] == 'prompt.txt')
            self.assertEqual(first.view.evidence.read(dependency['sha256']), before)
            source.write_bytes(before + b' A changed source.')
            for remove in (False, True):
                with self.subTest(removed=remove):
                    if remove:
                        source.unlink()
                    with patch.object(LiveSourceRead, '__init__', side_effect=AssertionError('Execution reads saved input')):
                        current = workflow.read_current(self.root, self.run_id, force=True)
                        self.assertEqual(current.view.evidence.read(dependency['sha256']), before)
                        workflow.assert_current(self.root, self.run_id)
                    failures, notices = workflow.freshness(self.root, self.run_id)
                    self.assertEqual(failures, [])
                    [changed] = [item for item in notices if item['file'] == 'prompt.txt']
                    self.assertEqual((changed['code'], changed['severity']), ('SOURCE_CHANGED', 'warning'))
                    self.assertEqual(changed['actual'], None if remove else c.sha256_file(source))
            self.assertEqual(first.view.evidence.read(dependency['sha256']), before)

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

        for boundary in ('force', 'fresh'):
            with self.subTest(boundary=boundary), read_context.public_call():
                before = workflow.read_run(self.root, self.run_id)
                self.assertEqual(before.evidence.read(evidence['sha256']), raw)
                path.write_bytes(raw + b' changed')
                try:
                    if boundary == 'force':
                        with self.assertRaises(ProductionError) as caught:
                            workflow.read_run(self.root, self.run_id, force=True)
                    else:
                        with read_context.public_call(fresh=True), self.assertRaises(ProductionError) as caught:
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
        with read_context.public_call():
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

    def test_delegation_template_acquires_sources_once_without_rewriting_author_choices(self):
        import production_request
        import production_workspace
        loaded = workflow.read_run(self.root, self.run_id)
        prior = store.read_authority(self.root, self.case['task']['task_id'])
        before = store.event_rows(self.root, 'authority:' + prior.task_id)
        template = production_request.delegation_template(loaded.prepared,
            loaded.artifacts['execution-plan.json']['operations'], prior.document)
        self.assertEqual(template['state'], 'unapproved')
        self.assertEqual(template['scope']['plan'], {'path': None, 'locator': None})
        self.assertTrue(Path(template['schema']).is_file())
        self.assertEqual(store.event_rows(self.root, 'authority:' + prior.task_id), before)
        declaration = mutable(prior.document)
        source = declaration['evidence']
        declaration['grants'][0]['request_scope'] = template['scope']
        declaration['grants'][0]['request_scope']['plan'] = dict(source)
        path = self.root / 'delegation.json'
        fixtures.write(path, declaration)
        original = path.read_bytes()
        reads = Counter()
        read = store.stable_read

        def counted(selected, *args, **kwargs):
            reads[str(selected)] += 1
            return read(selected, *args, **kwargs)

        with patch.object(store, 'stable_read', side_effect=counted):
            imported = store.import_authority(self.root, 'delegation.json', expected=prior.event['sha256'])
        self.assertEqual(path.read_bytes(), original)
        pinned = imported['data']['authority']['grants'][0]['request_scope']['plan']
        self.assertEqual(pinned['sha256'], c.sha256_file(self.root / source['path']))
        self.assertEqual(reads[str(self.root / source['path'])], 1)
        snapshot = store.authority_snapshot(self.root, prior.task_id, store.read_authority(self.root, prior.task_id))
        self.assertEqual(snapshot['event_sha256'], imported['sha256'])
        self.assertEqual(snapshot['source_path'], 'delegation.json')
        self.assertEqual(snapshot['update_action']['argv'][-2:], ['--expected-event', imported['sha256']])
        (self.root / source['path']).write_bytes((self.root / source['path']).read_bytes() + b'Later unrelated instruction.\n')
        view = production_workspace.workspace(self.root, self.run_id, phase='decision')
        self.assertEqual(view['authority']['document']['grants'][0]['request_scope']['plan'], pinned)

    def test_declared_scope_digest_is_checked_before_authority_event_is_appended(self):
        import production_request
        loaded = workflow.read_run(self.root, self.run_id)
        prior = store.read_authority(self.root, self.case['task']['task_id'])
        template = production_request.delegation_template(loaded.prepared,
            loaded.artifacts['execution-plan.json']['operations'], prior.document)
        declaration = mutable(prior.document)
        template['scope']['plan'] = {**declaration['evidence'], 'sha256': '0' * 64}
        declaration['grants'][0]['request_scope'] = template['scope']
        fixtures.write(self.root / 'wrong-source.json', declaration)
        before = store.event_rows(self.root, 'authority:' + prior.task_id)
        with self.assertRaises(ProductionError) as caught:
            store.import_authority(self.root, 'wrong-source.json', expected=prior.event['sha256'])
        self.assertEqual(caught.exception.diagnostic.code, 'SOURCE_CHANGED')
        self.assertEqual(store.event_rows(self.root, 'authority:' + prior.task_id), before)

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

    def test_owned_authority_is_reused_until_a_new_call_checks_saved_evidence(self):
        task_id = self.case['task']['task_id']
        with read_context.public_call():
            loaded = workflow.read_run(self.root, self.run_id)
            held = store.read_authority(self.root, task_id)
            item = held.evidence[0]
            (self.root / 'production/objects' / item['sha256']).write_bytes(b'Changed authority evidence')
            self.assertEqual(store.captured_authority_inputs(held)[0]['raw'], item['raw'])
            with store.transaction(self.root):
                self.assertIs(workflow.current_authority(self.root, loaded.prepared), held)
            self.assertIs(store.read_authority(self.root, task_id), held)
        with read_context.public_call(), self.assertRaises(ProductionError) as caught:
            store.read_authority(self.root, task_id)
        self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        with read_context.public_call(fresh=True), self.assertRaises(ProductionError) as caught:
            store.read_authority(self.root, task_id)
        self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        exported = mutable(held.document)
        exported['grants'].clear()
        self.assertTrue(held.document['grants'])

    def test_impact_discovery_reacquires_registered_inputs_after_an_owned_read(self):
        with read_context.public_call():
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
            with read_context.public_call():
                bindings = runtime_snapshot._run_bindings(self.root)
                self.assertEqual([run for run, _ in bindings], [self.run_id])
                with self.assertRaises(TypeError):
                    bindings[0][1]['records'].clear()
            path = workflow.run_dir(self.root, self.run_id) / 'prepared.json'
            changed = c.load(path)
            changed['runtime_snapshot']['binding']['records'].clear()
            path.write_bytes(c.encoded(changed))
            with read_context.public_call():
                self.assertEqual(runtime_snapshot._run_bindings(self.root), ())

    def test_committed_write_replaces_the_current_read_history(self):
        with read_context.public_call():
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

        with read_context.public_call():
            read = studio.StudioRead(self.root)
            loaded = read.run(self.run_id)
            self.assertEqual(loaded.rows, [])
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(workflow.abandon_task, self.root, loaded.prepared['task']['task_id'],
                            actor='Synthetic author', reason='Concurrent synthetic closure').result(timeout=20)
            # The caller retains its immutable observation until publication
            # reconciles the other connection's committed changes.
            self.assertEqual(read.run(self.run_id).rows, [])
            with patch.object(studio, 'write_gallery', side_effect=record_projection):
                result = studio_activity.refresh(self.root, read=read, views={'gallery'})
            self.assertTrue(result['ok'], result)
            self.assertEqual(observed, ['abandoned'])
            self.assertEqual([row['event'] for row in read.run(self.run_id).rows], ['abandoned'])

    def test_rollback_restores_owned_state_without_replaying_history(self):
        with read_context.public_call(), \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication, \
             patch.object(store, 'read_history', wraps=store.read_history) as history, \
             patch.object(lifecycle, 'completion_tail', wraps=lifecycle.completion_tail) as replay:
            before = workflow.read_run(self.root, self.run_id)
            self.assertEqual(before.rows, [])
            with self.assertRaisesRegex(RuntimeError, 'abort fixture'):
                with store.transaction(self.root):
                    loaded = workflow.read_run(self.root, self.run_id)
                    workflow.append_record(loaded, 'abandoned',
                                           {'actor': 'Synthetic author', 'reason': 'Rolled back fixture'})
                    self.assertEqual(workflow.load_run(self.root, self.run_id).rows[-1]['event'], 'abandoned')
                    raise RuntimeError('abort fixture')
            after = workflow.read_run(self.root, self.run_id)
            self.assertIs(after.prepared, before.prepared)
            self.assertIs(after.lifecycle, before.lifecycle)
            self.assertEqual(after.rows, [])
            self.assertEqual((publication.call_count, history.call_count, replay.call_count), (1, 1, 1))

    def test_force_and_new_public_calls_detect_changed_publication(self):
        with read_context.public_call():
            loaded = workflow.load_run(self.root, self.run_id)
            consumer = loaded.directory / 'consumer.json'
            consumer.write_bytes(consumer.read_bytes() + b' ')
            self.assertEqual(workflow.load_run(self.root, self.run_id).consumer, loaded.consumer)
            with self.assertRaises(ProductionError):
                workflow.load_run(self.root, self.run_id, force=True)
            with self.assertRaises(ProductionError):
                workflow.load_run(self.root, self.run_id)
        with read_context.public_call(), self.assertRaises(ProductionError):
            workflow.load_run(self.root, self.run_id)

    def test_rolled_back_registration_cannot_survive_as_a_decoded_run(self):
        loaded = workflow.load_run(self.root, self.run_id)
        with store.transaction(self.root) as connection:
            connection.execute('DELETE FROM runs WHERE run_id=?', (self.run_id,))
        with read_context.public_call():
            with self.assertRaisesRegex(RuntimeError, 'abort registration'):
                with store.transaction(self.root):
                    store.register_run(self.root, self.run_id, loaded.prepared, loaded.directory)
                    self.assertEqual(workflow.load_run(self.root, self.run_id).rows, [])
                    raise RuntimeError('abort registration')
            with self.assertRaises(ProductionError) as caught:
                workflow.load_run(self.root, self.run_id)
            self.assertEqual(caught.exception.diagnostic.code, 'RUN_NOT_REGISTERED')


class DecisionReadBoundaryTests(unittest.TestCase):
    """Display evidence has its own acquisition; it never authorizes an effect."""

    @staticmethod
    def build_template(base):
        case = fixtures.create(base / 'studio', base / 'runtime')
        root = case['root']
        run = workflow.prepare(root, 'task.json')['run']
        decisions = fixtures.fill_decisions(root, run, 'synthetic-decisions.json')
        result = execution.execute(root, run, decisions_file=decisions)
        if not result['execution_completed']:
            raise AssertionError(result)
        return case, {'run': run, 'candidate': result['runs'][0]['candidates'][0]}

    @classmethod
    def setUpClass(cls):
        cls.template = fixtures.CaseTemplate.for_class(cls, cls.build_template)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        case, metadata = fixtures.CaseTemplate.for_test(
            self, Path(temporary.name), self.build_template, self.template)
        self.root = case['root']
        self.run_id = metadata['run']
        self.candidate = metadata['candidate']
        self.directory = workflow.run_dir(self.root, self.run_id)

    def test_independent_gallery_acquires_only_decision_records_and_event_evidence(self):
        opened = Counter()
        original = Path.open

        def observe(path, *args, **kwargs):
            if path.is_relative_to(self.directory):
                opened[path.relative_to(self.directory).as_posix()] += 1
            return original(path, *args, **kwargs)

        with patch.object(Path, 'open', observe), \
             patch.object(workflow, 'read_run', side_effect=AssertionError('candidate display owns its decision read')):
            rows = studio.read_iterations(studio.character_home(self.root, 'robot'))
        self.assertEqual(rows[0]['evaluation'], 'unreviewed')
        self.assertNotIn('production_diagnostic', rows[0])
        self.assertEqual({name: count for name, count in opened.items() if not name.startswith('objects/')},
                         {'manifest.json': 1, 'prepared.json': 1, 'consumer.json': 1})
        history = store.event_rows(self.root, self.run_id)
        evidence = {item['sha256'] for row in history
                    for item in row['data'].get('files', []) + row['data'].get('evidence', [])}
        self.assertTrue(evidence)
        self.assertTrue(all(opened['objects/' + key] == 1 for key in evidence))

    def test_decision_records_do_not_treat_manifest_membership_as_verified_bytes(self):
        registered = store.registered_run(self.root, self.run_id)
        records = compiler.acquire_decision_records(self.directory, expected=registered['manifest_sha256'])
        self.assertEqual(records.verified_objects, {})
        source = next(item for item in records.prepared['dependencies']
                      if item['space'] == 'studio' and item['path'] == 'prompt.txt')
        path = self.directory / 'objects' / source['sha256']
        before = path.stat()
        raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(ProductionError) as caught:
            records.evidence.read(source['sha256'])
        self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
        self.assertEqual(records.verified_objects, {})

    def test_display_does_not_promote_to_a_publication_audit_or_writer_observation(self):
        disposition = workflow.draft_disposition(self.root, self.run_id, self.candidate)
        disposition.update(actor='Synthetic author', reason='Private fixture disposition.')
        fixtures.write(self.root / 'disposition.json', disposition)
        path = self.directory / 'package.json'
        raw = path.read_bytes()
        path.write_bytes(raw + b' ')
        with read_context.public_call():
            display = workflow.read_decisions(self.root, self.run_id)
            self.assertIsInstance(display, DecisionRead)
            self.assertEqual(display.candidate(self.candidate)['evaluation'], 'unreviewed')
            for field in ('rows', 'prepared', 'consumer', 'artifacts', 'mutation', 'append', 'integrity'):
                self.assertFalse(hasattr(display, field), field)
            with self.assertRaises(TypeError):
                display.candidate(self.candidate)['evaluation'] = 'conforming'
            with self.assertRaises(ProductionError) as caught:
                workflow.read_run(self.root, self.run_id)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')
            self.assertFalse(execution.status(self.root, self.run_id)['ok'])
            before = store.event_rows(self.root, self.run_id)
            with self.assertRaises(ProductionError) as writing:
                workflow.disposition(self.root, self.run_id, 'disposition.json')
            self.assertEqual(writing.exception.diagnostic.code, 'ARTIFACT_CORRUPT')
            self.assertEqual(store.event_rows(self.root, self.run_id), before)

    def test_new_decision_boundary_checks_same_size_same_mtime_event_bytes(self):
        candidate = workflow.find(store.event_rows(self.root, self.run_id), 'candidate', self.candidate)
        path = self.directory / 'objects' / candidate['data']['files'][0]['sha256']
        raw, before = path.read_bytes(), path.stat()
        with read_context.public_call():
            observed = workflow.read_decisions(self.root, self.run_id)
            path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertIs(workflow.read_decisions(self.root, self.run_id), observed)
            with store.transaction(self.root):
                self.assertIs(workflow.read_decisions(self.root, self.run_id), observed)
            self.assertIs(workflow.read_decisions(self.root, self.run_id), observed)
            self.assertEqual(observed.candidate(self.candidate)['evaluation'], 'unreviewed')
        with read_context.public_call(), self.assertRaises(ProductionError):
            workflow.read_decisions(self.root, self.run_id)

    def test_failed_fresh_and_forced_reads_cannot_restore_a_decision_observation(self):
        path = self.directory / 'consumer.json'
        original = path.read_bytes()
        for boundary in ('fresh', 'force'):
            with self.subTest(boundary=boundary), read_context.public_call():
                observed = workflow.read_decisions(self.root, self.run_id)
                path.write_bytes(original + b' ')
                try:
                    if boundary == 'fresh':
                        with read_context.public_call(fresh=True), self.assertRaises(ProductionError):
                            workflow.read_decisions(self.root, self.run_id)
                    else:
                        with self.assertRaises(ProductionError):
                            workflow.read_run(self.root, self.run_id, force=True)
                    with self.assertRaises(ProductionError):
                        workflow.read_decisions(self.root, self.run_id)
                    self.assertEqual(observed.candidate(self.candidate)['disposition'], 'pending')
                finally:
                    path.write_bytes(original)

    def test_rollback_discards_decision_successor_and_keeps_old_observation_immutable(self):
        with read_context.public_call(), store.transaction(self.root):
            observed = workflow.read_decisions(self.root, self.run_id)
            with self.assertRaisesRegex(RuntimeError, 'abort fixture'):
                with store.transaction(self.root):
                    full = workflow.read_run(self.root, self.run_id)
                    workflow.append_record(full, 'disposition', {'disposition': {
                        'input_sha256': full.prepared['input_sha256'], 'candidate': self.candidate,
                        'disposition': 'not_selected', 'actor': 'Synthetic author',
                        'reason': 'Rolled back fixture.', 'review': None}, 'files': [], 'previous_decision': None})
                    self.assertEqual(workflow.read_decisions(self.root, self.run_id).candidate(
                        self.candidate)['disposition'], 'not_selected')
                    raise RuntimeError('abort fixture')
            after = workflow.read_decisions(self.root, self.run_id)
            self.assertEqual(after.candidate(self.candidate)['disposition'], 'pending')
            self.assertIs(after, observed)
            self.assertEqual(observed.candidate(self.candidate)['disposition'], 'pending')

    def test_own_decision_commit_and_display_share_the_updated_run(self):
        with read_context.public_call(), \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication, \
             patch.object(store, '_verified_history', wraps=store._verified_history) as history, \
             patch.object(lifecycle, 'completion_tail', wraps=lifecycle.completion_tail) as replay:
            before = workflow.read_run(self.root, self.run_id)
            previous_display = workflow.read_decisions(self.root, self.run_id)
            data = workflow.draft_disposition(self.root, self.run_id, self.candidate)
            data.update(actor='Synthetic author', reason='Retain an explicit nonselection.')
            receipt = workflow.disposition_value(self.root, self.run_id, data)
            after = workflow.read_run(self.root, self.run_id)
            display = workflow.read_decisions(self.root, self.run_id)
            report = execution.status(self.root, self.run_id)
            self.assertEqual(receipt['event'], 'disposition')
            self.assertIs(after.prepared, before.prepared)
            self.assertIs(after.evidence, before.evidence)
            self.assertEqual(previous_display.candidate(self.candidate)['disposition'], 'pending')
            self.assertEqual(display.candidate(self.candidate)['disposition'], 'not_selected')
            self.assertEqual(report['runs'][0]['candidate_states'][0]['disposition'], 'not_selected')
            run_acquisitions = sum(call.args[0] == self.run_id for call in history.call_args_list)
            self.assertEqual((publication.call_count, run_acquisitions, replay.call_count), (1, 1, 1))
        gallery = c.load(self.root / 'gallery.json')
        entry = next(item for item in gallery['entries']
                     if item.get('production', {}).get('candidate') == self.candidate)
        self.assertEqual(entry['disposition'], 'not_selected')


class WriterHistoryTests(unittest.TestCase):
    """Exercise the real SQLite writer and run owner without a Studio fixture."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run_id = 'synthetic-writer'
        self.directory = self.root / 'production' / 'runs' / self.run_id
        self.directory.mkdir(parents=True)
        self.prepared = {'run': self.run_id, 'input_sha256': 'a' * 64, 'envelope_sha256': 'b' * 64,
            'task': {'task_id': 'synthetic-task', 'production_id': 'synthetic-production', 'execution': 'external'}}
        files = []
        for name, value in [('prepared.json', self.prepared), ('consumer.json', {'synthetic': True})]:
            raw = c.encoded(value)
            (self.directory / name).write_bytes(raw)
            files.append({'path': name, 'sha256': c.digest(raw), 'size': len(raw)})
        (self.directory / 'manifest.json').write_bytes(c.encoded({'complete': True, 'files': files}))
        store.register_run(self.root, self.run_id, self.prepared, self.directory)
        # This minimal publication isolates event ownership from task authoring.
        # Publication bytes, event integrity and lifecycle rules are real reads.
        self.reader = RunReader(self.root, lambda *args: None, workflow._validate_run_history,
                                workflow._validate_run_append)

    def witness(self, raw=b'Synthetic received output.'):
        key = c.digest(raw)
        path = self.directory / 'objects' / key
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        return {'path': 'received-output', 'sha256': key, 'size': len(raw)}

    def record(self, event, data):
        loaded = self.reader.read(self.run_id)
        return workflow.append_record(loaded, event, data)

    def test_successive_writes_reuse_one_acquisition_and_preserve_prior_views(self):
        with store.transaction(self.root), \
             patch.object(store, 'read_history', wraps=store.read_history) as acquired, \
             patch.object(lifecycle, 'completion_tail', wraps=lifecycle.completion_tail) as replayed:
            first = self.reader.read(self.run_id)
            hand = workflow.append_record(first, 'handoff', {'recipient': 'Synthetic recipient'})
            second = self.reader.read(self.run_id)
            data = {'handoff': hand['sha256'], 'files': [self.witness()], 'note': ['Actual received output']}
            candidate = workflow.append_record(second, 'candidate', data)
            data['note'].append('Caller edit after append')
            current = self.reader.read(self.run_id)
            self.assertEqual((acquired.call_count, replayed.call_count), (1, 1))
            self.assertEqual(first.rows, [])
            self.assertEqual([row['event'] for row in second.rows], ['handoff'])
            self.assertIs(second.rows[0], current.rows[0])
            self.assertIs(current.rows.lifecycle, current.lifecycle)
            self.assertEqual(current.rows[-1]['data']['note'], ['Actual received output'])
            candidate['data']['note'].append('Returned export edit')
            self.assertEqual(current.rows[-1]['data']['note'], ['Actual received output'])
            repeated = workflow.append_record(current, 'candidate', current.rows[-1]['data'])
            self.assertEqual(repeated['sha256'], current.rows[-1]['sha256'])
            self.assertIs(self.reader.read(self.run_id), current)
            with self.assertRaises(ProductionError):
                workflow.append_record(second, 'abandoned', {'reason': 'Superseded observation'})
            fresh = store.read_history(self.root, self.run_id)
            self.assertEqual(fresh.rows, current.rows)
            state = workflow._validate_run_history(self.run_id, current.prepared, fresh, current.evidence, {})
            self.assertEqual(state.seal()._events, current.lifecycle._events)

    def test_commits_keep_owned_history_and_rebind_only_the_writer(self):
        witness = self.witness()
        with read_context.public_call(), \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication, \
             patch.object(store, 'read_history', wraps=store.read_history) as history, \
             patch.object(lifecycle, 'completion_tail', wraps=lifecycle.completion_tail) as replay:
            first = self.reader.read(self.run_id)
            with store.transaction(self.root):
                writer = self.reader.read(self.run_id)
                self.assertIs(writer.prepared, first.prepared)
                self.assertIs(writer.lifecycle, first.lifecycle)
                handoff = workflow.append_record(writer, 'handoff', {'recipient': 'Synthetic recipient'})
                committed_writer = self.reader.read(self.run_id)
            committed = self.reader.read(self.run_id)
            self.assertIs(committed.lifecycle, committed_writer.lifecycle)
            self.assertIs(committed.evidence, first.evidence)
            with self.assertRaises((ProductionError, ValueError)):
                workflow.append_record(committed_writer, 'candidate', {'files': [witness]})
            with store.transaction(self.root):
                writer = self.reader.read(self.run_id)
                self.assertIs(writer.lifecycle, committed.lifecycle)
                with self.assertRaises((ProductionError, ValueError)):
                    workflow.append_record(committed_writer, 'candidate', {'files': [witness]})
                workflow.append_record(writer, 'candidate', {'handoff': handoff['sha256'], 'files': [witness]})
            after = self.reader.read(self.run_id)
            self.assertEqual([row['event'] for row in after.rows], ['handoff', 'candidate'])
            self.assertEqual(first.rows, [])
            self.assertEqual([row['event'] for row in committed.rows], ['handoff'])
            self.assertIs(after.prepared, first.prepared)
            self.assertEqual((publication.call_count, history.call_count, replay.call_count), (1, 1, 1))
        self.assertEqual([row['event'] for row in store.event_rows(self.root, self.run_id)], ['handoff', 'candidate'])

    def test_new_transaction_observes_another_connections_committed_event(self):
        witness = self.witness()
        with read_context.public_call():
            before = self.reader.read(self.run_id)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(store.append, self.root, self.run_id, self.prepared['input_sha256'],
                            'handoff', {'recipient': 'Another operation'}).result(timeout=20)
            self.assertEqual(before.rows, [])
            with store.transaction(self.root):
                current = self.reader.read(self.run_id)
                self.assertEqual([row['event'] for row in current.rows], ['handoff'])
                workflow.append_record(current, 'candidate', {'files': [witness]})
            after = self.reader.read(self.run_id)
            self.assertEqual([row['event'] for row in after.rows], ['handoff', 'candidate'])
            self.assertEqual(after.rows[-1]['previous'], after.rows[0]['sha256'])
            self.assertEqual(before.rows, [])

    def test_external_history_edit_is_detected_even_when_count_and_tail_stay_equal(self):
        with store.transaction(self.root):
            self.record('handoff', {'recipient': 'Original recipient'})
            self.record('candidate', {'files': [self.witness()]})
        with read_context.public_call():
            before = self.reader.read(self.run_id)
            changed = mutable(before.rows[0])
            changed['data']['recipient'] = 'Changed recipient'
            connection = sqlite3.connect(store.database(self.root))
            try:
                connection.execute('UPDATE events SET body=? WHERE scope=? AND sequence=1',
                                   (c.encoded(changed), self.run_id))
                connection.commit()
                count, tail = connection.execute(
                    'SELECT COUNT(*), MAX(sequence) FROM events WHERE scope=?', (self.run_id,)).fetchone()
                self.assertEqual((count, tail), (len(before.rows), before.rows[-1]['sequence']))
                digest = connection.execute('SELECT sha256 FROM events WHERE scope=? AND sequence=?',
                                            (self.run_id, tail)).fetchone()[0]
                self.assertEqual(digest, before.rows[-1]['sha256'])
            finally:
                connection.close()
            with store.transaction(self.root), self.assertRaises(ProductionError) as caught:
                self.reader.read(self.run_id)
            self.assertEqual(caught.exception.diagnostic.code, 'EVENT_CHAIN_CORRUPT')
            self.assertEqual(before.rows[0]['data']['recipient'], 'Original recipient')

    def test_execution_successors_keep_the_previous_nested_indexes_immutable(self):
        with store.transaction(self.root):
            request = {'operation': 'submit', 'targets': ['delivery'], 'payload': {'count': 1},
                       'actor': 'Synthetic author', 'grant': 'synthetic-grant', 'outputs': 1}
            authorization = self.record('authorization', {'request': request})
            created = {'execution_id': 'synthetic-execution', 'authorization_sha256': authorization['sha256'],
                       'grant': request['grant'], 'actor': request['actor'], 'requested_outputs': 1,
                       'task_id': self.prepared['task']['task_id'], 'request_sha256': c.content_id(request['payload'])}
            self.record('execution-created', created)
            claimed = self.reader.read(self.run_id)
            self.record('execution-start', {'execution_id': created['execution_id'], 'effect': 'external-io', 'claim': 'c' * 64})
            started = self.reader.read(self.run_id)
            step = {'execution_id': created['execution_id'], 'claim': 'c' * 64, 'step': 'send', 'operation': 'send',
                    'request_sha256': created['request_sha256']}
            self.record('external-step', step)
            sent = self.reader.read(self.run_id)
            evidence = [self.witness()]
            self.record('external-effect-result', {'execution_id': created['execution_id'], 'claim': 'c' * 64,
                                                  'step': 'send', 'usage': None, 'evidence': evidence})
            received = self.reader.read(self.run_id)
            self.record('execution-result', {'execution_id': created['execution_id'], 'outputs': 1,
                                             'cost': None, 'final': True, 'evidence': evidence})
            complete = self.reader.read(self.run_id)
            identifier = created['execution_id']
            self.assertEqual(claimed.lifecycle.executions[identifier]['status'], 'claimed')
            self.assertEqual(started.lifecycle.executions[identifier]['steps'], [])
            self.assertEqual(started.lifecycle._steps[identifier], {})
            self.assertEqual(sent.lifecycle.executions[identifier]['effect_results'], {})
            self.assertEqual(received.lifecycle.executions[identifier]['status'], 'started')
            self.assertEqual(complete.lifecycle.executions[identifier]['status'], 'complete')
            fresh = self.reader.read(self.run_id, force=True)
            self.assertEqual(fresh.lifecycle.executions, complete.lifecycle.executions)
            self.assertEqual(fresh.lifecycle._steps, complete.lifecycle._steps)

    def test_invalid_new_evidence_and_transition_leave_the_writer_unchanged(self):
        with store.transaction(self.root):
            loaded = self.reader.read(self.run_id)
            witness = self.witness()
            with self.assertRaises(ProductionError) as caught:
                workflow.append_record(loaded, 'candidate', {'files': [{**witness, 'size': witness['size'] + 1}]})
            self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')
            self.assertIs(self.reader.read(self.run_id), loaded)
            self.assertEqual(store.event_rows(self.root, self.run_id), [])
            with self.assertRaises(ProductionError):
                workflow.append_record(loaded, 'execution-start', {'execution_id': 'missing-owner'})
            self.assertIs(self.reader.read(self.run_id), loaded)
            self.assertEqual(store.event_rows(self.root, self.run_id), [])
            workflow.append_record(loaded, 'candidate', {'files': [witness]})
            self.assertEqual(len(self.reader.read(self.run_id).rows), 1)

    def test_rollback_restores_predecessor_and_transaction_exit_ends_its_writer(self):
        with store.transaction(self.root), \
             patch.object(compiler, 'acquire_publication', wraps=compiler.acquire_publication) as publication, \
             patch.object(store, 'read_history', wraps=store.read_history) as history, \
             patch.object(lifecycle, 'completion_tail', wraps=lifecycle.completion_tail) as replay:
            self.record('handoff', {'recipient': 'Synthetic recipient'})
            before = self.reader.read(self.run_id)
            with self.assertRaisesRegex(RuntimeError, 'stop nested writer'):
                with store.transaction(self.root):
                    workflow.append_record(before, 'abandoned', {'reason': 'Rolled back'})
                    uncommitted = self.reader.read(self.run_id)
                    raise RuntimeError('stop nested writer')
            with self.assertRaises((ProductionError, ValueError)):
                workflow.append_record(uncommitted, 'candidate', {'files': []})
            current = self.reader.read(self.run_id)
            self.assertIs(current.lifecycle, before.lifecycle)
            self.assertIs(current.prepared, before.prepared)
            self.assertEqual([row['event'] for row in current.rows], ['handoff'])
            workflow.append_record(current, 'candidate', {'files': []})
            committed = self.reader.read(self.run_id)
            self.assertEqual((publication.call_count, history.call_count, replay.call_count), (1, 1, 1))
        with self.assertRaises(ProductionError):
            workflow.append_record(committed, 'abandoned', {'reason': 'Ended writer'})
        with store.transaction(self.root):
            current = self.reader.read(self.run_id)
            self.assertEqual(len(current.rows), 2)
            workflow.append_record(current, 'abandoned', {'reason': 'New writer observation'})

    def test_failed_forced_acquisition_cannot_leave_a_writable_prior_view(self):
        with store.transaction(self.root):
            loaded = self.reader.read(self.run_id)
            path = self.directory / 'consumer.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.assertRaises(ProductionError):
                self.reader.read(self.run_id, force=True)
            with self.assertRaises(ProductionError):
                workflow.append_record(loaded, 'handoff', {'recipient': 'Stale publication'})
            path.write_bytes(original)
            current = self.reader.read(self.run_id)
            workflow.append_record(current, 'handoff', {'recipient': 'Checked publication'})

    def test_savepoint_rollback_cannot_restore_a_failed_forced_publication(self):
        with store.transaction(self.root):
            observed = self.reader.read(self.run_id)
            path = self.directory / 'consumer.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.assertRaisesRegex(ProductionError, 'ARTIFACT_CORRUPT'):
                with store.transaction(self.root):
                    self.reader.read(self.run_id, force=True)
            with self.assertRaisesRegex(ProductionError, 'ARTIFACT_CORRUPT'):
                self.reader.read(self.run_id)
            with self.assertRaises(ProductionError):
                workflow.append_record(observed, 'handoff', {'recipient': 'Failed forced observation'})
            path.write_bytes(original)
            current = self.reader.read(self.run_id)
            self.assertIsNot(current, observed)
            workflow.append_record(current, 'handoff', {'recipient': 'Repaired and acquired publication'})

    def test_expired_transaction_context_cannot_return_its_previous_run_view(self):
        with store.transaction(self.root):
            observed = self.reader.read(self.run_id)
            copied = contextvars.copy_context()
        path = self.directory / 'consumer.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaisesRegex(ProductionError, 'ARTIFACT_CORRUPT'):
            copied.run(self.reader.read, self.run_id)
        self.assertEqual(observed.consumer, {'synthetic': True})
        path.write_bytes(original)
        current = copied.run(self.reader.read, self.run_id)
        self.assertIsNot(current, observed)
        self.assertEqual(current.consumer, observed.consumer)

    def test_interrupted_event_journal_rolls_back_before_the_writer_can_continue(self):
        from types import SimpleNamespace

        def interrupted(event, **details):
            if event == 'formal_event_staged':
                raise OSError('Interrupted event journal')

        operation = SimpleNamespace(link=lambda **links: None, event=interrupted)
        with store.transaction(self.root):
            loaded = self.reader.read(self.run_id)
            with patch('operation_context.current', return_value=operation), \
                 self.assertRaisesRegex(OSError, 'Interrupted event journal'):
                workflow.append_record(loaded, 'handoff', {'recipient': 'Uncommitted recipient'})
            self.assertEqual(store.event_rows(self.root, self.run_id), [])
            current = self.reader.read(self.run_id)
            self.assertIs(current.lifecycle, loaded.lifecycle)
            workflow.append_record(current, 'handoff', {'recipient': 'Checked writer'})

    def test_storage_commit_requires_its_current_connection_and_predecessor(self):
        with store.transaction(self.root):
            loaded = self.reader.read(self.run_id)
            history = store.read_history(self.root, self.run_id)
            proposal = store.propose_append(history, self.prepared['input_sha256'], 'handoff',
                                            {'recipient': 'Another owner in the same writer'})
            store.commit_append(self.root, proposal)
            with self.assertRaises(ProductionError) as caught:
                workflow.append_record(loaded, 'candidate', {'files': []})
            self.assertEqual(caught.exception.diagnostic.code, 'EVENT_CONFLICT')
            current = self.reader.read(self.run_id, force=True)
            workflow.append_record(current, 'candidate', {'files': []})
            self.assertEqual(len(store.event_rows(self.root, self.run_id)), 2)
        with store.transaction(self.root), self.assertRaises(ValueError):
            store.commit_append(self.root, proposal)


class ProjectionScopeTests(unittest.TestCase):
    def test_decision_scope_comes_from_prepared_input_without_rebuilding_a_run_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / studio.MANIFEST).write_text('{}', encoding='utf-8')
            receipt = {'event': 'selection', 'sha256': 'a' * 64}
            prepared = {'run': 'owned-run', 'task': {}}
            with patch.object(workflow, 'read_run', side_effect=AssertionError('Use the decision input')), \
                 patch.object(studio_activity, 'changed', return_value={'ok': True}) as changed:
                self.assertIs(workflow._refresh_studio_projection(root, receipt, prepared=prepared), receipt)
                self.assertEqual(changed.call_args.kwargs['subject'], prepared['run'])
                self.assertEqual(changed.call_args.kwargs['characters'], set())
                prepared['task']['recording'] = {'character': 'robot'}
                workflow._refresh_studio_projection(root, receipt, prepared=prepared)
                self.assertEqual(changed.call_args.kwargs['characters'], {'robot'})


class PublicationEvidenceTests(unittest.TestCase):
    def test_producer_documents_are_checked_without_decoding_and_remain_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = {'nested': [{'label': 'producer'}], 'sequence': (1, 2)}
            raw = c.encoded(value)
            (directory / 'document.json').write_bytes(raw)
            c.atomic(directory / 'manifest.json', c.encoded({'complete': True, 'files': [
                {'path': 'document.json', 'sha256': c.digest(raw), 'size': len(raw)}]}))
            decode = c.decode

            def only_unowned(data, *args, **kwargs):
                if data == raw:
                    raise AssertionError('consume the checked producer document')
                return decode(data, *args, **kwargs)

            with patch.object(c, 'decode', only_unowned):
                acquired = compiler.acquire_publication(directory, documents={'document.json'},
                    owned_documents={'document.json': value})
            value['nested'][0]['label'] = 'later author edit'
            self.assertEqual(acquired.documents['document.json']['nested'][0]['label'], 'producer')
            self.assertIsInstance(acquired.documents['document.json']['sequence'], list)
            self.assertEqual(acquired.documents['document.json']['sequence'], [1, 2])
            with self.assertRaises(TypeError):
                acquired.documents['document.json']['nested'][0]['label'] = 'mutation'
            with self.assertRaises(ProductionError) as caught:
                compiler.acquire_publication(directory, documents={'document.json'},
                    owned_documents={'document.json': value})
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_CORRUPT')

            with self.assertRaisesRegex(TypeError, 'JSON object names'):
                compiler.acquire_publication(directory, documents={'document.json'},
                    owned_documents={'document.json': {1: 'invalid object name'}})

    def test_semantics_use_the_manifest_scan_bytes_without_reopening_the_object(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = c.encoded({'observed': 'original'})
            key = c.digest(raw)
            path = directory / 'objects' / key
            path.parent.mkdir()
            path.write_bytes(raw)
            c.atomic(directory / 'manifest.json', c.encoded({'complete': True, 'files': [
                {'path': 'objects/' + key, 'sha256': key, 'size': len(raw)}]}))
            original = Path.open
            opened = Counter()

            def observe(selected, *args, **kwargs):
                if selected == path:
                    opened[str(selected)] += 1
                return original(selected, *args, **kwargs)

            with patch.object(Path, 'open', observe):
                acquired = compiler.acquire_publication(directory)
                self.assertEqual(acquired.evidence.document(key), {'observed': 'original'})
                self.assertEqual(acquired.evidence.read(key), raw)
            self.assertEqual(opened, {str(path): 1})
            before = path.stat()
            path.write_bytes(raw.replace(b'original', b'modified'))
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertEqual(acquired.evidence.document(key), {'observed': 'original'})
            with self.assertRaises(ProductionError) as caught:
                compiler.acquire_publication(directory)
            self.assertEqual(caught.exception.diagnostic.code, 'EVIDENCE_SNAPSHOT_CORRUPT')

    def test_large_publication_objects_stream_and_do_not_enlarge_retained_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'stage'
            directory.mkdir()
            raw = b'x' * (8 * 1024 * 1024 + 1)
            key = c.digest(raw)
            path = directory / 'objects' / key
            path.parent.mkdir()
            path.write_bytes(raw)
            c.atomic(directory / 'manifest.json', c.encoded({'complete': True, 'files': [
                {'path': 'objects/' + key, 'sha256': key, 'size': len(raw)}]}))
            original = Path.open
            reads = []

            class ObservedStream:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    self.stream.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.stream.__exit__(*args)

                def read(self, size=-1):
                    reads.append(size)
                    return self.stream.read(size)

            def observe(selected, *args, **kwargs):
                stream = original(selected, *args, **kwargs)
                return ObservedStream(stream) if selected == path else stream

            with patch.object(Path, 'open', observe):
                acquired = compiler.acquire_publication(directory)
            self.assertGreater(len(reads), 1)
            self.assertEqual(set(reads), {1024 * 1024})
            self.assertEqual(acquired.verified_objects, {key: len(raw)})
            self.assertEqual(acquired.evidence._size, 0)
            self.assertNotIn(key, acquired.evidence._objects)
            published = Path(temporary) / 'published'
            directory.rename(published)
            handed = acquired.published_at(published)
            self.assertIs(handed.evidence, acquired.evidence)
            self.assertEqual(handed.evidence.read(key), raw)
            self.assertEqual(handed.evidence._size, 0)


class JournalOwnershipTests(unittest.TestCase):
    def test_written_journal_values_are_owned_without_a_file_roundtrip(self):
        from dispatch_runtime import RunJournal
        with tempfile.TemporaryDirectory() as temporary, read_context.public_call():
            root = Path(temporary)
            (root / 'runs').mkdir()
            journal = RunJournal.create(root, operation='synthetic')
            answer = {'outputs': [{'status': 'complete', 'indices': [1], 'bounds': (0, 8)}]}
            expected = {'outputs': [{'status': 'complete', 'indices': [1], 'bounds': [0, 8]}]}
            journal.write('answer.json', answer)
            answer['outputs'][0]['indices'].append(99)
            with patch.object(c, 'read', side_effect=AssertionError('owned journal bytes must not be reopened')):
                self.assertIs(RunJournal.open(journal.path), journal)
                self.assertEqual(journal.read('answer.json'), expected)
                self.assertEqual(journal.bytes('answer.json'), c.encoded(expected))
                self.assertEqual(journal.write('answer.json', expected), journal.path / 'answer.json')
                with self.assertRaises(TypeError):
                    journal.read('answer.json')['outputs'][0]['indices'].append(2)
            with self.assertRaisesRegex(TypeError, 'JSON object names must be strings'):
                journal.write('invalid.json', {1: 'ambiguous name'})
            self.assertFalse((journal.path / 'invalid.json').exists())

    def test_new_call_reacquires_a_reused_journal_before_updating_metadata(self):
        from dispatch_runtime import RunJournal
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'runs').mkdir()
            with read_context.public_call():
                journal = RunJournal.create(root, operation='synthetic')
                journal.write('answer.json', {'result': 'first observation'})
                first = journal.read('answer.json')
            changed = c.load(journal.path / 'run.json')
            changed['external_note'] = 'Committed by a separate recovery operation.'
            c.atomic(journal.path / 'run.json', c.encoded(changed), replace=True)
            c.atomic(journal.path / 'answer.json', c.encoded({'result': 'new observation'}), replace=True)
            with read_context.public_call(), patch.object(c, 'read', wraps=c.read) as acquire:
                journal.update(status='resumed')
                self.assertEqual(journal.document['external_note'], changed['external_note'])
                self.assertEqual(journal.read('answer.json'), {'result': 'new observation'})
                self.assertIs(RunJournal.open(journal.path), journal)
                self.assertEqual(journal.read('answer.json'), {'result': 'new observation'})
                self.assertEqual(Counter(Path(call.args[0]).name for call in acquire.call_args_list),
                                 {'run.json': 1, 'answer.json': 1})
            self.assertEqual(first, {'result': 'first observation'})
            self.assertEqual(c.load(journal.path / 'run.json')['external_note'], changed['external_note'])


class EvidenceOwnershipTests(unittest.TestCase):
    def test_decoded_evidence_and_sidecar_meaning_share_their_current_acquisition(self):
        import character_sheet
        raw = character_sheet.BLANK_TEMPLATE_PATH.read_bytes()
        key = c.digest(raw)
        lines = c.encoded({'step': 1}) + c.encoded({'step': 2})
        line_key = c.digest(lines)
        reads = Counter()

        def read(selected):
            reads[selected] += 1
            return {key: raw, line_key: lines}[selected]

        owner = EvidenceReader(read)
        with patch.object(character_sheet, 'check_sidecar', wraps=character_sheet.check_sidecar) as checked:
            document = owner.document(key)
            self.assertIs(owner.sidecar(key), document)
            self.assertIs(owner.sidecar(key), document)
            self.assertEqual(checked.call_count, 1)
        with self.assertRaises(TypeError):
            document['fields']['field.sheet_layout_profile'] = 'Caller edit'
        observed = owner.lines(line_key)
        self.assertIs(owner.lines(line_key), observed)
        with self.assertRaises(TypeError):
            observed[0]['step'] = 3
        self.assertEqual(reads, {key: 1, line_key: 1})
        later = EvidenceReader(read)
        self.assertIsNot(later.sidecar(key), document)
        self.assertEqual(reads[key], 2)
        bounded = EvidenceReader(read, limit=0)
        self.assertIsNot(bounded.document(key), bounded.document(key))
        self.assertEqual(bounded._size, 0)


class OwnedJsonTests(unittest.TestCase):
    def test_owned_decode_preserves_first_duplicate_diagnostics_at_every_depth(self):
        for raw, key in ((b'{"a":1,"b":2,"b":3,"a":4}', 'b'),
                         (b'[{"outer":{"nested":1,"nested":2}}]', 'nested'),
                         (b'{"a":[],"a":{}}', 'a'),
                         (b'{"a":1,"\\u0061":2}', 'a')):
            for owned in (False, True):
                with self.subTest(raw=raw, owned=owned), self.assertRaises(ValueError) as caught:
                    c.decode(raw, owned=owned)
                self.assertEqual(str(caught.exception), 'duplicate JSON key: ' + key)

    def test_owned_deepcopy_keeps_aliases_memo_and_scalar_subclass_protocol(self):
        class AuthoredText(str):
            def __deepcopy__(self, memo):
                return {'copied': str(self)}

        child = {'values': [1, None, True, 1.5, 'text', b'bytes']}
        held = freeze({'first': child, 'second': child, 'authored': AuthoredText('label')})
        exported = copy.deepcopy(held)
        self.assertIs(exported['first'], exported['second'])
        self.assertIsNot(exported['first'], held['first'])
        self.assertEqual(exported['authored'], {'copied': 'label'})
        exported['first']['values'].append('edit')
        self.assertEqual(len(held['first']['values']), 6)
        marker = object()
        replaced = copy.deepcopy(held, {id(held['first']['values'][4]): marker})
        self.assertIs(replaced['first']['values'][4], marker)

    def test_owned_decoding_finishes_nested_arrays_and_objects_without_mutable_aliases(self):
        value = [{'name': 'Aster', 'values': [[1, {'active': True}], [], {}]}, None]
        raw = c.encoded(value)
        held = c.decode(raw, owned=True)
        self.assertEqual(held, value)
        self.assertEqual(c.encoded(held), raw)
        self.assertIs(freeze(held), held)
        for change in (lambda: held.append({}), lambda: held[0].update(name='Changed'),
                       lambda: held[0]['values'][0].append(2),
                       lambda: held[0]['values'][0][1].update(active=False),
                       lambda: held[0]['values'][1].append(3),
                       lambda: held[0]['values'][2].update(added=True)):
            with self.assertRaises(TypeError):
                change()
        exported = mutable(held)
        exported[0]['values'][0][1]['active'] = False
        self.assertTrue(held[0]['values'][0][1]['active'])
        for raw in (b'{"value":1,"value":2}', b'[{"value":NaN}]', b'[[Infinity]]'):
            with self.assertRaises(ValueError):
                c.decode(raw, owned=True)

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
