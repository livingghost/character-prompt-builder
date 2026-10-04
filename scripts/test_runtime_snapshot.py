"""Fixed pack runtime: binding, content storage, drift diagnostics and reuse."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import operation_context as operations
import pack_manager
import production_case_fixtures as fixtures
import production_execution as execution
import production_store as store
import production_variation as variation
import production_workflow as workflow
import runtime_snapshot
from catalog_retrieval import runtime
from production_diagnostics import ProductionError
from test_production_execution import decisions


ROOT = Path(__file__).resolve().parents[1]
COMMONS = '01a0043b-2250-720d-87b7-f1e6fd7ed230'
MINIMAL_PACK = ROOT / 'examples' / 'pack-authoring' / 'minimal-pack'


class RuntimeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.case = fixtures.create(self.base / 'studio', self.base / 'runtime')
        self.root = self.case['root']
        self.run = workflow.prepare(self.root, 'task.json')['run']
        self.descriptor = workflow.load_run(self.root, self.run)[1]['runtime_snapshot']
        self.models = self.case['pack'] / 'records/models.json'

    def diagnostics(self, run: str | None = None):
        run = run or self.run
        descriptor = workflow.load_run(self.root, run)[1]['runtime_snapshot']
        return runtime_snapshot.current_diagnostics(self.root, descriptor, run=run)

    def codes(self, run: str | None = None):
        return [(row['code'], row['severity']) for row in self.diagnostics(run)]

    def enable(self, pack: Path) -> str:
        state = c.load(self.case['settings'].state_file)
        ident = c.load(pack / 'pack.json')['pack_id']
        state['pack_roots'] = sorted({*state['pack_roots'], str(pack)})
        state['enabled_packs'].append(ident)
        pack_manager.save_state(self.case['settings'].state_file, state)
        runtime.configure_pack_runtime(self.case['settings'])
        return ident

    def operation(self, name: str):
        """Run one public operation context whose stage records the test reads."""
        operation = operations.Operation(name)
        token = operations._CURRENT.set(operation)
        self.addCleanup(lambda: operation.closed or operation.finish(0))
        return operation, token

    def test_one_public_operation_reuses_verified_fixed_runtime(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        payload = runtime_snapshot.read(directory, self.descriptor)
        expected = sum(len(pack['files']) for pack in payload['packs'])
        calls = []
        original = runtime_snapshot.c.sha256_file
        def counted(path):
            calls.append(str(path))
            return original(path)
        with patch.dict(os.environ, {'CPB_HOME': str(self.base / 'home')}), \
             patch.object(runtime_snapshot.c, 'sha256_file', side_effect=counted):
            operation, token = self.operation('runtime-snapshot-test')
            try:
                runtime_snapshot.read(directory, self.descriptor)
                runtime_snapshot.read(directory, self.descriptor)
                self.assertEqual(len(calls), expected)
                runtime_snapshot.read(directory, self.descriptor, force_verify=True)
                self.assertEqual(len(calls), expected * 2)
            finally:
                operation.finish(0)
                operations._CURRENT.reset(token)

    def test_one_public_call_reuses_verified_fixed_runtime_without_operation(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        payload = runtime_snapshot.read(directory, self.descriptor)
        expected = sum(len(pack['files']) for pack in payload['packs'])
        calls = []
        original = runtime_snapshot.c.sha256_file
        def counted(path):
            calls.append(str(path))
            return original(path)
        token = operations._CURRENT.set(None)
        try:
            with patch.object(runtime_snapshot.c, 'sha256_file', side_effect=counted):
                runtime_snapshot.read(directory, self.descriptor)
                self.assertEqual(len(calls), expected)
                with runtime_snapshot.public_call():
                    runtime_snapshot.read(directory, self.descriptor)
                    runtime_snapshot.read(directory, self.descriptor)
                    self.assertEqual(len(calls), expected * 2)
                    runtime_snapshot.read(directory, self.descriptor, force_verify=True)
                    self.assertEqual(len(calls), expected * 3)
                runtime_snapshot.read(directory, self.descriptor)
                self.assertEqual(len(calls), expected * 4)
        finally:
            operations._CURRENT.reset(token)

    def test_fixed_runtime_pack_file_changed_within_a_call_is_refused_when_forced(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        pinned = directory / 'packs' / fixtures.PACK_ID / 'records/models.json'
        with runtime_snapshot.public_call():
            runtime_snapshot.read(directory, self.descriptor)
            pinned.write_bytes(pinned.read_bytes() + b'\n')
            with self.assertRaises(ProductionError) as caught:
                runtime_snapshot.read(directory, self.descriptor, force_verify=True)
        self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
        with self.assertRaises(ProductionError):
            runtime_snapshot.read(directory, self.descriptor)

    def test_lookup_records_are_read_only_and_built_once_per_call(self):
        import copy
        directory = runtime_snapshot.path(self.root, self.descriptor)
        payload = runtime_snapshot.read(directory, self.descriptor)
        stored = next(e['record'] for e in payload['entries'] if e['record'].get('id') == fixtures.MODEL_ID)
        def model():
            return next(entry for entry in runtime.load_entries() if entry.record.get('id') == fixtures.MODEL_ID)
        with runtime_snapshot.public_call():
            with runtime_snapshot.using(directory, self.descriptor):
                first = runtime.load_pack_catalog()
                found = model()
                found.record['label'] = 'Changed by one lookup'
                with self.assertRaises(TypeError):
                    found.record['aliases'].append('changed alias')
                packed = next(entry for entry in first.entries if entry.record.get('id') == fixtures.MODEL_ID)
                with self.assertRaises(TypeError):
                    packed.record['label'] = 'Changed in the shared catalogue'
                editable = copy.deepcopy(packed.record)
                editable['aliases'].append('an editable copy')
                self.assertEqual(json.loads(json.dumps(packed.record)), stored)
            with runtime_snapshot.using(directory, self.descriptor):
                self.assertIs(runtime.load_pack_catalog(), first)
                self.assertEqual(model().record, stored)
        with runtime_snapshot.using(directory, self.descriptor):
            self.assertIsNot(runtime.load_pack_catalog(), first)
            self.assertEqual(model().record, stored)

    def test_run_binds_the_model_service_and_guides_it_used(self):
        binding = self.descriptor['binding']
        self.assertEqual((binding['model'], binding['service']), (fixtures.MODEL_ID, 'synthetic'))
        self.assertEqual([(row['id'], row['role'], row['pack'], row['path']) for row in binding['records']],
                         [(fixtures.MODEL_ID, 'model', fixtures.PACK_ID, 'records/models.json')])
        roles = {(row['name'], row['role'], row['pack']) for row in binding['resources']}
        self.assertTrue({('service-profiles', 'service', fixtures.PACK_ID),
                         ('prompt-writing-guide', 'guide', COMMONS)} <= roles, roles)
        payload = runtime_snapshot.read(runtime_snapshot.path(self.root, self.descriptor), self.descriptor)
        pinned = {(pack['pack_id'], item['path']): item['sha256'] for pack in payload['packs'] for item in pack['files']}
        for row in runtime_snapshot.dependencies(binding):
            self.assertEqual(pinned[(row['pack'], row['path'])], row['sha256'])
        self.assertNotIn('warnings', payload)
        self.assertEqual(self.codes(), [])

    def test_live_edit_of_a_used_record_changes_nothing_fixed(self):
        bound = self.descriptor['binding']['records'][0]['sha256']
        self.models.write_bytes(self.models.read_bytes().replace(b'Authored synthetic prose.', b'Edited live prose.'))
        [row] = self.diagnostics()
        self.assertEqual((row['code'], row['severity'], row['pack'], row['resource']),
                         ('PACK_CONTENT_MISMATCH', 'error', fixtures.PACK_ID, 'records/models.json'))
        self.assertEqual(row['expected'], bound)
        self.assertEqual(row['actual'], c.sha256_file(self.models))
        self.assertEqual(row['affected_runs'], [self.run])
        self.assertEqual([action['operation'] for action in row['actions']], ['restore', 'retarget'])
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertEqual(caught.exception.diagnostic.code, 'PACK_CONTENT_MISMATCH')
        self.assertEqual(store.event_rows(self.root, self.run), [])
        fixed = runtime_snapshot.path(self.root, self.descriptor) / 'packs' / fixtures.PACK_ID / 'records/models.json'
        self.assertEqual(c.sha256_file(fixed), bound)

    def test_removed_record_and_vanished_pack_are_not_found(self):
        document = c.load(self.models)
        document['records'][0]['id'] = 'cpb-synthetic-renamed'
        fixtures.write(self.models, document)
        [row] = self.diagnostics()
        self.assertEqual((row['code'], row['record'], row['resource']),
                         ('RECORD_NOT_FOUND', [fixtures.MODEL_ID], 'records/models.json'))
        shutil.move(str(self.case['pack']), str(self.case['pack']) + '-moved')
        codes = self.codes()
        self.assertIn(('RECORD_NOT_FOUND', 'error'), codes)
        self.assertNotIn('PINNED_RESOURCE_MISSING', [code for code, _ in codes])
        self.assertEqual(self.diagnostics()[0]['pack'], fixtures.PACK_ID)

    def test_release_change_is_reported_on_its_own(self):
        manifest = c.load(self.case['pack'] / 'pack.json')
        manifest['release'] = '2026.09.25.1'
        fixtures.write(self.case['pack'] / 'pack.json', manifest)
        pack_manager.write_lock(self.case['pack'])
        [row] = self.diagnostics()
        self.assertEqual((row['code'], row['expected'], row['actual']),
                         ('PACK_RELEASE_MISMATCH', '2026.09.24.1', '2026.09.25.1'))

    def test_disabled_pack_stops_execute_and_variant(self):
        pack_manager.disable_pack(self.case['settings'], fixtures.PACK_ID)
        self.assertEqual(self.codes(), [('PACK_NOT_ENABLED', 'error')])
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root, self.run, decisions_file=decisions(self.root, self.run))
        self.assertEqual(caught.exception.diagnostic.code, 'PACK_NOT_ENABLED')
        self.assertEqual(store.event_rows(self.root, self.run), [])
        fixtures.write(self.root / 'changes.json', {'changes': {'parameter:steps': 22}, 'reason': 'Synthetic change.'})
        with self.assertRaises(ProductionError) as caught:
            variation.derive(self.root, self.run, changes_file='changes.json', prepare=True)
        self.assertEqual(caught.exception.diagnostic.code, 'PACK_NOT_ENABLED')
        self.assertEqual(len(store.runs(self.root)), 1)

    def test_a_resource_is_fixed_as_the_file_of_the_pack_that_outranks(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        payload = runtime_snapshot.read(directory, self.descriptor)
        self.assertEqual(payload['selection'], {'enabled_packs': sorted([COMMONS, fixtures.PACK_ID])})
        resolved = payload['resources']['service-profiles']
        self.assertEqual((resolved['pack_id'], resolved['path']), (fixtures.PACK_ID, 'resources/services.json'))
        self.assertEqual(sorted(c.load(directory / 'packs' / fixtures.PACK_ID / resolved['path'])['services']), ['synthetic'])
        services = self.case['pack'] / 'resources/services.json'
        document = c.load(services)
        document['services']['synthetic']['label'] = 'Edited synthetic fixture'
        fixtures.write(services, document)
        [row] = self.diagnostics()
        self.assertEqual((row['code'], row['severity'], row['pack'], row['resource']),
                         ('PACK_CONTENT_MISMATCH', 'error', fixtures.PACK_ID, 'resources/services.json'))

    def test_newly_enabled_pack_is_an_error_only_when_it_declares_a_used_record(self):
        extra = self.base / 'runtime' / 'packs' / 'extra'
        shutil.copytree(MINIMAL_PACK, extra)
        ident = self.enable(extra)
        [row] = self.diagnostics()
        self.assertEqual((row['code'], row['severity'], row['pack']), ('PACK_SELECTION_CHANGED', 'warning', ident))
        rival = fixtures.create_pack(self.base / 'runtime' / 'packs' / 'rival')
        manifest = c.load(rival / 'pack.json')
        manifest.update(pack_id=pack_manager.generate_uuid7(), name='Synthetic Rival')
        fixtures.write(rival / 'pack.json', manifest)
        pack_manager.write_lock(rival)
        rival_id = self.enable(rival)
        errors = [row for row in self.diagnostics() if row['severity'] == 'error']
        self.assertEqual([(row['code'], row['pack'], row.get('record'), row.get('resource')) for row in errors],
                         [('PACK_SELECTION_CHANGED', rival_id, [fixtures.MODEL_ID], None),
                          ('PACK_SELECTION_CHANGED', rival_id, None, ['service-profiles'])])
        self.assertEqual([row['actions'][0]['operation'] for row in errors], ['disable-pack', 'disable-pack'])

    def test_newly_enabled_pack_binding_a_used_resource_is_an_error(self):
        extra = self.base / 'runtime' / 'packs' / 'extra'
        shutil.copytree(MINIMAL_PACK, extra)
        manifest = c.load(extra / 'pack.json')
        manifest['content'].update(resource_globs=['resources/**/*'],
                                   resource_bindings={'service-profiles': 'resources/services.json'})
        fixtures.write(extra / 'pack.json', manifest)
        (extra / 'resources').mkdir()
        shutil.copy2(self.case['pack'] / 'resources/services.json', extra / 'resources/services.json')
        ident = self.enable(extra)
        [row] = self.diagnostics()
        self.assertEqual((row['code'], row['severity'], row['pack'], row['resource'], row['affected_runs']),
                         ('PACK_SELECTION_CHANGED', 'error', ident, ['service-profiles'], [self.run]))
        self.assertEqual(row['actions'][0]['operation'], 'disable-pack')

    def test_missing_or_corrupt_fixed_runtime_is_reported_on_the_snapshot_side(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        (directory / 'packs' / fixtures.PACK_ID / 'records/models.json').unlink()
        with self.assertRaises(ProductionError) as caught:
            self.diagnostics()
        self.assertEqual(caught.exception.diagnostic.code, 'PINNED_RESOURCE_MISSING')
        (directory / 'snapshot.json').unlink()
        with self.assertRaises(ProductionError) as caught:
            self.diagnostics()
        self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')

    def test_unlocked_pack_being_edited_still_prepares(self):
        development = self.base / 'runtime' / 'packs' / 'development'
        shutil.copytree(MINIMAL_PACK, development)
        self.assertFalse((development / 'pack.lock.json').exists())
        ident = self.enable(development)
        run = workflow.prepare(self.root, 'task.json')['run']
        descriptor = workflow.load_run(self.root, run)[1]['runtime_snapshot']
        payload = runtime_snapshot.read(runtime_snapshot.path(self.root, descriptor), descriptor)
        self.assertIn(ident, [pack['pack_id'] for pack in payload['packs']])
        self.assertNotIn(ident, {row['pack'] for row in runtime_snapshot.dependencies(descriptor['binding'])})
        record = development / 'records/lighting.json'
        document = c.load(record)
        document['records'][0]['label'] += ' edited'
        fixtures.write(record, document)
        self.assertEqual(self.codes(run), [])

    def test_warm_preparation_reuses_stored_content_by_stage_records(self):
        with patch.dict(os.environ, {'CPB_HOME': str(self.base / 'home')}):
            def prepared(name):
                operation, token = self.operation(name)
                try:
                    run = workflow.prepare(self.root, 'task.json')['run']
                finally:
                    operation.finish(0)
                    operations._CURRENT.reset(token)
                events = [json.loads(line) for line in (operation.path / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
                return run, events
            objects = self.root / 'runtime' / 'objects'
            shutil.rmtree(self.root / 'runtime')
            cold_run, cold = prepared('cold-prepare')
            warm_run, warm = prepared('warm-prepare')
            stages = lambda events: {row['phase'] for row in events if row['event'] == 'stage_completed'}
            published = lambda events: next(row for row in events if row['event'] == 'runtime_snapshot_published')
            self.assertEqual(stages(cold), stages(warm))
            self.assertIn('runtime-resolution', stages(cold))
            self.assertTrue(all('duration_seconds' in row for row in cold + warm if row['event'] == 'stage_completed'))
            first = published(cold)
            self.assertEqual((first['snapshot_reused'], first['stored'], first['reused']), (False, first['files'], 0))
            self.assertTrue(published(warm)['snapshot_reused'])
            self.assertEqual(len(list(objects.iterdir())), first['files'])
            (self.case['pack'] / 'README.md').write_text('Synthetic pack notes added after preparation.\n', encoding='utf-8')
            pack_manager.write_lock(self.case['pack'])
            runtime.configure_pack_runtime(self.case['settings'])
            edited_run, edited = prepared('edited-prepare')
            changed = published(edited)
            # Only the added README.md and the rebuilt lock are new content.
            self.assertEqual(changed['files'], first['files'] + 1)
            self.assertEqual((changed['snapshot_reused'], changed['stored'], changed['reused']), (False, 2, first['files'] - 1))
            descriptor = workflow.load_run(self.root, edited_run)[1]['runtime_snapshot']
            view = runtime_snapshot.path(self.root, descriptor) / 'packs' / COMMONS / 'pack.json'
            self.assertTrue(os.path.samefile(view, objects / c.sha256_file(view)))
        self.assertEqual(len({cold_run, warm_run, edited_run}), 3)

    def test_file_system_without_hard_links_stores_complete_copies(self):
        import errno
        shutil.rmtree(self.root / 'runtime')
        def refused(*args, **kwargs):
            raise OSError(errno.EPERM, 'Synthetic file system without hard links')
        with patch.object(os, 'link', side_effect=refused) as link:
            run = workflow.prepare(self.root, 'task.json')['run']
        self.assertTrue(link.called)
        descriptor = workflow.load_run(self.root, run)[1]['runtime_snapshot']
        directory = runtime_snapshot.path(self.root, descriptor)
        payload = runtime_snapshot.read(directory, descriptor, force_verify=True)
        files = [(pack['pack_id'], item) for pack in payload['packs'] for item in pack['files']]
        objects = self.root / 'runtime' / 'objects'
        self.assertEqual(sorted(path.name for path in objects.iterdir()), sorted({item['sha256'] for _, item in files}))
        for pack, item in files:
            view = directory / 'packs' / pack / item['path']
            stored = objects / item['sha256']
            self.assertFalse(os.path.samefile(view, stored))
            self.assertEqual((c.sha256_file(view), c.sha256_file(stored)), (item['sha256'], item['sha256']))
        self.assertEqual(self.codes(run), [])

    def test_execute_hashes_only_the_live_files_the_run_uses(self):
        decision_file = decisions(self.root, self.run)
        bound = {((self.case['pack'] if row['pack'] == fixtures.PACK_ID else ROOT / 'packs' / 'commons') / row['path']).resolve()
                 for row in runtime_snapshot.dependencies(self.descriptor['binding'])}
        live_roots = (self.case['pack'].resolve(), (ROOT / 'packs' / 'commons').resolve())
        hashed, rescans = [], []
        original = c.sha256_file
        original_pack = pack_manager.sha256_file
        def counted(path):
            resolved = Path(path).resolve()
            if any(root in resolved.parents for root in live_roots):
                hashed.append(resolved)
            return original(path)
        def counted_pack(path):
            rescans.append(path)
            return original_pack(path)
        with patch.dict(os.environ, {'CPB_HOME': str(self.base / 'home')}), \
             patch.object(c, 'sha256_file', side_effect=counted), \
             patch.object(pack_manager, 'sha256_file', side_effect=counted_pack):
            operation, token = self.operation('bounded-execute')
            try:
                result = execution.execute(self.root, self.run, decisions_file=decision_file)
            finally:
                operation.finish(0)
                operations._CURRENT.reset(token)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(rescans, [])
        self.assertTrue(set(hashed) <= bound, set(hashed) - bound)
        # One comparison for the operation, and at most one forced comparison at the external effect.
        self.assertLessEqual(len(hashed), 2 * len(bound))


class TransactionScopeTests(unittest.TestCase):
    def test_threads_opening_transaction_scopes_at_once_each_get_their_own(self):
        import sys
        import threading
        # Ended transactions leave scopes that the next new scope removes.
        ended = {-index: (object(), {}) for index in range(1, 50001)}
        connections = [object() for _ in range(8)]
        start = threading.Barrier(len(connections))
        found, errors = {}, []
        def open_scope(connection):
            try:
                start.wait()
                found[id(connection)] = runtime_snapshot._transaction_scope(connection)
            except Exception as exc:
                errors.append(exc)
        interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            with patch.dict(runtime_snapshot._TRANSACTIONS, ended):
                threads = [threading.Thread(target=open_scope, args=(item,)) for item in connections]
                for thread in threads: thread.start()
                for thread in threads: thread.join()
        finally:
            sys.setswitchinterval(interval)
        self.assertEqual(errors, [])
        self.assertEqual(len({id(scope) for scope in found.values()}), len(connections))


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
