"""Preparation carries checked inputs and writes each final document once."""
from __future__ import annotations

from collections import Counter
import copy
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import execution_contract as c
import production_compiler as compiler
import production_store as store
from publication_artifacts import StagedArtifacts


FINAL_DOCUMENTS = {
    'execution-plan.json', 'package.json', 'request-contract.json', 'request-preview.json',
}


class EvidenceRootsTests(unittest.TestCase):
    def test_named_input_roots_use_catalog_ownership_without_scanning_records(self):
        import runtime_evidence
        from catalog_retrieval import runtime

        class UnusedRecords:
            def __iter__(self):
                raise AssertionError('input roots do not depend on catalog record count')

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            pack_root = root / 'pack'
            pack_root.mkdir()
            catalog = SimpleNamespace(entries=UnusedRecords(), pack_roots={'synthetic-pack': pack_root})
            with patch.object(runtime, 'load_pack_catalog', return_value=catalog):
                reader = runtime_evidence.reader(root)
            self.assertIs(reader.named_roots['@pack/synthetic-pack'], pack_root)
            self.assertEqual(reader.named_roots['@skill'], runtime_evidence.ROOT)


class EvidenceAcquisitionTests(unittest.TestCase):
    def test_owned_evidence_has_no_live_reader_and_new_acquisition_reads_new_bytes(self):
        from input_evidence import EvidenceAcquisition
        raw=b'{"items":["first"]}'
        calls=[]

        def source(path):
            calls.append(path)
            return raw

        acquired=EvidenceAcquisition(None,read_source=source)
        ref=acquired.select('@pack/synthetic/contract.json')
        document=acquired.json(ref)
        self.assertIs(acquired.at(ref).json(ref),document)
        owned=acquired.finish()
        raw=b'{"items":["other"]}'
        self.assertEqual(owned.read(ref),b'{"items":["first"]}')
        self.assertIs(owned.at(ref).json(ref),document)
        with self.assertRaisesRegex(TypeError,'read-only'):
            document['items'].append('changed')
        self.assertEqual(calls,['@pack/synthetic/contract.json'])
        fresh=EvidenceAcquisition(None,read_source=source)
        replacement=fresh.select(ref['path'])
        self.assertNotEqual(replacement['sha256'],ref['sha256'])
        self.assertEqual(fresh.json(replacement)['items'],['other'])
        self.assertEqual(len(calls),2)

    def test_failed_acquisition_cannot_export_a_partial_success(self):
        from input_evidence import EvidenceAcquisition
        acquired=EvidenceAcquisition(None,read_source=lambda path:b'{"ok":true}')
        selected=acquired.select('@pack/synthetic/contract.json')
        with self.assertRaisesRegex(ValueError,'bytes differ'):
            acquired.read({**selected,'sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'failed input acquisition'):
            acquired.finish()
        fresh=EvidenceAcquisition(None,read_source=lambda path:b'{"ok":true}')
        self.assertEqual(fresh.json(fresh.select(selected['path'])),{'ok':True})


class CompilationInputsTests(unittest.TestCase):
    def setUp(self):
        import production_case_fixtures as fixtures
        import production_fixtures
        from catalog_retrieval import runtime

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.enterContext(production_fixtures.scratch_home(self.base / 'home'))
        self.addCleanup(runtime.configure_pack_runtime, None)
        self.case = fixtures.create(self.base / 'studio', self.base / 'runtime', with_alternate=True)
        self.root = self.case['root']

    def observe_writes(self):
        writes = Counter()
        original = StagedArtifacts.write

        def write(owner, path, raw, **kwargs):
            writes[str(path)] += 1
            return original(owner, path, raw, **kwargs)

        self.enterContext(patch.object(StagedArtifacts, 'write', write))
        return writes

    def test_prepare_publishes_one_canonical_copy_of_each_document(self):
        import production_workflow as workflow
        import production_case_fixtures as fixtures
        import request_contract

        task = c.load(self.root / 'task.json')
        retrieval_path = c.local(self.root, task['generation']['retrieval_record'])
        retrieval = c.load(retrieval_path)
        retrieval['elements'][0]['inspected_records'] = [fixtures.ALTERNATE_MODEL_ID]
        fixtures.write(retrieval_path, retrieval)
        writes = self.observe_writes()
        result = workflow.prepare(self.root, 'task.json')
        self.assertEqual({name: writes[name] for name in FINAL_DOCUMENTS},
                         {name: 1 for name in FINAL_DOCUMENTS})
        directory = workflow.run_dir(self.root, result['run'])
        prepared = c.load(directory / 'prepared.json')
        package = c.load(directory / 'package.json')
        rendered = c.load(directory / 'request-contract.json')
        request_contract.validate_seal(rendered)
        self.assertEqual(prepared['compiled']['package_sha256'], c.sha256_file(directory / 'package.json'))
        self.assertEqual(prepared['compiled']['plan_sha256'], c.sha256_file(directory / 'execution-plan.json'))
        self.assertEqual(result['request_preview'], rendered['request'])
        binding = prepared['runtime_snapshot']['binding']
        pinned_records = {row['id'] for row in binding['records']}
        self.assertIn(fixtures.ALTERNATE_MODEL_ID, pinned_records)
        self.assertEqual(next(row['role'] for row in binding['records']
                              if row['id'] == fixtures.ALTERNATE_MODEL_ID), 'retrieval')
        self.assertEqual({row['locator'] for row in binding['evidence']},
                         {name for name in package['input_snapshots'] if name.startswith('@pack/')})

    def test_check_returns_complete_values_without_writing_final_documents(self):
        writes = self.observe_writes()
        report = compiler.check_task(self.root, 'task.json')
        self.assertTrue(report['publishable'], report['diagnostics'])
        self.assertEqual({name: writes[name] for name in FINAL_DOCUMENTS},
                         {name: 0 for name in FINAL_DOCUMENTS})
        self.assertEqual(report['request_preview'], report['execution_plan']['request'])
        self.assertIsNone(report['execution_plan']['run'])
        self.assertEqual(store.runs(self.root), [])

    def test_builder_receives_immutable_checked_inputs_and_preview_stays_editable(self):
        import build_generation_payload as builder

        build = builder.acquire_generation
        supplied = {}

        def inspect(inputs,**kwargs):
            values=inputs.values
            supplied.update(specification=values['production_spec'], plot=values['plot'])
            with self.assertRaisesRegex(TypeError, 'read-only'):
                values['production_spec']['render_intent']['axes']['medium'] = 'changed after checking'
            with self.assertRaisesRegex(TypeError, 'read-only'):
                values['plot']['approved']['by'] = 'changed after checking'
            supplied['original'] = copy.deepcopy(values['production_spec'])
            return build(inputs,**kwargs)

        with patch.object(builder, 'acquire_generation', side_effect=inspect):
            report = compiler.check_task(self.root, 'task.json')
        self.assertTrue(report['publishable'], report['diagnostics'])
        report['request_preview']['prompt'] = 'An independently edited preview.'
        report['execution_plan']['validation']['target']['service'] = 'edited-service'
        self.assertEqual(supplied['specification'], supplied['original'])
        self.assertEqual(c.load(self.root / self.case['task']['generation']['production_spec']), supplied['original'])

    def test_direct_compilation_exports_an_independently_verifiable_package(self):
        import build_generation_payload as builder
        import verify_generation_payload as verifier

        with patch.object(verifier,'verify',side_effect=AssertionError('internal compilation must consume its domain result')):
            compiled=compiler.compile_task(self.root,'task.json')
        self.assertTrue(compiled.report['publishable'],compiled.report['diagnostics'])
        self.addCleanup(shutil.rmtree,compiled.directory,ignore_errors=True)
        verified=verifier.verify(compiled.package,package_root=compiled.directory,studio=self.root,
                                 reading_ledgers=[compiled.directory/'reads.jsonl'])
        self.assertTrue(verified['verified'])
        self.assertEqual(verified['generation_input_sha256'],compiled.package['generation_input_sha256'])
        changed=copy.deepcopy(compiled.package)
        changed['plot']['approved']['by']=''
        changed['plot_sha256']=builder.sha256_json(changed['plot'])
        changed['generation_contract']['plot_sha256']=changed['plot_sha256']
        digest=builder.generation_input_sha256(changed)
        changed['generation_input_sha256']=digest
        changed['generation_contract']['generation_input_sha256']=digest
        with self.assertRaisesRegex(ValueError,'approv|plot|by'):
            verifier.verify(changed,package_root=compiled.directory,studio=self.root,
                            reading_ledgers=[compiled.directory/'reads.jsonl'])

    def test_failed_request_does_not_capture_runtime_or_publish_and_retry_is_fresh(self):
        import request_renderer
        import runtime_snapshot

        with patch.object(request_renderer,'generation_from_inputs',side_effect=ValueError('late request rejection')):
            with patch.object(runtime_snapshot,'capture_compilation',side_effect=AssertionError('failed meaning cannot be captured')):
                failed=compiler.check_task(self.root,'task.json')
        self.assertFalse(failed['publishable'])
        self.assertTrue(any('late request rejection' in row['message'] for row in failed['diagnostics']))
        self.assertEqual(store.runs(self.root),[])
        retried=compiler.check_task(self.root,'task.json')
        self.assertTrue(retried['publishable'],retried['diagnostics'])

    def test_public_package_builder_uses_the_same_schema_bytes_as_its_evidence(self):
        import build_generation_payload as builder
        import pack_manager
        import production_case_fixtures as fixtures
        import request_validation
        import runtime_evidence
        import service_profile
        import transport_synthetic
        from catalog_retrieval import runtime
        from input_evidence import InputEvidence
        from visual_fixtures import fixture_visual

        models_path=self.case['pack']/'records/models.json'
        models=c.load(models_path)
        model=models['records'][0]
        offering=model['offerings'][0]
        offering['schema_snapshot']='resources/parameter-schema.json'
        schema={'artifact_type':'observed-parameter-schema','model_id':model['id'],
                'service':offering['service'],'model_identifier':offering['model_identifier'],
                'observed_at':offering['observed_at'],'source':'Synthetic acquired parameter schema',
                'schema':{'type':'object','properties':{'width':{'const':32}}}}
        schema_path=self.case['pack']/offering['schema_snapshot']
        fixtures.write(models_path,models)
        fixtures.write(schema_path,schema)
        pack_manager.write_lock(self.case['pack'])
        runtime.configure_pack_runtime(self.case['settings'])
        service=service_profile.load_service('synthetic',self.case['pack']/'resources/services.json')
        validation=request_validation.from_offering(model['id'],model,offering,service,transport_synthetic,
                                                     runtime_evidence.reader(self.root))
        specification=c.load(self.root/'spec.json')
        visual=fixture_visual(specification,root=self.root)
        acquire=runtime_evidence.acquisition

        def change_live_schema(*args,**kwargs):
            evidence=acquire(*args,**kwargs)
            changed=copy.deepcopy(schema)
            changed['schema']['properties']['width']['const']=64
            fixtures.write(schema_path,changed)
            return evidence

        with patch.object(runtime_evidence,'acquisition',side_effect=change_live_schema):
            package=builder.build_payload(execution=self.case['task']['execution'],model=model['id'],prompt=fixtures.PROMPT,negative_prompt='',brief='',
                creative_intent=c.load(self.root/'creative-intent.json'),parameters=c.load(self.root/'parameters.json'),
                production_spec=specification,plot=c.load(self.root/'plot.json'),
                retrieval_record=c.load(self.root/'retrieval.json'),visual_continuity=visual,
                visual_root=self.root,input_root=self.root,production_root=self.root,
                route_reading=c.load(self.root/'reading.json'),request_validation=validation,service='synthetic')

        captured=InputEvidence._decode(package['input_snapshots'][validation['contract']['path']])
        self.assertEqual(c.decode(captured),schema)
        self.assertEqual(package['generation_payload']['parameters']['width'],32)
        self.assertEqual(c.load(schema_path)['schema']['properties']['width']['const'],64)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
