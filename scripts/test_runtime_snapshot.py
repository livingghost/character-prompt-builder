"""Fixed pack runtime: binding, content storage, drift diagnostics and reuse."""
from __future__ import annotations
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
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


class RuntimeMembershipTests(unittest.TestCase):
    """Small file-only snapshots exercise publication ownership without a DB."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'studio'

    def snapshot(self, name: str, *, extra_declared: bool = False):
        directory = self.base / name
        files = []
        contents = {'records/models.json': b'{"model":"synthetic"}\n'}
        if extra_declared:
            contents['resources/guide.txt'] = b'Complete declared guide.\n'
        for relative, raw in contents.items():
            c.atomic(directory / 'packs' / fixtures.PACK_ID / relative, raw)
            files.append({'path': relative, 'sha256': c.digest(raw), 'size': len(raw)})
        payload = {'packs': [{'pack_id': fixtures.PACK_ID, 'files': files}]}
        c.atomic(directory / 'snapshot.json', c.encoded(payload))
        return directory, {'sha256': c.content_id(payload), 'settings': {}}

    def test_fresh_publication_keeps_unexpected_staged_bytes_for_inspection(self):
        directory, descriptor = self.snapshot('staged')
        extra = directory / 'packs' / fixtures.PACK_ID / 'records' / 'unowned.json'
        c.atomic(extra, b'unexpected stable bytes')
        with self.assertRaises(ProductionError) as caught:
            runtime_snapshot.publish(self.root, directory, descriptor)
        self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
        self.assertEqual(caught.exception.diagnostic.details['cause']['code'], 'ARTIFACT_SET_MISMATCH')
        self.assertEqual(extra.read_bytes(), b'unexpected stable bytes')
        self.assertFalse(runtime_snapshot.path(self.root, descriptor).exists())

    def test_reuse_checks_staged_and_existing_trees_before_disposal(self):
        original, descriptor = self.snapshot('first')
        target = runtime_snapshot.publish(self.root, original, descriptor)
        for place in ('staged', 'target'):
            with self.subTest(place=place):
                staged, _ = self.snapshot('second-' + place)
                extra = (staged if place == 'staged' else target) / 'unowned.txt'
                with runtime_snapshot.public_call():
                    runtime_snapshot.read(staged, descriptor)
                    runtime_snapshot.read(target, descriptor)
                    c.atomic(extra, b'preserved')
                    with self.assertRaises(ProductionError) as caught:
                        runtime_snapshot.publish(self.root, staged, descriptor)
                self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
                self.assertTrue(staged.is_dir())
                self.assertEqual(extra.read_bytes(), b'preserved')

    def test_reuse_preserves_stage_until_the_existing_name_is_durable(self):
        original, descriptor = self.snapshot('published-first')
        target = runtime_snapshot.publish(self.root, original, descriptor)
        staged, _ = self.snapshot('duplicate-stage')
        flush = c.fsync_dir

        def fail_parent(path):
            if path == target.parent:
                raise OSError('Synthetic competing publisher directory flush failure')
            return flush(path)

        with patch.object(c, 'fsync_dir', side_effect=fail_parent):
            with self.assertRaises(OSError):
                runtime_snapshot.publish(self.root, staged, descriptor)
        self.assertTrue(staged.is_dir())
        self.assertTrue(target.is_dir())
        self.assertEqual(runtime_snapshot.read(staged, descriptor), runtime_snapshot.read(target, descriptor))

    def test_force_verification_checks_membership_within_a_cached_call(self):
        directory, descriptor = self.snapshot('staged')
        with runtime_snapshot.public_call():
            runtime_snapshot.read(directory, descriptor)
            c.atomic(directory / 'additional.txt', b'added after the first read')
            with self.assertRaises(ProductionError):
                runtime_snapshot.read(directory, descriptor, force_verify=True)
            with self.assertRaises(ProductionError):
                runtime_snapshot.read(directory, descriptor)
        with self.assertRaises(ProductionError):
            runtime_snapshot.read(directory, descriptor)

    def test_force_current_rechecks_cached_pinned_files(self):
        directory, descriptor = self.snapshot('staged')
        directory = runtime_snapshot.publish(self.root, directory, descriptor)
        pinned = directory / 'packs' / fixtures.PACK_ID / 'records/models.json'
        with runtime_snapshot.public_call():
            runtime_snapshot.read(directory, descriptor)
            pinned.write_bytes(b'changed fixed runtime')
            with self.assertRaises(ProductionError) as caught:
                runtime_snapshot.require_current(self.root, descriptor, force=True)
            self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
            with self.assertRaises(ProductionError):
                runtime_snapshot.read(directory, descriptor)

    def test_shared_object_reuse_keeps_a_corrupt_staged_view_instead_of_replacing_it(self):
        first, descriptor = self.snapshot('first')
        runtime_snapshot.publish(self.root, first, descriptor)
        staged, changed_descriptor = self.snapshot('second', extra_declared=True)
        view = staged / 'packs' / fixtures.PACK_ID / 'records/models.json'
        view.write_bytes(b'changed before storage')
        with self.assertRaises(ProductionError) as caught:
            runtime_snapshot.publish(self.root, staged, changed_descriptor)
        self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
        self.assertEqual(view.read_bytes(), b'changed before storage')
        self.assertFalse(runtime_snapshot.path(self.root, changed_descriptor).exists())

    def test_unchanged_metadata_has_one_decoded_owner_across_forced_checks(self):
        directory,descriptor=self.snapshot('owned-metadata')
        with runtime_snapshot.public_call(), patch.object(c,'decode',wraps=c.decode) as decode, \
                patch.object(runtime_snapshot,'_verify_fixed_file',wraps=runtime_snapshot._verify_fixed_file) as verify:
            first=runtime_snapshot.acquire_runtime(directory,descriptor)
            second=runtime_snapshot.acquire_runtime(directory,descriptor,previous=first)
            forced=runtime_snapshot.acquire_runtime(directory,descriptor,force_verify=True,previous=first)
            self.assertIs(first.payload,second.payload)
            self.assertIs(first.payload,forced.payload)
            self.assertEqual(decode.call_count,1)
            self.assertEqual(verify.call_count,3)
            with self.assertRaises(TypeError):first.payload['packs'].append({})
            exported=runtime_snapshot.read(directory,descriptor)
            exported['packs'].clear()
            self.assertEqual(len(first.payload['packs']),1)

    def test_changed_metadata_is_checked_even_with_an_owned_payload(self):
        directory,descriptor=self.snapshot('metadata-change')
        with runtime_snapshot.public_call():
            owned=runtime_snapshot.acquire_runtime(directory,descriptor)
            (directory/'snapshot.json').write_bytes(b'{"packs":[]}\n')
            with self.assertRaisesRegex(ProductionError,'RUNTIME_SNAPSHOT_CORRUPT'):
                runtime_snapshot.acquire_runtime(directory,descriptor,force_verify=True,previous=owned)
            with self.assertRaisesRegex(ProductionError,'RUNTIME_SNAPSHOT_CORRUPT'):
                runtime_snapshot.acquire_runtime(directory,descriptor,previous=owned)

    def test_route_reads_owned_resource_bytes_without_catalogue_or_source_reopens(self):
        import route_reading
        from live_source_read import LiveSourceRead
        directory,descriptor=self.snapshot('named-resources')
        payload=c.load(directory/'snapshot.json')
        payload['resources']={}
        for name,value in [('prompt-writing-guide',{'sections':[]}),('prompt-dialects',{'dialects':[]})]:
            relative='resources/'+name+'.json'
            raw=c.encoded(value)
            c.atomic(directory/'packs'/fixtures.PACK_ID/relative,raw)
            payload['packs'][0]['files'].append({'path':relative,'sha256':c.digest(raw),'size':len(raw)})
            payload['resources'][name]={'pack_id':fixtures.PACK_ID,'path':relative,'media_type':'application/json'}
        c.atomic(directory/'snapshot.json',c.encoded(payload),replace=True)
        descriptor['sha256']=c.content_id(payload)
        skill=self.base/'synthetic-skill'
        manifest={'routes':{'synthetic':{'features':['prompt-dialect'],'reads':['guide.md'],'stages':[]}},
                  'features':{'prompt-dialect':{'reads':[],'source_roles':[]}},'always_read':[]}
        inputs={'config/execution-routes.json':c.encoded(manifest),'guide.md':b'Complete synthetic route.\n'}
        for path,raw in inputs.items():c.atomic(skill/path,raw)
        sources=LiveSourceRead(self.root,skill,[{'space':'skill','path':path} for path in inputs])
        with runtime_snapshot.public_call():
            owned=runtime_snapshot.acquire_runtime(directory,descriptor)
            removed=directory/'packs'/fixtures.PACK_ID/'resources/prompt-writing-guide.json'
            removed.unlink()
            with patch.object(c,'read',side_effect=AssertionError('route reopened acquired bytes')), \
                    patch.object(route_reading,'_live_resource_reader',side_effect=AssertionError('route rebuilt a catalogue')):
                reading,bodies=route_reading.capture('synthetic',root=skill,
                    resource_reader=owned.read_resource,read_source=sources.skill_bytes)
            self.assertEqual(reading['resources']['prompt-writing-guide']['status'],'present')
            self.assertEqual(len(bodies),3)
            with self.assertRaisesRegex(ProductionError,'PINNED_RESOURCE_MISSING'):
                runtime_snapshot.acquire_runtime(directory,descriptor,force_verify=True)

    def test_file_flush_failure_keeps_the_private_stage_without_shared_objects(self):
        from publication_artifacts import StagedArtifacts
        directory,descriptor=self.snapshot('flush-failure')
        with patch.object(StagedArtifacts,'flush_files',side_effect=OSError('Synthetic file flush failure')):
            with self.assertRaisesRegex(OSError,'Synthetic file flush failure'):
                runtime_snapshot.publish(self.root,directory,descriptor)
        self.assertTrue((directory/'snapshot.json').is_file())
        self.assertFalse((self.root/'runtime/objects').exists())
        self.assertFalse(runtime_snapshot.path(self.root,descriptor).exists())

    def test_publication_retires_the_stage_and_target_acquisition_is_independent(self):
        directory,descriptor=self.snapshot('owner-transfer')
        with runtime_snapshot.public_call():
            owned=runtime_snapshot.acquire_runtime(directory,descriptor)
            target=runtime_snapshot.publish(self.root,directory,descriptor,read=owned)
            published=runtime_snapshot.acquire_runtime(target,descriptor)
            self.assertEqual(published.payload,owned.payload)
            self.assertIsNot(published,owned)
            with self.assertRaisesRegex(ProductionError,'RUNTIME_SNAPSHOT_CORRUPT'):
                with runtime_snapshot.using(directory,descriptor):
                    self.fail('The disposed stage remained a usable runtime source')


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

    def test_explicit_fixed_acquisitions_check_every_member_inside_an_operation(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        payload = runtime_snapshot.read(directory, self.descriptor)
        expected = sum(len(pack['files']) for pack in payload['packs'])
        calls = []
        original = runtime_snapshot._verify_fixed_file
        def counted(directory,pack,item,**kwargs):
            calls.append((pack,item['path']))
            return original(directory,pack,item,**kwargs)
        with patch.dict(os.environ, {'CPB_HOME': str(self.base / 'home')}), \
             patch.object(runtime_snapshot, '_verify_fixed_file', side_effect=counted):
            operation, token = self.operation('runtime-snapshot-test')
            try:
                runtime_snapshot.read(directory, self.descriptor)
                runtime_snapshot.read(directory, self.descriptor)
                self.assertEqual(len(calls), expected * 2)
                runtime_snapshot.read(directory, self.descriptor, force_verify=True)
                self.assertEqual(len(calls), expected * 3)
            finally:
                operation.finish(0)
                operations._CURRENT.reset(token)

    def test_public_call_scope_does_not_replace_a_new_fixed_acquisition(self):
        directory = runtime_snapshot.path(self.root, self.descriptor)
        payload = runtime_snapshot.read(directory, self.descriptor)
        expected = sum(len(pack['files']) for pack in payload['packs'])
        calls = []
        original = runtime_snapshot._verify_fixed_file
        def counted(directory,pack,item,**kwargs):
            calls.append((pack,item['path']))
            return original(directory,pack,item,**kwargs)
        token = operations._CURRENT.set(None)
        try:
            with patch.object(runtime_snapshot, '_verify_fixed_file', side_effect=counted):
                runtime_snapshot.read(directory, self.descriptor)
                self.assertEqual(len(calls), expected)
                with runtime_snapshot.public_call():
                    runtime_snapshot.read(directory, self.descriptor)
                    runtime_snapshot.read(directory, self.descriptor)
                    self.assertEqual(len(calls), expected * 3)
                    runtime_snapshot.read(directory, self.descriptor, force_verify=True)
                    self.assertEqual(len(calls), expected * 4)
                runtime_snapshot.read(directory, self.descriptor)
                self.assertEqual(len(calls), expected * 5)
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
            with self.assertRaises(ProductionError):
                runtime_snapshot.read(directory, self.descriptor)
        self.assertEqual(caught.exception.diagnostic.code, 'RUNTIME_SNAPSHOT_CORRUPT')
        with self.assertRaises(ProductionError):
            runtime_snapshot.read(directory, self.descriptor)

    def test_prior_runtime_metadata_preserves_current_acquisition_and_failure_recovery(self):
        first = workflow.read_current(self.root, self.run)
        owned = first.runtime
        with store.transaction(self.root):
            current = workflow.read_current(self.root, self.run, previous_runtime=owned)
            self.assertIs(current.runtime.payload, owned.payload)
            self.assertIsNot(current.runtime.file_bytes, owned.file_bytes)
        directory = runtime_snapshot.path(self.root, self.descriptor)
        member = directory / 'packs' / fixtures.PACK_ID / 'records/models.json'
        original = member.read_bytes()
        changed = original + b'\n'
        member.write_bytes(changed)
        for force in (False, True):
            with self.subTest(force=force), self.assertRaisesRegex(ProductionError, 'RUNTIME_SNAPSHOT_CORRUPT'):
                workflow.read_current(self.root, self.run, force=force, previous_runtime=owned)
        reported = workflow.freshness_diagnostics(self.root, self.run, previous_runtime=owned)
        self.assertIn('RUNTIME_SNAPSHOT_CORRUPT', {item['code'] for item in reported})

        # Rewriting member checksums cannot substitute a different archive for
        # the descriptor retained by the run or the earlier acquired metadata.
        replacement = c.decode(owned.raw)
        pack = next(item for item in replacement['packs'] if item['pack_id'] == fixtures.PACK_ID)
        record = next(item for item in pack['files'] if item['path'] == 'records/models.json')
        record.update(sha256=c.digest(changed), size=len(changed))
        (directory / 'snapshot.json').write_bytes(c.encoded(replacement))
        with self.assertRaisesRegex(ProductionError, 'RUNTIME_SNAPSHOT_CORRUPT'):
            workflow.assert_current(self.root, self.run, force=True, previous_runtime=owned)

        member.write_bytes(original)
        (directory / 'snapshot.json').write_bytes(owned.raw)
        restored = workflow.read_current(self.root, self.run, force=True, previous_runtime=owned)
        self.assertIs(restored.runtime.payload, owned.payload)
        self.assertIsNot(restored.runtime.file_bytes, owned.file_bytes)
        self.assertEqual(restored.runtime.read_pack(fixtures.PACK_ID, 'records/models.json'), original)

        # Fixed metadata supplies no proof that current pack sources still
        # match. The diagnostic fallback keeps the same independent findings.
        live = self.models.read_bytes()
        try:
            self.models.write_bytes(live + b'\n')
            with self.assertRaises(ProductionError):
                workflow.read_current(self.root, self.run, previous_runtime=owned)
            self.assertEqual(workflow.freshness_diagnostics(self.root, self.run, previous_runtime=owned),
                             workflow.freshness_diagnostics(self.root, self.run))
        finally:
            self.models.write_bytes(live)

    def test_lookup_records_are_read_only_and_each_explicit_adapter_owns_its_input(self):
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
                self.assertIsNot(runtime.load_pack_catalog(), first)
                self.assertEqual(model().record, stored)
        with runtime_snapshot.using(directory, self.descriptor):
            self.assertIsNot(runtime.load_pack_catalog(), first)
            self.assertEqual(model().record, stored)

    def test_run_retains_full_runtime_and_status_needs_no_catalogue(self):
        directory=runtime_snapshot.path(self.root,self.descriptor)
        with runtime_snapshot.public_call():
            owned=runtime_snapshot.acquire_runtime(directory,self.descriptor)
            with patch.object(runtime_snapshot,'catalogue',side_effect=AssertionError('status built a catalogue')):
                report=workflow.status(self.root,self.run)
            self.assertTrue(report['ok'])
            json.dumps(report)
            self.assertIn('profiles',owned.payload)
            self.assertIn('phrases',owned.payload)
            required={(row['pack'],row['path']) for row in runtime_snapshot.dependencies(self.descriptor['binding'])}
            declared={(pack['pack_id'],item['path']) for pack in owned.payload['packs'] for item in pack['files']}
            self.assertEqual(set(owned.file_bytes),declared)
            self.assertLess(required,declared)
            self.assertLess({row['id'] for row in self.descriptor['binding']['records']},
                            {row['record']['id'] for row in owned.payload['entries']})
            forced=runtime_snapshot.acquire_runtime(directory,self.descriptor,force_verify=True,previous=owned)
            self.assertIs(forced.payload,owned.payload)
            exported=runtime_snapshot.read(directory,self.descriptor)
            self.assertIs(type(exported),dict)
            self.assertEqual(c.content_id(exported),self.descriptor['sha256'])
            built=runtime_snapshot.catalogue(directory,owned.payload,read=owned)
            self.assertEqual(built.fingerprint,self.descriptor['sha256'])
            model=next(entry for entry in built.entries if entry.record.get('id')==fixtures.MODEL_ID)
            with self.assertRaises(TypeError):model.record['aliases'].append('shared mutation')
            exported['entries'].clear()
            self.assertTrue(owned.payload['entries'])
            pack,relative=next(iter(declared-required))
            (directory/'packs'/pack/relative).write_bytes(b'Changed archived member outside the used binding.')
            with self.assertRaisesRegex(ProductionError,'RUNTIME_SNAPSHOT_CORRUPT'):
                runtime_snapshot.require_current_read(self.root,self.descriptor)

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

    def test_capture_preserves_full_edition_and_owned_evidence_without_a_file_roundtrip(self):
        values={'resources/selected-schema.json':{'schema':{'type':'object'}},
                'resources/selected-policy.json':{'basis':'resources/selected-basis.txt'},
                'resources/selected-basis.txt':'Complete authored evidence.\n'}
        for relative,value in values.items():
            fixtures.write(self.case['pack']/relative,value)
        pack_manager.write_lock(self.case['pack'])
        source=runtime_snapshot.compilation_inputs(self.root).runtime
        evidence={'@pack/'+fixtures.PACK_ID+'/'+relative:source.read_named('@pack/'+fixtures.PACK_ID+'/'+relative)
                  for relative in values}
        target={'model_id':fixtures.MODEL_ID,'offering':{'service':'synthetic'}}
        projection={'retrieval_record':{'elements':[]},'input_snapshots':{}}
        checked,none=runtime_snapshot.capture_compilation(source,None,target=target,package=projection,
            reading_resources={},evidence_bytes=evidence)
        self.assertIsNone(none)
        for relative in values:
            (self.case['pack']/relative).unlink()
        destination=self.base/'owned-runtime'
        # Pack text belongs to the acquired inputs even if its live path
        # disappears; the publication/current boundary must reject that drift.
        descriptor,owned=runtime_snapshot.capture_compilation(source,destination,target=target,package=projection,
            reading_resources={},evidence_bytes=evidence)
        self.assertEqual(checked,descriptor)
        expected={(fixtures.PACK_ID,relative) for relative in values}
        self.assertEqual({(row['pack'],row['path']) for row in descriptor['binding']['evidence']},expected)
        self.assertLess(expected,set(owned.file_bytes))
        self.assertIn('profiles',owned.payload)
        self.assertIn('phrases',owned.payload)
        runtime_snapshot.publish(self.root,destination,descriptor,read=owned)
        with self.assertRaisesRegex(ProductionError,'RECORD_NOT_FOUND'):
            runtime_snapshot.require_current_read(self.root,descriptor)

    def test_missing_pack_evidence_does_not_publish_an_incomplete_runtime(self):
        source=runtime_snapshot.compilation_inputs(self.root).runtime
        destination=self.base/'incomplete-runtime'
        with self.assertRaisesRegex(ProductionError,'RECORD_NOT_FOUND'):
            runtime_snapshot.capture_compilation(source,destination,
                target={'model_id':fixtures.MODEL_ID,'offering':{'service':'synthetic'}},
                package={'input_snapshots':{'@pack/'+fixtures.PACK_ID+'/resources/missing.json':{}}},
                reading_resources={})
        self.assertFalse(destination.exists())

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
        self.assertEqual(payload['selection'], {'enabled_packs': sorted([COMMONS, fixtures.PACK_ID]),
                                                'pack_order':[fixtures.PACK_ID,COMMONS]})
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

    def test_existing_enabled_pack_cannot_redirect_a_used_resource(self):
        extra=self.base/'runtime/packs/extra'
        shutil.copytree(MINIMAL_PACK,extra)
        ident=self.enable(extra)
        run=workflow.prepare(self.root,'task.json')['run']
        manifest=c.load(extra/'pack.json')
        manifest['dependencies']=[{'pack_id':fixtures.PACK_ID}]
        manifest['content'].update(resource_globs=['resources/**/*'],
            resource_bindings={'service-profiles':'resources/services.json'})
        fixtures.write(extra/'pack.json',manifest)
        (extra/'resources').mkdir()
        shutil.copy2(self.case['pack']/'resources/services.json',extra/'resources/services.json')
        rows=self.diagnostics(run)
        changed=[row for row in rows if row['code']=='PACK_SELECTION_CHANGED' and row['severity']=='error']
        self.assertEqual([(row['pack'],row['resource']) for row in changed],[(ident,['service-profiles'])])
        self.assertEqual(changed[0]['actual'],{'pack':ident,'path':'resources/services.json'})

    def test_current_selection_ignores_changes_to_unused_resource_names(self):
        extra=self.base/'runtime/packs/extra'
        shutil.copytree(MINIMAL_PACK,extra)
        self.enable(extra)
        run=workflow.prepare(self.root,'task.json')['run']
        manifest=c.load(extra/'pack.json')
        manifest['content'].update(resource_globs=['resources/**/*'],
            resource_bindings={'unrelated-notes':'resources/notes.txt'})
        fixtures.write(extra/'pack.json',manifest)
        fixtures.write(extra/'resources/notes.txt','Only an unused authored resource changed.\n')
        self.assertEqual(self.codes(run),[])

    def test_pack_order_is_an_explicit_fixed_selection_contract(self):
        payload=runtime_snapshot.read(runtime_snapshot.path(self.root,self.descriptor),self.descriptor)
        original=[fixtures.PACK_ID,COMMONS]
        changed=[COMMONS,fixtures.PACK_ID]
        self.assertEqual(payload['selection']['pack_order'],original)
        state=c.load(self.case['settings'].state_file)
        state['pack_order']=changed
        pack_manager.save_state(self.case['settings'].state_file,state)
        rows=[row for row in self.diagnostics() if row.get('resource')=='pack_order']
        self.assertEqual([(row['code'],row['severity'],row['expected'],row['actual']) for row in rows],
            [('PACK_SELECTION_CHANGED','error',original,changed)])
        self.assertIn('retarget',[action['operation'] for action in rows[0]['actions']])

    def test_equal_unordered_used_resources_keep_the_existing_selected_source(self):
        extra=self.base/'runtime/packs/extra'
        shutil.copytree(MINIMAL_PACK,extra)
        manifest=c.load(extra/'pack.json')
        manifest['pack_id']='019a0290-1234-789a-8123-0123456789ac'
        fixtures.write(extra/'pack.json',manifest)
        self.enable(extra)
        run=workflow.prepare(self.root,'task.json')['run']
        manifest=c.load(extra/'pack.json')
        self.assertGreater(manifest['pack_id'],fixtures.PACK_ID)
        manifest['content'].update(resource_globs=['resources/**/*'],
            resource_bindings={'service-profiles':'resources/services.json'})
        fixtures.write(extra/'pack.json',manifest)
        (extra/'resources').mkdir()
        shutil.copy2(self.case['pack']/'resources/services.json',extra/'resources/services.json')
        self.assertEqual(self.codes(run),[])

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
        self.assertIn(ident,payload['selection']['enabled_packs'])
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
        from collections import Counter
        decision_file = decisions(self.root, self.run)
        bound = {((self.case['pack'] if row['pack'] == fixtures.PACK_ID else ROOT / 'packs' / 'commons') / row['path']).resolve()
                 for row in runtime_snapshot.dependencies(self.descriptor['binding'])}
        live_roots = (self.case['pack'].resolve(), (ROOT / 'packs' / 'commons').resolve())
        hashed, rescans, boundaries = [], [], []
        active=None
        original = store.stable_bytes
        original_pack = pack_manager.sha256_file
        original_current=runtime_snapshot.require_current_read
        def counted(root,relative,*args,**kwargs):
            resolved = (Path(root)/relative).resolve()
            if any(root in resolved.parents for root in live_roots):
                hashed.append(resolved)
                if active is not None:active.append(resolved)
            return original(root,relative,*args,**kwargs)
        def counted_pack(path):
            rescans.append(path)
            return original_pack(path)
        def current_boundary(*args,**kwargs):
            nonlocal active
            previous=active
            active=[]
            boundaries.append(active)
            try:return original_current(*args,**kwargs)
            finally:active=previous
        with patch.dict(os.environ, {'CPB_HOME': str(self.base / 'home')}), \
             patch.object(store, 'stable_bytes', side_effect=counted), \
             patch.object(pack_manager, 'sha256_file', side_effect=counted_pack), \
             patch.object(runtime_snapshot,'require_current_read',side_effect=current_boundary):
            operation, token = self.operation('bounded-execute')
            try:
                result = execution.execute(self.root, self.run, decisions_file=decision_file)
            finally:
                operation.finish(0)
                operations._CURRENT.reset(token)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(rescans, [])
        self.assertTrue(set(hashed) <= bound, set(hashed) - bound)
        # Every actual current-input boundary owns one pass over exactly the
        # bound live files. A separate boolean comparison cache must not hide
        # an intervening edit from a later transaction or returned status.
        self.assertTrue(boundaries)
        self.assertEqual(sum(map(len,boundaries)),len(hashed))
        for boundary in boundaries:
            self.assertEqual(Counter(boundary),Counter({path:1 for path in bound}))


class ForcedReadBoundaryTests(unittest.TestCase):
    def test_failed_pack_discovery_force_cannot_reuse_the_previous_comparison(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_file = root / 'synthetic-pack-state.json'
            state_file.write_bytes(b'{}')
            descriptor = {'sha256': 'e' * 64, 'binding': {}, 'settings': {}}
            with runtime_snapshot.public_call(), patch.object(runtime_snapshot, 'acquire_runtime', return_value=SimpleNamespace(payload={})), \
                 patch.object(runtime_snapshot, 'settings_from', return_value=SimpleNamespace(state_file=state_file)), \
                 patch.object(pack_manager, 'pack_cli_command', return_value='synthetic command'):
                with patch.object(runtime_snapshot, '_compare', return_value=[]):
                    self.assertEqual(runtime_snapshot.current_diagnostics(root, descriptor), [])
                with patch.object(runtime_snapshot, '_compare', side_effect=OSError('Synthetic discovery failure')):
                    with self.assertRaisesRegex(OSError, 'Synthetic discovery failure'):
                        runtime_snapshot.current_diagnostics(root, descriptor, force=True)
                    with self.assertRaisesRegex(OSError, 'Synthetic discovery failure'):
                        runtime_snapshot.current_diagnostics(root, descriptor)

    def test_failed_source_force_cannot_reuse_the_previous_success(self):
        import route_reading
        from production_read_model import RunSnapshot
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'synthetic.txt'
            source.write_bytes(b'original synthetic source')
            prepared = {'envelope_sha256': 'e' * 64, 'route_reading': {},
                        'task': {'route': 'synthetic', 'features': []},
                        'dependencies': [{'space': 'studio', 'path': source.name, 'sha256': c.sha256_file(source)}]}
            loaded = RunSnapshot(root, prepared, {}, [])
            with runtime_snapshot.public_call(), patch.object(workflow, 'read_run', return_value=loaded), \
                 patch.object(route_reading, 'require_route_reading'):
                workflow.assert_current(root, 'synthetic-run')
                source.write_bytes(b'changed synthetic source')
                with self.assertRaisesRegex(ProductionError, 'SOURCE_CHANGED'):
                    workflow.assert_current(root, 'synthetic-run', force=True)
                with self.assertRaisesRegex(ProductionError, 'SOURCE_CHANGED'):
                    workflow.assert_current(root, 'synthetic-run')

    def test_failed_registration_force_cannot_return_the_previous_run(self):
        from execution_lifecycle import ReplayState
        from production_compiler import write_manifest
        from production_read_model import RunReader
        from publication_artifacts import ArtifactSet
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = 'synthetic-run'
            directory = root / 'production' / 'runs' / run
            directory.mkdir(parents=True)
            prepared = {'task': {'task_id': 'synthetic-task', 'production_id': 'synthetic-production',
                                 'execution': 'conversation'},
                        'input_sha256': 'a' * 64, 'envelope_sha256': 'b' * 64}
            artifacts = ArtifactSet(directory)
            artifacts.write('prepared.json', c.encoded(prepared))
            artifacts.write('consumer.json', c.encoded({'synthetic': True}))
            write_manifest(directory, artifacts)
            store.register_run(root, run, prepared, directory)
            reader = RunReader(root, lambda *args: None,
                               lambda run, prepared, *args: ReplayState(prepared, run))
            with runtime_snapshot.public_call():
                self.assertEqual(reader.read(run).prepared, prepared)
                # A separate connection has no access to the caller's cache,
                # just as a different process cannot invalidate it directly.
                with closing(sqlite3.connect(store.database(root))) as connection, connection:
                    connection.execute('DELETE FROM runs WHERE run_id=?', (run,))
                with self.assertRaisesRegex(ProductionError, 'RUN_NOT_REGISTERED'):
                    reader.read(run, force=True)
                with self.assertRaisesRegex(ProductionError, 'RUN_NOT_REGISTERED'):
                    reader.read(run)


class TransactionScopeTests(unittest.TestCase):
    def test_concurrent_transactions_have_independent_read_boundaries(self):
        import concurrent.futures
        import threading
        count = 8
        start = threading.Barrier(count)
        with tempfile.TemporaryDirectory() as temp:
            def open_scope(index):
                root = Path(temp) / str(index)
                with store.transaction(root) as connection:
                    scope = runtime_snapshot.check_scope(root)
                    scope['owner'] = index
                    start.wait(timeout=20)
                    self.assertIs(runtime_snapshot.check_scope(root), scope)
                    self.assertEqual(scope['owner'], index)
                    self.assertEqual(set(runtime_snapshot._TRANSACTIONS.get()), {id(connection)})
                self.assertEqual(runtime_snapshot._TRANSACTIONS.get(), {})
                return scope
            with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                scopes = list(pool.map(open_scope, range(count)))
        self.assertEqual(len({id(scope) for scope in scopes}), count)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
